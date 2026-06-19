"""
Servicio de Validación de Paquetes
Valida que el usuario tenga acceso a un paquete vendido
"""
import re
import json
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from app.models.postsale import SoldPackage, PostSaleSession
from app.core.logging_config import get_logger
from app.utils.timezone_utils import now_argentina
from app.core.openai_client import get_sync_openai
from app.config import settings

logger = get_logger(__name__)


class PackageValidator:
    """Valida acceso a paquetes vendidos"""
    
    def __init__(self, db: Session):
        self.db = db
        self.client = get_sync_openai()
    
    def extract_booking_code(self, text: str) -> Optional[str]:
        """
        Extrae código de reserva del texto
        Formatos esperados: ABC123, PKG-2025-001, etc.
        Usa regex primero, LLM como fallback para formatos no estándar
        """
        # PASO 1: Intentar con regex (rápido)
        patterns = [
            r'\b([A-Z]{2,4}-\d{4}-\d{3,6})\b',  # BK-2025-010, PKG-2025-001
            r'\b([A-Z]{3,6}\d{3,6})\b',         # ABC123, ABCDEF123456
            r'\b([A-Z]{2,4}-\d{6})\b',          # AB-123456
            r'\b([A-Z]{2}\d{4,8})\b'            # AB12345678
        ]
        
        text_upper = text.upper()
        
        for pattern in patterns:
            match = re.search(pattern, text_upper)
            if match:
                code = match.group(1)
                logger.debug("Booking code extracted with regex", code=code, pattern=pattern)
                return code
        
        # PASO 2: Si regex falla, intentar con LLM (maneja variaciones)
        # Solo si el mensaje parece contener un código
        if self._might_contain_booking_code(text):
            logger.info("Regex failed, trying LLM fallback for booking code",
                       text_preview=text[:100])
            llm_code = self._extract_booking_code_with_llm(text)
            if llm_code:
                logger.info("Booking code extracted with LLM", code=llm_code)
                return llm_code
        
        return None
    
    def _might_contain_booking_code(self, text: str) -> bool:
        """
        Detecta si el texto podría contener un código de reserva
        (para evitar llamadas innecesarias al LLM)
        """
        text_lower = text.lower()
        
        # Keywords que sugieren código de reserva
        code_keywords = [
            'codigo', 'código', 'reserva', 'booking', 'code',
            'confirmacion', 'confirmación', 'referencia'
        ]
        
        # Si menciona keywords O tiene patrón de letras+números
        has_keyword = any(kw in text_lower for kw in code_keywords)
        has_alphanumeric = bool(re.search(r'[A-Za-z]{2,}.*\d{3,}|\d{3,}.*[A-Za-z]{2,}', text))
        
        return has_keyword or has_alphanumeric
    
    def _extract_booking_code_with_llm(self, text: str) -> Optional[str]:
        """
        Extrae código de reserva usando GPT-4o-mini
        Maneja variaciones como "bee-ka-2025-010" o "BK 2025 010"
        """
        try:
            prompt = f"""Extrae el código de reserva del mensaje.

Mensaje: "{text}"

Un código de reserva típicamente tiene formato:
- ABC123 (letras + números)
- BK-2025-010 (letras-año-número)
- AB-123456 (letras-número)

Responde SOLO con el código normalizado (mayúsculas, formato estándar) o "NONE" si no hay.

Ejemplos:
- "mi codigo es bee-ka-2025-010" → BK-2025-010
- "BK 2025 010" → BK-2025-010
- "ABC 123" → ABC123
- "mi reserva es AB-123456" → AB-123456
- "no tengo codigo" → NONE

Respuesta:"""
            
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_CLASSIFIER,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20,
                timeout=30
            )
            
            result = response.choices[0].message.content.strip().upper()
            
            if result and result != "NONE" and len(result) >= 5:
                logger.info("Booking code extracted with LLM",
                           original_text=text[:100],
                           extracted_code=result,
                           tokens_used=response.usage.total_tokens)
                return result
            
            return None
            
        except Exception as e:
            logger.error("Error extracting booking code with LLM",
                        error=str(e),
                        text_preview=text[:100])
            return None
    
    def extract_contact_info(self, text: str) -> Dict:
        """Extrae email y teléfono del texto"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        phone_pattern = r'\b\d{10,15}\b'
        
        email_match = re.search(email_pattern, text)
        phone_match = re.search(phone_pattern, text)
        
        result = {
            "email": email_match.group(0) if email_match else None,
            "phone": phone_match.group(0) if phone_match else None
        }
        
        if result["email"] or result["phone"]:
            logger.debug("Contact info extracted", **result)
        
        return result
    
    def validate_by_booking_code(self, booking_code: str) -> Optional[SoldPackage]:
        """Valida por código de reserva"""
        package = self.db.query(SoldPackage).filter(
            SoldPackage.booking_code == booking_code.upper()
        ).first()
        
        if package:
            logger.info("Package validated by booking code", 
                       booking_code=booking_code,
                       package_id=package.id,
                       passenger=f"{package.passenger_name} {package.passenger_lastname}")
        else:
            logger.warning("Booking code not found", booking_code=booking_code)
        
        return package
    
    def validate_by_contact(self, email: str = None, phone: str = None) -> List[SoldPackage]:
        """Valida por email o teléfono"""
        query = self.db.query(SoldPackage).filter(
            SoldPackage.trip_status.in_(['confirmed', 'in_progress'])
        )
        
        if email:
            query = query.filter(SoldPackage.passenger_email == email)
        elif phone:
            query = query.filter(SoldPackage.passenger_phone == phone)
        else:
            return []
        
        packages = query.all()
        
        logger.info("Packages found by contact",
                   email=email,
                   phone=phone,
                   count=len(packages))
        
        return packages
    
    def validate_access(self, message: str, session_id: str, conversation_history: list = None) -> Dict:
        """
        Valida acceso completo del usuario
        
        Args:
            message: Mensaje actual del usuario
            session_id: ID de sesión
            conversation_history: Historial de conversación para buscar código previo
        
        Returns:
            Dict con: valid, package, method, message
        """
        # 1. Verificar si ya tiene sesión activa
        existing_session = self.get_session_package(session_id)
        if existing_session:
            logger.info("Active session found", 
                       session_id=session_id,
                       package_id=existing_session.id)
            return {
                "valid": True,
                "package": existing_session,
                "method": "existing_session",
                "message": f"Hola {existing_session.passenger_name}! ¿En qué puedo ayudarte con tu viaje a {existing_session.destination_country}?"
            }
        
        # 2. Intentar por código de reserva en mensaje actual
        booking_code = self.extract_booking_code(message)
        
        # 2.5. Si no hay código en mensaje actual, buscar en historial
        if not booking_code and conversation_history:
            for msg in reversed(conversation_history):
                if msg.get("role") == "user":
                    prev_code = self.extract_booking_code(msg.get("content", ""))
                    if prev_code:
                        booking_code = prev_code
                        logger.info("Booking code found in conversation history",
                                   booking_code=booking_code)
                        break
        
        if booking_code:
            package = self.validate_by_booking_code(booking_code)
            if package:
                self._save_session(session_id, package.id, "booking_code")
                return {
                    "valid": True,
                    "package": package,
                    "method": "booking_code",
                    "message": f"Perfecto, {package.passenger_name}! Tengo tu reserva {booking_code} para {package.package_name}. ¿En qué puedo ayudarte?"
                }
            else:
                return {
                    "valid": False,
                    "message": f"No encuentro una reserva con el código {booking_code}. ¿Podrías verificarlo? Lo encuentras en tu email de confirmación."
                }
        
        # 3. Intentar por contacto
        contact = self.extract_contact_info(message)
        if contact["email"] or contact["phone"]:
            packages = self.validate_by_contact(
                email=contact["email"],
                phone=contact["phone"]
            )
            
            if len(packages) == 1:
                package = packages[0]
                self._save_session(session_id, package.id, "contact")
                return {
                    "valid": True,
                    "package": package,
                    "method": "contact",
                    "message": f"Hola {package.passenger_name}! Encontré tu reserva para {package.package_name}. ¿En qué puedo ayudarte?"
                }
            elif len(packages) > 1:
                return {
                    "valid": False,
                    "multiple": True,
                    "packages": [p.to_dict() for p in packages],
                    "message": "Veo que tienes varios viajes con nosotros. ¿Podrías darme el código de reserva del viaje sobre el que necesitas ayuda?"
                }
        
        # 4. No se pudo validar
        return {
            "valid": False,
            "message": "Para ayudarte con tu viaje, necesito tu código de reserva. Lo encuentras en el email de confirmación que recibiste al comprar el paquete."
        }
    
    def _save_session(self, session_id: str, package_id: int, method: str):
        """Guarda la sesión validada"""
        # Verificar si ya existe
        existing = self.db.query(PostSaleSession).filter(
            PostSaleSession.session_id == session_id
        ).first()
        
        if existing:
            # Actualizar
            existing.package_id = package_id
            existing.validated_at = now_argentina()
            existing.validation_method = method
            existing.is_active = True
            existing.last_interaction = now_argentina()
        else:
            # Crear nueva
            session = PostSaleSession(
                session_id=session_id,
                package_id=package_id,
                validated_at=now_argentina(),
                validation_method=method,
                is_active=True,
                last_interaction=now_argentina()
            )
            self.db.add(session)
        
        self.db.commit()
        
        logger.info("Post-sale session saved",
                   session_id=session_id,
                   package_id=package_id,
                   method=method)
    
    def get_session_package(self, session_id: str) -> Optional[SoldPackage]:
        """Obtiene el paquete de una sesión activa"""
        session = self.db.query(PostSaleSession).filter(
            PostSaleSession.session_id == session_id,
            PostSaleSession.is_active == True
        ).first()
        
        if session and session.package_id:
            return self.db.query(SoldPackage).get(session.package_id)
        
        return None
    
    def update_session_activity(self, session_id: str):
        """Actualiza la última interacción de la sesión"""
        session = self.db.query(PostSaleSession).filter(
            PostSaleSession.session_id == session_id
        ).first()
        
        if session:
            session.last_interaction = now_argentina()
            session.total_messages += 1
            self.db.commit()
    
    def close_session(self, session_id: str):
        """Cierra una sesión de post-venta"""
        session = self.db.query(PostSaleSession).filter(
            PostSaleSession.session_id == session_id
        ).first()
        
        if session:
            session.is_active = False
            self.db.commit()
            logger.info("Post-sale session closed", session_id=session_id)