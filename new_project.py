#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Démarre TicketsGoogleSheet sur un nouveau projet.

Détecte la convention d'artefacts du dépôt source, écrit `config.json` et
explique la suite. Reconnaît les outils courants :

- plans   : `docs/superpowers/plans/*.md` (convention plans/specs) ;
- gsd     : `.planning/` (ROADMAP.md, `phases/**/*-PLAN.md` avec `<task>`) ;
- tickets : `.scratch/<feature>/issues/NN-*.md` (tickets Markdown locaux) ;
- agent   : aucun plan reconnu ; les récits viennent de l'agent backlog-architect.

Usage :
    python3 new_project.py --source ../mon-projet --sheet <id> --credentials key.json
    python3 new_project.py --source ../mon-projet --convention gsd --run
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import config

CONVENTIONS = {
    "plans": ("docs/superpowers/plans", "docs/superpowers/specs"),
    "gsd": (".planning", ".planning"),
    "tickets": (".scratch", ".scratch"),
    "agent": ("docs", "docs"),
}


def detect(source: Path) -> str:
    if (source / "docs" / "superpowers" / "plans").is_dir():
        return "plans"
    if (source / ".planning").is_dir():
        return "gsd"
    if (source / ".scratch").is_dir():
        return "tickets"
    return "agent"


def is_git_repo(source: Path) -> bool:
    try:
        subprocess.run(["git", "-C", str(source), "rev-parse", "--git-dir"],
                       capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Configurer TicketsGoogleSheet pour un projet.")
    parser.add_argument("--source", required=True, help="dépôt à analyser")
    parser.add_argument("--convention", choices=["auto", *CONVENTIONS], default="auto")
    parser.add_argument("--sheet", default="", help="identifiant du classeur Google")
    parser.add_argument("--sheet-name", default="export-tickets")
    parser.add_argument("--credentials", default="key.json")
    parser.add_argument("--product", default="Backlog")
    parser.add_argument("--github", default="")
    parser.add_argument("--gitlab", default="")
    parser.add_argument("--force", action="store_true", help="écraser config.json")
    parser.add_argument("--run", action="store_true", help="lancer parser.py ensuite")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"Dépôt introuvable : {source}")

    convention = args.convention if args.convention != "auto" else detect(source)
    plans_dir, specs_dir = CONVENTIONS[convention]

    data = dict(config.DEFAULTS)
    try:
        data["source_repo"] = str(source.relative_to(config.TOOL_DIR))
    except ValueError:
        data["source_repo"] = str(source)
    data.update(
        {
            "convention": convention,
            "plans_dir": plans_dir,
            "specs_dir": specs_dir,
            "spreadsheet_id": args.sheet,
            "sheet_name": args.sheet_name,
            "credentials": args.credentials,
            "product_name": args.product,
            "github_repo": args.github,
            "gitlab_project": args.gitlab,
        }
    )

    target = config.CONFIG_FILE
    if target.exists() and not args.force:
        raise SystemExit(
            f"config.json existe déjà ({target}). Relancez avec --force pour l'écraser."
        )
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Convention détectée : {convention}  ({plans_dir})")
    print(f"config.json écrit    : {target}")
    if not is_git_repo(source):
        print("AVERTISSEMENT : la source n'est pas un dépôt git ; les statuts seront vides.")
    if convention == "agent":
        print("Aucun plan reconnu : générez les récits avec l'agent backlog-architect,")
        print("puis lancez parser.py et sheets.py.")
    else:
        print("Suite :")
        print("  .venv/bin/python parser.py")
        print("  .venv/bin/python sheets.py")
    if args.run:
        from parser import main as parse_main  # import local après écriture de la config

        parse_main()


if __name__ == "__main__":
    main()
