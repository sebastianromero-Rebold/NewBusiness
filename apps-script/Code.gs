/**
 * Rebold · NewBusiness — backend en Google Apps Script
 * ----------------------------------------------------
 * Este script es el "servidor" del aplicativo (index.html en GitHub Pages).
 * No requiere cuenta de Google Cloud: corre con la cuenta de Google Workspace
 * de quien lo despliega. Se encarga de:
 *   - Base de datos de propuestas + log de auditoría en Google Sheets
 *   - Carpetas por marca en Google Drive y conversión .pptx → Google Slides
 *   - Proxy hacia la API de Claude (la API key vive aquí, nunca en el HTML)
 *   - Transcripción de audios (opcional, con OpenAI Whisper)
 *   - Notificaciones por Slack a los directores y correos de aprobación
 *
 * Instalación: ver README.md del repositorio (sección "Backend").
 *
 * Propiedades del script (Configuración del proyecto → Propiedades del script):
 *   TEAM_CODE          (obligatoria) código de acceso que comparte el equipo
 *   ANTHROPIC_API_KEY  (opcional)    API key de Claude para generación automática. Sin ella,
 *                                    la app usa el modo "copiar y pegar" con la cuenta de claude.ai
 *   CLAUDE_MODEL       (opcional)    por defecto: claude-opus-5
 *   SLACK_BOT_TOKEN    (opcional)    xoxb-… para mensaje directo a cada director
 *   SLACK_CHANNEL_ID   (opcional)    ID de un canal (C…) donde la app también publica los avisos
 *   SLACK_WEBHOOK_URL  (opcional)    alternativa sin bot: webhook de un canal con menciones
 *   OPENAI_API_KEY     (opcional)    para transcribir audios subidos
 *   DIRECTIVOS_CC      (opcional)    correos extra separados por coma para la aprobación final
 *   APP_URL            (opcional)    URL pública del aplicativo (GitHub Pages)
 *   SPREADSHEET_ID / ROOT_FOLDER_ID  se crean solos en el primer uso
 */

var VERSION = '1.0.0';

var DEFAULT_APP_URL = 'https://sebastianromero-rebold.github.io/NewBusiness/';

// Directores de área que pueden revisar propuestas.
// IDs de Slack del workspace de ISPD, confirmados por Sebastian Romero (sep-2026).
// Verifica los correos antes de salir a producción.
var DIRECTORES = [
  { nombre: 'Natalia Patiño',    email: 'andrea.patino@letsrebold.com',    slack: 'U0BKUAQ8P5M' },
  { nombre: 'Javier Lozano',     email: 'javier.lozano@letsrebold.com',    slack: 'U0BL3E8L9J7' },
  { nombre: 'Jennifer Carvajal', email: 'jennifer.carvajal@letsrebold.com', slack: 'U0BL3EA7KNF' },
  { nombre: 'Sebastian Romero',  email: 'sebastian.romero@letsrebold.com', slack: 'U0BL3E8USLB' },
  { nombre: 'Alejandro Muller',  email: 'alejandro.muller@letsrebold.com', slack: 'U0ABN2XGUKD' }
];

var ESTADOS = ['Borrador', 'En revisión', 'Ajustes solicitados', 'Aprobada interna',
  'Enviada', 'Presentada', 'Aprobada', 'Rechazada', 'Eliminada'];

var COLS_PROP = ['id', 'creado', 'actualizado', 'marca', 'presupuesto', 'moneda', 'periodicidad',
  'tipoCliente', 'comercial', 'comercialEmail', 'clientes', 'directores', 'estado', 'version',
  'slidesUrl', 'slidesId', 'carpetaUrl', 'deckFileId', 'revisiones', 'resumen', 'creadoPor'];
var COLS_LOG = ['fecha', 'usuario', 'email', 'accion', 'propuestaId', 'marca', 'detalle', 'snapshot'];

// ───────────────────────────── Entradas HTTP ─────────────────────────────

function doGet() {
  return json_({ ok: true, service: 'rebold-newbusiness', version: VERSION });
}

function doPost(e) {
  var req;
  try {
    req = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: 'Solicitud inválida' });
  }
  var props = PropertiesService.getScriptProperties();
  var teamCode = props.getProperty('TEAM_CODE');
  if (!teamCode) return json_({ ok: false, error: 'Falta configurar TEAM_CODE en el backend' });
  if (String(req.code || '') !== teamCode) return json_({ ok: false, error: 'Código de equipo inválido' });

  var user = req.user || {};
  try {
    var fn = ACTIONS[req.action];
    if (!fn) return json_({ ok: false, error: 'Acción desconocida: ' + req.action });
    var out = fn(req, user) || {};
    out.ok = true;
    return json_(out);
  } catch (err) {
    try { log_(user, 'error', req.id || '', '', String(err && err.message || err), ''); } catch (e2) {}
    return json_({ ok: false, error: String(err && err.message || err) });
  }
}

var ACTIONS = {
  ping: function () {
    return {
      version: VERSION,
      directores: DIRECTORES.map(function (d) { return { nombre: d.nombre, email: d.email }; }),
      estados: ESTADOS,
      model: modelo_(),
      ia: !!prop_('ANTHROPIC_API_KEY'),
      transcripcion: !!prop_('OPENAI_API_KEY'),
      slack: !!(prop_('SLACK_BOT_TOKEN') || prop_('SLACK_WEBHOOK_URL'))
    };
  },

  // Proxy a Claude. El navegador arma el prompt; aquí solo se agrega la API key.
  llm: function (req, user) {
    var key = prop_('ANTHROPIC_API_KEY');
    if (!key) throw new Error('Falta ANTHROPIC_API_KEY en el backend');
    var body = {
      model: modelo_(),
      max_tokens: Math.min(Number(req.max_tokens) || 8000, 16000),
      system: [{ type: 'text', text: String(req.system || ''), cache_control: { type: 'ephemeral' } }],
      messages: req.messages,
      output_config: { effort: req.effort || 'medium' },
      fallbacks: 'default'
    };
    var res = claude_(key, body, true);
    if (res.code === 400 && /fallback/i.test(res.text)) {
      delete body.fallbacks;
      res = claude_(key, body, false);
    }
    if (res.code !== 200) throw new Error('Claude API ' + res.code + ': ' + res.text.slice(0, 400));
    var data = JSON.parse(res.text);
    if (data.stop_reason === 'refusal') throw new Error('El modelo declinó la solicitud. Revisa el material cargado.');
    var text = (data.content || []).filter(function (b) { return b.type === 'text'; })
      .map(function (b) { return b.text; }).join('');
    return { text: text, stop_reason: data.stop_reason, usage: data.usage };
  },

  transcribe: function (req, user) {
    var key = prop_('OPENAI_API_KEY');
    if (!key) throw new Error('La transcripción de audios no está configurada (falta OPENAI_API_KEY).');
    var blob = Utilities.newBlob(Utilities.base64Decode(req.data), req.mime || 'audio/mpeg', req.name || 'audio');
    var res = UrlFetchApp.fetch('https://api.openai.com/v1/audio/transcriptions', {
      method: 'post',
      headers: { Authorization: 'Bearer ' + key },
      payload: { file: blob, model: 'whisper-1', language: 'es' },
      muteHttpExceptions: true
    });
    if (res.getResponseCode() !== 200) throw new Error('Transcripción falló: ' + res.getContentText().slice(0, 300));
    log_(user, 'transcribir_audio', req.id || '', '', req.name || '', '');
    return { text: JSON.parse(res.getContentText()).text };
  },

  list: function () {
    return { propuestas: leerPropuestas_() };
  },

  get: function (req) {
    var p = buscar_(req.id);
    if (!p) throw new Error('Propuesta no encontrada');
    var deck = null;
    if (p.deckFileId) {
      try { deck = JSON.parse(DriveApp.getFileById(p.deckFileId).getBlob().getDataAsString('UTF-8')); } catch (e) {}
    }
    return { propuesta: p, deck: deck };
  },

  // Crea o actualiza la propuesta. Si viene deck, se guarda como JSON en Drive (una versión por guardado).
  save: function (req, user) {
    return conLock_(function () {
      var p = req.propuesta || {};
      var existente = p.id ? buscar_(p.id) : null;
      var ahora = new Date().toISOString();
      if (!existente) {
        p.id = p.id || nuevoId_();
        p.creado = ahora;
        p.estado = p.estado || 'Borrador';
        p.version = 0;
        p.creadoPor = user.email || user.nombre || '';
        p.revisiones = [];
      } else {
        // Campos que solo cambia el backend
        ['creado', 'creadoPor', 'slidesUrl', 'slidesId', 'carpetaUrl', 'revisiones', 'version', 'deckFileId']
          .forEach(function (k) { if (p[k] === undefined || k === 'revisiones' || k === 'creado') p[k] = existente[k]; });
        if (!p.estado) p.estado = existente.estado;
      }
      p.actualizado = ahora;
      var folder = carpetaMarca_(p.marca);
      p.carpetaUrl = folder.getUrl();
      if (req.deck) {
        var nombre = 'deck_v' + ((Number(p.version) || 0) + 1) + '_' + ahora.slice(0, 19).replace(/[:T]/g, '-') + '.json';
        var f = folder.createFile(nombre, JSON.stringify(req.deck), 'application/json');
        p.deckFileId = f.getId();
      }
      escribir_(p);
      log_(user, existente ? 'actualizar_propuesta' : 'crear_propuesta', p.id, p.marca,
        req.detalle || '', existente ? JSON.stringify(existente) : '');
      return { propuesta: p };
    });
  },

  // Recibe el .pptx en base64 y lo convierte en Google Slides dentro de la carpeta de la marca.
  uploadDeck: function (req, user) {
    var p = buscar_(req.id);
    if (!p) throw new Error('Propuesta no encontrada');
    var folder = carpetaMarca_(p.marca);
    var version = (Number(p.version) || 0) + 1;
    var nombre = p.marca + ' · Propuesta Rebold · v' + version;
    var blob = Utilities.newBlob(Utilities.base64Decode(req.data),
      'application/vnd.openxmlformats-officedocument.presentationml.presentation', nombre + '.pptx');
    var file = Drive.Files.create({ name: nombre, mimeType: MimeType.GOOGLE_SLIDES, parents: [folder.getId()] }, blob);
    compartir_(file.id, p);
    return conLock_(function () {
      var prev = JSON.stringify(p);
      p.slidesId = file.id;
      p.slidesUrl = 'https://docs.google.com/presentation/d/' + file.id + '/edit';
      p.version = version;
      p.carpetaUrl = folder.getUrl();
      p.actualizado = new Date().toISOString();
      escribir_(p);
      log_(user, 'guardar_en_drive', p.id, p.marca, 'Google Slides v' + version + ': ' + p.slidesUrl, prev);
      return { propuesta: p };
    });
  },

  // Guarda material fuente (notas, audios, PDFs…) como respaldo en Drive.
  uploadFile: function (req, user) {
    var p = buscar_(req.id);
    if (!p) throw new Error('Propuesta no encontrada');
    var folder = subcarpeta_(carpetaMarca_(p.marca), 'Material de reunión');
    var blob = Utilities.newBlob(Utilities.base64Decode(req.data), req.mime || 'application/octet-stream', req.name || 'archivo');
    var f = folder.createFile(blob);
    log_(user, 'subir_material', p.id, p.marca, req.name + ' → ' + f.getUrl(), '');
    return { url: f.getUrl() };
  },

  // El comercial envía a revisión: notifica por Slack a los directores seleccionados.
  submitReview: function (req, user) {
    return conLock_(function () {
      var p = buscar_(req.id);
      if (!p) throw new Error('Propuesta no encontrada');
      var prev = JSON.stringify(p);
      p.estado = 'En revisión';
      p.revisiones = (p.revisiones || []).concat([{
        fecha: new Date().toISOString(), tipo: 'envio', por: user.nombre || '', version: p.version, comentario: req.comentario || ''
      }]);
      p.actualizado = new Date().toISOString();
      escribir_(p);
      var link = appUrl_() + '#/review/' + p.id;
      var dirs = directoresDe_(p);
      var menciones = dirs.map(function (d) { return d.slack ? '<@' + d.slack + '>' : d.nombre; }).join(' ');
      var texto = ':memo: *Nueva propuesta para revisión* — *' + p.marca + '*\n' +
        'Comercial: ' + (p.comercial || '-') + ' · Presupuesto: ' + dinero_(p.presupuesto, p.moneda) +
        (p.periodicidad ? ' (' + p.periodicidad + ')' : '') + ' · v' + p.version + '\n' +
        (req.comentario ? '> ' + req.comentario + '\n' : '') +
        ':point_right: Revisar y aprobar / pedir ajustes: ' + link +
        (p.slidesUrl ? '\n:file_folder: Google Slides en Drive: ' + p.slidesUrl : '');
      var r = slack_(dirs, menciones + ' ' + texto);
      log_(user, 'enviar_a_revision', p.id, p.marca, 'Slack → ' + dirs.map(function (d) { return d.nombre; }).join(', ') + ' · ' + r, prev);
      return { propuesta: p, slack: r };
    });
  },

  // Decisión de un director: aprobar | ajustes | validar
  review: function (req, user) {
    return conLock_(function () {
      var p = buscar_(req.id);
      if (!p) throw new Error('Propuesta no encontrada');
      var prev = JSON.stringify(p);
      var quien = req.director || user.nombre || '';
      var decision = req.decision;
      if (['aprobar', 'ajustes', 'validar'].indexOf(decision) < 0) throw new Error('Decisión inválida');
      p.revisiones = (p.revisiones || []).concat([{
        fecha: new Date().toISOString(), tipo: decision, por: quien, version: p.version, comentario: req.comentario || ''
      }]);
      var link = appUrl_() + '#/review/' + p.id;
      var editar = appUrl_() + '#/p/' + p.id;
      var notas = [];

      if (decision === 'ajustes') {
        p.estado = 'Ajustes solicitados';
        slack_([], ':warning: *Ajustes solicitados* en *' + p.marca + '* por ' + quien + ':\n> ' +
          (req.comentario || '(sin comentario)') + '\nEditar: ' + editar);
        if (p.comercialEmail) {
          correo_(p.comercialEmail, '', 'Ajustes solicitados · ' + p.marca,
            '<p>' + esc_(quien) + ' solicitó ajustes a la propuesta <b>' + esc_(p.marca) + '</b> (v' + p.version + '):</p>' +
            '<blockquote>' + esc_(req.comentario || '') + '</blockquote>' +
            '<p><a href="' + editar + '">Abrir la propuesta para ajustarla</a></p>');
          notas.push('correo al comercial');
        }
      } else if (decision === 'aprobar') {
        var dirs = directoresDe_(p);
        var aprobados = {};
        p.revisiones.forEach(function (r) {
          // Solo cuentan los aprobados de la versión vigente (tras ajustes se vuelve a aprobar)
          if (r.version == p.version && r.tipo === 'aprobar') aprobados[r.por] = true;
        });
        var pendientes = dirs.filter(function (d) { return !aprobados[d.nombre]; });
        if (pendientes.length === 0) {
          p.estado = 'Aprobada interna';
          // Aprobado final → correo a los directivos implicados para validar
          var para = dirs.map(function (d) { return d.email; }).filter(String);
          var cc = (prop_('DIRECTIVOS_CC') || '').split(',').map(function (s) { return s.trim(); }).filter(String);
          if (p.comercialEmail) cc.push(p.comercialEmail);
          correo_(para.join(','), cc.join(','), 'Propuesta aprobada para validar · ' + p.marca,
            '<p>La propuesta <b>' + esc_(p.marca) + '</b> recibió el aprobado final de revisión.</p>' +
            '<ul><li>Comercial: ' + esc_(p.comercial || '-') + '</li>' +
            '<li>Presupuesto: ' + esc_(dinero_(p.presupuesto, p.moneda)) + (p.periodicidad ? ' (' + esc_(p.periodicidad) + ')' : '') + '</li>' +
            '<li>Versión: v' + p.version + '</li></ul>' +
            '<p>Por favor apruébala y valídala antes de enviarla al cliente:</p>' +
            '<p><a href="' + link + '">Validar propuesta en la plataforma</a>' +
            (p.slidesUrl ? ' · <a href="' + p.slidesUrl + '">Abrir en Google Slides</a>' : '') + '</p>');
          notas.push('correo de validación a ' + para.join(', '));
          slack_([], ':white_check_mark: *' + p.marca + '* aprobada internamente. Se envió correo de validación a los directivos.');
        } else {
          notas.push('faltan: ' + pendientes.map(function (d) { return d.nombre; }).join(', '));
        }
      } else if (decision === 'validar') {
        notas.push('validación registrada');
      }
      p.actualizado = new Date().toISOString();
      escribir_(p);
      log_(user, 'revision_' + decision, p.id, p.marca, quien + ': ' + (req.comentario || '') + (notas.length ? ' · ' + notas.join(' · ') : ''), prev);
      return { propuesta: p, notas: notas };
    });
  },

  status: function (req, user) {
    if (ESTADOS.indexOf(req.estado) < 0) throw new Error('Estado inválido');
    return conLock_(function () {
      var p = buscar_(req.id);
      if (!p) throw new Error('Propuesta no encontrada');
      var prev = JSON.stringify(p);
      var anterior = p.estado;
      p.estado = req.estado;
      p.actualizado = new Date().toISOString();
      escribir_(p);
      log_(user, req.estado === 'Eliminada' ? 'eliminar_propuesta' : 'cambiar_estado', p.id, p.marca,
        anterior + ' → ' + req.estado + (req.comentario ? ' · ' + req.comentario : ''), prev);
      return { propuesta: p };
    });
  },

  logEvent: function (req, user) {
    log_(user, req.accion || 'evento', req.id || '', req.marca || '', req.detalle || '', '');
    return {};
  },

  log: function (req) {
    var sh = hoja_('Log', COLS_LOG);
    var n = sh.getLastRow() - 1;
    if (n <= 0) return { log: [] };
    var limite = Math.min(Number(req.limit) || 300, n);
    var vals = sh.getRange(sh.getLastRow() - limite + 1, 1, limite, COLS_LOG.length).getValues();
    var out = vals.reverse().map(function (r) {
      var o = {};
      COLS_LOG.forEach(function (c, i) { o[c] = c === 'snapshot' ? (r[i] ? '1' : '') : r[i]; });
      if (o.fecha instanceof Date) o.fecha = o.fecha.toISOString();
      return o;
    });
    return { log: out, sheetUrl: libro_().getUrl() };
  }
};

// ───────────────────────────── Sheets ─────────────────────────────

function libro_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SPREADSHEET_ID');
  if (id) {
    try { return SpreadsheetApp.openById(id); } catch (e) {}
  }
  var ss = SpreadsheetApp.create('Rebold NewBusiness · Base de propuestas y log');
  props.setProperty('SPREADSHEET_ID', ss.getId());
  try { DriveApp.getFileById(ss.getId()).moveTo(raiz_()); } catch (e) {}
  return ss;
}

function hoja_(nombre, cols) {
  var ss = libro_();
  var sh = ss.getSheetByName(nombre);
  if (!sh) {
    sh = ss.insertSheet(nombre);
    sh.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
    sh.setFrozenRows(1);
    var def = ss.getSheetByName('Hoja 1') || ss.getSheetByName('Sheet1');
    if (def && ss.getSheets().length > 1) ss.deleteSheet(def);
  }
  return sh;
}

var JSON_COLS = { clientes: 1, directores: 1, revisiones: 1, resumen: 1 };

function leerPropuestas_() {
  var sh = hoja_('Propuestas', COLS_PROP);
  var n = sh.getLastRow() - 1;
  if (n <= 0) return [];
  var vals = sh.getRange(2, 1, n, COLS_PROP.length).getValues();
  return vals.map(fila_).filter(function (p) { return p.id; });
}

function fila_(r) {
  var o = {};
  COLS_PROP.forEach(function (c, i) {
    var v = r[i];
    if (v instanceof Date) v = v.toISOString();
    if (JSON_COLS[c]) { try { v = v ? JSON.parse(v) : (c === 'resumen' ? null : []); } catch (e) { v = []; } }
    o[c] = v;
  });
  return o;
}

function buscar_(id) {
  if (!id) return null;
  var ps = leerPropuestas_();
  for (var i = 0; i < ps.length; i++) if (ps[i].id === id) return ps[i];
  return null;
}

function escribir_(p) {
  var sh = hoja_('Propuestas', COLS_PROP);
  var fila = COLS_PROP.map(function (c) {
    var v = p[c];
    if (JSON_COLS[c]) return JSON.stringify(v || (c === 'resumen' ? null : []));
    return v === undefined || v === null ? '' : v;
  });
  var n = sh.getLastRow() - 1;
  if (n > 0) {
    var ids = sh.getRange(2, 1, n, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (ids[i][0] === p.id) { sh.getRange(i + 2, 1, 1, fila.length).setValues([fila]); return; }
    }
  }
  sh.appendRow(fila);
}

function log_(user, accion, id, marca, detalle, snapshot) {
  var sh = hoja_('Log', COLS_LOG);
  sh.appendRow([new Date(), user.nombre || '', user.email || '', accion, id || '', marca || '',
    String(detalle || '').slice(0, 5000), String(snapshot || '').slice(0, 45000)]);
}

// ───────────────────────────── Drive ─────────────────────────────

function raiz_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('ROOT_FOLDER_ID');
  if (id) { try { return DriveApp.getFolderById(id); } catch (e) {} }
  var f = DriveApp.createFolder('Rebold · Propuestas NewBusiness');
  try { f.setSharing(DriveApp.Access.DOMAIN_WITH_LINK, DriveApp.Permission.EDIT); } catch (e) {}
  props.setProperty('ROOT_FOLDER_ID', f.getId());
  return f;
}

function carpetaMarca_(marca) {
  return subcarpeta_(raiz_(), String(marca || 'Sin marca').trim() || 'Sin marca');
}

function subcarpeta_(padre, nombre) {
  var it = padre.getFoldersByName(nombre);
  return it.hasNext() ? it.next() : padre.createFolder(nombre);
}

// Da acceso de edición a directores y comercial sin enviar correos de Drive.
function compartir_(fileId, p) {
  var correos = directoresDe_(p).map(function (d) { return d.email; });
  if (p.comercialEmail) correos.push(p.comercialEmail);
  correos.filter(String).forEach(function (email) {
    try {
      Drive.Permissions.create({ role: 'writer', type: 'user', emailAddress: email }, fileId, { sendNotificationEmail: false });
    } catch (e) {}
  });
}

// ───────────────────────────── Notificaciones ─────────────────────────────

function directoresDe_(p) {
  var nombres = p.directores || [];
  return DIRECTORES.filter(function (d) { return nombres.indexOf(d.nombre) >= 0; });
}

function slack_(dirs, texto) {
  var enviados = [];
  var token = prop_('SLACK_BOT_TOKEN');
  var postear = function (canal) {
    var r = UrlFetchApp.fetch('https://slack.com/api/chat.postMessage', {
      method: 'post', contentType: 'application/json; charset=utf-8',
      headers: { Authorization: 'Bearer ' + token },
      payload: JSON.stringify({ channel: canal, text: texto }), muteHttpExceptions: true
    });
    try { return JSON.parse(r.getContentText()).ok; } catch (e) { return false; }
  };
  if (token) {
    // Mensaje directo a cada director (el ID de usuario abre el chat con la app)
    dirs.forEach(function (d) { if (d.slack && postear(d.slack)) enviados.push('DM ' + d.nombre); });
    // Canal del equipo (opcional): la app debe estar agregada al canal
    var canal = prop_('SLACK_CHANNEL_ID');
    if (canal && postear(canal)) enviados.push('canal');
  }
  var hook = prop_('SLACK_WEBHOOK_URL');
  if (hook) {
    var r2 = UrlFetchApp.fetch(hook, {
      method: 'post', contentType: 'application/json; charset=utf-8',
      payload: JSON.stringify({ text: texto }), muteHttpExceptions: true
    });
    if (r2.getResponseCode() === 200) enviados.push('canal');
  }
  return enviados.length ? enviados.join(', ') : 'Slack no configurado';
}

function correo_(para, cc, asunto, html) {
  if (!para) return;
  var opts = {
    to: para, subject: '[Rebold NewBusiness] ' + asunto, name: 'Rebold NewBusiness',
    htmlBody: '<div style="font-family:Arial,sans-serif;font-size:14px;color:#111">' + html +
      '<p style="color:#888;font-size:12px">Mensaje automático de la plataforma de propuestas de Rebold.</p></div>'
  };
  if (cc) opts.cc = cc;
  MailApp.sendEmail(opts);
}

// ───────────────────────────── Utilidades ─────────────────────────────

function claude_(key, body, conFallback) {
  var headers = { 'x-api-key': key, 'anthropic-version': '2023-06-01' };
  if (conFallback) headers['anthropic-beta'] = 'server-side-fallback-2026-07-01';
  var r = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
    method: 'post', contentType: 'application/json', headers: headers,
    payload: JSON.stringify(body), muteHttpExceptions: true
  });
  return { code: r.getResponseCode(), text: r.getContentText() };
}

function conLock_(fn) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try { return fn(); } finally { lock.releaseLock(); }
}

function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function modelo_() { return prop_('CLAUDE_MODEL') || 'claude-opus-5'; }
function appUrl_() { return prop_('APP_URL') || DEFAULT_APP_URL; }
function nuevoId_() { return 'P' + Utilities.formatDate(new Date(), 'GMT', 'yyMMdd') + '-' + Utilities.getUuid().slice(0, 6).toUpperCase(); }
function dinero_(v, m) { return (m || 'COP') + ' $' + Number(v || 0).toLocaleString('es-CO'); }
function esc_(s) { return String(s || '').replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

/** Ejecuta esto una vez desde el editor para autorizar permisos y crear la hoja y la carpeta. */
function setup() {
  hoja_('Propuestas', COLS_PROP);
  hoja_('Log', COLS_LOG);
  Logger.log('Hoja: ' + libro_().getUrl());
  Logger.log('Carpeta: ' + raiz_().getUrl());
  MailApp.getRemainingDailyQuota();
  UrlFetchApp.fetch('https://api.anthropic.com', { muteHttpExceptions: true });
}
