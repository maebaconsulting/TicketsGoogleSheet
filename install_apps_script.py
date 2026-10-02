#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Installe le projet Apps Script lié au classeur (formulaires lama).

Crée le projet lié et pousse `appsscript.json`, `Code.gs` et `Formulaire.html`
via l'API Apps Script, puis écrit `tools/export-tickets/.clasp.json`.

Prérequis : l'API Apps Script doit être activée sur le projet Google Cloud
(l'installeur affiche le lien exact si ce n'est pas le cas).

Usage :
    GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json python3 tools/export-tickets/install_apps_script.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import sheets as tool

HERE = Path(__file__).resolve().parent
APPS = HERE / "apps-script"
CLASP = HERE / ".clasp.json"
SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/drive.readonly",
]


def files_payload() -> list[dict]:
    manifest = (APPS / "appsscript.json").read_text(encoding="utf-8")
    code = (APPS / "Code.gs").read_text(encoding="utf-8")
    html = (APPS / "Formulaire.html").read_text(encoding="utf-8")
    return [
        {"name": "appsscript", "type": "JSON", "source": manifest},
        {"name": "Code", "type": "SERVER_JS", "source": code},
        {"name": "Formulaire", "type": "HTML", "source": html},
    ]


def activation_url(error: HttpError) -> str | None:
    try:
        details = json.loads(error.content.decode("utf-8"))["error"].get("details", [])
        for detail in details:
            url = detail.get("metadata", {}).get("activationUrl")
            if url:
                return url
    except Exception:
        pass
    return None


def main() -> None:
    credentials = service_account.Credentials.from_service_account_file(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        or str(tool.DEFAULT_KEYS[0]),
        scopes=SCOPES,
    )
    script = build("script", "v1", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)
    spreadsheet_id = tool.CFG["spreadsheet_id"] or tool.find_spreadsheet(drive)

    script_id = ""
    if CLASP.exists():
        script_id = json.loads(CLASP.read_text(encoding="utf-8")).get("scriptId", "")

    try:
        if not script_id:
            project = script.projects().create(
                body={"title": "lama saisie", "parentId": spreadsheet_id}
            ).execute(num_retries=3)
            script_id = project["scriptId"]
            print(f"Projet Apps Script créé : {script_id}")
        script.projects().updateContent(
            scriptId=script_id, body={"files": files_payload()}
        ).execute(num_retries=3)
        print("Code et formulaire déployés.")
        CLASP.write_text(
            json.dumps({"scriptId": script_id, "rootDir": "apps-script"}, indent=2),
            encoding="utf-8",
        )
        print(f".clasp.json écrit : {CLASP}")
        print("Dans le classeur : Extensions > Apps Script (le projet est lié), puis")
        print("recharger la page ; le menu « lama » apparaît. Autorisez au premier usage.")
    except HttpError as error:
        if error.status_code == 403:
            content = error.content.decode("utf-8", errors="ignore")
            if "home/usersettings" in content:
                print("L'API Apps Script exige un compte utilisateur, pas un compte de service.")
                print("Un compte de service ne peut pas activer ce réglage.")
                print("Deux voies possibles :")
                print("  1. Déploiement par clasp, sous votre compte Google :")
                print("       npx @google/clasp login")
                print("       cd tools/export-tickets")
                print("       npx @google/clasp create --type sheets \\")
                print('         --title "lama saisie" --parentId <SHEET_ID> --rootDir apps-script')
                print("       npx @google/clasp push -f")
                print("     (activer d'abord l'API ici : https://script.google.com/home/usersettings)")
                print("  2. Collage manuel : Extensions > Apps Script, coller Code.gs et Formulaire.html.")
                sys.exit(2)
            url = activation_url(error)
            print("L'API Apps Script est désactivée sur le projet Google Cloud.")
            if url:
                print(f"Activez-la ici (une fois) : {url}")
            print("Puis relancez : python3 tools/export-tickets/install_apps_script.py")
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
