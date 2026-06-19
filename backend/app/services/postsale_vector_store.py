"""
Vector Store para Paquetes Vendidos
Búsqueda semántica de paquetes por contexto natural
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
from datetime import datetime
from app.models.postsale import SoldPackage
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class PostSaleVectorStore:
    """Vector store para búsqueda semántica de paquetes vendidos"""
    
    def __init__(self, persist_directory: str = "./chroma_db_postsale"):
        """
        Inicializa el vector store
        
        Args:
            persist_directory: Directorio donde se persiste ChromaDB
        """
        try:
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            self.collection = self.client.get_or_create_collection(
                name="sold_packages",
                metadata={"description": "Paquetes turísticos vendidos para búsqueda semántica"}
            )
            
            logger.info("PostSale vector store initialized",
                       collection=self.collection.name,
                       count=self.collection.count(),
                       persist_dir=persist_directory)
        except Exception as e:
            logger.error("Error initializing vector store", error=str(e))
            raise
    
    def _build_search_text(self, package: SoldPackage) -> str:
        """
        Construye texto optimizado para búsqueda semántica
        
        Args:
            package: Paquete vendido
            
        Returns:
            Texto descriptivo del paquete
        """
        parts = [
            f"Paquete {package.package_name}",
            f"para {package.passenger_name} {package.passenger_lastname}",
            f"Código de reserva {package.booking_code}",
            f"Destino {package.destination_country}"
        ]
        
        if package.destination_cities:
            parts.append(f"Ciudades: {package.destination_cities}")
        
        # Formatear fechas en español
        if package.departure_date:
            parts.append(f"Salida {package.departure_date.strftime('%d de %B %Y')}")
        
        if package.return_date:
            parts.append(f"Regreso {package.return_date.strftime('%d de %B %Y')}")
        
        parts.append(f"Duración {package.duration_days} días {package.duration_days - 1} noches")
        
        if package.passenger_email:
            parts.append(f"Email {package.passenger_email}")
        
        if package.passenger_phone:
            parts.append(f"Teléfono {package.passenger_phone}")
        
        return ". ".join(parts)
    
    def add_package(self, package: SoldPackage) -> bool:
        """
        Agrega un paquete al vector store
        
        Args:
            package: Paquete a agregar
            
        Returns:
            True si se agregó correctamente
        """
        try:
            # Construir texto para vectorización
            text = self._build_search_text(package)
            
            # Metadata para filtros
            metadata = {
                "package_id": package.id,
                "booking_code": package.booking_code,
                "passenger_name": f"{package.passenger_name} {package.passenger_lastname}",
                "passenger_email": package.passenger_email,
                "passenger_phone": package.passenger_phone,
                "destination_country": package.destination_country,
                "departure_date": package.departure_date.isoformat() if package.departure_date else None,
                "return_date": package.return_date.isoformat() if package.return_date else None,
                "trip_status": package.trip_status,
                "duration_days": package.duration_days
            }
            
            # Agregar a ChromaDB
            self.collection.add(
                documents=[text],
                metadatas=[metadata],
                ids=[f"pkg_{package.id}"]
            )
            
            logger.info("Package added to vector store",
                       package_id=package.id,
                       booking_code=package.booking_code,
                       passenger=metadata["passenger_name"])
            
            return True
            
        except Exception as e:
            logger.error("Error adding package to vector store",
                        package_id=package.id,
                        error=str(e))
            return False
    
    def search_package(self, query: str, n_results: int = 3, 
                      trip_status: List[str] = None) -> List[Dict]:
        """
        Busca paquetes por similitud semántica
        
        Args:
            query: Texto de búsqueda del usuario
            n_results: Número máximo de resultados
            trip_status: Filtrar por estados (confirmed, in_progress, etc.)
            
        Returns:
            Lista de paquetes encontrados con scores de similitud
        """
        try:
            # Preparar filtros
            where = None
            if trip_status:
                where = {"trip_status": {"$in": trip_status}}
            
            # Buscar en ChromaDB
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
            
            packages = []
            
            if results and results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    # Convertir distancia a score de similitud (0-1)
                    distance = results['distances'][0][i]
                    similarity_score = 1 / (1 + distance)  # Normalizar
                    
                    package_data = {
                        "package_id": results['metadatas'][0][i]['package_id'],
                        "booking_code": results['metadatas'][0][i]['booking_code'],
                        "passenger_name": results['metadatas'][0][i]['passenger_name'],
                        "destination": results['metadatas'][0][i]['destination_country'],
                        "departure_date": results['metadatas'][0][i].get('departure_date'),
                        "trip_status": results['metadatas'][0][i]['trip_status'],
                        "score": similarity_score,
                        "distance": distance,
                        "text": results['documents'][0][i]
                    }
                    
                    packages.append(package_data)
            
            logger.info("Package search completed",
                       query=query,
                       results_found=len(packages),
                       top_score=packages[0]['score'] if packages else 0)
            
            return packages
            
        except Exception as e:
            logger.error("Error searching packages",
                        query=query,
                        error=str(e))
            return []
    
    def update_package(self, package: SoldPackage) -> bool:
        """
        Actualiza un paquete en el vector store
        
        Args:
            package: Paquete actualizado
            
        Returns:
            True si se actualizó correctamente
        """
        try:
            # Eliminar versión anterior
            self.delete_package(package.id)
            
            # Agregar versión actualizada
            return self.add_package(package)
            
        except Exception as e:
            logger.error("Error updating package in vector store",
                        package_id=package.id,
                        error=str(e))
            return False
    
    def delete_package(self, package_id: int) -> bool:
        """
        Elimina un paquete del vector store
        
        Args:
            package_id: ID del paquete a eliminar
            
        Returns:
            True si se eliminó correctamente
        """
        try:
            self.collection.delete(ids=[f"pkg_{package_id}"])
            
            logger.info("Package deleted from vector store",
                       package_id=package_id)
            
            return True
            
        except Exception as e:
            logger.error("Error deleting package from vector store",
                        package_id=package_id,
                        error=str(e))
            return False
    
    def bulk_add_packages(self, packages: List[SoldPackage]) -> Dict:
        """
        Agrega múltiples paquetes en lote
        
        Args:
            packages: Lista de paquetes a agregar
            
        Returns:
            Dict con estadísticas de la operación
        """
        stats = {
            "total": len(packages),
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        for package in packages:
            try:
                if self.add_package(package):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append({
                    "package_id": package.id,
                    "error": str(e)
                })
        
        logger.info("Bulk add packages completed",
                   total=stats["total"],
                   success=stats["success"],
                   failed=stats["failed"])
        
        return stats
    
    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del vector store
        
        Returns:
            Dict con estadísticas
        """
        try:
            count = self.collection.count()
            
            return {
                "collection_name": self.collection.name,
                "total_packages": count,
                "status": "active"
            }
        except Exception as e:
            logger.error("Error getting vector store stats", error=str(e))
            return {
                "collection_name": "sold_packages",
                "total_packages": 0,
                "status": "error",
                "error": str(e)
            }
    
    def reset(self) -> bool:
        """
        Resetea el vector store (elimina todos los documentos)
        
        Returns:
            True si se reseteó correctamente
        """
        try:
            self.client.delete_collection("sold_packages")
            self.collection = self.client.get_or_create_collection(
                name="sold_packages",
                metadata={"description": "Paquetes turísticos vendidos para búsqueda semántica"}
            )
            
            logger.warning("Vector store reset completed")
            return True
            
        except Exception as e:
            logger.error("Error resetting vector store", error=str(e))
            return False