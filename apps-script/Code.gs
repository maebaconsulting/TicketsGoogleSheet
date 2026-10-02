/**
 * lama : formulaires de saisie intégrés au classeur.
 *
 * Ajoute au classeur un menu « lama » qui ouvre un formulaire HTML stylé pour
 * modifier un récit, en créer un, ou enregistrer une demande du métier. Le script
 * s'exécute sous le compte de la personne connectée et n'écrit que les colonnes
 * éditables (H à Q) ; les colonnes protégées ne sont jamais touchées.
 */

var SHEET_RECITS = 'Récits métier';
var SHEET_DEMANDES = 'Demandes';
var SHEET_REF = 'Référentiels';
var TZ = 'Africa/Douala';

// Nom affiché dans le menu et les boîtes. Remplacé au déploiement par
// bind_apps_script_user.py ; repli générique sinon.
var PRODUCT = '__PRODUCT__';
if (PRODUCT.indexOf('__') === 0) PRODUCT = 'Backlog';

var EDITABLE = [
  { header: 'Priorité', key: 'priorite' },
  { header: 'Statut métier', key: 'statut_metier' },
  { header: 'Décision', key: 'decision' },
  { header: 'Porteur', key: 'porteur' },
  { header: 'Relecteur', key: 'relecteur' },
  { header: 'Validateur', key: 'validateur' },
  { header: 'Échéance', key: 'echeance' },
  { header: 'Commentaire', key: 'commentaire' },
  { header: 'Valeur', key: 'valeur' },
  { header: 'Effort', key: 'effort' }
];

var RECIT_FIELDS = [
  { header: 'Domaine', key: 'domaine' },
  { header: 'Rôle', key: 'role' },
  { header: 'Fonctionnalité', key: 'fonctionnalite' },
  { header: 'Récit', key: 'recit' },
  { header: 'Bénéfice', key: 'benefice' },
  { header: "Critères d'acceptation", key: 'criteres' }
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu(PRODUCT)
    .addItem('Modifier un récit', 'showRecitForm')
    .addItem('Créer un récit', 'showCreateForm')
    .addItem('Nouvelle demande', 'showDemandeForm')
    .addSeparator()
    .addItem('Aller aux récits', 'goRecits')
    .addItem('Aller aux demandes', 'goDemandes')
    .addToUi();
}

function showRecitForm() { showForm_('recit'); }
function showCreateForm() { showForm_('create'); }
function showDemandeForm() { showForm_('demande'); }

function showForm_(mode) {
  var template = HtmlService.createTemplateFromFile('Formulaire');
  template.mode = mode;
  template.product = PRODUCT;
  var html = template.evaluate().setWidth(980).setHeight(800);
  SpreadsheetApp.getUi().showModalDialog(html, PRODUCT + ' : saisie');
}

function goRecits() {
  SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_RECITS).activate();
}

function goDemandes() {
  SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_DEMANDES).activate();
}

/* --- Lecture --------------------------------------------------------------- */

function getData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_RECITS);
  var values = sheet.getDataRange().getValues();
  var headers = values[0].map(String);
  var index = headerIndex_(headers);
  var recits = [];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    if (!row[index['ID']]) continue;
    recits.push({
      id: String(row[index['ID']]),
      domaine: text_(row[index['Domaine']]),
      role: text_(row[index['Rôle']]),
      fonctionnalite: text_(row[index['Fonctionnalité']]),
      recit: text_(row[index['Récit']]),
      benefice: text_(row[index['Bénéfice']]),
      criteres: text_(row[index["Critères d'acceptation"]]),
      priorite: text_(row[index['Priorité']]),
      statut_metier: text_(row[index['Statut métier']]),
      decision: text_(row[index['Décision']]),
      porteur: text_(row[index['Porteur']]),
      relecteur: text_(row[index['Relecteur']]),
      validateur: text_(row[index['Validateur']]),
      echeance: dateText_(row[index['Échéance']]),
      commentaire: text_(row[index['Commentaire']]),
      valeur: text_(row[index['Valeur']]),
      effort: text_(row[index['Effort']]),
      avancement: text_(row[index['Avancement']])
    });
  }
  return { recits: recits, referentiels: readReferentiels_(ss), product: PRODUCT };
}

function readReferentiels_(ss) {
  var sheet = ss.getSheetByName(SHEET_REF);
  if (!sheet) return {};
  var values = sheet.getDataRange().getValues();
  if (!values.length) return {};
  var headers = values[0].map(String);
  var out = {};
  for (var c = 0; c < headers.length; c++) {
    var list = [];
    for (var r = 1; r < values.length; r++) {
      if (values[r][c] !== '' && values[r][c] != null) list.push(String(values[r][c]));
    }
    out[headers[c]] = list;
  }
  return out;
}

/* --- Écriture -------------------------------------------------------------- */

function saveRecit(payload) {
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_RECITS);
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
    var index = headerIndex_(headers);
    var row = findRow_(sheet, index['ID'], payload.id);
    if (row < 0) throw new Error('Récit introuvable : ' + payload.id);
    for (var i = 0; i < EDITABLE.length; i++) {
      var field = EDITABLE[i];
      var column = index[field.header] + 1;
      if (field.header === 'Échéance') {
        setDateCell_(sheet, row, column, payload[field.key]);
      } else if (field.header === 'Valeur' || field.header === 'Effort') {
        var n = Number(payload[field.key]);
        sheet.getRange(row, column).setValue(payload[field.key] === '' || isNaN(n) ? '' : n);
      } else {
        sheet.getRange(row, column).setValue(sanitize_(payload[field.key]));
      }
    }
    return { ok: true, id: payload.id };
  } finally {
    lock.releaseLock();
  }
}

function createRecit(payload) {
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_RECITS);
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
    var index = headerIndex_(headers);
    var id = nextId_(sheet, index['ID'], 'REC-');

    var row = new Array(headers.length).fill('');
    row[index['ID']] = id;
    RECIT_FIELDS.forEach(function (field) {
      row[index[field.header]] = sanitize_(payload[field.key]);
    });
    EDITABLE.forEach(function (field) {
      row[index[field.header]] = sanitize_(payload[field.key]);
    });
    row[index['Avancement']] = 'À cadrer';
    row[index['Origine']] = 'manuel';
    row[index['Valeur']] = numberOrBlank_(payload.valeur);
    row[index['Effort']] = numberOrBlank_(payload.effort);

    sheet.appendRow(row);
    var newRow = sheet.getLastRow();
    setScoreFormulas_(sheet, index, newRow);
    return { ok: true, id: id };
  } finally {
    lock.releaseLock();
  }
}

function addDemande(payload) {
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_DEMANDES);
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
    var index = headerIndex_(headers);
    var id = nextId_(sheet, index['ID'], 'DEM-');
    var row = new Array(headers.length).fill('');
    row[index['ID']] = id;
    row[index['Date']] = Utilities.formatDate(new Date(), TZ, 'dd/MM/yyyy');
    row[index['Demandeur']] = sanitize_(payload.demandeur);
    row[index['Besoin']] = sanitize_(payload.besoin);
    row[index['Récit proposé']] = sanitize_(payload.recit);
    row[index['Impact']] = sanitize_(payload.impact);
    row[index['Priorité']] = sanitize_(payload.priorite);
    row[index['Statut']] = 'À cadrer';
    row[index['Commentaire']] = sanitize_(payload.commentaire);
    sheet.appendRow(row);
    return { ok: true, id: id };
  } finally {
    lock.releaseLock();
  }
}

/* --- Aides ----------------------------------------------------------------- */

function headerIndex_(headers) {
  var index = {};
  headers.forEach(function (name, i) { index[name] = i; });
  return index;
}

function findRow_(sheet, idColumn, id) {
  var last = sheet.getLastRow();
  if (last < 2) return -1;
  var values = sheet.getRange(2, idColumn + 1, last - 1, 1).getValues();
  for (var i = 0; i < values.length; i++) {
    if (String(values[i][0]) === String(id)) return i + 2;
  }
  return -1;
}

function nextId_(sheet, idColumn, prefix) {
  var last = sheet.getLastRow();
  var max = 0;
  if (last >= 2) {
    var values = sheet.getRange(2, idColumn + 1, last - 1, 1).getValues();
    values.forEach(function (row) {
      var value = String(row[0] || '');
      if (value.indexOf(prefix) === 0) {
        var n = parseInt(value.slice(prefix.length), 10);
        if (!isNaN(n) && n > max) max = n;
      }
    });
  }
  return prefix + String(max + 1).padStart(3, '0');
}

function columnLetter_(column) {
  var letter = '';
  while (column > 0) {
    var rem = (column - 1) % 26;
    letter = String.fromCharCode(65 + rem) + letter;
    column = Math.floor((column - 1) / 26);
  }
  return letter;
}

function setScoreFormulas_(sheet, index, row) {
  var scoreCol = index['Score'] + 1;
  var alerteCol = index['Alerte'] + 1;
  var valeur = columnLetter_(index['Valeur'] + 1);
  var effort = columnLetter_(index['Effort'] + 1);
  var echeance = columnLetter_(index['Échéance'] + 1);
  var avancement = columnLetter_(index['Avancement'] + 1);
  if (scoreCol > 0) {
    sheet.getRange(row, scoreCol).setFormula(
      '=IFERROR(IF(AND(' + valeur + row + '<>"",' + effort + row + '<>"",' + effort + row + '>0),' +
      'ROUND(' + valeur + row + '/' + effort + row + ',2),""),"")'
    );
  }
  if (alerteCol > 0) {
    sheet.getRange(row, alerteCol).setFormula(
      '=IF(AND(ISNUMBER(' + echeance + row + '),' + echeance + row + '<TODAY(),' +
      avancement + row + '<>"Livré"),"En retard","")'
    );
  }
}

function setDateCell_(sheet, row, column, value) {
  if (!value) { sheet.getRange(row, column).setValue(''); return; }
  var parts = String(value).split('/');
  if (parts.length === 3) {
    var d = parseInt(parts[0], 10), m = parseInt(parts[1], 10), y = parseInt(parts[2], 10);
    if (!isNaN(d) && !isNaN(m) && !isNaN(y)) {
      sheet.getRange(row, column).setValue(new Date(y, m - 1, d));
      return;
    }
  }
  sheet.getRange(row, column).setValue(sanitize_(value));
}

function numberOrBlank_(value) {
  var n = Number(value);
  return value === '' || value == null || isNaN(n) ? '' : n;
}

function text_(value) {
  if (value == null) return '';
  if (value instanceof Date) return Utilities.formatDate(value, TZ, 'dd/MM/yyyy');
  return String(value);
}

function dateText_(value) {
  if (value instanceof Date) return Utilities.formatDate(value, TZ, 'dd/MM/yyyy');
  return value == null ? '' : String(value);
}

function sanitize_(value) {
  if (value == null) return '';
  var s = String(value);
  if (s.charAt(0) === '=' || s.charAt(0) === '+' || s.charAt(0) === '@') {
    return "'" + s;
  }
  return s;
}
