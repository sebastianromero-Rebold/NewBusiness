"""Paso 4 — Construcción de la narrativa estratégica (arco: contexto → dolor
validado → servicio(s) recomendado(s) → cómo se mide el éxito → camino de cuenta).

Nunca recibe la tabla de pricing ni genera cifras de inversión — ver pipeline/llm.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .diagnostic_engine import Diagnosis, diagnosis_a_dict
from .ingest import NotaNormalizada
from .llm import LLMProvider
from .signals import Senales


@dataclass
class Narrativa:
    contexto: str
    insight: str
    camino_de_cuenta: list[str]
    modo: str


def construir(nota: NotaNormalizada, senales: Senales, diagnosis: Diagnosis, llm: LLMProvider) -> Narrativa:
    contexto_llm = {
        "cliente": nota.cliente,
        "tipo_relacion": nota.tipo_relacion,
        "madurez_datos": senales.madurez_datos,
        "diagnosis": diagnosis_a_dict(diagnosis),
    }
    resultado: dict[str, Any] = llm.redactar_narrativa(contexto_llm)

    return Narrativa(
        contexto=resultado.get("contexto", ""),
        insight=resultado.get("insight", ""),
        camino_de_cuenta=resultado.get("camino_de_cuenta") or diagnosis.camino_de_cuenta,
        modo=resultado.get("modo", "desconocido"),
    )
