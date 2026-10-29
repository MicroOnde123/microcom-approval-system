"""Optional links only; never invokes the physical-return operation."""
from django import template
from invoicing.return_note_access import navigation

register = template.Library()


@register.simple_tag
def return_note_links(user, request_id):
    return navigation(user, request_id=request_id)
