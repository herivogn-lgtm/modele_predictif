---
status: accepted
---

# Cible ordinale de sévérité-phase (hiérarchique) plutôt que présence/absence binaire

## Contexte

L'OS3 de la thèse définit la cible du modèle comme une **présence/absence**
(probabilité de présence, validation AUC — §31, §33). L'inspection de
`2001_2026_Acrido_vf.xls` (29 706 relevés, 2001–2025) révèle que la donnée porte
nativement **deux axes** : la **phase** (`Sol`/`Trans`/`Greg`, larves et adultes,
en comptages) et l'**abondance** (`L1–L6`, `A1–A5`, densités `DL_*`/`DI_*`).
Une présence de solitaires dispersés n'a quasi aucune valeur opérationnelle pour
l'IFVM ; ce qui déclenche l'action, c'est la **phase** (transiens/grégaire).

## Décision

La cible primaire est une **variable ordinale de sévérité à 4 niveaux**, fondée sur
la **phase maximale** observée dans la cellule × décade :

- **0** absence (relevé, tous compteurs à 0) — ~35 % des relevés sont de vraies absences
- **1** présence solitaire (`Sol`/`Sol larve` > 0)
- **2** transiens (`Trans`/`Trans larve` > 0)
- **3** grégaire (`Greg`/`Greg larve` > 0)

Structure **hiérarchique** : on en dérive (a) un **binaire présence/absence**
(niveau ≥ 1) pour conserver l'AUC et la fidélité thèse, et (b) une **couche
d'intensité optionnelle** (`log(densité)`) là où la densité existe.

## Options considérées

- **Présence/absence binaire** (thèse stricte) — rejetée : efface la distinction
  solitaire/grégaire, qui est précisément l'information opérationnelle.
- **Score continu pondéré phase × densité** — rejeté : écrase deux axes
  orthogonaux en un scalaire via un « taux de change » arbitraire, et hérite du
  bruit des densités.
- **Ordinal 0–6 type Annexe 8, niveaux splittés par densité** — rejeté : les
  densités ont ~35 % de NaN et atteignent 2 M ; trop peu fiables pour *définir*
  des classes. On ne bâtit pas la cible sur la colonne la moins fiable.

## Conséquences

- **Déviation assumée de la thèse** : la sévérité-phase dépasse le présence/absence
  de l'OS3. Le binaire dérivé préserve néanmoins la validation AUC exigée (§31).
- **Validation double** : QWK (ordinal) + AUC (binaire dérivé) + confrontation terrain.
- **Robustesse** : la couche d'intensité est dégradable — l'absence de densité
  n'empêche jamais la production des niveaux 0–3.
- **Restitution** : carte de sévérité 1 km × décade, agrégeable au mois.
