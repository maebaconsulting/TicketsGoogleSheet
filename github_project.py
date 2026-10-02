#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crée un tableau GitHub Projects (kanban) et y range les issues par statut.

Sous votre compte GitHub (gh authentifié), à partir du dépôt `github_repo` de
`config.json` :

1. crée (ou réutilise) un projet v2 ;
2. ajoute toutes les issues du dépôt ;
3. règle le champ Statut depuis le label `statut:*` de chaque issue
   (à faire → Todo, en cours → In progress, fait/remplacé → Done).

Usage :
    python3 github_project.py [--repo owner/name] [--owner owner] [--title "..."] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import config

# Correspondance entre nos statuts et les options du champ Status de GitHub.
STATUS_MAP = {
    "à faire": "Todo",
    "en cours": "In Progress",
    "fait": "Done",
    "remplacé": "Done",
}


def option_id(options: dict, wanted: str) -> str | None:
    for name, oid in options.items():
        if name.lower() == wanted.lower():
            return oid
    return None


def gh(*args: str) -> tuple[int, str]:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def gh_json(*args: str) -> dict | list:
    code, out = gh(*args)
    if code != 0:
        raise SystemExit(f"gh {' '.join(args)} a échoué : {out[:300]}")
    return json.loads(out or "{}")


def find_project(owner: str, title: str) -> dict | None:
    data = gh_json("project", "list", "--owner", owner, "--format", "json", "--limit", "100")
    projects = data if isinstance(data, list) else data.get("projects", [])
    for project in projects:
        if project.get("title") == title:
            return project
    return None


def status_field(owner: str, number: int) -> tuple[str, dict]:
    data = gh_json("project", "field-list", str(number), "--owner", owner, "--format", "json")
    for field in data.get("fields", []):
        if field.get("name") == "Status":
            options = {option["name"]: option["id"] for option in field.get("options", [])}
            return field["id"], options
    raise SystemExit("Champ « Status » introuvable dans le projet.")


def existing_items(owner: str, number: int) -> dict[str, str]:
    data = gh_json("project", "item-list", str(number), "--owner", owner,
                   "--format", "json", "--limit", "1000")
    mapping = {}
    for item in data.get("items", []):
        url = (item.get("content") or {}).get("url")
        if url:
            mapping[url] = item["id"]
    return mapping


def label_status(labels: list[dict]) -> str:
    for label in labels:
        name = label.get("name", "")
        if name.startswith("statut:"):
            return name.split(":", 1)[1].replace("-", " ")
    return ""


def main() -> None:
    cfg = config.load()
    parser = argparse.ArgumentParser(description="Kanban GitHub Projects.")
    parser.add_argument("--repo", default=cfg["github_repo"], help="owner/name")
    parser.add_argument("--owner", default="")
    parser.add_argument("--title", default=f"{cfg['product_name']} backlog")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.repo or "/" not in args.repo:
        raise SystemExit("Renseignez github_repo dans config.json (owner/name).")
    owner = args.owner or args.repo.split("/", 1)[0]

    if not shutil_which("gh"):
        raise SystemExit("gh est absent : https://cli.github.com")

    project = find_project(owner, args.title)
    if project:
        number, project_id = project["number"], project["id"]
        print(f"Projet existant : #{number} {project.get('url', '')}")
    else:
        print(f"Création du projet « {args.title} » pour {owner} …")
        gh("project", "create", "--owner", owner, "--title", args.title)
        project = find_project(owner, args.title)
        if not project:
            raise SystemExit("Projet introuvable après création.")
        number, project_id = project["number"], project["id"]

    field_id, options = status_field(owner, number)
    items = existing_items(owner, number)

    code, out = gh("issue", "list", "--repo", args.repo, "--state", "all",
                   "--limit", "1000", "--json", "number,url,labels")
    if code != 0:
        raise SystemExit(f"gh issue list a échoué : {out[:300]}")
    issues = json.loads(out or "[]")
    print(f"{len(issues)} issues à ranger.")

    for issue in issues:
        url = issue["url"]
        if url not in items:
            if args.dry_run:
                print(f"  + {url}")
                continue
            code, out = gh("project", "item-add", str(number), "--owner", owner,
                           "--url", url, "--format", "json")
            if code != 0:
                print(f"  échec ajout {url} : {out[:120]}")
                continue
            items[url] = json.loads(out)["id"]
        wanted = STATUS_MAP.get(label_status(issue.get("labels", [])))
        oid = option_id(options, wanted) if wanted else None
        if args.dry_run or not oid:
            continue
        code, out = gh(
            "project", "item-edit",
            "--project-id", project_id, "--id", items[url],
            "--field-id", field_id, "--single-select-option-id", oid,
        )
        if code != 0:
            print(f"  échec statut {url} : {out[:120]}")

    print(f"Tableau : {project.get('url', '')}")
    if args.dry_run:
        print("(répétition à blanc : rien n'a été modifié)")


def shutil_which(name: str) -> bool:
    import shutil

    return shutil.which(name) is not None


if __name__ == "__main__":
    main()
