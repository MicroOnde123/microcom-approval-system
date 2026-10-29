# Phase 2 Stage 1 foundations

This stage adds catalogue and document preferences only. One central material
balance remains authoritative. Succursales have no stock quantities, transfers,
department links or request assignments.
Future historical request/invoice relationships must use protected foreign keys;
this stage introduces no such relationship and assigns no historical request.

## Administrator screens

- Inventory / Succursales: unique code, name, active status and timestamps.
- Inventory / Materials: optional unit price and currency, retaining the existing
  original-balance check and locking for inventory admin saves.
- Core / Company and document settings: one optional configuration record with
  company identity/contact fields, a relative static logo reference, default
  currency and numbering formats. No company/address/contact data is seeded.

These screens use Django's existing staff/model permissions. Stock-report access
alone grants no succursale or company-configuration permissions. Settings cannot
be deleted through admin; edit the single record instead.

## Price semantics

Existing materials receive NULL price and NULL currency. NULL is unknown; a
decimal zero is a known, explicit price. Prices have two decimal places and may
not be negative. Initially supported currencies are USD, CDF and EUR; this is a
supported-currency list, not a complete ISO currency registry or conversion system.

Model/form validation defaults a newly supplied price's missing currency from the
company/document settings, falling back to USD. It does not populate currencies
on unpriced materials or change an already selected currency. Direct ORM callers
must call full_clean() or supply currency explicitly when entering a price.
Database checks reject negative prices, unsupported currency codes and a priced
material without currency. Stock services do not validate or require prices.

## Document preferences

The existing static logo is the default reference. External URLs and traversal
paths are rejected. The default format FAC/{number:04d}/{year} is a preference
only. Supported placeholders are number (once) and optional year; integer widths
are limited to 12. There are no counters, invoice records, PDFs or issued documents.
Company information must be verified by an administrator before future issuance.

## Migration safety

- core/0001_initial creates the optional singleton settings table.
- inventory/0003_succursale_material_currency_material_unit_price_and_more
  creates the succursale table, adds two nullable material columns, and adds price
  validation checks. No data migration or historical backfill is included.
- requests_app migrations 0015 and 0016 are unchanged.

The inventory migration takes schema locks and validates CHECK constraints on the
material table. Production lock contention and backup/restore preparation require
a separate release review. Reversing Stage 1 after configuration/pricing is entered
would discard the new data; do not treat reversal as a lossless operational rollback.

Existing request creation, ownership, routing, correction/resubmission, final
approval deduction, returns, reports, Excel and Bon de sortie are unchanged.
Approval records continue to be rebuilt on resubmission, as explicitly required.
New request classification and document generation require separate Stage 2 approval.
