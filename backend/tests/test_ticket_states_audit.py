"""
Tests de los fixes de la auditoría de coherencia (P1 y P2).

P1 — Colisión de vocabulario de estados de ticket: la columna `status` mezcla el set
base (open/in_progress/resolved/escalated) con el operativo (asignado/pre_resuelto/
resuelto). Las constantes TICKET_OPEN_STATES / TICKET_RESOLVED_STATES son la única fuente
de verdad; las métricas del dueño y la detección de post-venta deben usarlas para no
perder de vista los tickets operativos (que quedaban mal contados / duplicados).

P2 — Las escalaciones quedan sin dueño: al escalar (cancelar/reembolso/queja), el ticket
debe asignarse a un área del equipo (recepción), no solo marcarse 'escalated'.

Deterministas, sin OpenAI. Usan el fixture `db` en memoria del conftest.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# P1 — Constantes de estado: cubren AMBOS vocabularios
# ---------------------------------------------------------------------------
class TestTicketStateConstants:
    def test_open_states_incluye_operativos(self):
        from app.models.hotel import TICKET_OPEN_STATES
        # Base + operativo: un ticket asignado/pre_resuelto sigue "abierto" (activo).
        for s in ("open", "in_progress", "escalated", "asignado", "pre_resuelto"):
            assert s in TICKET_OPEN_STATES
        assert "resuelto" not in TICKET_OPEN_STATES
        assert "resolved" not in TICKET_OPEN_STATES

    def test_resolved_states_cubre_ambos_idiomas(self):
        from app.models.hotel import TICKET_RESOLVED_STATES
        assert "resolved" in TICKET_RESOLVED_STATES   # cierre IA
        assert "resuelto" in TICKET_RESOLVED_STATES   # cierre del loop operativo


# ---------------------------------------------------------------------------
# P1 — Métricas del dueño: un ticket operativo se cuenta en el estado correcto
# ---------------------------------------------------------------------------
class TestOwnerMetricsRecognizeOperationalStates:
    _seq = 0

    def _mk_ticket(self, db, status, category="complaint", escalated=0):
        from app.models.hotel import HotelTicket
        from datetime import datetime
        TestOwnerMetricsRecognizeOperationalStates._seq += 1
        t = HotelTicket(
            ticket_number=f"HT-AUD{TestOwnerMetricsRecognizeOperationalStates._seq:05d}",
            session_id="wa_549111", subject="x", category=category,
            status=status, escalated=escalated, created_at=datetime.now(),
        )
        db.add(t); db.commit()
        return t

    def test_queja_asignada_cuenta_como_abierta_no_resuelta(self, db):
        # Una queja enrutada al staff (status 'asignado') NO debe contarse como resuelta.
        from datetime import date, timedelta
        from app.services import business_metrics
        self._mk_ticket(db, "asignado", category="complaint")
        start = date.today() - timedelta(days=1)
        end = date.today() + timedelta(days=1)
        r = business_metrics.get_complaints(db, start, end)
        assert r["total"] == 1
        assert r["open"] == 1       # antes del fix: 0 (se contaba como resuelta)
        assert r["resolved"] == 0

    def test_postsale_metrics_cuenta_resuelto_operativo(self, db):
        # Un ticket cerrado por el loop operativo ('resuelto') debe contar como auto-resuelto.
        from app.services.metrics_service import metrics_service
        before = metrics_service.get_postsale_metrics(db=db)
        self._mk_ticket(db, "resuelto", category="info", escalated=0)
        after = metrics_service.get_postsale_metrics(db=db)
        # antes del fix: +0 ('resolved' != 'resuelto'); con el fix: +1
        assert after["auto_resolved_tickets"] == before["auto_resolved_tickets"] + 1

    def test_service_request_no_duplica_en_containment(self, db):
        # Un service_request en estado 'resuelto' se cuenta como service_request, NO también
        # como auto_resolved (evita doble conteo en containment). Comparamos antes/después
        # para ser robustos a tickets de otros tests en la misma DB en memoria.
        from app.services.metrics_service import metrics_service
        before = metrics_service.get_postsale_metrics(db=db)
        self._mk_ticket(db, "resuelto", category="service_request", escalated=0)
        after = metrics_service.get_postsale_metrics(db=db)
        assert after["service_requests"] == before["service_requests"] + 1
        # El nuevo service_request NO debe sumar en auto_resolved (excluido por categoría).
        assert after["auto_resolved_tickets"] == before["auto_resolved_tickets"]


# ---------------------------------------------------------------------------
# P2 — Una escalación se asigna a un área (no queda sin dueño)
# ---------------------------------------------------------------------------
class TestEscalationGetsAssigned:
    def test_escalar_enruta_a_recepcion(self, db):
        from app.models.hotel import HotelTicket
        from app.services.hotel_postsale import HotelPostSaleService
        from datetime import datetime

        ticket = HotelTicket(
            ticket_number="HT-ESC001", session_id="wa_549111",
            subject="Cancelación", category="general", status="open",
            description="Sesión de soporte iniciada", created_at=datetime.now(),
        )
        db.add(ticket); db.commit()

        svc = HotelPostSaleService.__new__(HotelPostSaleService)
        svc.db = db

        # Mockeamos solo el ruteo/notificación al equipo (I/O del operations_service):
        # validamos que la escalación los INVOCA (no que quede solo 'escalated').
        with patch("app.services.operations_service.log_event") as m_log, \
             patch("app.services.operations_service.classify_and_assign") as m_assign, \
             patch("app.services.operations_service.notify_staff_assignment") as m_notify:
            m_assign.return_value = MagicMock(name="StaffMember")
            svc.apply_ticket_action(
                ticket, requires_escalation=True,
                response_text="Un asesor te contactará.",
                query="quiero cancelar mi reserva y que me devuelvan la plata",
                analysis={"category": "cancel", "escalation_reason": "pide cancelar",
                          "urgency_level": "alta"},
            )
            # La escalación debe enrutar al equipo y notificar (no quedar sin dueño).
            assert m_assign.called, "una escalación debe asignarse a un área del equipo"
            assert m_notify.called, "el staff debe ser notificado de la escalación"
            # Y una cancelación va a recepción.
            _, kwargs = m_assign.call_args
            assert kwargs.get("area_hint") == "recepcion"

        assert ticket.escalated == 1   # se preserva la marca de que requirió humano
