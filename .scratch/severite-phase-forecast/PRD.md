# PRD — Modèle de forecast de sévérité-phase acridienne (OS3)

Status: ready-for-agent

> Volet technique (OS3) de la thèse N. RANDRIANARIJAONA. Toutes les décisions
> structurantes sont tracées dans `CONTEXT.md` (glossaire) et `docs/adr/0001`→`0005`.
> Ce PRD est un **rework** des pipelines existants (`src/` à la racine), pas du neuf.
> `model_2/` est **obsolète** (ADR contradictoires) et sera supprimé hors de ce PRD.

## Problem Statement

L'IFVM lutte contre le Criquet migrateur malgache (*Locusta migratoria capito*) de
manière essentiellement **réactive** : on prospecte puis on traite une fois les foyers
visibles. La surveillance acridienne dévient coûteuse et discontinue, et les zones à risque
ne sont pas anticipées. Le décideur n'a aucun outil lui disant **où** et **avec quelle
gravité** un foyer risque d'apparaître à la **prochaine décade**, ce qui empêche de
cibler les prospections et de réduire les coûts.

## Solution

Un modèle prédictif spatio-temporel qui, pour chaque cellule de **1 km** de l'aire
grégarigène et pour la **décade suivante (T+1)**, estime une **sévérité-phase ordinale
0–3** (0 absence, 1 solitaire, 2 transiens, 3 grégaire) à partir de covariables
**passées** issues de la télédétection (NDVI/EVI, LST, pluviométrie CHIRPS), de la
**POP** (plage d'optimum pluviométrique) et du compartiment grégarigène. La sortie est
restituée en **carte décadaire** (alerte précoce) et **agrégée au mois** (planification),
avec un **binaire présence/absence dérivé** pour la validation AUC exigée par la thèse.
L'outil oriente les prospections vers les cellules à sévérité 2–3.

## User Stories

1. En tant que prospecteur IFVM, je veux une carte de sévérité-phase 0–3 à 1 km pour la décade à venir, afin de concentrer mes tournées sur les cellules les plus à risque.
2. En tant que prospecteur IFVM, je veux distinguer une présence solitaire (niveau 1, bruit de fond) d'un foyer transiens/grégaire (niveaux 2–3), afin de ne pas gaspiller mes déplacements sur des présences sans enjeu.
3. En tant que responsable de la lutte, je veux une alerte dès qu'une cellule passe au niveau 3 (grégaire) en T+1, afin de déclencher une intervention avant l'expression du foyer.
4. En tant que responsable de la lutte, je veux une vue agrégée mensuelle de la sévérité par aire complémentaire (AMI/ATM/AD/AGT), afin de planifier les interventions.
5. En tant que décideur national, je veux une carte de probabilité de présence (binaire dérivé), afin de comparer la performance à la littérature (AUC) et de justifier l'outil.
6. En tant que prospecteur, je veux que la prédiction couvre toute l'aire grégarigène (les 12 secteurs), pas seulement le Sud-Ouest, afin de ne pas laisser d'angle mort.
7. En tant qu'analyste, je veux que les cellules non prospectées soient prédites (surface de prédiction) et non traitées comme des absences, afin d'éviter un biais massif.
8. En tant qu'analyste, je veux que la sévérité d'une cellule × décade soit la **phase maximale** observée, afin que le pire stade présent gouverne le risque.
9. En tant qu'analyste, je veux une couche d'intensité optionnelle (log densité) là où la densité existe, afin d'enrichir l'alerte sans bloquer la sortie quand la densité manque.
10. En tant qu'ingénieur données, je veux nettoyer et joindre les relevés (`2001_2026_Acrido_vf.xls`) puis les **rattacher à leur cellule 1 km**, afin de construire les labels.
11. En tant qu'ingénieur données, je veux **clipper strictement** relevés et grille aux polygones de l'aire grégarigène, afin que l'entraînement et la prédiction partagent la même emprise.
12. En tant qu'ingénieur données, je veux que les relevés à zéro partout comptent comme **vraies absences** (niveau 0), afin d'avoir des négatifs réels sans pseudo-absences.
13. En tant qu'ingénieur features, je veux extraire NDVI/EVI/LST/CHIRPS via Google Earth Engine, agrégés à la décade sur la grille 1 km, afin d'alimenter le modèle.
14. En tant qu'ingénieur features, je veux calculer la **POP** : appartenance à la bande 50–125 mm/mois (fenêtre glissante) et **persistance multi-mois**, afin d'encoder le déterminant pluviométrique.
15. En tant qu'ingénieur features, je veux des **lags** (cumul pluie 2–3 décades, NDVI/LST décalés, sévérité historique) **sans aucune covariable de T+1**, afin d'éviter toute fuite temporelle.
16. En tant qu'ingénieur features, je veux `AIRE_CODE` (AMI/ATM/AD/AGT) comme prédicteur catégoriel, afin de capter la compartimentation opérationnelle.
17. En tant que data scientist, je veux **benchmarker** régression ordinale (baseline), Random Forest, XGBoost, LightGBM, CatBoost et tester un LSTM, afin de ne pas imposer un algorithme a priori.
18. En tant que data scientist, je veux une **validation walk-forward par campagne** (saut 2023-2024), afin de mesurer la performance sur des saisons futures sans fuite.
19. En tant que data scientist, je veux sélectionner le modèle sur le **rappel des niveaux 2–3 sous contrainte QWK ≥ baseline**, afin de prioriser « ne pas manquer un foyer ».
20. En tant que data scientist, je veux juger la **robustesse** par la variance inter-folds et la pire campagne, et non la meilleure moyenne, afin de retenir un modèle fiable.
21. En tant que data scientist, je veux un **tie-break vers le modèle le plus simple/interprétable** à performance proche, afin de privilégier le feature importance (POP, NDVI) exploitable par l'IFVM.
22. En tant que data scientist, je veux vérifier la **calibration** des probabilités, afin que les seuils d'alerte soient exploitables.
23. En tant que data scientist, je veux une **pondération de classe** pour le niveau 3 minoritaire (6,6 %), afin qu'il ne soit pas écrasé.
24. En tant qu'analyste, je veux un rapport de performance par campagne (QWK, rappel 2–3, AUC binaire, courbe de gain/lift), afin d'évaluer le gain opérationnel.
25. En tant qu'analyste, je veux que la fenêtre d'entraînement couvre **2001–2026** sans couper les années précoces, afin de conserver les rares exemples grégaires (2004/2007/2008).
26. En tant qu'ingénieur, je veux que la lacune 2023-2024 (labels absents) soit gérée sans casser le calcul des features (covariables GEE continues), afin de garder un pipeline robuste.
27. En tant qu'utilisateur de l'outil, je veux une carte PNG + un export SIG des sévérités, afin d'intégrer le résultat dans mes supports terrain.
28. En tant que mainteneur, je veux que chaque étage de pipeline reste une fonction pure testable, afin de préserver la testabilité existante.

## Implementation Decisions

- **Architecture** : conserver le découpage en pipelines numérotés de `src/` (chaque module = fonctions pures + un `run()` d'orchestration I/O). Réutiliser les seams existants, pas en créer de nouveaux sauf nécessité.
- **Emprise (ADR 0003)** : grille régulière **1 km clipée à l'intérieur des polygones** `data/aire_gregarigene/` (12 secteurs, ~1 800 cellules). Clip strict : entraînement = prédiction. Relevés hors polygones (16 %) écartés.
- **Unité spatio-temporelle** : cellule 1 km × **décade** (col. `Decade` 1–36). Restitution agrégée au mois (`Mois_`, `M_Annee`).
- **Pipeline 01 (nettoyage/jointure)** : passer du rattachement `région naturelle` au **snap point→cellule 1 km** + clip aux polygones. Conserver `LAT_DD`/`LNG_DD`, `Date_`, `Decade`, `Campagne`.
- **Pipeline 03 (labels) — changement majeur** : `compute_label` (binaire) devient `compute_severite` → **ordinal 0–3** = phase maximale dans la cellule × décade :
  - 0 si relevé à zéro partout ; 1 si `Sol`/`Sol larve` > 0 seuls ; 2 si `Trans`/`Trans larve` > 0 ; 3 si `Greg`/`Greg larve` > 0.
  - `aggregate_per_cell` agrège plusieurs relevés d'une même cellule × décade par la phase max.
  - **Binaire dérivé** = (sévérité ≥ 1), conservé pour l'AUC.
  - **Intensité optionnelle** = `log(densité)` (`DL_*`/`DI_*`) là où renseigné, jamais bloquante (~35 % NaN).
- **Pipeline 04 (GEE)** : extraire NDVI/EVI (MODIS/Sentinel-2), LST (MODIS), précipitations (CHIRPS) agrégés **à la décade** sur la grille 1 km. Conserver le module de helpers ee-free pour la testabilité.
- **Pipeline 05 (features)** : ajouter (a) **POP** = bande **50–125 mm/mois** en fenêtre glissante + **persistance multi-mois** ; (b) **lags** : cumul pluie 2–3 décades, NDVI/LST décalés, sévérité historique de la cellule ; (c) `AIRE_CODE` catégoriel. **Interdiction de toute feature de la décade T+1** (anti-fuite).
- **Pipeline 06 (table)** : assembler la table cellule × décade : features laggées + cible ordinale + binaire dérivé + intensité optionnelle.
- **Pipelines 07/08 (modèles) — refonte** : remplacer le « LightGBM seul » par un **benchmark** : régression ordinale (baseline), Random Forest (référence thèse), XGBoost, LightGBM, CatBoost (catégoriel natif), + **LSTM** testé. Cadrage ordinal (régression 0–3 arrondie ou multiclasse). Pondération de classe pour le niveau 3.
- **Nouveaux seams** : `walk_forward_split` (folds = campagnes chronologiques, saut 2023-2024) et `select_robust` (classe les modèles par rappel niv. 2–3 sous contrainte QWK ≥ baseline, départage par variance inter-folds puis simplicité).
- **Pipeline 09 (sorties)** : carte de sévérité 0–3 (décade + agrégat mensuel par aire), binaire dérivé, export PNG + SIG./ha
- **Pipeline 10 (rapport)** : métriques walk-forward par campagne — QWK, rappel niveaux 2–3, AUC binaire, calibration, courbe de gain/lift.
- **Pipeline 11 (NeuralProphet)** : **supprimé** (ADR 0005).
- **Fenêtre (ADR 0004)** : 2001–2026 complet, lacune 2023-2024 gérée (features GEE continues, campagnes vides sautées en validation).

## Testing Decisions

- **Principe** : tester le **comportement externe** des fonctions pures de chaque étage, pas l'implémentation ni l'I/O. Pattern existant : `tests/test_NN_*.py` construisent des DataFrames synthétiques et vérifient les transformations (ex. `test_03` teste `compute_label`/`aggregate_per_cell`).
- **Prior art** : `test_01_nettoyage_jointure`, `test_03_labels_entrainement`, `test_05_feature_engineering`, `test_06_table_entrainement_unifiee` — mêmes helpers (`_make_survey_df`, `_make_group`).
- **Modules testés** :
  - 01 : `snap_to_grid` (un point tombe dans la bonne cellule 1 km), `clip_to_aire` (points hors polygones exclus).
  - 03 : `compute_severite` (cas canoniques 0/1/2/3, NaN ≠ zéro, phase max), `aggregate_per_cell` (plusieurs relevés → max), `derive_binary`.
  - 05 : `compute_pop` (bande 50–125, persistance multi-mois), `build_lags` (aucune fuite T+1, décalages corrects).
  - 06 : `assemble_table` (jointure features/labels, colonnes attendues).
  - 07/08 : `walk_forward_split` (folds chronologiques, 2023-2024 absent, pas de chevauchement train/test dans le temps), `select_robust` (départage rappel→variance→simplicité sur métriques synthétiques).
  - 09 : `to_severity_map` (agrégation décade→mois correcte), `derive_binary`.
- **Hors test unitaire** : la qualité prédictive réelle (valeurs d'AUC/QWK) se mesure via le rapport 10 sur données réelles, pas en pytest.

## Out of Scope

- Les volets **OS1 (socio-politique)** et **OS2 (financement hybride)** de la thèse.
- Le **tableau de bord interactif** (phase ultérieure) ; ce PRD livre cartes PNG + exports SIG + rapport.
- La **modélisation de la densité/abondance** comme cible primaire (reste une couche optionnelle dégradable).
- L'**échelle 0–6 Annexe 8** et la **grille 5 km** (abandonnées).
- Le traitement spécifique de l'**AGT** (transitoire) : disponible comme `AIRE_CODE`, pas de modèle séparé pour l'instant.
- La suppression effective de `model_2/` (à faire dans un ticket de nettoyage distinct).

## Further Notes

- **Fidélité thèse** : le binaire dérivé + AUC préservent l'exigence §31/§33 ; RF reste dans le panel comme référence. Déviations assumées et tracées : périmètre élargi (ADR 0003), cible ordinale (ADR 0001), benchmark vs RF imposé (ADR 0005).
- **POP** = descripteur écologique dérivé (50–125 mm/mois + persistance), pas la pluie brute ; hérite du support CHIRPS ~5 km, attaché aux cellules 1 km — le déterminant pluviométrique est **temporel/régional**, ce qui ne tire pas vers une maille 5 km.
- **Parcimonie spatiale** : ~1,5 % des cellules-décades sont observées (stations vues ~1 fois) → le modèle généralise via les covariables environnementales, ce qui valide l'approche télédétection.
- **Biais d'effort** de prospection (croissant dans le temps) : affecte l'échantillonnage, pas le label conditionnel.
- Décisions complètes : `docs/adr/0001`→`0005` et glossaire `CONTEXT.md`.
