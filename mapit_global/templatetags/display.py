import re

from django import template

register = template.Library()


@register.filter
def css_indent_class(area):
    """Get a CSS class for use on <li> representations of this area

    Currently this is only used to indicate the indentation level
    that should be used on the code types O02, O03, O04 ... O011,
    used by global MapIt.
    """
    m = re.search(r'^O([01][0-9])$', area.type.code)
    if m:
        return "area_level_%d" % int(m.group(1))
    else:
        return ""
