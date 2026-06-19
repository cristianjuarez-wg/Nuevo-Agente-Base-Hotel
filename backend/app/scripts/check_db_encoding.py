#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFICACIÓN RÁPIDA DE CHROMADB
================================
Script ligero para verificar estado de ChromaDB.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

def quick_check():
    """Verificación rápida de ChromaDB."""
    print("🔍 VERIFICACIÓN RÁPIDA DE CHROMADB")
    print("=" * 60)
    
    try:
        import chromadb
        from chromadb.config import Settings
        
        db_path = Path(__file__).parent.parent.parent / "chroma_db"
        
        if not db_path.exists():
            print("ℹ️  ChromaDB no existe todavía")
            return
        
        client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        collections = client.list_collections()
        
        print(f"\n📊 Colecciones: {len(collections)}")
        
        for col in collections:
            count = col.count()
            print(f"   • {col.name}: {count} documentos")
            
            # Muestra de 3 documentos
            sample = col.get(limit=3, include=['documents'])
            
            if sample and sample['documents']:
                print(f"\n   📄 Muestra de documentos:")
                for i, doc in enumerate(sample['documents'][:3], 1):
                    preview = doc[:100].replace('\n', ' ')
                    has_corruption = '�' in doc
                    status = "⚠️" if has_corruption else "✅"
                    print(f"      {status} Doc {i}: {preview}...")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    quick_check()
