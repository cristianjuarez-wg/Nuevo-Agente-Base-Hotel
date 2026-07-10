from typing import Dict, List
from app.core.observability.logging_config import get_logger
import re

logger = get_logger(__name__)

class DocumentClassifier:
    """
    Clasifica documentos automáticamente según su contenido.
    Detecta tipo de documento y extrae features específicas.
    """
    
    def __init__(self):
        # Keywords fuertes (alta confianza) - peso 2
        self.strong_keywords = {
            "package": [
                "itinerario", "destinos", "días", "noches", "incluye",
                "alojamiento", "hotel", "traslados", "excursiones",
                "precio base", "desde us$", "duración", "paquete turístico"
            ],
            "policy": [
                "cancelación", "reembolso", "devolución", "política",
                "condiciones de cancelación", "penalidad", "cargo por cancelación",
                "términos y condiciones"
            ],
            "payment": [
                "forma de pago", "métodos de pago", "financiamiento",
                "cuotas", "tarjeta de crédito", "transferencia bancaria",
                "anticipo", "saldo", "pago total", "medios de pago"
            ],
            "faq": [
                "preguntas frecuentes", "faq", "consultas habituales",
                "preguntas comunes"
            ]
        }
        
        # Keywords medias (confianza media) - peso 1
        self.medium_keywords = {
            "package": [
                "visita", "tour", "recorrido", "ciudad", "país",
                "salida", "regreso", "vuelo", "aeropuerto", "guía"
            ],
            "policy": [
                "términos", "condiciones", "normas", "reglas",
                "obligatorio", "prohibido", "permitido", "aplica"
            ],
            "payment": [
                "costo", "precio", "valor", "monto", "total",
                "depósito", "reserva", "abono"
            ],
            "faq": [
                "¿qué", "¿cómo", "¿cuándo", "¿dónde", "¿por qué"
            ]
        }
        
        logger.info("Document classifier initialized")
    
    def classify(self, text: str, filename: str = "") -> Dict:
        """
        Clasifica un documento según su contenido.
        
        Args:
            text: Contenido del documento
            filename: Nombre del archivo (opcional)
            
        Returns:
            dict: {
                "type": str,
                "confidence": float,
                "features": dict
            }
        """
        text_lower = text.lower()
        scores = {doc_type: 0 for doc_type in self.strong_keywords.keys()}
        
        # Scoring por keywords fuertes (peso 2)
        for doc_type, keywords in self.strong_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[doc_type] += 2
        
        # Scoring por keywords medias (peso 1)
        for doc_type, keywords in self.medium_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[doc_type] += 1
        
        # Determinar tipo con mayor score
        if max(scores.values()) == 0:
            return {
                "type": "general",
                "confidence": 0.5,
                "features": {}
            }
        
        doc_type = max(scores, key=scores.get)
        max_score = scores[doc_type]
        total_possible = len(self.strong_keywords[doc_type]) * 2 + len(self.medium_keywords.get(doc_type, [])) * 1
        confidence = min(max_score / total_possible, 1.0)
        
        # Extraer features específicas según el tipo
        features = self._extract_features(text, doc_type)
        
        logger.info("Document classified",
                   type=doc_type,
                   confidence=f"{confidence:.2f}",
                   filename=filename[:50] if filename else None)
        
        return {
            "type": doc_type,
            "confidence": confidence,
            "features": features
        }
    
    def _extract_features(self, text: str, doc_type: str) -> Dict:
        """Extrae features específicas según el tipo de documento"""
        features = {}
        
        if doc_type == "package":
            features = self._extract_package_features(text)
        elif doc_type == "policy":
            features = self._extract_policy_features(text)
        elif doc_type == "payment":
            features = self._extract_payment_features(text)
        
        return features
    
    def _extract_package_features(self, text: str) -> Dict:
        """Extrae features de paquetes turísticos"""
        features = {}
        
        # Extraer duración (ej: "14 días", "12 noches")
        duration_match = re.search(r'(\d+)\s*(días|noches|day|night)', text, re.IGNORECASE)
        if duration_match:
            features["duration_value"] = int(duration_match.group(1))
            features["duration_unit"] = duration_match.group(2).lower()
        
        # Extraer precio (ej: "US$ 13,980", "USD 8,190")
        price_match = re.search(r'(?:US\$|USD|usd)\s*([0-9,\.]+)', text, re.IGNORECASE)
        if price_match:
            price_str = price_match.group(1).replace(',', '').replace('.', '')
            try:
                features["price_from"] = int(price_str)
            except:
                pass
        
        # Detectar si incluye vuelos
        features["includes_flights"] = any(word in text.lower() for word in ["aéreo", "vuelo", "flight", "aéreos"])
        
        # Detectar tipo de paquete
        if "todo incluido" in text.lower():
            features["package_subtype"] = "all_inclusive"
        
        return features
    
    def _extract_policy_features(self, text: str) -> Dict:
        """Extrae features de políticas"""
        features = {}
        
        # Detectar tipo de política
        if "cancelación" in text.lower():
            features["policy_type"] = "cancellation"
        elif "reembolso" in text.lower():
            features["policy_type"] = "refund"
        elif "cambio" in text.lower():
            features["policy_type"] = "changes"
        
        # Detectar si aplica a todos los paquetes
        if "todos los paquetes" in text.lower() or "aplica a" in text.lower():
            features["applies_to"] = "all_packages"
        
        return features
    
    def _extract_payment_features(self, text: str) -> Dict:
        """Extrae features de información de pagos"""
        features = {}
        
        # Detectar métodos de pago mencionados
        payment_methods = []
        if "tarjeta" in text.lower():
            payment_methods.append("credit_card")
        if "transferencia" in text.lower():
            payment_methods.append("bank_transfer")
        if "efectivo" in text.lower():
            payment_methods.append("cash")
        
        if payment_methods:
            features["payment_methods"] = payment_methods
        
        # Detectar si hay financiamiento
        if "cuotas" in text.lower() or "financiamiento" in text.lower():
            features["has_financing"] = True
        
        return features

# Instancia global
document_classifier = DocumentClassifier()
