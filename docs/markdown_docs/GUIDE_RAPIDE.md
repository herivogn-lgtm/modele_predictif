# Guide d'utilisation rapide - Documents Markdown Acridiens

## 🎯 Objectif

Deux documents PDF scientifiques sur les criquets à Madagascar ont été convertis en format Markdown structuré pour faciliter l'analyse par l'IA et les systèmes de RAG (Retrieval-Augmented Generation).

---

## 📚 Documents disponibles

### 1. Thèse de Nicolas RANDRIANARIJAONA (2026)
- **Fichier complet** : `Nicolas_RANDRIANARIJAONA_Thèse_20260124.md` (46 KB)
- **Index détaillé** : `Nicolas_RANDRIANARIJAONA_Thèse_20260124_INDEX_DETAILLE.md`
- **Sections** : 38 sections individuelles dans le dossier `*_sections/`
- **Format JSONL** : `these_sections.jsonl` (pour embeddings/IA)

### 2. Manuel de Lutte Préventive
- **Fichier complet** : `MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md` (593 KB)
- **Index détaillé** : `MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_INDEX_DETAILLE.md`
- **Sections** : 322 sections individuelles dans le dossier `*_sections/`

---

## 🛠️ Scripts Python disponibles

### 1. `pdf_to_markdown.py`
Convertit les PDFs en markdown avec OCR automatique.

```bash
python scripts/pdf_to_markdown.py
```

**Fonctionnalités** :
- Extraction de texte avec OCR (Tesseract)
- Nettoyage et formatage automatique
- Génération de métadonnées
- Extraction de la table des matières

---

### 2. `split_markdown_sections.py`
Divise les documents en sections navigables.

```bash
python scripts/split_markdown_sections.py
```

**Fonctionnalités** :
- Détection automatique des titres (# à ######)
- Création d'index hiérarchisé
- Navigation entre sections (précédent/suivant)
- Métadonnées par section

---

### 3. `markdown_usage_examples.py`
Exemples d'utilisation des documents.

```bash
python scripts/markdown_usage_examples.py
```

**Exemples inclus** :
1. Charger un document complet
2. Rechercher un mot-clé dans toutes les sections
3. Extraire les sections d'un niveau donné
4. Extraire le contexte autour d'un mot-clé
5. Statistiques comparatives
6. Construire un glossaire
7. Navigation dans les sections

---

### 4. `markdown_ai_utils.py`
Utilitaires pour l'intégration IA.

```bash
python scripts/markdown_ai_utils.py
```

**Fonctionnalités** :
- Chargeur de documents avec métadonnées
- Recherche sémantique dans les sections
- Préparation de chunks pour embeddings
- Export en format JSONL
- Création d'index récapitulatif

---

## 💻 Exemples de code

### Charger un document complet

```python
from pathlib import Path

doc_path = Path("data/markdown_docs/Nicolas_RANDRIANARIJAONA_Thèse_20260124.md")
with open(doc_path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Mots: {len(content.split()):,}")
```

---

### Rechercher dans les sections

```python
from pathlib import Path
import re

sections_dir = Path("data/markdown_docs/MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_sections")

for section_file in sections_dir.glob("*.md"):
    with open(section_file, 'r', encoding='utf-8') as f:
        if 'grégarisation' in f.read().lower():
            print(f"Trouvé dans: {section_file.name}")
```

---

### Utiliser le MarkdownDocumentLoader

```python
from scripts.markdown_ai_utils import MarkdownDocumentLoader

loader = MarkdownDocumentLoader()

# Charger une section spécifique
section = loader.load_section("Nicolas_RANDRIANARIJAONA_Thèse_20260124", 5)
print(section['metadata']['title'])

# Rechercher dans les sections
results = loader.search_in_sections(
    "MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)", 
    "télédétection", 
    max_results=5
)

for r in results:
    print(f"{r['title']} - {r['occurrences']} occurrences")
```

---

### Préparer pour les embeddings

```python
from scripts.markdown_ai_utils import prepare_for_embeddings

chunks = prepare_for_embeddings(
    "Nicolas_RANDRIANARIJAONA_Thèse_20260124",
    chunk_size=1000,
    overlap=200
)

print(f"Nombre de chunks: {len(chunks)}")

# Utiliser avec OpenAI, Anthropic, etc.
for chunk in chunks[:5]:
    print(f"Chunk {chunk['id']}: {chunk['length']} caractères")
```

---

### Charger le format JSONL

```python
import json

with open('data/markdown_docs/these_sections.jsonl', 'r') as f:
    for line in f:
        section = json.loads(line)
        print(f"{section['id']}: {section['title']}")
        # Traiter chaque section...
```

---

## 📊 Statistiques

| Métrique | Thèse | Manuel | Total |
|----------|-------|--------|-------|
| **Pages** | 22 | 307 | 329 |
| **Mots** | 5,972 | 81,398 | 87,370 |
| **Sections** | 38 | 322 | 360 |
| **Taille** | 46 KB | 593 KB | 639 KB |

---

## 🔑 Mots-clés principaux

| Mot-clé | Occurrences |
|---------|-------------|
| criquet | 528 |
| lutte | 322 |
| solitaire | 180 |
| Madagascar | 180 |
| grégaire | 179 |
| locuste | 124 |
| surveillance | 94 |
| grégarisation | 93 |
| essaim | 77 |
| pullulation | 53 |

---

## 📁 Structure des fichiers

```
data/markdown_docs/
├── README.md                                          # Documentation complète
├── GUIDE_RAPIDE.md                                    # Ce guide
├── documents_index.json                               # Index avec mots-clés
├── these_sections.jsonl                               # Format pour IA
│
├── Nicolas_RANDRIANARIJAONA_Thèse_20260124.md        # Document complet
├── Nicolas_RANDRIANARIJAONA_Thèse_20260124_INDEX_DETAILLE.md
├── Nicolas_RANDRIANARIJAONA_Thèse_20260124_sections/ # 38 sections
│   ├── section_001_nicolas-randrianarijaona_thèse_20260124.md
│   ├── section_002_i-introduction-generale.md
│   └── ...
│
├── MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md                # Document complet
├── MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_INDEX_DETAILLE.md
└── MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_sections/         # 322 sections
    ├── section_001_manuel-de-lutte-préventive-vf.md
    ├── section_002_manuel-de-lutte-préventive-antiacridienne-à-madaga.md
    └── ...
```

---

## 🚀 Cas d'usage pour l'IA

### 1. RAG (Retrieval-Augmented Generation)
```python
# Charger toutes les sections
# Créer des embeddings
# Stocker dans une base vectorielle
# Rechercher les sections pertinentes
# Générer des réponses contextualisées
```

### 2. Analyse sémantique
```python
# Extraire les concepts clés
# Identifier les relations entre termes
# Construire un graphe de connaissances
```

### 3. Q&A automatique
```python
# Question: "Quels sont les facteurs de grégarisation?"
# → Rechercher dans les sections
# → Retourner les passages pertinents
# → Synthétiser une réponse
```

### 4. Résumé automatique
```python
# Charger toutes les sections d'un chapitre
# Résumer chaque section
# Créer un résumé hiérarchique
```

---

## 🎓 Thématiques disponibles

- **Biologie** : cycle de vie, phases, reproduction
- **Écologie** : facteurs environnementaux, habitats
- **Géographie** : aires grégarigènes, migrations
- **Climatologie** : impact des pluies, température
- **Télédétection** : NDVI, données satellitaires
- **Surveillance** : prospections, alerte précoce
- **Lutte préventive** : stratégies, techniques
- **Organisation** : gouvernance, financement
- **Modélisation** : prévision, machine learning

---

## 📞 Support

Pour toute question ou amélioration :
- Consulter le `README.md` détaillé
- Examiner les scripts Python avec leurs commentaires
- Vérifier l'index JSON pour les statistiques

---

*Généré le 7 juin 2026*  
*Workspace: modele_predictif*
