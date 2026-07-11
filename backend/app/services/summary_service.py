"""
Servicio para generar resúmenes IA de contactos - Visión 360°
"""
from sqlalchemy.orm import Session
from app.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.lead import Lead
from datetime import datetime
from typing import Optional
from app.core.llm.openai_client import get_async_openai
import logging
from app.utils.timezone_utils import utcnow_naive

logger = logging.getLogger(__name__)


class SummaryService:
    """Servicio para generar resúmenes IA de contactos"""
    
    def __init__(self, openai_api_key: str = None):
        """
        Inicializa el servicio.

        Args:
            openai_api_key: aceptado por compatibilidad con el llamador; el cliente
                            OpenAI proviene del singleton compartido (misma API key
                            de settings). Ver app/core/openai_client.py.
        """
        self.openai_api_key = openai_api_key
        self.client = get_async_openai()
    
    async def generate_contact_summary(
        self, 
        contact_id: int, 
        db: Session,
        force: bool = False
    ) -> Optional[str]:
        """
        Genera resumen IA del contacto
        
        Args:
            contact_id: ID del contacto
            db: Sesión de base de datos
            force: Forzar regeneración aunque no sea necesario
        
        Returns:
            Resumen generado o None si falla
        """
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            logger.warning(f"generate_contact_summary: contact_id={contact_id} not found")
            return None
        
        # Verificar si necesita actualización
        if not force and not contact.needs_summary_update():
            logger.info(f"generate_contact_summary: contact_id={contact_id} summary is up to date")
            return contact.ai_summary
        
        # Formatear contexto para GPT
        context = self._format_contact_context(contact, db)
        
        if not context:
            logger.warning(f"generate_contact_summary: no context for contact_id={contact_id}")
            return None
        
        try:
            # Llamar a GPT con nueva API
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_FAST,
                messages=[
                    {
                        "role": "system", 
                        "content": "Eres un asistente que genera resúmenes concisos del historial de clientes. "
                                   "Genera un resumen de 2-3 líneas que capture lo más importante: "
                                   "intereses principales, estado actual, y próximos pasos."
                    },
                    {
                        "role": "user", 
                        "content": f"Genera un resumen del siguiente cliente:\n\n{context}"
                    }
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            summary = response.choices[0].message.content.strip()
            
            # Guardar resumen
            contact.ai_summary = summary
            contact.last_summary_update = utcnow_naive()
            db.commit()
            
            logger.info(f"generate_contact_summary: summary generated for contact_id={contact_id}")
            return summary
            
        except Exception as e:
            logger.error(f"generate_contact_summary: error for contact_id={contact_id}: {str(e)}")
            return None
    
    def _format_contact_context(self, contact: Contact, db: Session) -> str:
        """
        Formatea el contexto del contacto para GPT
        
        Args:
            contact: Contacto
            db: Sesión de base de datos
        
        Returns:
            Contexto formateado
        """
        lines = []
        
        # Información básica
        lines.append(f"CONTACTO: {contact.get_display_name()}")
        lines.append(f"Tipo: {contact.contact_type}")
        lines.append(f"Primera interacción: {contact.first_contact_date.strftime('%d/%m/%Y') if contact.first_contact_date else 'N/A'}")
        lines.append(f"Última interacción: {contact.last_interaction_date.strftime('%d/%m/%Y') if contact.last_interaction_date else 'N/A'}")
        lines.append("")
        
        # Métricas
        lines.append("MÉTRICAS:")
        lines.append(f"- Conversaciones: {contact.total_conversations}")
        lines.append(f"- Leads generados: {contact.leads_generated}")
        lines.append(f"- Compras realizadas: {contact.purchases_made}")
        lines.append(f"- Tickets creados: {contact.tickets_created}")
        lines.append("")
        
        # Últimas conversaciones
        conversations = db.query(Conversation).filter(
            Conversation.contact_id == contact.id
        ).order_by(Conversation.started_at.desc()).limit(3).all()
        
        if conversations:
            lines.append("ÚLTIMAS CONVERSACIONES:")
            for conv in conversations:
                date = conv.started_at.strftime('%d/%m/%Y')
                destinations = ', '.join(conv.destinations_mentioned or []) if conv.destinations_mentioned else 'N/A'
                lines.append(f"- {date}: Destinos mencionados: {destinations}")
            lines.append("")
        
        # Últimos leads
        leads = db.query(Lead).filter(
            Lead.contact_id == contact.id
        ).order_by(Lead.created_at.desc()).limit(2).all()
        
        if leads:
            lines.append("LEADS:")
            for lead in leads:
                lines.append(f"- {lead.lead_type}: {lead.main_interest or 'N/A'}")
                if lead.obstacle:
                    lines.append(f"  Obstáculo: {lead.obstacle}")
            lines.append("")
        
        # (Fase 0.2: se retiró el bloque de SoldPackage — modelo de turismo ya inexistente.)

        return "\n".join(lines)
    
    def should_regenerate_summary(self, contact: Contact) -> bool:
        """
        Decide si regenerar resumen
        
        Args:
            contact: Contacto
        
        Returns:
            True si debe regenerarse
        """
        return contact.needs_summary_update()
    
    async def batch_generate_summaries(
        self, 
        db: Session,
        limit: int = 10,
        only_outdated: bool = True
    ):
        """
        Genera resúmenes en lote
        
        Args:
            db: Sesión de base de datos
            limit: Límite de contactos a procesar
            only_outdated: Solo procesar contactos con resúmenes desactualizados
        """
        query = db.query(Contact)
        
        if only_outdated:
            # Contactos sin resumen o desactualizados
            query = query.filter(
                (Contact.ai_summary == None) |
                (Contact.last_summary_update == None) |
                (Contact.last_interaction_date > Contact.last_summary_update)
            )
        
        contacts = query.limit(limit).all()
        
        logger.info(f"batch_generate_summaries: processing {len(contacts)} contacts")
        
        for contact in contacts:
            try:
                await self.generate_contact_summary(contact.id, db, force=False)
            except Exception as e:
                logger.error(f"batch_generate_summaries: error for contact_id={contact.id}: {str(e)}")
                continue
        
        logger.info(f"batch_generate_summaries: completed")


# ── Resumen puntual de una SESIÓN (Fase 4 — handoff a humano) ────────────────────
def summarize_session(session_id: str, db: Session, max_messages: int = 12) -> str:
    """Resumen corto (2-3 líneas) de la conversación en curso, para que un humano que TOMA la
    charla sepa de qué se trata sin leer todo. Se genera UNA vez al derivar (no por turno).

    Sync (las tools del agente corren sync). Usa OPENAI_MODEL_FAST. Fail-open: si algo falla,
    devuelve "" (el humano igual tiene la transcripción). Distinto del ai_summary del CONTACTO:
    esto resume ESTA conversación.
    """
    try:
        rows = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(max_messages)
            .all()
        )
        if not rows:
            return ""
        rows = list(reversed(rows))  # cronológico
        convo = "\n".join(
            f"{'Huésped' if m.role == 'user' else 'Aura'}: {(m.content or '')[:400]}" for m in rows
        )
        from app.core.llm.openai_client import get_sync_openai
        client = get_sync_openai()
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL_FAST,
            messages=[
                {"role": "system", "content":
                    "Resumís, en 2-3 líneas y en español, una conversación entre un huésped de hotel "
                    "y el asistente Aura, para que una PERSONA del equipo la retome. Contá QUÉ necesita "
                    "el huésped, qué se intentó y por qué se deriva. Directo, sin saludos."},
                {"role": "user", "content": f"Conversación:\n{convo}"},
            ],
            max_tokens=140,
            temperature=0.3,
            timeout=20,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001 — el resumen nunca debe romper la derivación
        logger.warning(f"summarize_session falló para {session_id}: {e}")
        return ""
