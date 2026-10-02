#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export PDF de la revue hebdomadaire.

Exporte le classeur entier en PDF (Drive) dans
`tools/export-tickets/out/revue-AAAA-MM-JJ.pdf`.

Usage :
    GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json python3 tools/export-tickets/export_pdf.py
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from googleapiclient.discovery import build

import sheets as tool

OUT_DIR = Path(__file__).resolve().parent / "out"


def main() -> None:
    credentials = tool.load_credentials()
    drive = build("drive", "v3", credentials=credentials)
    spreadsheet_id = tool.CFG["spreadsheet_id"] or tool.find_spreadsheet(drive)

    data = drive.files().export(fileId=spreadsheet_id, mimeType="application/pdf").execute()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"revue-{date.today().isoformat()}.pdf"
    path.write_bytes(data)
    print(f"PDF de revue : {path} ({len(data) // 1024} Ko)")


if __name__ == "__main__":
    main()
