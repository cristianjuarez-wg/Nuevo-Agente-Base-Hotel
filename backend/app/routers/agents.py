"""
Router del "Centro del Empleado Digital" — agentes como entidad de primera clase.

  GET  /api/agents                     → lista de agentes (para el selector del legajo)
  GET  /api/agents/{id}                → identidad de un agente
  PUT  /api/agents/{id}                → editar identidad/estado (protegido X-Admin-Key)
  GET  /api/agents/{id}/performance    → legajo de desempeño + costo, por período

El desempeño se calcula on-demand (agent_performance_service) reusando
business_metrics y usage; no hay datos duplicados.
"""
import os
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.agent import Agent
from app.models.staff import StaffMember
from app.models.training_document import TrainingDocument
from app.models.skill import Skill, AgentSkill
from app.services import agent_performance_service, skill_service
from app.config import settings
from app.core.security.admin_auth import require_admin_key
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/agents", tags=["Agents"])


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None            # active | paused
    channels: Optional[List[str]] = None
    description: Optional[str] = None


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    """Todos los agentes, ordenados por id."""
    agents = db.query(Agent).order_by(Agent.id.asc()).all()
    return {"agents": [a.to_dict() for a in agents]}


# ── Kill switch global del Centro (Fase A) ───────────────────────────────────
# Declarados ANTES de las rutas /{agent_id} para que "centro-config" no matchee
# como un id de agente.

class CentroConfigUpdate(BaseModel):
    use_agent_config: bool


@router.get("/centro-config")
def get_centro_config_endpoint(db: Session = Depends(get_db)):
    """Estado del interruptor global 'usar configuración del Centro'."""
    from app.services import skill_service
    return skill_service.get_centro_config(db).to_dict()


@router.get("/training-schemas")
def get_training_schemas():
    """Formularios de entrenamiento por categoría (única fuente de verdad para el frontend)."""
    from app.services.training_service import FORM_SCHEMAS, CATEGORY_ORDER
    return {"order": CATEGORY_ORDER, "schemas": FORM_SCHEMAS}


@router.put("/centro-config", dependencies=[Depends(require_admin_key)])
def update_centro_config(payload: CentroConfigUpdate, db: Session = Depends(get_db)):
    """Prende/apaga la capa de configuración por agente (botón de emergencia).

    Apagado → los agentes corren con su comportamiento hardcodeado actual, al instante.
    """
    from app.services import skill_service
    config = skill_service.get_centro_config(db)
    config.use_agent_config = bool(payload.use_agent_config)
    db.commit()
    db.refresh(config)
    skill_service.invalidate_centro_cache()
    logger.info("Centro kill switch updated", enabled=config.use_agent_config)
    return config.to_dict()


@router.get("/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    return agent.to_dict()


@router.put("/{agent_id}", dependencies=[Depends(require_admin_key)])
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    """Edita la identidad/estado de un agente. El rol no se cambia desde acá (es estructural)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    if payload.name is not None:
        agent.name = payload.name.strip() or agent.name
    if payload.status is not None:
        if payload.status not in ("active", "paused"):
            raise HTTPException(400, "Estado inválido. Usar 'active' o 'paused'.")
        agent.status = payload.status
    if payload.channels is not None:
        agent.channels = payload.channels
    if payload.description is not None:
        agent.description = payload.description.strip() or None
    db.commit()
    db.refresh(agent)
    logger.info("Agent updated", id=agent.id, status=agent.status)
    return agent.to_dict()


@router.get("/{agent_id}/performance")
def get_performance(agent_id: int, period: str = "mes", db: Session = Depends(get_db)):
    """Legajo de desempeño + costo de IA del agente, para el período pedido."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    return agent_performance_service.get_agent_performance(db, agent, period=period)


# ── Parte de fin de día (Etapa 2) ────────────────────────────────────────────

class DailyReportConfig(BaseModel):
    enabled: bool = False
    recipient_staff_ids: List[int] = []


def _get_agent_or_404(db: Session, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agente no encontrado.")
    return agent


@router.get("/{agent_id}/daily-report")
def get_daily_report(agent_id: int, db: Session = Depends(get_db)):
    """Texto del parte de HOY (calculado on-demand) + la config de envío vigente.

    Siempre disponible: el parte se muestra aunque el envío automático esté apagado.
    """
    agent = _get_agent_or_404(db, agent_id)
    text = agent_performance_service.build_daily_report(db, agent)
    cfg = agent.daily_report or {"enabled": False, "recipient_staff_ids": []}
    return {"text": text, "config": cfg}


@router.put("/{agent_id}/daily-report/config", dependencies=[Depends(require_admin_key)])
def update_daily_report_config(agent_id: int, payload: DailyReportConfig, db: Session = Depends(get_db)):
    """Guarda la config opt-in del parte: activo/inactivo + destinatarios del staff."""
    agent = _get_agent_or_404(db, agent_id)
    # Validar que los destinatarios existan en el equipo.
    valid_ids = []
    for sid in payload.recipient_staff_ids:
        if db.query(StaffMember.id).filter(StaffMember.id == sid).first():
            valid_ids.append(sid)
    agent.daily_report = {"enabled": bool(payload.enabled), "recipient_staff_ids": valid_ids}
    db.commit()
    db.refresh(agent)
    logger.info("Daily report config updated", agent=agent.name, enabled=agent.daily_report["enabled"])
    return agent.daily_report


@router.post("/{agent_id}/daily-report/send", dependencies=[Depends(require_admin_key)])
def send_daily_report_now(agent_id: int, db: Session = Depends(get_db)):
    """Envía el parte AHORA a los destinatarios configurados (disparo manual).

    Funciona aunque el envío automático esté desactivado: el botón manual es independiente.
    Si no hay destinatarios configurados, devuelve 409 para que el frontend lo avise.
    """
    agent = _get_agent_or_404(db, agent_id)
    cfg = agent.daily_report or {}
    staff_ids = cfg.get("recipient_staff_ids") or []
    if not staff_ids:
        raise HTTPException(409, "No hay destinatarios configurados. Configurá el envío primero.")
    return agent_performance_service.send_daily_report(db, agent, staff_ids)


@router.post("/cron/daily-report", dependencies=[Depends(require_admin_key)])
def cron_daily_report(db: Session = Depends(get_db)):
    """Para un cron externo (Render Cron Job / ping): envía el parte de cada agente con
    el envío automático ACTIVADO a sus destinatarios. (El cron real se programa aparte.)"""
    results = []
    agents = db.query(Agent).all()
    for agent in agents:
        cfg = agent.daily_report or {}
        if not cfg.get("enabled"):
            continue
        staff_ids = cfg.get("recipient_staff_ids") or []
        if not staff_ids:
            continue
        results.append(agent_performance_service.send_daily_report(db, agent, staff_ids))
    return {"agents_sent": len(results), "results": results}


# ── Entrenamiento por agente (Etapa 3) ───────────────────────────────────────
# Reusa el parseo de documentos del repositorio de conocimiento (PDF/MD/TXT).
# Etapa (a) §7.2: el documento se guarda asociado al agente; el filtrado en el
# retrieval (RAG por agente) es etapa posterior — acá NO se ingesta al vector store.


class TrainingTextPayload(BaseModel):
    title: str
    text: str


@router.get("/{agent_id}/training")
def list_training(agent_id: int, db: Session = Depends(get_db)):
    """Documentos de entrenamiento de un agente."""
    _get_agent_or_404(db, agent_id)
    docs = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.agent_id == agent_id)
        .order_by(TrainingDocument.created_at.desc(), TrainingDocument.id.desc())
        .all()
    )
    return {"documents": [d.to_dict() for d in docs]}


@router.post("/{agent_id}/training/upload", dependencies=[Depends(require_admin_key)])
async def upload_training_document(
    agent_id: int,
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Sube un documento de entrenamiento (PDF/MD/TXT) para un agente."""
    from app.routers.knowledge import _extract_doc_text, DOC_ACCEPTED_EXTS, DOC_PDF_EXT

    agent = _get_agent_or_404(db, agent_id)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in DOC_ACCEPTED_EXTS:
        raise HTTPException(400, "Formatos aceptados: PDF, Markdown (.md) o texto (.txt). O pegá el texto.")

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Archivo demasiado grande (máx {settings.MAX_FILE_SIZE_MB}MB)")

    text = _extract_doc_text(content, file.filename)
    if not text or not text.strip():
        raise HTTPException(422, "No se pudo extraer texto del documento (¿es un PDF escaneado sin OCR?).")

    source = "pdf" if ext == DOC_PDF_EXT else "markdown" if ext in (".md", ".markdown") else "text"
    doc = TrainingDocument(
        agent_id=agent.id, title=title.strip() or (file.filename or "Documento"),
        source=source, filename=file.filename, content=text.strip(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info("Training document uploaded", agent=agent.name, doc_id=doc.id, source=source)
    return doc.to_dict()


@router.post("/{agent_id}/training/text", dependencies=[Depends(require_admin_key)])
def add_training_text(agent_id: int, payload: TrainingTextPayload, db: Session = Depends(get_db)):
    """Crea un documento de entrenamiento a partir de texto pegado."""
    agent = _get_agent_or_404(db, agent_id)
    if not payload.text.strip():
        raise HTTPException(400, "El texto no puede estar vacío.")
    doc = TrainingDocument(
        agent_id=agent.id, title=payload.title.strip() or "Documento",
        source="text", content=payload.text.strip(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc.to_dict()


@router.delete("/{agent_id}/training/{doc_id}", dependencies=[Depends(require_admin_key)])
def delete_training_document(agent_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Elimina un documento de entrenamiento del agente. Las plantillas de fábrica NO se
    borran: se desactivan o se restauran (así siempre se puede volver al punto de partida)."""
    doc = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.id == doc_id, TrainingDocument.agent_id == agent_id)
        .first()
    )
    if not doc:
        raise HTTPException(404, "Documento no encontrado.")
    if doc.is_default:
        raise HTTPException(400, "Las plantillas de fábrica no se eliminan: desactivala o restaurala.")
    db.delete(doc)
    db.commit()
    return {"deleted": True, "id": doc_id}


# ── Entrenamiento ESTRUCTURADO (Fase E1) ─────────────────────────────────────

class TrainingEntryPayload(BaseModel):
    category: str
    data: dict
    title: Optional[str] = None


class TrainingUpdatePayload(BaseModel):
    data: Optional[dict] = None
    active: Optional[bool] = None
    title: Optional[str] = None


@router.post("/{agent_id}/training/entry", dependencies=[Depends(require_admin_key)])
def create_training_entry(agent_id: int, payload: TrainingEntryPayload, db: Session = Depends(get_db)):
    """Crea un entrenamiento estructurado desde el formulario (campos, no texto libre)."""
    from app.services import training_service
    agent = _get_agent_or_404(db, agent_id)
    if payload.category not in training_service.FORM_SCHEMAS:
        raise HTTPException(400, f"Categoría inválida. Válidas: {', '.join(training_service.CATEGORY_ORDER)}")
    clean, notes = training_service.validate_training_data(payload.category, payload.data)
    doc = TrainingDocument(
        agent_id=agent.id,
        title=(payload.title or "").strip() or training_service.FORM_SCHEMAS[payload.category]["label"],
        source="form", category=payload.category, data=clean, active=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {**doc.to_dict(), "notes": notes}


@router.put("/{agent_id}/training/{doc_id}", dependencies=[Depends(require_admin_key)])
def update_training_entry(agent_id: int, doc_id: int, payload: TrainingUpdatePayload, db: Session = Depends(get_db)):
    """Edita los campos y/o el estado activo de un entrenamiento (incluidas las de fábrica)."""
    from app.services import training_service
    doc = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.id == doc_id, TrainingDocument.agent_id == agent_id)
        .first()
    )
    if not doc:
        raise HTTPException(404, "Documento no encontrado.")
    notes = []
    if payload.data is not None:
        if not doc.category:
            raise HTTPException(400, "Este documento es de texto libre (legado): no tiene formulario.")
        clean, notes = training_service.validate_training_data(doc.category, payload.data)
        doc.data = clean
    if payload.active is not None:
        doc.active = bool(payload.active)
    if payload.title is not None:
        doc.title = payload.title.strip() or doc.title
    db.commit()
    db.refresh(doc)
    return {**doc.to_dict(), "notes": notes}


@router.post("/{agent_id}/training/{doc_id}/restore", dependencies=[Depends(require_admin_key)])
def restore_training_entry(agent_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Restaura una plantilla de fábrica a su contenido original (solo is_default)."""
    from app.services import training_service
    doc = (
        db.query(TrainingDocument)
        .filter(TrainingDocument.id == doc_id, TrainingDocument.agent_id == agent_id)
        .first()
    )
    if not doc:
        raise HTTPException(404, "Documento no encontrado.")
    if not doc.is_default or doc.category not in training_service.FACTORY:
        raise HTTPException(400, "Solo las plantillas de fábrica se pueden restaurar.")
    factory = training_service.FACTORY[doc.category]
    doc.data = factory["data"]
    doc.active = factory["active"]
    doc.title = training_service.FORM_SCHEMAS[doc.category]["label"]
    db.commit()
    db.refresh(doc)
    return doc.to_dict()


@router.post("/{agent_id}/training/extract", dependencies=[Depends(require_admin_key)])
async def extract_training(
    agent_id: int,
    category: str = Form(...),
    file: UploadFile = File(None),
    text: str = Form(None),
    db: Session = Depends(get_db),
):
    """Sube un documento (o texto) y la IA propone los CAMPOS del formulario de la
    categoría, ya validados. El cliente revisa el formulario pre-llenado antes de guardar."""
    from app.services import training_service
    from app.routers.knowledge import _extract_doc_text, DOC_ACCEPTED_EXTS

    _get_agent_or_404(db, agent_id)
    if category not in training_service.FORM_SCHEMAS:
        raise HTTPException(400, f"Categoría inválida. Válidas: {', '.join(training_service.CATEGORY_ORDER)}")

    doc_text = (text or "").strip()
    if file is not None:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in DOC_ACCEPTED_EXTS:
            raise HTTPException(400, "Formatos aceptados: PDF, Markdown (.md) o texto (.txt). O pegá el texto.")
        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(413, f"Archivo demasiado grande (máx {settings.MAX_FILE_SIZE_MB}MB)")
        doc_text = _extract_doc_text(content, file.filename)

    if not doc_text.strip():
        raise HTTPException(422, "No se pudo obtener texto del documento.")

    data = training_service.extract_training_fields(category, doc_text)
    if not data:
        raise HTTPException(422, "No pude extraer directivas de ese documento. Cargá los campos a mano.")
    return {"category": category, "data": data}


# ── Skills + políticas (Etapa 4) ─────────────────────────────────────────────

class AgentSkillUpdate(BaseModel):
    enabled: Optional[bool] = None
    policy_values: Optional[dict] = None


@router.get("/{agent_id}/skills")
def list_skills(agent_id: int, kind: str = "function", db: Session = Depends(get_db)):
    """Skills de un tipo con la config de este agente.

    kind="function" (default): las adosables de la pestaña Skills.
    kind="flow": los flujos principales, para la pestaña Flujos (Fase C).
    """
    if kind not in ("function", "flow"):
        raise HTTPException(400, "kind inválido. Usar 'function' o 'flow'.")
    _get_agent_or_404(db, agent_id)
    return {"skills": skill_service.list_agent_skills(db, agent_id, kind=kind)}


@router.put("/{agent_id}/skills/{skill_id}", dependencies=[Depends(require_admin_key)])
def update_agent_skill(agent_id: int, skill_id: int, payload: AgentSkillUpdate, db: Session = Depends(get_db)):
    """Habilita/configura una skill para un agente.

    INVARIANTE §2.5: los valores se validan contra el schema y se RECORTAN al techo
    duro server-side. Devuelve los valores efectivos + notas de los recortes aplicados.
    """
    _get_agent_or_404(db, agent_id)
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(404, "Skill no encontrada.")

    # Los FLUJOS principales no se apagan por agente: solo se configuran. El apagado
    # global es el kill switch del Centro (centro-config). Tratamiento 4 de la Fase A.
    if payload.enabled is not None and (skill.kind or "function") == "flow":
        raise HTTPException(
            400,
            "Los flujos principales no se apagan; para desactivar la capa usá el interruptor global del Centro.",
        )

    inst = skill_service.get_or_create_agent_skill(db, agent_id, skill_id)
    notes = []
    if payload.policy_values is not None:
        clean, notes = skill_service.validate_and_clamp(skill, payload.policy_values)
        inst.policy_values = clean
    if payload.enabled is not None:
        inst.enabled = bool(payload.enabled)
    db.commit()
    db.refresh(inst)
    logger.info("Agent skill updated", agent_id=agent_id, skill=skill.key, enabled=inst.enabled)
    return {**inst.to_dict(), "notes": notes}
