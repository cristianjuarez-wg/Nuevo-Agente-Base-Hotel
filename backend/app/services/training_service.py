"""
Entrenamiento ESTRUCTURADO del agente (Fase E del Centro).

Principio (decisión del usuario): el cliente NUNCA escribe texto libre que va
directo al prompt. Llena CAMPOS (formulario por categoría); el texto inyectable
lo renderiza NUESTRA plantilla fija (render_training) con topes de largo. Así
el entrenamiento es máximamente parametrizable sin poder romper el cerebro.

Categorías espejo vs. adicionales (FLUJOS_Y_ESTRATEGIA.md §10):
  - tono_marca / politica_comercial: espejo del cerebro → fábrica ACTIVA (paridad).
  - objeciones: mixta → fábrica activa SOLO con el contenido espejo (precio).
  - argumentario / calificacion_leads / ejemplos: 100% adicionales → fábrica
    sembrada pero DESACTIVADA (el cliente revisa y activa).

La INYECCIÓN al prompt es la Fase E2 (tras gate de aprobación del usuario);
acá quedan listos schemas, validación, render, extractor IA y seed.
"""
import json
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.training_document import TrainingDocument
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Topes de sanitización (validación server-side; el render además capea el total).
_MAX_STR = 400          # largo máximo de un campo de texto
_MAX_TAGS = 12          # elementos máximos en un campo de etiquetas
_MAX_TAG_LEN = 60
_MAX_ITEMS = 10         # filas máximas en un campo lista
_MAX_RENDER = 1200      # largo máximo del bloque renderizado por categoría

CATEGORY_ORDER = [
    "tono_marca", "politica_comercial", "objeciones",
    "argumentario", "calificacion_leads", "ejemplos",
]

# ---------------------------------------------------------------------------
# FORMULARIOS por categoría — única fuente de verdad (el frontend los consume
# vía GET /api/agents/training-schemas y renderiza los campos genéricamente).
# Tipos: text | textarea | select | bool | tags | list (con item_fields).
# ---------------------------------------------------------------------------
FORM_SCHEMAS: Dict[str, Dict] = {
    "tono_marca": {
        "label": "Tono de marca",
        "hint": "Cómo habla el agente: trato, palabras y estilo de la marca.",
        "fields": [
            {"key": "trato", "label": "Trato", "type": "select", "options": ["vos", "usted"], "default": "vos"},
            {"key": "emojis", "label": "Puede usar emojis (con moderación)", "type": "bool", "default": True},
            {"key": "palabras_preferidas", "label": "Palabras y expresiones preferidas", "type": "tags"},
            {"key": "palabras_evitar", "label": "Palabras y expresiones a evitar", "type": "tags"},
            {"key": "notas", "label": "Notas de estilo", "type": "textarea"},
        ],
    },
    "politica_comercial": {
        "label": "Política comercial",
        "hint": "Reglas comerciales internas: qué no prometer, cuándo ofrecer promos, qué derivar.",
        "fields": [
            {"key": "no_prometer", "label": "Nunca prometer", "type": "tags"},
            {"key": "cuando_promo", "label": "Cuándo mencionar promociones", "type": "textarea"},
            {"key": "derivar_a_humano", "label": "Casos que se derivan a una persona", "type": "tags"},
        ],
    },
    "objeciones": {
        "label": "Manejo de objeciones",
        "hint": "Qué responder cuando el huésped duda u objeta.",
        "fields": [
            {"key": "items", "label": "Objeciones", "type": "list", "item_fields": [
                {"key": "objecion", "label": "Objeción del huésped", "type": "text"},
                {"key": "respuesta", "label": "Cómo responder", "type": "textarea"},
            ]},
        ],
    },
    "argumentario": {
        "label": "Argumentario por tipo de huésped",
        "hint": "Qué destacar según quién consulta.",
        "fields": [
            {"key": "items", "label": "Perfiles", "type": "list", "item_fields": [
                {"key": "tipo_huesped", "label": "Tipo de huésped", "type": "text"},
                {"key": "puntos", "label": "Puntos a destacar (máx. 3)", "type": "tags"},
            ]},
        ],
    },
    "calificacion_leads": {
        "label": "Calificación de leads",
        "hint": "Qué consultas valen más para este hotel y qué preguntar.",
        "fields": [
            {"key": "items", "label": "Perfiles de lead", "type": "list", "item_fields": [
                {"key": "perfil", "label": "Perfil", "type": "text"},
                {"key": "prioridad", "label": "Prioridad", "type": "select", "options": ["alta", "media", "baja"], "default": "media"},
                {"key": "dato_a_preguntar", "label": "Dato clave a preguntar", "type": "text"},
            ]},
        ],
    },
    "ejemplos": {
        "label": "Ejemplos de conversaciones",
        "hint": "Respuestas modelo para que el agente imite el estilo.",
        "fields": [
            {"key": "items", "label": "Ejemplos", "type": "list", "item_fields": [
                {"key": "situacion", "label": "Situación", "type": "text"},
                {"key": "respuesta_modelo", "label": "Respuesta modelo", "type": "textarea"},
            ]},
        ],
    },
}

# ---------------------------------------------------------------------------
# FÁBRICA — contenido de las plantillas por defecto para Aura.
# Espejo: alineado 1:1 con el prompt actual (activarlas = paridad).
# Adicionales: ejemplos sugeridos, nacen DESACTIVADAS.
# ---------------------------------------------------------------------------
FACTORY = {
    "tono_marca": {
        "active": True,   # espejo del carácter actual (prompt §QUIÉN SOS)
        "data": {
            "trato": "vos",
            "emojis": True,
            "palabras_preferidas": ["dale", "bárbaro", "un montón", "fijate"],
            "palabras_evitar": ["tuteo (tú tienes)", "jerga corporativa"],
            "notas": "Cálida y genuina, con humor sutil cuando viene al caso. Hospitalidad Hilton sin sonar corporativa. Orgullosa de la Patagonia.",
        },
    },
    "politica_comercial": {
        "active": True,   # espejo de la política de descuentos + límites actuales
        "data": {
            "no_prometer": ["upgrades de habitación", "descuentos no publicados", "servicios no confirmados en la base de conocimiento"],
            "cuando_promo": "Solo si el huésped pide una promoción o muestra resistencia al precio. El descuento es herramienta de cierre, no de apertura.",
            "derivar_a_humano": ["grupos y eventos", "pedidos especiales fuera de política"],
        },
    },
    "objeciones": {
        "active": True,   # SOLO el contenido espejo (objeción de precio, ya en el cerebro)
        "data": {
            "items": [
                {"objecion": "Es caro / se me va de presupuesto",
                 "respuesta": "Destacá el valor (desayuno incluido, ubicación) antes que el precio y ofrecé avisarle de promociones. No ofrezcas descuentos de entrada."},
            ],
        },
    },
    "argumentario": {
        "active": False,  # 100% adicional: el cliente revisa y activa
        "data": {
            "items": [
                {"tipo_huesped": "Familia con chicos", "puntos": ["Pileta climatizada", "Desayuno incluido", "Habitación Family"]},
                {"tipo_huesped": "Pareja", "puntos": ["Vista al lago", "Late checkout", "Cena en el restaurante"]},
                {"tipo_huesped": "Viajero de negocios", "puntos": ["Wifi", "Factura A", "Ubicación céntrica"]},
            ],
        },
    },
    "calificacion_leads": {
        "active": False,  # 100% adicional
        "data": {
            "items": [
                {"perfil": "Estadía larga en temporada baja", "prioridad": "alta", "dato_a_preguntar": "fechas exactas y flexibilidad"},
                {"perfil": "Fin de semana en temporada alta", "prioridad": "media", "dato_a_preguntar": "cantidad de personas"},
            ],
        },
    },
    "ejemplos": {
        "active": False,  # 100% adicional
        "data": {
            "items": [
                {"situacion": "Consulta de precio sin fechas",
                 "respuesta_modelo": "¡Hola! Encantada de ayudarte. Para pasarte precios exactos necesito las fechas — ¿cuándo estarías viniendo?"},
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# VALIDACIÓN — el data del cliente se sanea contra el schema (server-side).
# ---------------------------------------------------------------------------

def _clean_str(v, max_len=_MAX_STR) -> str:
    s = str(v or "").strip().replace("\r", " ").replace("\n", " ")
    return s[:max_len]


def _clean_tags(v) -> List[str]:
    if not isinstance(v, list):
        return []
    out = []
    for t in v[:_MAX_TAGS]:
        s = _clean_str(t, _MAX_TAG_LEN)
        if s:
            out.append(s)
    return out


def validate_training_data(category: str, raw: Dict) -> Tuple[Dict, List[str]]:
    """Sanea `raw` contra el schema de la categoría. Devuelve (data_limpia, notas).

    Solo acepta claves declaradas; recorta largos y cantidades; los strings se
    encajonan (sin saltos de línea) para que el render controle la estructura.
    """
    schema = FORM_SCHEMAS.get(category)
    if schema is None:
        raise ValueError(f"Categoría inválida: {category}")
    raw = raw or {}
    clean: Dict = {}
    notes: List[str] = []

    for field in schema["fields"]:
        key, ftype = field["key"], field["type"]
        if key not in raw:
            continue
        val = raw[key]
        if ftype in ("text", "textarea"):
            clean[key] = _clean_str(val, _MAX_STR if ftype == "text" else _MAX_STR * 2)
        elif ftype == "select":
            s = _clean_str(val, _MAX_TAG_LEN)
            if s in field.get("options", []):
                clean[key] = s
            else:
                notes.append(f"{field['label']}: opción inválida, se ignora.")
        elif ftype == "bool":
            clean[key] = bool(val)
        elif ftype == "tags":
            clean[key] = _clean_tags(val)
        elif ftype == "list":
            items = val if isinstance(val, list) else []
            if len(items) > _MAX_ITEMS:
                notes.append(f"{field['label']}: se toman las primeras {_MAX_ITEMS} filas.")
            rows = []
            for item in items[:_MAX_ITEMS]:
                if not isinstance(item, dict):
                    continue
                row = {}
                for sub in field["item_fields"]:
                    sk, st = sub["key"], sub["type"]
                    sv = item.get(sk)
                    if sv is None:
                        continue
                    if st == "tags":
                        row[sk] = _clean_tags(sv)[:3]
                    elif st == "select":
                        s = _clean_str(sv, _MAX_TAG_LEN)
                        if s in sub.get("options", []):
                            row[sk] = s
                    else:
                        row[sk] = _clean_str(sv, _MAX_STR)
                if any(v for v in row.values()):
                    rows.append(row)
            clean[key] = rows

    return clean, notes


# ---------------------------------------------------------------------------
# RENDER — el texto inyectable lo arma NUESTRA plantilla fija (Fase E2 lo usa).
# ---------------------------------------------------------------------------

def render_training(category: str, data: Dict) -> str:
    """Bloque de texto (acotado) para inyectar al prompt, desde los campos."""
    d = data or {}
    lines: List[str] = []

    if category == "tono_marca":
        lines.append("TONO DE MARCA (directiva del hotel):")
        if d.get("trato"):
            lines.append(f"- Trato: {d['trato']}.")
        if "emojis" in d:
            lines.append(f"- Emojis: {'sí, con moderación' if d['emojis'] else 'no usar'}.")
        if d.get("palabras_preferidas"):
            lines.append(f"- Usá expresiones como: {', '.join(d['palabras_preferidas'])}.")
        if d.get("palabras_evitar"):
            lines.append(f"- Evitá: {', '.join(d['palabras_evitar'])}.")
        if d.get("notas"):
            lines.append(f"- Estilo: {d['notas']}")
    elif category == "politica_comercial":
        lines.append("POLÍTICA COMERCIAL (directiva del hotel):")
        if d.get("no_prometer"):
            lines.append(f"- NUNCA prometas: {', '.join(d['no_prometer'])}.")
        if d.get("cuando_promo"):
            lines.append(f"- Promociones: {d['cuando_promo']}")
        if d.get("derivar_a_humano"):
            lines.append(f"- Derivá a una persona del equipo: {', '.join(d['derivar_a_humano'])}.")
    elif category == "objeciones":
        rows = d.get("items") or []
        if rows:
            lines.append("MANEJO DE OBJECIONES (directivas del hotel):")
            for r in rows:
                if r.get("objecion") and r.get("respuesta"):
                    lines.append(f"- Si dice \"{r['objecion']}\": {r['respuesta']}")
    elif category == "argumentario":
        rows = d.get("items") or []
        if rows:
            lines.append("QUÉ DESTACAR SEGÚN EL HUÉSPED (directivas del hotel):")
            for r in rows:
                if r.get("tipo_huesped") and r.get("puntos"):
                    lines.append(f"- {r['tipo_huesped']}: {', '.join(r['puntos'])}.")
    elif category == "calificacion_leads":
        rows = d.get("items") or []
        if rows:
            lines.append("PRIORIDAD DE CONSULTAS PARA ESTE HOTEL:")
            for r in rows:
                if r.get("perfil"):
                    extra = f" (preguntá: {r['dato_a_preguntar']})" if r.get("dato_a_preguntar") else ""
                    lines.append(f"- {r['perfil']}: prioridad {r.get('prioridad', 'media')}{extra}.")
    elif category == "ejemplos":
        rows = d.get("items") or []
        if rows:
            lines.append("EJEMPLOS DE RESPUESTA (imitá este estilo, no los copies literal):")
            for r in rows:
                if r.get("situacion") and r.get("respuesta_modelo"):
                    lines.append(f"- Ante \"{r['situacion']}\": \"{r['respuesta_modelo']}\"")

    text = "\n".join(lines).strip()
    return text[:_MAX_RENDER]


# ---------------------------------------------------------------------------
# EXTRACCIÓN con IA — el cliente sube un documento y la IA propone los CAMPOS
# (patrón calcado de knowledge_extractor: GPT-4o-mini, JSON estricto, el
# cliente SIEMPRE revisa antes de guardar).
# ---------------------------------------------------------------------------
_EXTRACT_MODEL = "gpt-4o-mini"

_EXTRACT_SCHEMAS = {
    "tono_marca": (
        'Extraé el tono de marca. Devolvé JSON: {"trato": "vos|usted", "emojis": true|false, '
        '"palabras_preferidas": ["string"], "palabras_evitar": ["string"], "notas": "string"}'
    ),
    "politica_comercial": (
        'Extraé la política comercial. Devolvé JSON: {"no_prometer": ["string"], '
        '"cuando_promo": "string", "derivar_a_humano": ["string"]}'
    ),
    "objeciones": (
        'Extraé objeciones de clientes y cómo responderlas. Devolvé JSON: '
        '{"items": [{"objecion": "string", "respuesta": "string"}]}'
    ),
    "argumentario": (
        'Extraé qué destacar según el tipo de huésped/cliente. Devolvé JSON: '
        '{"items": [{"tipo_huesped": "string", "puntos": ["string"]}]} (máx 3 puntos por tipo)'
    ),
    "calificacion_leads": (
        'Extraé criterios de calificación de leads. Devolvé JSON: '
        '{"items": [{"perfil": "string", "prioridad": "alta|media|baja", "dato_a_preguntar": "string"}]}'
    ),
    "ejemplos": (
        'Extraé ejemplos de buenas respuestas. Devolvé JSON: '
        '{"items": [{"situacion": "string", "respuesta_modelo": "string"}]}'
    ),
}


def extract_training_fields(category: str, text: str) -> Dict:
    """Propone los campos del formulario de `category` desde un documento.

    Devuelve el `data` YA validado contra el schema (el cliente revisa en el
    formulario pre-llenado antes de guardar). Defensivo: ante error, {}.
    """
    schema = _EXTRACT_SCHEMAS.get(category)
    text = (text or "").strip()
    if not schema or not text:
        return {}
    text = text[:8000]

    from app.core.openai_client import get_sync_openai
    client = get_sync_openai()
    try:
        resp = client.chat.completions.create(
            model=_EXTRACT_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    "Sos un extractor de directivas de entrenamiento para el agente de un hotel. "
                    "Devolvés SOLO un JSON válido. Si un dato no aparece, dejalo vacío. No inventes."
                )},
                {"role": "user", "content": f"{schema}\n\nDOCUMENTO:\n{text}"},
            ],
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        clean, _ = validate_training_data(category, raw)
        logger.info("Training fields extracted", category=category, keys=list(clean.keys()))
        return clean
    except Exception as e:  # noqa: BLE001
        logger.error("training extract failed", category=category, error=str(e))
        return {}


# ---------------------------------------------------------------------------
# SEED — plantillas de fábrica para el agente huésped (Aura). Idempotente,
# NUNCA pisa (el doc, una vez creado, es del cliente; restaurar es explícito).
# ---------------------------------------------------------------------------

def seed_training_defaults(db: Session) -> None:
    try:
        from app.models.agent import Agent
        aura = db.query(Agent).filter(Agent.role == "guest").first()
        if not aura:
            return
        for category in CATEGORY_ORDER:
            exists = (
                db.query(TrainingDocument)
                .filter(TrainingDocument.agent_id == aura.id,
                        TrainingDocument.category == category,
                        TrainingDocument.is_default == True)  # noqa: E712
                .first()
            )
            if exists:
                continue
            factory = FACTORY[category]
            db.add(TrainingDocument(
                agent_id=aura.id,
                title=FORM_SCHEMAS[category]["label"],
                source="form",
                category=category,
                data=factory["data"],
                active=factory["active"],
                is_default=True,
            ))
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo sembrar el entrenamiento de fábrica", error=str(e))
        db.rollback()
