# Pipeline #01 — Nettoyage et jointure spatiale

**Script** : `src/nettoyage_jointure_01.py`  
**Entrée principale** : `data/2001_2026_Acrido_vf.xls` (feuille `2001_2025_AA`)  
**Sortie** : `data/processed/01_releves_nettoyes.parquet`  
**Durée estimée** : < 5 minutes  
**Dépendance obligatoire** : aucune (premier pipeline de la chaîne)

---

## Objectif

Charger les 29 706 relevés acridiens terrain accumulés de 2001 à 2026, supprimer les lignes dont les coordonnées GPS sont aberrantes ou manquantes, affecter chaque relevé à sa région naturelle et à son acrido-région par double jointure spatiale, et calculer les champs temporels dérivés (campagne, décade de campagne). Ce pipeline produit la table de référence utilisée par tous les pipelines aval.

---

## Entrées

| Fichier | Description | Colonnes clés utilisées |
|---------|-------------|-------------------------|
| `data/2001_2026_Acrido_vf.xls` (feuille `2001_2025_AA`) | Relevés acridiens terrain bruts | `Date_` (serial Excel), `LAT_DD`, `LNG_DD`, `Sol`, `Trans`, `Greg`, `Sol_larve`, `Trans_larve`, `Greg_larve`, `DI_dif_moy`, `DL_dif_moy`, `Decade`, `Campagne` |
| `data/region_naturelle/region_naturelle.shp` | 90 polygones des régions naturelles de Madagascar | `rn_nom`, `rn_num`, `geometry` |
| `data/aire_gregarigene/aire_gregarigene.shp` | 12 polygones des acrido-régions (secteurs) | `AIRE_NOM`, `AIRE_CODE`, `SECT_NOM`, `SECT_NO`, `geometry` |

---

## Sorties

Toutes les colonnes LMC d'origine (sans `_NSE`), plus les colonnes dérivées suivantes :

| Colonne | Type | Description |
|---------|------|-------------|
| `date` | Timestamp | Date convertie depuis le numéro de série Excel (`Date_`) |
| `campagne_calc` | str ou None | Campagne au format `"YYYY-YYYY+1"`, calculé depuis `date` (source de vérité) |
| `decade_intra` | int (1–3) | Position de la décade dans le mois (D1 = jours 1–10, D2 = 11–20, D3 = 21–fin) |
| `campagne_decade` | int (1–30) | Position de la décade dans la campagne (octobre-D1 = 1, juillet-D3 = 30) |
| `rn_num` | Int64 nullable | Identifiant de la région naturelle (1–90), NaN si hors-polygone |
| `rn_nom` | str ou NaN | Nom de la région naturelle |
| `AIRE_NOM` | str ou NaN | Nom de l'acrido-région |
| `AIRE_CODE` | str ou NaN | Code de l'acrido-région |
| `SECT_NOM` | str ou NaN | Nom du secteur |
| `SECT_NO` | int ou NaN | Numéro du secteur |
| `hors_aire` | bool | `True` si le relevé est hors des 12 polygones de l'aire grégarigène |
| `geometry` | Point (EPSG:4326) | Point GPS du relevé |

---

## Règles métier

### RM-1 : Filtrage GPS

Les coordonnées valides pour Madagascar sont : `LAT_DD ∈ [-26.0, -11.0]` et `LNG_DD ∈ [43.0, 51.0]`. Les relevés dont l'une ou l'autre des coordonnées est NaN ou hors de ces bornes sont **définitivement supprimés** — ils ne sont pas conservés avec un flag. Les comptages sont affichés en fin d'exécution :

- Lignes supprimées pour GPS NaN : ~262
- Lignes supprimées pour GPS hors-bornes : ~39
- Total supprimé : ~301 lignes (< 1,1 % du dataset)

### RM-2 : Suppression des colonnes NSE

Toute colonne dont le nom contient le motif `_NSE` ou qui correspond exactement à `NSE.Sup_inf` est supprimée avant tout traitement. Le pipeline ne cible que *Locusta migratoria capito* (LMC).

### RM-3 : Priorité de la date calculée

La colonne `campagne_calc` est calculée depuis `date` (elle-même dérivée de `Date_` par conversion du serial Excel via `xlrd.xldate_as_datetime`), et non depuis la colonne `Campagne` du fichier XLS. En cas d'incohérence entre les deux, `date` est la source de vérité. Un avertissement non-bloquant est émis si le nombre d'incohérences détectées est supérieur à 0.

### RM-4 : Mois hors campagne acridienne

Les relevés dont la `date` tombe en août (mois 8) ou septembre (mois 9) reçoivent `campagne_calc = None` et `campagne_decade = None`. Ces lignes sont **conservées** dans le fichier Parquet de sortie (elles constituent de vraies observations terrain) mais ne participeront à aucun calcul de label ou de feature dans les pipelines aval.

### RM-5 : Correspondance décade → campagne_decade

| Mois | Décade intra-mois | campagne_decade |
|------|-------------------|-----------------|
| Octobre | D1, D2, D3 | 1, 2, 3 |
| Novembre | D1, D2, D3 | 4, 5, 6 |
| Décembre | D1, D2, D3 | 7, 8, 9 |
| Janvier | D1, D2, D3 | 10, 11, 12 |
| Février | D1, D2, D3 | 13, 14, 15 |
| Mars | D1, D2, D3 | 16, 17, 18 |
| Avril | D1, D2, D3 | 19, 20, 21 |
| Mai | D1, D2, D3 | 22, 23, 24 |
| Juin | D1, D2, D3 | 25, 26, 27 |
| Juillet | D1, D2, D3 | 28, 29, 30 |

### RM-6 : Jointure spatiale "within"

Un relevé reçoit `rn_num = NaN` s'il n'est pas strictement contenu dans l'un des 90 polygones de `region_naturelle`. De même, il reçoit `AIRE_NOM = NaN` et `hors_aire = True` s'il n'est pas contenu dans l'un des 12 polygones de `aire_gregarigene`. Les deux jointures sont indépendantes.

Les relevés `hors_aire = True` (~4 254 lignes) sont **conservés** car ils représentent de vraies prospections. Ils contribuent à l'effort de prospection mais ne génèrent pas de labels ni de prédictions spatiales dans les pipelines aval.

---

## Exécution

```bash
python src/nettoyage_jointure_01.py
```

Pas d'argument obligatoire. Le script lit les chemins depuis des constantes en tête de fichier.

---

## Dépendances

- **Amont** : aucune — premier pipeline de la chaîne
- **Aval** : [#02](02-gregarite-potentiel.md), [#03](03-labels-entrainement.md) consomment `01_releves_nettoyes.parquet`
- **Bibliothèques** : `geopandas`, `pandas`, `openpyxl`, `xlrd`, `shapely`, `pyarrow`

---

## Avertissements

Les valeurs aberrantes de coordonnées GPS (ex. `LAT_DD = -2 210 452`) proviennent d'erreurs de saisie dans le fichier Excel. Elles sont filtrées silencieusement après affichage du comptage — vérifier les statistiques en sortie à chaque exécution.

Les relevés `hors_aire` ne contribueront pas aux prédictions spatiales. Un secteur dont la plupart des relevés tombent `hors_aire` indique soit une imprécision GPS systématique, soit un problème de correspondance entre le shapefile et le terrain réel.
