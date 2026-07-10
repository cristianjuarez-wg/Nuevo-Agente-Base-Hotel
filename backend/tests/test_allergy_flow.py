"""
Tests del flujo de ALERGIAS / DIETAS del huésped (seguridad alimentaria).

Regresión del bug: una alergia del huésped existía en el perfil pero el agente
respondía "no tengo información de alergias". Causa: el dato estaba guardado bajo
`preferences.dietary` en vez de `preferences.allergies`, y el bloque de contexto del
agente (y la regla de seguridad) leen SOLO `allergies`.

Estos tests son deterministas y no llaman a OpenAI. Cubren las tres capas donde el
dato puede perderse:
  1. Clasificación dieta vs alergia (`_clasificar_preferencia`).
  2. Separación en el seed demo (`_split_prefs`) — el origen del bug.
  3. Render del bloque de contexto que ve el agente (`build_guest_profile_block`):
     la alergia debe caer en la sección ⚠️ CRÍTICA y disparar la regla de seguridad.
"""
import pytest


# ---------------------------------------------------------------------------
# 1. Clasificación dieta vs alergia (lógica viva, reutilizada por el seed)
# ---------------------------------------------------------------------------
class TestClasificarPreferencia:
    def _clasificar(self, texto, hint=None):
        from app.services.hotel_tools import _clasificar_preferencia
        return _clasificar_preferencia(texto, hint)

    @pytest.mark.parametrize("texto", [
        "alergia_frutos_secos",
        "alergia al maní",
        "soy alérgico a los mariscos",
        "intolerancia a la lactosa",
        "riesgo de anafilaxia con el huevo",
    ])
    def test_alergias_clasifican_como_allergies(self, texto):
        assert self._clasificar(texto) == "allergies"

    @pytest.mark.parametrize("texto", [
        "vegetariano",
        "vegano",
        "sin_tacc",
        "sin lactosa",
    ])
    def test_dietas_clasifican_como_dietary(self, texto):
        assert self._clasificar(texto) == "dietary"

    def test_hint_explicito_gana_sobre_texto(self):
        # El agente puede forzar el tipo aunque el texto sea ambiguo.
        assert self._clasificar("frutos secos", hint="alergia") == "allergies"
        assert self._clasificar("algo raro", hint="dieta") == "dietary"


# ---------------------------------------------------------------------------
# 2. Separación en el seed demo (`_split_prefs`) — el origen exacto del bug
# ---------------------------------------------------------------------------
class TestSplitPrefs:
    def _split(self, items):
        from app.services.demo_data_service import _split_prefs
        return _split_prefs(items)

    def test_alergia_va_a_allergies_sin_prefijo(self):
        # Regresión directa: 'alergia_frutos_secos' debe quedar en allergies y
        # SIN el prefijo 'alergia_' (alérgeno limpio).
        out = self._split(["alergia_frutos_secos"])
        assert out == {"allergies": ["frutos_secos"]}
        assert "dietary" not in out  # NO debe quedar como dieta (el bug original)

    def test_dieta_va_a_dietary(self):
        out = self._split(["vegetariano", "sin_tacc"])
        assert out == {"dietary": ["vegetariano", "sin_tacc"]}
        assert "allergies" not in out

    def test_mezcla_se_separa_correctamente(self):
        out = self._split(["alergia_mariscos", "vegetariano"])
        assert out["allergies"] == ["mariscos"]
        assert out["dietary"] == ["vegetariano"]


# ---------------------------------------------------------------------------
# 3. Bloque de contexto del agente — donde el bug se manifestaba
# ---------------------------------------------------------------------------
class TestGuestProfileBlock:
    def _build(self, preferences):
        from app.domains.hotel.prompts.context_blocks import build_guest_profile_block
        # Estructura real de contact_service.get_guest_profile(): el nombre va en
        # `contact`, y se necesita al menos un dato (estadía/preferencia) para que el
        # bloque se renderice (si no hay nada útil devuelve "").
        profile = {
            "contact": {"first_name": "Huésped Test"},
            "is_staying_now": True,
            "active_stay": {"code": "HTL-TEST", "room_type": "King"},
            "preferences": preferences,
        }
        return build_guest_profile_block(profile)

    def test_alergia_aparece_en_seccion_critica(self):
        block = self._build({"allergies": ["frutos_secos"], "dietary": ["vegetariano"]})
        # La alergia debe estar marcada como CRÍTICA / seguridad alimentaria.
        assert "ALERGIAS" in block.upper()
        assert "frutos_secos" in block
        assert "CRÍTICO" in block or "CRITICO" in block.upper()
        # Y debe dispararse la regla de seguridad alimentaria.
        assert "SEGURIDAD ALIMENTARIA" in block.upper()

    def test_dieta_no_dispara_regla_de_seguridad(self):
        # Una dieta sola NO debe activar la advertencia crítica de alergias.
        block = self._build({"dietary": ["vegetariano"]})
        assert "vegetariano" in block
        assert "SEGURIDAD ALIMENTARIA" not in block.upper()

    def test_alergia_mal_archivada_como_dieta_es_el_bug(self):
        # Documenta el bug original: si la alergia se guarda en `dietary`, el bloque
        # NO la trata como alergia crítica. Por eso el fix está en el seed/clasificación.
        block = self._build({"dietary": ["alergia_frutos_secos"]})
        assert "SEGURIDAD ALIMENTARIA" not in block.upper()

    def test_sin_preferencias_no_rompe(self):
        block = self._build({})
        assert isinstance(block, str) and len(block) > 0
