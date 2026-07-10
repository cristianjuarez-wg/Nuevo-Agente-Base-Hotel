"""
Post-venta del HOTEL (adaptador mínimo sobre Booking).

Reemplaza al PostSaleService de turismo (atado a SoldPackage, vuelos, proveedores,
vouchers). Conserva el PATRÓN clave de Freeway:
  - Gate determinístico: valida acceso por código de reserva (HTL-XXXX) antes del loop.
  - Ticket de sesión: un HotelTicket por sesión de soporte contra una reserva.
  - Escalado determinístico: el LLM ANALIZA, pero el código decide escalar/resolver.

NO incluye: estado de vuelos, contacto de proveedores, vouchers (no aplican a un hotel
single-property en esta demo).
"""
import json
import re
import secrets
import string
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.llm.openai_client import get_async_openai
from app.core.observability.logging_config import get_logger
from app.utils.timezone_utils import now_business
from app.models.hotel import Booking, HotelTicket, TICKET_OPEN_STATES

logger = get_logger(__name__)

# Mismo patrón de código que el resto del sistema (HTL-XXXX, 4 alfanuméricos).
_BOOKING_CODE_RE = re.compile(r"\bHTL-[A-Z0-9]{4}\b")


def _extract_booking_code(text: str) -> Optional[str]:
    m = _BOOKING_CODE_RE.search((text or "").upper())
    return m.group(0) if m else None


class HotelPostSaleService:
    """Servicio de post-venta del hotel. Una instancia por request (lleva la db)."""

    def __init__(self, db: Session):
        self.db = db
        self.client = get_async_openai()

    # ------------------------------------------------------------------
    # Validación de acceso (booking code)
    # ------------------------------------------------------------------
    def _find_booking(self, code: str) -> Optional[Booking]:
        return (
            self.db.query(Booking)
            .filter(Booking.code == code.strip().upper())
            .first()
        )

    def _find_booking_by_session(self, session_id: str) -> Optional[Booking]:
        """Reserva creada en ESTA sesión web (la última no cancelada). Permite reconocer al
        huésped que acaba de reservar en la misma charla, sin pedirle de nuevo el código que
        el sistema le entregó hace un par de turnos."""
        if not session_id:
            return None
        return (
            self.db.query(Booking)
            .filter(Booking.session_id == session_id, Booking.status != "cancelled")
            .order_by(Booking.created_at.desc())
            .first()
        )

    def _find_booking_by_phone(self, phone: str) -> Optional[Booking]:
        """Reserva activa o futura más cercana de un teléfono (para huéspedes de WhatsApp,
        ya identificados por su número). Resuelve el contacto con el match tolerante de
        ContactService y devuelve su Booking no cancelado con check_out >= hoy más próximo.
        None si el teléfono no tiene contacto o reserva vigente."""
        from app.services.contact_service import ContactService
        from app.utils.phone_normalizer import normalize_phone

        norm = normalize_phone(phone)
        if not norm:
            return None
        contact = ContactService()._find_by_phone(norm, self.db)
        if not contact:
            return None
        today = now_business().date()
        return (
            self.db.query(Booking)
            .filter(
                Booking.contact_id == contact.id,
                Booking.status != "cancelled",
                Booking.check_out >= today,
            )
            .order_by(Booking.check_in.asc())
            .first()
        )

    def validate_access(
        self, message: str, session_id: str, history: List[Dict] = None
    ) -> Dict:
        """Valida que el usuario tenga una reserva. Busca el código en el mensaje y,
        si no está, en el historial reciente."""
        code = _extract_booking_code(message)
        # Buscar el código en el historial: tanto en lo que escribió el usuario como en lo que
        # respondió Aura (ej. "¡Reserva confirmada! Código HTL-XXXX" de un crear_reserva en esta
        # misma charla). Así no le re-pedimos un código que el sistema acaba de entregar.
        if not code and history:
            for msg in reversed(history):
                prev = _extract_booking_code(msg.get("content", ""))
                if prev:
                    code = prev
                    break

        # WhatsApp: ya identificamos al huésped por su teléfono (el session_id es wa_<phone>).
        # Si no tipeó el código pero tiene una reserva vigente, la usamos directo —no le pedimos
        # un código que el sistema ya conoce. (Dueño/staff usan otros prefijos de sesión, así
        # que este atajo es solo para huéspedes.)
        if not code and (session_id or "").startswith("wa_"):
            booking = self._find_booking_by_phone("+" + session_id[3:])
            if booking:
                return {"valid": True, "booking": booking, "code": booking.code}

        # Web: si reservó en ESTA sesión, reconocemos su reserva sin pedir el código de nuevo.
        if not code:
            booking = self._find_booking_by_session(session_id)
            if booking:
                return {"valid": True, "booking": booking, "code": booking.code}

        if not code:
            # Red final: si el huésped solo se está despidiendo/agradeciendo (sin código y sin
            # otra consulta), NO le pidas un código — cerrá cálido. Cubre el caso de una
            # despedida que llegó al gate por contexto de post-venta de la sesión.
            from app.utils.social_text import is_pure_social
            if is_pure_social(message):
                return {
                    "valid": False,
                    "message": "¡Un placer ayudarte! Que tengas una hermosa estadía en Bariloche 😊",
                }
            return {
                "valid": False,
                "message": (
                    "Para ayudarte con tu reserva necesito tu código (formato HTL-XXXX). "
                    "Lo encontrás en el email de confirmación de tu reserva."
                ),
            }

        booking = self._find_booking(code)
        if not booking:
            return {
                "valid": False,
                "message": (
                    f"No encuentro una reserva con el código {code}. "
                    "¿Podés verificar que esté bien escrito?"
                ),
            }

        return {"valid": True, "booking": booking, "code": code}

    # ------------------------------------------------------------------
    # Ticket de sesión
    # ------------------------------------------------------------------
    def _generate_ticket_number(self) -> str:
        suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        return f"HT-{suffix}"

    def get_or_create_session_ticket(self, session_id: str, booking: Booking) -> HotelTicket:
        ticket = (
            self.db.query(HotelTicket)
            .filter(
                HotelTicket.session_id == session_id,
                HotelTicket.status.in_(TICKET_OPEN_STATES),
            )
            .order_by(HotelTicket.created_at.desc())
            .first()
        )
        if ticket:
            return ticket

        ticket = HotelTicket(
            ticket_number=self._generate_ticket_number(),
            booking_id=booking.id,
            session_id=session_id,
            subject=f"Consulta de {booking.guest_name} — reserva {booking.code}",
            category="general",
            priority="medium",
            status="open",
            description=f"Sesión de soporte iniciada para la reserva {booking.code}.",
            escalated=0,
        )
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        logger.info("Hotel support ticket created",
                    ticket_number=ticket.ticket_number, session_id=session_id)
        return ticket

    # ------------------------------------------------------------------
    # Contexto de la reserva (para el prompt del orquestador)
    # ------------------------------------------------------------------
    def build_booking_context(self, booking: Booking) -> str:
        from datetime import date as _date
        d = booking.to_dict()
        # Marca temporal: ayuda al agente a no hablar como si el huésped "ya estuvo"/"vuelve"
        # cuando la reserva es futura (caso típico: recién reservó para más adelante).
        try:
            ci = booking.check_in if isinstance(booking.check_in, _date) else _date.fromisoformat(str(d["check_in"]))
            etapa = "FUTURA (el huésped aún no se hospedó)" if ci > _date.today() else "en curso / pasada"
        except Exception:
            etapa = "—"
        return "\n".join([
            f"INFORMACIÓN DE LA RESERVA {d['code']}:",
            f"Huésped: {d['guest_name']}",
            f"Habitación: {d.get('room_type', 'N/A')}",
            f"Check-in: {d['check_in']} | Check-out: {d['check_out']} ({d['nights']} noche(s))",
            f"Etapa de la estadía: {etapa}",
            f"Huéspedes: {d['guests']}",
            f"Total: USD {d['total_price_usd']:.0f} / ARS {d['total_price_ars']:,.0f}",
            f"Estado: {d['status']} | Pago: {d['payment_status']}",
            self._promo_line(booking.promo_name),
        ])

    def _promo_line(self, promo_name: Optional[str]) -> str:
        """Línea de la promo aplicada a ESTA reserva, con qué incluye (para que el agente
        responda '¿tengo X incluido?' mirando la reserva, no el RAG genérico). Sin promo →
        lo dice explícito para que NO asuma inclusiones (los extras son con cargo)."""
        name = (promo_name or "").strip()
        if not name:
            return "Promo aplicada: ninguna (sin inclusiones extra; servicios como estacionamiento son con cargo)"
        try:
            from app.models.promotions import Promotion
            # Buscamos por nombre (no por vigencia): lo que importa es lo que la reserva YA
            # tiene aplicado, aunque la promo se haya despublicado luego.
            promo = (
                self.db.query(Promotion).filter(Promotion.name == name).first()
            )
        except Exception:
            promo = None
        if promo is not None:
            detalle = " ".join(filter(None, [promo.description, promo.conditions])).strip()
            if detalle:
                return f"Promo aplicada: {name} — {detalle}"
        return f"Promo aplicada: {name}"

    # ------------------------------------------------------------------
    # Análisis de escalación (LLM analiza, código decide)
    # ------------------------------------------------------------------
    async def analyze_escalation(self, consulta: str, booking: Booking) -> Dict:
        """Determina si la consulta se puede auto-resolver o requiere asesor humano.

        Devuelve {requires_escalation, urgency_level, escalation_reason, category}.
        Ante cualquier falla, escala por seguridad (no auto-resolver un caso serio).
        """
        prompt = (
            "Sos el analista de soporte de un hotel. Clasificá la consulta de un huésped "
            "que YA tiene una reserva confirmada y decidí si el concierge IA puede "
            "resolverla solo o si debe ESCALAR a un asesor humano.\n\n"
            "DISTINGUÍ con cuidado entre PEDIR INFORMACIÓN y EJECUTAR UNA ACCIÓN:\n"
            "AUTO-RESOLVER (requires_escalation=false) si el huésped PIDE INFORMACIÓN, "
            "incluso sobre temas sensibles: '¿cuál es la política de cancelación?', "
            "'¿hasta cuándo puedo cancelar sin cargo?', '¿puedo cambiar fechas y cómo?', "
            "horarios de check-in/out, servicios incluidos, amenities, cómo llegar, qué "
            "incluye la reserva. En estos casos el concierge informa la política/condición "
            "y, si el huésped luego quiere EJECUTARLA, recién ahí ofrece pasar a un asesor.\n"
            "ESCALAR (requires_escalation=true) SOLO si el huésped PIDE EJECUTAR una acción "
            "que modifica la reserva o compromete dinero: 'cancelá mi reserva', 'cambiame la "
            "fecha al 15', pedido de reembolso, un reclamo formal grave, o un cobro incorrecto.\n"
            "NO ESCALAR (requires_escalation=false) los PEDIDOS DE SERVICIO de la estadía "
            "(toallas, limpieza, algo que no funciona, llave, late checkout, room service): "
            "esos se registran como pedido para el staff con otra herramienta, no se escalan. "
            "Categoría 'service' para esos casos.\n\n"
            f"CONSULTA DEL HUÉSPED: \"{consulta}\"\n\n"
            "Respondé SOLO un JSON: "
            '{"requires_escalation": bool, "urgency_level": "baja|media|alta", '
            '"escalation_reason": "...", "category": "info|change|cancel|complaint|general"}'
        )
        try:
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=150,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            return {
                "requires_escalation": bool(data.get("requires_escalation", True)),
                "urgency_level": data.get("urgency_level", "media"),
                "escalation_reason": data.get("escalation_reason", ""),
                "category": data.get("category", "general"),
            }
        except Exception as e:
            logger.error("Hotel escalation analysis failed, escalando por seguridad", error=str(e))
            return {
                "requires_escalation": True,
                "urgency_level": "alta",
                "escalation_reason": "no se pudo analizar la consulta (falla del análisis)",
                "category": "general",
            }

    # ------------------------------------------------------------------
    # Acción determinística sobre el ticket
    # ------------------------------------------------------------------
    def apply_ticket_action(
        self,
        ticket: HotelTicket,
        requires_escalation: bool,
        response_text: str,
        query: str,
        analysis: Optional[Dict] = None,
    ) -> str:
        """Aplica el resultado al ticket. NO lo decide el LLM: lo decide este código
        según el análisis de escalación. Devuelve el status final del ticket."""
        # Actualizar subject/category/priority con la consulta real
        if analysis:
            ticket.category = analysis.get("category", ticket.category)
            urgency = analysis.get("urgency_level", "media")
            ticket.priority = {"baja": "low", "media": "medium", "alta": "high"}.get(urgency, "medium")
        if query and ticket.description and "Sesión de soporte iniciada" in ticket.description:
            ticket.description = query[:1000]

        if requires_escalation:
            ticket.status = "escalated"
            ticket.escalated = 1
            logger.warning("Hotel ticket escalated",
                           ticket_number=ticket.ticket_number,
                           reason=(analysis or {}).get("escalation_reason"))
            self.db.commit()
            # Una escalación (cancelar/reembolso/queja grave) NO puede quedar sin dueño:
            # la enrutamos a un área del equipo y la notificamos, igual que un pedido de
            # servicio. Así lo MÁS serio también llega a una persona, no solo al backoffice.
            try:
                from app.services import operations_service
                operations_service.log_event(
                    self.db, ticket, "escalated", actor_type="agent",
                    note=f"Escalado: {(analysis or {}).get('escalation_reason', query[:80])}",
                )
                # Cancelaciones, reembolsos, cambios y quejas son tema de recepción/gerencia.
                # El resto cae a la clasificación por keywords del texto.
                cat = (analysis or {}).get("category", "")
                area_hint = "recepcion" if cat in ("cancel", "change", "complaint") else None
                staff = operations_service.classify_and_assign(
                    self.db, ticket, area_hint=area_hint,
                )
                operations_service.notify_staff_assignment(staff, ticket)
            except Exception as e:  # noqa: BLE001 — no romper la respuesta al huésped
                logger.warning("No se pudo asignar/notificar la escalación al equipo",
                               ticket_number=ticket.ticket_number, error=str(e))
            return ticket.status
        else:
            ticket.status = "resolved"
            ticket.auto_resolved_by_agent = response_text[:2000]

        self.db.commit()
        return ticket.status

    def register_service_request(
        self, ticket: HotelTicket, pedido: str, tipo: str = "general", urgencia: str = "media",
    ) -> str:
        """Registra un pedido de servicio del huésped como ticket para el staff.

        A diferencia de una escalación genérica, deja el ticket con categoría
        'service_request', el tipo (housekeeping/mantenimiento/recepcion/...) y la prioridad,
        en estado 'open' para que el equipo del hotel lo atienda. Es lo que convierte a Aura
        en un concierge real (service routing) en vez de "un asesor te contactará".
        """
        priority = {"baja": "low", "media": "medium", "alta": "high"}.get(urgencia, "medium")
        ticket.category = "service_request"
        ticket.priority = priority
        ticket.subject = f"Pedido de servicio ({tipo})"
        ticket.description = pedido[:1000]
        ticket.origin = "guest"
        ticket.status = "open"
        # updated_at se refresca solo (onupdate=datetime.now en el modelo).
        self.db.commit()
        logger.info("Service request registered",
                    ticket_number=ticket.ticket_number, tipo=tipo, priority=priority)

        # "Empleado digital" (Fase 4): enrutar el pedido al área del equipo y avisarle por
        # WhatsApp. Best-effort: si falla la asignación/notificación, el ticket igual queda
        # abierto y visible en el backoffice (no rompe la respuesta al huésped).
        try:
            from app.services import operations_service
            operations_service.log_event(
                self.db, ticket, "created", actor_type="agent",
                note=f"Pedido del huésped: {pedido[:80]}",
            )
            staff = operations_service.classify_and_assign(self.db, ticket, area_hint=tipo)
            operations_service.notify_staff_assignment(staff, ticket)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo enrutar/notificar el pedido al equipo",
                           ticket_number=ticket.ticket_number, error=str(e))

        return ticket.status

    # ------------------------------------------------------------------
    # GATE — preparación determinística del turno (espejo de run_gate de Freeway)
    # ------------------------------------------------------------------
    async def run_gate(
        self, message: str, session_id: str, history: List[Dict] = None
    ) -> Dict:
        """Valida acceso y prepara el turno.

        Returns:
          - {"handled": True, "result": {...}}            → respuesta terminal (validación
            fallida o solo-código → bienvenida); no sigue al orquestador.
          - {"handled": False, "booking": Booking, "ticket": HotelTicket,
             "query_to_process": str}                     → listo para el loop de tools.
        """
        validation = self.validate_access(message, session_id, history)
        if not validation["valid"]:
            return {"handled": True, "result": {
                "response": validation["message"],
                "requires_validation": True,
                "ticket_created": False,
            }}

        booking = validation["booking"]

        # Si el usuario solo dio el código, buscar su consulta real en el historial.
        original_query = None
        if history and _extract_booking_code(message):
            for i in range(len(history) - 1, -1, -1):
                if history[i].get("role") == "user":
                    prev = history[i].get("content", "")
                    if not _extract_booking_code(prev):
                        original_query = prev
                        break

        query_to_process = original_query or message

        # Solo código sin consulta concreta → bienvenida determinística.
        if not original_query and _extract_booking_code(message) and message.strip().upper() == validation["code"]:
            ticket = self.get_or_create_session_ticket(session_id, booking)
            welcome = (
                f"¡Hola {booking.guest_name}! 😊 Tengo tu reserva {booking.code} "
                f"({booking.to_dict().get('room_type', '')}, check-in {booking.check_in}). "
                "¿En qué puedo ayudarte con tu estadía?"
            )
            return {"handled": True, "result": {
                "response": welcome,
                "requires_more_info": True,
                "ticket_created": True,
                "ticket_number": ticket.ticket_number,
            }}

        ticket = self.get_or_create_session_ticket(session_id, booking)
        return {
            "handled": False,
            "booking": booking,
            "ticket": ticket,
            "query_to_process": query_to_process,
        }
