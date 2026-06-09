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
| `to_cell_map(carte_decade)` | Réduit la carte décadaire à 1 valeur/cellule (phase max sur la campagne) pour les exports spatiaux |

`mois_campagne = (campagne_decade − 1) // 3 + 1` (3 décades par mois).

L'orchestration `run()` (non testée) entraîne le modèle retenu sur l'historique observé, prédit la **dernière campagne** (décade T+1), et réutilise `_predit_fold` / `_lire_modele_retenu` (#10) et `build_models` / `get_feature_columns` (#07) — sans nouveau seam.

---

## Lancement

```bash
./.venv/bin/python src/sorties_operationnelles_09.py
```

Le script s'adapte automatiquement au modèle retenu via `07_modele_retenu.txt` : après un nouveau run de référence #07, le relancer régénère les cartes.

---

## Avertissements

La **qualité** de la carte dépend du modèle retenu. Si le modèle retenu est la régression ordinale linéaire (carte plate, peu de relief), c'est cohérent avec son QWK / gain-lift modestes (#10) — relancer après un run complet de référence #07 qui retiendrait un modèle plus expressif (arbres / CatBoost). La validation humaine HITL via le rapport #10 reste obligatoire avant diffusion terrain.
