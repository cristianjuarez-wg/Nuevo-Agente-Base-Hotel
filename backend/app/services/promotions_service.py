"""
Servicio de PROMOCIONES: re-ingesta automática al vector store + query de vigentes.

Sigue el mismo patrón que knowledge_service.py:
  - reingest(promo): borra chunks viejos y re-agrega si la promo está activa.
  - remove_from_index(promo): borra completamente del vector store al eliminar.
  - get_vigentes(db): query determinística de promos activas y dentro de rango de fechas.
    La usa el handler de la tool `promos_vigentes`.
"""
import hashlib
from datetime import datetime
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.config import settings
from app.services.vector_store import get_vector_store
from app.core.logging_config import get_logger
from app.models.promotions import Promotion

logger = get_logger(__name__)


def _build_chunks(doc_source: str, text: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(text)
    doc_id = hashlib.md5(doc_source.encode()).hexdigest()[:12]
    return [
        {
            "text": piece,
            "metadata": {
                "doc_id": doc_id,
                "chunk_index": i,
                "status": "active",
                "source": doc_source,
                "filename": doc_source,
            },
        }
        for i, piece in enumerate(pieces)
    ]


async def reingest(promo: Promotion) -> dict:
    """Re-ingesta una promoción. Idempotente: borra y vuelve a agregar."""
    vs = get_vector_store()
    source = promo.doc_source

    deleted = 0
    try:
        result = vs.delete_by_source(source)
        deleted = result.get("deleted", 0)
    except Exception as e:
        logger.warning("promotions reingest: delete_by_source falló", source=source, error=str(e))

    added = 0
    if promo.status == "active":
        text = promo.to_ingest_text().strip()
        if text:
            chunks = _build_chunks(source, text)
            try:
                add_result = await vs.add_documents(chunks)
                added = add_result.get("added", 0)
            except Exception as e:
                logger.error("promotions reingest: add_documents falló", source=source, error=str(e))

    logger.info("Promotion re-ingested", source=source, deleted=deleted, added=added)
    return {"deleted": deleted, "added": added}


async def remove_from_index(promo: Promotion) -> dict:
    """Quita la promoción del vector store al eliminarla."""
    vs = get_vector_store()
    source = promo.doc_source
    deleted = 0
    try:
        result = vs.delete_by_source(source)
        deleted = result.get("deleted", 0)
    except Exception as e:
        logger.warning("promotions remove_from_index falló", source=source, error=str(e))
    logger.info("Promotion removed from index", source=source, deleted=deleted)
    return {"deleted": deleted}


def get_vigentes(db: Session) -> List[Promotion]:
    """Devuelve las promociones activas y dentro de su rango de fechas (si tienen)."""
    now = datetime.now()
    promos = db.query(Promotion).filter(Promotion.status == "active").all()
    vigentes = []
    for p in promos:
        if p.valid_from and p.valid_from > now:
            continue
        if p.valid_until and p.valid_until < now:
            continue
        vigentes.append(p)
    return vigentes


# ---------------------------------------------------------------------------
# Motor de descuento (determinístico — NUNCA lo calcula el LLM)
# ---------------------------------------------------------------------------
def aplicar_descuento(promo: Promotion, base_price_usd: float, nights: int) -> "dict | None":
    """Calcula el efecto de una promo sobre una estadía concreta.

    Devuelve dict con el desglose o None si la promo no aplica (no cumple el mínimo
    de noches, o es cualitativa / sin valor calculable).

      free_night → se bonifican `discount_value` noches: pagás (nights - bonif).
      percentage → `discount_value`% sobre el total.

    Todos los importes en USD; el ARS lo resuelve el caller con la cotización vigente.
    """
    if base_price_usd is None or nights <= 0:
        return None
    if promo.min_nights and nights < promo.min_nights:
        return None

    full = round(base_price_usd * nights, 2)
    free_nights = 0  # noches bonificadas para ESTA estadía (solo free_night)

    if promo.discount_type == "free_night" and promo.discount_value:
        bonif = int(promo.discount_value)
        if bonif <= 0 or bonif >= nights:
            return None  # no tiene sentido bonificar todas (o más) las noches
        free_nights = bonif
        paid_nights = nights - bonif
        final = round(base_price_usd * paid_nights, 2)
    elif promo.discount_type == "percentage" and promo.discount_value:
        pct = float(promo.discount_value)
        if pct <= 0 or pct >= 100:
            return None
        final = round(full * (1 - pct / 100), 2)
    else:
        return None  # "other" o sin valor → cualitativa, no calculable

    savings = round(full - final, 2)
    if savings <= 0:
        return None

    return {
        "promo_id": promo.id,
        "promo_name": promo.name,
        "discount_type": promo.discount_type,
        "full_price_usd": full,
        "final_price_usd": final,
        "savings_usd": savings,
        # Mecánica concreta para ESTA estadía (no deducible del nombre de la promo).
        # free_night: cuántas noches paga y cuántas van bonificadas. percentage: 0 noches gratis.
        "free_nights": free_nights,
        "paid_nights": nights - free_nights,
    }


def mejor_promo(db: Session, base_price_usd: float, nights: int) -> "dict | None":
    """La promo vigente CALCULABLE de mayor ahorro para esta estadía, o None."""
    mejor = None
    for p in get_vigentes(db):
        oferta = aplicar_descuento(p, base_price_usd, nights)
        if oferta and (mejor is None or oferta["savings_usd"] > mejor["savings_usd"]):
            mejor = oferta
    return mejor


def promos_cualitativas(db: Session) -> List[Promotion]:
    """Promos vigentes NO calculables (discount_type 'other' o sin valor) — para upsell."""
    out = []
    for p in get_vigentes(db):
        calculable = (
            (p.discount_type == "free_night" and p.discount_value)
            or (p.discount_type == "percentage" and p.discount_value)
        )
        if not calculable:
            out.append(p)
    return out


def promos_calculables_cercanas(db: Session, nights: int) -> List[Promotion]:
    """Promos calculables que NO aplican hoy por faltar noches, ordenadas por cercanía.

    Sirve para el upsell: "si sumás N noches accedés a la 4x3". Solo promos cuyo
    min_nights es mayor a las noches actuales.
    """
    out = []
    for p in get_vigentes(db):
        calculable = (
            (p.discount_type == "free_night" and p.discount_value)
            or (p.discount_type == "percentage" and p.discount_value)
        )
        if calculable and p.min_nights and p.min_nights > nights:
            out.append(p)
    out.sort(key=lambda p: p.min_nights)
    return out
