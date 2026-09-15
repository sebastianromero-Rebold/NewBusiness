"""Paso 3 — Motor de diagnóstico. Reglas explícitas de negocio (rebold-servicios-suite),
NO delegadas al LLM. El LLM solo entra después, para redactar narrativa sobre una
decisión que este módulo ya tomó de forma determinística.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ingest import NotaNormalizada
from .signals import Senales

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

with open(DATA_DIR / "casos_prueba.json", encoding="utf-8") as f:
    _CASOS = json.load(f)["casos"]

# --- Catálogo de servicios: pitch + a qué "familia" de pricing corresponde ---
SERVICIOS: dict[str, dict[str, str]] = {
    "insight_factory": {
        "nombre": "Insight Factory",
        "pitch": "Antes de gastar en pauta o contenido, sepamos exactamente a quién le hablamos y qué está esperando de la categoría.",
    },
    "creative_lab": {
        "nombre": "Creative Lab",
        "pitch": "Hackeamos el proceso creativo tradicional con IA para que el contenido no sea el cuello de botella del negocio.",
    },
    "activation_hub": {
        "nombre": "Activation Hub",
        "pitch": "No vendemos más pauta. Vendemos más eficiencia por cada peso invertido.",
    },
    "rebold_audit": {
        "nombre": "Rebold Audit",
        "pitch": "No vendemos auditorías. Vendemos decisiones con impacto económico.",
        "grupo": "growth_engine",
    },
    "audience_nexus": {
        "nombre": "Audience Nexus",
        "pitch": "Tu audiencia ya es un activo. Hoy no la estás cobrando.",
        "grupo": "growth_engine",
    },
    "agent_lab": {
        "nombre": "Agent Lab",
        "pitch": "Tu base de clientes ya existe. Lo que falta es un agente que la active todos los días.",
        "complementario": True,
    },
}

# Matriz de cross-sell / up-sell (rebold-servicios-suite, sección "Matriz de
# cross-selling / up-selling"): qué ofrecer después y por qué, dado lo que el
# cliente ya tiene. Va SOLO a las notas del orador, nunca a la slide visible.
CROSS_SELL: dict[str, list[dict[str, str]]] = {
    "rebold_audit": [
        {"servicio": "activation_hub", "razon": "El AES bajo del audit ya generó la evidencia; solo falta accionarla en medios."},
        {"servicio": "creative_lab", "razon": "El CES bajo del audit ya generó la evidencia; solo falta accionarla en creatividad."},
        {"servicio": "insight_factory", "razon": "El AIS bajo del audit ya generó la evidencia; falta profundizar en investigación."},
        {"servicio": "audience_nexus", "razon": "Si el AIS salió alto, la data 1P ya está madura y es candidata directa a monetizarse."},
    ],
    "insight_factory": [
        {"servicio": "activation_hub", "razon": "Ya se sabe a quién hablarle; falta activar la pauta con ese insight."},
        {"servicio": "creative_lab", "razon": "Ya se sabe a quién hablarle; falta activar el contenido con ese insight."},
        {"servicio": "audience_nexus", "razon": "Si la audiencia mapeada es grande y de valor, se puede monetizar."},
    ],
    "activation_hub": [
        {"servicio": "agent_lab", "razon": "Ya hay tráfico/leads entrando; un agente de IA los convierte en recompra sin subir costo de atención."},
        {"servicio": "creative_lab", "razon": "Si el AES está resuelto pero el CTR sigue bajo, el problema pasó a ser creativo."},
    ],
    "creative_lab": [
        {"servicio": "activation_hub", "razon": "Contenido nuevo necesita el motor de medios optimizado para escalar su alcance."},
    ],
    "agent_lab": [
        {"servicio": "audience_nexus", "razon": "Si ya hay un flujo de datos de usuario activo vía CRM/agentes, esa data también se puede monetizar."},
    ],
}

CATEGORIA_A_SERVICIO = {
    "activation_hub": "activation_hub",
    "creative_lab": "creative_lab",
    "insight_factory": "insight_factory",
    "audience_nexus": "audience_nexus",
    "rebold_audit": "rebold_audit",
    "agent_lab": "agent_lab",
}


@dataclass
class RecomendacionServicio:
    servicio_id: str
    nombre: str
    dolor_citado: str
    pitch: str
    proof_case: dict[str, Any]
    siguiente_paso_cross_sell: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Diagnosis:
    recomendaciones: list[RecomendacionServicio]
    oportunidades_futuras: list[str]
    reglas_aplicadas: list[str]
    camino_de_cuenta: list[str]


def _proof_case_para(servicio_nombre: str) -> dict[str, Any]:
    candidatos = [c for c in _CASOS if c["servicio"] == servicio_nombre]
    if not candidatos:
        return {
            "cliente": None,
            "resumen": "No hay un caso de prueba registrado para este servicio todavía — no se debe fabricar uno.",
            "cifras": [],
            "es_referencia_industria_distinta": False,
        }
    caso = candidatos[0]
    return {**caso, "es_referencia_industria_distinta": False}


def diagnosticar(nota: NotaNormalizada, senales: Senales) -> Diagnosis:
    reglas_aplicadas: list[str] = []
    candidatos_orden: list[tuple[str, str]] = []  # [(servicio_id, dolor_citado)]

    for dolor in senales.dolores:
        servicio_id = CATEGORIA_A_SERVICIO.get(dolor["categoria"])
        if not servicio_id:
            continue
        if servicio_id == "agent_lab" and not senales.señal_crm_dormido:
            # Regla dura: Agent Lab nunca sin señal explícita de CRM/base dormida.
            reglas_aplicadas.append(
                "Se detectó lenguaje relacionado a Agent Lab pero SIN señal explícita de "
                "CRM/base dormida confirmada — se descarta como candidato de apertura."
            )
            continue
        candidatos_orden.append((servicio_id, dolor["cita"]))

    # Default para prospecto nuevo sin señal fuerte: Rebold Audit (regla dura).
    # OJO: dolor_citado queda vacío a propósito — no hay una frase textual del
    # cliente que citar, y no se debe fabricar una que parezca una cita real.
    if nota.tipo_relacion == "prospecto_nuevo" and not candidatos_orden:
        candidatos_orden.append(("rebold_audit", ""))
        reglas_aplicadas.append(
            "Prospecto nuevo sin señal fuerte de otro servicio → apertura por defecto con Rebold Audit."
        )

    if not candidatos_orden:
        return Diagnosis(recomendaciones=[], oportunidades_futuras=[], reglas_aplicadas=reglas_aplicadas, camino_de_cuenta=[])

    # Merge Growth Engine: si Rebold Audit y Audience Nexus aparecen ambos,
    # se presentan como una sola línea narrativa (regla dura), ocupando 1 de los 2 slots.
    servicios_vistos: list[str] = []
    dolores_por_servicio: dict[str, str] = {}
    for servicio_id, cita in candidatos_orden:
        if servicio_id not in servicios_vistos:
            servicios_vistos.append(servicio_id)
            dolores_por_servicio[servicio_id] = cita

    growth_engine_merge = "rebold_audit" in servicios_vistos and "audience_nexus" in servicios_vistos
    if growth_engine_merge:
        reglas_aplicadas.append(
            "Rebold Audit y Audience Nexus detectados juntos → se presentan como una sola línea narrativa (Growth Engine)."
        )
        # Reordenar para que el merge cuente como un solo slot, en la posición del primero de los dos.
        primero = next(s for s in servicios_vistos if s in ("rebold_audit", "audience_nexus"))
        nuevo_orden = [primero] + [s for s in servicios_vistos if s not in ("rebold_audit", "audience_nexus")]
        servicios_vistos = nuevo_orden

    # Máximo 2 servicios recomendados (regla dura).
    seleccionados = servicios_vistos[:2]
    oportunidades_futuras_ids = servicios_vistos[2:]
    if oportunidades_futuras_ids:
        reglas_aplicadas.append(
            f"Se identificaron más de 2 dolores/servicios candidatos; se priorizan los primeros 2 "
            f"y el resto queda como oportunidad futura interna: {', '.join(oportunidades_futuras_ids)}."
        )

    recomendaciones: list[RecomendacionServicio] = []
    camino_de_cuenta: list[str] = []

    for servicio_id in seleccionados:
        info = SERVICIOS[servicio_id]
        if servicio_id == "rebold_audit" and growth_engine_merge:
            nombre_mostrado = "Growth Engine (Rebold Audit → Audience Nexus)"
            dolor_citado = dolores_por_servicio.get("rebold_audit") or dolores_por_servicio.get("audience_nexus")
            pitch = (
                SERVICIOS["rebold_audit"]["pitch"] + " " + SERVICIOS["audience_nexus"]["pitch"]
            )
            proof = _proof_case_para("Rebold Audit") or _proof_case_para("Audience Nexus")
        else:
            nombre_mostrado = info["nombre"]
            dolor_citado = dolores_por_servicio[servicio_id]
            pitch = info["pitch"]
            proof = _proof_case_para(info["nombre"])

        cross_sell = CROSS_SELL.get(servicio_id, [])
        cross_sell_resuelto = [
            {"servicio": SERVICIOS[c["servicio"]]["nombre"], "razon": c["razon"]}
            for c in cross_sell
            if c["servicio"] in SERVICIOS
        ]
        camino_de_cuenta.extend(f"{nombre_mostrado} → {c['servicio']}: {c['razon']}" for c in cross_sell_resuelto)

        recomendaciones.append(
            RecomendacionServicio(
                servicio_id=servicio_id,
                nombre=nombre_mostrado,
                dolor_citado=dolor_citado,
                pitch=pitch,
                proof_case=proof,
                siguiente_paso_cross_sell=cross_sell_resuelto,
            )
        )

    oportunidades_futuras = [SERVICIOS[s]["nombre"] for s in oportunidades_futuras_ids if s in SERVICIOS]

    return Diagnosis(
        recomendaciones=recomendaciones,
        oportunidades_futuras=oportunidades_futuras,
        reglas_aplicadas=reglas_aplicadas,
        camino_de_cuenta=camino_de_cuenta,
    )


def diagnosis_a_dict(d: Diagnosis) -> dict[str, Any]:
    return {
        "recomendaciones": [
            {
                "servicio_id": r.servicio_id,
                "nombre": r.nombre,
                "dolor_citado": r.dolor_citado,
                "pitch": r.pitch,
                "proof_case": r.proof_case,
                "siguiente_paso_cross_sell": r.siguiente_paso_cross_sell,
            }
            for r in d.recomendaciones
        ],
        "oportunidades_futuras": d.oportunidades_futuras,
        "reglas_aplicadas": d.reglas_aplicadas,
        "camino_de_cuenta": d.camino_de_cuenta,
    }
