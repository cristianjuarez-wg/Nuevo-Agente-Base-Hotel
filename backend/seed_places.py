"""
Seed de LUGARES Y EXCURSIONES + COMERCIOS AMIGOS del Hampton by Hilton Bariloche.

Crea registros Place (editables desde el backoffice) para que el agente pueda recomendar
qué hacer en Bariloche, dónde esquiar, dónde comer rico y cómo llegar — en vez de no tener
nada cargado. Tras crear cada Place lo re-ingesta al vector store (igual que el backoffice),
así el agente lo tiene disponible sin redeploy.

Los LUGARES son reales de Bariloche (nombres y distancias aproximadas reales). Los datos de
COMERCIOS AMIGOS —descuentos, teléfonos/WhatsApp, tarifas— son de DEMOSTRACIÓN y plausibles:
el cliente los edita con sus acuerdos reales (igual que el CBU/alias de pagos). Los teléfonos
son ficticios con formato argentino válido.

Idempotente: no duplica si ya existe un Place con el mismo nombre.

Ejecutar:  python seed_places.py
"""
import asyncio

from app.models.database import SessionLocal
from app.models.knowledge import Place
from app.services import knowledge_service

# Maps por búsqueda de nombre (sin place_id inventado).
def _maps(query: str) -> str:
    from urllib.parse import quote_plus
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


# Foto de Wikimedia Commons por nombre de archivo real (Special:FilePath devuelve la
# imagen directa y estable). Los nombres fueron verificados en Commons.
def _wikimedia(filename: str, width: int = 800) -> str:
    from urllib.parse import quote
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width={width}"


# (name, category, description, address, price_info, maps_url,
#  is_partner, discount, phone, whatsapp)
PLACES = [
    # ── EXCURSIONES / ATRACCIONES (info para recomendar, sin acuerdo comercial) ──
    {
        "name": "Cerro Catedral",
        "category": "excursion",
        "description": (
            "El principal centro de esquí de Bariloche y uno de los más grandes de "
            "Sudamérica, a unos 19 km del hotel. En invierno, pistas para todos los niveles, "
            "escuela de esquí y snowboard, y alquiler de equipos. En verano, trekking, "
            "mountain bike y un mirador espectacular del lago Gutiérrez."
        ),
        "address": "Villa Catedral, San Carlos de Bariloche",
        "price_info": "Pase diario de ski y alquiler de equipos: según temporada. Consultá en recepción.",
        "maps_url": _maps("Cerro Catedral Bariloche"),
        "image_url": _wikimedia("Base del Cerro Catedral (Bariloche).JPG"),
    },
    {
        "name": "Circuito Chico",
        "category": "excursion",
        "description": (
            "El recorrido panorámico clásico de Bariloche (~25 km de paseo): bordea el lago "
            "Nahuel Huapi pasando por Playa Bonita, Cerro Campanario, Llao Llao y Punto "
            "Panorámico. Ideal para hacer en auto, en bici o con una excursión guiada."
        ),
        "address": "Av. Bustillo, San Carlos de Bariloche",
        "price_info": "Recorrido libre o excursión guiada de medio día.",
        "maps_url": _maps("Circuito Chico Bariloche"),
        "image_url": _wikimedia("Bariloche circuito chico - panoramio.jpg"),
    },
    {
        "name": "Cerro Campanario",
        "category": "atraccion",
        "description": (
            "Su mirador fue elegido por National Geographic entre las mejores vistas del "
            "mundo. Se sube en aerosilla (o caminando) y desde arriba se ve el lago Nahuel "
            "Huapi, Llao Llao y los cerros. A unos 17 km del hotel, sobre la Av. Bustillo."
        ),
        "address": "Av. Bustillo km 17,5, San Carlos de Bariloche",
        "price_info": "Aerosilla con costo; hay confitería en la cima.",
        "maps_url": _maps("Cerro Campanario Bariloche aerosilla"),
        "image_url": _wikimedia("Argentina - View from Cerro Campanario.jpg"),
    },
    {
        "name": "Cerro Tronador y Ventisquero Negro",
        "category": "excursion",
        "description": (
            "Excursión de día completo al cerro más alto de la zona (3.478 m), con su "
            "glaciar Ventisquero Negro y cascadas. Atraviesa el Parque Nacional Nahuel Huapi "
            "y el bosque andino-patagónico. Suele salir temprano y volver al atardecer."
        ),
        "address": "Parque Nacional Nahuel Huapi",
        "price_info": "Excursión de día completo (con guía). Reservá con anticipación.",
        "maps_url": _maps("Cerro Tronador Bariloche"),
        "image_url": _wikimedia("Cerro tronador desde lago mascardi 01b.jpg"),
    },
    {
        "name": "Isla Victoria y Bosque de Arrayanes",
        "category": "excursion",
        "description": (
            "Navegación por el lago Nahuel Huapi hasta la Isla Victoria y el Parque Nacional "
            "Los Arrayanes, un bosque único de árboles de corteza canela. Salidas desde "
            "Puerto Pañuelo (zona Llao Llao). Excursión de medio día o día completo."
        ),
        "address": "Puerto Pañuelo, Av. Bustillo km 25,5",
        "price_info": "Navegación con costo; medio día o día completo.",
        "maps_url": _maps("Isla Victoria Bosque de Arrayanes Bariloche"),
        "image_url": _wikimedia("Isla Victoria Lago Nahuel Huapi (2408).jpg"),
    },
    {
        "name": "Villa La Angostura",
        "category": "excursion",
        "description": (
            "Pintoresco pueblo de montaña a ~80 km, sobre la Ruta de los Siete Lagos. "
            "Calles arboladas, gastronomía, el Bosque de Arrayanes y el cerro Bayo (esquí en "
            "invierno). Una linda escapada de un día desde Bariloche."
        ),
        "address": "Villa La Angostura, Neuquén",
        "price_info": "Escapada de día completo.",
        "maps_url": _maps("Villa La Angostura"),
        "image_url": _wikimedia("Villa La Angostura Montaje.jpg"),
    },
    {
        "name": "Centro Cívico",
        "category": "atraccion",
        "description": (
            "El corazón histórico de Bariloche, a solo 150 metros del hotel (se llega "
            "caminando). Construcciones de piedra y madera estilo alpino, la torre del reloj, "
            "museos, artesanos y la postal clásica frente al lago. Punto de partida ideal "
            "para recorrer el centro, chocolaterías y restaurantes."
        ),
        "address": "Centro Cívico, San Carlos de Bariloche",
        "price_info": "Acceso libre. A 150 m del hotel.",
        "maps_url": _maps("Centro Civico Bariloche"),
        "image_url": _wikimedia("CentrocivicoBarilochenieve.jpg"),
    },
    {
        "name": "Llao Llao y Puerto Pañuelo",
        "category": "atraccion",
        "description": (
            "Una de las postales más icónicas de la Patagonia: la zona del hotel Llao Llao, "
            "la capilla San Eduardo, miradores y senderos de bosque sobre la Av. Bustillo. "
            "Punto de salida de navegaciones por el Nahuel Huapi."
        ),
        "address": "Av. Bustillo km 25, San Carlos de Bariloche",
        "price_info": "Miradores y senderos de acceso libre.",
        "maps_url": _maps("Llao Llao Puerto Panuelo Bariloche"),
        "image_url": _wikimedia("Llao Llao Peninsula.jpg"),
    },

    # ── GASTRONOMÍA — COMERCIOS AMIGOS (descuentos de DEMO, editables) ──
    {
        "name": "Rapa Nui",
        "category": "gastronomia",
        "description": (
            "Chocolatería y heladería emblema de Bariloche, sobre la calle Mitre, en pleno "
            "centro. Chocolates artesanales, el clásico 'rama' y helados de dulce de leche y "
            "frutos del bosque. Imperdible para llevarse algo dulce."
        ),
        "address": "Av. Mitre 202, San Carlos de Bariloche",
        "price_info": "Cafetería y tienda de chocolates.",
        "maps_url": _maps("Rapa Nui Bariloche Mitre"),
        "image_url": _wikimedia("Huevo de chocolate en Bariloche (Argentina).jpg"),
        "is_partner": True,
        "discount": "10% para huéspedes presentando la llave del hotel",
        "phone": "+54 294 442-3999",
        "whatsapp": "5492944230000",
    },
    {
        "name": "Mamuschka",
        "category": "gastronomia",
        "description": (
            "Chocolatería premium muy querida de Bariloche, también sobre Mitre. Bombones, "
            "tabletas y un café con vista a la calle. Una de las marcas de chocolate más "
            "reconocidas de la ciudad."
        ),
        "address": "Av. Mitre 298, San Carlos de Bariloche",
        "price_info": "Cafetería y tienda de chocolates.",
        "maps_url": _maps("Mamuschka Bariloche"),
        "image_url": _wikimedia("Huevo de chocolate en Bariloche..jpg"),
        "is_partner": True,
        "discount": "10% para huéspedes en compras en tienda",
        "phone": "+54 294 442-3294",
        "whatsapp": "5492944230001",
    },
    {
        "name": "Cervecería Patagonia",
        "category": "gastronomia",
        "description": (
            "Cervecería con una de las mejores vistas al lago, sobre el Circuito Chico (zona "
            "Llao Llao). Cervezas artesanales propias, tablas para compartir y pizzas. Un "
            "plan ideal al atardecer."
        ),
        "address": "Av. Bustillo km 24,7, San Carlos de Bariloche",
        "price_info": "Cervecería y cocina. Ideal atardecer.",
        "maps_url": _maps("Cerveceria Patagonia Bariloche Bustillo"),
        "is_partner": True,
        "discount": "Primera pinta de cortesía para huéspedes del Hampton",
        "phone": "+54 294 445-8400",
        "whatsapp": "5492944230002",
    },
    {
        "name": "El Boliche de Alberto",
        "category": "gastronomia",
        "description": (
            "Parrilla clásica de Bariloche, famosa por sus carnes y porciones generosas. Un "
            "imperdible para los amantes del asado patagónico. Conviene reservar en temporada."
        ),
        "address": "Villegas 347, San Carlos de Bariloche",
        "price_info": "Parrilla. Reservar en temporada alta.",
        "maps_url": _maps("El Boliche de Alberto Bariloche Villegas"),
        "is_partner": True,
        "discount": "10% en efectivo para huéspedes",
        "phone": "+54 294 443-1433",
        "whatsapp": "5492944230003",
    },
    {
        "name": "Manush",
        "category": "gastronomia",
        "description": (
            "Cervecería artesanal y cocina en pleno centro, a pasos del Centro Cívico. Buena "
            "carta de cervezas propias, hamburguesas y platos para compartir, en un ambiente "
            "relajado."
        ),
        "address": "Neumeyer 20, San Carlos de Bariloche",
        "price_info": "Cervecería y cocina, ambiente relajado.",
        "maps_url": _maps("Manush Bariloche cerveceria"),
        "is_partner": True,
        "discount": "Tabla de cortesía o 10% para huéspedes",
        "phone": "+54 294 452-2755",
        "whatsapp": "5492944230004",
    },

    # ── TRANSPORTE ──
    {
        "name": "Traslado Aeropuerto ↔ Hotel",
        "category": "transporte",
        "description": (
            "Servicio de traslado entre el Aeropuerto de Bariloche (Teniente Luis Candelaria) "
            "y el hotel, a unos 20 minutos. Combi o remís privado. Coordinalo en recepción "
            "indicando tu número y horario de vuelo y te esperamos a la llegada."
        ),
        "address": "Aeropuerto de Bariloche (BRC) ↔ Libertad 290",
        "price_info": "Tarifa preferencial para huéspedes. Coordinar en recepción.",
        "maps_url": _maps("Aeropuerto Bariloche"),
        "is_partner": True,
        "discount": "Tarifa preferencial para huéspedes del Hampton",
        "phone": "+54 294 474-6200",
        "whatsapp": "5492944746200",
    },
]


async def main():
    db = SessionLocal()
    created = 0
    updated = 0
    try:
        for p in PLACES:
            exists = db.query(Place).filter(Place.name == p["name"]).first()
            if exists:
                # Actualiza si cambió algún campo editable (foto, descripción, descuento…),
                # para que re-correr el seed aplique las mejoras sobre lo ya cargado.
                campos = {
                    "category": p["category"],
                    "description": p.get("description"),
                    "address": p.get("address"),
                    "price_info": p.get("price_info"),
                    "maps_url": p.get("maps_url"),
                    "image_url": p.get("image_url"),
                    "is_partner": p.get("is_partner", False),
                    "discount": p.get("discount"),
                    "phone": p.get("phone"),
                    "whatsapp": p.get("whatsapp"),
                }
                cambios = {k: v for k, v in campos.items() if getattr(exists, k) != v}
                if cambios:
                    for k, v in cambios.items():
                        setattr(exists, k, v)
                    db.commit()
                    db.refresh(exists)
                    await knowledge_service.reingest(exists)
                    updated += 1
                    print(f"[seed-places] '{p['name']}' actualizado ({', '.join(cambios)}).")
                else:
                    print(f"[seed-places] '{p['name']}' ya existe sin cambios (id {exists.id}).")
                continue
            place = Place(
                name=p["name"],
                category=p["category"],
                description=p.get("description"),
                address=p.get("address"),
                price_info=p.get("price_info"),
                maps_url=p.get("maps_url"),
                image_url=p.get("image_url"),
                is_partner=p.get("is_partner", False),
                discount=p.get("discount"),
                phone=p.get("phone"),
                whatsapp=p.get("whatsapp"),
                status="active",
            )
            db.add(place)
            db.commit()
            db.refresh(place)
            await knowledge_service.reingest(place)
            created += 1
            tag = " (comercio amigo)" if place.is_partner else ""
            print(f"[seed-places] '{place.name}'{tag} creado (id {place.id}) y re-ingestado.")
        print(f"[seed-places] LISTO. {created} nuevos, {updated} actualizados.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
