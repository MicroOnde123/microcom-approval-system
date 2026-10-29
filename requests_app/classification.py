"""Classification persistence, called only inside the locked approval service."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from inventory.models import Succursale
from .models import Request, RequestAuditLog


@transaction.atomic
def confirm_classification(request, user, classification, succursale):
    if not user.is_active:
        raise ValidationError(_("You are not allowed to approve this step."))
    if classification not in Request.Classification.values:
        raise ValidationError(_("Select Client or Microcom to approve the stock review."))
    branch = None
    if classification == Request.Classification.MICROCOM:
        try:
            branch = Succursale.objects.select_for_update().get(pk=getattr(succursale, "pk", succursale), is_active=True)
        except (Succursale.DoesNotExist, TypeError, ValueError):
            raise ValidationError(_("Select an active succursale for a Microcom request."))
    elif succursale is not None:
        raise ValidationError(_("Client requests must not select a succursale."))
    previous = request.classification or "-"
    previous_branch = request.succursale_id or "-"
    request.classification = classification
    request.succursale = branch
    request.classified_by = user
    request.classified_at = timezone.now()
    request.save(update_fields=["classification", "succursale", "classified_by", "classified_at"])
    RequestAuditLog.objects.create(request=request, action="STOCK_CLASSIFIED", performed_by=user,
        comment=_("Classification confirmed: %(classification)s; succursale: %(succursale)s. Previous classification: %(previous)s; previous succursale: %(previous_succursale)s.") % {
            "classification": classification, "succursale": str(branch) if branch else "-",
            "previous": previous, "previous_succursale": previous_branch})
