"""
Compatibilidad de parámetros entre familias de modelos (GPT-4 vs GPT-5/o1/o3).

Estos tests existen porque el fallo es SILENCIOSO en desarrollo y RUIDOSO en
producción: con GPT-5, mandar `temperature=0.3` o `max_tokens=N` devuelve 400 y
el agente no responde ningún turno. Verificado contra la API real:

    temperature=0.3 -> "Only the default (1) value is supported"
    max_tokens=50   -> "Use 'max_completion_tokens' instead"
"""
import pytest

from app.core.llm.model_compat import adapt_params, ensure_json_hint, is_restricted_family
from app.core.llm.token_pricing import cost_usd


class TestFamiliaRestringida:
    @pytest.mark.parametrize("model", [
        "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5.2",
        "gpt-5-mini-2025-08-07",   # snapshot fechado
        "gpt-5.6-luna",            # nombres futuros que aún no existen acá
        "o1-preview", "o3-mini",
    ])
    def test_detecta_restringidos(self, model):
        assert is_restricted_family(model) is True

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "gpt-4o-2024-08-06", "", None])
    def test_gpt4_y_vacios_no_restringidos(self, model):
        assert is_restricted_family(model) is False


class TestAdaptacionDeParams:
    def test_gpt5_elimina_temperature(self):
        out = adapt_params("gpt-5-mini", {"model": "gpt-5-mini", "temperature": 0.3})
        assert "temperature" not in out

    def test_gpt5_renombra_max_tokens(self):
        out = adapt_params("gpt-5-mini", {"max_tokens": 150})
        assert "max_tokens" not in out
        assert out["max_completion_tokens"] == 150

    def test_gpt5_no_pisa_max_completion_tokens_existente(self):
        out = adapt_params("gpt-5", {"max_tokens": 150, "max_completion_tokens": 999})
        assert out["max_completion_tokens"] == 999

    def test_gpt4_no_se_toca(self):
        """El camino viejo debe quedar EXACTAMENTE igual: sin regresiones."""
        params = {"model": "gpt-4o", "temperature": 0.3, "max_tokens": 150}
        assert adapt_params("gpt-4o", params) == params

    def test_no_muta_el_dict_original(self):
        params = {"temperature": 0.3, "max_tokens": 10}
        adapt_params("gpt-5", params)
        assert params == {"temperature": 0.3, "max_tokens": 10}


class TestJsonHint:
    def test_inyecta_json_si_falta(self):
        params = {
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": "extraé el nombre"}],
        }
        out = ensure_json_hint("gpt-5-mini", params)
        assert any("json" in str(m["content"]).lower() for m in out["messages"])

    def test_respeta_prompt_que_ya_dice_json(self):
        params = {
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": "devolvé un JSON con el nombre"}],
        }
        assert ensure_json_hint("gpt-5-mini", params) == params

    def test_sin_response_format_no_toca_nada(self):
        params = {"messages": [{"role": "user", "content": "hola"}]}
        assert ensure_json_hint("gpt-5-mini", params) == params


class TestPreciosGpt5:
    def test_snapshot_mini_no_cae_en_el_precio_de_gpt5(self):
        """Regresión: con match por primer prefijo, gpt-5-mini costaba 5x de más."""
        mini = cost_usd("gpt-5-mini-2025-08-07", 1_000_000, 0)
        full = cost_usd("gpt-5", 1_000_000, 0)
        assert mini == pytest.approx(0.25)
        assert mini < full

    def test_nano_es_el_mas_barato(self):
        assert cost_usd("gpt-5-nano", 1_000_000, 0) < cost_usd("gpt-5-mini", 1_000_000, 0)

    def test_modelo_desconocido_usa_fallback_conservador(self):
        """Nunca subestimar el gasto: lo desconocido se cobra como gpt-4o."""
        assert cost_usd("modelo-inexistente", 1_000_000, 0) == cost_usd("gpt-4o", 1_000_000, 0)
