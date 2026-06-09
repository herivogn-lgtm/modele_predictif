# Glossaire — extraction GEE & modèle de sévérité-phase

Vocabulaire technique du pipeline d'extraction Google Earth Engine (pipelines 04/04b)
et du modèle de forecast, expliqué simplement et rattaché aux données du projet
(criquet migrateur malgache, aire grégarigène).

> Voir aussi : `CONTEXT.md` (glossaire métier), `docs/adr/` (décisions),
> `.scratch/severite-phase-forecast/04-scope-roadmap.excalidraw` (schéma d'ensemble).

---

## 1. L'espace et le temps — « où » et « quand »

| Terme | C'est quoi | Dans le projet |
|---|---|---|
| **Cellule** | Un carré de territoire de **1 km × 1 km**. Unité géographique de base. | **181 413** cellules sur l'aire grégarigène. |
| **Grille 1 km** | L'ensemble des carrés en quadrillage sur la carte. | `data/processed/01_grille_1km.parquet` |
| **`cell_id`** | Nom unique d'une cellule, ex. `515_7168` (colonne_ligne). Clé de jointure entre toutes les tables. | — |
| **AIRE_CODE / secteur** | Découpage écologique (AMI, ATM, AD, AGT). Chaque cellule appartient à un secteur. | 4 aires, 12 secteurs. |
| **Décade** | Tranche de **10 jours**. Le mois est coupé en 3 (1–10, 11–20, 21–fin). Unité de **temps**. | 30 décades / campagne (oct→juil). |
| **Campagne** | La saison acridienne d'une année, ex. `2010-2011`. | 22 campagnes de données. |
| **T+1** | « La prochaine décade ». Le modèle prédit ce qui se passera à la décade suivante. | Cœur de l'outil : alerter avant. |

> **Unité fondamentale = une cellule × une décade** (ex. carré `515_7168`, 2ᵉ décade
> de janvier 2010). Tout le pipeline tourne autour de ce couple.

---

## 2. Ce qu'on veut prédire — le **label**

| Terme | C'est quoi |
|---|---|
| **Label** (ou **cible**) | La « bonne réponse » connue grâce aux relevés terrain : y avait-il des criquets, à quel stade ? Ce que le modèle apprend à prédire. |
| **Sévérité-phase 0–3** | L'échelle du label : **0** absence · **1** solitaire · **2** transiens · **3** grégaire (le plus dangereux). |
| **Binaire dérivé** | Version simplifiée : présence (≥1) ou absence (0). Sert à la comparaison AUC avec la littérature. |
| **Cellule observée** | Cellule où un prospecteur est réellement allé → on a un label. |

> **Point clé du problème de scaling** : sur 181 413 cellules, seules **5 399 (3 %)**
> ont déjà été visitées. Les 97 % restantes n'ont **aucun label**.

---

## 3. Les données satellite — les **covariables**

| Terme | C'est quoi | Pourquoi |
|---|---|---|
| **Covariable** (= **feature**, variable explicative) | Une mesure qui aide à prédire le label. Ici, des données satellite. | Les criquets dépendent de la pluie et de la végétation. |
| **GEE** (Google Earth Engine) | Le « Google Maps des données satellite » : service en ligne stockant des décennies d'images et calculant sur ses serveurs. | C'est là qu'on va chercher les covariables. |
| **CHIRPS** | Données de **pluie** (précipitations), résolution ~5,5 km. | La pluie déclenche les pontes. |
| **NDVI / EVI** | Indices de **verdure de la végétation** (MODIS, 250 m). | Végétation verte = nourriture. |
| **LST** | **Température de surface** du sol (MODIS, 1 km). | Influence le développement. |
| **MODIS** | Le capteur satellite fournissant NDVI, EVI, LST. | — |
| **Baseline** | Pluie **moyenne historique** (1981–2010) d'une décade donnée. | Référence de « normalité ». |
| **Anomalie** | Pluie actuelle **moins** baseline → a-t-il plu plus/moins que d'habitude ? | Signal fort pour les criquets. |

---

## 4. Les outils GEE — la **mécanique**

| Terme | C'est quoi | Analogie |
|---|---|---|
| **`sampleRegions`** | « Donne la valeur du satellite **au centre de chaque cellule** » (1 point/carré). | Planter une sonde au milieu de chaque carré et lire. |
| **`reduceRegions`** | Variante : **moyenne sur toute la surface** d'une zone (adaptée aux grandes régions, pas aux carrés 1 km). | Plus utilisé. |
| **`getInfo`** | « Renvoie le résultat **tout de suite** » (mode interactif). | Question → réponse en direct. |
| **Limite des 5000 éléments** | `getInfo` refuse de renvoyer plus de **5000 lignes** d'un coup. | D'où ~86 000 requêtes nécessaires sur la grille pleine → trop lent. |
| **`Export.table` / tâche** | « **Calcule en arrière-plan** et dépose le résultat dans un fichier (Drive) ». Pas de limite de taille. | On commande, ça mijote côté serveur, on récupère plus tard. |
| **EECU-hours** | Unité de **consommation de calcul** GEE. Plus la tâche est grosse, plus c'est long/coûteux. | Les « 8 657 » d'une tâche = tâche énorme. |
| **Parquet** | Format de fichier **tableau compressé** (Excel géant et rapide). | Toutes les sorties `.parquet`. |

---

## 5. Le vocabulaire du modèle (pipeline aval)

| Terme | C'est quoi |
|---|---|
| **POP** (Plage d'Optimum Pluviométrique) | La pluie est-elle dans la bande **50–125 mm/mois** (idéale criquets), et depuis combien de mois ? |
| **Lag** (décalage) | Covariable du **passé** (ex. pluie des 2 décades précédentes). Le modèle regarde l'historique. |
| **Anti-fuite (T+1)** | Règle stricte : **interdit d'utiliser une donnée du futur** (décade à prédire) pour prédire. Sinon on triche. |
| **Surface de prédiction** | Toutes les cellules pour lesquelles on veut une prédiction, **même jamais visitées** (covariables présentes, label inconnu) — ≠ absences. |
| **Walk-forward** | Validation : entraîner sur le passé, tester sur la saison suivante, avancer dans le temps. |

---

## En une phrase — le problème de scaling

> On a voulu télécharger les **covariables satellite (GEE)** pour **chaque cellule ×
> chaque décade** (141 M combinaisons), mais **97 % des cellules n'ont pas de label**
> → inutile pour entraîner. La cible : ne télécharger que les **5 399 cellules
> observées** pour l'entraînement, et garder la grille complète seulement pour la
> **carte de prédiction de la prochaine décade (T+1)**.
