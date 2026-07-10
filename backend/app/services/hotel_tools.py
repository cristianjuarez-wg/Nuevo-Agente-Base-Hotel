"""
FACHADA de compatibilidad (Fase 2.3): hotel_tools.py se partió en el paquete
hotel_tools_pkg/ (info/booking/promos/restaurant/misc + _shared). Este módulo reexporta
la API pública histórica para que los imports existentes
(`from app.services.hotel_tools import execute_tool`, etc.) sigan funcionando sin cambios.
"""
from app.services.hotel_tools_pkg import (  # noqa: F401
    execute_tool,
    _DISPATCH,
    _match_menu_items,
    persist_preferences,
    _clasificar_preferencia,
)
from app.services.hotel_tools_pkg.restaurant import _handle_registrar_pedido  # noqa: F401
