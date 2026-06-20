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
