"""
Carta REAL del restaurante PLAZA - Hampton's Kitchen House (Bariloche).

Datos tomados de la carta online del cliente. Los precios están en ARS (como en la
carta real); al sembrar se convierten a USD con la cotización vigente (USD = fuente
de verdad del sistema).

Cada plato tiene su PROPIA foto: las reales del Hampton (CDN bistrify del cliente,
servidas a 600px) cuando existen; el resto, fotos de stock específicas (Unsplash)
elegidas por plato para dar variedad visual a la carta.

Cada ítem: (name, category, price_ars, description, tags[], allergens[], only_dinner, image_url)
"""

# Helper para las fotos reales del Hampton (su CDN sirve thumbnails de 128px; pedimos 600px).
def _hampton(uuid: str) -> str:
    return f"https://cdn.bistrify.app/cdn-cgi/image/w=600,h=600,fit=cover/images/items/{uuid}.jpg"


# Fotos de stock específicas por plato (Unsplash), cuando no hay foto del Hampton.
_U = "https://images.unsplash.com/photo-{id}?w=600&q=80"


# (name, category, price_ars, description, tags, allergens, only_dinner, image_url)
MENU = [
    # ── TAPAS ───────────────────────────────────────────────────────────────
    ("Tabla de empanadas de carne", "tapas", 20000, "4 empanadas de carne cortada a cuchillo.", [], ["gluten"], False,
     _hampton("fe5d7b6b-f645-43b3-ade7-a9139a72bdbf")),
    ("Tequeños", "tapas", 13000, "Bastones de queso con alioli y cilantro.", ["vegetariano"], ["gluten", "lacteos"], False,
     _hampton("8ee46064-c4e6-4abb-88ad-711efa401e28")),
    ("Papas con alioli y salsa picante", "tapas", 13500, "Papas fritas con alioli casero y salsa picante.", ["vegetariano", "sin_tacc"], ["lacteos"], False,
     "https://images.unsplash.com/photo-1630384060421-cb20d0e0649d?w=600&q=80"),
    ("Provoleta rellena", "tapas", 21000, "Provoleta rellena con cebolla, queso azul y cherry.", ["vegetariano", "sin_tacc"], ["lacteos"], False,
     "https://images.unsplash.com/photo-1633896949673-1eb9d131a9b4?w=600&q=80"),
    ("Tostado de jamón y queso", "tapas", 13500, "Sándwich tostado de jamón y queso.", [], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1528736235302-52922df5c122?w=600&q=80"),

    # ── PLATOS / SUGERENCIAS ─────────────────────────────────────────────────
    ("Ojo de bife con papas rotas a la provenzal", "plato", 32500, "Ojo de bife con papas rotas a la provenzal y criolla. Solo cena.", ["sin_tacc"], [], True,
     "https://images.unsplash.com/photo-1546964124-0cce460f38ef?w=600&q=80"),
    ("Trucha de Alicurá sellada al limón", "plato", 31500, "Trucha sellada al limón, puré de zanahoria al comino y gremolata de almendras.", ["sin_tacc"], ["frutos_secos", "pescado"], False,
     _hampton("86eda1ac-be8b-47b1-a7b8-b90e223d857e")),
    ("Milanesa con guarnición", "plato", 25000, "Milanesa con papas fritas, puré o ensaladas.", [], ["gluten"], False,
     "https://images.unsplash.com/photo-1599921841143-819065a55cc6?w=600&q=80"),
    ("Milanesa napolitana", "plato", 29500, "Milanesa napolitana con papas fritas, puré o ensaladas.", [], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=600&q=80"),
    ("Ñoquis de papa", "plato", 21000, "Ñoquis de papa con salsa a elección.", ["vegetariano"], ["gluten"], False,
     "https://images.unsplash.com/photo-1587740908075-9e245070dfaa?w=600&q=80"),
    ("Panzottis de calabaza y queso", "plato", 25000, "Panzottis de calabaza y queso con salsa de hongos.", ["vegetariano"], ["gluten", "lacteos"], False,
     _hampton("c4dd8c7d-2ec1-4307-a668-e9e3f58cb00b")),
    ("Cintas con salsa bolognesa", "plato", 24000, "Cintas con salsa bolognesa.", [], ["gluten"], False,
     _hampton("577115e4-f99b-4735-8dc2-8dd46a015086")),

    # ── SÁNDWICHES / BURGERS ─────────────────────────────────────────────────
    ("Sándwich de lomo", "sandwich", 27500, "Lomo con cebolla caramelizada, quesos, rúcula, hongos y alioli.", [], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1553909489-cd47e0907980?w=600&q=80"),
    ("Hamburguesa Hampton", "sandwich", 25500, "Cebolla caramelizada, queso azul y rúcula.", [], ["gluten", "lacteos"], False,
     _hampton("af7bc8f6-be8e-4ec1-b93e-a40e3b6e3f29")),
    ("Hamburguesa Americana", "sandwich", 27500, "Cheddar, bacon, cebolla caramelizada, huevo, tomate y lechuga.", [], ["gluten", "lacteos"], False,
     _hampton("16581430-8656-4c25-8e47-dd65e62d265e")),
    ("Hamburguesa vegetariana de calabaza y lentejas", "sandwich", 23000, "Con espinaca, tomate asado, alioli y queso.", ["vegetariano"], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1525059696034-4967a8e1dca2?w=600&q=80"),

    # ── ENSALADAS ────────────────────────────────────────────────────────────
    ("Caesar by Hampton", "ensalada", 23000, "Ensalada Caesar con pollo rebozado.", [], ["gluten", "lacteos"], False,
     _hampton("6e0946a2-1e61-4cff-ae53-5cad35ff4d17")),
    ("Ensalada Hampton", "ensalada", 23500, "Rúcula, hongos, huevo poché, palta, cherry y reggianito.", ["vegetariano", "sin_tacc"], ["lacteos", "huevo"], False,
     "https://images.unsplash.com/photo-1607532941433-304659e8198a?w=600&q=80"),
    ("Ensalada Plaza", "ensalada", 21000, "Rúcula, cherry asado, almendras tostadas y pategras al pesto.", ["vegetariano", "sin_tacc"], ["lacteos", "frutos_secos"], False,
     "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=600&q=80"),

    # ── PIZZAS ───────────────────────────────────────────────────────────────
    ("Pizza de cebolla caramelizada y queso azul", "pizza", 18000, "Cebolla caramelizada, hongos y queso azul.", ["vegetariano"], ["gluten", "lacteos"], False,
     _hampton("98d3e973-866c-41a7-91d7-cbb178b8a76c")),
    ("Pizza Napolitana", "pizza", 16000, "Napolitana con cherry asado y ajo.", ["vegetariano"], ["gluten", "lacteos"], False,
     _hampton("dcf12544-67b9-42e0-963e-11002428ff57")),
    ("Pizza Muzzarella", "pizza", 14500, "Pizza individual de muzzarella.", ["vegetariano"], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=600&q=80"),

    # ── POSTRES ──────────────────────────────────────────────────────────────
    ("Volcán de dulce de leche", "postre", 12500, "Volcán de dulce de leche con crema. Al momento.", ["vegetariano"], ["gluten", "lacteos", "huevo"], False,
     _hampton("c8a24b78-38df-42ec-8a5f-72c56526872e")),
    ("Flan con crema y dulce de leche", "postre", 8500, "Flan casero con crema y dulce de leche.", ["vegetariano", "sin_tacc"], ["lacteos", "huevo"], False,
     "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=600&q=80"),
    ("Postre Vigilante", "postre", 6500, "Queso y dulce de membrillo.", ["vegetariano", "sin_tacc"], ["lacteos"], False,
     "https://images.unsplash.com/photo-1505253716362-afaea1d3d1af?w=600&q=80"),

    # ── CERVEZAS ─────────────────────────────────────────────────────────────
    ("Pinta Patagonia 500cc", "cerveza", 11000, "Cerveza tirada, pinta de 500cc.", [], ["gluten"], False,
     "https://images.unsplash.com/photo-1535958636474-b021ee887b13?w=600&q=80"),
    ("Amber Patagonia (lata 410cc)", "cerveza", 8500, "Cerveza Amber en lata.", [], ["gluten"], False,
     "https://images.unsplash.com/photo-1618183479302-1e0aa382c36b?w=600&q=80"),
    ("Vera IPA Patagonia (lata 410cc)", "cerveza", 8500, "Cerveza IPA en lata.", [], ["gluten"], False,
     "https://images.unsplash.com/photo-1608270586620-248524c67de9?w=600&q=80"),

    # ── TRAGOS ───────────────────────────────────────────────────────────────
    ("Aperol Spritz", "trago", 22000, "Aperol, espumante y soda.", ["vegano", "sin_tacc"], [], False,
     "https://images.unsplash.com/photo-1560512823-829485b8bf24?w=600&q=80"),
    ("Gin Athos Bariloche", "trago", 15500, "Gin Athos, agua tónica y piel de limón.", ["vegano", "sin_tacc"], [], False,
     "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?w=600&q=80"),
    ("Negroni", "trago", 18000, "Campari, gin y Carpano Rosso.", ["vegano", "sin_tacc"], [], False,
     "https://images.unsplash.com/photo-1536935338788-846bb9981813?w=600&q=80"),

    # ── VINOS ────────────────────────────────────────────────────────────────
    ("Malbec Terrazas Reserva", "vino", 32000, "Terrazas de los Andes Reserva Malbec (botella).", ["vegano", "sin_tacc"], [], False,
     "https://images.unsplash.com/photo-1553361371-9b22f78e8b1d?w=600&q=80"),
    ("Pinot Noir Malma Reserva", "vino", 32000, "Malma Reserva de Familia Pinot Noir (botella).", ["vegano", "sin_tacc"], [], False,
     "https://images.unsplash.com/photo-1510812431401-41d2bd2722f3?w=600&q=80"),
    ("Copa de vino", "vino", 9000, "Copa de vino de la casa.", ["vegano", "sin_tacc"], [], False,
     "https://images.unsplash.com/photo-1474722883778-792e7990302f?w=600&q=80"),

    # ── CAFETERÍA / MERIENDAS ────────────────────────────────────────────────
    ("Capuccino", "cafeteria", 8500, "Capuccino.", ["vegetariano", "sin_tacc"], ["lacteos"], False,
     "https://images.unsplash.com/photo-1572442388796-11668a67e53d?w=600&q=80"),
    ("Chocolate caliente", "cafeteria", 8500, "Chocolate caliente.", ["vegetariano", "sin_tacc"], ["lacteos"], False,
     "https://images.unsplash.com/photo-1542990253-0d0f5be5f0ed?w=600&q=80"),
    ("Roll de canela", "merienda", 4500, "Roll de canela casero.", ["vegetariano"], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1509365390695-33aee754301f?w=600&q=80"),
    ("Crumble de manzana", "merienda", 9500, "Crumble de manzana tibio.", ["vegetariano"], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1568571780765-9276ac8b75a2?w=600&q=80"),
    ("Croissant con jamón y queso", "merienda", 5500, "Croissant relleno de jamón y queso.", [], ["gluten", "lacteos"], False,
     "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=600&q=80"),
]


def menu_for_seed(rate: float):
    """Devuelve la carta lista para crear MenuItem (precio en USD con la cotización)."""
    out = []
    for name, cat, price_ars, desc, tags, allergens, only_dinner, image_url in MENU:
        out.append({
            "name": name,
            "category": cat,
            "price_usd": round(price_ars / rate, 2) if rate else round(price_ars / 1000, 2),
            "description": desc,
            "tags": tags,
            "allergens": allergens,
            "only_dinner": only_dinner,
            "image_url": image_url,
        })
    return out
