---
status: accepted
---

# Horizon de prédiction : forecast à la décade T+1 (pas nowcast)

## Contexte

L'OS3 vise la **détection précoce** et l'**anticipation** des foyers (thèse §31, RA2).
Un *nowcast* (estimer la sévérité de la décade courante à partir des covariables de la
même décade) ne fait que compléter la couverture spatiale : au moment où l'image de la
décade T est disponible, le foyer s'exprime déjà.

## Décision

Le modèle prédit la **sévérité-phase de la décade T+1** à partir de covariables
**passées uniquement** (lags) : cumuls de pluie sur 2–3 décades, NDVI/LST décalés,
POP et persistance multi-mois, sévérité historique de la cellule. La cible
d'entraînement et de validation est la décade **T+1**.

## Conséquences

- **Feature engineering = lags**. Aucune covariable de la décade T+1 ne peut entrer
  comme prédicteur (sinon fuite temporelle).
- **Validation walk-forward** par campagne/saison obligatoire (pas de k-fold aléatoire,
  qui fuiterait dans le temps).
- Le **nowcast spatial** reste possible comme sous-produit (carte de complétion là où
  l'IFVM n'a pas prospecté), mais n'est pas la cible primaire.
