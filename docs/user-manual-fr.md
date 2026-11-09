![Microcom](manual-assets/microcom-logo.png)

# Système d’approbation Microcom

## Guide de formation des employés

**NOVEMBRE 2026 — GUIDE UTILISATEUR TEXTUEL**

Version 3.0 · November / novembre 2026 · 2026-11-09

Source: 72b527b739d2e42a0ead10d17af4ec571876dfc8

Édition textuelle finalisée. Suivez les procédures numérotées correspondant à vos droits. Les captures de l’application feront l’objet d’une amélioration distincte.

[Validation](user-manual-validation.md) · [Capture checklist / Liste des captures](manual-screenshot-checklist.md) · [EN/FR](user-manual-en.md)

## Sommaire

- [0. Utiliser ce guide](#guide-start)
- [1. Se connecter](#01-login)
- [2. Naviguer dans le tableau de bord](#02-dashboard)
- [3. Créer une demande administrative](#03-administrative)
- [4. Créer une demande de matériel de technicien](#04-material)
- [5. Classer à l’étape désignée de revue du stock](#05-classification)
- [6. Choisir la succursale](#06-succursale)
- [7. Approuver, rejeter ou retourner](#07-decisions)
- [8. Corriger, soumettre de nouveau ou annuler](#08-correction)
- [9. Consulter disponibilité et rapports stock](#09-stock)
- [10. Gérer le catalogue, les prix et les devises](#10-catalog)
- [11. Comprendre la déduction automatique](#11-deduction)
- [12. Émettre les BC et BS](#12-bcbs)
- [13. Créer et préparer un brouillon de facture](#13-invoice-draft)
- [14. Vérifier et finaliser la facture](#14-invoice-issue)
- [15. Avoirs : limite de disponibilité](#15-credit-boundary)
- [16. Enregistrer un retour physique](#16-physical-return)
- [17. Régulariser l’utilisation du matériel](#17-reconciliation)
- [18. Émettre un reçu RCP non financier](#18-receipt)
- [19. Émettre un bon valorisé lié à la facture](#19-return-note)
- [20. Suivre approbations et audit](#20-audit)
- [21. Gérer comptes et permissions](#21-users)
- [22. Configurer les workflows](#22-workflows)
- [23. Configurer société et informations documentaires vérifiées](#23-company)
- [24. Imprimer et télécharger les documents](#24-print)
- [25. Dépanner sans doublons](#25-errors)
- [26. Créer un matériel et son stock initial](#26-entry-new)
- [27. Réceptionner un matériel existant](#27-entry-existing)
- [28. Enregistrer, reprendre et annuler un brouillon d’entrée](#28-entry-drafts)
- [29. Utiliser les notifications et préférences de courriel](#29-notifications)
- [A. Glossaire et références](#glossary)

<a id="guide-start"></a>

## 0. Utiliser ce guide

Version de novembre 2026. Les procédures reflètent le code courant et la nouvelle présentation de la page Factures. Aucune donnée de production n’a été utilisée pour préparer ce guide.

Microcom possède un stock central unique. Les succursales sont administratives/de facturation, jamais des entrepôts. Request For Department possède/oriente la demande ; ce n’est pas une succursale de facturation. La classification initiale diffère des utilisations ultérieures. CLIENT est exclu de la facturation interne ; chaque demande MICROCOM admissible peut avoir une facture selon besoin.

Lisez les prérequis, suivez les étapes numérotées puis vérifiez le résultat attendu. Les contrôles importants précisent droits, erreurs et protections. Les exemples utilisent des références fictives.

| Role / Rôle | Access / Accès |
|---|---|
| Employé / technicien | Ses soumissions, modification de ses Draft/Returned, annulation de ses demandes ouvertes et documents autorisés ; département requis pour créer. |
| Principal / suppléant | Étape courante affectée en attente seulement ; consultation affectée autorisée. Les suivants attendent. |
| Personnel du stock | can_manage_stock ou superutilisateur : rapports, retours physiques, régularisations, RCP et notes approuvées. Aucun droit facture implicite. |
| Lecteur administratif | can_view_administration_reports ou superutilisateur : rapport approuvé du type configuré tous départements, sans détails ordinaires/approbation. |
| Opérateur facture | view_invoice et droit d’action, périmètre de revue stock ; superutilisateur ou staff + manage_all_invoices pour global. |
| Administrateur | Droits staff/modèles et attestations financières explicites. Un nom de rôle n’accorde pas tout. |

Brouillon/demande → soumission → revue désignée stock désignée (si configurée) → approbations ordonnées → approbation finale et déduction unique. Puis BC/BS et, pour MICROCOM admissible, création/revue/finalisation de facture. Ensuite : retour physique restaure le stock ; régularisation décrit les résultats ; RCP documente les retours ; bon lié à facture les valorise. Aucun ne crée automatiquement d’avoir comptable.

<a id="01-login"></a>

## 1. Se connecter

**Avant de commencer** — Utilisez votre compte actif et l’adresse de l’application fournie par l’informatique.

### Procédure

1. Ouvrez l’adresse approuvée et vérifiez que vous êtes sur le système attendu.

2. Saisissez identifiant/mot de passe puis utilisez le bouton de connexion.

3. En cas d’oubli, utilisez le lien de réinitialisation et le courriel enregistré ; contactez l’informatique si nécessaire.

> **Contrôle important** — Ne capturez jamais un mot de passe rempli. L’expiration exige une reconnexion et peut perdre les modifications non enregistrées.

> **Résultat attendu** — Le tableau de bord s’ouvre ; les comptes invalides/inactifs restent bloqués.

<details><summary>Référence du code</summary>

config/urls.py; accounts/forms.py; templates/registration/login.html

</details>

<a id="02-dashboard"></a>

## 2. Naviguer dans le tableau de bord

**Avant de commencer** — Les utilisateurs connectés voient la navigation selon leurs droits. Le texte de statut n’est pas un contrôle de santé en temps réel.

### Procédure

1. Utilisez Create Request / New Request pour commencer et My Requests pour vos soumissions.

2. Approvals affiche vos étapes courantes ; Approval History vos décisions.

3. Ouvrez les rapports autorisés ou Invoices. Choisissez FR/EN avec le sélecteur ; terminez par Logout.

> **Contrôle important** — Un nom de rôle ne donne pas tous les menus. Consultez les listes même sans courriel : les notifications peuvent échouer silencieusement.

> **Résultat attendu** — La bonne rubrique s’ouvre dans la langue choisie.

<details><summary>Référence du code</summary>

core/views.py; templates/core/dashboard.html; templates/base.html; requests_app/context_processors.py

</details>

<a id="03-administrative"></a>

## 3. Créer une demande administrative

**Avant de commencer** — Le compte exige un département et un workflow configuré. Les indicateurs du type imposent les champs.

### Procédure

1. Choisissez Request Type et Request For Department : équipe responsable, pas succursale de facturation.

2. Saisissez description, Date Needed et Amount si requis ; joignez les justificatifs.

3. Leave Permission exige By Foot/By Car, destination et motif ; heures/chauffeur sont facultatifs. Site Authorization exige site, dates, agents Microcom et motif ; TT/personnes externes sont facultatifs.

4. Submit Request, ou Save as Draft. Rouvrez My Requests → Edit Draft, complétez puis soumettez.

> **Contrôle important** — Un brouillon ne lance ni approbation ni réservation. Vérifiez les lignes incomplètes sauvegardées. Amount n’est ni facture ni paiement. Contrôlez la chronologie vous-même.

> **Résultat attendu** — La soumission lance le circuit ; le brouillon reste modifiable et non soumis. Relevez la référence.

<details><summary>Référence du code</summary>

requests_app/forms.py; requests_app/views.py:create_request; templates/requests_app/create_request.html

</details>

<a id="04-material"></a>

## 4. Créer une demande de matériel de technicien

**Avant de commencer** — Choisissez type matériel, département responsable et articles actifs. Tout provient du stock central.

### Procédure

1. Saisissez objet/destination et Date Needed.

2. Recherchez par nom, code ou catégorie, ou Filter By Category ; choisissez l’article réel et une quantité positive dans son unité.

3. Utilisez + Add Material / Remove, une ligne par article ; vérifiez puis Submit Request ou Save as Draft.

> **Contrôle important** — Au moins un article, sans doublon, avec quantités positives valides. Stock contrôlé à la saisie et à la fin ; rien n’est réservé. Aucune note par ligne affichée : utilisez la description.

> **Résultat attendu** — La demande entre en approbation. Les techniciens ne classent pas et ne choisissent pas la succursale de facturation.

<details><summary>Référence du code</summary>

requests_app/forms.py; requests_app/views.py:create_request; templates/requests_app/includes/material_formset.html

</details>

<a id="05-classification"></a>

## 5. Classer à l’étape désignée de revue du stock

**Avant de commencer** — Seul le titulaire actif ou son suppléant affecté peut classer lorsque cette étape est courante ; les étapes précédentes doivent être terminées.

### Procédure

1. Ouvrez l’approbation courante qui vous est affectée et vérifiez le matériel et le motif.

2. Choisissez Approuver puis CLIENT ou MICROCOM. CLIENT ne nécessite aucune succursale.

3. Pour MICROCOM, choisissez la succursale active appropriée, ajoutez le commentaire requis et soumettez.

4. Les approbateurs suivants attendent leur tour. La revue du stock peut être la deuxième ou la dernière étape sans réordonner les autres.

> **Contrôle important** — Une seule revue peut être désignée. Sa configuration reste facultative : l’administrateur doit la prévoir dans les circuits matériels. Le retour et le rejet n’exigent pas de classification.

> **Résultat attendu** — Une classification valide est obligatoire pour approuver cette étape. Les demandes CLIENT ne nécessitent pas de facture interne.

<details><summary>Référence du code</summary>

requests_app/approval_forms.py; requests_app/classification.py; requests_app/services.py:approve_step; workflows/models.py

</details>

<a id="06-succursale"></a>

## 6. Choisir la succursale

**Avant de commencer** — Une succursale est administrative/de facturation, jamais un entrepôt. Vous êtes l’approbatrice stock désignée approuvant Microcom.

### Procédure

1. Confirmez la destination avec l’équipe et choisissez code/nom dans Succursale.

2. Si absente/inactive, faites contrôler Inventory → Succursales par un administrateur ; ne remplacez pas par une autre succursale ou un département.

3. Soumettez puis vérifiez classification/succursale dans les détails.

> **Contrôle important** — Microcom exige une succursale ; Client n’en accepte pas. Adresse physique requise à la création et à la facture, même pour les anciennes. La sélection ne transfère aucun stock.

> **Résultat attendu** — L’entité de facturation est liée ; le stock reste central.

<details><summary>Référence du code</summary>

requests_app/approval_forms.py; requests_app/classification.py; inventory/models.py:Succursale; inventory/admin.py

</details>

<a id="07-decisions"></a>

## 7. Approuver, rejeter ou retourner

**Avant de commencer** — Seule votre étape principale/suppléante courante en attente d’une demande ouverte est traitable.

### Procédure

1. Filtrez Approvals par type, département responsable, recherche ou période Date Needed.

2. Examinez détails, montant, matériels et pièces avant Review / Approve Request.

3. Choisissez Approve, Reject ou Return for changes, expliquez dans Comment puis Submit ; actualisez.

> **Contrôle important** — Commentaire facultatif mais recommandé pour rejet/correction. Après l’action d’un acteur, l’autre ne répète pas. Les suivants attendent ; superutilisateur seul ne contourne pas l’affectation. Required ne saute pas d’étape.

> **Résultat attendu** — Approve avance/finalise ; Return produit Returned ; Reject clôt en Rejected, sans resoumission ordinaire.

<details><summary>Référence du code</summary>

requests_app/views.py:pending_approvals,approval_detail; requests_app/services.py; requests_app/approval_forms.py

</details>

<a id="08-correction"></a>

## 8. Corriger, soumettre de nouveau ou annuler

**Avant de commencer** — Le propriétaire actif modifie son propre brouillon ou sa demande retournée. Lisez d’abord le commentaire de retour.

### Procédure

1. Ouvrez Mes demandes, la demande, puis Modifier et soumettre de nouveau ou Modifier le brouillon.

2. Corrigez les informations et les lignes ; ajoutez les pièces nécessaires. Enregistrer les modifications laisse une demande retournée dans cet état.

3. Choisissez Soumettre de nouveau lorsque tout est complet. Une demande matérielle reprend le circuit applicable depuis le début.

4. Une autorisation générale peut reprendre à l’étape de retour uniquement si les informations pertinentes, le circuit et les preuves fiables restent inchangés ; sinon elle recommence.

5. Lisez le résultat et les tentatives précédentes. Si nécessaire, utilisez Annuler la demande uniquement pour une demande ouverte admissible, puis confirmez.

> **Contrôle important** — Les étapes antérieures sont archivées avant reconstruction du circuit actif. Les historiques antérieurs à cette fonction ne sont pas reconstitués. Une demande rejetée ne dispose pas de resoumission ordinaire.

> **Résultat attendu** — La référence initiale reste stable ; les décisions précédentes restent consultables comme preuves archivées.

<details><summary>Référence du code</summary>

requests_app/views.py:edit_request,cancel_request; requests_app/services.py:resubmit_request; templates/requests_app/edit_request.html

</details>

<a id="09-stock"></a>

## 9. Consulter disponibilité et rapports stock

**Avant de commencer** — Disponibilité visible au sélecteur/détails autorisés. Material Reports exige can_manage_stock ou superutilisateur.

### Procédure

1. Vérifiez unités et disponibilité centrale ; consulter ne réserve aucun stock.

2. Ouvrez les rapports matériels et appliquez les filtres proposés : demande, département et dates.

3. Consultez inventaire courant, entrées, sorties/retours et activité du stock selon les rubriques disponibles. Séparez unités et devises.

4. Exportez le rapport Excel filtré. Feuilles et valeurs financières restent soumises aux droits ; l’export ne mouvemente ni n’émet de document.

> **Contrôle important** — Quantités demandées, soldes courants et retours nets sont des mesures différentes. Réduisez les exports trop volumineux et examinez toute incohérence avant une nouvelle opération.

> **Résultat attendu** — Retrouvez les demandes approuvées et exportez sans mouvement stock.

<details><summary>Référence du code</summary>

inventory/models.py; requests_app/views.py:material_reports; templates/requests_app/material_reports.html

</details>

<a id="10-catalog"></a>

## 10. Gérer le catalogue, les prix et les devises

**Avant de commencer** — Django Admin exige l’accès staff et les permissions matérielles. Le personnel actif du stock peut aussi modifier les prix depuis les entrées de matériel.

### Procédure

1. Dans Inventaire → Matériels, gérez catégorie, code unique, nom, description, unité, activation et seuil minimal.

2. À l’ouverture du formulaire d’ajout, la devise provient des paramètres documentaires, sinon USD. Une devise USD, CDF ou EUR existante reste sélectionnée ; une devise non affectée affiche la valeur par défaut.

3. Renseignez le prix unitaire connu et choisissez USD, CDF ou EUR. Un prix vide est inconnu ; zéro est un prix explicite. Aucune conversion n’est effectuée.

4. Pour modifier un prix ou une devise existants, saisissez le motif puis enregistrez. Les versions du stock, du prix et du catalogue doivent correspondre ; rechargez en cas de conflit.

5. Vous pouvez aussi choisir un matériel dans Réceptionner du stock puis Modifier le prix. Saisissez prix, devise et motif précis, puis enregistrez dans la boîte de dialogue. Cette action est distincte de la réception.

6. Dans Admin, consultez l’historique des prix : acteur, motif, anciennes et nouvelles valeurs, origine. Utilisez les entrées de matériel pour tracer les livraisons.

> **Contrôle important** — Une devise soumise vide avec un prix prend la devise documentaire, sinon USD, même si l’ancienne différait. Ouvrir le formulaire ne modifie rien. Enregistrer la valeur affichée produit une modification auditée. La modification directe du stock dans Admin ne crée pas de réception.

> **Résultat attendu** — L’historique des prix est protégé. Les changements du catalogue ne réécrivent ni factures finalisées, ni quantités, ni anciennes écritures.

<details><summary>Référence du code</summary>

inventory/models.py; inventory/admin.py; core/document_config.py

</details>

<a id="11-deduction"></a>

## 11. Comprendre la déduction automatique

**Avant de commencer** — Aucun bouton Deduct Stock. Le dernier approbateur affecté termine le circuit matériel.

### Procédure

1. Examinez puis soumettez la dernière action Approve.

2. Si stock insuffisant, faites contrôler par le stock ; ne forcez pas Approved.

3. Après réussite, vérifiez Approved et le suivi ; un administrateur autorisé peut consulter les OUT liés.

> **Contrôle important** — Le service verrouille demande/soldes et utilise stock_deducted contre les répétitions. Un échec annule la dernière approbation. Protections inspectées, pas testées à l’exécution pour ces guides.

> **Résultat attendu** — Déduction unique et OUT avec acteur. Documents/factures/régularisation ne déduisent pas à nouveau.

<details><summary>Référence du code</summary>

requests_app/services.py:approve_step; requests_app/stock_services.py:deduct_material_stock

</details>

<a id="12-bcbs"></a>

## 12. Émettre les BC et BS

**Avant de commencer** — BC : commande interne ; BS : autorisation de sortie. Exige Approved, stock_deducted, lignes matériel et accès documentaire autorisé.

### Procédure

1. Dans les détails ou Material Reports, ouvrez l’action BC ou BS voulue.

2. À la première émission, contrôlez type/référence puis Confirm & Print. Cancel n’attribue rien.

3. Vérifiez référence officielle, Print 1 copy / Print 2 copies ; plus de six articles impose un exemplaire. Print / Save as PDF, vérifiez A4, signez/archivez.

> **Contrôle important** — Confirmation unique ; même référence en réimpression. Exemples : BC/0001/2026 et BS/0001/2026, pas des données réelles. Aucun mouvement stock. L’impression groupée historique n’attribue pas de BC/BS officiels.

> **Résultat attendu** — Le document numéroté s’ouvre. Référence figée ; noms, stock actuel et remarques peuvent varier à la réimpression.

<details><summary>Référence du code</summary>

requests_app/material_documents.py; requests_app/views.py:material_document; templates/requests_app/material_document_confirm.html

</details>

<a id="13-invoice-draft"></a>

## 13. Créer et préparer un brouillon de facture

**Avant de commencer** — Une facture par demande MICROCOM admissible, à la demande. Exige view_invoice + add_invoice et périmètre, preuves Approved/déduction, revue désignée/succursale et société valide.

### Procédure

1. Ouvrez Factures. Les demandes disponibles pour examen de facturation apparaissent en premier, avant l’historique. Recherchez la référence avec le bouton Rechercher de cette rubrique, puis ouvrez le lien de la demande admissible.

2. Dans l’écran de création, vérifiez la demande MICROCOM et la succursale, choisissez la devise et confirmez la création du brouillon. L’admissibilité est contrôlée avant enregistrement.

3. Sous les demandes disponibles, les factures existantes disposent de leur recherche, des filtres de dates d’émission et de statut, de l’impression des factures filtrées, du tableau et de la pagination. La recherche de demandes ne filtre ni factures ni impression.

4. Edit invoice draft : vérifiez Net billable quantity, saisissez Unit price autorisés et éventuel Invoice note ; Save draft prices.

5. Après de nouveaux retours physiques : Refresh issued quantities, puis revérifiez/enregistrez avant finalisation.

> **Contrôle important** — CLIENT exclu. Aucun numéro officiel au brouillon. Net = sorties moins retours. Prix d’autre devise inconnu, sans conversion. Zéro explicite, vide inconnu. Preuves ambiguës/doublons bloquent.

> **Résultat attendu** — Brouillon modifiable non numéroté prêt à vérifier ; aucune opération stock/paiement.

<details><summary>Référence du code</summary>

invoicing/permissions.py; invoicing/views.py:invoice_list,invoice_create,invoice_edit; invoicing/services.py

</details>

<a id="14-invoice-issue"></a>

## 14. Vérifier et finaliser la facture

**Avant de commencer** — Exige view_invoice + finalize_invoice et périmètre ; prix/net vérifiés ; attestation société, série annuelle vérifiée et adresse physique de succursale.

### Procédure

1. Ouvrez Finalize invoice et comparez articles, net, prix et totaux aux preuves.

2. Choisissez Invoice series. Si absente, faites vérifier la numérotation ; n’inventez pas de numéro.

3. Cochez la confirmation permanente puis Finalize invoice. Vérifiez Finalized, numéro, date, succursale, total et historique.

> **Contrôle important** — Revue utilisateur et attestations sont des prérequis, pas un statut supplémentaire. Données financières/parties et numéro deviennent immuables. Devise homogène ; date/année Africa/Kinshasa. Nouveaux retours/révision périmée : actualiser/revoir.

> **Résultat attendu** — Pièce comptable définitive sans seconde déduction. Les retours ne la réécrivent pas ; modification/suppression ordinaire indisponible.

<details><summary>Référence du code</summary>

invoicing/forms.py; invoicing/services.py:finalize_invoice; invoicing/views.py:invoice_finalize

</details>

<a id="15-credit-boundary"></a>

## 15. Avoirs : limite de disponibilité

**Avant de commencer** — Modèles/protections de base présents, mais aucune route utilisateur de création/émission ni cycle administratif d’avoir enregistré trouvé.

### Procédure

1. Relevez facture d’origine et preuves de retour physique.

2. Demandez l’évaluation aux Finances/informatique ; n’inventez pas de bouton Create credit note.

3. Distinguez reçu RCP, valorisation liée à la facture et avoir comptable.

> **Contrôle important** — Protections : facture finalisée/devise, retours attribuables, plafonds, revue explicite, numérotation vérifiée et preuves finales immuables. Cela ne prouve ni protections déployées ni parcours utilisateur. Les affectations d’avoir actives peuvent bloquer les bons valorisés.

> **Résultat attendu** — Besoin transmis sans fabriquer d’avoir. Limite de disponibilité, pas procédure d’émission.

<details><summary>Référence du code</summary>

invoicing/models.py:CreditNote,CreditAllocation,CreditOperation; invoicing/migrations/0004_credit_reservation_schema.py; invoicing/migrations/0005_credit_financial_guards.py; invoicing/urls.py; invoicing/admin.py

</details>

<a id="16-physical-return"></a>

## 16. Enregistrer un retour physique

**Avant de commencer** — Accès stock, demande Approved/déduite et preuves OUT/RETURN cohérentes requis. Recevez les biens avant saisie.

### Procédure

1. Material Management → Returns & Receipts : développez l’article. La page séparée Return to Stock reste disponible.

2. Vérifiez Available to return ; saisissez Returned Quantity positive (deux décimales) et Return Reason obligatoire.

3. Confirm return to stock, vérifiez le dialogue puis Confirm ; Back annule. Vérifiez réussite/reste. Retour complet : aucun formulaire actif.

> **Contrôle important** — Plafond cumulé contrôlé. Verrous/transaction protègent stock/mouvement/audit. Rejeu exact du jeton validé sans double ajout. Si incertain, même formulaire ou historique, pas nouvelle opération. Anciennes preuves ambiguës bloquées. Contrôles serveur sans JavaScript.

> **Résultat attendu** — Stock restauré une fois, RETURN/motif. Dix sortis moins quatre retournés : six admissibles. Aucun document financier/reçu automatique.

<details><summary>Référence du code</summary>

requests_app/stock_services.py:return_material_stock,material_return_totals; requests_app/material_outcome_views.py; requests_app/stock_forms.py

</details>

<a id="17-reconciliation"></a>

## 17. Régulariser l’utilisation du matériel

**Avant de commencer** — Le stock enregistre les résultats pour le technicien d’origine d’une demande Approved/déduite. Classification initiale inchangée.

### Procédure

1. Material Management → Overview, puis Reconcile et développez chaque article.

2. Destination rapide pour tout le reste ou Split quantities / multiple outcomes : CLIENT-installed, MICROCOM-used, Retained / testing.

3. Physically returned vient des mouvements, en lecture seule. Les quatre résultats totalisent la sortie. Short explanation, Review and save, vérifiez puis Confirm ; consultez Reconciliation history.

> **Contrôle important** — Avant révision, usage inconnu. De nouveaux retours peuvent produire Review required. Rechargez et ajoutez une révision ; les anciennes restent. Aucun changement stock/facture.

> **Résultat attendu** — Résultats versionnés pour toute unité : dix sortis = quatre CLIENT + deux MICROCOM + un conservé + trois retournés.

<details><summary>Référence du code</summary>

requests_app/material_outcomes.py:reconcile; requests_app/material_outcome_views.py; templates/requests_app/material_outcomes.html

</details>

<a id="18-receipt"></a>

## 18. Émettre un reçu RCP non financier

**Avant de commencer** — Generate Bon de retour crée un reçu RCP de retour physique, pas un avoir ou une valorisation liée à la facture.

### Procédure

1. Avec accès stock, sélectionnez les RETURN réels dans Material Return Receipt.

2. Generate Bon de retour, vérifiez puis Confirm ; Back n’émet rien.

3. Vérifiez référence/historique RCP. Réglez la langue de l’application puis View PDF / Print ; utilisez le lecteur pour enregistrer/imprimer.

> **Contrôle important** — Retours réels distincts pas encore reçus dans un RCP. Rejeu exact : même reçu. Ni stock, avoir, remboursement ou ajustement facture. Échec PDF : reprise du reçu, pas nouvelle émission.

> **Résultat attendu** — Référence RCP/année permanente et données de retour figées en PDF protégé.

<details><summary>Référence du code</summary>

requests_app/material_outcomes.py:issue_receipt; requests_app/material_outcome_views.py:receipt_pdf; requests_app/return_receipt_documents.py

</details>

<a id="19-return-note"></a>

## 19. Émettre un bon valorisé lié à la facture

**Avant de commencer** — Exige interface activée, facture interne finalisée, retours complets admissibles, série/année RETURN_NOTE vérifiée, périmètre et droits dédiés.

### Procédure

1. Depuis la facture finalisée : Issue material return note ou Material return note history.

2. Sélectionnez mouvements complets, Operation reason et Return note series ; Preview material return note.

3. Vérifiez facture, prix figés, quantités, valeur retournée, cumul et valeur nette ajustée. Change selection si besoin ; aperçu sans numéro.

4. Cochez la confirmation permanente puis Issue material return note ; vérifiez numéro/historique puis Print selon droits.

> **Contrôle important** — Paramètres actuels activés, repli/anciennes notes désactivés : vérifiez le déploiement sans changer les drapeaux. Retours exclus avant facture, doublons, preuve ambiguë ou avoirs affectés actifs peuvent bloquer. Confirmation max deux heures, session parfois plus courte. Réponse perdue : historique d’abord.

> **Résultat attendu** — Valorisation permanente aux prix d’origine sans stock, avoir/ajustement paiement ni réécriture de facture. Distincte du RCP.

<details><summary>Référence du code</summary>

invoicing/return_note_access.py; invoicing/return_note_views.py; invoicing/return_note_services.py; invoicing/return_note_forms.py; config/settings.py

</details>

<a id="20-audit"></a>

## 20. Suivre approbations et audit

**Avant de commencer** — Utilisez propriété/affectation ou droits rapport/facture ; accès rapport seul n’ouvre pas les détails ordinaires.

### Procédure

1. My Requests → détails : référence/statut, origine/responsable, pièces, Approval Timeline et Audit Log.

2. Approval History affiche votre dernière action non en attente admissible par demande, pas toutes les affectations ; filtre responsable.

3. Invoice history → Audit details explique les événements financiers. Material Management conserve révisions et historique RCP.

4. Administration Report : type configuré approuvé, recherche, origine/responsable/demandeur et dates de soumission, puis View Document / Print (25/page).

5. Pour une autorisation Administration approuvée, Voir le document / Imprimer ouvre le Bon d’accès dédié. Le droit au rapport ne donne pas de droit ordinaire de modification ou d’approbation.

> **Contrôle important** — Les approbations antérieures sont archivées à la resoumission et consultables dans les tentatives précédentes. Les historiques manquants plus anciens ne sont pas reconstitués. L’audit ne fige pas tous les champs.

> **Résultat attendu** — Le support relie référence/action/heure en distinguant décisions, stock et documents.

<details><summary>Référence du code</summary>

requests_app/views.py:request_detail,approval_history,administration_reports; invoicing/views.py:invoice_detail; templates/requests_app/request_detail.html

</details>

<a id="21-users"></a>

## 21. Gérer comptes et permissions

**Avant de commencer** — Accès staff/modèles et procédure de comptes approuvés requis. Aucun compte créé pendant cette préparation.

### Procédure

1. Accounts → Users : identité, courriel requis, département, rôle, Active ; Departments/Roles séparément.

2. Accordez Can Manage Stock Reports / Can view administration reports selon besoin ; accès staff/modèles distinct.

3. Factures : view_invoice et add/change/finalize nécessaires, avec périmètre d’affectation revue stock. Global : superutilisateur ou staff + manage_all_invoices.

4. Bons valorisés : view_invoice + view_materialreturnnote ; aperçu aussi issue_materialreturnnote ; émission aussi add_materialreturnnote ; documents aussi view_materialreturnnote_document. Enregistrez puis faites vérifier.

> **Contrôle important** — ModelAdmin personnalisé sans assistant standard : jamais de mot de passe en clair dans le champ brut ; procédure approuvée. Désactivez les départs, conservez les acteurs. Stock ou staff seul ne donne pas facturation/périmètre.

> **Résultat attendu** — Les comptes existants ont les droits approuvés ; les étapes courantes affectées contrôlent l’approbation.

<details><summary>Référence du code</summary>

accounts/admin.py; accounts/models.py; invoicing/permissions.py; requests_app/material_outcomes.py:authorize

</details>

<a id="22-workflows"></a>

## 22. Configurer les workflows

**Avant de commencer** — Administrateur autorisé et politique approuvée. Routage par type/montant et département responsable, puis repli global sans département.

### Procédure

1. Gérez Request types et indicateurs Requires materials / Requires amount / Is permission request ; espace de référence affecté inchangé.

2. Workflows → Approval workflows : type, responsable facultatif, bornes, Active.

3. Ajoutez étapes ordonnées uniques : utilisateur ou rôle actif du département responsable, avec suppléant si besoin.

4. Pour un circuit matériel, désignez au plus une revue du stock à toute position valide, avec titulaire nominatif actif et suppléant actif éventuel. Enregistrez sans réordonner les étapes existantes.

> **Contrôle important** — La revue du stock ne devient accessible qu’après les approbations précédentes. Vérifiez le circuit avec des données de répétition autorisées.

> **Résultat attendu** — Les futures soumissions suivent la configuration ; enregistrer ne prouve pas la réception à l’exécution.

<details><summary>Référence du code</summary>

workflows/models.py; workflows/admin.py; requests_app/services.py:get_applicable_workflow,create_approval_steps

</details>

<a id="23-company"></a>

## 23. Configurer société et informations documentaires vérifiées

**Avant de commencer** — Droits staff/modèles dont invoicing.add_companyverification pour société et invoicing.change_documentsequence pour séquence ; historique externe contrôlé.

### Procédure

1. Core → Company and document settings : nom, adresse vérifiée, contacts, logo statique existant, devise USD/CDF/EUR et Africa/Kinshasa ; Save.

2. Dans la liste, sélectionnez et Attest current company information après contrôle ; réattestez les changements pertinents.

3. Invoicing → Document sequences : INVOICE ou RETURN_NOTE, année/série/format/départ sûr et preuves externes. Save, sélectionnez puis Attest checked external numbering history.

4. Inventory → Succursales : code/nom/actif/adresse ; nouvelles succursales et facturation exigent l’adresse.

> **Contrôle important** — N’inventez pas de compteur, ne baissez pas les utilisés et ne réécrivez pas les références. Format seul sans attribution ; BC/BS et RCP ont des compteurs séparés. Aucune autorisation de commande annuelle ou changement de drapeau.

> **Résultat attendu** — Société courante et numérotation annuelle attestées, émission possible si autres contrôles réussis ; documents figés inchangés.

<details><summary>Référence du code</summary>

core/models.py; core/admin.py; invoicing/admin.py; invoicing/models.py:CompanyVerification,DocumentSequence; inventory/admin.py

</details>

<a id="24-print"></a>

## 24. Imprimer et télécharger les documents

**Avant de commencer** — Accès documentaire autorisé, documents émis/finalisés et navigateur PDF. Vérifiez type, référence et langue.

### Procédure

1. Réglez la langue ; facture finalisée → Print Invoice. Le serveur prépare le PDF protégé ; utilisez le lecteur.

2. Factures filtrées : deux dates d’émission dans Invoices, recherche/statut puis Print Invoices. Sélection serveur des finalisées sur toutes les pages ; maximum 20.

3. BC/BS : Print / Save as PDF et exemplaires. RCP : View PDF / Print ; bon valorisé : Print.

4. Autorisations approuvées : Permission Document → Print / Save PDF. Lecteurs Administration Report : View Document / Print.

> **Contrôle important** — Factures via PDF protégé, pas impression du corps de page. Limites de 20, taille/pages. Échec PDF sans annuler émission : reprenez l’existant, pas une nouvelle facture/reçu. Impression groupée historique sans BC/BS officiel.

> **Résultat attendu** — PDF/imprimé vérifié avec référence existante. Mise en page, imprimante et protection à vérifier en répétition.

<details><summary>Référence du code</summary>

invoicing/views.py:invoice_print,invoice_bulk_print; invoicing/printing.py; invoicing/print_delivery.py; requests_app/material_outcome_views.py; templates/invoicing/list.html

</details>

<a id="25-errors"></a>

## 25. Dépanner sans doublons

**Avant de commencer** — Lisez l’erreur exacte et conservez la référence. Configuration/preuves incohérentes relèvent de l’informatique.

### Procédure

1. Workflow/département/approbateur absent : signalez type, responsable et montant ; vérifiez My Requests avant recréation.

2. Classification : Client sans succursale, Microcom avec active. Stock/retour excessif/révision périmée : actualisez/corrigez, jamais de statut/mouvement forcé.

3. Facture sans prix/adresse/attestation/série : Finances/informatique. Échec PDF : reprise de l’existant.

4. Confirmation expirée : rouvrez/refaites l’aperçu. Émission incertaine : historique d’abord. Forbidden : permission et périmètre.

> **Contrôle important** — Jamais de nouvelle opération pour vérifier la première. Ni mots de passe ni pièces confidentielles au support. Écran d’avoir absent : limite produit.

> **Résultat attendu** — Résolvez/transmettez référence, heure et message exact, sans doublons stock/document.

<details><summary>Référence du code</summary>

requests_app/approval_forms.py; requests_app/stock_services.py; invoicing/services.py; invoicing/return_note_services.py; PDF error templates

</details>

<a id="26-entry-new"></a>

## 26. Créer un matériel et son stock initial

**Avant de commencer** — Personnel actif du stock ou superutilisateur. Stock central unique, sans choix d’entrepôt.

### Procédure

1. Ouvrez Entrées de matériel puis Enregistrer un nouveau matériel.

2. Saisissez nom, code unique, catégorie, unité, description, activation, seuil et prix facultatif. Ce formulaire propose USD initialement ; choisissez explicitement CDF ou EUR si nécessaire.

3. Saisissez la quantité initiale (au moins 0,01), la date et, si disponibles, fournisseur, référence de livraison et notes.

4. Choisissez Vérifier les détails. Rien n’est encore réceptionné. Contrôlez identité, unité, prix, quantité et livraison ; utilisez Modifier pour corriger.

5. Choisissez Confirmer et enregistrer une fois. Lisez Réception terminée et conservez la référence IN. Ouvrez les détails ou l’historique des réceptions.

> **Contrôle important** — Ce formulaire ne permet pas un stock initial nul ; la création du catalogue dans Admin est distincte. Brouillon et vérification ne créent aucun stock. Après perte de réponse, reprenez la même opération au lieu de créer une livraison en double.

> **Résultat attendu** — La confirmation crée ensemble matériel, réception et mouvement IN. Le stock initial est enregistré une seule fois.

<details><summary>Référence du code</summary>

inventory/entry_forms.py; inventory/entry_services.py; inventory/entry_views.py; templates/inventory/entry_review.html

</details>

<a id="27-entry-existing"></a>

## 27. Réceptionner un matériel existant

**Avant de commencer** — Personnel actif du stock ou superutilisateur. Le droit de modifier les prix seul ne permet ni réception ni historique des réceptions.

### Procédure

1. Ouvrez Entrées de matériel → Réceptionner du stock et recherchez le matériel existant.

2. Vérifiez code, unité, stock courant et prix. Saisissez quantité reçue, date, fournisseur/référence et notes si disponibles.

3. Le stock estimé après réception reste indicatif. Choisissez Vérifier les détails et contrôlez le récapitulatif.

4. Choisissez Confirmer et enregistrer. Relevez référence IN, quantité reçue et stock après réception.

5. Consultez les détails ou l’historique. Nouvelle entrée commence une livraison distincte.

> **Contrôle important** — La confirmation présente les soldes historiques enregistrés, pas le stock actuel. Les anciens reçus sans instantané identitaire signalent les informations du catalogue courant. Une réception n’est liée ni à une demande technicien, ni à une facture ou un avoir.

> **Résultat attendu** — La réception confirmée augmente une seule fois le stock central et crée un mouvement entrant.

<details><summary>Référence du code</summary>

inventory/entry_forms.py; inventory/entry_views.py; inventory/entry_services.py; templates/inventory/receipt_confirmation.html

</details>

<a id="28-entry-drafts"></a>

## 28. Enregistrer, reprendre et annuler un brouillon d’entrée

**Avant de commencer** — Accès au stock ; le brouillon appartient à son créateur et reste distinct d’un brouillon de demande.

### Procédure

1. Dans l’un des formulaires d’entrée, choisissez Enregistrer le brouillon pour conserver les informations sans réceptionner de stock.

2. Après la confirmation d’enregistrement, choisissez Continuer la modification ou Nouvelle entrée. Les brouillons enregistrés vous proposent Reprendre et Annuler.

3. Reprenez le brouillon, complétez-le, puis vérifiez les détails et confirmez l’enregistrement.

4. Pour abandonner un brouillon ouvert, choisissez Annuler le brouillon, vérifiez puis confirmez.

5. Si un autre onglet a modifié le brouillon, rechargez les informations courantes. Un brouillon terminé ne peut pas être annulé ; consultez sa réception.

> **Contrôle important** — Le brouillon ne réserve, ne crée ni matériel ni mouvement IN. Son annulation ne contre-passe pas une réception terminée. N’utilisez pas un ancien onglet pour écraser des données récentes.

> **Résultat attendu** — Seule la confirmation comptabilise la réception ; conserver ou annuler un travail inachevé ne change pas le stock.

<details><summary>Référence du code</summary>

inventory/entry_drafts.py; inventory/entry_views.py; templates/inventory/draft_saved_notice.html; templates/inventory/cancel_entry_draft.html

</details>

<a id="29-notifications"></a>

## 29. Utiliser les notifications et préférences de courriel

**Avant de commencer** — Compte individuel actif. Une notification ne remplace pas les droits d’approbation.

### Procédure

1. Ouvrez Notifications dans la navigation. Choisissez Toutes ou Non lues ; Afficher toutes les notifications ouvre l’historique paginé.

2. Vérifiez référence et état courant. Voir la demande marque la notification comme lue et ouvre la demande uniquement si vos droits le permettent encore.

3. Marquer comme lue accuse réception sans approuver, rejeter ni retourner la demande.

4. Consultez Approbations en attente pour le travail réellement disponible. Une notification historique ne réactive pas une affectation terminée ou remplacée.

5. Demandez à un administrateur habilité de régler Recevoir les notifications par courriel dans Comptes → Utilisateurs. Ce choix concerne les courriels facultatifs du circuit, pas les messages de sécurité ni les notifications internes.

> **Contrôle important** — Le badge compte les notifications d’approbation actives non lues, pas tous les événements historiques. Les anciens événements ne sont pas reconstitués. Un échec de courriel n’annule pas la demande ; consultez les files de travail.

> **Résultat attendu** — La lecture est personnelle. Marquer comme lue ne change ni décision ni stock.

<details><summary>Référence du code</summary>

requests_app/notifications.py; requests_app/notification_views.py; templates/includes/workflow_notifications.html; accounts/admin.py

</details>

<a id="glossary"></a>

## A. Glossaire et références

Nouvelles références : REQ-{espace}-{compteur}/{année}, ex. REQ-MAT-0001/2026 ou REQ-ADM-0001/2026 : formats illustratifs, pas des données réelles. Durables à la création, brouillons compris ; anciennes références inchangées. BC/BS/RCP attribuent séparément à l’émission dans l’année Africa/Kinshasa. Ne réutilisez/réécrivez jamais manuellement.

| Term / Terme | Meaning / Sens |
|---|---|
| Draft / Returned / Rejected | Non soumis / à corriger / clos par rejet : états distincts. |
| Pending / In Review / Approved / Cancelled | Approbation ouverte / en examen / réussite finale / arrêté avant fin. |
| Origine / responsable | Département demandeur / Request For Department pour routage et principaux filtres. |
| CLIENT / MICROCOM | Classification initiale confirmée par revue du stock désignée. |
| BC / BS | Commande interne / sortie autorisée, chacun avec référence officielle. |
| Facture | Pièce comptable figée d’une demande MICROCOM admissible ; pas une opération de paiement. |
| Reçu RCP | Preuve non financière de retour physique, ni avoir/remboursement/ajustement facture. |
| Bon valorisé | Valorisation liée à facture du matériel déjà retourné, pas restauration physique ou avoir. |
| Régularisation | Résultats versionnés : installé CLIENT, utilisé MICROCOM, conservé, retourné. |
| OUT / RETURN | Mouvement réel de déduction / restauration du stock. |
| Material Issue Note | Remarques libres : le stock ouvre les détails approuvés, modifie puis Save Note. Visible dans documents/rapports ; pas de numéro distinct. Le texte antérieur complet n’est pas conservé par l’événement. |
| Audit / données figées | Preuves d’actions / données documentaires conservées ; pas d’historique complet de tous les champs. |

Édition textuelle finalisée. Suivez les procédures numérotées correspondant à vos droits. Les captures de l’application feront l’objet d’une amélioration distincte.
