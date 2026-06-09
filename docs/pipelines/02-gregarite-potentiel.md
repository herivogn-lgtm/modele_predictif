# Pipeline #02 — Grégarité et potentiel acridien

**Script** : `src/gregarite_potentiel_02.py`  
**Entrée** : `data/processed/01_releves_nettoyes.parquet`  
**Sortie** : `data/processed/02_gregarite_potentiel.parquet`  
**Durée estimée** : < 2 minutes  
**Dépendance obligatoire** : Pipeline [#01](01-nettoyage-jointure.md)

---

## Objectif

Calculer pour chaque relevé acridien nettoyé trois indicateurs biologiques dérivés : le niveau de grégarité simplifié (absent / S / St / T / G), la densité équivalent imago en individus par hectare, et le potentiel acridien (0–5) via la matrice Annexe 8 du Manuel de lutte préventive. Ces indicateurs sont les cibles biologiques du système et servent à la fois de features et de variables de validation dans les pipelines aval.

---

## Entrées

| Fichier | Description | Colonnes clés utilisées |
|---------|-------------|-------------------------|
| `data/processed/01_releves_nettoyes.parquet` | Relevés nettoyés avec jointure spatiale | `Sol`, `Trans`, `Greg`, `DI_dif_moy`, `DL_dif_moy` |

---

## Sorties

Toutes les colonnes de `01_releves_nettoyes.parquet`, plus :

| Colonne | Type | Description |
|---------|------|-------------|
| `niveau_gregarite` | str ou None | Phase acridienne : `"absent"`, `"S"`, `"St"`, `"T"`, `"G"`, ou `None` si données manquantes |
| `densite_imago` | float (ind/ha) | Densité totale équivalent imago |
| `potentiel_acridien` | int (0–5) ou None | Niveau de potentiel selon la matrice Annexe 8 |

---

## Règles métier

### RM-1 : Algorithme de détermination du niveau de grégarité

Les colonnes `Sol`, `Trans`, `Greg` représentent les comptages d'imagos adultes observés en phase solitaire, transiente et grégaire. L'algorithme de classification est :

```
total = Sol + Trans + Greg
si total == 0        → "absent"
si Greg > 0          → "G"   (grégaires présents)
si Trans >= Sol > 0  → "T"   (transiens dominants)
si Trans > 0         → "St"  (solitaro-transiens)
sinon (Sol > 0)      → "S"   (solitaires uniquement)
```

Si l'une des trois colonnes (`Sol`, `Trans`, `Greg`) est NaN → `niveau_gregarite = None`.

### RM-2 : Calcul de la densité équivalent imago

La densité est calculée à partir des données de comptage en transects :

```
densite_imago = DI_dif_moy + DL_dif_moy / 9
```

- `DI_dif_moy` : densité des imagos adultes (ind/ha) — directe
- `DL_dif_moy` : densité des larves (ind/ha) divisée par 9 — le facteur 9 convertit les larves en équivalent imago (source : Manuel de lutte préventive, p. 52 : 1 imago ≡ 9 petites larves)

Règles sur les NaN : si une seule valeur est NaN, elle est traitée comme 0. Si les deux sont NaN → `densite_imago = NaN`.

### RM-3 : Matrice Annexe 8 — potentiel acridien

La matrice (source : Manuel de lutte préventive, p. 307) associe un potentiel acridien (0–5) au croisement du niveau de grégarité et de la classe de densité :

| Niveau \ Densité (ind/ha) | d = 0 | ]0–10] | ]10–100] | ]100–500] | ]500–1500] | ]1500–2500] | ]2500–10000] | > 10000 |
|--------------------------|-------|--------|----------|-----------|------------|-------------|--------------|---------|
| absent | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S | 0 | 1 | 1 | 2 | 2 | 3 | 3 | 3 |
| St | 0 | 1 | 2 | 2 | 3 | 3 | 3 | 3 |
| T | 0 | 2 | 2 | 2 | 3 | 3 | 3 | 4 |
| G | 0 | 2 | 2 | 3 | 3 | 3 | 4 | 5 |

> Note : Le terrain ne distingue pas les sous-niveaux T1/T2/T3. La phase T est mappée conservativement sur T1 lors de la consultation de la matrice.

### RM-4 : Cas particuliers

- `niveau_gregarite = "absent"` → `potentiel_acridien = 0` sans consulter la densité
- `niveau_gregarite = None` → `potentiel_acridien = None`
- `densite_imago = NaN` avec niveau ≠ "absent" → `potentiel_acridien = None`

---

## Exécution

```bash
python src/gregarite_potentiel_02.py
```

---

## Dépendances

- **Amont** : [#01](01-nettoyage-jointure.md) — `01_releves_nettoyes.parquet`
- **Aval** :
  - [#03](03-labels-entrainement.md) — consomme `Sol`, `Trans`, `Greg` pour la sévérité ordinale et `densite_imago` pour l'intensité optionnelle
- **Bibliothèques** : `pandas`, `numpy`, `pyarrow`

---

## Avertissements

Le potentiel acridien (RM-3) et la densité (RM-2) sont des indicateurs **observés** au niveau du relevé. Dans l'architecture OS3 actuelle ([ADR 0001](../adr/0001-cible-ordinale-severite-phase.md)), la cible du modèle est la **sévérité-phase ordinale 0–3** dérivée des comptages (#03), pas le potentiel acridien 0–5 de l'Annexe 8 — cette échelle 0–6 / 0–5 a été abandonnée du périmètre de modélisation. Le `niveau_gregarite` et `densite_imago` restent calculés ici car ils alimentent la sévérité (#03) et l'intensité optionnelle.
