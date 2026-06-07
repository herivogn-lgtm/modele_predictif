#!/usr/bin/env python3
"""
Utilitaires pour préparer les documents markdown
pour l'analyse par des modèles d'IA (RAG, embeddings, etc.)
"""

from pathlib import Path
from typing import List, Dict, Optional
import json
import re

BASE_DIR = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/data/markdown_docs")

class MarkdownDocumentLoader:
    """Chargeur de documents markdown pour l'IA"""
    
    def __init__(self, base_dir: Path = BASE_DIR):
        self.base_dir = base_dir
        
    def load_document(self, doc_name: str) -> str:
        """Charge un document complet"""
        doc_path = self.base_dir / f"{doc_name}.md"
        with open(doc_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def load_section(self, doc_name: str, section_number: int) -> Dict[str, str]:
        """Charge une section spécifique avec métadonnées"""
        sections_dir = self.base_dir / f"{doc_name}_sections"
        section_files = sorted(sections_dir.glob("section_*.md"))
        
        if section_number < 1 or section_number > len(section_files):
            raise ValueError(f"Section {section_number} introuvable")
        
        section_file = section_files[section_number - 1]
        with open(section_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extraire métadonnées
        metadata = self._extract_metadata(content)
        
        return {
            'number': section_number,
            'file': section_file.name,
            'content': content,
            'metadata': metadata
        }
    
    def load_all_sections(self, doc_name: str) -> List[Dict[str, str]]:
        """Charge toutes les sections d'un document"""
        sections_dir = self.base_dir / f"{doc_name}_sections"
        sections = []
        
        for i, section_file in enumerate(sorted(sections_dir.glob("section_*.md")), 1):
            with open(section_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            sections.append({
                'number': i,
                'file': section_file.name,
                'content': content,
                'metadata': self._extract_metadata(content)
            })
        
        return sections
    
    def _extract_metadata(self, content: str) -> Dict[str, str]:
        """Extrait les métadonnées d'une section"""
        metadata = {}
        
        # Titre
        title_match = re.search(r'^# Section \d+: (.+)$', content, re.MULTILINE)
        if title_match:
            metadata['title'] = title_match.group(1)
        
        # Document source
        source_match = re.search(r'> Extrait de: (.+)$', content, re.MULTILINE)
        if source_match:
            metadata['source'] = source_match.group(1)
        
        # Niveau
        level_match = re.search(r'> Niveau: (\d+)$', content, re.MULTILINE)
        if level_match:
            metadata['level'] = int(level_match.group(1))
        
        return metadata
    
    def search_in_sections(self, doc_name: str, query: str, 
                          max_results: int = 10) -> List[Dict]:
        """Recherche dans les sections et retourne les plus pertinentes"""
        sections = self.load_all_sections(doc_name)
        results = []
        
        query_lower = query.lower()
        
        for section in sections:
            content_lower = section['content'].lower()
            if query_lower in content_lower:
                count = content_lower.count(query_lower)
                results.append({
                    'section': section['number'],
                    'title': section['metadata'].get('title', 'Sans titre'),
                    'file': section['file'],
                    'occurrences': count,
                    'preview': self._extract_preview(section['content'], query, 200)
                })
        
        # Trier par pertinence
        results.sort(key=lambda x: x['occurrences'], reverse=True)
        return results[:max_results]
    
    def _extract_preview(self, content: str, query: str, 
                        context_chars: int = 200) -> str:
        """Extrait un aperçu autour du mot-clé"""
        lower_content = content.lower()
        query_lower = query.lower()
        
        pos = lower_content.find(query_lower)
        if pos == -1:
            return ""
        
        start = max(0, pos - context_chars // 2)
        end = min(len(content), pos + len(query) + context_chars // 2)
        
        preview = content[start:end]
        if start > 0:
            preview = "..." + preview
        if end < len(content):
            preview = preview + "..."
        
        return preview.strip()

def prepare_for_embeddings(doc_name: str, chunk_size: int = 1000,
                          overlap: int = 200) -> List[Dict]:
    """
    Prépare le document pour la création d'embeddings
    en le divisant en chunks avec overlap
    """
    loader = MarkdownDocumentLoader()
    content = loader.load_document(doc_name)
    
    chunks = []
    start = 0
    chunk_id = 1
    
    while start < len(content):
        end = start + chunk_size
        chunk_text = content[start:end]
        
        # Essayer de terminer à un saut de ligne
        if end < len(content):
            last_newline = chunk_text.rfind('\n')
            if last_newline > chunk_size // 2:
                end = start + last_newline
                chunk_text = content[start:end]
        
        chunks.append({
            'id': chunk_id,
            'text': chunk_text,
            'start': start,
            'end': end,
            'length': len(chunk_text)
        })
        
        start = end - overlap
        chunk_id += 1
    
    return chunks

def export_to_jsonl(doc_name: str, output_file: str):
    """Exporte les sections en format JSONL pour l'IA"""
    loader = MarkdownDocumentLoader()
    sections = loader.load_all_sections(doc_name)
    
    output_path = Path(output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        for section in sections:
            # Nettoyer le contenu (enlever navigation, etc.)
            clean_content = re.sub(r'---\n\n## Navigation.*$', '', 
                                  section['content'], flags=re.DOTALL)
            
            record = {
                'id': f"{doc_name}_section_{section['number']:03d}",
                'title': section['metadata'].get('title', ''),
                'level': section['metadata'].get('level', 1),
                'content': clean_content.strip(),
                'source': doc_name
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    print(f"✅ Export JSONL terminé: {output_path}")
    print(f"   Sections exportées: {len(sections)}")

def create_summary_index():
    """Crée un index récapitulatif de tous les documents"""
    loader = MarkdownDocumentLoader()
    
    documents = [
        "Nicolas_RANDRIANARIJAONA_Thèse_20260124",
        "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)"
    ]
    
    index = {
        'documents': [],
        'total_sections': 0,
        'keywords': {}
    }
    
    # Mots-clés à indexer
    keywords = [
        'criquet', 'locuste', 'grégaire', 'solitaire', 'pullulation',
        'essaim', 'grégarisation', 'migration', 'surveillance', 'lutte',
        'prévention', 'NDVI', 'télédétection', 'Madagascar', 'climat'
    ]
    
    for doc_name in documents:
        sections = loader.load_all_sections(doc_name)
        content = loader.load_document(doc_name)
        
        doc_info = {
            'name': doc_name,
            'sections': len(sections),
            'characters': len(content),
            'words': len(content.split()),
            'keywords': {}
        }
        
        # Compter les mots-clés
        content_lower = content.lower()
        for keyword in keywords:
            count = content_lower.count(keyword.lower())
            if count > 0:
                doc_info['keywords'][keyword] = count
                
                if keyword not in index['keywords']:
                    index['keywords'][keyword] = {'total': 0, 'documents': {}}
                
                index['keywords'][keyword]['total'] += count
                index['keywords'][keyword]['documents'][doc_name] = count
        
        index['documents'].append(doc_info)
        index['total_sections'] += len(sections)
    
    return index

def main():
    """Démonstration des utilitaires"""
    print("=" * 70)
    print("🤖 Utilitaires IA pour documents markdown acridiens")
    print("=" * 70)
    print()
    
    loader = MarkdownDocumentLoader()
    
    # Test 1 : Charger une section
    print("📄 Test 1 : Chargement d'une section")
    section = loader.load_section("Nicolas_RANDRIANARIJAONA_Thèse_20260124", 5)
    print(f"   Section {section['number']}: {section['metadata'].get('title', 'N/A')}")
    print(f"   Taille: {len(section['content'])} caractères")
    print()
    
    # Test 2 : Recherche
    print("🔍 Test 2 : Recherche dans les sections")
    results = loader.search_in_sections(
        "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)", 
        "télédétection", 
        max_results=5
    )
    print(f"   Résultats trouvés: {len(results)}")
    for r in results[:3]:
        print(f"   • Section {r['section']}: {r['title']} ({r['occurrences']} fois)")
    print()
    
    # Test 3 : Chunks pour embeddings
    print("📦 Test 3 : Préparation de chunks pour embeddings")
    chunks = prepare_for_embeddings(
        "Nicolas_RANDRIANARIJAONA_Thèse_20260124",
        chunk_size=1000,
        overlap=200
    )
    print(f"   Chunks créés: {len(chunks)}")
    print(f"   Taille moyenne: {sum(c['length'] for c in chunks) // len(chunks)} caractères")
    print()
    
    # Test 4 : Export JSONL
    print("💾 Test 4 : Export en JSONL")
    output_dir = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/data/markdown_docs")
    export_to_jsonl(
        "Nicolas_RANDRIANARIJAONA_Thèse_20260124",
        output_dir / "these_sections.jsonl"
    )
    print()
    
    # Test 5 : Index récapitulatif
    print("📊 Test 5 : Création d'un index récapitulatif")
    index = create_summary_index()
    print(f"   Documents indexés: {len(index['documents'])}")
    print(f"   Sections totales: {index['total_sections']}")
    print(f"   Mots-clés indexés: {len(index['keywords'])}")
    print("\n   Top 5 mots-clés les plus fréquents:")
    sorted_keywords = sorted(index['keywords'].items(), 
                           key=lambda x: x[1]['total'], 
                           reverse=True)
    for kw, data in sorted_keywords[:5]:
        print(f"      • {kw}: {data['total']} occurrences")
    
    # Sauvegarder l'index
    index_path = output_dir / "documents_index.json"
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\n   Index sauvegardé: {index_path}")
    print()
    
    print("=" * 70)
    print("✅ Tous les tests ont réussi!")
    print("=" * 70)

if __name__ == "__main__":
    main()
