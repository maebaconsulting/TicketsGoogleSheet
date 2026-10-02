#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Initialisation automatique avec gcloud.

Automatise ce qui est automatisable, sous VOTRE compte Google :

1. vérifie gcloud et l'authentification (`gcloud auth login`) ;
2. choisit ou crée le projet Google Cloud ;
3. active les API Sheets, Drive et Apps Script ;
4. crée le compte de service et sa clé JSON ;
5. crée le classeur et le partage en Éditeur avec le compte de service ;
6. écrit `config.json`.

Reste à faire par une personne : activer le réglage utilisateur Apps Script
(https://script.google.com/home/usersettings) avant de déployer les formulaires.

Prérequis : gcloud installé (https://cloud.google.com/sdk/docs/install) et
`gcloud auth login` fait une fois.

Usage :
    python3 bootstrap.py --source ../mon-projet [--project MON-PROJET] [--key key.json]
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import config
import new_project

APIS = [
    "sheets.googleapis.com",
    "drive.googleapis.com",
    "script.googleapis.com",
]


def gcloud(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gcloud", *args], capture_output=True, text=True, check=check)


def access_token() -> str:
    return gcloud("auth", "print-access-token").stdout.strip()


def api(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"{method} {url} -> {error.code} : {error.read().decode('utf-8', 'ignore')[:300]}"
        )


def active_account() -> str:
    result = gcloud("auth", "list", "--filter=status:ACTIVE", "--format=value(account)")
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""


def choose_project(wanted: str) -> str:
    if wanted:
        gcloud("projects", "describe", wanted)
        return wanted
    current = gcloud("config", "get-value", "project", check=False).stdout.strip()
    if current and current != "(unset)":
        return current
    project = f"tickets-sheet-{secrets.token_hex(3)}"
    print(f"Création du projet {project} …")
    gcloud("projects", "create", project)
    return project


def service_account_email(project: str) -> str:
    email = gcloud(
        "iam", "service-accounts", "list", "--project", project,
        "--filter=email:export-tickets", "--format=value(email)",
    ).stdout.strip()
    if email:
        return email
    print("Création du compte de service export-tickets …")
    gcloud(
        "iam", "service-accounts", "create", "export-tickets",
        "--display-name", "export-tickets", "--project", project,
    )
    return f"export-tickets@{project}.iam.gserviceaccount.com"


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialisation automatique via gcloud.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--project", default="")
    parser.add_argument("--key", default="key.json")
    parser.add_argument("--sheet-name", default="export-tickets")
    parser.add_argument("--product", default="Backlog")
    parser.add_argument("--convention", choices=["auto", *new_project.CONVENTIONS], default="auto")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not shutil.which("gcloud"):
        raise SystemExit(
            "gcloud est absent. Installez le SDK : "
            "https://cloud.google.com/sdk/docs/install"
        )
    account = active_account()
    if not account:
        raise SystemExit("Non connecté. Lancez d'abord : gcloud auth login")
    print(f"Compte : {account}")

    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"Dépôt introuvable : {source}")

    project = choose_project(args.project)
    print(f"Projet : {project}")

    print("Activation des API Sheets, Drive, Apps Script …")
    gcloud("services", "enable", *APIS, "--project", project)

    email = service_account_email(project)
    key_path = Path(args.key).expanduser()
    print(f"Compte de service : {email}")
    if not key_path.exists():
        gcloud(
            "iam", "service-accounts", "keys", "create", str(key_path),
            "--iam-account", email, "--project", project,
        )
        print(f"Clé écrite : {key_path}")
    else:
        print(f"Clé déjà présente : {key_path}")

    token = access_token()
    print(f"Création du classeur « {args.sheet_name} » …")
    sheet = api(
        "POST", "https://sheets.googleapis.com/v4/spreadsheets", token,
        {"properties": {"title": args.sheet_name}},
    )
    spreadsheet_id = sheet["spreadsheetId"]
    api(
        "POST",
        f"https://www.googleapis.com/drive/v3/files/{spreadsheet_id}/permissions"
        "?sendNotificationEmail=false",
        token,
        {"role": "writer", "type": "user", "emailAddress": email},
    )
    print(f"Classeur partagé en Éditeur avec {email}")

    convention = args.convention if args.convention != "auto" else new_project.detect(source)
    plans_dir, specs_dir = new_project.CONVENTIONS[convention]
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
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": args.sheet_name,
            "credentials": str(key_path),
            "product_name": args.product,
        }
    )
    if config.CONFIG_FILE.exists() and not args.force:
        print(f"config.json existe déjà ({config.CONFIG_FILE}) ; relancez avec --force.")
    else:
        config.CONFIG_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"config.json écrit : {config.CONFIG_FILE}")

    print()
    print("Suite :")
    print("  .venv/bin/python parser.py && .venv/bin/python sheets.py")
    print("Formulaires : activez https://script.google.com/home/usersettings,")
    print("  npx @google/clasp login, puis .venv/bin/python bind_apps_script_user.py")
    print(f"Classeur : https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")


if __name__ == "__main__":
    main()
