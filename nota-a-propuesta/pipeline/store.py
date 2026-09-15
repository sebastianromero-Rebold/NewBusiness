"""Almacén de propuestas para el dashboard.

Dos backends, elegidos automáticamente según el entorno:

- **Local (por defecto)**: un JSON simple (`data/propuestas.json`). Suficiente
  para correr la app en tu máquina.
- **Firestore**: se activa solo si detecta que corre en Google Cloud Run
  (variables de entorno `K_SERVICE`/`GOOGLE_CLOUD_PROJECT`, que Cloud Run
  define automáticamente). Necesario en cuanto la app se comparte con varios
  equipos desde una sola URL — un archivo JSON local no sobrevive a que Cloud
  Run reinicie o reemplace la instancia, y no se comparte entre instancias.

El resto de este módulo (crear_propuesta, marcar_descargada, etc.) es igual
sin importar el backend — solo cambian `_leer_todas` / `_escribir_todas`.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROPUESTAS_PATH = DATA_DIR / "propuestas.json"
FIRESTORE_COLLECTION = "propuestas"

USANDO_FIRESTORE = bool(os.environ.get("K_SERVICE") or os.environ.get("GOOGLE_CLOUD_PROJECT"))

_lock = threading.Lock()
_firestore_client = None


def _firestore():
    global _firestore_client
    if _firestore_client is None:
        from google.cloud import firestore  # import diferido: no requerido en dev local

        _firestore_client = firestore.Client()
    return _firestore_client


def _leer_todas() -> list[dict[str, Any]]:
    if USANDO_FIRESTORE:
        docs = _firestore().collection(FIRESTORE_COLLECTION).stream()
        return [d.to_dict() for d in docs]
    if not PROPUESTAS_PATH.exists():
        return []
    try:
        with open(PROPUESTAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _escribir_todas(registros: list[dict[str, Any]]) -> None:
    """Solo usado por el backend local — Firestore se escribe documento a
    documento en crear_propuesta/marcar_descargada, nunca se reescribe todo."""
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
    registro = {
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
    }
    if USANDO_FIRESTORE:
        _firestore().collection(FIRESTORE_COLLECTION).document(draft_id).set(registro)
        return
    with _lock:
        registros = _leer_todas()
        registros.append(registro)
        _escribir_todas(registros)


def marcar_descargada(draft_id: str, archivo: str) -> None:
    cambios = {
        "estado": "descargada",
        "descargado_en": datetime.now().isoformat(timespec="seconds"),
        "archivo": archivo,
    }
    if USANDO_FIRESTORE:
        _firestore().collection(FIRESTORE_COLLECTION).document(draft_id).update(cambios)
        return
    with _lock:
        registros = _leer_todas()
        for r in registros:
            if r["draft_id"] == draft_id:
                r.update(cambios)
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
