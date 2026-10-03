# Systeme d'approbation et de workflow Microcom

## Manuel utilisateur

**Version du document :** 1.0  
**Public concerne :** employes et approbateurs  
**Langue :** Francais

---

## Table des matieres

1. [Introduction](#1-introduction)
2. [Connexion](#2-connexion)
3. [Tableau de bord](#3-tableau-de-bord)
4. [Creation des demandes](#4-creation-des-demandes)
5. [Demande pour le departement](#5-demande-pour-le-departement)
6. [Demandes brouillons](#6-demandes-brouillons)
7. [Modification des demandes retournees](#7-modification-des-demandes-retournees)
8. [Annulation des demandes](#8-annulation-des-demandes)
9. [Processus d'approbation](#9-processus-dapprobation)
10. [Suivi des demandes](#10-suivi-des-demandes)
11. [Documents de materiel](#11-documents-de-materiel)
12. [Questions frequentes](#12-questions-frequentes)
13. [Bonnes pratiques](#13-bonnes-pratiques)

---

## 1. Introduction

Le systeme d'approbation et de workflow Microcom permet de soumettre, approuver, suivre, imprimer et analyser les demandes de l'entreprise. Il aide les employes a transmettre leurs demandes au bon departement et permet aux approbateurs de les traiter selon un circuit controle.

### 1.1 A quoi sert le systeme

Vous pouvez utiliser le systeme pour :

- Creer des demandes.
- Enregistrer une demande incomplete comme brouillon.
- Soumettre une demande a l'approbation.
- Suivre l'etat d'une demande.
- Corriger et resoumettre une demande retournee.
- Annuler une demande encore ouverte.
- Approuver, rejeter ou retourner une demande si vous etes approbateur.
- Imprimer les documents de materiel ou de permission lorsqu'ils sont disponibles.

### 1.2 Types de demandes

Le systeme prend en charge plusieurs types de demandes :

- Demandes de materiel.
- Demandes generales.
- Demandes de paiement.
- Demandes de permission ou de sortie.

Les champs du formulaire peuvent changer selon le type de demande selectionne.

**Emplacement capture d'ecran :** Tableau de bord apres connexion.

---

## 2. Connexion

### 2.1 Se connecter

1. Ouvrir le systeme Microcom dans le navigateur.
2. Saisir le nom d'utilisateur et le mot de passe.
3. Cliquer sur **Login**.

Apres connexion, le tableau de bord s'affiche.

**Emplacement capture d'ecran :** Page de connexion.

### 2.2 Reinitialiser le mot de passe

Si vous oubliez votre mot de passe :

1. Ouvrir la page de connexion.
2. Cliquer sur le lien de reinitialisation.
3. Saisir l'adresse email liee au compte.
4. Suivre les instructions recues par email.

> **Note :** Si aucun email n'arrive, contactez l'administrateur pour verifier l'adresse email de votre compte.

### 2.3 Changer de langue

Le systeme prend en charge l'anglais et le francais. Utilisez le selecteur de langue dans la navigation.

---

## 3. Tableau de bord

Le tableau de bord est la premiere page apres connexion.

### 3.1 Widgets

Selon vos droits, le tableau de bord peut afficher des informations sur vos demandes, les approbations en attente, les demandes retournees et les raccourcis utiles.

### 3.2 Menu de navigation

Les entrees courantes sont :

- **Dashboard**
- **Create Request**
- **My Requests**
- **Pending Approvals**
- **Approval History**
- **Material Reports** pour les utilisateurs autorises

### 3.3 Notifications

Le systeme affiche des indicateurs pour les approbations en attente et les demandes retournees. Les approbateurs doivent consulter regulierement les approbations en attente.

**Emplacement capture d'ecran :** Menu de navigation et indicateur de notification.

---

## 4. Creation des demandes

Ouvrir **Create Request** pour commencer une demande.

### 4.1 Champs communs

La plupart des formulaires comprennent :

- **Request Type :** type de demande.
- **Request For Department :** departement proprietaire de la demande.
- **Description :** explication du besoin.
- **Amount :** montant, requis uniquement pour certains types.
- **Date Needed :** date a laquelle la demande est necessaire.
- **Attachments :** pieces justificatives.

### 4.2 Demande de materiel

Pour une demande de materiel, ajouter chaque materiel requis :

- Materiel.
- Quantite.
- Note de ligne si necessaire.

Le systeme verifie le stock disponible. Vous ne pouvez pas demander une quantite superieure au stock disponible.

> **Conseil :** Utilisez la note pour les numeros de serie, lieux, details d'installation ou autres informations utiles.

### 4.3 Demande generale

1. Selectionner le type de demande generale.
2. Choisir le bon departement dans **Request For Department**.
3. Rediger une description claire.
4. Ajouter des pieces jointes si necessaire.
5. Soumettre ou enregistrer comme brouillon.

### 4.4 Demande de paiement

1. Selectionner le type de demande de paiement.
2. Saisir le montant si le champ est requis.
3. Decrire le motif du paiement.
4. Joindre les justificatifs si necessaire.
5. Soumettre pour approbation.

Les demandes avec montant eleve peuvent etre orientees vers des approbateurs supplementaires.

### 4.5 Permission ou sortie

Pour une demande de permission, des champs supplementaires apparaissent.

Une permission de sortie peut inclure :

- Type de permission.
- Destination.
- Motif.
- Heure de depart.
- Heure de retour.
- Heure d'arrivee.
- Nom du chauffeur.

Une autorisation de site peut inclure :

- Site.
- Valable du.
- Valable jusqu'au.
- Agents Microcom.
- TT.
- Personnes externes.
- Motif.

> **Note :** Les heures de depart et de retour peuvent etre optionnelles pour certaines permissions de sortie.

### 4.6 Soumettre la demande

Lorsque la demande est complete :

1. Verifier le type de demande et **Request For Department**.
2. Verifier la description, le montant, les materiels et les pieces jointes.
3. Cliquer sur **Submit Request**.

La demande est envoyee au premier approbateur du workflow applicable.

---

## 5. Demande pour le departement

### 5.1 Definition

Par defaut, la demande est affectee a votre departement. Si vous soumettez une demande pour le compte d'un autre departement, selectionnez le departement approprie.

Ce champ controle le departement proprietaire de la demande et le workflow d'approbation utilise.

### 5.2 Exemples

**Exemple 1 : demande pour votre propre departement**

Si vous travaillez dans Administration et que la demande concerne Administration, laissez **Request For Department** sur Administration.

**Exemple 2 : demande pour Fiber**

Si vous travaillez dans Administration mais creez une demande pour Fiber, selectionnez Fiber dans **Request For Department**.

**Exemple 3 : demande pour IT**

Si vous travaillez dans Administration mais creez une demande pour IT, selectionnez IT dans **Request For Department**.

> **Avertissement :** Un mauvais departement peut envoyer la demande vers le mauvais workflow.

**Emplacement capture d'ecran :** Champ Request For Department dans le formulaire.

---

## 6. Demandes brouillons

### 6.1 Enregistrer comme brouillon

Utilisez **Save as Draft** lorsque la demande est incomplete ou doit etre terminee plus tard.

### 6.2 Modifier un brouillon

Les brouillons apparaissent dans **My Requests**. Ouvrez le brouillon et cliquez sur **Edit Draft** pour continuer.

### 6.3 Soumettre plus tard

Lorsque le brouillon est complet, soumettez-le depuis l'ecran de modification.

> **Avertissement :** Les brouillons ne sont PAS envoyes a l'approbation. Les approbateurs ne les voient pas tant qu'ils ne sont pas soumis.

### 6.4 Limites

- Aucun circuit d'approbation n'est cree.
- Aucun stock n'est reserve.
- Aucun stock n'est deduit.
- Un brouillon peut etre annule.

---

## 7. Modification des demandes retournees

### 7.1 Processus de retour

Un approbateur peut retourner une demande lorsque des informations sont manquantes ou doivent etre corrigees. Le statut devient **Returned**.

Le commentaire de l'approbateur indique la correction attendue.

### 7.2 Modifier les materiels

Pour une demande de materiel retournee, vous pouvez :

- Changer le materiel.
- Changer la quantite.
- Modifier la note.

### 7.3 Retirer des materiels

Supprimez la ligne de materiel ou utilisez l'option de suppression si elle est affichee.

### 7.4 Ajouter des materiels de remplacement

Ajoutez une nouvelle ligne, selectionnez le materiel, saisissez la quantite et enregistrez ou resoumettez.

### 7.5 Resoumettre

Apres correction :

1. Relire tous les champs.
2. Confirmer **Request For Department**.
3. Soumettre a nouveau.

Le systeme cree un nouveau chemin d'approbation pour la demande corrigee.

> **Conseil :** Repondez directement au commentaire de l'approbateur avant de resoumettre.

---

## 8. Annulation des demandes

### 8.1 Quand l'annulation est disponible

Vous pouvez annuler votre propre demande tant qu'elle est ouverte :

- Draft.
- Returned.
- Pending.
- In Review.

### 8.2 Quand l'annulation est indisponible

Vous ne pouvez pas annuler une demande deja :

- Approuvee.
- Rejetee.
- Annulee.

### 8.3 Comment annuler

1. Ouvrir **My Requests**.
2. Ouvrir le detail de la demande.
3. Cliquer sur l'action d'annulation si elle est disponible.
4. Confirmer.

> **Avertissement :** Annulez seulement une demande qui ne doit plus continuer. Si elle doit simplement etre corrigee, utilisez le processus de retour.

---

## 9. Processus d'approbation

### 9.1 Approbation en attente

Une demande est en attente ou en cours d'examen lorsqu'elle attend un ou plusieurs approbateurs.

Les approbateurs ouvrent **Pending Approvals** pour consulter les demandes qui leur sont assignees comme approbateur principal ou alternatif.

### 9.2 Actions de l'approbateur

Un approbateur peut :

- **Approve :** passer a l'etape suivante ou approuver definitivement.
- **Return :** renvoyer la demande au demandeur pour correction.
- **Reject :** cloturer la demande comme rejetee.

### 9.3 Signification des statuts

- **Draft :** enregistre mais non soumis.
- **Pending / In Review :** soumis et en attente d'approbation.
- **Returned :** renvoye pour correction.
- **Approved :** completement approuve.
- **Rejected :** rejete par un approbateur.
- **Cancelled :** arrete par le demandeur avant finalisation.

### 9.4 Approbation finale

Lorsque la derniere etape est approuvee, la demande devient **Approved**. Pour les demandes de materiel, le stock est deduit apres l'approbation finale.

---

## 10. Suivi des demandes

### 10.1 Mes demandes

Utilisez **My Requests** pour voir les demandes que vous avez soumises. Vous pouvez filtrer par statut et par **Request For Department**.

### 10.2 Detail d'une demande

La page detail affiche :

- Numero de demande.
- Type de demande.
- Departement d'origine.
- Request For Department.
- Statut.
- Description.
- Montant et date souhaitee.
- Materiels.
- Pieces jointes.
- Etapes d'approbation.
- Historique d'audit.

### 10.3 Historique

Les approbateurs peuvent utiliser **Approval History** pour revoir les demandes sur lesquelles ils ont agi ou qui leur etaient assignees. Les filtres de departement utilisent **Request For Department**.

**Emplacement capture d'ecran :** Detail d'une demande avec historique.

---

## 11. Documents de materiel

### 11.1 Bon de Sortie

Les demandes de materiel approuvees peuvent generer un **Bon de Sortie**. Ce document accompagne la sortie du materiel, les signatures et l'archivage.

### 11.2 Impression

Utilisez l'action d'impression sur le document approuve ou l'impression en lot dans les rapports de materiel si elle est disponible.

### 11.3 Signatures

Les documents imprimes peuvent contenir des zones de signature. Suivez la procedure interne pour les signatures.

### 11.4 Archivage

Conservez les documents imprimes selon les procedures internes. Les notes de sortie peuvent contenir les numeros de serie, remarques de livraison, details d'installation ou autres informations.

---

## 12. Questions frequentes

### 12.1 Pourquoi ma demande n'est-elle pas encore approuvee ?

Elle attend probablement l'approbateur courant. Ouvrez le detail de la demande pour consulter les etapes et le statut.

### 12.2 Qu'est-ce qu'un brouillon ?

Un brouillon est une demande enregistree mais non soumise a l'approbation.

### 12.3 Pourquoi ma demande a-t-elle ete retournee ?

Un approbateur a demande des corrections ou des informations supplementaires. Lisez son commentaire, modifiez la demande et resoumettez-la.

### 12.4 Puis-je modifier une demande approuvee ?

Non. Une demande approuvee est finale. Contactez un administrateur si une correction documentaire est necessaire.

### 12.5 Puis-je annuler ma demande ?

Vous pouvez annuler votre demande tant qu'elle est ouverte. Vous ne pouvez pas l'annuler apres approbation ou rejet.

### 12.6 Comment soumettre pour un autre departement ?

Selectionnez le bon departement dans **Request For Department** avant de soumettre.

### 12.7 Pourquoi ne vois-je pas les rapports de materiel ?

Les rapports de materiel sont reserves aux utilisateurs ayant le droit de gestion de stock.

---

## 13. Bonnes pratiques

- Choisir le bon type de demande.
- Verifier **Request For Department** avant soumission.
- Fournir une description claire et complete.
- Ajouter les pieces jointes utiles.
- Enregistrer comme brouillon si les informations sont incompletes.
- Lire attentivement les commentaires des demandes retournees.
- Ne demander que les quantites de materiel necessaires.
- Consulter regulierement **Pending Approvals** si vous etes approbateur.
- Ajouter un commentaire utile lors de l'approbation, du retour ou du rejet.
- Imprimer et classer les documents de materiel selon les procedures internes.

