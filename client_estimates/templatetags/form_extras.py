# client_estimates/templatetags/form_extras.py

from django import template

register = template.Library()

@register.filter
def get_field(form, field_name):
    """
    Allows template usage like:
    {{ form|get_field:"field_name" }}
    """
    return form[field_name]


@register.filter
def wizard_step(fieldset):
    """
    Extracts the wizard step from a fieldset (default 1).
    """
    classes = getattr(fieldset, "classes", []) or []
    if isinstance(classes, str):
        classes = classes.split()
    for css_class in classes:
        if css_class.startswith("estimate-step-"):
            return css_class.replace("estimate-step-", "")
    return "1"


@register.simple_tag
def prefixed_field(form, prefix, identifier):
    """
    Returns a bound field whose name is composed of prefix + identifier.
    """
    field_name = f"{prefix}{identifier}"
    try:
        return form[field_name]
    except KeyError:
        return ""


@register.simple_tag
def meal_field(form, prefix, item_id, meal_index):
    """
    Helper for dynamic meal checkbox fields (e.g. include_item_12_meal_0).
    """
    field_name = f"{prefix}_{item_id}_meal_{meal_index}"
    try:
        return form[field_name]
    except KeyError:
        return ""
