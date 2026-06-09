# Pipeline #10 — Rapport de performance walk-forward par campagne

**Script** : `src/rapport_performance_08.py` (Pipeline 10 du PRD ; suffixe `_08` = numéro d'issue)
**Entrées** : `06_table_entrainement_unifiee.parquet`, `07_modele_retenu.txt`
**Sorties** : `08_rapport_par_campagne.csv`, `08_calibration.csv`, `08_gain_lift.csv`, `08_rapport_resume.txt`
**Durée estimée** : 5–30 minutes (selon le modèle retenu)
**Dépendances obligatoires** : Pipelines [#06](06-table-entrainement.md), [#07](07-benchmark-ordinal.md)

> Ce rapport est le **support de la revue humaine HITL** : un humain juge le modèle retenu ici **avant** la génération des cartes terrain ([#09](09-sorties-operationnelles.md)).

---

## Objectif

Mesurer la qualité prédictive du **modèle retenu** (#07) sur données réelles, **ventilée par campagne** (folds walk-forward). Métriques :

- **QWK** (quadratic weighted kappa, réutilisé de #07) et **rappel des niveaux 2–3** (« ne pas manquer un foyer »).
- **AUC du binaire dérivé** (présence = sévérité ≥ 1) — exigence thèse §31/§33.
- **Calibration** des probabilités (proba moyenne vs fréquence observée par bin).
- **Courbe de gain / lift** (gain opérationnel d'une prospection priorisée).

La **robustesse** est jugée sur la **variance inter-folds** et la **pire campagne** (PRD §20/§24), pas sur la meilleure moyenne.

---

## Sorties

| Fichier | Contenu |
|---------|---------|
| `08_rapport_par_campagne.csv` | 1 ligne/campagne : `qwk`, `recall_23`, `auc_binaire`, `n` |
| `08_calibration.csv` | Diagramme de fiabilité : `proba_moyenne`, `freq_observee`, `n` par bin |
| `08_gain_lift.csv` | Courbe de gain/lift : `quantile`, `pop_cumulee`, `gain_cumule`, `lift` |
| `08_rapport_resume.txt` | Modèle retenu + robustesse (moyenne / variance inter-folds / pire campagne) |

---

## Fonctions pures (testées — `tests/test_08_rapport_performance.py`)

| Fonction | Rôle |
|----------|------|
| `derive_binaire(severite)` | Binaire présence dérivé (sév ≥ 1) |
| `presence_from_proba(proba, classes)` | Proba de présence multiclasse = somme des niveaux ≥ 1 (= 1 − P(absence)) |
| `auc_binaire(y_bin, score)` | AUC du binaire dérivé (NaN si classe unique dans le fold) |
| `calibration_table(y_bin, proba, n_bins=10)` | Diagramme de fiabilité (bins largeur égale, vides exclus) |
| `gain_lift_table(y_bin, score, n_bins=10)` | Courbe de gain/lift (tri score décroissant, cumul) |
| `rapport_par_campagne(folds)` | Assemblage du rapport ventilé par campagne |
| `resume_robustesse(rapport)` | Par métrique : moyenne, variance inter-folds, pire campagne (nan-agrégats) |

L'orchestration `run()` (non testée) ré-entraîne le modèle retenu par fold walk-forward, génère sévérité ordinale + score de présence (multiclasse : `predict_proba` ; régression : logistique centrée sur 0,5).

---

## Lancement

```bash
./.venv/bin/python -u src/rapport_performance_08.py 2>&1 | tee /tmp/rapport08.log
```

Mêmes leviers de coût que #07 : `BENCH_N_ESTIMATORS`, `BENCH_N_JOBS`, `BENCH_LSTM`.

---

## Lecture (run de référence, modèle `regression_ordinale`)

- AUC binaire moyen ≈ **0,75** (pire campagne ~0,44, variance inter-folds ~0,012).
- QWK ≈ 0,31 et rappel 2–3 ≈ 0,54 — **identiques aux chiffres #07** (contrôle de cohérence).
- Calibration monotone ; gain/lift modeste (lift ~1,20 au 1er décile) → signal à arbitrer en revue humaine avant les cartes ([#09](09-sorties-operationnelles.md)).

> Après un run complet de référence #07, si `select_robust` retient un autre modèle, relancer simplement ce script — il s'adapte via `07_modele_retenu.txt`.
