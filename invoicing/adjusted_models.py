"""Append-only adjusted valuation statements; never mutate source documents."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from .models import FinancialRecord, Invoice, DocumentSequence

class AdjustedInvoiceStatement(FinancialRecord):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='adjusted_statements')
    sequence = models.ForeignKey(DocumentSequence, on_delete=models.PROTECT, related_name='adjusted_statements')
    sequence_counter = models.PositiveBigIntegerField()
    number = models.CharField(max_length=100, unique=True)
    issued_at = models.DateTimeField()
    issue_date = models.DateField()
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issuer_name = models.CharField(max_length=300)
    operation_token = models.UUIDField(unique=True, editable=False)
    confirmation_digest = models.CharField(max_length=64)
    snapshot = models.JSONField()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(_('Issued adjusted statements are immutable.'))
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(_('Issued adjusted statements are immutable.'))

    class Meta:
        permissions = [('issue_adjustedinvoicestatement', _('Can issue adjusted invoice statements')),
                       ('document_adjustedinvoicestatement', _('Can print and download adjusted invoice statements'))]
        constraints = [models.UniqueConstraint(models.F('invoice'), models.Func(models.F('snapshot'), function='inv_as_state_key', output_field=models.CharField()), name='as_invoice_state_unique'),
                       models.UniqueConstraint(fields=['sequence','sequence_counter'], name='as_sequence_counter_unique'),
                       models.CheckConstraint(condition=models.Q(sequence_counter__gte=1), name='as_positive_counter')]
        ordering = ['-issued_at','-pk']
        verbose_name = _('Adjusted invoice statement')
