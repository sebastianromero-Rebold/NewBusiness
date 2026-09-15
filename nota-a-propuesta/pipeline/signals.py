"""Paso 2 — Extracción de señales de negocio, en JSON estructurado (nunca prosa libre)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .ingest import NotaNormalizada
from .llm import LLMProvider


@dataclass
class Senales:
    dolores: list[dict[str, str]]  # [{"categoria": ..., "cita": ...}]
    servicios_actuales: list[str]
    madurez_datos: str
    scores_rebold_audit: dict[str, int]
    señal_crm_dormido: bool
    necesita_aclaracion: bool = False
    mensaje_aclaracion: str = ""


def _normalizar_espacios(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def extraer(nota: NotaNormalizada, llm: LLMProvider) -> Senales:
    crudo: dict[str, Any] = llm.extraer_senales(nota.texto_bruto)

    # Guardarraíl anti-alucinación aplicado SIEMPRE, sin importar el proveedor:
    # una "cita" que no es substring verbatim (normalizando espacios/mayúsculas)
    # de la nota original se descarta. Esto es lo que hace medible la métrica de
    # "% de propuestas donde la cita de la slide 2 aparece en la nota original".
    texto_norm = _normalizar_espacios(nota.texto_bruto)
    dolores_validados = []
    for d in crudo.get("dolores", []):
        cita = d.get("cita", "")
        if cita and _normalizar_espacios(cita) in texto_norm:
            dolores_validados.append({"categoria": d.get("categoria", "sin_categoria"), "cita": cita})

    servicios_actuales = list(crudo.get("servicios_actuales", []))
    if nota.servicios_actuales_declarados:
        for s in nota.servicios_actuales_declarados:
            if s not in servicios_actuales:
                servicios_actuales.append(s)

    senales = Senales(
        dolores=dolores_validados,
        servicios_actuales=servicios_actuales,
        madurez_datos=crudo.get("madurez_datos", "desconocida"),
        scores_rebold_audit={k: v for k, v in crudo.get("scores_rebold_audit", {}).items() if v is not None},
        señal_crm_dormido=bool(crudo.get("señal_crm_dormido", False)),
    )

    # Caso ambiguo (Sección 4 del brief): nunca forzar un diagnóstico sin dolor.
    if not senales.dolores:
        senales.necesita_aclaracion = True
        senales.mensaje_aclaracion = (
            "No se identificó un dolor claro en la nota. ¿El cliente mencionó algo sobre "
            "pauta/inversión en medios, contenido, research de audiencia, o una base de "
            "datos/CRM sin aprovechar que no quedó registrado literalmente en el texto? "
            "Agrega esa frase textual a la nota antes de continuar — la app no puede "
            "inventar un dolor que el cliente no dijo."
        )

    return senales
