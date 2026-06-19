#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST DE BÚSQUEDAS CON PALABRAS EN ESPAÑOL
==========================================
Prueba búsquedas con caracteres especiales.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

def test_spanish_searches():
    """Ejecuta búsquedas de prueba."""
    print("🔎 TEST DE BÚSQUEDAS EN ESPAÑOL")
    print("=" * 60)
    
    # Test cases extendidos con casos específicos de turismo
    test_cases = [
        ("España", "País europeo"),
        ("México", "País latinoamericano"),
        ("Cancún", "Ciudad turística"),
        ("año", "Palabra común"),
        ("niño", "Palabra con ñ"),
        ("Descripción completa", "Frase con acento"),
        ("paquete turístico", "Servicio de turismo"),
        ("viaje romántico", "Tipo de viaje"),
        ("precio en dólares", "Moneda"),
        ("habitación doble", "Tipo de alojamiento"),
        ("pensión completa", "Régimen alimentario"),
        ("excursión incluida", "Actividad turística")
    ]
    
    try:
        from app.services.rag_service import RAGService
        
        rag_service = RAGService()
        
        print("\n📊 Ejecutando búsquedas...\n")
        
        for query, description in test_cases:
            try:
                results = rag_service.buscar_documentos(query, n_results=3)
                status = "✅" if results else "ℹ️"
                result_count = len(results) if results else 0
                
                print(f"{status} '{query}' ({description}): {result_count} resultados")
                
                if results and len(results) > 0:
                    preview = results[0]['content'][:80].replace('\n', ' ')
                    print(f"      Preview: {preview}...")
                    
            except Exception as e:
                print(f"❌ '{query}': Error - {str(e)}")
        
        print("\n" + "=" * 60)
        
    except ImportError:
        print("ℹ️  RAGService no disponible")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    test_spanish_searches()
