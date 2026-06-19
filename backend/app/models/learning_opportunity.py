from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from app.models.database import Base


class LearningOpportunity(Base):
    __tablename__ = "learning_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    business_impact = Column(Text, nullable=False)
    implementation_plan = Column(Text, nullable=False)
    impact_category = Column(String(50), nullable=True)  # conversion|satisfaction|efficiency|other
    impact_score = Column(Integer, nullable=True)  # 1-10

    # Estado de la oportunidad
    status = Column(String(30), default="pending_review", index=True)
    # pending_review | approved | rejected | implementing | implemented | evaluating | rolled_back

    # Alcance del cambio propuesto
    target_type = Column(String(30), nullable=False)
    # agent_profile_field | system_prompt | config_flag | manual_review_required
    target_profile = Column(String(50), nullable=True)   # turismo | postventa
    target_field = Column(String(100), nullable=True)    # campo exacto en el JSON del perfil
    proposed_value = Column(Text, nullable=True)         # nuevo contenido propuesto por GPT

    # Procedencia de la auditoría
    conversations_analyzed = Column(Integer, nullable=True)
    sample_session_ids = Column(JSON, nullable=True)     # list[str]

    # Aprobación / rechazo
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Implementación
    implementation_details = Column(JSON, nullable=True)  # {"snapshot_id": int, "changed": {...}}
    implemented_at = Column(DateTime(timezone=True), nullable=True)

    # Evaluación
    evaluation_result = Column(String(20), nullable=True)  # satisfactory | unsatisfactory
    evaluation_notes = Column(Text, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)

    # Rollback
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
    rollback_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "business_impact": self.business_impact,
            "implementation_plan": self.implementation_plan,
            "impact_category": self.impact_category,
            "impact_score": self.impact_score,
            "status": self.status,
            "target_type": self.target_type,
            "target_profile": self.target_profile,
            "target_field": self.target_field,
            "proposed_value": self.proposed_value,
            "conversations_analyzed": self.conversations_analyzed,
            "sample_session_ids": self.sample_session_ids,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "rejection_reason": self.rejection_reason,
            "implementation_details": self.implementation_details,
            "implemented_at": self.implemented_at.isoformat() if self.implemented_at else None,
            "evaluation_result": self.evaluation_result,
            "evaluation_notes": self.evaluation_notes,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "rolled_back_at": self.rolled_back_at.isoformat() if self.rolled_back_at else None,
            "rollback_reason": self.rollback_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
