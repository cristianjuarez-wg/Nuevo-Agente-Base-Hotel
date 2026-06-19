"""
Servicio Post-Venta
Gestiona consultas, problemas y tickets de soporte para paquetes vendidos
"""
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.openai_client import get_async_openai
import json
from app.utils.timezone_utils import now_argentina
from app.models.postsale import SoldPackage, SupportTicket, TicketInteraction
from app.models.provider import Provider
from app.services.package_validator import PackageValidator
from app.services.postsale_vector_store import PostSaleVectorStore
from app.services.escalation_analyzer import escalation_analyzer
from app.services.severity_classifier import severity_classifier
from app.services.voucher_service import voucher_service
from app.services.contact_service import ContactService
from app.services.maps_service import get_maps_service
from app.core.logging_config import get_logger
from app.config import settings
from app.constants import (
    CATEGORY_KEYWORDS,
    CATEGORY_PRIORITY,
    URGENT_KEYWORDS,
    HIGH_KEYWORDS
)
import re

logger = get_logger(__name__)

# Instancia global de ContactService
contact_service = ContactService()


class PostSaleService:
    """Servicio principal de post-venta"""
    
    def __init__(self, db: Session):
        self.db = db
        self.validator = PackageValidator(db)
        self.vector_store = PostSaleVectorStore()
        self.client = get_async_openai()
    
    def classify_intent(self, message: str) -> Dict:
        """
        Clasifica la intención del mensaje
        
        Prioriza keywords de ACCIÓN sobre keywords de UBICACIÓN
        para evitar que "hotel" domine sobre "cambiar hotel"
        
        Returns:
            Dict con: category, priority, is_problem, keywords_found
        """
        message_lower = message.lower()
        
        # PRIMERO: Detectar categorías de ACCIÓN (tienen prioridad)
        action_categories = ["change"]
        for cat in action_categories:
            keywords = CATEGORY_KEYWORDS[cat]
            # Buscar cualquier keyword de acción
            if any(kw in message_lower for kw in keywords):
                logger.info("Action category detected (priority)",
                           category=cat,
                           message_preview=message_lower[:50])
                return self._build_intent_result(cat, message_lower, max_matches=1)
        
        # SEGUNDO: Detectar otras categorías
        category = "general"
        max_matches = 0
        
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if cat in action_categories:
                continue  # Ya revisamos las de acción
            
            matches = sum(1 for kw in keywords if kw in message_lower)
            if matches > max_matches:
                max_matches = matches
                category = cat
        
        return self._build_intent_result(category, message_lower, max_matches)
    
    def _build_intent_result(self, category: str, message_lower: str, max_matches: int) -> Dict:
        """
        Construye el resultado de clasificación de intención
        
        Args:
            category: Categoría detectada
            message_lower: Mensaje en minúsculas
            max_matches: Número de keywords encontradas
            
        Returns:
            Dict con category, priority, is_problem, keywords_found
        """
        # Detectar si es un problema
        problem_indicators = [
            "problema", "error", "no funciona", "no puedo", "ayuda",
            "perdido", "cancelado", "cambio", "modificar"
        ]
        is_problem = any(ind in message_lower for ind in problem_indicators)
        
        # Calcular prioridad
        priority = self._calculate_priority(message_lower)
        
        logger.info("Intent classified",
                   category=category,
                   priority=priority,
                   is_problem=is_problem)
        
        return {
            "category": category,
            "priority": priority,
            "is_problem": is_problem,
            "keywords_found": max_matches
        }
    
    def _calculate_priority(self, message_lower: str) -> str:
        """
        Calcula la prioridad del ticket
        
        Returns:
            urgent, high, medium, low
        """
        # Urgente
        if any(kw in message_lower for kw in URGENT_KEYWORDS):
            return "urgent"
        
        # Alta
        if any(kw in message_lower for kw in HIGH_KEYWORDS):
            return "high"
        
        # Media (por defecto para problemas)
        if any(word in message_lower for word in ["problema", "error", "ayuda"]):
            return "medium"
        
        # Baja (consultas generales)
        return "low"
    
    def _calculate_priority_by_travel_date(self, package: SoldPackage) -> str:
        """
        Ajusta prioridad según cercanía del viaje
        
        Returns:
            urgent, high, medium, low
        """
        if not package.departure_date:
            return "medium"
        
        days_until_travel = (package.departure_date - now_argentina().date()).days
        
        if days_until_travel < 0:
            # Ya está viajando
            return "urgent"
        elif days_until_travel <= 3:
            return "urgent"
        elif days_until_travel <= 7:
            return "high"
        elif days_until_travel <= 30:
            return "medium"
        else:
            return "low"
    
    def update_ticket_category(self, ticket: SupportTicket, new_category: str) -> bool:
        """
        Actualiza la categoría del ticket si la nueva es más prioritaria
        
        Args:
            ticket: Ticket a actualizar
            new_category: Nueva categoría sugerida
            
        Returns:
            True si se actualizó, False si no
        """
        current_priority = CATEGORY_PRIORITY.get(ticket.ticket_category, 0)
        new_priority = CATEGORY_PRIORITY.get(new_category, 0)
        
        if new_priority > current_priority:
            old_category = ticket.ticket_category
            ticket.ticket_category = new_category
            
            logger.info("Ticket category updated",
                       ticket_number=ticket.ticket_number,
                       old_category=old_category,
                       new_category=new_category,
                       old_priority=current_priority,
                       new_priority=new_priority)
            return True
        
        return False
    
    def _map_urgency_to_priority(self, urgency_level: str) -> str:
        """
        Mapea nivel de urgencia del análisis inteligente a prioridad de ticket
        
        Args:
            urgency_level: "critical" | "high" | "medium" | "low"
            
        Returns:
            "urgent" | "high" | "medium" | "low"
        """
        mapping = {
            "critical": "urgent",
            "high": "high",
            "medium": "medium",
            "low": "low"
        }
        return mapping.get(urgency_level, "medium")
    
    def get_or_create_session_ticket(self, session_id: str, package: SoldPackage) -> SupportTicket:
        """
        Obtiene el ticket activo de la sesión o crea uno nuevo.
        El subject y description se actualizan después con update_ticket_with_query().

        LÓGICA: 1 sesión = 1 ticket
        """
        from app.models.postsale import PostSaleSession

        # Buscar sesión
        session = self.db.query(PostSaleSession).filter(
            PostSaleSession.session_id == session_id
        ).first()

        if not session:
            # Crear sesión si no existe
            session = PostSaleSession(
                session_id=session_id,
                package_id=package.id,
                is_active=True,
                validated_at=now_argentina()
            )
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)

        # Si tiene ticket activo, retornarlo
        if session.active_ticket_id:
            ticket = self.db.query(SupportTicket).get(session.active_ticket_id)
            if ticket:
                logger.info("Reusing existing session ticket",
                           ticket_number=ticket.ticket_number,
                           session_id=session_id)
                return ticket

        # Si no tiene ticket, crear uno nuevo
        ticket_number = self._generate_ticket_number()

        ticket = SupportTicket(
            package_id=package.id,
            session_id=session_id,
            ticket_number=ticket_number,
            ticket_subject=f"Consulta general — {package.passenger_name} {package.passenger_lastname}".strip(),
            ticket_category="general",
            priority="medium",
            status="open",
            description=f"Sesión iniciada para reserva {package.booking_code} ({package.package_name})",
            auto_resolved_by_agent=False,
            has_escalated_issues=False,
            auto_resolved_issues_count=0,
            escalated_issues_count=0
        )

        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)

        # Guardar ticket_id en sesión
        session.active_ticket_id = ticket.id
        self.db.commit()

        logger.info("Created new session ticket",
                   ticket_number=ticket.ticket_number,
                   session_id=session_id)

        return ticket

    def update_ticket_with_query(self, ticket: SupportTicket, query: str, category: str = None, priority: str = None):
        """
        Actualiza subject y description del ticket con la consulta real del usuario.
        Se llama una vez que se conoce el problema concreto (post-análisis).
        Solo sobreescribe si el subject todavía es el placeholder inicial.
        """
        changed = False

        if query and "Sesión iniciada" in ticket.description:
            ticket.description = query
            changed = True

        if query and ticket.ticket_subject.startswith("Consulta general —"):
            ticket.ticket_subject = self._generate_subject(category or ticket.ticket_category, query)
            changed = True

        if category and category != ticket.ticket_category:
            self.update_ticket_category(ticket, category)
            changed = True

        if priority:
            priority_order = {"urgent": 4, "high": 3, "medium": 2, "low": 1}
            if priority_order.get(priority, 0) > priority_order.get(ticket.priority, 0):
                ticket.priority = priority
                changed = True

        if changed:
            self.db.commit()
            logger.info("Ticket updated with real query",
                       ticket_number=ticket.ticket_number,
                       category=ticket.ticket_category,
                       priority=ticket.priority)
    
    def create_ticket(self, package: SoldPackage, message: str, session_id: str, 
                     intent: Dict, will_auto_resolve: bool = False) -> SupportTicket:
        """
        Crea un ticket de soporte
        
        Args:
            package: Paquete asociado
            message: Mensaje del usuario
            session_id: ID de sesión
            intent: Intención clasificada
            will_auto_resolve: Si el ticket será auto-resuelto por el agente
            
        Returns:
            Ticket creado
        """
        # Determinar estado inicial según si será auto-resuelto
        if will_auto_resolve:
            status = "resolved"
            resolved_at = now_argentina()
            auto_resolved = True
            resolution_type = "auto_resolved"
        else:
            status = "open"
            resolved_at = None
            auto_resolved = False
            resolution_type = None
        
        # Calcular prioridad final (la más alta entre mensaje y fecha)
        message_priority = intent["priority"]
        date_priority = self._calculate_priority_by_travel_date(package)
        
        priority_order = {"urgent": 4, "high": 3, "medium": 2, "low": 1}
        final_priority = message_priority if priority_order[message_priority] >= priority_order[date_priority] else date_priority
        
        ticket = SupportTicket(
            ticket_number=self._generate_ticket_number(),
            package_id=package.id,
            
            ticket_category=intent["category"],
            priority=final_priority,
            ticket_subject=self._generate_subject(intent["category"], message),
            description=message,
            
            status=status,
            resolved_at=resolved_at,
            auto_resolved_by_agent=auto_resolved,
            resolution_type=resolution_type,
            created_at=now_argentina()
        )
        
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        
        # Crear primera interacción con el mensaje del cliente
        interaction = TicketInteraction(
            ticket_id=ticket.id,
            interaction_type="customer_message",
            message=message,
            created_by=f"{package.passenger_name} {package.passenger_lastname}",
            created_at=now_argentina()
        )
        
        self.db.add(interaction)
        self.db.commit()
        
        logger.info("Ticket created",
                   ticket_number=ticket.ticket_number,
                   package_id=package.id,
                   category=intent["category"],
                   priority=final_priority,
                   status=status,
                   auto_resolved=auto_resolved)
        
        return ticket
    
    def _generate_ticket_number(self) -> str:
        """Genera número único de ticket"""
        timestamp = now_argentina().strftime("%Y%m%d%H%M%S")
        count = self.db.query(SupportTicket).count() + 1
        return f"TKT-{timestamp}-{count:04d}"
    
    def _generate_subject(self, category: str, message: str) -> str:
        """Genera asunto del ticket"""
        category_names = {
            "emergency": "🚨 Emergencia",
            "service_failure": "⚠️ Falla de servicio",
            "complaint": "📢 Queja/Reclamo",
            "change": "🔄 Solicitud de cambio",
            "flight": "✈️ Consulta sobre vuelo",
            "hotel": "🏨 Consulta sobre hotel",
            "transfer": "🚗 Consulta sobre traslado",
            "activity": "🎯 Consulta sobre actividad",
            "documentation": "📄 Consulta sobre documentación",
            "information": "ℹ️ Solicitud de información",
            "general": "💬 Consulta general"
        }
        
        base_subject = category_names.get(category, "Consulta")
        
        # Truncar mensaje si es muy largo
        if len(message) > 50:
            message_preview = message[:47] + "..."
        else:
            message_preview = message
        
        return f"{base_subject}: {message_preview}"
    
    async def analyze_with_intelligence(self, message: str, package: SoldPackage, 
                                       conversation_history: list = None) -> Dict:
        """
        🆕 Análisis inteligente usando GPT para determinar escalación
        Reemplaza la lógica hardcodeada de can_auto_resolve
        
        Returns:
            Dict con análisis completo de escalación
        """
        # Construir información del paquete para el análisis
        package_info = {
            "booking_code": package.booking_code,
            "destination": package.destination_country,
            "departure_date": package.departure_date.isoformat() if package.departure_date else None,
            "return_date": package.return_date.isoformat() if package.return_date else None,
            "travel_status": package.trip_status,
            "passenger_name": f"{package.passenger_name} {package.passenger_lastname}"
        }
        
        # Llamar al analizador inteligente
        analysis = await escalation_analyzer.analyze_escalation_need(
            message=message,
            package_info=package_info,
            conversation_history=conversation_history
        )
        
        return analysis
    
    def can_auto_resolve(self, intent: Dict, message: str) -> bool:
        """
        🔄 DEPRECADO - Mantenido por compatibilidad
        Usar analyze_with_intelligence() para nuevas implementaciones
        
        Determina si el agente puede resolver automáticamente
        
        Returns:
            True si puede auto-resolver
        """
        message_lower = message.lower()
        
        # NUNCA auto-resolver cambios, cancelaciones o modificaciones
        if intent["category"] == "change":
            logger.info("Change request detected, escalating",
                       category=intent["category"])
            return False
        
        # Detectar pérdida o robo de documentos (combinación de palabras)
        loss_keywords = ['perdí', 'perdí', 'perdido', 'robaron', 'robado', 'robo']
        document_keywords = ['pasaporte', 'documento', 'dni', 'identificación']
        
        has_loss = any(kw in message_lower for kw in loss_keywords)
        has_document = any(kw in message_lower for kw in document_keywords)
        
        if has_loss and has_document:
            logger.info("Document loss/theft detected, escalating",
                       message_preview=message[:50])
            return False
        
        # Detectar emergencias médicas o de seguridad
        emergency_keywords = ['accidente', 'hospital', 'policía', 'emergencia médica', 'herido']
        if any(kw in message_lower for kw in emergency_keywords):
            logger.info("Emergency detected, escalating",
                       message_preview=message[:50])
            return False
        
        # Detectar problemas de servicio no entregado (con contexto)
        service_failure_phrases = ['no llegó', 'no aparece', 'no está', 'no vino', 'no apareció']
        service_keywords = ['traslado', 'transfer', 'conductor', 'guía', 'hotel']
        
        has_failure = any(phrase in message_lower for phrase in service_failure_phrases)
        has_service = any(kw in message_lower for kw in service_keywords)
        
        if has_failure and has_service:
            logger.info("Service failure detected, escalating",
                       message_preview=message[:50])
            return False
        
        # Para categorías de INFORMACIÓN: auto-resolver por defecto
        information_categories = ["general", "documentation", "flight", "hotel", 
                                 "transfer", "activity"]
        
        if intent["category"] in information_categories:
            logger.info("Information category, auto-resolving",
                       category=intent["category"],
                       priority=intent["priority"],
                       message_preview=message[:50])
            return True
        
        # Si no es un problema, puede auto-resolverse
        if not intent["is_problem"]:
            return True
        
        # Por defecto, escalar problemas no clasificados
        return False
    
    def resolve_ticket(self, ticket: SupportTicket, resolution: str, 
                      auto_resolved: bool = False):
        """
        Resuelve un ticket
        
        Args:
            ticket: Ticket a resolver
            resolution: Texto de resolución
            auto_resolved: Si fue resuelto automáticamente por el agente
        """
        ticket.status = "resolved"
        ticket.resolution = resolution
        ticket.resolved_at = now_argentina()
        ticket.auto_resolved_by_agent = auto_resolved
        ticket.resolution_type = "auto_resolved" if auto_resolved else "operator_resolved"
        
        # Calcular tiempo de resolución
        if ticket.created_at:
            resolution_time = (now_argentina() - ticket.created_at).total_seconds() / 60
            ticket.resolution_time_minutes = int(resolution_time)
        
        # Agregar interacción de resolución
        interaction = TicketInteraction(
            ticket_id=ticket.id,
            interaction_type="resolution",
            message=resolution,
            created_by="Kami AI" if auto_resolved else "Operator",
            created_at=now_argentina()
        )
        
        self.db.add(interaction)
        self.db.commit()
        
        logger.info("Ticket resolved",
                   ticket_number=ticket.ticket_number,
                   auto_resolved=auto_resolved,
                   resolution_time_minutes=ticket.resolution_time_minutes)
    
    def _save_interaction(
        self,
        ticket: SupportTicket,
        message: str,
        interaction_type: str,
        created_by: str,
        auto_resolved: bool = False,
        requires_escalation: bool = False,
        provider_id: int = None
    ) -> TicketInteraction:
        """
        🆕 Método genérico para guardar cualquier interacción en un ticket
        
        Args:
            ticket: Ticket asociado
            message: Mensaje de la interacción
            interaction_type: Tipo (user_message, agent_response, etc.)
            created_by: Quién creó la interacción
            auto_resolved: Si fue auto-resuelto
            requires_escalation: Si requiere escalación
            provider_id: ID del proveedor relacionado
            
        Returns:
            Interacción creada
        """
        # Contar interacciones para sequence_number
        interaction_count = self.db.query(TicketInteraction).filter(
            TicketInteraction.ticket_id == ticket.id
        ).count()
        
        interaction = TicketInteraction(
            ticket_id=ticket.id,
            interaction_type=interaction_type,
            message=message,
            created_by=created_by,
            created_at=now_argentina(),
            sequence_number=interaction_count + 1,
            auto_resolved=auto_resolved,
            requires_escalation=requires_escalation,
            provider_id=provider_id
        )
        
        self.db.add(interaction)
        self.db.commit()
        self.db.refresh(interaction)
        
        return interaction
    
    def add_agent_response(self, ticket_number: str, response: str):
        """
        Agrega la respuesta del agente a un ticket auto-resuelto
        
        Args:
            ticket_number: Número del ticket
            response: Respuesta generada por el agente
        """
        ticket = self.db.query(SupportTicket).filter(
            SupportTicket.ticket_number == ticket_number
        ).first()
        
        if not ticket:
            logger.warning("Ticket not found for agent response", ticket_number=ticket_number)
            return
        
        # Usar método genérico
        self._save_interaction(
            ticket=ticket,
            message=response,
            interaction_type="agent_response",
            created_by="Kami (Agente IA)"
        )
        
        # Si el ticket fue auto-resuelto, guardar la resolución
        if ticket.auto_resolved_by_agent and not ticket.resolution:
            ticket.resolution = response
            
            # Calcular tiempo de resolución
            if ticket.created_at:
                resolution_time = (now_argentina() - ticket.created_at).total_seconds() / 60
                ticket.resolution_time_minutes = int(resolution_time)
            
            self.db.commit()
        
        logger.info("Agent response added to ticket",
                   ticket_number=ticket_number,
                   auto_resolved=ticket.auto_resolved_by_agent)
    
    def escalate_ticket(self, ticket: SupportTicket, reason: str):
        """
        Escala un ticket a un operador humano
        
        Args:
            ticket: Ticket a escalar
            reason: Razón de la escalación
        """
        ticket.status = "open"  # ✅ Tickets escalados van a "open" para que operador los tome
        ticket.assigned_at = now_argentina()
        
        # Agregar nota de escalación
        interaction = TicketInteraction(
            ticket_id=ticket.id,
            interaction_type="escalation",
            message=f"Ticket escalado a operador humano. Razón: {reason}",
            created_by="System",
            created_at=now_argentina()
        )
        
        self.db.add(interaction)
        self.db.commit()
        
        logger.warning("Ticket escalated",
                      ticket_number=ticket.ticket_number,
                      reason=reason)
    
    async def run_gate(self, message: str, session_id: str, conversation_history: list = None) -> Dict:
        """
        Gate determinístico de post-venta (sin clasificaciones LLM de severidad/escalación).

        Ejecuta SIEMPRE: validación de acceso, vinculación de contacto, atajos de
        voucher/cortesía, y obtención del ticket de sesión. Lo usa el orquestador
        post-venta del Agents SDK para preparar el turno antes del loop de tools.

        Returns un dict con una de estas formas:
          - {"handled": True, "result": <dict respuesta terminal>}  → ya se respondió
            (validación fallida, solo-código, voucher o cortesía); no sigue al orquestador.
          - {"handled": False, "package": SoldPackage, "ticket": SupportTicket,
             "query_to_process": str}  → listo para el loop de tool calling.
        """
        validation = self.validator.validate_access(message, session_id, conversation_history)
        if not validation["valid"]:
            return {"handled": True, "result": {
                "response": validation["message"],
                "requires_validation": True,
                "ticket_created": False,
            }}

        package = validation["package"]

        # Visión 360°: vincular contacto (mismo bloque que handle_message)
        try:
            if package.passenger_phone:
                contact = contact_service.get_or_create_contact(
                    phone=package.passenger_phone,
                    name=package.passenger_name or None,
                    last_name=getattr(package, "passenger_lastname", None) or None,
                    email=getattr(package, "passenger_email", None) or None,
                    db=self.db,
                )
                if contact:
                    if not package.contact_id:
                        package.contact_id = contact.id
                        self.db.commit()
                    contact_service.link_conversation_by_session(session_id, contact.id, self.db)
                    contact_service.update_contact_metrics(contact.id, self.db)
        except Exception as e:
            logger.error("Error linking package to contact (gate)", error=str(e))

        # Buscar consulta original en historial si solo dio el código
        original_query = None
        if validation["method"] == "booking_code" and conversation_history:
            for i in range(len(conversation_history) - 1, -1, -1):
                if conversation_history[i].get("role") == "user":
                    prev = conversation_history[i].get("content", "")
                    if not self.validator.extract_booking_code(prev):
                        original_query = prev
                        break

        query_to_process = original_query if original_query else message

        # Solo código sin consulta → bienvenida determinística
        if not original_query and self.validator.extract_booking_code(message):
            ticket = self.get_or_create_session_ticket(session_id, package)
            self._save_interaction(
                ticket=ticket,
                message=f"Código de reserva proporcionado: {package.booking_code}",
                interaction_type="user_message",
                created_by=f"{package.passenger_name} {package.passenger_lastname}".strip(),
            )
            welcome = f"Hola {package.passenger_name}! Tengo tu reserva para {package.package_name}. ¿En qué puedo ayudarte con tu viaje?"
            self._save_interaction(
                ticket=ticket, message=welcome,
                interaction_type="agent_response", created_by="Kami (Agente IA)",
            )
            return {"handled": True, "result": {
                "response": welcome, "requires_more_info": True,
                "ticket_created": True, "ticket_number": ticket.ticket_number,
            }}

        # Atajos determinísticos: voucher y cortesía
        if self._is_voucher_request(query_to_process):
            return {"handled": True, "result": await self._handle_voucher_request(package, session_id, query_to_process)}
        if self._is_courtesy_message(query_to_process):
            return {"handled": True, "result": await self._handle_courtesy_message(query_to_process, package, session_id)}

        # Listo para el loop de tool calling
        ticket = self.get_or_create_session_ticket(session_id, package)
        self.validator.update_session_activity(session_id)
        return {"handled": False, "package": package, "ticket": ticket, "query_to_process": query_to_process}

    async def handle_message(self, message: str, session_id: str, conversation_history: list = None) -> Dict:
        """
        Maneja un mensaje de post-venta

        Args:
            message: Mensaje del usuario
            session_id: ID de sesión
            conversation_history: Historial de conversación para contexto

        Returns:
            Dict con respuesta y acciones tomadas
        """
        # 1. Validar acceso al paquete (pasar historial para buscar código previo)
        validation = self.validator.validate_access(message, session_id, conversation_history)
        
        if not validation["valid"]:
            return {
                "response": validation["message"],
                "requires_validation": True,
                "ticket_created": False
            }
        
        package = validation["package"]
        
        # 🆕 VISIÓN 360°: Crear/vincular Contact cuando se valida un paquete
        try:
            if package.passenger_phone:
                contact = contact_service.get_or_create_contact(
                    phone=package.passenger_phone,
                    name=package.passenger_name if package.passenger_name else None,
                    last_name=package.passenger_lastname if hasattr(package, 'passenger_lastname') and package.passenger_lastname else None,
                    email=package.passenger_email if hasattr(package, 'passenger_email') and package.passenger_email else None,
                    db=self.db
                )
                
                if contact:
                    # Vincular paquete al contact si no está vinculado
                    if not package.contact_id:
                        package.contact_id = contact.id
                        self.db.commit()
                        logger.info("SoldPackage linked to contact",
                                   package_id=package.id,
                                   contact_id=contact.id,
                                   booking_code=package.booking_code)
                    
                    # Vincular conversación al contact
                    contact_service.link_conversation_by_session(
                        session_id=session_id,
                        contact_id=contact.id,
                        db=self.db
                    )
                    
                    # Actualizar métricas
                    contact_service.update_contact_metrics(contact.id, self.db)
                    
                    logger.info("POST-VENTA contact created/linked",
                               contact_id=contact.id,
                               booking_code=package.booking_code,
                               session_id=session_id)
        except Exception as e:
            logger.error("Error linking package to contact",
                        package_id=package.id,
                        error=str(e))
            # No fallar si hay error en la vinculación
        
        # 2. Si acaba de validar el código, buscar consulta original en el historial
        original_query = None
        if validation["method"] == "booking_code" and conversation_history:
            # Buscar el último mensaje del usuario antes de dar el código
            for i in range(len(conversation_history) - 1, -1, -1):
                if conversation_history[i].get("role") == "user":
                    prev_message = conversation_history[i].get("content", "")
                    # Si no es el código mismo, es la consulta original
                    if not self.validator.extract_booking_code(prev_message):
                        original_query = prev_message
                        logger.info("Original query found in history",
                                   original_query=original_query[:50])
                        break
        
        # 3. Usar la consulta original si existe, sino el mensaje actual
        query_to_process = original_query if original_query else message
        
        # 3.5. Si solo dio el código sin consulta, pedir más información
        if not original_query and self.validator.extract_booking_code(message):
            logger.info("User only provided booking code without query",
                       booking_code=message)
            
            # 🆕 Guardar interacción de validación
            ticket = self.get_or_create_session_ticket(session_id, package)
            
            self._save_interaction(
                ticket=ticket,
                message=f"Código de reserva proporcionado: {package.booking_code}",
                interaction_type="user_message",
                created_by=f"{package.passenger_name} {package.passenger_lastname}".strip(),
                auto_resolved=False,
                requires_escalation=False
            )
            
            welcome_response = f"Hola {package.passenger_name}! Tengo tu reserva para {package.package_name}. ¿En qué puedo ayudarte con tu viaje?"
            
            self._save_interaction(
                ticket=ticket,
                message=welcome_response,
                interaction_type="agent_response",
                created_by="Kami (Agente IA)",
                auto_resolved=False,
                requires_escalation=False
            )
            
            return {
                "response": welcome_response,
                "requires_more_info": True,
                "ticket_created": True,
                "ticket_number": ticket.ticket_number
            }
        
        # 3.6. 🆕 DETECTAR SI PIDE VOUCHER (antes de clasificar severidad)
        if self._is_voucher_request(query_to_process):
            return await self._handle_voucher_request(package, session_id, query_to_process)
        
        # 3.7. 🆕 DETECTAR SI ES MENSAJE DE CORTESÍA (gracias, despedida)
        if self._is_courtesy_message(query_to_process):
            return await self._handle_courtesy_message(query_to_process, package, session_id)
        
        # 4. 🆕 CLASIFICACIÓN DE SEVERIDAD (nueva fase de indagación)
        severity_result = None
        try:
            # Primero clasificar intención básica
            intent_basic = self.classify_intent(query_to_process)
            
            # Clasificar severidad con GPT
            package_info = {
                "destination": package.destination_country,
                "departure_date": package.departure_date.isoformat() if package.departure_date else None,
                "travel_status": package.trip_status
            }
            
            severity_result = await severity_classifier.classify_severity(
                message=query_to_process,
                category=intent_basic["category"],
                package_info=package_info,
                conversation_history=conversation_history  # ✅ Pasar historial completo
            )
            
            logger.info("Severity classified",
                       severity=severity_result.get("severity"),
                       suggested_action=severity_result.get("suggested_action"),
                       message_preview=query_to_process[:50])
            
            # 🆕 Si necesita clarificación, pedir más detalles
            if severity_result.get("severity") == "needs_clarification":
                clarification_msg = severity_classifier.generate_clarification_response(
                    category=intent_basic["category"],
                    questions=severity_result.get("clarification_questions")
                )
                
                logger.info("Requesting clarification from user",
                           category=intent_basic["category"],
                           message_preview=query_to_process[:50])
                
                # 🆕 Guardar interacción de clarificación
                ticket = self.get_or_create_session_ticket(session_id, package)
                
                self._save_interaction(
                    ticket=ticket,
                    message=query_to_process,
                    interaction_type="user_message",
                    created_by=f"{package.passenger_name} {package.passenger_lastname}".strip(),
                    auto_resolved=False,
                    requires_escalation=False
                )
                
                self._save_interaction(
                    ticket=ticket,
                    message=clarification_msg,
                    interaction_type="agent_response",
                    created_by="Kami (Agente IA)",
                    auto_resolved=False,
                    requires_escalation=False
                )
                
                return {
                    "response": clarification_msg,
                    "requires_more_info": True,
                    "ticket_created": True,
                    "ticket_number": ticket.ticket_number,
                    "severity": "needs_clarification"
                }
            
        except Exception as e:
            logger.error("Error in severity classification",
                        error=str(e),
                        message_preview=query_to_process[:50])
            # Continuar con análisis de escalación normal
        
        # 4.5. 🆕 ANÁLISIS INTELIGENTE con GPT (solo si no es informational)
        try:
            escalation_analysis = await self.analyze_with_intelligence(
                message=query_to_process,
                package=package,
                conversation_history=conversation_history
            )
            
            # 🆕 Sobrescribir con resultado de severidad si existe
            if severity_result:
                # Mapear severidad a escalación
                if severity_result["severity"] == "informational":
                    escalation_analysis["requires_escalation"] = False
                    escalation_analysis["urgency_level"] = "low"
                elif severity_result["severity"] == "minor":
                    escalation_analysis["requires_escalation"] = False
                    escalation_analysis["urgency_level"] = "low"
                    escalation_analysis["suggested_action"] = "contact_provider"
                elif severity_result["severity"] == "moderate":
                    escalation_analysis["requires_escalation"] = True
                    escalation_analysis["urgency_level"] = "medium"
                elif severity_result["severity"] == "major":
                    escalation_analysis["requires_escalation"] = True
                    escalation_analysis["urgency_level"] = "high"
                
                escalation_analysis["severity_reasoning"] = severity_result.get("reasoning", "")
                
        except Exception as e:
            import traceback
            logger.error("Error in intelligent analysis, using SAFE fallback (escalate)",
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc())
            # 🆕 FALLBACK SEGURO: Escalar por defecto cuando falla el análisis
            # Es mejor escalar de más que auto-resolver casos críticos
            escalation_analysis = {
                "requires_escalation": True,
                "urgency_level": "high",
                "suggested_category": "general",
                "escalation_reason": "Análisis inteligente falló - escalando por seguridad",
                "key_issues": ["análisis_fallido"],
                "recommended_response_tone": "professional_reassuring"
            }
        
        # 4.5. 🆕 CHEQUEO ESPECIAL: Consultas de vuelos con problemas detectados
        if "flight" in escalation_analysis.get("suggested_category", ""):
            flight_status = self._get_flight_status_with_monitoring(package, query_to_process)
            
            # Si hay problemas reales detectados, FORZAR escalación
            if flight_status["has_issues"]:
                escalation_analysis["requires_escalation"] = True
                escalation_analysis["urgency_level"] = "high"
                issue_descriptions = [f"{i['issue_type']} en {i['flight']}" for i in flight_status["issues"]]
                escalation_analysis["escalation_reason"] = f"Problema detectado en vuelo: {', '.join(issue_descriptions)}"
                
                logger.warning("Flight issue detected - forcing escalation",
                              issues=flight_status["issues"],
                              query=query_to_process[:100])
        
        # 5. Determinar si puede auto-resolver basado en análisis inteligente
        can_auto = not escalation_analysis["requires_escalation"]
        
        logger.info("Escalation analysis result",
                   requires_escalation=escalation_analysis["requires_escalation"],
                   urgency_level=escalation_analysis["urgency_level"],
                   can_auto_resolve=can_auto,
                   query=query_to_process[:100])
        
        # 6. Construir intent mejorado con análisis inteligente
        suggested_category = escalation_analysis["suggested_category"]
        base_priority = self._map_urgency_to_priority(escalation_analysis["urgency_level"])
        
        # 🔥 OVERRIDE: Categorías críticas siempre tienen prioridad urgent
        if suggested_category in ["emergency", "service_failure"]:
            final_priority = "urgent"
        else:
            final_priority = base_priority
        
        intent = {
            "category": suggested_category,
            "priority": final_priority,
            "escalation_reason": escalation_analysis.get("escalation_reason", ""),
            "key_issues": escalation_analysis.get("key_issues_detected", []),
            "recommended_tone": escalation_analysis.get("recommended_response_tone", "standard")
        }
        
        # 7. 🆕 NUEVA LÓGICA: Obtener o crear ticket único de la sesión
        ticket = self.get_or_create_session_ticket(session_id, package)
        
        # 8. 🆕 Contar interacciones para sequence_number
        from app.models.postsale import PostSaleSession
        interaction_count = self.db.query(TicketInteraction).filter(
            TicketInteraction.ticket_id == ticket.id
        ).count()
        
        # 9. 🆕 Identificar proveedor relacionado
        provider_id = self._identify_provider_for_interaction(
            package=package,
            category=intent["category"],
            message=query_to_process
        )
        
        # Obtener proveedor si existe
        provider = None
        if provider_id:
            provider = self.db.query(Provider).filter(Provider.id == provider_id).first()
        
        # Determinar si mostrar contacto del proveedor
        show_provider_contact = False
        if provider:
            show_provider_contact = await self._should_show_provider_contact(
                message=query_to_process,
                escalation_analysis=escalation_analysis,
                conversation_history=conversation_history
            )
        
        # 9.5. 🆕 Crear interacción con nuevos campos (incluyendo proveedor)
        requires_escalation = not can_auto
        interaction = TicketInteraction(
            ticket_id=ticket.id,
            interaction_type="user_message",
            message=query_to_process,
            created_by=f"{package.passenger_name} {package.passenger_lastname}",
            channel="chat",
            interaction_category=intent["category"],
            requires_escalation=requires_escalation,
            auto_resolved=can_auto,
            sequence_number=interaction_count + 1,
            provider_id=provider_id,  # 🆕 Proveedor asociado
            provider_contact_shown=show_provider_contact,  # 🆕 Si se mostró contacto
            created_at=now_argentina()
        )
        
        self.db.add(interaction)
        
        # 9.5. 🆕 Actualizar categoría del ticket si es más prioritaria
        self.update_ticket_category(ticket, intent["category"])
        
        # 10. 🆕 Actualizar contadores y estado del ticket
        if requires_escalation:
            ticket.has_escalated_issues = True
            ticket.escalated_issues_count += 1
            ticket.auto_resolved_by_agent = False
            
            # 🆕 Asignar proveedor al ticket si requiere escalación
            if provider_id and not ticket.provider_id:
                ticket.provider_id = provider_id
                logger.info("Provider assigned to ticket",
                           ticket_id=ticket.id,
                           provider_id=provider_id)
            
            # Si el ticket no está cerrado/resuelto, ponerlo en "open"
            if ticket.status not in ["resolved", "closed"]:
                ticket.status = "open"
        else:
            ticket.auto_resolved_issues_count += 1
            interaction.resolved_at = now_argentina()
            
            # Si NO tiene issues escalados, marcar como resuelto
            if not ticket.has_escalated_issues:
                ticket.status = "resolved"
                ticket.auto_resolved_by_agent = True
        
        # 11. 🆕 Actualizar sesión
        session = self.db.query(PostSaleSession).filter(
            PostSaleSession.session_id == session_id
        ).first()
        
        if session:
            if requires_escalation:
                session.has_escalated_issues = True
                session.escalated_count += 1
            else:
                session.auto_resolved_count += 1

            session.last_interaction = now_argentina()
            # total_messages lo incrementa update_session_activity() al final del método

        self.db.commit()
        
        response_data = {
            "package": package.to_dict(),
            "ticket_number": ticket.ticket_number,
            "ticket_created": True,
            "priority": ticket.priority,
            "category": ticket.ticket_category,
            "can_auto_resolve": can_auto,
            "auto_resolved_count": ticket.auto_resolved_issues_count,
            "escalated_count": ticket.escalated_issues_count
        }
        
        if can_auto:
            # El agente intentará responder con contexto del paquete
            response_data["package_context"] = self._build_package_context(package)
            response_data["response"] = self._build_auto_response(package, intent, query_to_process)
            response_data["status"] = "auto_resolving"
            response_data["use_package_context"] = True
            response_data["answered_original_query"] = original_query is not None
            
            # 🆕 Agregar información del proveedor si se debe mostrar contacto
            if provider and show_provider_contact:
                provider_response = self._build_provider_response(provider, True, package)
                response_data["response"] += provider_response
                logger.info("Provider contact shown to client",
                           provider_id=provider_id,
                           provider_name=provider.provider_name)
            
            # Agregar interacción de auto-resolución
            # Nota: La respuesta final del LLM se agregará después en agent_service
            logger.info("Ticket auto-resolved by agent",
                       ticket_number=ticket.ticket_number,
                       category=ticket.ticket_category)
        else:
            # Escalar a operador
            self.escalate_ticket(ticket, f"Prioridad {ticket.priority} o requiere intervención humana")
            response_data["response"] = await self._build_escalation_response(
                ticket=ticket,
                message=query_to_process,
                escalation_analysis=escalation_analysis,
                package=package
            )
            response_data["status"] = "escalated"
            
            # 🆕 Agregar información del proveedor (sin contacto)
            if provider:
                provider_response = self._build_provider_response(provider, False, package)
                response_data["response"] += provider_response
                logger.info("Provider info added (no contact)",
                           provider_id=provider_id,
                           provider_name=provider.provider_name)
        
        # Actualizar actividad de sesión
        self.validator.update_session_activity(session_id)
        
        return response_data
    
    def _build_package_context(self, package: SoldPackage) -> str:
        """Construye contexto con información del paquete para el LLM"""
        context_parts = [
            f"INFORMACIÓN DEL PAQUETE {package.booking_code}:",
            f"Pasajero: {package.passenger_name}",
            f"Paquete: {package.package_name}",
            f"Destino: {package.destination_country}",
            f"Duración: {package.duration_days} días",
            f"Salida: {package.departure_date}",
            f"Regreso: {package.return_date}",
            ""
        ]
        
        # VUELOS (con estado de monitoreo si está disponible)
        if package.flights:
            context_parts.append("VUELOS:")
            
            # 🆕 Obtener estado de monitoreo
            flight_status = self._get_flight_status_with_monitoring(package, "estado vuelo")
            
            for flight_info in flight_status["flights"]:
                flight = flight_info["flight"]
                flight_type = "IDA" if flight.flight_type == "outbound" else "REGRESO"
                
                # Info básica
                info = (
                    f"- {flight_type}: {flight.airline} {flight.flight_number}, "
                    f"Sale {flight.departure_datetime.strftime('%d/%m/%Y %H:%M')} desde {flight.departure_airport_code}, "
                    f"Llega {flight.arrival_datetime.strftime('%d/%m/%Y %H:%M')} a {flight.arrival_airport_code}, "
                    f"Asientos: {flight.seat_numbers or 'Por asignar'}, "
                    f"Equipaje: {flight.baggage_allowance}"
                )
                
                # 🆕 Agregar estado si viene de monitoreo
                if flight_info["source"] == "monitoring":
                    status_es = self._translate_flight_status(flight_info['status'])
                    info += f"\n  📊 ESTADO ACTUAL: {status_es}"
                    if flight_info["delay"] > 0:
                        info += f" - ⚠️ RETRASADO {flight_info['delay']} minutos"
                    if flight_info["gate"]:
                        info += f" - Puerta: {flight_info['gate']}"
                    if flight_info["terminal"]:
                        info += f" - Terminal: {flight_info['terminal']}"
                        
                        # 🆕 Generar link de Google Maps para la terminal
                        try:
                            maps_service = get_maps_service(self.db)
                            maps_link = maps_service.get_terminal_maps_link(
                                airport_iata=flight.departure_airport_code,
                                terminal_code=flight_info["terminal"],
                                airport_name=flight.departure_airport_name
                            )
                            
                            if maps_link:
                                info += f"\n  📍 Ubicación de Terminal: {maps_link['maps_url']}"
                                info += f"\n  💡 {maps_link['instructions']}"
                        except Exception as e:
                            logger.warning(f"Error generando link de maps: {e}")
                    if flight_info["last_checked"]:
                        info += f"\n  Última actualización: {flight_info['last_checked'].strftime('%d/%m/%Y %H:%M')}"
                
                context_parts.append(info)
            
            context_parts.append("")
        
        # HOTELES
        if package.accommodations:
            context_parts.append("HOTELES:")
            for hotel in package.accommodations:
                hotel_info = (
                    f"- {hotel.hotel_name} ({hotel.hotel_category}) en {hotel.city}, "
                    f"📍 Dirección: {hotel.address}, "
                    f"Check-in: {hotel.checkin_date}, Check-out: {hotel.checkout_date}, "
                    f"{hotel.nights_count} noches, {hotel.room_type}, {hotel.meal_plan}"
                )
                
                # Agregar Google Maps si existe
                if hotel.google_maps_url:
                    hotel_info += f"\n  🗺️ Google Maps: {hotel.google_maps_url}"
                
                # 🆕 Agregar información del proveedor si existe
                if hotel.provider:
                    provider = hotel.provider
                    hotel_info += f"\n  Proveedor: {provider.provider_name}"
                    
                    if provider.primary_phone_number:
                        phone = provider.get_formatted_phone()
                        hotel_info += f"\n  📞 Teléfono: {phone}"
                    
                    if provider.whatsapp_number:
                        whatsapp = provider.get_formatted_whatsapp()
                        hotel_info += f"\n  💬 WhatsApp: {whatsapp}"
                    
                    if provider.primary_email:
                        hotel_info += f"\n  📧 Email: {provider.primary_email}"
                    
                    if provider.operates_24_7:
                        hotel_info += "\n  ⏰ Servicio 24/7 disponible"
                
                context_parts.append(hotel_info)
            context_parts.append("")
        
        # TRASLADOS
        if package.transfers:
            context_parts.append("TRASLADOS:")
            for transfer in package.transfers:
                transfer_info = (
                    f"- {transfer.transfer_type}: {transfer.transfer_date} a las {transfer.pickup_time}, "
                    f"Desde {transfer.pickup_location} hasta {transfer.dropoff_location}, "
                    f"{transfer.vehicle_type}"
                )
                
                # 🆕 Agregar información del proveedor si existe
                if transfer.provider:
                    provider = transfer.provider
                    transfer_info += f"\n  Proveedor: {provider.provider_name}"
                    
                    if provider.primary_phone_number:
                        phone = provider.get_formatted_phone()
                        transfer_info += f"\n  📞 Teléfono: {phone}"
                    
                    if provider.whatsapp_number:
                        whatsapp = provider.get_formatted_whatsapp()
                        transfer_info += f"\n  💬 WhatsApp: {whatsapp}"
                    
                    if provider.primary_email:
                        transfer_info += f"\n  📧 Email: {provider.primary_email}"
                    
                    if provider.operates_24_7:
                        transfer_info += "\n  ⏰ Servicio 24/7 disponible"
                
                context_parts.append(transfer_info)
            context_parts.append("")
        
        # ACTIVIDADES
        if package.activities:
            context_parts.append("ACTIVIDADES:")
            for activity in package.activities:
                activity_info = (
                    f"- {activity.activity_name} en {activity.city}, "
                    f"{activity.activity_date} a las {activity.start_time}, "
                    f"Duración: {activity.duration_hours}h, "
                    f"Punto de encuentro: {activity.meeting_point}"
                )
                
                # 🆕 Agregar información del proveedor si existe
                if activity.provider:
                    provider = activity.provider
                    activity_info += f"\n  Proveedor: {provider.provider_name}"
                    
                    if provider.primary_phone_number:
                        phone = provider.get_formatted_phone()
                        activity_info += f"\n  📞 Teléfono: {phone}"
                    
                    if provider.whatsapp_number:
                        whatsapp = provider.get_formatted_whatsapp()
                        activity_info += f"\n  💬 WhatsApp: {whatsapp}"
                    
                    if provider.primary_email:
                        activity_info += f"\n  📧 Email: {provider.primary_email}"
                    
                    if provider.operates_24_7:
                        activity_info += "\n  ⏰ Servicio 24/7 disponible"
                
                context_parts.append(activity_info)
            context_parts.append("")
        
        # ITINERARIO
        if package.itinerary:
            context_parts.append("ITINERARIO:")
            for day in package.itinerary[:3]:  # Solo primeros 3 días para no saturar
                context_parts.append(
                    f"- Día {day.day_number} ({day.day_title}) en {day.city}: "
                    f"Mañana: {day.morning_activities[:100]}..."
                )
            if len(package.itinerary) > 3:
                context_parts.append(f"... y {len(package.itinerary) - 3} días más")
        
        return "\n".join(context_parts)
    
    def _build_auto_response(self, package: SoldPackage, intent: Dict, message: str) -> str:
        """Construye respuesta automática con contexto del paquete"""
        # Construir contexto con datos reales
        package_context = self._build_package_context(package)
        
        # Crear prompt para el LLM con el contexto
        response_prompt = f"""{package_context}

CONSULTA DEL USUARIO: {message}

INSTRUCCIONES:
- Responde la consulta del usuario usando ÚNICAMENTE la información proporcionada arriba
- Sé específico y proporciona los datos exactos (horarios, códigos, nombres)
- Si la información no está disponible, indícalo claramente
- Mantén un tono amable y profesional
- No inventes información que no esté en el contexto
"""
        
        return response_prompt
    
    async def _build_escalation_response(self, ticket: SupportTicket, message: str, escalation_analysis: Dict, package: SoldPackage) -> str:
        """
        🆕 Usa GPT para construir respuesta empática y personalizada según el problema específico
        
        Args:
            ticket: Ticket creado
            message: Mensaje original del usuario
            escalation_analysis: Análisis de escalación
            package: Paquete del cliente
            
        Returns:
            Respuesta personalizada y empática
        """
        try:
            # Mapeo de emojis por categoría
            category_emojis = {
                "emergency": "🚨",
                "service_failure": "😟",
                "change": "📝",
                "flight": "✈️",
                "hotel": "🏨",
                "transfer": "🚗",
                "activity": "🎯",
                "documentation": "📄",
                "general": "💬"
            }
            
            emoji = category_emojis.get(ticket.ticket_category, "💬")
            
            # Determinar tiempo de respuesta
            response_time_map = {
                "urgent": "**de inmediato** (en minutos)",
                "high": "**en las próximas horas**",
                "medium": "**en breve** (dentro del día)",
                "low": "**a la brevedad** (24-48 horas)"
            }
            response_time = response_time_map.get(ticket.priority, "pronto")
            
            prompt = f"""Eres un agente de soporte al cliente empático y profesional de una agencia de viajes.

SITUACIÓN:
- Problema del cliente: "{message}"
- Categoría: {ticket.ticket_category}
- Prioridad: {ticket.priority}
- Análisis: {escalation_analysis.get('escalation_reason', 'Problema requiere atención')}
- Destino: {package.destination_country}
- Fecha de viaje: {package.departure_date.strftime('%d/%m/%Y') if package.departure_date else 'N/A'}
- Número de ticket: {ticket.ticket_number}

TAREA:
Redacta un mensaje de escalación que sea:
1. EMPÁTICO y reconozca el problema ESPECÍFICO (no genérico)
2. TRANQUILIZADOR explicando que se creó un ticket
3. CLARO sobre tiempo de respuesta
4. PROFESIONAL pero cercano

ESTRUCTURA REQUERIDA:
{emoji} [Reconocimiento empático del problema específico del cliente]

**[Acción tomada con prioridad {ticket.priority.upper()}]** y nuestro equipo te contactará {response_time}.

📋 **Número de ticket:** `{ticket.ticket_number}`

[Mensaje tranquilizador sobre seguimiento]

{"[Si es urgente: agregar recordatorio de teléfono disponible]" if ticket.priority == "urgent" else ""}

IMPORTANTE:
- NO uses lenguaje genérico tipo "tu consulta", "el inconveniente"
- Menciona el PROBLEMA ESPECÍFICO que reportó
- Adapta el TONO a la gravedad (urgente = más serio, bajo = más tranquilo)
- Sé CONCISO pero completo (máximo 8 líneas)
- USA formato markdown para negritas

EJEMPLO de lo que NO hacer:
"Entiendo tu consulta. He creado un ticket."

EJEMPLO de lo que SÍ hacer:
"Lamento muchísimo que tu traslado no haya llegado al hotel. Entiendo lo frustrante que debe ser estar esperando sin transporte."

Genera SOLO el mensaje, sin introducción ni comentarios adicionales."""

            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Eres un experto en atención al cliente de turismo. Redactas mensajes empáticos y profesionales, siempre personalizados al problema específico."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=400,
                timeout=15
            )
            
            escalation_message = response.choices[0].message.content.strip()
            
            logger.info("Escalation message generated with GPT",
                       ticket_number=ticket.ticket_number,
                       priority=ticket.priority,
                       category=ticket.ticket_category,
                       message_length=len(escalation_message))
            
            return escalation_message
            
        except Exception as e:
            logger.error("Error generating escalation message with GPT, using fallback",
                        error=str(e),
                        ticket_number=ticket.ticket_number)
            
            # Fallback: respuesta básica pero funcional
            emoji = category_emojis.get(ticket.ticket_category, "💬")
            response_time = response_time_map.get(ticket.priority, "pronto")
            
            fallback_message = f"""{emoji} He recibido tu consulta y entiendo tu situación.

**He creado un ticket de prioridad {ticket.priority.upper()}** y nuestro equipo te contactará {response_time}.

📋 **Número de ticket:** `{ticket.ticket_number}`

Puedes usar este número para hacer seguimiento. Nuestro equipo tiene toda la información de tu reserva y trabajará para ayudarte lo antes posible."""

            if ticket.priority == "urgent":
                fallback_message += "\n\n⚠️ **Por favor mantén tu teléfono disponible** para que podamos contactarte rápidamente."
            
            return fallback_message
    
    def get_package_info(self, package_id: int) -> Optional[Dict]:
        """Obtiene información completa de un paquete"""
        package = self.db.query(SoldPackage).get(package_id)
        
        if not package:
            return None
        
        return {
            "package": package.to_dict(),
            "flights": [f.id for f in package.flights],
            "hotels": [h.id for h in package.accommodations],
            "transfers": [t.id for t in package.transfers],
            "activities": [a.id for a in package.activities],
            "documents": [d.id for d in package.documents]
        }
    
    def _translate_flight_status(self, status: str) -> str:
        """
        🆕 Traduce el estado del vuelo de inglés a español
        
        Args:
            status: Estado en inglés
            
        Returns:
            Estado en español
        """
        translations = {
            "scheduled": "PROGRAMADO",
            "active": "EN VUELO",
            "landed": "ATERRIZÓ",
            "cancelled": "CANCELADO",
            "diverted": "DESVIADO",
            "incident": "INCIDENTE",
            "delayed": "RETRASADO",
            "departed": "DESPEGÓ",
            "arrived": "LLEGÓ",
            "on_time": "A TIEMPO",
            "early": "ADELANTADO",
            "unknown": "DESCONOCIDO"
        }
        
        # Si no está en el diccionario, devolver en mayúsculas
        return translations.get(status.lower(), status.upper())
    
    def _get_flight_status_with_monitoring(self, package: SoldPackage, query: str) -> Dict:
        """
        Obtiene estado de vuelos consultando monitoreo si está disponible
        
        Args:
            package: Paquete del cliente
            query: Consulta del usuario
            
        Returns:
            {
                "source": "monitoring" | "package",
                "flights": [...],
                "has_issues": bool,
                "issues": [...],
                "last_checked": datetime
            }
        """
        from app.models.postsale import PackageFlight
        from app.models.flight_tracking import FlightStatusTracking
        
        # Detectar si pregunta por estado/cambios
        status_keywords = ["estado", "cambios", "retrasado", "delay", "retraso",
                          "cancelado", "puerta", "gate", "terminal", "problema",
                          "actualización", "novedad", "modificación"]
        is_status_query = any(kw in query.lower() for kw in status_keywords)
        
        flights_info = []
        has_issues = False
        issues = []
        
        now = now_argentina()
        
        for flight in package.flights:
            hours_until = (flight.departure_datetime - now).total_seconds() / 3600
            
            # ¿Está en ventana de monitoreo? (48hs antes, 6hs después)
            if -6 <= hours_until <= 48 and is_status_query:
                # Buscar último chequeo
                last_check = self.db.query(FlightStatusTracking).filter(
                    FlightStatusTracking.flight_id == flight.id
                ).order_by(FlightStatusTracking.check_timestamp.desc()).first()
                
                if last_check:
                    # Detectar problemas
                    if last_check.has_changes or last_check.departure_delay > 0:
                        has_issues = True
                        issue_type = "delay" if last_check.departure_delay > 0 else "change"
                        issues.append({
                            "flight": flight.flight_number,
                            "issue_type": issue_type,
                            "delay_minutes": last_check.departure_delay,
                            "severity": last_check.change_severity,
                            "status": last_check.flight_status
                        })
                    
                    flights_info.append({
                        "source": "monitoring",
                        "flight": flight,
                        "status": last_check.flight_status,
                        "delay": last_check.departure_delay,
                        "gate": last_check.departure_gate,
                        "terminal": last_check.departure_terminal,
                        "has_changes": last_check.has_changes,
                        "last_checked": last_check.check_timestamp
                    })
                    continue
            
            # Si no hay monitoring, usar info del paquete
            flights_info.append({
                "source": "package",
                "flight": flight,
                "status": "scheduled",
                "delay": 0,
                "has_changes": False,
                "gate": None,
                "terminal": None,
                "last_checked": None
            })
        
        return {
            "flights": flights_info,
            "has_issues": has_issues,
            "issues": issues,
            "source": "monitoring" if any(f["source"] == "monitoring" for f in flights_info) else "package"
        }
    
    # ==================== MÉTODOS DE PROVEEDORES ====================
    
    def _identify_provider_for_interaction(self, package: SoldPackage, category: str, message: str) -> Optional[int]:
        """
        Identificar proveedor relacionado con la interaction
        
        Args:
            package: Paquete del cliente
            category: Categoría de la consulta
            message: Mensaje del usuario
            
        Returns:
            provider_id o None
        """
        message_lower = message.lower()
        
        # Hotel
        if any(word in message_lower for word in ["hotel", "habitación", "alojamiento", "check-in", "check-out", "recepción"]):
            if package.accommodations and len(package.accommodations) > 0:
                return package.accommodations[0].provider_id
        
        # Transfer
        elif any(word in message_lower for word in ["transfer", "traslado", "chofer", "transporte", "pickup", "recogida"]):
            if package.transfers and len(package.transfers) > 0:
                return package.transfers[0].provider_id
        
        # Vuelo
        elif any(word in message_lower for word in ["vuelo", "aerolínea", "avión", "aeropuerto", "boarding", "embarque"]):
            if package.flights and len(package.flights) > 0:
                return package.flights[0].provider_id
        
        # Actividad
        elif any(word in message_lower for word in ["actividad", "tour", "excursión", "visita", "guía"]):
            if package.activities and len(package.activities) > 0:
                return package.activities[0].provider_id
        
        # Si no se identificó por palabras clave, usar categoría
        if category == "hotel" and package.accommodations:
            return package.accommodations[0].provider_id
        elif category == "transfer" and package.transfers:
            return package.transfers[0].provider_id
        elif category == "flight" and package.flights:
            return package.flights[0].provider_id
        elif category == "activity" and package.activities:
            return package.activities[0].provider_id
        
        return None
    
    async def _should_show_provider_contact(self, message: str, escalation_analysis: Dict, conversation_history: list = None) -> bool:
        """
        🆕 Usa GPT para determinar si mostrar contacto del proveedor (contextual e inteligente)
        
        Args:
            message: Mensaje del usuario
            escalation_analysis: Análisis de escalación
            conversation_history: Historial de conversación para contexto
            
        Returns:
            True si debe mostrar contacto, False si no
        """
        try:
            # Construir contexto de conversación
            conversation_context = ""
            if conversation_history and len(conversation_history) > 0:
                recent_history = conversation_history[-2:]  # Últimos 2 mensajes
                conversation_lines = []
                for msg in recent_history:
                    role = "Usuario" if msg.get("role") == "user" else "Asistente"
                    content = msg.get("content", "")[:100]
                    conversation_lines.append(f"{role}: {content}")
                conversation_context = "\n".join(conversation_lines)
            
            prompt = f"""Analiza si debes proporcionar contacto directo del proveedor al cliente.

MENSAJE DEL CLIENTE: "{message}"

SITUACIÓN ANALIZADA: {escalation_analysis.get('escalation_reason', 'Sin análisis previo')}
REQUIERE ESCALACIÓN: {escalation_analysis.get('requires_escalation', False)}

{f"CONVERSACIÓN RECIENTE:{chr(10)}{conversation_context}" if conversation_context else ""}

REGLAS PARA DECIDIR:

✅ DAR CONTACTO SI:
- Pregunta explícitamente por teléfono, email, WhatsApp, contacto
- Consulta información del proveedor (nombre, datos, empresa)
- Consulta simple sobre el servicio (horarios, ubicación)
- Quiere coordinar algo directamente con ellos

❌ NO DAR CONTACTO SI:
- Problema real que requiere nuestra intervención (servicio no entregado)
- Emergencia o situación crítica
- Servicio falló o no funcionó correctamente
- Cliente está reportando un incidente serio

IMPORTANTE:
- Si hay DUDA → DAR contacto (ser permisivo para mejor UX)
- Solo NO dar si es claramente un problema que debemos resolver nosotros

Responde SOLO con JSON válido:
{{
    "show_contact": true/false,
    "reasoning": "Breve explicación de la decisión"
}}"""

            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[
                    {"role": "system", "content": "Eres un experto en servicio al cliente. Decides si proporcionar contacto de proveedores basándote en el contexto completo."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=150,
                timeout=10
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parsear JSON
            start_idx = result_text.find('{')
            end_idx = result_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = result_text[start_idx:end_idx]
                result = json.loads(json_str)
                
                show_contact = result.get("show_contact", True)  # Default: mostrar
                reasoning = result.get("reasoning", "")
                
                logger.info("Provider contact decision made with GPT",
                           show_contact=show_contact,
                           reasoning=reasoning,
                           message_preview=message[:50])
                
                return show_contact
            else:
                logger.warning("No JSON found in GPT response, defaulting to show contact")
                return True
                
        except Exception as e:
            logger.error("Error in GPT provider contact decision, defaulting to show contact",
                        error=str(e),
                        message_preview=message[:50])
            # Fallback seguro: mostrar contacto por defecto
            return True
    
    def _build_provider_response(self, provider: Provider, show_contact: bool, package: SoldPackage) -> str:
        """
        Construir respuesta con información del proveedor
        
        Args:
            provider: Proveedor
            show_contact: Si debe mostrar contacto
            package: Paquete del cliente
            
        Returns:
            Texto de respuesta
        """
        if not provider:
            return ""
        
        response = f"\n\nTu servicio es con **{provider.provider_name}**"
        
        if show_contact:
            # CONSULTA: Dar contacto completo
            response += ":\n\n"
            response += f"📞 **Teléfono:** {provider.get_formatted_phone()}\n"
            
            if provider.whatsapp_number:
                # get_formatted_whatsapp() ya incluye el country code con '+'
                response += f"💬 **WhatsApp:** {provider.get_formatted_whatsapp()}\n"

            if provider.primary_email:
                response += f"📧 **Email:** {provider.primary_email}\n"

            if provider.operates_24_7:
                response += f"\n⏰ Operan 24/7\n"

            response += f"\n**Por favor menciona tu código de reserva:** {package.booking_code}"
        else:
            # PROBLEMA: NO dar contacto
            response += ".\n\n"
            response += "Estamos contactando al proveedor ahora mismo para resolver la situación."
        
        return response
    
    def _is_courtesy_message(self, message: str) -> bool:
        """
        🆕 Detecta si es un mensaje de cortesía (gracias, despedida, etc.)
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            bool: True si es mensaje de cortesía
        """
        message_lower = message.lower()
        
        # Keywords de agradecimiento
        thanks_keywords = [
            "gracias", "muchas gracias", "mil gracias", "te agradezco",
            "agradezco", "excelente", "perfecto", "genial",
            "thank you", "thanks", "ty"
        ]
        
        # Keywords de despedida
        goodbye_keywords = [
            "nada más", "nada mas", "eso es todo", "es todo",
            "listo", "ok", "bueno", "perfecto", "excelente",
            "chau", "adiós", "adios", "hasta luego", "nos vemos",
            "bye", "goodbye", "see you"
        ]
        
        # Verificar si es mensaje muy corto con keyword de cortesía
        is_short = len(message.split()) <= 5
        has_thanks = any(kw in message_lower for kw in thanks_keywords)
        has_goodbye = any(kw in message_lower for kw in goodbye_keywords)
        
        return is_short and (has_thanks or has_goodbye)
    
    def _is_voucher_request(self, message: str) -> bool:
        """
        Detecta si el usuario está pidiendo el voucher
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            bool: True si pide voucher, False en caso contrario
        """
        message_lower = message.lower()
        
        # Keywords de voucher
        voucher_keywords = [
            "voucher", "comprobante", "confirmación", "confirmacion",
            "documento de viaje", "documento del viaje",
            "necesito el voucher", "envíame el voucher", "enviame el voucher",
            "quiero el voucher", "dame el voucher",
            "pdf", "descarga", "descargar"
        ]
        
        # Verificar si contiene keyword de voucher
        has_voucher_keyword = any(kw in message_lower for kw in voucher_keywords)
        
        if not has_voucher_keyword:
            return False
        
        # Evitar falsos positivos: si tiene keywords de otras consultas, NO es voucher.
        # Se usan word boundaries para no matchear substrings dentro de otras palabras
        # (ej: "mal" en "que mal lo mío", o "error" en "errores"), que generaban
        # falsos negativos y hacían que un pedido legítimo de voucher se ignorara.
        other_query_phrases = [
            "cambiar", "modificar", "cancelar", "queja", "reclamo",
            "equivocado", "incorrecto", "no funciona", "está mal", "esta mal",
            "hay un error", "tengo un problema",
        ]

        has_other_query = any(
            re.search(rf"\b{re.escape(kw)}\b", message_lower)
            for kw in other_query_phrases
        )

        if has_other_query:
            logger.info("Voucher keyword detected but has other query keywords",
                       message=message[:50])
            return False
        
        logger.info("Voucher request detected",
                   message=message[:50])
        return True
    
    async def _handle_courtesy_message(
        self,
        message: str,
        package: SoldPackage,
        session_id: str
    ) -> Dict:
        """
        🆕 Maneja mensajes de cortesía (agradecimientos, despedidas)
        
        Args:
            message: Mensaje del usuario
            package: Paquete de la reserva
            session_id: ID de sesión
            
        Returns:
            Dict con respuesta
        """
        logger.info("Handling courtesy message",
                   booking_code=package.booking_code,
                   message=message[:50])
        
        # Obtener o crear ticket de sesión
        ticket = self.get_or_create_session_ticket(session_id, package)
        
        # Guardar mensaje del usuario
        self._save_interaction(
            ticket=ticket,
            message=message,
            interaction_type="user_message",
            created_by=f"{package.passenger_name} {package.passenger_lastname}".strip(),
            auto_resolved=True,
            requires_escalation=False
        )
        
        # Generar respuesta apropiada
        message_lower = message.lower()
        
        if any(kw in message_lower for kw in ["gracias", "thank"]):
            response_text = f"¡De nada, {package.passenger_name}! 😊 Estoy aquí para ayudarte siempre que lo necesites. Te deseo un maravilloso viaje a {package.destination_country}. Si surge cualquier otra consulta, no dudes en contactarme. ¡Que disfrutes mucho tu aventura! ✈️🌍"
        else:
            response_text = f"¡Perfecto, {package.passenger_name}! Si necesitas cualquier cosa durante tu viaje, estaré aquí para ayudarte 24/7. ¡Que tengas un excelente viaje! ✈️😊"
        
        # Guardar respuesta del agente
        self._save_interaction(
            ticket=ticket,
            message=response_text,
            interaction_type="agent_response",
            created_by="Kami (Agente IA)",
            auto_resolved=True,
            requires_escalation=False
        )
        
        # Marcar ticket como resuelto si aún no lo está
        if ticket.status != "resolved":
            ticket.status = "resolved"
            ticket.resolved_at = now_argentina()
            ticket.auto_resolved_by_agent = True
            self.db.commit()
        
        logger.info("Courtesy message handled",
                   booking_code=package.booking_code,
                   ticket_number=ticket.ticket_number)
        
        return {
            "response": response_text,
            "ticket_created": True,
            "ticket_number": ticket.ticket_number,
            "requires_escalation": False,
            "courtesy_message": True
        }
    
    async def _handle_voucher_request(
        self,
        package: SoldPackage,
        session_id: str,
        user_message: str = None
    ) -> Dict:
        """
        🆕 Maneja la solicitud de voucher y guarda la interacción en el ticket

        Args:
            package: Paquete de la reserva
            session_id: ID de sesión
            user_message: Mensaje real del usuario (para guardar en el historial)

        Returns:
            Dict con respuesta y link de descarga
        """
        try:
            logger.info("Handling voucher request",
                       booking_code=package.booking_code,
                       session_id=session_id)

            # 🆕 Obtener o crear ticket de sesión
            ticket = self.get_or_create_session_ticket(session_id, package)

            # 🆕 Guardar solicitud del usuario (usar mensaje real si está disponible)
            self._save_interaction(
                ticket=ticket,
                message=user_message if user_message else "Solicitud de voucher",
                interaction_type="user_message",
                created_by=f"{package.passenger_name} {package.passenger_lastname}".strip(),
                auto_resolved=True,
                requires_escalation=False
            )
            
            # Generar PDF
            pdf_path = await voucher_service.generate_voucher_pdf(
                package.booking_code, 
                self.db
            )
            
            # Construir URL de descarga (archivo estático)
            download_url = f"{settings.BASE_URL}/vouchers/{package.booking_code}.pdf"
            
            # Respuesta del agente
            response_text = f"""¡Por supuesto, {package.passenger_name}! Aquí está tu voucher de viaje:

📄 **Voucher {package.booking_code}**

Puedes descargarlo aquí: {download_url}

Este documento contiene toda la información de tu viaje:
✓ Datos de pasajeros
✓ Vuelos y horarios
✓ Hoteles y traslados
✓ Itinerario completo
✓ Contactos de emergencia

**Importante:** Lleva este voucher impreso o en tu celular el día del viaje.

¿Necesitas algo más?"""
            
            # 🆕 Guardar respuesta del agente
            self._save_interaction(
                ticket=ticket,
                message=response_text,
                interaction_type="agent_response",
                created_by="Kami (Agente IA)",
                auto_resolved=True,
                requires_escalation=False
            )
            
            # 🆕 Marcar ticket como auto-resuelto si aún no lo está
            if not ticket.auto_resolved_by_agent:
                ticket.auto_resolved_by_agent = True
                ticket.auto_resolved_issues_count += 1
                ticket.status = "resolved"
                ticket.resolved_at = now_argentina()
                self.db.commit()
            
            logger.info("Voucher generated successfully",
                       booking_code=package.booking_code,
                       pdf_path=pdf_path,
                       ticket_number=ticket.ticket_number)
            
            return {
                "response": response_text,
                "voucher_generated": True,
                "download_url": download_url,
                "pdf_path": pdf_path,
                "ticket_created": True,  # 🆕 Ahora sí crea/usa ticket
                "ticket_number": ticket.ticket_number,  # 🆕
                "requires_escalation": False
            }
            
        except Exception as e:
            logger.error("Error generating voucher",
                        booking_code=package.booking_code,
                        error=str(e))
            
            error_response = f"Disculpa, {package.passenger_name}. Hubo un error al generar tu voucher. Por favor contacta a soporte."
            
            # 🆕 Intentar guardar error si hay ticket
            try:
                ticket = self.get_or_create_session_ticket(session_id, package)
                self._save_interaction(
                    ticket=ticket,
                    message=error_response,
                    interaction_type="system_error",
                    created_by="Sistema",
                    requires_escalation=True
                )
            except:
                pass  # No fallar por error al guardar interacción
            
            return {
                "response": error_response,
                "voucher_generated": False,
                "ticket_created": False,
                "error": str(e)
            }

    def cleanup_inactive_sessions(self, days: int = 7) -> int:
        """Marca como inactivas las PostSaleSession sin actividad en los últimos `days` días.

        Returns:
            Número de sesiones desactivadas.
        """
        from app.models.postsale import PostSaleSession
        cutoff = now_argentina() - timedelta(days=days)
        updated = (
            self.db.query(PostSaleSession)
            .filter(
                PostSaleSession.is_active == True,
                PostSaleSession.last_interaction < cutoff,
            )
            .update({"is_active": False}, synchronize_session="fetch")
        )
        self.db.commit()
        logger.info("Inactive postsale sessions cleaned up",
                    days_threshold=days, sessions_deactivated=updated)
        return updated