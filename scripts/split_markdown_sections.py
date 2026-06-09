#!/usr/bin/env python3
"""
Script pour diviser les documents markdown en sections
avec un index détaillé pour faciliter la navigation
"""

import re
from pathlib import Path
from typing import List, Tuple

def extract_sections(markdown_content: str) -> List[Tuple[str, str, int]]:
    """
    Extrait les sections basées sur les titres markdown
    
    Returns:
        Liste de tuples (niveau, titre, position)
    """
    sections = []
    lines = markdown_content.split('\n')
    
    for i, line in enumerate(lines):
        # Détecte les titres markdown (# à ######)
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            sections.append((level, title, i))
    
    return sections

def create_anchor(title: str) -> str:
    """Crée un anchor HTML compatible depuis un titre"""
    anchor = title.lower()
    # Supprime les caractères spéciaux
    anchor = re.sub(r'[^\w\s-]', '', anchor)
    # Remplace les espaces par des tirets
    anchor = re.sub(r'[-\s]+', '-', anchor)
    return anchor

def split_by_sections(markdown_file: Path, output_dir: Path):
    """
    Divise un document markdown en sections individuelles
    et crée un index détaillé
    """
    print(f"\n📄 Traitement de: {markdown_file.name}")
    
    # Lecture du contenu
    with open(markdown_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extraction des sections
    sections = extract_sections(content)
    print(f"   Sections trouvées: {len(sections)}")
    
    if not sections:
        print("   ⚠️  Aucune section détectée")
        return
    
    # Création du répertoire de sortie
    base_name = markdown_file.stem
    sections_dir = output_dir / f"{base_name}_sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    
    # Création de l'index détaillé
    index_content = f"# Index détaillé - {base_name}\n\n"
    index_content += f"> Document source: {markdown_file.name}\n"
    index_content += f"> Sections: {len(sections)}\n\n"
    index_content += "## Table des matières\n\n"
    
    lines = content.split('\n')
    
    # Génération de l'index avec hiérarchie
    for i, (level, title, line_num) in enumerate(sections):
        indent = "  " * (level - 1)
        anchor = create_anchor(title)
        section_file = f"section_{i+1:03d}_{anchor[:50]}.md"
        
        index_content += f"{indent}- [{title}]({base_name}_sections/{section_file})\n"
    
    # Sauvegarde de l'index
    index_path = output_dir / f"{base_name}_INDEX_DETAILLE.md"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_content)
    print(f"   ✅ Index créé: {index_path.name}")
    
    # Division en fichiers de section
    for i, (level, title, start_line) in enumerate(sections):
        # Détermine la fin de la section
        if i < len(sections) - 1:
            end_line = sections[i + 1][2]
        else:
            end_line = len(lines)
        
        # Extrait le contenu de la section
        section_lines = lines[start_line:end_line]
        section_content = '\n'.join(section_lines)
        
        # Crée le nom de fichier
        anchor = create_anchor(title)
        section_file = f"section_{i+1:03d}_{anchor[:50]}.md"
        section_path = sections_dir / section_file
        
        # En-tête de section
        header = f"# Section {i+1}: {title}\n\n"
        header += f"> Extrait de: {markdown_file.name}\n"
        header += f"> Niveau: {level}\n"
        header += f"> Position: ligne {start_line + 1}\n\n"
        header += "---\n\n"
        
        # Navigation
        nav = "\n\n---\n\n## Navigation\n\n"
        if i > 0:
            prev_anchor = create_anchor(sections[i-1][1])
            prev_file = f"section_{i:03d}_{prev_anchor[:50]}.md"
            nav += f"← [Section précédente: {sections[i-1][1]}]({prev_file})\n\n"
        
        nav += f"↑ [Retour à l'index](../{base_name}_INDEX_DETAILLE.md)\n\n"
        
        if i < len(sections) - 1:
            next_anchor = create_anchor(sections[i+1][1])
            next_file = f"section_{i+2:03d}_{next_anchor[:50]}.md"
            nav += f"→ [Section suivante: {sections[i+1][1]}]({next_file})\n"
        
        # Assemblage et sauvegarde
        full_content = header + section_content + nav
        with open(section_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
    
    print(f"   📁 {len(sections)} sections créées dans: {sections_dir.name}/")
    
    # Statistiques
    total_chars = sum(len(lines[sections[i][2]:sections[i+1][2] if i < len(sections)-1 else len(lines)]) 
                     for i in range(len(sections)))
    avg_section_size = total_chars // len(sections) if sections else 0
    
    print(f"   📊 Taille moyenne par section: {avg_section_size:,} caractères")

def main():
    """Fonction principale"""
    docs_dir = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/data/markdown_docs")
    
    markdown_files = [
        docs_dir / "Nicolas_RANDRIANARIJAONA_Thèse_20260124.md",
        docs_dir / "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md"
    ]
    
    print("=" * 70)
    print("✂️  Division des documents en sections indexées")
    print("=" * 70)
    
    for md_file in markdown_files:
        if md_file.exists():
            split_by_sections(md_file, docs_dir)
        else:
            print(f"\n⚠️  Fichier introuvable: {md_file}")
    
    print("\n" + "=" * 70)
    print("✨ Division terminée!")
    print("=" * 70)

if __name__ == "__main__":
    main()
