#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export des tickets du dépôt (tâches des plans) vers GitHub, GitLab et Google Sheets.

Lit docs/superpowers/plans/*.md, extrait un Epic par plan et un ticket par
« ### Tâche N », déduit l'avancement de git (sujet de commit écrit dans le plan),
puis écrit dans out/ : le pivot tickets.json, les exports GitHub, GitLab et les
CSV des onglets de la Google Sheet.

Usage : python3 tools/export-tickets/parser.py
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import config

TOOL_DIR = Path(__file__).resolve().parent
CFG = config.load()
PATHS = config.resolved(CFG)
ROOT = PATHS["source"]
PLANS_DIR = PATHS["plans"]
SPECS_DIR = PATHS["specs"]
OUT_DIR = TOOL_DIR / "out"
BODIES_DIR = OUT_DIR / "bodies"
SHEETS_DIR = OUT_DIR / "sheets"
STORIES_FILE = PATHS["stories"]
GENERATED_DIR = PATHS["generated"]
PEOPLE_FILE = PATHS["people"]
MAIN_BRANCH = CFG["main_branch"]


def load_people() -> list[str]:
    """Personnes proposées dans les listes déroulantes (Porteur, Relecteur, Validateur)."""
    if PEOPLE_FILE.exists():
        data = json.loads(PEOPLE_FILE.read_text(encoding="utf-8"))
        return [str(p) for p in data.get("personnes", [])]
    return []

GITHUB_REPO = CFG["github_repo"]
GITLAB_PROJECT = CFG["gitlab_project"]

TASK_RE = re.compile(r"^### Tâche\s+(\d+)\s*:\s*(.+?)\s*$")
FILE_ITEM_RE = re.compile(r"^-\s+(Cr[ée]er|Modifier|Tests?|Test suivi)\s*:\s*(.+)$")
IFACE_RE = re.compile(r"^-\s+(Consomme|Produit)\s*:\s*(.+)$")
ETAPE_RE = re.compile(r"^-\s*\[( |x|X)\]\s*\*\*Étape\s+(\d+)\s*:\s*(.+?)\*\*\s*$")
PATH_RE = re.compile(r"`([^`]+)`")
BRANCH_RE = re.compile(r"Branche\s+`([^`]+)`")
SUPERSEDE_RE = re.compile(
    r"[Rr]emplace le plan\s+`" + re.escape(CFG["plans_dir"]) + r"/([^`]+)`"
)
COMMIT_M_RE = re.compile(r'git commit[^\n]*?-m\s+"([^"]+)"')
COMMIT_HEREDOC_RE = re.compile(r"git commit[^\n]*<<'?EOF'?\s*\n(.*?)\nEOF", re.S)
GOAL_RE = re.compile(r"^\*\*(?:Goal \(objectif\)|Objectif)\s*:\*\*\s*(.*)$")
ARCHI_RE = re.compile(r"^\*\*Architecture\s*:\*\*\s*(.*)$")
TECH_RE = re.compile(r"^\*\*Tech Stack[^*]*:\*\*\s*(.*)$")
SPEC_RE = re.compile(r"^\*\*Spec\s*:\*\*\s*(.*)$")
SPEC_PATH_RE = re.compile(re.escape(CFG["specs_dir"]) + r"/[A-Za-z0-9._-]+\.md")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout


def match_paths(text: str) -> list[str]:
    """Chemins cités entre accents graves, sans doublons, dans l'ordre."""
    seen: list[str] = []
    for raw in PATH_RE.findall(text):
        path = raw.strip()
        if path and path not in seen:
            seen.append(path)
    return seen


def extract_commit_subject(block: str) -> str:
    m = COMMIT_HEREDOC_RE.search(block)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if line:
                return line
    m = COMMIT_M_RE.search(block)
    if m:
        return m.group(1).strip()
    return ""


def code_from(title: str, stem: str) -> tuple[str, str, str]:
    """Renvoie (code, sous_projet, vague) depuis le titre du plan."""
    label = f"{title} {stem}"
    sp_match = re.search(r"[Ss]ous-projet\s+([0-9]+[A-Za-z]?)", label)
    vague_match = re.search(r"vague\s+([0-9]+[A-Za-z]?)", label, re.I)
    if sp_match:
        sp = "SP" + sp_match.group(1).upper()
    elif "renommage" in label.lower():
        sp = "LAMA"
    else:
        sp = "GEN"
    vague = vague_match.group(1).upper() if vague_match else ""
    code = sp + (f"-V{vague}" if vague else "")
    return code, sp, vague


def parse_plan(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), path.stem)
    code, sp, vague = code_from(title, path.stem)

    header = lines[:80]

    def header_field(regex: re.Pattern[str]) -> str:
        for line in header:
            m = regex.match(line)
            if m:
                return m.group(1).strip()
        return ""

    branch_match = BRANCH_RE.search(text)
    branch = branch_match.group(1) if branch_match else ""
    specs = []
    for s in SPEC_PATH_RE.findall(text):
        if s not in specs:
            specs.append(s)

    plan = {
        "fichier": str(path.relative_to(ROOT)),
        "titre": title,
        "code": code,
        "sous_projet": sp,
        "vague": vague,
        "branche": branch,
        "objectif": header_field(GOAL_RE),
        "architecture": header_field(ARCHI_RE),
        "tech": header_field(TECH_RE),
        "spec": header_field(SPEC_RE),
        "specs": specs,
        "milestone": f"{code} - {title.split(' : ')[0]}",
        "remplace_par": [],
        "tasks": [],
    }

    task_starts = [(i, TASK_RE.match(l)) for i, l in enumerate(lines)]
    task_starts = [(i, m) for i, m in task_starts if m]
    for idx, (line_no, m) in enumerate(task_starts):
        end = task_starts[idx + 1][0] if idx + 1 < len(task_starts) else len(lines)
        block = "\n".join(lines[line_no:end])
        number = int(m.group(1))
        titre = m.group(2).strip()

        creer: list[str] = []
        modifier: list[str] = []
        tests: list[str] = []
        consomme: list[str] = []
        produit: list[str] = []
        etapes: list[dict] = []

        for line in lines[line_no:end]:
            fm = FILE_ITEM_RE.match(line)
            if fm:
                kind, rest = fm.group(1), fm.group(2)
                paths = match_paths(rest)
                if kind == "Créer":
                    creer += [p for p in paths if p not in creer]
                elif kind == "Modifier":
                    modifier += [p for p in paths if p not in modifier]
                else:
                    tests += [p for p in paths if p not in tests]
                continue
            im = IFACE_RE.match(line)
            if im:
                kind, rest = im.group(1), im.group(2)
                values = [v.strip() for v in rest.split(" ; ") if v.strip()]
                (consomme if kind == "Consomme" else produit).extend(values)
                continue
            em = ETAPE_RE.match(line)
            if em:
                etapes.append(
                    {"n": int(em.group(2)), "libelle": em.group(3).strip(), "fait": em.group(1).lower() == "x"}
                )

        plan["tasks"].append(
            {
                "plan_fichier": plan["fichier"],
                "plan_titre": title,
                "code": code,
                "sous_projet": sp,
                "vague": vague,
                "branche": branch,
                "numero": number,
                "titre": titre,
                "fichiers_creer": creer,
                "fichiers_modifier": modifier,
                "tests": tests,
                "consomme": consomme,
                "produit": produit,
                "etapes": etapes,
                "commit_subject": extract_commit_subject(block),
                "corps_extrait": block.strip(),
            }
        )

    return plan


def build_id(task: dict) -> str:
    return f"{task['code']}-T{task['numero']:02d}" if task["code"] else f"T{task['numero']:02d}"


def topic_labels(task: dict) -> list[str]:
    paths = task["fichiers_creer"] + task["fichiers_modifier"] + task["tests"]
    labels: list[str] = []
    if any(p.startswith("src/server") for p in paths):
        labels.append("serveur")
    if any(p.startswith("src/client") for p in paths):
        labels.append("client")
    if any("migrations" in p for p in paths):
        labels.append("migration")
    if any("i18n" in p for p in paths):
        labels.append("i18n")
    if any(p.startswith("deploy") for p in paths):
        labels.append("deploy")
    if any(p.endswith(".md") or p.startswith("docs") for p in paths):
        labels.append("docs")
    if task["tests"] or any(".test." in p for p in paths):
        labels.append("tests")
    return labels


def render_body(task: dict, statut: str, commit_hash: str) -> str:
    lines: list[str] = []
    lines.append(f"## Contexte")
    lines.append("")
    lines.append(f"- **Plan** : `{task['plan_fichier']}` — {task['plan_titre']}")
    if task.get("plan_specs"):
        for s in task["plan_specs"]:
            lines.append(f"- **Spec** : `{s}`")
    lines.append(f"- **Sous-projet** : {task['sous_projet']} · **vague** {task['vague'] or '—'}")
    lines.append(f"- **Branche** : `{task['branche']}`" if task["branche"] else "- **Branche** : —")
    lines.append(f"- **Ticket** : {build_id(task)} (tâche {task['numero']})")
    lines.append("")

    def section(title: str, items: list[str]) -> None:
        if not items:
            return
        lines.append(f"## {title}")
        lines.append("")
        for it in items:
            lines.append(f"- `{it}`" if not it.startswith(("|", "-")) else f"- {it}")
        lines.append("")

    section("Fichiers à créer", task["fichiers_creer"])
    section("Fichiers à modifier", task["fichiers_modifier"])
    section("Tests", task["tests"])

    if task["consomme"] or task["produit"]:
        lines.append("## Interfaces")
        lines.append("")
        if task["consomme"]:
            lines.append("**Consomme** : " + " ; ".join(task["consomme"]))
        if task["produit"]:
            lines.append("**Produit** : " + " ; ".join(task["produit"]))
        lines.append("")

    if task["etapes"]:
        lines.append("## Étapes")
        lines.append("")
        for e in task["etapes"]:
            mark = "x" if e["fait"] else " "
            lines.append(f"- [{mark}] {e['n']}. {e['libelle']}")
        lines.append("")

    lines.append("## Commit")
    lines.append("")
    if task["commit_subject"]:
        suffix = f" ({commit_hash})" if commit_hash else ""
        lines.append(f"`{task['commit_subject']}`{suffix}")
    else:
        lines.append("—")
    lines.append("")
    return "\n".join(lines)


def clean(text):
    """Tirets cadratins et demi-cadratins remplacés par un tiret court."""
    if isinstance(text, str):
        return text.replace("\u2014", "-").replace("\u2013", "-")
    return text


def write_csv(path: Path, columns: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow([clean(c) for c in columns])
        writer.writerows([[clean(c) for c in row] for row in rows])


# --- Adaptateurs de conventions ------------------------------------------------
# Chaque adaptateur renvoie des plans (epics) au même format que parse_plan, pour
# que l'aval (statuts, exports, classeur) soit identique quelle que soit la source :
#   plans   : docs/superpowers/plans/*.md (convention OpenSalon, « ### Tâche N »)
#   gsd     : .planning/phases/**/*-PLAN.md (balises <task>)
#   tickets : .scratch/<feature>/issues/NN-*.md (un fichier par ticket)
#   agent   : aucun plan ; seuls les récits générés par l'agent sont utilisés.


def slugify(text: str) -> str:
    text = re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-").upper()
    return text or "X"


def empty_plan(fichier: str, titre: str, code: str, sous_projet="", vague="",
               branche="", spec="", specs=None) -> dict:
    return {
        "fichier": fichier, "titre": titre, "code": code,
        "sous_projet": sous_projet, "vague": vague, "branche": branche,
        "objectif": "", "architecture": "", "tech": "", "spec": spec,
        "specs": specs or [], "milestone": f"{code} - {titre}" if code else titre,
        "remplace_par": [], "tasks": [],
    }


def empty_task(plan: dict, numero: int, titre: str, statut_hint="") -> dict:
    return {
        "plan_fichier": plan["fichier"], "plan_titre": plan["titre"],
        "code": plan["code"], "sous_projet": plan["sous_projet"], "vague": plan["vague"],
        "branche": plan["branche"], "numero": numero, "titre": titre,
        "fichiers_creer": [], "fichiers_modifier": [], "tests": [],
        "consomme": [], "produit": [], "etapes": [], "commit_subject": "",
        "statut_hint": statut_hint, "corps_extrait": "",
    }


def discover_gsd(planning_dir: Path) -> list[dict]:
    plans: list[dict] = []
    if not planning_dir.exists():
        return plans
    for plan_file in sorted(planning_dir.rglob("*-PLAN.md")):
        text = plan_file.read_text(encoding="utf-8")

        rel = str(plan_file.relative_to(ROOT)) if plan_file.is_relative_to(ROOT) else str(plan_file)
        front = re.search(r"\A---\s*\n(.*?)\n---", text, re.S)
        phase = re.search(r"^phase:\s*(.+)$", front.group(1), re.M) if front else None
        phase = phase.group(1).strip() if phase else plan_file.parent.name
        goal = re.search(r"<objective>\s*(.*?)\s*</objective>", text, re.S)
        title = goal.group(1).strip().splitlines()[0][:80] if goal else plan_file.stem
        code = "GSD-" + slugify(str(phase))[:24]
        plan = empty_plan(rel, title, code, sous_projet="GSD", vague=str(phase))
        plan["objectif"] = goal.group(1).strip() if goal else ""
        plan["spec"] = str((planning_dir / "ROADMAP.md").relative_to(ROOT)) if (planning_dir / "ROADMAP.md").exists() else ""
        if plan["spec"]:
            plan["specs"] = [plan["spec"]]
        summary = plan_file.with_name(plan_file.name.replace("-PLAN.md", "-SUMMARY.md"))
        hint = "fait" if summary.exists() else "à faire"
        for index, task_html in enumerate(re.findall(r"<task\b[^>]*>(.*?)</task>", text, re.S), 1):
            name = re.search(r"<name>\s*(.*?)\s*</name>", task_html, re.S)
            label = re.sub(r"^Task\s+\d+\s*:\s*", "", name.group(1).strip()) if name else f"Tâche {index}"
            task = empty_task(plan, index, label, statut_hint=hint)
            files = re.search(r"<files>\s*(.*?)\s*</files>", task_html, re.S)
            if files:
                task["fichiers_modifier"] = [f.strip() for f in files.group(1).split(",") if f.strip()]
            criteria = re.search(r"<acceptance_criteria>\s*(.*?)\s*</acceptance_criteria>", task_html, re.S)
            if criteria:
                task["etapes"] = [
                    {"n": i, "libelle": line.strip("- ").strip(), "fait": False}
                    for i, line in enumerate(criteria.group(1).strip().splitlines(), 1) if line.strip().startswith("-")
                ]
            task["corps_extrait"] = task_html.strip()
            plan["tasks"].append(task)
        if plan["tasks"]:
            plans.append(plan)
    return plans


def discover_tickets(scratch_dir: Path) -> list[dict]:
    plans: list[dict] = []
    if not scratch_dir.exists():
        return plans
    for feature in sorted(p for p in scratch_dir.iterdir() if p.is_dir()):
        issues_dir = feature / "issues"
        issue_files = sorted(issues_dir.glob("*.md")) if issues_dir.exists() else []
        spec = feature / "spec.md"
        if not issue_files and not spec.exists():
            continue
        rel = str(feature.relative_to(ROOT)) if feature.is_relative_to(ROOT) else str(feature)
        code = "MATT-" + slugify(feature.name)[:20]
        plan = empty_plan(rel, feature.name, code, sous_projet="MATT", vague=feature.name)
        if spec.exists():
            plan["spec"] = str(spec.relative_to(ROOT)) if spec.is_relative_to(ROOT) else str(spec)
            plan["specs"] = [plan["spec"]]

        def add_issue(path: Path, numero: int) -> None:
            text = path.read_text(encoding="utf-8")
            heading = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), path.stem)
            status = re.search(r"^Status:\s*(.+)$", text, re.M | re.I)
            value = status.group(1).strip().lower() if status else ""
            hint = {"resolved": "fait", "done": "fait", "claimed": "en cours"}.get(value, "à faire")
            task = empty_task(plan, numero, heading, statut_hint=hint)
            task["etapes"] = [
                {"n": i, "libelle": m.group(2).strip(), "fait": m.group(1).lower() == "x"}
                for i, m in enumerate(re.finditer(r"^-\s*\[( |x|X)\]\s*(.+)$", text, re.M), 1)
            ]
            task["corps_extrait"] = text.strip()
            plan["tasks"].append(task)

        for index, path in enumerate(issue_files, 1):
            add_issue(path, index)
        if not plan["tasks"] and spec.exists():
            add_issue(spec, 1)
        if plan["tasks"]:
            plans.append(plan)
    return plans


def discover_plans() -> list[dict]:
    convention = CFG.get("convention", "plans")
    if convention == "agent":
        return []
    if convention == "gsd":
        return discover_gsd(PLANS_DIR)
    if convention == "tickets":
        return discover_tickets(PLANS_DIR)
    return [parse_plan(p) for p in sorted(PLANS_DIR.glob("*.md"))]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BODIES_DIR.mkdir(parents=True, exist_ok=True)
    SHEETS_DIR.mkdir(parents=True, exist_ok=True)

    main_subjects = set(
        s for s in git("log", MAIN_BRANCH, "--pretty=format:%s").splitlines() if s
    )
    all_log = git("log", "--all", "--pretty=format:%H\t%s").splitlines()
    subject_hash: dict[str, str] = {}
    for line in all_log:
        if "\t" not in line:
            continue
        h, s = line.split("\t", 1)
        subject_hash.setdefault(s, h)
    merged = set(
        b.strip().lstrip("*+ ")
        for b in git("branch", "--merged", MAIN_BRANCH).splitlines()
        if b.strip()
    )
    existing = set(b.strip().lstrip("*+ ") for b in git("branch").splitlines() if b.strip())

    plans = discover_plans()

    # Plans remplacés (détectés dans les en-têtes « Remplace le plan ... »).
    replaced: dict[str, str] = {}
    if CFG.get("convention", "plans") == "plans":
        for p in PLANS_DIR.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            for old in SUPERSEDE_RE.findall(text):
                replaced[old] = p.name
    for plan in plans:
        name = Path(plan["fichier"]).name
        if name in replaced:
            plan["remplace_par"] = [replaced[name]]

    ticket_rows: list[dict] = []
    for plan in plans:
        superseded = bool(plan["remplace_par"]) or plan["code"] == "GEN"
        # « bilingue-cameroun » explicite : remplacé par sp3
        if Path(plan["fichier"]).name == "2026-09-27-bilingue-cameroun.md":
            superseded = True
            plan["remplace_par"] = plan["remplace_par"] or ["2026-09-28-sp3-bilingue.md"]
        for task in plan["tasks"]:
            task["plan_specs"] = plan["specs"]
            subject = task["commit_subject"]
            commit_hash = ""
            if superseded:
                statut, source = "remplacé", "plan remplacé"
            elif subject and subject in main_subjects:
                statut, source = "fait", "commit"
                commit_hash = subject_hash.get(subject, "")
            elif subject and subject in subject_hash:
                statut, source = "en cours", "commit"
                commit_hash = subject_hash.get(subject, "")
            elif task.get("statut_hint"):
                statut, source = task["statut_hint"], "source externe"
            else:
                statut, source = "", "indéterminé"
            task["statut"] = statut
            task["statut_source"] = source
            task["commit"] = commit_hash

    # Deuxième passe : tâches sans commit retrouvé, résolues par la branche puis par le plan.
    for plan in plans:
        tasks = plan["tasks"]
        matched_main = sum(
            1 for t in tasks if t["statut_source"] == "commit" and t["statut"] == "fait"
        )
        en_cours = sum(1 for t in tasks if t["statut"] == "en cours")
        for task in tasks:
            if task["statut"]:
                continue
            branch = plan["branche"]
            if branch and branch in merged:
                task["statut"], task["statut_source"] = "fait", "branche fusionnée"
            elif branch and branch in existing:
                task["statut"], task["statut_source"] = "en cours", "branche"
            elif matched_main >= 1 and en_cours == 0:
                task["statut"], task["statut_source"] = "fait", "plan fusionné"
            else:
                task["statut"], task["statut_source"] = "à faire", "à faire"

    for plan in plans:
        for task in plan["tasks"]:
            labels = ["type:tâche"]
            if plan["sous_projet"]:
                labels.append(f"sous-projet:{plan['sous_projet']}")
            if plan["vague"]:
                labels.append(f"vague:{plan['vague']}")
            labels.append(f"statut:{task['statut'].replace(' ', '-')}")
            for t in topic_labels(task):
                if t not in labels:
                    labels.append(t)

            task.update(
                {
                    "id": build_id(task),
                    "labels": labels,
                    "milestone": plan["milestone"],
                    "specs": plan["specs"],
                    "github_url": "",
                    "gitlab_url": "",
                }
            )
            task["corps_markdown"] = render_body(task, task["statut"], task["commit"])
            ticket_rows.append(task)

    # Ordre chronologique des plans, puis numéro de tâche.
    plan_order = {p["fichier"]: i for i, p in enumerate(sorted(plans, key=lambda x: x["fichier"]))}
    ticket_rows.sort(key=lambda t: (plan_order[t["plan_fichier"]], t["numero"]))

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts: dict[str, int] = {}
    for t in ticket_rows:
        counts[t["statut"]] = counts.get(t["statut"], 0) + 1

    pivot = {
        "generatedAt": generated,
        "repo": GITHUB_REPO,
        "counts": {"plans": len(plans), "tickets": len(ticket_rows)},
        "statuts": counts,
        "plans": [
            {
                **{k: v for k, v in plan.items() if k != "tasks"},
                "taches": len(plan["tasks"]),
                "fait": sum(1 for t in plan["tasks"] if t.get("statut") == "fait"),
                "en_cours": sum(1 for t in plan["tasks"] if t.get("statut") == "en cours"),
                "a_faire": sum(1 for t in plan["tasks"] if t.get("statut") == "à faire"),
                "statut": (
                    "remplacé"
                    if plan["remplace_par"]
                    else (
                        "terminé"
                        if all(t.get("statut") == "fait" for t in plan["tasks"])
                        else "en cours"
                        if any(t.get("statut") in ("fait", "en cours") for t in plan["tasks"])
                        else "à faire"
                    )
                ),
            }
            for plan in plans
        ],
        "tickets": ticket_rows,
    }
    (OUT_DIR / "tickets.json").write_text(
        json.dumps(pivot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Récits métier : couche lisible par la gérante, la réception et les praticiennes.
    # Deux sources : stories.json (écrits à la main) et generated/ (issus de
    # l'analyse du code par l'agent backlog-architect).
    stories: list[dict] = []
    seen_ids: set[str] = set()

    def merge_stories(items: list[dict], origine: str) -> None:
        for story in items:
            if story.get("id") in seen_ids:
                continue
            story["origine"] = origine
            seen_ids.add(story["id"])
            stories.append(story)

    if STORIES_FILE.exists():
        merge_stories(json.loads(STORIES_FILE.read_text(encoding="utf-8")), "manuel")
    if GENERATED_DIR.exists():
        for path in sorted(GENERATED_DIR.glob("stories*.json")):
            merge_stories(json.loads(path.read_text(encoding="utf-8")), "analyse du code")
    plan_status = {p["code"]: p["statut"] for p in pivot["plans"]}
    tickets_by_plan: dict[str, list[str]] = {}
    for t in ticket_rows:
        tickets_by_plan.setdefault(t["code"], []).append(t["id"])
    story_tickets: dict[str, list[str]] = {}
    ticket_stories: dict[str, list[str]] = {}
    for s in stories:
        linked: list[str] = []
        for code in s.get("plans", []):
            linked += tickets_by_plan.get(code, [])
        story_tickets[s["id"]] = linked
        for tid in linked:
            ticket_stories.setdefault(tid, []).append(s["id"])
        statuses = [plan_status.get(c, "") for c in s.get("plans", [])]
        if not statuses:
            s["avancement"] = "À cadrer"
        elif any(x == "en cours" for x in statuses):
            s["avancement"] = "En cours"
        elif all(x in ("terminé", "remplacé") for x in statuses):
            s["avancement"] = "Livré"
        else:
            s["avancement"] = "Partiel"

    # Corps Markdown par ticket
    for t in ticket_rows:
        (BODIES_DIR / f"{t['id']}.md").write_text(
            clean(t["corps_markdown"]), encoding="utf-8"
        )

    # GitHub : CSV d'import + script gh
    gh_columns = ["title", "body", "labels", "milestone"]
    gh_rows = []
    for t in ticket_rows:
        title = clean(f"[{t['code']}] T{t['numero']:02d} - {t['titre']}")
        gh_rows.append([title, t["corps_markdown"], ",".join(t["labels"]), t["milestone"]])
    write_csv(OUT_DIR / "github-import.csv", gh_columns, gh_rows)

    gh = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f'REPO="{GITHUB_REPO}"',
        'DIR="$(cd "$(dirname "$0")" && pwd)"',
        "",
        "# Labels",
    ]
    all_labels: list[str] = []
    for t in ticket_rows:
        for lab in t["labels"]:
            if lab not in all_labels:
                all_labels.append(lab)
    for lab in all_labels:
        color = "ededed"
        gh.append(f'gh label create "{lab}" --repo "$REPO" --force || true')
    gh.append("")
    gh.append("# Milestones")
    milestones: list[str] = []
    for t in ticket_rows:
        if t["milestone"] not in milestones:
            milestones.append(t["milestone"])
    for ms in milestones:
        gh.append(
            f'gh api "repos/$REPO/milestones" -f title="{ms}" >/dev/null 2>&1 || true'
        )
    gh.append("")
    gh.append("# Issues")
    for t in ticket_rows:
        title = clean(f"[{t['code']}] T{t['numero']:02d} - {t['titre']}")
        labels = ",".join(t["labels"])
        gh.append(
            f'gh issue create --repo "$REPO" --title "{title}" '
            f'--body-file "$DIR/bodies/{t["id"]}.md" --label "{labels}" --milestone "{t["milestone"]}"'
        )
        gh.append("sleep 1  # respecte la limite de cadence GitHub")
    (OUT_DIR / "github-issues.sh").write_text("\n".join(gh) + "\n", encoding="utf-8")

    # GitLab : NDJSON pour l'API + script glab
    ndjson_lines = []
    for t in ticket_rows:
        title = clean(f"[{t['code']}] T{t['numero']:02d} - {t['titre']}")
        ndjson_lines.append(
            json.dumps(
                {
                    "title": title,
                    "description": t["corps_markdown"],
                    "labels": ",".join(t["labels"]),
                    "milestone": t["milestone"],
                    "id": t["id"],
                },
                ensure_ascii=False,
            )
        )
    (OUT_DIR / "gitlab-issues.ndjson").write_text(
        "\n".join(ndjson_lines) + "\n", encoding="utf-8"
    )
    gl = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f'PROJECT="{GITLAB_PROJECT}"',
        'DIR="$(cd "$(dirname "$0")" && pwd)"',
        "",
        "# Labels",
    ]
    for lab in all_labels:
        gl.append(f'glab label create --name "{lab}" --force 2>/dev/null || true')
    gl.append("")
    gl.append("# Milestones")
    for ms in milestones:
        gl.append(
            f'glab api "projects/$PROJECT/milestones" -f title="{ms}" >/dev/null 2>&1 || true'
        )
    gl.append("")
    gl.append("# Issues")
    for t in ticket_rows:
        title = clean(f"[{t['code']}] T{t['numero']:02d} - {t['titre']}")
        labels = ",".join(t["labels"])
        gl.append(
            f'glab issue create --title "{title}" '
            f'--description "$(cat "$DIR/bodies/{t["id"]}.md")" '
            f'--label "{labels}" --milestone "{t["milestone"]}"'
        )
    (OUT_DIR / "gitlab-issues.sh").write_text("\n".join(gl) + "\n", encoding="utf-8")

    # Google Sheets : CSV par onglet
    ticket_columns = [
        "ID", "Titre", "Sous-projet", "Vague", "N° tâche", "Plan", "Fichier plan",
        "Spec", "Branche", "Statut", "Source statut", "Commit", "Message commit",
        "Fichiers à créer", "Fichiers à modifier", "Tests", "Interfaces consommées",
        "Interfaces produites", "Étapes", "Labels", "Milestone", "URL GitHub", "URL GitLab",
        "Récits liés",
    ]
    ticket_sheet_rows = []
    for t in ticket_rows:
        ticket_sheet_rows.append(
            [
                t["id"], t["titre"], t["sous_projet"], t["vague"], t["numero"],
                t["plan_titre"], t["plan_fichier"], " ; ".join(t["specs"]), t["branche"],
                t["statut"], t["statut_source"], t["commit"], t["commit_subject"],
                "\n".join(t["fichiers_creer"]), "\n".join(t["fichiers_modifier"]),
                "\n".join(t["tests"]), " ; ".join(t["consomme"]), " ; ".join(t["produit"]),
                "\n".join(f"{e['n']}. {e['libelle']}" for e in t["etapes"]),
                ", ".join(t["labels"]), t["milestone"], t["github_url"], t["gitlab_url"],
                ", ".join(ticket_stories.get(t["id"], [])),
            ]
        )
    write_csv(SHEETS_DIR / "Tickets.csv", ticket_columns, ticket_sheet_rows)

    # Onglet des récits : colonnes éditables par le métier (Priorité à Commentaire).
    recit_columns = [
        "ID", "Domaine", "Rôle", "Fonctionnalité", "Récit", "Bénéfice",
        "Critères d'acceptation", "Priorité", "Statut métier", "Décision",
        "Porteur", "Relecteur", "Validateur", "Échéance", "Commentaire",
        "Valeur", "Effort", "Score", "Avancement", "Origine",
        "Plans liés", "Tickets liés", "Preuves (code)", "Alerte",
    ]
    recit_rows = []
    for s in stories:
        recit_rows.append(
            [
                s["id"], s.get("domaine", ""), s.get("role", ""),
                s.get("fonctionnalite", ""), s.get("recit", ""), s.get("benefice", ""),
                s.get("criteres", ""),
                "", "", "", "", "", "", "", "",  # Priorité à Commentaire
                "", "",  # Valeur, Effort
                "",  # Score (formule posée par sheets.py)
                s.get("avancement", ""),
                s.get("origine", ""),
                " ; ".join(s.get("plans", [])),
                ", ".join(story_tickets.get(s["id"], [])),
                " ; ".join(s.get("evidence", [])),
                "",  # Alerte (formule posée par sheets.py)
            ]
        )
    write_csv(SHEETS_DIR / "Recits.csv", recit_columns, recit_rows)

    plan_columns = [
        "Code", "Titre", "Fichier", "Branche", "Sous-projet", "Vague", "Specs",
        "Nb tâches", "Fait", "En cours", "À faire", "Statut", "Remplacé par",
    ]
    plan_sheet_rows = []
    for plan in pivot["plans"]:
        plan_sheet_rows.append(
            [
                plan["code"], plan["titre"], plan["fichier"], plan["branche"],
                plan["sous_projet"], plan["vague"], " ; ".join(plan["specs"]),
                plan["taches"], plan["fait"], plan["en_cours"], plan["a_faire"],
                plan["statut"], " ; ".join(plan["remplace_par"]),
            ]
        )
    write_csv(SHEETS_DIR / "Plans.csv", plan_columns, plan_sheet_rows)

    spec_columns = ["Fichier", "Titre", "Plans liés"]
    spec_rows = []
    for spec in sorted(SPECS_DIR.glob("*.md")):
        title = ""
        for line in spec.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        linked = [
            plan["code"]
            for plan in pivot["plans"]
            if str(spec.relative_to(ROOT)) in plan["specs"]
        ]
        spec_rows.append([str(spec.relative_to(ROOT)), title, ", ".join(linked)])
    write_csv(SHEETS_DIR / "Specs.csv", spec_columns, spec_rows)

    columns = [
        ("Statut", ["à faire", "en cours", "fait", "remplacé"]),
        ("Sous-projet", sorted({p["sous_projet"] for p in pivot["plans"] if p["sous_projet"]})),
        ("Vague", sorted({p["vague"] for p in pivot["plans"] if p["vague"]})),
        ("Label", all_labels),
        ("Priorité", ["Indispensable", "Importante", "Souhaitable", "Plus tard"]),
        ("Statut métier", ["À cadrer", "À valider", "Validé", "En cours", "Livré", "Refusé"]),
        ("Décision", ["En attente", "Validée", "À revoir", "Refusée"]),
        ("Personne", load_people()),
    ]
    max_len = max(len(values) for _, values in columns)
    referentiel_rows = [
        [values[i] if i < len(values) else "" for _, values in columns]
        for i in range(max_len)
    ]
    write_csv(
        SHEETS_DIR / "Referentiels.csv",
        [name for name, _ in columns],
        referentiel_rows,
    )

    print(f"Plans           : {len(plans)}")
    print(f"Tickets         : {len(ticket_rows)}")
    print(f"Récits métier   : {len(stories)}")
    print(f"Statuts         : {counts}")
    print(f"Sortie          : {OUT_DIR}")
    unresolved = [t["id"] for t in ticket_rows if t["statut_source"] in ("à faire", "indéterminé")]
    if unresolved:
        print(f"Statut non résolu ({len(unresolved)}) : {', '.join(unresolved[:20])}")


if __name__ == "__main__":
    main()
