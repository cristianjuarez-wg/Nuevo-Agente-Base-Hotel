"""
Fase 1.5 — persist_preferences captura las 5 categorías (antes solo alergia/dieta).

Arregla los campos "muertos": el bloque del agente leía family/services_used/notes pero nada los
escribía. Ahora guardar_preferencia (vía persist_preferences) los persiste según el `tipo` hint.
"""
from app.models.contact import Contact
from app.services.hotel_tools_pkg._shared import persist_preferences
from app.services import contact_service


def _contact(db, phone):
    c = Contact(full_name="Pref Cap", first_name="Pref", phone_number=phone)
    db.add(c); db.commit(); db.refresh(c)
    return c


def test_alergia_y_dieta_siguen_funcionando(db):
    c = _contact(db, "+5491990001001")
    ag = persist_preferences(db, c, ["maní"], "alergia")
    assert ag.get("allergies") == ["maní"]
    ag = persist_preferences(db, c, ["vegetariano"], "dieta")
    assert ag.get("dietary") == ["vegetariano"]
    prefs = contact_service.contact_service.get_guest_profile(c.id, db)["preferences"]
    assert "maní" in prefs["allergies"] and "vegetariano" in prefs["dietary"]


def test_acompanante_se_guarda_como_family(db):
    c = _contact(db, "+5491990001002")
    ag = persist_preferences(db, c, ["Tomás (hijo)"], "acompañante")
    assert ag.get("family") == ["Tomás (hijo)"]
    prefs = contact_service.contact_service.get_guest_profile(c.id, db)["preferences"]
    assert prefs["family"] == [{"name": "Tomás (hijo)"}]  # forma que espera el render


def test_servicio_y_nota(db):
    c = _contact(db, "+5491990001003")
    persist_preferences(db, c, ["spa"], "servicio")
    persist_preferences(db, c, ["prefiere pisos altos"], "nota")
    prefs = contact_service.contact_service.get_guest_profile(c.id, db)["preferences"]
    assert "spa" in prefs["services_used"]
    assert "prefiere pisos altos" in prefs["notes"]


def test_no_duplica(db):
    c = _contact(db, "+5491990001004")
    persist_preferences(db, c, ["spa"], "servicio")
    ag = persist_preferences(db, c, ["spa"], "servicio")  # repetido
    assert not ag.get("services_used")  # no se agregó de nuevo
    prefs = contact_service.contact_service.get_guest_profile(c.id, db)["preferences"]
    assert prefs["services_used"].count("spa") == 1


def test_sin_hint_cae_a_dieta_o_alergia(db):
    """Sin tipo, el comportamiento histórico se mantiene: comida → alergia/dieta, nunca family."""
    c = _contact(db, "+5491990001005")
    ag = persist_preferences(db, c, ["sin gluten"], None)
    assert "dietary" in ag or "allergies" in ag
    assert "family" not in ag and "services_used" not in ag


def test_family_y_servicio_llegan_al_bloque_del_agente(db):
    """Cierre del bug: lo que se guarda ahora SÍ aparece en el bloque que ve el agente."""
    from app.services import guest_context_service
    c = _contact(db, "+5491990001006")
    persist_preferences(db, c, ["Tomás"], "acompañante")
    persist_preferences(db, c, ["spa"], "servicio")
    block = guest_context_service.build_guest_context("guest", c.id, db)
    assert "Suele viajar con: Tomás" in block
    assert "Servicios que suele usar: spa" in block
