#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration de TicketsGoogleSheet.

La configuration est lue dans cet ordre (le plus fort gagne) :
1. variables d'environnement ;
2. `config.json` à la racine de l'outil (ignoré par git) ;
3. valeurs par défaut ci-dessous.

Les chemins relatifs sont résolus par rapport à la racine de l'outil, sauf
`plans_dir`, `specs_dir` et `decisions_path`, qui le sont par rapport au dépôt
analysé (`source_repo`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
CONFIG_FILE = TOOL_DIR / "config.json"

DEFAULTS = {
    "source_repo": ".",
    "convention": "plans",
    "plans_dir": "docs/superpowers/plans",
    "specs_dir": "docs/superpowers/specs",
    "decisions_path": "docs/superpowers/DECISIONS.md",
    "main_branch": "main",
    "github_repo": "",
    "gitlab_project": "",
    "spreadsheet_id": "",
    "sheet_name": "export-tickets",
    "credentials": "key.json",
    "stories_file": "stories.json",
    "generated_dir": "generated",
    "people_file": "people.json",
    "issue_map": "issue-map.csv",
    "product_name": "Tickets Google Sheet",
}

ENV_MAP = {
    "source_repo": "SOURCE_REPO",
    "convention": "CONVENTION",
    "plans_dir": "PLANS_DIR",
    "specs_dir": "SPECS_DIR",
    "decisions_path": "DECISIONS_PATH",
    "main_branch": "MAIN_BRANCH",
    "github_repo": "GITHUB_REPO",
    "gitlab_project": "GITLAB_PROJECT",
    "spreadsheet_id": "SHEET_ID",
    "sheet_name": "SHEET_NAME",
    "credentials": "GOOGLE_APPLICATION_CREDENTIALS",
    "stories_file": "STORIES_FILE",
    "generated_dir": "GENERATED_DIR",
    "people_file": "PEOPLE_FILE",
    "product_name": "PRODUCT_NAME",
}


def load() -> dict:
    data = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        data.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    for key, env in ENV_MAP.items():
        value = os.environ.get(env)
        if value:
            data[key] = value
    return data


def tool_path(value: str) -> Path:
    """Chemin relatif à la racine de l'outil."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (TOOL_DIR / path).resolve()


def source_path(cfg: dict) -> Path:
    """Chemin du dépôt analysé, résolu par rapport à la racine de l'outil."""
    return tool_path(cfg["source_repo"])


def source_file(cfg: dict, key: str) -> Path:
    """Fichier du dépôt analysé (plans_dir, specs_dir, decisions_path)."""
    path = Path(cfg[key]).expanduser()
    return path if path.is_absolute() else (source_path(cfg) / path)


# Chemins résolus, prêts à l'emploi.
def resolved(cfg: dict | None = None) -> dict:
    cfg = cfg or load()
    return {
        "source": source_path(cfg),
        "plans": source_file(cfg, "plans_dir"),
        "specs": source_file(cfg, "specs_dir"),
        "decisions": source_file(cfg, "decisions_path"),
        "stories": tool_path(cfg["stories_file"]),
        "generated": tool_path(cfg["generated_dir"]),
        "people": tool_path(cfg["people_file"]),
        "issue_map": tool_path(cfg["issue_map"]),
        "credentials": tool_path(cfg["credentials"]),
    }


if __name__ == "__main__":
    import pprint

    pprint.pprint(resolved())
