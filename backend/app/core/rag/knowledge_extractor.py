"""
Extracción de campos de formulario desde un documento, con GPT-4o-mini.

El cliente sube un documento (PDF o texto) y el sistema extrae los campos de la categoría
correspondiente para PRE-RELLENAR el formulario. El cliente SIEMPRE revisa y corrige antes
de guardar (sobre todo en pagos: un CBU mal leído sería grave).

Se usa gpt-4o-mini (≈16x más barato que gpt-4o) porque la tarea es de extracción simple.
Cada categoría tiene su propio "esquema de extracción" (qué campos pedir).
"""
import json
from typing import Dict

from app.core.llm.openai_client import get_sync_openai
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

# Modelo económico para extracción.
_MODEL = "gpt-4o-mini"

# Instrucción de extracción por categoría: qué forma de JSON debe devolver el modelo.
# El modelo devuelve SOLO los campos que encuentra; lo que no esté, lo deja vacío.
_SCHEMAS = {
    "pagos": (
        "Extraé los datos de pago y transferencia. Devolvé un JSON con esta forma exacta:\n"
        '{"medios": ["string"], "cuentas": [{"titular": "", "banco": "", "cbu": "", '
        '"alias": "", "moneda": "ARS|USD"}], "content": ""}\n'
        "- medios: lista de medios de pago aceptados (efectivo, tarjeta, transferencia, etc.).\n"
        "- cuentas: una por cada cuenta bancaria que encuentres. moneda en ARS o USD.\n"
        "- content: notas adicionales sobre pagos (señas, condiciones), si las hay.\n"
        "Copiá los CBU y alias EXACTAMENTE como aparecen, sin alterar dígitos."
    ),
    "checkin": (
        "Extraé horarios y políticas de ingreso/egreso. Devolvé JSON: "
        '{"content": "texto claro con horarios de check-in y check-out y condiciones"}'
    ),
    "cancelacion": (
        "Extraé la política de cancelación / no-show. Devolvé JSON: "
        '{"content": "texto claro con las condiciones de cancelación y no-show"}'
    ),
    "mascotas": (
        "Extraé la política de mascotas/niños/fumadores. Devolvé JSON: "
        '{"content": "texto claro con la política de convivencia"}'
    ),
    "servicios": (
        "Extraé los servicios e instalaciones del hotel. Devolvé JSON: "
        '{"content": "texto claro listando los servicios e instalaciones"}'
    ),
    "faq": (
        "Extraé pares de pregunta y respuesta. Devolvé JSON: "
        '{"items": [{"q": "pregunta", "a": "respuesta"}]}'
    ),
    "general": (
        "Resumí la información relevante para el hotel. Devolvé JSON: "
        '{"content": "texto claro con la información"}'
    ),
}


def extract_fields(category: str, text: str) -> Dict:
    """Extrae los campos del formulario de `category` desde `text` con GPT-4o-mini.

    Devuelve un dict con la forma esperada por el formulario de esa categoría
    (subconjunto de title/content/data). Defensivo: ante error, devuelve {}.
    """
    schema = _SCHEMAS.get(category)
    if not schema:
        return {}
    text = (text or "").strip()
    if not text:
        return {}
    # Recortar para no gastar tokens de más (un documento de políticas no necesita más).
    text = text[:8000]

    client = get_sync_openai()
    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sos un extractor de datos para un hotel. Extraés información de un "
                        "documento y devolvés SOLO un JSON válido, sin texto adicional. "
                        "Si un dato no aparece, dejalo vacío. No inventes datos."
                    ),
                },
                {"role": "user", "content": f"{schema}\n\nDOCUMENTO:\n{text}"},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        logger.info("Knowledge fields extracted", category=category, keys=list(data.keys()))
        return _shape(category, data)
    except Exception as e:
        logger.error("knowledge_extractor failed", category=category, error=str(e))
        return {}


def _shape(category: str, data: Dict) -> Dict:
    """Normaliza la salida del modelo a la forma que consume el formulario del front."""
    if category == "pagos":
        cuentas = data.get("cuentas") or []
        # Marcar la primera como default.
        for i, c in enumerate(cuentas):
            c["default"] = (i == 0)
            c.setdefault("moneda", "ARS")
        return {
            "data": {"medios": data.get("medios") or [], "cuentas": cuentas},
            "content": data.get("content") or "",
        }
    if category == "faq":
        return {"data": {"items": data.get("items") or []}}
    # Resto: content libre.
    return {"content": data.get("content") or ""}
