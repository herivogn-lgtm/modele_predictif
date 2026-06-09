# Documentation Acridienne en Markdown

Ce répertoire contient les documents PDF convertis en format Markdown pour faciliter l'analyse par l'IA et la recherche de contenu.

## 📋 Résumé de la conversion

**Date de conversion** : 7 juin 2026  
**Documents traités** : 2 PDFs scientifiques sur les criquets à Madagascar

---

## 📁 Structure des fichiers

### 1. Thèse de Nicolas RANDRIANARIJAONA (2026)

**Fichiers principaux :**
- `Nicolas_RANDRIANARIJAONA_Thèse_20260124.md` (46 KB, ~6,000 mots)
  - Document complet en un seul fichier
  - Contient métadonnées et contenu intégral

- `Nicolas_RANDRIANARIJAONA_Thèse_20260124_INDEX_DETAILLE.md`
  - Index hiérarchisé avec 38 sections
  - Liens vers chaque section individuelle

- `Nicolas_RANDRIANARIJAONA_Thèse_20260124_sections/` (40 fichiers)
  - Sections individuelles avec navigation
  - Chaque section contient : titre, métadonnées, contenu, liens de navigation

**Sections principales :**
- I. Introduction générale (contexte mondial, africain, Madagascar)
- II. État de l'art, problématique et méthodologie
- III. Conclusion générale
- IV. Références bibliographiques

---

### 2. Manuel de Lutte Préventive Antiacridienne

**Fichiers principaux :**
- `MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md` (593 KB, ~81,000 mots)
  - Document complet en un seul fichier
  - 307 pages extraites avec OCR sur les pages images

- `MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_INDEX_DETAILLE.md`
  - Index hiérarchisé avec 322 sections
  - Navigation complète du manuel

- `MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_sections/` (322 fichiers)
  - Sections détaillées par thématique
  - Navigation inter-sections

**Sections principales :**
1. Les locustes malgaches (taxonomie, bio-écologie, phases)
2. Le Criquet migrateur (*Locusta migratoria capito*)
3. Le Criquet nomade (*Nomadacris septemfasciata*)
4. Techniques de prospection et surveillance
5. Méthodes de lutte préventive
6. Organisation et logistique

---

## 🔍 Utilisation pour l'IA

### Avantages du format Markdown

1. **Recherche textuelle facilitée** : Format texte brut, facilement analysable
2. **Structure hiérarchique préservée** : Titres et sous-titres conservés
3. **Navigation optimisée** : Index détaillés avec liens
4. **Sections modulaires** : Chaque section peut être chargée indépendamment
5. **Métadonnées explicites** : Source, position, niveau de hiérarchie

### Cas d'usage

```python
# Exemple : Charger une section spécifique
with open('Nicolas_RANDRIANARIJAONA_Thèse_20260124_sections/section_005_madagascar-vulnérabilité-structurelle-et-crises-ré.md', 'r') as f:
    section = f.read()
    # Analyser le contenu...
```

```python
# Exemple : Rechercher dans tout le corpus
import glob
for section in glob.glob('*_sections/*.md'):
    with open(section) as f:
        if 'grégarisation' in f.read().lower():
            print(f"Trouvé dans: {section}")
```

---

## 📊 Statistiques

| Document | Pages | Mots | Sections | Taille MD |
|----------|-------|------|----------|-----------|
| Thèse RANDRIANARIJAONA | 22 | 5,937 | 38 | 46 KB |
| Manuel de Lutte Préventive | 307 | 81,357 | 322 | 593 KB |
| **Total** | **329** | **87,294** | **360** | **639 KB** |

---

## 🛠️ Scripts utilisés

### `pdf_to_markdown.py`
Convertit les PDFs en markdown avec :
- Extraction automatique du texte
- OCR sur les pages images (Tesseract)
- Nettoyage et formatage
- Génération de métadonnées

### `split_markdown_sections.py`
Divise les documents en sections avec :
- Détection automatique des titres (# à ######)
- Création d'index hiérarchisés
- Navigation entre sections (précédent/suivant/index)
- Génération d'anchors compatibles

---

## 📖 Thématiques principales

### Contenu scientifique
- **Biologie acridienne** : cycle de vie, phases (solitaire/grégaire), reproduction
- **Écologie** : facteurs environnementaux, habitats favorables, dynamique des populations
- **Géographie** : aires grégarigènes, zones de pullulation, migrations
- **Climatologie** : impact des pluies, température, humidité
- **Télédétection** : utilisation du NDVI, données satellitaires

### Contenu opérationnel
- **Surveillance** : prospections, collecte de données, systèmes d'alerte
- **Lutte préventive** : stratégies, techniques, produits phytosanitaires
- **Organisation** : structure institutionnelle (CNA/IFVM), gouvernance
- **Financement** : modèles de financement, dépendance aux bailleurs
- **Modélisation prédictive** : machine learning, prévision des pullulations

---

## 🎯 Pour les développeurs

### Charger l'index complet
```python
import json
from pathlib import Path

def load_document_index(doc_name):
    """Charge l'index d'un document"""
    index_path = Path(f'data/markdown_docs/{doc_name}_INDEX_DETAILLE.md')
    with open(index_path) as f:
        return f.read()

# Charger tous les index
these_index = load_document_index('Nicolas_RANDRIANARIJAONA_Thèse_20260124')
manuel_index = load_document_index('MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)')
```

### Recherche sémantique
```python
def search_in_sections(keyword, doc_sections_dir):
    """Recherche un mot-clé dans toutes les sections"""
    results = []
    for section_file in Path(doc_sections_dir).glob('*.md'):
        with open(section_file) as f:
            content = f.read()
            if keyword.lower() in content.lower():
                results.append({
                    'file': section_file.name,
                    'path': str(section_file)
                })
    return results

# Exemple
results = search_in_sections('grégarisation', 
    'data/markdown_docs/MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_sections')
```

---

## 🔗 Liens utiles

- **Script de conversion** : `/scripts/pdf_to_markdown.py`
- **Script de division** : `/scripts/split_markdown_sections.py`
- **Données sources** : `/data/Modle_predictif_acridien/`
- **Documentation projet** : `/CLAUDE.md`

---

## ⚠️ Notes techniques

### Extraction OCR
- Certaines pages du manuel ont nécessité de l'OCR (85 pages sur 307)
- Les images et graphiques ont été intentionnellement omis
- La qualité du texte extrait peut varier selon la source

### Format des fichiers
- Encodage : UTF-8
- Format de ligne : Unix (LF)
- Structure markdown : CommonMark compatible

### Limitations
- Les tableaux complexes peuvent avoir une mise en forme approximative
- Les équations mathématiques sont en texte brut
- Les images et schémas ne sont pas inclus (mentions "<==picture omitted==>")

---

*Généré automatiquement le 7 juin 2026*  
*Scripts Python disponibles dans `/scripts/`*
