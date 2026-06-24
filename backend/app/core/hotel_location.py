"""
Ubicación del hotel y helpers para armar links de Google Maps SIN API key.

Fuente única de la dirección del hotel y de las URLs públicas de Google Maps que el
agente comparte con el huésped. No llama a ninguna API facturable: arma URLs de tipo
`maps/dir` (direcciones/ruta) y `maps/search` (búsqueda) que el cliente abre en su
propio Google Maps, donde ve la ruta, la distancia y el tiempo reales.

Si en el futuro se integra la Google Maps API (Directions / Distance Matrix) para dar
distancia/tiempo DENTRO del chat, este módulo es el punto único donde enchufarla.
"""
from urllib.parse import quote


HOTEL_NAME = "Hampton by Hilton Bariloche"
HOTEL_ADDRESS = "Libertad 290, San Carlos de Bariloche, Río Negro, Argentina"

# Ciudad del hotel, en minúsculas, para la heurística de "origen lejano" (nota aérea).
HOTEL_CITY = "bariloche"

# Aeropuerto de referencia para llegadas desde otras ciudades.
HOTEL_AIRPORT = "Aeropuerto de Bariloche (BRC)"


# Bloque de ubicación OFICIAL para inyectar en el system prompt del agente. Es el dato
# fijo y confiable de dónde está el hotel: evita que el agente lo invente o lo recupere
# mal del RAG. NO incluye distancia exacta al lago a propósito (no la tenemos como dato);
# para eso el agente deriva a Google Maps vía la tool `como_llegar`.
HOTEL_LOCATION_BLOCK = """\
UBICACIÓN OFICIAL DEL HOTEL (dato fijo y confiable — NUNCA lo inventes ni lo cambies):
- Dirección exacta: Libertad 290, (8400) San Carlos de Bariloche, Río Negro, Argentina.
- A 150 metros del Centro Cívico de Bariloche (el hotel NO está DENTRO del Centro Cívico: \
está a 150 m de él, en pleno centro).
- A 20 minutos del Aeropuerto de Bariloche (BRC).
- En el centro de la ciudad, cerca del lago Nahuel Huapi y de comercios y gastronomía.

UBICACIÓN — NUNCA INVENTES: la dirección y las distancias del hotel son EXACTAMENTE las \
de arriba. Si te piden la dirección, dala textual ("Libertad 290, San Carlos de Bariloche"). \
NUNCA digas que el hotel está "dentro del Centro Cívico" ni inventes una distancia al lago u \
otros puntos. Para "¿a cuánto está de X?" o "¿cómo llego a X?" (el lago, el Cerro Otto, etc.) \
usá SIEMPRE la herramienta `como_llegar` y compartí el link de Google Maps: ahí el huésped ve \
la distancia y el tiempo reales. JAMÁS tires un número de distancia o tiempo de memoria."""


def directions_url(origin: str, destination: str, mode: str = "driving") -> str:
    """Arma un link de Google Maps con la ruta origin → destination.

    `mode`: "driving" (auto) | "walking" (a pie) | "transit" (transporte público).
    El tiempo/distancia los calcula Google Maps al abrir el link; acá no se inventan.
    """
    valid_modes = {"driving", "walking", "transit", "bicycling"}
    mode = mode if mode in valid_modes else "driving"
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote(origin)}"
        f"&destination={quote(destination)}"
        f"&travelmode={mode}"
    )


def search_url(query: str) -> str:
    """Arma un link de búsqueda en Google Maps (ej. 'restaurantes cerca de Libertad 290')."""
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


def near_hotel_search_url(rubro: str) -> str:
    """Link de búsqueda de un rubro cerca del hotel (fallback de comercios genéricos)."""
    return search_url(f"{rubro} cerca de {HOTEL_ADDRESS}")


def is_far_origin(origin: str) -> bool:
    """Heurística simple: el origen es 'lejano' si no menciona la ciudad del hotel.

    Sirve solo para decidir si conviene mencionar la opción aérea (vuelo a BRC). No
    pretende ser geográficamente exacta.
    """
    return HOTEL_CITY not in (origin or "").lower()
