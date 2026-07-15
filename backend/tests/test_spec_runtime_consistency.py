"""
Red de seguridad contra la clase de bug que reincidió 2 veces (auditoría arquitectónica):
una tool presente en el `_TOOLS` del orquestador pero AUSENTE en `spec.tools` (o al revés).

- Post-venta / owner / staff resuelven sus tools DESDE la spec (`resolve_tools(spec.tools)`),
  así que una omisión en la spec quita la tool en runtime → bug de comportamiento (fue el caso
  de `postsale.derivar_a_humano`).
- Pre-venta usa `tools_override=_TOOLS`, así que su spec no se lee en runtime; una divergencia
  no cambia el comportamiento pero HACE MENTIR a la spec (base de agent_capabilities) — fue el
  caso de `presale.derivar_a_humano`.

Este test cruza `spec.tools` contra el `_TOOLS` real de cada módulo. Importa los orquestadores
para que registren sus tools (`register_tool` corre como side-effect del import).
"""
# Importar los orquestadores registra las tools (prefijo <rol>.<fn>) en el tool_registry.
import app.services.hotel_sdk_orchestrator as presale_mod  # noqa: F401
import app.services.hotel_postsale_orchestrator as postsale_mod  # noqa: F401
import app.services.owner_orchestrator as owner_mod  # noqa: F401
import app.services.staff_orchestrator as staff_mod  # noqa: F401

from app.domains.hotel.agent_specs import SPECS


def _keys(prefix, tools_list):
    """Conjunto de keys 'prefijo.<fn.name>' a partir de una lista de function-tools."""
    return {f"{prefix}.{t.name}" for t in tools_list}


def test_presale_spec_coincide_con_TOOLS():
    # Pre-venta usa tools_override=_TOOLS: la spec DEBE reflejar exactamente ese conjunto,
    # aunque en runtime mande el override (si no, la spec miente — base de las capacidades).
    assert set(SPECS["hotel_presale"].tools) == _keys("presale", presale_mod._TOOLS)


def test_postsale_spec_coincide_con_TOOLS():
    # Post-venta resuelve DESDE la spec: una divergencia acá es bug de comportamiento real.
    assert set(SPECS["hotel_postsale"].tools) == _keys("postsale", postsale_mod._TOOLS)


def test_owner_spec_coincide_con_TOOLS():
    assert set(SPECS["hotel_owner"].tools) == _keys("owner", owner_mod._TOOLS)


def test_staff_spec_coincide_con_TOOLS():
    assert set(SPECS["hotel_staff"].tools) == _keys("staff", staff_mod._TOOLS)


def test_specs_leidas_por_runtime_resuelven_sin_error():
    """post/owner/staff pasan por resolve_tools(spec.tools): debe resolver sin KeyError y
    devolver exactamente el conjunto declarado (detecta keys mal escritas o no registradas)."""
    from app.core.agents.tool_registry import resolve_tools
    for spec_key in ("hotel_postsale", "hotel_owner", "hotel_staff"):
        spec = SPECS[spec_key]
        resolved = resolve_tools(spec.tools)
        assert {t.name for t in resolved} == {k.split(".", 1)[-1] for k in spec.tools}
