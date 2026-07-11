"""
Fase 3 — naturalidad como bloque base opt-in por customer_facing.

Verifica: (a) el texto de NATURALIDAD_BLOCK no cambió (sha snapshot); (b) el placeholder está en
los templates customer_facing (pre-venta, casual, post-venta) y NO en los internos (owner, staff);
(c) el flag customer_facing de las specs es el esperado; (d) el opt-in decide el valor inyectado.
"""
import hashlib

from app.domains.hotel.prompts.generation_prompts import NATURALIDAD_BLOCK, CASUAL_RESPONSE_SYSTEM
from app.domains.hotel.prompts.tool_agent_prompts import TOOL_AGENT_SYSTEM
from app.domains.hotel.prompts.postsale_tool_prompts import POSTSALE_TOOL_SYSTEM
from app.domains.hotel.prompts.owner_prompts import OWNER_AGENT_SYSTEM
from app.domains.hotel.prompts.staff_tool_prompts import STAFF_AGENT_SYSTEM
from app.domains.hotel.agent_specs import SPECS


# sha256 del texto histórico del bloque (capturado en la Fase 3, antes de tocar nada más).
_NATURALIDAD_SHA = "b45ed66cddddb02c0f86f05da91e01825e14dfd51340399f9e2e94e4436a1d63"


def test_naturalidad_block_texto_no_cambio():
    assert hashlib.sha256(NATURALIDAD_BLOCK.encode("utf-8")).hexdigest() == _NATURALIDAD_SHA


def test_placeholder_en_customer_facing_una_vez():
    for name, tmpl in [("preventa", TOOL_AGENT_SYSTEM), ("casual", CASUAL_RESPONSE_SYSTEM),
                       ("postventa", POSTSALE_TOOL_SYSTEM)]:
        assert tmpl.count("{naturalidad_block}") == 1, f"{name} debe tener el placeholder una vez"


def test_placeholder_ausente_en_internos():
    for name, tmpl in [("owner", OWNER_AGENT_SYSTEM), ("staff", STAFF_AGENT_SYSTEM)]:
        assert "{naturalidad_block}" not in tmpl, f"{name} (interno) NO debe tener el placeholder"


def test_flags_customer_facing_esperados():
    esperado = {
        "hotel_presale": True, "hotel_postsale": True, "casual": True,
        "triage": False, "hotel_owner": False, "hotel_staff": False,
    }
    for key, val in esperado.items():
        assert SPECS[key].customer_facing is val, f"{key}.customer_facing debe ser {val}"


def test_opt_in_decide_el_valor():
    """El patrón usado en los orquestadores: NATURALIDAD_BLOCK si customer_facing, else ''."""
    def inject(spec):
        return NATURALIDAD_BLOCK if spec.customer_facing else ""
    assert inject(SPECS["hotel_presale"]) == NATURALIDAD_BLOCK
    assert inject(SPECS["hotel_postsale"]) == NATURALIDAD_BLOCK
    assert inject(SPECS["hotel_staff"]) == ""
    assert inject(SPECS["hotel_owner"]) == ""
    assert inject(SPECS["triage"]) == ""
