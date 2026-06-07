# Pipeline #09 — Sorties opérationnelles niveau de risque 0–4

**Script** : `src/sorties_operationnelles_09.py`  
**Entrées** : Sorties de #06, #07, #08 + shapefiles  
**Sorties** : `09_rn_risque_decade.parquet` + 6 fichiers CSV/GeoJSON  
**Durée estimée** : < 5 minutes  
**Dépendances obligatoires** : Pipelines [#06](06-table-entrainement.md), [#07](07-lgbm-baseline.md), [#08](08-lgbm-hierarchique.md)

---

## Objectif

Chaîner les trois modèles LightGBM (présence, densité, phase) sur l'ensemble des lignes de la table unifiée, calculer le niveau de risque acridien 0–4 par région naturelle × décade, puis agréger vers les 12 secteurs de l'aire grégarigène et exporter les résultats aux trois horizons temporels (décadaire, mensuel, saisonnier) en format CSV et GeoJSON géoréférencés.

---

## Entrées

| Fichier | Usage |
|---------|-------|
| `data/processed/06_table_entrainement_unifiee.parquet` | Features pour toutes les cellules (toutes campagnes) |
| `data/processed/07_lgbm_model.pkl` | Modèle de présence/absence |
| `data/processed/07_rapport_walk_forward.csv` | Seuil de présence (ligne GLOBAL, colonne `threshold`) |
| `data/processed/08_lgbm_densite.pkl` | Modèle de régression densité |
| `data/processed/08_lgbm_phase.pkl` | Modèle de classification phase |
| `data/processed/08_rapport_walk_forward.csv` | Seuil G (ligne GLOBAL, colonne `threshold_G`) |
| `data/aire_gregarigene/aire_gregarigene.shp` | 12 secteurs (projection UTM 38S pour la jointure spatiale) |
| `data/region_naturelle/region_naturelle.shp` | 90 régions naturelles |

---

## Sorties

| Fichier | Description | Lignes approx. |
|---------|-------------|----------------|
| `data/processed/09_rn_risque_decade.parquet` | Risque par région naturelle × décade (intermédiaire) | 90 × N décades |
| `data/processed/09_sorties_decadaire.csv` | Risque par secteur × décade | 12 × N décades |
| `data/processed/09_sorties_mensuelle.csv` | Risque par secteur × mois de campagne | 12 × N mois |
| `data/processed/09_sorties_saisonniere.csv` | Risque par secteur × campagne | 12 × N campagnes |
| `data/processed/09_sorties_decadaire.geojson` | Version géoréférencée décadaire | idem CSV |
| `data/processed/09_sorties_mensuelle.geojson` | Version géoréférencée mensuelle | idem CSV |
| `data/processed/09_sorties_saisonniere.geojson` | Version géoréférencée saisonnière | idem CSV |

### Schéma de `09_rn_risque_decade.parquet`

| Colonne | Type | Description |
|---------|------|-------------|
| `rn_num`, `rn_nom` | int/str | Identifiant région naturelle |
| `campagne_calc` | str | Campagne `"YYYY-YYYY+1"` |
| `campagne_decade` | int | Décade dans la campagne (1–30) |
| `presence_pred` | int (0/1) | Présence prédite |
| `densite_pred` | float ou NaN | Densité prédite si présence=1 |
| `phase_pred` | str ou None | Phase prédite si présence=1 |
| `potentiel_predit` | int (0–5) | Potentiel acridien calculé par Annexe 8 |
| `niveau_risque` | int (0–4) | Potentiel plafonné à 4 |
| `effort_bas` | bool | True si effort_prospection ≤ 1 |

### Schéma des sorties décadaires/mensuelles/saisonnières (CSV + GeoJSON)

| Colonne | Description |
|---------|-------------|
| `SECT_NO`, `SECT_NOM` | Identifiants du secteur |
| `AIRE_CODE`, `AIRE_NOM` | Acrido-région |
| `campagne_calc` | Campagne |
| `campagne_decade` (décadaire) / `mois_campagne` (mensuel) | Période |
| `niveau_risque_max` | Maximum des niveaux de risque des régions du secteur |
| `phase_dominante` | Mode des phases prédites non-None dans le secteur |
| `n_regions` | Nombre de régions naturelles dans le secteur |
| `n_regions_risque_eleve` | Nombre de régions avec niveau_risque ≥ 3 |
| `n_regions_effort_bas` | Nombre de régions avec effort_bas = True |
| `faible_couverture` | True si majorité des régions avec effort_bas = True |
| `risque_eleve` | 1 si niveau_risque_max ≥ 3, sinon 0 |
| `geometry` (GeoJSON) | Géométrie du secteur (EPSG:4326) |

---

## Règles métier

### RM-1 : Chaîne d'inférence hiérarchique

Pour chaque cellule (région × décade) :

```
Étape 1 : presence_pred = (P(présence) ≥ threshold_pres)

Si presence_pred == 0 :
    densite_pred  = NaN
    phase_pred    = None
    potentiel_predit = 0

Si presence_pred == 1 :
    Étape 2 : densite_pred = model_densite.predict(X)
    Étape 3 : phase_pred   = _apply_threshold_G(model_phase.predict_proba(X), threshold_G)
    potentiel_predit = Annexe 8[phase_pred, classe_densite(densite_pred)]
```

Les seuils `threshold_pres` et `threshold_G` sont lus depuis la ligne `GLOBAL` des rapports #07 et #08.

### RM-2 : Calcul du niveau de risque

```
niveau_risque = min(potentiel_predit, 4)
```

Le potentiel acridien Annexe 8 peut atteindre 5 (phase G + densité très élevée). Il est plafonné à 4 pour s'aligner avec l'échelle opérationnelle du SIG-LMC (0–4).

### RM-3 : Agrégation vers les secteurs

| Métrique de sortie | Règle d'agrégation |
|--------------------|-------------------|
| `niveau_risque_max` | Maximum des `niveau_risque` des régions du secteur |
| `phase_dominante` | Mode des `phase_pred` non-None dans le secteur |
| `n_regions_risque_eleve` | Compte des régions avec `niveau_risque ≥ 3` |
| `faible_couverture` | True si `n_regions_effort_bas > n_regions / 2` |

### RM-4 : Flag effort_bas

`effort_bas = True` pour une région × décade si `effort_prospection ≤ 1` (constante `SEUIL_EFFORT_BAS = 1`). Ce flag signale que la prédiction de risque dans cette région est basée sur peu ou pas d'observations terrain directes — le modèle extrapole à partir des features environnementales.

### RM-5 : Agrégation horizon mensuel

`mois_campagne = (campagne_decade - 1) // 3 + 1` (octobre = mois 1, juillet = mois 10). L'agrégation mensuelle groupe les 3 décades consécutives et prend le maximum de `niveau_risque` sur les 3 décades.

### RM-6 : Jointure spatiale régions → secteurs

La jointure utilise la projection UTM 38S (EPSG:32738) pour le calcul des surfaces. En cas de chevauchement d'une région naturelle sur plusieurs secteurs, le secteur avec la **plus grande surface d'intersection** est retenu.

---

## Exécution

```bash
python src/sorties_operationnelles_09.py
```

---

## Dépendances

- **Amont** :
  - [#06](06-table-entrainement.md) — features
  - [#07](07-lgbm-baseline.md) — modèle + seuil présence
  - [#08](08-lgbm-hierarchique.md) — modèles densité + phase + seuil G
  - Shapefiles `data/aire_gregarigene/` et `data/region_naturelle/`
- **Aval** : [#10](10-rapport-performance.md) — charge `09_rn_risque_decade.parquet`
- **Bibliothèques** : `lightgbm`, `geopandas`, `pandas`, `joblib`, `pyarrow`

---

## Avertissements

Les sorties couvrent **toutes les campagnes** (train, validation, inference). Pour un usage opérationnel, filtrer sur les campagnes récentes via la colonne `campagne_calc`.

Un secteur avec `faible_couverture = True` et `niveau_risque_max = 0` doit être interprété avec précaution : le risque faible prédit pourrait être dû à un manque de prospections terrain plutôt qu'à une véritable absence de criquets. Le guide d'interprétation [guide-interpretation-risque.md](../guide-interpretation-risque.md) recommande d'ajouter +1 niveau de précaution dans ce cas.
