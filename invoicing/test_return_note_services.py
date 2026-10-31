"""Authorized E-R2 services against synthetic, disposable financial evidence."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, PropertyMock
from uuid import uuid4
import time

from django.contrib.auth.models import AnonymousUser, Permission
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import connection, transaction, DatabaseError
from django.utils.translation import override

from inventory.models import Material
from requests_app.models import RequestMaterialItem, StockMovement
from requests_app.services import approve_step
from .models import (CreditAllocation, CreditNote, CreditOperation, CreditReservationAudit,
                     DocumentSequence, Invoice, InvoiceLine, MaterialReturnNote,
                     MaterialReturnNoteAudit, MaterialReturnNoteLine)
from . import return_note_services as service
from .test_return_note_guards import ReturnNoteFixtures


PERMISSIONS = ["view_invoice", "view_materialreturnnote", "add_materialreturnnote", "issue_materialreturnnote"]


class ReturnNoteServiceFixtures(ReturnNoteFixtures):
    def setUp(self):
        super().setUp()
        self.grant(self.user)

    def grant(self, user, permissions=PERMISSIONS):
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing", codename__in=permissions))

    def preview(self, movements=None, user=None, **kwargs):
        return service.preview_material_return_note(self.invoice.pk, user or self.user,
            return_movement_ids=[m.pk for m in movements or [self.returned]],
            reason=kwargs.pop("reason", "Returned materials"), **kwargs)

    def issue(self, preview, movements=None, user=None, **kwargs):
        return service.issue_material_return_note(self.invoice.pk, user or self.user,
            return_movement_ids=[m.pk for m in movements or [self.returned]],
            reason=kwargs.pop("reason", "Returned materials"), issuance_token=preview["issuance_token"],
            confirmation=preview["confirmation"], **kwargs)

    def financial_snapshot(self):
        return {model.__name__: list(model.objects.order_by("pk").values()) for model in
                (Invoice, InvoiceLine, CreditNote, CreditAllocation, CreditOperation, CreditReservationAudit)}


class ReturnNoteServiceTests(ReturnNoteServiceFixtures):
    def test_preview_has_no_persistent_draft_audit_number_or_source_writes(self):
        self.partial_history()
        before, financial = self.source_snapshot(), self.financial_snapshot()
        preview = self.preview()
        self.assertEqual(preview["total"], "0.01")
        self.assertFalse(MaterialReturnNote.objects.exists())
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        self.assertFalse(DocumentSequence.objects.filter(document_type="RETURN_NOTE").exists())
        self.assertEqual(before, self.source_snapshot())
        self.assertEqual(financial, self.financial_snapshot())

    def test_complete_return_preserves_original_facture_and_stock(self):
        self.setup_invoice(price="2.1234")
        self.return_sequence()
        before, financial = self.source_snapshot(), self.financial_snapshot()
        note = self.issue(self.preview())
        self.assertEqual(note.total, self.invoice.total)
        self.assertEqual(note.adjusted_net_value, 0)
        self.assertEqual(note.status, "FINALIZED")
        self.assertEqual(note.number, f"BR/0007/{note.issue_date.year}")
        self.assertEqual(note.original_invoice_snapshot["total"], str(self.invoice.total))
        self.assertEqual(note.company_snapshot, self.invoice.company_snapshot)
        self.assertEqual(before, self.source_snapshot())
        self.assertEqual(financial, self.financial_snapshot())
        self.assertEqual(Invoice.objects.get(pk=self.invoice.pk).status, "FINALIZED")
        self.assertEqual(service.get_material_return_note(note.pk, self.user).pk, note.pk)

    def test_finalization_retains_exact_database_stamped_header_identity(self):
        self.setup_invoice(); self.return_sequence()
        preview = self.preview(); original = MaterialReturnNote.save; checked = []
        def check_identity(note, *args, **kwargs):
            if note.status == "FINALIZED":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT created_at FROM invoicing_materialreturnnote WHERE id=%s", [note.pk])
                    self.assertEqual(note.created_at, cursor.fetchone()[0])
                checked.append(note.pk)
            return original(note, *args, **kwargs)
        with patch.object(MaterialReturnNote, "save", check_identity):
            note = self.issue(preview)
        self.assertEqual(checked, [note.pk])

    def test_multiple_whole_movements_round_cumulatively_and_cap(self):
        first = self.partial_history()
        second, _ = self.restore(1)
        third, _ = self.restore(1)
        self.return_sequence()
        a = self.issue(self.preview([second, first]), [first, second])
        self.assertEqual(list(a.lines.order_by("pk").values_list("line_total", flat=True)), [Decimal(".01"), Decimal("0")])
        b = self.issue(self.preview([third]), [third])
        self.assertEqual(b.total, Decimal(".01"))
        self.assertEqual(b.cumulative_returned_value, self.invoice.total)
        self.assertEqual(b.adjusted_net_value, 0)
        self.assertEqual(MaterialReturnNoteLine.objects.count(), 3)

    def test_multiple_materials_in_one_note(self):
        self.req, self.item = self.make_request(3)
        material = Material.objects.create(category=self.category, code="SECOND", name="Second", unit="pcs", stock_quantity=100)
        second_item = RequestMaterialItem.objects.create(request=self.req, material=material, quantity=2)
        approve_step(self.req.approvals.get(), self.user, classification="MICROCOM", succursale=self.branch)
        self.req.refresh_from_db()
        invoice = self.create(); self.price(invoice, "1.2345"); self.verified_sequence()
        self.invoice = self.finalize(invoice)
        self.returned, _ = self.restore(1)
        from requests_app.stock_services import return_material_stock, RETURN_TOKEN_SALT
        token = signing.dumps({"item": second_item.pk, "user": self.user.pk, "operation": str(uuid4())}, salt=RETURN_TOKEN_SALT)
        other, _ = return_material_stock(second_item.pk, self.user, 2, "Synthetic", token)
        self.return_sequence()
        note = self.issue(self.preview([other, self.returned]), [other, self.returned])
        self.assertEqual(note.lines.count(), 2)
        self.assertEqual(note.total, Decimal("3.70"))

    def test_zero_price_and_zero_rounding_increment(self):
        self.setup_invoice(price="0")
        self.return_sequence()
        note = self.issue(self.preview())
        self.assertEqual(note.total, 0)
        self.assertEqual(note.lines.get().quantity, self.returned.quantity)
        self.assertTrue(note.amount_words_fr)

    def test_fractional_quantities_use_exact_original_price(self):
        self.partial_history(price="0.1234")
        movement, _ = self.restore(Decimal("0.25"))
        self.return_sequence()
        note = self.issue(self.preview([movement]), [movement])
        self.assertEqual(note.total, Decimal(".03"))
        self.assertEqual(note.lines.get().quantity, Decimal(".25"))

    def test_catalogue_and_company_changes_do_not_reprice_or_change_snapshots(self):
        self.setup_invoice(price="2")
        self.return_sequence()
        preview = self.preview()
        self.material.unit_price = Decimal("999"); self.material.currency = "EUR"
        self.material.name = "Changed"; self.material.save()
        self.configuration.company_name = "Changed company"; self.configuration.save()
        self.branch.physical_address = "Changed current address"; self.branch.save(update_fields=["physical_address"])
        note = self.issue(preview)
        self.assertEqual(note.total, Decimal("6"))
        self.assertEqual(note.currency, "USD")
        self.assertEqual(note.lines.get().unit_price_snapshot, Decimal("2"))
        self.assertEqual(note.company_snapshot, self.invoice.company_snapshot)
        self.assertEqual(note.succursale_snapshot, self.invoice.succursale_snapshot)
        self.assertNotEqual(note.succursale_snapshot["physical_address"], self.branch.physical_address)

    def test_legacy_null_token_accepted_and_preserved(self):
        self.setup_invoice()
        StockMovement.objects.filter(pk=self.returned.pk).update(return_operation_token=None)
        self.return_sequence()
        self.issue(self.preview())
        self.assertIsNone(StockMovement.objects.get(pk=self.returned.pk).return_operation_token)

    def test_precutoff_equal_future_excluded_and_wrong_type_rejected(self):
        self.partial_history(pre_return=1)
        for created_at in [self.invoice.finalized_at - timedelta(seconds=1), self.invoice.finalized_at,
                           service.database_now() + timedelta(days=1)]:
            with self.subTest(created_at=created_at):
                StockMovement.objects.filter(pk=self.returned.pk).update(created_at=created_at)
                with self.assertRaises(ValidationError): self.preview()
        with self.assertRaises(ValidationError): self.preview([self.excluded])
        with self.assertRaises(ValidationError): self.preview([self.issue_allocation.out_movement])

    def test_ambiguous_out_and_overreturn_and_wrong_request_block(self):
        self.setup_invoice()
        StockMovement.objects.create(request=self.req, material=self.material, movement_type="OUT", quantity=1)
        with self.assertRaises(ValidationError): self.preview()
        StockMovement.objects.filter(request=self.req, movement_type="OUT").exclude(pk=self.issue_allocation.out_movement_id).delete()
        StockMovement.objects.filter(pk=self.returned.pk).update(quantity=4)
        with self.assertRaises(ValidationError): self.preview()
        StockMovement.objects.filter(pk=self.returned.pk).update(quantity=3, request=None)
        with self.assertRaises(ValidationError): self.preview()

    def test_duplicate_missing_and_malformed_selections(self):
        self.setup_invoice()
        for values in [[], [self.returned.pk] * 2, [True], [str(self.returned.pk)], [0], [2**63], [99999999], None]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                service.preview_material_return_note(self.invoice.pk, self.user, return_movement_ids=values, reason="Return")
        for reason in ["", " " * 3, "x" * 2001, None]:
            with self.assertRaises(ValidationError): self.preview(reason=reason)

    def test_malformed_confirmations_and_ids_are_rejected_before_transaction_entry(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        with patch.object(service, "_outermost") as boundary:
            for confirmation in [None, 42, b"not-a-string", {}, []]:
                with self.subTest(confirmation=confirmation), self.assertRaises(ValidationError):
                    self.issue({**preview, "confirmation": confirmation})
            for value in [True, "1", 0, -1, 2**63, None]:
                with self.subTest(invoice_id=value), self.assertRaises(ValidationError):
                    service.preview_material_return_note(value, self.user,
                        return_movement_ids=[self.returned.pk], reason="Return")
            boundary.assert_not_called()

    def test_missing_issue_allocation_has_translated_provenance_error(self):
        self.setup_invoice()
        with patch.object(InvoiceLine, "issue_allocation", new_callable=PropertyMock,
                          side_effect=ObjectDoesNotExist), self.assertRaisesMessage(ValidationError, "provenance"):
            self.preview()

    def test_eligibility_database_failure_does_not_leak_raw_sql_error(self):
        self.setup_invoice()
        with patch.object(service, "_calculate", side_effect=DatabaseError("synthetic SQL details")):
            with self.assertRaisesMessage(ValidationError, "could not be issued safely"):
                service.eligible_return_movements(self.invoice.pk, self.user)

    def test_unfinalized_invoice_cannot_be_previewed(self):
        self.invoice = self.create()
        with self.assertRaisesMessage(ValidationError, "finalized internal invoice"):
            service.preview_material_return_note(self.invoice.pk, self.user,
                return_movement_ids=[self.out.pk], reason="Return")

    def test_permission_revocation_during_request_lock_wait_is_rechecked(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        from requests_app.models import Request
        original = Request.objects.select_for_update
        permission = Permission.objects.get(content_type__app_label="invoicing", codename="issue_materialreturnnote")
        def revoke(*args, **kwargs):
            self.user.user_permissions.remove(permission)
            return original(*args, **kwargs)
        with patch.object(Request.objects, "select_for_update", side_effect=revoke), self.assertRaises(PermissionDenied):
            self.issue(preview)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())

    def test_existing_documentation_blocks_new_preview(self):
        self.setup_invoice(); self.return_sequence()
        self.issue(self.preview())
        with self.assertRaises(ValidationError): self.preview()
        self.assertFalse(service.eligible_return_movements(self.invoice.pk, self.user)[0]["eligible"])

    def test_exact_replay_after_expiry_no_duplicate_audit_counter_or_number(self):
        self.setup_invoice(); sequence = self.return_sequence()
        preview = self.preview(); note = self.issue(preview)
        with patch("django.core.signing.time.time", return_value=10**11):
            self.assertEqual(self.issue(preview).pk, note.pk)
        self.assertEqual(MaterialReturnNoteAudit.objects.count(), 1)
        self.assertEqual(MaterialReturnNote.objects.count(), 1)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 8)

    def test_changed_payload_token_and_confirmation_rejected(self):
        self.partial_history(); second, _ = self.restore(1); self.return_sequence()
        preview = self.preview(); self.issue(preview)
        for changes in [{"reason": "Changed"}, {"series": "OTHER"}]:
            with self.assertRaises(ValidationError): self.issue(preview, **changes)
        with self.assertRaises(ValidationError): self.issue(preview, [second])
        with self.assertRaises(ValidationError): self.issue({**preview, "issuance_token": str(uuid4())})
        with self.assertRaises(ValidationError): self.issue({**preview, "confirmation": "forged"})

    def test_expired_uncommitted_preview_and_stale_new_return_rejected(self):
        self.partial_history(); self.return_sequence(); preview = self.preview()
        with patch("django.core.signing.time.time", return_value=10**11), self.assertRaises(ValidationError):
            self.issue(preview)
        self.restore(1)
        with self.assertRaises(ValidationError): self.issue(preview)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())

    def test_conflicting_credit_reservation_after_preview_rolls_back(self):
        self.partial_history(price="2"); second, _ = self.restore(1); self.return_sequence()
        preview = self.preview(); credit = self.new_credit(); self.reserve(credit, amount="2", returned=second)
        before = self.financial_snapshot()
        with self.assertRaises(ValidationError): self.issue(preview)
        self.assertFalse(MaterialReturnNote.objects.exists())
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        self.assertEqual(before, self.financial_snapshot())

    def test_finalized_credit_blocks_and_released_credit_is_preserved(self):
        self.setup_invoice(); credit = self.new_credit(); allocation = self.reserve(credit)
        self.review(credit)
        with self.write("FINALIZE"): self.schema_transition(credit)
        with self.assertRaises(ValidationError): self.preview()

    def test_released_reservation_does_not_block(self):
        self.setup_invoice(); credit = self.new_credit(); allocation = self.reserve(credit)
        with self.write("RELEASE") as op:
            allocation.released_at = service.database_now(); allocation.release_operation = op; allocation.save()
        before = self.financial_snapshot(); self.return_sequence(); self.issue(self.preview())
        self.assertEqual(before, self.financial_snapshot())

    def test_missing_unverified_and_collision_numbering_roll_back_all_evidence(self):
        self.setup_invoice(); preview = self.preview()
        with self.assertRaises(ValidationError): self.issue(preview)
        sequence = self.return_sequence()
        with connection.cursor() as c:
            c.execute("UPDATE invoicing_documentsequence SET verification_digest='wrong' WHERE id=%s", [sequence.pk])
        with self.assertRaises(ValidationError): self.issue(preview)
        sequence.attest(self.admin, "Reviewed")
        # Keep the MAIN counter monotonic. A separately verified unused series
        # can legitimately start at one and collide with the existing facture.
        collision = DocumentSequence.objects.create(document_type="RETURN_NOTE", series="COLLISION",
            year=self.invoice.issue_date.year, number_format="FAC/{number:04d}/{year}",
            starting_value=1, next_counter=1)
        collision.attest(self.admin, "Reviewed synthetic collision")
        collision_preview = self.preview(series="COLLISION")
        with self.assertRaises(ValidationError): self.issue(collision_preview, series="COLLISION")
        collision.refresh_from_db(); self.assertEqual(collision.next_counter, 1)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 7)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        self.assertFalse(MaterialReturnNote.objects.exists())

    def test_failure_after_number_increment_rolls_back(self):
        self.setup_invoice(); sequence = self.return_sequence(); preview = self.preview()
        original = MaterialReturnNote.save
        def fail(note, *args, **kwargs):
            if note.status == "FINALIZED": raise ValidationError("Injected failure")
            return original(note, *args, **kwargs)
        with patch.object(MaterialReturnNote, "save", fail), self.assertRaises(ValidationError): self.issue(preview)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 7)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        self.assertFalse(MaterialReturnNoteLine.objects.exists())
        self.issue(preview)

    def test_deferred_commit_failure_rolls_back_and_exact_retry_succeeds(self):
        self.setup_invoice(); sequence = self.return_sequence(); preview = self.preview()
        original = MaterialReturnNote.refresh_from_db
        def corrupt(note, *args, **kwargs):
            original(note, *args, **kwargs)
            if note.status == "FINALIZED":
                with connection.cursor() as c:
                    c.execute("UPDATE requests_app_stockmovement SET quantity=99 WHERE id=%s", [self.returned.pk])
        with patch.object(MaterialReturnNote, "refresh_from_db", corrupt), self.assertRaises(ValidationError): self.issue(preview)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 7)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        self.returned.refresh_from_db(); self.assertEqual(self.returned.quantity, 3)
        self.issue(preview)

    def test_actual_transaction_retry_rolls_back_first_attempt_evidence(self):
        self.setup_invoice(); sequence = self.return_sequence(); preview = self.preview()
        original = MaterialReturnNote.save; failed = []
        def deadlock(note, *args, **kwargs):
            if note.status == "FINALIZED" and not failed:
                failed.append(True)
                with connection.cursor() as c:
                    c.execute("DO $$ BEGIN RAISE EXCEPTION 'synthetic deadlock' USING ERRCODE='40P01'; END $$")
            return original(note, *args, **kwargs)
        with patch.object(MaterialReturnNote, "save", deadlock): note = self.issue(preview)
        self.assertEqual(note.sequence_counter, 7)
        self.assertEqual(MaterialReturnNoteAudit.objects.count(), 1)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 8)

    def test_retry_exhaustion_and_unsupported_ambient_transaction(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        def deadlock(*args, **kwargs):
            with connection.cursor() as c:
                c.execute("DO $$ BEGIN RAISE EXCEPTION 'synthetic deadlock' USING ERRCODE='40P01'; END $$")
        with patch.object(MaterialReturnNoteLine.objects, "create", side_effect=deadlock), self.assertRaises(ValidationError): self.issue(preview)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        with transaction.atomic(), self.assertRaises(ValidationError): self.issue(preview)

    def test_explicit_permissions_and_scope_required_without_cached_grants(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        self.user.has_perm("invoicing.issue_materialreturnnote")
        self.user.user_permissions.remove(Permission.objects.get(codename="issue_materialreturnnote"))
        with self.assertRaises(PermissionDenied): self.issue(preview)
        self.grant(self.user)
        self.user.is_staff = False; self.user.save(update_fields=["is_staff"])
        preview = self.preview()
        note = self.issue(preview)
        self.assertEqual(self.issue(preview).pk, note.pk)
        with self.assertRaises(PermissionDenied): self.preview(user=AnonymousUser())
        self.grant(self.other)
        with self.assertRaises(PermissionDenied): self.preview(user=self.other)
        self.req.approvals.update(alternate_approver_user=self.other)
        # The movement is already documented; authorization still succeeds.
        service.authorize_return_note(self.other, self.req.pk, issue=True)

    def test_delay_after_sequence_operations_uses_update_statement_time(self):
        self.partial_history(price="50"); sequence = self.return_sequence(); preview = self.preview()
        source, financial = self.source_snapshot(), self.financial_snapshot()
        original = DocumentSequence.save
        def delayed(sequence, *args, **kwargs):
            result = original(sequence, *args, **kwargs)
            if sequence.document_type == "RETURN_NOTE" and kwargs.get("update_fields") == ["next_counter"]:
                time.sleep(6)
            return result
        with patch.object(DocumentSequence, "save", delayed):
            note = self.issue(preview)
        self.assertEqual(note.total, Decimal("50"))
        self.assertEqual(note.adjusted_net_value, Decimal("100"))
        self.assertEqual(source, self.source_snapshot()); self.assertEqual(financial, self.financial_snapshot())
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 8)

    def test_delay_inside_final_model_validation_uses_update_statement_time(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        original = MaterialReturnNote.full_clean
        def delayed(note, *args, **kwargs):
            result = original(note, *args, **kwargs)
            if note.status == "FINALIZED": time.sleep(6)
            return result
        with patch.object(MaterialReturnNote, "full_clean", delayed):
            note = self.issue(preview)
        self.assertEqual(note.status, "FINALIZED")
        self.assertEqual(self.issue(preview).pk, note.pk)
        self.assertEqual(MaterialReturnNoteAudit.objects.count(), 1)

    def test_finance_permissions_without_stock_scope_cannot_issue(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        self.grant(self.other)
        with self.assertRaises(PermissionDenied): self.issue(preview, user=self.other)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())

    def test_midnight_and_year_rollover_after_preview_fail_closed(self):
        from datetime import date
        self.setup_invoice(); sequence = self.return_sequence(); preview = self.preview()
        original = service.business_date
        today = self.invoice.issue_date
        for changed in (today + timedelta(days=1), date(today.year + 1, 1, 1)):
            calls = []
            def rollover(moment, zone):
                calls.append(True)
                return changed if len(calls) == 3 else original(moment, zone)
            with patch.object(service, "business_date", side_effect=rollover), self.assertRaises(ValidationError):
                self.issue(preview)
            sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 7)
            self.assertFalse(MaterialReturnNoteAudit.objects.exists())
            self.assertFalse(MaterialReturnNote.objects.exists())

    def test_database_business_date_guard_still_rolls_back_final_update(self):
        self.setup_invoice(); sequence = self.return_sequence(); preview = self.preview()
        source, financial = self.source_snapshot(), self.financial_snapshot()
        original = MaterialReturnNote.save
        def crossed_boundary(note, *args, **kwargs):
            if note.status == "FINALIZED": note.issue_date += timedelta(days=1)
            return original(note, *args, **kwargs)
        with patch.object(MaterialReturnNote, "save", crossed_boundary), \
                self.assertLogs(service.logger, level="WARNING") as logs, self.assertRaises(ValidationError) as caught:
            self.issue(preview)
        self.assertEqual(caught.exception.code, "outcome_uncertain")
        self.assertIn("guard=return_note_business_date", logs.output[0])
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 7)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        self.assertFalse(MaterialReturnNoteLine.objects.exists())
        self.assertEqual(source, self.source_snapshot()); self.assertEqual(financial, self.financial_snapshot())
        self.assertEqual(self.issue(preview).sequence_counter, 7)

    def test_each_permission_inactive_staff_global_scope_and_replay_authorization(self):
        self.setup_invoice(); self.return_sequence()
        for codename in PERMISSIONS:
            permission = Permission.objects.get(content_type__app_label="invoicing", codename=codename)
            self.user.user_permissions.remove(permission)
            with self.assertRaises(PermissionDenied):
                service.authorize_return_note(self.user, self.req.pk, issue=True)
            self.user.user_permissions.add(permission)
        self.grant(self.other)
        self.other.user_permissions.add(Permission.objects.get(codename="manage_all_invoices"))
        self.preview(user=self.other)
        preview = self.preview(); note = self.issue(preview)
        self.user.is_active = False; self.user.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied): self.issue(preview)
        with self.assertRaises(PermissionDenied): service.get_material_return_note(note.pk, self.user)

    def test_confirmation_cannot_be_used_by_other_authorized_actor(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        with self.assertRaises(ValidationError): self.issue(preview, user=self.admin)

    def test_read_permission_is_separate_and_no_automatic_grants(self):
        self.setup_invoice(); self.return_sequence(); note = self.issue(self.preview())
        self.grant(self.other, ["view_invoice", "view_materialreturnnote"])
        self.req.approvals.update(alternate_approver_user=self.other)
        self.assertEqual(service.get_material_return_note(note.pk, self.other).pk, note.pk)
        with self.assertRaises(PermissionDenied): self.preview(user=self.other)
        self.assertFalse(self.other.has_perm("invoicing.issue_materialreturnnote"))

    def test_business_day_change_after_preview_is_stale(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview()
        with patch.object(service, "business_date", side_effect=lambda now, tz: now.date() + timedelta(days=2)), self.assertRaises(ValidationError): self.issue(preview)
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())

    def test_all_new_literal_messages_have_french_runtime_translation(self):
        import ast
        from pathlib import Path
        from django.utils.translation import gettext
        messages = set()
        for name in ("return_note_services.py", "permissions.py"):
            tree = ast.parse(Path(__file__).with_name(name).read_text(encoding="utf-8"))
            messages.update(node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "_" and node.args
                and isinstance(node.args[0], ast.Constant))
        with override("fr"):
            for message in messages: self.assertNotEqual(gettext(message), message, message)
        self.setup_invoice()
        for language, word in [("en", "reason"), ("fr", "motif")]:
            with override(language), self.assertRaisesMessage(ValidationError, word): self.preview(reason="")
