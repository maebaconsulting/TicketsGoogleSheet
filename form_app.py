#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Formulaire de saisie local, style monday.com, pour le classeur export-tickets.

Sert une petite application web (http://127.0.0.1:8765) qui permet au métier de
modifier les colonnes éditables d'un récit et d'ajouter une demande, en écrivant
directement dans le classeur Google via le compte de service. La clé n'est jamais
exposée au navigateur.

Usage :
    GOOGLE_APPLICATION_CREDENTIALS=/chemin/cle.json python3 tools/export-tickets/form_app.py
    # réseau de l'institut (à vos risques, sans authentification) :
    FORM_HOST=0.0.0.0 python3 tools/export-tickets/form_app.py
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from googleapiclient.discovery import build

import sheets as tool

HOST = os.environ.get("FORM_HOST", "127.0.0.1")
PORT = int(os.environ.get("FORM_PORT", "8765"))
LOCK = threading.Lock()

SHEETS = None
SPREADSHEET_ID = None
# Colonnes éditables de Récits métier : H..Q (index 7..16).
EDITABLE = [
    "priorite", "statut_metier", "decision", "porteur", "relecteur",
    "validateur", "echeance", "commentaire", "valeur", "effort",
]


def safe(value: str) -> str:
    """Évite qu'une saisie commence une formule."""
    value = (value or "").strip()
    return "'" + value if value[:1] in ("=", "+", "@") else value


def read_recits() -> list[dict]:
    values = (
        SHEETS.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="'Récits métier'!A1:X")
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
        recits.append({
            "id": cell(row, "ID"),
            "recit": cell(row, "Récit"),
            "domaine": cell(row, "Domaine"),
            "role": cell(row, "Rôle"),
            "priorite": cell(row, "Priorité"),
            "statut_metier": cell(row, "Statut métier"),
            "decision": cell(row, "Décision"),
            "porteur": cell(row, "Porteur"),
            "relecteur": cell(row, "Relecteur"),
            "validateur": cell(row, "Validateur"),
            "echeance": cell(row, "Échéance"),
            "commentaire": cell(row, "Commentaire"),
            "valeur": cell(row, "Valeur"),
            "effort": cell(row, "Effort"),
            "avancement": cell(row, "Avancement"),
        })
    return recits


def read_referentiels() -> dict:
    values = (
        SHEETS.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="Référentiels!A1:J")
        .execute(num_retries=5)
        .get("values", [])
    )
    if not values:
        return {}
    header = values[0]
    out = {}
    for i, name in enumerate(header):
        out[name] = [row[i] for row in values[1:] if i < len(row) and row[i]]
    return out


def find_row(recit_id: str) -> int | None:
    ids = (
        SHEETS.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="'Récits métier'!A2:A")
        .execute(num_retries=5)
        .get("values", [])
    )
    for i, row in enumerate(ids):
        if row and row[0] == recit_id:
            return i + 2  # 1-based, ligne 2 = premier récit
    return None


def save_recit(payload: dict) -> tuple[int, str]:
    recit_id = payload.get("id", "")
    row = find_row(recit_id)
    if not row:
        return 404, json.dumps({"error": f"Récit introuvable : {recit_id}"})
    values = [[safe(str(payload.get(key, ""))) for key in EDITABLE]]
    with LOCK:
        SHEETS.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'Récits métier'!H{row}:Q{row}",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute(num_retries=5)
    return 200, json.dumps({"ok": True, "id": recit_id})


def next_demande_id() -> str:
    values = (
        SHEETS.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="Demandes!A2:A")
        .execute(num_retries=5)
        .get("values", [])
    )
    numbers = [int(r[0].split("-")[-1]) for r in values if r and r[0].startswith("DEM-")]
    return f"DEM-{(max(numbers) + 1) if numbers else 1:03d}"


def save_demande(payload: dict) -> tuple[int, str]:
    row = [
        next_demande_id(),
        date.today().strftime("%d/%m/%Y"),
        safe(payload.get("demandeur", "")),
        safe(payload.get("besoin", "")),
        safe(payload.get("recit", "")),
        safe(payload.get("impact", "")),
        safe(payload.get("priorite", "")),
        "À cadrer",
        safe(payload.get("commentaire", "")),
    ]
    with LOCK:
        SHEETS.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Demandes!A2",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute(num_retries=5)
    return 200, json.dumps({"ok": True, "id": row[0]})


PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>lama : saisie</title>
<style>
  :root{
    --brand:#0073ea; --text:#323338; --subtle:#676879; --border:#e6e9ef;
    --surface:#fff; --alt:#f6f7fb; --green:#00c875; --orange:#fdab3d;
    --red:#e2445c; --blue:#579bfc; --purple:#a25ddc; --grey:#c4c4c4;
  }
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;
       color:var(--text);background:var(--alt)}
  header{background:var(--brand);color:#fff;padding:14px 20px;display:flex;
         align-items:center;gap:12px;font-weight:600;font-size:16px}
  header .dot{width:10px;height:10px;border-radius:50%;background:#fff}
  .wrap{display:grid;grid-template-columns:340px 1fr;gap:18px;padding:18px;max-width:1240px;margin:0 auto}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:10px}
  .list{padding:12px;max-height:78vh;overflow:auto}
  .search{width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:8px;margin-bottom:10px}
  .item{padding:10px 12px;border-radius:8px;cursor:pointer;border:1px solid transparent;margin-bottom:4px}
  .item:hover{background:var(--alt)}
  .item.active{background:#eaf2ff;border-color:#cfe0ff}
  .item .id{font-size:11px;color:var(--subtle);font-weight:600}
  .item .t{font-weight:600;font-size:13px}
  .form{padding:20px}
  h2{margin:0 0 4px;font-size:18px}
  .sub{color:var(--subtle);font-size:12px;margin-bottom:18px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  label{display:block;font-size:12px;font-weight:600;color:var(--subtle);margin-bottom:5px}
  input,select,textarea{width:100%;padding:9px 11px;border:1px solid var(--border);
    border-radius:8px;font:inherit;color:var(--text);background:#fff;outline:none}
  input:focus,select:focus,textarea:focus{border-color:var(--brand);box-shadow:0 0 0 2px #dbe9ff}
  textarea{min-height:80px;resize:vertical}
  .full{grid-column:1/-1}
  .actions{margin-top:18px;display:flex;gap:10px;align-items:center}
  button{background:var(--brand);color:#fff;border:0;border-radius:8px;padding:10px 18px;
    font-weight:600;cursor:pointer}
  button.ghost{background:#fff;color:var(--brand);border:1px solid var(--border)}
  button:disabled{opacity:.5;cursor:default}
  .toast{position:fixed;bottom:22px;right:22px;background:#323338;color:#fff;padding:11px 16px;
    border-radius:8px;opacity:0;transform:translateY(8px);transition:.2s}
  .toast.on{opacity:1;transform:none}
  .tabs{display:flex;gap:8px;padding:14px 18px 0}
  .tab{padding:8px 14px;border-radius:8px 8px 0 0;cursor:pointer;color:var(--subtle);font-weight:600}
  .tab.active{background:var(--surface);color:var(--brand)}
  .pill{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;
        color:#fff;background:var(--grey)}
  .pill.Livré,.pill.Validé,.pill.Validée,.pill.fait{background:var(--green)}
  .pill.encours,.pill.Àrevoir,.pill.Importante{background:var(--orange);color:#323338}
  .pill.Refusé,.pill.Refusée,.pill.Indispensable{background:var(--red)}
  .pill.Àcadrer,.pill.Enattente,.pill.Plustard{background:var(--grey);color:#323338}
  .meta{font-size:12px;color:var(--subtle);margin:2px 0 14px}
</style>
</head>
<body>
<header><span class="dot"></span> lama : saisie du backlog</header>
<div class="tabs">
  <div class="tab active" data-tab="recit">Modifier un récit</div>
  <div class="tab" data-tab="demande">Nouvelle demande</div>
</div>
<div class="wrap">
  <div class="card list" id="listPane">
    <input class="search" id="search" placeholder="Rechercher un récit…">
    <div id="list"></div>
  </div>
  <div>
    <div class="card form" id="recitPane">
      <h2 id="rTitle">Choisissez un récit</h2>
      <div class="sub" id="rSub">Les colonnes H à Q seront enregistrées.</div>
      <form id="recitForm" class="grid" hidden>
        <div class="full meta" id="rMeta"></div>
        <div><label>Priorité</label><select name="priorite" id="f_priorite"></select></div>
        <div><label>Statut métier</label><select name="statut_metier" id="f_statut"></select></div>
        <div><label>Décision</label><select name="decision" id="f_decision"></select></div>
        <div><label>Porteur</label><input name="porteur" id="f_porteur" list="people"></div>
        <div><label>Relecteur</label><input name="relecteur" id="f_relecteur" list="people"></div>
        <div><label>Validateur</label><input name="validateur" id="f_validateur" list="people"></div>
        <div><label>Échéance (jj/mm/aaaa)</label><input name="echeance" id="f_echeance" placeholder="jj/mm/aaaa"></div>
        <div><label>Valeur (1-5)</label><input name="valeur" id="f_valeur" type="number" min="1" max="5"></div>
        <div><label>Effort (1-5)</label><input name="effort" id="f_effort" type="number" min="1" max="5"></div>
        <div class="full"><label>Commentaire</label><textarea name="commentaire" id="f_commentaire"></textarea></div>
        <div class="actions full">
          <button type="submit">Enregistrer</button>
          <button type="button" class="ghost" id="reset">Annuler</button>
        </div>
      </form>
    </div>
    <div class="card form" id="demandePane" hidden>
      <h2>Nouvelle demande</h2>
      <div class="sub">Un besoin exprimé par le métier, ajouté à l'onglet Demandes.</div>
      <form id="demandeForm" class="grid">
        <div><label>Demandeur</label><input name="demandeur" list="people" required></div>
        <div><label>Priorité</label><select name="priorite" id="d_priorite"></select></div>
        <div class="full"><label>Besoin</label><textarea name="besoin" required></textarea></div>
        <div class="full"><label>Récit proposé</label><input name="recit" placeholder="En tant que…, je veux…"></div>
        <div class="full"><label>Impact attendu</label><textarea name="impact"></textarea></div>
        <div class="full"><label>Commentaire</label><textarea name="commentaire"></textarea></div>
        <div class="actions full"><button type="submit">Envoyer la demande</button></div>
      </form>
    </div>
  </div>
</div>
<datalist id="people"></datalist>
<div class="toast" id="toast"></div>

<script>
let DATA = {recits: [], referentiels: {}}, CURRENT = null;
const $ = (s) => document.querySelector(s);
function toast(msg){const t=$("#toast");t.textContent=msg;t.classList.add("on");
  setTimeout(()=>t.classList.remove("on"),2200);}
function fill(select, values, keep){const el=$(select);el.innerHTML="";
  (values||[]).forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v||"—";el.appendChild(o);});
  if(keep!==undefined) el.value=keep;}
function setTab(name){document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.dataset.tab===name));
  $("#recitPane").hidden = name!=="recit"; $("#demandePane").hidden = name!=="demande";
  $("#listPane").style.visibility = name==="recit" ? "visible" : "hidden";}
function renderList(filter){const box=$("#list");box.innerHTML="";const f=(filter||"").toLowerCase();
  DATA.recits.filter(r=>!f||r.id.toLowerCase().includes(f)||(r.recit||"").toLowerCase().includes(f)||(r.domaine||"").toLowerCase().includes(f))
  .forEach(r=>{const d=document.createElement("div");d.className="item"+(CURRENT&&CURRENT.id===r.id?" active":"");
    d.innerHTML=`<div class="id">${r.id} · ${r.domaine}</div><div class="t">${(r.recit||"").slice(0,70)}</div>`;
    d.onclick=()=>selectRecit(r);box.appendChild(d);});}
function selectRecit(r){CURRENT=r;$("#rTitle").textContent=r.id;$("#rSub").textContent=r.domaine+" · "+r.role;
  $("#rMeta").innerHTML=`Avancement : <span class="pill ${(r.avancement||"").replace(/\\s/g,"")}">${r.avancement||"—"}</span>`;
  const f=$("#recitForm");f.hidden=false;
  f.priorite.value=r.priorite||"";f.statut_metier.value=r.statut_metier||"";f.decision.value=r.decision||"";
  f.porteur.value=r.porteur||"";f.relecteur.value=r.relecteur||"";f.validateur.value=r.validateur||"";
  f.echeance.value=r.echeance||"";f.commentaire.value=r.commentaire||"";f.valeur.value=r.valeur||"";f.effort.value=r.effort||"";
  renderList($("#search").value);}
async function load(){const res=await fetch("/api/data");DATA=await res.json();
  const ref=DATA.referentiels||{};
  fill("#f_priorite",ref["Priorité"]);fill("#f_statut",ref["Statut métier"]);fill("#f_decision",ref["Décision"]);
  fill("#d_priorite",ref["Priorité"]);
  const dl=$("#people");dl.innerHTML="";(ref["Personne"]||[]).forEach(p=>{const o=document.createElement("option");o.value=p;dl.appendChild(o);});
  renderList("");}
$("#search").oninput=(e)=>renderList(e.target.value);
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>setTab(t.dataset.tab));
$("#recitForm").onsubmit=async(e)=>{e.preventDefault();if(!CURRENT)return;
  const body={id:CURRENT.id};new FormData(e.target).forEach((v,k)=>body[k]=v);
  const res=await fetch("/api/recit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const out=await res.json();if(res.ok){toast("Récit enregistré");await load();}else toast(out.error||"Erreur");};
$("#reset").onclick=()=>CURRENT&&selectRecit(CURRENT);
$("#demandeForm").onsubmit=async(e)=>{e.preventDefault();
  const body={};new FormData(e.target).forEach((v,k)=>body[k]=v);
  const res=await fetch("/api/demande",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const out=await res.json();if(res.ok){toast("Demande "+out.id+" envoyée");e.target.reset();}else toast(out.error||"Erreur");};
load();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/api/data":
            payload = {"recits": read_recits(), "referentiels": read_referentiels()}
            self._send(200, json.dumps(payload, ensure_ascii=False))
        else:
            self._send(404, "{}")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(400, json.dumps({"error": "JSON invalide"}))
            return
        path = urlparse(self.path).path
        if path == "/api/recit":
            code, body = save_recit(payload)
        elif path == "/api/demande":
            code, body = save_demande(payload)
        else:
            code, body = 404, "{}"
        self._send(code, body)


def main() -> None:
    global SHEETS, SPREADSHEET_ID
    credentials = tool.load_credentials()
    SHEETS = build("sheets", "v4", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)
    SPREADSHEET_ID = tool.CFG["spreadsheet_id"] or tool.find_spreadsheet(drive)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Formulaire : http://{HOST}:{PORT}")
    print("Arrêt : Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
