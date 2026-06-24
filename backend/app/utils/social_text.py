"""
Detección de mensajes SOCIALES PUROS (agradecimiento / despedida) para el chat del agente.

Un "social puro" es un cierre amable sin otra intención: "gracias", "chau", "nada más,
graciasss", "muchas gracias!". NO es social si además trae una consulta o un código de
reserva. Se usa para que una despedida NO caiga en el gate de post-venta (que pediría el
código HTL): el agente debe cerrar cálido, no re-pedir datos.

Conservador a propósito: ante la duda (queda alguna palabra que no es relleno ni social),
devuelve False — preferimos no desviar una consulta real que arriesgar una despedida mal
clasificada (de eso se encarga la red final del gate).
"""
import re
import unicodedata

# Núcleo de palabras sociales (saludos + despedidas + gracias), ya normalizadas (sin tildes).
_SOCIAL_WORDS = {
    "gracias", "chau", "adios", "hola", "buenas", "saludos", "abrazo", "exito",
    "placer", "amable", "genia", "genio", "crack", "hi", "hello", "hey", "bye",
    "dia", "dias", "tardes", "noches", "luego", "pronto", "vista", "vemos",
}

# Rellenos que no agregan intención (se ignoran al evaluar).
_FILLER = {
    "nada", "mas", "y", "todo", "muy", "muchas", "muchisimas", "che", "ok", "okey",
    "dale", "buenisimo", "barbaro", "genial", "perfecto", "joya", "listo", "dema",
    "demas", "dios", "que", "te", "lo", "la", "un", "una", "para", "gracia", "fue",
    "hasta", "buen", "buenos",
}


def _normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    # Colapsar letras repetidas 3+ veces ("graciasss"→"gracias", "holaaa"→"hola").
    return re.sub(r"(.)\1{2,}", r"\1", t)


def is_pure_social(message: str) -> bool:
    """True si el mensaje es SOLO agradecimiento/despedida (sin otra intención ni código)."""
    t = _normalize(message)
    if not t:
        return False
    tokens = [w for w in t.split() if w]
    if not tokens:
        return False
    core = [w for w in tokens if w not in _FILLER]
    if not core:
        # Solo rellenos (ej. "nada mas", "ok dale"): cierre social.
        return True
    return all(w in _SOCIAL_WORDS for w in core)
