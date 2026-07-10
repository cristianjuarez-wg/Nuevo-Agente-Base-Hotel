"""
Regresión — los prompts de agente no tienen placeholders sin proveer.

Cada prompt se compone con `.format(**kwargs)` en su orquestador. Si el TEXTO tiene un
`{placeholder}` que el `.format()` NO provee, revienta con KeyError EN RUNTIME (el agente
responde "problemas para procesar") — un bug que los unit tests mockeados no ven y solo las
evals (con LLM) detectan. Este test extrae los placeholders del texto y verifica que el
conjunto que cada orquestador provee los cubre. Determinista, sin LLM.

Atrapa el bug de la Fase 1.2b: POSTSALE_TOOL_SYSTEM tenía {passenger_name} en el cuerpo
pero el orquestador dejó de pasarlo → KeyError en post-venta.
"""
import re
import string

_FIELD = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


def _placeholders(template: str) -> set:
    """Nombres de campo {x} del template (ignora {{ }} escapados)."""
    names = set()
    for _lit, field, _spec, _conv in string.Formatter().parse(template):
        if field:
            names.add(field.split(".")[0].split("[")[0])
    return names


def test_preventa_placeholders_cubiertos():
    from app.domains.hotel.prompts.tool_agent_prompts import TOOL_AGENT_SYSTEM
    # Claves que hotel_sdk_orchestrator._build_instructions provee.
    provided = {
        "agent_name", "identity_block", "fecha_actual", "hora_actual", "flow_block",
        "tono_block", "politica_block", "training_block", "lead_block", "language_block",
        "naturalidad_block", "ubicacion_block", "team_block",
    }
    missing = _placeholders(TOOL_AGENT_SYSTEM) - provided
    assert not missing, f"pre-venta: placeholders sin proveer → {missing}"


def test_postventa_placeholders_cubiertos():
    from app.domains.hotel.prompts.postsale_tool_prompts import POSTSALE_TOOL_SYSTEM
    provided = {
        "identity_block", "passenger_name", "package_context", "chat_history",
        "continuidad", "team_block",
    }
    missing = _placeholders(POSTSALE_TOOL_SYSTEM) - provided
    assert not missing, f"post-venta: placeholders sin proveer → {missing}"


def test_owner_placeholders_cubiertos():
    from app.domains.hotel.prompts.owner_prompts import OWNER_AGENT_SYSTEM
    provided = {"owner_name", "fecha_actual", "business_name"}
    missing = _placeholders(OWNER_AGENT_SYSTEM) - provided
    assert not missing, f"owner: placeholders sin proveer → {missing}"


def test_staff_placeholders_cubiertos():
    from app.domains.hotel.prompts.staff_tool_prompts import STAFF_AGENT_SYSTEM
    provided = {
        "nombre_agente", "business_name", "staff_name", "staff_area",
        "fecha_actual", "pending",
    }
    missing = _placeholders(STAFF_AGENT_SYSTEM) - provided
    assert not missing, f"staff: placeholders sin proveer → {missing}"


def test_casual_placeholders_cubiertos():
    from app.domains.hotel.prompts.generation_prompts import CASUAL_RESPONSE_SYSTEM
    provided = {
        "identity_block", "naturalidad_block", "team_block", "history_section",
        "message", "lead_capture_hint",
    }
    missing = _placeholders(CASUAL_RESPONSE_SYSTEM) - provided
    assert not missing, f"casual: placeholders sin proveer → {missing}"
