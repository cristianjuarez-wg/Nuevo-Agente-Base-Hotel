"""
Triage de ruteo PRE-VENTA / POST-VENTA / CASUAL sobre el OpenAI Agents SDK.

Es la "Capa 1" de ruteo: UNA sola pasada del SDK con handoffs desambigua el destino.
Reemplazó a las dos llamadas LLM caseras de agent_service.chat()
(`_is_casual_conversation` + `_detect_postsale_context`), retiradas en P4. Es el único
ruteo borroso del agente; chat() lo invoca siempre que no haya señal dura previa.

IMPORTANTE — qué hace y qué NO hace:
  - SÍ desambigua la ruta borrosa: ¿el usuario quiere comprar (pre), ya viajó/compró
    (post) o es charla casual/off-topic?
  - NO ejecuta el agente destino. El triage solo DEVUELVE la ruta. La construcción del
    paquete/ticket de post-venta (run_gate) y la acción sobre el ticket siguen viviendo
    en agent_service.chat(), determinísticas, como única fuente de verdad.
  - El triage SOLO corre cuando NO hubo señal dura previa (código de reserva por regex o
    sesión post-venta activa en BD). Esos cortocircuitos siguen en chat() y cuestan 0 LLM.

Mecanismo: un Agent "triage" con handoffs hacia dos agentes-marcador (preventa/postventa)
que no hacen nada más que marcar el destino; para casual, el triage responde directo sin
handoff. Tras Runner.run() se lee result.last_agent para derivar la ruta.
"""
import time
from typing import Dict, List

from agents import (
    Agent,
    Runner,
    ModelSettings,
    OpenAIChatCompletionsModel,
    set_default_openai_client,
    set_tracing_export_api_key,
)

from app.config import settings
from app.core.agent_profile import profile_manager
from app.core.observability.logging_config import get_logger
from app.core.llm.openai_client import get_async_openai
from app.core.llm.sdk_usage import extract_usage

logger = get_logger(__name__)

MAX_HISTORY_MESSAGES = 6

# Cliente OpenAI compartido por el SDK (singleton del proyecto, ver core/openai_client).
_sdk_client = get_async_openai()
set_default_openai_client(_sdk_client, use_for_tracing=False)
set_tracing_export_api_key(settings.OPENAI_API_KEY)

# Rutas posibles que devuelve el triage.
ROUTE_PREVENTA = "preventa"
ROUTE_POSTVENTA = "postventa"
ROUTE_CASUAL = "casual"

# Agentes-marcador: no ejecutan lógica, solo señalan el destino del handoff.
# El triage les hace handoff y luego leemos result.last_agent para saber la ruta.
_PREVENTA_MARKER = Agent(
    name="preventa",
    handoff_description="Consultas para conocer el hotel o RESERVAR una estadía: habitaciones, "
    "servicios, instalaciones, ubicación, políticas, promociones, precios, disponibilidad de "
    "fechas, y la intención de reservar. Dudas previas a tener una reserva.",
    instructions="Sos un marcador de ruteo. No respondas nada al usuario.",
)

_POSTVENTA_MARKER = Agent(
    name="postventa",
    handoff_description="Consultas de un huésped que YA tiene una reserva: dudas o problemas "
    "sobre SU reserva/estadía, cambios de fechas, cancelaciones, reclamos, asistencia durante "
    "la estadía. Incluye cuando menciona 'mi reserva', 'mi estadía' o da un código HTL-XXXX.",
    instructions="Sos un marcador de ruteo. No respondas nada al usuario.",
)


def _build_triage_instructions() -> str:
    agent_name = profile_manager.get_agent_name()
    return (
        f"Sos el sistema de ruteo de {agent_name}, concierge del Hampton by Hilton Bariloche. "
        "Tu única tarea es clasificar el mensaje del usuario en UNA de tres rutas y actuar:\n\n"
        "1) CONOCER EL HOTEL o RESERVAR (pre-venta): habitaciones, servicios, instalaciones, "
        "ubicación, políticas (check-in/out, mascotas, estacionamiento), promociones, precios, "
        "disponibilidad para fechas, e intención de reservar. TAMBIÉN, y MUY IMPORTANTE, cualquier "
        "señal de INTENCIÓN DE VIAJE O ESTADÍA, aunque venga envuelta en charla informal: ganas de "
        "viajar/venir a Bariloche, querer esquiar o hacer actividades EN EL MARCO de un viaje, "
        "mencionar fechas aunque sean vagas ('en las vacaciones de invierno', 'en julio', 'el finde "
        "largo'), decir con quién viaja (familia, pareja, los chicos) o de dónde viene. Todo eso "
        "puede llevar a una reserva → es pre-venta. TAMBIÉN incluye el RESTAURANTE: la carta/menú, "
        "qué hay para comer o tomar, pedir comida, room service, o reservar una mesa. TAMBIÉN "
        "incluye FORMAS DE PAGO y TRANSFERENCIAS: cómo pagar, datos bancarios, CBU, alias, cuentas "
        "bancarias o cuentas en otra moneda (pesos/dólares). TAMBIÉN consultas informativas sobre "
        "el hotel o sobre Bariloche relacionadas con la estadía aunque todavía no haya reserva. "
        "→ Hacé handoff a 'preventa'.\n\n"
        "2) HUÉSPED QUE YA TIENE RESERVA (post-venta): SOLO si el usuario da una SEÑAL EXPLÍCITA "
        "de que tiene una reserva propia ya confirmada — un código de reserva HTL-XXXX, o frases "
        "como 'mi reserva', 'mi estadía', 'ya reservé', 'estoy alojado' —, o pide un cambio de "
        "fecha, cancelación, reclamo o asistencia sobre ESA reserva suya. Si el usuario NO menciona "
        "una reserva propia, NO es post-venta. → Hacé handoff a 'postventa'.\n\n"
        "3) CHARLA CASUAL u OFF-TOPIC: saludos (incluso con varias palabras: 'Buenas, ¿cómo va "
        "todo?'), '¿cómo estás?', agradecimientos, despedidas, y temas que no tienen que ver con "
        "el hotel ni con un viaje: el clima en abstracto, cómo andás, recetas, fórmulas, hablar de "
        "fútbol o deportes como tema suelto, etc. Preguntar por el clima o 'cómo va todo' es CASUAL, "
        "NUNCA post-venta. OJO con la diferencia: 'me gusta esquiar' como comentario suelto puede ser "
        "casual, pero 'quiero ir a esquiar' / 'esquiar en mis vacaciones' / 'tengo ganas de viajar a "
        "Bariloche' es INTENCIÓN DE VIAJE → pre-venta, no casual. Una pregunta sobre el hotel, sus "
        "servicios, precios o Bariloche NO es casual: es pre-venta. "
        "→ NO hagas handoff. Respondé EXACTAMENTE con la palabra 'CASUAL' y nada más. "
        "NO redactes una respuesta para el usuario, NO des información sobre el tema off-topic, "
        "NO resuelvas recetas/tareas/cálculos: otra capa se encarga de redactar la respuesta.\n\n"
        "REGLAS DE DESEMPATE (importantes): un saludo o charla social SIN ninguna señal de viaje "
        "('hola', '¿cómo andás?', 'qué frío', 'aburrido el lunes') es SIEMPRE casual — jamás "
        "pre-venta ni post-venta. Pero si en el mensaje aparece una señal CONCRETA de intención de "
        "viaje o estadía (ganas de viajar a Bariloche, fechas, esquiar/actividades de un viaje, con "
        "quién viaja) → pre-venta, aunque venga con tono informal: preferimos poder ofrecerle "
        "disponibilidad y opciones antes que quedarnos solo en la charla. Preguntar por una PROMO, "
        "beneficio o descuento del hotel (qué incluye, o SI APLICA a sus fechas) es pre-venta, "
        "NUNCA casual: requiere verificar la promo con las herramientas, no responder de memoria. "
        "Ante la duda entre "
        "pre-venta y post-venta cuando el usuario NO mencionó una reserva propia → pre-venta. Solo "
        "enviá a post-venta cuando haya señal real de una reserva suya: el gate de post-venta le pide "
        "el código de reserva, así que un saludo o una charla social pura jamás debe caer ahí."
    )


class TriageSDKOrchestrator:
    """Ruteo pre/post/casual sobre el SDK. Devuelve la ruta; no ejecuta el agente destino."""

    def __init__(self):
        self._model_name = settings.OPENAI_MODEL_CLASSIFIER
        self._model = OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL_CLASSIFIER,  # gpt-4o-mini: ruteo barato
            openai_client=_sdk_client,
        )

    def _build_input_list(self, history: List[Dict], message: str) -> List[Dict]:
        recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
        items = [{"role": m["role"], "content": m["content"]} for m in recent]
        items.append({"role": "user", "content": message})
        return items

    async def route(self, message: str, session_id: str, history: List[Dict]) -> Dict:
        """Clasifica el mensaje y devuelve SOLO la ruta (no redacta respuestas).

        La respuesta para la ruta casual la genera siempre _generate_casual_response()
        en agent_service, que es la única fuente con las reglas de alcance (no recetas,
        no tareas, declinar off-topic y ofrecer ayuda con viajes).

        Returns:
            {
              "route": "preventa" | "postventa" | "casual",
              "processing_time": "X.XXs",
            }
        """
        start = time.time()
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model": self._model_name}

        triage_agent = Agent(
            name="triage",
            instructions=_build_triage_instructions(),
            model=self._model,
            model_settings=ModelSettings(temperature=0),
            handoffs=[_PREVENTA_MARKER, _POSTVENTA_MARKER],
        )

        input_list = self._build_input_list(history, message)

        try:
            result = await Runner.run(triage_agent, input=input_list, max_turns=3)
            usage = extract_usage(result, model=self._model_name)
            last_agent_name = getattr(result.last_agent, "name", "triage")

            if last_agent_name == _PREVENTA_MARKER.name:
                route = ROUTE_PREVENTA
            elif last_agent_name == _POSTVENTA_MARKER.name:
                route = ROUTE_POSTVENTA
            else:
                # No hubo handoff: el triage marcó casual/off-topic (responde "CASUAL").
                route = ROUTE_CASUAL
        except Exception as e:
            # Fallback conservador: si el triage falla, asumimos pre-venta (flujo de venta,
            # sin riesgo de negocio — el gate post-venta no se gatilla).
            logger.error("Triage SDK failed, defaulting to preventa",
                         session_id=session_id, error=str(e))
            route = ROUTE_PREVENTA

        duration = time.time() - start
        logger.info("Triage SDK route decided",
                    session_id=session_id, route=route,
                    message_preview=message[:50], duration=f"{duration:.2f}s")

        return {
            "route": route,
            "processing_time": f"{duration:.2f}s",
            "usage": usage,
        }


# Instancia global
triage_sdk_orchestrator = TriageSDKOrchestrator()
