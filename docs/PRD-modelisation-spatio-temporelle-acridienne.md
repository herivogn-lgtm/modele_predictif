# PRD — Modélisation Spatio-Temporelle du Risque Acridien à Madagascar

**Statut** : ready-for-agent  
**Date** : 2026-06-06  
**Espèce cible** : *Locusta migratoria capito* (LMC)  
**Référence glossaire** : `CONTEXT.md`  
**Décisions architecturales** : `docs/adr/0001-architecture-double-sortie.md`, `docs/adr/0002-contrainte-cpu-uniquement.md`

---

## Problem Statement

Le système de surveillance antiacridienne à Madagascar (CNA/IFVM) opère aujourd'hui dans une logique réactive : les équipes de terrain prospectent l'aire grégarigène sans savoir à l'avance où se trouvent les populations à risque. Cette approche dilapide des ressources humaines, logistiques et financières limitées — des prospections sont conduites dans des zones vides pendant que des foyers de transiens congregans passent inaperçus.

Les données historiques de terrain (2001–2026, 29 706 relevés géoréférencés) et les données satellitaires disponibles via Google Earth Engine ne sont pas exploitées pour anticiper les zones à risque. Aucun modèle prédictif opérationnel n'existe à Madagascar pour *Locusta migratoria capito*. Cette absence maintient le dispositif dans une dépendance aux interventions curatives massives, coûteuses et tardives.

---

## Solution

Développer un système de prédiction spatio-temporelle du risque acridien, fonctionnant sur CPU standard, qui produit pour chaque région naturelle de l'aire grégarigène une carte de risque à trois horizons temporels (décadaire, mensuel, saisonnier). Le système oriente les prospections vers les zones où la probabilité de trouver des transiens congregans est suffisamment élevée pour justifier l'envoi d'une équipe — sans prospections "à l'aveugle".

Le système produit deux types de sorties complémentaires (voir ADR-0001) :
1. **Sortie opérationnelle** : niveau de risque acridien 0–4 par région naturelle, agrégé à l'acrido-région pour les décisions terrain
2. **Sorties analytiques** : modèle hiérarchique présence/absence → densité → phase dominante, pour la recherche scientifique

---

## User Stories

### Opérationnel terrain (Chef de Zone Antiacridienne / Chef de PA)

1. En tant que chef de ZA, je veux recevoir chaque mois une carte de risque 0–4 par acrido-région pour la campagne en cours, afin de prioriser l'affectation de mes équipes de prospecteurs.
2. En tant que chef de PA, je veux consulter une prédiction décadaire du risque par région naturelle, afin de planifier les itinéraires de prospection des 10 prochains jours.
3. En tant que chef de ZA, je veux que la carte distingue clairement les zones à risque 3–4 (transiens congregans probables) des zones à risque 1–2 (solitaires), afin d'orienter en priorité mes moyens sur les foyers potentiels.
4. En tant que responsable logistique, je veux une prédiction saisonnière produite en septembre avant le démarrage de la campagne (octobre), afin de planifier les budgets, le carburant et les intrants de lutte pour les 10 mois à venir.
5. En tant que chef de ZA, je veux savoir dans quelle mesure une zone a été prospectée récemment, afin d'interpréter correctement une prédiction de risque faible (zone bien surveillée vs zone non visitée).

### Scientifique / Analyste (Chercheur, Direction IFVM)

6. En tant que chercheur, je veux accéder aux prédictions de présence/absence, de densité et de phase dominante séparément, afin d'analyser les déterminants biologiques de la grégarisation.
7. En tant qu'analyste, je veux que le modèle atteigne une AUC > 0,85 sur la tâche présence/absence, afin de valider sa performance selon les standards internationaux.
8. En tant que chercheur, je veux que la performance sur la classe grégaire soit évaluée par le rappel et le F1-macro, afin de ne pas masquer les limites du modèle sur la classe la plus critique.
9. En tant que directeur de l'IFVM, je veux visualiser la performance du modèle par campagne historique (walk-forward), afin d'évaluer sa fiabilité sur des données jamais vues à l'entraînement.
10. En tant que chercheur, je veux pouvoir comparer les prédictions du modèle avec les cartes de risque du SIG-LMC existant, afin de démontrer l'apport de l'approche ML.

### Gestion des données

11. En tant que data engineer, je veux extraire automatiquement les statistiques zonales GEE (CHIRPS, MODIS NDVI/EVI, ERA5, LST) par région naturelle et par décade, afin d'alimenter le modèle sans intervention manuelle.
12. En tant que data engineer, je veux qu'une région naturelle × décade sans aucun relevé terrain soit masquée (label inconnu) plutôt que traitée comme une absence, afin d'éviter d'entraîner le modèle sur de faux zéros.
13. En tant que data engineer, je veux que le nombre de prospections par région naturelle et par décade soit calculé et inclus comme feature d'effort de prospection, afin de corriger le biais de détection dans le modèle.
14. En tant que data engineer, je veux que les campagnes 2023–2024 soient exclues des labels d'entraînement mais que leurs features GEE soient conservées pour l'inférence, afin de ne pas introduire de circularité dans les labels.
15. En tant que data engineer, je veux nettoyer les coordonnées GPS aberrantes (latitude ou longitude hors de la plage Madagascar) avant la jointure spatiale avec les régions naturelles, afin d'éviter des erreurs d'attribution géographique.
16. En tant que data engineer, je veux calculer le compteur de mois consécutifs dans la Plage d'Optimum Pluviométrique (POP : 50–125 mm/mois) à partir de CHIRPS, afin d'encoder le facteur de risque de grégarisation le plus prédictif identifié dans la littérature.

### Modélisation

17. En tant que modélisateur, je veux entraîner un modèle LightGBM baseline sur les features GEE ingénierées + lags temporels, afin d'établir une référence de performance interprétable avant de tester des architectures plus complexes.
18. En tant que modélisateur, je veux utiliser `scale_pos_weight` dans LightGBM et un seuil de décision abaissé (~0,15–0,20) pour la classe grégaire, afin de maximiser le rappel sur la classe la plus critique au détriment acceptable de la précision.
19. En tant que modélisateur, je veux valider le modèle avec une stratégie walk-forward par campagne entière (jamais de split aléatoire), afin d'évaluer la généralisation temporelle qui est l'usage réel du système.
20. En tant que modélisateur, je veux reconstruire le niveau de risque 0–4 depuis les colonnes terrain (Sol, Trans, Greg, DI_dif_moy, DL_dif_moy) via la matrice Annexe 8 du Manuel, afin de disposer d'une variable cible cohérente avec le SIG-LMC existant.
21. En tant que modélisateur, je veux que les prédictions soient produites à l'échelle des 90 régions naturelles puis agrégées en 12 acrido-régions pour la sortie opérationnelle, afin de reproduire le flux du SIG-LMC existant.

---

## Implementation Decisions

### Pipeline de données

- **Source terrain** : `data/2001_2026_Acrido_vf.xls`, feuille `2001_2025_AA`. Colonnes LMC uniquement — les colonnes suffixées `_NSE` (*Nomadacris septemfasciata*) sont ignorées.
- **Jointure spatiale** : chaque relevé (point GPS `LAT_DD`, `LNG_DD`) est affecté à sa région naturelle par jointure spatiale avec `data/region_naturelle/region_naturelle.shp`. Les coordonnées hors plage Madagascar sont écartées avant la jointure.
- **Agrégation temporelle** : par décade (`Decade`) et par région naturelle. L'unité temporelle de base est la **décade de campagne** (campagne = octobre à juillet, soit ~30 décades par campagne).
- **Label de présence** : présence = Sol + Trans + Greg > 0 sur au moins une ligne de la région × décade. Absence vérifiée = toutes les lignes de la région × décade ont Sol=Trans=Greg=0. Région × décade sans aucune ligne = label masqué.

### Reconstruction du niveau de grégarité (label cible)

```
# Niveau de grégarité simplifié depuis les comptages terrain
total = Sol + Trans + Greg (adultes)
if total == 0          → absent
elif Greg > 0          → G  (grégaire)
elif Trans >= Sol > 0  → T  (transiens dominant, mappé sur T1 dans Annexe 8)
elif Trans > 0         → St (solitaro-transiens)
else                   → S  (solitaire)

# Densité totale équivalent imago (ind/ha)
densite = DI_dif_moy + DL_dif_moy / 9
# (9 petites larves = 1 imago, Manuel p.52)
```

Le potentiel acridien (0–5) est déduit de la matrice Annexe 8 (densité × niveau de grégarité). Le niveau de risque final (0–5) est obtenu en croisant potentiel acridien avec le potentiel écologique, appris implicitement par le modèle depuis les features GEE.

### Features environnementales (GEE)

| Feature | Source | Résolution | Type |
|---|---|---|---|
| Cumul pluviométrique décadaire | CHIRPS | 0,05° | Dynamique |
| Anomalie pluviométrique vs historique | CHIRPS | 0,05° | Dynamique |
| **POP consécutifs** (mois en [50–125mm]) | CHIRPS calculé | — | Engineered |
| NDVI moyen par région | MODIS MOD13A2 | 250m / 16j | Dynamique |
| EVI moyen par région | MODIS MOD13A2 | 250m / 16j | Dynamique |
| Humidité du sol | ERA5 | 0,25° | Dynamique |
| LST (température de surface) | MODIS MOD11A2 | 1km / 8j | Dynamique |
| ENSO / ONI | NOAA (externe) | Mensuel | Dynamique |
| Occupation du sol | MODIS MCD12Q1 | 500m / annuel | Semi-statique |
| Texture du sol | SoilGrids via GEE | 250m | Statique |
| Altitude (DEM) | SRTM | 30m | Statique |
| **Effort de prospection** | Calculé depuis XLS | Par région×décade | Engineered |

Toutes les features dynamiques sont agrégées par statistique zonale (moyenne, min, max, écart-type) sur chaque polygone de région naturelle.

### Architecture ML (voir ADR-0002)

- **Phase 1** : LightGBM avec features GEE ingénierées + lags temporels (décade-1, décade-2, mois précédent). Entraînement CPU, < 5 min.
- **Phase 2** : NeuralProphet pour la prédiction multi-horizon (décadaire/mensuel/saisonnier en une passe). CPU natif.
- **Phase 3** (conditionnelle à AUC < 0,80) : LSTM léger PyTorch sur CPU.
- Correction du déséquilibre de classes : `scale_pos_weight` LightGBM + seuil de décision ~0,15–0,20 pour la classe grégaire + optimisation sur F1-macro.

### Validation

- **Walk-forward par campagne** : entraîner sur campagnes 2001–02 à 2015–16, tester sur 2016–17 à 2021–22, valider sur 2025–26.
- **Leave-one-campaign-out** : pour le tuning des hyperparamètres.
- **Pas de split aléatoire** — data leakage sur séries temporelles.
- Campagnes 2023–24 : exclues des labels (features GEE disponibles pour inférence uniquement).

---

## Testing Decisions

### Ce qui constitue un bon test

Tester le comportement observable depuis l'extérieur du module, pas les détails d'implémentation internes. Un test utile vérifie qu'un input donné produit le bon output — pas que telle fonction interne est appelée de telle façon.

### Modules à tester

| Module | Type de test | Ce qu'on teste |
|---|---|---|
| Reconstruction du niveau de grégarité | Unitaire | La matrice S/St/T/G × densité → potentiel acridien produit les valeurs attendues de l'Annexe 8 |
| Feature POP consécutifs | Unitaire | Séquences de pluviométrie connues → compteur correct (ex. 3 mois consécutifs en POP → 3) |
| Jointure spatiale GPS → région naturelle | Intégration | Un point GPS connu retourne la bonne région naturelle |
| Masquage des labels inconnus | Unitaire | Une région×décade sans ligne de prospection retourne label=None, pas 0 |
| Effort de prospection | Unitaire | Le comptage de lignes par région×décade est exact sur un sous-ensemble connu |
| Pipeline GEE → feature table | Intégration | L'extraction sur une région naturelle et une décade retourne des valeurs dans les plages attendues |
| Modèle présence/absence | Performance | AUC > 0,85 sur le fold de validation walk-forward |
| Modèle phase | Performance | Rappel sur classe grégaire > 0,70 sur le fold de validation |

---

## Out of Scope

- *Nomadacris septemfasciata* (NSE) — hors périmètre, focus exclusif LMC.
- Modélisation des déplacements migratoires (voies de déplacement Lecoq 1979) — les corridors sont utilisés comme contexte conceptuel, pas modélisés explicitement.
- Architectures GPU (ConvLSTM, GAT-LSTM, TFT complet) — voir ADR-0002.
- Interface utilisateur / dashboard de visualisation — production de fichiers de sortie (CSV, GeoJSON) suffisante pour cette phase.
- Reconstruction rétrospective du potentiel écologique depuis les archives du SIG-LMC — le potentiel écologique est appris implicitement par le modèle depuis les features GEE.
- Données Sentinel-2 comme variable principale — disponible seulement depuis 2017, couvrant 8 ans sur 25 ans de données d'entraînement.
- Modélisation de *Nomadacris septemfasciata* ou des acridiens secondaires (tsaboroty).

---

## Further Notes

- **Référence théorique centrale** : Manuel de lutte préventive antiacridienne (Duranton et al., 2009) — en particulier Tableau XVII (contextes acridiens), Annexe 8 (matrice potentiel acridien), et Tableau XVIII (classes pluviométriques POP).
- **Thèse de référence** : Nicolas RANDRIANARIJAONA (2026) — cadre méthodologique et revue de littérature sur les variables environnementales pertinentes pour LMC.
- **Seuil de grégarisation LMC** : ~1 500–2 500 imagos/ha. Les populations dépassant ce seuil requièrent une lutte curative, pas préventive — l'objectif du modèle est la détection *avant* ce seuil.
- **Biais de détection** : les équipes prospectent là où elles espèrent trouver des criquets. La feature "effort de prospection" corrige ce biais mais ne l'élimine pas — interpréter les prédictions dans les zones historiquement peu prospectées avec prudence.
- **Coordonnées aberrantes** dans `2001_2026_Acrido_vf.xls` : certaines valeurs `LAT_DD`/`LNG_DD` sont hors plage Madagascar (ex. LAT_DD = -2 210 452). À identifier et corriger ou exclure avant toute jointure spatiale.
- **Campagne acridienne** : octobre à juillet (10 mois). La prédiction saisonnière est produite en septembre, avant le démarrage de la campagne.
