"""Prepare annual numbering scopes; never allocate or attest references."""
from itertools import combinations
from string import Formatter

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from core.models import CompanyDocumentSettings
from .configuration import business_date
from .models import DocumentSequence
from .services import database_now


def following_year(moment, timezone_name):
    if timezone_name != "Africa/Kinshasa":
        raise ValidationError(_("Invoice preparation requires Africa/Kinshasa."))
    year = business_date(moment, timezone_name).year + 1
    if year > 9999:
        raise ValidationError(_("The following business year is outside the supported range."))
    return year


def conflicting_series(sequences):
    """Conservative proof: differing, non-overlapping literal prefixes are safe.

    Prefixes that overlap are reported even if later literals might distinguish
    them. Sampling counters cannot prove that formats never collide.
    """
    conflicts = []
    for left, right in combinations(sequences, 2):
        a = next(Formatter().parse(left.number_format))[0]
        b = next(Formatter().parse(right.number_format))[0]
        if a.startswith(b) or b.startswith(a):
            conflicts.append((left.series, right.series))
    return conflicts


@transaction.atomic
def prepare_invoice_year():
    # One stable coordinator serializes cooperating preparations, including
    # initially absent target rows. The scope unique constraint is a backstop.
    configuration = CompanyDocumentSettings.objects.select_for_update().get(pk=1)
    year = following_year(database_now(), configuration.business_timezone)
    rows = list(DocumentSequence.objects.select_for_update().filter(
        document_type="INVOICE", year__in=[year - 1, year]).order_by("year", "series"))
    sources = [row for row in rows if row.year == year - 1 and row.is_verified]
    targets = {row.series: row for row in rows if row.year == year}
    for row in rows:
        row.full_clean()
    planned = dict(targets)
    for source in sources:
        planned.setdefault(source.series, source)
    conflicts = conflicting_series(list(planned.values()))
    report = {"year": year, "prepared": [], "existing": sorted(targets),
              "unverified": sorted(row.series for row in targets.values() if not row.is_verified),
              "conflicts": conflicts, "sources": len(sources)}
    if conflicts:
        return report  # No partial preparation if any format needs review.
    for source in sources:
        if source.series in targets:
            continue
        row, created = DocumentSequence.objects.get_or_create(
            document_type="INVOICE", year=year, series=source.series,
            defaults={"number_format": source.number_format, "starting_value": 1, "next_counter": 1})
        report["prepared" if created else "existing"].append(row.series)
        if not row.is_verified:
            report["unverified"].append(row.series)
    return report
