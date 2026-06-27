"""
Servicio de skills: seed de la biblioteca del hotel + validación con TECHO DURO.

El invariante de seguridad (CENTRO_EMPLEADO_DIGITAL.md §2.5) vive acá: cuando un
agente guarda los valores de una skill (`policy_values`), el servidor los valida
contra el `parameter_schema` y los **recorta** a `parameter_limits`. El cliente
nunca puede superar el techo, aunque mande un valor mayor desde el frontend.
"""
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.skill import Skill, AgentSkill
from app.core.logging_config import get_logger

logger = get_logger(__name__)

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


def seed_skills(db: Session) -> None:
    """Da de alta la biblioteca de skills del hotel (idempotente por `key`)."""
    try:
        for spec in _SEED_SKILLS:
            if db.query(Skill).filter(Skill.key == spec["key"]).first():
                continue
            db.add(Skill(
                key=spec["key"], name=spec["name"], description=spec["description"],
                vertical=spec["vertical"], parameter_schema=spec["parameter_schema"],
                parameter_limits=spec["parameter_limits"], is_active=True,
            ))
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo sembrar las skills", error=str(e))
        db.rollback()


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


def list_agent_skills(db: Session, agent_id: int) -> List[Dict]:
    """Todas las skills activas con la config del agente (mergea plantilla + instancia)."""
    skills = db.query(Skill).filter(Skill.is_active == True).order_by(Skill.id.asc()).all()  # noqa: E712
    instances = {
        i.skill_id: i
        for i in db.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).all()
    }
    out = []
    for sk in skills:
        inst = instances.get(sk.id)
        out.append({
            "skill": sk.to_dict(),
            "enabled": bool(inst.enabled) if inst else False,
            "policy_values": (inst.policy_values or {}) if inst else {},
        })
    return out
