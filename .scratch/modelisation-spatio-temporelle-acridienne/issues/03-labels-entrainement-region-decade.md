---
Status: done
---

# #03 — Agrégation en labels d'entraînement par région naturelle × décade

## What to build

Agréger les relevés acridiens géoréférencés et enrichis (sorties des issues #01 et #02) par `région naturelle × décade de campagne` pour produire la table de labels d'entraînement. Trois cas distincts sont gérés : **présence** (Sol+Trans+Greg > 0 sur au moins une ligne), **absence vérifiée** (toutes les lignes de la cellule ont Sol=Trans=Greg=0), **masqué** (aucune ligne de prospection pour cette cellule — label inconnu, jamais traité comme absence). L'effort de prospection (nombre de lignes de relevés pour la cellule) est calculé et conservé comme colonne. Les campagnes 2023–2024 sont exclues des labels (colonnes labels = None) mais leurs cellules sont conservées pour l'inférence future.

## Acceptance criteria

- [x] Les trois cas (présence / absence vérifiée / masqué) sont correctement distingués
- [x] Une région naturelle × décade sans aucune ligne de prospection retourne `label = None`, jamais `0`
- [x] L'effort de prospection (compte de lignes) est exact sur un sous-ensemble vérifié manuellement
- [x] Les campagnes 2023–2024 ont `label = None` pour toutes les cellules
- [x] Test unitaire : séquences connues de lignes terrain → labels attendus vérifiés

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/01-nettoyage-jointure-relevés.md`
- `.scratch/modelisation-spatio-temporelle-acridienne/issues/02-reconstruction-niveau-gregarite.md`
