from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict, Optional
from app.config import settings
from app.core.observability.logging_config import get_logger
from app.core.geography import geography_service
from app.core.intelligent_geography import intelligent_extractor
from app.core.rag.document_classifier import document_classifier
from app.services.llm_metadata_extractor import llm_extractor  # 🆕 Extractor LLM
import hashlib
import os
from datetime import datetime

logger = get_logger(__name__)

class PDFProcessor:
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len
        )
        logger.info("PDF processor initialized", 
                   chunk_size=settings.CHUNK_SIZE, 
                   chunk_overlap=settings.CHUNK_OVERLAP)
    
    def extract_countries_from_text(self, text: str, filename: str = "", 
                                    document_type: str = "package") -> List[str]:
        """
        Extrae países usando el extractor inteligente multi-nivel.
        Detecta: países explícitos, regiones especiales, ciudades, landmarks, itinerarios.
        Filtra países que son solo puntos de partida o escalas (análisis inteligente).
        
        Args:
            text: Texto completo del documento
            filename: Nombre del archivo
            document_type: Tipo de documento (package, policy, etc.)
        """
        try:
            # 1. Usar extractor inteligente
            geo_data = intelligent_extractor.extract_all_geographic_entities(text, filename)
            
            countries = geo_data['countries']
            
            if not countries:
                return []
            
            # 2. Filtrar países usando análisis inteligente de relevancia
            # (solo para paquetes con múltiples países)
            filtered_countries = intelligent_extractor.filter_destination_countries(
                text, 
                countries, 
                document_type
            )
            
            # Log de detección
            if filtered_countries != countries:
                logger.info("Countries filtered (intelligent analysis)",
                           original_countries=countries,
                           filtered_countries=filtered_countries,
                           cities=geo_data.get('cities', []),
                           landmarks=geo_data.get('landmarks', []),
                           special_regions=geo_data.get('special_regions', []))
            else:
                logger.info("Countries detected (intelligent extraction)",
                           countries=filtered_countries,
                           cities=geo_data.get('cities', []),
                           landmarks=geo_data.get('landmarks', []),
                           special_regions=geo_data.get('special_regions', []),
                           confidence=geo_data.get('confidence', {}))
            
            return filtered_countries
            
        except Exception as e:
            logger.error("Error extracting countries from text",
                        error=str(e))
            return []
    
    def extract_text(self, pdf_path: str) -> str:
        """Extrae texto del PDF"""
        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"Archivo PDF no encontrado: {pdf_path}")
            
            reader = PdfReader(pdf_path)
            text = ""
            
            logger.info("Extracting text from PDF", 
                       file=pdf_path, 
                       pages=len(reader.pages))
            
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                text += page_text + "\n"
                logger.debug("Extracted page", 
                           page_number=i+1, 
                           characters=len(page_text))
            
            logger.info("Text extraction completed", 
                       total_characters=len(text))
            
            return text
            
        except Exception as e:
            logger.error("Error extracting text from PDF", 
                        file=pdf_path, 
                        error=str(e))
            raise
    
    def validate_pdf(self, pdf_path: str) -> tuple[bool, str]:
        """Valida que el archivo PDF sea procesable"""
        try:
            if not os.path.exists(pdf_path):
                return False, "Archivo no encontrado"
            
            # Verificar tamaño del archivo
            file_size = os.path.getsize(pdf_path)
            max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            
            if file_size > max_size:
                return False, f"Archivo demasiado grande: {file_size / (1024*1024):.1f}MB > {settings.MAX_FILE_SIZE_MB}MB"
            
            # Intentar abrir el PDF
            reader = PdfReader(pdf_path)
            
            if len(reader.pages) == 0:
                return False, "PDF no contiene páginas"
            
            # Verificar que se pueda extraer texto de al menos una página
            sample_text = reader.pages[0].extract_text()
            if not sample_text.strip():
                return False, "PDF no contiene texto extraíble (podría ser solo imágenes)"
            
            return True, "PDF válido"
            
        except Exception as e:
            return False, f"Error validando PDF: {str(e)}"
    
    def process_pdf(self, pdf_path: str, filename: str) -> List[Dict]:
        """Procesa PDF y retorna chunks con metadata"""
        try:
            logger.info("Starting PDF processing", 
                       file=filename, 
                       path=pdf_path)
            
            # Validar PDF
            is_valid, validation_msg = self.validate_pdf(pdf_path)
            if not is_valid:
                raise ValueError(f"PDF inválido: {validation_msg}")
            
            # Extraer texto
            full_text = self.extract_text(pdf_path)
            
            if not full_text.strip():
                raise ValueError("No se pudo extraer texto del PDF")
            
            # 🆕 EXTRAER METADATA CON LLM (GPT-4o)
            llm_metadata = llm_extractor.extract_metadata(full_text, filename)
            
            logger.info("LLM metadata extracted",
                       document_type=llm_metadata.get('document_type'),
                       countries=llm_metadata.get('countries'),
                       cities=llm_metadata.get('cities'))
            
            # Dividir en chunks
            chunks = self.text_splitter.split_text(full_text)
            
            if not chunks:
                raise ValueError("No se pudieron crear chunks del texto")
            
            # Generar ID único para el documento
            doc_hash = hashlib.md5(filename.encode()).hexdigest()
            
            # Timestamp actual
            uploaded_at = datetime.now().isoformat()
            
            # Crear chunks con metadata enriquecida (DESDE LLM)
            processed_chunks = []
            for i, chunk in enumerate(chunks):
                if chunk.strip():  # Solo agregar chunks no vacíos
                    metadata = {
                        "source": filename,
                        "doc_id": doc_hash,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "status": "active",
                        "uploaded_at": uploaded_at,
                        
                        # 🆕 METADATA EXTRAÍDA POR LLM (GPT-4o)
                        "document_type": llm_metadata.get('document_type', 'other'),
                        "confidence": llm_metadata.get('confidence', 0.5),
                        "language": llm_metadata.get('language', 'es'),
                        "summary": llm_metadata.get('summary', '')
                    }
                    
                    # Países (SOLO destinos reales, sin tránsito)
                    if llm_metadata.get('countries'):
                        metadata["countries"] = ", ".join(llm_metadata['countries'])
                        metadata["country"] = llm_metadata['countries'][0]  # Primer país
                    
                    # Ciudades
                    if llm_metadata.get('cities'):
                        metadata["cities"] = ", ".join(llm_metadata['cities'])
                    
                    # Landmarks
                    if llm_metadata.get('landmarks'):
                        metadata["landmarks"] = ", ".join(llm_metadata['landmarks'])
                    
                    # Keywords
                    if llm_metadata.get('keywords'):
                        metadata["keywords"] = ", ".join(llm_metadata['keywords'])
                    
                    # 🆕 METADATA ESPECÍFICA PARA PAQUETES
                    if llm_metadata['document_type'] == 'package':
                        metadata["package_name"] = llm_metadata.get('package_name', filename.replace('.pdf', ''))
                        metadata["package_id"] = llm_metadata.get('package_id', '')
                        metadata["package_type"] = llm_metadata.get('package_type', 'unknown')
                        
                        # Información adicional del paquete
                        if llm_metadata.get('duration_days'):
                            metadata["duration_days"] = llm_metadata['duration_days']
                        if llm_metadata.get('includes_flights') is not None:
                            metadata["includes_flights"] = llm_metadata['includes_flights']
                        if llm_metadata.get('meal_plan'):
                            metadata["meal_plan"] = llm_metadata['meal_plan']
                        if llm_metadata.get('price_from'):
                            metadata["price_from"] = llm_metadata['price_from']
                        if llm_metadata.get('package_category'):
                            metadata["package_category"] = llm_metadata['package_category']
                        if llm_metadata.get('target_audience'):
                            # Validar que sea lista
                            target_aud = llm_metadata['target_audience']
                            if isinstance(target_aud, list):
                                metadata["target_audience"] = ", ".join(target_aud)
                            else:
                                metadata["target_audience"] = str(target_aud)
                    
                    # 🆕 METADATA ESPECÍFICA PARA POLÍTICAS
                    elif llm_metadata['document_type'] == 'policy':
                        if llm_metadata.get('policy_type'):
                            metadata["policy_type"] = llm_metadata['policy_type']
                        if llm_metadata.get('applies_to'):
                            applies = llm_metadata['applies_to']
                            if isinstance(applies, list):
                                metadata["applies_to"] = ", ".join(applies)
                            else:
                                metadata["applies_to"] = str(applies)
                    
                    # 🆕 METADATA ESPECÍFICA PARA FAQs
                    elif llm_metadata['document_type'] == 'faq':
                        if llm_metadata.get('faq_categories'):
                            faq_cats = llm_metadata['faq_categories']
                            if isinstance(faq_cats, list):
                                metadata["faq_categories"] = ", ".join(faq_cats)
                            else:
                                metadata["faq_categories"] = str(faq_cats)
                    
                    # 🆕 METADATA ESPECÍFICA PARA PAGOS
                    elif llm_metadata['document_type'] == 'payment':
                        if llm_metadata.get('payment_methods'):
                            pay_methods = llm_metadata['payment_methods']
                            if isinstance(pay_methods, list):
                                metadata["payment_methods"] = ", ".join(pay_methods)
                            else:
                                metadata["payment_methods"] = str(pay_methods)
                        if llm_metadata.get('installments_available') is not None:
                            metadata["installments_available"] = llm_metadata['installments_available']
                    
                    processed_chunks.append({
                        "text": chunk.strip(),
                        "metadata": metadata
                    })
            
            logger.info("PDF processing completed with LLM metadata", 
                       file=filename,
                       total_chunks=len(processed_chunks),
                       text_length=len(full_text),
                       document_type=llm_metadata.get('document_type'),
                       confidence=f"{llm_metadata.get('confidence', 0):.2f}",
                       detected_countries=llm_metadata.get('countries'))
            
            return processed_chunks
            
        except Exception as e:
            logger.error("Error processing PDF", 
                        file=filename, 
                        error=str(e))
            raise
    
    def get_pdf_info(self, pdf_path: str) -> Dict:
        """Obtiene información básica del PDF"""
        try:
            reader = PdfReader(pdf_path)
            
            info = {
                "pages": len(reader.pages),
                "file_size": os.path.getsize(pdf_path),
                "metadata": reader.metadata if reader.metadata else {}
            }
            
            # Extraer muestra de texto para análisis
            if len(reader.pages) > 0:
                sample_text = reader.pages[0].extract_text()[:500]
                info["sample_text"] = sample_text
                info["has_text"] = bool(sample_text.strip())
            
            return info
            
        except Exception as e:
            logger.error("Error getting PDF info", 
                        file=pdf_path, 
                        error=str(e))
            return {"error": str(e)}

# Instancia global del procesador
pdf_processor = PDFProcessor()
