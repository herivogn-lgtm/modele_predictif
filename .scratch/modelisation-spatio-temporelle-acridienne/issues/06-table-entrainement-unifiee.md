---
Status: done
---

# #06 — Table d'entraînement ML unifiée

## What to build

Joindre la table de labels (#03) avec la table de features ingénierées (#05) sur la clé `région naturelle × décade de campagne` pour produire le panel ML complet. La table finale contient : identifiant région naturelle, décade de campagne, toutes les features environnementales et dérivées, l'effort de prospection, le label de présence/absence (ou None si masqué), le potentiel acridien (ou None), le niveau de grégarité dominant. Définir et matérialiser le découpage temporel walk-forward : entraînement sur campagnes 2001–02 à 2015–16, validation sur 2016–17 à 2021–22, inférence sur 2025–26 (campagnes 2023–24 sans labels). Persister en Parquet pour les étapes suivantes.

## Acceptance criteria

- [x] Aucune cellule masquée (label None) n'est incluse dans les ensembles d'entraînement ou de validation
- [x] Le découpage walk-forward respecte la frontière temporelle campagne entière (pas de split aléatoire, pas de décade d'une campagne dans les deux ensembles)
- [x] L'effort de prospection est présent comme colonne feature dans la table finale
- [x] Les campagnes 2023–24 apparaissent dans la table mais avec labels = None (réservées à l'inférence)
- [x] La table Parquet est lisible et vérifiable sans exécuter le pipeline complet

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/03-labels-entrainement-region-decade.md`
- `.scratch/modelisation-spatio-temporelle-acridienne/issues/05-feature-engineering-pop-lags.md`
