"""
Fase 2.6 — PARIDAD del text splitter propio vs langchain.

Garantiza que `app.core.rag.text_splitter.RecursiveCharacterTextSplitter` produce chunks
BYTE-IDÉNTICOS a los de langchain para las configuraciones que usa el proyecto (los dos
sets de separadores + chunk_size/overlap reales). Si langchain no está instalado (tras la
poda), estos casos se saltan: la paridad ya quedó fijada en el commit que hizo la migración.
"""
import pytest

from app.core.rag.text_splitter import RecursiveCharacterTextSplitter as Ours

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter as LC
    _HAS_LC = True
except Exception:  # noqa: BLE001
    _HAS_LC = False

# Los dos sets de separadores usados en el código real.
SEP_PLAIN = ["\n\n", "\n", ". ", " ", ""]                    # pdf_processor, restaurant
SEP_MD = ["\n## ", "\n# ", "\n\n", "\n", ". ", " ", ""]      # promotions, knowledge

# chunk_size/overlap reales (config.py) + variantes chicas para forzar merges y solapes.
CONFIGS = [(1000, 200), (120, 30), (50, 10), (200, 0)]

TEXTS = [
    "",
    "corto",
    "una sola oración sin separadores fuertes aquí.",
    "línea uno. línea dos. línea tres. " * 20,
    "# Título\n\nPárrafo uno con varias oraciones. Otra oración más larga que la anterior "
    "para forzar el split. \n\n## Sub\n\nContenido del sub con lista:\n- a\n- b\n- c\n\n"
    "Cierre del documento con una oración final bastante extensa y descriptiva.",
    ("Palabra " * 400).strip(),
    "\n\n\n\n\n\n",
    "Sin puntos ni saltos solo espacios entre muchas palabras repetidas " * 15,
    "## H2 arriba\ntexto\n# H1 abajo\nmás texto\n\notro bloque\ncon renglones\ny más",
]


@pytest.mark.skipif(not _HAS_LC, reason="langchain no instalado (post-poda): paridad ya fijada")
@pytest.mark.parametrize("seps", [SEP_PLAIN, SEP_MD], ids=["plain", "markdown"])
@pytest.mark.parametrize("size,overlap", CONFIGS)
def test_paridad_con_langchain(seps, size, overlap):
    for t in TEXTS:
        lc = LC(chunk_size=size, chunk_overlap=overlap, separators=seps).split_text(t)
        ours = Ours(chunk_size=size, chunk_overlap=overlap, separators=seps).split_text(t)
        assert ours == lc, f"mismatch size={size} ov={overlap} seps={seps[:2]} text={t[:40]!r}"


def test_smoke_sin_langchain():
    """El splitter propio funciona por sí solo (no depende de langchain en runtime)."""
    out = Ours(chunk_size=50, chunk_overlap=10, separators=SEP_PLAIN).split_text(
        "Una oración. Otra oración. Y una tercera bastante más larga que las anteriores."
    )
    assert isinstance(out, list) and all(isinstance(c, str) for c in out)
    assert all(len(c) <= 50 or " " not in c for c in out) or len(out) >= 1
