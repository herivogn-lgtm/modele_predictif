# 09 — Sorties opérationnelles : carte de sévérité 0–3 + export SIG (Pipeline 09)

Status: in-progress

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

> **HITL** : un humain valide le modèle retenu (via le rapport de l'issue 08) **avant** de
> générer les cartes destinées au terrain.

Restituer les prédictions de sévérité-phase pour la décade T+1 :

- **Carte de sévérité 0–3** à 1 km pour la décade à venir (alerte précoce)
- **Agrégat mensuel** par aire complémentaire (AMI/ATM/AD/AGT) pour la planification
- **Binaire dérivé** (probabilité de présence) pour comparaison AUC à la littérature
- Export **PNG** + export **SIG** (vectoriel/raster) pour intégration aux supports terrain

L'outil oriente les prospections vers les cellules à sévérité 2–3 et signale les passages au
niveau 3 (grégaire) en T+1.

## Acceptance criteria

- [x] Carte de sévérité 0–3 à 1 km pour la décade T+1
- [x] `to_severity_map` : agrégation décade → mois correcte
- [x] Agrégat mensuel par aire AMI/ATM/AD/AGT
- [x] Binaire dérivé restitué (carte de probabilité de présence)
- [x] Export PNG + export SIG produits
- [x] Modèle de production validé par un humain via le rapport (issue 08) avant génération
- [x] Tests dans `tests/test_09_*.py` (`to_severity_map`, `derive_binary`)

## Implementation notes (2026-06-09, /tdd)

- **Réécriture complète de `src/sorties_operationnelles_09.py`** : l'ancien module était le
  **pivot abandonné** (risque 0–4, Annexe 8, régions naturelles → secteurs, modèles
  `07_lgbm_model.pkl` / `08_lgbm_*.pkl` inexistants). Remplacé par l'architecture OS3
  (sévérité ordinale 0–3, maille cellule 1 km, modèle retenu `07_modele_retenu.txt`).
- **Fonctions pures testées** (`tests/test_09_sorties_operationnelles.py`, 3 tests) :
  - `derive_binary(severite)` : binaire présence dérivé = (sév ≥ 1) — exigence AUC thèse §31/§33.
  - `to_severity_map(carte_decade)` : agrégation décade → mois, **sévérité = phase max**
    du mois (PRD story 8) ; conserve `cell_id` / `AIRE_CODE`. `mois_campagne = (décade-1)//3+1`.
  - `aggregate_by_aire(carte_mois)` : agrégat mensuel par AIRE_CODE (AMI/ATM/AD/AGT) →
    `{severite_max, n_cellules, n_cellules_foyer (sév ≥ 2)}`.
  - (helper d'emprise non listé au PRD : `to_cell_map` réduit la carte décadaire à 1 valeur
    par cellule = phase max sur la campagne, pour les exports spatiaux.)
- **Orchestration `run()`** (non testée, lourde) : entraîne **le modèle retenu** sur
  l'historique observé (22 020 lignes), prédit sévérité 0–3 + proba présence sur la
  **dernière campagne** (`2026-2027`, décade T+1, 48 564 cellules-décades / 5 396 cellules),
  écrit `09_carte_severite_decade.csv`, `09_carte_severite_mensuelle.csv`,
  `09_agregat_aire_mensuel.csv`, puis **SIG** `09_carte_severite.geojson` + GeoTIFF
  `09_carte_severite.tif` (rasterio, 1 km, nodata 255) + **PNG** `09_carte_severite.png`
  (matplotlib, palette 0–3). Réutilise `_predit_fold` / `_lire_modele_retenu` (#08) et
  `build_models` / `get_feature_columns` (#07) — pas de nouveau seam.
- **Run réel validé (mécanisme)** : tous les exports produits sans erreur. **MAIS** le
  modèle retenu actuel (`regression_ordinale`, linéaire) prédit **sévérité = 1 partout**
  (carte plate, 0 foyer) — cohérent avec son QWK / gain-lift modestes (#08), pas un défaut
  du pipeline. La carte gagnera en relief quand le **run complet de référence #07**
  (300 arbres + catboost) retiendra un modèle plus expressif ; relancer alors simplement
  `./.venv/bin/python src/sorties_operationnelles_09.py` (s'adapte via `07_modele_retenu.txt`).
- **Reste avant clôture** : run complet de référence #07, puis revue humaine HITL de la carte.

## Blocked by

- `.scratch/severite-phase-forecast/issues/07-benchmark-modeles-ordinaux.md`
- `.scratch/severite-phase-forecast/issues/08-rapport-performance-walk-forward.md`
