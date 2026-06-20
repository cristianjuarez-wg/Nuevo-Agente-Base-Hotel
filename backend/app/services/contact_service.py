"""
Servicio para gestionar contactos - Visión 360°
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.lead import Lead
from app.models.conversation_message import ConversationMessage
from app.utils.phone_normalizer import normalize_phone, extract_country_code
from typing import Optional, Dict, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ContactService:
    """Servicio para gestionar contactos unificados"""
    
    def get_or_create_contact(
        self, 
        phone: str, 
        name: str = None,
        last_name: str = None,
        email: str = None, 
        db: Session = None
    ) -> Optional[Contact]:
        """
        Busca o crea un contacto por teléfono normalizado
        
        Args:
            phone: Número de teléfono (cualquier formato)
            name: Nombre del contacto
            last_name: Apellido del contacto
            email: Email del contacto
            db: Sesión de base de datos
        
        Returns:
            Contact o None si el teléfono es inválido
        """
        if not phone:
            logger.warning("get_or_create_contact: phone is empty")
            return None
        
        # Normalizar teléfono
        phone_normalized = normalize_phone(phone)
        
        if not phone_normalized:
            logger.warning(f"get_or_create_contact: invalid phone {phone}")
            return None
        
        logger.info(f"get_or_create_contact: normalized {phone} -> {phone_normalized}")
        
        # Buscar contacto existente
        contact = db.query(Contact).filter(
            Contact.phone_number == phone_normalized
        ).first()
        
        if contact:
            # Actualizar última interacción
            contact.last_interaction_date = datetime.utcnow()
            
            # Actualizar información si se proporciona y no existe
            if name and not contact.first_name:
                contact.first_name = name
            if last_name and not contact.last_name:
                contact.last_name = last_name
            if email and not contact.email:
                contact.email = email
            
            contact.update_full_name()
            db.commit()
            db.refresh(contact)
            
            logger.info(f"get_or_create_contact: found existing contact_id={contact.id}")
            return contact
        
        # Crear nuevo contacto
        country_code = extract_country_code(phone_normalized)
        
        contact = Contact(
            phone_number=phone_normalized,
            phone_country_code=country_code,
            first_name=name,
            last_name=last_name,
            email=email,
            contact_type='lead'
        )
        contact.update_full_name()
        
        db.add(contact)
        db.commit()
        db.refresh(contact)
        
        logger.info(f"get_or_create_contact: created new contact_id={contact.id}")
        return contact
    
    def normalize_and_find_contact(self, phone: str, db: Session) -> Optional[Contact]:
        """
        Normaliza un teléfono y busca el contacto
        
        Args:
            phone: Número de teléfono
            db: Sesión de base de datos
        
        Returns:
            Contact o None si no existe
        """
        if not phone:
            return None
        
        phone_normalized = normalize_phone(phone)
        if not phone_normalized:
            return None
        
        return db.query(Contact).filter(
            Contact.phone_number == phone_normalized
        ).first()
    
    def update_contact_metrics(self, contact_id: int, db: Session):
        """
        Actualiza todas las métricas del contacto
        
        Args:
            contact_id: ID del contacto
            db: Sesión de base de datos
        """
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            logger.warning(f"update_contact_metrics: contact_id={contact_id} not found")
            return
        
        # Contar conversaciones
        contact.total_conversations = db.query(Conversation).filter(
            Conversation.contact_id == contact_id
        ).count()
        
        # Contar mensajes
        contact.total_messages = db.query(ConversationMessage).join(
            Conversation
        ).filter(
            Conversation.contact_id == contact_id
        ).count()
        
        # Contar leads
        contact.leads_generated = db.query(Lead).filter(
            Lead.contact_id == contact_id
        ).count()
        
        # Contar compras = reservas del hotel (Booking) vinculadas a este Contact.
        # (Antes contaba SoldPackage de turismo, que en el hotel está vacío y dejaba
        #  a todos como 'lead'. La fuente correcta para el hotel son los Bookings.)
        try:
            from app.models.hotel import Booking
            purchases = db.query(Booking).filter(
                Booking.contact_id == contact_id,
                Booking.status != "cancelled",
            ).count()
            # Fallback: si hay bookings históricos sin contact_id, matchear por teléfono.
            if purchases == 0 and contact.phone_number:
                phone_last = contact.phone_number[-10:] if len(contact.phone_number) >= 10 else contact.phone_number
                purchases = db.query(Booking).filter(
                    Booking.guest_phone.like(f'%{phone_last}%'),
                    Booking.status != "cancelled",
                ).count()
            contact.purchases_made = purchases
        except Exception:
            contact.purchases_made = 0
        
        # Contar tickets (si existe la tabla support_tickets) - A través de paquetes
        try:
            from app.models.postsale import SupportTicket, SoldPackage
            if contact.phone_number:
                phone_last_digits = contact.phone_number[-10:] if len(contact.phone_number) >= 10 else contact.phone_number
                # Obtener IDs de paquetes del contacto
                package_ids = db.query(SoldPackage.id).filter(
                    SoldPackage.passenger_phone.like(f'%{phone_last_digits}%')
                ).all()
                package_ids = [pid[0] for pid in package_ids]
                
                if package_ids:
                    contact.tickets_created = db.query(SupportTicket).filter(
                        SupportTicket.package_id.in_(package_ids)
                    ).count()
                else:
                    contact.tickets_created = 0
            else:
                contact.tickets_created = 0
        except:
            contact.tickets_created = 0
        
        # Actualizar tipo de contacto (clasificación simple)
        # Cliente: compró al menos 1 vez (purchases_made > 0)
        # Lead: nunca compró (purchases_made == 0)
        if contact.purchases_made > 0:
            contact.contact_type = 'customer'
        else:
            contact.contact_type = 'lead'
        
        db.commit()
        logger.info(f"update_contact_metrics: contact_id={contact_id} updated")
    
    def link_conversation_to_contact(
        self, 
        conversation_id: int, 
        contact_id: int, 
        db: Session
    ):
        """
        Vincula una conversación a un contacto
        
        Args:
            conversation_id: ID de la conversación
            contact_id: ID del contacto
            db: Sesión de base de datos
        """
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            logger.warning(f"link_conversation_to_contact: conversation_id={conversation_id} not found")
            return
        
        conversation.contact_id = contact_id
        db.commit()
        
        logger.info(f"link_conversation_to_contact: conversation_id={conversation_id} -> contact_id={contact_id}")
    
    def link_conversation_by_session(
        self, 
        session_id: str, 
        contact_id: int, 
        db: Session
    ):
        """
        Vincula una conversación a un contacto usando session_id
        
        Args:
            session_id: ID de la sesión
            contact_id: ID del contacto
            db: Sesión de base de datos
        """
        conversation = db.query(Conversation).filter(
            Conversation.session_id == session_id
        ).first()
        
        if not conversation:
            logger.warning(f"link_conversation_by_session: session_id={session_id} not found")
            return
        
        conversation.contact_id = contact_id
        db.commit()
        
        logger.info(f"link_conversation_by_session: session_id={session_id} -> contact_id={contact_id}")
    
    def get_contact_360(self, contact_id: int, db: Session) -> Optional[Dict]:
        """
        Obtiene la vista 360° completa de un contacto
        
        Args:
            contact_id: ID del contacto
            db: Sesión de base de datos
        
        Returns:
            Diccionario con toda la información del contacto
        """
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            return None
        
        # 🆕 ACTUALIZAR MÉTRICAS AUTOMÁTICAMENTE
        logger.info(f"Updating metrics for contact {contact_id} before loading 360 view")
        self.update_contact_metrics(contact_id, db)
        
        # Refrescar contacto para obtener métricas actualizadas
        db.refresh(contact)
        
        # Obtener conversaciones
        conversations = db.query(Conversation).filter(
            Conversation.contact_id == contact_id
        ).order_by(Conversation.started_at.desc()).all()
        
        # Obtener leads
        leads = db.query(Lead).filter(
            Lead.contact_id == contact_id
        ).order_by(Lead.created_at.desc()).all()
        
        # Obtener paquetes (si existen) - Buscar por teléfono
        packages = []
        try:
            from app.models.postsale import SoldPackage
            # Buscar por teléfono (últimos 10 dígitos para mayor precisión)
            if contact.phone_number:
                phone_last_digits = contact.phone_number[-10:] if len(contact.phone_number) >= 10 else contact.phone_number
                packages = db.query(SoldPackage).filter(
                    SoldPackage.passenger_phone.like(f'%{phone_last_digits}%')
                ).order_by(SoldPackage.created_at.desc()).all()
                logger.info(f"Found {len(packages)} packages for contact {contact_id} by phone")
        except Exception as e:
            logger.error(f"Error getting packages: {e}")
        
        # Obtener tickets (si existen) - A través de paquetes
        tickets = []
        try:
            from app.models.postsale import SupportTicket
            if packages:
                package_ids = [pkg.id for pkg in packages]
                tickets = db.query(SupportTicket).filter(
                    SupportTicket.package_id.in_(package_ids)
                ).order_by(SupportTicket.created_at.desc()).all()
                logger.info(f"Found {len(tickets)} tickets for contact {contact_id}")
        except Exception as e:
            logger.error(f"Error getting tickets: {e}")
        
        return {
            "contact": contact.to_dict(),
            "conversations": [c.to_dict() for c in conversations],
            "leads": [l.to_dict() for l in leads],
            "packages": [p.to_dict() for p in packages] if packages else [],
            "tickets": [t.to_dict() for t in tickets] if tickets else []
        }
    
    def search_contacts(
        self, 
        query: str = None, 
        contact_type: str = None,
        limit: int = 50,
        offset: int = 0,
        db: Session = None
    ) -> List[Contact]:
        """
        Busca contactos con filtros
        
        Args:
            query: Texto de búsqueda (nombre, email, teléfono)
            contact_type: Filtro por tipo ('lead', 'customer', 'both')
            limit: Límite de resultados
            offset: Offset para paginación
            db: Sesión de base de datos
        
        Returns:
            Lista de contactos
        """
        q = db.query(Contact)
        
        # Filtro por tipo
        if contact_type:
            q = q.filter(Contact.contact_type == contact_type)
        
        # Búsqueda por texto
        if query:
            search_filter = (
                Contact.first_name.ilike(f"%{query}%") |
                Contact.last_name.ilike(f"%{query}%") |
                Contact.email.ilike(f"%{query}%") |
                Contact.phone_number.ilike(f"%{query}%")
            )
            q = q.filter(search_filter)
        
        # Ordenar por última interacción
        q = q.order_by(Contact.last_interaction_date.desc())
        
        # Paginación
        q = q.limit(limit).offset(offset)

        return q.all()

    def get_channel(self, contact_id: int, db: Session) -> Optional[str]:
        """Canal preferente del contacto: del último Lead, o derivado de sus reservas.

        Un pasajero puede no tener Lead (reservó directo); en ese caso inferimos el
        canal de la reserva: session_id "wa_" → whatsapp, si no → web.
        """
        lead = (
            db.query(Lead)
            .filter(Lead.contact_id == contact_id)
            .order_by(Lead.created_at.desc())
            .first()
        )
        if lead and lead.channel:
            return lead.channel

        from app.models.hotel import Booking
        booking = (
            db.query(Booking)
            .filter(Booking.contact_id == contact_id)
            .order_by(Booking.created_at.desc())
            .first()
        )
        if booking:
            return "whatsapp" if (booking.session_id or "").startswith("wa_") else "web"
        return None

    def get_guest_profile(self, contact_id: int, db: Session) -> Dict:
        """Perfil 360° del huésped DERIVADO de sus reservas + preferencias guardadas.

        No captura datos nuevos: estadías, habitación preferida, frecuencia, estadía
        activa y gasto salen de los Bookings vinculados (Entrega A). `preferences` es la
        estructura extensible (gustos, servicios, familia) que se llena aparte.
        """
        from app.models.hotel import Booking
        from datetime import date
        import json

        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            return {}

        bookings = (
            db.query(Booking)
            .filter(Booking.contact_id == contact_id, Booking.status != "cancelled")
            .order_by(Booking.check_in.desc())
            .all()
        )

        today = date.today()
        stays = [b.to_dict() for b in bookings]
        # Estadía activa: hoy está dentro de algún rango check_in..check_out.
        active = next(
            (b for b in bookings if b.check_in and b.check_out and b.check_in <= today <= b.check_out),
            None,
        )
        # Habitación preferida: room_type más frecuente.
        room_counts: Dict[str, int] = {}
        for b in bookings:
            rt = b.room.room_type if b.room else None
            if rt:
                room_counts[rt] = room_counts.get(rt, 0) + 1
        preferred_room = max(room_counts, key=room_counts.get) if room_counts else None
        total_spent_usd = round(sum(b.total_price_usd or 0 for b in bookings), 2)

        # preferences es JSON guardado como TEXT.
        prefs = {}
        raw = getattr(contact, "preferences", None)
        if raw:
            try:
                prefs = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                prefs = {}

        return {
            "contact": contact.to_dict(),
            "channel": self.get_channel(contact_id, db),
            "is_staying_now": active is not None,
            "active_stay": active.to_dict() if active else None,
            "stays_count": len(bookings),
            "is_recurring": len(bookings) > 1,
            "first_stay": stays[-1]["check_in"] if stays else None,
            "last_stay": stays[0]["check_in"] if stays else None,
            "preferred_room": preferred_room,
            "total_spent_usd": total_spent_usd,
            "stays": stays,
            "preferences": prefs,
        }

    def set_preferences(self, contact_id: int, preferences: Dict, db: Session) -> bool:
        """Guarda el JSON de preferencias del huésped (gustos, servicios, familia)."""
        import json
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            return False
        contact.preferences = json.dumps(preferences, ensure_ascii=False)
        db.commit()
        return True


# Instancia global reutilizable (mismo patrón que lead_service).
contact_service = ContactService()
