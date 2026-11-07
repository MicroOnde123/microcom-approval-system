"""Documentation build only. No Django imports, database access or network."""
from pathlib import Path
import hashlib
import json
from html import escape
from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak, Image, KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents
from pypdf import PdfReader
import reportlab

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
COMMIT = 'd3eb76641c1bd3efe431f26a4536964a0be1aeaf'
DATE = '2026-11-02'
# Paired content is deliberately kept together for coverage review.
CHAPTERS = [
('A', 'Access and navigation', 'Connexion et navigation',
 'Employees use their individual account. Navigation reflects their access; an absent menu is not a reason to share an administrator account.',
 'Chaque employé utilise son compte personnel. Les menus dépendent des droits : leur absence ne justifie jamais le partage d’un compte administrateur.',
 'Active account; approved application address supplied by your administrator.',
 'Compte actif ; adresse de l’application communiquée par l’administrateur.',
 ['Open the approved address and enter your username and password on Login. Never use a password-reset link supplied by another employee.',
  'Use the dashboard to open Create Request, My Requests or Pending Approvals as appropriate. Review the request reference before acting.',
  'Choose English or Français in the language selector. Documents use the current application language; choose it before opening a PDF.',
  'Use Logout when finished. An expired session requires signing in again; unsaved form content may be lost.'],
 ['Ouvrez l’adresse autorisée et saisissez vos identifiants sur la page de connexion. N’utilisez jamais le lien de réinitialisation d’un autre employé.',
  'Depuis le tableau de bord, ouvrez Créer une demande, Mes demandes ou Approbations en attente selon votre tâche. Vérifiez la référence avant toute action.',
  'Choisissez English ou Français dans le sélecteur de langue. Les documents suivent la langue active : sélectionnez-la avant d’ouvrir le PDF.',
  'Déconnectez-vous après utilisation. Une session expirée impose une nouvelle connexion ; les données non enregistrées peuvent être perdues.'],
 'Expected: your own dashboard and permitted menus. If access fails, ask the administrator to check account activation; never publish passwords or session cookies.',
 'Résultat : votre tableau de bord et les menus autorisés. En cas de refus, faites vérifier l’activation du compte ; ne transmettez aucun mot de passe ni cookie de session.',
 ['login','dashboard']),
('B', 'Administrative requests and corrections', 'Demandes administratives et corrections',
 'A request belongs to its Request For Department, which determines routing. Saving a draft does not submit it for approval.',
 'Le champ Demande pour le département détermine le département responsable et le circuit. Enregistrer un brouillon ne le soumet pas aux approbateurs.',
 'Signed-in requester; active request type and applicable workflow.', 'Demandeur connecté ; type actif et circuit applicable.',
 ['Open Create Request. Select Request Type and Request For Department; enter Description / Reason, Date Needed and any type-specific fields.',
  'Add required attachments. Check the selected files and remove inappropriate confidential information before submission.',
  'Save as Draft to continue later, or submit the completed request. Record its generated REQ-ADM reference; other configured types have their own stable namespace.',
  'Open My Requests and filter by reference, department, type, status or dates. Open the detail page to read comments and approval progress.',
  'For a Returned request, read the correction comment, open its edit action, correct the fields and submit again. The request keeps its original reference.',
  'Use cancellation only when available for your open request. An approved request cannot be rewritten through the correction process.'],
 ['Ouvrez Créer une demande. Sélectionnez le type et le département destinataire ; renseignez Description / Motif, la date souhaitée et les champs propres au type.',
  'Joignez les pièces nécessaires. Vérifiez leur contenu et retirez les informations confidentielles sans rapport avec la demande.',
  'Enregistrez un brouillon pour continuer plus tard, ou soumettez la demande complète. Notez sa référence REQ-ADM ; les autres types disposent de leur propre espace de références.',
  'Dans Mes demandes, filtrez par référence, département, type, statut ou dates. Consultez le détail pour lire les commentaires et suivre les approbations.',
  'Pour une demande retournée, lisez le commentaire, ouvrez la modification, corrigez puis soumettez de nouveau. La référence initiale reste inchangée.',
  'Annulez uniquement lorsque cette action est proposée pour votre demande ouverte. Une demande approuvée ne peut pas être réécrite par ce processus.'],
 'Expected: one stable reference, including drafts and resubmissions. A missing workflow blocks submission; contact the administrator rather than changing the department merely to bypass routing.',
 'Résultat : une référence stable, y compris pour le brouillon et les nouvelles soumissions. Si aucun circuit ne correspond, contactez l’administrateur plutôt que de modifier le département pour contourner le contrôle.',
 ['request-create','my-requests','request-draft','request-edit']),
('C', 'Technician material requests', 'Demandes de matériel des techniciens',
 'Request only the materials required. Technicians submit and track requests; authorized stock personnel record subsequent reconciliation and physical returns.',
 'Demandez uniquement le matériel nécessaire. Le technicien soumet et suit la demande ; le personnel du stock habilité enregistre ensuite la régularisation et les retours physiques.',
 'Material request type and available active materials.', 'Type de demande de matériel et articles actifs disponibles.',
 ['Select the material request type on Create Request. Confirm the owning department before entering material rows.',
  'Add each material, quantity and useful item note. Check units carefully; do not treat a cable length as a number of pieces.',
  'Review all rows and submit, or save a draft. A draft does not reserve or deduct stock.',
  'Keep the REQ-MAT reference and follow the approval chain in request details. Final stock availability is checked again during approval.'],
 ['Sélectionnez le type de demande de matériel. Confirmez le département responsable avant de saisir les lignes.',
  'Ajoutez le matériel, la quantité et une note utile. Vérifiez les unités : une longueur de câble ne correspond pas à un nombre de pièces.',
  'Vérifiez toutes les lignes puis soumettez, ou enregistrez un brouillon. Un brouillon ne réserve ni ne déduit le stock.',
  'Conservez la référence REQ-MAT et suivez les étapes dans le détail. La disponibilité est contrôlée de nouveau à l’approbation finale.'],
 'Expected: complete material rows and an approval chain after submission. Correct invalid quantities; never create a second request merely because a response was slow.',
 'Résultat : des lignes complètes et un circuit après soumission. Corrigez les quantités invalides ; ne créez pas une deuxième demande uniquement parce que la réponse tarde.',
 ['material-request-create','material-request-lines','pending-approvals']),
('D', 'Stock classification: deployment discrepancy', 'Classification du stock : écart à résoudre',
 'RELEASE CHECK: the supplied target workflow allows stock review at any configured step. This checkout still requires it to be the FIRST step. Do not configure the proposed Step 2 example against this version.',
 'CONTRÔLE AVANT DIFFUSION : le besoin annoncé autorise la revue du stock à toute étape. Cette version exige encore la PREMIÈRE étape. N’y configurez pas l’exemple avec revue à l’étape 2.',
 'Assigned primary or alternate stock reviewer at the current approval step. A stock-report flag alone does not assign an approval.',
 'Responsable principal ou suppléant affecté à l’étape courante de revue du stock. Le droit aux rapports ne crée pas cette affectation.',
 ['Open Pending Approvals and the assigned material request. Confirm quantities, purpose and supporting evidence.',
  'For CLIENT work, choose CLIENT. No Microcom succursale is required or retained.',
  'For MICROCOM work, choose MICROCOM and select a valid succursale. Classification and succursale are mandatory for this approval.',
  'Approve only after review. Missing classification blocks approval; returning for correction or rejecting must remain possible under the existing rules.',
  'The requested Fiber example is Initial approval → Stock Classification Review → Direction → Finances. It is a target example, NOT a verified configuration supported by this checkout. Ask the application owner to reconcile versions first.'],
 ['Dans Approbations en attente, ouvrez la demande affectée. Vérifiez les quantités, le motif et les justificatifs.',
  'Pour une intervention CLIENT, choisissez CLIENT. Aucune succursale Microcom n’est exigée ni conservée.',
  'Pour un usage MICROCOM, choisissez MICROCOM et une succursale valide. Ces informations sont obligatoires pour cette approbation.',
  'Approuvez après vérification. Une classification manquante bloque l’approbation ; le retour pour correction et le rejet suivent leurs règles habituelles.',
  'L’exemple Fiber demandé est : approbation initiale → revue du stock → Direction → Finances. Il s’agit d’un circuit cible, NON d’une configuration vérifiée pour cette version. Faites d’abord clarifier la version par le responsable applicatif.'],
 'Expected: classification evidence is retained. Never reorder a live workflow or grant administrator access to work around a routing error.',
 'Résultat : la preuve de classification est conservée. Ne réordonnez pas un circuit en service et n’accordez pas de droits administrateur pour contourner une erreur.',
 ['stock-classification-client','stock-classification-microcom','admin-workflow']),
('E', 'Central inventory and material prices', 'Stock central et prix du matériel',
 'One central warehouse supplies technicians. Succursales identify administrative destinations and billing entities, not independent warehouses.',
 'Un stock central unique approvisionne les techniciens. Les succursales sont des destinations administratives et de facturation, pas des entrepôts indépendants.',
 'Stock-report access for reports; separate staff and model permissions for Django material administration.',
 'Droits aux rapports de stock ; droits administrateur et permissions de modèle distincts pour gérer le catalogue.',
 ['Open Material Reports to review issued, physically returned and remaining returnable quantities, alongside ledger status.',
  'Authorized administrators open Inventory → Materials in Django Admin. Select an existing item to review code, category, unit, stock and minimum level.',
  'When adding a priced material, verify the proposed USD selection or choose CDF/EUR. Editing retains the saved currency; there is no automatic currency conversion.',
  'Enter an unknown price as blank, not zero. Zero means an explicit legitimate price. Save only approved catalog changes.',
  'Do not edit stock balances to simulate an issue or a return. Use the approved operational process and investigate inconsistent movement history.'],
 ['Ouvrez Rapports matériels pour examiner les quantités sorties, retournées et encore retournables, ainsi que la cohérence du registre.',
  'Dans Django Admin, les administrateurs habilités ouvrent Inventaire → Matériels. Consultez le code, la catégorie, l’unité, le stock et le seuil minimum.',
  'À la création d’un matériel tarifé, vérifiez USD ou choisissez CDF/EUR. La modification conserve la devise enregistrée ; aucune conversion automatique n’est effectuée.',
  'Laissez un prix inconnu vide : zéro constitue un prix explicite valide. Enregistrez uniquement les modifications autorisées du catalogue.',
  'Ne modifiez pas les soldes pour simuler une sortie ou un retour. Utilisez le processus prévu et faites examiner tout historique incohérent.'],
 'Expected: prices and currencies are deliberate. Catalog changes do not rewrite finalized invoice snapshots. A historical discrepancy requires stock administrator review, not deletion of movements.',
 'Résultat : les prix et devises sont choisis explicitement. Le catalogue ne réécrit pas les factures finalisées. Une incohérence historique nécessite une vérification, jamais la suppression de mouvements.',
 ['material-reports','admin-materials','admin-material']),
('F', 'Approvals, corrections and stock deduction', 'Approbations, corrections et déduction du stock',
 'Only the current assigned approver or permitted alternate acts. Request status and your own approval action are different pieces of information.',
 'Seul l’approbateur affecté à l’étape courante ou son suppléant autorisé agit. Le statut global et votre propre décision sont deux informations distinctes.',
 'A submitted request assigned to the signed-in approver.', 'Demande soumise et affectée à l’approbateur connecté.',
 ['Open Pending Approvals, then the request. Read attachments, quantities and previous comments.',
  'Choose Approve, Return for correction or Reject as appropriate and provide the required comment. Do not approve incomplete evidence.',
  'An approval advances to the next configured step. At final material approval, the application validates and deducts stock exactly once.',
  'Use Approval History to review your actions and the overall request status. The requester corrects a Returned request through its edit/resubmit flow.',
  'If final approval fails, report the displayed validation message and request reference. Do not manually deduct stock or repeatedly submit different operations.'],
 ['Ouvrez Approbations en attente puis la demande. Lisez les pièces jointes, les quantités et les commentaires précédents.',
  'Choisissez Approuver, retourner pour correction ou rejeter selon le cas, avec le commentaire requis. N’approuvez pas des justificatifs incomplets.',
  'L’approbation avance à l’étape suivante. À l’approbation finale du matériel, l’application contrôle et déduit le stock une seule fois.',
  'Consultez Historique des approbations pour vos décisions et le statut global. Le demandeur corrige une demande retournée puis la soumet de nouveau.',
  'En cas d’échec final, transmettez le message et la référence. Ne déduisez pas manuellement le stock et ne multipliez pas les opérations différentes.'],
 'Expected: the approved request retains its approval history and exactly one issuance per material. Printing, reconciliation and reporting must not repeat this deduction.',
 'Résultat : la demande conserve son historique et une seule sortie par matériel. L’impression, la régularisation et les rapports ne répètent pas cette déduction.',
 ['pending-approvals','approval-history','approved-request']),
('G', 'Bon de commande and bon de sortie', 'Bon de commande et bon de sortie',
 'BC is an internal material order, not supplier purchasing. BS documents the authorized issue. Both use the existing issue-note layout, with different titles and references.',
 'Le BC est une commande interne de matériel, pas un achat fournisseur. Le BS documente la sortie autorisée. Les deux utilisent le même modèle, avec des titres et références distincts.',
 'Approved material request, confirmed stock deduction and material rows; requester, assigned approver, stock user or superuser access as permitted.',
 'Demande de matériel approuvée, stock déduit et lignes présentes ; accès selon les droits du demandeur, de l’approbateur, du stock ou du superutilisateur.',
 ['Open the approved request and choose BC or BS in its document actions.',
  'For first issuance, verify the request reference on the confirmation page. Cancel leaves it unissued; opening this page alone assigns no number.',
  'Choose Confirm & Print only when authorized. This POST assigns a permanent BC/0001/YYYY or BS/0001/YYYY reference using independent annual counters.',
  'Use the print view controls and browser print dialog; Save as PDF is a browser option where supported.',
  'Reopen the same document for a reprint. Its reference remains unchanged and no stock is deducted again. Material-report bulk printing does not allocate official references.'],
 ['Ouvrez la demande approuvée et choisissez BC ou BS parmi les actions documentaires.',
  'À la première émission, vérifiez la référence sur la page de confirmation. Annuler laisse le document non émis ; ouvrir cette page seul n’attribue aucun numéro.',
  'Choisissez Confirmer et imprimer uniquement si vous êtes habilité. Cette validation attribue BC/0001/AAAA ou BS/0001/AAAA, avec des compteurs annuels indépendants.',
  'Utilisez les commandes d’impression et la boîte de dialogue du navigateur ; l’enregistrement PDF dépend de ses options.',
  'Rouvrez le même document pour une réimpression. Sa référence reste stable, sans nouvelle sortie de stock. L’impression groupée des rapports n’alloue aucune référence officielle.'],
 'Expected: at most one BC and one BS per request. Their annual rollover uses Africa/Kinshasa. Do not confuse the request reference with either document reference.',
 'Résultat : au maximum un BC et un BS par demande. Le changement d’année suit Africa/Kinshasa. Ne confondez pas la référence de demande avec celles des documents.',
 ['bc-confirm','bs-confirm']),
('H', 'Internal invoices', 'Factures internes',
 'A facture is on-demand bookkeeping for one eligible MICROCOM request, not a sale or a stock movement. CLIENT work does not require an internal Microcom invoice.',
 'La facture est un document comptable interne émis à la demande pour une demande MICROCOM admissible. Ce n’est ni une vente ni un mouvement de stock. Une intervention CLIENT n’exige pas de facture interne.',
 'Approved MICROCOM request with actual OUT evidence, confirmed succursale and physical address, compatible material prices, verified company settings, and a verified annual INVOICE series for finalization. Explicit invoice action permissions and stock-review scope are required.',
 'Demande MICROCOM approuvée avec preuve de sortie, succursale et adresse, prix compatibles, informations de société attestées et série annuelle INVOICE vérifiée pour finaliser. Permissions explicites et périmètre de revue du stock sont requis.',
 ['Open Invoices and select an eligible candidate request, or use the permitted invoice action associated with the request. Select the currency and create its draft.',
  'Review material descriptions, net billable quantities, currency and unit prices. Catalog prices are copied into the draft when currencies match; unknown or mismatched prices remain incomplete.',
  'An authorized editor may correct draft prices or explicitly refresh quantities. Review the history; a refresh may record that no quantity or price changed.',
  'A draft has a Draft #ID label and a provisional sum only when all lines are priced. It has no official invoice number or finalized total.',
  'Choose Finalize invoice, review the configured series and confirm only after verifying all evidence. Finalization freezes the branch name/address, company data, material labels and financial values. Do not use this training manual to issue live financial documents.',
  'For a finalized invoice, use Print Invoice. The active-language PDF opens in the private viewer with Print and Download fallback controls. Existing artifacts remain immutable and checksummed.',
  'For combined printing, enter both From and To official issue dates in Invoices, refine search/status, then print filtered invoices. Only authorized finalized matches across all pages are included, subject to the configured maximum.'],
 ['Ouvrez Factures et sélectionnez une demande admissible, ou son action facture autorisée. Choisissez la devise puis créez le brouillon.',
  'Vérifiez les descriptions, quantités nettes, devise et prix unitaires. Les prix du catalogue sont copiés si la devise correspond ; les prix inconnus ou incompatibles restent incomplets.',
  'Un éditeur habilité peut corriger les prix du brouillon ou actualiser explicitement les quantités. Consultez l’historique ; une actualisation peut ne constater aucun changement.',
  'Le brouillon affiche Brouillon n° ID et une somme provisoire seulement si toutes les lignes sont tarifées. Il n’a ni numéro officiel ni total finalisé.',
  'Choisissez Finaliser la facture, vérifiez la série et les preuves avant de confirmer. La finalisation fige la succursale, son adresse, la société, les descriptions et les valeurs. Ce guide ne constitue pas une autorisation d’émettre des documents réels.',
  'Pour une facture finalisée, choisissez Imprimer la facture. Le PDF dans la langue active s’ouvre dans le lecteur privé avec les commandes d’impression et de téléchargement. Les anciens fichiers restent immuables et contrôlés par empreinte.',
  'Pour une impression groupée, renseignez Du et Au selon les dates officielles d’émission, affinez les filtres puis imprimez les factures filtrées. Toutes les pages sont couvertes, uniquement pour les factures finalisées autorisées et dans la limite configurée.'],
 'Expected: official FAC/0001/YYYY numbering only at finalization. New years require verified financial sequences; never reset a counter. After an error, reload and request administrator review without changing guards or frozen values.',
 'Résultat : le numéro FAC/0001/AAAA est attribué uniquement à la finalisation. Chaque année exige une série financière vérifiée ; ne remettez jamais un compteur à zéro. Après une erreur, rechargez et demandez une vérification sans modifier les protections ni les valeurs figées.',
 ['invoices','invoice-draft','invoice-finalize']),
('I', 'Credit notes: supported boundary', 'Avoirs : limite de la fonctionnalité',
 'The repository contains credit models, allocations, reservation audit and financial guards. No employee credit creation/issuance/PDF route is present in invoicing/urls.py. A complete credit-note workflow must not be inferred from model permissions or Django Admin.',
 'Le dépôt contient les modèles d’avoirs, allocations, audits de réservation et protections financières. Aucune route utilisateur complète de création, émission ou PDF d’avoir n’existe dans invoicing/urls.py. Les permissions ou Django Admin ne constituent pas ce processus.',
 'Administrator or finance review of the supported business process; no documented self-service credit action.',
 'Examen du processus pris en charge avec l’administrateur ou la finance ; aucune action autonome documentée.',
 ['If a monetary credit or refund is needed, stop and contact the responsible finance administrator.',
  'Do not use a physical return receipt or financial Material Return Note as a credit, refund or payment adjustment.',
  'Do not create or edit protected credit records manually to bypass the missing issuance workflow. Active credit allocations exclude financial return-note evidence for the entire invoice, in both directions.'],
 ['Si un avoir monétaire ou un remboursement est nécessaire, contactez le responsable financier.',
  'N’utilisez ni le reçu de retour physique ni le bon de retour de valorisation comme avoir, remboursement ou ajustement de paiement.',
  'Ne créez ni ne modifiez manuellement des enregistrements protégés pour contourner le processus absent. Les allocations actives d’avoir excluent la preuve financière de retour pour toute la facture, et réciproquement.'],
 'Expected: escalation rather than an invented menu or unsafe financial workaround. Credit creation screenshots are not applicable to this checkout.',
 'Résultat : une prise en charge par le responsable, sans menu inventé ni contournement financier. Les captures de création d’avoir ne sont pas applicables à cette version.', []),
('J', 'Material Management, physical returns and receipts', 'Gestion du matériel, retours physiques et bons',
 'Use the existing three-tab Material Management workspace. Reconciliation records outcomes; a physical return restores central stock; RCP acknowledges actual returns; invoice-linked BR values eligible returns without changing stock or the original invoice.',
 'Utilisez Gestion du matériel et ses trois onglets. La régularisation décrit les usages ; le retour physique réintègre le stock central ; le RCP constate les retours ; le BR lié à une facture valorise les retours admissibles sans modifier le stock ni la facture initiale.',
 'Approved material request with confirmed deduction; authorized stock personnel. Financial BR additionally needs its enabled gate, explicit permissions, scope, finalized invoice and eligible post-finalization returns.',
 'Demande de matériel approuvée et stock déduit ; personnel du stock habilité. Le BR financier exige en plus l’activation, les permissions explicites, le périmètre autorisé, une facture finalisée et des retours postérieurs admissibles.',
 ['Open Material Management from request details or Material Reports. Overview shows issued, CLIENT-installed, MICROCOM-used, physically returned and retained/testing quantities.',
  'In Reconcile, record technician-reported outcomes for every material. Use split quantities where needed, select the responsible technician and give the reason. Returned quantities come from actual movements and are not invented in this editor.',
  'Review and save a revision. The original classification, approvals, OUT movements and BC/BS stay unchanged. Open revision history to inspect previous reports. A stale edit requires reloading and reviewing the latest revision.',
  'Receive and verify the physical materials before opening Returns & Receipts. Enter an allowed quantity and reason; review and confirm the return. No separate return approval lifecycle is introduced. The protected service restores stock exactly once.',
  'Do not exceed the remaining quantity. Fully returned materials have no active return action. Historical stock discrepancy — review required means stop and ask the stock administrator; never delete movements or edit balances.',
  'Select recorded, undocumented RETURN movements and confirm Generate Bon de retour to issue the NONFINANCIAL RCP receipt. It works for CLIENT, MICROCOM and requests without invoices. Reprints keep the RCP reference and do not restore stock again.',
  'Use View PDF or Print on an issued receipt. The current application language is used. A PDF failure does not undo the recorded physical return or receipt; retry the PDF only.',
  'For financial BR, use the finalized invoice return-note action only when enabled and authorized. Select complete eligible RETURN movements strictly after invoice finalization; preview their frozen valuation, enter a reason and confirm once.',
  'An uncertain BR outcome must be retried using the SAME retained confirmation handle and issuance token. Do not start a new preview as a substitute. If the session is lost, inspect issued-note history and contact support before attempting another operation.',
  'Financial BR leaves the original facture unchanged, with cumulative caps, rounding and credit exclusivity enforced. The signed preview lasts two hours but the application session still times out after 15 minutes.'],
 ['Depuis le détail ou Rapports matériels, ouvrez Gestion du matériel. Vue d’ensemble affiche les quantités sorties, installées CLIENT, utilisées MICROCOM, retournées et conservées pour essais.',
  'Dans Régulariser, saisissez les résultats rapportés par le technicien pour chaque matériel. Répartissez les quantités si nécessaire, identifiez le technicien et indiquez le motif. Les quantités retournées proviennent des mouvements réels.',
  'Vérifiez puis enregistrez une révision. Classification initiale, approbations, sorties et BC/BS restent inchangés. Consultez l’historique repliable. Une modification périmée impose de recharger et revoir la dernière révision.',
  'Réceptionnez et contrôlez physiquement le matériel avant Retours et bons de retour. Saisissez la quantité permise et le motif puis confirmez. Aucun nouveau circuit d’approbation n’est ajouté. Le service protégé restaure le stock une seule fois.',
  'Ne dépassez pas le solde retournable. Un article entièrement retourné n’a plus d’action active. Incohérence historique du stock — vérification nécessaire impose l’arrêt et la vérification par le responsable, jamais la suppression de mouvements.',
  'Sélectionnez les mouvements RETURN encore non documentés et confirmez Générer le bon de retour pour émettre le reçu RCP NON FINANCIER. Il couvre CLIENT, MICROCOM et les demandes sans facture. La réimpression conserve sa référence sans nouvelle entrée en stock.',
  'Utilisez Voir le PDF ou Imprimer sur le reçu. La langue active est utilisée. Un échec PDF n’annule ni le retour ni le reçu : réessayez uniquement le PDF.',
  'Pour le BR financier, utilisez l’action de la facture finalisée seulement si elle est activée et autorisée. Sélectionnez des mouvements RETURN complets admissibles, strictement postérieurs à la finalisation ; vérifiez la valorisation figée et le motif avant confirmation.',
  'Si le résultat du BR est incertain, réessayez avec la MÊME confirmation conservée et le même jeton d’émission. Un nouvel aperçu ne remplace pas cet essai. Si la session est perdue, vérifiez l’historique et contactez le support.',
  'Le BR financier préserve la facture, avec plafonds cumulés, arrondis et exclusivité des avoirs. L’aperçu signé dure deux heures, mais la session conserve son expiration de 15 minutes.'],
 'Expected: auditable outcome revisions and stock restoration only for accepted physical returns. The isolated rehearsal keeps financial BR disabled; issuance, financial PDFs and recovery screenshots remain pending.',
 'Résultat : des révisions traçables et une réintégration uniquement pour les retours physiques validés. Le BR financier reste désactivé dans cette répétition ; ses captures d’émission, PDF et reprise restent à réaliser.',
 ['material-overview','material-reconcile-editor','material-return-editor']),
('K', 'Administrator reference', 'Référence administrateur',
 'Administrative access is separate from operational stock and financial permissions. Never grant staff status merely to permit a scoped stock action.',
 'L’accès administrateur est distinct des permissions opérationnelles et financières. N’accordez pas le statut administrateur uniquement pour permettre une action du stock.',
 'Authorized staff account and the relevant model/action permissions.', 'Compte administrateur autorisé et permissions de modèle/action appropriées.',
 ['In Django Admin, maintain active users, departments and roles. Use individual identities and review stock-report and administration-report flags separately.',
  'Maintain request types and applicable workflows by owning department and amount range. Set primary and alternate approvers and unique step order. Test routing with approved rehearsal data before operational use.',
  'STOP: this source currently permits one designated stock-review step and requires it first. The desired any-step configuration must be reconciled with the application owner before publishing that procedure.',
  'Maintain succursale name, code, active status and physical address. New succursales require an address; legacy blank records can remain, but new Microcom invoice finalization requires a valid address.',
  'Review Company and document settings, save approved details and use Attest current company information. Changing those details invalidates the current content attestation for future issuance.',
  'Review Document sequences for type, year, series, format, next counter and verification evidence. Use the existing verification action; never reset a used counter. Financial invoice preparation does not silently attest a new year.',
  'Inspect request, reconciliation, receipt and invoice histories. Report protected-record errors instead of modifying immutable records. Requests cannot be added through Django Admin; create them through the application.'],
 ['Dans Django Admin, gérez les utilisateurs actifs, départements et rôles. Utilisez des identités individuelles et examinez séparément les accès aux rapports du stock et administratifs.',
  'Gérez les types et circuits selon le département responsable et les montants. Définissez titulaires, suppléants et ordre unique. Vérifiez le routage avec des données de répétition avant usage.',
  'ARRÊT : ce code permet une seule étape de revue du stock et l’exige en premier. Faites clarifier l’écart avec la configuration attendue à toute étape avant de diffuser cette procédure.',
  'Gérez le nom, code, activation et adresse des succursales. Une nouvelle succursale exige une adresse ; les anciens enregistrements vides restent compatibles, mais une nouvelle facture MICROCOM exige une adresse valide.',
  'Vérifiez les paramètres société/documents puis utilisez l’action d’attestation des informations courantes. Leur modification invalide l’attestation de contenu pour les futures émissions.',
  'Vérifiez les séries : type, année, série, format, prochain compteur et justificatifs. Utilisez l’action de vérification prévue ; ne réinitialisez jamais un compteur utilisé. Préparer une année financière ne l’atteste pas automatiquement.',
  'Consultez les historiques des demandes, régularisations, reçus et factures. Signalez les erreurs de protection sans modifier les pièces immuables. Créez les demandes dans l’application, jamais par l’ajout Django Admin.'],
 'Expected: permissions and attestations are explicit. Do not expose private PDF paths, reset links, logs containing credentials or signed confirmations in support tickets or training screenshots.',
 'Résultat : permissions et attestations explicites. N’exposez ni chemins privés PDF, liens de réinitialisation, secrets de journaux ni confirmations signées dans les tickets ou captures.',
 ['admin','admin-users','admin-workflows','admin-workflow','admin-succursale','admin-company','admin-company-timezone','admin-sequences']),
('L', 'Reports, exports and troubleshooting', 'Rapports, exports et dépannage',
 'Reports respect your permitted dataset. Filters narrow that dataset; they do not grant access to other departments or financial values.',
 'Les rapports respectent votre périmètre autorisé. Les filtres réduisent ce périmètre ; ils n’accordent ni accès supplémentaire ni visibilité financière.',
 'Material Reports flag or superuser; separate financial invoice permission/scope for bookkeeping values. Administration Report uses its own flag.',
 'Droit aux rapports matériels ou superutilisateur ; permissions/périmètre financiers distincts pour les valeurs. Le rapport administratif possède son propre droit.',
 ['Set search, department and dates as offered. Use Reset to clear filters. Invalid dates display errors and no results rather than an unfiltered report.',
  'Review issued, returned and remaining quantities and the movement status. Open request details or history for evidence; an inconsistency disables further return actions.',
  'Export Excel using the active filters. Authorized financial users receive eight worksheets; stock-only users receive seven without Bookkeeping. The four existing charts are retained.',
  'Review Material Report, Dashboard, Graphs, Stock Movements, Succursale Summary, Material Group Summary and Monthly Statistics. Bookkeeping uses finalized snapshots only and is added only where authorized.',
  'Keep currencies and units separate. Blank historical prices mean unknown, never zero. CLIENT activity remains in stock statistics but internal facture coverage is not applicable; MICROCOM invoices are on demand.',
  'An export exceeding the configured row limit (default 10,000) must be narrowed using filters. Exports never issue BC/BS, invoices or stock movements.',
  'For support, provide the request/document reference, timestamp, action, language and sanitized displayed error. Never send passwords, session cookies, confirmation tokens or complete confidential documents.'],
 ['Renseignez la recherche, le département et les dates proposés. Réinitialiser efface les filtres. Une date invalide produit un message et aucun résultat, pas un rapport non filtré.',
  'Vérifiez sorties, retours, soldes et cohérence. Consultez le détail ou l’historique comme preuve ; une incohérence désactive les nouveaux retours.',
  'Exportez Excel avec les filtres actifs. Les utilisateurs financièrement habilités obtiennent huit feuilles ; les utilisateurs du stock seuls, sept sans Comptabilité. Les quatre graphiques sont conservés.',
  'Consultez Rapport matériel, Tableau de bord, Graphiques, Mouvements de stock, Synthèse par succursale, Synthèse par groupe et Statistiques mensuelles. Comptabilité, si autorisée, utilise uniquement les valeurs finalisées figées.',
  'Séparez devises et unités. Un prix historique vide est inconnu, jamais zéro. L’activité CLIENT reste dans les statistiques de stock mais la couverture de facture interne ne s’y applique pas ; les factures MICROCOM sont émises à la demande.',
  'Au-delà de la limite configurée, de 10 000 lignes par défaut, réduisez l’export par les filtres. Exporter ne crée ni BC/BS, ni facture, ni mouvement.',
  'Pour le support, fournissez référence, heure, action, langue et message sans données sensibles. Ne transmettez ni mots de passe, cookies, jetons de confirmation ni documents confidentiels complets.'],
 'Expected: localized, read-only reports. Missing access requires an authorized permission review, not another employee’s exported workbook.',
 'Résultat : des rapports localisés en lecture seule. Un accès manquant exige une revue des droits, pas l’utilisation du fichier confidentiel d’un autre employé.',
 ['material-reports','material-filter-error','invoices'])
]

def annotate(manifest):
    """Draw in an external gutter; raw UI pixels are never rewritten."""
    fontpath = Path('C:/Windows/Fonts/arialbd.ttf')
    font = ImageFont.truetype(str(fontpath), 20)
    for shot in manifest['screens']:
        root = DOCS / 'manual-assets' / shot['language']
        raw = root / 'raw' / (shot['name'] + '.png')
        image = PILImage.open(raw).convert('RGB')
        left = top = 0
        # Training close-ups improve printed readability; preserve the uncropped original.
        if shot['name'] in {'stock-classification','stock-classification-client','stock-classification-microcom','admin-material','admin-succursale','material-request-lines'}:
            controls=[c for c in shot['controls'] if not c.get('missing') and c.get('visible')]
            left=max(0,int(min(c['x'] for c in controls))-210)
            top=max(0,int(min(c['y'] for c in controls))-(65 if shot['name']=='material-request-lines' else 25))
            right=min(image.width,int(max(c['x']+c['width'] for c in controls))+(10 if shot['name']=='material-request-lines' else 35))
            bottom=min(image.height,int(max(c['y']+c['height'] for c in controls))+25)
            shot['annotation_crop']=[left,top,right,bottom]
            image=image.crop((left,top,right,bottom))
        out = PILImage.new('RGB', (image.width + 110, image.height), '#f4f6f8')
        out.paste(image, (110, 0))
        draw = ImageDraw.Draw(out)
        for mark in shot.get('marks',[]):
            x,y=110+mark['x']-left,mark['y']-top
            if x>=110 and y>=0 and y+mark['height']<=image.height:
                draw.rectangle((x-2,y-2,x+mark['width']+2,y+mark['height']+2),outline={'success':'#15803d','warning':'#b45309','error':'#b91c1c'}[mark['kind']],width=2)
        if shot['name']=='stock-classification-microcom':
            c=shot['controls'][1];x,y=110+c['x']-left,c['y']-top
            draw.rectangle((x-2,y-2,x+c['width']+2,y+c['height']+2),outline='#b45309',width=2)
        callouts = []
        for index, control in enumerate(shot['controls'], 1):
            if control.get('missing') or not control.get('visible'):
                continue
            target = (110 + max(0, control['x']-left-4), max(25, min(image.height-25, control['y']-top-3)))
            y = target[1]
            if callouts and abs(y-callouts[-1]['y'])<55:
                y = min(image.height-30, callouts[-1]['y']+60)
            draw.line([(63,y),(86,y),(86,target[1]),target], fill='#2563eb', width=2)
            draw.ellipse((20,y-20,60,y+20), fill='#123d6b', outline='white', width=2)
            draw.text((40,y),str(index),anchor='mm',font=font,fill='white')
            draw.ellipse((target[0]-3,target[1]-3,target[0]+3,target[1]+3), fill='#2563eb')
            callouts.append({'number':index, 'selector':control['selector'], 'y':y})
        # Color marks only actual existing UI status elements, never fabricated labels.
        folder=root/'annotated';folder.mkdir(parents=True,exist_ok=True)
        out.save(folder/(shot['name']+'-annotated.png'))
        shot['callouts']=callouts
        shot['raw_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
    (DOCS/'manual-assets/capture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

LABELS = {
 '#id_username':('Username field','Champ du nom d’utilisateur'),
 '#id_date_from':('Correct the invalid start date','Corrigez la date de début invalide'), '.errorlist':('Validation error: no unfiltered results are shown','Erreur de validation : aucun résultat non filtré n’est affiché'),
 '#material-date-from':('Correct the invalid start date','Corrigez la date de début invalide'),
 '#id_material_items-0-material':('Material selection','Choix du matériel'), '#id_material_items-0-quantity':('Requested quantity in the material unit','Quantité demandée dans l’unité du matériel'),
 '.material-search-field':('Search/select material by name, code or category','Recherchez et sélectionnez le matériel par nom, code ou catégorie'),
 '#id_invoice_number_format':('Invoice numbering preference; sequence verification is separate','Préférence de format ; vérification de série distincte'),
 'button[type=submit]':('Submission control: read the page before confirming','Commande de validation : vérifiez la page avant de confirmer'),
 '.navbar':('Application navigation and language controls','Navigation et choix de langue'),
 '.app-container':('Dashboard work area','Zone de travail du tableau de bord'),
 '#id_request_type':('Request type','Type de demande'), '#id_request_for_department':('Owning department','Département responsable'),
 'form[method=get]':('Search and filter controls','Commandes de recherche et filtres'),'table':('Record list or material lines','Liste des enregistrements ou lignes de matériel'),
 '.page-header':('Page heading and permitted actions','Titre et actions autorisées'), 'a[href$="/edit/"]':('Edit the open request','Modifier la demande ouverte'),
 '#id_classification':('CLIENT / MICROCOM classification','Classification CLIENT / MICROCOM'), '#id_succursale':('Succursale selection for MICROCOM','Choix de succursale pour MICROCOM'),
 '.context-toolbar':('Related operational and document actions','Actions opérationnelles et documentaires'),
 '.document-confirm__reference':('Original material request reference','Référence de la demande initiale'),
 '#tab-overview':('Overview tab','Onglet Vue d’ensemble'),'#tab-reconcile':('Reconcile tab','Onglet Régulariser'), '#tab-returns':('Returns & Receipts tab','Onglet Retours et bons de retour'),
 '#material-status':('Issued quantities and outcomes','Quantités sorties et résultats'), '#reconcile-materials':('Outcome editor; expand the material row','Éditeur des résultats : dépliez la ligne'),
 '#return-materials':('Physical return form; receive materials first','Formulaire de retour physique : réceptionnez d’abord le matériel'),
 '#invoice-filter-form':('Official issue-date and invoice filters','Filtres des factures et dates officielles'),
 'h1':('Document or administration page heading','Titre du document ou de la page'), 'form[method=post]':('Protected confirmation form','Formulaire de confirmation protégé'),
 '#content-main':('Authorized administration modules','Modules d’administration autorisés'), '#user-tools':('Account and session actions','Actions de compte et session'),
 '#changelist-search':('Administration search','Recherche administrative'), '#result_list':('Authorized records','Enregistrements autorisés'), '#changelist':('Administrative list and actions','Liste administrative et actions'),
 '#id_name':('Stored name','Nom enregistré'),'.inline-group':('Configured approval steps','Étapes d’approbation configurées'),
 '#id_unit_price':('Unit price; blank means unknown','Prix unitaire : vide signifie inconnu'), '#id_currency':('Stored price currency','Devise du prix enregistré'),
 '#id_physical_address':('Succursale physical address','Adresse physique de la succursale'), '#id_company_name':('Company settings, not the invoice PDF heading','Paramètres société, distincts du titre PDF'),
 '#id_business_timezone':('Africa/Kinshasa business timezone','Fuseau métier Africa/Kinshasa')
}

FIGURES = {
 'login':('Sign in','Connexion'), 'dashboard':('Dashboard and navigation','Tableau de bord et navigation'),
 'request-create':('Create a request','Créer une demande'), 'material-request-create':('Material request entry','Saisie d’une demande de matériel'),
 'material-request-lines':('Material and quantity rows','Lignes de matériel et quantités'),
 'admin-company-timezone':('Business timezone and numbering preference','Fuseau métier et préférence de numérotation'),
 'my-requests':('My Requests','Mes demandes'), 'request-draft':('Request draft','Brouillon de demande'), 'request-edit':('Edit a request','Modifier une demande'),
 'pending-approvals':('Pending Approvals','Approbations en attente'), 'stock-classification':('Stock classification','Classification du stock'),
 'stock-classification-client':('CLIENT classification — control detail','Classification CLIENT — détail des champs'),
 'stock-classification-microcom':('MICROCOM classification — control detail','Classification MICROCOM — détail des champs'),
 'approval-history':('Approval History','Historique des approbations'), 'approved-request':('Approved material request','Demande de matériel approuvée'),
 'bc-confirm':('BC first-issuance confirmation','Confirmation de première émission du BC'), 'bs-confirm':('BS first-issuance confirmation','Confirmation de première émission du BS'),
 'material-reports':('Material Reports','Rapports matériels'), 'material-overview':('Material Management — Overview','Gestion du matériel — Vue d’ensemble'),
 'material-filter-error':('Invalid date filter — safe error state','Filtre de date invalide — message de validation'),
 'material-reconcile':('Material Management — Reconcile','Gestion du matériel — Régulariser'),
 'material-reconcile-editor':('Material Reconciliation editor','Éditeur de régularisation du matériel'),
 'material-returns':('Returns & Receipts','Retours et bons de retour'), 'material-return-editor':('Physical return editor','Saisie d’un retour physique'),
 'invoices':('Invoice list and filters','Liste et filtres des factures'), 'invoice-draft':('Invoice draft','Brouillon de facture'),
 'invoice-finalize':('Invoice finalization — configuration check','Finalisation de facture — contrôle de configuration'),
 'admin':('Administration modules','Modules d’administration'), 'admin-users':('User management','Gestion des utilisateurs'),
 'admin-workflows':('Approval workflow list','Liste des circuits d’approbation'), 'admin-workflow':('Approval workflow configuration','Configuration du circuit d’approbation'),
 'admin-materials':('Material catalog','Catalogue du matériel'), 'admin-material':('Unit price and currency — control detail','Prix unitaire et devise — détail des champs'),
 'admin-succursale':('Succursale name and address — control detail','Nom et adresse de succursale — détail des champs'),
 'admin-company':('Company and document settings','Paramètres de l’entreprise et des documents'), 'admin-sequences':('Verified financial sequences','Séries financières vérifiées')
}

def build():
    manifest=json.loads((DOCS/'manual-assets/capture-manifest.json').read_text(encoding='utf-8'))
    annotate(manifest)
    fontroot=Path(reportlab.__file__).parent/'fonts'
    pdfmetrics.registerFont(TTFont('Guide',str(fontroot/'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('Guide-Bold',str(fontroot/'VeraBd.ttf')))
    pdfmetrics.registerFontFamily('Guide',normal='Guide',bold='Guide-Bold',italic='Guide',boldItalic='Guide-Bold')
    styles=getSampleStyleSheet()
    for name in ('Normal','BodyText','Title','Heading1','Heading2'):
        styles[name].fontName='Guide-Bold' if name in ('Title','Heading1','Heading2') else 'Guide'
    styles['BodyText'].fontSize=11;styles['BodyText'].leading=16;styles['BodyText'].spaceAfter=9
    styles['Heading1'].textColor=colors.HexColor('#123d6b');styles['Heading1'].fontSize=20
    styles['Heading2'].fontSize=14;styles['Title'].fontSize=30;styles['Title'].leading=38
    styles.add(ParagraphStyle(name='CaptionGuide',fontName='Guide',fontSize=10,leading=14,spaceAfter=7))
    styles.add(ParagraphStyle(name='NoticeGuide',fontName='Guide-Bold',fontSize=11,leading=16,textColor=colors.HexColor('#92400e'),spaceAfter=12))
    width,height=landscape(A4)
    results=[]
    for lang in ('en','fr'):
        fr=lang=='fr';idx=1 if fr else 0
        title='Guide utilisateur Microcom' if fr else 'Microcom User Manual'
        notice=('VERSION DE REVUE — captures authentiques partielles ; écart de circuit et vérification du déploiement non résolus. Ne pas diffuser comme guide final.' if fr else
                'REVIEW EDITION — authentic screenshots are partial; workflow discrepancy and deployment verification remain unresolved. Not approved as a final training guide.')
        out=DOCS/('Microcom_Guide_Utilisateur_FR.pdf' if fr else 'Microcom_User_Manual_EN.pdf')
        md=[f'# {title}', '',f'Version 2.0 — {DATE}', '',notice,'',f'Code: `{COMMIT}`','',
            'Ce guide révise les guides utilisateur et administrateur de docs/manuals/. Les captures viennent de la véritable application Django locale avec données de formation.' if fr else
            'This guide updates the user and administrator guides under docs/manuals/. Screenshots show the actual local Django application using training data.','']
        story=[]
        def paragraph(text,style='BodyText'):
            story.append(Paragraph(escape(text),styles[style]))
        class GuideDoc(BaseDocTemplate):
            def afterFlowable(self,flowable):
                if isinstance(flowable,Paragraph) and flowable.style.name=='Heading1' and flowable.getPlainText() not in {'Contents','Sommaire'}:
                    key='section-'+str(self.seq.nextf('section'))
                    self.canv.bookmarkPage(key)
                    self.notify('TOCEntry',(0,flowable.getPlainText(),self.page,key))
        def chrome(canvas,doc):
            canvas.saveState();canvas.setStrokeColor(colors.HexColor('#123d6b'));canvas.line(36,height-30,width-36,height-30)
            canvas.setFont('Guide',8);canvas.setFillColor(colors.HexColor('#475569'))
            canvas.drawString(36,height-22,title+' · 2.0 · '+DATE)
            canvas.drawString(36,20,'Formation / Training — données fictives / synthetic records')
            canvas.drawRightString(width-36,20,str(doc.page));canvas.restoreState()
        doc=GuideDoc(str(out),pagesize=(width,height),leftMargin=42,rightMargin=42,topMargin=48,bottomMargin=40,
            title=title,author='Microcom',subject='Review edition; source-inspected bilingual employee training')
        doc.addPageTemplates(PageTemplate(id='guide',frames=[Frame(42,40,width-84,height-88,id='body')],onPage=chrome))
        logo=PILImage.open(ROOT/'static/images/microcom_logo.png')
        story.append(Image(str(ROOT/'static/images/microcom_logo.png'),width=150,height=150*logo.height/logo.width))
        paragraph(title,'Title');paragraph('Employés · approbateurs · stock · administrateurs' if fr else 'Employees · approvers · stock personnel · administrators')
        paragraph('Version 2.0 | '+DATE);paragraph(notice,'NoticeGuide')
        paragraph(('Révision source : ' if fr else 'Source revision: ')+COMMIT)
        paragraph('Aucun accès à la production. Aucune émission financière réelle.' if fr else 'No production access. No real financial issuance.')
        story.append(PageBreak());paragraph('Sommaire' if fr else 'Contents','Heading1')
        toc=TableOfContents();toc.levelStyles=[ParagraphStyle(name='TOCGuide',fontName='Guide',fontSize=11,leading=18,leftIndent=0)]
        story.append(toc);story.append(PageBreak())
        paragraph('Lire ce guide' if fr else 'How to use this guide','Heading1')
        paragraph(notice,'NoticeGuide')
        paragraph('Les cercles bleus numérotés et traits fins désignent les commandes réelles. Chaque légende explique les numéros. Vert : résultat positif ; ambre : contrôle ; rouge : erreur ou action interdite. Ne confondez pas une capture de page avec la validation complète du processus.' if fr else
                  'Blue numbered circles and thin pointers identify real controls. Each caption explains its numbers. Green means success; amber means check; red means error or prohibited action. A captured page does not prove the entire workflow was tested.')
        paragraph('Les captures ont été réalisées avec un administrateur de formation : la présence d’un bouton ne prouve pas les droits d’un autre rôle. Les procédures financières non exécutées sont décrites à partir du code et marquées dans la matrice de validation.' if fr else
                  'Screenshots use a training administrator: a visible button does not prove another role has access. Unexecuted financial procedures are described from source and marked in the validation matrix.')
        for section in CHAPTERS:
            code,en,frtitle,introen,introfr,preen,prefr,stepsen,stepsfr,resulten,resultfr,shots=section
            story.append(PageBreak());heading=code+'. '+(frtitle if fr else en)
            paragraph(heading,'Heading1');md+=['## '+heading,'',introfr if fr else introen,'']
            paragraph(introfr if fr else introen)
            pre=('Prérequis : ' if fr else 'Prerequisites: ')+(prefr if fr else preen)
            paragraph(pre,'NoticeGuide');md += [pre,'']
            for n,step in enumerate(stepsfr if fr else stepsen,1):
                paragraph(f'{n}. {step}');md.append(f'{n}. {step}')
            result=resultfr if fr else resulten;paragraph(result);md+=['',result,'']
            if code=='J':
                extra=('Exemple représentatif : un CPE initialement demandé pour essais MICROCOM est installé chez le CLIENT ; le câble et l’alimentation inutilisés sont réceptionnés au stock. Enregistrez les retours physiques puis une régularisation des résultats mixtes. La classification initiale MICROCOM reste inchangée. Le processus couvre tous les matériels, pas seulement les CPE.' if fr else
                       'Representative example: a CPE initially requested for MICROCOM testing is installed at the CLIENT site; unused cable and power supply are physically received back into stock. Record the returns, then reconcile mixed outcomes. The original MICROCOM classification remains unchanged. This feature supports every stock-managed material, not just CPEs.')
                paragraph(extra);md +=[extra,'']
            for name in shots:
                shot=next(s for s in manifest['screens'] if s['language']==lang and s['name']==name)
                caption=f'{code} · '+FIGURES[name][idx]
                imgpath=DOCS/'manual-assets'/lang/'annotated'/(name+'-annotated.png')
                im=PILImage.open(imgpath)
                scale=min((width-84)/im.width, (height-170)/im.height)
                legends=[]
                for c in shot['callouts']:
                    label=LABELS.get(c['selector'],(c['selector'],c['selector']))[idx]
                    legends.append(f"{c['number']}. {label}")
                legend=' · '.join(legends)
                story.append(KeepTogether([Spacer(1,10),Paragraph(escape(caption),styles['Heading2']),
                    Image(str(imgpath),width=im.width*scale,height=im.height*scale,hAlign='LEFT'),
                    Paragraph(escape(legend),styles['CaptionGuide'])]))
                md +=[f'![{caption}](manual-assets/{lang}/annotated/{name}-annotated.png)','',legend,'']
        story.append(PageBreak());paragraph('Dépannage rapide' if fr else 'Quick troubleshooting','Heading1')
        troubleshooting=[
            ('Missing approval controls: check current assignment and status, not just stock-report access.','Commandes d’approbation absentes : vérifiez l’affectation courante et le statut, pas seulement l’accès aux rapports.'),
            ('Missing price: complete the draft using authorized evidence; never replace an unknown value with zero.','Prix manquant : complétez le brouillon avec des justificatifs autorisés ; ne remplacez pas un inconnu par zéro.'),
            ('Missing sequence/company verification: contact the administrator; never change counters or guards.','Série ou attestation manquante : contactez l’administrateur ; ne modifiez ni compteurs ni protections.'),
            ('PDF failure: return to the issued document and retry only generation, not issuance.','Échec PDF : revenez au document émis et relancez uniquement la génération, pas l’émission.'),
            ('Uncertain financial issuance: retain the same confirmation; inspect history if the session was lost.','Émission financière incertaine : conservez la même confirmation ; consultez l’historique si la session est perdue.'),
            ('Historical over-return or ambiguous OUT: stop returns and request a ledger review.','Retour historique excessif ou sortie ambiguë : arrêtez les retours et demandez une vérification du registre.')]
        md+=['## '+('Dépannage rapide' if fr else 'Quick troubleshooting'),'']
        for en,frtext in troubleshooting:
            text=frtext if fr else en;paragraph(text);md+=['- '+text]
        story.append(PageBreak());paragraph('Glossaire' if fr else 'Glossary','Heading1');md+=['','## '+('Glossaire' if fr else 'Glossary'),'']
        glossary=[('Succursale','Administrative destination/billing entity; not a warehouse.','Destination administrative/de facturation ; pas un entrepôt.'),
            ('BC','Internal material order.','Bon de commande interne.'),('BS','Authorized material issue note.','Bon de sortie autorisée.'),
            ('FAC','Immutable finalized internal bookkeeping invoice.','Facture comptable interne finalisée et immuable.'),
            ('RCP','Nonfinancial receipt linked to actual physical RETURN movements.','Reçu non financier lié aux mouvements physiques RETURN.'),
            ('BR','Invoice-linked returned-material valuation; no refund, credit or stock operation.','Valorisation de retours liée à une facture ; ni remboursement, ni avoir, ni mouvement de stock.'),
            ('Reconciliation / Régularisation','Append-only report of actual material outcomes.','Rapport des résultats réels du matériel, conservé par révisions.'),
            ('Africa/Kinshasa','Business timezone used for annual numbering and operational reporting.','Fuseau métier des références annuelles et rapports opérationnels.')]
        for term,en,frtext in glossary:
            text=term+' — '+(frtext if fr else en);paragraph(text);md +=['- '+text]
        paragraph('Validation et captures manquantes : voir user-manual-validation.md et manual-screenshot-checklist.md.' if fr else 'Validation and missing captures: see user-manual-validation.md and manual-screenshot-checklist.md.','NoticeGuide')
        doc.multiBuild(story)
        (DOCS/f'user-manual-{lang}.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
        reader=PdfReader(str(out))
        assert all(p.extract_text().strip() for p in reader.pages)
        results.append({'language':lang,'pdf':out.name,'pages':len(reader.pages),'screenshots':len([s for s in manifest['screens'] if s['language']==lang]),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
    (DOCS/'manual-assets/build-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results))

if __name__=='__main__':
    build()
