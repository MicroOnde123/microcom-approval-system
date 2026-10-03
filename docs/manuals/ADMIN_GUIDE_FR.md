# Systeme d'approbation et de workflow Microcom

## Manuel administrateur

**Version du document :** 1.0  
**Public concerne :** administrateurs systeme, administrateurs de departement, responsables de plateforme  
**Langue :** Francais

---

## Table des matieres

1. [Introduction](#1-introduction)
2. [Connexion](#2-connexion)
3. [Gestion des utilisateurs](#3-gestion-des-utilisateurs)
4. [Gestion des workflows](#4-gestion-des-workflows)
5. [Types de demandes](#5-types-de-demandes)
6. [Inventaire et materiels](#6-inventaire-et-materiels)
7. [Departement proprietaire de la demande](#7-departement-proprietaire-de-la-demande)
8. [Demandes brouillons](#8-demandes-brouillons)
9. [Demandes retournees](#9-demandes-retournees)
10. [Annulation des demandes](#10-annulation-des-demandes)
11. [Rapports](#11-rapports)
12. [Administration systeme](#12-administration-systeme)
13. [Depannage](#13-depannage)
14. [Bonnes pratiques](#14-bonnes-pratiques)

---

## 1. Introduction

Le systeme d'approbation et de workflow Microcom est une plateforme web destinee a creer, approuver, suivre, imprimer et analyser les demandes operationnelles. Il prend en charge l'appartenance departementale des demandes, les circuits d'approbation configurables, la gestion du stock de materiels, l'utilisation en anglais et en francais, ainsi qu'un historique d'audit.

### 1.1 Objectif de la plateforme

La plateforme centralise le traitement des demandes afin que chaque demande soit introduite selon un processus standard, orientee vers les bons approbateurs, traitee etape par etape, puis conservee avec son historique.

Les administrateurs utilisent la plateforme pour gerer :

- Les departements et les roles.
- Les utilisateurs et les droits lies aux rapports de stock.
- Les types de demandes et leur comportement.
- Les workflows d'approbation et leurs etapes.
- Le catalogue de materiels, les niveaux de stock et les controles de reporting.

### 1.2 Fonctionnalites principales

- Departements et roles personnalises.
- Profils utilisateurs avec matricule, departement, role et droit de gestion des rapports de stock.
- Types de demandes configurables pour les materiels, paiements, demandes generales et permissions.
- Workflows propres a un departement et workflows globaux de secours.
- Routage selon les montants.
- Etapes d'approbation sequentielles avec approbateur principal et approbateur alternatif.
- Brouillons non transmis a l'approbation tant qu'ils ne sont pas soumis.
- Correction et nouvelle soumission des demandes retournees.
- Annulation des demandes ouvertes.
- Deduction du stock apres approbation finale.
- Enregistrement des retours de materiel en stock.
- Exports CSV et Excel des rapports de materiel.
- Impression des bons de sortie materiel et des documents de permission.
- Prise en charge de l'anglais et du francais.

### 1.3 Vue d'ensemble du workflow d'approbation

Lorsqu'un utilisateur soumet une demande, le systeme selectionne un workflow actif pour le type de demande. Si la demande contient un montant, le workflow doit egalement respecter les limites minimum et maximum configurees.

L'ordre de selection est le suivant :

1. Workflow actif correspondant au type de demande et au champ **Demande pour le departement**.
2. Workflow actif correspondant au type de demande sans departement renseigne. Il s'agit du workflow global de secours.
3. Si aucun workflow ne correspond, la soumission est bloquee et l'administrateur doit configurer un workflow applicable.

Une fois le workflow selectionne, le systeme cree les enregistrements d'approbation pour chaque etape. L'etape courante est affectee a l'utilisateur approbateur configure ou a un utilisateur actif du departement proprietaire possedant le role configure.

> **Note :** Le departement utilise pour le routage est **Demande pour le departement**, et non le departement du demandeur.

**Emplacement capture d'ecran :** Tableau de bord administrateur et menu de navigation.

---

## 2. Connexion

### 2.1 Connexion administrateur

Les administrateurs se connectent via `/login/` avec leur nom d'utilisateur et leur mot de passe. Apres connexion, le tableau de bord s'affiche.

Les administrateurs disposant d'un acces staff peuvent ouvrir l'administration Django via `/admin/`.

**Emplacement capture d'ecran :** Ecran de connexion.

### 2.2 Reinitialisation du mot de passe

Les utilisateurs peuvent demander la reinitialisation du mot de passe depuis la page de connexion. Le systeme utilise le backend email configure pour envoyer les instructions. Les pages de reinitialisation sont disponibles sous `/password-reset/`.

### 2.3 Recommandations de securite

- Accorder l'acces administrateur uniquement aux personnes qui en ont besoin.
- Maintenir des adresses email valides, car la reinitialisation du mot de passe en depend.
- Desactiver les comptes au lieu de les supprimer lorsqu'un utilisateur change de fonction ou quitte l'organisation.
- Revoir regulierement les utilisateurs ayant des droits de gestion de stock.
- Utiliser des mots de passe robustes et eviter les comptes administrateurs partages.
- Garder les secrets d'environnement hors du code source.

> **Avertissement :** Ne jamais utiliser un compte personnel comme compte administrateur partage. L'historique d'audit est rattache a l'utilisateur qui effectue l'action.

---

## 3. Gestion des utilisateurs

La gestion des utilisateurs se fait dans l'interface d'administration.

### 3.1 Departements

Les departements representent les unites organisationnelles, par exemple Administration, Fiber, IT, Finance ou Logistique.

Chaque departement contient :

- **Nom :** libelle lisible du departement.
- **Code :** code court unique.

Les departements servent a l'affectation des utilisateurs, a la propriete des demandes, aux filtres, aux rapports et au routage des approbations.

### 3.2 Roles

Les roles representent les responsabilites d'approbation. Exemples : Responsable de departement, Responsable financier, Responsable stock, Directeur.

Chaque role contient :

- **Nom :** libelle lisible du role.
- **Code :** code court unique.

Une etape de workflow peut router l'approbation vers un utilisateur precis ou vers le premier utilisateur actif du departement proprietaire ayant le role configure.

### 3.3 Utilisateurs

Les utilisateurs disposent des champs de connexion standards et des champs specifiques a Microcom :

- **Nom complet**
- **Matricule**
- **Departement**
- **Role**
- **Peut gerer les rapports de stock**
- **Statut actif**
- **Statut staff** pour l'acces administratif

Le formulaire administrateur exige une adresse email valide.

### 3.4 Creer un departement

1. Ouvrir `/admin/`.
2. Aller dans **Accounts > Departments**.
3. Cliquer sur **Add Department**.
4. Saisir le nom du departement et son code unique.
5. Enregistrer.

**Emplacement capture d'ecran :** Formulaire de creation d'un departement.

### 3.5 Modifier un departement

1. Ouvrir **Accounts > Departments**.
2. Selectionner le departement.
3. Modifier le nom ou le code.
4. Enregistrer.

> **Conseil :** Eviter de modifier les codes de departement en production sans validation interne.

### 3.6 Desactiver un departement

Le modele actuel de departement ne comporte pas de champ actif/inactif. Pour ne plus utiliser un departement :

1. Ne plus l'utiliser dans les nouveaux workflows.
2. Transferer les utilisateurs actifs vers un autre departement ou les desactiver.
3. Conserver l'enregistrement pour preserver l'historique des demandes et des audits.

> **Avertissement :** Ne pas supprimer un departement deja reference par des utilisateurs, workflows ou demandes.

### 3.7 Creer un utilisateur

1. Ouvrir **Accounts > Users**.
2. Cliquer sur **Add User**.
3. Renseigner le nom d'utilisateur, le nom complet, le matricule, l'email, le departement et le role.
4. Accorder les droits staff ou superutilisateur uniquement si necessaire.
5. Cocher **Can Manage Stock Reports** uniquement pour les personnes autorisees a gerer les rapports et les retours de stock.
6. Enregistrer.

### 3.8 Modifier un utilisateur

1. Ouvrir **Accounts > Users**.
2. Rechercher par nom d'utilisateur, nom complet ou email.
3. Mettre a jour le departement, le role, l'email, le statut actif ou le droit de gestion de stock.
4. Enregistrer.

### 3.9 Reinitialiser le mot de passe d'un utilisateur

Utiliser l'une des methodes suivantes :

- Demander a l'utilisateur d'utiliser la page de reinitialisation.
- Utiliser les outils de mot de passe de l'administration Django si disponibles.
- En environnement de developpement avec backend console, recuperer le lien dans la sortie serveur.

### 3.10 Activer ou desactiver un utilisateur

1. Ouvrir le profil dans **Accounts > Users**.
2. Cocher ou decocher **Active**.
3. Enregistrer.

Les utilisateurs inactifs ne sont pas selectionnes par la resolution des approbateurs basee sur les roles.

---

## 4. Gestion des workflows

La gestion se fait via **Workflows > Approval workflows** et **Workflows > Approval workflow steps** dans `/admin/`.

### 4.1 Workflows d'approbation

Un workflow d'approbation definit le processus applicable a une demande.

Champs principaux :

- **Nom**
- **Type de demande**
- **Departement** : optionnel. S'il est vide, le workflow est global.
- **Montant minimum**
- **Montant maximum**
- **Actif**

### 4.2 Etapes d'approbation

Les etapes definissent qui doit agir et dans quel ordre.

Champs principaux :

- **Workflow**
- **Ordre de l'etape**
- **Role approbateur**
- **Utilisateur approbateur**
- **Approbateur alternatif**
- **Obligatoire**

Le systeme traite les etapes par ordre croissant. Un workflow ne peut avoir qu'une seule etape pour un meme ordre.

### 4.3 Affecter les approbateurs

Deux modes sont disponibles :

- **Utilisateur approbateur specifique :** l'etape va toujours a cet utilisateur.
- **Role approbateur :** le systeme choisit un utilisateur actif du departement proprietaire ayant ce role.

Un approbateur alternatif peut egalement etre configure. Il peut approuver, rejeter ou retourner la meme etape en attente.

> **Conseil :** Utiliser les roles pour les workflows departementaux et les utilisateurs specifiques pour les validations exceptionnelles.

### 4.4 Creer un workflow

1. Ouvrir `/admin/`.
2. Aller dans **Workflows > Approval workflows**.
3. Cliquer sur **Add Approval workflow**.
4. Saisir le nom.
5. Selectionner le type de demande.
6. Choisir un departement pour un workflow departemental, ou laisser vide pour un workflow global.
7. Configurer les montants minimum et maximum si necessaire.
8. Garder **Active** coche.
9. Ajouter les etapes en ligne ou les ajouter apres enregistrement.

**Emplacement capture d'ecran :** Workflow avec etapes en ligne.

### 4.5 Creer les etapes d'approbation

1. Ouvrir le workflow.
2. Ajouter l'ordre `1` pour le premier approbateur.
3. Selectionner un role approbateur ou un utilisateur approbateur.
4. Ajouter un approbateur alternatif si necessaire.
5. Ajouter les etapes suivantes avec les ordres `2`, `3`, etc.
6. Enregistrer.

### 4.6 Configurer les workflows departementaux

Un workflow departemental s'applique lorsque **Demande pour le departement** correspond au departement du workflow.

Exemple :

- Type de demande : Demande de materiel
- Departement : Fiber
- Etape 1 : Responsable Fiber
- Etape 2 : Responsable stock

Si Administration soumet une demande de materiel pour Fiber, ce workflow est selectionne car la demande appartient a Fiber.

### 4.7 Configurer les workflows selon le montant

Utiliser les champs de montant minimum et maximum pour definir les plages de validation.

Exemple :

- Demande de paiement, Finance, minimum vide, maximum `999.99` : Responsable financier.
- Demande de paiement, Finance, minimum `1000.00`, maximum vide : Responsable financier puis Directeur.

Pour une demande avec montant, le workflow choisi doit correspondre a la plage configuree.

### 4.8 Configurer les workflows globaux de secours

Un workflow global n'a pas de departement. Il s'applique uniquement lorsqu'aucun workflow departemental ne correspond au type, au montant et au departement proprietaire.

> **Avertissement :** Un workflow global ne doit pas remplacer les workflows departementaux lorsque la propriete departementale est importante.

### 4.9 Exemples

**Exemple 1 : Administration soumet pour Fiber**

1. Departement du demandeur : Administration.
2. Demande pour le departement : Fiber.
3. Type : Demande de materiel.
4. Le systeme recherche un workflow actif de demande de materiel pour Fiber.
5. Les roles approbateurs sont resolus parmi les utilisateurs actifs de Fiber.

**Exemple 2 : Administration soumet pour IT**

1. Departement du demandeur : Administration.
2. Demande pour le departement : IT.
3. Type : Demande generale.
4. Le systeme recherche un workflow actif pour IT.
5. A defaut, il utilise le workflow global correspondant.

---

## 5. Types de demandes

Les types de demandes sont geres dans **Requests app > Request types**.

### 5.1 Champs d'un type de demande

- **Nom**
- **Code**
- **Description**
- **Actif**
- **Est une demande de permission**
- **Requiert des materiels**
- **Requiert un montant**

### 5.2 Demandes de materiel

Les demandes de materiel doivent avoir **Requires materials** active. L'utilisateur selectionne les materiels et quantites. Apres approbation finale, le stock est deduit et des mouvements de stock sont crees.

### 5.3 Demandes generales

Les demandes generales exigent normalement une description. Elles ne demandent pas de materiels sauf si le type est configure pour cela.

### 5.4 Demandes de paiement

Les demandes de paiement doivent generalement avoir **Requires amount** active afin de rendre le montant obligatoire et d'utiliser le routage selon le montant.

### 5.5 Demandes de permission et de sortie

Les types de permission doivent avoir **Is permission request** active. Cela affiche les champs supplementaires pour les permissions de sortie et les autorisations de site.

Groupes de permission :

- Permission de sortie.
- Autorisation de site.

> **Note :** Le comportement depend de champs explicites, pas du nom affiche du type de demande.

---

## 6. Inventaire et materiels

L'inventaire est gere via **Inventory > Material categories**, **Inventory > Materials** et les rapports de materiel.

### 6.1 Catalogue de materiels

Un materiel comprend :

- Categorie.
- Nom.
- Code.
- Description.
- Unite.
- Statut actif.
- Quantite en stock.
- Niveau de stock minimum.

### 6.2 Stock de materiel

La quantite en stock est conservee sur chaque materiel. Le systeme verifie que la quantite demandee ne depasse pas le stock disponible.

Apres approbation finale d'une demande de materiel, le systeme deduit le stock et cree un mouvement **Stock Out**.

### 6.3 Ajouter un materiel

1. Ouvrir `/admin/`.
2. Aller dans **Inventory > Materials**.
3. Cliquer sur **Add Material**.
4. Choisir une categorie.
5. Saisir le nom, le code, l'unite, la quantite et le niveau minimum.
6. Garder **Active** coche si le materiel doit etre disponible.
7. Enregistrer.

### 6.4 Modifier un materiel

1. Ouvrir **Inventory > Materials**.
2. Rechercher par nom ou code.
3. Modifier les champs necessaires.
4. Enregistrer.

### 6.5 Mettre a jour le stock

Les administrateurs peuvent ajuster la quantite sur la fiche materiel. Les sorties liees aux demandes approuvees creent automatiquement des mouvements de stock.

### 6.6 Consulter l'historique de stock

Les mouvements de stock sont disponibles sous **Requests app > Stock movements**. Ils affichent le materiel, le type de mouvement, la quantite, la demande associee, l'utilisateur et la date.

### 6.7 Rapports de materiel

L'ecran `/materials/reports/` permet aux utilisateurs autorises de filtrer, exporter, imprimer les documents de materiel, mettre a jour les notes de sortie et retourner des materiels en stock lorsque c'est applicable.

**Emplacement capture d'ecran :** Rapport de materiel avec filtres et boutons d'export.

---

## 7. Departement proprietaire de la demande

La propriete departementale est un element central du routage Microcom.

### 7.1 Departement d'origine

Le departement d'origine est le departement du demandeur. Il indique d'ou provient la demande.

### 7.2 Demande pour le departement

**Demande pour le departement** est le departement proprietaire de la demande. Il controle :

- La selection du workflow.
- La recherche des approbateurs par role.
- Les filtres departementaux.
- Les informations imprimees et exportees.

Par defaut, la demande est affectee au departement du demandeur. Si l'utilisateur soumet pour un autre departement, il doit selectionner le bon departement.

### 7.3 Exemple : Administration soumet pour Fiber

Le systeme conserve Administration comme departement d'origine, affecte Fiber comme departement proprietaire, recherche un workflow Fiber et choisit les approbateurs actifs de Fiber.

### 7.4 Exemple : Administration soumet pour IT

Le systeme conserve Administration comme departement d'origine, route vers le workflow IT s'il existe, puis utilise le workflow global uniquement en l'absence de workflow IT applicable.

> **Avertissement :** Ne pas baser le routage sur le departement du demandeur lorsque le processus depend du departement proprietaire.

---

## 8. Demandes brouillons

### 8.1 Definition

Un brouillon est une demande enregistree avant soumission. Il est utile lorsque les informations ne sont pas encore completes.

### 8.2 Cycle de vie

1. L'utilisateur cree une demande.
2. Il choisit **Save as Draft**.
3. La demande est enregistree avec le statut **Draft**.
4. Aucune etape d'approbation n'est creee.
5. L'utilisateur modifie le brouillon plus tard.
6. Il soumet la demande quand elle est prete.

### 8.3 Visibilite

Les brouillons apparaissent dans la liste des demandes du demandeur. Ils n'apparaissent pas dans les approbations en attente.

### 8.4 Limites

- Aucun approbateur n'est notifie.
- Aucun stock n'est reserve.
- Aucun stock n'est deduit.
- Le brouillon peut etre annule.

> **Avertissement :** Un brouillon n'est pas une demande active d'approbation.

---

## 9. Demandes retournees

### 9.1 Retour d'une demande

Un approbateur peut retourner une demande pour correction. La demande passe au statut **Returned** et le chemin d'approbation courant est interrompu.

### 9.2 Correction

Le demandeur peut modifier la description, le montant, les materiels, les pieces jointes ou les autres informations selon le type de demande.

### 9.3 Nouvelle soumission

Lors de la nouvelle soumission :

1. Les anciens enregistrements d'approbation sont supprimes.
2. Le statut revient au traitement de soumission.
3. Le systeme selectionne a nouveau le workflow applicable.
4. De nouvelles etapes d'approbation sont creees.

> **Note :** La modification du type, du montant ou du departement proprietaire peut changer le routage.

---

## 10. Annulation des demandes

### 10.1 Cas autorises

Le demandeur peut annuler une demande aux statuts suivants :

- Draft.
- Returned.
- Pending.
- In Review.

### 10.2 Cas bloques

L'annulation est bloquee lorsque la demande est :

- Approuvee.
- Rejetee.
- Deja annulee.

### 10.3 Effets

Lorsqu'une demande est annulee :

- Le statut devient **Cancelled**.
- Le traitement d'approbation s'arrete.
- L'action est inscrite dans l'audit.
- Les approbateurs ne peuvent plus finaliser l'etape.

---

## 11. Rapports

### 11.1 Rapports de materiel

Les rapports de materiel sont disponibles via `/materials/reports/`. Ils incluent les demandes de materiel approuvees, les materiels, les quantites, le departement d'origine, le departement proprietaire et les notes de sortie.

### 11.2 Listes de demandes

Le suivi operationnel se fait via :

- **My Requests** : `/requests/`.
- **Pending Approvals** : `/approvals/pending/`.
- **Approval History** : `/approvals/history/`.

### 11.3 Filtrage par departement

Les filtres utilisent **Demande pour le departement**, afin de respecter la propriete de la demande.

### 11.4 Export CSV

L'export CSV est disponible depuis le rapport de materiel et conserve les filtres actifs.

### 11.5 Export Excel

L'export Excel est disponible depuis le rapport de materiel. Les libelles sont localises selon la langue active.

### 11.6 Documents imprimables

Le systeme prend en charge :

- **Bon de Sortie** pour les demandes de materiel approuvees.
- Document de permission pour les demandes de permission.
- Impression en lot depuis les rapports de materiel.

**Emplacement capture d'ecran :** Apercu d'impression du Bon de Sortie.

---

## 12. Administration systeme

### 12.1 Variables d'environnement

Les principaux reglages utilisent des variables d'environnement :

- `SECRET_KEY`
- `DEBUG`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USE_TLS`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`
- `SHOW_DRC_MATCH_BANNER`

### 12.2 Bannieres

`SHOW_DRC_MATCH_BANNER` controle l'affichage de la banniere du tableau de bord.

### 12.3 Langues

Le systeme prend en charge l'anglais et le francais. Le changement de langue utilise l'internationalisation Django et le cookie `django_language`.

### 12.4 Fichiers statiques

Les fichiers statiques sont geres par la configuration Django et WhiteNoise. En production, ils doivent etre collectes dans `STATIC_ROOT`.

### 12.5 Sessions

La duree de session et l'expiration a la fermeture du navigateur sont configurees. Les parametres de cookies doivent etre revus avant un deploiement HTTPS.

---

## 13. Depannage

### 13.1 Un utilisateur ne peut pas se connecter

Verifier que le compte est actif, que le nom d'utilisateur et le mot de passe sont corrects, et que l'utilisateur accede a la bonne URL.

### 13.2 Probleme de reinitialisation du mot de passe

Verifier l'adresse email, le backend email, le domaine du lien de reinitialisation et la configuration du serveur mail.

### 13.3 Demande bloquee en approbation

Verifier le statut, l'ordre d'etape courant, l'approbation en attente, l'approbateur principal, l'approbateur alternatif et l'etat actif des utilisateurs.

### 13.4 Mauvais approbateur affecte

Verifier **Demande pour le departement**, le workflow selectionne, les limites de montant, la configuration de l'etape et le role des utilisateurs dans le departement proprietaire.

### 13.5 Ecart de stock

Verifier la quantite en stock, les mouvements de stock, le statut de la demande, l'indicateur de deduction et les retours en stock.

### 13.6 Export indisponible

Verifier les droits de gestion de stock, les filtres du rapport, les restrictions du navigateur et les journaux serveur.

### 13.7 Aucun workflow applicable

Verifier que le type de demande possede un workflow actif, que le departement proprietaire est couvert, qu'un workflow global existe si necessaire, et que la plage de montant inclut la demande.

---

## 14. Bonnes pratiques

- Utiliser des workflows departementaux pour les processus propres a un departement.
- Maintenir des workflows globaux de secours lorsque c'est pertinent.
- Configurer les types de demandes avec des indicateurs explicites.
- Maintenir au moins un utilisateur actif par role et par departement utilise dans les workflows.
- Configurer des approbateurs alternatifs pour les etapes critiques.
- Revoir regulierement les quantites en stock et les seuils minimums.
- Desactiver les utilisateurs au lieu de les supprimer.
- Tester le routage apres toute modification de departement, role, type de demande ou plage de montant.
- Utiliser le retour pour correction et l'annulation pour arreter une demande.


## Rapport Administration
Les employés autorisés peuvent rechercher, consulter et imprimer toutes les demandes d'Autorisation Générale entièrement approuvées, quels que soient le département demandeur et le département concerné. Dans Django Admin > Accounts > Users, activer **Peut consulter les rapports Administration** (`can_view_administration_reports`) pour chaque employé sélectionné. Ce champ utilisateur suit le mécanisme du Rapport de Stock ; les permissions de groupe ne l'activent pas. Les superutilisateurs ont aussi accès.

Rechercher par numéro, nom ou identifiant du demandeur, ou description. Filtrer par département demandeur, département concerné, demandeur et dates de soumission. Les filtres sont conservés dans la pagination ; les deux filtres de département sont facultatifs et limitent uniquement le registre des autorisations générales approuvées. Cliquer sur **Voir le document** ou **Imprimer**, puis utiliser l'impression/enregistrement PDF et les commandes d'un ou deux exemplaires du document existant.

Ce droit donne uniquement accès au rapport et à ses documents approuvés. Il ne permet pas de consulter la page normale de détail, modifier ou approuver une demande. Les brouillons, autres statuts et autres types de demande (dont MATERIAL) sont exclus. La date d'approbation utilise `finalized_at` lorsqu'elle existe.

Déploiement : appliquer la migration accounts `0003_user_can_view_administration_reports`. Configurer `ADMINISTRATION_REPORT_REQUEST_TYPE_CODE` (défaut `AUTORISATION_GENERAL`) dans l'environnement. Le registre inclut les demandes selon leur statut approuvé et ce code de type uniquement. Il n'y a aucune restriction de département ni configuration de code de département. Aucune donnée existante n'est modifiée.
