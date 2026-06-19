import json
from typing import Dict, List, Optional
from datetime import datetime
import locale
from app.config import settings
from app.utils.timezone_utils import now_argentina

class AgentProfileManager:
    def __init__(self):
        self.current_profile = self._load_profile(settings.AGENT_PROFILE_PATH)
    
    def _load_profile(self, profile_path: str) -> Dict:
        """Carga perfil desde JSON"""
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"No se encontró el archivo de perfil: {profile_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Error al parsear el archivo de perfil: {e}")
    
    def get_system_prompt(self, context: str, chat_history: str = "", custom_instructions: str = None) -> str:
        """Genera el prompt del sistema con el contexto"""
        
        # Configurar locale para español (intentar varias opciones)
        try:
            locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
        except:
            try:
                locale.setlocale(locale.LC_TIME, 'Spanish_Spain.1252')
            except:
                try:
                    locale.setlocale(locale.LC_TIME, 'es_ES')
                except:
                    pass  # Si falla, usar formato por defecto
        
        # Obtener fecha y hora actual de Argentina
        now = now_argentina()
        try:
            fecha_actual = now.strftime("%A %d de %B de %Y")
            hora_actual = now.strftime("%H:%M")
        except:
            # Fallback si locale no funciona
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
            fecha_actual = f"{dias[now.weekday()]} {now.day} de {meses[now.month-1]} de {now.year}"
            hora_actual = now.strftime("%H:%M")
        
        # Agregar información temporal y contexto geográfico
        context_with_date = f"""INFORMACIÓN TEMPORAL:
- Fecha actual: {fecha_actual}
- Hora actual: {hora_actual}

╔══════════════════════════════════════════════════════════════════════╗
║  CONTEXTO GEOGRÁFICO DEL USUARIO                                    ║
╚══════════════════════════════════════════════════════════════════════╝

🌍 UBICACIÓN DEL USUARIO (PRE-VENTA):
- Por defecto, asume que el usuario consulta desde ARGENTINA
- Si el usuario menciona estar en otro país, ajusta tu respuesta
- Usa el clima de Argentina como referencia para comparaciones

🌤️ USO DE INFORMACIÓN CLIMÁTICA:
- Si se proporciona información del clima del destino, úsala para:
  * Dar recomendaciones de qué empacar
  * Comparar con el clima actual de Argentina
  * Sugerir la mejor época para viajar
  * Hacer la experiencia más personalizada

EJEMPLO DE USO:
Usuario: "Me gustaría viajar a Japón en marzo"
Tú: "¡Excelente elección! En marzo, Japón tiene clima primaveral (15°C).
      Comparado con Argentina en marzo (otoño, 20°C), es un poco más fresco.
      Te recomiendo llevar abrigo ligero, paraguas y ropa en capas."

{context}"""
        
        template = self.current_profile['system_prompt_template']
        
        # Si se pasan custom_instructions dinámicas, usarlas; sino usar las del perfil
        if custom_instructions is None:
            custom_instructions = self.current_profile.get('custom_instructions', '')
        
        return template.format(
            agent_name=self.current_profile['agent_name'],
            domain=self.current_profile.get('domain', 'general'),
            context=context_with_date,
            chat_history=chat_history,
            custom_instructions=custom_instructions
        )
    
    def get_greeting(self) -> str:
        """Obtiene mensaje de saludo del agente"""
        return self.current_profile['greeting_message']
    
    def get_no_info_response(self) -> str:
        """Obtiene respuesta cuando no hay información disponible"""
        return self.current_profile['no_info_response']
    
    def get_agent_name(self) -> str:
        """Obtiene nombre del agente"""
        return self.current_profile['agent_name']
    
    def get_domain(self) -> str:
        """Obtiene dominio de especialización"""
        return self.current_profile.get('domain', 'general')
    
    def get_capabilities(self) -> List[str]:
        """Obtiene lista de capacidades del agente"""
        return self.current_profile.get('capabilities', [])
    
    def get_conversation_starters(self) -> List[str]:
        """Obtiene sugerencias de conversación"""
        return self.current_profile.get('conversation_starters', [])
    
    def get_profile_info(self) -> Dict:
        """Obtiene información completa del perfil actual"""
        return {
            "profile_name": self.current_profile['profile_name'],
            "domain": self.get_domain(),
            "description": self.current_profile.get('description', ''),
            "agent_name": self.get_agent_name(),
            "capabilities": self.get_capabilities(),
            "conversation_starters": self.get_conversation_starters()
        }
    
    def switch_profile(self, profile_path: str):
        """Cambia el perfil activo"""
        new_profile = self._load_profile(profile_path)
        self.current_profile = new_profile
        return f"Perfil cambiado a: {new_profile['profile_name']}"
    
    def validate_profile(self, profile_data: Dict) -> tuple[bool, str]:
        """Valida que un perfil tenga la estructura correcta"""
        required_fields = [
            'profile_name', 'domain', 'system_prompt_template',
            'agent_name', 'greeting_message', 'no_info_response'
        ]
        
        for field in required_fields:
            if field not in profile_data:
                return False, f"Campo requerido faltante: {field}"
        
        # Validar que el template tenga los placeholders mínimos necesarios
        template = profile_data['system_prompt_template']
        required_placeholders = ['{agent_name}', '{context}']

        for placeholder in required_placeholders:
            if placeholder not in template:
                return False, f"Placeholder requerido faltante en system_prompt_template: {placeholder}"
        
        return True, "Perfil válido"

# Instancia global del gestor de perfiles
profile_manager = AgentProfileManager()
