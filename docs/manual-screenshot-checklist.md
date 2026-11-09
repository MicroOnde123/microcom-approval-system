# Microcom — Screenshot capture checklist / Liste des captures

**NONBLOCKING IMPROVEMENT BACKLOG: version 3.0 is released as a text-based guide. Capture work awaits an isolated environment and separate authorization.**

Verified source: 72b527b739d2e42a0ead10d17af4ec571876dfc8, current repository. Isolated capture access has not been supplied for this update. Database name was supplied for context only; no database was accessed. Do not start the application, create accounts, query databases or capture screens before the approved access is supplied. No production data.

## 1. Access and data prerequisites

Owner must supply: rehearsal URL; approved existing authentication method and role accounts (no passwords in docs); approved synthetic fixtures; permission for the sample lifecycle transitions to be captured; confirmation of actual build, schema/static files and private-PDF availability. Do not change flags or server configuration for screenshots. Financial notes need the deployed UI gate and permissions confirmed.

Required responsibilities: employee/technician, designated stock reviewer at the configured position and alternate, later/final approver, stock-only user, invoice creator/editor/finalizer, return-note issuer/document reader, administration-report reader and authorized administrator. Permissions may be combined only where the owner approves. Denial examples need a low-access account.

## 2. Visual and privacy standard

1. Capture separate English and French screens using the actual language selector. Use native PNG, preferably viewport 1440×1000 or larger at 100% browser zoom. Crop irrelevant space but retain title, relevant controls and status/reference context. Split long pages instead of shrinking unreadable text.

2. Use synthetic people, branches, materials, addresses and amounts. Check every header, user menu, file name, document party, browser tab and URL. Prefer sanitized fixtures; otherwise use irreversible flattened redaction in a sanitized copy. Never put confidential originals or filled passwords into the docs tree.

3. Use 24–32 px numbered circles in free margins and 2 px arrows/thin connector lines ending at exact controls; add subtle target outlines. Do not cover labels. Blue #2563EB actions/navigation; green #15803D completion; amber #B7791F warnings/checks; red #B91C1C errors/prohibitions. Use words/numbers as well as color. Each pointer must match its caption; split cross-screen pointers into separate images.

4. Save sanitized base and annotated PNG separately: {id}-base.png / {id}-annotated.png in docs/manual-assets/en/ or fr/. Retain only approved sanitized bases. Do not rename a pending SVG as if it were a capture. Each real image needs language, build, role, state, date, native dimensions, caption, pointer legend, reviewer and privacy review in the capture manifest.

5. Replace pending panels only with accepted real annotated screenshots. Add state-specific images immediately below the relevant instructions. Rebuild PDFs with real images; check every page at normal reading size and obtain owner/stock/Finance sign-off before removing draft warnings.

## 3. Every required screen-state

Each row needs a real EN image and a real FR image. All are missing. Some states need more than one image to preserve readable text. These future illustration plans are not coordinates verified against a running screen.

| ID | Chapter / screen-state | Entry | Pointer focus | EN | FR |
|---|---|---|---|---|---|
| 01-login | 1. Sign in | /login/ | Blue 1 — username; Blue 2 — empty password field; Blue 3 — login button; Amber 4 — reset link | MISSING | MISSING |
| 02-dashboard | 2. Navigate the dashboard | / | Blue 1 — request links; Blue 2 — Approvals and counter; Blue 3 — report/invoice links; Blue 4 — language/Logout | MISSING | MISSING |
| 03-administrative | 3. Create an administrative request | /requests/create/ | Blue 1 — type; Amber 2 — owning department; Blue 3 — conditional fields/attachments; Blue 4 — submit/draft | MISSING | MISSING |
| 03b-permission | 3. Leave Permission fields / Champs de permission de sortie | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 03c-site | 3. Site Authorization fields / Champs d’autorisation de site | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 03d-draft | 3. Saved draft and Edit Draft / Brouillon enregistré et modification | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 04-material | 4. Create a technician material request | /requests/create/ | Blue 1 — search/category; Amber 2 — selected material/unit; Blue 3 — quantity/add/remove; Blue 4 — submit | MISSING | MISSING |
| 05-classification | 5. Classify at the designated stock-review step | /approvals/{approval_id}/ | 1 — current step; 2 — classification; 3 — succursale; 4 — approval action | MISSING | MISSING |
| 05b-client | 5. CLIENT without branch / CLIENT sans succursale | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 06-succursale | 6. Select the succursale | /approvals/{approval_id}/ | Amber 1 — Microcom; Blue 2 — branch dropdown; Amber 3 — correct code/name; Green 4 — saved branch (another capture) | MISSING | MISSING |
| 06b-saved | 6. Saved classification and branch / Classification et succursale enregistrées | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 07-decisions | 7. Approve, reject or return | /approvals/pending/ | Blue 1 — filters; Blue 2 — Review; Amber 3 — decision/comment; Green 4 — result (another capture) | MISSING | MISSING |
| 07b-result | 7. Decision success and next step / Décision réussie et étape suivante | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 08-correction | 8. Correct, resubmit or cancel | /requests/{request_id}/edit/ | 1 — return comment; 2 — corrected information; 3 — resubmit result; 4 — archived attempts | MISSING | MISSING |
| 08b-cancel | 8. Cancel Request confirmation / Confirmation d’annulation | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 09-stock | 9. View availability and stock reports | /materials/reports/ | Blue 1 — filters; Amber 2 — stock quantity/badge; Blue 3 — View/Material Management; Blue 4 — exports | MISSING | MISSING |
| 10-catalog | 10. Maintain materials, prices and currencies | /admin/inventory/material/ | 1 — currency; 2 — change reason; 3 — Modify Price; 4 — price history | MISSING | MISSING |
| 10b-branch-admin | 10. Succursale admin and address / Administration succursale et adresse | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 10-price-dialog | 10. Modify Price and reason; stale conflict / Modifier le prix et motif ; conflit de version | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 10-price-history | 10. Read-only price audit history / Historique des prix en lecture seule | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 11-deduction | 11. Understand automatic deduction | /requests/{request_id}/ | Green 1 — Approved; Blue 2 — completed timeline; Amber 3 — quantities/live stock; Green 4 — OUT evidence (separate admin capture) | MISSING | MISSING |
| 11b-out | 11. OUT stock movement / Mouvement stock OUT | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 12-bcbs | 12. Issue BC and BS | /requests/{request_id}/material-documents/BC/ or BS/ | Amber 1 — BC/BS kind; Amber 2 — source request; Blue 3 — Confirm & Print; Green 4 — permanent reference (separate capture) | MISSING | MISSING |
| 12b-bc-issued | 12. Official BC print page / Page du BC officiel | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 12c-bs-issued | 12. Official BS print page / Page du BS officiel | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 13-invoice-draft | 13. Create and prepare an invoice draft | /invoices/ | Blue 1 — eligible request/create; Amber 2 — currency; Blue 3 — draft prices; Amber 4 — quantity refresh | MISSING | MISSING |
| 13b-currency | 13. Invoice creation currency / Devise à la création de facture | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 13c-prices | 13. Draft invoice prices and refresh / Prix et actualisation du brouillon | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 14-invoice-issue | 14. Verify and finalize the invoice | /invoices/{invoice_id}/finalize/ | Amber 1 — quantities/prices; Blue 2 — series; Amber 3 — confirmation; Green 4 — issued number/status (another capture) | MISSING | MISSING |
| 14b-finalized | 14. Finalized invoice details / Détails de facture finalisée | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 16-physical-return | 16. Record a physical stock return | /requests/{request_id}/material-outcomes/?tab=returns | Blue 1 — returns tab; Amber 2 — remaining maximum; Blue 3 — quantity/reason; Blue 4 — confirmation | MISSING | MISSING |
| 16b-confirm | 16. Physical return confirmation dialog / Dialogue de confirmation du retour | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 16c-full | 16. Fully returned and no active form / Retour complet sans formulaire actif | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 17-reconciliation | 17. Reconcile material usage | /requests/{request_id}/material-outcomes/?tab=reconcile | Blue 1 — three tabs; Blue 2 — destination/split; Amber 3 — returned/read-only and totals; Blue 4 — reason/review | MISSING | MISSING |
| 17b-overview | 17. Material Management Overview tab / Vue d’ensemble du matériel | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 17c-review | 17. Reconciliation review dialog / Dialogue de revue de régularisation | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 17d-history | 17. Reconciliation revision history / Historique des révisions | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 18-receipt | 18. Issue a nonfinancial RCP return receipt | /requests/{request_id}/material-outcomes/?tab=returns | Blue 1 — return checkboxes; Amber 2 — Generate Bon de retour; Green 3 — RCP reference; Blue 4 — PDF/Print (another capture) | MISSING | MISSING |
| 18b-confirm | 18. RCP selected-movement confirmation / Confirmation des mouvements RCP | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 18c-issued | 18. RCP history and PDF actions / Historique RCP et commandes PDF | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 18d-pdf | 18. Nonfinancial RCP PDF / PDF RCP non financier | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 19-return-note | 19. Issue an invoice-linked valued return note | /invoices/{invoice_id}/return-notes/new/ | Blue 1 — eligible movements; Amber 2 — reason/series; Blue 3 — preview; Amber 4 — preview totals/confirmation (separate capture) | MISSING | MISSING |
| 19b-preview | 19. Valued return-note preview / Aperçu du bon valorisé | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 19c-issued | 19. Issued valued return-note detail / Détails du bon valorisé émis | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 19d-history | 19. Valued return-note history / Historique des bons valorisés | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 20-audit | 20. Follow approvals and audit records | /requests/{request_id}/; /approvals/history/ | Blue 1 — reference/status; Blue 2 — timeline; Blue 3 — audit actor/time/comment; Blue 4 — linked histories | MISSING | MISSING |
| 20b-invoice-audit | 20. Invoice audit details / Détails d’audit de facture | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 20c-admin-report | 20. Administration Report and filters / Rapport administratif et filtres | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 20-access-document | 20. Approved Bon d’accès via Administration Report / Bon d’accès approuvé depuis le rapport Administration | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 21-users | 21. Manage users and permissions | /admin/accounts/user/ | Blue 1 — department/role; Amber 2 — stock/report flags; Amber 3 — exact permissions; Blue 4 — Active/staff/Save | MISSING | MISSING |
| 21b-permissions | 21. Explicit invoice/return-note permissions / Permissions facture/bon valorisé | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 22-workflows | 22. Configure approval workflows | /admin/workflows/approvalworkflow/ | 1 — type / department; 2 — order; 3 — stock review; 4 — assignment | MISSING | MISSING |
| 22b-first-review | 22. Designated named stock review / Revue du stock nominative à sa position configurée | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 23-company | 23. Configure verified company/document information | /admin/core/companydocumentsettings/; /admin/invoicing/documentsequence/ | Blue 1 — company identity/contacts; Amber 2 — currency/timezone; Blue 3 — attest action (list capture); Amber 4 — sequence verification (separate capture) | MISSING | MISSING |
| 23b-company-attest | 23. Company attestation list action / Action d’attestation société | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 23c-sequence | 23. Annual sequence and attestation / Séquence annuelle et attestation | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 24-print | 24. Print and download documents | /invoices/ and issued document pages | Amber 1 — language; Blue 2 — document print; Amber 3 — both issue dates; Blue 4 — PDF viewer controls (another capture) | MISSING | MISSING |
| 24b-filter-print | 24. Both issue dates and Print Filtered Invoices / Deux dates et impression des factures filtrées | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 24c-viewer | 24. Invoice PDF viewer print/save / Impression/enregistrement du PDF facture | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 24d-permission | 24. Approved Permission Document / Document d’autorisation approuvé | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 25-errors | 25. Troubleshoot without duplicate operations | Current workflow validation/error screen | Red 1 — exact error; Amber 2 — reference; Blue 3 — safe retry/back; Amber 4 — affected required field | MISSING | MISSING |
| 25b-pdf-error | 25. PDF unavailable and safe retry / PDF indisponible et reprise sûre | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 26-entry-new | 26. Register a new material and initial stock | /materials/entries/ | 1 — material information; 2 — initial stock; 3 — review; 4 — confirmation/reference | MISSING | MISSING |
| 26-review | 26. New material review before confirmation / Vérification du nouveau matériel avant confirmation | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 26-completed | 26. New material receipt completed / Réception du nouveau matériel terminée | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 27-entry-existing | 27. Receive an existing material | /materials/entries/?mode=existing | 1 — material selection; 2 — quantity and estimate; 3 — verification; 4 — historical confirmation | MISSING | MISSING |
| 27-completed | 27. Existing receipt historical balances / Soldes historiques d’une réception existante | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 28-entry-drafts | 28. Save, resume and cancel an entry draft | /materials/entries/ | 1 — Save Draft; 2 — saved notice; 3 — Resume Draft; 4 — cancellation confirmation | MISSING | MISSING |
| 28-saved | 28. Draft saved notice: continue/new entry / Brouillon enregistré : continuer/nouvelle entrée | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 28-cancel | 28. Draft cancellation confirmation / Confirmation d’annulation du brouillon | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 28-stale | 28. Stale draft refusal / Refus d’un brouillon périmé | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 29-notifications | 29. Use workflow notifications and email preferences | /notifications/ | 1 — notification menu; 2 — All/Unread; 3 — View Request / Mark as Read; 4 — email preference | MISSING | MISSING |
| 29-unread | 29. Unread filter and mark-read result / Filtre non lu et résultat du marquage | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |
| 29-preference | 29. Administrator email preference / Préférence de courriel dans Admin | Parent workflow entry | Reference + exact action + required check + result; adapt parent numbered legend to this state | MISSING | MISSING |

## 4. Separate validation/error examples

Capture the following as separate approved synthetic scenarios under 25-errors, each in EN and FR: missing classification; Microcom with no branch; insufficient final stock; excessive cumulative return; stale reconciliation; stale invoice revision/net quantity; unknown price; missing branch address; missing company attestation; missing verified annual series; expired return-note preview; Forbidden access. Under 25b-pdf-error capture invoice/receipt/valued-note PDF failure and the correct retry. Do not create faults in production or alter flags for evidence.

## 5. Boundaries and exact controls

- No credit-note screenshot target: chapter 15 is an availability notice. Models/guards are not an employee credit-note screen.
- No Deduct Stock button: capture Approved detail and matching OUT evidence.
- Stock review is opt-in configuration: confirm the designated test reviewer and configured position.
- Inspected settings enable MATERIAL_RETURN_NOTE_UI_ENABLED; older docs/fallback say off. Confirm actual rehearsal activation without changing it.
- Current RCP controls use application language, not the per-receipt selector mentioned in older notes.
- Capture official BC and BS independently; legacy bulk printing does not issue official references.
- Current filtered invoice action is Print Filtered Invoices, not checkbox-selected printing.

## 6. Completion ledger

- 28 primary pending illustration panels per language.
- 74 inventory rows × two languages, plus distinct validation/error variants; this is not a fixed final screenshot quota.
- Real screenshots captured: 0. Real screenshots annotated: 0. Authenticated workflows manually verified: 0.
- Markdown and PDF versions are final text-based guides with no inline screenshot placeholders. Future illustrated editions require genuine sanitized captures and verified annotations; screenshot gaps do not block this text release.
