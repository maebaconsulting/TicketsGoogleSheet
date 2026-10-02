# TicketsGoogleSheet

Transformer le travail d'un dépôt (plans, specs, code) en un **backlog collaboratif
dans Google Sheets** : récits métier éditables, tickets d'ingénierie, décisions,
priorisation, formulaires de saisie intégrés au classeur, et boucle retour vers le
dépôt.

L'outil est autonome : il analyse un dépôt **configurable** (`source_repo`) et écrit
dans un classeur Google **configurable** (`spreadsheet_id` ou `sheet_name`).

## Fonctionnalités

- **Pivot JSON** : 16 plans / 167 tickets / 93 récits pour l'exemple lama.
- **Onglet Récits métier** : récits « En tant que… », colonnes éditables préservées,
  priorisation Valeur/Effort, vues filtrées par rôle, notes d'en-tête.
- **Onglets Tickets, Plans, Specs, Décisions, Demandes, Référentiels, Tableau de bord**
  avec graphiques et thème monday.com.
- **Formulaires Apps Script** intégrés au classeur (menu, modale stylée) : modifier ou
  créer un récit, saisir une demande.
- **Boucle retour** : `sync_back.py` relit les décisions du classeur et écrit
  `backlog.json` et un journal `DECISIONS.md` dans le dépôt analysé.
- **Relances** : `notify.py` (décisions en attente, échéances dépassées) via webhook.
- **Exports** : `github-import.csv` + `github-issues.sh`, `gitlab-issues.ndjson` +
  `gitlab-issues.sh`, PDF de revue.
- **Agent** opencode `backlog-architect` pour générer les récits en analysant un codebase.

Guide de démarrage complet, pas à pas : [GUIDE.md](GUIDE.md).

## Prérequis

- Python 3.11+ ; un compte de service Google avec l'API **Google Sheets** et
  **Google Drive** activées ; le classeur partagé en Éditeur avec l'e-mail du compte
  de service ; le fichier de clé JSON.
- Node.js (facultatif, pour `clasp` et les formulaires Apps Script).

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.json config.json   # puis éditer
```

`config.json` (ignoré par git) contient :

| Clé | Rôle |
|---|---|
| `source_repo` | dépôt analysé (chemin absolu ou relatif à l'outil) |
| `plans_dir`, `specs_dir` | dossiers des plans et specs dans le dépôt analysé |
| `decisions_path` | emplacement du journal de décisions dans le dépôt analysé |
| `main_branch` | branche principale (défaut `main`) |
| `github_repo`, `gitlab_project` | dépôts cibles des exports d'issues |
| `spreadsheet_id` | identifiant du classeur (vide : découverte par `sheet_name`) |
| `sheet_name` | nom du classeur à découvrir (défaut `export-tickets`) |
| `credentials` | clé JSON du compte de service (défaut `key.json`) |
| `stories_file`, `generated_dir` | sources des récits |
| `product_name` | nom affiché dans les formulaires |

Priorité : variables d'environnement > `config.json` > défauts.

## Utilisation

```bash
# 1. Produire le pivot et les exports
.venv/bin/python parser.py

# 2. Remplir et habiller le classeur
.venv/bin/python sheets.py

# 3. Rapatrier les décisions du métier
.venv/bin/python sync_back.py

# 4. Relancer (webhook Slack compatible) et revue PDF
NOTIFY_WEBHOOK=https://hooks.slack.com/... .venv/bin/python notify.py
.venv/bin/python export_pdf.py
```

### Formulaires Apps Script

L'API Apps Script n'est **pas utilisable par un compte de service** : il faut le
compte Google d'une personne.

```bash
# une fois : activer l'API et s'authentifier
#   https://script.google.com/home/usersettings
npx @google/clasp login
.venv/bin/python bind_apps_script_user.py
```

Le script lié est créé et déployé ; recharger le classeur fait apparaître le menu.

## Structure

```
config.py               configuration
new_project.py          amorçage sur un nouveau projet (détection de convention)
parser.py               dépôt -> tickets.json + exports
sheets.py               habillage et remplissage du classeur
sync_back.py            classeur -> backlog.json + DECISIONS.md
notify.py               relances
export_pdf.py           revue PDF
form_app.py             formulaire local (optionnel)
create_form.py          Google Form (optionnel)
install_apps_script.py  diagnostic (compte de service)
bind_apps_script_user.py déploiement Apps Script (compte utilisateur)
deploy_apps_script.sh   déploiement via clasp
apps-script/            Code.gs, Formulaire.html, appsscript.json
.opencode/agent/        agent backlog-architect
examples/lama/          jeu de données et config d'exemple
mapping.md              schéma, correspondances et modes d'emploi
```

## Intégrations (gstack, GSD, Matt Pocock)

Le parser lit une **convention** configurable (`convention`) et l'agent
`backlog-architect` sert de pont universel pour ce qui n'est pas structuré.

| Outil | Où sont les artefacts | `convention` | `plans_dir` |
|---|---|---|---|
| plans/specs maison (OpenSalon) | `docs/superpowers/plans`, `specs` | `plans` | `docs/superpowers/plans` |
| GSD (`/gsd-*`) | `.planning/ROADMAP.md`, `phases/**/*-PLAN.md` (`<task>`) | `gsd` | `.planning` |
| Matt Pocock (tickets Markdown locaux) | `.scratch/<feature>/issues/NN-*.md` | `tickets` | `.scratch` |
| Matt Pocock (GitHub/GitLab) | issues du dépôt | `agent` | — |
| gstack (`/spec`, `/plan-*`, `/autoplan`) | plans libres, issues | `agent` | — |

- **`plans`** : chaque `### Tâche` d'un plan devient un ticket ; le statut vient du
  sujet de commit retrouvé dans git (fait / en cours / à faire).
- **`gsd`** : chaque `*-PLAN.md` devient un epic, chaque `<task>` un ticket ; le
  statut vient de la présence d'un `*-SUMMARY.md`.
- **`tickets`** : chaque dossier `.scratch/<feature>` devient un epic, chaque
  fichier d'issue un ticket ; le statut vient de la ligne `Status:` (`resolved`,
  `claimed`).
- **`agent`** : aucun ticket déduit des plans ; l'agent `backlog-architect` analyse
  le code et écrit `generated/stories.generated.json`, chargé dans l'onglet Récits.

Pour un tracker GitHub/GitLab (Matt Pocock ou gstack), reliez les tickets créés à
leurs issues par `issue-map.csv` (`id,github,gitlab`) : `sync_back.py` génère alors
`issues-sync.sh` pour aligner labels et statuts.

### Démarrer sur un nouveau projet

```bash
python3 new_project.py --source ../mon-projet --sheet <id_du_classeur> \
  --credentials key.json --product "Mon Backlog"
# détecte la convention (.planning, .scratch, docs/superpowers ou agent),
# écrit config.json, puis :
.venv/bin/python parser.py && .venv/bin/python sheets.py
```

Options : `--convention plans|gsd|tickets|agent`, `--github`, `--gitlab`,
`--force`, `--run`.

## Exemple lama

`examples/lama/` contient le jeu de données du projet lama (OpenSalon) : config,
`stories.json` (35 récits écrits à la main) et `generated/stories.generated.json`
(58 récits issus de l'analyse du code). Copier `examples/lama/config.json` en
`config.json` pour rejouer ce cas.

## Licence

AGPL-3.0, comme OpenSalon dont le code est dérivé.
