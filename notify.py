#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Relances collaboratives : décisions en attente et échéances dépassées.

Construit un condensé depuis le classeur et le publie sur un webhook si
`NOTIFY_WEBHOOK` est défini (format Slack entrant : `{"text": "..."}`).

Usage :
    GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json \
    NOTIFY_WEBHOOK=https://hooks.slack.com/... \
    python3 tools/export-tickets/notify.py

Sans webhook, le condensé est seulement affiché (utile en cron pour les journaux).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime

from googleapiclient.discovery import build

import sheets as tool


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
    idx = {name: i for i, name in enumerate(header)}

    def cell(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else ""

    recits = []
    for row in values[1:]:
        if not row or not row[idx["ID"]]:
            continue
        recits.append(
            {
                "id": cell(row, "ID"),
                "recit": cell(row, "Récit"),
                "decision": cell(row, "Décision"),
                "statut": cell(row, "Statut métier"),
                "echeance": cell(row, "Échéance"),
                "avancement": cell(row, "Avancement"),
                "porteur": cell(row, "Porteur"),
            }
        )
    return recits


def parse_date(text: str):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def build_digest(recits: list[dict]) -> str:
    today = date.today()
    pending = [r for r in recits if r["decision"] == "En attente"]
    late = []
    for r in recits:
        due = parse_date(r["echeance"])
        if due and due < today and r["avancement"] != "Livré":
            late.append(r)
    lines = [f"lama : revue du {today.strftime('%d/%m/%Y')}"]
    lines.append(f"- À décider : {len(pending)} récit(s)")
    for r in pending[:10]:
        lines.append(f"    {r['id']} {r['recit'][:80]}")
    lines.append(f"- En retard : {len(late)} récit(s)")
    for r in late[:10]:
        lines.append(f"    {r['id']} échéance {r['echeance']} ({r['porteur'] or 'sans porteur'})")
    return "\n".join(lines)


def publish(text: str) -> None:
    url = os.environ.get("NOTIFY_WEBHOOK")
    if not url:
        return
    body = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        print(f"Webhook : {response.status}")


def main() -> None:
    credentials = tool.load_credentials()
    sheets = build("sheets", "v4", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)
    spreadsheet_id = tool.CFG["spreadsheet_id"] or tool.find_spreadsheet(drive)

    recits = read_recits(sheets, spreadsheet_id)
    digest = build_digest(recits)
    print(digest)
    publish(digest)


if __name__ == "__main__":
    main()
