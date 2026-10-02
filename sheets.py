#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Habille et remplit le classeur Google « export-tickets ».

Espace de travail métier et ingénierie : accueil, récits éditables, décisions,
demandes, tickets, plans, specs, référentiels et tableau de bord graphique.

Collaboration : colonnes éditables préservées par identifiant, priorisation
Valeur/Effort avec quadrant, vues filtrées par rôle, notes d'en-tête, alerte sur
échéances dépassées, protection des colonnes générées et, si `people.json` fournit
les adresses du métier, édition réservée à ces personnes.

Usage :
    GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json python3 tools/export-tickets/sheets.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

TOOL_DIR = Path(__file__).resolve().parent
CFG = config.load()
PATHS = config.resolved(CFG)
SHEETS_DIR = TOOL_DIR / "out" / "sheets"
PEOPLE_FILE = PATHS["people"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
TABS = [
    "Accueil",
    "Récits métier",
    "Décisions",
    "Demandes",
    "Tickets",
    "Plans",
    "Specs",
    "Référentiels",
    "Tableau de bord",
]
DATA_TABS = ["Récits métier", "Tickets", "Plans", "Specs", "Référentiels"]
FILE_FOR = {"Récits métier": "Recits", "Référentiels": "Referentiels"}
DEFAULT_KEYS = [PATHS["credentials"]]

# Charte inspirée de monday.com : tableaux clairs, bandes couleur, pastilles vives,
# texte anthracite. Palette monday : bleu #0073EA, vert #00C875, orange #FDAB3D,
# rouge #E2445C, bleu clair #579BFC, violet #A25DDC, jaune #FFCB00, gris #C4C4C4.
WHITE = "#FFFFFF"
HEADER_BG = "#F5F6F8"
SURFACE_ALT = "#F7F8FB"
TEXT = "#323338"
SUBTLE = "#676879"
BORDER = "#E6E9EF"
BRAND = "#0073EA"
INK = BRAND
INK_SOFT = "#0B5FBF"
IVORY = HEADER_BG
GREY = SUBTLE
LINE = BORDER
AMBER_BG = "#FFF7DB"
AMBER_FG = "#7A5C12"
LINK = BRAND

GREEN_BG, GREEN_FG = "#00C875", "#FFFFFF"
ORANGE_BG, ORANGE_FG = "#FDAB3D", "#323338"
BLUE_BG, BLUE_FG = "#579BFC", "#FFFFFF"
DARKBLUE_BG, DARKBLUE_FG = "#0086C0", "#FFFFFF"
PURPLE_BG, PURPLE_FG = "#A25DDC", "#FFFFFF"
GREY_BG, GREY_FG = "#C4C4C4", "#323338"
RED_BG, RED_FG = "#E2445C", "#FFFFFF"
YELLOW_BG, YELLOW_FG = "#FFCB00", "#323338"

ROLE_COLORS = {
    "gérante": (PURPLE_BG, PURPLE_FG),
    "réception": (BLUE_BG, BLUE_FG),
    "praticienne": (DARKBLUE_BG, DARKBLUE_FG),
    "technicien": (GREY_BG, GREY_FG),
}

# Couleurs de groupe par domaine (bandes monday), attribuées dans l'ordre alphabétique.
DOMAIN_CHIPS = [
    (YELLOW_BG, YELLOW_FG), (GREEN_BG, GREEN_FG), (ORANGE_BG, ORANGE_FG),
    (BLUE_BG, BLUE_FG), (PURPLE_BG, PURPLE_FG), (DARKBLUE_BG, DARKBLUE_FG),
    (RED_BG, RED_FG), ("#66CCFF", "#323338"), ("#9CD326", "#323338"),
]

# Indices de colonnes de l'onglet Récits métier (0 = A).
C_PRIORITE, C_STATUT, C_DECISION = 7, 8, 9
C_PORTEUR, C_RELECTEUR, C_VALIDATEUR = 10, 11, 12
C_ECHEANCE, C_COMMENTAIRE = 13, 14
C_VALEUR, C_EFFORT, C_SCORE = 15, 16, 17
C_AVANCEMENT, C_ORIGINE = 18, 19
C_ALERTE = 23
RECITS_COLS = 24
EDITABLE_START, EDITABLE_END = 7, 17  # H à Q inclus (l'édition s'arrête à Effort)

RECIT_NOTES = {
    0: "Identifiant stable du récit. Ne pas modifier.",
    1: "Domaine métier du récit.",
    2: "Personne principalement concernée.",
    3: "Nom court de la capacité.",
    4: "Récit au format « En tant que…, je veux…, afin de… ».",
    5: "Valeur métier apportée.",
    6: "Critères qui disent qu'un récit est satisfait.",
    7: "Indispensable, Importante, Souhaitable ou Plus tard (liste déroulante).",
    8: "À cadrer, À valider, Validé, En cours, Livré ou Refusé.",
    9: "En attente, Validée, À revoir ou Refusée.",
    10: "Personne qui porte le récit (voir la liste Personne dans Référentiels).",
    11: "Personne qui relit (RACI).",
    12: "Personne qui valide (RACI).",
    13: "Date au format jj/mm/aaaa. Passe en rouge si dépassée et non livrée.",
    14: "Commentaire libre du métier.",
    15: "Valeur de 1 (faible) à 5 (forte).",
    16: "Effort de 1 (faible) à 5 (fort).",
    17: "Score Valeur / Effort, calculé.",
    18: "Avancement calculé depuis git. Ne pas modifier.",
    19: "manuel ou analyse du code.",
    20: "Plans de mise en œuvre liés.",
    21: "Tickets d'ingénierie liés.",
    22: "Fichiers qui justifient un récit généré.",
    23: "Calculé : « En retard » si l'échéance est dépassée et le récit non livré.",
}

DEMANDE_HEADERS = [
    "ID", "Date", "Demandeur", "Besoin", "Récit proposé", "Impact",
    "Priorité", "Statut", "Commentaire",
]
DEMANDE_NOTES = {
    0: "Identifiant de la demande (DEM-001, DEM-002…).",
    1: "Date de la demande.",
    2: "Personne qui exprime le besoin.",
    3: "Besoin exprimé, dans les mots du métier.",
    4: "Récit proposé, si utile.",
    5: "Effet attendu sur l'institut.",
    6: "Indispensable, Importante, Souhaitable ou Plus tard.",
    7: "À cadrer, À valider, Retenu ou Refusé.",
    8: "Commentaire.",
}

DECISION_HEADERS = [
    "Date", "Récit", "Domaine", "Priorité", "Décision", "Statut métier",
    "Validateur", "Échéance", "Commentaire",
]


def rgb(hex_color: str) -> dict:
    value = hex_color.lstrip("#")
    return {
        "red": int(value[0:2], 16) / 255,
        "green": int(value[2:4], 16) / 255,
        "blue": int(value[4:6], 16) / 255,
    }


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def load_people() -> dict:
    if PEOPLE_FILE.exists():
        return json.loads(PEOPLE_FILE.read_text(encoding="utf-8"))
    return {}


def load_credentials():
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if path and Path(path).exists():
        return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    for candidate in DEFAULT_KEYS:
        if candidate.exists():
            return service_account.Credentials.from_service_account_file(
                str(candidate), scopes=SCOPES
            )
    sys.exit(
        "Clé de compte de service introuvable : renseignez "
        "GOOGLE_APPLICATION_CREDENTIALS ou déposez key.json dans ce dossier."
    )


def find_spreadsheet(drive) -> str:
    name = CFG["sheet_name"].replace("'", "\\'")
    query = (
        f"name = '{name}' "
        "and mimeType = 'application/vnd.google-apps.spreadsheet' "
        "and trashed = false"
    )
    result = (
        drive.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id,name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute(num_retries=5)
    )
    files = result.get("files", [])
    if not files:
        sys.exit(
            f"Aucun classeur « {CFG['sheet_name']} » partagé avec le compte de service. "
            "Vérifiez le partage (Éditeur) ou renseignez spreadsheet_id."
        )
    if len(files) > 1:
        print(f"Plusieurs classeurs trouvés, le premier est utilisé : {files[0]['id']}")
    return files[0]["id"]


def ensure_tabs(sheets, spreadsheet_id: str) -> dict[str, int]:
    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute(num_retries=5)
    ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    requests = []
    extras = [title for title in ids if title not in TABS]
    if "Récits métier" not in ids and extras:
        default = extras.pop(0)
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": ids[default], "title": "Récits métier"},
                    "fields": "title",
                }
            }
        )
        ids["Récits métier"] = ids.pop(default)
    for title in TABS:
        if title not in ids:
            requests.append({"addSheet": {"properties": {"title": title}}})
    for title in extras:
        requests.append({"deleteSheet": {"sheetId": ids[title]}})
    if requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute(num_retries=5)

    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute(num_retries=5)
    ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    order = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": ids[title], "index": index},
                "fields": "index",
            }
        }
        for index, title in enumerate(TABS)
        if title in ids
    ]
    if order:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": order}
        ).execute(num_retries=5)
    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute(num_retries=5)
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}


def write_tab(sheets, spreadsheet_id, title, rows, raw=True) -> None:
    sheets.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range=f"'{title}'"
    ).execute(num_retries=5)
    if rows:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{title}'!A1",
            valueInputOption="RAW" if raw else "USER_ENTERED",
            body={"values": rows},
        ).execute(num_retries=5)


def preserve_recit_edits(sheets, spreadsheet_id: str) -> dict[str, list[str]]:
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Récits métier'!A2:Q")
        .execute(num_retries=5)
    )
    preserved: dict[str, list[str]] = {}
    for row in result.get("values", []):
        if not row or not row[0]:
            continue
        row = row + [""] * (EDITABLE_END - EDITABLE_START)
        preserved[row[0]] = row[EDITABLE_START:EDITABLE_END]
    return preserved


def overlay_recit_edits(rows, preserved) -> list[list[str]]:
    out = []
    width = EDITABLE_END - EDITABLE_START
    for row in rows:
        row = list(row)
        if row and row[0] in preserved:
            row = row + [""] * (EDITABLE_END - len(row))
            row[EDITABLE_START:EDITABLE_END] = preserved[row[0]][:width]
        out.append(row)
    return out


def read_values(sheets, spreadsheet_id, a1: str) -> list[list[str]]:
    return (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=a1)
        .execute(num_retries=5)
        .get("values", [])
    )


def read_existing_recits(sheets, spreadsheet_id) -> list[list[str]]:
    """Récits présents dans la feuille (dont ceux créés depuis le classeur)."""
    rows = read_values(sheets, spreadsheet_id, "'Récits métier'!A2:X")
    return [r + [""] * (RECITS_COLS - len(r)) for r in rows if r and r[0]]


def read_existing_demandes(sheets, spreadsheet_id) -> list[list[str]]:
    rows = read_values(sheets, spreadsheet_id, "Demandes!A2:I")
    return [r for r in rows if any(str(c).strip() for c in r)]


# --- Constructeurs de requêtes ------------------------------------------------


def rng(gid, r0, r1, c0, c1) -> dict:
    return {
        "sheetId": gid,
        "startRowIndex": r0,
        "endRowIndex": r1,
        "startColumnIndex": c0,
        "endColumnIndex": c1,
    }


def repeat(gid, r0, r1, c0, c1, fmt, fields) -> dict:
    return {
        "repeatCell": {
            "range": rng(gid, r0, r1, c0, c1),
            "cell": {"userEnteredFormat": fmt},
            "fields": f"userEnteredFormat({fields})",
        }
    }


def merge(gid, r0, r1, c0, c1) -> dict:
    return {"mergeCells": {"range": rng(gid, r0, r1, c0, c1), "mergeType": "MERGE_ALL"}}


def banding(gid, r0, r1, c0, c1) -> dict:
    return {
        "addBanding": {
            "bandedRange": {
                "range": rng(gid, r0, r1, c0, c1),
                "rowProperties": {
                    "firstBandColor": rgb(WHITE),
                    "secondBandColor": rgb(SURFACE_ALT),
                },
            }
        }
    }


def col_width(gid, index, pixels) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": index, "endIndex": index + 1},
            "properties": {"pixelSize": pixels},
            "fields": "pixelSize",
        }
    }


def row_height(gid, index, pixels) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": gid, "dimension": "ROWS", "startIndex": index, "endIndex": index + 1},
            "properties": {"pixelSize": pixels},
            "fields": "pixelSize",
        }
    }


def conditional(gid, r0, r1, column, text, bg, fg, bold=False) -> dict:
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [rng(gid, r0, r1, column, column + 1)],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": text}]},
                    "format": {
                        "backgroundColor": rgb(bg),
                        "textFormat": {"foregroundColor": rgb(fg), "bold": bold},
                    },
                },
            },
            "index": 0,
        }
    }


def custom_conditional(gid, r0, r1, column, formula, bg, fg, bold=False) -> dict:
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [rng(gid, r0, r1, column, column + 1)],
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]},
                    "format": {
                        "backgroundColor": rgb(bg),
                        "textFormat": {"foregroundColor": rgb(fg), "bold": bold},
                    },
                },
            },
            "index": 0,
        }
    }


def gradient(gid, r0, r1, c0, c1, min_color=WHITE, max_color=INK_SOFT) -> dict:
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [rng(gid, r0, r1, c0, c1)],
                "gradientRule": {
                    "minpoint": {"color": rgb(min_color), "type": "MIN"},
                    "maxpoint": {"color": rgb(max_color), "type": "MAX"},
                },
            },
            "index": 0,
        }
    }


def validation(gid, rows, start_col, end_col, ref) -> dict:
    return {
        "setDataValidation": {
            "range": rng(gid, 1, rows + 1, start_col, end_col),
            "rule": {
                "condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": ref}]},
                "showCustomUi": True,
                "strict": False,
            },
        }
    }


def number_between(gid, rows, column, low, high) -> dict:
    """Validation numérique : stocke un nombre, pas du texte (score et matrice)."""
    return {
        "setDataValidation": {
            "range": rng(gid, 1, rows + 1, column, column + 1),
            "rule": {
                "condition": {
                    "type": "NUMBER_BETWEEN",
                    "values": [
                        {"userEnteredValue": str(low)},
                        {"userEnteredValue": str(high)},
                    ],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    }


def protect(gid, r0, r1, c0, c1, editors) -> dict:
    protected = {"range": rng(gid, r0, r1, c0, c1), "warningOnly": False}
    if editors:
        protected["editors"] = {"users": editors}
    else:
        protected["warningOnly"] = True
    return {"addProtectedRange": {"protectedRange": protected}}


def note(gid, column, text) -> dict:
    return {
        "updateCells": {
            "range": rng(gid, 0, 1, column, column + 1),
            "rows": [{"values": [{"note": text}]}],
            "fields": "note",
        }
    }


def filter_view(title, gid, rows, column, value) -> dict:
    return {
        "addFilterView": {
            "filter": {
                "title": title,
                "range": rng(gid, 0, rows + 1, 0, RECITS_COLS),
                "criteria": {
                    str(column): {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]}
                    }
                },
            }
        }
    }


# --- Page d'accueil -----------------------------------------------------------


def build_home(ids, sep, generated) -> list[list[str]]:
    def countif(sheet_column, value):
        return f'=COUNTIF({sheet_column}{sep}"{value}")'

    nav = ["Accueil", "Récits métier", "Décisions", "Demandes", "Tickets",
           "Plans", "Specs", "Référentiels", "Tableau de bord"]
    rows = [
        ["lama : backlog produit"],
        ["Récits métier et tickets d'ingénierie, générés depuis le dépôt. Travail collaboratif."],
        [f"Dernière génération : {generated}"],
        [],
        ["Récits métier", "", "Tickets", "", "Livrés", "", "À décider", "", "En retard"],
        [
            "=COUNTA('Récits métier'!A2:A)", "",
            "=COUNTA(Tickets!A2:A)", "",
            countif("Tickets!J2:J", "fait"), "",
            countif("'Récits métier'!J2:J", "En attente"), "",
            countif("'Récits métier'!X2:X", "En retard"), "",
        ],
        [],
        ["Naviguer"],
    ]
    for name in nav:
        rows.append([f'=HYPERLINK("#gid={ids[name]}"{sep}"{name}")'])
    rows += [
        [],
        ["Légende des statuts"],
        ["Fait / Livré", "Travail terminé et fusionné."],
        ["En cours", "Travail commencé, non terminé."],
        ["À faire", "Identifié, pas encore commencé."],
        ["Remplacé / Refusé", "Hors périmètre ou remplacé."],
        [],
        ["Colonnes éditables", "Récits métier : colonnes H à Q (Priorité, Statut, Décision, "
         "Porteur, Relecteur, Validateur, Échéance, Commentaire, Valeur, Effort). "
         "Score, Avancement et Alerte sont calculés. Vues filtrées : gérante, réception, "
         "praticienne, À décider, En retard."],
        ["Demandes", "Onglet Demandes : recueillir un besoin du métier sans toucher au backlog."],
        ["Décisions", "Onglet Décisions : trace des récits ayant un statut, une décision ou un validateur."],
    ]
    return rows


def format_home(gid, service_email) -> list[dict]:
    editors = [service_email] if service_email else []
    reqs = [
        merge(gid, 0, 1, 0, 9),
        merge(gid, 1, 2, 0, 9),
        merge(gid, 2, 3, 0, 9),
        merge(gid, 7, 8, 0, 9),
        merge(gid, 9, 10, 0, 9),
        merge(gid, 15, 16, 0, 9),
        merge(gid, 19, 20, 0, 9),
        repeat(gid, 0, 1, 0, 9,
               {"backgroundColor": rgb(INK), "textFormat": {"bold": True, "foregroundColor": rgb(WHITE), "fontSize": 20}},
               "backgroundColor,textFormat"),
        row_height(gid, 0, 48),
        repeat(gid, 1, 3, 0, 9,
               {"textFormat": {"foregroundColor": rgb(GREY), "fontSize": 10, "italic": True}},
               "textFormat"),
        repeat(gid, 4, 5, 0, 9,
               {"textFormat": {"bold": True, "foregroundColor": rgb(GREY), "fontSize": 10}},
               "textFormat"),
        repeat(gid, 5, 6, 0, 9,
               {"textFormat": {"bold": True, "foregroundColor": rgb(INK), "fontSize": 22},
                "horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE"},
               "textFormat,horizontalAlignment,verticalAlignment"),
        repeat(gid, 7, 8, 0, 9,
               {"backgroundColor": rgb(INK), "textFormat": {"bold": True, "foregroundColor": rgb(WHITE), "fontSize": 11}},
               "backgroundColor,textFormat"),
        repeat(gid, 8, 17, 0, 9,
               {"textFormat": {"bold": True, "foregroundColor": rgb(LINK), "fontSize": 11},
                "verticalAlignment": "MIDDLE"},
               "textFormat,verticalAlignment"),
        repeat(gid, 9, 10, 0, 9,
               {"backgroundColor": rgb(INK), "textFormat": {"bold": True, "foregroundColor": rgb(WHITE), "fontSize": 11}},
               "backgroundColor,textFormat"),
        repeat(gid, 15, 16, 0, 9,
               {"backgroundColor": rgb(INK), "textFormat": {"bold": True, "foregroundColor": rgb(WHITE), "fontSize": 11}},
               "backgroundColor,textFormat"),
        repeat(gid, 16, 17, 0, 9,
               {"wrapStrategy": "WRAP", "verticalAlignment": "TOP", "textFormat": {"foregroundColor": rgb(GREY), "fontSize": 10}},
               "wrapStrategy,verticalAlignment,textFormat"),
        repeat(gid, 19, 21, 0, 9,
               {"wrapStrategy": "WRAP", "verticalAlignment": "TOP", "textFormat": {"foregroundColor": rgb(GREY), "fontSize": 10}},
               "wrapStrategy,verticalAlignment,textFormat"),
    ]
    for row, bg, fg in [(10, GREEN_BG, GREEN_FG), (11, BLUE_BG, BLUE_FG),
                        (12, GREY_BG, GREY_FG), (13, RED_BG, RED_FG)]:
        reqs.append(repeat(gid, row, row + 1, 0, 1,
                           {"backgroundColor": rgb(bg), "textFormat": {"bold": True, "foregroundColor": rgb(fg)}},
                           "backgroundColor,textFormat"))
    for index, width in enumerate([150, 160, 150, 160, 150, 160, 150, 160, 150]):
        reqs.append(col_width(gid, index, width))
    reqs.append(col_width(gid, 9, 40))
    reqs.append(protect(gid, 0, 30, 0, 10, editors))
    return reqs


# --- Tableau de bord ----------------------------------------------------------


def build_dashboard(recits, tickets, sep, generated):
    def countif(sheet_column, value):
        return f'=COUNTIF({sheet_column}{sep}"{value}")'

    def countifs(c1, v1, c2, v2):
        return f'=COUNTIFS({c1}{sep}"{v1}"{sep}{c2}{sep}"{v2}")'

    domains = sorted({row[1] for row in recits[1:] if len(row) > 1 and row[1]})
    origines = ["manuel", "analyse du code"]
    statuts = ["fait", "en cours", "à faire", "remplacé"]
    sous_projets = ["SP1", "SP2A", "SP2B", "SP3", "SP4", "SP5", "SP7", "LAMA", "GEN"]

    rows = [["Tableau de bord"], [f"Dernière génération : {generated}"]]
    refs: dict[str, tuple[int, int]] = {}

    def add_block(key, title, header, pairs):
        rows.append([])
        rows.append([title])
        rows.append(header)
        start = len(rows)
        for name, formula in pairs:
            rows.append([name, formula])
        refs[key] = (start, len(rows))

    add_block("domaines", "Récits par domaine", ["Domaine", "Récits"],
              [(d, countif("'Récits métier'!B2:B", d)) for d in domains])
    add_block("statuts", "Tickets par statut", ["Statut", "Tickets"],
              [(s, countif("Tickets!J2:J", s)) for s in statuts])
    add_block("sousprojets", "Tickets par sous-projet", ["Sous-projet", "Tickets"],
              [(s, countif("Tickets!C2:C", s)) for s in sous_projets])
    add_block("origines", "Récits par origine", ["Origine", "Récits"],
              [(o, countif("'Récits métier'!T2:T", o)) for o in origines])

    # Matrice de priorisation Valeur (colonnes) x Effort (lignes).
    rows.append([])
    rows.append(["Matrice de priorisation : Valeur (colonnes) selon Effort (lignes)"])
    rows.append(["Effort \\ Valeur", "1", "2", "3", "4", "5"])
    matrix_start = len(rows)
    for effort in range(1, 6):
        line = [str(effort)]
        for valeur in range(1, 6):
            line.append(
                countifs("'Récits métier'!$P$2:$P", valeur, "'Récits métier'!$Q$2:$Q", effort)
            )
        rows.append(line)
    refs["matrice"] = (matrix_start, len(rows))
    return rows, refs


def format_dashboard(gid, refs, service_email):
    reqs = [
        merge(gid, 0, 1, 0, 9),
        merge(gid, 1, 2, 0, 9),
        repeat(gid, 0, 1, 0, 9,
               {"backgroundColor": rgb(INK), "textFormat": {"bold": True, "foregroundColor": rgb(WHITE), "fontSize": 20}},
               "backgroundColor,textFormat"),
        row_height(gid, 0, 48),
        repeat(gid, 1, 2, 0, 9,
               {"textFormat": {"foregroundColor": rgb(GREY), "fontSize": 10, "italic": True}},
               "textFormat"),
    ]
    for key, (start, end) in refs.items():
        title_row = start - 2
        header_row = start - 1
        reqs.append(repeat(gid, title_row, title_row + 1, 0, 9,
                           {"textFormat": {"bold": True, "foregroundColor": rgb(INK), "fontSize": 12}},
                           "textFormat"))
        reqs.append(repeat(gid, header_row, header_row + 1, 0, 2 if key != "matrice" else 6,
                           {"backgroundColor": rgb(HEADER_BG),
                            "textFormat": {"bold": True, "foregroundColor": rgb(TEXT), "fontSize": 10}},
                           "backgroundColor,textFormat"))
        if key != "matrice":
            reqs.append(banding(gid, start, end, 0, 2))
    # dégradé de la matrice
    start, end = refs["matrice"]
    reqs.append(gradient(gid, start, end, 1, 6))
    reqs.append(col_width(gid, 0, 190))
    for index in range(1, 7):
        reqs.append(col_width(gid, index, 60))
    reqs.append(protect(gid, 0, 70, 0, 22, [service_email] if service_email else []))
    return reqs


def chart_requests(gid, recits_gid, recit_end, refs):
    def source(sheet_id, start, end, column):
        return {"sources": [rng(sheet_id, start, end, column, column + 1)]}

    def bar(title, key, row, column):
        start, end = refs[key]
        return {"addChart": {"chart": {
            "spec": {"title": title, "backgroundColor": rgb(WHITE),
                     "basicChart": {"chartType": "BAR", "legendPosition": "NO_LEGEND",
                                    "domains": [{"domain": {"sourceRange": source(gid, start, end, 0)}}],
                                    "series": [{"series": {"sourceRange": source(gid, start, end, 1)},
                                                "targetAxis": "BOTTOM_AXIS"}]}},
            "position": {"overlayPosition": {"anchorCell": {"sheetId": gid, "rowIndex": row, "columnIndex": column},
                                             "widthPixels": 460, "heightPixels": 280}}}}}

    def pie(title, key, row, column):
        start, end = refs[key]
        return {"addChart": {"chart": {
            "spec": {"title": title, "backgroundColor": rgb(WHITE),
                     "pieChart": {"legendPosition": "RIGHT_LEGEND",
                                  "domain": {"sourceRange": source(gid, start, end, 0)},
                                  "series": {"sourceRange": source(gid, start, end, 1)}}},
            "position": {"overlayPosition": {"anchorCell": {"sheetId": gid, "rowIndex": row, "columnIndex": column},
                                             "widthPixels": 460, "heightPixels": 280}}}}}

    scatter = {"addChart": {"chart": {
        "spec": {"title": "Priorisation : Valeur selon Effort", "backgroundColor": rgb(WHITE),
                 "basicChart": {"chartType": "SCATTER", "legendPosition": "NO_LEGEND",
                                "domains": [{"domain": {"sourceRange": source(recits_gid, 1, recit_end, C_EFFORT)}}],
                                "series": [{"series": {"sourceRange": source(recits_gid, 1, recit_end, C_VALEUR)},
                                            "targetAxis": "LEFT_AXIS"}]}},
        "position": {"overlayPosition": {"anchorCell": {"sheetId": gid, "rowIndex": 2, "columnIndex": 12},
                                         "widthPixels": 460, "heightPixels": 280}}}}}

    return [
        bar("Récits par domaine", "domaines", 2, 4),
        pie("Tickets par statut", "statuts", 2, 12),
        bar("Tickets par sous-projet", "sousprojets", 22, 4),
        pie("Récits par origine", "origines", 22, 12),
        scatter,
    ]


# --- Habillage des onglets ----------------------------------------------------

WIDTHS = {
    "Récits métier": [70, 110, 90, 150, 400, 200, 300, 100, 100, 100, 100, 100, 100, 100, 180, 70, 70, 70, 100, 110, 140, 200, 220, 90],
    "Tickets": [80, 300, 90, 60, 60, 240, 240, 220, 120, 90, 120, 90, 300, 220, 220, 220, 240, 240, 200, 150, 180, 110, 110, 140],
    "Plans": [70, 360, 300, 130, 90, 60, 220, 70, 60, 70, 70, 90, 200],
    "Specs": [420, 320, 160],
    "Référentiels": [120, 110, 90, 150, 110, 110, 110, 120],
}


def data_tab_requests(gid, rows, widths, notes=None) -> list[dict]:
    ncols = len(widths)
    reqs = [
        repeat(gid, 0, 1, 0, ncols,
               {"backgroundColor": rgb(HEADER_BG),
                "textFormat": {"bold": True, "foregroundColor": rgb(TEXT), "fontSize": 11},
                "verticalAlignment": "MIDDLE",
                "horizontalAlignment": "LEFT"},
               "backgroundColor,textFormat,verticalAlignment,horizontalAlignment"),
        row_height(gid, 0, 34),
        {"updateSheetProperties": {
            "properties": {"sheetId": gid, "gridProperties": {
                "frozenRowCount": 1, "frozenColumnCount": 1, "hideGridlines": True}},
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount,gridProperties.hideGridlines"}},
        {"updateBorders": {
            "range": rng(gid, 0, 1, 0, ncols),
            "bottom": {"style": "SOLID_MEDIUM", "color": rgb(BRAND)}}},
    ]
    end = rows + 1
    if rows > 0:
        reqs.append(repeat(gid, 1, end, 0, ncols,
                           {"wrapStrategy": "WRAP", "verticalAlignment": "TOP",
                            "textFormat": {"foregroundColor": rgb(TEXT), "fontSize": 10}},
                           "wrapStrategy,verticalAlignment,textFormat"))
        reqs.append(banding(gid, 1, end, 0, ncols))
    reqs.append({"updateBorders": {
        "range": rng(gid, 0, end, 0, ncols),
        "bottom": {"style": "SOLID", "color": rgb(BORDER)},
        "innerHorizontal": {"style": "SOLID", "color": rgb(BORDER)}}})
    reqs.append({"setBasicFilter": {"filter": {"range": rng(gid, 0, end, 0, ncols)}}})
    for index, width in enumerate(widths):
        reqs.append(col_width(gid, index, width))
    if notes:
        for column, text in notes.items():
            reqs.append(note(gid, column, text))
    return reqs


def recit_requests(gid, rows, service_email, metier_emails, domaines) -> list[dict]:
    end = rows + 1
    reqs = []
    reqs.append(repeat(gid, 1, end, EDITABLE_START, EDITABLE_END,
                       {"backgroundColor": rgb(AMBER_BG), "textFormat": {"foregroundColor": rgb(AMBER_FG)}},
                       "backgroundColor,textFormat"))
    reqs.append(validation(gid, rows, C_PRIORITE, C_PRIORITE + 1, "='Référentiels'!$E$2:$E$100"))
    reqs.append(validation(gid, rows, C_STATUT, C_STATUT + 1, "='Référentiels'!$F$2:$F$100"))
    reqs.append(validation(gid, rows, C_DECISION, C_DECISION + 1, "='Référentiels'!$G$2:$G$100"))
    reqs.append(validation(gid, rows, C_PORTEUR, C_PORTEUR + 1, "='Référentiels'!$H$2:$H$100"))
    reqs.append(validation(gid, rows, C_RELECTEUR, C_RELECTEUR + 1, "='Référentiels'!$H$2:$H$100"))
    reqs.append(validation(gid, rows, C_VALIDATEUR, C_VALIDATEUR + 1, "='Référentiels'!$H$2:$H$100"))
    reqs.append(number_between(gid, rows, C_VALEUR, 1, 5))
    reqs.append(number_between(gid, rows, C_EFFORT, 1, 5))

    formats = [
        (C_PRIORITE, [("Indispensable", RED_BG, RED_FG), ("Importante", ORANGE_BG, ORANGE_FG),
                      ("Souhaitable", BLUE_BG, BLUE_FG), ("Plus tard", GREY_BG, GREY_FG)]),
        (C_STATUT, [("Livré", GREEN_BG, GREEN_FG), ("Validé", GREEN_BG, GREEN_FG),
                    ("En cours", ORANGE_BG, ORANGE_FG), ("À cadrer", GREY_BG, GREY_FG),
                    ("Refusé", RED_BG, RED_FG)]),
        (C_DECISION, [("Validée", GREEN_BG, GREEN_FG), ("À revoir", ORANGE_BG, ORANGE_FG),
                      ("Refusée", RED_BG, RED_FG), ("En attente", GREY_BG, GREY_FG)]),
    ]
    for column, rules in formats:
        for text, bg, fg in rules:
            reqs.append(conditional(gid, 1, end, column, text, bg, fg))
    # groupement par domaine : bande de couleur sur la colonne Domaine
    for index, domain in enumerate(domaines):
        bg, fg = DOMAIN_CHIPS[index % len(DOMAIN_CHIPS)]
        reqs.append(conditional(gid, 1, end, 1, domain, bg, fg, bold=True))
    for role, (bg, fg) in ROLE_COLORS.items():
        reqs.append(conditional(gid, 1, end, 2, role, bg, fg))
    reqs.append(conditional(gid, 1, end, C_AVANCEMENT, "Livré", GREEN_BG, GREEN_FG))
    reqs.append(conditional(gid, 1, end, C_AVANCEMENT, "En cours", ORANGE_BG, ORANGE_FG))
    reqs.append(conditional(gid, 1, end, C_AVANCEMENT, "À cadrer", GREY_BG, GREY_FG))
    reqs.append(conditional(gid, 1, end, C_ALERTE, "En retard", RED_BG, RED_FG, bold=True))
    # échéance dépassée : rouge tant que non livré
    reqs.append(custom_conditional(gid, 1, end, C_ECHEANCE,
                                   '=AND(ISNUMBER($N2);$N2<TODAY();$S2<>"Livré")',
                                   RED_BG, RED_FG, bold=True))
    # valeur / effort : dégradé léger
    reqs.append(gradient(gid, 1, end, C_VALEUR, C_EFFORT + 1, min_color=WHITE, max_color="#BBD3FB"))
    # technique grisé
    reqs.append(repeat(gid, 1, end, C_ORIGINE, C_PREUVES := 23,
                       {"textFormat": {"foregroundColor": rgb(GREY), "fontSize": 9}},
                       "textFormat"))
    # formats numériques
    reqs.append(repeat(gid, 1, end, C_ECHEANCE, C_ECHEANCE + 1,
                       {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}, "numberFormat"))
    reqs.append(repeat(gid, 1, end, C_VALEUR, C_EFFORT + 1,
                       {"numberFormat": {"type": "NUMBER", "pattern": "0"}, "horizontalAlignment": "CENTER"},
                       "numberFormat,horizontalAlignment"))
    reqs.append(repeat(gid, 1, end, C_SCORE, C_SCORE + 1,
                       {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}, "horizontalAlignment": "CENTER"},
                       "numberFormat,horizontalAlignment"))
    # protection
    editors = [service_email] if service_email else []
    reqs.append(protect(gid, 0, end, 0, EDITABLE_START, editors))
    reqs.append(protect(gid, 0, end, EDITABLE_END, RECITS_COLS, editors))
    if metier_emails:
        reqs.append(protect(gid, 0, end, EDITABLE_START, EDITABLE_END,
                            metier_emails + editors))
    # vues filtrées
    reqs.append(filter_view("Vue gérante", gid, rows, 2, "gérante"))
    reqs.append(filter_view("Vue réception", gid, rows, 2, "réception"))
    reqs.append(filter_view("Vue praticienne", gid, rows, 2, "praticienne"))
    reqs.append(filter_view("À décider", gid, rows, C_DECISION, "En attente"))
    reqs.append(filter_view("En retard", gid, rows, C_ALERTE, "En retard"))
    return reqs


def ticket_requests(gid, rows, service_email) -> list[dict]:
    end = rows + 1
    editors = [service_email] if service_email else []
    reqs = []
    for text, bg, fg in [("fait", GREEN_BG, GREEN_FG), ("en cours", ORANGE_BG, ORANGE_FG),
                         ("à faire", GREY_BG, GREY_FG), ("remplacé", RED_BG, RED_FG)]:
        reqs.append(conditional(gid, 1, end, 9, text, bg, fg))
    reqs.append(protect(gid, 0, end, 0, 24, editors))
    return reqs


def plan_requests(gid, rows, service_email) -> list[dict]:
    end = rows + 1
    editors = [service_email] if service_email else []
    reqs = []
    for text, bg, fg in [("terminé", GREEN_BG, GREEN_FG), ("en cours", ORANGE_BG, ORANGE_FG),
                         ("à faire", GREY_BG, GREY_FG), ("remplacé", RED_BG, RED_FG)]:
        reqs.append(conditional(gid, 1, end, 11, text, bg, fg))
    reqs.append(protect(gid, 0, end, 0, 13, editors))
    return reqs


def decisions_requests(gid, rows, service_email) -> list[dict]:
    end = rows + 1
    editors = [service_email] if service_email else []
    reqs = [
        repeat(gid, 0, 1, 0, len(DECISION_HEADERS),
               {"backgroundColor": rgb(HEADER_BG),
                "textFormat": {"bold": True, "foregroundColor": rgb(TEXT), "fontSize": 11}},
               "backgroundColor,textFormat"),
        row_height(gid, 0, 34),
        {"updateSheetProperties": {
            "properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1, "hideGridlines": True}},
            "fields": "gridProperties.frozenRowCount,gridProperties.hideGridlines"}},
        protect(gid, 0, max(end, 2), 0, len(DECISION_HEADERS), editors),
    ]
    if rows > 0:
        reqs.append(banding(gid, 1, end, 0, len(DECISION_HEADERS)))
        reqs.append(repeat(gid, 1, end, 0, len(DECISION_HEADERS),
                           {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"},
                           "wrapStrategy,verticalAlignment"))
    for index, width in enumerate([130, 90, 120, 100, 110, 110, 110, 100, 220]):
        reqs.append(col_width(gid, index, width))
    return reqs


def demandes_requests(gid, service_email) -> list[dict]:
    reqs = [
        repeat(gid, 0, 1, 0, len(DEMANDE_HEADERS),
               {"backgroundColor": rgb(HEADER_BG),
                "textFormat": {"bold": True, "foregroundColor": rgb(TEXT), "fontSize": 11}},
               "backgroundColor,textFormat"),
        row_height(gid, 0, 34),
        {"updateSheetProperties": {
            "properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1, "hideGridlines": True}},
            "fields": "gridProperties.frozenRowCount,gridProperties.hideGridlines"}},
        repeat(gid, 1, 201, 0, len(DEMANDE_HEADERS),
               {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}, "wrapStrategy,verticalAlignment"),
        banding(gid, 1, 201, 0, len(DEMANDE_HEADERS)),
        validation(gid, 200, 6, 7, "='Référentiels'!$E$2:$E$100"),
        validation(gid, 200, 7, 8, "='Référentiels'!$F$2:$F$100"),
    ]
    for column, text in DEMANDE_NOTES.items():
        reqs.append(note(gid, column, text))
    for index, width in enumerate([80, 100, 130, 300, 260, 240, 100, 110, 220]):
        reqs.append(col_width(gid, index, width))
    return reqs


TAB_COLORS = {
    "Accueil": BRAND, "Récits métier": PURPLE_BG, "Décisions": ORANGE_BG,
    "Demandes": YELLOW_BG, "Tickets": GREY_BG, "Plans": "#8A8F98",
    "Specs": "#8A8F98", "Référentiels": "#B9BEC6", "Tableau de bord": BRAND,
}


def tab_color_requests(ids) -> list[dict]:
    return [{"updateSheetProperties": {
        "properties": {"sheetId": ids[t], "tabColor": rgb(TAB_COLORS[t])}, "fields": "tabColor"}}
        for t in TABS if t in ids]


def reset_cosmetics(meta, ids) -> list[dict]:
    reqs = []
    managed = set(ids)
    for sheet in meta["sheets"]:
        if sheet["properties"]["title"] not in managed:
            continue
        gid = sheet["properties"]["sheetId"]
        for chart in sheet.get("charts", []):
            reqs.append({"deleteEmbeddedObject": {"objectId": chart["chartId"]}})
        rules = sheet.get("conditionalFormats", [])
        for index in range(len(rules) - 1, -1, -1):
            reqs.append({"deleteConditionalFormatRule": {"sheetId": gid, "index": index}})
        for band in sheet.get("bandedRanges", []):
            reqs.append({"deleteBanding": {"bandedRangeId": band["bandedRangeId"]}})
        for view in sheet.get("filterViews", []):
            reqs.append({"deleteFilterView": {"filterId": view["filterViewId"]}})
        for prot in sheet.get("protectedRanges", []):
            reqs.append({"deleteProtectedRange": {"protectedRangeId": prot["protectedRangeId"]}})
    return reqs


def main() -> None:
    if not (SHEETS_DIR / "Tickets.csv").exists():
        sys.exit("Exports absents : lancez d'abord parser.py.")

    credentials = load_credentials()
    service_email = getattr(credentials, "service_account_email", "")
    people = load_people()
    metier_emails = [e for e in people.get("metier", []) if e]
    sheets = build("sheets", "v4", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)

    spreadsheet_id = CFG["spreadsheet_id"] or find_spreadsheet(drive)
    ids = ensure_tabs(sheets, spreadsheet_id)

    locale = (sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute(num_retries=5)
              ["properties"].get("locale", "") or "").lower()
    sep = ";" if locale.startswith(("fr", "de", "es", "it", "pt", "nl")) else ","
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    preserved = preserve_recit_edits(sheets, spreadsheet_id)
    recit_rows = overlay_recit_edits(read_csv_rows(SHEETS_DIR / "Recits.csv"), preserved)
    # Conserver les récits créés depuis le classeur (identifiants inconnus du parser).
    generated_ids = {r[0] for r in recit_rows if r}
    recit_rows += [r for r in read_existing_recits(sheets, spreadsheet_id)
                   if r[0] not in generated_ids]
    ticket_rows = read_csv_rows(SHEETS_DIR / "Tickets.csv")
    plan_rows = read_csv_rows(SHEETS_DIR / "Plans.csv")
    spec_rows = read_csv_rows(SHEETS_DIR / "Specs.csv")
    ref_rows = read_csv_rows(SHEETS_DIR / "Referentiels.csv")

    write_tab(sheets, spreadsheet_id, "Récits métier", recit_rows)
    write_tab(sheets, spreadsheet_id, "Tickets", ticket_rows)
    write_tab(sheets, spreadsheet_id, "Plans", plan_rows)
    write_tab(sheets, spreadsheet_id, "Specs", spec_rows)
    write_tab(sheets, spreadsheet_id, "Référentiels", ref_rows)

    # Score et Alerte : formules posées après l'écriture des valeurs.
    n = len(recit_rows)
    if n > 1:
        score = [[f'=IFERROR(IF(AND(P{r}<>""{sep}Q{r}<>""{sep}Q{r}>0){sep}ROUND(P{r}/Q{r}{sep}2){sep}""){sep}"")']
                 for r in range(2, n + 1)]
        alerte = [[f'=IF(AND(ISNUMBER(N{r}){sep}N{r}<TODAY(){sep}S{r}<>"Livré"){sep}"En retard"{sep}"")']
                  for r in range(2, n + 1)]
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"'Récits métier'!R2:R{n}",
            valueInputOption="USER_ENTERED", body={"values": score}).execute(num_retries=5)
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"'Récits métier'!X2:X{n}",
            valueInputOption="USER_ENTERED", body={"values": alerte}).execute(num_retries=5)

    write_tab(sheets, spreadsheet_id, "Accueil", build_home(ids, sep, generated), raw=False)
    decisions = [DECISION_HEADERS]
    for row in recit_rows[1:]:
        row = row + [""] * (RECITS_COLS - len(row))
        if row[C_DECISION] or row[C_STATUT] or row[C_VALIDATEUR]:
            decisions.append([generated, row[0], row[1], row[C_PRIORITE], row[C_DECISION],
                              row[C_STATUT], row[C_VALIDATEUR], row[C_ECHEANCE], row[C_COMMENTAIRE]])
    write_tab(sheets, spreadsheet_id, "Décisions", decisions)
    # Demandes : en-tête réécrit, lignes saisies conservées.
    write_tab(sheets, spreadsheet_id, "Demandes",
              [DEMANDE_HEADERS] + read_existing_demandes(sheets, spreadsheet_id))
    dash_rows, refs = build_dashboard(recit_rows, ticket_rows, sep, generated)
    write_tab(sheets, spreadsheet_id, "Tableau de bord", dash_rows, raw=False)

    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute(num_retries=5)
    requests = reset_cosmetics(meta, ids)

    counts = {"Récits métier": len(recit_rows) - 1, "Tickets": len(ticket_rows) - 1,
              "Plans": len(plan_rows) - 1, "Specs": len(spec_rows) - 1,
              "Référentiels": len(ref_rows) - 1}
    for title in DATA_TABS:
        requests += data_tab_requests(ids[title], counts[title], WIDTHS[title],
                                      RECIT_NOTES if title == "Récits métier" else None)
    domaines = sorted({r[1] for r in recit_rows[1:] if len(r) > 1 and r[1]})
    requests += recit_requests(ids["Récits métier"], counts["Récits métier"],
                               service_email, metier_emails, domaines)
    requests += ticket_requests(ids["Tickets"], counts["Tickets"], service_email)
    requests += plan_requests(ids["Plans"], counts["Plans"], service_email)
    requests.append(protect(ids["Specs"], 0, counts["Specs"] + 1, 0, 3,
                            [service_email] if service_email else []))
    requests.append(protect(ids["Référentiels"], 0, counts["Référentiels"] + 1, 0, 8,
                            [service_email] if service_email else []))
    requests += format_home(ids["Accueil"], service_email)
    requests += decisions_requests(ids["Décisions"], len(decisions) - 1, service_email)
    requests += demandes_requests(ids["Demandes"], service_email)
    requests += format_dashboard(ids["Tableau de bord"], refs, service_email)
    requests += chart_requests(ids["Tableau de bord"], ids["Récits métier"], len(recit_rows), refs)
    requests += tab_color_requests(ids)

    for start in range(0, len(requests), 300):
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests[start:start + 300]}
        ).execute(num_retries=5)

    print(f"Classeur mis à jour : https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    for title in DATA_TABS:
        print(f"  {title}: {counts[title]} lignes")
    print(f"  Décisions: {len(decisions) - 1} lignes")
    if metier_emails:
        print(f"  Édition réservée à : {', '.join(metier_emails)}")


if __name__ == "__main__":
    main()
