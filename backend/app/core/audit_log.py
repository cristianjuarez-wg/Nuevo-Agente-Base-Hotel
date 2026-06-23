"""
Auditoría de turnos del chat de Aura.

Escribe UNA línea JSON por turno (JSONL) en backend/logs/aura_audit.jsonl con toda
la traza: mensaje del usuario, ruta del triage (casual/pre/post), tools llamadas
(nombre + args + resultado), respuesta final, cards adjuntadas, lead analysis,
tokens y tiempos. Sirve para auditar cómo razona el agente y detectar errores de
lógica revisando las conversaciones turno a turno.

Activación: AUDIT_CHAT=true (default activado en DEBUG). Se puede apagar en prod.
Pensado para no romper nunca el flujo del chat: cualquier error al loguear se traga.
"""
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Carpeta y archivo de auditoría (junto al backend).
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "aura_audit.jsonl")

# Rotación simple: si el archivo supera este tamaño, se renombra a .1 (un solo backup).
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

_lock = threading.Lock()


def is_enabled() -> bool:
    """Auditoría activa si AUDIT_CHAT=true, o por defecto cuando DEBUG está on."""
    flag = getattr(settings, "AUDIT_CHAT", None)
    if flag is None:
        return bool(settings.DEBUG)
    return bool(flag)


def _rotate_if_needed() -> None:
    try:
        if os.path.exists(_LOG_FILE) and os.path.getsize(_LOG_FILE) > _MAX_BYTES:
            backup = _LOG_FILE + ".1"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(_LOG_FILE, backup)
    except OSError:
        pass  # rotación best-effort; nunca interrumpe


def log_turn(entry: Dict[str, Any]) -> None:
    """Agrega una línea JSON al log de auditoría. No lanza nunca."""
    if not is_enabled():
        return
    try:
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), **entry}
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with _lock:
            os.makedirs(_LOG_DIR, exist_ok=True)
            _rotate_if_needed()
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        # Eco en consola para verlo en vivo al probar local (resumen, no el JSON entero).
        logger.info("AUDIT turn",
                    session=entry.get("session_id"),
                    route=entry.get("route"),
                    tools=[t.get("name") for t in entry.get("tools", [])],
                    cards=[c.get("type") for c in entry.get("cards", [])])
    except Exception as e:  # noqa: BLE001 — auditar nunca debe tumbar el chat
        logger.warning("audit_log.log_turn failed", error=str(e))


def build_tool_trace(sdk_result: Any) -> list:
    """Extrae de un resultado del Agents SDK la traza de tools: nombre, args y output.

    Tolera distintas formas de `new_items` (tool_call_item / tool_call_output_item).
    Devuelve [{name, arguments, output}] en orden de invocación.
    """
    calls: list = []
    outputs_by_callid: Dict[str, Any] = {}
    try:
        items = getattr(sdk_result, "new_items", []) or []
        # Primera pasada: recolectar outputs por call_id si están disponibles.
        for it in items:
            if getattr(it, "type", None) == "tool_call_output_item":
                raw = getattr(it, "raw_item", None)
                call_id = _get(raw, "call_id") or _get(raw, "id")
                out = getattr(it, "output", None)
                if call_id is not None:
                    outputs_by_callid[call_id] = out
        # Segunda pasada: las llamadas, emparejadas con su output.
        for it in items:
            if getattr(it, "type", None) == "tool_call_item":
                raw = getattr(it, "raw_item", None)
                name = _get(raw, "name")
                if not name:
                    continue
                args = _get(raw, "arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else args
                except (ValueError, TypeError):
                    pass
                call_id = _get(raw, "call_id") or _get(raw, "id")
                calls.append({
                    "name": name,
                    "arguments": _truncate(args),
                    "output": _truncate(outputs_by_callid.get(call_id)),
                })
    except Exception as e:  # noqa: BLE001
        logger.warning("audit_log.build_tool_trace failed", error=str(e))
    return calls


def _get(obj: Any, attr: str) -> Optional[Any]:
    """Lee un atributo tanto de objeto como de dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(attr)
    return getattr(obj, attr, None)


def _truncate(value: Any, limit: int = 1500) -> Any:
    """Acorta valores largos (outputs de tools) para que el JSONL siga siendo legible."""
    try:
        s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = str(value)
    if len(s) > limit:
        return s[:limit] + f"…[+{len(s) - limit} chars]"
    return value if not isinstance(value, str) else s
