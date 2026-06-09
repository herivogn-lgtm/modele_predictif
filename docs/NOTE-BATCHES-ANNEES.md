# Note technique — Batches d'années vs décades extraites

## Question

Pourquoi `--decades 2026-14:2026-18` affiche "1 lots d'années" alors qu'on veut seulement 5 décades ?

---

## Réponse courte

**Le message est trompeur mais le comportement est correct** : GEE extrait **uniquement les 5 décades demandées**, pas toute l'année 2026.

---

## Explication détaillée

### Architecture des tâches GEE

Les tâches d'export sont organisées par **lots d'années** (batches) pour limiter la taille de chaque tâche :

```
Tâche = (source × batch d'années × tuile spatiale)
```

**Exemple avec `--years 2001 2002 2003 2004 2005 2006`** :
- Batch 1 : [2001, 2002, 2003]
- Batch 2 : [2004, 2005, 2006]
- → 2 lots × 3 sources × 13 tuiles = 78 tâches

---

### Cas `--decades 2026-14:2026-18`

**Étape 1 : Déterminer les années concernées**

```python
years_list = list(range(y_start, y_end + 1))  # [2026]
```

Ici, `y_start=2026` et `y_end=2026`, donc **1 seule année**.

**Étape 2 : Créer les batches d'années**

```python
batches = _year_batches([2026])  # [[2026]]
```

Résultat : **1 batch contenant [2026]**

**Étape 3 : Générer les specs GEE**

Pour chaque batch, on filtre le calendrier :

```python
batch_calendar = calendar[calendar["year"].isin([2026])]
# → Garde seulement les 5 décades (14-18) de 2026

specs = build_specs(batch_calendar, lead, lag)
# → 5 specs précises avec dates ISO
```

**Résultat** : Les tâches GEE reçoivent **uniquement 5 specs** avec fenêtres temporelles précises :

```
Decade 202614 : 2026-05-01 → 2026-05-30
Decade 202615 : 2026-05-11 → 2026-06-10
Decade 202616 : 2026-05-22 → 2026-06-20
Decade 202617 : 2026-06-01 → 2026-06-30
Decade 202618 : 2026-06-11 → 2026-07-10
```

**GEE filtrera les ImageCollections avec `filterDate(start, end)`** pour chaque spec → extraction des **5 décades uniquement**.

---

## Preuve par les volumes

### Extraction `--decades 2026-14:2026-18`

```
Décades extraites : 5
Lignes attendues  : 181,413 cellules × 5 décades = 907,065 lignes
```

### Si c'était toute l'année 2026

```
Décades extraites : 36
Lignes attendues  : 181,413 cellules × 36 décades = 6,530,868 lignes
```

**Ratio** : 907k vs 6,5M lignes → **7× moins de données** avec `--decades`.

---

## Pourquoi le message "1 lots d'années" ?

Le code organise les tâches par **batch d'années** pour des raisons techniques (limite de taille des tâches GEE). Le message affiche le nombre de batches, mais **ne signifie pas que toute l'année est extraite**.

**Avant correction** :
```
1 lots d'années (≤ 3 ans).
```
☹️ Trompeur : on dirait que toute l'année 2026 est extraite.

**Après correction** :
```
1 lot(s) de tâches GEE (les specs filtrent précisément les 5 décades).
```
✅ Clair : précise que seules les décades demandées sont extraites.

---

## Vérification après extraction

Après `assemble`, vérifiez le volume de données :

```bash
./.venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('data/processed/04_variables_environnementales/')

# Filtrer juin 2026 (décades 16-18)
june = df[(df.date_start >= '2026-06-01') & (df.date_start < '2026-07-01')]
print(f'Juin 2026: {len(june):,} lignes, {june.cell_id.nunique():,} cellules')
print(f'Attendu: {181413 * 3:,} lignes (181,413 cellules × 3 décades)')

# Filtrer mai-juin 2026 (décades 14-18)
may_june = df[(df.date_start >= '2026-05-11') & (df.date_start <= '2026-06-30')]
print(f'\nMai-Juin 2026: {len(may_june):,} lignes')
print(f'Attendu: {181413 * 5:,} lignes (181,413 cellules × 5 décades)')
"
```

**Attendu** :
- Juin seul (D16-18) : ~544 239 lignes
- Mai D2-D3 + Juin (D14-18) : ~907 065 lignes

---

## Conclusion

✅ **Le comportement est correct** : `--decades 2026-14:2026-18` extrait **uniquement 5 décades**.

✅ **Le message a été corrigé** pour être plus clair.

✅ **Vérifiez le volume de données** après `assemble` pour confirmer (~907k lignes, pas 6,5M).
