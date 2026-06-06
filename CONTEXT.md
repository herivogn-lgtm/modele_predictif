# Modélisation Spatio-Temporelle du Criquet Migrateur Malagasy

Système de prédiction de la dynamique du criquet migrateur (*Locusta migratoria capito*) dans l'aire grégarigène de Madagascar, visant à orienter les prospections acridiennes pour rationaliser les ressources de surveillance.

## Language

### Espèce et territoire

**Criquet migrateur malagasy** :
*Locusta migratoria capito* — sous-espèce endémique de Madagascar, espèce cible du système.
_Avoid_ : criquet, locuste, acridien (trop génériques)

**Aire grégarigène** :
Zone géographique du Sud et Sud-Ouest de Madagascar où les criquets se concentrent et forment des essaims. Délimitée par le shapefile `aire_gregarigene/` (12 polygones).
_Avoid_ : zone d'étude, habitat

**Acrido-région** :
Subdivision spatiale de l'aire grégarigène utilisée comme unité de surveillance de terrain. Correspond aux entités du shapefile `aire_gregarigene/` (champ `AIRE_NOM` / `AIRE_CODE`).
_Avoid_ : zone, région, secteur

### Données

**Relevé acridien** :
Observation de terrain enregistrée dans `2001_2026_Acrido_vf.xls`, couvrant 2001–2026 avec des lacunes complètes en 2023–2024 et des données partielles en 2022 et 2025.
_Avoid_ : donnée, observation

**Variables environnementales** :
Covariables extraites de Google Earth Engine (pluviométrie, humidité des sols, température, occupation du sol / couverture végétale) utilisées comme prédicteurs du modèle.
_Avoid_ : données GEE, features climatiques

### Modèle

**Modèle hiérarchique** :
Architecture de prédiction en trois étapes séquentielles et dépendantes : (1) présence/absence, (2) densité conditionnelle à la présence, (3) phase conditionnelle à la présence. Une sortie nulle à l'étape 1 court-circuite les étapes suivantes.
_Avoid_ : modèle multi-sortie, modèle combiné

**Présence/absence** :
Étape 1 du modèle hiérarchique. Classification binaire : le criquet est-il observable dans une unité spatio-temporelle donnée ? Métrique cible : AUC > 0,85.
_Avoid_ : détection, occurrence

**Densité** :
Étape 2 du modèle hiérarchique, conditionnelle à la présence. Variable continue représentant l'abondance des criquets (unité à préciser selon les relevés). Métrique cible : RMSE ou MAE.
_Avoid_ : abondance, nombre

**Phase acridienne** :
Étape 3 du modèle hiérarchique, conditionnelle à la présence. Classification de l'état comportemental du criquet : solitaire ou grégaire. Métrique cible : F1-macro.
_Avoid_ : état, comportement, forme

**Cible acridienne** :
Population de transiens congregans dont la densité approche le seuil de grégarisation (~1 500–2 500 imagos/ha pour LMC). Correspond aux niveaux de risque 3–4 sur l'échelle du SIG. C'est le signal précoce qui justifie une intervention préventive — pas la présence de grégaires, qui indique une situation déjà critique.
_Avoid_ : zone cible, zone à prospecter, présence de criquets

**Niveau de risque acridien** :
Indice synthétique 0–4 par polygone calculé par le SIG-LMC du CNA, croisant le potentiel acridien (phase × densité × stade) et le potentiel écologique (biotope × pluviométrie). 0 = absence, 1–2 = risque faible/moyen, 3–4 = risque sérieux de grégarisation. Variable cible principale du modèle pour l'usage opérationnel.
_Avoid_ : score de risque, indice acridien

**Transiens congregans** :
Population de criquets en phase de transition grégarigène, comportant un comportement grégaire (grégarigeste) mais une morphologie encore intermédiaire (transitiforme), à densité moyenne à forte. Signal précoce d'alerte, cible de la lutte préventive.
_Avoid_ : transiens (seul, ambigu — inclut aussi les transiens degregans)

**Niveau de grégarité (simplifié)** :
Classification à 4 niveaux dérivée des comptages terrain `Sol`, `Trans`, `Greg` : **absent** (total=0), **S** (solitaires, Trans=0), **St** (solitaro-transiens, 0 < Trans < Sol), **T** (transiens dominant, Trans ≥ Sol, Greg=0), **G** (grégaires, Greg > 0). Les sous-niveaux T1/T2/T3 du manuel ne sont pas distingués sur le terrain — les prospecteurs notent uniquement "transiens". T est mappé sur T1 (valeur conservatrice) dans la matrice Annexe 8.
_Avoid_ : T1, T2, T3 (non observés dans les données)

**Seuil de grégarisation** :
Densité à partir de laquelle la transformation phasaire vers le grégaire est déclenchée : ~1 500 à 2 500 imagos/ha pour LMC. Au-delà, une intervention curative (et non plus préventive) devient nécessaire.
_Avoid_ : seuil de densité

**Contexte acridien** :
Situation globale de la dynamique acridienne à un instant donné : rémission, pseudo-rémission, résurgence, recrudescence, pré-invasion ou invasion. Détermine la stratégie de lutte applicable. Le modèle vise à maintenir le contexte en rémission via détection précoce.
_Avoid_ : situation acridienne, état acridien

### Architecture ML

**Déséquilibre de classes** :
La classe grégaire représente 5,8% des observations — la plus rare mais la plus critique. Correction simultanée par trois leviers : (1) `scale_pos_weight` dans LightGBM à l'entraînement, (2) seuil de décision abaissé (~0,15–0,20) pour maximiser le rappel sur la classe grégaire, (3) optimisation sur F1-macro ou rappel-grégaire plutôt que sur AUC globale. L'AUC > 0,85 de la fiche projet s'applique à l'étape 1 (présence/absence), pas à la classification de phase.
_Avoid_ : accuracy, AUC comme métrique unique pour la phase

**Effort de prospection** :
Nombre de visites terrain effectuées dans une région naturelle pour une décade donnée. Utilisé comme feature d'entrée du modèle pour corriger le biais de détection (les équipes prospectent là où elles espèrent trouver des criquets, créant des faux zéros dans les zones sous-prospectées).
_Avoid_ : intensité de surveillance, couverture terrain

**Absence vérifiée** :
Observation terrain explicite où Sol=Trans=Greg=0 sur une ligne de prospection datée et géoréférencée. Seul type d'absence utilisable comme label 0. Les régions×décades sans aucune ligne de prospection sont masquées (label inconnu, pas 0).
_Avoid_ : absence, zéro (ambigus sans précision)

**Périmètre espèce** :
Le modèle cible exclusivement *Locusta migratoria capito* (LMC). Les colonnes `_NSE` (*Nomadacris septemfasciata*) du fichier XLS sont ignorées — elles ne constituent ni variable cible ni feature d'entrée.
_Avoid_ : NSE, criquet nomade (hors périmètre)

**Campagne acridienne** :
Période opérationnelle annuelle de surveillance et de lutte antiacridienne à Madagascar, couvrant **octobre à juillet** (10 mois). Unité temporelle de base pour la validation walk-forward et pour la prédiction saisonnière. Une campagne enjambe deux années civiles (ex. campagne 2001-2002 = oct 2001 – juil 2002). La prédiction saisonnière est produite en **septembre** avant le démarrage de la campagne.
_Avoid_ : année, saison des pluies (trop court — couvre seulement nov–avril)

**Lacunes de données** :
Campagnes 2023–2024 : labels terrain absents — exclus de l'entraînement, utilisés uniquement en inférence (les features GEE existent). Campagnes 2022 et 2025 : observations partielles conservées, décades manquantes masquées. Pas d'imputation des labels terrain manquants — évite la circularité d'entraîner sur des labels auto-générés.
_Avoid_ : interpolation des absences, imputation des cibles

**Stack modèle** :
Exécutable sur CPU standard, sans GPU. Trois niveaux : (1) LightGBM/XGBoost comme baseline obligatoire — robuste, rapide, interprétable ; (2) NeuralProphet comme composante temporelle multi-horizon — conçu pour la saisonnalité et les lacunes, CPU natif ; (3) LSTM léger (PyTorch CPU) optionnel si les deux précédents sont insuffisants. Les architectures gourmandes (ConvLSTM, GAT-LSTM, TFT complet) sont explicitement hors périmètre.
_Avoid_ : deep learning lourd, CNN, GPU-only

### Sorties du modèle (architecture C)

**Sortie opérationnelle** :
Niveau de risque acridien 0–4 prédit par polygone et par période, utilisé directement pour orienter les prospections et la programmation des interventions. Produite à trois horizons temporels : décadaire (où envoyer les équipes dans les 10 prochains jours), mensuel (bulletin CNA et planification mensuelle), saisonnier (budget et logistique de campagne).
_Avoid_ : score, prédiction principale

**Région naturelle** :
Unité spatiale de modélisation — l'un des 90 polygones du shapefile `region_naturelle/`, constituant le maillage éco-géographique de référence du SIG-LMC. Les prédictions sont produites à ce niveau, puis agrégées à l'acrido-région pour la décision opérationnelle.
_Avoid_ : pixel, maille, zone

**Sorties analytiques** :
Trois variables prédites séparément par le modèle hiérarchique : présence/absence (AUC), densité conditionnelle à la présence (RMSE/MAE), phase dominante conditionnelle à la présence (F1-macro). Utilisées pour l'analyse scientifique et la validation du modèle.
_Avoid_ : variables secondaires
