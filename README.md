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
│   ├── 04b_export_variables_gee.py # Pipeline #04b — export par lots grille 1 km
│   ├── feature_engineering_05.py  # Pipeline #05 — ingénierie des features
│   ├── table_entrainement_06.py   # Pipeline #06 — table d'entraînement unifiée
│   ├── lgbm_baseline_07.py        # Pipeline #07 — baseline LightGBM
│   ├── benchmark_ordinal_07.py    # Pipeline #07 — benchmark ordinal 0–3 multi-modèles
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

**Variables environnementales** : 24 prédicteurs issus de 4 sources principales :
- ☔ **CHIRPS** (7 variables) : pluviométrie + POP (Plage d'Optimum Pluviométrique 50-125 mm/mois)
- 🌱 **MODIS** (6 variables) : NDVI/EVI (végétation)
- 🌡️ **MODIS LST** (3 variables) : température de surface
- 🦗 **Relevés terrain** (4 variables) : historique acridien (sévérité, densité)
- 📍 **Métadonnées** (4 variables) : spatial/temporel (aires, saisonnalité)

**Voir** : [`docs/VARIABLES-REFERENCE-RAPIDE.md`](docs/VARIABLES-REFERENCE-RAPIDE.md) pour la liste complète et [`docs/INDEX.md`](docs/INDEX.md) pour naviguer dans la documentation.

## Installation

Toutes les dépendances (versions figées) sont déclarées dans [`requirements.txt`](requirements.txt).

```bash
# 1. Créer et activer un environnement virtuel (Python 3.14 de référence)
python3 -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt
```

Le pipeline #04 requiert un compte **Google Earth Engine** authentifié (une fois) :

```bash
python -c "import ee; ee.Authenticate()"
```

## Exécution des pipelines

Les pipelines se lancent dans l'ordre numérique, environnement virtuel activé :

```bash
# ── Préparation des données terrain ──────────────────────────────────
python src/nettoyage_jointure_01.py
python src/gregarite_potentiel_02.py
python src/labels_entrainement_03.py

# ── Extraction des variables environnementales (Google Earth Engine) ─
# Sanity-check de la connexion / des sources avant le run complet :
python src/04_extraction_variables_gee.py --test-only
python src/04_extraction_variables_gee.py

# Export par lots de la grille pleine 1 km (tâches GEE asynchrones) :
python src/04b_export_variables_gee.py submit --cells all --no-baseline
python src/04b_export_variables_gee.py status     # suivre l'avancement des tâches
python src/04b_export_variables_gee.py assemble    # réassembler les shards exportés
#   Variantes : --decades 2026-14:2026-18 | --years 2026 | --cells observed

# ── Features & table d'entraînement ──────────────────────────────────
python src/feature_engineering_05.py
python src/table_entrainement_06.py

# ── Modélisation ─────────────────────────────────────────────────────
python src/lgbm_baseline_07.py
# Benchmark ordinal 0–3 (RF / LightGBM / XGBoost / CatBoost / LSTM) :
python src/benchmark_ordinal_07.py
#   Réglages via variables d'env : BENCH_N_ESTIMATORS, BENCH_N_JOBS, BENCH_LSTM=0
python src/lgbm_hierarchique_08.py
python src/neuralprophet_11.py

# ── Sorties opérationnelles (cartes PNG de sévérité 0–3) ─────────────
python src/sorties_operationnelles_09.py
# Cibler un modèle / une campagne / une décade précise :
python src/sorties_operationnelles_09.py --modele catboost --campagne 2025-2026 --decade 19
python src/sorties_operationnelles_09.py --modele random_forest --month 06
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
