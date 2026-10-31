"""Sanitized inventory diagnostics; never repairs data or emits private text."""
import json
from collections import Counter
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction, DatabaseError
from django.db.models import Exists, OuterRef, Q, Prefetch
from django.utils.translation import gettext as _, override
from requests_app.models import Request, RequestMaterialItem, StockMovement
from requests_app.stock_integrity import annotate_return_ledgers, movement_prefetch


class Command(BaseCommand):
    help = "Read-only stock integrity audit. No repair, private names, reasons, prices or credentials."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--confirm-database", required=True, help="Exact database name; no target is selected automatically.")
        parser.add_argument("--request-id", type=int)
        parser.add_argument("--include-record-ids", action="store_true", help="Include internal IDs only, never private text.")
        parser.add_argument("--max-details", type=int, default=100)
        parser.add_argument("--language", choices=["en", "fr"], default="en")

    def handle(self, *args, **options):
        with override(options["language"]):
            return self.audit(options)

    def audit(self, options):
        alias = options["database"]
        if alias not in connections:
            raise CommandError(_("Unknown database alias."))
        connection = connections[alias]
        if connection.vendor != "postgresql" or str(connection.settings_dict["NAME"]) != options["confirm_database"]:
            raise CommandError(_("PostgreSQL target confirmation failed. No inspection performed."))
        if connection.in_atomic_block or not connection.get_autocommit():
            raise CommandError(_("This audit requires its own outermost read-only transaction."))
        if not 1 <= options["max_details"] <= 1000 or options["request_id"] is not None and options["request_id"] <= 0:
            raise CommandError(_("Invalid audit scope or detail limit."))
        try:
            with override(options["language"]), transaction.atomic(using=alias):
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    cursor.execute("SET LOCAL statement_timeout = '30s'")
                    cursor.execute("SET LOCAL lock_timeout = '3s'")
                counts, details, groups = Counter(), [], 0
                requests = Request.objects.using(alias).filter(
                    Q(status="APPROVED", material_items__isnull=False) |
                    Q(stock_movements__movement_type__in=["OUT", "RETURN"])).distinct()
                if options["request_id"] is not None:
                    requests = requests.filter(pk=options["request_id"])
                requests = requests.only("id", "status", "stock_deducted").prefetch_related(
                    Prefetch("material_items", queryset=RequestMaterialItem.objects.using(alias).only("id", "request_id", "material_id", "quantity")),
                    movement_prefetch(alias)).order_by("pk")
                for request in requests.iterator(chunk_size=250):
                    annotate_return_ledgers([request])
                    # Repeated material lines are one ambiguous association, not multiple findings.
                    seen = set()
                    for item in request.material_items.all():
                        if item.material_id in seen:
                            continue
                        seen.add(item.material_id)
                        groups += 1
                        issues = item.return_ledger["issues"]
                        counts.update(issues)
                        if issues and options["include_record_ids"] and len(details) < options["max_details"]:
                            details.append({"request_id": request.pk, "material_id": item.material_id,
                                "item_ids": [row.pk for row in request.material_items.all() if row.material_id == item.material_id][:100],
                                "movement_ids": [row.pk for row in item.return_history[:100]],
                                "movement_count": len(item.return_history), "issues": issues})
                associated = RequestMaterialItem.objects.using(alias).filter(request_id=OuterRef("request_id"), material_id=OuterRef("material_id"))
                orphaned = StockMovement.objects.using(alias).filter(movement_type__in=["OUT", "RETURN"]).annotate(has_item=Exists(associated)).filter(has_item=False)
                if options["request_id"] is not None:
                    orphaned = orphaned.filter(request_id=options["request_id"])
                orphan_count = orphaned.count()
                if orphan_count:
                    counts["unassociated_movement"] = orphan_count
                    if options["include_record_ids"]:
                        for row in orphaned.order_by("pk").values("pk", "request_id", "material_id")[:max(0, options["max_details"]-len(details))]:
                            details.append({"movement_id": row["pk"], "request_id": row["request_id"], "material_id": row["material_id"], "issues": ["unassociated_movement"]})
                result = {"read_only": True, "isolation": "repeatable read", "material_groups_scanned": groups,
                    "issue_counts": dict(sorted(counts.items())),
                    "message": _("Historical stock discrepancy — review required.") if counts else _("No stock integrity discrepancies found."),
                    "details": details, "detail_limit": options["max_details"],
                    "privacy": _("No request references, names, reasons, actors, financial values or connection details."),
                    "repairs_performed": False}
                # Always roll back, including the read-only transaction's local settings.
                transaction.set_rollback(True, using=alias)
            self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
        except DatabaseError:
            raise CommandError(_("The read-only audit could not complete. Review database availability and schema; no repairs were attempted.")) from None
