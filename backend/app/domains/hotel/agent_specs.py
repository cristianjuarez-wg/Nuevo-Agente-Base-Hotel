"""
Catálogo DECLARATIVO de los agentes del hotel (Fase 2.2).

Cada agente es una AgentSpec: modelo, temperatura, turnos, historial, tools (por key del
ToolRegistry) y guardrails. El loop de ejecución es el runtime genérico
(core/agents/sdk_runtime.run_agent); los orquestadores quedan como capa fina de dominio
(composición del prompt + post-procesamiento propio).

Los valores replican EXACTAMENTE los históricos de cada orquestador (paridad):
  staff: turns=5, hist=10, temp=0.4 · owner: 6/20/settings · post: 5/8/0.7+guardrail ·
  pre: 6/20/settings+guardrail. Triage y casual usan engine="completions"/clasificador y
  no corren por el runtime SDK, pero figuran acá para que el catálogo esté completo.
"""
from app.core.agents.agent_spec import AgentSpec

SPECS = {
    "hotel_staff": AgentSpec(
        key="hotel_staff",
        display_name="Coordinador de Operaciones",
        display_role="staff",
        engine="sdk",
        model_setting="OPENAI_MODEL",
        temperature=0.4,
        max_turns=5,
        max_history=10,
        tools=("staff.resolver_ticket", "staff.reportar_incidencia", "staff.mis_tickets"),
        prompt_composer="hotel_staff",
        channels=("whatsapp",),
    ),
    "hotel_owner": AgentSpec(
        key="hotel_owner",
        display_name="Asesor de Gerencia",
        display_role="management",
        engine="sdk",
        model_setting="OPENAI_MODEL",
        temperature_setting="OPENAI_TEMPERATURE",
        max_turns=6,
        max_history=20,
        tools=(
            "owner.consultar_ocupacion", "owner.consultar_ingresos", "owner.consultar_leads",
            "owner.consultar_quejas", "owner.consultar_resumen_negocio",
            "owner.operacion_hoy", "owner.buscar_huesped", "owner.consultar_habitacion",
            "owner.analizar_ingresos", "owner.analizar_ocupacion", "owner.ranking_habitaciones",
            "owner.comparar_periodos", "owner.consultar_embudo", "owner.consultar_soporte",
            "owner.consultar_equipo", "owner.consultar_conocimiento",
            "owner.registrar_plan", "owner.consultar_planes", "owner.actualizar_plan",
        ),
        prompt_composer="hotel_owner",
        channels=("whatsapp",),
    ),
    "hotel_postsale": AgentSpec(
        key="hotel_postsale",
        display_name="",  # sale del perfil (Aura) — name_from_profile
        display_role="guest",
        engine="sdk",
        model_setting="OPENAI_MODEL",
        temperature=0.7,
        max_turns=5,
        max_history=8,
        tools=(
            "postsale.analizar_escalacion", "postsale.consultar_info_hotel",
            "postsale.solicitar_servicio", "postsale.ver_fotos_habitacion",
            "postsale.registrar_preferencia", "postsale.ver_carta", "postsale.reservar_mesa",
            "postsale.armar_pedido_carta", "postsale.consultar_pago",
            "postsale.comercios_amigos", "postsale.promociones_vigentes",
            "postsale.excursiones_y_atracciones",
        ),
        prompt_composer="hotel_postsale",
        input_guardrails=("postsale.relevancia",),
        channels=("web", "whatsapp"),
        name_from_profile=True,
    ),
    "hotel_presale": AgentSpec(
        key="hotel_presale",
        display_name="",  # sale del perfil (Aura)
        display_role="guest",
        engine="sdk",
        model_setting="OPENAI_MODEL",
        temperature_setting="OPENAI_TEMPERATURE",
        max_turns=6,
        max_history=20,
        tools=(
            "presale.info_hotel", "presale.consultar_disponibilidad", "presale.crear_reserva",
            "presale.consultar_reserva", "presale.info_pago", "presale.como_llegar",
            "presale.comercios_amigos", "presale.excursiones_y_atracciones",
            "presale.promos_vigentes", "presale.calcular_precio_promo", "presale.ver_carta",
            "presale.armar_pedido_carta", "presale.registrar_pedido", "presale.reservar_mesa",
            "presale.comprar_voucher", "presale.guardar_preferencia",
        ),
        prompt_composer="hotel_presale",
        input_guardrails=("presale.relevancia",),
        channels=("web", "whatsapp"),
        name_from_profile=True,
    ),
    # ── Fuera del runtime SDK (catálogo completo) ────────────────────────────
    "casual": AgentSpec(
        key="casual",
        display_name="",  # Aura
        display_role="guest",
        engine="completions",
        model_setting="OPENAI_MODEL",
        temperature=0.8,
        max_history=4,
        prompt_composer="casual",
        channels=("web", "whatsapp"),
        name_from_profile=True,
    ),
    "triage": AgentSpec(
        key="triage",
        display_name="triage",
        display_role="guest",
        engine="sdk",
        model_setting="OPENAI_MODEL_CLASSIFIER",
        temperature=0.0,
        max_turns=3,
        max_history=20,
        prompt_composer="triage",
        channels=("web", "whatsapp"),
    ),
}
