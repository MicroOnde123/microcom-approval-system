"""Actual committed E-R2 races using independent PostgreSQL connections."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections, transaction, IntegrityError

from requests_app.services import approve_step
from .models import MaterialReturnNote, MaterialReturnNoteAudit, MaterialReturnNoteLine
from .test_return_note_services import ReturnNoteServiceFixtures


class ReturnNoteConcurrencyTests(ReturnNoteServiceFixtures):
    def worker(self, function, barrier=None):
        close_old_connections()
        try:
            if barrier: barrier.wait(10)
            try: return ("ok", function())
            except (ValidationError, IntegrityError): return ("blocked", None)
        finally:
            connections.close_all()

    def race(self, first, second):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, f, barrier) for f in (first, second)]
            return [future.result(30) for future in futures]

    def test_same_token_concurrent_exact_replay_commits_once(self):
        self.setup_invoice(); sequence = self.return_sequence(); preview = self.preview()
        results = self.race(lambda: self.issue(preview).pk, lambda: self.issue(preview).pk)
        self.assertEqual([r[0] for r in results], ["ok", "ok"])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(MaterialReturnNoteAudit.objects.count(), 1)
        self.assertEqual(MaterialReturnNoteLine.objects.count(), 1)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 8)

    def test_overlapping_selections_different_tokens_only_one_commits(self):
        self.setup_invoice(); sequence = self.return_sequence()
        a, b = self.preview(), self.preview()
        results = self.race(lambda: self.issue(a).pk, lambda: self.issue(b).pk)
        self.assertEqual(sorted(r[0] for r in results), ["blocked", "ok"])
        self.assertEqual(MaterialReturnNoteAudit.objects.count(), 1)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 8)

    def test_disjoint_same_invoice_stales_loser_then_repreview_serializes_rounding(self):
        self.partial_history(); second, _ = self.restore(1); self.return_sequence()
        a, b = self.preview(), self.preview([second])
        results = self.race(lambda: self.issue(a).pk, lambda: self.issue(b, [second]).pk)
        self.assertEqual(sorted(r[0] for r in results), ["blocked", "ok"])
        remaining = self.returned if not MaterialReturnNoteLine.objects.filter(return_movement=self.returned).exists() else second
        self.issue(self.preview([remaining]), [remaining])
        self.assertEqual(sum(n.total for n in MaterialReturnNote.objects.all()), self.invoice.total / 2)
        self.assertEqual(MaterialReturnNoteAudit.objects.count(), 2)

    def test_two_invoices_share_numbering_without_collision(self):
        self.partial_history(price="2"); sequence = self.return_sequence()
        original_invoice = self.invoice
        a = self.preview()
        first_movement = self.returned
        self.req, self.item = self.make_request(2)
        approve_step(self.req.approvals.get(), self.user, classification="MICROCOM", succursale=self.branch)
        self.req.refresh_from_db()
        invoice = self.create(); self.price(invoice, "2")
        self.invoice = self.finalize(invoice)
        self.returned, _ = self.restore(1)
        b = self.preview()
        from .return_note_services import issue_material_return_note
        def issue_original():
            return issue_material_return_note(original_invoice.pk, self.user, return_movement_ids=[first_movement.pk],
                reason="Returned materials", issuance_token=a["issuance_token"], confirmation=a["confirmation"]).number
        results = self.race(issue_original, lambda: self.issue(b).number)
        self.assertEqual([r[0] for r in results], ["ok", "ok"])
        self.assertNotEqual(results[0][1], results[1][1])
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 9)

    def test_credit_winner_blocks_waiting_issuance(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview(); credit = self.new_credit()
        started = Event()
        def contender():
            started.set()
            return self.issue(preview).pk
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.write("RESERVE"):
                self.allocation_row(credit)
                future = pool.submit(self.worker, contender)
                self.assertTrue(started.wait(5))
                with self.assertRaises(TimeoutError): future.result(.15)
            self.assertEqual(future.result(20)[0], "blocked")
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())

    def test_return_note_winner_blocks_waiting_credit(self):
        self.setup_invoice(); self.return_sequence(); preview = self.preview(); credit = self.new_credit()
        original = MaterialReturnNote.save
        futures = []
        started = Event()
        def contender():
            started.set()
            return self.reserve(credit).pk
        with ThreadPoolExecutor(max_workers=1) as pool:
            def hold(note, *args, **kwargs):
                value = original(note, *args, **kwargs)
                if note.status == "FINALIZED":
                    future = pool.submit(self.worker, contender); futures.append(future)
                    self.assertTrue(started.wait(5))
                    with self.assertRaises(TimeoutError): future.result(.15)
                return value
            with patch.object(MaterialReturnNote, "save", hold): self.issue(preview)
            self.assertEqual(futures[0].result(20)[0], "blocked")
        self.assertFalse(credit.allocations.exists())

    def test_concurrent_stock_return_stales_preview_without_second_inventory_adjustment(self):
        self.partial_history(); self.return_sequence(); preview = self.preview(); started = Event()
        def contender():
            started.set()
            return self.issue(preview).pk
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                self.restore(1)
                future = pool.submit(self.worker, contender)
                self.assertTrue(started.wait(5))
                with self.assertRaises(TimeoutError): future.result(.15)
            self.assertEqual(future.result(20)[0], "blocked")
        before = self.source_snapshot()
        self.issue(self.preview())
        self.assertEqual(before, self.source_snapshot())
