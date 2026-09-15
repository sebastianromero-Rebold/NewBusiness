"""Capa de acceso al modelo de lenguaje — intercambiable.

Regla de arquitectura (no negociable): esta capa SOLO se usa para extraer señales
(Paso 2) y redactar narrativa (Paso 4). Nunca se le pasa la tabla de pricing ni se
le pide que escriba montos — la slide de inversión se construye en `pricing/` a
partir de datos estructurados, nunca de texto generado.

Sin ANTHROPIC_API_KEY configurada, se usa `MockLLMProvider`: un extractor por
reglas/keywords que solo puede citar substrings textuales de la nota (no puede
"inventar" porque no genera texto libre). Es menos matizado que un LLM real, pero
nunca alucina. Al configurar ANTHROPIC_API_KEY, la app cambia automáticamente a
`AnthropicLLMProvider` sin tocar el resto del pipeline.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

# Categorías de dolor -> pistas léxicas (español, coloquial) usadas por el
# extractor heurístico Y como vocabulario de referencia para validar / instruir
# al LLM real. Mantener sincronizado con pipeline/diagnostic_engine.py.
DOLOR_KEYWORDS: dict[str, list[str]] = {
    "activation_hub": [
        "cpa", "cpl", "ctr bajo", "roas", "pauta", "no está rindiendo",
        "no rinde", "inversión en medios", "no sé si mi inversión",
        "escalar presupuesto", "campañas desordenadas",
    ],
    "creative_lab": [
        "contenido lento", "contenido caro", "se demora", "se ve siempre igual",
        "fatiga creativa", "contenido genérico", "territorio de marca",
        "refresh de marca", "producción creativa",
    ],
    "insight_factory": [
        "no conozco a mi audiencia", "no conozco bien a mi audiencia",
        "no sabemos quién es nuestro consumidor", "research", "entender el mercado",
        "decisiones sin datos", "a ciegas", "entrar a una categoría nueva",
        "mercado nuevo",
    ],
    "audience_nexus": [
        "data de usuarios sin usar", "muchísima data", "audiencia propia",
        "monetizar", "base de usuarios grande", "1p", "first party",
    ],
    "rebold_audit": [
        "no sé por dónde empezar", "diagnóstico objetivo", "auditoría",
        "no sabemos si está bien construido", "revisión objetiva",
    ],
    "agent_lab": [
        "crm dormid", "base de clientes sin aprovechar", "base dormida",
        "atención al cliente cara", "atención al cliente lenta",
        "recompra", "no explotamos nuestra base",
    ],
}

RELACION_KEYWORDS = {
    "cliente_actual": [
        "ya trabajamos con", "actualmente tienen", "ya somos su agencia",
        "el servicio que ya tienen", "renovación",
    ],
    "prospecto_nuevo": [
        "primera reunión", "todavía no es cliente", "prospecto", "nunca han trabajado con",
    ],
}


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def extraer_senales(self, texto_bruto: str) -> dict[str, Any]:
        """Devuelve JSON estructurado: dolores, servicios_actuales, madurez_datos, scores."""

    @abstractmethod
    def redactar_narrativa(self, contexto: dict[str, Any]) -> dict[str, Any]:
        """Devuelve el contenido slide-a-slide de la narrativa (sin cifras de inversión)."""


def _sentencias(texto: str) -> list[str]:
    partes = re.split(r"(?<=[\.\!\?\n])\s+", texto.strip())
    return [p.strip() for p in partes if p.strip()]


class MockLLMProvider(LLMProvider):
    """Extractor heurístico por keywords. No genera texto libre: solo cita
    substrings verbatim de la nota, por lo que es imposible que alucine cifras
    o dolores que el cliente no dijo."""

    name = "heuristico (sin API key)"

    def extraer_senales(self, texto_bruto: str) -> dict[str, Any]:
        texto_low = texto_bruto.lower()
        sentencias = _sentencias(texto_bruto)

        dolores: list[dict[str, str]] = []
        for categoria, keywords in DOLOR_KEYWORDS.items():
            for sent in sentencias:
                sent_low = sent.lower()
                coincide = any(kw in sent_low for kw in keywords)
                # CRM/base dormida se dice de muchas formas ("base de clientes
                # dormida en el CRM", "CRM que no tocamos hace meses", etc.) —
                # además del match exacto de keywords, aceptamos la combinación
                # "dormid*"/"sin tocar"/"sin usar" + "crm"/"base de clientes".
                if not coincide and categoria == "agent_lab":
                    tiene_estado = any(w in sent_low for w in ["dormid", "sin tocar", "sin usar", "sin aprovechar", "abandonad"])
                    tiene_activo = "crm" in sent_low or "base de clientes" in sent_low or "base de datos" in sent_low
                    coincide = tiene_estado and tiene_activo
                if coincide:
                    dolores.append({"categoria": categoria, "cita": sent})
                    break  # una cita representativa por categoría es suficiente

        servicios_actuales = []
        if "audit" in texto_low or "auditoría" in texto_low:
            servicios_actuales.append("Rebold Audit")
        if "creative lab" in texto_low or "creatividad" in texto_low and "ya" in texto_low:
            servicios_actuales.append("Creative Lab")
        if "activation hub" in texto_low or "pauta" in texto_low and "ya gestionan" in texto_low:
            servicios_actuales.append("Activation Hub")

        madurez_datos = "alta" if any(
            kw in texto_low for kw in ["crm robusto", "base grande", "mucha data", "1p madura"]
        ) else ("media" if "crm" in texto_low or "base de datos" in texto_low else "baja")

        scores = {}
        for score in ["ori", "aes", "ces", "uxcs", "ais"]:
            m = re.search(rf"{score}[^\d]{{0,10}}(\d{{1,3}})", texto_low)
            if m:
                scores[score.upper()] = int(m.group(1))

        # Misma lógica flexible que arriba: la señal de gating de Agent Lab debe
        # coincidir exactamente con lo que hizo que la categoría "agent_lab"
        # entrara a `dolores`, para no desalinear el gate del resto del motor.
        crm_dormido = any(d["categoria"] == "agent_lab" for d in dolores)

        return {
            "dolores": dolores,
            "servicios_actuales": servicios_actuales,
            "madurez_datos": madurez_datos,
            "scores_rebold_audit": scores,
            "señal_crm_dormido": crm_dormido,
        }

    def redactar_narrativa(self, contexto: dict[str, Any]) -> dict[str, Any]:
        cliente = contexto["cliente"]
        diagnosis = contexto["diagnosis"]
        dolor_principal = diagnosis["recomendaciones"][0]["dolor_citado"] if diagnosis["recomendaciones"] else ""

        if dolor_principal:
            texto_contexto = (
                f"{cliente} llega a esta conversación con Rebold en un momento concreto: "
                f"\"{dolor_principal}\". Esta propuesta parte de esa frase, no de un template genérico."
            )
        else:
            texto_contexto = (
                f"Esta es una primera conversación exploratoria con {cliente}, sin un dolor "
                f"específico todavía declarado. Por eso se abre con un diagnóstico objetivo "
                f"(Rebold Audit) en vez de asumir un problema que el cliente no ha dicho."
            )

        return {
            "contexto": texto_contexto,
            "insight": (
                f"El problema no es la falta de esfuerzo — es la falta de un diagnóstico y un "
                f"camino claro para accionar lo que {cliente} ya sabe intuitivamente."
            ),
            "camino_de_cuenta": diagnosis.get("camino_de_cuenta", []),
            "modo": "heuristico",
        }


class AnthropicLLMProvider(LLMProvider):
    """Usa la API de Claude para extracción y narrativa. Requiere ANTHROPIC_API_KEY."""

    name = "Claude API"

    def __init__(self, model: str = "claude-sonnet-4-5-20250929") -> None:
        import anthropic  # type: ignore

        self._client = anthropic.Anthropic()
        self._model = model

    def extraer_senales(self, texto_bruto: str) -> dict[str, Any]:
        categorias = ", ".join(DOLOR_KEYWORDS.keys())
        system = (
            "Eres un extractor de señales de negocio para Rebold, una agencia de growth marketing. "
            "Tu única tarea es leer una nota de una reunión comercial y devolver JSON estructurado. "
            "REGLA NO NEGOCIABLE: cada 'cita' en 'dolores' debe ser una copia EXACTA (verbatim, "
            "carácter por carácter) de una frase que aparece en el texto de la nota. Nunca "
            "parafrasees, resumas ni inventes una cita. Si no hay una frase clara para una "
            "categoría, no la incluyas. No inventes cifras, scores ni servicios que no estén "
            "explícitos en el texto."
        )
        user = (
            f"Categorías válidas de dolor: {categorias}.\n\n"
            "Devuelve SOLO un objeto JSON con esta forma exacta:\n"
            '{"dolores": [{"categoria": "...", "cita": "..."}], '
            '"servicios_actuales": ["..."], "madurez_datos": "alta|media|baja|desconocida", '
            '"scores_rebold_audit": {"ORI": null, "AES": null, "CES": null, "UXCS": null, "AIS": null}, '
            '"señal_crm_dormido": false}\n\n'
            f"Nota de la reunión:\n---\n{texto_bruto}\n---"
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text
        data = _parse_json_loose(raw)

        # Guardarraíl anti-alucinación: descarta cualquier "cita" que no sea
        # substring verbatim (normalizando espacios) de la nota original.
        texto_norm = _normalizar_espacios(texto_bruto)
        dolores_validados = []
        for d in data.get("dolores", []):
            cita_norm = _normalizar_espacios(d.get("cita", ""))
            if cita_norm and cita_norm in texto_norm:
                dolores_validados.append(d)
        data["dolores"] = dolores_validados
        return data

    def redactar_narrativa(self, contexto: dict[str, Any]) -> dict[str, Any]:
        system = (
            "Eres un estratega senior de Rebold escribiendo la narrativa de una propuesta "
            "comercial, siguiendo la metodología de storytelling: problema real -> oportunidad -> "
            "insight clave -> servicio recomendado -> camino de cuenta. "
            "REGLA NO NEGOCIABLE: nunca menciones cifras de inversión, precios, tarifas ni "
            "porcentajes de revenue-share — esa información NO es tuya para decidir ni redactar, "
            "la inserta un sistema aparte a partir de una tabla de pricing controlada por "
            "liderazgo. Si sientes la tentación de poner un número de dinero, omítelo. "
            "Usa el lenguaje y las citas textuales del cliente que se te dan, no inventes otras."
        )
        user = (
            "Con este contexto (diagnóstico ya decidido por reglas de negocio, no lo cuestiones, "
            "solo redacta la narrativa alrededor de él), devuelve SOLO un JSON con esta forma:\n"
            '{"contexto": "...", "insight": "...", "camino_de_cuenta": ["...", "..."]}\n\n'
            f"Contexto:\n{json.dumps(contexto, ensure_ascii=False, indent=2)}"
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text
        data = _parse_json_loose(raw)
        data["modo"] = "claude_api"
        return data


def _normalizar_espacios(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _parse_json_loose(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    return json.loads(raw)


def get_llm_provider() -> LLMProvider:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicLLMProvider()
        except Exception:
            # Si falla la inicialización (paquete no instalado, key inválida, etc.)
            # degradamos a heurístico en vez de romper la app.
            return MockLLMProvider()
    return MockLLMProvider()
