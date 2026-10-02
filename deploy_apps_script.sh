#!/usr/bin/env bash
# Déploie les formulaires Apps Script sous VOTRE compte Google (clasp).
# Prérequis : activer l'API ici https://script.google.com/home/usersettings
#             puis s'authentifier une fois : npx @google/clasp login
set -euo pipefail

cd "$(dirname "$0")"
SHEET_ID="${SHEET_ID:-$(python3 -c "import config;print(config.load()['spreadsheet_id'])" 2>/dev/null)}"
if [ -z "$SHEET_ID" ]; then
  echo "Renseignez spreadsheet_id dans config.json (ou SHEET_ID)."
  exit 1
fi

if ! npx --yes @google/clasp show-authorized-user >/dev/null 2>&1; then
  echo "Non connecté. Lancez d'abord :"
  echo "  npx @google/clasp login"
  exit 1
fi

if [ ! -f .clasp.json ]; then
  npx --yes @google/clasp create \
    --type sheets --title "lama saisie" \
    --parentId "$SHEET_ID" --rootDir apps-script
fi

npx --yes @google/clasp push -f
echo "Déployé. Ouvrez le classeur, Extensions > Apps Script, autorisez, puis rechargez la page."
