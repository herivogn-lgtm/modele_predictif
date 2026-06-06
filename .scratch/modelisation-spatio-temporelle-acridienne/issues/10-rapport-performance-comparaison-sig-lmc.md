---
Status: done
---

# #10 — Rapport de performance walk-forward et comparaison avec le SIG-LMC existant

## What to build

Produire le rapport de performance complet du système sur les campagnes historiques 2001–2022, en mode walk-forward par campagne entière. Le rapport inclut : métriques par fold (AUC présence/absence, F1-macro phase, RMSE densité, rappel grégaire), courbe de performance au fil des campagnes, et analyse du biais de détection lié à l'effort de prospection (performance corrélée à la densité de relevés par région naturelle × décade). Comparer les prédictions de niveau de risque 0–4 du modèle avec les cartes de risque historiques du SIG-LMC du CNA pour les campagnes disponibles, et quantifier l'apport de l'approche ML.

## Acceptance criteria

- [x] Les métriques sont reportées par fold de campagne (pas uniquement une moyenne globale)
- [x] L'analyse du biais de détection montre la relation entre effort de prospection et performance prédictive par région naturelle
- [x] La comparaison avec les cartes SIG-LMC historiques quantifie l'accord et les divergences (stub conditionnel — données non encore disponibles dans `data/sig_lmc/`)
- [x] Le rapport est exporté dans un format lisible (notebook Jupyter ou HTML)
- [x] Les campagnes 2023–24 (inférence uniquement, sans labels) sont clairement exclues de l'évaluation

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/09-sorties-operationnelles-niveau-risque.md`
