"""
Servicio para gestión de métricas y análisis de tendencias
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract
from app.utils.timezone_utils import now_argentina
from app.models.metrics_snapshot import MetricsSnapshot
from app.models.conversation import Conversation
from app.models.lead import Lead
from app.core.logging_config import get_logger
from typing import Dict, List, Optional
from collections import Counter

logger = get_logger(__name__)

class MetricsService:
    def __init__(self):
        logger.info("Metrics service initialized")
    
    def create_snapshot(self, db: Session) -> Dict:
        """Crea un snapshot de las métricas actuales"""
        try:
            # Obtener métricas de conversaciones
            total_conversations = db.query(Conversation).count()
            active_conversations = db.query(Conversation).filter(
                Conversation.status == "active"
            ).count()
            
            total_messages = db.query(func.sum(Conversation.message_count)).scalar() or 0
            avg_response_time = db.query(func.avg(Conversation.avg_response_time)).scalar() or 0.0
            avg_duration = db.query(func.avg(Conversation.total_duration)).scalar() or 0.0
            
            # Obtener métricas de leads (solo con nombre Y contacto)
            total_leads = db.query(Lead).filter(
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            active_leads = db.query(Lead).filter(
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            
            leads_calientes = db.query(Lead).filter(
                Lead.lead_type == "CALIENTE",
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            leads_tibios = db.query(Lead).filter(
                Lead.lead_type == "TIBIO",
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            leads_frios = db.query(Lead).filter(
                Lead.lead_type == "FRIO",
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            
            leads_with_contact = db.query(Lead).filter(
                Lead.name.isnot(None),
                Lead.phone.isnot(None),
                Lead.status == "active"
            ).count()
            
            leads_ready = db.query(Lead).filter(
                Lead.contact_readiness == True,
                Lead.status == "active",
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            ).count()
            
            conversion_rate = (leads_with_contact / active_leads * 100) if active_leads > 0 else 0
            
            # Obtener destinos populares
            popular_destinations = self._get_popular_destinations(db)
            
            # Crear snapshot
            snapshot = MetricsSnapshot(
                snapshot_date=now_argentina(),
                period_type="daily",
                total_conversations=total_conversations,
                total_messages=int(total_messages),
                active_sessions=active_conversations,
                avg_response_time=float(avg_response_time),
                avg_conversation_duration=float(avg_duration),
                total_leads=total_leads,
                active_leads=active_leads,
                leads_calientes=leads_calientes,
                leads_tibios=leads_tibios,
                leads_frios=leads_frios,
                leads_with_contact=leads_with_contact,
                leads_ready_contact=leads_ready,
                conversion_rate=float(conversion_rate),
                popular_destinations=popular_destinations
            )
            
            db.add(snapshot)
            db.commit()
            
            logger.info("Metrics snapshot created", snapshot_id=snapshot.id)
            return snapshot.to_dict()
            
        except Exception as e:
            logger.error("Error creating metrics snapshot", error=str(e))
            db.rollback()
            raise
    
    def get_trends(self, db: Session, days: int = 30) -> Dict:
        """Calcula tendencias comparando con período anterior"""
        try:
            now = now_argentina()
            
            # Obtener métricas actuales (últimas 24 horas)
            current_start = now - timedelta(days=1)
            current_snapshot = self._get_period_metrics(db, current_start, now)
            
            # Obtener métricas del período anterior (días anteriores)
            previous_end = current_start
            previous_start = previous_end - timedelta(days=days)
            previous_snapshot = self._get_period_metrics(db, previous_start, previous_end)
            
            # Calcular tendencias
            trends = {
                "conversations_trend": self._calculate_trend(
                    current_snapshot.get("total_conversations", 0),
                    previous_snapshot.get("total_conversations", 0)
                ),
                "leads_trend": self._calculate_trend(
                    current_snapshot.get("total_leads", 0),
                    previous_snapshot.get("total_leads", 0)
                ),
                "conversion_trend": self._calculate_trend(
                    current_snapshot.get("conversion_rate", 0),
                    previous_snapshot.get("conversion_rate", 0)
                ),
                "ready_contact_trend": self._calculate_trend(
                    current_snapshot.get("leads_ready_contact", 0),
                    previous_snapshot.get("leads_ready_contact", 0)
                ),
                "current_metrics": current_snapshot,
                "previous_metrics": previous_snapshot
            }
            
            return trends
            
        except Exception as e:
            logger.error("Error calculating trends", error=str(e))
            return {
                "conversations_trend": 0,
                "leads_trend": 0,
                "conversion_trend": 0,
                "ready_contact_trend": 0
            }
    
    def get_timeline_data(self, db: Session, period: str = "hourly") -> Dict:
        """Obtiene datos reales de timeline de conversaciones (excluye post-venta)"""
        try:
            now = now_argentina()
            
            if period == "hourly":
                # Últimas 24 horas
                start_time = now - timedelta(hours=24)
                
                # Agrupar por hora (excluir conversaciones de post-venta)
                hourly_data = db.query(
                    extract('hour', Conversation.started_at).label('hour'),
                    func.count(Conversation.id).label('count')
                ).filter(
                    Conversation.started_at >= start_time,
                    Conversation.context_type != 'post_sale'  # Excluir soporte
                ).group_by('hour').all()
                
                # Crear array de 24 horas
                labels = [f"{i:02d}:00" for i in range(24)]
                data = [0] * 24
                
                for hour, count in hourly_data:
                    if hour is not None:
                        data[int(hour)] = count
                
                return {
                    "labels": labels,
                    "data": data,
                    "period": "hourly"
                }
            
            elif period == "daily":
                # Últimos 7 días
                start_time = now - timedelta(days=7)
                
                # Agrupar por día (excluir conversaciones de post-venta)
                daily_data = db.query(
                    func.date(Conversation.started_at).label('date'),
                    func.count(Conversation.id).label('count')
                ).filter(
                    Conversation.started_at >= start_time,
                    Conversation.context_type != 'post_sale'  # Excluir soporte
                ).group_by('date').all()
                
                # Crear array de 7 días
                labels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
                data = [0] * 7
                
                for date, count in daily_data:
                    if date:
                        weekday = date.weekday()
                        data[weekday] = count
                
                return {
                    "labels": labels,
                    "data": data,
                    "period": "daily"
                }
            
            return {"labels": [], "data": [], "period": period}
            
        except Exception as e:
            logger.error("Error getting timeline data", error=str(e))
            # Retornar datos vacíos en caso de error
            return {
                "labels": [f"{i:02d}:00" for i in range(24)],
                "data": [0] * 24,
                "period": "hourly"
            }
    
    def get_heatmap_data(self, db: Session, days: int = 7, channel: str = None) -> Dict:
        """
        Obtiene datos para heatmap de actividad (día × hora)
        Excluye conversaciones de post-venta

        Args:
            db: Sesión de base de datos
            days: Número de días a analizar (default: 7)
            channel: Filtro opcional por canal ("web" | "whatsapp"); None = todos

        Returns:
            Dict con datos formateados para heatmap
        """
        try:
            now = now_argentina()
            start_time = now - timedelta(days=days)

            # Consulta agrupada por día de semana y hora
            # dow: 0=Domingo, 1=Lunes, ..., 6=Sábado
            query = db.query(
                extract('dow', Conversation.started_at).label('day_of_week'),
                extract('hour', Conversation.started_at).label('hour'),
                func.count(Conversation.id).label('count')
            ).filter(
                Conversation.started_at >= start_time,
                Conversation.context_type != 'post_sale'  # Excluir soporte
            )
            if channel in ("web", "whatsapp"):
                query = query.filter(Conversation.channel == channel)
            heatmap_data = query.group_by('day_of_week', 'hour').all()
            
            # Mapeo de días (PostgreSQL/SQLite usan 0=Domingo)
            days_map = {
                0: "Dom", 1: "Lun", 2: "Mar", 3: "Mié", 
                4: "Jue", 5: "Vie", 6: "Sáb"
            }
            
            # Formatear datos
            formatted_data = []
            max_count = 0
            total = 0
            
            for dow, hour, count in heatmap_data:
                if dow is not None and hour is not None:
                    formatted_data.append({
                        "day": days_map.get(int(dow), "?"),
                        "day_index": int(dow),
                        "hour": int(hour),
                        "count": count
                    })
                    max_count = max(max_count, count)
                    total += count
            
            # Rellenar celdas vacías con 0 (para visualización completa)
            existing_keys = {(d['day_index'], d['hour']) for d in formatted_data}
            for day_idx in range(7):
                for hour in range(24):
                    if (day_idx, hour) not in existing_keys:
                        formatted_data.append({
                            "day": days_map[day_idx],
                            "day_index": day_idx,
                            "hour": hour,
                            "count": 0
                        })
            
            logger.info("Heatmap data generated",
                       total_conversations=total,
                       max_count=max_count,
                       period_days=days)
            
            return {
                "data": formatted_data,
                "max_count": max_count,
                "total_conversations": total,
                "period_days": days,
                "start_date": start_time.strftime("%Y-%m-%d"),
                "end_date": now.strftime("%Y-%m-%d")
            }
            
        except Exception as e:
            logger.error("Error getting heatmap data", error=str(e))
            return {
                "data": [],
                "max_count": 0,
                "total_conversations": 0,
                "period_days": days,
                "start_date": "",
                "end_date": ""
            }
    
    def get_conversations_by_channel(self, db: Session) -> Dict:
        """
        Distribución REAL de conversaciones por canal (web / whatsapp).
        Cuenta sobre Conversation.channel. Excluye post-venta.

        Args:
            db: Sesión de base de datos

        Returns:
            Dict con distribución por canal
        """
        try:
            rows = db.query(
                Conversation.channel,
                func.count(Conversation.id)
            ).filter(
                Conversation.context_type != 'post_sale'
            ).group_by(Conversation.channel).all()

            # Normalizar: las conversaciones sin canal seteado se asumen "web".
            counts = {"web": 0, "whatsapp": 0}
            for channel, count in rows:
                key = channel if channel in ("web", "whatsapp") else "web"
                counts[key] += count

            total = counts["web"] + counts["whatsapp"]
            labels = {"web": "Web", "whatsapp": "WhatsApp"}
            channels = [
                {
                    "name": labels[key],
                    "channel": key,
                    "count": counts[key],
                    "percentage": round((counts[key] / total * 100), 1) if total > 0 else 0,
                }
                for key in ("web", "whatsapp")
            ]

            logger.info("Conversations by channel (real)", total=total, **counts)
            return {"channels": channels, "total_conversations": total}

        except Exception as e:
            logger.error("Error getting conversations by channel", error=str(e))
            return {
                "channels": [
                    {"name": "Web", "channel": "web", "count": 0, "percentage": 0},
                    {"name": "WhatsApp", "channel": "whatsapp", "count": 0, "percentage": 0},
                ],
                "total_conversations": 0,
            }
    
    def get_popular_packages(self, db: Session, limit: int = 10) -> List[Dict]:
        """Obtiene paquetes más vistos"""
        try:
            # Obtener todas las conversaciones con paquetes
            conversations = db.query(Conversation).filter(
                Conversation.packages_viewed.isnot(None)
            ).all()
            
            # Contar paquetes
            all_packages = []
            for conv in conversations:
                if conv.packages_viewed:
                    all_packages.extend(conv.packages_viewed)
            
            # Contar frecuencias
            package_counts = Counter(all_packages)
            
            # Top N
            top_packages = [
                {"name": package, "views": count}
                for package, count in package_counts.most_common(limit)
            ]
            
            return top_packages
            
        except Exception as e:
            logger.error("Error getting popular packages", error=str(e))
            return []
    
    def get_popular_documents(self, db: Session, limit: int = 10) -> List[Dict]:
        """Obtiene documentos más utilizados"""
        try:
            # Obtener todas las conversaciones con documentos
            conversations = db.query(Conversation).filter(
                Conversation.documents_consulted.isnot(None)
            ).all()
            
            # Contar documentos
            all_documents = []
            for conv in conversations:
                if conv.documents_consulted:
                    all_documents.extend(conv.documents_consulted)
            
            # Contar frecuencias
            document_counts = Counter(all_documents)
            
            # Top N
            top_documents = [
                {"name": doc, "uses": count}
                for doc, count in document_counts.most_common(limit)
            ]
            
            return top_documents
            
        except Exception as e:
            logger.error("Error getting popular documents", error=str(e))
            return []
    
    def get_content_metrics(self, db: Session) -> Dict:
        """Obtiene todas las métricas de contenido juntas"""
        try:
            destinations = self._get_popular_destinations(db)
            packages = self.get_popular_packages(db, limit=10)
            documents = self.get_popular_documents(db, limit=10)
            
            return {
                "destinations": destinations.get("top_destinations", [])[:5],
                "packages": packages[:5],
                "documents": documents[:5]
            }
        except Exception as e:
            logger.error("Error getting content metrics", error=str(e))
            return {
                "destinations": [],
                "packages": [],
                "documents": []
            }
    
    def track_conversation(self, db: Session, session_id: str, is_user_message: bool = True, 
                          response_time: float = 0.0, destination: str = None,
                          documents: List[str] = None, packages: List[str] = None) -> None:
        """Trackea una conversación y actualiza métricas"""
        logger.info("track_conversation called", 
                   session_id=session_id,
                   destination=destination,
                   documents_count=len(documents) if documents else 0)
        
        try:
            conversation = db.query(Conversation).filter(
                Conversation.session_id == session_id
            ).first()
            
            if not conversation:
                logger.info("Creating new conversation", session_id=session_id)
                conversation = Conversation(
                    session_id=session_id,
                    started_at=now_argentina()
                )
                db.add(conversation)
                db.flush()  # Flush para obtener el ID
                logger.info("New conversation created", 
                           session_id=session_id,
                           conversation_id=conversation.id)
            else:
                logger.info("Updating existing conversation",
                           session_id=session_id,
                           conversation_id=conversation.id)
            
            conversation.update_message_count(is_user_message)
            
            if response_time > 0:
                # Actualizar tiempo promedio de respuesta
                if conversation.avg_response_time == 0:
                    conversation.avg_response_time = response_time
                else:
                    conversation.avg_response_time = (
                        conversation.avg_response_time + response_time
                    ) / 2
            
            if destination:
                conversation.add_destination(destination)
            
            if documents:
                for doc in documents:
                    conversation.add_document(doc)
            
            if packages:
                for package in packages:
                    conversation.add_package(package)
            
            conversation.calculate_duration()
            
            db.commit()
            logger.info("Conversation tracked successfully", session_id=session_id)
            
        except Exception as e:
            logger.error("Error tracking conversation", 
                        session_id=session_id, 
                        error=str(e),
                        error_type=type(e).__name__)
            import traceback
            logger.error("Traceback", traceback=traceback.format_exc())
            db.rollback()
    
    def _get_period_metrics(self, db: Session, start_date: datetime, 
                           end_date: datetime) -> Dict:
        """Obtiene métricas para un período específico"""
        conversations = db.query(Conversation).filter(
            and_(
                Conversation.started_at >= start_date,
                Conversation.started_at < end_date
            )
        ).count()
        
        leads = db.query(Lead).filter(
            and_(
                Lead.created_at >= start_date,
                Lead.created_at < end_date,
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            )
        ).count()
        
        leads_with_contact = db.query(Lead).filter(
            and_(
                Lead.created_at >= start_date,
                Lead.created_at < end_date,
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            )
        ).count()
        
        leads_ready = db.query(Lead).filter(
            and_(
                Lead.created_at >= start_date,
                Lead.created_at < end_date,
                Lead.contact_readiness == True,
                Lead.name.isnot(None),
                ((Lead.email.isnot(None)) | (Lead.phone.isnot(None)))
            )
        ).count()
        
        conversion_rate = (leads_with_contact / leads * 100) if leads > 0 else 0
        
        return {
            "total_conversations": conversations,
            "total_leads": leads,
            "leads_with_contact": leads_with_contact,
            "leads_ready_contact": leads_ready,
            "conversion_rate": conversion_rate
        }
    
    def _calculate_trend(self, current: float, previous: float) -> float:
        """Calcula tendencia porcentual"""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        
        trend = ((current - previous) / previous) * 100
        return round(trend, 1)
    
    def _get_popular_destinations(self, db: Session) -> Dict:
        """Obtiene destinos más mencionados"""
        try:
            # Obtener todas las conversaciones con destinos
            conversations = db.query(Conversation).filter(
                Conversation.destinations_mentioned.isnot(None)
            ).all()
            
            # Contar destinos
            all_destinations = []
            for conv in conversations:
                if conv.destinations_mentioned:
                    all_destinations.extend(conv.destinations_mentioned)
            
            # Contar frecuencias
            destination_counts = Counter(all_destinations)
            
            # Top 10
            top_destinations = [
                {"name": dest, "count": count}
                for dest, count in destination_counts.most_common(10)
            ]
            
            return {"top_destinations": top_destinations}

        except Exception as e:
            logger.error("Error getting popular destinations", error=str(e))
            return {"top_destinations": []}

    def get_postsale_metrics(self, db: Session) -> Dict:
        """Métricas de calidad del agente POST-VENTA (soporte al huésped en viaje).

        Mide containment: qué tan bien Aura resuelve sola vs cuánto escala a un humano,
        más los pedidos de servicio que enruta al staff (service routing). Es la métrica
        de "calidad del agente como producto" que recomienda el estado del arte
        (containment / escalation rate).

        Usa HotelTicket (modelo del hotel). Antes apuntaba a SupportTicket (legacy de
        turismo), por eso estas métricas salían siempre en cero para el hotel.
        """
        from app.models.hotel import HotelTicket, TICKET_OPEN_STATES, TICKET_RESOLVED_STATES
        try:
            total = db.query(func.count(HotelTicket.id)).scalar() or 0
            escalated = db.query(func.count(HotelTicket.id)).filter(
                HotelTicket.escalated == 1
            ).scalar() or 0
            # Auto-resueltos por el agente sin escalar (containment efectivo). Cuenta ambos
            # vocabularios de "cerrado": resolved (IA) y resuelto (loop operativo del staff).
            # Excluye los service_request, que se cuentan aparte (evita doble conteo en
            # containment cuando un pedido de servicio ya quedó en estado 'resuelto').
            auto_resolved = db.query(func.count(HotelTicket.id)).filter(
                HotelTicket.status.in_(TICKET_RESOLVED_STATES),
                HotelTicket.escalated == 0,
                HotelTicket.category != "service_request",
            ).scalar() or 0
            # Pedidos de servicio enrutados al staff (toallas, mantenimiento, etc.).
            service_requests = db.query(func.count(HotelTicket.id)).filter(
                HotelTicket.category == "service_request"
            ).scalar() or 0
            # Abiertos = cualquier estado activo (incluye asignado/pre_resuelto del operativo).
            open_tickets = db.query(func.count(HotelTicket.id)).filter(
                HotelTicket.status.in_(TICKET_OPEN_STATES)
            ).scalar() or 0

            # Containment = atendidos sin escalar (auto-resueltos + pedidos enrutados).
            contained = auto_resolved + service_requests
            containment_rate = round((contained / total * 100), 1) if total else 0.0
            escalation_rate = round((escalated / total * 100), 1) if total else 0.0
            auto_resolution_rate = round((auto_resolved / total * 100), 1) if total else 0.0

            return {
                "total_tickets": total,
                "escalated_tickets": escalated,
                "auto_resolved_tickets": auto_resolved,
                "service_requests": service_requests,
                "open_tickets": open_tickets,
                "containment_rate": containment_rate,        # % atendido sin escalar
                "escalation_rate": escalation_rate,          # % escalado a humano
                "auto_resolution_rate": auto_resolution_rate,  # % resuelto por el agente
            }
        except Exception as e:
            logger.error("Error getting postsale metrics", error=str(e))
            return {
                "total_tickets": 0, "escalated_tickets": 0, "auto_resolved_tickets": 0,
                "service_requests": 0, "open_tickets": 0, "containment_rate": 0.0,
                "escalation_rate": 0.0, "auto_resolution_rate": 0.0,
            }

    def get_funnel(self, db: Session, channel: str = None) -> Dict:
        """Embudo REAL conversaciones → leads → reservas, opcionalmente por canal.

        Usa datos persistidos (no sesiones en memoria):
          - Conversaciones: tabla conversations (excluye post-venta).
          - Leads: tabla leads.
          - Reservas: tabla bookings vinculadas a un Contact (contact_id NOT NULL),
            no canceladas. El canal de la reserva se infiere del Lead/Conversation del
            mismo Contact, o del session_id de la reserva si lo tiene.
        """
        from app.models.hotel import Booking
        from app.models.contact import Contact
        try:
            ch = channel if channel in ("web", "whatsapp") else None

            # 1) Conversaciones (pre-venta)
            conv_q = db.query(func.count(Conversation.id)).filter(
                Conversation.context_type != 'post_sale'
            )
            if ch:
                conv_q = conv_q.filter(Conversation.channel == ch)
            conversations = conv_q.scalar() or 0

            # 2) Leads (ya tienen channel)
            lead_q = db.query(func.count(Lead.id))
            if ch:
                lead_q = lead_q.filter(Lead.channel == ch)
            leads = lead_q.scalar() or 0

            # 3) Reservas vinculadas a Contact, no canceladas.
            book_q = db.query(func.count(Booking.id)).filter(
                Booking.status != "cancelled",
                Booking.contact_id.isnot(None),
            )
            if ch:
                # Canal de la reserva: por session_id (wa_ = whatsapp) cuando exista,
                # con fallback a "web" para reservas sin session de WhatsApp.
                if ch == "whatsapp":
                    book_q = book_q.filter(Booking.session_id.like("wa_%"))
                else:  # web
                    book_q = book_q.filter(
                        (Booking.session_id.is_(None)) | (~Booking.session_id.like("wa_%"))
                    )
            reservations = book_q.scalar() or 0

            def rate(part, whole):
                return round((part / whole * 100), 1) if whole > 0 else 0.0

            return {
                "channel": channel or "all",
                "stages": [
                    {"name": "Conversaciones", "count": conversations, "percentage": 100.0},
                    {"name": "Leads", "count": leads, "percentage": rate(leads, conversations)},
                    {"name": "Reservas", "count": reservations, "percentage": rate(reservations, conversations)},
                ],
                "conversion_rates": {
                    "conversation_to_lead": rate(leads, conversations),
                    "lead_to_reservation": rate(reservations, leads),
                },
            }
        except Exception as e:
            logger.error("Error getting funnel", error=str(e))
            return {
                "channel": channel or "all",
                "stages": [
                    {"name": "Conversaciones", "count": 0, "percentage": 100.0},
                    {"name": "Leads", "count": 0, "percentage": 0.0},
                    {"name": "Reservas", "count": 0, "percentage": 0.0},
                ],
                "conversion_rates": {"conversation_to_lead": 0.0, "lead_to_reservation": 0.0},
            }


# Instancia global
metrics_service = MetricsService()
