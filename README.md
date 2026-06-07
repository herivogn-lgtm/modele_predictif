# Modélisation Spatio-Temporelle du Criquet Migrateur Malagasy

Système de prédiction de la dynamique du criquet migrateur (*Locusta migratoria capito*) dans l'aire grégarigène de Madagascar, visant à orienter les prospections acridiennes pour rationaliser les ressources de surveillance du CNA.

## Contexte

Le criquet migrateur malagasy (*Locusta migratoria capito*, LMC) est une sous-espèce endémique de Madagascar dont les grégarisations périodiques menacent la sécurité alimentaire. Ce projet construit un **modèle hiérarchique** à trois étapes (présence/absence → densité → phase acridienne) produisant des prédictions opérationnelles à trois horizons : décadaire, mensuel et saisonnier.

## Structure du projet

```
.
├── data/
│   ├── aire_gregarigene/          # 12 polygones de l'aire grégarigène (EPSG:4326)
│   ├── region_naturelle/          # 90 polygones des régions naturelles (EPSG:4326)
│   ├── 2001_2026_Acrido_vf.xls   # Relevés acridiologiques terrain 2001–2026
│   └── *.pdf                      # Documents de référence
├── src/
│   ├── nettoyage_jointure_01.py   # Pipeline #01 — nettoyage et jointure des relevés
│   ├── gregarite_potentiel_02.py  # Pipeline #02 — calcul du potentiel de grégarité
│   ├── labels_entrainement_03.py  # Pipeline #03 — construction des labels
│   ├── 04_extraction_variables_gee.py  # Pipeline #04 — extraction GEE
│   ├── feature_engineering_05.py  # Pipeline #05 — ingénierie des features
│   ├── table_entrainement_06.py   # Pipeline #06 — table d'entraînement unifiée
│   ├── lgbm_baseline_07.py        # Pipeline #07 — baseline LightGBM
│   ├── lgbm_hierarchique_08.py    # Pipeline #08 — modèle hiérarchique LightGBM
│   ├── sorties_operationnelles_09.py  # Pipeline #09 — sorties opérationnelles
│   ├── neuralprophet_11.py        # Pipeline #11 — NeuralProphet multi-horizon
│   └── config_gee.py              # Configuration Google Earth Engine
├── tests/                         # Tests unitaires par pipeline
├── notebooks/
│   └── 10_rapport_performance.ipynb  # Rapport de performance walk-forward
├── docs/
│   ├── adr/                       # Architecture Decision Records
│   ├── agents/                    # Configuration des agents IA
│   └── PRD-modelisation-spatio-temporelle-acridienne.md
├── CONTEXT.md                     # Glossaire domaine et vocabulaire canonique
└── CLAUDE.md                      # Instructions pour Claude Code
```

## Architecture du modèle

Le **modèle hiérarchique** prédit trois sorties séquentielles par région naturelle × décade :

| Étape | Tâche | Métrique cible |
|-------|-------|----------------|
| 1 | Présence/absence | AUC > 0,85 |
| 2 | Densité (si présent) | RMSE / MAE |
| 3 | Phase acridienne (si présent) | F1-macro |

La **sortie opérationnelle** est le niveau de risque acridien 0–4 par polygone, agrégé depuis les régions naturelles vers les acrido-régions.

**Stack technique** (CPU uniquement) :
- LightGBM / XGBoost — baseline robuste et interprétable
- NeuralProphet — composante temporelle multi-horizon
- PyTorch LSTM léger — optionnel si besoin

## Données

| Fichier | Description |
|---------|-------------|
| `aire_gregarigene/` | 12 polygones — zones de concentration et grégarisation |
| `region_naturelle/` | 90 polygones — unité spatiale de modélisation |
| `2001_2026_Acrido_vf.xls` | Relevés terrain 2001–2026 (lacunes 2023–2024) |

**Variables environnementales** extraites via Google Earth Engine : pluviométrie, humidité des sols, température, occupation du sol / couverture végétale.

## Installation

```bash
pip install geopandas shapely pandas openpyxl matplotlib contextily pyproj lightgbm neuralprophet torch
```

## Exécution des pipelines

Les pipelines se lancent dans l'ordre numérique depuis `src/` :

```bash
python src/nettoyage_jointure_01.py
python src/gregarite_potentiel_02.py
python src/labels_entrainement_03.py
# Pipeline #04 requiert un accès Google Earth Engine authentifié
python src/04_extraction_variables_gee.py
python src/feature_engineering_05.py
python src/table_entrainement_06.py
python src/lgbm_baseline_07.py
python src/lgbm_hierarchique_08.py
python src/sorties_operationnelles_09.py
python src/neuralprophet_11.py
```

## Tests

```bash
pytest tests/
```

## Documents de référence

- `data/MANUEL DE LUTTE PRÉVENTIVE (VF).pdf` — manuel de lutte préventive terrain
- `data/LIVRE BLANC - EDGRND Décembre 2022.pdf` — livre blanc stratégique EDGRND
- `data/Nicolas RANDRIANARIJAONA_Thèse_20260124.pdf` — thèse de doctorat sur la dynamique acridienne à Madagascar
- `data/1979LecoqetalVoiesdedplacementLocusta.pdf` — Lecoq et al. 1979, routes de déplacement
