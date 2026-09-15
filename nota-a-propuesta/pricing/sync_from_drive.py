"""Script manual para refrescar data/pricing.json desde la hoja real de Drive
"Productos y pricing Rebold" (id 1mXV8REGMwFuViSuV_1NjJNWFGD1k_Y4huEMgiKTE2UE).

Este script NO se ejecuta automáticamente dentro de la app web — es una
herramienta aparte que corre el ejecutivo o Sofia cuando liderazgo actualiza
la hoja, para no darle a la app (ni al LLM) permiso de escritura sobre pricing.

Uso:
    1. En Google Cloud Console: crea un proyecto, habilita "Google Sheets API",
       crea credenciales OAuth de tipo "Desktop app" y descarga el archivo como
       credentials.json en esta misma carpeta (pricing/credentials.json).
    2. pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
    3. python pricing/sync_from_drive.py
       (la primera vez abre el navegador para autorizar con tu cuenta de Google
       que tenga acceso a la hoja; guarda un token.json local para las próximas)

Este script SOLO lee la hoja (scope readonly) y solo actualiza los campos que
vienen como cifra cerrada de un valor único (no rangos) — todo lo demás queda
marcado "pendiente" automáticamente, igual que el snapshot manual actual.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SHEET_ID = "1mXV8REGMwFuViSuV_1NjJNWFGD1k_Y4huEMgiKTE2UE"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"


def _get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = HERE / "token.json"
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_path = HERE / "credentials.json"
            if not creds_path.exists():
                raise SystemExit(
                    f"Falta {creds_path}. Sigue las instrucciones del docstring de este archivo."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return creds


def _es_valor_unico(pricing_texto: str) -> bool:
    """True si el texto de precio es una cifra cerrada (no un rango ni %)."""
    return bool(re.fullmatch(r"\$[\d.,]+", pricing_texto.strip()))


def _a_entero(pricing_texto: str) -> int:
    return int(re.sub(r"[^\d]", "", pricing_texto))


def sync() -> None:
    from googleapiclient.discovery import build

    creds = _get_credentials()
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SHEET_ID, range="Venta Servicios Rebold!A2:C30")
        .execute()
    )
    filas = result.get("values", [])

    pricing_path = DATA_DIR / "pricing.json"
    pricing = json.loads(pricing_path.read_text(encoding="utf-8"))

    actualizados = 0
    for fila in filas:
        if len(fila) < 3:
            continue
        _area, producto, precio_texto = fila[0], fila[1], fila[2]
        if not _es_valor_unico(precio_texto):
            continue  # rango o %: no se toca automáticamente, requiere mapeo manual
        monto = _a_entero(precio_texto)
        # Actualiza solo si el producto ya existe como modalidad definida en pricing.json
        for item in pricing["servicios"]:
            for modalidad, detalle in item.get("modalidades", {}).items():
                if producto.strip().lower() in modalidad.lower() and detalle.get("estado") == "definido":
                    if detalle.get("monto") != monto:
                        detalle["monto"] = monto
                        actualizados += 1

    pricing["_meta"]["sincronizado_manualmente_el"] = "actualizado por sync_from_drive.py"
    pricing_path.write_text(json.dumps(pricing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo. {actualizados} valores actualizados en data/pricing.json.")
    print("Revisa el diff antes de confiar en él — este script NUNCA debe correr sin supervisión humana.")


if __name__ == "__main__":
    sync()
