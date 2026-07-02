"""
Servicio de skills: seed de la biblioteca del hotel + validación con TECHO DURO.

El invariante de seguridad (CENTRO_EMPLEADO_DIGITAL.md §2.5) vive acá: cuando un
agente guarda los valores de una skill (`policy_values`), el servidor los valida
contra el `parameter_schema` y los **recorta** a `parameter_limits`. El cliente
nunca puede superar el techo, aunque mande un valor mayor desde el frontend.
"""
import time
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.skill import Skill, AgentSkill
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# KILL SWITCH global (CentroConfig) — Fase A.
# Cache corto para no agregar una query en cada turno (patrón _budget_cache).
# ---------------------------------------------------------------------------
_CENTRO_CACHE_TTL = 15  # segundos
_centro_cache: Dict[str, object] = {"checked_at": 0.0, "enabled": True}


def get_centro_config(db: Session):
    """Obtiene (o crea) la fila única del kill switch. Nace ENCENDIDO de fábrica."""
    from app.models.centro_config import CentroConfig
    config = db.query(CentroConfig).filter(CentroConfig.id == 1).first()
    if config is None:
        config = CentroConfig(id=1, use_agent_config=True)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def is_centro_enabled(db: Session) -> bool:
    """True si la capa de configuración por agente está activa. Fail-open a True
    solo en el sentido de NO romper: ante error devuelve False (= comportamiento
    hardcodeado actual, el estado más seguro)."""
    now = time.time()
    if (now - float(_centro_cache["checked_at"])) < _CENTRO_CACHE_TTL:
        return bool(_centro_cache["enabled"])
    try:
        enabled = bool(get_centro_config(db).use_agent_config)
    except Exception as e:  # noqa: BLE001 — sin config legible → capa apagada (defaults)
        logger.warning("No se pudo leer CentroConfig; capa de agentes apagada", error=str(e))
        enabled = False
    _centro_cache["checked_at"] = now
    _centro_cache["enabled"] = enabled
    return enabled


def invalidate_centro_cache() -> None:
    """Fuerza relectura en el próximo turno (llamar al cambiar el switch o una config)."""
    _centro_cache["checked_at"] = 0.0

# Biblioteca de skills del HOTEL (vertical). El Centro es horizontal; esto es el
# contenido que cambia por rubro. Empezamos con capacidades gobernables (niveles 1-2
# de visión §10.2). La negociación con proveedor llega en la Etapa 5.
_SEED_SKILLS = [
    {
        "key": "coordinar_transfer",
        "name": "Coordinar transfer al aeropuerto",
        "description": "Agenda y confirma el traslado del huésped con la remisería partner.",
        "vertical": "hotel",
        "parameter_schema": [
            {"key": "anticipacion_horas", "label": "Anticipación de aviso (horas)", "type": "number", "default": 12},
            {"key": "costo_max_usd", "label": "Costo máximo del traslado (USD)", "type": "number", "default": 30},
            {"key": "confirmar_con_huesped", "label": "Confirmar con el huésped antes de cerrar", "type": "bool", "default": True},
        ],
        "parameter_limits": {"costo_max_usd": {"ceiling": 60}},
    },
    {
        "key": "upsell_servicios",
        "name": "Ofrecer servicios del hotel (upsell)",
        "description": "Sugiere spa, late checkout o experiencias cuando es relevante en la charla.",
        "vertical": "hotel",
        "parameter_schema": [
            {"key": "descuento_max_pct", "label": "Descuento máximo a ofrecer (%)", "type": "percent", "default": 10},
            {"key": "solo_si_pregunta", "label": "Ofrecer solo si el huésped abre el tema", "type": "bool", "default": False},
        ],
        "parameter_limits": {"descuento_max_pct": {"ceiling": 20}},
    },
]


# FLUJOS principales por rol (kind="flow"). Los DEFAULTS de cada parámetro son EXACTAMENTE
# los valores hoy hardcodeados en el código (lead_analyzer / postsale / staff): con valores
# de fábrica el comportamiento es idéntico → PARIDAD por construcción (Fase A).
# La `description` es el "espejo del cerebro": qué hace el flujo, en lenguaje claro (UI Fase C).
_SEED_FLOWS = [
    {
        "key": "flujo_preventa",
        "name": "Flujo de pre-venta",
        "role": "guest",
        "description": (
            "Atiende consultas y avanza la venta con calidez. Pide las FECHAS antes que los "
            "datos de contacto. Captura el lead cuando hay interés real o en el momento de "
            "cierre (despedida u objeción de precio). Pide nombre y teléfono; email opcional."
        ),
        "parameter_schema": [
            # Variante de ESTILO comercial (Fase B). Las plantillas viven en
            # prompts/flow_blocks.py; acá solo la elección + descripción legible.
            {
                "key": "variante", "label": "Estilo comercial", "type": "select",
                "default": "estandar",
                "options": [
                    {"value": "estandar", "label": "Captación estándar",
                     "description": "Avanza la venta con calidez: pide las fechas antes que los datos, muestra disponibilidad y captura el contacto cuando hay interés real o en el momento de cierre. Es el comportamiento recomendado."},
                    {"value": "proactiva", "label": "Captación proactiva",
                     "description": "Ofrece ver disponibilidad apenas detecta interés de viaje. Busca el cierre con tacto cuando el huésped ya vio opciones, y menciona las promociones vigentes ante una objeción de precio, sin esperar."},
                    {"value": "sin_presion", "label": "Atención sin presión",
                     "description": "Informa y atiende con calidez, sin vender activamente: no pide datos de contacto por iniciativa propia ni insiste con la reserva. Captura el contacto solo si el huésped lo ofrece o lo pide expresamente."},
                ],
            },
            {"key": "min_msgs", "label": "Mensajes mínimos antes de pedir contacto", "type": "number", "default": 2},
            {"key": "score_caliente", "label": "Interés mínimo para pedir contacto (lead caliente, 1-10)", "type": "number", "default": 7},
            {"key": "score_tibio", "label": "Interés mínimo en leads tibios (1-10)", "type": "number", "default": 6},
            {"key": "msgs_tibio", "label": "Mensajes mínimos para pedir contacto a un lead tibio", "type": "number", "default": 4},
        ],
        "parameter_limits": {
            "min_msgs": {"ceiling": 6},
            "score_caliente": {"ceiling": 9},
            "score_tibio": {"ceiling": 9},
            "msgs_tibio": {"ceiling": 10},
        },
    },
    {
        "key": "flujo_postventa",
        "name": "Flujo de post-venta",
        "role": "guest",
        "description": (
            "Atiende huéspedes con reserva confirmada. Evalúa cada mensaje: ¿lo resuelvo o "
            "escalo a un humano? Considera 'sesión nueva' tras una pausa de silencio."
        ),
        "parameter_schema": [
            {"key": "gap_minutes", "label": "Minutos de silencio para considerar sesión nueva", "type": "number", "default": 30},
        ],
        "parameter_limits": {"gap_minutes": {"ceiling": 240}},
    },
    {
        "key": "flujo_operaciones",
        "name": "Flujo de operaciones",
        "role": "staff",
        "description": (
            "Coordina al equipo del hotel: resuelve tickets, registra incidencias y lista "
            "las tareas pendientes de cada miembro."
        ),
        "parameter_schema": [
            {"key": "max_tickets", "label": "Máximo de tareas pendientes a listar", "type": "number", "default": 8},
        ],
        "parameter_limits": {"max_tickets": {"ceiling": 20}},
    },
]


def defaults_from_schema(skill: Skill) -> Dict:
    """Valores default declarados en el parameter_schema (única fuente de verdad)."""
    return {
        p["key"]: p["default"]
        for p in (skill.parameter_schema or [])
        if "default" in p
    }


def seed_skills(db: Session) -> None:
    """Da de alta la biblioteca de skills y los flujos del hotel (idempotente por `key`).

    Para los FLUJOS además pre-crea las instancias AgentSkill HABILITADAS por rol
    (Aura ← preventa+postventa; Operaciones ← operaciones) con los defaults del schema.
    Nunca pisa una instancia existente: las ediciones del cliente sobreviven redeploys.
    """
    try:
        for spec in _SEED_SKILLS:
            _upsert_skill_template(db, spec, kind="function", vertical=spec["vertical"])
        for spec in _SEED_FLOWS:
            _upsert_skill_template(db, spec, kind="flow", vertical="hotel")
        db.commit()
        _seed_flow_instances(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo sembrar las skills", error=str(e))
        db.rollback()


def _upsert_skill_template(db: Session, spec: Dict, kind: str, vertical: str) -> None:
    """Crea o REFRESCA la plantilla de una skill sembrada de fábrica.

    Regla de propiedad: la PLANTILLA (schema, techos, nombre, descripción) es NUESTRA
    y se actualiza con cada deploy (así los flujos ganan parámetros nuevos, ej.
    `variante` en Fase B). La INSTANCIA (AgentSkill.policy_values) es DEL CLIENTE y
    nunca se toca acá: los valores viejos siguen válidos y los parámetros nuevos
    caen a su default vía el merge de get_flow_values.
    """
    skill = db.query(Skill).filter(Skill.key == spec["key"]).first()
    if skill is None:
        db.add(Skill(
            key=spec["key"], name=spec["name"], description=spec["description"],
            kind=kind, vertical=vertical,
            parameter_schema=spec["parameter_schema"],
            parameter_limits=spec["parameter_limits"], is_active=True,
        ))
        return
    skill.name = spec["name"]
    skill.description = spec["description"]
    skill.kind = kind
    skill.parameter_schema = spec["parameter_schema"]
    skill.parameter_limits = spec["parameter_limits"]


def _seed_flow_instances(db: Session) -> None:
    """Pre-crea las AgentSkill de los flujos, HABILITADAS y con defaults, por rol del agente.

    Idempotente sin pisar: si la instancia ya existe (aunque el cliente la haya editado),
    no se toca.
    """
    from app.models.agent import Agent
    for spec in _SEED_FLOWS:
        skill = db.query(Skill).filter(Skill.key == spec["key"]).first()
        if not skill:
            continue
        agents = db.query(Agent).filter(Agent.role == spec["role"]).all()
        for agent in agents:
            exists = (
                db.query(AgentSkill)
                .filter(AgentSkill.agent_id == agent.id, AgentSkill.skill_id == skill.id)
                .first()
            )
            if exists:
                continue  # nunca pisar ediciones del cliente
            db.add(AgentSkill(
                agent_id=agent.id, skill_id=skill.id,
                policy_values=defaults_from_schema(skill), enabled=True,
            ))
    db.commit()


def _coerce(value, ptype):
    """Convierte el valor entrante al tipo declarado (best-effort)."""
    try:
        if ptype in ("number", "percent"):
            return float(value)
        if ptype == "bool":
            return bool(value)
        return str(value)
    except (TypeError, ValueError):
        return None


def validate_and_clamp(skill: Skill, raw_values: Dict) -> Tuple[Dict, List[str]]:
    """Valida `raw_values` contra el schema de la skill y RECORTA al techo duro.

    Devuelve (valores_saneados, notas). `notas` lista los recortes aplicados, para
    que el frontend pueda avisar "se ajustó X al máximo permitido".
    Solo se aceptan claves declaradas en el schema (ignora cualquier extra).
    """
    schema = skill.parameter_schema or []
    limits = skill.parameter_limits or {}
    clean: Dict = {}
    notes: List[str] = []

    for param in schema:
        key = param.get("key")
        ptype = param.get("type", "text")
        if key not in raw_values:
            # Si no vino, usar el default declarado (si hay).
            if "default" in param:
                clean[key] = param["default"]
            continue
        val = _coerce(raw_values.get(key), ptype)
        if val is None:
            continue  # valor inválido para el tipo → se descarta (queda el default si lo hubiera)
        # select: solo opciones declaradas en el schema; inválida → default de fábrica.
        if ptype == "select":
            allowed = {o.get("value") for o in (param.get("options") or [])}
            if val not in allowed:
                notes.append(f"{param.get('label', key)}: opción inválida, se usa la de fábrica.")
                continue
        # Techo duro: recortar si supera el ceiling.
        ceiling = (limits.get(key) or {}).get("ceiling")
        if ceiling is not None and ptype in ("number", "percent") and val > ceiling:
            val = ceiling
            notes.append(f"{param.get('label', key)} se ajustó al máximo permitido ({ceiling}).")
        clean[key] = val

    return clean, notes


def get_or_create_agent_skill(db: Session, agent_id: int, skill_id: int) -> AgentSkill:
    """Devuelve la instancia AgentSkill (la crea deshabilitada si no existe)."""
    inst = (
        db.query(AgentSkill)
        .filter(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill_id)
        .first()
    )
    if inst is None:
        inst = AgentSkill(agent_id=agent_id, skill_id=skill_id, policy_values={}, enabled=False)
        db.add(inst)
        db.commit()
        db.refresh(inst)
    return inst


def list_agent_skills(db: Session, agent_id: int, kind: str = "function") -> List[Dict]:
    """Skills activas de un tipo con la config del agente (mergea plantilla + instancia).

    Por defecto solo `function`: los flujos (kind="flow") NO se muestran como toggles en la
    pestaña Skills — tienen su UI propia (Fase C) y no se apagan individualmente.
    """
    skills = (
        db.query(Skill)
        .filter(Skill.is_active == True, Skill.kind == kind)  # noqa: E712
        .order_by(Skill.id.asc())
        .all()
    )
    instances = {
        i.skill_id: i
        for i in db.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).all()
    }
    out = []
    for sk in skills:
        inst = instances.get(sk.id)
        # FLUJOS: solo los ASIGNADOS a este agente (con instancia). Las functions sí
        # se listan como catálogo completo (cualquier agente puede activarlas).
        if kind == "flow" and inst is None:
            continue
        out.append({
            "skill": sk.to_dict(),
            "enabled": bool(inst.enabled) if inst else False,
            "policy_values": (inst.policy_values or {}) if inst else {},
        })
    return out


# ---------------------------------------------------------------------------
# Lectura de config de FLUJOS en el turno (Fase A) — fail-open SIEMPRE.
# ---------------------------------------------------------------------------

def get_flow_values(db: Session, agent_id: Optional[int], flow_key: str) -> Optional[Dict]:
    """Config efectiva de un flujo para un agente: {defaults del schema, **policy_values}.

    Devuelve None cuando la capa debe ignorarse (kill switch apagado, agente/flujo
    inexistente, o cualquier error). Los llamadores tratan None = usar los valores
    hardcodeados actuales (fail-open, paridad garantizada).
    """
    try:
        if agent_id is None or not is_centro_enabled(db):
            return None
        skill = db.query(Skill).filter(Skill.key == flow_key, Skill.kind == "flow").first()
        if not skill or not skill.is_active:
            return None
        inst = (
            db.query(AgentSkill)
            .filter(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill.id)
            .first()
        )
        if not inst or not inst.enabled:
            return None
        return {**defaults_from_schema(skill), **(inst.policy_values or {})}
    except Exception as e:  # noqa: BLE001 — nunca romper un turno por config
        logger.warning("No se pudo leer la config del flujo", flow=flow_key, error=str(e))
        return None


def get_flow_values_for_session(db: Session, session_id: str, flow_key: str) -> Optional[Dict]:
    """Como get_flow_values, resolviendo el agente desde el session_id (wa_/web-/owner_/staff_)."""
    try:
        from app.services.agent_directory import agent_for_session
        agent = agent_for_session(db, session_id)
        return get_flow_values(db, agent.id if agent else None, flow_key)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo resolver el agente de la sesión", error=str(e))
        return None


def get_flow_values_by_role(db: Session, role: str, flow_key: str) -> Optional[Dict]:
    """Como get_flow_values, resolviendo el agente por rol (para llamadores sin session_id)."""
    try:
        from app.models.agent import Agent
        agent = db.query(Agent).filter(Agent.role == role).first()
        return get_flow_values(db, agent.id if agent else None, flow_key)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo resolver el agente por rol", role=role, error=str(e))
        return None


# ---------------------------------------------------------------------------
# Filtrado de TOOLS por function-skills (Fase A) — mapa VACÍO de fábrica.
# Regla dura: tool que no figure en el mapa = SIEMPRE activa. Así las 16 tools
# actuales quedan intactas (paridad por construcción). Las funciones nuevas
# (ej. reservar_remis) nacen mapeadas; las viejas se migran una a una con
# decisión explícita (FLUJOS_Y_ESTRATEGIA.md §6, tratamiento 1).
# ---------------------------------------------------------------------------
SKILL_TOOL_MAP: Dict[str, List[str]] = {}


def _tool_name(tool) -> str:
    """Nombre de una tool del SDK (FunctionTool.name) o de una función plana."""
    return getattr(tool, "name", None) or getattr(tool, "__name__", "") or ""


def filter_tools(tools: List, enabled_skill_keys: set, tool_map: Optional[Dict[str, List[str]]] = None) -> List:
    """Núcleo puro del filtrado (testeable sin DB): quita las tools gobernadas por una
    skill NO habilitada. Tool sin skill mapeada → siempre activa."""
    tmap = SKILL_TOOL_MAP if tool_map is None else tool_map
    governed = {t: key for key, names in tmap.items() for t in names}
    out = []
    for tool in tools:
        skill_key = governed.get(_tool_name(tool))
        if skill_key is None or skill_key in enabled_skill_keys:
            out.append(tool)
    return out


def filter_tools_for_session(db: Session, session_id: str, tools: List) -> List:
    """Filtra las tools según las function-skills habilitadas del agente de la sesión.

    Fail-open: con kill switch apagado, mapa vacío o cualquier error, devuelve la lista intacta.
    """
    try:
        if not SKILL_TOOL_MAP:
            return tools  # mapa vacío (Fase A): nada que filtrar, cero costo
        from app.services.agent_directory import agent_for_session
        agent = agent_for_session(db, session_id)
        if agent is None or not is_centro_enabled(db):
            return tools
        rows = (
            db.query(Skill.key)
            .join(AgentSkill, AgentSkill.skill_id == Skill.id)
            .filter(AgentSkill.agent_id == agent.id, AgentSkill.enabled == True,  # noqa: E712
                    Skill.kind == "function")
            .all()
        )
        enabled_keys = {r[0] for r in rows}
        filtered = filter_tools(tools, enabled_keys)
        return filtered if filtered else tools  # jamás dejar al agente sin tools
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo filtrar tools por skills; se usan todas", error=str(e))
        return tools
