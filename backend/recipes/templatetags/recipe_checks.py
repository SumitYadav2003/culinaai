from django import template

from recipes.check_summary import summarise_checks

register = template.Library()


@register.filter
def check_summary(report):
    """{% with summary=report|check_summary %} for the one-line check summary."""
    return summarise_checks(report)
