"""Paso 5 — Inserción de costos. NUNCA generados por IA.

Todo monto que termina en la slide de inversión sale de `data/pricing.json`
(snapshot de la hoja de Drive "Productos y pricing Rebold") o de la regla fija
de Activation Hub que Sebastian definió explícitamente para esta app. Si una
combinación servicio+modalidad no tiene cifra cerrada, se devuelve el texto
"Monto pendiente de definir con liderazgo Rebold" — nunca se estima, redondea
ni infiere del tamaño del cliente.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PENDIENTE_TEXTO = "Monto pendiente de definir con liderazgo Rebold"


def _cargar_pricing() -> dict[str, Any]:
    ruta = DATA_DIR / "pricing.json"
    if not ruta.exists():
        # Primer arranque después de clonar el repo: todavía no existe la copia
        # local con cifras reales (data/pricing.json está en .gitignore a
        # propósito). Se usa la plantilla pública como fallback — todo sale
        # "pendiente" hasta que alguien copie sus precios reales, que es
        # exactamente el comportamiento seguro que se espera aquí.
        ruta = DATA_DIR / "pricing.example.json"
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _formatear_cop(monto: int) -> str:
    return f"${monto:,.0f}".replace(",", ".") + " COP"


@dataclass
class LineaInversion:
    servicio: str
    modalidad: str
    estado: str  # "definido" | "pendiente" | "regla_definida_por_usuario"
    texto_cliente: str  # lo que se muestra en la slide visible al cliente
    nota_interna: str = ""  # solo para el ejecutivo / speaker notes


def listar_modalidades(servicio_nombre: str) -> list[str]:
    pricing = _cargar_pricing()
    for item in pricing["servicios"]:
        if item["servicio"] == servicio_nombre:
            return list(item.get("modalidades", {}).keys())
    return []


def resolver(
    servicio_nombre: str,
    modalidad: str | None = None,
    *,
    inversion_digital_mensual: float | None = None,
    inversion_atl_mensual: float | None = None,
) -> LineaInversion:
    pricing = _cargar_pricing()
    item = next((s for s in pricing["servicios"] if s["servicio"] == servicio_nombre), None)

    if item is None:
        return LineaInversion(
            servicio=servicio_nombre,
            modalidad=modalidad or "—",
            estado="pendiente",
            texto_cliente=PENDIENTE_TEXTO,
            nota_interna="Este servicio no existe todavía en data/pricing.json.",
        )

    modalidades = item.get("modalidades", {})

    # --- Caso especial: Activation Hub, regla fija de fee escalonado ---
    if servicio_nombre == "Activation Hub" and (modalidad is None or "Medios digitales" in (modalidad or "")):
        regla = modalidades.get("Medios digitales (fee agencia)", {})
        if inversion_digital_mensual is None:
            return LineaInversion(
                servicio=servicio_nombre,
                modalidad="Medios digitales (fee agencia)",
                estado="regla_definida_por_usuario",
                texto_cliente=(
                    "Fee de agencia: 2.000.000 COP fijos/mes si la inversión en medios digitales "
                    "es menor a 20.000.000 COP/mes; 10% sobre inversión digital + 3% sobre inversión "
                    "ATL si la inversión digital es igual o mayor a 20.000.000 COP/mes. "
                    "(Ingresa la inversión estimada del cliente para calcular el fee exacto)."
                ),
                nota_interna=regla.get("regla", ""),
            )
        if inversion_digital_mensual < 20_000_000:
            monto = 2_000_000
            detalle = "inversión digital < 20.000.000 COP/mes → fee fijo"
        else:
            fee_digital = inversion_digital_mensual * 0.10
            fee_atl = (inversion_atl_mensual or 0) * 0.03
            monto = fee_digital + fee_atl
            detalle = "inversión digital ≥ 20.000.000 COP/mes → 10% digital + 3% ATL"
        return LineaInversion(
            servicio=servicio_nombre,
            modalidad="Medios digitales (fee agencia)",
            estado="regla_definida_por_usuario",
            texto_cliente=f"Fee de agencia: {_formatear_cop(monto)}/mes ({detalle})",
            nota_interna=regla.get("referencia_hoja", ""),
        )

    if modalidad is None:
        return LineaInversion(
            servicio=servicio_nombre,
            modalidad="—",
            estado="pendiente",
            texto_cliente=PENDIENTE_TEXTO,
            nota_interna="No se especificó modalidad para resolver el costo.",
        )

    detalle_modalidad = modalidades.get(modalidad)
    if detalle_modalidad is None:
        return LineaInversion(
            servicio=servicio_nombre,
            modalidad=modalidad,
            estado="pendiente",
            texto_cliente=PENDIENTE_TEXTO,
            nota_interna=f"La modalidad '{modalidad}' no existe en la tabla de pricing para {servicio_nombre}.",
        )

    estado = detalle_modalidad.get("estado", "pendiente")

    if estado == "definido":
        if "monto" in detalle_modalidad:
            texto = _formatear_cop(detalle_modalidad["monto"])
            unidad = detalle_modalidad.get("unidad")
            if unidad:
                texto += f" ({unidad})"
        elif "porcentaje" in detalle_modalidad:
            texto = f"{detalle_modalidad['porcentaje']}% ({detalle_modalidad.get('unidad', '')})"
        else:
            texto = PENDIENTE_TEXTO
        return LineaInversion(
            servicio=servicio_nombre,
            modalidad=modalidad,
            estado="definido",
            texto_cliente=texto,
            nota_interna=detalle_modalidad.get("nota", ""),
        )

    # estado == "pendiente"
    rango = item.get("rango_referencia_interno")
    nota_interna = detalle_modalidad.get("razon", "")
    if rango and isinstance(rango, dict) and "min" in rango:
        nota_interna += (
            f" Rango de referencia interno (NO mostrar al cliente como cifra cerrada): "
            f"{_formatear_cop(rango['min'])} - {_formatear_cop(rango['max'])} "
            f"según {rango.get('variable', 'variables del proyecto')}."
        )
    return LineaInversion(
        servicio=servicio_nombre,
        modalidad=modalidad,
        estado="pendiente",
        texto_cliente=PENDIENTE_TEXTO,
        nota_interna=nota_interna,
    )


def meta_fuente() -> dict[str, Any]:
    return _cargar_pricing()["_meta"]
