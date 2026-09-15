"""Paso 1 — Ingesta y normalización de la nota de reunión."""
from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field


@dataclass
class NotaNormalizada:
    cliente: str
    tipo_relacion: str  # "cliente_actual" | "prospecto_nuevo"
    fecha: str
    participantes: str
    texto_bruto: str
    contacto_nombre: str = ""
    contacto_email: str = ""
    servicios_actuales_declarados: list[str] = field(default_factory=list)


TIPOS_RELACION_VALIDOS = {"cliente_actual", "prospecto_nuevo"}


def leer_docx(file_storage) -> str:
    """Extrae texto plano de un .docx subido (werkzeug FileStorage)."""
    import docx  # python-docx

    buffer = io.BytesIO(file_storage.read())
    documento = docx.Document(buffer)
    parrafos = [p.text for p in documento.paragraphs if p.text.strip()]
    return "\n".join(parrafos)


def normalizar(
    *,
    cliente: str,
    tipo_relacion: str,
    texto_bruto: str,
    participantes: str = "",
    contacto_nombre: str = "",
    contacto_email: str = "",
    fecha: str | None = None,
    servicios_actuales_declarados: list[str] | None = None,
) -> NotaNormalizada:
    if tipo_relacion not in TIPOS_RELACION_VALIDOS:
        raise ValueError(
            "tipo_relacion debe ser explícito ('cliente_actual' o 'prospecto_nuevo'). "
            "La app nunca debe asumir este dato — debe preguntarlo al usuario."
        )
    if not texto_bruto or not texto_bruto.strip():
        raise ValueError("La nota no puede estar vacía.")

    return NotaNormalizada(
        cliente=cliente.strip() or "Cliente sin nombre",
        tipo_relacion=tipo_relacion,
        fecha=fecha or dt.date.today().isoformat(),
        participantes=participantes.strip(),
        texto_bruto=texto_bruto.strip(),
        contacto_nombre=contacto_nombre.strip(),
        contacto_email=contacto_email.strip(),
        servicios_actuales_declarados=servicios_actuales_declarados or [],
    )
