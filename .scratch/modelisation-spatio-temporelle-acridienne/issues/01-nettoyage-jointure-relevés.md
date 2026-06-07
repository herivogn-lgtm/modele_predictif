---
Status: done
---

# #01 — Nettoyage et jointure spatiale des relevés acridiens

## What to build

Charger la feuille `2001_2025_AA` du fichier XLS de relevés acridiens (colonnes LMC uniquement, colonnes `_NSE` ignorées), filtrer les coordonnées GPS hors plage Madagascar (valeurs aberrantes comme `LAT_DD = -2 210 452`), puis affecter chaque relevé acridien à sa région naturelle par jointure spatiale avec le shapefile des 90 régions naturelles. La sortie est un DataFrame géoréférencé avec, pour chaque relevé : identifiant de région naturelle, campagne acridienne (ex. `2001-2002`), décade de campagne, et les colonnes terrain originales (`Sol`, `Trans`, `Greg`, `DI_dif_moy`, `DL_dif_moy`).

## Acceptance criteria

- [x] Les coordonnées GPS hors des bornes géographiques de Madagascar sont écartées avant la jointure spatiale
- [x] Chaque relevé valide est associé à exactement une région naturelle (ou marqué hors-aire si hors du shapefile `aire_gregarigene`)
- [x] Les colonnes suffixées `_NSE` sont absentes de la sortie
- [x] La campagne acridienne est correctement calculée (octobre → juillet, enjambant deux années civiles)
- [x] Test d'intégration : un point GPS connu retourne la bonne région naturelle

## Blocked by

None - can start immediately

## Synthèse d'implémentation

**Fichiers produits**
- `src/nettoyage_jointure_01.py` — pipeline principal
- `tests/test_01_nettoyage_jointure.py` — 13 tests (8 unitaires + 5 intégration)
- `data/processed/01_releves_nettoyes.parquet` — sortie géoréférencée

**Chiffres d'exécution**
- 29 706 relevés bruts → 29 405 après filtrage GPS (262 NaN + 39 hors-bornes Madagascar)
- 34 colonnes `_NSE` supprimées → 46 colonnes LMC conservées
- 4 254 relevés hors `aire_gregarigene` (marqués `hors_aire=True`)
- 4 252 relevés sans région naturelle (majoritairement = les mêmes hors-aire)

**Décisions techniques**
- `engine="xlrd"` obligatoire pour le format `.xls` (BIFF8 — openpyxl ne le supporte pas)
- `Date_` est un serial Excel float ; converti via `xlrd.xldate_as_datetime(serial, 0)`
- La colonne `Decade` du XLS encode la **décade absolue de l'année civile** (1–36), non la décade intra-mensuelle. `decade_intra` et `campagne_decade` sont dérivés de `Date_` (source de vérité), la colonne `Decade` étant incohérente avec `Mois_` sur 292 lignes
- Mois 8-9 (août-septembre) → `campagne_calc = None` (période inter-campagne, ~655 lignes)
- `predicate="within"` pour le sjoin : pas de duplication (shapefiles sans overlap)
- `rn_num` converti en `Int64` nullable pour les pipelines avals
- Colonnes avec espaces renommées : `Sol larve` → `Sol_larve`, etc.
- Colonne `Campagne` du XLS conservée sous `campagne_xls` pour référence
