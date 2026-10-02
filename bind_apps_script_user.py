#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lie un projet Apps Script au classeur existant, sous VOTRE compte (OAuth clasp).

Utilise les identifiants déjà stockés par `clasp login` (~/.clasprc.json), crée un
script **lié** au classeur (parentId = identifiant du classeur), pousse
`appsscript.json`, `Code.gs` et `Formulaire.html`, écrit `.clasp.json`, et met à la
corbeille un classeur créé par erreur par `clasp create`.

Usage :
    python3 tools/export-tickets/bind_apps_script_user.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

HERE = Path(__file__).resolve().parent
APPS = HERE / "apps-script"
CLASP = HERE / ".clasp.json"
CFG = config.load()
SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/drive.file",
]


def user_credentials() -> Credentials:
    store = json.loads((Path.home() / ".clasprc.json").read_text(encoding="utf-8"))
    tokens = store["tokens"]["default"]
    credentials = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=tokens.get("client_id"),
        client_secret=tokens.get("client_secret"),
        scopes=SCOPES,
    )
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials


def files_payload() -> list[dict]:
    code = (APPS / "Code.gs").read_text(encoding="utf-8")
    code = code.replace("__PRODUCT__", CFG["product_name"])
    return [
        {"name": "appsscript", "type": "JSON",
         "source": (APPS / "appsscript.json").read_text(encoding="utf-8")},
        {"name": "Code", "type": "SERVER_JS", "source": code},
        {"name": "Formulaire", "type": "HTML",
         "source": (APPS / "Formulaire.html").read_text(encoding="utf-8")},
    ]


def discover_sheet(drive) -> str:
    name = CFG["sheet_name"].replace("'", "\\'")
    query = (f"name = '{name}' and trashed = false "
             "and mimeType = 'application/vnd.google-apps.spreadsheet'")
    files = drive.files().list(q=query, spaces="drive", fields="files(id)").execute(
        num_retries=3
    ).get("files", [])
    if not files:
        raise SystemExit(
            f"Aucun classeur « {CFG['sheet_name']} » accessible. "
            "Renseignez spreadsheet_id dans config.json."
        )
    return files[0]["id"]


def cleanup(drive, accidental_doc: str, accidental_script: str) -> None:
    for file_id in (accidental_doc, accidental_script):
        if not file_id:
            continue
        try:
            drive.files().update(fileId=file_id, body={"trashed": True}).execute(num_retries=3)
            print(f"  mis à la corbeille : {file_id}")
        except HttpError as error:
            print(f"  à supprimer manuellement : {file_id} ({error.status_code})")


def main() -> None:
    previous = {}
    if CLASP.exists():
        previous = json.loads(CLASP.read_text(encoding="utf-8"))

    credentials = user_credentials()
    script = build("script", "v1", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)
    sheet_id = CFG["spreadsheet_id"] or discover_sheet(drive)

    project = script.projects().create(
        body={"title": "lama saisie", "parentId": sheet_id}
    ).execute(num_retries=3)
    script_id = project["scriptId"]
    print(f"Projet lié au classeur créé : {script_id}")

    script.projects().updateContent(
        scriptId=script_id, body={"files": files_payload()}
    ).execute(num_retries=3)
    print("Code et formulaire déployés.")

    CLASP.write_text(
        json.dumps(
            {"scriptId": script_id, "rootDir": "apps-script", "parentId": sheet_id},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f".clasp.json écrit : {CLASP}")

    accidental_doc = previous.get("parentId", "")
    accidental_script = previous.get("scriptId", "")
    if accidental_doc and accidental_doc != sheet_id:
        print("Nettoyage du classeur créé par erreur :")
        cleanup(drive, accidental_doc, accidental_script)

    print("Ouvrez le classeur : recharger la page, menu « lama » dans la barre.")


if __name__ == "__main__":
    main()
