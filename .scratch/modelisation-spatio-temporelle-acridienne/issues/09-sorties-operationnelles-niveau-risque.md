---
Status: done
---

# #09 — Sorties opérationnelles : niveau de risque acridien 0-4 par acrido-région à trois horizons

## What to build

À partir des prédictions du modèle hiérarchique (#08) à l'échelle des 90 régions naturelles, calculer le niveau de risque acridien 0–4 par polygone (en combinant potentiel acridien prédit et potentiel écologique implicitement capturé par les features GEE), puis agréger vers les 12 acrido-régions du shapefile `aire_gregarigene`. Produire les sorties à trois horizons temporels : **décadaire** (où envoyer les équipes dans les 10 prochains jours), **mensuel** (bulletin CNA), **saisonnier** (prédiction de septembre avant la campagne d'octobre). Les sorties sont exportées en GeoJSON (avec géométrie des acrido-régions) et en CSV (pour intégration SIG-LMC).

## Acceptance criteria

- [x] Le niveau de risque 0–4 est calculé pour chacune des 90 régions naturelles avant agrégation
- [x] L'agrégation vers les 12 acrido-régions utilise le shapefile `aire_gregarigene` (champ `AIRE_CODE`)
- [x] Les sorties à trois horizons sont produites en GeoJSON et CSV
- [x] Les niveaux 3–4 (transiens congregans probables) sont distingués des niveaux 1–2 dans les sorties
- [x] Les cellules correspondant à des zones non ou peu prospectées sont annotées (effort de prospection bas)

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/08-modele-hierarchique-densite-phase.md`
