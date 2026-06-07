# Pipeline #10 — Rapport de performance walk-forward

**Notebook** : `notebooks/10_rapport_performance.ipynb`  
**Entrées** : Sorties de #06, #07, #08, #09  
**Sortie** : `data/processed/10_courbe_performance.png`  
**Durée estimée** : < 5 minutes (notebook interactif)  
**Dépendances obligatoires** : Pipelines [#06](06-table-entrainement.md), [#07](07-lgbm-baseline.md), [#08](08-lgbm-hierarchique.md), [#09](09-sorties-operationnelles.md)

> Ce pipeline est un notebook Jupyter, pas un script Python exécutable directement. Cette fiche documente son usage et l'interprétation de ses résultats.

---

## Objectif

Consolider et visualiser les métriques de performance des pipelines #07 et #08 sur les 8 folds walk-forward, analyser le biais de détection lié à l'effort de prospection, et comparer optionnellement les prédictions du modèle avec les cartes historiques du SIG-LMC.

---

## Entrées

| Fichier | Usage dans le notebook |
|---------|------------------------|
| `data/processed/07_rapport_walk_forward.csv` | Métriques présence/absence (AUC-ROC, F1, précision, rappel, seuil) par fold |
| `data/processed/08_rapport_walk_forward.csv` | Métriques densité (RMSE, MAE) et phase (F1-macro, recall_G) par fold |
| `data/processed/06_table_entrainement_unifiee.parquet` | Effort de prospection par région × décade (analyse de biais) |
| `data/processed/09_rn_risque_decade.parquet` | Prédictions de risque par région (comparaison SIG-LMC, si disponible) |
| `data/sig_lmc/*.csv` (optionnel) | Historique SIG-LMC : colonnes `AIRE_CODE` ou `rn_num`, `campagne_calc`, `niveau_risque_siglmc` (int 0–4) |

---

## Sorties

| Fichier | Description |
|---------|-------------|
| `data/processed/10_courbe_performance.png` | Graphique double-panel : performance au fil des campagnes |

---

## Sections du notebook

### Section 1 — Tableau des métriques par fold

Tableau récapitulatif des 8 folds de validation + ligne GLOBAL :

| Colonne | Description |
|---------|-------------|
| `campagne_calc` | Campagne de validation du fold |
| `n_positifs` / `n_negatifs` | Effectifs dans le fold |
| `auc_roc` | AUC-ROC présence/absence (cible ≥ 0,85) |
| `f1` | F1 binaire présence/absence |
| `precision`, `recall` | Précision et rappel |
| `rmse_densite`, `mae_densite` | Erreur de régression de densité |
| `f1_macro_phase` | F1-macro classification de phase (S/St/T/G) |
| `recall_G` | Rappel sur la classe grégaire (cible ≥ 0,70) |

Les valeurs maximales et minimales sur les métriques cibles sont mises en évidence.

### Section 2 — Courbe de performance au fil du temps

Graphique à deux panneaux exporté en `10_courbe_performance.png` :
- **Panneau supérieur** : AUC-ROC et F1 présence/absence par campagne de validation, avec ligne de référence `cible_auc = 0,85`
- **Panneau inférieur** : F1-macro phase et recall_G par campagne, avec ligne de référence `cible_recall_G = 0,70`
- Axe X : campagnes dans l'ordre chronologique

### Section 3 — Analyse du biais de détection

Cette section est critique pour l'interprétation des résultats. Elle illustre le biais de détection inhérent aux données acridologiques de terrain :

**Graphique 1 — Scatter effort vs taux de présence** :
- Axe X : `effort_prospection` moyen par (région × campagne)
- Axe Y : taux de présence observé dans la cellule
- Droite de tendance + coefficient de corrélation r

**Graphique 2 — Barplot taux de présence par quartile d'effort** :
- Q1 (effort faible) → Q4 (effort élevé)
- Illustre que les régions peu prospectées apparaissent "absentes" non par absence réelle mais par manque d'observation

**Interprétation** : Une corrélation positive effort-présence n'indique pas que les criquets préfèrent les zones souvent prospectées — elle reflète le fait que les zones peu visitées ont un label `label = 0` (absence vérifiée) même quand aucun criquet n'a été cherché intensivement. Ce biais est inhérent aux données terrain et non à la qualité du modèle.

### Section 4 — Comparaison SIG-LMC (optionnelle)

Cette section s'active automatiquement si le dossier `data/sig_lmc/` contient des fichiers CSV avec les colonnes attendues :
- `AIRE_CODE` ou `rn_num` — identifiant spatial
- `campagne_calc` — campagne au format `"YYYY-YYYY+1"`
- `niveau_risque_siglmc` — niveau de risque SIG-LMC (entier 0–4)

Sorties de la section :
- Matrice de confusion 5×5 (niveaux 0–4 prédits vs SIG-LMC)
- Accord exact et accord à ± 1 niveau
- Kappa de Cohen

### Section 5 — Tableau de synthèse des cibles

| Métrique | Valeur GLOBAL | Cible | Statut |
|----------|---------------|-------|--------|
| AUC-ROC présence/absence | X,XX | ≥ 0,85 | ✓ / ✗ |
| Recall_G (phase grégaire) | X,XX | ≥ 0,70 | ✓ / ✗ |

Les campagnes exclues de l'évaluation (2023-2024, inférence uniquement) sont listées explicitement.

---

## Exécution

```bash
# Mode interactif (recommandé pour exploration)
jupyter notebook notebooks/10_rapport_performance.ipynb

# Mode non-interactif (génère la sortie PNG sans interaction)
jupyter nbconvert --to notebook --execute notebooks/10_rapport_performance.ipynb \
  --output notebooks/10_rapport_performance_executed.ipynb
```

---

## Dépendances

- **Amont** : [#07](07-lgbm-baseline.md), [#08](08-lgbm-hierarchique.md), [#09](09-sorties-operationnelles.md), [#06](06-table-entrainement.md)
- **Aval** : aucun pipeline n'utilise les sorties de ce notebook
- **Bibliothèques** : `pandas`, `matplotlib`, `seaborn`, `scipy`, `pyarrow`

---

## Avertissements

Les campagnes 2023-2024 sont en mode inférence et sont **explicitement exclues** de toutes les métriques de performance. La section SIG-LMC est silencieusement ignorée si `data/sig_lmc/` est absent — pas d'erreur.

Le biais de détection quantifié en Section 3 est un fait structurel des données de surveillance acridienne : les zones isolées ou difficiles d'accès sont systématiquement sous-prospectées. Ce biais ne peut pas être corrigé par le modèle ML seul ; il doit être pris en compte lors de l'interprétation des prédictions de risque faible dans des zones à effort de prospection historiquement faible.
