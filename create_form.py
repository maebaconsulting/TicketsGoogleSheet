#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crée un Google Form pour recueillir les demandes du métier.

Les réponses du Form alimentent une feuille liée (dans Google Forms, onglet
« Réponses », bouton « Lier à une feuille ») que l'on copie ensuite dans l'onglet
`Demandes`. Si l'API Forms est désactivée, le script explique comment l'activer.

Usage :
    GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json python3 tools/export-tickets/create_form.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import sheets as tool

SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file",
]
QUESTIONS = [
    ("Demandeur", "Qui exprime le besoin ?"),
    ("Besoin", "Quel besoin, dans vos mots ?"),
    ("Impact", "Quel effet attendu sur l'institut ?"),
    ("Priorité", "Indispensable, Importante, Souhaitable ou Plus tard ?"),
]


def key_path() -> str:
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if path and Path(path).exists():
        return path
    for candidate in tool.DEFAULT_KEYS:
        if candidate.exists():
            return str(candidate)
    sys.exit("Clé de compte de service introuvable.")


def main() -> None:
    credentials = service_account.Credentials.from_service_account_file(
        key_path(), scopes=SCOPES
    )
    forms = build("forms", "v1", credentials=credentials)
    try:
        form = forms.forms().create(
            body={"info": {"title": "lama : demandes du métier"}}
        ).execute()
        requests = [
            {
                "updateFormInfo": {
                    "info": {"description": "Recueil des besoins de l'institut."},
                    "updateMask": "description",
                }
            }
        ]
        for title, help_text in QUESTIONS:
            requests.append(
                {
                    "createItem": {
                        "item": {
                            "title": title,
                            "description": help_text,
                            "questionItem": {"question": {"required": title in ("Besoin",)}},
                        },
                        "location": {"index": len(requests)},
                    }
                }
            )
        forms.forms().batchUpdate(formId=form["formId"], body={"requests": requests}).execute()
        print("Formulaire créé.")
        print(f"  Répondre : {form.get('responderUri')}")
        print("  Lier les réponses à une feuille depuis Google Forms, puis copier les lignes")
        print("  dans l'onglet Demandes du classeur.")
    except HttpError as error:
        print(f"API Forms indisponible ({error.status_code}).")
        print("Activez « Google Forms API » dans le projet Google Cloud, puis relancez.")
        print("Sinon, créez le formulaire à la main avec les champs :")
        for title, help_text in QUESTIONS:
            print(f"  - {title} : {help_text}")


if __name__ == "__main__":
    main()
