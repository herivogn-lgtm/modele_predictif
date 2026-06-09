#!/usr/bin/env python3
"""
Exemples d'utilisation des documents markdown
pour l'analyse IA et la recherche de contenu
"""

from pathlib import Path
import re
from typing import List, Dict

# Configuration des chemins
BASE_DIR = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/data/markdown_docs")
THESE_SECTIONS = BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124_sections"
MANUEL_SECTIONS = BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_sections"

def example_1_load_full_document():
    """Exemple 1 : Charger un document complet"""
    print("=" * 70)
    print("Exemple 1 : Charger le document complet de la thèse")
    print("=" * 70)
    
    these_path = BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124.md"
    with open(these_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"📄 Document chargé: {these_path.name}")
    print(f"📊 Taille: {len(content):,} caractères")
    print(f"📝 Mots: {len(content.split()):,}")
    print(f"📑 Lignes: {content.count(chr(10)):,}")
    print()

def example_2_search_keyword(keyword: str):
    """Exemple 2 : Rechercher un mot-clé dans toutes les sections"""
    print("=" * 70)
    print(f"Exemple 2 : Recherche du mot-clé '{keyword}'")
    print("=" * 70)
    
    results = []
    for section_file in MANUEL_SECTIONS.glob("*.md"):
        with open(section_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if keyword.lower() in content.lower():
                # Extraire le titre de la section
                match = re.search(r'^#+ (.+)$', content, re.MULTILINE)
                title = match.group(1) if match else section_file.stem
                
                # Compter les occurrences
                count = content.lower().count(keyword.lower())
                results.append({
                    'file': section_file.name,
                    'title': title,
                    'count': count
                })
    
    # Trier par nombre d'occurrences
    results.sort(key=lambda x: x['count'], reverse=True)
    
    print(f"🔍 Résultats trouvés: {len(results)} sections")
    print(f"📊 Occurrences totales: {sum(r['count'] for r in results)}")
    print("\n📋 Top 10 sections:")
    for i, result in enumerate(results[:10], 1):
        print(f"   {i}. {result['title']} ({result['count']} occurrences)")
        print(f"      → {result['file']}")
    print()

def example_3_extract_sections_by_level(level: int = 2):
    """Exemple 3 : Extraire toutes les sections d'un niveau donné"""
    print("=" * 70)
    print(f"Exemple 3 : Extraire les sections de niveau {level}")
    print("=" * 70)
    
    manuel_path = BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md"
    with open(manuel_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern pour détecter les titres du niveau spécifié
    pattern = r'^' + '#' * level + r'\s+(.+)$'
    sections = re.findall(pattern, content, re.MULTILINE)
    
    print(f"📚 Sections de niveau {level} trouvées: {len(sections)}")
    print("\n📋 Liste des sections:")
    for i, section in enumerate(sections[:20], 1):
        print(f"   {i}. {section}")
    
    if len(sections) > 20:
        print(f"   ... et {len(sections) - 20} autres sections")
    print()

def example_4_extract_context_around_keyword(keyword: str, context_lines: int = 3):
    """Exemple 4 : Extraire le contexte autour d'un mot-clé"""
    print("=" * 70)
    print(f"Exemple 4 : Contexte autour de '{keyword}'")
    print("=" * 70)
    
    these_path = BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124.md"
    with open(these_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    results = []
    for i, line in enumerate(lines):
        if keyword.lower() in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            context = ''.join(lines[start:end])
            results.append({
                'line': i + 1,
                'context': context
            })
    
    print(f"🔍 Occurrences trouvées: {len(results)}")
    print("\n📄 Premiers résultats avec contexte:")
    for i, result in enumerate(results[:3], 1):
        print(f"\n--- Occurrence {i} (ligne {result['line']}) ---")
        print(result['context'])
        print("-" * 70)
    print()

def example_5_statistics_by_document():
    """Exemple 5 : Statistiques comparatives des documents"""
    print("=" * 70)
    print("Exemple 5 : Statistiques comparatives")
    print("=" * 70)
    
    documents = [
        ("Thèse RANDRIANARIJAONA", 
         BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124.md"),
        ("Manuel de Lutte Préventive", 
         BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md")
    ]
    
    print(f"\n{'Document':<30} {'Caractères':>12} {'Mots':>10} {'Sections':>10}")
    print("-" * 70)
    
    for name, path in documents:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        chars = len(content)
        words = len(content.split())
        sections = len(re.findall(r'^#{1,6}\s+', content, re.MULTILINE))
        
        print(f"{name:<30} {chars:>12,} {words:>10,} {sections:>10}")
    print()

def example_6_build_glossary(terms: List[str]):
    """Exemple 6 : Construire un glossaire à partir de termes"""
    print("=" * 70)
    print("Exemple 6 : Glossaire des termes acridiens")
    print("=" * 70)
    
    glossary = {}
    manuel_path = BASE_DIR / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md"
    
    with open(manuel_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for term in terms:
        # Rechercher les définitions (lignes contenant le terme suivi de ":")
        pattern = rf'^.*{term}.*:.*$'
        definitions = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
        
        glossary[term] = {
            'count': content.lower().count(term.lower()),
            'definitions': definitions[:3]  # Top 3 définitions
        }
    
    print("\n📖 Glossaire généré:")
    for term, data in glossary.items():
        print(f"\n🔹 {term.upper()}")
        print(f"   Occurrences: {data['count']}")
        if data['definitions']:
            print(f"   Définitions trouvées:")
            for def_text in data['definitions'][:2]:
                print(f"   • {def_text[:100]}...")
    print()

def example_7_list_all_sections_with_navigation():
    """Exemple 7 : Lister les sections avec leurs liens de navigation"""
    print("=" * 70)
    print("Exemple 7 : Sections avec navigation")
    print("=" * 70)
    
    index_path = BASE_DIR / "Nicolas_RANDRIANARIJAONA_Thèse_20260124_INDEX_DETAILLE.md"
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extraire les liens markdown
    links = re.findall(r'\[(.+?)\]\((.+?)\)', content)
    
    print(f"\n📚 Sections indexées: {len(links)}")
    print("\n📋 Structure (10 premières):")
    for i, (title, path) in enumerate(links[:10], 1):
        level = title.count('*') // 2 if '*' in title else 0
        indent = "  " * level
        clean_title = title.replace('**', '').replace('_', '')
        print(f"   {indent}{i}. {clean_title}")
        print(f"   {indent}   → {Path(path).name}")
    print()

def main():
    """Exécuter tous les exemples"""
    print("\n🦗 EXEMPLES D'UTILISATION DES DOCUMENTS MARKDOWN ACRIDIENS")
    print("=" * 70)
    print()
    
    # Exemple 1 : Charger document complet
    example_1_load_full_document()
    
    # Exemple 2 : Recherche de mot-clé
    example_2_search_keyword("grégarisation")
    
    # Exemple 3 : Extraire sections par niveau
    example_3_extract_sections_by_level(2)
    
    # Exemple 4 : Contexte autour d'un mot-clé
    example_4_extract_context_around_keyword("Locusta migratoria", context_lines=2)
    
    # Exemple 5 : Statistiques
    example_5_statistics_by_document()
    
    # Exemple 6 : Glossaire
    terms = ["criquet", "locuste", "grégaire", "solitaire", "pullulation", "essaim"]
    example_6_build_glossary(terms)
    
    # Exemple 7 : Navigation
    example_7_list_all_sections_with_navigation()
    
    print("=" * 70)
    print("✅ Tous les exemples ont été exécutés avec succès!")
    print("=" * 70)

if __name__ == "__main__":
    main()
