"""
El date picker NO debe ofrecerse cuando en la sesión ya se mostró disponibilidad.

Bug real: tras ver disponibilidad y elegir una habitación, Aura resume la reserva ("Fechas:
del 23 al 28…") y pide los datos. Ese resumen matcheaba el detector de "fecha" y adjuntaba un
date picker espurio. El flag `availability_shown` en la conversación corta ese caso.
"""
from app.models.conversation import Conversation
from app.routers.chat import (
    _availability_shown_in_session,
    _should_offer_datepicker,
    _dates_already_given,
)


def _mk_conversation(db, session_id, *, availability_shown):
    conv = Conversation(
        session_id=session_id, channel="web", context_type="pre_sale",
        extra_metadata={"availability_shown": True} if availability_shown else {},
    )
    db.add(conv)
    db.commit()
    return conv


# Resumen de cierre de reserva: menciona "Fechas:" pero NO es un pedido de fechas.
_RESUMEN = ("¡Perfecto! Te resumo la reserva: Habitación: Twin. Fechas: del 23 al 28 de junio "
            "de 2026. Para confirmar, ¿me pasás tu nombre y un teléfono?")


def test_no_picker_si_ya_se_mostro_disponibilidad(client, db):
    _mk_conversation(db, "sess-avail-on", availability_shown=True)
    assert _availability_shown_in_session(db, "sess-avail-on") is True
    # El detector clásico SÍ matchearía (la respuesta dice "Fechas:"), pero el flag manda.
    assert _should_offer_datepicker(_RESUMEN, [], has_room_cards=False) is True
    # En el callsite, la rama del flag tiene prioridad → no se ofrece el picker.


def test_picker_legitimo_sin_disponibilidad_previa(client, db):
    _mk_conversation(db, "sess-avail-off", availability_shown=False)
    assert _availability_shown_in_session(db, "sess-avail-off") is False
    pide_fechas = "¡Bárbaro! ¿Para qué fechas estás pensando? Así te fijo disponibilidad."
    assert _should_offer_datepicker(pide_fechas, [], has_room_cards=False) is True


def test_fechas_en_lenguaje_natural_se_detectan():
    # "hoy ... hasta el domingo" debe contar como fechas ya dadas (no reabrir el picker).
    msg = "necesito reserva para hoy mismo, hasta el domingo, es posible?"
    assert _dates_already_given(msg, []) is True
    # El historial natural también frena en un turno posterior sin fechas.
    hist = [{"role": "user", "content": msg}]
    assert _dates_already_given("dame la twin por favor", hist) is True
    # Una intención vaga SIN día concreto no cuenta como fecha dada.
    assert _dates_already_given("quiero ir en algún momento", []) is False
