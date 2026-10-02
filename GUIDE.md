# Guide de démarrage pas à pas

Ce guide part de zéro et va jusqu'au classeur collaboratif rempli, avec les
formulaires intégrés. Comptez 20 à 30 minutes la première fois.

- [0. Aperçu](#0-aperçu)
- [1. Prérequis](#1-prérequis)
- [2. Installer l'outil](#2-installer-loutil)
- [3. Créer le compte de service et sa clé](#3-créer-le-compte-de-service-et-sa-clé)
- [4. Activer les API Google](#4-activer-les-api-google)
- [5. Créer le classeur et le partager](#5-créer-le-classeur-et-le-partager)
- [6. Configurer l'outil](#6-configurer-loutil)
- [7. Premier export](#7-premier-export)
- [8. Vérifier le classeur](#8-vérifier-le-classeur)
- [9. Formulaires dans le classeur](#9-formulaires-dans-le-classeur)
- [10. Travailler à plusieurs](#10-travailler-à-plusieurs)
- [11. Boucle retour vers le dépôt](#11-boucle-retour-vers-le-dépôt)
- [12. Notifications et revue PDF](#12-notifications-et-revue-pdf)
- [13. Intégrations (GSD, gstack, Matt Pocock)](#13-intégrations-gsd-gstack-matt-pocock)
- [14. Dépannage](#14-dépannage)
- [Annexe : référence des commandes](#annexe--référence-des-commandes)

## 0. Aperçu

À la fin, vous aurez :

1. un **classeur Google** rempli depuis un dépôt (récits métier, tickets, plans,
   specs, décisions, demandes, tableau de bord) ;
2. des **formulaires intégrés** au classeur (menu) pour saisir depuis le métier ;
3. une **boucle retour** qui ramène les décisions vers le dépôt et des relances.

Le dépôt analysé et le classeur sont **configurables** : rien n'est en dur.

## 1. Prérequis

- Python 3.11 ou plus récent (`python3 --version`).
- Un **compte Google** (le vôtre) pour créer le compte de service et le classeur.
- Node.js 18+ (facultatif, seulement pour déployer les formulaires Apps Script).
- `git` (l'avancement des tickets est déduit des commits du dépôt analysé).

## 2. Installer l'outil

```bash
git clone https://github.com/maebaconsulting/TicketsGoogleSheet.git
cd TicketsGoogleSheet
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Sur Windows, remplacez `.venv/bin/python` par `.venv\Scripts\python`.

## 3. Créer le compte de service et sa clé

Le compte de service est l'identité robot qui écrit dans le classeur.

1. Ouvrez <https://console.cloud.google.com> et **créez un projet** (ou prenez-en un).
2. Menu **IAM et administration > Comptes de service > Créer un compte de service**.
   - Nom : `export-tickets`. Aucun rôle IAM n'est nécessaire.
3. Ouvrez le compte créé, onglet **Clés > Ajouter une clé > Créer une clé > JSON**.
   Le fichier se télécharge : c'est votre clé.
4. Déposez la clé dans le dossier de l'outil sous le nom `key.json`, ou gardez-la
   ailleurs et notez son chemin absolu.
5. Notez l'**e-mail du compte de service** :
   `export-tickets@<projet>.iam.gserviceaccount.com`.

Ne committez jamais `key.json` : il est déjà ignoré par `.gitignore`.

## 4. Activer les API Google

Dans le même projet Google Cloud, menu **API et services > Bibliothèque** :

- activez **Google Sheets API** ;
- activez **Google Drive API** ;
- activez **Google Apps Script API** (nécessaire pour les formulaires de l'étape 9).

Sans cela, la première exécution s'arrête avec une erreur `403 SERVICE_DISABLED`,
qui affiche le lien d'activation exact.

## 5. Créer le classeur et le partager

1. Ouvrez <https://sheets.new>, renommez le classeur `export-tickets`.
2. Copiez son **identifiant** dans l'URL :
   `docs.google.com/spreadsheets/d/<IDENTIFIANT>/edit`.
3. Bouton **Partager**, ajoutez l'e-mail du compte de service en **Éditeur**.
   (Astuce : créez le classeur à la main puis partagez-le ; un compte de service
   n'a pas de quota de stockage Drive.)

## 6. Configurer l'outil

Deux façons. La plus simple détecte la convention du dépôt :

```bash
.venv/bin/python new_project.py \
  --source ../mon-projet \
  --sheet <IDENTIFIANT> \
  --credentials key.json \
  --product "Mon Backlog"
```

`new_project.py` détecte la convention (`.planning`, `.scratch`,
`docs/superpowers`, sinon `agent`) et écrit `config.json`.

Sinon, copiez l'exemple et éditez-le :

```bash
cp config.example.json config.json
```

`config.json` (ignoré par git) :

| Clé | Rôle |
|---|---|
| `source_repo` | dépôt analysé (chemin absolu ou relatif à l'outil) |
| `convention` | `plans`, `gsd`, `tickets` ou `agent` |
| `plans_dir` / `specs_dir` | dossiers des plans et specs dans le dépôt analysé |
| `main_branch` | branche principale (défaut `main`) |
| `github_repo` / `gitlab_project` | dépôts cibles des exports d'issues |
| `spreadsheet_id` | identifiant du classeur (laisser vide : découverte par nom) |
| `sheet_name` | nom du classeur à découvrir (défaut `export-tickets`) |
| `credentials` | chemin de la clé du compte de service |
| `product_name` | nom affiché dans les formulaires |

Priorité : variables d'environnement > `config.json` > défauts.

## 7. Premier export

```bash
.venv/bin/python parser.py     # lit le dépôt et écrit out/
.venv/bin/python sheets.py     # remplit et habille le classeur
```

Sortie attendue de `parser.py`, par exemple :

```
Plans           : 16
Tickets         : 167
Récits métier   : 93
Statuts         : {'fait': 157, 'remplacé': 10}
Sortie          : .../out
```

`sheets.py` affiche l'URL du classeur et le nombre de lignes par onglet.

## 8. Vérifier le classeur

Ouvrez le classeur : les onglets `Accueil`, `Récits métier`, `Décisions`,
`Demandes`, `Tickets`, `Plans`, `Specs`, `Référentiels`, `Tableau de bord` sont
créés et remplis. Les colonnes éditables des récits sont en jaune ; les autres
sont protégées.

## 9. Formulaires dans le classeur

Les formulaires sont des **Apps Script liés au classeur**. L'API Apps Script
**n'accepte pas les comptes de service** : il faut un compte utilisateur.

1. Activez le réglage : <https://script.google.com/home/usersettings>
   (interrupteur « Google Apps Script API » sur **Activé**).
2. Authentifiez `clasp` une fois :
   ```bash
   npx @google/clasp login
   ```
3. Déployez le script lié au classeur :
   ```bash
   .venv/bin/python bind_apps_script_user.py
   ```
   Le script est créé sur le bon classeur et les fichiers sont poussés.
4. Rechargez la page du classeur : le menu **lama** (ou le nom de votre `product_name`)
   apparaît. Au premier usage, autorisez le script.

Variante manuelle, si vous préférez : classeur > **Extensions > Apps Script**,
collez `apps-script/Code.gs` et `apps-script/Formulaire.html`, enregistrez.

## 10. Travailler à plusieurs

Dans l'onglet **Récits métier**, le métier renseigne les colonnes H à Q :
Priorité, Statut métier, Décision, Porteur, Relecteur, Validateur, Échéance,
Commentaire, Valeur, Effort. Le Score et l'alerte « en retard » sont calculés.

- **Vues filtrées** : Vue gérante, Vue réception, Vue praticienne, À décider,
  En retard.
- **Priorisation** : Valeur et Effort (1 à 5) alimentent la matrice et le nuage de
  points du tableau de bord.
- **Saisies préservées** : relancer `sheets.py` ne perd jamais le travail du
  métier (les colonnes éditables sont relues puis réinjectées par identifiant).
- **Formulaires** : menu du classeur, onglets Modifier un récit, Créer un récit,
  Nouvelle demande.

Pour réserver l'édition des colonnes H à Q à certaines personnes, copiez
`people.example.json` en `people.json` et renseignez `personnes` et `metier`.

## 11. Boucle retour vers le dépôt

```bash
.venv/bin/python sync_back.py
```

Écrit `out/backlog.json` (décisions du métier) et, dans le dépôt analysé,
`docs/superpowers/DECISIONS.md` (chemin configurable par `decisions_path`). Si
`issue-map.csv` (`id,github,gitlab`) existe, il génère `out/issues-sync.sh` pour
aligner labels et statuts des issues.

## 12. Notifications et revue PDF

```bash
NOTIFY_WEBHOOK=https://hooks.slack.com/... .venv/bin/python notify.py
.venv/bin/python export_pdf.py
```

`notify.py` envoie un condensé (décisions en attente, échéances dépassées) au
webhook, ou l'affiche seulement. `export_pdf.py` produit
`out/revue-AAAA-MM-JJ.pdf`.

Pour planifier les relances, ajoutez une tâche cron :

```cron
0 8 * * 1 cd /chemin/TicketsGoogleSheet && .venv/bin/python notify.py >> notify.log 2>&1
```

## 13. Intégrations (GSD, gstack, Matt Pocock)

Le parser lit une **convention** configurable, et l'agent `backlog-architect`
sert de pont pour ce qui n'est pas structuré.

| Outil | Artefacts | `convention` |
|---|---|---|
| plans/specs maison | `docs/superpowers/plans` | `plans` |
| GSD | `.planning/` (`*-PLAN.md`, `<task>`) | `gsd` |
| Matt Pocock (Markdown local) | `.scratch/<feature>/issues/NN-*.md` | `tickets` |
| Matt Pocock / gstack (GitHub, GitLab) | issues du dépôt | `agent` + `issue-map.csv` |

Démarrage sur un nouveau projet :

```bash
.venv/bin/python new_project.py --source ../mon-projet --sheet <ID> --run
```

## 14. Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `403 SERVICE_DISABLED` | API non activée | ouvrez le lien affiché et activez l'API |
| `User has not enabled the Apps Script API` | réglage utilisateur absent | activez-le sur script.google.com/home/usersettings, puis `clasp login` |
| `Aucun classeur « export-tickets » partagé` | classeur non partagé | partagez-le en Éditeur avec l'e-mail du compte de service, ou renseignez `spreadsheet_id` |
| `Clé de compte de service introuvable` | chemin de clé | corrigez `credentials` ou `GOOGLE_APPLICATION_CREDENTIALS` |
| Statuts vides | source sans git, ou commits absents | vérifiez `source_repo` et `main_branch` |
| `429 Quota exceeded` | trop d'écritures en une minute | attendez une minute ; les reprises sont automatiques |
| La source n'est pas un dépôt git | `git` introuvable dans `source_repo` | lancez depuis un dépôt git ou corrigez le chemin |

## Annexe : référence des commandes

```bash
# Installer
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Configurer un nouveau projet
.venv/bin/python new_project.py --source ../mon-projet --sheet <ID> --credentials key.json

# Pipeline
.venv/bin/python parser.py        # dépôt -> out/ (tickets.json, CSV, issues)
.venv/bin/python sheets.py        # remplit et habille le classeur
.venv/bin/python sync_back.py     # classeur -> dépôt (backlog.json, DECISIONS.md)
.venv/bin/python notify.py        # relances
.venv/bin/python export_pdf.py    # revue PDF

# Formulaires Apps Script
npx @google/clasp login
.venv/bin/python bind_apps_script_user.py

# Options
python3 new_project.py --help
python3 parser.py                 # lit config.json ; variables d'env prioritaires
```
