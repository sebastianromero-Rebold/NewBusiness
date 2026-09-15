"""De Nota de Reunión a Propuesta Comercial — Rebold.

App local (Flask) que implementa el pipeline completo del brief:
ingesta -> señales -> diagnóstico por reglas -> narrativa -> pricing controlado
-> .pptx borrador -> descarga para revisión humana obligatoria.

Correr:
    pip install -r requirements.txt
    python app.py
Luego abrir http://127.0.0.1:5000
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

from deck.builder import ContenidoPropuesta, construir_pptx
from pipeline import diagnostic_engine, ingest, narrative, signals, store
from pipeline.llm import get_llm_provider
from pricing import provider as pricing_provider

BASE_DIR = Path(__file__).resolve().parent
DRAFTS_DIR = BASE_DIR / "data" / "drafts"
AUDIT_LOG = BASE_DIR / "data" / "audit_log.jsonl"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-solo-local-no-usar-en-produccion")

# Almacén en memoria del proceso — suficiente para una app local de un solo
# usuario. Si se despliega para varias personas a la vez, cambiar por una
# base de datos real.
DRAFTS: dict[str, dict] = {}

LLM = get_llm_provider()

SERVICIOS_DISPONIBLES = [info["nombre"] for info in diagnostic_engine.SERVICIOS.values()]


@app.route("/", methods=["GET"])
def dashboard():
    return render_template(
        "dashboard.html",
        marcas=store.resumen_por_marca(),
        llm_modo=LLM.name,
    )


@app.route("/nueva", methods=["GET"])
def nueva_propuesta():
    return render_template(
        "index.html",
        llm_modo=LLM.name,
        servicios_disponibles=SERVICIOS_DISPONIBLES,
    )


@app.route("/procesar", methods=["POST"])
def procesar():
    cliente = request.form.get("cliente", "").strip()
    tipo_relacion = request.form.get("tipo_relacion", "")
    texto_manual = request.form.get("texto_bruto", "").strip()
    participantes = request.form.get("participantes", "")
    contacto_nombre = request.form.get("contacto_nombre", "").strip()
    contacto_email = request.form.get("contacto_email", "").strip()
    servicios_actuales_raw = request.form.get("servicios_actuales", "").strip()

    valores_previos = {
        "cliente": cliente,
        "tipo_relacion": tipo_relacion,
        "texto_bruto": texto_manual,
        "participantes": participantes,
        "contacto_nombre": contacto_nombre,
        "contacto_email": contacto_email,
        "servicios_actuales": servicios_actuales_raw,
    }

    archivo = request.files.get("archivo_docx")
    texto_bruto = texto_manual
    if archivo and archivo.filename:
        try:
            texto_bruto = ingest.leer_docx(archivo)
        except Exception as exc:  # noqa: BLE001
            flash(f"No se pudo leer el .docx: {exc}")
            return redirect(url_for("nueva_propuesta"))

    if tipo_relacion not in ingest.TIPOS_RELACION_VALIDOS:
        flash("Debes indicar si es un cliente actual o un prospecto nuevo — la app no puede asumirlo.")
        return redirect(url_for("nueva_propuesta"))

    if not texto_bruto:
        flash("Pega el texto de la nota o sube un .docx.")
        return redirect(url_for("nueva_propuesta"))

    servicios_actuales_declarados = [
        s.strip() for s in servicios_actuales_raw.split(",") if s.strip() and s.strip().lower() != "no sé"
    ]

    try:
        nota = ingest.normalizar(
            cliente=cliente,
            tipo_relacion=tipo_relacion,
            texto_bruto=texto_bruto,
            participantes=participantes,
            contacto_nombre=contacto_nombre,
            contacto_email=contacto_email,
            servicios_actuales_declarados=servicios_actuales_declarados,
        )
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("nueva_propuesta"))

    senales = signals.extraer(nota, LLM)

    # OJO: no cortamos aquí solo porque no se detectó un dolor explícito. La
    # regla dura de diagnostic_engine ("prospecto nuevo sin señal fuerte →
    # default Rebold Audit") es precisamente el manejo válido de ese caso para
    # prospectos nuevos, y necesita correr antes de decidir si de verdad
    # hace falta pedirle más info al ejecutivo. Solo bloqueamos si, después de
    # aplicar esa regla, el motor sigue sin tener nada que recomendar
    # (típicamente: cliente actual sin dolor y sin servicios declarados).
    diagnosis = diagnostic_engine.diagnosticar(nota, senales)

    if not diagnosis.recomendaciones:
        mensaje = senales.mensaje_aclaracion or (
            "El motor de diagnóstico no encontró un servicio claro para recomendar con la "
            "información disponible. Agrega más detalle a la nota (dolor explícito del cliente) "
            "e inténtalo de nuevo."
        )
        return render_template(
            "index.html",
            llm_modo=LLM.name,
            servicios_disponibles=SERVICIOS_DISPONIBLES,
            mensaje_aclaracion=mensaje,
            valores_previos=valores_previos,
        )

    narrativa = narrative.construir(nota, senales, diagnosis, LLM)

    draft_id = uuid.uuid4().hex[:12]
    DRAFTS[draft_id] = {
        "nota": nota,
        "senales": senales,
        "diagnosis": diagnosis,
        "narrativa": narrativa,
        "lineas_inversion": {},  # servicio_nombre -> LineaInversion dict
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    }

    store.crear_propuesta(
        draft_id=draft_id,
        marca=nota.cliente,
        tipo_relacion=nota.tipo_relacion,
        contacto_nombre=nota.contacto_nombre,
        contacto_email=nota.contacto_email,
        servicios_recomendados=[r.nombre for r in diagnosis.recomendaciones],
    )

    return redirect(url_for("revisar", draft_id=draft_id))


@app.route("/revisar/<draft_id>", methods=["GET"])
def revisar(draft_id: str):
    draft = DRAFTS.get(draft_id)
    if not draft:
        flash("Ese borrador ya no existe en memoria (¿reiniciaste la app?). Procesa la nota de nuevo.")
        return redirect(url_for("nueva_propuesta"))

    diagnosis = draft["diagnosis"]
    modalidades_por_servicio = {
        rec.nombre: pricing_provider.listar_modalidades(rec.nombre) for rec in diagnosis.recomendaciones
    }

    return render_template(
        "review.html",
        draft_id=draft_id,
        nota=draft["nota"],
        senales=draft["senales"],
        diagnosis=diagnosis,
        narrativa=draft["narrativa"],
        modalidades_por_servicio=modalidades_por_servicio,
        lineas_inversion=draft["lineas_inversion"],
        fuente_pricing=pricing_provider.meta_fuente(),
        llm_modo=LLM.name,
    )


@app.route("/revisar/<draft_id>/pricing", methods=["POST"])
def calcular_pricing(draft_id: str):
    draft = DRAFTS.get(draft_id)
    if not draft:
        flash("Ese borrador ya no existe. Procesa la nota de nuevo.")
        return redirect(url_for("nueva_propuesta"))

    diagnosis = draft["diagnosis"]
    inv_digital = request.form.get("inversion_digital_mensual", "").strip()
    inv_atl = request.form.get("inversion_atl_mensual", "").strip()
    inv_digital_val = float(inv_digital) if inv_digital else None
    inv_atl_val = float(inv_atl) if inv_atl else None

    lineas = {}
    for rec in diagnosis.recomendaciones:
        modalidad = request.form.get(f"modalidad__{rec.servicio_id}") or None
        linea = pricing_provider.resolver(
            rec.nombre,
            modalidad,
            inversion_digital_mensual=inv_digital_val,
            inversion_atl_mensual=inv_atl_val,
        )
        lineas[rec.nombre] = {
            "servicio": linea.servicio,
            "modalidad": linea.modalidad,
            "estado": linea.estado,
            "texto_cliente": linea.texto_cliente,
            "nota_interna": linea.nota_interna,
        }
    draft["lineas_inversion"] = lineas

    return redirect(url_for("revisar", draft_id=draft_id))


@app.route("/revisar/<draft_id>/generar", methods=["POST"])
def generar(draft_id: str):
    draft = DRAFTS.get(draft_id)
    if not draft:
        flash("Ese borrador ya no existe. Procesa la nota de nuevo.")
        return redirect(url_for("nueva_propuesta"))

    nota = draft["nota"]
    diagnosis = draft["diagnosis"]
    narrativa = draft["narrativa"]
    lineas_inversion = draft["lineas_inversion"]

    if not lineas_inversion:
        flash("Calcula la inversión (elige modalidad para cada servicio) antes de generar el archivo.")
        return redirect(url_for("revisar", draft_id=draft_id))

    diagnosis_dict = diagnostic_engine.diagnosis_a_dict(diagnosis)

    contenido = ContenidoPropuesta(
        cliente=nota.cliente,
        fecha=nota.fecha,
        tipo_relacion=nota.tipo_relacion,
        contacto_nombre=nota.contacto_nombre,
        contacto_email=nota.contacto_email,
        narrativa_contexto=narrativa.contexto,
        narrativa_insight=narrativa.insight,
        dolor_principal_cita=diagnosis.recomendaciones[0].dolor_citado,
        recomendaciones=diagnosis_dict["recomendaciones"],
        camino_de_cuenta=narrativa.camino_de_cuenta,
        oportunidades_futuras=diagnosis.oportunidades_futuras,
        lineas_inversion=list(lineas_inversion.values()),
        fuente_pricing=pricing_provider.meta_fuente().get("fuente", "desconocida"),
    )

    nombre_archivo = f"BORRADOR_{nota.cliente.replace(' ', '_')}_{nota.fecha}_{draft_id}.pptx"
    ruta_salida = DRAFTS_DIR / nombre_archivo
    construir_pptx(contenido, str(ruta_salida))

    _registrar_auditoria(draft_id, nota, diagnosis, lineas_inversion, narrativa)
    store.marcar_descargada(draft_id, nombre_archivo)

    return send_file(ruta_salida, as_attachment=True, download_name=nombre_archivo)


def _registrar_auditoria(draft_id, nota, diagnosis, lineas_inversion, narrativa) -> None:
    """Métricas de éxito (Sección 7 del brief): control de alucinación de citas,
    montos pendientes vs. definidos, servicios recomendados, tiempo nota-a-borrador."""
    texto_norm = " ".join(nota.texto_bruto.lower().split())
    citas_ok = all(
        " ".join(rec.dolor_citado.lower().split()) in texto_norm for rec in diagnosis.recomendaciones
    )
    montos_pendientes = [k for k, v in lineas_inversion.items() if v["estado"] == "pendiente"]

    entrada = {
        "draft_id": draft_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "cliente": nota.cliente,
        "tipo_relacion": nota.tipo_relacion,
        "servicios_recomendados": [r.nombre for r in diagnosis.recomendaciones],
        "citas_verbatim_ok": citas_ok,
        "montos_pendientes_de_definir": montos_pendientes,
        "modo_llm": narrativa.modo,
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
