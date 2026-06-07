# Guide d'interprétation des sorties opérationnelles — Niveau de risque acridien 0–4

**Audience** : Chef de Zone Antiacridienne (CNA), Chef de Poste d'Alerte, responsable logistique  
**Fichiers concernés** : `data/processed/09_sorties_decadaire.csv`, `09_sorties_mensuelle.csv`, `09_sorties_saisonniere.csv` et leurs équivalents GeoJSON

---

## 1. L'échelle de risque acridien 0–4

Le système produit un niveau de risque entier entre 0 et 4 pour chaque acrido-région et chaque période. Ce niveau correspond au potentiel acridien observé ou prédit, aligné sur l'échelle utilisée par le SIG-LMC.

| Niveau | Signification | Phase correspondante | Action recommandée |
|--------|---------------|----------------------|-------------------|
| **0** | Absence de *Locusta migratoria capito* — aucun criquet détecté | — | Aucune prospection prioritaire dans ce secteur |
| **1** | Solitaires présents, densités très faibles (< 10 ind/ha) | S (solitaires) | Surveillance de routine ; noter dans le registre de campagne |
| **2** | Solitaro-transiens, densités modérées (10–500 ind/ha) | St (transition) | Prospections de confirmation dans les régions naturelles concernées |
| **3** | Transiens congregans probables — **cible prioritaire de la lutte préventive** | T (transiens) | **Envoi d'équipe de terrain en priorité dans la décade** |
| **4** | Grégaires présents ou densités critiques (> 1 500 ind/ha) — intervention urgente | G (grégaires) | **Lutte curative immédiate — alerter la hiérarchie** |

Les niveaux 3 et 4 correspondent aux *transiens congregans* atteignant ou dépassant le seuil de grégarisation de *Locusta migratoria capito* (~1 500–2 500 imagos/ha). Ces phases constituent les cibles de la lutte préventive telle que définie dans le Manuel de lutte préventive.

---

## 2. Les trois horizons temporels

Le système produit des prédictions à trois horizons, chacun adapté à un type de décision différent :

| Horizon | Fichier | Unité temporelle | Usage CNA recommandé |
|---------|---------|------------------|----------------------|
| **Décadaire** | `09_sorties_decadaire.csv` | Décade de campagne (10 jours) | Planification des itinéraires de prospection à 10 jours ; affectation d'équipes mobiles |
| **Mensuel** | `09_sorties_mensuelle.csv` | Mois de campagne (1 mois) | Bulletin mensuel CNA ; décisions de déploiement logistique |
| **Saisonnier** | `09_sorties_saisonniere.csv` | Campagne complète (oct–jul) | Budget avant démarrage de campagne (à produire en septembre) ; planification des ressources annuelles |

---

## 3. Lecture d'une ligne de sortie décadaire

Exemple de ligne CSV décadaire :

```
SECT_NO=3, AIRE_NOM="Ihosy", campagne_calc="2024-2025", campagne_decade=15,
niveau_risque_max=3, phase_dominante="T", n_regions=8, n_regions_risque_eleve=2,
n_regions_effort_bas=3, faible_couverture=False, risque_eleve=1
```

**Interprétation** :
- **Secteur** : acrido-région Ihosy (secteur n°3)
- **Période** : décade 15 de la campagne 2024-2025, soit la **3e décade de mars 2025** (voir tableau de correspondance section 5)
- **Risque** : niveau maximum **3** (transiens probables) — envoi d'équipe terrain recommandé
- **Détail** : 2 régions naturelles sur les 8 du secteur montrent un risque élevé (≥ 3)
- **Effort** : 3 régions sur 8 ont un effort de prospection faible — mais la majorité du secteur est couverte (`faible_couverture=False`)
- **Signal d'alerte** : `risque_eleve=1` indique que le seuil de déclenchement est atteint

### Description de chaque champ

| Champ | Description |
|-------|-------------|
| `SECT_NO` | Numéro du secteur (1–12) |
| `SECT_NOM` | Nom du secteur |
| `AIRE_CODE`, `AIRE_NOM` | Code et nom de l'acrido-région |
| `campagne_calc` | Campagne au format `"YYYY-YYYY+1"` |
| `campagne_decade` | Position de la décade dans la campagne (1–30) |
| `mois_campagne` | Mois dans la campagne (1–10, mensuel et saisonnier uniquement) |
| `niveau_risque_max` | Niveau de risque maximal parmi les régions naturelles du secteur (0–4) |
| `phase_dominante` | Phase acridienne la plus fréquente parmi les régions avec présence prédite |
| `n_regions` | Nombre total de régions naturelles dans le secteur |
| `n_regions_risque_eleve` | Nombre de régions avec `niveau_risque ≥ 3` |
| `n_regions_effort_bas` | Nombre de régions avec peu de relevés terrain (effort ≤ 1 relevé/décade) |
| `faible_couverture` | `True` si la majorité des régions du secteur ont un effort faible |
| `risque_eleve` | 1 si `niveau_risque_max ≥ 3`, sinon 0 — indicateur binaire d'alerte |

---

## 4. Interprétation du flag `faible_couverture`

Le flag `faible_couverture = True` signale que la majorité des régions naturelles du secteur ont été **peu prospectées** (`effort_prospection ≤ 1 relevé par décade`).

**Signification pour l'interprétation du risque** :

Une prédiction de **risque faible** (niveau 0 ou 1) dans un secteur avec `faible_couverture = True` doit être interprétée avec précaution. Le modèle prédit à partir des variables environnementales (pluies, végétation, température), mais sans données terrain récentes pour valider ou invalider sa prédiction.

**Règle de précaution** : Pour les secteurs avec `faible_couverture = True` et `niveau_risque_max ≤ 1`, considérer le risque réel comme **+1 niveau** (ex. risque 0 → traiter comme risque 1 ; risque 1 → traiter comme risque 2) jusqu'à ce qu'une prospection terrain confirme ou infirme.

Ce biais est inhérent aux données de surveillance acridienne : les zones isolées ou difficiles d'accès ont historiquement moins de relevés, ce qui crée une corrélation artificielle entre "peu prospectée" et "absence apparente".

---

## 5. Correspondance décade de campagne ↔ date calendaire

| Décades de campagne | Mois de campagne | Mois calendaire | Période |
|--------------------|-----------------|-----------------|---------|
| 1, 2, 3 | 1 | Octobre (année YYYY) | Début de campagne — saison sèche tardive |
| 4, 5, 6 | 2 | Novembre | Premières pluies |
| 7, 8, 9 | 3 | Décembre | Pleine saison des pluies |
| 10, 11, 12 | 4 | Janvier (année YYYY+1) | Pic de pluies |
| 13, 14, 15 | 5 | Février | Forte végétation |
| 16, 17, 18 | 6 | Mars | Transition |
| 19, 20, 21 | 7 | Avril | Début saison sèche |
| 22, 23, 24 | 8 | Mai | Saison sèche |
| 25, 26, 27 | 9 | Juin | Saison sèche avancée |
| 28, 29, 30 | 10 | Juillet | Fin de campagne |

**Exemple** : `campagne_decade=15` de la campagne `"2024-2025"` correspond à la 3e décade de **février 2025** (jours 21–28 ou 21–29 selon l'année).

---

## 6. Limites du modèle et précautions

### Zones peu prospectées historiquement

Le modèle a été entraîné sur les données de prospection de 2001 à 2022. Les régions naturelles qui n'ont jamais ou rarement été prospectées ont moins influencé l'apprentissage. Dans ces zones, les prédictions reposent essentiellement sur les variables environnementales (précipitations, végétation) sans ancrage terrain.

### Campagnes 2023-2024 — inférence uniquement

La campagne "2023-2024" n'a pas de labels terrain (prospections non saisies dans la base). Les prédictions sur cette campagne sont des extrapolations hors de la fenêtre de validation. Les interpréter avec une **marge d'incertitude accrue** par rapport aux prédictions sur des campagnes récentes avec labels disponibles.

### Foyers localisés dans des secteurs vastes

Le niveau de risque du secteur est le **maximum** des niveaux des régions naturelles qui le composent. Un secteur avec `niveau_risque_max=3` peut avoir 7 régions à risque 0 et 1 région à risque 3. Consulter le fichier `data/processed/09_rn_risque_decade.parquet` pour le détail à la région naturelle (90 polygones plus fins).

### Seuil de grégarisation LMC

Pour *Locusta migratoria capito* en Madagascar, le seuil de grégarisation est estimé à **1 500–2 500 imagos/ha** (thèse Randrianarijaona 2026 ; Manuel de lutte préventive). Un niveau 3 indique une population *approchant* ce seuil — la lutte préventive est encore possible. Un niveau 4 indique que le seuil est probablement atteint ou dépassé — la lutte curative devient nécessaire.

---

## 7. Utilisation des fichiers GeoJSON dans un SIG

Les fichiers `.geojson` contiennent la géométrie des 12 secteurs de l'aire grégarigène avec les attributs de risque. Ils peuvent être chargés directement dans :

- **QGIS** : Glisser-déposer le fichier `.geojson` dans la fenêtre de carte, ou menu *Couche → Ajouter une couche → Ajouter une couche vectorielle*
- **SIG-LMC existant** : Import au format GeoJSON (vérifier la compatibilité de la version du SIG)
- **Tout SIG supportant GeoJSON** : Projection EPSG:4326 (WGS84), attributs identiques aux fichiers CSV

**Note** : Un secteur avec `geometry = null` dans le GeoJSON indique qu'il n'a pas de correspondance dans le shapefile `aire_gregarigene` pour ce code `AIRE_CODE`. Vérifier la jointure spatiale lors de la mise à jour du shapefile.

Pour visualiser le risque au niveau des 90 régions naturelles (plus fin que les 12 secteurs), utiliser le fichier `data/processed/09_rn_risque_decade.parquet` en jointure avec `data/region_naturelle/region_naturelle.shp` sur la clé `rn_num`.
