# 01 — Snap point→cellule 1 km + clip strict à l'aire grégarigène (Pipeline 01)

Status: ready-for-agent

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Remplacer, dans le pipeline de nettoyage/jointure, le rattachement par `région naturelle`
par un rattachement **point→cellule 1 km** sur une grille régulière, puis un **clip strict**
à l'intérieur des polygones de `data/aire_gregarigene/` (12 secteurs).

La grille 1 km clipée (~1 800 cellules) devient l'**emprise partagée** entre entraînement et
prédiction. Les relevés tombant hors des polygones (~16 %) sont écartés. On conserve
`LAT_DD`/`LNG_DD`, `Date_`, `Decade`, `Campagne` et on ajoute l'identifiant de cellule.

Chemin end-to-end : relevés bruts → snap sur grille 1 km → clip aux polygones → table nettoyée
avec `cell_id`, vérifiable via un `run()` produisant la table et via les tests unitaires des
fonctions pures.

## Acceptance criteria

- [x] `snap_to_grid` : un point donné tombe dans la bonne cellule 1 km (test sur coordonnées connues)
- [x] `clip_to_aire` : les points hors des polygones `data/aire_gregarigene/` sont exclus
- [x] La grille 1 km régulière est construite et clipée à l'intérieur des 12 secteurs
- [x] La table nettoyée conserve `LAT_DD`, `LNG_DD`, `Date_`, `Decade`, `Campagne` + identifiant de cellule
- [x] Couverture des 12 secteurs (pas seulement le Sud-Ouest)
- [x] Tests dans `tests/test_01_nettoyage_jointure.py` (DataFrames synthétiques, mêmes helpers que l'existant)

## Findings — correction doc à traiter (ticket séparé)

Aire grégarigène réelle ≈ **181 500 km²** → grille 1 km ≈ **181 000 cellules**, **pas
~1 800**. Vérifié deux fois (UTM 38S + géodésique WGS84) ; `SUP_HA` (somme 181 414) est
en **km²**, et le clip retient 85,5 % des relevés (≈ 84 % attendus par l'ADR). Le chiffre
« ~1 814 km² / ~1 800 cellules » de **ADR 0003 + PRD + CONTEXT.md** est une erreur d'un
facteur 100 (confusion ha↔km²). Décision (2026-06-07) : grille réelle conservée, doc à
corriger dans un ticket dédié (1 814 → 181 500 km² ; 1 800 → ~181 000 cellules).

## Implementation notes

- Remplacement effectué : double sjoin (région naturelle + aire) → `snap_to_grid` +
  `clip_to_aire` (clip strict `within`, rattache `AIRE_CODE`/`SECT_NO`/`AIRE_NOM`).
- Grille 1 km en UTM 38S (EPSG:32738), `cell_id="col_row"`, origine partagée snap↔grille
  (garantie par le test de round-trip centroïde).
- Sorties : `data/processed/01_releves_nettoyes.parquet` (25 151 relevés clipés) +
  `data/processed/01_grille_1km.parquet` (emprise partagée entraînement = prédiction).
- Colonnes `rn_num`/`rn_nom` supprimées → **pipeline 03 aval à adapter** (traité dans son
  propre ticket : cible ordinale `compute_severite` + agrégation par cellule).

## Blocked by

None - can start immediately
