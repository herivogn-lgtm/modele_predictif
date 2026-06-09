#!/usr/bin/env python3
"""
Script pour convertir les PDFs acridiens en markdown structuré
avec table des matières et indexation pour faciliter l'analyse IA
"""

import pymupdf4llm
import os
import re
from pathlib import Path

def clean_text(text):
    """Nettoie le texte extrait du PDF"""
    # Supprime les espaces multiples
    text = re.sub(r' +', ' ', text)
    # Supprime les sauts de ligne multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def extract_toc(pdf_path):
    """Extrait la table des matières du PDF si disponible"""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    toc = doc.get_toc()
    doc.close()
    return toc

def generate_index(toc, output_path):
    """Génère un fichier index à partir de la table des matières"""
    if not toc:
        return None
    
    index_content = "# Index\n\n"
    for level, title, page in toc:
        indent = "  " * (level - 1)
        # Créer un lien anchor compatible markdown
        anchor = re.sub(r'[^\w\s-]', '', title.lower())
        anchor = re.sub(r'[-\s]+', '-', anchor)
        index_content += f"{indent}- [{title}](#{anchor}) (page {page})\n"
    
    return index_content

def pdf_to_markdown(pdf_path, output_dir, max_pages=None):
    """
    Convertit un PDF en markdown avec structure et index
    
    Args:
        pdf_path: Chemin vers le fichier PDF
        output_dir: Répertoire de sortie pour les fichiers markdown
        max_pages: Nombre maximum de pages à traiter (None = toutes)
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🔄 Traitement de: {pdf_path.name}")
    
    # Nom de base pour les fichiers de sortie
    base_name = pdf_path.stem.replace(' ', '_')
    
    # Extraction de la table des matières
    print("📑 Extraction de la table des matières...")
    toc = extract_toc(str(pdf_path))
    
    # Conversion du PDF en markdown
    print("📝 Conversion en markdown...")
    try:
        md_text = pymupdf4llm.to_markdown(
            str(pdf_path),
            pages=list(range(max_pages)) if max_pages else None,
            write_images=False,
            page_chunks=False
        )
        
        # Nettoyage du texte
        md_text = clean_text(md_text)
        
        # Création de l'en-tête du document
        header = f"""# {pdf_path.stem}

> Document source: {pdf_path.name}
> Date d'extraction: {Path(pdf_path).stat().st_mtime}
> 
> Ce document a été converti automatiquement du format PDF vers Markdown
> pour faciliter l'analyse et la compréhension par l'IA.

---

"""
        
        # Génération de l'index
        index_content = ""
        if toc:
            print(f"📊 Table des matières trouvée: {len(toc)} entrées")
            index_content = generate_index(toc, output_dir)
            if index_content:
                index_content += "\n---\n\n"
        
        # Assemblage du document final
        full_content = header + index_content + md_text
        
        # Sauvegarde du fichier principal
        main_output = output_dir / f"{base_name}.md"
        with open(main_output, 'w', encoding='utf-8') as f:
            f.write(full_content)
        print(f"✅ Fichier principal créé: {main_output}")
        
        # Sauvegarde de l'index séparé si disponible
        if index_content:
            index_output = output_dir / f"{base_name}_INDEX.md"
            with open(index_output, 'w', encoding='utf-8') as f:
                f.write(f"# Index - {pdf_path.stem}\n\n{index_content}")
            print(f"📋 Index créé: {index_output}")
        
        # Statistiques
        import pymupdf
        doc = pymupdf.open(str(pdf_path))
        total_pages = len(doc)
        doc.close()
        
        word_count = len(md_text.split())
        print(f"\n📈 Statistiques:")
        print(f"   - Pages: {total_pages}")
        print(f"   - Mots extraits: {word_count:,}")
        print(f"   - Taille markdown: {len(full_content):,} caractères")
        
        return main_output, index_output if index_content else None
        
    except Exception as e:
        print(f"❌ Erreur lors de la conversion: {e}")
        return None, None

def main():
    """Fonction principale"""
    base_path = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/data/Modle_predictif_acridien")
    output_dir = Path("/Users/olivierrakotondravao/Workspaces/modele_predictif/data/markdown_docs")
    
    pdfs = [
        base_path / "Nicolas RANDRIANARIJAONA_Thèse_20260124.pdf",
        base_path / "MANUEL DE LUTTE PRÉVENTIVE (VF).pdf"
    ]
    
    print("=" * 70)
    print("🦗 Conversion des documents acridiens en Markdown")
    print("=" * 70)
    print()
    
    results = []
    for pdf_path in pdfs:
        if pdf_path.exists():
            main_file, index_file = pdf_to_markdown(pdf_path, output_dir)
            if main_file:
                results.append((pdf_path.name, main_file, index_file))
            print()
        else:
            print(f"⚠️  Fichier introuvable: {pdf_path}")
            print()
    
    # Résumé final
    print("=" * 70)
    print("✨ Conversion terminée!")
    print("=" * 70)
    print("\n📁 Fichiers générés:\n")
    for original, main_file, index_file in results:
        print(f"   • {original}")
        print(f"     → {main_file}")
        if index_file:
            print(f"     → {index_file}")
        print()
    
    # Création d'un fichier README pour les docs markdown
    readme_path = output_dir / "README.md"
    readme_content = """# Documentation Acridienne en Markdown

Ce répertoire contient les documents PDF convertis en format Markdown pour faciliter 
l'analyse par l'IA et la recherche de contenu.

## Fichiers disponibles

"""
    for original, main_file, index_file in results:
        readme_content += f"### {original}\n\n"
        readme_content += f"- **Document principal**: [`{main_file.name}`]({main_file.name})\n"
        if index_file:
            readme_content += f"- **Index**: [`{index_file.name}`]({index_file.name})\n"
        readme_content += "\n"
    
    readme_content += """
## Utilisation

Ces documents peuvent être utilisés pour :
- Analyse de texte par l'IA
- Recherche de contenu spécifique
- Extraction d'informations sur les criquets migrateurs
- Référence pour le modèle prédictif acridien

## Structure

Chaque document contient :
1. Métadonnées du document source
2. Table des matières (index) si disponible
3. Contenu complet en markdown

---

*Généré automatiquement par pdf_to_markdown.py*
"""
    
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print(f"📖 README créé: {readme_path}")

if __name__ == "__main__":
    main()
