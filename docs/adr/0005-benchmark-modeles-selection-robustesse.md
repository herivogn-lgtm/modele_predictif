---
status: accepted
---

# Sélection du modèle par benchmark walk-forward (pas de RF imposé a priori)

## Contexte

La thèse (H3) nomme **Random Forest**. Mais le problème est **tabulaire** (cellule × décade,
features = lags environnementaux + POP + `AIRE_CODE` + sévérité historique), cible **ordinale
0–3**, forecast T+1. Sur tabulaire, les arbres boostés et RF dominent ; un LSTM est mal
adapté (cellules vues ~1 fois → pas de séquence par entité ; la dynamique vit dans les lags,
déjà fournis comme features).

## Décision

- **Benchmark** plutôt que choix a priori. Panel : régression **ordinale** (plancher),
  **Random Forest** (référence thèse à battre), **XGBoost**, **LightGBM**, option **CatBoost** ;
  **LSTM** testé à la demande mais rejet probable.
- **Cadrage ordinal** (régression 0–3 arrondie ou multiclasse), métrique **QWK**.
- **Protocole de sélection = robustesse**, pas meilleure moyenne :
  - validation **walk-forward par campagne** ;
  - **« robuste » = faible variance inter-folds + bonne *pire* campagne** ;
  - **métrique primaire = rappel sur niveaux 2–3** (ne pas manquer un foyer), **sous
    contrainte QWK ≥ baseline** ;
  - AUC du binaire dérivé suivi pour la fidélité thèse §31 ;
  - calibration des probabilités vérifiée ;
  - **tie-break vers le modèle le plus simple/interprétable** (outil IFVM, valeur du
    feature importance POP/NDVI).

## Conséquences

- RF reste dans le panel comme référence, conformément à l'esprit de la thèse, sans être imposé.
- Le niveau 3 minoritaire (6,6 %) impose pondération de classe / réglage de seuil.
- Le modèle retenu doit être déployable côté IFVM (favorise GBDT/RF sur deep learning).
