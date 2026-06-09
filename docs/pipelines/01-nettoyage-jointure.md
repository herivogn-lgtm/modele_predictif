# Pipeline #01 — Nettoyage et rattachement à la grille 1 km

**Script** : `src/nettoyage_jointure_01.py`
**Entrée principale** : `data/2001_2026_Acrido_vf.xls` (feuille `2001_2025_AA`)
**Sorties** : `data/processed/01_releves_nettoyes.parquet`, `data/processed/01_grille_1km.parquet`
**Durée estimée** : < 5 minutes
**Dépendance obligatoire** : aucune (premier pipeline de la chaîne)

---

## Objectif

Charger les relevés acridiens terrain 2001–2026, écarter les coordonnées GPS aberrantes ou manquantes, puis **rattacher chaque relevé à sa cellule de la grille régulière 1 km** (`snap_to_grid`) et **clipper strictement à l'intérieur de l'aire grégarigène** (`clip_to_aire`, [ADR 0003](../adr/0003-emprise-aire-gregarigene-clip-strict.md)). Le pipeline produit deux artefacts : les relevés nettoyés géoréférencés et la **grille 1 km partagée** qui garantit que l'emprise d'entraînement = l'emprise de prédiction.

> Changement majeur vs l'ancien pipeline : on abandonne le rattachement à la région naturelle au profit du **snap point → cellule 1 km** (`cell_id`). Les relevés hors polygones de l'aire grégarigène (~16 %) sont écartés.

---

## Entrées

| Fichier | Description | Colonnes clés utilisées |
|---------|-------------|-------------------------|
| `data/2001_2026_Acrido_vf.xls` (feuille `2001_2025_AA`) | Relevés acridiens terrain bruts | `Date_`, `LAT_DD`, `LNG_DD`, `Sol`, `Trans`, `Greg`, `Sol_larve`, `Trans_larve`, `Greg_larve`, `DI_dif_moy`, `DL_dif_moy`, `Decade`, `Campagne` |
| `data/aire_gregarigene/aire_gregarigene.shp` | 12 polygones des acrido-régions (secteurs) | `AIRE_NOM`, `AIRE_CODE`, `SECT_NOM`, `SECT_NO`, `geometry` |

---

## Sorties

| Fichier | Contenu |
|---------|---------|
| `data/processed/01_releves_nettoyes.parquet` | Relevés nettoyés + `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`, comptages, densités |
| `data/processed/01_grille_1km.parquet` | Grille régulière 1 km clipée (polygones cellule, EPSG:32738) : `cell_id`, `cell_col`, `cell_row`, `AIRE_CODE`, `SECT_NO`, `AIRE_NOM`, `geometry` |

---

## Fonctions pures (testées — `tests/test_01_nettoyage_jointure.py`)

| Fonction | Rôle |
|----------|------|
| `compute_campagne(date)` | Campagne acridienne (oct→sept) à partir de la date |
| `compute_temporal_fields(date)` | Champs temporels dérivés (campagne, décade de campagne) |
| `snap_to_grid(points_gdf, cell_size=1000)` | Affecte chaque point à sa cellule 1 km (UTM 38S) |
| `clip_to_aire(points_gdf, aire_gdf)` | Conserve uniquement les points strictement à l'intérieur des polygones |
| `build_grid(aire_gdf, cell_size=1000)` | Construit la grille régulière 1 km clipée à l'aire grégarigène |

---

## Paramètres clés

- `GRID_CRS = "EPSG:32738"` (WGS 84 / UTM zone 38S) — projection métrique de Madagascar.
- `CELL_SIZE_M = 1000.0` — maille 1 km.

---

## Lancement

```bash
./.venv/bin/python src/nettoyage_jointure_01.py
```

## Aval

Pipeline [#02](02-gregarite-potentiel.md) (indicateurs acridologiques) et, via la grille, le pipeline [#04](04-extraction-gee.md) (extraction GEE) et le pipeline [#09](09-sorties-operationnelles.md) (géométrie des cartes).
