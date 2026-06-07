#!/usr/bin/env python3
"""
Script de vérification de la conversion PDF → Markdown
Vérifie l'intégrité et la structure des documents convertis
"""

from pathlib import Path
import json

BASE_DIR = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/data/markdown_docs")

def check_file_exists(filepath: Path, description: str) -> bool:
    """Vérifie l'existence d'un fichier"""
    if filepath.exists():
        print(f"   ✅ {description}")
        return True
    else:
        print(f"   ❌ {description} - MANQUANT")
        return False

def verify_conversion():
    """Vérification complète de la conversion"""
    print("=" * 70)
    print("🔍 VÉRIFICATION DE LA CONVERSION PDF → MARKDOWN")
    print("=" * 70)
    print()
    
    all_ok = True
    
    # 1. Vérifier les fichiers principaux
    print("📄 1. Fichiers principaux")
    files_to_check = [
        (BASE_DIR / "README.md", "README.md"),
        (BASE_DIR / "GUIDE_RAPIDE.md", "GUIDE_RAPIDE.md"),
        (BASE_DIR / "documents_index.json", "Index JSON"),
        (BASE_DIR / "these_sections.jsonl", "Thèse en JSONL"),
    ]
    
    for filepath, desc in files_to_check:
        if not check_file_exists(filepath, desc):
            all_ok = False
    print()
    
    # 2. Vérifier les documents thèse
    print("📚 2. Document Thèse RANDRIANARIJAONA")
    these_files = [
        (BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124.md", "Document complet"),
        (BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124_INDEX_DETAILLE.md", "Index détaillé"),
        (BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124_sections", "Dossier sections"),
    ]
    
    for filepath, desc in these_files:
        if not check_file_exists(filepath, desc):
            all_ok = False
    
    # Compter les sections
    sections_dir = BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124_sections"
    if sections_dir.exists():
        sections_count = len(list(sections_dir.glob("*.md")))
        print(f"   📊 Sections trouvées: {sections_count}")
        if sections_count != 38:
            print(f"   ⚠️  Attendu 38 sections, trouvé {sections_count}")
            all_ok = False
    print()
    
    # 3. Vérifier les documents manuel
    print("📚 3. Manuel de Lutte Préventive")
    manuel_files = [
        (BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md", "Document complet"),
        (BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_INDEX_DETAILLE.md", "Index détaillé"),
        (BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_sections", "Dossier sections"),
    ]
    
    for filepath, desc in manuel_files:
        if not check_file_exists(filepath, desc):
            all_ok = False
    
    # Compter les sections
    sections_dir = BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_sections"
    if sections_dir.exists():
        sections_count = len(list(sections_dir.glob("*.md")))
        print(f"   📊 Sections trouvées: {sections_count}")
        if sections_count != 322:
            print(f"   ⚠️  Attendu 322 sections, trouvé {sections_count}")
            all_ok = False
    print()
    
    # 4. Vérifier les scripts
    print("🛠️  4. Scripts Python")
    scripts_dir = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/scripts")
    scripts = [
        (scripts_dir / "pdf_to_markdown.py", "Conversion PDF"),
        (scripts_dir / "split_markdown_sections.py", "Division en sections"),
        (scripts_dir / "markdown_usage_examples.py", "Exemples d'utilisation"),
        (scripts_dir / "markdown_ai_utils.py", "Utilitaires IA"),
    ]
    
    for filepath, desc in scripts:
        if not check_file_exists(filepath, desc):
            all_ok = False
    print()
    
    # 5. Vérifier l'index JSON
    print("📊 5. Validation de l'index JSON")
    index_path = BASE_DIR / "documents_index.json"
    if index_path.exists():
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)
            
            print(f"   ✅ Index JSON valide")
            print(f"   📈 Documents: {len(index['documents'])}")
            print(f"   📈 Mots-clés: {len(index['keywords'])}")
            print(f"   📈 Sections totales: {index['total_sections']}")
            
            if index['total_sections'] != 360:
                print(f"   ⚠️  Attendu 360 sections, trouvé {index['total_sections']}")
                all_ok = False
        except Exception as e:
            print(f"   ❌ Erreur de lecture JSON: {e}")
            all_ok = False
    print()
    
    # 6. Vérifier les tailles de fichiers
    print("💾 6. Tailles des fichiers")
    these_path = BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124.md"
    manuel_path = BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md"
    
    if these_path.exists():
        size_kb = these_path.stat().st_size / 1024
        print(f"   📏 Thèse: {size_kb:.1f} KB")
        if size_kb < 40 or size_kb > 60:
            print(f"   ⚠️  Taille inhabituelle (attendu ~46 KB)")
    
    if manuel_path.exists():
        size_kb = manuel_path.stat().st_size / 1024
        print(f"   📏 Manuel: {size_kb:.1f} KB")
        if size_kb < 500 or size_kb > 700:
            print(f"   ⚠️  Taille inhabituelle (attendu ~593 KB)")
    print()
    
    # Résultat final
    print("=" * 70)
    if all_ok:
        print("✅ VÉRIFICATION RÉUSSIE - Tous les fichiers sont présents")
    else:
        print("⚠️  VÉRIFICATION INCOMPLÈTE - Certains fichiers sont manquants")
    print("=" * 70)
    print()
    
    # Recommandations
    print("📝 Prochaines étapes:")
    print("   1. Consulter le README.md pour la documentation complète")
    print("   2. Consulter le GUIDE_RAPIDE.md pour les exemples")
    print("   3. Utiliser markdown_ai_utils.py pour l'intégration IA")
    print("   4. Charger les sections dans votre système de RAG")
    print()

if __name__ == "__main__":
    verify_conversion()
