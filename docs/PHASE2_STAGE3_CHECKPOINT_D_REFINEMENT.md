# Checkpoint D — PDF design refinement

Visual-only local refinement of the reviewed invoice design. Renderer version is
`invoice-a4-v2-rl5.1.0`; new generation cannot reuse the earlier logo-bearing v1
artifact. Existing artifacts and finalized records are not overwritten.

The A4 layout now uses a centered plain-text company header, compact monochrome
typography, aligned metadata, right-aligned numeric headings/values, light table
rules, right-aligned total and Service Stock, and tighter comments/summary spacing.
Widths account for the document frame's internal padding. There is no drawn or
embedded logo image. Frozen branding remains unchanged and its existing integrity
checks are retained. Company details still come exclusively from final snapshots.

Quantities trim redundant decimal zeros: 10.00 → 10, 1.50 → 1.5. Prices and totals
display at least two decimals: 2.0000 → 2.00, 2.1000 → 2.10. Significant price
precision is never rounded away: 2.1234 → 2.1234, 0.0001 → 0.0001. This changes
presentation only, with no Decimal-field, pricing, rounding or financial calculation
change. Existing English/French labels and stored French “Nous disons” are retained.

Final focused verification: **18/18 PDF tests passed**, zero failures/errors/skips,
71.062 seconds on identity-guarded disposable PostgreSQL18.6 at localhost15490,
database test_microcom_checkpoint_d_refinement. The preceding layout run also
passed18/18. The complete application suite was not rerun for this visual-only pass.
Coverage includes bilingual content, no image objects, quantity/price precision,
snapshot independence, permissions/CSRF, private downloads, checksums/tampering,
retry/storage failures, concurrent generation, financial-state preservation and
multi-page output. System checks, dry-run migration consistency, protected hashes,
French catalogue checks and diff whitespace checks passed. No migration, package
installation, translation-catalogue change or service modification was needed.

Windows.Data.Pdf generated actual page PNGs for visual inspection. Final English
and French single pages, pages2/3 of the 66-line French sample, and final pages of
both long-description languages were inspected. Accents, œ, €, $, literal escaped
text, metadata/table alignment, whole quantities, decimal prices, totals, French
words, comments, Service Stock and footers are readable without clipping. The
66-line invoice is now three pages; the long-description examples are four pages.
Sample company/address/contact data is explicitly synthetic, not a company attestation.

Evidence and review samples: `local_artifacts/checkpoint_d_refinement_evidence_5a453f88/`.
It contains five PDFs, thirteen rendered page PNGs, extracted EN/FR text, test results,
verification/checksum summary and cleanup/port evidence. Both fresh clusters were
stopped, their test databases dropped, and only the two owned disposable directories
were removed after absolute-path, PID and reparse-point checks. Localhost15489 and
15490 were verified free with exclusive binds. Existing staging/services were untouched.

Modified files:

- `invoicing/pdf.py` — presentation and renderer version only.
- `invoicing/test_documents.py` — revised no-logo/formatting assertions and precision test.
- `docs/PHASE2_STAGE3_CHECKPOINT_D.md` — link to this refinement report.

Created files:

- This document.
- `local_artifacts/test_checkpoint_d_refinement_runner.py`.
- `local_artifacts/checkpoint_d_refinement_guard.json`.
- The retained evidence directory listed above.

Hash checks confirm stock/approval services, invoice-finalization/pricing services,
document-storage/security and permission services remain unchanged. Finalized
snapshots, historical logo data, numbering, inventory and audit records are preserved.
Existing private-storage configuration/ACL requirements still apply. No production
access, commit, push, deployment or Checkpoint E work occurred. Ready for design review.
