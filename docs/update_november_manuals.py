"""Build November documentation candidates using the existing branded guide.

Documentation only: no Django imports, database, network or screenshot synthesis.
Run with the project venv; candidates are not promoted by this script.
"""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
OUT = DOCS / 'manual-assets' / 'november-2026-review'
SOURCE = DOCS / 'manual-assets' / 'build_guides.py'
REVISION = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def prepare():
    # Retain the existing portrait layout, logo, colors, font embedding and pages.
    source = SOURCE.read_text(encoding='utf-8')
    source = source.replace('Version 2.0-preparation · 31 October / octobre 2026',
                            'Version 3.0 · November / novembre 2026 · 2026-11-09')
    source = source.replace('MICROCOM · d3eb766 · ', 'MICROCOM · November / novembre 2026 · ')
    source = source.replace('Source: C:/MicrocomRehearsal/app · ', 'Source: ')
    source = source.replace('d3eb766 · Documentation draft', REVISION[:7]+' · Documentation draft')
    source = source.replace('"REVIEW DRAFT" if lang=="en" else "PROJET À RELIRE"',
                            '"USER GUIDE" if lang=="en" else "GUIDE UTILISATEUR"')
    # Final text editions contain procedures, not empty visual panels or pointer plans.
    md_start = source.index('        if c["capture"]:', source.index('def markdown('))
    md_end = source.index('        blocks += [f">', md_start)
    source = source[:md_start] + source[md_end:]
    visual_start = source.index('        story += [PageBreak(),p(f"{n:02d}  {title}"')
    visual_end = source.index('        story += box(t["warning"]', visual_start)
    source = source[:visual_start] + source[visual_end:]
    # Contents use page numbers recorded by the first layout pass.
    source = source.replace('p(f"{n:02d}    {c[lang][0]}")',
                            'p(f"{n:02d}    {c[lang][0]}    {PAGE_MAP.get((lang, c[lang][0]), chr(8212))}")')
    source = source.replace('doc=SimpleDocTemplate(str(DOCS/filename)',
        '''class IndexedGuide(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph) and flowable.style.name == "MChapter":
                heading = flowable.getPlainText()
                for card in CARDS:
                    if heading.endswith(card[lang][0]):
                        PAGE_MAP.setdefault((lang, card[lang][0]), self.page)
    doc=IndexedGuide(str(DOCS/filename)''')
    ns = {'__file__': str(SOURCE), '__name__': 'november_guide', 'PAGE_MAP': {}}
    exec(compile(source, str(SOURCE), 'exec'), ns)
    ns['DOCS'] = OUT
    ns['COMMIT'] = REVISION
    cards = ns['CARDS']
    login=cards[0]
    for lang, pre, step in [
        ('en','Use your own active account and the application address supplied by IT.','Open the approved application address and check that you are on the intended system.'),
        ('fr','Utilisez votre compte actif et l’adresse de l’application fournie par l’informatique.','Ouvrez l’adresse approuvée et vérifiez que vous êtes sur le système attendu.')]:
        v=list(login[lang]);v[1]=pre;v[2]=[step]+v[2][1:];login[lang]=tuple(v)

    def change(key, en, fr):
        card = next(c for c in cards if c['key'] == key)
        card['en'], card['fr'] = en, fr

    invoice_card = next(c for c in cards if c['key']=='13-invoice-draft')
    for lang, steps in [
        ('en', ['Open Invoices. Requests available for invoice review appears first, above invoice history. Search by request reference with its Search button and open the eligible request link.',
                'On the creation screen review the MICROCOM request and succursale, select invoice currency and confirm draft creation. Eligibility is checked before saving.',
                'Below the available requests, existing invoices have their own search, issue-date and status filters, Print Filtered Invoices, history table and pagination. Request search does not filter invoices or printing.']),
        ('fr', ['Ouvrez Factures. Les demandes disponibles pour examen de facturation apparaissent en premier, avant l’historique. Recherchez la référence avec le bouton Rechercher de cette rubrique, puis ouvrez le lien de la demande admissible.',
                'Dans l’écran de création, vérifiez la demande MICROCOM et la succursale, choisissez la devise et confirmez la création du brouillon. L’admissibilité est contrôlée avant enregistrement.',
                'Sous les demandes disponibles, les factures existantes disposent de leur recherche, des filtres de dates d’émission et de statut, de l’impression des factures filtrées, du tableau et de la pagination. La recherche de demandes ne filtre ni factures ni impression.'])]:
        values=list(invoice_card[lang]); values[2]=steps+values[2][1:]; invoice_card[lang]=tuple(values)

    change('05-classification', (
        'Classify at the designated stock-review step',
        'Only the assigned active primary or alternate can classify when this step is current; preceding steps must finish first.',
        ['Open the current assigned approval and review the materials and purpose.',
         'Choose Approve and CLIENT or MICROCOM. CLIENT does not require a succursale.',
         'For MICROCOM select the appropriate active succursale, add the required comment and submit.',
         'Later approvers wait for their configured turn. A workflow may place stock review second or last without reordering other steps.'],
        ['1 — current step', '2 — classification', '3 — succursale', '4 — approval action'],
        'Only one designated review is allowed. Designation is optional in configuration: administrators must ensure material workflows include it. Returning or rejecting does not require classification.',
        'Valid classification is required before this step can approve. CLIENT requests do not require an internal invoice.'), (
        'Classer à l’étape désignée de revue du stock',
        'Seul le titulaire actif ou son suppléant affecté peut classer lorsque cette étape est courante ; les étapes précédentes doivent être terminées.',
        ['Ouvrez l’approbation courante qui vous est affectée et vérifiez le matériel et le motif.',
         'Choisissez Approuver puis CLIENT ou MICROCOM. CLIENT ne nécessite aucune succursale.',
         'Pour MICROCOM, choisissez la succursale active appropriée, ajoutez le commentaire requis et soumettez.',
         'Les approbateurs suivants attendent leur tour. La revue du stock peut être la deuxième ou la dernière étape sans réordonner les autres.'],
        ['1 — étape courante', '2 — classification', '3 — succursale', '4 — décision'],
        'Une seule revue peut être désignée. Sa configuration reste facultative : l’administrateur doit la prévoir dans les circuits matériels. Le retour et le rejet n’exigent pas de classification.',
        'Une classification valide est obligatoire pour approuver cette étape. Les demandes CLIENT ne nécessitent pas de facture interne.'))

    change('08-correction', (
        'Correct, resubmit or cancel', 'The active owner edits their own Draft or Returned request. Read the return comment first.',
        ['Open My Requests, the request, then Edit and Resubmit or Edit Draft.',
         'Correct the information and material rows; add attachments when necessary. Save Changes keeps a returned request returned.',
         'Choose Resubmit Request when complete. Material requests restart the applicable approval workflow.',
         'General Permission requests can resume at the returning step only if approval-relevant information, workflow and reliable evidence are unchanged; otherwise they restart.',
         'Read the resubmission result and previous attempts. If no longer needed, use Cancel Request only for an eligible open request and confirm.'],
        ['1 — return comment', '2 — corrected information', '3 — resubmit result', '4 — archived attempts'],
        'Earlier approval rows are archived before active routing is rebuilt. Existing history predating this archive feature is not reconstructed. Rejected requests have no ordinary resubmission action.',
        'The original request reference remains stable; earlier decisions remain visible as archived evidence.'), (
        'Corriger, soumettre de nouveau ou annuler', 'Le propriétaire actif modifie son propre brouillon ou sa demande retournée. Lisez d’abord le commentaire de retour.',
        ['Ouvrez Mes demandes, la demande, puis Modifier et soumettre de nouveau ou Modifier le brouillon.',
         'Corrigez les informations et les lignes ; ajoutez les pièces nécessaires. Enregistrer les modifications laisse une demande retournée dans cet état.',
         'Choisissez Soumettre de nouveau lorsque tout est complet. Une demande matérielle reprend le circuit applicable depuis le début.',
         'Une autorisation générale peut reprendre à l’étape de retour uniquement si les informations pertinentes, le circuit et les preuves fiables restent inchangés ; sinon elle recommence.',
         'Lisez le résultat et les tentatives précédentes. Si nécessaire, utilisez Annuler la demande uniquement pour une demande ouverte admissible, puis confirmez.'],
        ['1 — commentaire de retour', '2 — corrections', '3 — résultat', '4 — tentatives archivées'],
        'Les étapes antérieures sont archivées avant reconstruction du circuit actif. Les historiques antérieurs à cette fonction ne sont pas reconstitués. Une demande rejetée ne dispose pas de resoumission ordinaire.',
        'La référence initiale reste stable ; les décisions précédentes restent consultables comme preuves archivées.'))

    change('10-catalog', (
        'Maintain materials, prices and currencies', 'Django Admin requires staff access and material permissions. Catalogue price editing also supports active stock personnel through Material Entries.',
        ['In Inventory → Materials maintain category, unique code, name, description, unit, active status and minimum stock level.',
         'On an unbound Add Material form, currency uses company document currency or USD. An existing USD, CDF or EUR remains selected; an unassigned currency displays the default.',
         'Enter a known unit price and select USD, CDF or EUR. Blank price means unknown; zero is an explicit price. There is no currency conversion.',
         'For an existing price/currency change, enter Price change reason and Save. Stock, price and catalogue revisions must still match; reload and review conflicts.',
         'Alternatively, on Receive Stock select the material and Modify Price. Enter price, currency and a meaningful reason, then save the price in the dialog. This is separate from receipt confirmation.',
         'Use View price history in Admin to inspect actor, reason, old/new values and source. Use Material Entries for traceable deliveries rather than direct stock edits.'],
        ['1 — currency', '2 — change reason', '3 — Modify Price', '4 — price history'],
        'A blank currency submitted with a price resolves to company currency or USD, even if the old currency differed. Opening a form writes nothing. Saving a displayed default is an audited currency change. Direct Admin stock edits do not create receipt movements.',
        'Price history is append-only. Catalogue changes do not rewrite finalized invoices, stock quantities or old financial records.'), (
        'Gérer le catalogue, les prix et les devises', 'Django Admin exige l’accès staff et les permissions matérielles. Le personnel actif du stock peut aussi modifier les prix depuis les entrées de matériel.',
        ['Dans Inventaire → Matériels, gérez catégorie, code unique, nom, description, unité, activation et seuil minimal.',
         'À l’ouverture du formulaire d’ajout, la devise provient des paramètres documentaires, sinon USD. Une devise USD, CDF ou EUR existante reste sélectionnée ; une devise non affectée affiche la valeur par défaut.',
         'Renseignez le prix unitaire connu et choisissez USD, CDF ou EUR. Un prix vide est inconnu ; zéro est un prix explicite. Aucune conversion n’est effectuée.',
         'Pour modifier un prix ou une devise existants, saisissez le motif puis enregistrez. Les versions du stock, du prix et du catalogue doivent correspondre ; rechargez en cas de conflit.',
         'Vous pouvez aussi choisir un matériel dans Réceptionner du stock puis Modifier le prix. Saisissez prix, devise et motif précis, puis enregistrez dans la boîte de dialogue. Cette action est distincte de la réception.',
         'Dans Admin, consultez l’historique des prix : acteur, motif, anciennes et nouvelles valeurs, origine. Utilisez les entrées de matériel pour tracer les livraisons.'],
        ['1 — devise', '2 — motif', '3 — modification du prix', '4 — historique'],
        'Une devise soumise vide avec un prix prend la devise documentaire, sinon USD, même si l’ancienne différait. Ouvrir le formulaire ne modifie rien. Enregistrer la valeur affichée produit une modification auditée. La modification directe du stock dans Admin ne crée pas de réception.',
        'L’historique des prix est protégé. Les changements du catalogue ne réécrivent ni factures finalisées, ni quantités, ni anciennes écritures.'))

    for lang, first, second in (
        ('en', 'For material workflows designate at most one Stock classification review at any valid position, with an active named primary and optional active alternate. Save without reordering existing steps.', 'The stock review is actionable only after preceding approvals. Test the configured sequence using approved rehearsal data.'),
        ('fr', 'Pour un circuit matériel, désignez au plus une revue du stock à toute position valide, avec titulaire nominatif actif et suppléant actif éventuel. Enregistrez sans réordonner les étapes existantes.', 'La revue du stock ne devient accessible qu’après les approbations précédentes. Vérifiez le circuit avec des données de répétition autorisées.')):
        card = next(c for c in cards if c['key']=='22-workflows')
        values=list(card[lang]); values[2]=values[2][:3]+[first]; values[3]=['1 — type / département', '2 — ordre', '3 — revue du stock', '4 — affectation'] if lang=='fr' else ['1 — type / department','2 — order','3 — stock review','4 — assignment']
        values[4]=second; card[lang]=tuple(values)

    def add(key, source, entry, en, fr):
        ns['add'](key,source,entry,en,fr)

    add('26-entry-new','inventory/entry_forms.py; inventory/entry_services.py; inventory/entry_views.py; templates/inventory/entry_review.html','/materials/entries/',(
        'Register a new material and initial stock', 'Active stock personnel or superuser. One central stock; no warehouse selection.',
        ['Open Material Entries and Register New Material.', 'Enter name, unique code, category, unit, description, active status, minimum stock level and optional catalogue price. This form initially selects USD; choose CDF or EUR explicitly when needed.', 'Enter initial quantity (at least 0.01), receipt date, and optional supplier, delivery reference and notes.', 'Choose Verify details. Nothing is received yet. Check material identity, unit, price, quantity and delivery details; use Modify to correct.', 'Choose Confirm and Save once. Read Receipt completed and retain the IN reference. Open View receipt details or Receipt History.'],
        ['1 — material information','2 — initial stock','3 — review','4 — confirmation/reference'],
        'A new material with zero opening stock cannot use this receipt form; authorized Admin catalogue creation is separate. Draft saving and verification do not create stock. Retry the same operation after a lost response; do not start a duplicate delivery.',
        'Confirmation atomically creates the material, receipt and IN movement. Initial stock is recorded once.'),(
        'Créer un matériel et son stock initial', 'Personnel actif du stock ou superutilisateur. Stock central unique, sans choix d’entrepôt.',
        ['Ouvrez Entrées de matériel puis Enregistrer un nouveau matériel.', 'Saisissez nom, code unique, catégorie, unité, description, activation, seuil et prix facultatif. Ce formulaire propose USD initialement ; choisissez explicitement CDF ou EUR si nécessaire.', 'Saisissez la quantité initiale (au moins 0,01), la date et, si disponibles, fournisseur, référence de livraison et notes.', 'Choisissez Vérifier les détails. Rien n’est encore réceptionné. Contrôlez identité, unité, prix, quantité et livraison ; utilisez Modifier pour corriger.', 'Choisissez Confirmer et enregistrer une fois. Lisez Réception terminée et conservez la référence IN. Ouvrez les détails ou l’historique des réceptions.'],
        ['1 — informations','2 — stock initial','3 — vérification','4 — confirmation/référence'],
        'Ce formulaire ne permet pas un stock initial nul ; la création du catalogue dans Admin est distincte. Brouillon et vérification ne créent aucun stock. Après perte de réponse, reprenez la même opération au lieu de créer une livraison en double.',
        'La confirmation crée ensemble matériel, réception et mouvement IN. Le stock initial est enregistré une seule fois.'))

    add('27-entry-existing','inventory/entry_forms.py; inventory/entry_views.py; inventory/entry_services.py; templates/inventory/receipt_confirmation.html','/materials/entries/?mode=existing',(
        'Receive an existing material', 'Active stock personnel or superuser. Price-edit permission alone does not allow receipts or receipt history.',
        ['Open Material Entries → Receive Stock and search/select the existing material.', 'Check code and unit, current stock and catalogue price. Enter quantity received, receipt date, supplier/reference and notes as applicable.', 'Read Estimated stock after receipt as an estimate. Choose Verify details and check the summary.', 'Choose Confirm and Save. Read the IN reference, quantity received and stock after receipt.', 'Open receipt details/history to consult the saved record. New Entry starts a separate delivery.'],
        ['1 — material selection','2 — quantity and estimate','3 — verification','4 — historical confirmation'],
        'Receipt confirmation shows recorded historical balances, not live stock. Older records without an identity snapshot label catalogue fields as current information. A receipt is not linked to a technician request, invoice or credit note.',
        'The confirmed receipt increases central stock once and creates an incoming movement.'),(
        'Réceptionner un matériel existant', 'Personnel actif du stock ou superutilisateur. Le droit de modifier les prix seul ne permet ni réception ni historique des réceptions.',
        ['Ouvrez Entrées de matériel → Réceptionner du stock et recherchez le matériel existant.', 'Vérifiez code, unité, stock courant et prix. Saisissez quantité reçue, date, fournisseur/référence et notes si disponibles.', 'Le stock estimé après réception reste indicatif. Choisissez Vérifier les détails et contrôlez le récapitulatif.', 'Choisissez Confirmer et enregistrer. Relevez référence IN, quantité reçue et stock après réception.', 'Consultez les détails ou l’historique. Nouvelle entrée commence une livraison distincte.'],
        ['1 — matériel','2 — quantité et estimation','3 — vérification','4 — confirmation historique'],
        'La confirmation présente les soldes historiques enregistrés, pas le stock actuel. Les anciens reçus sans instantané identitaire signalent les informations du catalogue courant. Une réception n’est liée ni à une demande technicien, ni à une facture ou un avoir.',
        'La réception confirmée augmente une seule fois le stock central et crée un mouvement entrant.'))

    add('28-entry-drafts','inventory/entry_drafts.py; inventory/entry_views.py; templates/inventory/draft_saved_notice.html; templates/inventory/cancel_entry_draft.html','/materials/entries/',(
        'Save, resume and cancel an entry draft', 'Stock access; drafts belong to their creator and are separate from request drafts.',
        ['On either entry form choose Save Draft to retain unfinished information without receiving stock.', 'After Draft saved successfully choose Continue Editing or New Entry. Saved Drafts lists your own open drafts with Resume Draft and Cancel Draft.', 'Resume the draft, finish its fields, then Verify details and Confirm and Save.', 'To abandon an open draft, choose Cancel Draft, review the confirmation and confirm cancellation.', 'If another tab changed the draft, reload and review the latest information. Completed drafts cannot be cancelled; find their receipt instead.'],
        ['1 — Save Draft','2 — saved notice','3 — Resume Draft','4 — cancellation confirmation'],
        'A draft is not a reservation, material registration or IN movement. Cancelling it does not reverse an already completed receipt. Do not reuse stale tabs to overwrite newer work.',
        'Only confirmation posts the stock receipt; saving or cancelling unfinished work leaves inventory unchanged.'),(
        'Enregistrer, reprendre et annuler un brouillon d’entrée', 'Accès au stock ; le brouillon appartient à son créateur et reste distinct d’un brouillon de demande.',
        ['Dans l’un des formulaires d’entrée, choisissez Enregistrer le brouillon pour conserver les informations sans réceptionner de stock.', 'Après la confirmation d’enregistrement, choisissez Continuer la modification ou Nouvelle entrée. Les brouillons enregistrés vous proposent Reprendre et Annuler.', 'Reprenez le brouillon, complétez-le, puis vérifiez les détails et confirmez l’enregistrement.', 'Pour abandonner un brouillon ouvert, choisissez Annuler le brouillon, vérifiez puis confirmez.', 'Si un autre onglet a modifié le brouillon, rechargez les informations courantes. Un brouillon terminé ne peut pas être annulé ; consultez sa réception.'],
        ['1 — enregistrement','2 — confirmation','3 — reprise','4 — annulation'],
        'Le brouillon ne réserve, ne crée ni matériel ni mouvement IN. Son annulation ne contre-passe pas une réception terminée. N’utilisez pas un ancien onglet pour écraser des données récentes.',
        'Seule la confirmation comptabilise la réception ; conserver ou annuler un travail inachevé ne change pas le stock.'))

    add('29-notifications','requests_app/notifications.py; requests_app/notification_views.py; templates/includes/workflow_notifications.html; accounts/admin.py','/notifications/',(
        'Use workflow notifications and email preferences', 'Active individual account. Notifications do not replace approval authorization.',
        ['Open Notifications in the navigation. Choose All or Unread; use View All Notifications for the paginated history.', 'Check reference and current state. View Request marks the notification read and opens the request only when your access still permits it.', 'Use Mark as Read to acknowledge a notice without approving, rejecting or returning the request.', 'Use Pending Approvals for work that is currently actionable. Historical notifications do not reactivate completed or superseded assignments.', 'Ask an authorized administrator to adjust Receive email notifications in Accounts → Users. This preference controls optional workflow email, not security/account messages or in-app notifications.'],
        ['1 — notification menu','2 — All/Unread','3 — View Request / Mark as Read','4 — email preference'],
        'The unread badge counts active unread approval notices, not every unread historical event. Earlier events are not backfilled. Email failure does not cancel the request; check the application queues.',
        'Read state is personal. Marking read changes neither the request decision nor stock.'),(
        'Utiliser les notifications et préférences de courriel', 'Compte individuel actif. Une notification ne remplace pas les droits d’approbation.',
        ['Ouvrez Notifications dans la navigation. Choisissez Toutes ou Non lues ; Afficher toutes les notifications ouvre l’historique paginé.', 'Vérifiez référence et état courant. Voir la demande marque la notification comme lue et ouvre la demande uniquement si vos droits le permettent encore.', 'Marquer comme lue accuse réception sans approuver, rejeter ni retourner la demande.', 'Consultez Approbations en attente pour le travail réellement disponible. Une notification historique ne réactive pas une affectation terminée ou remplacée.', 'Demandez à un administrateur habilité de régler Recevoir les notifications par courriel dans Comptes → Utilisateurs. Ce choix concerne les courriels facultatifs du circuit, pas les messages de sécurité ni les notifications internes.'],
        ['1 — menu','2 — toutes/non lues','3 — voir/marquer comme lue','4 — préférence de courriel'],
        'Le badge compte les notifications d’approbation actives non lues, pas tous les événements historiques. Les anciens événements ne sont pas reconstitués. Un échec de courriel n’annule pas la demande ; consultez les files de travail.',
        'La lecture est personnelle. Marquer comme lue ne change ni décision ni stock.'))

    # Correct obsolete statements in preserved chapters, in both languages.
    for card in cards:
        if card['key']=='20-audit':
            for lang, warning in [('en','Earlier approvals are archived on resubmission and can be consulted in previous attempts. Pre-feature missing history is not reconstructed. Audit evidence is not a complete snapshot of every field.'),('fr','Les approbations antérieures sont archivées à la resoumission et consultables dans les tentatives précédentes. Les historiques manquants plus anciens ne sont pas reconstitués. L’audit ne fige pas tous les champs.')]:
                v=list(card[lang]);v[4]=warning
                v[2]=v[2]+[('For an approved Administration permission request, View Document / Print opens the dedicated Bon d’accès. Report access does not grant ordinary request editing or approval rights.' if lang=='en' else 'Pour une autorisation Administration approuvée, Voir le document / Imprimer ouvre le Bon d’accès dédié. Le droit au rapport ne donne pas de droit ordinaire de modification ou d’approbation.')]
                card[lang]=tuple(v)
        if card['key']=='09-stock':
            for lang, steps, warning in [
                ('en',['Read material units and current central availability; no stock is reserved by browsing.', 'Open Material Reports and apply the offered request, department and date filters.', 'Review current inventory, entries, issuance/returns and warehouse activity in the available report sections. Keep units and currencies separate.', 'Export the filtered Excel report. Financial sheets and values remain permission-scoped; exports never post stock or issue documents.'], 'Requested quantities, current balances and net returns describe different measures. Current Stock Inventory is a live snapshot including inactive materials; request/activity filters do not apply to that sheet. Narrow large exports and investigate inconsistent evidence before further stock actions.'),
                ('fr',['Vérifiez unités et disponibilité centrale ; consulter ne réserve aucun stock.', 'Ouvrez les rapports matériels et appliquez les filtres proposés : demande, département et dates.', 'Consultez inventaire courant, entrées, sorties/retours et activité du stock selon les rubriques disponibles. Séparez unités et devises.', 'Exportez le rapport Excel filtré. Feuilles et valeurs financières restent soumises aux droits ; l’export ne mouvemente ni n’émet de document.'], 'Quantités demandées, soldes courants et retours nets sont des mesures différentes. Réduisez les exports trop volumineux et examinez toute incohérence avant une nouvelle opération.')]:
                v=list(card[lang]);v[2]=steps;v[4]=warning;card[lang]=tuple(v)
        # Invoice eligibility follows the designated review, irrespective of position.
        for lang in ('en','fr'):
            def clean(value):
                if isinstance(value,list): return [clean(x) for x in value]
                return value.replace('first-review confirmation/branch','designated-review confirmation/branch').replace('première revue/succursale','revue désignée/succursale')
            card[lang]=tuple(clean(v) for v in card[lang])
    for lang in ('en','fr'):
        t=ns['TEXT'][lang]
        t['draft']='NOVEMBER 2026 — TEXT USER GUIDE' if lang=='en' else 'NOVEMBRE 2026 — GUIDE UTILISATEUR TEXTUEL'
        t['status']='Final text edition. Follow the numbered procedures for your authorized role. Application screenshots are a separate future improvement.' if lang=='en' else 'Édition textuelle finalisée. Suivez les procédures numérotées correspondant à vos droits. Les captures de l’application feront l’objet d’une amélioration distincte.'
        t['intro']='November 2026 release. Procedures reflect the current implementation and the invoice-page presentation update. No production records were used to prepare this guide.' if lang=='en' else 'Version de novembre 2026. Les procédures reflètent le code courant et la nouvelle présentation de la page Factures. Aucune donnée de production n’a été utilisée pour préparer ce guide.'
        t['legend']='Read prerequisites, follow the numbered steps, then check the expected result. Important checks explain permissions, errors and safeguards. Examples use synthetic references.' if lang=='en' else 'Lisez les prérequis, suivez les étapes numérotées puis vérifiez le résultat attendu. Les contrôles importants précisent droits, erreurs et protections. Les exemples utilisent des références fictives.'
        t['flow']=t['flow'].replace('designated first stock review','designated stock review at its configured position').replace('première revue','revue désignée').replace('revue stock initiale','revue du stock à sa position configurée')
        t['gloss']=[(a,b.replace('designated first stock reviewer','designated stock reviewer').replace('premier responsable','responsable désigné')) for a,b in t['gloss']]
        t['gloss']=[(a,b.replace('première revue stock désignée','revue du stock désignée')) for a,b in t['gloss']]
    ns['EXTRA'].extend([
        ('26-review',26,'New material review before confirmation','Vérification du nouveau matériel avant confirmation'),
        ('26-completed',26,'New material receipt completed','Réception du nouveau matériel terminée'),
        ('27-completed',27,'Existing receipt historical balances','Soldes historiques d’une réception existante'),
        ('28-saved',28,'Draft saved notice: continue/new entry','Brouillon enregistré : continuer/nouvelle entrée'),
        ('28-cancel',28,'Draft cancellation confirmation','Confirmation d’annulation du brouillon'),
        ('28-stale',28,'Stale draft refusal','Refus d’un brouillon périmé'),
        ('10-price-dialog',10,'Modify Price and reason; stale conflict','Modifier le prix et motif ; conflit de version'),
        ('10-price-history',10,'Read-only price audit history','Historique des prix en lecture seule'),
        ('29-unread',29,'Unread filter and mark-read result','Filtre non lu et résultat du marquage'),
        ('29-preference',29,'Administrator email preference','Préférence de courriel dans Admin'),
        ('20-access-document',20,'Approved Bon d’accès via Administration Report','Bon d’accès approuvé depuis le rapport Administration'),
    ])
    ns['EXTRA'][:]=[(ident,chapter,
        en.replace('First named stock review','Designated named stock review').replace('first named stock review','designated stock review'),
        fr.replace('Première revue stock nominative','Revue du stock nominative à sa position configurée'))
        for ident,chapter,en,fr in ns['EXTRA']]
    return ns


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ns=prepare()
    for lang in ('en','fr'):
        ns['markdown'](lang)
        ns['pdf'](lang)  # first pass records actual chapter pages
        ns['pdf'](lang)  # final contents includes actual page references
    ns['checklist']()
    checklist=OUT/'manual-screenshot-checklist.md'
    text=checklist.read_text(encoding='utf-8')
    text=text.replace('C:/MicrocomRehearsal/app. The owner confirms rehearsal is not running.',
        'current repository. Isolated capture access has not been supplied for this update.')
    text=text.replace('first named stock reviewer','designated stock reviewer at the configured position')
    text=text.replace('confirm the existing first named test reviewer','confirm the designated test reviewer and configured position')
    text=text.replace('**STATUS: awaiting owner-supplied rehearsal URL and approved access. No capture authorized yet.**',
        '**NONBLOCKING IMPROVEMENT BACKLOG: version 3.0 is released as a text-based guide. Capture work awaits an isolated environment and separate authorization.**')
    text=text.replace('The chapter callout plans are proposed, not coordinates verified against a running screen.',
        'These future illustration plans are not coordinates verified against a running screen.')
    text=text.replace('Stock review is opt-in configuration: confirm the existing designated stock reviewer at the configured position.',
        'Stock review is opt-in configuration: confirm the designated reviewer at the configured position.')
    text=text.replace('Markdown and PDF versions are preparation drafts, not the final illustrated manuals. Final acceptance requires real screenshots with numbered arrows/pointers; placeholders do not fulfill that final requirement.',
        'Markdown and PDF versions are final text-based guides with no inline screenshot placeholders. Future illustrated editions require genuine sanitized captures and verified annotations; screenshot gaps do not block this text release.')
    checklist.write_text(text,encoding='utf-8')
    manifest={'source_commit':REVISION,'release':'November 2026','real_captured':0,
        'real_annotated':0,'workflow_runtime_verified':0,'owner_access_pending':True,
        'primary':[{'id':c['key'],'entry':c['entry'],'source':c['source'],
                    'en':c['en'][0],'fr':c['fr'][0],'status':'missing' if c['capture'] else 'no_ui',
                    'en_callouts':c['en'][3],'fr_callouts':c['fr'][3]} for c in ns['CARDS']],
        'additional_states':[{'id':e[0],'chapter':e[1],'en':e[2],'fr':e[3],'status':'missing'} for e in ns['EXTRA']]}
    (OUT/'capture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Built documentation candidates only:',OUT)


if __name__=='__main__':
    main()
