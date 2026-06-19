"""
Prompts para clasificación de mensajes del usuario.
Todos los prompts usan f-strings para interpolación de variables en runtime.
"""

CLASSIFY_FIRST_MESSAGE = """\
Analiza el siguiente mensaje del usuario y clasifica su intención.

Mensaje: "{message}"

Clasifica como UNA de estas opciones:

1. "greeting" - Si es un saludo inicial
   Ejemplos: "hola", "hola como estas", "buenos días", "hello", "hi", "hey"

2. "farewell" - Si es una despedida
   Ejemplos: "gracias", "chau", "adiós", "bye", "hasta luego"

3. "query" - Si es una consulta o pregunta
   Ejemplos: "quiero viajar a España", "busco cruceros", "tengo una pregunta"

Responde SOLO con UNA palabra: greeting, farewell o query"""


CLASSIFY_MESSAGE_INTENT = """\
Analiza el siguiente mensaje del usuario y clasifica su intención.

Historial reciente de la conversación:
{history_str}

Mensaje actual del usuario: "{message}"

Clasifica la intención como UNA de estas opciones:

1. "followup" - Si el usuario pide más información sobre algo que ya se habló
   Ejemplos: "más detalle", "cuéntame más", "el itinerario", "qué incluye", "amplía", "desarrollá"

2. "new_query" - Si el usuario hace una consulta NUEVA sobre un destino o viaje
   Ejemplos: "quiero viajar a España", "busco cruceros", "me interesa Europa"

3. "personal_data" - Si el usuario está dando sus datos personales
   Ejemplos: "mi nombre es Juan", "mi teléfono es 123456", "juan@email.com"

4. "confirmation" - Si el usuario confirma, acepta o está de acuerdo
   Ejemplos: "si", "ok", "claro", "dale", "perfecto", "genial"

IMPORTANTE:
- Si hay historial y el mensaje es corto ("si", "ok"), probablemente sea "confirmation" o "followup"
- Si NO hay historial, un mensaje corto puede ser "new_query"

Responde SOLO con UNA palabra: followup, new_query, personal_data o confirmation"""


IS_CASUAL_CONVERSATION = """\
Analiza si el mensaje del usuario es conversación casual o consulta de viajes.

{history_section}

Mensaje actual: "{message}"

REGLAS DE CLASIFICACIÓN:

1. Es CONVERSACIÓN CASUAL si:
   - Pregunta personal al asistente (cómo estás, qué tal tu día)
   - Comentario general sin relación a viajes (hace calor, lindo día)
   - Saludo inicial sin consulta específica
   - Small talk que NO continúa una conversación de viajes
   - Pregunta completamente ajena al turismo: recetas de cocina, deportes, matemáticas, medicina, programación
   - Cualquier consulta cuyo tema principal NO sea viajes, paquetes, destinos ni reservas

2. Es CONSULTA DE VIAJES si:
   - Menciona destinos, países, ciudades
   - Pregunta sobre paquetes, precios, servicios
   - Responde a una pregunta sobre viajes (ej: "si" después de "¿te gustaría conocer más?")
   - Confirma interés en información de viajes
   - Continúa una conversación sobre destinos

IMPORTANTE - CONSIDERA EL CONTEXTO:
- Si en el historial se habló de destinos/paquetes, el mensaje actual probablemente es continuación
- Respuestas cortas ("si", "ok", "claro") en contexto de viajes = VIAJE
- Solo marca "casual" si el mensaje realmente NO tiene relación con viajes

Responde SOLO con: "casual" o "viaje" """


DETECT_POSTSALE_CONTEXT = """\
Analiza el siguiente mensaje del usuario y determina si se refiere a:
- PRE-VENTA: Usuario está buscando información para comprar un viaje (destinos, precios, opciones)
- POST-VENTA: Usuario ya compró un viaje y tiene consultas sobre su reserva

Historial reciente de la conversación:
{history_context}

Mensaje actual: "{message}"

IMPORTANTE:
- Si el usuario está viendo paquetes o pidiendo información de destinos → PRE-VENTA
- Si el agente pidió datos de contacto y el usuario los está dando → PRE-VENTA
- Si el usuario da nombre + teléfono después de que el agente lo pidió → PRE-VENTA
- Si el usuario menciona "mi reserva", "mi código", "ya compré" → POST-VENTA
- Si pide "itinerario" de un paquete que le están mostrando → PRE-VENTA
- Si pide "itinerario" de su reserva ya comprada → POST-VENTA
- Si el mensaje no tiene ninguna relación con viajes, turismo ni reservas → OFF-TOPIC

Responde SOLO con una palabra: "PRE-VENTA", "POST-VENTA" u "OFF-TOPIC"

Ejemplos:
- Agente pidió datos + Usuario: "Juan Pérez, 123456789" → PRE-VENTA
- Usuario viendo paquetes + "quiero el itinerario" → PRE-VENTA
- "Perdí la info de mis vuelos" → POST-VENTA
- "¿Cuánto cuesta ir a Italia?" → PRE-VENTA
- "Tengo un problema con mi reserva" → POST-VENTA
- "¿Sabés la receta de fideos a la carbonara?" → OFF-TOPIC
- "¿Quién ganó el partido de ayer?" → OFF-TOPIC
- "¿Me ayudás con una tarea de matemáticas?" → OFF-TOPIC
"""
