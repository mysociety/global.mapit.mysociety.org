from __future__ import unicode_literals

from contextlib import contextmanager
from mock import Mock, patch
import os
from os.path import join, dirname
import re

from django.core.management import call_command
from django.test import TestCase

from mapit.models import Area, CodeType, Country, Generation, Type

from .mkdtemp_contextmanager import TemporaryDirectory


def get_example_kml(tags, include_big_square=False, include_big_square_with_hole=False, include_small_square=False):
    polygons = [
        (
            include_big_square, '''
            <Polygon>
              <outerBoundaryIs>
                <LinearRing>
                  <coordinates>0,53,0  4,53,0  4,49,0  0,49,0  0,53,0 </coordinates>
                </LinearRing>
              </outerBoundaryIs>
            </Polygon>
'''),
        (
            include_big_square_with_hole, '''
            <Polygon>
              <outerBoundaryIs>
                <LinearRing>
                  <coordinates>0,53,0  4,53,0  4,49,0  0,49,0  0,53,0 </coordinates>
                </LinearRing>
              </outerBoundaryIs>
              <innerBoundaryIs>
                <LinearRing>
                  <coordinates>1,52,0  3,52,0  3,50,0  1,50,0  1,52,0 </coordinates>
                </LinearRing>
              </innerBoundaryIs>
            </Polygon>
'''),
        (
            include_small_square, '''
            <Polygon>
              <outerBoundaryIs>
                <LinearRing>
                  <coordinates>-3,52,0  -2,52,0  -2,51,0  -3,51,0  -3,52,0 </coordinates>
                </LinearRing>
              </outerBoundaryIs>
            </Polygon>
''')
    ]
    polygons_xml = ''.join(p for include, p in polygons if include)
    tags_xml = ''.join(
        '''
            <Data name="{key}">
              <value>{value}</value>
            </Data>
'''.format(key=k, value=v)
        for k, v in
        sorted(tags.items())
    )
    name = 'Exampleshire'
    if 'name' in tags:
        name = tags['name']
    return '''<?xml version='1.0' encoding='utf-8'?>
    <kml xmlns="http://earth.google.com/kml/2.1">
      <Folder>
        <name>Boundaries for {name} [relation XXXXXX]</name>
        <Placemark>
          <name>{name}</name>
          <ExtendedData>
{tags_xml}
          </ExtendedData>
          <MultiGeometry>
{polygons_xml}
          </MultiGeometry>
        </Placemark>
      </Folder>
   </kml>'''.format(tags_xml=tags_xml, polygons_xml=polygons_xml, name=name)


@contextmanager
def example_files(type_code, file_data):
    with TemporaryDirectory() as tmp_dir:
        type_dir = join(tmp_dir, type_code)
        os.makedirs(type_dir)
        for leafname, contents in file_data:
            with open(join(type_dir, leafname), 'w') as f:
                f.write(contents)
        yield tmp_dir


def fake_get(url, **kwargs):
    if url != 'http://www.loc.gov/standards/iso639-2/ISO-639-2_utf-8.txt':
        raise Exception("The URL {url} hasn't been faked")
    local_filename = join(dirname(__file__), 'country-data', 'ISO-639-2_utf-8.txt')
    fake_response = Mock()
    fake_response.iter_lines.return_value = open(local_filename, 'rb')
    return fake_response


class ImportCommandTests(TestCase):

    def change_to_repo_root(self):
        os.chdir(join(dirname(__file__), '..', '..'))

    def setUp(self):
        # The import command actually changes directory, so make sure
        # we change back to the repository root before each test.
        self.change_to_repo_root()
        # Make sure requests.get is patched in every tests in this class.
        self.patcher = patch('mapit_global.management.commands.mapit_global_import.requests')
        self.mock_requests = self.patcher.start()
        self.mock_requests.get = fake_get
        self.addCleanup(self.patcher.stop)

    def test_fixtures_loaded(self):
        call_command('loaddata', 'global.json')
        assert Country.objects.filter(code='G').exists()
        assert CodeType.objects.filter(code='osm_rel').exists()
        assert CodeType.objects.filter(code='osm_way').exists()
        assert Type.objects.filter(code='OCL').exists()
        assert Type.objects.filter(code='O02').exists()
        assert Type.objects.filter(code='O10').exists()

    def test_import_two_files(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'foo': 'bar',
                          'name:fr': 'Le Ambridge'},
                         include_big_square_with_hole=True)),
                    ('relation-5678-unknown.kml',
                     get_example_kml(
                         {'name': 'Borchester', 'baz': 'quux'},
                         include_small_square=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        assert Area.objects.count() == 2
        area_a, area_b = list(Area.objects.all())
        # Check their names:
        assert area_a.name == 'Ambridge'
        assert area_b.name == 'Borchester'
        # Check that the right tags were imported:
        assert list(area_a.codes.values_list('type__code', 'code')) == \
            [('osm_way', '1234')]
        assert list(area_a.names.values_list('type__code', 'name')) == \
            [('default', 'Ambridge'), ('fr', 'Le Ambridge')]
        assert list(area_b.codes.values_list('type__code', 'code')) == \
            [('osm_rel', '5678')]
        assert list(area_b.names.values_list('type__code', 'name')) == \
            [('default', 'Borchester')]
        # Check that the right number of polygons exist for both areas:
        assert area_a.polygons.count() == 1
        assert area_b.polygons.count() == 1
        # Check that the generation high and low are as expected:
        new_generation = Generation.objects.new()
        assert area_a.generation_high == new_generation
        assert area_b.generation_high == new_generation
        assert area_a.generation_low == new_generation
        assert area_b.generation_low == new_generation

    def test_nothing_imported_without_commit(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge', 'foo': 'bar'},
                         include_big_square_with_hole=True)),
                    ('relation-5678-unknown.kml',
                     get_example_kml(
                         {'name': 'Borchester', 'baz': 'quux'},
                         include_small_square=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', tmp_dir)
        assert Area.objects.count() == 0

    def test_update_nothing_changed(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'foo': 'bar',
                          'name:fr': 'Le Ambridge'},
                         include_big_square_with_hole=True)),
                    ('relation-5678-unknown.kml',
                     get_example_kml(
                         {'name': 'Borchester', 'baz': 'quux'},
                         include_small_square=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
            # Activate that generation, create a new one and import the same data:
            call_command('mapit_generation_activate', '--commit')
            call_command('mapit_generation_create', '--commit', '--desc=Second import')
            call_command('mapit_global_import', '--commit', tmp_dir)

        assert Area.objects.count() == 2
        area_a, area_b = list(Area.objects.all())
        # Check their names:
        assert area_a.name == 'Ambridge'
        assert area_b.name == 'Borchester'
        # Check that the right tags were imported:
        assert list(area_a.codes.values_list('type__code', 'code')) == \
            [('osm_way', '1234')]
        assert sorted(area_a.names.values_list('type__code', 'name')) == \
            [('default', 'Ambridge'), ('fr', 'Le Ambridge')]
        assert list(area_b.codes.values_list('type__code', 'code')) == \
            [('osm_rel', '5678')]
        assert list(area_b.names.values_list('type__code', 'name')) == \
            [('default', 'Borchester')]
        # Check that the right number of polygons exist for both areas:
        assert area_a.polygons.count() == 1
        assert area_b.polygons.count() == 1
        first_generation, second_generation = list(Generation.objects.order_by('id'))
        assert area_a.generation_low == first_generation
        assert area_b.generation_low == first_generation
        assert area_a.generation_high == second_generation
        assert area_b.generation_high == second_generation

    def test_add_ref_code(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'ref': 'source:ABC'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        area = Area.objects.get()
        # Check that the ref code is present:
        assert sorted(area.codes.values_list('type__code', 'code')) == \
            [('osm_attr_ref', 'source:ABC'), ('osm_way', '1234')]

    def test_remove_ref_code(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'ref': 'source:ABC'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        # Activate that generation, create a new one and import the same data:
        call_command('mapit_generation_activate', '--commit')
        call_command('mapit_generation_create', '--commit', '--desc=Second import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        area = Area.objects.get()
        assert sorted(area.codes.values_list('type__code', 'code')) == \
            [('osm_way', '1234')]

    def test_change_ref_code(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'ref': 'source:ABC'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        # Activate that generation, create a new one and import the same data:
        call_command('mapit_generation_activate', '--commit')
        call_command('mapit_generation_create', '--commit', '--desc=Second import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'ref': 'source:XYZ'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        area = Area.objects.get()
        assert sorted(area.codes.values_list('type__code', 'code')) == \
            [('osm_attr_ref', 'source:XYZ'), ('osm_way', '1234')]

    def test_alter_current_generation_fail_on_changed_boundary(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'ref': 'source:ABC'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        # Activate that generation, create a new one and import the same data:
        call_command('mapit_generation_activate', '--commit')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'ref': 'source:ABC'},
                         include_big_square=True)),
                ]
        ) as tmp_dir:
            area = Area.objects.get()
            current_generation = Generation.objects.current()
            expected_msg = (
                'The area for 1234 (osm_way) [{area_id}] already existed with '
                'a different boundary in the current generation; using '
                '--alter-current-generation to import this data would result '
                'in a duplicate area in Generation {current_generation_id} '
                '(active)').format(
                    area_id=area.id,
                    current_generation_id=current_generation.id)
            with self.assertRaisesRegexp(
                    Exception,
                    re.escape(expected_msg)):
                call_command('mapit_global_import', '--commit', '--alter-current-generation', tmp_dir)

    def test_alter_current_generation_change_metadata(self):
        call_command('loaddata', 'global.json')
        call_command('mapit_generation_create', '--commit', '--desc=Initial import')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'Ambridge',
                          'ref': 'source:ABC'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', tmp_dir)
        # Activate that generation, create a new one and import the same data:
        call_command('mapit_generation_activate', '--commit')
        with example_files(
                'OCL',
                [
                    ('way-1234-ambridge.kml',
                     get_example_kml(
                         {'name': 'New Ambridge',
                          'name:fr': 'Nouveau Ambridge',
                          'ref': 'source:XYZ'},
                         include_big_square_with_hole=True)),
                ]
        ) as tmp_dir:
            call_command('mapit_global_import', '--commit', '--alter-current-generation', tmp_dir)
        area = Area.objects.get()
        assert sorted(area.codes.values_list('type__code', 'code')) == \
            [('osm_attr_ref', 'source:XYZ'), ('osm_way', '1234')]
        assert list(area.names.values_list('type__code', 'name')) == \
            [('default', 'New Ambridge'), ('fr', 'Nouveau Ambridge')]
