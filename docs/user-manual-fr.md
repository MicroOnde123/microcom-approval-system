# Guide utilisateur Microcom

Version 2.0 — 2026-11-02

VERSION DE REVUE — captures authentiques partielles ; écart de circuit et vérification du déploiement non résolus. Ne pas diffuser comme guide final.

Code: `d3eb76641c1bd3efe431f26a4536964a0be1aeaf`

Ce guide révise les guides utilisateur et administrateur de docs/manuals/. Les captures viennent de la véritable application Django locale avec données de formation.

## A. Connexion et navigation

Chaque employé utilise son compte personnel. Les menus dépendent des droits : leur absence ne justifie jamais le partage d’un compte administrateur.

Prérequis : Compte actif ; adresse de l’application communiquée par l’administrateur.

1. Ouvrez l’adresse autorisée et saisissez vos identifiants sur la page de connexion. N’utilisez jamais le lien de réinitialisation d’un autre employé.
2. Depuis le tableau de bord, ouvrez Créer une demande, Mes demandes ou Approbations en attente selon votre tâche. Vérifiez la référence avant toute action.
3. Choisissez English ou Français dans le sélecteur de langue. Les documents suivent la langue active : sélectionnez-la avant d’ouvrir le PDF.
4. Déconnectez-vous après utilisation. Une session expirée impose une nouvelle connexion ; les données non enregistrées peuvent être perdues.

Résultat : votre tableau de bord et les menus autorisés. En cas de refus, faites vérifier l’activation du compte ; ne transmettez aucun mot de passe ni cookie de session.

![A · Connexion](manual-assets/fr/annotated/login-annotated.png)

1. Champ du nom d’utilisateur · 2. Commande de validation : vérifiez la page avant de confirmer

![A · Tableau de bord et navigation](manual-assets/fr/annotated/dashboard-annotated.png)

1. Navigation et choix de langue · 2. Zone de travail du tableau de bord

## B. Demandes administratives et corrections

Le champ Demande pour le département détermine le département responsable et le circuit. Enregistrer un brouillon ne le soumet pas aux approbateurs.

Prérequis : Demandeur connecté ; type actif et circuit applicable.

1. Ouvrez Créer une demande. Sélectionnez le type et le département destinataire ; renseignez Description / Motif, la date souhaitée et les champs propres au type.
2. Joignez les pièces nécessaires. Vérifiez leur contenu et retirez les informations confidentielles sans rapport avec la demande.
3. Enregistrez un brouillon pour continuer plus tard, ou soumettez la demande complète. Notez sa référence REQ-ADM ; les autres types disposent de leur propre espace de références.
4. Dans Mes demandes, filtrez par référence, département, type, statut ou dates. Consultez le détail pour lire les commentaires et suivre les approbations.
5. Pour une demande retournée, lisez le commentaire, ouvrez la modification, corrigez puis soumettez de nouveau. La référence initiale reste inchangée.
6. Annulez uniquement lorsque cette action est proposée pour votre demande ouverte. Une demande approuvée ne peut pas être réécrite par ce processus.

Résultat : une référence stable, y compris pour le brouillon et les nouvelles soumissions. Si aucun circuit ne correspond, contactez l’administrateur plutôt que de modifier le département pour contourner le contrôle.

![B · Créer une demande](manual-assets/fr/annotated/request-create-annotated.png)

1. Type de demande · 2. Département responsable

![B · Mes demandes](manual-assets/fr/annotated/my-requests-annotated.png)

1. Commandes de recherche et filtres · 2. Liste des enregistrements ou lignes de matériel

![B · Brouillon de demande](manual-assets/fr/annotated/request-draft-annotated.png)

1. Titre et actions autorisées · 2. Modifier la demande ouverte

![B · Modifier une demande](manual-assets/fr/annotated/request-edit-annotated.png)

1. Type de demande · 2. Commande de validation : vérifiez la page avant de confirmer

## C. Demandes de matériel des techniciens

Demandez uniquement le matériel nécessaire. Le technicien soumet et suit la demande ; le personnel du stock habilité enregistre ensuite la régularisation et les retours physiques.

Prérequis : Type de demande de matériel et articles actifs disponibles.

1. Sélectionnez le type de demande de matériel. Confirmez le département responsable avant de saisir les lignes.
2. Ajoutez le matériel, la quantité et une note utile. Vérifiez les unités : une longueur de câble ne correspond pas à un nombre de pièces.
3. Vérifiez toutes les lignes puis soumettez, ou enregistrez un brouillon. Un brouillon ne réserve ni ne déduit le stock.
4. Conservez la référence REQ-MAT et suivez les étapes dans le détail. La disponibilité est contrôlée de nouveau à l’approbation finale.

Résultat : des lignes complètes et un circuit après soumission. Corrigez les quantités invalides ; ne créez pas une deuxième demande uniquement parce que la réponse tarde.

![C · Saisie d’une demande de matériel](manual-assets/fr/annotated/material-request-create-annotated.png)

1. Type de demande · 2. Recherchez et sélectionnez le matériel par nom, code ou catégorie

![C · Lignes de matériel et quantités](manual-assets/fr/annotated/material-request-lines-annotated.png)

1. Recherchez et sélectionnez le matériel par nom, code ou catégorie · 2. Quantité demandée dans l’unité du matériel

![C · Approbations en attente](manual-assets/fr/annotated/pending-approvals-annotated.png)

1. Commandes de recherche et filtres · 2. Liste des enregistrements ou lignes de matériel

## D. Classification du stock : écart à résoudre

CONTRÔLE AVANT DIFFUSION : le besoin annoncé autorise la revue du stock à toute étape. Cette version exige encore la PREMIÈRE étape. N’y configurez pas l’exemple avec revue à l’étape 2.

Prérequis : Responsable principal ou suppléant affecté à l’étape courante de revue du stock. Le droit aux rapports ne crée pas cette affectation.

1. Dans Approbations en attente, ouvrez la demande affectée. Vérifiez les quantités, le motif et les justificatifs.
2. Pour une intervention CLIENT, choisissez CLIENT. Aucune succursale Microcom n’est exigée ni conservée.
3. Pour un usage MICROCOM, choisissez MICROCOM et une succursale valide. Ces informations sont obligatoires pour cette approbation.
4. Approuvez après vérification. Une classification manquante bloque l’approbation ; le retour pour correction et le rejet suivent leurs règles habituelles.
5. L’exemple Fiber demandé est : approbation initiale → revue du stock → Direction → Finances. Il s’agit d’un circuit cible, NON d’une configuration vérifiée pour cette version. Faites d’abord clarifier la version par le responsable applicatif.

Résultat : la preuve de classification est conservée. Ne réordonnez pas un circuit en service et n’accordez pas de droits administrateur pour contourner une erreur.

![D · Classification CLIENT — détail des champs](manual-assets/fr/annotated/stock-classification-client-annotated.png)

1. Classification CLIENT / MICROCOM · 2. Choix de succursale pour MICROCOM

![D · Classification MICROCOM — détail des champs](manual-assets/fr/annotated/stock-classification-microcom-annotated.png)

1. Classification CLIENT / MICROCOM · 2. Choix de succursale pour MICROCOM

![D · Configuration du circuit d’approbation](manual-assets/fr/annotated/admin-workflow-annotated.png)

1. Nom enregistré · 2. Étapes d’approbation configurées

## E. Stock central et prix du matériel

Un stock central unique approvisionne les techniciens. Les succursales sont des destinations administratives et de facturation, pas des entrepôts indépendants.

Prérequis : Droits aux rapports de stock ; droits administrateur et permissions de modèle distincts pour gérer le catalogue.

1. Ouvrez Rapports matériels pour examiner les quantités sorties, retournées et encore retournables, ainsi que la cohérence du registre.
2. Dans Django Admin, les administrateurs habilités ouvrent Inventaire → Matériels. Consultez le code, la catégorie, l’unité, le stock et le seuil minimum.
3. À la création d’un matériel tarifé, vérifiez USD ou choisissez CDF/EUR. La modification conserve la devise enregistrée ; aucune conversion automatique n’est effectuée.
4. Laissez un prix inconnu vide : zéro constitue un prix explicite valide. Enregistrez uniquement les modifications autorisées du catalogue.
5. Ne modifiez pas les soldes pour simuler une sortie ou un retour. Utilisez le processus prévu et faites examiner tout historique incohérent.

Résultat : les prix et devises sont choisis explicitement. Le catalogue ne réécrit pas les factures finalisées. Une incohérence historique nécessite une vérification, jamais la suppression de mouvements.

![E · Rapports matériels](manual-assets/fr/annotated/material-reports-annotated.png)

1. Commandes de recherche et filtres · 2. Liste des enregistrements ou lignes de matériel

![E · Catalogue du matériel](manual-assets/fr/annotated/admin-materials-annotated.png)

1. Recherche administrative · 2. Enregistrements autorisés

![E · Prix unitaire et devise — détail des champs](manual-assets/fr/annotated/admin-material-annotated.png)

1. Prix unitaire : vide signifie inconnu · 2. Devise du prix enregistré

## F. Approbations, corrections et déduction du stock

Seul l’approbateur affecté à l’étape courante ou son suppléant autorisé agit. Le statut global et votre propre décision sont deux informations distinctes.

Prérequis : Demande soumise et affectée à l’approbateur connecté.

1. Ouvrez Approbations en attente puis la demande. Lisez les pièces jointes, les quantités et les commentaires précédents.
2. Choisissez Approuver, retourner pour correction ou rejeter selon le cas, avec le commentaire requis. N’approuvez pas des justificatifs incomplets.
3. L’approbation avance à l’étape suivante. À l’approbation finale du matériel, l’application contrôle et déduit le stock une seule fois.
4. Consultez Historique des approbations pour vos décisions et le statut global. Le demandeur corrige une demande retournée puis la soumet de nouveau.
5. En cas d’échec final, transmettez le message et la référence. Ne déduisez pas manuellement le stock et ne multipliez pas les opérations différentes.

Résultat : la demande conserve son historique et une seule sortie par matériel. L’impression, la régularisation et les rapports ne répètent pas cette déduction.

![F · Approbations en attente](manual-assets/fr/annotated/pending-approvals-annotated.png)

1. Commandes de recherche et filtres · 2. Liste des enregistrements ou lignes de matériel

![F · Historique des approbations](manual-assets/fr/annotated/approval-history-annotated.png)

1. Commandes de recherche et filtres · 2. Liste des enregistrements ou lignes de matériel

![F · Demande de matériel approuvée](manual-assets/fr/annotated/approved-request-annotated.png)

1. Titre et actions autorisées · 2. Actions opérationnelles et documentaires

## G. Bon de commande et bon de sortie

Le BC est une commande interne de matériel, pas un achat fournisseur. Le BS documente la sortie autorisée. Les deux utilisent le même modèle, avec des titres et références distincts.

Prérequis : Demande de matériel approuvée, stock déduit et lignes présentes ; accès selon les droits du demandeur, de l’approbateur, du stock ou du superutilisateur.

1. Ouvrez la demande approuvée et choisissez BC ou BS parmi les actions documentaires.
2. À la première émission, vérifiez la référence sur la page de confirmation. Annuler laisse le document non émis ; ouvrir cette page seul n’attribue aucun numéro.
3. Choisissez Confirmer et imprimer uniquement si vous êtes habilité. Cette validation attribue BC/0001/AAAA ou BS/0001/AAAA, avec des compteurs annuels indépendants.
4. Utilisez les commandes d’impression et la boîte de dialogue du navigateur ; l’enregistrement PDF dépend de ses options.
5. Rouvrez le même document pour une réimpression. Sa référence reste stable, sans nouvelle sortie de stock. L’impression groupée des rapports n’alloue aucune référence officielle.

Résultat : au maximum un BC et un BS par demande. Le changement d’année suit Africa/Kinshasa. Ne confondez pas la référence de demande avec celles des documents.

![G · Confirmation de première émission du BC](manual-assets/fr/annotated/bc-confirm-annotated.png)

1. Référence de la demande initiale · 2. Commande de validation : vérifiez la page avant de confirmer

![G · Confirmation de première émission du BS](manual-assets/fr/annotated/bs-confirm-annotated.png)

1. Référence de la demande initiale · 2. Commande de validation : vérifiez la page avant de confirmer

## H. Factures internes

La facture est un document comptable interne émis à la demande pour une demande MICROCOM admissible. Ce n’est ni une vente ni un mouvement de stock. Une intervention CLIENT n’exige pas de facture interne.

Prérequis : Demande MICROCOM approuvée avec preuve de sortie, succursale et adresse, prix compatibles, informations de société attestées et série annuelle INVOICE vérifiée pour finaliser. Permissions explicites et périmètre de revue du stock sont requis.

1. Ouvrez Factures et sélectionnez une demande admissible, ou son action facture autorisée. Choisissez la devise puis créez le brouillon.
2. Vérifiez les descriptions, quantités nettes, devise et prix unitaires. Les prix du catalogue sont copiés si la devise correspond ; les prix inconnus ou incompatibles restent incomplets.
3. Un éditeur habilité peut corriger les prix du brouillon ou actualiser explicitement les quantités. Consultez l’historique ; une actualisation peut ne constater aucun changement.
4. Le brouillon affiche Brouillon n° ID et une somme provisoire seulement si toutes les lignes sont tarifées. Il n’a ni numéro officiel ni total finalisé.
5. Choisissez Finaliser la facture, vérifiez la série et les preuves avant de confirmer. La finalisation fige la succursale, son adresse, la société, les descriptions et les valeurs. Ce guide ne constitue pas une autorisation d’émettre des documents réels.
6. Pour une facture finalisée, choisissez Imprimer la facture. Le PDF dans la langue active s’ouvre dans le lecteur privé avec les commandes d’impression et de téléchargement. Les anciens fichiers restent immuables et contrôlés par empreinte.
7. Pour une impression groupée, renseignez Du et Au selon les dates officielles d’émission, affinez les filtres puis imprimez les factures filtrées. Toutes les pages sont couvertes, uniquement pour les factures finalisées autorisées et dans la limite configurée.

Résultat : le numéro FAC/0001/AAAA est attribué uniquement à la finalisation. Chaque année exige une série financière vérifiée ; ne remettez jamais un compteur à zéro. Après une erreur, rechargez et demandez une vérification sans modifier les protections ni les valeurs figées.

![H · Liste et filtres des factures](manual-assets/fr/annotated/invoices-annotated.png)

1. Filtres des factures et dates officielles · 2. Liste des enregistrements ou lignes de matériel

![H · Brouillon de facture](manual-assets/fr/annotated/invoice-draft-annotated.png)

1. Titre et actions autorisées · 2. Liste des enregistrements ou lignes de matériel

![H · Finalisation de facture — contrôle de configuration](manual-assets/fr/annotated/invoice-finalize-annotated.png)

1. Titre du document ou de la page · 2. Formulaire de confirmation protégé

## I. Avoirs : limite de la fonctionnalité

Le dépôt contient les modèles d’avoirs, allocations, audits de réservation et protections financières. Aucune route utilisateur complète de création, émission ou PDF d’avoir n’existe dans invoicing/urls.py. Les permissions ou Django Admin ne constituent pas ce processus.

Prérequis : Examen du processus pris en charge avec l’administrateur ou la finance ; aucune action autonome documentée.

1. Si un avoir monétaire ou un remboursement est nécessaire, contactez le responsable financier.
2. N’utilisez ni le reçu de retour physique ni le bon de retour de valorisation comme avoir, remboursement ou ajustement de paiement.
3. Ne créez ni ne modifiez manuellement des enregistrements protégés pour contourner le processus absent. Les allocations actives d’avoir excluent la preuve financière de retour pour toute la facture, et réciproquement.

Résultat : une prise en charge par le responsable, sans menu inventé ni contournement financier. Les captures de création d’avoir ne sont pas applicables à cette version.

## J. Gestion du matériel, retours physiques et bons

Utilisez Gestion du matériel et ses trois onglets. La régularisation décrit les usages ; le retour physique réintègre le stock central ; le RCP constate les retours ; le BR lié à une facture valorise les retours admissibles sans modifier le stock ni la facture initiale.

Prérequis : Demande de matériel approuvée et stock déduit ; personnel du stock habilité. Le BR financier exige en plus l’activation, les permissions explicites, le périmètre autorisé, une facture finalisée et des retours postérieurs admissibles.

1. Depuis le détail ou Rapports matériels, ouvrez Gestion du matériel. Vue d’ensemble affiche les quantités sorties, installées CLIENT, utilisées MICROCOM, retournées et conservées pour essais.
2. Dans Régulariser, saisissez les résultats rapportés par le technicien pour chaque matériel. Répartissez les quantités si nécessaire, identifiez le technicien et indiquez le motif. Les quantités retournées proviennent des mouvements réels.
3. Vérifiez puis enregistrez une révision. Classification initiale, approbations, sorties et BC/BS restent inchangés. Consultez l’historique repliable. Une modification périmée impose de recharger et revoir la dernière révision.
4. Réceptionnez et contrôlez physiquement le matériel avant Retours et bons de retour. Saisissez la quantité permise et le motif puis confirmez. Aucun nouveau circuit d’approbation n’est ajouté. Le service protégé restaure le stock une seule fois.
5. Ne dépassez pas le solde retournable. Un article entièrement retourné n’a plus d’action active. Incohérence historique du stock — vérification nécessaire impose l’arrêt et la vérification par le responsable, jamais la suppression de mouvements.
6. Sélectionnez les mouvements RETURN encore non documentés et confirmez Générer le bon de retour pour émettre le reçu RCP NON FINANCIER. Il couvre CLIENT, MICROCOM et les demandes sans facture. La réimpression conserve sa référence sans nouvelle entrée en stock.
7. Utilisez Voir le PDF ou Imprimer sur le reçu. La langue active est utilisée. Un échec PDF n’annule ni le retour ni le reçu : réessayez uniquement le PDF.
8. Pour le BR financier, utilisez l’action de la facture finalisée seulement si elle est activée et autorisée. Sélectionnez des mouvements RETURN complets admissibles, strictement postérieurs à la finalisation ; vérifiez la valorisation figée et le motif avant confirmation.
9. Si le résultat du BR est incertain, réessayez avec la MÊME confirmation conservée et le même jeton d’émission. Un nouvel aperçu ne remplace pas cet essai. Si la session est perdue, vérifiez l’historique et contactez le support.
10. Le BR financier préserve la facture, avec plafonds cumulés, arrondis et exclusivité des avoirs. L’aperçu signé dure deux heures, mais la session conserve son expiration de 15 minutes.

Résultat : des révisions traçables et une réintégration uniquement pour les retours physiques validés. Le BR financier reste désactivé dans cette répétition ; ses captures d’émission, PDF et reprise restent à réaliser.

Exemple représentatif : un CPE initialement demandé pour essais MICROCOM est installé chez le CLIENT ; le câble et l’alimentation inutilisés sont réceptionnés au stock. Enregistrez les retours physiques puis une régularisation des résultats mixtes. La classification initiale MICROCOM reste inchangée. Le processus couvre tous les matériels, pas seulement les CPE.

![J · Gestion du matériel — Vue d’ensemble](manual-assets/fr/annotated/material-overview-annotated.png)

1. Onglet Vue d’ensemble · 2. Quantités sorties et résultats

![J · Éditeur de régularisation du matériel](manual-assets/fr/annotated/material-reconcile-editor-annotated.png)

1. Onglet Régulariser · 2. Éditeur des résultats : dépliez la ligne

![J · Saisie d’un retour physique](manual-assets/fr/annotated/material-return-editor-annotated.png)

1. Onglet Retours et bons de retour · 2. Formulaire de retour physique : réceptionnez d’abord le matériel

## K. Référence administrateur

L’accès administrateur est distinct des permissions opérationnelles et financières. N’accordez pas le statut administrateur uniquement pour permettre une action du stock.

Prérequis : Compte administrateur autorisé et permissions de modèle/action appropriées.

1. Dans Django Admin, gérez les utilisateurs actifs, départements et rôles. Utilisez des identités individuelles et examinez séparément les accès aux rapports du stock et administratifs.
2. Gérez les types et circuits selon le département responsable et les montants. Définissez titulaires, suppléants et ordre unique. Vérifiez le routage avec des données de répétition avant usage.
3. ARRÊT : ce code permet une seule étape de revue du stock et l’exige en premier. Faites clarifier l’écart avec la configuration attendue à toute étape avant de diffuser cette procédure.
4. Gérez le nom, code, activation et adresse des succursales. Une nouvelle succursale exige une adresse ; les anciens enregistrements vides restent compatibles, mais une nouvelle facture MICROCOM exige une adresse valide.
5. Vérifiez les paramètres société/documents puis utilisez l’action d’attestation des informations courantes. Leur modification invalide l’attestation de contenu pour les futures émissions.
6. Vérifiez les séries : type, année, série, format, prochain compteur et justificatifs. Utilisez l’action de vérification prévue ; ne réinitialisez jamais un compteur utilisé. Préparer une année financière ne l’atteste pas automatiquement.
7. Consultez les historiques des demandes, régularisations, reçus et factures. Signalez les erreurs de protection sans modifier les pièces immuables. Créez les demandes dans l’application, jamais par l’ajout Django Admin.

Résultat : permissions et attestations explicites. N’exposez ni chemins privés PDF, liens de réinitialisation, secrets de journaux ni confirmations signées dans les tickets ou captures.

![K · Modules d’administration](manual-assets/fr/annotated/admin-annotated.png)

1. Modules d’administration autorisés · 2. Actions de compte et session

![K · Gestion des utilisateurs](manual-assets/fr/annotated/admin-users-annotated.png)

1. Recherche administrative · 2. Enregistrements autorisés

![K · Liste des circuits d’approbation](manual-assets/fr/annotated/admin-workflows-annotated.png)

1. Liste administrative et actions · 2. Enregistrements autorisés

![K · Configuration du circuit d’approbation](manual-assets/fr/annotated/admin-workflow-annotated.png)

1. Nom enregistré · 2. Étapes d’approbation configurées

![K · Nom et adresse de succursale — détail des champs](manual-assets/fr/annotated/admin-succursale-annotated.png)

1. Nom enregistré · 2. Adresse physique de la succursale

![K · Paramètres de l’entreprise et des documents](manual-assets/fr/annotated/admin-company-annotated.png)

1. Paramètres société, distincts du titre PDF

![K · Fuseau métier et préférence de numérotation](manual-assets/fr/annotated/admin-company-timezone-annotated.png)

1. Fuseau métier Africa/Kinshasa · 2. Préférence de format ; vérification de série distincte

![K · Séries financières vérifiées](manual-assets/fr/annotated/admin-sequences-annotated.png)

1. Liste administrative et actions · 2. Titre du document ou de la page

## L. Rapports, exports et dépannage

Les rapports respectent votre périmètre autorisé. Les filtres réduisent ce périmètre ; ils n’accordent ni accès supplémentaire ni visibilité financière.

Prérequis : Droit aux rapports matériels ou superutilisateur ; permissions/périmètre financiers distincts pour les valeurs. Le rapport administratif possède son propre droit.

1. Renseignez la recherche, le département et les dates proposés. Réinitialiser efface les filtres. Une date invalide produit un message et aucun résultat, pas un rapport non filtré.
2. Vérifiez sorties, retours, soldes et cohérence. Consultez le détail ou l’historique comme preuve ; une incohérence désactive les nouveaux retours.
3. Exportez Excel avec les filtres actifs. Les utilisateurs financièrement habilités obtiennent huit feuilles ; les utilisateurs du stock seuls, sept sans Comptabilité. Les quatre graphiques sont conservés.
4. Consultez Rapport matériel, Tableau de bord, Graphiques, Mouvements de stock, Synthèse par succursale, Synthèse par groupe et Statistiques mensuelles. Comptabilité, si autorisée, utilise uniquement les valeurs finalisées figées.
5. Séparez devises et unités. Un prix historique vide est inconnu, jamais zéro. L’activité CLIENT reste dans les statistiques de stock mais la couverture de facture interne ne s’y applique pas ; les factures MICROCOM sont émises à la demande.
6. Au-delà de la limite configurée, de 10 000 lignes par défaut, réduisez l’export par les filtres. Exporter ne crée ni BC/BS, ni facture, ni mouvement.
7. Pour le support, fournissez référence, heure, action, langue et message sans données sensibles. Ne transmettez ni mots de passe, cookies, jetons de confirmation ni documents confidentiels complets.

Résultat : des rapports localisés en lecture seule. Un accès manquant exige une revue des droits, pas l’utilisation du fichier confidentiel d’un autre employé.

![L · Rapports matériels](manual-assets/fr/annotated/material-reports-annotated.png)

1. Commandes de recherche et filtres · 2. Liste des enregistrements ou lignes de matériel

![L · Filtre de date invalide — message de validation](manual-assets/fr/annotated/material-filter-error-annotated.png)

1. Corrigez la date de début invalide · 2. Erreur de validation : aucun résultat non filtré n’est affiché

![L · Liste et filtres des factures](manual-assets/fr/annotated/invoices-annotated.png)

1. Filtres des factures et dates officielles · 2. Liste des enregistrements ou lignes de matériel

## Dépannage rapide

- Commandes d’approbation absentes : vérifiez l’affectation courante et le statut, pas seulement l’accès aux rapports.
- Prix manquant : complétez le brouillon avec des justificatifs autorisés ; ne remplacez pas un inconnu par zéro.
- Série ou attestation manquante : contactez l’administrateur ; ne modifiez ni compteurs ni protections.
- Échec PDF : revenez au document émis et relancez uniquement la génération, pas l’émission.
- Émission financière incertaine : conservez la même confirmation ; consultez l’historique si la session est perdue.
- Retour historique excessif ou sortie ambiguë : arrêtez les retours et demandez une vérification du registre.

## Glossaire

- Succursale — Destination administrative/de facturation ; pas un entrepôt.
- BC — Bon de commande interne.
- BS — Bon de sortie autorisée.
- FAC — Facture comptable interne finalisée et immuable.
- RCP — Reçu non financier lié aux mouvements physiques RETURN.
- BR — Valorisation de retours liée à une facture ; ni remboursement, ni avoir, ni mouvement de stock.
- Reconciliation / Régularisation — Rapport des résultats réels du matériel, conservé par révisions.
- Africa/Kinshasa — Fuseau métier des références annuelles et rapports opérationnels.
