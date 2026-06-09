# Runbook — #04 Extraction des variables environnementales GEE

Pipelines :
- `src/04_extraction_variables_gee.py` — variante **getInfo** (interactif)
- `src/04b_export_variables_gee.py` — variante **Export.table** (batch, scalable)
- `src/extraction_gee_sources.py` — primitives GEE **partagées** (valeurs identiques)
- `src/extraction_gee_helpers.py` — logique pure ee-free (testée en pytest)

Sortie : `data/processed/04_variables_environnementales/` — **dataset Parquet
partitionné** (`part-XXXX.parquet`), lu en aval par `pd.read_parquet(<dossier>)`.

Maille : **cellule 1 km × décade** (`cell_id`, `AIRE_CODE`, `campagne_calc`,
`campagne_decade`). Sources : **NDVI/EVI** (MODIS MOD13A2), **LST** (MOD11A2),
**CHIRPS** (pluie) **+ anomalie** vs baseline 1981–2010. Décade **1–30** (campagne
oct→juil). Échantillonnage **par centroïde** (`sampleRegions`, 1 point/cellule).

> Voir aussi : `docs/glossaire-gee.md` (vocabulaire), `docs/pipelines/04-extraction-gee.md`,
> issue `.scratch/severite-phase-forecast/issues/10-couche-ee-grille-1km-scaling.md`,
> schéma `.scratch/severite-phase-forecast/04-scope-roadmap.excalidraw`.

---

## Quel périmètre ? (`--cells`)

Le **cube complet 181 413 cellules × 780 décades (~141 M lignes) n'est jamais requis.**
Deux extractions distinctes, pilotées par `--cells` :

| `--cells` | Cellules | Usage | Volume |
|---|---|---|---|
| **`observed`** (défaut) | ~5 396 cellules **labellisées** (∩ `03_labels_cellule_decade.parquet`) | **Entraînement / validation** | ~4,2 M lignes |
| **`all`** | grille complète (181 413) | **Surface de prédiction** — à lancer pour **la décade cible uniquement** (`--years <cible>`) | 181k × N décades |
| **`file`** | liste de `cell_id` (`--cells-file x.parquet`) | cas particuliers | — |

> 3 cellules labellisées tombent hors de la grille clipée (snapping bordure) →
> logguées et **ignorées** (d'où 5 396 et non 5 399).

---

## Quelle variante ? (`04` vs `04b`)

| | `04` getInfo | `04b` Export.table |
|---|---|---|
| Mécanisme | requêtes interactives | tâches batch async (→ Google Drive) |
| Plafond GEE 5000 éléments/getInfo | **subi** (sous-tuilage forcé) | **contourné** |
| `--cells observed` (~5 396) | OK, quelques min | OK, ~28 tâches |
| `--cells all` (181k) | ~86 000 appels = **à éviter** | recommandé (lots d'années) |
| Récupération | directe (écrit le parquet) | Drive → `assemble` |

**Règle** : `observed` → `04` (simple). `all` (surface de prédiction) → **`04b`**.

---

## Prérequis (une seule fois)

### Compte & environnement
```bash
pip install earthengine-api geopandas pandas pyarrow
python -c "import ee; ee.Authenticate()"   # navigateur → credentials locaux
```
Renseigner le projet Cloud dans `src/config_gee.py` :
```python
GEE_PROJECT_ID = "ee-tojoniriina"   # ← votre projet Earth Engine
```

### Données requises (produites en amont)
- `data/processed/01_grille_1km.parquet` — grille 1 km clipée (issue 01)
- `data/processed/03_labels_cellule_decade.parquet` — labels (issue 03), définit `observed`

---

## A. Variante getInfo (`04`) — recommandée pour `--cells observed`

### Étape 1 — Test d'intégration (1 cellule × 1 décade)
```bash
python src/04_extraction_variables_gee.py --test-only
```
Sortie attendue :
```
=== Test d'intégration : 1 cellule, janvier 2010 D1 ===
  cellule de test : 515_7168
  CHIRPS   : OK
  NDVI_EVI : OK
  LST      : OK
=== Test d'intégration réussi ===
```

### Étape 2 — Run entraînement (cellules observées)
```bash
python src/04_extraction_variables_gee.py --cells observed
```
- 1ʳᵉ exécution : calcule la **baseline CHIRPS** (36 décades, mise en cache
  `data/processed/04_chirps_baseline_cache.parquet`) ; runs suivants → cache.
- Progression par tuile → écrit `part-XXXX.parquet` dans le dossier de sortie.

Validation rapide sur une année avant le run complet :
```bash
python src/04_extraction_variables_gee.py --cells observed --years 2010
```

### (Optionnel) terminal détaché
```bash
nohup python src/04_extraction_variables_gee.py --cells observed > logs/04_gee.log 2>&1 &
tail -f logs/04_gee.log
```

---

## B. Variante Export.table (`04b`) — pour `--cells all` (surface de prédiction)

Flux en 3 temps, Drive servant de tampon.

### 1. submit — lancer les tâches
```bash
# Surface de prédiction : grille complète, décade(s) cible(s) uniquement
python src/04b_export_variables_gee.py submit --cells all --years 2026
```
- Tâches = **3 sources × lots d'années (`YEARS_PER_TASK`) × tuiles** + baseline/tuile.
- `--no-baseline` : réutiliser une baseline déjà exportée (la grille pleine en Drive
  reste valable, `compute_chirps_anomaly` est un merge gauche).
- `--no-dynamic` : ne (re)faire que la baseline.

### 2. status / cancel — suivre
```bash
python src/04b_export_variables_gee.py status   # tally READY/RUNNING/COMPLETED/FAILED
python src/04b_export_variables_gee.py cancel    # annule les tâches en cours de ce pipeline
```
Quand tout est `COMPLETED` : **télécharger** le dossier Drive
`ee_exports_locusta_v04/` (cf. `EXPORT_DRIVE_FOLDER`) dans
`data/processed/04_exports_drive/` (cf. `PATHS['exports_dir']`).

### 3. assemble — CSV → parquet partitionné
```bash
python src/04b_export_variables_gee.py assemble --cells all --years 2026
```
> ⚠️ Passer **le même `--cells` / `--years`** qu'au `submit` : le tiling est rejoué
> à l'identique pour apparier chaque CSV (`t{ti}`) à ses cellules.

---

## Vérification de la sortie
```bash
python - <<'EOF'
import pandas as pd
df = pd.read_parquet("data/processed/04_variables_environnementales")  # dossier !
print("lignes × colonnes :", df.shape)
print("cellules :", df["cell_id"].nunique(), "| décades :", df["campagne_decade"].nunique())
for c in ["chirps_sum_mean","chirps_anomaly_mean","ndvi_mean","evi_mean","lst_mean"]:
    if c in df: print(f"  NaN {c:20s} {df[c].isna().mean():.1%}")
v = df["ndvi_mean"].dropna();  assert v.between(-1,1).all(),   "NDVI hors [-1,1]"
v = df["lst_mean"].dropna();   assert v.between(200,400).all(),"LST hors [200,400] K"
v = df["chirps_sum_mean"].dropna(); assert (v>=0).all(),       "CHIRPS négatif"
print("plages physiques OK")
EOF
```
Critères : décade ∈ **1–30** · NDVI/EVI ∈ [-1,1] · LST ∈ [200,400] K · CHIRPS ≥ 0 ·
NaN NDVI tolérable (couverture nuageuse). `--cells observed` → ~4,2 M lignes,
5 396 cellules.

---

## Reprise après interruption
- **`04` getInfo** : relancer sur les années manquantes
  `--cells observed --years $(seq 2016 2026 | tr '\n' ' ')`. Le dossier de sortie
  est **purgé** au démarrage (`part-*.parquet`) → relancer sur la fenêtre complète
  voulue, ou réassembler les parts à la main.
- **`04b` Export** : `status` pour repérer les tâches `FAILED`, re-`submit` (au besoin
  avec `--no-baseline`), puis re-`assemble`.

---

## Dépannage

| Erreur / symptôme | Cause | Action |
|---|---|---|
| `Collection query aborted after accumulating over 5000 elements` | plafond getInfo (`04`) | géré par sous-tuilage + bissection ; si récurrent, baisser `CELL_CHUNK_SIZE` / `GETINFO_ELEMENT_BUDGET` |
| Tâche `04b` qui dure des heures / milliers d'EECU-h | lot d'années trop gros | baisser `YEARS_PER_TASK` (config) et re-`submit` |
| `EEException: Quota exceeded` | rate limit | retry exponentiel automatique ; sinon attendre et relancer |
| `EEException: Asset ... not found` | collection GEE indisponible | vérifier les IDs dans `config_gee.py` ([catalogue GEE](https://developers.google.com/earth-engine/datasets)) |
| `FileNotFoundError: ...01_grille_1km.parquet` | issue 01 non exécutée | produire la grille d'abord |
| `assemble` : `Aucun CSV pour v04_...` | CSV non téléchargés / mauvais `exports_dir` | télécharger le dossier Drive dans `PATHS['exports_dir']` |
| `assemble` : décades incomplètes (AssertionError) | `--cells`/`--years` ≠ ceux du `submit` | rejouer avec les mêmes options |
| NDVI hors [-1,1] / LST > 10 000 | facteur d'échelle | `multiply(0.0001)` (NDVI) / `multiply(0.02)` (LST) dans `extraction_gee_sources.py` |
| baseline recalculée à chaque run (`04`) | cache absent/corrompu | supprimer `04_chirps_baseline_cache.parquet` et relancer |

---

## Tests (sans GEE)
```bash
python -m pytest tests/test_04_extraction_helpers.py -q   # logique pure ee-free
```
Les couches GEE (`04`, `04b`, `extraction_gee_sources`) ne sont **pas** testables en
pytest (auth requise) → validation live via `04 --test-only` puis un petit run
`--cells observed --years 2010`.

---

## Étape suivante
Le dataset partitionné `04_variables_environnementales/` alimente le **#05 — Feature
engineering** (POP + lags + AIRE_CODE). NB : le pipeline 05 lit encore l'ancien
fichier `.parquet` unique avec clé région → **adaptation requise** (lecture du dossier
+ clé `cell_id`) avant exécution de bout en bout.
