"""
Test del kanban de leads: mover un lead de etapa sincroniza su status interno
(won→converted, lost→inactive, new/contacted→active) para que las métricas y la lista
sean coherentes con el tablero.
"""
import pytest


_seq = 0


def _mk_lead(db, session_id, name="Test", stage="new", status="active"):
    from app.models.lead import Lead
    from datetime import datetime
    global _seq
    _seq += 1
    # created_at fuera de cualquier rango de otros tests (la DB en memoria es compartida).
    lead = Lead(session_id=session_id, name=name, phone=f"+549115000{_seq:04d}",
                lead_type="TIBIO", interest_score=5, status=status, kanban_stage=stage,
                created_at=datetime(2099, 1, 1))
    db.add(lead); db.commit()
    return lead


class TestKanbanStageSync:
    def test_mover_a_won_marca_convertido(self, db):
        from app.services.kanban_service import kanban_service
        lead = _mk_lead(db, "web-kb-1", status="active", stage="new")
        kanban_service.update_lead_stage(db, lead.id, "won")
        db.refresh(lead)
        assert lead.kanban_stage == "won"
        assert lead.status == "converted"

    def test_mover_a_lost_marca_inactivo(self, db):
        from app.services.kanban_service import kanban_service
        lead = _mk_lead(db, "web-kb-2", status="active", stage="contacted")
        kanban_service.update_lead_stage(db, lead.id, "lost")
        db.refresh(lead)
        assert lead.kanban_stage == "lost"
        assert lead.status == "inactive"

    def test_volver_a_contacted_reactiva(self, db):
        from app.services.kanban_service import kanban_service
        lead = _mk_lead(db, "web-kb-3", status="converted", stage="won")
        kanban_service.update_lead_stage(db, lead.id, "contacted")
        db.refresh(lead)
        assert lead.kanban_stage == "contacted"
        assert lead.status == "active"

    def test_etapa_invalida_no_rompe_datos(self, db):
        from app.services.kanban_service import kanban_service
        lead = _mk_lead(db, "web-kb-4", status="active", stage="new")
        with pytest.raises(ValueError):
            kanban_service.update_lead_stage(db, lead.id, "papas")
        db.refresh(lead)
        assert lead.kanban_stage == "new"  # sin cambios
        assert lead.status == "active"


class TestKanbanCardFields:
    def test_card_expone_channel_y_whatsapp(self, db):
        from app.models.lead import Lead
        from app.services.kanban_service import kanban_service
        from datetime import datetime
        db.add(Lead(session_id="wa_5491150000098", name="WA Lead", phone="+5491150000098",
                    lead_type="CALIENTE", interest_score=8, status="active",
                    kanban_stage="new", channel="whatsapp", created_at=datetime(2099, 1, 1)))
        db.commit()
        card = kanban_service._format_lead_card(
            db.query(Lead).filter(Lead.session_id == "wa_5491150000098").first()
        )
        assert card["channel"] == "whatsapp"
        assert card["whatsapp_linked"] is True
