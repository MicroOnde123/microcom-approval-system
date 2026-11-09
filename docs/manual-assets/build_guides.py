"""Documentation build only: no Django, network, database or account operations.
Run: C:/MicrocomRehearsal/venv/Scripts/python.exe docs/manual-assets/build_guides.py
ReportLab is already installed in that environment.
"""
from pathlib import Path
from html import escape
import json

DOCS = Path(__file__).resolve().parents[1]
ASSETS = DOCS / "manual-assets"
COMMIT = "d3eb76641c1bd3efe431f26a4536964a0be1aeaf"
CARDS = []


def add(key, source, entry, en, fr, capture=True):
    # title, purpose/prerequisites, numbered steps, numbered callout targets,
    # warning, expected result. EN and FR carry the same information.
    assert len(en) == len(fr) == 6
    CARDS.append(dict(key=key, source=source, entry=entry, en=en, fr=fr, capture=capture))


add("01-login", "config/urls.py; accounts/forms.py; templates/registration/login.html", "/login/", (
    "Sign in", "Use your own active account. The rehearsal address and approved access method must first be supplied by the owner.",
    ["Open the supplied rehearsal URL and verify the environment.", "Enter username/password and use the login button.", "For a forgotten password, use the reset link and registered email; contact IT if delivery or the link fails."],
    ["Blue 1 — username", "Blue 2 — empty password field", "Blue 3 — login button", "Amber 4 — reset link"],
    "Never capture a populated password. Session expiry requires signing in again and can lose unsaved edits.",
    "Dashboard opens; invalid/inactive accounts cannot sign in."), (
    "Se connecter", "Utilisez votre compte actif. Le responsable doit d’abord fournir l’URL de répétition et l’accès approuvé.",
    ["Ouvrez l’URL fournie et vérifiez l’environnement.", "Saisissez identifiant/mot de passe puis utilisez le bouton de connexion.", "En cas d’oubli, utilisez le lien de réinitialisation et le courriel enregistré ; contactez l’informatique si nécessaire."],
    ["Bleu 1 — identifiant", "Bleu 2 — champ mot de passe vide", "Bleu 3 — connexion", "Ambre 4 — réinitialisation"],
    "Ne capturez jamais un mot de passe rempli. L’expiration exige une reconnexion et peut perdre les modifications non enregistrées.",
    "Le tableau de bord s’ouvre ; les comptes invalides/inactifs restent bloqués."))

add("02-dashboard", "core/views.py; templates/core/dashboard.html; templates/base.html; requests_app/context_processors.py", "/", (
    "Navigate the dashboard", "Signed-in users see navigation according to their access. Dashboard status text is not a live health check.",
    ["Use Create Request / New Request to begin and My Requests for your submissions.", "Use Approvals for current assigned steps and Approval History for your decisions.", "Open permitted reports or Invoices. Choose EN/FR with the language selector; use Logout when finished."],
    ["Blue 1 — request links", "Blue 2 — Approvals and counter", "Blue 3 — report/invoice links", "Blue 4 — language/Logout"],
    "A role name does not grant every menu. Check lists even without email: workflow notifications may fail silently.",
    "The right work area opens in the chosen language."), (
    "Naviguer dans le tableau de bord", "Les utilisateurs connectés voient la navigation selon leurs droits. Le texte de statut n’est pas un contrôle de santé en temps réel.",
    ["Utilisez Create Request / New Request pour commencer et My Requests pour vos soumissions.", "Approvals affiche vos étapes courantes ; Approval History vos décisions.", "Ouvrez les rapports autorisés ou Invoices. Choisissez FR/EN avec le sélecteur ; terminez par Logout."],
    ["Bleu 1 — demandes", "Bleu 2 — approbations/compteur", "Bleu 3 — rapports/factures", "Bleu 4 — langue/déconnexion"],
    "Un nom de rôle ne donne pas tous les menus. Consultez les listes même sans courriel : les notifications peuvent échouer silencieusement.",
    "La bonne rubrique s’ouvre dans la langue choisie."))

add("03-administrative", "requests_app/forms.py; requests_app/views.py:create_request; templates/requests_app/create_request.html", "/requests/create/", (
    "Create an administrative request", "Your account needs a department and a configured workflow. Request-type flags control required fields.",
    ["Choose Request Type and Request For Department: the owning team, not a billing succursale.", "Enter description, Date Needed and Amount when required; attach supporting files.", "For Leave Permission enter By Foot/By Car, destination and reason; travel times/driver are optional. Site Authorization requires site, validity dates, Microcom agents and reason; TT/external persons are optional.", "Submit Request, or Save as Draft. Reopen My Requests → Edit Draft, finish and submit."],
    ["Blue 1 — type", "Amber 2 — owning department", "Blue 3 — conditional fields/attachments", "Blue 4 — submit/draft"],
    "A draft starts no approvals or stock reservation. Recheck saved rows if incomplete. Amount is not an invoice/payment execution. Check chronological consistency yourself.",
    "Submission starts routing; a draft remains editable and unsubmitted. Note the reference."), (
    "Créer une demande administrative", "Le compte exige un département et un workflow configuré. Les indicateurs du type imposent les champs.",
    ["Choisissez Request Type et Request For Department : équipe responsable, pas succursale de facturation.", "Saisissez description, Date Needed et Amount si requis ; joignez les justificatifs.", "Leave Permission exige By Foot/By Car, destination et motif ; heures/chauffeur sont facultatifs. Site Authorization exige site, dates, agents Microcom et motif ; TT/personnes externes sont facultatifs.", "Submit Request, ou Save as Draft. Rouvrez My Requests → Edit Draft, complétez puis soumettez."],
    ["Bleu 1 — type", "Ambre 2 — département responsable", "Bleu 3 — champs conditionnels/pièces", "Bleu 4 — soumission/brouillon"],
    "Un brouillon ne lance ni approbation ni réservation. Vérifiez les lignes incomplètes sauvegardées. Amount n’est ni facture ni paiement. Contrôlez la chronologie vous-même.",
    "La soumission lance le circuit ; le brouillon reste modifiable et non soumis. Relevez la référence."))

add("04-material", "requests_app/forms.py; requests_app/views.py:create_request; templates/requests_app/includes/material_formset.html", "/requests/create/", (
    "Create a technician material request", "Choose a material request type, owning department and active catalog materials. All materials come from central stock.",
    ["Enter purpose/destination and Date Needed.", "Search by name, code or category, or Filter By Category; select the actual item and enter a positive quantity in its unit.", "Use + Add Material / Remove, one row per item; review then Submit Request or Save as Draft."],
    ["Blue 1 — search/category", "Amber 2 — selected material/unit", "Blue 3 — quantity/add/remove", "Blue 4 — submit"],
    "At least one item, no duplicates, and valid positive quantities are required. Stock is checked at entry and final approval; nothing is reserved. No editable item-note box is rendered: use the description.",
    "The request enters approval. Technicians do not perform stock classification or select the billing branch."), (
    "Créer une demande de matériel de technicien", "Choisissez type matériel, département responsable et articles actifs. Tout provient du stock central.",
    ["Saisissez objet/destination et Date Needed.", "Recherchez par nom, code ou catégorie, ou Filter By Category ; choisissez l’article réel et une quantité positive dans son unité.", "Utilisez + Add Material / Remove, une ligne par article ; vérifiez puis Submit Request ou Save as Draft."],
    ["Bleu 1 — recherche/catégorie", "Ambre 2 — article/unité", "Bleu 3 — quantité/ajout/retrait", "Bleu 4 — soumission"],
    "Au moins un article, sans doublon, avec quantités positives valides. Stock contrôlé à la saisie et à la fin ; rien n’est réservé. Aucune note par ligne affichée : utilisez la description.",
    "La demande entre en approbation. Les techniciens ne classent pas et ne choisissent pas la succursale de facturation."))

add("05-classification", "requests_app/approval_forms.py; requests_app/classification.py; requests_app/services.py:approve_step; workflows/models.py", "/approvals/{approval_id}/", (
    "Perform the stock-lady classification", "Only the active primary/alternate assigned to the designated first Stock classification review can confirm classification.",
    ["Open Approvals, inspect the request details, then Review.", "Choose Approve and Stock classification: Client or Microcom.", "For Client leave Succursale empty; for Microcom select the appropriate active branch. Add Comment and Submit."],
    ["Blue 1 — Action", "Amber 2 — Stock classification", "Amber 3 — Succursale", "Blue 4 — Comment/Submit"],
    "Reject/Return for changes does not require classification. Other steps cannot classify. Workflows without a designated review are still allowed by code: administrators must configure this first step for the intended process.",
    "The classification, reviewer and time are saved; approval advances. CLIENT requests are excluded from internal invoicing."), (
    "Effectuer la classification par la responsable du stock", "Seul le principal/suppléant actif affecté à la première Stock classification review désignée peut confirmer.",
    ["Ouvrez Approvals, examinez les détails puis Review.", "Choisissez Approve et Stock classification : Client ou Microcom.", "Pour Client, laissez Succursale vide ; pour Microcom choisissez la succursale active appropriée. Ajoutez Comment puis Submit."],
    ["Bleu 1 — action", "Ambre 2 — classification", "Ambre 3 — succursale", "Bleu 4 — commentaire/soumission"],
    "Reject/Return for changes n’exige pas de classification. Les autres étapes ne classent pas. Le code autorise les circuits sans revue désignée : l’administrateur doit la configurer en premier pour le processus voulu.",
    "Classification, acteur et date sont enregistrés ; le circuit avance. CLIENT est exclu de la facturation interne."))

add("06-succursale", "requests_app/approval_forms.py; requests_app/classification.py; inventory/models.py:Succursale; inventory/admin.py", "/approvals/{approval_id}/", (
    "Select the succursale", "A succursale is an administrative/billing entity, never a warehouse. You must be the designated stock reviewer approving Microcom.",
    ["Confirm the intended destination with the requesting team and select its code/name in Succursale.", "If missing/inactive, ask an authorized administrator to review Inventory → Succursales; do not substitute another branch or department.", "Submit and check classification/branch in request details."],
    ["Amber 1 — Microcom", "Blue 2 — branch dropdown", "Amber 3 — correct code/name", "Green 4 — saved branch (another capture)"],
    "Microcom requires a branch; Client must not select one. New branches require physical address; final invoicing requires it for older branches too. Selection never transfers stock.",
    "The billing entity is linked; stock remains central."), (
    "Choisir la succursale", "Une succursale est administrative/de facturation, jamais un entrepôt. Vous êtes l’approbatrice stock désignée approuvant Microcom.",
    ["Confirmez la destination avec l’équipe et choisissez code/nom dans Succursale.", "Si absente/inactive, faites contrôler Inventory → Succursales par un administrateur ; ne remplacez pas par une autre succursale ou un département.", "Soumettez puis vérifiez classification/succursale dans les détails."],
    ["Ambre 1 — Microcom", "Bleu 2 — liste succursales", "Ambre 3 — code/nom exact", "Vert 4 — succursale enregistrée (autre capture)"],
    "Microcom exige une succursale ; Client n’en accepte pas. Adresse physique requise à la création et à la facture, même pour les anciennes. La sélection ne transfère aucun stock.",
    "L’entité de facturation est liée ; le stock reste central."))

add("07-decisions", "requests_app/views.py:pending_approvals,approval_detail; requests_app/services.py; requests_app/approval_forms.py", "/approvals/pending/", (
    "Approve, reject or return", "Only your current pending primary/alternate step of an open request is actionable.",
    ["Filter Approvals by type, owning department, search or Date Needed range.", "Inspect details, amount, materials and attachments before Review / Approve Request.", "Choose Approve, Reject or Return for changes, explain in Comment and Submit; refresh to check result."],
    ["Blue 1 — filters", "Blue 2 — Review", "Amber 3 — decision/comment", "Green 4 — result (another capture)"],
    "Comment is optional in code but should explain rejection/correction. Once one assigned actor acts, the other cannot repeat. Later steps wait; superuser alone cannot bypass assignment. Required does not skip steps.",
    "Approve advances/finalizes; Return sets Returned; Reject closes as Rejected, without ordinary resubmission."), (
    "Approuver, rejeter ou retourner", "Seule votre étape principale/suppléante courante en attente d’une demande ouverte est traitable.",
    ["Filtrez Approvals par type, département responsable, recherche ou période Date Needed.", "Examinez détails, montant, matériels et pièces avant Review / Approve Request.", "Choisissez Approve, Reject ou Return for changes, expliquez dans Comment puis Submit ; actualisez."],
    ["Bleu 1 — filtres", "Bleu 2 — examen", "Ambre 3 — décision/commentaire", "Vert 4 — résultat (autre capture)"],
    "Commentaire facultatif mais recommandé pour rejet/correction. Après l’action d’un acteur, l’autre ne répète pas. Les suivants attendent ; superutilisateur seul ne contourne pas l’affectation. Required ne saute pas d’étape.",
    "Approve avance/finalise ; Return produit Returned ; Reject clôt en Rejected, sans resoumission ordinaire."))

add("08-correction", "requests_app/views.py:edit_request,cancel_request; requests_app/services.py:resubmit_request; templates/requests_app/edit_request.html", "/requests/{request_id}/edit/", (
    "Correct, resubmit or cancel", "Ordinary editing is for your own Draft/Returned requests. Read the return comment first.",
    ["Open My Requests → detail → Edit and Resubmit (or Edit Draft).", "Correct fields and material rows; add attachments if needed. There is no ordinary attachment-delete control.", "Save Changes keeps Returned; Resubmit Request rebuilds routing. Drafts use Save Draft / Submit Request.", "If no longer needed, Cancel Request and confirm: owner/superuser can cancel Draft, Returned, Pending or In Review only."],
    ["Amber 1 — return comment", "Blue 2 — edit action", "Blue 3 — corrected fields", "Blue 4 — save/resubmit"],
    "Resubmission still deletes old approval rows. Audit actions/comments remain, but full earlier assignments/timeline do not. The history-preservation business rule remains incomplete. Preserve required evidence by company procedures.",
    "The corrected request restarts the current applicable workflow. Cancellation stops an open request; it cannot reverse approved stock."), (
    "Corriger, resoumettre ou annuler", "La modification ordinaire concerne vos Draft/Returned. Lisez d’abord le commentaire de retour.",
    ["My Requests → détails → Edit and Resubmit (ou Edit Draft).", "Corrigez champs et lignes ; ajoutez des pièces si besoin. Aucun retrait ordinaire des pièces existantes.", "Save Changes conserve Returned ; Resubmit Request recrée le routage. Brouillons : Save Draft / Submit Request.", "Si inutile, Cancel Request puis confirmez : propriétaire/superutilisateur peuvent annuler seulement Draft, Returned, Pending ou In Review."],
    ["Ambre 1 — commentaire de retour", "Bleu 2 — modifier", "Bleu 3 — champs corrigés", "Bleu 4 — enregistrer/resoumettre"],
    "La resoumission supprime encore les anciennes étapes. Actions/commentaires restent, pas toutes les affectations/l’ancien suivi. L’exigence de conservation reste incomplète. Conservez les preuves selon les procédures internes.",
    "La demande corrigée relance le workflow actuel applicable. L’annulation arrête une demande ouverte, sans inverser le stock approuvé."))

add("09-stock", "inventory/models.py; requests_app/views.py:material_reports; templates/requests_app/material_reports.html", "/materials/reports/", (
    "View availability and stock reports", "Employees see availability in picker/permitted details. Material Reports requires can_manage_stock or superuser.",
    ["Read the material unit and Available Stock; availability is central and live.", "In Material Reports search request/requester/material; filter Date Needed and owning department.", "Use View or Material Management; export filtered CSV/Excel. Checkboxes select legacy bulk prints, not export scope."],
    ["Blue 1 — filters", "Amber 2 — stock quantity/badge", "Blue 3 — View/Material Management", "Blue 4 — exports"],
    "Not a stock reservation or historic balance. Badges use fixed thresholds 5/10, not the catalog minimum. Requested-quantity Excel analytics are not net returns, current inventory or monetary value; unlike units are not equivalent.",
    "Find approved material requests and download the filtered report without moving stock."), (
    "Consulter disponibilité et rapports stock", "Disponibilité visible au sélecteur/détails autorisés. Material Reports exige can_manage_stock ou superutilisateur.",
    ["Lisez unité et Available Stock : disponibilité centrale actuelle.", "Recherchez demande/demandeur/matériel dans Material Reports ; filtrez Date Needed et département responsable.", "Utilisez View ou Material Management ; exportez CSV/Excel filtrés. Cases pour impressions groupées historiques, pas périmètre d’export."],
    ["Bleu 1 — filtres", "Ambre 2 — stock/alerte", "Bleu 3 — consultation/gestion", "Bleu 4 — exports"],
    "Ni réservation ni solde historique. Alertes fixes 5/10, pas minimum catalogue. Analyses Excel de quantités demandées : ni net après retours, inventaire courant ou valeur financière ; unités différentes non équivalentes.",
    "Retrouvez les demandes approuvées et exportez sans mouvement stock."))

add("10-catalog", "inventory/models.py; inventory/admin.py; core/document_config.py", "/admin/inventory/material/", (
    "Configure materials, prices and currencies", "Authorized staff with Inventory model permissions maintains the shared catalog.",
    ["Maintain Inventory → Material categories, then open Materials and add/select an item.", "Set category, unique code, name, description, unit, Active, stock quantity and minimum level.", "Set Unit price when known and USD/CDF/EUR Price currency, then Save. Reload/review if a stale stock conflict appears."],
    ["Blue 1 — material identity", "Amber 2 — stock/unit", "Blue 3 — price/currency", "Blue 4 — Save"],
    "Blank price means unknown; zero is explicit. Catalog prices have two decimals; draft invoice prices allow four. No currency conversion. Direct stock edits do not automatically create IN movements or implement controlled receiving/stocktake.",
    "Catalog changes can initialize future same-currency invoice drafts; finalized invoices stay unchanged."), (
    "Configurer matériels, prix et devises", "Le personnel autorisé avec droits Inventory tient le catalogue partagé.",
    ["Gérez Inventory → Material categories puis Materials, ajoutez/sélectionnez l’article.", "Renseignez catégorie, code unique, nom, description, unité, Active, quantité et minimum.", "Renseignez Unit price si connu et Price currency USD/CDF/EUR puis Save. Rechargez/vérifiez en cas de conflit stock périmé."],
    ["Bleu 1 — identité", "Ambre 2 — stock/unité", "Bleu 3 — prix/devise", "Bleu 4 — enregistrement"],
    "Prix vide = inconnu ; zéro explicite. Catalogue à deux décimales, brouillon facture à quatre. Aucune conversion. Modification directe du stock sans IN automatique ni circuit contrôlé de réception/inventaire.",
    "Les changements initialisent les futurs brouillons dans la même devise ; les factures finalisées restent inchangées."))

add("11-deduction", "requests_app/services.py:approve_step; requests_app/stock_services.py:deduct_material_stock", "/requests/{request_id}/", (
    "Understand automatic deduction", "There is no Deduct Stock button. The final assigned approver completes the material workflow.",
    ["Review and submit the final Approve action.", "If insufficient stock is reported, ask stock staff to review; do not force Approved manually.", "On success check Approved and the timeline; authorized administrators can inspect related OUT movements."],
    ["Green 1 — Approved", "Blue 2 — completed timeline", "Amber 3 — quantities/live stock", "Green 4 — OUT evidence (separate admin capture)"],
    "The service locks request/material balances and uses stock_deducted against repeated deduction. Failure rolls back final approval. Safeguards were inspected, not runtime-tested for these guides.",
    "Stock deducts once and OUT movements record the actor. Documents/invoices/reconciliation never deduct again."), (
    "Comprendre la déduction automatique", "Aucun bouton Deduct Stock. Le dernier approbateur affecté termine le circuit matériel.",
    ["Examinez puis soumettez la dernière action Approve.", "Si stock insuffisant, faites contrôler par le stock ; ne forcez pas Approved.", "Après réussite, vérifiez Approved et le suivi ; un administrateur autorisé peut consulter les OUT liés."],
    ["Vert 1 — Approved", "Bleu 2 — suivi terminé", "Ambre 3 — quantités/stock actuel", "Vert 4 — preuve OUT (capture administrative séparée)"],
    "Le service verrouille demande/soldes et utilise stock_deducted contre les répétitions. Un échec annule la dernière approbation. Protections inspectées, pas testées à l’exécution pour ces guides.",
    "Déduction unique et OUT avec acteur. Documents/factures/régularisation ne déduisent pas à nouveau."))

add("12-bcbs", "requests_app/material_documents.py; requests_app/views.py:material_document; templates/requests_app/material_document_confirm.html", "/requests/{request_id}/material-documents/BC/ or BS/", (
    "Issue BC and BS", "BC is an internal material order; BS is the authorized issue document. Requires Approved, stock_deducted, material rows and permitted request/document access.",
    ["In detail or Material Reports open the required BC or BS action.", "At first issuance check kind/reference, then Confirm & Print. Cancel allocates nothing.", "Check the official reference, choose Print 1 copy / Print 2 copies; over six items forces one. Print / Save as PDF, review A4, sign/archive."],
    ["Amber 1 — BC/BS kind", "Amber 2 — source request", "Blue 3 — Confirm & Print", "Green 4 — permanent reference (separate capture)"],
    "Confirmation allocates once; reprints reuse it. Format examples: BC/0001/2026 and BS/0001/2026, not actual records. Issuance never moves stock. Legacy bulk printing does not allocate official BC/BS.",
    "The numbered document opens. Reference is frozen; live names, available stock and editable issue remarks may change on reprint."), (
    "Émettre les BC et BS", "BC : commande interne ; BS : autorisation de sortie. Exige Approved, stock_deducted, lignes matériel et accès documentaire autorisé.",
    ["Dans les détails ou Material Reports, ouvrez l’action BC ou BS voulue.", "À la première émission, contrôlez type/référence puis Confirm & Print. Cancel n’attribue rien.", "Vérifiez référence officielle, Print 1 copy / Print 2 copies ; plus de six articles impose un exemplaire. Print / Save as PDF, vérifiez A4, signez/archivez."],
    ["Ambre 1 — type BC/BS", "Ambre 2 — demande source", "Bleu 3 — confirmation", "Vert 4 — référence définitive (autre capture)"],
    "Confirmation unique ; même référence en réimpression. Exemples : BC/0001/2026 et BS/0001/2026, pas des données réelles. Aucun mouvement stock. L’impression groupée historique n’attribue pas de BC/BS officiels.",
    "Le document numéroté s’ouvre. Référence figée ; noms, stock actuel et remarques peuvent varier à la réimpression."))

add("13-invoice-draft", "invoicing/permissions.py; invoicing/views.py:invoice_list,invoice_create,invoice_edit; invoicing/services.py", "/invoices/", (
    "Create and prepare an invoice draft", "One invoice per individual eligible MICROCOM request, on demand. Requires view_invoice + add_invoice and scope, Approved/deducted stock evidence, first-review confirmation/branch and valid company configuration.",
    ["In Invoices choose the eligible request’s Create invoice draft; select Invoice currency and confirm creation.", "Open Edit invoice draft: check Net billable quantity, enter authorized Unit price and optional Invoice note; Save draft prices.", "After new physical returns use Refresh issued quantities, then review/save again before finalization."],
    ["Blue 1 — eligible request/create", "Amber 2 — currency", "Blue 3 — draft prices", "Amber 4 — quantity refresh"],
    "CLIENT excluded. Draft has no official number. Net quantities = issued less returns. Other-currency catalog prices remain unknown; no conversion. Zero is explicit, blank unknown. Duplicate/ambiguous stock evidence blocks invoicing.",
    "An editable unnumbered draft is ready for review; no stock/payment operation occurs."), (
    "Créer et préparer un brouillon de facture", "Une facture par demande MICROCOM admissible, à la demande. Exige view_invoice + add_invoice et périmètre, preuves Approved/déduction, première revue/succursale et société valide.",
    ["Dans Invoices, choisissez Create invoice draft de la demande ; sélectionnez Invoice currency puis créez.", "Edit invoice draft : vérifiez Net billable quantity, saisissez Unit price autorisés et éventuel Invoice note ; Save draft prices.", "Après de nouveaux retours physiques : Refresh issued quantities, puis revérifiez/enregistrez avant finalisation."],
    ["Bleu 1 — demande/création", "Ambre 2 — devise", "Bleu 3 — prix du brouillon", "Ambre 4 — actualisation"],
    "CLIENT exclu. Aucun numéro officiel au brouillon. Net = sorties moins retours. Prix d’autre devise inconnu, sans conversion. Zéro explicite, vide inconnu. Preuves ambiguës/doublons bloquent.",
    "Brouillon modifiable non numéroté prêt à vérifier ; aucune opération stock/paiement."))

add("14-invoice-issue", "invoicing/forms.py; invoicing/services.py:finalize_invoice; invoicing/views.py:invoice_finalize", "/invoices/{invoice_id}/finalize/", (
    "Verify and finalize the invoice", "Requires view_invoice + finalize_invoice and scope; prices/net quantities reviewed; current company attestation, verified annual series and branch physical address.",
    ["Open Finalize invoice and compare materials, net quantities, prices and totals to evidence.", "Choose Invoice series. If absent, ask the authorized administrator to verify numbering; do not invent a number.", "Tick permanent confirmation and Finalize invoice. Check Finalized, number, issue date, branch, total and Invoice history."],
    ["Amber 1 — quantities/prices", "Blue 2 — series", "Amber 3 — confirmation", "Green 4 — issued number/status (another capture)"],
    "User review and administrator attestations are prerequisites, not an extra invoice approval status. Financial/party snapshots and number become immutable. Currency consistent; date/year Africa/Kinshasa. New returns/stale revision require refresh/review.",
    "Permanent bookkeeping invoice issued without a second stock deduction. Later returns do not silently rewrite it; ordinary edit/delete is unavailable."), (
    "Vérifier et finaliser la facture", "Exige view_invoice + finalize_invoice et périmètre ; prix/net vérifiés ; attestation société, série annuelle vérifiée et adresse physique de succursale.",
    ["Ouvrez Finalize invoice et comparez articles, net, prix et totaux aux preuves.", "Choisissez Invoice series. Si absente, faites vérifier la numérotation ; n’inventez pas de numéro.", "Cochez la confirmation permanente puis Finalize invoice. Vérifiez Finalized, numéro, date, succursale, total et historique."],
    ["Ambre 1 — quantités/prix", "Bleu 2 — série", "Ambre 3 — confirmation", "Vert 4 — numéro/statut émis (autre capture)"],
    "Revue utilisateur et attestations sont des prérequis, pas un statut supplémentaire. Données financières/parties et numéro deviennent immuables. Devise homogène ; date/année Africa/Kinshasa. Nouveaux retours/révision périmée : actualiser/revoir.",
    "Pièce comptable définitive sans seconde déduction. Les retours ne la réécrivent pas ; modification/suppression ordinaire indisponible."))

add("15-credit-boundary", "invoicing/models.py:CreditNote,CreditAllocation,CreditOperation; invoicing/migrations/0004_credit_reservation_schema.py; invoicing/migrations/0005_credit_financial_guards.py; invoicing/urls.py; invoicing/admin.py", "No employee credit-note route", (
    "Credit notes: availability boundary", "Credit models/database safeguards exist, but no employee credit-note creation/issue route or registered credit admin lifecycle was found.",
    ["Record original invoice reference and actual physical return evidence.", "Ask Finance/IT to assess the accounting action; do not invent a Create credit note button.", "Keep physical RCP receipt, invoice-linked return valuation and accounting credit separate."],
    ["No screenshot target — no reachable credit-note UI", "Red boundary — no raw admin/database record creation"],
    "Schema safeguards include finalized original invoice/currency, attributable returns, reservation caps, explicit review, verified numbering and immutable final evidence. This does not prove deployed guards or expose a user workflow. Active credit allocations can block valued return notes.",
    "The accounting need is escalated without fabricating a credit. This is a boundary notice, not an issue procedure."), (
    "Avoirs : limite de disponibilité", "Modèles/protections de base présents, mais aucune route utilisateur de création/émission ni cycle administratif d’avoir enregistré trouvé.",
    ["Relevez facture d’origine et preuves de retour physique.", "Demandez l’évaluation aux Finances/informatique ; n’inventez pas de bouton Create credit note.", "Distinguez reçu RCP, valorisation liée à la facture et avoir comptable."],
    ["Aucune capture cible — pas d’interface d’avoir accessible", "Limite rouge — pas de création brute administration/base"],
    "Protections : facture finalisée/devise, retours attribuables, plafonds, revue explicite, numérotation vérifiée et preuves finales immuables. Cela ne prouve ni protections déployées ni parcours utilisateur. Les affectations d’avoir actives peuvent bloquer les bons valorisés.",
    "Besoin transmis sans fabriquer d’avoir. Limite de disponibilité, pas procédure d’émission."), capture=False)

add("16-physical-return", "requests_app/stock_services.py:return_material_stock,material_return_totals; requests_app/material_outcome_views.py; requests_app/stock_forms.py", "/requests/{request_id}/material-outcomes/?tab=returns", (
    "Record a physical stock return", "Stock access, Approved/deducted material request and consistent OUT/RETURN evidence are required. Receive the goods before recording.",
    ["Material Management → Returns & Receipts: expand the correct material. The standalone Return to Stock page remains available.", "Check Available to return; enter positive Returned Quantity (two decimals) and required Return Reason.", "Confirm return to stock, review the dialog then Confirm; Back cancels. Check success/new remainder. Fully returned items have no active form."],
    ["Blue 1 — returns tab", "Amber 2 — remaining maximum", "Blue 3 — quantity/reason", "Blue 4 — confirmation"],
    "Cumulative cap enforced. Locks and one transaction protect stock/movement/audit. Exact committed-token replay does not restore twice. If uncertain retry the same form or inspect history, not a new operation. Ambiguous old evidence is blocked. Server checks apply without JavaScript.",
    "Stock restored once with RETURN/audit reason. Ten issued minus four returned leaves six eligible. No invoice, credit or receipt is automatically issued."), (
    "Enregistrer un retour physique", "Accès stock, demande Approved/déduite et preuves OUT/RETURN cohérentes requis. Recevez les biens avant saisie.",
    ["Material Management → Returns & Receipts : développez l’article. La page séparée Return to Stock reste disponible.", "Vérifiez Available to return ; saisissez Returned Quantity positive (deux décimales) et Return Reason obligatoire.", "Confirm return to stock, vérifiez le dialogue puis Confirm ; Back annule. Vérifiez réussite/reste. Retour complet : aucun formulaire actif."],
    ["Bleu 1 — onglet retours", "Ambre 2 — reste maximal", "Bleu 3 — quantité/motif", "Bleu 4 — confirmation"],
    "Plafond cumulé contrôlé. Verrous/transaction protègent stock/mouvement/audit. Rejeu exact du jeton validé sans double ajout. Si incertain, même formulaire ou historique, pas nouvelle opération. Anciennes preuves ambiguës bloquées. Contrôles serveur sans JavaScript.",
    "Stock restauré une fois, RETURN/motif. Dix sortis moins quatre retournés : six admissibles. Aucun document financier/reçu automatique."))

add("17-reconciliation", "requests_app/material_outcomes.py:reconcile; requests_app/material_outcome_views.py; templates/requests_app/material_outcomes.html", "/requests/{request_id}/material-outcomes/?tab=reconcile", (
    "Reconcile material usage", "Stock personnel record outcomes for the original technician on an Approved/deducted request. Original classification is unchanged.",
    ["Use Material Management → Overview, then Reconcile and expand each material.", "Use quick destination for all remaining units or Split quantities / multiple outcomes: CLIENT-installed, MICROCOM-used, Retained / testing.", "Physically returned is read-only from movements. All four outcomes must total issued quantity. Enter Short explanation, Review and save, review then Confirm; inspect Reconciliation history."],
    ["Blue 1 — three tabs", "Blue 2 — destination/split", "Amber 3 — returned/read-only and totals", "Blue 4 — reason/review"],
    "Before a revision, usage is unknown. New physical returns can mark the old revision Review required. Reload stale data and append a new revision; old revisions remain. No stock/invoice changes.",
    "Versioned outcomes account for every unit: e.g. ten issued = four CLIENT + two MICROCOM + one retained + three physically returned."), (
    "Régulariser l’utilisation du matériel", "Le stock enregistre les résultats pour le technicien d’origine d’une demande Approved/déduite. Classification initiale inchangée.",
    ["Material Management → Overview, puis Reconcile et développez chaque article.", "Destination rapide pour tout le reste ou Split quantities / multiple outcomes : CLIENT-installed, MICROCOM-used, Retained / testing.", "Physically returned vient des mouvements, en lecture seule. Les quatre résultats totalisent la sortie. Short explanation, Review and save, vérifiez puis Confirm ; consultez Reconciliation history."],
    ["Bleu 1 — trois onglets", "Bleu 2 — destination/répartition", "Ambre 3 — retour figé/totaux", "Bleu 4 — motif/revue"],
    "Avant révision, usage inconnu. De nouveaux retours peuvent produire Review required. Rechargez et ajoutez une révision ; les anciennes restent. Aucun changement stock/facture.",
    "Résultats versionnés pour toute unité : dix sortis = quatre CLIENT + deux MICROCOM + un conservé + trois retournés."))

add("18-receipt", "requests_app/material_outcomes.py:issue_receipt; requests_app/material_outcome_views.py:receipt_pdf; requests_app/return_receipt_documents.py", "/requests/{request_id}/material-outcomes/?tab=returns", (
    "Issue a nonfinancial RCP return receipt", "The stock button Generate Bon de retour creates an RCP physical-return receipt, not a financial credit or invoice-linked valuation.",
    ["With stock access, select recorded physical RETURN movements under Material Return Receipt.", "Generate Bon de retour, review selections and Confirm; Back issues nothing.", "Check the RCP reference/history. Set application language, then View PDF / Print; use the PDF viewer to save/print."],
    ["Blue 1 — return checkboxes", "Amber 2 — Generate Bon de retour", "Green 3 — RCP reference", "Blue 4 — PDF/Print (another capture)"],
    "Only actual distinct returns not already in an RCP. Exact token replay reuses the receipt. No stock change, credit, refund or invoice adjustment. On PDF failure use retry on this receipt; do not issue another.",
    "A permanent RCP/year reference and frozen return snapshot are available through protected PDF access."), (
    "Émettre un reçu RCP non financier", "Generate Bon de retour crée un reçu RCP de retour physique, pas un avoir ou une valorisation liée à la facture.",
    ["Avec accès stock, sélectionnez les RETURN réels dans Material Return Receipt.", "Generate Bon de retour, vérifiez puis Confirm ; Back n’émet rien.", "Vérifiez référence/historique RCP. Réglez la langue de l’application puis View PDF / Print ; utilisez le lecteur pour enregistrer/imprimer."],
    ["Bleu 1 — cases retours", "Ambre 2 — génération", "Vert 3 — référence RCP", "Bleu 4 — PDF/impression (autre capture)"],
    "Retours réels distincts pas encore reçus dans un RCP. Rejeu exact : même reçu. Ni stock, avoir, remboursement ou ajustement facture. Échec PDF : reprise du reçu, pas nouvelle émission.",
    "Référence RCP/année permanente et données de retour figées en PDF protégé."))

add("19-return-note", "invoicing/return_note_access.py; invoicing/return_note_views.py; invoicing/return_note_services.py; invoicing/return_note_forms.py; config/settings.py", "/invoices/{invoice_id}/return-notes/new/", (
    "Issue an invoice-linked valued return note", "Requires enabled UI, finalized internal invoice, eligible complete returns, verified RETURN_NOTE year/series, invoice scope and dedicated permissions.",
    ["From finalized invoice open Issue material return note or Material return note history.", "Select eligible complete movements, Operation reason and Return note series; Preview material return note.", "Check original invoice, frozen prices, quantities, returned value, cumulative value and adjusted net value. Change selection if needed; preview allocates no number.", "Tick permanent confirmation and Issue material return note; check its number/history, then Print if permitted."],
    ["Blue 1 — eligible movements", "Amber 2 — reason/series", "Blue 3 — preview", "Amber 4 — preview totals/confirmation (separate capture)"],
    "Current settings enable UI; fallback/older notes say disabled: verify deployment, do not change flags. Pre-invoice excluded returns, duplicates, ambiguous provenance or active credit allocations can block. Confirmation max two hours; session may expire earlier. Lost response: check history first.",
    "Permanent valuation issued at original invoice prices, without stock change, credit/payment adjustment or rewriting the original invoice. Distinct from RCP."), (
    "Émettre un bon valorisé lié à la facture", "Exige interface activée, facture interne finalisée, retours complets admissibles, série/année RETURN_NOTE vérifiée, périmètre et droits dédiés.",
    ["Depuis la facture finalisée : Issue material return note ou Material return note history.", "Sélectionnez mouvements complets, Operation reason et Return note series ; Preview material return note.", "Vérifiez facture, prix figés, quantités, valeur retournée, cumul et valeur nette ajustée. Change selection si besoin ; aperçu sans numéro.", "Cochez la confirmation permanente puis Issue material return note ; vérifiez numéro/historique puis Print selon droits."],
    ["Bleu 1 — mouvements admissibles", "Ambre 2 — motif/série", "Bleu 3 — aperçu", "Ambre 4 — totaux/confirmation (autre capture)"],
    "Paramètres actuels activés, repli/anciennes notes désactivés : vérifiez le déploiement sans changer les drapeaux. Retours exclus avant facture, doublons, preuve ambiguë ou avoirs affectés actifs peuvent bloquer. Confirmation max deux heures, session parfois plus courte. Réponse perdue : historique d’abord.",
    "Valorisation permanente aux prix d’origine sans stock, avoir/ajustement paiement ni réécriture de facture. Distincte du RCP."))

add("20-audit", "requests_app/views.py:request_detail,approval_history,administration_reports; invoicing/views.py:invoice_detail; templates/requests_app/request_detail.html", "/requests/{request_id}/; /approvals/history/", (
    "Follow approvals and audit records", "Use ownership/assignment or appropriate report/invoice access; report-only rights do not unlock ordinary request detail.",
    ["Open My Requests → detail: reference/status, origin/owning departments, attachments, Approval Timeline and Audit Log.", "Approval History shows your latest qualifying non-pending action per request, not all assignments; filter owning department.", "Invoice history → Audit details explains financial events. Material Management shows reconciliation revisions and RCP history.", "Administration Report readers filter approved configured-type requests by search, origin/owner/requester and submission dates, then View Document / Print (25 per page)."],
    ["Blue 1 — reference/status", "Blue 2 — timeline", "Blue 3 — audit actor/time/comment", "Blue 4 — linked histories"],
    "Draft/cancelled requests are excluded from approval history. Resubmission removes prior approval rows. Audit is not every field’s immutable snapshot. Direct attachment/media authorization still needs deployment checks.",
    "Support can trace a reference/action/time and distinguish decisions, stock and document evidence."), (
    "Suivre approbations et audit", "Utilisez propriété/affectation ou droits rapport/facture ; accès rapport seul n’ouvre pas les détails ordinaires.",
    ["My Requests → détails : référence/statut, origine/responsable, pièces, Approval Timeline et Audit Log.", "Approval History affiche votre dernière action non en attente admissible par demande, pas toutes les affectations ; filtre responsable.", "Invoice history → Audit details explique les événements financiers. Material Management conserve révisions et historique RCP.", "Administration Report : type configuré approuvé, recherche, origine/responsable/demandeur et dates de soumission, puis View Document / Print (25/page)."],
    ["Bleu 1 — référence/statut", "Bleu 2 — suivi", "Bleu 3 — acteur/date/commentaire", "Bleu 4 — historiques liés"],
    "Brouillons/annulations exclus de l’historique d’approbation. La resoumission enlève les étapes antérieures. Audit n’est pas une copie immuable de tous les champs. Autorisation directe des médias à vérifier.",
    "Le support relie référence/action/heure en distinguant décisions, stock et documents."))

add("21-users", "accounts/admin.py; accounts/models.py; invoicing/permissions.py; requests_app/material_outcomes.py:authorize", "/admin/accounts/user/", (
    "Manage users and permissions", "Authorized staff/model access and an approved account process are required. No accounts are created during guide preparation.",
    ["Accounts → Users: maintain identity, required email, department, role, Active; maintain Departments/Roles separately.", "Grant Can Manage Stock Reports / Can view administration reports only as needed; staff/model access is separate.", "Invoices require view_invoice plus add/change/finalize as needed and stock-review assignment scope. Broad scope: superuser or staff + manage_all_invoices.", "Valued notes: view_invoice + view_materialreturnnote; preview also issue_materialreturnnote; issue also add_materialreturnnote; documents also view_materialreturnnote_document. Save and arrange access verification."],
    ["Blue 1 — department/role", "Amber 2 — stock/report flags", "Amber 3 — exact permissions", "Blue 4 — Active/staff/Save"],
    "Custom ModelAdmin is not the standard password wizard: never type plaintext in its raw password field; use approved provisioning/reset. Deactivate leavers, preserve actors. Stock flag or staff alone grants no invoice actions/scope.",
    "Existing accounts have the approved permissions; assigned current steps still control approvals."), (
    "Gérer comptes et permissions", "Accès staff/modèles et procédure de comptes approuvés requis. Aucun compte créé pendant cette préparation.",
    ["Accounts → Users : identité, courriel requis, département, rôle, Active ; Departments/Roles séparément.", "Accordez Can Manage Stock Reports / Can view administration reports selon besoin ; accès staff/modèles distinct.", "Factures : view_invoice et add/change/finalize nécessaires, avec périmètre d’affectation revue stock. Global : superutilisateur ou staff + manage_all_invoices.", "Bons valorisés : view_invoice + view_materialreturnnote ; aperçu aussi issue_materialreturnnote ; émission aussi add_materialreturnnote ; documents aussi view_materialreturnnote_document. Enregistrez puis faites vérifier."],
    ["Bleu 1 — département/rôle", "Ambre 2 — indicateurs stock/rapport", "Ambre 3 — permissions exactes", "Bleu 4 — Active/staff/Save"],
    "ModelAdmin personnalisé sans assistant standard : jamais de mot de passe en clair dans le champ brut ; procédure approuvée. Désactivez les départs, conservez les acteurs. Stock ou staff seul ne donne pas facturation/périmètre.",
    "Les comptes existants ont les droits approuvés ; les étapes courantes affectées contrôlent l’approbation."))

add("22-workflows", "workflows/models.py; workflows/admin.py; requests_app/services.py:get_applicable_workflow,create_approval_steps", "/admin/workflows/approvalworkflow/", (
    "Configure approval workflows", "Authorized administrator and agreed policy. Routing uses type/amount and owning department, then department-free global fallback.",
    ["Maintain Request types and Requires materials / Requires amount / Is permission request flags; keep assigned reference namespaces unchanged.", "Workflows → Approval workflows: type, optional owning department, amount bounds, Active.", "Add unique ordered steps: specific user or active owning-department role user, with alternate where appropriate.", "For material workflow designate one first Stock classification review, explicit active primary and active optional alternate. Save; arrange separate authorized rehearsal validation."],
    ["Blue 1 — type/department/bounds", "Blue 2 — ordered steps", "Amber 3 — first stock-review checkbox", "Amber 4 — named active actors"],
    "Review designation is opt-in, so code accepts no-review workflows: avoid that for the required process. Avoid empty workflows, overlapping ranges and ambiguous role users. Required does not implement optional-step skipping.",
    "Future submissions use configured steps; saving configuration is not proof of runtime acceptance."), (
    "Configurer les workflows", "Administrateur autorisé et politique approuvée. Routage par type/montant et département responsable, puis repli global sans département.",
    ["Gérez Request types et indicateurs Requires materials / Requires amount / Is permission request ; espace de référence affecté inchangé.", "Workflows → Approval workflows : type, responsable facultatif, bornes, Active.", "Ajoutez étapes ordonnées uniques : utilisateur ou rôle actif du département responsable, avec suppléant si besoin.", "Pour matériel, une première Stock classification review, principal actif explicite et suppléant actif facultatif. Enregistrez ; validation séparée autorisée ensuite."],
    ["Bleu 1 — type/département/bornes", "Bleu 2 — ordre", "Ambre 3 — première revue stock", "Ambre 4 — acteurs nommés actifs"],
    "Désignation facultative : code accepte sans revue ; évitez pour le processus requis. Évitez circuits vides, plages chevauchantes et rôles ambigus. Required ne saute pas d’étape facultative.",
    "Les futures soumissions suivent la configuration ; enregistrer ne prouve pas la réception à l’exécution."))

add("23-company", "core/models.py; core/admin.py; invoicing/admin.py; invoicing/models.py:CompanyVerification,DocumentSequence; inventory/admin.py", "/admin/core/companydocumentsettings/; /admin/invoicing/documentsequence/", (
    "Configure verified company/document information", "Authorized staff/model rights including invoicing.add_companyverification for company attestation and invoicing.change_documentsequence for sequence attestation; checked external numbering history.",
    ["Core → Company and document settings: name, verified address, contacts, existing static logo reference, default USD/CDF/EUR and Africa/Kinshasa timezone; Save.", "In the list select settings and Attest current company information after checking; re-attest relevant changes.", "Invoicing → Document sequences: correct INVOICE or RETURN_NOTE type/year/series/format/safe starting value and external-history evidence. Save, select and Attest checked external numbering history.", "Inventory → Succursales: maintain code/name/active/physical address; new branches require address and invoicing requires it."],
    ["Blue 1 — company identity/contacts", "Amber 2 — currency/timezone", "Blue 3 — attest action (list capture)", "Amber 4 — sequence verification (separate capture)"],
    "Never guess counters, lower used counters or rewrite issued references. Format preferences alone allocate nothing; BC/BS and RCP have separate automatic counters. No authorization here to run year-preparation commands or change flags.",
    "Current company and annual numbering have recorded attestations, enabling issuance if other checks pass; frozen existing documents remain unchanged."), (
    "Configurer société et informations documentaires vérifiées", "Droits staff/modèles dont invoicing.add_companyverification pour société et invoicing.change_documentsequence pour séquence ; historique externe contrôlé.",
    ["Core → Company and document settings : nom, adresse vérifiée, contacts, logo statique existant, devise USD/CDF/EUR et Africa/Kinshasa ; Save.", "Dans la liste, sélectionnez et Attest current company information après contrôle ; réattestez les changements pertinents.", "Invoicing → Document sequences : INVOICE ou RETURN_NOTE, année/série/format/départ sûr et preuves externes. Save, sélectionnez puis Attest checked external numbering history.", "Inventory → Succursales : code/nom/actif/adresse ; nouvelles succursales et facturation exigent l’adresse."],
    ["Bleu 1 — identité/contacts", "Ambre 2 — devise/fuseau", "Bleu 3 — attestation (capture de liste)", "Ambre 4 — séquence/vérification (autre capture)"],
    "N’inventez pas de compteur, ne baissez pas les utilisés et ne réécrivez pas les références. Format seul sans attribution ; BC/BS et RCP ont des compteurs séparés. Aucune autorisation de commande annuelle ou changement de drapeau.",
    "Société courante et numérotation annuelle attestées, émission possible si autres contrôles réussis ; documents figés inchangés."))

add("24-print", "invoicing/views.py:invoice_print,invoice_bulk_print; invoicing/printing.py; invoicing/print_delivery.py; requests_app/material_outcome_views.py; templates/invoicing/list.html", "/invoices/ and issued document pages", (
    "Print and download documents", "Authorized document access and issued/finalized documents; browser PDF capability. Check type, reference and language.",
    ["Set application language; finalized invoice → Print Invoice. The server prepares its protected PDF; use viewer print/save.", "For filtered invoices, supply both issue dates in Invoices, narrow search/status then Print Invoices. Server selects finalized matches across pages; maximum 20.", "BC/BS use Print / Save as PDF and copy controls. RCP uses View PDF / Print; valued return note uses Print.", "Approved permissions use Permission Document → Print / Save PDF. Authorized Administration Report readers use View Document / Print."],
    ["Amber 1 — language", "Blue 2 — document print", "Amber 3 — both issue dates", "Blue 4 — PDF viewer controls (another capture)"],
    "Invoice printing uses protected PDF artifacts, not page-body printing. Filtered print has 20-document, size and page limits. PDF failure does not undo issuance: retry existing document, not a new invoice/receipt. Legacy material bulk print allocates no official BC/BS.",
    "Reviewed PDF/print uses the existing official reference. Layout, printer behaviour and download protection still require rehearsal verification."), (
    "Imprimer et télécharger les documents", "Accès documentaire autorisé, documents émis/finalisés et navigateur PDF. Vérifiez type, référence et langue.",
    ["Réglez la langue ; facture finalisée → Print Invoice. Le serveur prépare le PDF protégé ; utilisez le lecteur.", "Factures filtrées : deux dates d’émission dans Invoices, recherche/statut puis Print Invoices. Sélection serveur des finalisées sur toutes les pages ; maximum 20.", "BC/BS : Print / Save as PDF et exemplaires. RCP : View PDF / Print ; bon valorisé : Print.", "Autorisations approuvées : Permission Document → Print / Save PDF. Lecteurs Administration Report : View Document / Print."],
    ["Ambre 1 — langue", "Bleu 2 — impression document", "Ambre 3 — deux dates", "Bleu 4 — lecteur PDF (autre capture)"],
    "Factures via PDF protégé, pas impression du corps de page. Limites de 20, taille/pages. Échec PDF sans annuler émission : reprenez l’existant, pas une nouvelle facture/reçu. Impression groupée historique sans BC/BS officiel.",
    "PDF/imprimé vérifié avec référence existante. Mise en page, imprimante et protection à vérifier en répétition."))

add("25-errors", "requests_app/approval_forms.py; requests_app/stock_services.py; invoicing/services.py; invoicing/return_note_services.py; PDF error templates", "Current workflow validation/error screen", (
    "Troubleshoot without duplicate operations", "Read exact error and preserve request/document reference. IT handles configuration/inconsistent evidence.",
    ["Missing workflow/department/approver: report type, owning department and amount; check My Requests before recreating.", "Classification: Client without branch; Microcom with active branch. Stock/excess return/stale revision: refresh evidence, correct quantity; never force status/movements.", "Invoice missing price/address/attestation/series: resolve with Finance/IT. PDF failure: retry existing document.", "Expired confirmation: reopen/preview as directed. Uncertain issuance: history first. Forbidden: check action permission and request scope."],
    ["Red 1 — exact error", "Amber 2 — reference", "Blue 3 — safe retry/back", "Amber 4 — affected required field"],
    "Never create a new return/receipt/invoice just to check the first. No passwords or confidential attachments in support messages. A missing credit-note screen is a product boundary.",
    "Resolve/escalate with reference, time and exact message, avoiding duplicate stock/documents."), (
    "Dépanner sans doublons", "Lisez l’erreur exacte et conservez la référence. Configuration/preuves incohérentes relèvent de l’informatique.",
    ["Workflow/département/approbateur absent : signalez type, responsable et montant ; vérifiez My Requests avant recréation.", "Classification : Client sans succursale, Microcom avec active. Stock/retour excessif/révision périmée : actualisez/corrigez, jamais de statut/mouvement forcé.", "Facture sans prix/adresse/attestation/série : Finances/informatique. Échec PDF : reprise de l’existant.", "Confirmation expirée : rouvrez/refaites l’aperçu. Émission incertaine : historique d’abord. Forbidden : permission et périmètre."],
    ["Rouge 1 — erreur exacte", "Ambre 2 — référence", "Bleu 3 — reprise/retour sûr", "Ambre 4 — champ concerné"],
    "Jamais de nouvelle opération pour vérifier la première. Ni mots de passe ni pièces confidentielles au support. Écran d’avoir absent : limite produit.",
    "Résolvez/transmettez référence, heure et message exact, sans doublons stock/document."))

# These are additional real screen states, not generated screen images.
EXTRA = [
    ("03b-permission",3,"Leave Permission fields","Champs de permission de sortie"),
    ("03c-site",3,"Site Authorization fields","Champs d’autorisation de site"),
    ("03d-draft",3,"Saved draft and Edit Draft","Brouillon enregistré et modification"),
    ("05b-client",5,"CLIENT without branch","CLIENT sans succursale"),
    ("06b-saved",6,"Saved classification and branch","Classification et succursale enregistrées"),
    ("07b-result",7,"Decision success and next step","Décision réussie et étape suivante"),
    ("08b-cancel",8,"Cancel Request confirmation","Confirmation d’annulation"),
    ("10b-branch-admin",10,"Succursale admin and address","Administration succursale et adresse"),
    ("11b-out",11,"OUT stock movement","Mouvement stock OUT"),
    ("12b-bc-issued",12,"Official BC print page","Page du BC officiel"),
    ("12c-bs-issued",12,"Official BS print page","Page du BS officiel"),
    ("13b-currency",13,"Invoice creation currency","Devise à la création de facture"),
    ("13c-prices",13,"Draft invoice prices and refresh","Prix et actualisation du brouillon"),
    ("14b-finalized",14,"Finalized invoice details","Détails de facture finalisée"),
    ("16b-confirm",16,"Physical return confirmation dialog","Dialogue de confirmation du retour"),
    ("16c-full",16,"Fully returned and no active form","Retour complet sans formulaire actif"),
    ("17b-overview",17,"Material Management Overview tab","Vue d’ensemble du matériel"),
    ("17c-review",17,"Reconciliation review dialog","Dialogue de revue de régularisation"),
    ("17d-history",17,"Reconciliation revision history","Historique des révisions"),
    ("18b-confirm",18,"RCP selected-movement confirmation","Confirmation des mouvements RCP"),
    ("18c-issued",18,"RCP history and PDF actions","Historique RCP et commandes PDF"),
    ("18d-pdf",18,"Nonfinancial RCP PDF","PDF RCP non financier"),
    ("19b-preview",19,"Valued return-note preview","Aperçu du bon valorisé"),
    ("19c-issued",19,"Issued valued return-note detail","Détails du bon valorisé émis"),
    ("19d-history",19,"Valued return-note history","Historique des bons valorisés"),
    ("20b-invoice-audit",20,"Invoice audit details","Détails d’audit de facture"),
    ("20c-admin-report",20,"Administration Report and filters","Rapport administratif et filtres"),
    ("21b-permissions",21,"Explicit invoice/return-note permissions","Permissions facture/bon valorisé"),
    ("22b-first-review",22,"First named stock review","Première revue stock nominative"),
    ("23b-company-attest",23,"Company attestation list action","Action d’attestation société"),
    ("23c-sequence",23,"Annual sequence and attestation","Séquence annuelle et attestation"),
    ("24b-filter-print",24,"Both issue dates and Print Filtered Invoices","Deux dates et impression des factures filtrées"),
    ("24c-viewer",24,"Invoice PDF viewer print/save","Impression/enregistrement du PDF facture"),
    ("24d-permission",24,"Approved Permission Document","Document d’autorisation approuvé"),
    ("25b-pdf-error",25,"PDF unavailable and safe retry","PDF indisponible et reprise sûre"),
]

TEXT = {
    "en": {
        "title":"Microcom Approval System", "subtitle":"Employee Training Guide",
        "draft":"REVIEW DRAFT — REAL SCREENSHOTS PENDING",
        "status":"Not ready for final employee distribution. Real annotated screenshots and acceptance sign-off are still required.",
        "intro":"Source: updated rehearsal checkout, not the older workspace application. The owner confirms rehearsal is not running. Capture must wait for the owner-supplied URL and approved access method. No application/database was started or accessed, no accounts created and no workflow executed. The following are code-supported training drafts, not manually verified instructions. English UI source labels remain as precise references; French labels must be matched to actual captures before release.",
        "central":"Microcom has one central stock. Succursales are administrative/billing entities, never warehouses. Request For Department owns/routes the request; it is not a billing succursale. Original stock classification is distinct from later usage outcomes. CLIENT requests are excluded from internal invoicing; eligible MICROCOM requests can have an individual invoice created when needed.",
        "legend":"Blue #2563EB: navigation/actions. Green #15803D: completed result. Amber #B7791F: warning/required check. Red #B91C1C: error/prohibition. Planned numbers below identify future real-image callouts. Pending panels are not screenshots and depict no application UI.",
        "flow":"Draft/request → submit → designated first stock review (when configured) → ordered approvals → final approval and one stock deduction. Then issue BC/BS and, for eligible MICROCOM, create/review/finalize the invoice. Later: physical return restores stock; reconciliation records outcomes; RCP documents physical returns; invoice-linked note values returns. None automatically creates an accounting credit.",
        "roles":[("Employee / technician","Own submissions, own Draft/Returned editing, own open cancellation and permitted approved documents; department needed to create."),("Primary / alternate approver","Current assigned pending step only; permitted assigned-request access. Later approvers wait."),("Stock personnel","can_manage_stock or superuser: reports, physical returns, reconciliation, RCP and approved material issue notes. No invoice grant implied."),("Administration report reader","can_view_administration_reports or superuser: approved configured-type report across departments; no ordinary detail/approval grant."),("Invoice operator","view_invoice plus action permission and stock-review assignment scope; superuser or staff + manage_all_invoices for global scope."),("Administrator","Staff/model permissions and explicit financial attestations. Role names alone are not blanket permissions.")],
        "gloss":[("Draft / Returned / Rejected","Unsubmitted / needs correction / closed by rejection: distinct states."),("Pending / In Review / Approved / Cancelled","Open approval / under review / final success / stopped before completion."),("Origin / owning department","Submitter department / Request For Department for routing and most filters."),("CLIENT / MICROCOM","Original classification confirmed by designated first stock reviewer."),("BC / BS","Internal material order / authorized material issue, each with an official reference."),("Invoice","Bookkeeping snapshot for one eligible MICROCOM request; not a payment operation."),("RCP receipt","Nonfinancial evidence of physical returns, not credit/refund/invoice adjustment."),("Valued return note","Invoice-linked valuation of already-returned materials, not physical stock restoration or credit."),("Reconciliation","Versioned CLIENT-installed, MICROCOM-used, retained and physically returned outcomes."),("OUT / RETURN","Actual stock deduction / actual stock restoration movement."),("Material Issue Note","Free-text issue remarks: stock users open approved material detail, edit the note and Save Note. It appears in documents/reports; not a separately numbered document. Old full note text is not preserved in the update event."),("Audit / snapshot","Action evidence / frozen document data; not every request field has historical snapshots.")],
        "references":"New ordinary references follow REQ-{namespace}-{counter}/{year}, e.g. REQ-MAT-0001/2026 or REQ-ADM-0001/2026: examples only, not real records. They are durable at creation, including drafts; older references remain unchanged. BC/BS/RCP allocate independently at issuance in the Africa/Kinshasa business year. Never manually reuse/rewrite references.",
        "toc":"Contents","start":"Using this guide","before":"Before you begin","steps":"Do this","pointers":"Planned visual pointers — not yet verified on real screens","warning":"Important check","result":"Expected result","missing":"REAL SCREENSHOT PENDING","missing_text":"No application screen is depicted. Capture waits for approved rehearsal access.","appendix":"Glossary and references","extra":"Additional required captures","source":"Code trace",
    },
    "fr": {
        "title":"Système d’approbation Microcom", "subtitle":"Guide de formation des employés",
        "draft":"PROJET À RELIRE — CAPTURES RÉELLES EN ATTENTE",
        "status":"Non prêt pour diffusion finale aux employés. Captures réelles annotées et validation de réception restent nécessaires.",
        "intro":"Source : code de répétition actualisé, pas ancienne application de l’espace de travail. Le responsable confirme que la répétition n’est pas démarrée. Les captures attendent son URL et l’accès approuvé. Aucune application/base démarrée ou consultée, aucun compte créé ni parcours exécuté. Ces projets suivent le code, sans vérification manuelle. Les libellés source anglais servent de repères précis ; les libellés français devront correspondre aux captures réelles avant publication.",
        "central":"Microcom possède un stock central unique. Les succursales sont administratives/de facturation, jamais des entrepôts. Request For Department possède/oriente la demande ; ce n’est pas une succursale de facturation. La classification initiale diffère des utilisations ultérieures. CLIENT est exclu de la facturation interne ; chaque demande MICROCOM admissible peut avoir une facture selon besoin.",
        "legend":"Bleu #2563EB : navigation/actions. Vert #15803D : résultat obtenu. Ambre #B7791F : avertissement/contrôle. Rouge #B91C1C : erreur/interdiction. Les numéros prévus ci-dessous désignent les futurs repères réels. Les panneaux d’attente ne sont pas des captures et ne représentent aucune interface.",
        "flow":"Brouillon/demande → soumission → première revue stock désignée (si configurée) → approbations ordonnées → approbation finale et déduction unique. Puis BC/BS et, pour MICROCOM admissible, création/revue/finalisation de facture. Ensuite : retour physique restaure le stock ; régularisation décrit les résultats ; RCP documente les retours ; bon lié à facture les valorise. Aucun ne crée automatiquement d’avoir comptable.",
        "roles":[("Employé / technicien","Ses soumissions, modification de ses Draft/Returned, annulation de ses demandes ouvertes et documents autorisés ; département requis pour créer."),("Principal / suppléant","Étape courante affectée en attente seulement ; consultation affectée autorisée. Les suivants attendent."),("Personnel du stock","can_manage_stock ou superutilisateur : rapports, retours physiques, régularisations, RCP et notes approuvées. Aucun droit facture implicite."),("Lecteur administratif","can_view_administration_reports ou superutilisateur : rapport approuvé du type configuré tous départements, sans détails ordinaires/approbation."),("Opérateur facture","view_invoice et droit d’action, périmètre de revue stock ; superutilisateur ou staff + manage_all_invoices pour global."),("Administrateur","Droits staff/modèles et attestations financières explicites. Un nom de rôle n’accorde pas tout.")],
        "gloss":[("Draft / Returned / Rejected","Non soumis / à corriger / clos par rejet : états distincts."),("Pending / In Review / Approved / Cancelled","Approbation ouverte / en examen / réussite finale / arrêté avant fin."),("Origine / responsable","Département demandeur / Request For Department pour routage et principaux filtres."),("CLIENT / MICROCOM","Classification initiale confirmée par première revue stock désignée."),("BC / BS","Commande interne / sortie autorisée, chacun avec référence officielle."),("Facture","Pièce comptable figée d’une demande MICROCOM admissible ; pas une opération de paiement."),("Reçu RCP","Preuve non financière de retour physique, ni avoir/remboursement/ajustement facture."),("Bon valorisé","Valorisation liée à facture du matériel déjà retourné, pas restauration physique ou avoir."),("Régularisation","Résultats versionnés : installé CLIENT, utilisé MICROCOM, conservé, retourné."),("OUT / RETURN","Mouvement réel de déduction / restauration du stock."),("Material Issue Note","Remarques libres : le stock ouvre les détails approuvés, modifie puis Save Note. Visible dans documents/rapports ; pas de numéro distinct. Le texte antérieur complet n’est pas conservé par l’événement."),("Audit / données figées","Preuves d’actions / données documentaires conservées ; pas d’historique complet de tous les champs.")],
        "references":"Nouvelles références : REQ-{espace}-{compteur}/{année}, ex. REQ-MAT-0001/2026 ou REQ-ADM-0001/2026 : formats illustratifs, pas des données réelles. Durables à la création, brouillons compris ; anciennes références inchangées. BC/BS/RCP attribuent séparément à l’émission dans l’année Africa/Kinshasa. Ne réutilisez/réécrivez jamais manuellement.",
        "toc":"Sommaire","start":"Utiliser ce guide","before":"Avant de commencer","steps":"Procédure","pointers":"Repères visuels prévus — non vérifiés sur écran réel","warning":"Contrôle important","result":"Résultat attendu","missing":"CAPTURE RÉELLE EN ATTENTE","missing_text":"Aucune interface n’est représentée. Capture après accès de répétition approuvé.","appendix":"Glossaire et références","extra":"Captures complémentaires requises","source":"Référence du code",
    },
}


def placeholder(path, ident, lang):
    t=TEXT[lang]
    path.write_text(f"""<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="380" viewBox="0 0 1440 380" role="img" aria-label="{escape(t['missing'])}">
<rect width="1440" height="380" rx="16" fill="#f4f7fb"/>
<rect x="12" y="12" width="1416" height="356" rx="12" fill="none" stroke="#b7791f" stroke-width="3" stroke-dasharray="12 8"/>
<text x="60" y="75" font-family="Arial,sans-serif" font-size="24" font-weight="bold" fill="#17365d">MICROCOM · {ident} · {lang.upper()}</text>
<text x="60" y="165" font-family="Arial,sans-serif" font-size="32" font-weight="bold" fill="#996500">{escape(t['missing'])}</text>
<text x="60" y="230" font-family="Arial,sans-serif" font-size="24" fill="#475569">{escape(t['missing_text'])}</text>
<text x="60" y="315" font-family="Arial,sans-serif" font-size="20" fill="#64748b">d3eb766 · Documentation draft / Projet documentaire</text></svg>""",encoding="utf-8")


def md_table(headers, rows):
    return "\n".join(["| "+" | ".join(headers)+" |","|"+"---|"*len(headers)]+["| "+" | ".join(row)+" |" for row in rows])


def markdown(lang):
    t=TEXT[lang]
    other="fr" if lang=="en" else "en"
    blocks=["![Microcom](manual-assets/microcom-logo.png)",f"# {t['title']}",f"## {t['subtitle']}",f"**{t['draft']}**","Version 2.0-preparation · 31 October / octobre 2026",f"Source: C:/MicrocomRehearsal/app · {COMMIT}",t["status"],
        f"[Validation](user-manual-validation.md) · [Capture checklist / Liste des captures](manual-screenshot-checklist.md) · [EN/FR](user-manual-{other}.md)",f"## {t['toc']}"]
    toc=[f"- [0. {t['start']}](#guide-start)"]+[f"- [{i}. {c[lang][0]}](#{c['key']})" for i,c in enumerate(CARDS,1)]+[f"- [A. {t['appendix']}](#glossary)"]
    blocks+=["\n".join(toc),'<a id="guide-start"></a>',f"## 0. {t['start']}",t["intro"],t["central"],t["legend"],md_table(["Role / Rôle","Access / Accès"],t["roles"]),t["flow"]]
    for n,c in enumerate(CARDS,1):
        title,pre,steps,pointers,warn,result=c[lang]
        blocks += [f'<a id="{c["key"]}"></a>',f"## {n}. {title}",f"**{t['before']}** — {pre}",f"### {t['steps']}","\n\n".join(f"{i}. {step}" for i,step in enumerate(steps,1))]
        if c["capture"]:
            dest=ASSETS/lang/(c["key"]+"-pending.svg")
            placeholder(dest,c["key"],lang)
            blocks += [f"![{t['missing']} — {title}](manual-assets/{lang}/{dest.name})",f"*{lang.upper()}-{c['key']} · {t['missing']}*",f"### {t['pointers']}","\n".join("- "+x for x in pointers)]
            extra=[e for e in EXTRA if e[1]==n]
            if extra:
                blocks += [f"**{t['extra']}:** "+"; ".join(e[0]+" — "+e[2 if lang=="en" else 3] for e in extra)+"."]
        else:
            blocks+=["\n".join("> "+x for x in pointers)]
        blocks += [f"> **{t['warning']}** — {warn}",f"> **{t['result']}** — {result}",f"<details><summary>{t['source']}</summary>\n\n{c['source']}\n\n</details>"]
    blocks += ['<a id="glossary"></a>',f"## A. {t['appendix']}",t["references"],md_table(["Term / Terme","Meaning / Sens"],t["gloss"]),t["status"]]
    (DOCS/f"user-manual-{lang}.md").write_text("\n\n".join(blocks)+"\n",encoding="utf-8")


def checklist():
    rows=[]
    for n,c in enumerate(CARDS,1):
        if not c["capture"]:
            continue
        rows.append([c["key"],str(n)+". "+c["en"][0],c["entry"],"; ".join(c["en"][3]),"MISSING","MISSING"])
        for e in EXTRA:
            if e[1]==n:
                rows.append([e[0],str(n)+". "+e[2]+" / "+e[3],"Parent workflow entry","Reference + exact action + required check + result; adapt parent numbered legend to this state","MISSING","MISSING"])
    parts=["# Microcom — Screenshot capture checklist / Liste des captures",
        "**STATUS: awaiting owner-supplied rehearsal URL and approved access. No capture authorized yet.**",
        f"Verified source: {COMMIT}, C:/MicrocomRehearsal/app. The owner confirms rehearsal is not running. Database name was supplied for context only; no database was accessed. Do not start the application, create accounts, query databases or capture screens before the approved access is supplied. No production data.",
        "## 1. Access and data prerequisites",
        "Owner must supply: rehearsal URL; approved existing authentication method and role accounts (no passwords in docs); approved synthetic fixtures; permission for the sample lifecycle transitions to be captured; confirmation of actual build, schema/static files and private-PDF availability. Do not change flags or server configuration for screenshots. Financial notes need the deployed UI gate and permissions confirmed.",
        "Required responsibilities: employee/technician, first named stock reviewer and alternate, later/final approver, stock-only user, invoice creator/editor/finalizer, return-note issuer/document reader, administration-report reader and authorized administrator. Permissions may be combined only where the owner approves. Denial examples need a low-access account.",
        "## 2. Visual and privacy standard",
        "1. Capture separate English and French screens using the actual language selector. Use native PNG, preferably viewport 1440×1000 or larger at 100% browser zoom. Crop irrelevant space but retain title, relevant controls and status/reference context. Split long pages instead of shrinking unreadable text.",
        "2. Use synthetic people, branches, materials, addresses and amounts. Check every header, user menu, file name, document party, browser tab and URL. Prefer sanitized fixtures; otherwise use irreversible flattened redaction in a sanitized copy. Never put confidential originals or filled passwords into the docs tree.",
        "3. Use 24–32 px numbered circles in free margins and 2 px arrows/thin connector lines ending at exact controls; add subtle target outlines. Do not cover labels. Blue #2563EB actions/navigation; green #15803D completion; amber #B7791F warnings/checks; red #B91C1C errors/prohibitions. Use words/numbers as well as color. Each pointer must match its caption; split cross-screen pointers into separate images.",
        "4. Save sanitized base and annotated PNG separately: {id}-base.png / {id}-annotated.png in docs/manual-assets/en/ or fr/. Retain only approved sanitized bases. Do not rename a pending SVG as if it were a capture. Each real image needs language, build, role, state, date, native dimensions, caption, pointer legend, reviewer and privacy review in the capture manifest.",
        "5. Replace pending panels only with accepted real annotated screenshots. Add state-specific images immediately below the relevant instructions. Rebuild PDFs with real images; check every page at normal reading size and obtain owner/stock/Finance sign-off before removing draft warnings.",
        "## 3. Every required screen-state",
        "Each row needs a real EN image and a real FR image. All are missing. Some states need more than one image to preserve readable text. The chapter callout plans are proposed, not coordinates verified against a running screen.",
        md_table(["ID","Chapter / screen-state","Entry","Pointer focus","EN","FR"],rows),
        "## 4. Separate validation/error examples",
        "Capture the following as separate approved synthetic scenarios under 25-errors, each in EN and FR: missing classification; Microcom with no branch; insufficient final stock; excessive cumulative return; stale reconciliation; stale invoice revision/net quantity; unknown price; missing branch address; missing company attestation; missing verified annual series; expired return-note preview; Forbidden access. Under 25b-pdf-error capture invoice/receipt/valued-note PDF failure and the correct retry. Do not create faults in production or alter flags for evidence.",
        "## 5. Boundaries and exact controls",
        "- No credit-note screenshot target: chapter 15 is an availability notice. Models/guards are not an employee credit-note screen.\n- No Deduct Stock button: capture Approved detail and matching OUT evidence.\n- Stock review is opt-in configuration: confirm the existing first named test reviewer.\n- Inspected settings enable MATERIAL_RETURN_NOTE_UI_ENABLED; older docs/fallback say off. Confirm actual rehearsal activation without changing it.\n- Current RCP controls use application language, not the per-receipt selector mentioned in older notes.\n- Capture official BC and BS independently; legacy bulk printing does not issue official references.\n- Current filtered invoice action is Print Filtered Invoices, not checkbox-selected printing.",
        "## 6. Completion ledger",
        f"- {sum(c['capture'] for c in CARDS)} primary pending illustration panels per language.\n- {len(rows)} inventory rows × two languages, plus distinct validation/error variants; this is not a fixed final screenshot quota.\n- Real screenshots captured: 0. Real screenshots annotated: 0. Authenticated workflows manually verified: 0.\n- Markdown and PDF versions are preparation drafts, not the final illustrated manuals. Final acceptance requires real screenshots with numbered arrows/pointers; placeholders do not fulfill that final requirement.",
    ]
    (DOCS/"manual-screenshot-checklist.md").write_text("\n\n".join(parts)+"\n",encoding="utf-8")


def pdf(lang):
    from reportlab.pdfgen import canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    t=TEXT[lang]
    for name,file in [("Guide","arial.ttf"),("GuideBold","arialbd.ttf")]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,"C:/Windows/Fonts/"+file))
    pdfmetrics.registerFontFamily("Guide",normal="Guide",bold="GuideBold",italic="Guide",boldItalic="GuideBold")
    styles=getSampleStyleSheet()
    for name,size,leading,color in [("Text",10.3,16,"#243449"),("Title",29,36,"#17365d"),("Chapter",21,28,"#17365d"),("Label",10,15,"#2563eb"),("Small",8,12,"#64748b")]:
        styles.add(ParagraphStyle(name="M"+name,fontName="GuideBold" if name in {"Title","Chapter","Label"} else "Guide",fontSize=size,leading=leading,textColor=HexColor(color),spaceAfter=9,spaceBefore=5 if name=="Label" else 0,keepWithNext=name in {"Chapter","Label"}))
    def p(text,style="Text"):
        return Paragraph(escape(text),styles["M"+style])
    def box(title,body,bg):
        tab=Table([[p(title,"Label")],[p(body)]],colWidths=[499])
        tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),HexColor(bg)),("LEFTPADDING",(0,0),(-1,-1),13),("RIGHTPADDING",(0,0),(-1,-1),13),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
        return [tab,Spacer(1,10)]
    class Pages(canvas.Canvas):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.states=[]
        def showPage(self):
            self.states.append(dict(self.__dict__));self._startPage()
        def save(self):
            total=len(self.states)
            for state in self.states:
                self.__dict__.update(state)
                self.setStrokeColor(HexColor("#dbe3ed"));self.line(48,49,547,49)
                self.setFont("Guide",8);self.setFillColor(HexColor("#64748b"))
                self.drawString(48,34,"MICROCOM · d3eb766 · "+("REVIEW DRAFT" if lang=="en" else "PROJET À RELIRE"))
                self.drawRightString(547,34,f"{self._pageNumber} / {total}")
                self.setFont("GuideBold",8);self.setFillColor(HexColor("#17365d"));self.drawString(48,812,t["subtitle"])
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)
    logo=ASSETS/"microcom-logo.png"
    story=[Spacer(1,25)]
    if logo.exists():
        story += [Image(str(logo),width=176,height=116),Spacer(1,20)]
    story += [p("MICROCOM","Title"),p(t["subtitle"],"Title"),Spacer(1,18)]
    story+=box(t["draft"],t["status"],"#fff4d9")
    story+=[p("Version 2.0-preparation · 31 October / octobre 2026"),p("Source: "+COMMIT,"Small"),p(t["intro"]),Spacer(1,20),p(t["legend"]),PageBreak(),p(t["toc"],"Chapter")]
    for n,c in enumerate(CARDS,1):
        story.append(p(f"{n:02d}    {c[lang][0]}"))
    story+=[p("A    "+t["appendix"]),PageBreak(),p(t["start"],"Chapter"),p(t["central"]),p(t["flow"])]
    for a,b in t["roles"]:
        story+=[p(a,"Label"),p(b)]
    story.append(PageBreak())
    for n,c in enumerate(CARDS,1):
        title,pre,steps,pointers,warn,result=c[lang]
        story += [p(f"{n:02d}  {title}","Chapter"),p(t["before"],"Label"),p(pre),p(t["steps"],"Label")]
        for i,step in enumerate(steps,1):
            story += [p(f"{i}.  {step}"),Spacer(1,4)]
        story += box(t["result"],result,"#edf7ef")
        story += [PageBreak(),p(f"{n:02d}  {title}","Chapter"),p(t["pointers"],"Label")]
        if c["capture"]:
            story += box(t["missing"]+" · "+c["key"],t["missing_text"],"#fff4d9")
        for target in pointers:
            story.append(p(target))
        for e in EXTRA:
            if e[1]==n:
                story.append(p(e[0]+" — "+e[2 if lang=="en" else 3],"Small"))
        story += box(t["warning"],warn,"#fff4d9")
        story += [p(t["source"],"Label"),p(c["source"],"Small"),p(c["entry"],"Small"),PageBreak()]
    story += [p(t["appendix"],"Chapter"),p(t["references"])]
    for a,b in t["gloss"]:
        story += [p(a,"Label"),p(b)]
    filename="Microcom_User_Manual_EN.pdf" if lang=="en" else "Microcom_Guide_Utilisateur_FR.pdf"
    doc=SimpleDocTemplate(str(DOCS/filename),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=57,bottomMargin=66,title=t["title"]+" — "+t["draft"],author="Microcom — Documentation")
    doc.build(story,canvasmaker=Pages)


def main():
    # Normalize the exact visible label confirmed in the updated template.
    for c in CARDS:
        for lang in ("en","fr"):
            values=list(c[lang])
            values[2]=[s.replace("Print Invoices","Print Filtered Invoices") for s in values[2]]
            c[lang]=values
    for lang in ("en","fr"):
        (ASSETS/lang).mkdir(parents=True,exist_ok=True)
        markdown(lang)
        pdf(lang)
        (ASSETS/lang/"README.md").write_text("# Screenshot assets / Captures\n\nReal captured: 0. Annotated: 0.\n\nSVG files are explicit pending panels, not screenshots or UI mockups. Do not distribute these as final illustrated manuals. Replace only after owner-approved real capture. See ../../manual-screenshot-checklist.md.\n",encoding="utf-8")
    checklist()
    report_source=ASSETS/"validation-report.md"
    if report_source.exists():
        (DOCS/"user-manual-validation.md").write_text(report_source.read_text(encoding="utf-8"),encoding="utf-8")
    manifest={"source_commit":COMMIT,"real_captured":0,"real_annotated":0,"workflow_runtime_verified":0,"owner_access_pending":True,"primary":[{"id":c["key"],"entry":c["entry"],"source":c["source"],"en":c["en"][0],"fr":c["fr"][0],"en_callouts":c["en"][3],"fr_callouts":c["fr"][3],"status":"missing" if c["capture"] else "no_ui"} for c in CARDS],"additional_states":[{"id":e[0],"chapter":e[1],"en":e[2],"fr":e[3],"status":"missing"} for e in EXTRA]}
    (ASSETS/"capture-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Built EN/FR preparation drafts, PDFs and capture inventory. Real screenshots: 0; annotated: 0.")


if __name__=="__main__":
    main()
