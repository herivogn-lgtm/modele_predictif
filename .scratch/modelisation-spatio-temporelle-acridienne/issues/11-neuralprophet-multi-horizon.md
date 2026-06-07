---
Status: in-progress
---

# #11 — NeuralProphet multi-horizon (décadaire / mensuel / saisonnier)

## What to build

Entraîner un modèle NeuralProphet sur la table d'entraînement unifiée (#06) pour produire des prédictions simultanées aux trois horizons temporels (décadaire, mensuel, saisonnier) en une seule passe. NeuralProphet gère nativement les séries temporelles irrégulières et les lacunes (campagnes 2023–24 sans labels), et s'exécute sur CPU selon ADR-0002. Comparer les performances avec le baseline LightGBM (#07) sur les mêmes folds walk-forward. Cette tranche est déclenchée si l'AUC du baseline walk-forward (#10) est inférieure à 0,80, ou si la prédiction multi-horizon simultanée apporte un avantage démontrable sur les horizons mensuel et saisonnier.

## Acceptance criteria

- [ ] NeuralProphet produit des prédictions aux trois horizons (décadaire, mensuel, saisonnier) en une passe
- [ ] Les lacunes de données (campagnes 2023–24) sont gérées sans imputation des labels manquants
- [ ] Les métriques walk-forward sont comparées au baseline LightGBM sur les mêmes folds
- [ ] L'entraînement complet s'exécute sur CPU standard en moins de 30 minutes
- [ ] La décision de déployer NeuralProphet en production est documentée (gain vs complexité ajoutée)

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/06-table-entrainement-unifiee.md`
