#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boucle retour : lit les décisions du métier dans le classeur et les ramène au dépôt.

Écrit :
- `tools/export-tickets/out/backlog.json` : priorités, décisions et responsables par récit ;
- `docs/superpowers/DECISIONS.md` : journal des décisions validées ;
- `tools/export-tickets/out/issues-sync.sh` : si `issue-map.csv` (id,github,gitlab)
  existe, commandes `gh`/`glab` pour aligner les labels des issues.

Usage :
    GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json python3 tools/export-tickets/sync_back.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build

import sheets as tool
import config

TOOL_DIR = Path(__file__).resolve().parent
OUT_DIR = TOOL_DIR / "out"
PATHS = config.resolved()
DECISIONS_MD = PATHS["decisions"]
ISSUE_MAP = PATHS["issue_map"]

FIELDS = {
    "Priorité": "priorite",
    "Statut métier": "statut_metier",
    "Décision": "decision",
    "Porteur": "porteur",
    "Relecteur": "relecteur",
    "Validateur": "validateur",
    "Échéance": "echeance",
    "Commentaire": "commentaire",
    "Valeur": "valeur",
    "Effort": "effort",
    "Avancement": "avancement",
}


def read_recits(sheets, spreadsheet_id: str) -> list[dict]:
    values = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Récits métier'!A1:X")
        .execute(num_retries=5)
        .get("values", [])
    )
    if not values:
        return []
    header = values[0]
    index = {name: i for i, name in enumerate(header)}
    recits = []
    for row in values[1:]:
        if not row or not row[index["ID"]]:
            continue

        def cell(name: str) -> str:
            i = index.get(name)
            return row[i] if i is not None and i < len(row) else ""

        entry = {"id": cell("ID"), "recit": cell("Récit"), "domaine": cell("Domaine")}
        for name, key in FIELDS.items():
            entry[key] = cell(name)
        recits.append(entry)
    return recits


def write_backlog(recits: list[dict], generated: str) -> Path:
    path = OUT_DIR / "backlog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generatedAt": generated, "recits": {r["id"]: r for r in recits}}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_decisions(recits: list[dict], generated: str) -> Path:
    lines = ["# Journal des décisions", "", f"Mise à jour : {generated}.", "",
             "Décisions prises par le métier dans le classeur (onglet Récits métier).", "",
             "| Récit | Domaine | Priorité | Décision | Statut | Validateur | Commentaire |",
             "|---|---|---|---|---|---|---|"]
    rows = [
        r for r in recits
        if r["decision"] or r["statut_metier"] or r["validateur"]
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['domaine']} | {r['priorite']} | {r['decision']} | "
            f"{r['statut_metier']} | {r['validateur']} | {r['commentaire']} |"
        )
    if not rows:
        lines.append("| - | - | - | Aucune décision enregistrée | - | - | - |")
    lines.append("")
    DECISIONS_MD.parent.mkdir(parents=True, exist_ok=True)
    DECISIONS_MD.write_text("\n".join(lines), encoding="utf-8")
    return DECISIONS_MD


def write_issue_sync(recits: list[dict]) -> Path | None:
    if not ISSUE_MAP.exists():
        return None
    mapping = {}
    with ISSUE_MAP.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("id"):
                mapping[row["id"]] = row
    by_id = {r["id"]: r for r in recits}
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", "", "# Alignement des issues sur les décisions du métier"]
    for rid, row in mapping.items():
        r = by_id.get(rid)
        if not r:
            continue
        labels = [f"statut:{r['statut_metier'] or 'a-cadrer'}"]
        if r["priorite"]:
            labels.append(f"priorite:{r['priorite']}")
        joined = ",".join(labels)
        if row.get("github"):
            lines.append(f'gh issue edit {row["github"]} --add-label "{joined}" || true')
        if row.get("gitlab"):
            lines.append(f'glab issue update {row["gitlab"]} --label "{joined}" || true')
    path = OUT_DIR / "issues-sync.sh"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    credentials = tool.load_credentials()
    sheets = build("sheets", "v4", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)
    spreadsheet_id = os.environ.get("SHEET_ID") or tool.find_spreadsheet(drive)
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    recits = read_recits(sheets, spreadsheet_id)
    backlog = write_backlog(recits, generated)
    decisions = write_decisions(recits, generated)
    sync = write_issue_sync(recits)

    print(f"Récits lus        : {len(recits)}")
    print(f"Backlog           : {backlog}")
    print(f"Décisions         : {decisions}")
    if sync:
        print(f"Synchronisation   : {sync}")
    else:
        print("Synchronisation   : issue-map.csv absent (id,github,gitlab) - ignorée")


if __name__ == "__main__":
    main()
