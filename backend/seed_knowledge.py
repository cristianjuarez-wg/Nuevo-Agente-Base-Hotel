"""
Seed del REPOSITORIO DE CONOCIMIENTO con la info real del Hampton by Hilton Bariloche.

Crea KnowledgeEntry estructuradas (editables desde el backoffice) a partir de los datos
del hotel, para que el cliente arranque con información cargada en vez de una pantalla
vacía. Idempotente: no duplica si ya existen entries de esa categoría.

Tras crear cada entry, la re-ingesta al vector store (igual que el backoffice), de modo
que el agente la tiene disponible sin redeploy.

Los datos de PAGOS son de demostración (CBU/alias de ejemplo) — el cliente los edita.

Ejecutar:  python seed_knowledge.py
"""
import asyncio

from app.models.database import SessionLocal
from app.models.knowledge import KnowledgeEntry
from app.services import knowledge_service

# (category, title, content, data)
ENTRIES = [
    (
        "pagos",
        "Formas de pago y transferencia",
        "Aceptamos efectivo, tarjetas y transferencia bancaria. Para confirmar la reserva "
        "puede requerirse una seña; consultá las condiciones al reservar.",
        {
            "medios": ["Efectivo", "Tarjeta de crédito/débito", "Transferencia bancaria"],
            "titular": "Hampton by Hilton Bariloche",
            "banco": "Banco (a completar por el hotel)",
            "cbu": "0000000000000000000000",
            "alias": "HAMPTON.BARILOCHE",
        },
    ),
    (
        "checkin",
        "Check-in y Check-out",
        "Check-in a partir de las 15:00. Check-out hasta las 11:00. Para early check-in o "
        "late check-out, consultá en recepción según disponibilidad.",
        {},
    ),
    (
        "mascotas",
        "Mascotas y convivencia",
        "El hotel es pet friendly: las mascotas son bienvenidas consultando condiciones. "
        "Contamos con habitaciones y áreas comunes adaptadas para personas con movilidad "
        "reducida.",
        {},
    ),
    (
        "servicios",
        "Servicios e instalaciones",
        "Desayuno buffet incluido en todas las tarifas. WiFi gratuito en todo el hotel. "
        "Restaurante Plaza – Hampton's Kitchen House y Lobby Bar. Estacionamiento privado "
        "cubierto (con costo adicional). Recepción 24 hs y concierge. Ski storage para "
        "temporada de nieve. SUM para eventos. Lavandería. Programa Hilton Honors.",
        {},
    ),
    (
        "faq",
        "Preguntas frecuentes",
        "",
        {
            "items": [
                {"q": "¿El desayuno está incluido?", "a": "Sí, el desayuno buffet está incluido en todas las tarifas."},
                {"q": "¿Tienen estacionamiento?", "a": "Sí, contamos con estacionamiento privado cubierto con acceso directo, con costo adicional."},
                {"q": "¿Aceptan mascotas?", "a": "Sí, somos un hotel pet friendly. Consultá las condiciones al reservar."},
                {"q": "¿Dónde están ubicados?", "a": "En Libertad 290, a 150 metros del Centro Cívico y a 20 minutos del aeropuerto."},
                {"q": "¿Tienen habitaciones accesibles?", "a": "Sí, contamos con habitaciones y áreas comunes adaptadas para movilidad reducida."},
            ]
        },
    ),
]


async def main():
    db = SessionLocal()
    created = 0
    try:
        for category, title, content, data in ENTRIES:
            exists = db.query(KnowledgeEntry).filter(KnowledgeEntry.category == category).first()
            if exists:
                print(f"[seed-kb] '{category}' ya existe (id {exists.id}). Salto.")
                continue
            entry = KnowledgeEntry(
                category=category, title=title, content=content or None,
                data=data or {}, status="active",
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            await knowledge_service.reingest(entry)
            created += 1
            print(f"[seed-kb] '{category}' creado (id {entry.id}) y re-ingestado.")
        print(f"[seed-kb] LISTO. {created} entradas nuevas.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
