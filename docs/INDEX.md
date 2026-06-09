# Index de la documentation

**Projet** : Modèle prédictif spatio-temporel — Criquet migrateur malagasy  
**Dernière mise à jour** : 2026-06-09

---

## 🚀 Démarrage rapide

### Pour prédire le mois en cours (opérationnel)

1. **Guide rapide grille pleine** : [`docs/GUIDE-RAPIDE-GRILLE-PLEINE.md`](GUIDE-RAPIDE-GRILLE-PLEINE.md)
2. **Runbook extraction mensuelle** : [`docs/runbook-extraction-grille-pleine.md`](runbook-extraction-grille-pleine.md)
3. **Script de test** : [`scripts/test-extraction-grille-pleine.sh`](../scripts/test-extraction-grille-pleine.sh)

### Pour comprendre les variables du modèle

1. **Référence rapide variables** : [`docs/VARIABLES-REFERENCE-RAPIDE.md`](VARIABLES-REFERENCE-RAPIDE.md) ⭐
2. **Documentation complète variables** : [`docs/VARIABLES-ENVIRONNEMENTALES.md`](VARIABLES-ENVIRONNEMENTALES.md)
3. **Flux de données** : [`docs/FLUX-DONNEES-VARIABLES.md`](FLUX-DONNEES-VARIABLES.md)

---

## 📚 Documentation par thème

### Variables environnementales et données

| Document | Contenu | Public |
|----------|---------|--------|
| **[VARIABLES-REFERENCE-RAPIDE.md](VARIABLES-REFERENCE-RAPIDE.md)** | Liste des 24 variables, couverture, rôle écologique | ⭐ Tous |
| **[VARIABLES-ENVIRONNEMENTALES.md](VARIABLES-ENVIRONNEMENTALES.md)** | Documentation exhaustive (sources, formules, interprétation) | Technique |
| **[FLUX-DONNEES-VARIABLES.md](FLUX-DONNEES-VARIABLES.md)** | Schémas du pipeline de bout en bout | Visuel |

### Extraction grille pleine (prédiction opérationnelle)

| Document | Contenu | Public |
|----------|---------|--------|
| **[GUIDE-RAPIDE-GRILLE-PLEINE.md](GUIDE-RAPIDE-GRILLE-PLEINE.md)** | Commandes essentielles, vérifications | ⭐ Opérationnel |
| **[runbook-extraction-grille-pleine.md](runbook-extraction-grille-pleine.md)** | Workflow complet (5 étapes), dépannage, automatisation | Opérationnel |
| **[README-GRILLE-PLEINE.md](../README-GRILLE-PLEINE.md)** | Résumé exécutif de l'implémentation | Chef de projet |
| **[MODIFICATIONS-GRILLE-PLEINE.md](MODIFICATIONS-GRILLE-PLEINE.md)** | Changelog détaillé des modifications | Développeur |
| **[SESSION-INTERVIEW-GRILLE-PLEINE.md](SESSION-INTERVIEW-GRILLE-PLEINE.md)** | Décisions prises (17 questions/réponses) | Historique |
| **[NOTE-BATCHES-ANNEES.md](NOTE-BATCHES-ANNEES.md)** | Pourquoi "1 lot" n'extrait que 5 décades | Technique |

### Architecture et pipelines

| Document | Contenu | Public |
|----------|---------|--------|
| **[architecture-pipeline.md](architecture-pipeline.md)** | Vue d'ensemble du système complet | Architecture |
| **[pipelines/01-nettoyage-jointure.md](pipelines/01-nettoyage-jointure.md)** | Grille 1 km | Pipeline |
| **[pipelines/03-labels.md](pipelines/03-labels.md)** | Labels cellule × décade | Pipeline |
| **[pipelines/04-extraction-gee.md](pipelines/04-extraction-gee.md)** | Extraction GEE (#04 et #04b) | Pipeline |
| **[pipelines/05-feature-engineering.md](pipelines/05-feature-engineering.md)** | Feature engineering (POP, lags) | Pipeline |
| **[pipelines/06-construction-table.md](pipelines/06-construction-table.md)** | Table d'entraînement unifiée | Pipeline |
| **[pipelines/07-benchmark-ordinal.md](pipelines/07-benchmark-ordinal.md)** | Benchmark modèles | Pipeline |
| **[pipelines/09-sorties-operationnelles.md](pipelines/09-sorties-operationnelles.md)** | Cartes de prédiction | Pipeline |
| **[pipelines/10-rapport-final.md](pipelines/10-rapport-final.md)** | Rapport synthétique | Pipeline |

### Décisions architecturales (ADR)

| Document | Sujet |
|----------|-------|
| **[adr/0001-cible-ordinale-severite-phase.md](adr/0001-cible-ordinale-severite-phase.md)** | Pourquoi échelle ordinale 0-3 |
| **[adr/0002-forecast-decade-t-plus-1.md](adr/0002-forecast-decade-t-plus-1.md)** | Pourquoi prédire T+1 (forecast vs nowcast) |
| **[adr/0003-emprise-aire-gregarigene-clip-strict.md](adr/0003-emprise-aire-gregarigene-clip-strict.md)** | Pourquoi clip strict aux 12 polygones |
| **[adr/0004-fenetre-entrainement-complete.md](adr/0004-fenetre-entrainement-complete.md)** | Fenêtre d'entraînement (2001-2026 complet) |
| **[adr/0005-benchmark-modeles-selection-robustesse.md](adr/0005-benchmark-modeles-selection-robustesse.md)** | Sélection modèle (Régression Ordinale) |

### Runbooks opérationnels

| Document | Usage |
|----------|-------|
| **[runbook-04-extraction-gee.md](runbook-04-extraction-gee.md)** | Authentification GEE, extraction variables |
| **[runbook-extraction-grille-pleine.md](runbook-extraction-grille-pleine.md)** | Extraction mensuelle grille complète ⭐ |

---

## 🎯 Cas d'usage

### Je veux... prédire pour juin 2026 (opérationnel)

1. Lire : [`GUIDE-RAPIDE-GRILLE-PLEINE.md`](GUIDE-RAPIDE-GRILLE-PLEINE.md)
2. Exécuter : `./scripts/test-extraction-grille-pleine.sh`
3. Suivre : [`runbook-extraction-grille-pleine.md`](runbook-extraction-grille-pleine.md) section "Workflow mensuel"

**Commandes clés** :
```bash
# Extraction (10-20 min)
python src/04b_export_variables_gee.py submit --cells all --month 2026-06 --no-baseline

# Assemblage
python src/04b_export_variables_gee.py assemble --cells all --month 2026-06

# Pipeline complet
python src/feature_engineering_05.py
python src/construction_table_06.py
python src/sorties_operationnelles_09.py --campagne 2025-2026 --decade 18
```

---

### Je veux... comprendre les variables du modèle

1. Lire : [`VARIABLES-REFERENCE-RAPIDE.md`](VARIABLES-REFERENCE-RAPIDE.md) ⭐ (5 min)
2. Approfondir : [`VARIABLES-ENVIRONNEMENTALES.md`](VARIABLES-ENVIRONNEMENTALES.md) (30 min)
3. Visualiser : [`FLUX-DONNEES-VARIABLES.md`](FLUX-DONNEES-VARIABLES.md) (schémas)

**Variables clés** :
- ☔ `pop_consecutive` : Mois consécutifs en POP (50-125 mm/mois) — facteur critique
- 🌱 `ndvi_mean` : Disponibilité végétation herbacée
- 🌡️ `lst_mean` : Température de surface (vitesse développement)
- 🦗 `severite_lag1` : Persistance locale (si cellule observée)

---

### Je veux... comprendre le pipeline complet

1. Lire : [`architecture-pipeline.md`](architecture-pipeline.md) (vue d'ensemble)
2. Visualiser : [`FLUX-DONNEES-VARIABLES.md`](FLUX-DONNEES-VARIABLES.md) (schémas)
3. Détailler : [`pipelines/04-extraction-gee.md`](pipelines/04-extraction-gee.md), [`05-feature-engineering.md`](pipelines/05-feature-engineering.md), etc.

**Pipeline en 6 étapes** :
```
#01 Grille 1km → #04b Extraction GEE → #05 Feature engineering
                  ↓
#03 Labels → #06 Table unifiée → #07 Entraînement → #09 Prédiction
```

---

### Je veux... débugger une extraction GEE

1. Vérifier : [`NOTE-BATCHES-ANNEES.md`](NOTE-BATCHES-ANNEES.md) (pourquoi "1 lot" extrait bien 5 décades)
2. Tester : `python scripts/test-decades-dryrun.py` (simulation sans GEE)
3. Dépanner : [`runbook-extraction-grille-pleine.md`](runbook-extraction-grille-pleine.md) section "Dépannage"

**Problèmes fréquents** :
- Tâches FAILED → quota GEE dépassé
- CSV manquants → pas téléchargés depuis Drive
- Erreur "FileNotFoundError" → CSV absents dans `04_exports_drive/`

---

### Je veux... comprendre pourquoi QWK = 0.307

1. Lire : [`VARIABLES-ENVIRONNEMENTALES.md`](VARIABLES-ENVIRONNEMENTALES.md) section "Performance"
2. Voir : `data/processed/08_rapport_resume.txt` (métriques par campagne)
3. Analyser : Variables manquantes (LST 74%, historique 0.5% grille pleine)

**Facteurs limitants** :
- LST : 26% de données manquantes (nuages)
- Historique acridien : Disponible seulement pour 3% des cellules
- POP consécutif : Variable clé mais dérivée (dépend de CHIRPS)

**Pistes d'amélioration** :
- Ajouter ENSO/ONI (anomalies climatiques globales)
- Features POP avancées (persistance, intensité)
- Expansion temporelle (lags T-3, T-4)

---

## 📊 Données de référence

### Métriques du modèle actuel

**Modèle retenu** : Régression Ordinale  
**Performance** :
- QWK moyen : **0.307** (accord modéré)
- Recall 2-3 : **54.18%** (détecte 54% des cas critiques)
- AUC binaire : **0.746** (bonne discrimination présence/absence)

**Fichiers** :
- `data/processed/07_modele_retenu.txt`
- `data/processed/08_rapport_resume.txt`
- `data/processed/08_rapport_par_campagne.csv`

### Taille de la grille

- **Aire grégarigène** : 181 414 km²
- **Grille 1 km** : 181 413 cellules
- **Cellules observées** : 5 396 (3%)
- **Cellules à prédire** : 175 017 (97%)

**Fichiers** :
- `data/processed/01_grille_1km.parquet` (181 413 lignes)
- `data/processed/03_labels_cellule_decade.parquet` (5 396 cellules uniques)

---

## 🛠️ Scripts et outils

### Scripts opérationnels

| Script | Usage |
|--------|-------|
| **`src/04b_export_variables_gee.py`** | Extraction GEE grille complète |
| **`src/feature_engineering_05.py`** | Calcul POP, lags, cumuls |
| **`src/construction_table_06.py`** | Table unifiée features + labels |
| **`src/sorties_operationnelles_09.py`** | Génération carte prédiction |

### Scripts de test

| Script | Usage |
|--------|-------|
| **`scripts/test-extraction-grille-pleine.sh`** | Test interactif extraction mensuelle |
| **`scripts/test-decades-dryrun.py`** | Simulation extraction sans GEE |

### Commandes utiles

```bash
# Help CLI
python src/04b_export_variables_gee.py --help

# Vérifier données
python -c "import pandas as pd; df = pd.read_parquet('data/processed/06_table_entrainement_unifiee.parquet'); print(df.info())"

# Lister variables
python -c "import pandas as pd; df = pd.read_parquet('data/processed/06_table_entrainement_unifiee.parquet'); print(df.columns.tolist())"
```

---

## 📝 Glossaire

| Terme | Définition |
|-------|------------|
| **Aire grégarigène** | Zone d'étude (181 414 km², 12 polygones, 4 aires complémentaires) |
| **Sévérité-phase** | Échelle ordinale 0-3 (absence, solitaire, transiens, grégaire) |
| **POP** | Plage d'Optimum Pluviométrique (50-125 mm/mois) |
| **QWK** | Quadratic Weighted Kappa (métrique d'accord ordinal) |
| **Recall 2-3** | Taux de détection des cas transiens/grégaires |
| **Forecast T+1** | Prédire la décade suivante (pas la décade courante) |
| **Lag** | Décalage temporel (lag1d = décade T-1) |
| **GEE** | Google Earth Engine (plateforme cloud pour télédétection) |

---

## 🔗 Liens externes

- **CHIRPS** : https://www.chc.ucsb.edu/data/chirps
- **MODIS** : https://lpdaac.usgs.gov/
- **Google Earth Engine** : https://earthengine.google.com/
- **Thèse Randrianarijaona** : `data/Nicolas RANDRIANARIJAONA_Thèse_20260124.pdf`

---

## ❓ Support

**Questions fréquentes** :
1. Pourquoi "1 lot d'années" extrait seulement 5 décades ? → [`NOTE-BATCHES-ANNEES.md`](NOTE-BATCHES-ANNEES.md)
2. Comment ajouter un nouveau mois ? → [`runbook-extraction-grille-pleine.md`](runbook-extraction-grille-pleine.md)
3. Quelles variables sont les plus importantes ? → [`VARIABLES-ENVIRONNEMENTALES.md`](VARIABLES-ENVIRONNEMENTALES.md) section "Performance"

**Issues** : `.scratch/severite-phase-forecast/issues/`

**Contact** : Voir README principal
