"""
Gestor de Estado Conversacional
Maneja flujos multi-paso para captura de datos
"""
from typing import Dict, Optional
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

class ConversationStateManager:
    """
    Maneja estados de conversaciones multi-paso
    Estados en memoria (no persiste en BD)
    """
    
    def __init__(self):
        self._states = {}  # session_id → state_dict
        logger.info("ConversationStateManager initialized")
    
    def set_state(self, session_id: str, state: Dict):
        """
        Guarda estado de conversación
        
        Args:
            session_id: ID de sesión
            state: Diccionario con estado
        """
        self._states[session_id] = state
        logger.debug("Conversation state set",
                    session_id=session_id,
                    step=state.get("step"))
    
    def get_state(self, session_id: str) -> Optional[Dict]:
        """
        Obtiene estado actual de conversación
        
        Args:
            session_id: ID de sesión
            
        Returns:
            Estado o None si no existe
        """
        return self._states.get(session_id)
    
    def update_state(self, session_id: str, updates: Dict):
        """
        Actualiza estado existente
        
        Args:
            session_id: ID de sesión
            updates: Campos a actualizar
        """
        if session_id in self._states:
            self._states[session_id].update(updates)
            logger.debug("Conversation state updated",
                        session_id=session_id,
                        updates=list(updates.keys()))
    
    def clear_state(self, session_id: str):
        """
        Limpia estado de conversación
        
        Args:
            session_id: ID de sesión
        """
        if session_id in self._states:
            del self._states[session_id]
            logger.debug("Conversation state cleared",
                        session_id=session_id)
    
    def has_state(self, session_id: str) -> bool:
        """
        Verifica si existe estado para sesión
        
        Args:
            session_id: ID de sesión
            
        Returns:
            True si existe estado
        """
        return session_id in self._states
    
    def get_all_active_sessions(self) -> list:
        """
        Obtiene lista de sesiones con estado activo
        
        Returns:
            Lista de session_ids
        """
        return list(self._states.keys())
    
    def clear_all(self):
        """Limpia todos los estados (útil para testing)"""
        count = len(self._states)
        self._states.clear()
        logger.info("All conversation states cleared", count=count)

# Instancia global
conversation_state_manager = ConversationStateManager()
