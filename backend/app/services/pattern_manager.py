"""
Servicio para gestión de patrones de saludos y despedidas pendientes de aprobación
"""
import json
import os
from typing import Dict, List, Optional
from datetime import datetime
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class PatternManager:
    """Gestor de patrones pendientes de aprobación"""
    
    def __init__(self):
        self.base_path = os.path.join(os.path.dirname(__file__), "..", "data")
        self.pending_patterns_file = os.path.join(self.base_path, "pending_patterns.json")
        self.greetings_farewells_file = os.path.join(self.base_path, "greetings_farewells.json")
    
    def get_pending_patterns(self) -> Dict:
        """
        Obtiene todos los patrones pendientes de aprobación
        
        Returns:
            Dict con pending_greetings y pending_farewells
        """
        try:
            with open(self.pending_patterns_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info("Pending patterns loaded",
                       greetings=len(data.get("pending_greetings", [])),
                       farewells=len(data.get("pending_farewells", [])))
            
            return {
                "pending_greetings": data.get("pending_greetings", []),
                "pending_farewells": data.get("pending_farewells", []),
                "approved_greetings": data.get("approved_greetings", []),
                "approved_farewells": data.get("approved_farewells", []),
                "rejected_patterns": data.get("rejected_patterns", []),
                "metadata": data.get("metadata", {})
            }
        
        except FileNotFoundError:
            logger.warning("Pending patterns file not found")
            return {
                "pending_greetings": [],
                "pending_farewells": [],
                "approved_greetings": [],
                "approved_farewells": [],
                "rejected_patterns": [],
                "metadata": {}
            }
        except Exception as e:
            logger.error("Error loading pending patterns", error=str(e))
            raise
    
    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas de los patrones
        
        Returns:
            Dict con contadores
        """
        try:
            patterns = self.get_pending_patterns()
            
            stats = {
                "pending_greetings": len(patterns["pending_greetings"]),
                "pending_farewells": len(patterns["pending_farewells"]),
                "approved_greetings": len(patterns["approved_greetings"]),
                "approved_farewells": len(patterns["approved_farewells"]),
                "rejected_patterns": len(patterns["rejected_patterns"]),
                "total_pending": len(patterns["pending_greetings"]) + len(patterns["pending_farewells"]),
                "total_approved": len(patterns["approved_greetings"]) + len(patterns["approved_farewells"])
            }
            
            logger.info("Pattern stats calculated", stats=stats)
            return stats
        
        except Exception as e:
            logger.error("Error calculating stats", error=str(e))
            raise
    
    def approve_pattern(self, pattern_text: str, pattern_type: str) -> bool:
        """
        Aprueba un patrón y lo agrega al dataset principal
        
        Args:
            pattern_text: Texto del patrón
            pattern_type: 'greeting' o 'farewell'
            
        Returns:
            True si se aprobó correctamente
        """
        try:
            logger.info("Approving pattern", text=pattern_text, type=pattern_type)
            
            # Cargar patrones pendientes
            with open(self.pending_patterns_file, 'r', encoding='utf-8') as f:
                pending_data = json.load(f)
            
            # Buscar el patrón en la lista correspondiente
            list_key = f"pending_{pattern_type}s"
            pattern_list = pending_data.get(list_key, [])
            
            pattern_found = None
            for i, pattern in enumerate(pattern_list):
                if pattern["text"] == pattern_text:
                    pattern_found = pattern_list.pop(i)
                    break
            
            if not pattern_found:
                logger.warning("Pattern not found", text=pattern_text)
                return False
            
            # Marcar como aprobado
            pattern_found["status"] = "approved"
            pattern_found["approved_at"] = datetime.now().isoformat()
            
            # Agregar a lista de aprobados
            approved_key = f"approved_{pattern_type}s"
            pending_data[approved_key].append(pattern_found)
            
            # Actualizar metadata
            pending_data["metadata"]["last_updated"] = datetime.now().isoformat()
            
            # Guardar patrones pendientes actualizados
            with open(self.pending_patterns_file, 'w', encoding='utf-8') as f:
                json.dump(pending_data, f, ensure_ascii=False, indent=2)
            
            # Agregar al dataset principal
            self._add_to_main_dataset(pattern_text, pattern_type, pattern_found.get("suggested_metadata", {}))
            
            logger.info("Pattern approved successfully", text=pattern_text, type=pattern_type)
            return True
        
        except Exception as e:
            logger.error("Error approving pattern", text=pattern_text, error=str(e))
            raise
    
    def reject_pattern(self, pattern_text: str, pattern_type: str) -> bool:
        """
        Rechaza un patrón
        
        Args:
            pattern_text: Texto del patrón
            pattern_type: 'greeting' o 'farewell'
            
        Returns:
            True si se rechazó correctamente
        """
        try:
            logger.info("Rejecting pattern", text=pattern_text, type=pattern_type)
            
            # Cargar patrones pendientes
            with open(self.pending_patterns_file, 'r', encoding='utf-8') as f:
                pending_data = json.load(f)
            
            # Buscar el patrón en la lista correspondiente
            list_key = f"pending_{pattern_type}s"
            pattern_list = pending_data.get(list_key, [])
            
            pattern_found = None
            for i, pattern in enumerate(pattern_list):
                if pattern["text"] == pattern_text:
                    pattern_found = pattern_list.pop(i)
                    break
            
            if not pattern_found:
                logger.warning("Pattern not found", text=pattern_text)
                return False
            
            # Marcar como rechazado
            pattern_found["status"] = "rejected"
            pattern_found["rejected_at"] = datetime.now().isoformat()
            
            # Agregar a lista de rechazados
            pending_data["rejected_patterns"].append(pattern_found)
            
            # Actualizar metadata
            pending_data["metadata"]["last_updated"] = datetime.now().isoformat()
            
            # Guardar patrones pendientes actualizados
            with open(self.pending_patterns_file, 'w', encoding='utf-8') as f:
                json.dump(pending_data, f, ensure_ascii=False, indent=2)
            
            logger.info("Pattern rejected successfully", text=pattern_text, type=pattern_type)
            return True
        
        except Exception as e:
            logger.error("Error rejecting pattern", text=pattern_text, error=str(e))
            raise
    
    def _add_to_main_dataset(self, text: str, pattern_type: str, metadata: Dict) -> None:
        """
        Agrega un patrón aprobado al dataset principal
        
        Args:
            text: Texto del patrón
            pattern_type: 'greeting' o 'farewell'
            metadata: Metadata del patrón
        """
        try:
            # Cargar dataset principal
            with open(self.greetings_farewells_file, 'r', encoding='utf-8') as f:
                dataset = json.load(f)
            
            # Preparar entrada
            entry = {
                "text": text,
                "formality": metadata.get("formality", "neutral"),
                "category": "admin_approved",  # Marcar como aprobado por admin
                "has_emoji": metadata.get("has_emoji", False),
                "has_typo": metadata.get("has_typo", False),
                "region_specific": metadata.get("region_specific", False)
            }
            
            # Agregar a la lista correspondiente
            list_key = "saludos" if pattern_type == "greeting" else "despedidas"
            
            # Evitar duplicados
            if not any(item["text"] == text for item in dataset.get(list_key, [])):
                dataset[list_key].append(entry)
                
                # Guardar dataset actualizado
                with open(self.greetings_farewells_file, 'w', encoding='utf-8') as f:
                    json.dump(dataset, f, ensure_ascii=False, indent=2)
                
                logger.info("Pattern added to main dataset",
                           text=text,
                           type=pattern_type,
                           list_key=list_key)
            else:
                logger.warning("Pattern already exists in main dataset", text=text)
        
        except Exception as e:
            logger.error("Error adding to main dataset", text=text, error=str(e))
            # No lanzar excepción, el patrón ya fue aprobado en pending_patterns

# Instancia global
pattern_manager = PatternManager()
