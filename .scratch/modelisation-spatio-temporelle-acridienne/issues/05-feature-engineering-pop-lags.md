---
Status: done
---

# #05 — Feature engineering acridologique (POP consécutifs, lags temporels et spatiaux)

## What to build

À partir de la table de variables environnementales GEE (#04), calculer trois catégories de features dérivées. (1) **POP consécutifs** : compteur du nombre de mois consécutifs où la pluviométrie mensuelle CHIRPS est dans la Plage d'Optimum Pluviométrique (50–125 mm/mois) — le facteur de risque de grégarisation le plus prédictif identifié dans la littérature. (2) **Lags temporels** : pour chaque feature dynamique, les valeurs aux décades-1, décade-2, et mois précédent. (3) **Lags spatiaux** : valeur moyenne des régions naturelles adjacentes (définies par contiguïté dans le shapefile) pour les features environnementales clés, afin de partiellement capturer la propagation spatiale (en substitut des architectures GAT, hors périmètre selon ADR-0002).

## Acceptance criteria

- [x] Le compteur POP retourne 3 pour une séquence de 3 mois consécutifs en [50–125mm], puis se remet à 0 à la rupture
- [x] Les lags temporels (D-1, D-2, M-1) sont calculés sans fuite de données futures
- [x] Les lags spatiaux utilisent uniquement les régions contiguës (topologie du shapefile, pas un buffer distance)
- [x] Tests unitaires sur le compteur POP avec au moins 5 séquences pluviométriques connues (6 séquences testées)

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/04-extraction-variables-environnementales-gee.md`
