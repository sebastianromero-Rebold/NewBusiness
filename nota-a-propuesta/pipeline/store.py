"""Almacén local de propuestas para el dashboard.

Un JSON simple (una lista de registros) en `data/propuestas.json`. Suficiente
para una instancia local de un equipo pequeño; si esto se convierte en un
servicio compartido de verdad (varias personas escribiendo al mismo tiempo
desde distintas máquinas) esto debe migrar a una base de datos real.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROPUESTAS_PATH = DATA_DIR / "propuestas.json"

_lock = threading.Lock()


def _leer_todas() -> list[dict[str, Any]]:
    if not PROPUESTAS_PATH.exists():
        return []
    try:
        with open(PROPUESTAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _escribir_todas(registros: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROPUESTAS_PATH, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)


def crear_propuesta(
    *,
    draft_id: str,
    marca: str,
    tipo_relacion: str,
    contacto_nombre: str,
    contacto_email: str,
    servicios_recomendados: list[str],
) -> None:
    with _lock:
        registros = _leer_todas()
        registros.append({
            "draft_id": draft_id,
            "marca": marca,
            "tipo_relacion": tipo_relacion,
            "contacto_nombre": contacto_nombre,
            "contacto_email": contacto_email,
            "servicios_recomendados": servicios_recomendados,
            "estado": "borrador",
            "creado_en": datetime.now().isoformat(timespec="seconds"),
            "descargado_en": None,
            "archivo": None,
        })
        _escribir_todas(registros)


def marcar_descargada(draft_id: str, archivo: str) -> None:
    with _lock:
        registros = _leer_todas()
        for r in registros:
            if r["draft_id"] == draft_id:
                r["estado"] = "descargada"
                r["descargado_en"] = datetime.now().isoformat(timespec="seconds")
                r["archivo"] = archivo
        _escribir_todas(registros)


def listar_propuestas() -> list[dict[str, Any]]:
    return sorted(_leer_todas(), key=lambda r: r["creado_en"], reverse=True)


def resumen_por_marca() -> list[dict[str, Any]]:
    """Agrupa por marca/cliente para la vista de dashboard."""
    registros = listar_propuestas()
    por_marca: dict[str, dict[str, Any]] = {}
    for r in registros:
        m = r["marca"]
        if m not in por_marca:
            por_marca[m] = {
                "marca": m,
                "contacto_nombre": r["contacto_nombre"],
                "contacto_email": r["contacto_email"],
                "tipo_relacion": r["tipo_relacion"],
                "propuestas": [],
                "ultima_actividad": r["creado_en"],
            }
        por_marca[m]["propuestas"].append(r)
        if r["creado_en"] > por_marca[m]["ultima_actividad"]:
            por_marca[m]["ultima_actividad"] = r["creado_en"]
        # Si algún registro más reciente trae contacto, lo actualizamos.
        if r["contacto_nombre"] or r["contacto_email"]:
            por_marca[m]["contacto_nombre"] = r["contacto_nombre"] or por_marca[m]["contacto_nombre"]
            por_marca[m]["contacto_email"] = r["contacto_email"] or por_marca[m]["contacto_email"]
    return sorted(por_marca.values(), key=lambda x: x["ultima_actividad"], reverse=True)
