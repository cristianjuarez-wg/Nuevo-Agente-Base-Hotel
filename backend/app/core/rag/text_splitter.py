"""
Text splitter propio — reemplazo de langchain_text_splitters (Fase 2.6, poda de deps).

Reimplementa `RecursiveCharacterTextSplitter` de langchain con paridad EXACTA para la
configuración que usa el proyecto: `keep_separator=True`, `length_function=len`,
`strip_whitespace=True`, separadores LITERALES (no regex). El algoritmo (recursión por
separadores + merge con solape) está portado 1:1 de langchain_text_splitters
(base.py `_merge_splits`/`_join_docs` + character.py `_split_text`) para que los chunks
—y por ende los embeddings del RAG— sean byte-idénticos a los que generaba antes.

Verificado contra langchain en tests/test_text_splitter_parity.py.
"""
from __future__ import annotations

import re
from typing import Callable, List, Optional


def _split_text_with_regex_keep(text: str, separator: str) -> List[str]:
    """Split conservando el separador al INICIO de cada trozo (keep_separator=True).

    Portado de langchain_text_splitters.character._split_text_with_regex con
    keep_separator=True (rama por defecto, equivalente a "start").
    """
    if separator:
        # Los paréntesis capturan el delimitador para no perderlo en el resultado.
        _splits = re.split(f"({separator})", text)
        splits = [_splits[i] + _splits[i + 1] for i in range(1, len(_splits), 2)]
        if len(_splits) % 2 == 0:
            splits += _splits[-1:]
        splits = [_splits[0], *splits]
    else:
        splits = list(text)
    return [s for s in splits if s != ""]


class RecursiveCharacterTextSplitter:
    """Divide texto recursivamente probando una lista de separadores.

    Subset compatible con langchain para uso `split_text` con separadores literales.
    """

    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None,
        length_function: Callable[[str], int] = len,
        strip_whitespace: bool = True,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
        if chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be >= 0, got {chunk_overlap}")
        if chunk_overlap > chunk_size:
            raise ValueError(
                f"Got a larger chunk overlap ({chunk_overlap}) than chunk size "
                f"({chunk_size}), should be smaller."
            )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or ["\n\n", "\n", " ", ""]
        self._length_function = length_function
        self._strip_whitespace = strip_whitespace

    # ── merge (portado de base.TextSplitter) ─────────────────────────────────
    def _join_docs(self, docs: List[str], separator: str) -> Optional[str]:
        text = separator.join(docs)
        if self._strip_whitespace:
            text = text.strip()
        if text == "":
            return None
        return text

    def _merge_splits(self, splits, separator: str) -> List[str]:
        separator_len = self._length_function(separator)
        docs: List[str] = []
        current_doc: List[str] = []
        total = 0
        for d in splits:
            _len = self._length_function(d)
            if total + _len + (separator_len if len(current_doc) > 0 else 0) > self._chunk_size:
                if len(current_doc) > 0:
                    doc = self._join_docs(current_doc, separator)
                    if doc is not None:
                        docs.append(doc)
                    # Popear del inicio hasta respetar el solape / tamaño.
                    while total > self._chunk_overlap or (
                        total + _len + (separator_len if len(current_doc) > 0 else 0) > self._chunk_size
                        and total > 0
                    ):
                        total -= self._length_function(current_doc[0]) + (
                            separator_len if len(current_doc) > 1 else 0
                        )
                        current_doc = current_doc[1:]
            current_doc.append(d)
            total += _len + (separator_len if len(current_doc) > 1 else 0)
        doc = self._join_docs(current_doc, separator)
        if doc is not None:
            docs.append(doc)
        return docs

    # ── recursión por separadores (portado de character.RecursiveCharacterTextSplitter) ──
    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators: List[str] = []
        for i, _s in enumerate(separators):
            _sep_re = re.escape(_s)
            if _s == "":
                separator = _s
                break
            if re.search(_sep_re, text):
                separator = _s
                new_separators = separators[i + 1:]
                break

        _sep_re = re.escape(separator)
        splits = _split_text_with_regex_keep(text, _sep_re)

        _good_splits: List[str] = []
        # keep_separator=True → el separador ya viene incrustado en cada trozo; se une con "".
        _merge_sep = ""
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    final_chunks.extend(self._merge_splits(_good_splits, _merge_sep))
                    _good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    final_chunks.extend(self._split_text(s, new_separators))
        if _good_splits:
            final_chunks.extend(self._merge_splits(_good_splits, _merge_sep))
        return final_chunks

    def split_text(self, text: str) -> List[str]:
        return self._split_text(text, self._separators)
