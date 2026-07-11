"""
Fase 1 — guest_context_service: niveles de acceso por rol + paridad del render.

Verifica que el helper único devuelve el nivel correcto por rol (guest=360, management=vacío,
staff=mínimo), que sumar el ai_summary es aditivo (paridad para huéspedes sin summary), y que
el nivel staff no filtra datos comerciales.
"""
from datetime import date, timedelta

from app.models.contact import Contact
from app.models.hotel import Room, Booking
from app.services import guest_context_service
from app.domains.hotel.prompts.context_blocks import build_guest_profile_block
from app.services.contact_service import contact_service


def _seed_guest(db, *, phone, name, ai_summary=None, past=True):
    """Crea un contacto con 1 reserva (pasada por defecto → recurrente/ya se hospedó)."""
    c = Contact(full_name=name, first_name=name.split()[0], phone_number=phone,
                ai_summary=ai_summary)
    db.add(c); db.commit(); db.refresh(c)
    room = Room(room_type="King", capacity=2, base_price_usd=120, base_price_ars=126000,
                total_units=1, status="active")
    db.add(room); db.commit(); db.refresh(room)
    if past:
        ci = date.today() - timedelta(days=30)
        co = date.today() - timedelta(days=28)
    else:
        ci = date.today() + timedelta(days=20)
        co = date.today() + timedelta(days=22)
    b = Booking(code=f"HTL-{phone[-4:]}", room_id=room.id, contact_id=c.id,
                guest_name=name, check_in=ci, check_out=co, guests=2, nights=2,
                total_price_usd=240, total_price_ars=252000, status="confirmed")
    db.add(b); db.commit()
    return c


def test_management_siempre_vacio(db):
    c = _seed_guest(db, phone="+5491880000001", name="Ana Gerencia")
    assert guest_context_service.build_guest_context("management", c.id, db) == ""


def test_guest_incluye_estadias(db):
    c = _seed_guest(db, phone="+5491880000002", name="Beto Guest")
    block = guest_context_service.build_guest_context("guest", c.id, db)
    assert block  # no vacío: tiene historial
    assert "PERFIL DEL HUÉSPED" in block
    # Ya se hospedó (reserva pasada) → el render lo refleja.
    assert "hospedó" in block or "RECURRENTE" in block


def test_guest_sin_contacto_vacio(db):
    assert guest_context_service.build_guest_context("guest", None, db) == ""


def test_ai_summary_es_aditivo_paridad(db):
    """Sin ai_summary el bloque no lo menciona; con ai_summary suma exactamente una línea."""
    c = _seed_guest(db, phone="+5491880000003", name="Caro Sinsum", ai_summary=None)
    sin = guest_context_service.build_guest_context("guest", c.id, db)
    assert "Resumen del huésped" not in sin

    # Mismo huésped, ahora con summary: el bloque debe ser el anterior + la línea del summary.
    c.ai_summary = "Viajera frecuente, prefiere pisos altos, suele reservar para 2."
    db.commit()
    con = guest_context_service.build_guest_context("guest", c.id, db)
    linea = "- Resumen del huésped (histórico): Viajera frecuente, prefiere pisos altos, suele reservar para 2."
    assert linea in con
    # Paridad: quitar exactamente la línea nueva (con su salto previo) devuelve el bloque sin summary.
    assert con.replace("\n" + linea, "") == sin


def test_staff_minimo_sin_datos_comerciales(db):
    """Staff ve nombre + habitación (+ alergias si hay), NUNCA gasto/recurrencia/consumo."""
    c = _seed_guest(db, phone="+5491880000004", name="Dario Staff")
    block = guest_context_service.build_guest_context("staff", c.id, db)
    assert "HUÉSPED DEL TICKET" in block
    assert "Dario" in block
    # NADA comercial: sin recurrencia, sin gasto, sin consumo, sin ai_summary.
    for prohibido in ("RECURRENTE", "estadías", "Suele pedir", "Resumen del huésped", "gast"):
        assert prohibido not in block, f"el nivel staff no debe exponer: {prohibido!r}"


def test_staff_incluye_alergias_seguridad(db):
    """Alergias SÍ (seguridad), aunque el resto sea comercial y se excluya."""
    c = _seed_guest(db, phone="+5491880000005", name="Eva Alergica")
    import json
    c.preferences = json.dumps({"allergies": ["maní", "mariscos"]})
    db.commit()
    block = guest_context_service.build_guest_context("staff", c.id, db)
    assert "Alergias" in block and "maní" in block


def test_render_directo_sin_summary_no_menciona_summary(db):
    """El render base no inventa la línea de summary si el contacto no lo tiene."""
    c = _seed_guest(db, phone="+5491880000006", name="Fabi NoSum")
    profile = contact_service.get_guest_profile(c.id, db)
    block = build_guest_profile_block(profile)
    assert "Resumen del huésped" not in block


def test_reserva_futura_no_sugiere_regreso(db):
    """Fase 3 (bug de tono destapado en vivo): un huésped con SOLO reserva futura NO debe recibir
    ejemplos de 'tenerte de vuelta' / 'de siempre' — aún no se hospedó."""
    c = _seed_guest(db, phone="+5491880000007", name="Nora Futura", past=False)  # única reserva futura
    block = guest_context_service.build_guest_context("guest", c.id, db)
    assert "RESERVA FUTURA" in block or "reserva futura" in block.lower()
    # Los ejemplos de "cómo saludar" NO deben fingir un regreso.
    assert "tenerte de vuelta" not in block
    assert "reservo la King de siempre" not in block  # el ejemplo AFIRMATIVO de recurrencia
    assert "PRIMERA estadía" in block  # el ejemplo correcto para quien aún no llegó


def test_huesped_pasado_si_reconoce_regreso(db):
    """Contrapartida: quien YA se hospedó sí puede recibir el ejemplo de reconocer que lo conocés."""
    c = _seed_guest(db, phone="+5491880000008", name="Omar Pasado", past=True)  # estadía pasada
    block = guest_context_service.build_guest_context("guest", c.id, db)
    assert "ya lo conocés" in block or "de siempre" in block
    assert "PRIMERA estadía" not in block
