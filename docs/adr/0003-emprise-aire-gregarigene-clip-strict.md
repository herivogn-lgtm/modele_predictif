---
status: accepted
---

# Emprise d'étude : aire grégarigène complète, clip strict (entraînement = prédiction)

## Contexte

La thèse §31 restreignait l'OS3 au Sud-Ouest (Betioky/Soalara/Mikea). Le shapefile
`data/aire_gregarigene/` délimite en fait **toute** l'aire grégarigène : 12 secteurs /
4 aires complémentaires (AMI/ATM/AD/AGT), ~181 414 ha (~1 814 km²), **fragmentés** dans
une grande bbox (~420 × 620 km). Sur 5 352 stations géolocalisées, **4 493 (84 %)**
tombent dans les polygones, 859 (16 %) à l'extérieur. Les relevés sont très épars
(médiane = 1 relevé/station) : ~25 000 cellules-décades observées sur ~1,6 M.

## Décision

- **Emprise = aire grégarigène complète** (les 12 polygones), pas le seul Sud-Ouest.
  Déviation assumée de la thèse §31.
- **Grille 1 km uniquement *à l'intérieur* des polygones** (~1 800 cellules), pas la bbox.
- **Clip strict** : le jeu d'entraînement **et** la surface de prédiction partagent la
  même emprise. Les **859 stations hors polygones sont écartées** (option C2 retenue
  contre C1 « garder hors-aire avec buffer »).
- Les **cellules-décades non prospectées ne sont pas des absences** : elles constituent
  la surface de prédiction. L'entraînement n'utilise que les relevés réels (présences +
  vraies absences : ~35 % des relevés sont à zéro).

## Conséquences

- Perte de 16 % des stations, au profit d'une validation honnête (on n'apprend que sur
  le biotope qu'on prédit).
- Vu l'extrême parcimonie temporelle, le modèle **généralise via les covariables
  environnementales**, pas via l'historique par cellule — ce qui valide l'approche
  télédétection de l'OS3.
- `AIRE_CODE` (AMI/ATM/AD/AGT) disponible comme prédicteur catégoriel ; l'AGT
  (transitoire, ajoutée en 1996) pourra justifier un traitement distinct.
