# Annual invoice sequence preparation

The command is installed but is not automatically scheduled. After review and
database authorization, run from the project directory with its normal virtual
environment and verified development configuration:

```powershell
.\venv\Scripts\python.exe manage.py prepare_invoice_year --language en
.\venv\Scripts\python.exe manage.py prepare_invoice_year --language fr
```

It uses database time and the configured Africa/Kinshasa calendar. It prepares
the following year from **verified current-year INVOICE series only**, copying
their formats. New counters start at 1; this is a proposed annual starting
point, not authorization to issue. Existing target rows are reported and never
changed, even if their formats differ from the source. Source counters and
historical references remain untouched. No sequence is automatically attested.

Review each prepared row in Admin > Invoicing > Document sequences. Check its
year, series, format, starting counter, and external numbering history. Record
verification evidence and use the existing administrator verification action.
An authorized active staff member needs the existing change-document-sequence
permission. If external history requires another starting counter, configure it
before attestation and issuance. Never reset a used sequence.

Format conflict detection is deliberately conservative: only distinct,
non-overlapping literal prefixes prove separate series safe. Overlapping
prefixes stop all preparation with a nonzero exit code, even when later format
components might distinguish them. Existing target invoice series participate
in this check. Global reference uniqueness remains the final safeguard,
including against other document types; this command does not certify external
or cross-document numbering history.

Concurrent command runs serialize on the existing singleton company-settings
row, lock sequence rows in year/series order, and retain the unique scope
constraint. Manual concurrent administrative edits should be avoided during
preparation. No scheduler, role grants, financial triggers, or migrations are
introduced. Review missing/unverified output before year-end; schedule only
after operational approval. Running after midnight on January 1 prepares the
*next* year, not the newly started year.

Offline tests mock all persistence and do not prove PostgreSQL behavior.
`invoicing.test_year_preparation_postgresql` is supplied for a future explicitly
authorized isolated PostgreSQL test database; it has not been run against
Supabase or any database during implementation. Also defer concurrent real
finalization/rollover and database-trigger integration validation until that
environment is authorized. Keep MATERIAL_RETURN_NOTE_UI_ENABLED=False.
