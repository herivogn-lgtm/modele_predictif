# Modélisation Spatio-Temporelle du Criquet Migrateur Malagasy (OS3)

Volet technique (Objectif Spécifique 3) de la thèse de N. RANDRIANARIJAONA :
développer et tester un modèle prédictif spatio-temporel, fondé sur la télédétection
et des données environnementales, pour améliorer la **détection précoce des zones à
risque acridien** dans l'**aire grégarigène** de Madagascar, afin de cibler les
prospections et réduire les coûts de surveillance.

> Périmètre élargi par rapport à la thèse §31 (qui restreignait au Sud-Ouest :
> Betioky/Soalara/Mikea). Décision projet : couvrir **toute l'aire grégarigène**
> telle que délimitée par `data/aire_gregarigene/` (les 4 aires complémentaires).

## Language

### Espèce et territoire

**Criquet migrateur malagasy** :
*Locusta migratoria capito* — sous-espèce endémique de Madagascar, espèce cible du système.
_Avoid_ : criquet, locuste, acridien (trop génériques)

**Aire grégarigène** :
Zone d'étude du modèle = **toute** l'aire grégarigène du Criquet migrateur malgache,
délimitée par le shapefile `data/aire_gregarigene/` : **12 polygones / 12 secteurs**
regroupés en **4 aires complémentaires**, ≈ 181 414 ha (~1 814 km²), Sud / Sud-Ouest
(lat −25,6 à −20,0 ; lon 43,2 à 47,4), polygones **fragmentés**. C'est l'emprise de
modélisation (grille 1 km **à l'intérieur des polygones** uniquement, ~1 800 cellules).
**Clip strict** : entraînement et prédiction partagent cette emprise ; les relevés
hors polygones (16 %) sont écartés. Voir [ADR 0003](docs/adr/0003-emprise-aire-gregarigene-clip-strict.md).
_Avoid_ : zone d'étude, habitat, « Sud-Ouest seul » (la thèse §31 restreignait, pas nous)

**Aires complémentaires (AMI / ATM / AD / AGT)** :
Compartimentation opérationnelle de l'aire grégarigène (Manuel de lutte préventive) :
- **AMI** — aire de multiplication initiale (démarrage de la reproduction) ;
- **ATM** — aire transitoire de multiplication (plaines Androka, Befandriana Sud, Manombo) ;
- **AD** — aire de densation (concentration des populations) ;
- **AGT** — aire grégarigène transitoire (ajoutée en 1996, au nord ; 1ʳᵉ zone colonisée
  au démarrage d'une invasion : Zomandao, Makay, Morondava).
AD/ATM/AMI permettent d'enchaîner trois reproductions en saison des pluies. Champ
`AIRE_CODE` du shapefile (1=AGT, 2=AMI, 3=ATM, 4=AD), chaque aire subdivisée en secteurs.
_Avoid_ : zones, régions (réservés à d'autres entités)

### Données

**Relevé acridien** :
Observation de terrain issue des dispositifs de l'IFVM, enregistrée dans
`2001_2026_Acrido_vf.xls` (29 706 relevés, 2001–2026, **lacune totale 2023-2024**).
Sert à construire la **cible** (sévérité-phase). Un relevé à zéro partout est une **vraie
absence** (prospection effectuée, rien trouvé) : ~31 % des relevés. Stations très éparses
(médiane 1 relevé/station). Voir [ADR 0004](docs/adr/0004-fenetre-entrainement-complete.md).
_Avoid_ : donnée, observation

**Variables environnementales** :
Covariables prédictives issues de la télédétection : NDVI/EVI (MODIS, Sentinel-2),
température de surface LST (MODIS), pluviométrie (CHIRPS), et l'indice climatique
ENSO (NOAA) comme proxy des anomalies pluviométriques.
_Avoid_ : données GEE, features climatiques

**POP — Plage d'Optimum Pluviométrique** :
Descripteur écologique dérivé de la pluviométrie mensuelle (CHIRPS), et non la pluie
brute. Le développement du criquet est optimal quand la **pluie mensuelle est comprise
entre 50 et 125 mm** (incubation des oothèques + disponibilité de végétation herbacée) ;
la **répétition de cette plage sur plusieurs mois consécutifs** accroît fortement le
risque de grégarisation (thèse §006, §013). POP est donc une feature à deux dimensions :
appartenance à la bande [50,125] mm et persistance multi-mois.
_Avoid_ : pluie, CHIRPS brut, « plus il pleut mieux c'est »

### Modèle

**Sévérité-phase** :
Variable cible primaire du modèle. Niveau ordinal 0–3 attribué à une cellule × décade
selon la **phase maximale** observée : 0 = absence, 1 = solitaire, 2 = transiens,
3 = grégaire. Mesure le *risque* (qualité comportementale du danger), pas la simple
occurrence. Validation par **QWK** (ordinal). Voir [ADR 0001](docs/adr/0001-cible-ordinale-severite-phase.md).
_Avoid_ : présence/absence (c'est le dérivé binaire, pas la cible), score 0–6, gravité

**Présence dérivée** :
Réduction binaire de la sévérité-phase (niveau ≥ 1). Conservée pour la validation
**AUC** et la fidélité à l'OS3 de la thèse (§31, §33). N'est pas la cible primaire.
_Avoid_ : détection, occurrence

**Intensité** :
Couche optionnelle et dégradable estimant l'abondance (`log(densité)`, `DL_*`/`DI_*`)
là où elle est renseignée. Enrichit la sévérité-phase sans jamais la bloquer ; ~35 %
des relevés n'ont pas de densité exploitable.
_Avoid_ : densité brute, gravité

**Forecast T+1** :
Horizon du modèle : on prédit la sévérité-phase de la **décade suivante (T+1)** à partir
de covariables **passées** (lags), jamais de la décade courante. S'oppose au *nowcast*
(estimation de la décade courante, simple complétion spatiale). Voir
[ADR 0002](docs/adr/0002-forecast-decade-t-plus-1.md).
_Avoid_ : prédiction, temps réel, nowcast (c'est l'autre mode, pas le nôtre)
