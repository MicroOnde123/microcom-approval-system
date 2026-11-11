"""Financial schema only. No number allocation, issuance or stock mutation API."""
from decimal import Decimal
import hashlib
import json
import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.document_config import Currency, validate_number_format
from .configuration import configuration_digest, validate_business_timezone


class GuardedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(_("Use individual financial records; bulk changes are prohibited."))

    def bulk_update(self, *args, **kwargs):
        raise ValidationError(_("Use individual financial records; bulk changes are prohibited."))

    def bulk_create(self, *args, **kwargs):
        raise ValidationError(_("Use individual financial records; bulk changes are prohibited."))

    def delete(self):
        raise ValidationError(_("Bulk financial deletion is prohibited."))


class FinancialRecord(models.Model):
    objects = GuardedQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, _finalize_at_statement_time=False, **kwargs):
        if _finalize_at_statement_time and (
                not isinstance(self, (Invoice, MaterialReturnNote)) or self._state.adding or self.status != "FINALIZED"):
            raise ValueError("Statement-time finalization requires an existing finalized-state invoice or material return note.")
        self._check_immutable()
        self.full_clean()
        if _finalize_at_statement_time:
            # Validate concrete values first. PostgreSQL evaluates Now() as
            # STATEMENT_TIMESTAMP() in the UPDATE, after all validation queries.
            # The existing trigger checks its window, then stamps clock_timestamp().
            self.finalized_at = Now()
        return super().save(*args, **kwargs)

    def _check_immutable(self):
        if not self.pk or self._state.adding:
            return
        old = type(self).objects.get(pk=self.pk)
        if isinstance(self, (CompanyVerification, InvoiceAuditEvent, DocumentArtifact, CreditOperation, CreditReservationAudit, MaterialReturnNoteAudit, MaterialReturnNoteArtifact)):
            raise ValidationError(_("Financial evidence is append-only."))
        document = old if isinstance(old, (Invoice, CreditNote, MaterialReturnNote)) else None
        if isinstance(old, InvoiceLine):
            document = old.invoice
        elif isinstance(old, InvoiceIssueAllocation):
            document = old.line.invoice
        elif isinstance(old, InvoiceReturnExclusion):
            document = old.issue_allocation.line.invoice
        elif isinstance(old, MaterialReturnNoteLine):
            document = old.note
        elif isinstance(old, CreditAllocation):
            if old.released_at:
                raise ValidationError(_("Released credit reservations are immutable."))
            document = old.credit_note
        if document and document.status == "FINALIZED":
            raise ValidationError(_("Finalized financial records cannot be changed."))

    def delete(self, *args, **kwargs):
        self._check_immutable()
        return super().delete(*args, **kwargs)


class CompanyVerification(FinancialRecord):
    configuration = models.ForeignKey("core.CompanyDocumentSettings", on_delete=models.PROTECT, verbose_name=_("Configuration"))
    administrator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Administrator"))
    verified_at = models.DateTimeField(_("Verified at"), auto_now_add=True)
    content_digest = models.CharField(max_length=64, editable=False, verbose_name=_("Content digest"))
    configuration_snapshot = models.JSONField(default=dict, verbose_name=_("Configuration snapshot"))

    class Meta:
        verbose_name = _("Company verification")
        verbose_name_plural = _("Company verifications")

    @classmethod
    @transaction.atomic
    def attest(cls, configuration, administrator):
        if not (administrator.is_active and administrator.is_staff and
                administrator.has_perm("invoicing.add_companyverification")):
            raise PermissionDenied(_("Administrator verification permission is required."))
        configuration = type(configuration).objects.select_for_update().get(pk=configuration.pk)
        configuration.full_clean()
        if not all(value.strip() for value in (configuration.company_name,
                   configuration.company_address, configuration.contact_details)):
            raise ValidationError(_("Complete the company name, address and contact details before verification."))
        return cls.objects.create(configuration=configuration, administrator=administrator,
            content_digest=configuration_digest(configuration),
            configuration_snapshot={field.name: getattr(configuration, field.attname)
                for field in configuration._meta.concrete_fields if field.name not in {"id", "updated_at"}})

    @property
    def is_current(self):
        configuration = type(self.configuration).objects.get(pk=self.configuration_id)
        return self.content_digest == configuration_digest(configuration)

    def clean(self):
        if self._state.adding:
            if not (self.administrator.is_active and self.administrator.is_staff and
                    self.administrator.has_perm("invoicing.add_companyverification")):
                raise ValidationError(_("Administrator verification permission is required."))
            if self.content_digest != configuration_digest(self.configuration):
                raise ValidationError(_("Company verification does not match the configuration."))
            if not all(value.strip() for value in (self.configuration.company_name,
                    self.configuration.company_address, self.configuration.contact_details)):
                raise ValidationError(_("Complete the company name, address and contact details before verification."))
            expected = {field.name: getattr(self.configuration, field.attname)
                for field in self.configuration._meta.concrete_fields if field.name not in {"id", "updated_at"}}
            if self.configuration_snapshot != expected:
                raise ValidationError(_("Company verification does not match the configuration."))


class DocumentSequence(FinancialRecord):
    class Kind(models.TextChoices):
        INVOICE = "INVOICE", _("Invoice")
        CREDIT = "CREDIT", _("Credit note")
        RETURN_NOTE = "RETURN_NOTE", _("Material return note")
        ADJUSTED = "ADJUSTED", _("Adjusted invoice statement")

    document_type = models.CharField(_("Document type"), max_length=11, choices=Kind.choices)
    year = models.PositiveIntegerField(_("Business year"))
    series = models.CharField(_("Series"), max_length=30, default="MAIN")
    number_format = models.CharField(_("Number format"), max_length=100, validators=[validate_number_format])
    starting_value = models.PositiveBigIntegerField(_("Starting counter"), default=1)
    next_counter = models.PositiveBigIntegerField(_("Next counter"), default=1)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Verified by"))
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Verified at"))
    verification_digest = models.CharField(max_length=64, blank=True, verbose_name=_("Verification digest"))
    verification_evidence = models.CharField(_("Numbering verification evidence"), max_length=250, blank=True)

    def configuration_digest(self):
        values = [self.document_type, self.year, self.series, self.number_format, self.starting_value]
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()

    @property
    def is_verified(self):
        return bool(self.verified_by_id and self.verified_at and self.verification_evidence and
                    self.verification_digest == self.configuration_digest())

    @transaction.atomic
    def attest(self, administrator, evidence):
        if not (administrator.is_active and administrator.is_staff and
                administrator.has_perm("invoicing.change_documentsequence")):
            raise PermissionDenied(_("Administrator verification permission is required."))
        if not evidence.strip():
            raise ValidationError(_("Record the external numbering-history verification evidence."))
        current = type(self).objects.select_for_update().get(pk=self.pk)
        current.verified_by = administrator
        current.verified_at = timezone.now()
        current.verification_evidence = evidence
        current.verification_digest = current.configuration_digest()
        current.save()
        self.refresh_from_db()

    def save(self, *args, **kwargs):
        if self.verification_digest and self.verification_digest != self.configuration_digest():
            self.verified_by = self.verified_at = None
            self.verification_digest = self.verification_evidence = ""
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Document sequence")
        verbose_name_plural = _("Document sequences")
        constraints = [
            models.UniqueConstraint(fields=["document_type", "series", "year"], name="inv_sequence_scope"),
            models.CheckConstraint(condition=Q(year__gte=1, year__lte=9999), name="inv_sequence_year"),
            models.CheckConstraint(condition=Q(starting_value__gte=1) & Q(next_counter__gte=models.F("starting_value")), name="inv_sequence_counter"),
            models.CheckConstraint(condition=(Q(verified_by__isnull=True, verified_at__isnull=True, verification_digest="") |
                (Q(verified_by__isnull=False, verified_at__isnull=False) & ~Q(verification_digest=""))), name="inv_sequence_attestation"),
        ]

    def clean(self):
        super().clean()
        # Annual references must expose the year; a different format/series can
        # still collide, so finalized full references have a separate unique key.
        if self.number_format and "{year" not in self.number_format:
            raise ValidationError({"number_format": _("Annual document formats must include {year}.")})


class FinancialDocument(FinancialRecord):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        FINALIZED = "FINALIZED", _("Finalized")

    status = models.CharField(_("Status"), max_length=10, choices=Status.choices, default=Status.DRAFT)
    currency = models.CharField(_("Currency"), max_length=3, choices=Currency.choices)
    number = models.CharField(_("Document number"), max_length=150, unique=True, null=True, blank=True)
    sequence = models.ForeignKey(DocumentSequence, on_delete=models.PROTECT, null=True, blank=True, related_name="%(class)s_documents", verbose_name=_("Sequence"))
    sequence_counter = models.PositiveBigIntegerField(null=True, blank=True, verbose_name=_("Sequence counter"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_%(class)s", verbose_name=_("Created by"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="finalized_%(class)s", null=True, blank=True, verbose_name=_("Finalized by"))
    finalized_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Finalized at"))
    issue_date = models.DateField(_("Issue date"), null=True, blank=True)
    business_timezone = models.CharField(_("Business timezone"), max_length=64, default="Africa/Kinshasa", validators=[validate_business_timezone])
    company_snapshot = models.JSONField(default=dict, blank=True, verbose_name=_("Company snapshot"))
    succursale_snapshot = models.JSONField(default=dict, blank=True, verbose_name=_("Succursale snapshot"))
    request_reference_snapshot = models.CharField(max_length=100, blank=True, verbose_name=_("Request reference snapshot"))
    branding_snapshot = models.JSONField(default=dict, blank=True, verbose_name=_("Branding snapshot"))
    total = models.DecimalField(_("Total"), max_digits=20, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    rounding_policy = models.CharField(max_length=40, default="DECIMAL_HALF_UP_2_V1", verbose_name=_("Rounding policy"))
    amount_words_fr = models.TextField(_("Amount in French words"), blank=True)
    snapshot_version = models.PositiveSmallIntegerField(default=1, verbose_name=_("Snapshot version"))
    audit_metadata = models.JSONField(default=dict, blank=True, verbose_name=_("Audit metadata"))

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(condition=Q(total__isnull=True) | Q(total__gte=0), name="%(class)s_total_nonnegative"),
            models.CheckConstraint(condition=Q(currency__in=Currency.values), name="%(class)s_currency"),
            models.CheckConstraint(condition=(Q(status="DRAFT", number__isnull=True, sequence__isnull=True,
                sequence_counter__isnull=True, finalized_at__isnull=True, finalized_by__isnull=True, issue_date__isnull=True) |
                (Q(status="FINALIZED", number__isnull=False, sequence__isnull=False, sequence_counter__gte=1,
                    sequence_counter__isnull=False, finalized_at__isnull=False, finalized_by__isnull=False,
                    issue_date__isnull=False, total__isnull=False) & ~Q(number=""))), name="%(class)s_lifecycle"),
            models.UniqueConstraint(fields=["sequence", "sequence_counter"], name="%(class)s_sequence_counter"),
        ]


class Invoice(FinancialDocument):
    request = models.OneToOneField("requests_app.Request", on_delete=models.PROTECT, related_name="invoice", verbose_name=_("Request"))
    succursale = models.ForeignKey("inventory.Succursale", on_delete=models.PROTECT, verbose_name=_("Succursale"))
    classification_approval = models.ForeignKey("requests_app.RequestApproval", on_delete=models.PROTECT, verbose_name=_("Classification approval"))
    classification_actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="classified_invoices", verbose_name=_("Classification actor"))
    classification_at = models.DateTimeField(verbose_name=_("Classification at"))
    company_verification = models.ForeignKey(CompanyVerification, on_delete=models.PROTECT, verbose_name=_("Company verification"))

    class Meta(FinancialDocument.Meta):
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")
        permissions = [
            ("finalize_invoice", _("Can finalize invoices")),
            ("manage_all_invoices", _("Can manage invoices across stock-review assignments")),
        ]


class InvoiceLine(FinancialRecord):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="lines", verbose_name=_("Invoice"))
    material = models.ForeignKey("inventory.Material", on_delete=models.PROTECT, verbose_name=_("Material"))
    material_code_snapshot = models.CharField(max_length=100, verbose_name=_("Material code snapshot"))
    description_snapshot = models.TextField(verbose_name=_("Description snapshot"))
    unit_snapshot = models.CharField(max_length=50, blank=True, verbose_name=_("Unit snapshot"))
    quantity = models.DecimalField(_("Net billable quantity"), max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    unit_price = models.DecimalField(_("Unit price"), max_digits=16, decimal_places=4, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    currency = models.CharField(_("Currency"), max_length=3, choices=Currency.choices)
    line_total = models.DecimalField(_("Line total"), max_digits=20, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    position = models.PositiveIntegerField(default=1, verbose_name=_("Position"))
    rounding_policy = models.CharField(max_length=40, default="DECIMAL_HALF_UP_2_V1", verbose_name=_("Rounding policy"))

    class Meta:
        verbose_name = _("Invoice line")
        verbose_name_plural = _("Invoice lines")
        ordering = ["position", "pk"]
        constraints = [models.UniqueConstraint(fields=["invoice", "position"], name="inv_line_order"),
            models.UniqueConstraint(fields=["invoice", "material"], name="inv_line_material"),
            models.CheckConstraint(condition=Q(quantity__gte=0), name="inv_line_nonnegative_quantity"),
            models.CheckConstraint(condition=Q(unit_price__isnull=True) | Q(unit_price__gte=0), name="inv_line_price"),
            models.CheckConstraint(condition=Q(line_total__isnull=True) | Q(line_total__gte=0), name="inv_line_total"),
            models.CheckConstraint(condition=Q(currency__in=Currency.values), name="inv_line_currency")]


class InvoiceIssueAllocation(FinancialRecord):
    line = models.OneToOneField(InvoiceLine, on_delete=models.PROTECT, related_name="issue_allocation", verbose_name=_("Line"))
    out_movement = models.OneToOneField("requests_app.StockMovement", on_delete=models.PROTECT, related_name="invoice_issue_allocation", verbose_name=_("Out movement"))
    quantity = models.DecimalField(_("Allocated quantity"), max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        verbose_name = _("Invoice issue allocation")
        verbose_name_plural = _("Invoice issue allocations")
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=0), name="inv_issue_nonnegative")]


class InvoiceReturnExclusion(FinancialRecord):
    """Whole pre-finalization RETURN excluded from billing, never creditable."""
    issue_allocation = models.ForeignKey(InvoiceIssueAllocation, on_delete=models.PROTECT, related_name="return_exclusions", verbose_name=_("Issue allocation"))
    return_movement = models.OneToOneField("requests_app.StockMovement", on_delete=models.PROTECT, related_name="invoice_return_exclusion", verbose_name=_("Return movement"))
    quantity = models.DecimalField(_("Excluded return quantity"), max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])

    class Meta:
        verbose_name = _("Invoice return exclusion")
        verbose_name_plural = _("Invoice return exclusions")
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="inv_exclusion_positive")]


class CreditNote(FinancialDocument):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="credit_notes", verbose_name=_("Invoice"))
    creation_operation_token = models.UUIDField(null=True, blank=True, unique=True, editable=False, verbose_name=_("Credit creation token"))
    reservation_revision = models.PositiveBigIntegerField(default=0, editable=False, verbose_name=_("Reservation revision"))
    reviewed_revision = models.PositiveBigIntegerField(null=True, blank=True, editable=False, verbose_name=_("Reviewed revision"))
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_credits", verbose_name=_("Reviewed by"))
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Reviewed at"))
    review_operation = models.ForeignKey("CreditOperation", on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_documents", verbose_name=_("Review operation"))

    class Meta(FinancialDocument.Meta):
        verbose_name = _("Credit note")
        verbose_name_plural = _("Credit notes")
        permissions = [("finalize_creditnote", _("Can finalize credit notes"))]


class CreditAllocation(FinancialRecord):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, related_name="allocations", verbose_name=_("Credit note"))
    issue_allocation = models.ForeignKey(InvoiceIssueAllocation, on_delete=models.PROTECT, related_name="credit_allocations", verbose_name=_("Issue allocation"))
    return_movement = models.ForeignKey("requests_app.StockMovement", on_delete=models.PROTECT, related_name="financial_credit_allocations", verbose_name=_("Return movement"))
    quantity = models.DecimalField(_("Credited quantity"), max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    unit_price_snapshot = models.DecimalField(max_digits=16, decimal_places=4, verbose_name=_("Unit price snapshot"))
    line_total = models.DecimalField(max_digits=20, decimal_places=2, verbose_name=_("Line total"))
    description_snapshot = models.TextField(verbose_name=_("Description snapshot"))
    audit_metadata = models.JSONField(default=dict, blank=True, verbose_name=_("Audit metadata"))

    released_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name=_("Reservation released at"))
    release_operation = models.ForeignKey("CreditOperation", on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="released_reservations", verbose_name=_("Release operation"))

    class Meta:
        verbose_name = _("Credit allocation")
        verbose_name_plural = _("Credit allocations")
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="inv_credit_positive"),
            models.CheckConstraint(condition=Q(unit_price_snapshot__gte=0, line_total__gte=0), name="inv_credit_amounts"),
            models.CheckConstraint(condition=Q(released_at__isnull=True, release_operation__isnull=True) | Q(released_at__isnull=False, release_operation__isnull=False), name="credit_release_pair")]


class CreditOperation(FinancialRecord):
    """Append-only transaction attribution. No operational service is provided."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, verbose_name=_("Invoice"))
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Actor"))
    kind = models.CharField(max_length=12, choices=[(k, _(label)) for k,label in (
        ("CREATE","Create credit draft"),("RESERVE","Reserve credit"),("REBALANCE","Rebalance credit reservations"),
        ("RELEASE","Release credit reservation"),("REVIEW","Review credit amounts"),("FINALIZE","Finalize credit note"))], verbose_name=_("Operation kind"))
    reason = models.TextField(verbose_name=_("Operation reason"))
    payload = models.JSONField(default=dict, blank=True, verbose_name=_("Operation payload"))
    transaction_id = models.CharField(max_length=32, blank=True, editable=False, verbose_name=_("Database transaction"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Credit operation")
        verbose_name_plural = _("Credit operations")

    def clean(self):
        super().clean()
        if not self.reason.strip():
            raise ValidationError(_("A credit operation reason is required."))
        if not self.actor.is_active:
            raise ValidationError(_("An active credit operation actor is required."))


class CreditReservationAudit(FinancialRecord):
    """Database-generated evidence; application callers cannot manufacture rows."""
    allocation = models.ForeignKey(CreditAllocation, on_delete=models.PROTECT, related_name="reservation_audits", verbose_name=_("Credit allocation"))
    operation = models.ForeignKey(CreditOperation, on_delete=models.PROTECT, related_name="adjustments", verbose_name=_("Credit operation"))
    previous_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True, verbose_name=_("Previous reserved amount"))
    new_amount = models.DecimalField(max_digits=20, decimal_places=2, verbose_name=_("New reserved amount"))
    previous_quantity = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Previous reserved quantity"))
    new_quantity = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("New reserved quantity"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Credit reservation audit")
        verbose_name_plural = _("Credit reservation audits")


class DocumentArtifact(FinancialRecord):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Invoice"))
    credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Credit note"))
    document_type = models.CharField(max_length=10, choices=[(DocumentSequence.Kind.INVOICE, _("Invoice")), (DocumentSequence.Kind.CREDIT, _("Credit note"))], verbose_name=_("Document type"))
    language = models.CharField(max_length=2, choices=[("en", _("English")), ("fr", _("French"))], verbose_name=_("Language"))
    rendering_version = models.CharField(max_length=40, verbose_name=_("Rendering version"))
    file_reference = models.CharField(max_length=500, verbose_name=_("File reference"))
    checksum = models.CharField(max_length=64, verbose_name=_("Checksum"))
    rendering_status = models.CharField(max_length=10, choices=[("PENDING", _("Pending")), ("READY", _("Ready")), ("FAILED", _("Failed"))], verbose_name=_("Rendering status"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Created by"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Document artifact")
        verbose_name_plural = _("Document artifacts")
        constraints = [models.CheckConstraint(condition=(Q(invoice__isnull=False, credit_note__isnull=True, document_type="INVOICE") |
            Q(invoice__isnull=True, credit_note__isnull=False, document_type="CREDIT")), name="inv_artifact_owner")]


class InvoiceAuditEvent(FinancialRecord):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Invoice"))
    credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Credit note"))
    event_type = models.CharField(max_length=50, verbose_name=_("Event type"))
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Actor"))
    occurred_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Occurred at"))
    document_identifier = models.CharField(max_length=150, verbose_name=_("Document identifier"))
    details = models.JSONField(default=dict, blank=True, verbose_name=_("Details"))

    class Meta:
        verbose_name = _("Invoice audit event")
        verbose_name_plural = _("Invoice audit events")
        constraints = [models.CheckConstraint(condition=(Q(invoice__isnull=False, credit_note__isnull=True) |
            Q(invoice__isnull=True, credit_note__isnull=False)), name="inv_audit_owner")]


class MaterialReturnNoteAudit(FinancialRecord):
    """Append-only issuance attribution; no issuance service is provided."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, verbose_name=_("Invoice"))
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Actor"))
    reason = models.TextField(verbose_name=_("Operation reason"))
    payload = models.JSONField(default=dict, blank=True, verbose_name=_("Operation payload"))
    transaction_id = models.CharField(max_length=32, blank=True, editable=False, verbose_name=_("Database transaction"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Material return note audit")
        verbose_name_plural = _("Material return note audits")

    def clean(self):
        super().clean()
        if not self.reason.strip():
            raise ValidationError(_("A material return note reason is required."))
        if not self.actor.is_active:
            raise ValidationError(_("An active material return note actor is required."))


class MaterialReturnNote(FinancialDocument):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="material_return_notes", verbose_name=_("Invoice"))
    issuance_operation_token = models.UUIDField(null=True, blank=True, unique=True, editable=False, verbose_name=_("Return note issuance token"))
    operation = models.OneToOneField(MaterialReturnNoteAudit, on_delete=models.PROTECT, verbose_name=_("Issuance audit"))
    original_invoice_snapshot = models.JSONField(default=dict, blank=True, verbose_name=_("Original invoice snapshot"))
    cumulative_returned_value = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name=_("Cumulative documented return value"))
    adjusted_net_value = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name=_("Adjusted net material value"))

    class Meta(FinancialDocument.Meta):
        verbose_name = _("Material return note")
        verbose_name_plural = _("Material return notes")
        permissions = [("issue_materialreturnnote", _("Can issue material return notes")),
                       ("view_materialreturnnote_document", _("Can view protected material return note documents"))]
        constraints = FinancialDocument.Meta.constraints + [
            models.CheckConstraint(condition=Q(cumulative_returned_value__gte=0, adjusted_net_value__gte=0), name="return_note_values_nonnegative")]


class MaterialReturnNoteLine(FinancialRecord):
    note = models.ForeignKey(MaterialReturnNote, on_delete=models.PROTECT, related_name="lines", verbose_name=_("Material return note"))
    issue_allocation = models.ForeignKey(InvoiceIssueAllocation, on_delete=models.PROTECT, verbose_name=_("Issue allocation"))
    return_movement = models.OneToOneField("requests_app.StockMovement", on_delete=models.PROTECT, verbose_name=_("Return movement"))
    quantity = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("Returned quantity"))
    material_code_snapshot = models.CharField(max_length=100, verbose_name=_("Material code snapshot"))
    description_snapshot = models.TextField(verbose_name=_("Description snapshot"))
    unit_snapshot = models.CharField(max_length=50, blank=True, verbose_name=_("Unit snapshot"))
    unit_price_snapshot = models.DecimalField(max_digits=16, decimal_places=4, verbose_name=_("Unit price snapshot"))
    line_total = models.DecimalField(max_digits=20, decimal_places=2, verbose_name=_("Returned value"))

    class Meta:
        verbose_name = _("Material return note line")
        verbose_name_plural = _("Material return note lines")
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0,unit_price_snapshot__gte=0,line_total__gte=0), name="return_note_line_values")]


class MaterialReturnNoteArtifact(FinancialRecord):
    """Protected ownership metadata only; no rendering/download implementation."""
    note = models.ForeignKey(MaterialReturnNote, on_delete=models.PROTECT, related_name="artifacts", verbose_name=_("Material return note"))
    language = models.CharField(max_length=2, choices=[("en",_("English")),("fr",_("French"))], verbose_name=_("Language"))
    rendering_version = models.CharField(max_length=40, verbose_name=_("Rendering version"))
    file_reference = models.CharField(max_length=500, verbose_name=_("File reference"))
    checksum = models.CharField(max_length=64, verbose_name=_("Checksum"))
    rendering_status = models.CharField(max_length=10, choices=[("PENDING",_("Pending")),("READY",_("Ready")),("FAILED",_("Failed"))], verbose_name=_("Rendering status"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Created by"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Material return note artifact")
        verbose_name_plural = _("Material return note artifacts")
        constraints = [models.CheckConstraint(condition=Q(language__in=["en","fr"],rendering_status__in=["PENDING","READY","FAILED"]), name="return_note_artifact_state")]

from .adjusted_models import AdjustedInvoiceStatement  # noqa: E402
