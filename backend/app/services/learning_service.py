import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from app.core.openai_client import get_sync_openai
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.config import settings
from app.core.agent_profile import profile_manager
from app.models.learning_opportunity import LearningOpportunity
from app.models.agent_snapshot import AgentSnapshot
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Campos de perfil que pueden ser modificados automáticamente
PROFILE_FIELD_WHITELIST = {
    "greeting_message",
    "no_info_response",
    "capabilities",
    "conversation_starters",
}

# Claves de configuración que pueden ser modificadas en .env
CONFIG_FLAG_WHITELIST = {
    "OPENAI_TEMPERATURE",
    "TOP_K_RESULTS",
    "LOG_LEVEL",
}

# Rutas de perfil por nombre
PROFILE_PATHS = {
    "turismo": "./data/agent_profiles/turismo.json",
    "postventa": "./data/agent_profiles/postventa.json",
}

AUDIT_SYSTEM_PROMPT = """Eres un auditor de calidad para Kami, asistente IA de una agencia de turismo argentina.
Recibirás muestras de conversaciones reales entre clientes y Kami.

Tu tarea es detectar 2-5 oportunidades de mejora concretas y accionables, priorizando:
- Conversiones perdidas (usuario interesado que no dejó datos de contacto)
- Respuestas confusas, muy largas o sin estructura clara
- Preguntas frecuentes que Kami maneja mal o de forma inconsistente
- Oportunidades de upsell o cross-sell desaprovechadas
- Inconsistencias de tono o personalidad
- Falta de proactividad para capturar el lead

Para cada oportunidad DEBES proponer un cambio específico y accionable. Prefiere cambios pequeños y de alto impacto sobre reescrituras amplias.

Responde ÚNICAMENTE con un objeto JSON con esta estructura exacta:
{
  "opportunities": [
    {
      "title": "Título conciso (máx 80 caracteres)",
      "description": "Descripción detallada del problema detectado en las conversaciones",
      "rationale": "Por qué este cambio beneficia al agente y a la agencia",
      "business_impact": "Qué KPI mejora (conversión, satisfacción, eficiencia) y cómo. Sé específico con el valor de negocio.",
      "impact_category": "conversion|satisfaction|efficiency|other",
      "impact_score": 8,
      "target_type": "agent_profile_field|system_prompt|config_flag|manual_review_required",
      "target_profile": "turismo|postventa",
      "target_field": "nombre_del_campo_o_null",
      "proposed_value": "nuevo contenido propuesto o null si es manual_review_required",
      "implementation_plan": "Pasos concretos para implementar este cambio"
    }
  ]
}

Notas importantes:
- target_type=agent_profile_field: campos modificables: greeting_message, no_info_response, capabilities (lista), conversation_starters (lista)
- target_type=system_prompt: modifica system_prompt_template (DEBE preservar {agent_name} y {context})
- target_type=config_flag: modifica configuración del servidor (incluir key y valor en proposed_value como "KEY=valor")
- target_type=manual_review_required: mejora que requiere intervención humana (nuevos documentos, cambios de proceso)
- Solo sugiere cambios que puedas justificar con evidencia de las conversaciones analizadas
"""


class LearningService:

    def __init__(self):
        self._audit_in_progress = False
        self._client = get_sync_openai()

    # ─── AUDITORÍA ────────────────────────────────────────────────────────────

    async def audit_conversations(
        self,
        db: Session,
        max_conversations: int = 30,
        force: bool = False
    ) -> Dict:
        if self._audit_in_progress:
            return {
                "success": False,
                "skipped_reason": "audit_already_running",
                "opportunities_created": 0,
                "conversations_analyzed": 0,
            }

        self._audit_in_progress = True
        try:
            conversations = self._select_conversations_for_audit(db, max_conversations)
            if not conversations:
                return {
                    "success": True,
                    "opportunities_created": 0,
                    "conversations_analyzed": 0,
                    "skipped_reason": "no_conversations_found",
                }

            samples = self._serialize_conversations(conversations)
            raw_opportunities = self._call_audit_llm(samples)

            created = 0
            for opp_data in raw_opportunities:
                if self._validate_opportunity_data(opp_data):
                    opp = LearningOpportunity(
                        title=opp_data.get("title", "Sin título")[:255],
                        description=opp_data.get("description", ""),
                        rationale=opp_data.get("rationale", ""),
                        business_impact=opp_data.get("business_impact", ""),
                        implementation_plan=opp_data.get("implementation_plan", ""),
                        impact_category=opp_data.get("impact_category"),
                        impact_score=opp_data.get("impact_score"),
                        status="pending_review",
                        target_type=opp_data.get("target_type", "manual_review_required"),
                        target_profile=opp_data.get("target_profile"),
                        target_field=opp_data.get("target_field"),
                        proposed_value=opp_data.get("proposed_value"),
                        conversations_analyzed=len(conversations),
                        sample_session_ids=[c.session_id[-6:] for c in conversations],
                    )
                    db.add(opp)
                    created += 1

            db.commit()
            logger.info("Auditoría completada", opportunities_created=created, conversations_analyzed=len(conversations))
            return {
                "success": True,
                "opportunities_created": created,
                "conversations_analyzed": len(conversations),
            }

        except Exception as e:
            logger.error("Error en auditoría", error=str(e))
            db.rollback()
            raise
        finally:
            self._audit_in_progress = False

    def _select_conversations_for_audit(self, db: Session, max_conversations: int) -> List:
        budgets = {
            "negative": int(max_conversations * 0.40),
            "abandoned": int(max_conversations * 0.25),
            "positive": int(max_conversations * 0.20),
            "recent": max_conversations - int(max_conversations * 0.40) - int(max_conversations * 0.25) - int(max_conversations * 0.20),
        }

        results = []

        # Conversaciones completas sin lead — mayor señal de mejora
        negative = (
            db.query(Conversation)
            .filter(
                Conversation.status == "completed",
                Conversation.lead_generated == 0,
                Conversation.message_count >= 5,
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(budgets["negative"])
            .all()
        )
        results.extend(negative)

        # Conversaciones abandonadas
        abandoned = (
            db.query(Conversation)
            .filter(
                Conversation.status == "abandoned",
                Conversation.message_count.between(2, 6),
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(budgets["abandoned"])
            .all()
        )
        results.extend(abandoned)

        # Conversaciones con lead exitoso — señal positiva para referencia
        positive = (
            db.query(Conversation)
            .filter(
                Conversation.status == "completed",
                Conversation.lead_generated == 1,
                Conversation.message_count >= 4,
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(budgets["positive"])
            .all()
        )
        results.extend(positive)

        # Conversaciones recientes (cualquier estado)
        existing_ids = {c.id for c in results}
        recent = (
            db.query(Conversation)
            .filter(Conversation.id.notin_(existing_ids))
            .order_by(Conversation.started_at.desc())
            .limit(budgets["recent"])
            .all()
        )
        results.extend(recent)

        # Precargar mensajes
        all_session_ids = [c.session_id for c in results]
        messages_by_session: Dict[str, List] = {}
        if all_session_ids:
            all_messages = (
                db.query(ConversationMessage)
                .filter(ConversationMessage.session_id.in_(all_session_ids))
                .order_by(ConversationMessage.sequence_number)
                .all()
            )
            for msg in all_messages:
                messages_by_session.setdefault(msg.session_id, []).append(msg)

        for conv in results:
            conv._messages_cache = messages_by_session.get(conv.session_id, [])

        return results

    def _serialize_conversations(self, conversations: List) -> List[Dict]:
        samples = []
        for conv in conversations:
            messages = getattr(conv, "_messages_cache", [])
            # Truncar: primeros 6 + últimos 6 si hay más de 12
            if len(messages) > 12:
                selected = messages[:6] + messages[-6:]
            else:
                selected = messages

            samples.append({
                "session_id": conv.session_id[-6:],
                "status": conv.status,
                "lead_generated": bool(conv.lead_generated),
                "message_count": conv.message_count,
                "destinations_mentioned": conv.destinations_mentioned or [],
                "messages": [
                    {"role": m.role, "content": m.content[:500]}
                    for m in selected
                ],
            })
        return samples

    def _call_audit_llm(self, samples: List[Dict]) -> List[Dict]:
        user_message = (
            f"Analiza las siguientes {len(samples)} conversaciones y detecta oportunidades de mejora.\n\n"
            f"{json.dumps(samples, indent=2, ensure_ascii=False)}"
        )

        response = self._client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content
        data = json.loads(content)
        return data.get("opportunities", [])

    def _validate_opportunity_data(self, data: Dict) -> bool:
        required = ["title", "description", "rationale", "business_impact", "implementation_plan", "target_type"]
        if not all(k in data for k in required):
            return False
        valid_target_types = {"agent_profile_field", "system_prompt", "config_flag", "manual_review_required"}
        if data.get("target_type") not in valid_target_types:
            return False
        return True

    # ─── CRUD DE OPORTUNIDADES ────────────────────────────────────────────────

    def get_opportunities(
        self,
        db: Session,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[LearningOpportunity]:
        q = db.query(LearningOpportunity)
        if status:
            q = q.filter(LearningOpportunity.status == status)
        return q.order_by(LearningOpportunity.created_at.desc()).offset(offset).limit(limit).all()

    def get_opportunity(self, db: Session, opportunity_id: int) -> Optional[LearningOpportunity]:
        return db.query(LearningOpportunity).filter(LearningOpportunity.id == opportunity_id).first()

    def get_snapshots(self, db: Session, limit: int = 30) -> List[AgentSnapshot]:
        return db.query(AgentSnapshot).order_by(AgentSnapshot.created_at.desc()).limit(limit).all()

    # ─── FLUJO DE APROBACIÓN ─────────────────────────────────────────────────

    def approve_opportunity(self, db: Session, opportunity_id: int) -> LearningOpportunity:
        opp = self._get_or_raise(db, opportunity_id)
        if opp.status != "pending_review":
            raise ValueError(f"Solo se pueden aprobar oportunidades en estado pending_review. Estado actual: {opp.status}")
        opp.status = "approved"
        opp.approved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(opp)
        logger.info("Oportunidad aprobada", opportunity_id=opportunity_id)
        return opp

    def reject_opportunity(self, db: Session, opportunity_id: int, reason: str = "") -> LearningOpportunity:
        opp = self._get_or_raise(db, opportunity_id)
        if opp.status != "pending_review":
            raise ValueError(f"Solo se pueden rechazar oportunidades en estado pending_review. Estado actual: {opp.status}")
        opp.status = "rejected"
        opp.rejected_at = datetime.now(timezone.utc)
        opp.rejection_reason = reason
        db.commit()
        db.refresh(opp)
        logger.info("Oportunidad rechazada", opportunity_id=opportunity_id, reason=reason)
        return opp

    # ─── IMPLEMENTACIÓN ───────────────────────────────────────────────────────

    def implement_opportunity(self, db: Session, opportunity_id: int) -> Dict:
        opp = self._get_or_raise(db, opportunity_id)
        if opp.status != "approved":
            raise ValueError(f"Solo se pueden implementar oportunidades aprobadas. Estado actual: {opp.status}")

        opp.status = "implementing"
        db.commit()

        try:
            # Manual — no toca archivos
            if opp.target_type == "manual_review_required":
                opp.status = "implemented"
                opp.implemented_at = datetime.now(timezone.utc)
                opp.implementation_details = {"requires_manual": True}
                db.commit()
                return {
                    "success": True,
                    "requires_manual": True,
                    "manual_instructions": opp.implementation_plan,
                    "message": "Esta mejora requiere intervención manual. Consulta el plan de implementación.",
                }

            # Crear snapshot antes de modificar
            snapshot = self._create_snapshot(db, opp)

            if opp.target_type == "agent_profile_field":
                changed = self._implement_agent_profile_field(opp)
            elif opp.target_type == "system_prompt":
                changed = self._implement_system_prompt(opp)
            elif opp.target_type == "config_flag":
                changed = self._implement_config_flag(opp)
            else:
                raise ValueError(f"target_type no reconocido: {opp.target_type}")

            # Hot-reload del perfil en memoria si aplica
            if opp.target_type in ("agent_profile_field", "system_prompt") and opp.target_profile:
                profile_path = PROFILE_PATHS.get(opp.target_profile)
                if profile_path and opp.target_profile == "turismo":
                    profile_manager.switch_profile(profile_path)

            opp.status = "implemented"
            opp.implemented_at = datetime.now(timezone.utc)
            opp.implementation_details = {"snapshot_id": snapshot.id, "changed": changed}
            db.commit()

            logger.info("Oportunidad implementada", opportunity_id=opportunity_id, snapshot_id=snapshot.id)
            return {
                "success": True,
                "requires_manual": False,
                "snapshot_id": snapshot.id,
                "changed": changed,
                "message": "Implementación completada. Evalúa el resultado en los próximos días.",
            }

        except Exception as e:
            opp.status = "approved"  # revertir a approved para que se pueda reintentar
            db.commit()
            logger.error("Error implementando oportunidad", opportunity_id=opportunity_id, error=str(e))
            raise

    def _create_snapshot(self, db: Session, opp: LearningOpportunity) -> AgentSnapshot:
        profile_name = opp.target_profile or "turismo"
        profile_path = PROFILE_PATHS.get(profile_name, PROFILE_PATHS["turismo"])

        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)

        snapshot = AgentSnapshot(
            snapshot_type="agent_profile",
            profile_name=profile_name,
            profile_path=profile_path,
            snapshot_data=profile_data,
            reason=f"pre_opportunity_{opp.id}",
            opportunity_id=opp.id,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot

    def _implement_agent_profile_field(self, opp: LearningOpportunity) -> Dict:
        if opp.target_field not in PROFILE_FIELD_WHITELIST:
            raise ValueError(f"Campo no permitido: {opp.target_field}. Campos permitidos: {PROFILE_FIELD_WHITELIST}")

        profile_name = opp.target_profile or "turismo"
        profile_path = PROFILE_PATHS.get(profile_name)

        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)

        old_value = profile_data.get(opp.target_field)

        # Intentar parsear como JSON si es lista
        new_value = opp.proposed_value
        try:
            parsed = json.loads(new_value)
            new_value = parsed
        except (json.JSONDecodeError, TypeError):
            pass  # es un string simple

        profile_data[opp.target_field] = new_value

        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2, ensure_ascii=False)

        return {"field": opp.target_field, "old_value": old_value, "new_value": new_value}

    def _implement_system_prompt(self, opp: LearningOpportunity) -> Dict:
        profile_name = opp.target_profile or "turismo"
        profile_path = PROFILE_PATHS.get(profile_name)

        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)

        old_value = profile_data.get("system_prompt_template", "")
        new_value = opp.proposed_value

        # Validar placeholders obligatorios
        test_profile = dict(profile_data)
        test_profile["system_prompt_template"] = new_value
        valid, msg = profile_manager.validate_profile(test_profile)
        if not valid:
            raise ValueError(f"El system_prompt propuesto no es válido: {msg}")

        profile_data["system_prompt_template"] = new_value

        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2, ensure_ascii=False)

        return {"field": "system_prompt_template", "old_value": old_value[:200] + "...", "new_value": new_value[:200] + "..."}

    def _implement_config_flag(self, opp: LearningOpportunity) -> Dict:
        # proposed_value debe tener formato "KEY=valor"
        if not opp.proposed_value or "=" not in opp.proposed_value:
            raise ValueError("Para config_flag, proposed_value debe tener formato KEY=valor")

        key, _, value = opp.proposed_value.partition("=")
        key = key.strip()

        if key not in CONFIG_FLAG_WHITELIST:
            raise ValueError(f"Clave no permitida: {key}. Claves permitidas: {CONFIG_FLAG_WHITELIST}")

        env_path = ".env"
        if not os.path.exists(env_path):
            env_path = "./backend/.env"

        lines = []
        old_value = None
        replaced = False

        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                    old_value = line.strip().split("=", 1)[1] if "=" in line else None
                    new_lines.append(f"{key}={value}\n")
                    replaced = True
                else:
                    new_lines.append(line)
            lines = new_lines

        if not replaced:
            lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return {
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "requires_restart": True,
        }

    # ─── EVALUACIÓN ──────────────────────────────────────────────────────────

    def evaluate_implementation(
        self,
        db: Session,
        opportunity_id: int,
        evaluation_result: str,
        notes: str = "",
    ) -> Dict:
        opp = self._get_or_raise(db, opportunity_id)
        if opp.status not in ("implemented", "evaluating"):
            raise ValueError(f"Solo se pueden evaluar oportunidades implementadas. Estado actual: {opp.status}")

        if evaluation_result not in ("satisfactory", "unsatisfactory"):
            raise ValueError("evaluation_result debe ser 'satisfactory' o 'unsatisfactory'")

        opp.evaluation_result = evaluation_result
        opp.evaluation_notes = notes
        opp.evaluated_at = datetime.now(timezone.utc)
        opp.status = "evaluating"
        db.commit()

        rolled_back = False
        if evaluation_result == "unsatisfactory":
            self.rollback_implementation(db, opportunity_id, reason="Rollback automático por evaluación insatisfactoria")
            rolled_back = True

        db.refresh(opp)
        return {"status": opp.status, "rolled_back": rolled_back}

    # ─── ROLLBACK ─────────────────────────────────────────────────────────────

    def rollback_implementation(
        self,
        db: Session,
        opportunity_id: int,
        reason: str = "Rollback manual por el operador",
    ) -> Dict:
        opp = self._get_or_raise(db, opportunity_id)
        if opp.status not in ("implemented", "evaluating"):
            raise ValueError(f"Solo se puede revertir una oportunidad implementada. Estado actual: {opp.status}")

        details = opp.implementation_details or {}

        if details.get("requires_manual"):
            opp.status = "rolled_back"
            opp.rolled_back_at = datetime.now(timezone.utc)
            opp.rollback_reason = reason
            db.commit()
            return {"success": True, "message": "Marcada como revertida (era manual, no hay archivo que restaurar)."}

        snapshot_id = details.get("snapshot_id")
        if not snapshot_id:
            raise ValueError("No se encontró snapshot para hacer rollback.")

        snapshot = db.query(AgentSnapshot).filter(AgentSnapshot.id == snapshot_id).first()
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} no encontrado en la base de datos.")

        self._restore_from_snapshot(snapshot)

        # Hot-reload
        if opp.target_profile == "turismo":
            profile_manager.switch_profile(snapshot.profile_path)

        opp.status = "rolled_back"
        opp.rolled_back_at = datetime.now(timezone.utc)
        opp.rollback_reason = reason
        db.commit()

        logger.info("Rollback ejecutado", opportunity_id=opportunity_id, snapshot_id=snapshot_id)
        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "message": "El perfil fue restaurado al estado anterior.",
        }

    def _restore_from_snapshot(self, snapshot: AgentSnapshot) -> None:
        with open(snapshot.profile_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.snapshot_data, f, indent=2, ensure_ascii=False)

    # ─── HELPERS ──────────────────────────────────────────────────────────────

    def _get_or_raise(self, db: Session, opportunity_id: int) -> LearningOpportunity:
        opp = db.query(LearningOpportunity).filter(LearningOpportunity.id == opportunity_id).first()
        if not opp:
            raise ValueError(f"Oportunidad {opportunity_id} no encontrada.")
        return opp


learning_service = LearningService()
