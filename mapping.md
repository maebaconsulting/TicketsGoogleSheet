# Export des tickets

Les tickets du projet sont lus dans les artefacts du dépôt (plans, phases, tickets),
transformés en un pivot commun, puis déclinés vers GitHub, GitLab et une Google Sheet.
La **convention** est configurable (`convention`) et détectée par `new_project.py` :

- `plans` : `docs/superpowers/plans/*.md` (« ### Tâche N ») ;
- `gsd` : `.planning/` (ROADMAP, `phases/**/*-PLAN.md` avec `<task>`) ;
- `tickets` : `.scratch/<feature>/issues/NN-*.md` ;
- `agent` : aucun plan ; récits générés par l'agent `backlog-architect`.

## Sources (convention `plans`)

- `docs/superpowers/specs/*.md` : conception, un document par sous-projet, dit « fait foi ».
- `docs/superpowers/plans/*.md` : un plan par sous-projet et par vague ; chaque plan
  est un Epic, chaque `### Tâche N` est un ticket.
- `git` : l'avancement. Chaque tâche porte le sujet de son commit ; le plan indique
  aussi sa branche.

## Hiérarchie

| Dépôt | GitHub | GitLab | Google Sheet |
|---|---|---|---|
| Spec (`*-design.md`) | issue label `type:spec`, ou simple lien | idem | onglet `Specs` |
| Récit (`stories.json`) | issue label `type:récit` | idem | onglet `Récits métier` |
| Plan (`plans/*.md`) | milestone + issue parente | milestone | onglet `Plans` |
| Tâche (`### Tâche N`) | issue | issue | onglet `Tickets` |
| Étape (`- [ ] Étape`) | cases à cocher du corps | cases à cocher | colonne `Étapes` |

## Couche métier (récits)

Les 167 tâches sont la décomposition technique d'un travail : la gérante ou la
réception ne peuvent pas s'y exprimer. La couche des récits ajoute une lecture du
point de vue des utilisatrices du produit (gérante, réception, praticienne).

Deux sources alimentent l'onglet `Récits métier`, fusionnées par `parser.py` :

- `stories.json` — récits écrits à la main (origine `manuel`) ;
- `generated/stories*.json` — récits produits par l'agent `backlog-architect` en
  analysant le code (origine `analyse du code`).

La colonne `Origine` distingue les deux, `Preuves (code)` cite les fichiers qui
justifient un récit généré. Chaque récit :

- suit la forme « En tant que…, je veux…, afin de… » ;
- porte un domaine, un rôle, un bénéfice et des critères d'acceptation ;
- est relié aux plans et aux tâches qui le réalisent (`Plans liés`, `Tickets liés`) ;
- affiche un **Avancement** calculé depuis git (`Livré`, `En cours`, `À cadrer`).

L'onglet `Récits métier` est le premier du classeur. Les colonnes **H à M**
(Priorité, Statut métier, Décision, Porteur, Échéance, Commentaire) sont mises en
évidence et laissées vides : elles sont destinées au métier, avec des listes
déroulantes adossées à l'onglet `Référentiels`. Les autres colonnes sont produites
par l'outil (fond neutre). La correspondance est bidirectionnelle : l'onglet
`Tickets` porte la colonne `Récits liés`.

## Agent d'analyse (`backlog-architect`)

`.opencode/agent/backlog-architect.md` définit un sous-agent opencode qui lit un
codebase et en tire un backlog métier, sans modifier le code :

1. cartographie le produit (`PRODUCT.md`, `agent.md`, routes, écrans, migrations,
   droits, réglages) ;
2. en déduit les capacités et les écrit en récits « En tant que…, je veux…,
   afin de… » avec bénéfice, critères d'acceptation et références de code ;
3. déduplique contre `stories.json` ;
4. écrit `generated/stories.generated.json`.

Lancer l'agent depuis opencode (`@backlog-architect` ou en le choisissant comme
sous-agent), puis recharger le classeur :

```bash
python3 tools/export-tickets/parser.py
GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json tools/export-tickets/.venv/bin/python tools/export-tickets/sheets.py
```

Un agent défini dans `.opencode/agent/` n'apparaît qu'après un redémarrage
d'opencode (la configuration est lue au démarrage).

## Schéma canonique (pivot `tickets.json`)

| Champ | Contenu |
|---|---|
| `id` | `SP7-V1-T01` (code du plan + numéro de tâche) |
| `titre` | intitulé de la tâche |
| `sous_projet`, `vague`, `code` | `SP7`, `1`, `SP7-V1` |
| `plan_fichier`, `plan_titre` | chemin et titre du plan |
| `specs[]` | specs citées par le plan |
| `branche` | branche git du plan |
| `numero` | numéro de la tâche |
| `statut` | `fait`, `en cours`, `à faire`, `remplacé` |
| `statut_source` | `commit`, `branche fusionnée`, `plan fusionné`, `plan remplacé` |
| `commit`, `commit_subject` | hash et sujet du commit retrouvé |
| `fichiers_creer[]`, `fichiers_modifier[]`, `tests[]` | chemins extraits du bloc **Fichiers** |
| `consomme[]`, `produit[]` | interfaces extraites du bloc **Interfaces** |
| `etapes[]` | étapes numérotées avec leur état |
| `labels[]`, `milestone`, `corps_markdown` | générés pour les cibles |
| `github_url`, `gitlab_url` | à remplir après création des issues |

## Déduction du statut

1. Le sujet de commit de la tâche est cherché dans `git log --all`.
2. Trouvé sur `main` → `fait` ; trouvé sur une autre branche → `en cours`.
3. Sinon, si la branche du plan est fusionnée dans `main` → `fait` ; si elle existe
   encore → `en cours`.
4. Sinon, si le plan a des tâches retrouvées sur `main` et aucune en cours → `fait`
   (tâche de vérification, souvent sans commit propre).
5. Sinon → `à faire`. Un plan remplacé marque ses tâches `remplacé`.

## Conventions

- **Titre d'issue** : `[SP7-V1] T01 — migration 009 et file d'envoi sans contenu`.
- **Milestone** : un par plan, `SP7-V1 — Sous-projet 7, vague 1`.
- **Labels** : `type:tâche`, `sous-projet:SP7`, `vague:1`, `statut:fait`,
  puis selon les fichiers : `serveur`, `client`, `tests`, `migration`, `i18n`,
  `deploy`, `docs`.

## Correspondance des champs

| Pivot | GitHub | GitLab | Google Sheet |
|---|---|---|---|
| `titre` + `id` | `title` | `title` | colonnes `ID`, `Titre` |
| `corps_markdown` | `body` | `description` | non repris (corps dans `out/bodies/`) |
| `labels` | `labels` | `labels` | colonne `Labels` |
| `milestone` | `milestone` | `milestone` | colonne `Milestone` |
| `statut` | label `statut:*` (state open/closed) | label `statut:*` | colonne `Statut` |
| `fichiers_*`, `tests`, `interfaces`, `etapes` | corps | corps | colonnes dédiées |

## Fichiers produits (`out/`, ignoré par git)

- `tickets.json` : pivot complet (plans + tickets).
- `github-import.csv` : `title,body,labels,milestone`, à importer ou à rejouer.
- `github-issues.sh` : crée labels, milestones puis les issues par `gh`.
- `gitlab-issues.ndjson` + `gitlab-issues.sh` : équivalent GitLab.
- `sheets/{Recits,Tickets,Plans,Specs,Referentiels}.csv` : source de la Google Sheet.
- `bodies/<ID>.md` : corps Markdown d'un ticket (utilisé par les scripts).
- `backlog.json` : décisions du métier relues par `sync_back.py`.
- `revue-AAAA-MM-JJ.pdf` : export de revue (`export_pdf.py`).
- `../docs/superpowers/DECISIONS.md` : journal des décisions validées.

## Utilisation

```bash
# 1. Produire le pivot et les exports à partir des plans et de git
python3 tools/export-tickets/parser.py

# 2. Pousser le classeur Google (voir README des identifiants)
GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json \
SHEET_ID=<id_du_classeur> \
python3 tools/export-tickets/sheets.py

# 3. Rapatrier les décisions du métier vers le dépôt
python3 tools/export-tickets/sync_back.py     # backlog.json + DECISIONS.md

# 4. Relancer le métier sur les décisions et échéances
NOTIFY_WEBHOOK=https://hooks.slack.com/... python3 tools/export-tickets/notify.py

# 5. Préparer la revue hebdo
python3 tools/export-tickets/export_pdf.py
```

Les scripts `github-issues.sh` et `gitlab-issues.sh` sont fournis mais **à exécuter
vous-même** : aucune issue n'est créée automatiquement.

## Google Sheet

Classeur désigné par `spreadsheet_id`, ou découvert par `sheet_name`, partagé en
Éditeur avec l'e-mail du compte de service (`credentials`).

| Onglet | Contenu |
|---|---|
| `Accueil` | titre, date de génération, cartes KPI (récits, tickets, livrés, à décider, en retard), navigation, légende |
| `Récits métier` | 93 récits (35 manuels + 58 issus de l'analyse du code) ; colonnes éditables H à Q |
| `Kanban` | tickets en colonnes par statut (À faire, En cours, Fait, Remplacé), vue type monday |
| `Décisions` | trace des récits ayant un statut, une décision ou un validateur |
| `Demandes` | recueil des besoins du métier (à remplir, ou via Google Form) |
| `Tickets` | 167 tâches d'ingénierie (24 colonnes) avec leurs récits liés |
| `Plans` | 16 plans (epics) |
| `Specs` | 8 documents de conception |
| `Référentiels` | listes des menus déroulants (statut, priorité, décision, personne) |
| `Tableau de bord` | cartes, synthèses, matrice de priorisation et 5 graphiques |

### Apparence et expérience

Esthétique inspirée de monday.com, tenue professionnelle :

- Plateaux clairs, en-têtes gris très clair (`#F5F6F8`) avec liseré bleu de marque,
  lignes alternées blanc et bleu pâle, quadrillage masqué.
- **Pastilles de statut colorées** aux couleurs monday : vert `#00C875` (fait,
  livré, validé), orange `#FDAB3D` (en cours, à revoir), bleu `#579BFC`,
  violet `#A25DDC` (gérante), bleu foncé `#0086C0` (praticienne), rouge `#E2445C`
  (refusé, indispensable, alerte), gris `#C4C4C4` (à faire, en attente).
- **Bandes de groupe par domaine** : chaque domaine a sa teinte, comme les
  groupes d'un tableau monday.
- En-têtes figés, première colonne figée, filtres, notes explicatives.
- Colonnes éditables en jaune pâle, listes déroulantes (`Référentiels`).
- Onglets colorés à la palette monday ; Accueil et Tableau de bord en bleu de marque.
- `parser.py` remplace les tirets cadratins par des tirets courts dans tous les exports.

### Collaboration

- **Vues filtrées** dans `Récits métier` : Vue gérante, Vue réception, Vue
  praticienne, À décider, En retard.
- **Priorisation** : colonnes Valeur (1-5) et Effort (1-5) saisies au clavier
  (validation numérique), Score calculé, matrice Effort × Valeur et graphique de
  nuage de points sur le tableau de bord.
- **RACI léger** : Porteur, Relecteur, Validateur, avec liste de personnes.
- **Alertes** : colonne `Alerte` calculée et échéance en rouge si dépassée et non livrée.
- **Saisies préservées** : les colonnes H à Q de `Récits métier` sont relues avant
  chaque réécriture puis réinjectées par identifiant ; le travail du métier n'est
  jamais perdu.
- **Protection stricte** : les colonnes générées sont protégées ; le compte de
  service reste éditeur pour écrire. Si `people.json` fournit les adresses du
  métier, l'édition des colonnes H à Q leur est réservée.

### Boucle retour et rituels

| Script | Rôle |
|---|---|
| `sync_back.py` | relit les décisions du classeur, écrit `out/backlog.json` et `docs/superpowers/DECISIONS.md` ; génère `out/issues-sync.sh` si `issue-map.csv` existe |
| `notify.py` | condensé des décisions en attente et échéances dépassées ; publié via `NOTIFY_WEBHOOK` (Slack compatible) |
| `export_pdf.py` | exporte le classeur en PDF (`out/revue-AAAA-MM-JJ.pdf`) pour la revue hebdo |
| `create_form.py` | crée un Google Form pour recueillir les demandes (nécessite l'API Forms) |

`issue-map.csv` (créé par vos soins) : colonnes `id,github,gitlab`, pour relier un
récit à son issue et aligner les labels lors de la synchronisation.
Copier `people.example.json` en `people.json` (ignoré par git) pour les personnes
et les adresses du métier.

### Formulaires intégrés (Apps Script)

Le dossier `apps-script/` contient un script lié au classeur qui ajoute un menu
**lama** et trois formulaires HTML stylés monday.com, écrits directement dans les
cellules (aucune application locale, aucune clé) :

- `Code.gs` : menu (Modifier un récit, Créer un récit, Nouvelle demande),
  `getData`, `saveRecit`, `createRecit`, `addDemande` ; n'écrit que les colonnes
  H à Q et neutralise les saisies commençant par `=`.
- `Formulaire.html` : interface à trois onglets (recherche, pastilles, champs stylés).
- `appsscript.json` : V8, fuseau `Africa/Douala`, permissions minimales.

Installation automatique (recommandé). L'API Apps Script **ne peut pas** être
utilisée par un compte de service : il faut le compte Google d'une personne.

```bash
# une fois : activer l'API ici et s'authentifier
#   https://script.google.com/home/usersettings  (interrupteur Activé)
npx @google/clasp login

# crée le script lié au classeur et pousse les fichiers
python3 tools/export-tickets/bind_apps_script_user.py
```

Le script est lié au classeur (parentId = identifiant du classeur), l'URL est
`script.google.com/d/<scriptId>/edit`. Recharger la page du classeur : le menu
**lama** apparaît, avec l'autorisation à accorder une fois.

Installation manuelle : dans le classeur, **Extensions > Apps Script**, coller
`Code.gs` et `Formulaire.html`, enregistrer, autoriser, recharger.

Le script s'exécute sous le compte de la personne ; si `people.json` réserve
l'édition de H:Q, la personne doit y figurer.

`install_apps_script.py` (compte de service) sert de diagnostic : il détecte et
explique l'activation à faire, mais ne peut pas déployer, Google interdisant
l'API Apps Script aux comptes de service.

### Durabilité des saisies

`sheets.py` conserve ce qui est créé depuis le classeur : les **récits dont l'ID
n'est pas produit par le parser** sont réajoutés après les récits générés, et les
**lignes de l'onglet Demandes** ne sont jamais effacées (seul l'en-tête est
réécrit). L'onglet Décisions reste dérivé des récits.
