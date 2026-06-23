from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from app.models.database import Base


class AgentSnapshot(Base):
    __tablename__ = "agent_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_type = Column(String(30), nullable=False)   # agent_profile | config_flag
    profile_name = Column(String(100), nullable=False)   # hotel | hotel_postventa
    profile_path = Column(String(255), nullable=False)   # ruta relativa al archivo JSON
    snapshot_data = Column(JSON, nullable=False)         # contenido completo del JSON
    reason = Column(Text, nullable=True)                 # ej: "pre_opportunity_42"
    opportunity_id = Column(Integer, nullable=True, index=True)  # soft FK

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "snapshot_type": self.snapshot_type,
            "profile_name": self.profile_name,
            "profile_path": self.profile_path,
            "opportunity_id": self.opportunity_id,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
