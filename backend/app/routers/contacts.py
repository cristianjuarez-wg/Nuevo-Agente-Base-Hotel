"""
API Router para Visión 360° del Cliente
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.database import get_db
from app.services.contact_service import ContactService
from app.services.summary_service import SummaryService
from app.config import settings
from app.core.logging_config import get_logger
from pydantic import BaseModel
from datetime import datetime, timezone

logger = get_logger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

# Instancias de servicios
contact_service = ContactService()
summary_service = SummaryService(settings.OPENAI_API_KEY)


# ========================================
# SCHEMAS (Pydantic Models)
# ========================================

class ContactResponse(BaseModel):
    id: int
    phone_number: str
    phone_country_code: Optional[str]
    email: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str]
    first_contact_date: datetime
    last_interaction_date: datetime
    metrics: dict
    ai_summary: Optional[str]
    last_summary_update: Optional[datetime]
    contact_type: str
    is_active: bool

    class Config:
        from_attributes = True


class ContactListResponse(BaseModel):
    contacts: List[ContactResponse]
    total: int
    page: int
    page_size: int


class Contact360Response(BaseModel):
    contact: dict
    conversations: List[dict]
    leads: List[dict]
    packages: List[dict]
    tickets: List[dict]


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sequence_number: int
    created_at: datetime
    context_type: str
    metadata: dict

    class Config:
        from_attributes = True


# ========================================
# ENDPOINTS
# ========================================

@router.get("/", response_model=ContactListResponse)
async def list_contacts(
    query: Optional[str] = Query(None, description="Búsqueda por nombre, email o teléfono"),
    contact_type: Optional[str] = Query(None, description="Filtro por tipo: lead, customer, both"),
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(50, ge=1, le=100, description="Tamaño de página"),
    db: Session = Depends(get_db)
):
    """
    Lista contactos con filtros y paginación
    """
    offset = (page - 1) * page_size
    
    contacts = contact_service.search_contacts(
        query=query,
        contact_type=contact_type,
        limit=page_size,
        offset=offset,
        db=db
    )
    
    # Contar total (sin paginación)
    from app.models.contact import Contact
    total_query = db.query(Contact)
    
    if contact_type:
        total_query = total_query.filter(Contact.contact_type == contact_type)
    
    if query:
        search_filter = (
            Contact.first_name.ilike(f"%{query}%") |
            Contact.last_name.ilike(f"%{query}%") |
            Contact.email.ilike(f"%{query}%") |
            Contact.phone_number.ilike(f"%{query}%")
        )
        total_query = total_query.filter(search_filter)
    
    total = total_query.count()
    
    return ContactListResponse(
        contacts=[c.to_dict() for c in contacts],
        total=total,
        page=page,
        page_size=page_size
    )


def _contact_row(contact, db) -> dict:
    """Fila de contacto enriquecida con canal, origen y si está alojado hoy."""
    from app.models.hotel import Booking
    from app.core.origin import origin_from_channel
    from datetime import date
    row = contact.to_dict()
    channel = contact_service.get_channel(contact.id, db)
    row["channel"] = channel
    row["origin"] = origin_from_channel(channel)
    # Verde solo si TENEMOS contacto real por WhatsApp (la persona nos escribió por ahí).
    row["whatsapp_linked"] = contact_service.has_whatsapp_contact(contact.id, db)
    today = date.today()
    row["is_staying_now"] = db.query(Booking).filter(
        Booking.contact_id == contact.id,
        Booking.status != "cancelled",
        Booking.check_in <= today,
        Booking.check_out >= today,
    ).first() is not None
    return row


# NOTA: estas rutas estáticas van ANTES de "/{contact_id}" para que FastAPI no
# interprete "passengers"/"leads-identity" como un contact_id.
@router.get("/passengers")
async def list_passengers(db: Session = Depends(get_db)):
    """Pasajeros = Contacts con al menos 1 reserva (purchases_made > 0)."""
    from app.models.contact import Contact
    rows = (
        db.query(Contact)
        .filter(Contact.purchases_made > 0)
        .order_by(Contact.last_interaction_date.desc())
        .all()
    )
    return {"success": True, "passengers": [_contact_row(c, db) for c in rows]}


@router.get("/leads-identity")
async def list_lead_contacts(db: Session = Depends(get_db)):
    """Leads (identidad) = Contacts que aún no reservaron (purchases_made == 0)."""
    from app.models.contact import Contact
    rows = (
        db.query(Contact)
        .filter(Contact.purchases_made == 0)
        .order_by(Contact.last_interaction_date.desc())
        .all()
    )
    return {"success": True, "leads": [_contact_row(c, db) for c in rows]}


@router.get("/{contact_id}/profile")
async def get_guest_profile(contact_id: int, db: Session = Depends(get_db)):
    """Perfil 360° del huésped (estadías, habitación preferida, frecuencia, preferencias)."""
    profile = contact_service.get_guest_profile(contact_id, db)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Contacto {contact_id} no encontrado")
    return {"success": True, "profile": profile}


class PreferencesUpdate(BaseModel):
    preferences: dict


@router.patch("/{contact_id}/preferences")
async def update_preferences(contact_id: int, payload: PreferencesUpdate, db: Session = Depends(get_db)):
    """Actualiza el JSON de preferencias del huésped (gustos, servicios, familia)."""
    ok = contact_service.set_preferences(contact_id, payload.preferences, db)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Contacto {contact_id} no encontrado")
    return {"success": True, "message": "Preferencias actualizadas"}


class ContactFieldsUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None


@router.patch("/{contact_id}")
async def update_contact(contact_id: int, payload: ContactFieldsUpdate, db: Session = Depends(get_db)):
    """Edita los datos del pasajero (nombre, apellido, email, teléfono)."""
    result = contact_service.update_fields(contact_id, payload.model_dump(exclude_unset=True), db)
    if not result.get("ok"):
        # 409 si el teléfono choca con otro contacto; 404 si no existe.
        code = 404 if result.get("error") == "Contacto no encontrado." else 409
        raise HTTPException(status_code=code, detail=result.get("error", "No se pudo actualizar."))
    return {"success": True, "contact": result["contact"]}


@router.delete("/{contact_id}")
async def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    """Elimina un contacto (pasajero / lead-identidad) del backoffice.

    Reservas y leads se CONSERVAN despersonalizados (contact_id → NULL): son
    históricos de negocio. En cambio, las CONVERSACIONES (el hilo de chat/WhatsApp)
    se BORRAN por completo, junto con sus mensajes.

    Por qué borrar la conversación y no solo desvincularla: el session_id de WhatsApp
    se deriva del teléfono ("wa_<tel>"), y el historial se rehidrata por session_id, no
    por contact_id. Si solo se desvinculara, al reasignar ese teléfono a otro contacto
    el agente seguiría trayendo el historial del contacto borrado. Además limpiamos el
    cache en RAM del agente para esos session_id (ver más abajo).
    """
    from app.models.contact import Contact
    from app.models.hotel import Booking
    from app.models.lead import Lead
    from app.models.conversation import Conversation

    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")

    # Desvincular reservas y leads (históricos de negocio: se conservan despersonalizados).
    db.query(Booking).filter(Booking.contact_id == contact_id).update(
        {Booking.contact_id: None}, synchronize_session=False
    )
    db.query(Lead).filter(Lead.contact_id == contact_id).update(
        {Lead.contact_id: None}, synchronize_session=False
    )

    # Borrar las conversaciones del contacto (con sus mensajes en cascada). Iteramos y
    # usamos db.delete(conv) — NO un query().delete() masivo — para que se dispare el
    # cascade="all, delete-orphan" del modelo y se borren los ConversationMessage.
    # Guardamos los session_id para limpiar después el cache en RAM del agente.
    conversations = db.query(Conversation).filter(
        Conversation.contact_id == contact_id
    ).all()
    deleted_session_ids = [c.session_id for c in conversations if c.session_id]
    for conv in conversations:
        db.delete(conv)
    try:
        from app.models.postsale import SoldPackage
        db.query(SoldPackage).filter(SoldPackage.contact_id == contact_id).update(
            {SoldPackage.contact_id: None}, synchronize_session=False
        )
    except Exception:  # noqa: BLE001 — el modelo puede no estar presente en esta demo
        pass

    # Restaurante: pedidos, reservas de mesa y vouchers también referencian al contacto.
    # Sin desvincularlos, el DELETE falla por integridad referencial (Postgres) y el
    # contacto sobrevive ocupando su teléfono. Best-effort por si la tabla no existe.
    try:
        from app.models.restaurant import RestaurantOrder, TableReservation, Voucher
        for model in (RestaurantOrder, TableReservation, Voucher):
            db.query(model).filter(model.contact_id == contact_id).update(
                {model.contact_id: None}, synchronize_session=False
            )
    except Exception:  # noqa: BLE001
        pass

    try:
        db.delete(contact)
        db.commit()
    except Exception as e:  # noqa: BLE001 — alguna FK no desvinculada bloquea el borrado
        db.rollback()
        logger.error("Error eliminando contacto", contact_id=contact_id, error=str(e))
        raise HTTPException(
            status_code=409,
            detail="No se pudo eliminar: el contacto tiene registros vinculados. "
                   "Avisá al equipo para revisar.",
        )

    # Limpiar el cache en RAM del agente para cada session_id borrado, así el hilo no
    # revive desde memoria hasta el próximo reinicio del proceso. Best-effort: un fallo
    # acá no debe revertir el borrado, que ya está confirmado en la BD.
    for sid in deleted_session_ids:
        try:
            from app.services.agent_service import agent_service
            agent_service.clear_history(sid)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo limpiar cache RAM del agente",
                           session_id=sid, error=str(e))
        try:
            from app.services.conversation_state_manager import conversation_state_manager
            conversation_state_manager.clear_state(sid)
        except Exception:  # noqa: BLE001 — estado multi-paso puede no existir
            pass

    return {"success": True, "message": f"Contacto {contact_id} eliminado"}


@router.get("/{contact_id}", response_model=Contact360Response)
async def get_contact_360(
    contact_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene la vista 360° completa de un contacto
    """
    contact_360 = contact_service.get_contact_360(contact_id, db)
    
    if not contact_360:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    return contact_360


@router.get("/{contact_id}/conversations")
async def get_contact_conversations(
    contact_id: int,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Obtiene las conversaciones de un contacto
    """
    from app.models.conversation import Conversation
    
    conversations = db.query(Conversation).filter(
        Conversation.contact_id == contact_id
    ).order_by(
        Conversation.started_at.desc()
    ).limit(limit).offset(offset).all()
    
    total = db.query(Conversation).filter(
        Conversation.contact_id == contact_id
    ).count()
    
    return {
        "conversations": [c.to_dict() for c in conversations],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/{contact_id}/messages")
async def get_contact_messages(
    contact_id: int,
    conversation_id: Optional[int] = Query(None, description="Filtrar por conversación"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Obtiene los mensajes de un contacto
    """
    from app.models.conversation_message import ConversationMessage
    from app.models.conversation import Conversation
    
    query = db.query(ConversationMessage).join(
        Conversation
    ).filter(
        Conversation.contact_id == contact_id
    )
    
    if conversation_id:
        query = query.filter(ConversationMessage.conversation_id == conversation_id)
    
    messages = query.order_by(
        ConversationMessage.created_at.desc()
    ).limit(limit).offset(offset).all()
    
    total = query.count()
    
    return {
        "messages": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/{contact_id}/summary")
async def regenerate_summary(
    contact_id: int,
    force: bool = Query(False, description="Forzar regeneración"),
    db: Session = Depends(get_db)
):
    """
    Regenera el resumen IA de un contacto
    """
    from app.models.contact import Contact
    
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    try:
        summary = await summary_service.generate_contact_summary(
            contact_id=contact_id,
            db=db,
            force=force
        )
        
        if not summary:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate summary"
            )
        
        return {
            "success": True,
            "summary": summary,
            "updated_at": contact.last_summary_update.isoformat() if contact.last_summary_update else None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating summary: {str(e)}"
        )


@router.get("/{contact_id}/metrics")
async def get_contact_metrics(
    contact_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene las métricas actualizadas de un contacto
    """
    from app.models.contact import Contact
    
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    # Actualizar métricas
    contact_service.update_contact_metrics(contact_id, db)
    
    # Refrescar
    db.refresh(contact)
    
    return {
        "contact_id": contact.id,
        "metrics": {
            "total_conversations": contact.total_conversations,
            "total_messages": contact.total_messages,
            "leads_generated": contact.leads_generated,
            "purchases_made": contact.purchases_made,
            "tickets_created": contact.tickets_created
        },
        "contact_type": contact.contact_type,
        "last_interaction": contact.last_interaction_date.isoformat() if contact.last_interaction_date else None
    }


@router.get("/search/by-phone/{phone}")
async def search_by_phone(
    phone: str,
    db: Session = Depends(get_db)
):
    """
    Busca un contacto por teléfono (normalizado)
    """
    contact = contact_service.normalize_and_find_contact(phone, db)
    
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    return contact.to_dict()


@router.get("/stats/overview")
async def get_stats_overview(
    db: Session = Depends(get_db)
):
    """
    Obtiene estadísticas generales de contactos
    Clasificación simple: Lead (nunca compró) vs Cliente (compró al menos 1 vez)
    """
    from app.models.contact import Contact
    from sqlalchemy import func
    
    total_contacts = db.query(Contact).count()
    
    # Clasificación simple basada en purchases_made
    total_leads = db.query(Contact).filter(
        Contact.purchases_made == 0
    ).count()
    
    total_customers = db.query(Contact).filter(
        Contact.purchases_made > 0
    ).count()
    
    # Contactos activos (última interacción en últimos 30 días)
    from datetime import timedelta
    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    active_contacts = db.query(Contact).filter(
        Contact.last_interaction_date >= thirty_days_ago
    ).count()
    
    # Total de conversaciones
    from app.models.conversation import Conversation
    total_conversations = db.query(Conversation).filter(
        Conversation.contact_id.isnot(None)
    ).count()
    
    # Total de mensajes
    from app.models.conversation_message import ConversationMessage
    total_messages = db.query(ConversationMessage).count()
    
    return {
        "total_contacts": total_contacts,
        "total_leads": total_leads,
        "total_customers": total_customers,
        "active_contacts_30d": active_contacts,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "conversion_rate": round((total_customers / total_contacts * 100), 2) if total_contacts > 0 else 0
    }
