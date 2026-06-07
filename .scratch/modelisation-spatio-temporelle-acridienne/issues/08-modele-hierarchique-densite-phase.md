---
Status: ready-for-agent
---

# #08 — Modèle hiérarchique analytique (densité + phase acridienne)

## What to build

Compléter le modèle hiérarchique en ajoutant les deux étapes conditionnelles à la présence : (1) **densité** — modèle de régression LightGBM entraîné uniquement sur les relevés avec présence, prédisant la densité équivalent imago ; (2) **phase acridienne** — classifieur LightGBM entraîné sur les mêmes lignes, prédisant S/St/T/G. Le déséquilibre sévère de la classe grégaire (5,8% des observations) est corrigé par `scale_pos_weight` et seuil de décision abaissé. Les métriques cibles sont F1-macro et rappel sur la classe G. Les trois étapes (présence → densité → phase) sont enchaînées : une prédiction d'absence en étape 1 court-circuite les étapes 2 et 3.

## Acceptance criteria

- [ ] Rappel sur la classe grégaire (G) > 0,70 sur le fold de validation walk-forward
- [ ] F1-macro de classification de phase documenté par campagne
- [ ] Le pipeline hiérarchique court-circuite correctement les étapes densité et phase pour les prédictions d'absence
- [ ] RMSE et MAE de densité reportés sur les relevés avec présence uniquement
- [ ] Les trois modèles sont persistés séparément pour inférence indépendante

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/07-lgbm-baseline-presence-absence.md`
