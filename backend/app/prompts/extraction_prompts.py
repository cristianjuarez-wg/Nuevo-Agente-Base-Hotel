"""
Prompts para extracción de información de mensajes del usuario.
"""

EXTRACT_QUERY_FROM_GREETING = """\
Analiza el siguiente mensaje que contiene un saludo y una consulta.

Mensaje: "{message}"

Extrae SOLO la parte de la consulta, eliminando el saludo.

Ejemplos:
- "hola, quiero viajar a Perú" → "quiero viajar a Perú"
- "buenas! vi una promo de un viaje por perú" → "vi una promo de un viaje por perú"
- "buenos días, busco cruceros" → "busco cruceros"
- "hi! I'm looking for trips to Europe" → "I'm looking for trips to Europe"
- "hola" → "NO_QUERY"

Si NO hay consulta (solo saludo), responde: "NO_QUERY"

Responde SOLO con la consulta extraída:"""
