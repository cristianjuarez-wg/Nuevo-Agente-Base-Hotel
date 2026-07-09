"""
Fase 0.1 — PARIDAD del baseline de reglas (base_blocks).

Regla de trabajo 3 del plan: todo texto de regla que se MUEVE a un bloque compartido
debe quedar byte-idéntico al histórico. Los sha256 de abajo se capturaron del código
ORIGINAL (antes de mover nada); las constantes de base_blocks deben hashear igual.

Además: cada prompt contiene sus bloques asignados EXACTAMENTE una vez (sin duplicar
la regla compartida), y las reglas NUEVAS aparecen en los agentes que antes no las
tenían (contains-tests). Deterministas, sin LLM.
"""
import hashlib

from app.prompts.base_blocks import (
    HONESTIDAD_BLOCK,
    ANTI_INVENCION_PERSONAS_BLOCK,
    DATOS_BANCARIOS_BLOCK,
    alergias_block,
    limite_dominio_block,
    build_team_roster_block,
)
from app.prompts.generation_prompts import CASUAL_RESPONSE_SYSTEM
from app.prompts.tool_agent_prompts import TOOL_AGENT_SYSTEM
from app.prompts.postsale_tool_prompts import POSTSALE_TOOL_SYSTEM
from app.prompts.owner_prompts import OWNER_AGENT_SYSTEM
from app.prompts.staff_tool_prompts import STAFF_AGENT_SYSTEM


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# sha256 del texto HISTÓRICO exacto (capturado del código original pre-refactor).
SNAPSHOTS = {
    "anti_invencion": "6522c3a6d1b90ed1752bbb48c70a75672a97b2c5d0402e23a010d6a6e991ad6d",  # len=695
    "alergias_regla10": "8eb4fab4258cf67d3682b720fbfa250c965cb35d015d3a15d210b65ede442495",  # len=684
    "bancarios_pre": "7404f3014be668fee79d35fbb84e80b8105259ca234361e6b88fd9604d42d85d",  # len=200
    "limite_casual": "8ce8daa280bcf3e1bebcc1871a54f1c3fe548d2b03617f6c5722cd8b1e699c30",  # len=332
    "limite_pre": "ee0d96387071cbce2300098241c6689fab66044123f591a1a98cedd4f8fd3ee4",  # len=544
    "limite_owner": "343f15f5f7c065cd8364417b0182e3fd2b648f84ca69ef14da3e5905676e4b20",  # len=211
}


# ---------------------------------------------------------------------------
# 1. PARIDAD BYTE A BYTE del texto movido
# ---------------------------------------------------------------------------

def test_anti_invencion_es_el_texto_historico():
    assert _sha(ANTI_INVENCION_PERSONAS_BLOCK) == SNAPSHOTS["anti_invencion"]


def test_alergias_preventa_es_la_regla_10_historica():
    assert _sha(alergias_block("guardar_preferencia")) == SNAPSHOTS["alergias_regla10"]


def test_bancarios_es_el_texto_historico_de_preventa():
    assert _sha(DATOS_BANCARIOS_BLOCK) == SNAPSHOTS["bancarios_pre"]


def test_limites_movidos_son_los_historicos():
    assert _sha(limite_dominio_block("casual")) == SNAPSHOTS["limite_casual"]
    assert _sha(limite_dominio_block("preventa")) == SNAPSHOTS["limite_pre"]
    assert _sha(limite_dominio_block("owner")) == SNAPSHOTS["limite_owner"]


# ---------------------------------------------------------------------------
# 2. INYECCIÓN por matriz (cada bloque presente EXACTAMENTE una vez donde toca)
# ---------------------------------------------------------------------------

def test_casual_tiene_sus_bloques():
    assert CASUAL_RESPONSE_SYSTEM.count(ANTI_INVENCION_PERSONAS_BLOCK) == 1
    assert CASUAL_RESPONSE_SYSTEM.count(HONESTIDAD_BLOCK) == 1
    assert CASUAL_RESPONSE_SYSTEM.count(limite_dominio_block("casual")) == 1
    assert "{team_block}" in CASUAL_RESPONSE_SYSTEM


def test_preventa_tiene_sus_bloques():
    assert TOOL_AGENT_SYSTEM.count(HONESTIDAD_BLOCK) == 1
    assert TOOL_AGENT_SYSTEM.count(ANTI_INVENCION_PERSONAS_BLOCK) == 1  # NUEVA acá
    assert "{team_block}" in TOOL_AGENT_SYSTEM                          # roster runtime
    assert TOOL_AGENT_SYSTEM.count(DATOS_BANCARIOS_BLOCK) == 1
    assert TOOL_AGENT_SYSTEM.count(alergias_block("guardar_preferencia")) == 1
    assert TOOL_AGENT_SYSTEM.count(limite_dominio_block("preventa")) == 1


def test_postventa_tiene_sus_bloques():
    assert POSTSALE_TOOL_SYSTEM.count(HONESTIDAD_BLOCK) == 1            # NUEVA acá
    assert POSTSALE_TOOL_SYSTEM.count(ANTI_INVENCION_PERSONAS_BLOCK) == 1  # NUEVA acá
    assert "{team_block}" in POSTSALE_TOOL_SYSTEM
    assert POSTSALE_TOOL_SYSTEM.count(DATOS_BANCARIOS_BLOCK) == 1       # upgrade deliberado
    # La versión abreviada vieja ya no existe (una sola fuente del texto).
    assert "Devuelve los datos EXACTOS; NUNCA" not in POSTSALE_TOOL_SYSTEM
    assert POSTSALE_TOOL_SYSTEM.count(alergias_block("registrar_preferencia")) == 1  # NUEVA acá
    assert POSTSALE_TOOL_SYSTEM.count(limite_dominio_block("postventa")) == 1        # NUEVA acá


def test_staff_tiene_sus_bloques():
    assert STAFF_AGENT_SYSTEM.count(HONESTIDAD_BLOCK) == 1              # NUEVA acá
    assert STAFF_AGENT_SYSTEM.count(limite_dominio_block("staff")) == 1  # NUEVA (hueco #7)


def test_owner_conserva_su_regla_propia():
    # El owner mantiene su REGLA DE HONESTIDAD enriquecida (superset de BI):
    # NO se le inyecta el bloque genérico para no duplicar contenido.
    assert "REGLA DE HONESTIDAD" in OWNER_AGENT_SYSTEM
    assert HONESTIDAD_BLOCK not in OWNER_AGENT_SYSTEM
    assert OWNER_AGENT_SYSTEM.count(limite_dominio_block("owner")) == 1


# ---------------------------------------------------------------------------
# 3. ROSTER del equipo (runtime, desde StaffMember)
# ---------------------------------------------------------------------------

def test_team_roster_desde_db(db):
    from app.models.staff import StaffMember
    m = StaffMember(name="Test Roster Uno", phone="+5490000000001",
                    role="staff", area="recepcion", active=True)
    db.add(m)
    db.commit()
    try:
        roster = build_team_roster_block(db)
        assert "Test Roster Uno" in roster
        assert "recepción" in roster
        assert roster.startswith("EQUIPO DEL HOTEL")
    finally:
        db.delete(m)
        db.commit()


def test_agent_service_delega_en_base_blocks(db):
    """agent_service._build_team_roster_block sigue funcionando (delegación)."""
    from app.services.agent_service import agent_service
    # Sin staff sembrado por este test: solo verificamos que no rompe y devuelve str.
    assert isinstance(agent_service._build_team_roster_block(db), str)
