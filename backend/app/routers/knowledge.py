"""
Router del REPOSITORIO DE CONOCIMIENTO del hotel (Fase 1).

El cliente administra desde el backoffice su información estructurada (KnowledgeEntry por
categoría) y sus lugares/excursiones (Place). Cada alta/edición/baja re-ingesta el vector
store en caliente (knowledge_service), de modo que el agente la toma sin redeploy.

También expone subida de imágenes (URL o archivo) que se guardan en MEDIA_DIR (disco
persistente /data en Render) y se sirven desde /media.
"""
import os
import hashlib
import time
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.knowledge import (
    KnowledgeEntry, Place, KNOWLEDGE_CATEGORIES, PLACE_CATEGORIES,
)
from app.services import knowledge_service
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])

# Imágenes subidas: carpeta y validación.
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class KnowledgeEntryPayload(BaseModel):
    category: str
    title: str
    content: Optional[str] = None
    data: Optional[dict] = None
    status: Optional[str] = "active"


class PlacePayload(BaseModel):
    name: str
    category: Optional[str] = "atraccion"
    description: Optional[str] = None
    image_url: Optional[str] = None
    maps_url: Optional[str] = None
    address: Optional[str] = None
    price_info: Optional[str] = None
    status: Optional[str] = "active"


class StatusUpdate(BaseModel):
    status: str  # "active" | "inactive"


# ---------------------------------------------------------------------------
# KnowledgeEntry CRUD
# ---------------------------------------------------------------------------
@router.get("/entries")
async def list_entries(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(KnowledgeEntry)
    if category:
        q = q.filter(KnowledgeEntry.category == category)
    entries = q.order_by(KnowledgeEntry.category, KnowledgeEntry.id).all()
    return {"entries": [e.to_dict() for e in entries], "total": len(entries)}


@router.post("/entries")
async def create_entry(payload: KnowledgeEntryPayload, db: Session = Depends(get_db)):
    if payload.category not in KNOWLEDGE_CATEGORIES:
        raise HTTPException(400, f"Categoría inválida. Válidas: {', '.join(KNOWLEDGE_CATEGORIES)}")
    entry = KnowledgeEntry(
        category=payload.category,
        title=payload.title.strip(),
        content=(payload.content or "").strip() or None,
        data=payload.data or {},
        status=payload.status or "active",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    await knowledge_service.reingest(entry)
    return entry.to_dict()


@router.put("/entries/{entry_id}")
async def update_entry(entry_id: int, payload: KnowledgeEntryPayload, db: Session = Depends(get_db)):
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")
    if payload.category not in KNOWLEDGE_CATEGORIES:
        raise HTTPException(400, f"Categoría inválida. Válidas: {', '.join(KNOWLEDGE_CATEGORIES)}")
    entry.category = payload.category
    entry.title = payload.title.strip()
    entry.content = (payload.content or "").strip() or None
    entry.data = payload.data or {}
    if payload.status:
        entry.status = payload.status
    db.commit()
    db.refresh(entry)
    await knowledge_service.reingest(entry)
    return entry.to_dict()


@router.patch("/entries/{entry_id}/status")
async def set_entry_status(entry_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")
    entry.status = payload.status
    db.commit()
    db.refresh(entry)
    await knowledge_service.reingest(entry)
    return entry.to_dict()


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")
    await knowledge_service.remove_from_index(entry)
    db.delete(entry)
    db.commit()
    return {"deleted": True, "id": entry_id}


# ---------------------------------------------------------------------------
# Place CRUD
# ---------------------------------------------------------------------------
@router.get("/places")
async def list_places(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Place)
    if category:
        q = q.filter(Place.category == category)
    places = q.order_by(Place.category, Place.name).all()
    return {"places": [p.to_dict() for p in places], "total": len(places)}


@router.post("/places")
async def create_place(payload: PlacePayload, db: Session = Depends(get_db)):
    if payload.category and payload.category not in PLACE_CATEGORIES:
        raise HTTPException(400, f"Categoría inválida. Válidas: {', '.join(PLACE_CATEGORIES)}")
    place = Place(
        name=payload.name.strip(),
        category=payload.category or "atraccion",
        description=(payload.description or "").strip() or None,
        image_url=(payload.image_url or "").strip() or None,
        maps_url=(payload.maps_url or "").strip() or None,
        address=(payload.address or "").strip() or None,
        price_info=(payload.price_info or "").strip() or None,
        status=payload.status or "active",
    )
    db.add(place)
    db.commit()
    db.refresh(place)
    await knowledge_service.reingest(place)
    return place.to_dict()


@router.put("/places/{place_id}")
async def update_place(place_id: int, payload: PlacePayload, db: Session = Depends(get_db)):
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Lugar no encontrado")
    if payload.category and payload.category not in PLACE_CATEGORIES:
        raise HTTPException(400, f"Categoría inválida. Válidas: {', '.join(PLACE_CATEGORIES)}")
    place.name = payload.name.strip()
    place.category = payload.category or place.category
    place.description = (payload.description or "").strip() or None
    place.image_url = (payload.image_url or "").strip() or None
    place.maps_url = (payload.maps_url or "").strip() or None
    place.address = (payload.address or "").strip() or None
    place.price_info = (payload.price_info or "").strip() or None
    if payload.status:
        place.status = payload.status
    db.commit()
    db.refresh(place)
    await knowledge_service.reingest(place)
    return place.to_dict()


@router.patch("/places/{place_id}/status")
async def set_place_status(place_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Lugar no encontrado")
    place.status = payload.status
    db.commit()
    db.refresh(place)
    await knowledge_service.reingest(place)
    return place.to_dict()


@router.delete("/places/{place_id}")
async def delete_place(place_id: int, db: Session = Depends(get_db)):
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Lugar no encontrado")
    await knowledge_service.remove_from_index(place)
    db.delete(place)
    db.commit()
    return {"deleted": True, "id": place_id}


# ---------------------------------------------------------------------------
# Subida de imágenes
# ---------------------------------------------------------------------------
@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Guarda una imagen en MEDIA_DIR y devuelve su URL pública (/media/<archivo>)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"Formato no permitido. Usá: {', '.join(sorted(ALLOWED_IMAGE_EXT))}")

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"Imagen demasiado grande (máx {MAX_IMAGE_BYTES // (1024*1024)}MB)")

    os.makedirs(settings.MEDIA_DIR, exist_ok=True)
    digest = hashlib.md5(content).hexdigest()[:16]
    fname = f"{digest}{ext}"
    path = os.path.join(settings.MEDIA_DIR, fname)
    with open(path, "wb") as f:
        f.write(content)

    logger.info("Image uploaded", filename=fname, size=len(content))
    return {"url": f"/media/{fname}", "filename": fname}
