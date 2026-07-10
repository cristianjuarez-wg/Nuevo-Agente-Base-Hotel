"""
Simulador de huésped humano (Workstream T.2).

Un LLM barato (OPENAI_MODEL_FAST) juega el papel de un huésped con una PERSONA (cómo escribe +
qué quiere) y conversa N turnos contra el AGENTE REAL, usando el mismo path que run_evals
(agent_service.chat / owner / staff). Devuelve un Transcript que el juez (judge.py) evalúa.

Se monta SOBRE el harness existente: reusa el despacho al agente, el session_id (que encadena
el historial del guest automáticamente) y la limpieza por session_id. NO reescribe nada de eso.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from app.config import settings
from app.core.llm.openai_client import get_async_openai
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Persona:
    key: str
    system_prompt: str      # CÓMO escribe (typos, largo/corto, idioma, tono)
    goal: str               # QUÉ quiere lograr
    max_turns: int = 8
    satisfied_when: str = ""  # descripción (para el juez) de cuándo se daría por servida


@dataclass
class Transcript:
    persona_key: str
    flow_id: str
    session_id: str
    turns: List[Dict] = field(default_factory=list)   # [{user, assistant, tool_trace}]
    tool_trace: List[Dict] = field(default_factory=list)  # acumulado de todos los turnos

    def as_text(self) -> str:
        lines = []
        for t in self.turns:
            lines.append(f"HUÉSPED: {t['user']}")
            lines.append(f"AGENTE: {t['assistant']}")
        return "\n".join(lines)


# ── Las 7 personas mínimas (verificadas contra la matriz de flujos) ──────────────
PERSONAS: Dict[str, Persona] = {
    "apurado": Persona(
        key="apurado",
        system_prompt=("Sos un huésped APURADO. Escribís mensajes de 3-4 palabras, sin saludo, "
                       "directo. Te impacientás si el agente se explaya ('sí dale', 'y el precio?', "
                       "'rapido porfa'). Nunca das rodeos."),
        goal="Saber si hay disponibilidad para 2 personas un fin de semana y el precio, rápido.",
        satisfied_when="Le dieron un precio concreto para sus fechas.",
    ),
    "indeciso": Persona(
        key="indeciso",
        system_prompt=("Sos un huésped INDECISO. Cambiás las fechas al menos dos veces durante la "
                       "charla ('mejor el finde que viene', 'no, mejor en dos semanas'), preguntás "
                       "lo mismo reformulado, dudás en voz alta."),
        goal="Comparar opciones de fechas antes de decidir reservar.",
        satisfied_when="Vio precios para al menos dos combinaciones de fechas.",
    ),
    "desprolijo": Persona(
        key="desprolijo",
        system_prompt=("Sos un huésped DESPROLIJO al escribir: todo en minúscula, con typos, sin "
                       "signos de puntuación, varias ideas en un mismo mensaje ('hola qeria saber "
                       "si tienen lugar para el 20 somos 2 y un nene y si hay desayuno')."),
        goal="Reservar para 2 adultos y un niño, y saber si el desayuno está incluido.",
        satisfied_when="Le confirmaron disponibilidad y respondieron lo del desayuno.",
    ),
    "enojado": Persona(
        key="enojado",
        system_prompt=("Sos un huésped ENOJADO en post-venta. Tenés una reserva y algo salió mal "
                       "(el aire de tu habitación no anda). Tono cortante, exigís solución ya, sin "
                       "insultos pero firme ('esto es un desastre', 'necesito que lo arreglen ahora')."),
        goal="Que resuelvan el problema del aire de tu habitación y te den una respuesta clara.",
        satisfied_when="El agente reconoció el problema y dijo que lo escala/registra al equipo.",
    ),
    "extranjero": Persona(
        key="extranjero",
        system_prompt=("You are a foreign guest who writes in ENGLISH. You do not speak Spanish. "
                       "You ask normally about a stay. Keep writing in English the whole time."),
        goal="Check availability and price for 2 people for a weekend, in English.",
        satisfied_when="You got a clear answer in a language you understand, with a price.",
    ),
    "regateador": Persona(
        key="regateador",
        system_prompt=("Sos un huésped REGATEADOR. Presionás por un descuento una y otra vez de "
                       "distintas formas ('no tenés algo mejor?', 'y si pago en efectivo?', 'dale un "
                       "descuentito', 'para dos noches no hacés mejor precio?'). Insistís."),
        goal="Conseguir un descuento sobre la tarifa publicada.",
        satisfied_when="El agente respondió tu pedido de descuento (dándolo o explicando la política).",
    ),
    "distraido": Persona(
        key="distraido",
        system_prompt=("Sos un huésped DISTRAÍDO. En medio de una consulta de reserva metés "
                       "preguntas off-topic ('hay wifi?', 'aceptan mascotas?', 'qué hora es allá?', "
                       "'se puede fumar?'), saltando de tema. Volvés a la reserva de a ratos."),
        goal="Reservar, pero te distraés con preguntas sueltas sobre servicios.",
        satisfied_when="Pese a las distracciones, avanzaste hacia ver disponibilidad para reservar.",
    ),
}


async def _persona_next_message(persona: Persona, history: List[Dict], model: str) -> str:
    """Genera el próximo mensaje del huésped (LLM-persona) dado el historial de la charla."""
    client = get_async_openai()
    convo = "\n".join(
        f"{'VOS (huésped)' if h['role'] == 'user' else 'AGENTE'}: {h['content']}"
        for h in history
    ) or "(la conversación aún no empezó)"
    prompt = (
        f"{persona.system_prompt}\n\n"
        f"Tu OBJETIVO en esta charla: {persona.goal}\n\n"
        f"Conversación hasta ahora:\n{convo}\n\n"
        "Escribí ÚNICAMENTE tu próximo mensaje como huésped (sin comillas, sin explicaciones, "
        "sin narración). Si ya lograste tu objetivo o el agente no puede ayudarte más, respondé "
        "exactamente 'LISTO'."
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,   # variabilidad humana
        max_tokens=120,
        timeout=30,
    )
    return (resp.choices[0].message.content or "").strip()


async def run_simulation(persona: Persona, flow_id: str, dispatch,
                         model: Optional[str] = None) -> Transcript:
    """Corre una conversación simulada persona↔agente real.

    `dispatch(session_id, message, history) -> (response, tool_trace)` es la función que manda un
    turno al agente real (la provee run_evals, que ya sabe despachar guest/owner/staff y limpiar).
    Reutiliza el session_id para encadenar contexto. Corta en max_turns, en 'LISTO', o si el
    huésped se repite (deadlock).
    """
    model = model or settings.OPENAI_MODEL_FAST
    session_id = f"sim-{persona.key}-{flow_id}-{uuid.uuid4().hex[:8]}"
    transcript = Transcript(persona_key=persona.key, flow_id=flow_id, session_id=session_id)
    history: List[Dict] = []
    last_user = None

    for _ in range(persona.max_turns):
        user_msg = await _persona_next_message(persona, history, model)
        if not user_msg or user_msg.upper().strip(" .!") == "LISTO":
            break
        if user_msg == last_user:   # deadlock: el huésped se repite
            break
        last_user = user_msg

        response, tool_trace = await dispatch(session_id, user_msg, history)
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": response})
        transcript.turns.append({"user": user_msg, "assistant": response, "tool_trace": tool_trace})
        transcript.tool_trace.extend(tool_trace or [])

    logger.info("Simulación completada", persona=persona.key, flow=flow_id,
                turnos=len(transcript.turns))
    return transcript
