---
Status: done
---

# #04 — Extraction des variables environnementales GEE par région naturelle × décade

## What to build

Via Google Earth Engine, extraire les statistiques zonales (moyenne, min, max, écart-type) sur chacun des 90 polygones de régions naturelles pour chaque décade de campagne couverte par les données terrain (2001–2026). Sources à extraire : CHIRPS (pluviométrie décadaire + anomalie vs historique), MODIS MOD13A2 (NDVI, EVI), ERA5 (humidité du sol), MODIS MOD11A2 (LST), MODIS MCD12Q1 (occupation du sol, une valeur annuelle), SoilGrids (texture du sol, statique), SRTM DEM (altitude, statique). L'indice ENSO/ONI est récupéré depuis NOAA (source externe, mensuel). La sortie est une table `région naturelle × décade` avec toutes les features environnementales.

## Acceptance criteria

- [ ] Toutes les sources listées sont extraites pour la plage 2001–2026
- [ ] Les features statiques (DEM, texture du sol, occupation du sol) sont incluses une fois et jointes à la table
- [ ] Les valeurs extraites sont dans les plages physiquement attendues (ex. NDVI ∈ [-1, 1], LST en Kelvin raisonnable)
- [ ] Les décades sans couverture satellite (nuages, lacunes) sont marquées NaN et non imputées
- [ ] Test d'intégration : l'extraction sur une région naturelle et une décade retourne des valeurs dans les plages attendues pour chaque feature

## Blocked by

None - can start immediately
