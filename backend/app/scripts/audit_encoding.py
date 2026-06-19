#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDITORÍA DE ENCODING - AGENTE TURISMO IA
==========================================
Detecta problemas de encoding sin modificar datos.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import json

# Agregar path del proyecto
sys.path.append(str(Path(__file__).parent.parent.parent))

# Configurar encoding para Windows
import locale
import codecs

# Intentar configurar UTF-8 en Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

print("INICIANDO AUDITORIA DE ENCODING")
print("=" * 70)


# ============================================================================
# SECCIÓN 1: VERIFICAR ENCODING DE ARCHIVOS PYTHON
# ============================================================================

def audit_python_files():
    """Verifica encoding de archivos .py del proyecto."""
    print("\n[PYTHON] 1. AUDITORIA DE ARCHIVOS PYTHON")
    print("-" * 70)
    
    project_root = Path(__file__).parent.parent.parent
    python_files = list(project_root.rglob("*.py"))
    
    issues = []
    
    for py_file in python_files:
        if 'venv' in str(py_file) or '__pycache__' in str(py_file):
            continue
            
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Verificar si tiene caracteres especiales españoles
            spanish_chars = ['ñ', 'á', 'é', 'í', 'ó', 'ú', 'Ñ', 'Á', 'É', 'Í', 'Ó', 'Ú']
            has_spanish = any(char in content for char in spanish_chars)
            
            # Verificar si tiene declaración de encoding
            first_lines = content.split('\n')[:3]
            has_encoding_declaration = any('coding' in line for line in first_lines)
            
            if has_spanish and not has_encoding_declaration:
                issues.append({
                    'file': str(py_file.relative_to(project_root)),
                    'issue': 'Tiene caracteres españoles sin declaración de encoding'
                })
                
        except UnicodeDecodeError:
            issues.append({
                'file': str(py_file.relative_to(project_root)),
                'issue': 'ERROR: No se puede leer como UTF-8'
            })
    
    if issues:
        print(f"⚠️  Encontrados {len(issues)} archivos con problemas potenciales:")
        for issue in issues:
            print(f"   - {issue['file']}: {issue['issue']}")
    else:
        print("✅ Todos los archivos Python tienen encoding correcto")
    
    return issues


# ============================================================================
# SECCIÓN 2: VERIFICAR PDFs PROCESADOS
# ============================================================================

def audit_pdfs():
    """Verifica encoding en PDFs del directorio uploads."""
    print("\n📄 2. AUDITORÍA DE PDFs PROCESADOS")
    print("-" * 70)
    
    try:
        from pypdf import PdfReader
    except ImportError:
        print("❌ pypdf no instalado. Ejecutar: pip install pypdf")
        return []
    
    uploads_dir = Path(__file__).parent.parent.parent / "uploads"
    
    if not uploads_dir.exists():
        print("ℹ️  No existe directorio 'uploads' todavía")
        return []
    
    pdf_files = list(uploads_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("ℹ️  No hay PDFs en el directorio uploads")
        return []
    
    print(f"📊 Analizando {len(pdf_files)} archivos PDF...")
    
    issues = []
    
    for pdf_path in pdf_files:
        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
            
            # Extraer texto de primera página
            first_page_text = reader.pages[0].extract_text()
            
            # Buscar caracteres corruptos
            if '�' in first_page_text:
                issues.append({
                    'file': pdf_path.name,
                    'pages': total_pages,
                    'issue': 'Contiene caracteres corruptos (�)'
                })
                print(f"   ⚠️  {pdf_path.name}: Caracteres corruptos detectados")
            else:
                print(f"   ✅ {pdf_path.name}: OK ({total_pages} páginas)")
                
        except Exception as e:
            issues.append({
                'file': pdf_path.name,
                'issue': f'Error al procesar: {str(e)}'
            })
            print(f"   ❌ {pdf_path.name}: Error - {str(e)}")
    
    if not issues:
        print("\n✅ Todos los PDFs se procesan correctamente")
    
    return issues


# ============================================================================
# SECCIÓN 3: VERIFICAR CHROMADB
# ============================================================================

def audit_chromadb():
    """Verifica encoding en la base de datos vectorial."""
    print("\n🗄️  3. AUDITORÍA DE CHROMADB")
    print("-" * 70)
    
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        print("❌ chromadb no instalado. Ejecutar: pip install chromadb")
        return []
    
    # Path a ChromaDB
    db_path = Path(__file__).parent.parent.parent / "chroma_db"
    
    if not db_path.exists():
        print("ℹ️  ChromaDB no inicializada todavía")
        return []
    
    try:
        client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Obtener colección
        collections = client.list_collections()
        
        if not collections:
            print("ℹ️  No hay colecciones en ChromaDB")
            return []
        
        print(f"📊 Colecciones encontradas: {len(collections)}")
        
        issues = []
        
        for collection in collections:
            print(f"\n   Analizando colección: {collection.name}")
            
            # Obtener todos los documentos
            results = collection.get(include=['documents', 'metadatas'])
            
            if not results or not results['documents']:
                print(f"   ℹ️  Colección vacía")
                continue
            
            doc_count = len(results['documents'])
            print(f"   📄 Documentos: {doc_count}")
            
            # Verificar encoding en documentos
            corrupted_docs = 0
            for i, doc in enumerate(results['documents']):
                if '�' in doc:
                    corrupted_docs += 1
                    
                    # Obtener metadata del documento corrupto
                    metadata = results['metadatas'][i] if i < len(results['metadatas']) else {}
                    filename = metadata.get('filename', 'unknown')
                    
                    issues.append({
                        'collection': collection.name,
                        'doc_index': i,
                        'filename': filename,
                        'issue': 'Documento contiene caracteres corruptos'
                    })
            
            if corrupted_docs > 0:
                print(f"   ⚠️  {corrupted_docs} documentos con encoding corrupto")
            else:
                print(f"   ✅ Todos los documentos OK")
        
        return issues
        
    except Exception as e:
        print(f"❌ Error al acceder a ChromaDB: {str(e)}")
        return [{'issue': f'Error ChromaDB: {str(e)}'}]


# ============================================================================
# SECCIÓN 4: TEST DE BÚSQUEDAS CON CARACTERES ESPECIALES
# ============================================================================

def audit_search_functionality():
    """Prueba búsquedas con palabras en español."""
    print("\n🔎 4. TEST DE BÚSQUEDAS CON CARACTERES ESPAÑOLES")
    print("-" * 70)
    
    # Importar servicio RAG corregido
    try:
        sys.path.append(str(Path(__file__).parent.parent))
        from app.services.rag_service import RAGService
    except ImportError:
        print("ℹ️  RAGService no disponible todavía")
        return []
    
    # Test cases extendidos con casos específicos de turismo
    test_queries = [
        "España",
        "México", 
        "Cancún",
        "año",
        "descripción",
        "niño",
        "paquete turístico",      # Casos específicos de turismo
        "viaje romántico",
        "precio en dólares",
        "habitación doble",
        "pensión completa",
        "excursión incluida"
    ]
    
    print(f"🧪 Ejecutando {len(test_queries)} búsquedas de prueba...")
    
    issues = []
    
    try:
        # Inicializar RAG service
        rag_service = RAGService()
        
        for query in test_queries:
            try:
                # Intentar búsqueda usando el método correcto
                results = rag_service.buscar_documentos(query, n_results=3)
                
                if results:
                    print(f"   ✅ '{query}': {len(results)} resultados")
                else:
                    print(f"   ℹ️  '{query}': Sin resultados")
                    
            except Exception as e:
                issues.append({
                    'query': query,
                    'issue': f'Error en búsqueda: {str(e)}'
                })
                print(f"   ❌ '{query}': Error - {str(e)}")
        
        if not issues:
            print("\n✅ Todas las búsquedas funcionan correctamente")
            
    except Exception as e:
        print(f"❌ Error inicializando RAG: {str(e)}")
        issues.append({'issue': f'Error RAG: {str(e)}'})
    
    return issues


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def generate_report(all_issues):
    """Genera reporte final de auditoría."""
    print("\n" + "=" * 70)
    print("📊 REPORTE FINAL DE AUDITORÍA")
    print("=" * 70)
    
    # Crear directorio de resultados
    results_dir = Path(__file__).parent.parent.parent / "audit_results"
    results_dir.mkdir(exist_ok=True)
    
    # Generar reporte
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = results_dir / f"audit_report_{timestamp}.txt"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("AUDITORÍA DE ENCODING - AGENTE TURISMO IA\n")
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")
        
        total_issues = sum(len(issues) for issues in all_issues.values())
        
        if total_issues == 0:
            f.write("✅ RESULTADO: NO SE ENCONTRARON PROBLEMAS\n\n")
            f.write("El sistema maneja correctamente caracteres UTF-8.\n")
            f.write("No se requieren correcciones de encoding.\n")
            
            print("\n✅ SISTEMA OK: No se detectaron problemas de encoding")
            print(f"📄 Reporte guardado en: {report_file}")
            
        else:
            f.write(f"⚠️  RESULTADO: {total_issues} PROBLEMAS DETECTADOS\n\n")
            
            for section, issues in all_issues.items():
                if issues:
                    f.write(f"\n{section}:\n")
                    f.write("-" * 70 + "\n")
                    for issue in issues:
                        f.write(f"  • {json.dumps(issue, ensure_ascii=False, indent=4)}\n")
            
            print(f"\n⚠️  SE DETECTARON {total_issues} PROBLEMAS")
            print(f"📄 Reporte detallado en: {report_file}")
            
            # Guardar archivos problemáticos en JSON
            json_file = results_dir / f"problematic_items_{timestamp}.json"
            with open(json_file, 'w', encoding='utf-8') as jf:
                json.dump(all_issues, jf, ensure_ascii=False, indent=2)
            
            print(f"📄 Detalles JSON en: {json_file}")
    
    print("\n" + "=" * 70)
    return total_issues, report_file


def main():
    """Ejecuta auditoría completa."""
    
    all_issues = {
        'python_files': [],
        'pdfs': [],
        'chromadb': [],
        'searches': []
    }
    
    # Ejecutar auditorías
    all_issues['python_files'] = audit_python_files()
    all_issues['pdfs'] = audit_pdfs()
    all_issues['chromadb'] = audit_chromadb()
    all_issues['searches'] = audit_search_functionality()
    
    # Generar reporte
    total_issues, report_file = generate_report(all_issues)
    
    # Código de salida
    return 0 if total_issues == 0 else 1, report_file


if __name__ == "__main__":
    try:
        exit_code, report_file = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Auditoría cancelada por el usuario")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
