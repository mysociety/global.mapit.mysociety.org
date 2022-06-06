from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.functional import cached_property
from lxml import etree
import requests

from mapit.models import Area, Code, CodeType, Country, Generation


class Command(BaseCommand):

    OSM_COUNTRY_CODE_KEY = 'ISO3166-1'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--generation', required=True, type=int)

    @cached_property
    def generation_kwargs(self):
        return {
            'generation_low__lte': self.generation,
            'generation_high__gte': self.generation,
        }

    def set_country_codes_for_countries(self):
        country_areas_qs = Area.objects.filter(
            type__code='O02', **self.generation_kwargs)
        for area in country_areas_qs:
            area.codes.filter(type=self.iso_code_type).delete()
            code = area.codes.get(type__code__in=('osm_rel', 'osm_way'))
            osm_type = {
                'osm_rel': 'relation',
                'osm_way': 'way',
            }[code.type.code]
            api_url = 'http://api.openstreetmap.org/api/0.6/{0}/{1}'.format(osm_type, code.code)
            print('api_url:', api_url)
            r = requests.get(api_url)
            if r.status_code == 410:
                # We can get a "410 Gone" response if a relation or
                # way has been removed since the last import of
                # boundary data from OSM, in which case we should just
                # skip over that area.
                continue
            r.raise_for_status()
            root = etree.fromstring(r.content)
            tags = root.xpath('//tag[@k="{0}"]'.format(self.OSM_COUNTRY_CODE_KEY))
            if not tags:
                continue
            if len(tags) > 1:
                msg = 'More than one {0} tag found for {1}'
                raise Exception(msg.format(self.OSM_COUNTRY_CODE_KEY, area))
            country_code = tags[0].attrib['v']
            Code.objects.create(area=area, type=self.iso_code_type, code=country_code)

    def ensure_countries_exist(self):
        for code_object in self.iso_code_type.codes.select_related('area'):
            Country.objects.get_or_create(
                code=code_object.code,
                defaults={'name': code_object.area.name})
        Country.objects.get_or_create(
            code='?',
            defaults={'name': 'Multiple enclosing countries'})

    @cached_property
    def iso_code_type(self):
        return CodeType.objects.get_or_create(
            code='iso3166_1',
            defaults={'description': 'ISO3166-1 country code from OSM'})[0]

    def get_enclosing_country_codes(self, area):
        enclosing_country_codes = set()
        for polygon_object in area.polygons.all():
            point = polygon_object.polygon.point_on_surface
            # Now find the country-level areas that contain that point:
            for enclosing_country_area in Area.objects.filter(
                    type__code='O02',
                    codes__type=self.iso_code_type,
                    polygons__polygon__contains=point,
                    **self.generation_kwargs
            ):
                country_code_object = enclosing_country_area.codes.get(type=self.iso_code_type)
                enclosing_country_codes.add(country_code_object.code)
        return tuple(sorted(enclosing_country_codes))

    def get_countries_from_codes(self, country_codes):
        return [self.code_to_country[c] for c in country_codes]

    def set_country_on_all_areas(self):
        global_country = Country.objects.get(code='G')
        for area in Area.objects.filter(**self.generation_kwargs).iterator():
            print("Considering area:", area, area.id)
            enclosing_country_codes = self.get_enclosing_country_codes(area)
            countries = self.get_countries_from_codes(enclosing_country_codes)
            area.country = global_country
            area.countries.clear()
            area.countries.add(*countries)
            area.save()

    @cached_property
    def code_to_country(self):
        return {country.code: country for country in Country.objects.all()}

    def handle(self, **options):
        generation_id = options['generation']
        try:
            self.generation = Generation.objects.get(pk=generation_id)
        except Generation.DoesNotExist:
            raise CommandError('Couldn\'t find the generation {0}'.format(generation_id))

        with transaction.atomic():
            self.set_country_codes_for_countries()
            self.ensure_countries_exist()
            self.set_country_on_all_areas()
            if not options['commit']:
                raise Exception('Rolling back since --commit was not specified')
