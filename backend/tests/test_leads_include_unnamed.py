"""
Test del filtro de leads "crudos": get_active_leads(include_unnamed) decide si se
incluyen los leads con teléfono pero SIN nombre (ej. un número de WhatsApp que consultó
antes de reservar). Por defecto se ocultan (vista de calificados).

Nota: get_active_leads abre su propia SessionLocal (no usa el fixture db). Sembramos con
la misma SessionLocal para que vean los mismos datos.
"""
import pytest


def _mk_lead(session, session_id, name, phone, status="active"):
    from app.models.lead import Lead
    lead = Lead(session_id=session_id, name=name, phone=phone,
                lead_type="FRIO", interest_score=1, status=status)
    session.add(lead)
    session.commit()
    return lead


class TestIncludeUnnamed:
    def test_default_oculta_leads_sin_nombre(self, db):
        from app.models.database import SessionLocal
        from app.services.lead_service import lead_service

        # session_id propios de este test: el :memory: se comparte entre tests (StaticPool),
        # así que no asumimos BD limpia — filtramos SOLO los leads que sembramos acá.
        NAMED, CRUDO = "web-named-1", "wa_5491150000011"
        s = SessionLocal()
        try:
            _mk_lead(s, NAMED, "Juan Pérez", "+5491150000010")
            _mk_lead(s, CRUDO, None, "+5491150000011")  # crudo (WhatsApp)
        finally:
            s.close()

        mios = {NAMED, CRUDO}
        activos = [l for l in lead_service.get_active_leads(include_unnamed=False)
                   if l.get("session_id") in mios]
        session_ids = {l.get("session_id") for l in activos}
        # El lead con nombre aparece; el crudo (sin nombre) queda oculto por defecto.
        assert NAMED in session_ids, "el lead con nombre debe aparecer"
        assert CRUDO not in session_ids, "por defecto no deben aparecer leads sin nombre"

    def test_include_unnamed_suma_los_crudos(self, db):
        from app.models.database import SessionLocal
        from app.services.lead_service import lead_service

        s = SessionLocal()
        try:
            _mk_lead(s, "wa_5491150000022", None, "+5491150000022")  # crudo
        finally:
            s.close()

        leads = lead_service.get_active_leads(include_unnamed=True)
        # Debe aparecer al menos un lead sin nombre pero con teléfono.
        crudos = [
            l for l in leads
            if not (l.get("contact_info") or {}).get("name")
            and (l.get("contact_info") or {}).get("phone")
        ]
        assert crudos, "con include_unnamed=True deben aparecer los leads crudos (tel sin nombre)"
