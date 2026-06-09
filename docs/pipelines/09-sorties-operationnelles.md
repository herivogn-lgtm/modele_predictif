# Pipeline #09 — Sorties opérationnelles : carte de sévérité 0–3 à 1 km

**Script** : `src/sorties_operationnelles_09.py`
**Entrées** : `06_table_entrainement_unifiee.parquet`, `07_modele_retenu.txt`, `01_grille_1km.parquet`
**Sorties** : CSV décade/mois/aire + GeoJSON + GeoTIFF + PNG
**Durée estimée** : < 5 minutes (campagne T+1)
**Dépendances obligatoires** : Pipelines [#06](06-table-entrainement.md), [#07](07-benchmark-ordinal.md)

> **HITL** : un humain valide le modèle retenu via le rapport ([#10](10-rapport-performance.md)) **avant** de générer les cartes destinées au terrain.

---

## Objectif

Restituer les prédictions de **sévérité-phase ordinale 0–3** pour la **décade T+1** sur la grille **1 km** de l'aire grégarigène, en support à la prospection :

- **Carte de sévérité 0–3 à 1 km** (alerte précoce, décade à venir).
- **Agrégat mensuel par aire complémentaire** AMI/ATM/AD/AGT (`AIRE_CODE`, planification).
- **Binaire dérivé** (probabilité de présence, sév ≥ 1) pour comparaison AUC à la littérature.
- Export **PNG** + **SIG** (GeoJSON vectoriel + GeoTIFF raster) pour les supports terrain.

L'outil oriente les prospections vers les cellules à sévérité **2–3** et signale les passages au niveau 3 (grégaire) en T+1.

> Refonte vs l'ancien pipeline : abandon du **niveau de risque 0–4 / Annexe 8** et de l'agrégation par régions naturelles → secteurs. La cible est désormais la **sévérité ordinale 0–3** prédite par le modèle retenu (#07), restituée à la maille **cellule 1 km**.

---

## Entrées

| Fichier | Rôle |
|---------|------|
| `data/processed/06_table_entrainement_unifiee.parquet` | Historique observé (entraînement) + surface `a_predire` |
| `data/processed/07_modele_retenu.txt` | Nom du modèle retenu (#07) ré-entraîné ici |
| `data/processed/01_grille_1km.parquet` | Polygones cellule 1 km (EPSG:32738) pour les exports spatiaux |

---

## Sorties

| Fichier | Contenu |
|---------|---------|
| `09_carte_severite_decade.csv` | Sévérité 0–3 + proba présence par cellule × décade (campagne T+1) |
| `09_carte_severite_mensuelle.csv` | Sévérité agrégée au mois (phase max) par cellule |
| `09_agregat_aire_mensuel.csv` | Agrégat mensuel par `AIRE_CODE` (sév max, n cellules, n cellules-foyer) |
| `09_carte_severite.geojson` | Carte 1 km vectorielle (sévérité par cellule) |
| `09_carte_severite.tif` | Carte 1 km rasterisée (GeoTIFF, 1 km, nodata 255) |
| `09_carte_severite.png` | Rendu cartographique : cellules 0–3 **superposées sur les couches locales** `region_naturelle` (fond) + `aire_gregarigene` (contour des secteurs), semi-transparentes ; vue cadrée sur l'emprise des cellules. Aucune tuile web. |

---

## Fonctions pures (testées — `tests/test_09_sorties_operationnelles.py`)

| Fonction | Rôle |
|----------|------|
| `derive_binary(severite)` | Binaire présence dérivé = (sévérité ≥ 1) |
| `to_severity_map(carte_decade)` | Agrégation décade → mois ; sévérité mensuelle = **phase max** ; conserve `cell_id` / `AIRE_CODE` |
| `aggregate_by_aire(carte_mois)` | Agrégat mensuel par `AIRE_CODE` : `{severite_max, n_cellules, n_cellules_foyer (sév ≥ 2)}` |
| `to_cell_map(carte_decade)` | Variante « pire cas » : réduit la carte décadaire à 1 valeur/cellule (phase max sur la campagne). La carte par défaut utilise plutôt **une décade unique** (`--decade`) pour éviter la saturation. |

`mois_campagne = (campagne_decade − 1) // 3 + 1` (3 décades par mois).

L'orchestration `run()` (non testée) entraîne le modèle retenu sur l'historique observé, prédit la **dernière campagne** (décade T+1), et réutilise `_predit_fold` / `_lire_modele_retenu` (#10) et `build_models` / `get_feature_columns` (#07) — sans nouveau seam.

---

## Lancement

```bash
./.venv/bin/python src/sorties_operationnelles_09.py

# Choisir l'algorithme, la campagne et la décade en ligne de commande :
./.venv/bin/python src/sorties_operationnelles_09.py --modele catboost --campagne 2025-2026 --decade 19
./.venv/bin/python src/sorties_operationnelles_09.py -h   # aide
```

| Argument CLI | Env équivalent | Défaut |
|--------------|----------------|--------|
| `--modele {regression_ordinale,random_forest,lightgbm,xgboost,catboost,lstm}` | `SORTIES_MODELE` | modèle retenu `07_modele_retenu.txt` |
| `--campagne YYYY-YYYY` | `SORTIES_CAMPAGNE` | dernière campagne couverte (NDVI ≥ `MIN_COUVERTURE_FEATURES`, défaut 50 %) |
| `--decade N` (1–36) | `SORTIES_DECADE` | dernière décade de la campagne |

- **Carte spatiale = une seule décade** (la « décade T+1 »), **pas** le max sur la campagne — sinon chaque cellule atteint son pire niveau sur la saison et la carte sature en grégaire. Le run affiche les *décades à forte variété spatiale* pour aider au choix de `--decade`.
- **Campagne cible** : la toute dernière campagne du calendrier peut être un **futur non encore extrait par GEE** (features 100 % NaN → carte plate) ; elle est automatiquement ignorée.

> ⚠️ Un vrai forecast de la campagne future (ex. 2026-2027) nécessite d'abord d'**extraire ses covariables GEE** ([#04](04-extraction-gee.md)). Sans cela, seules les campagnes déjà couvertes produisent une carte exploitable.

---

## Avertissements

La **qualité** de la carte dépend du modèle retenu. Si le modèle retenu est la régression ordinale linéaire (carte plate, peu de relief), c'est cohérent avec son QWK / gain-lift modestes (#10) — relancer après un run complet de référence #07 qui retiendrait un modèle plus expressif (arbres / CatBoost). La validation humaine HITL via le rapport #10 reste obligatoire avant diffusion terrain.
