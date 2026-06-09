"""Pipeline #10 — Rapport de performance walk-forward par campagne (issue #08).

Mesure la qualité prédictive du modèle retenu (#07) sur données réelles, ventilée
par campagne (folds walk-forward), pour la revue humaine avant mise en production
des cartes (#09). Métriques :

  - QWK (réutilisé de #07) et rappel des niveaux 2–3 ;
  - AUC du **binaire dérivé** (présence = sévérité ≥ 1), exigence thèse §31/§33 ;
  - calibration des probabilités (proba moyenne vs fréquence observée par bin) ;
  - courbe de gain / lift (gain opérationnel).

Robustesse jugée sur la variance inter-folds et la pire campagne (PRD §20/§24), pas
sur la meilleure moyenne. Les fonctions de calcul de métriques sont pures et testées ;
seul `run()` orchestre l'I/O et l'entraînement réel (lourd, non testé unitairement).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_ordinal_07 import (  # noqa: E402  (réutilise le cœur #07)
    BASELINE,
    CAMPAIGN_COL,
    TARGET,
    build_models,
    compute_class_weights,
    evaluate_ordinal,
    get_feature_columns,
    to_ordinal,
)
from validation_seams import walk_forward_split  # noqa: E402  (folds chronologiques #06)

DATA_DIR     = Path(__file__).parent.parent / "data"
IN_PARQUET   = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
IN_CHOIX     = DATA_DIR / "processed" / "07_modele_retenu.txt"
OUT_RAPPORT  = DATA_DIR / "processed" / "08_rapport_par_campagne.csv"
OUT_CALIB    = DATA_DIR / "processed" / "08_calibration.csv"
OUT_GAINLIFT = DATA_DIR / "processed" / "08_gain_lift.csv"
OUT_RESUME   = DATA_DIR / "processed" / "08_rapport_resume.txt"

SEV_PRESENCE = 1  # seuil du binaire dérivé : présence = sévérité ≥ 1 (PRD)


def derive_binaire(severite) -> np.ndarray:
    """Binaire présence dérivé de la sévérité ordinale : 1 si sévérité ≥ 1, sinon 0."""
    return (np.asarray(severite) >= SEV_PRESENCE).astype(int)


def presence_from_proba(proba, classes) -> np.ndarray:
    """Proba de présence (sév ≥ 1) à partir des probas multiclasse d'un classifieur.

    `proba` : matrice (n, k) de `predict_proba` ; `classes` : labels de sévérité
    alignés sur les colonnes (`model.classes_`). Somme les colonnes des niveaux ≥ 1
    (= 1 − P(absence)). Robuste aux folds où certains niveaux manquent.
    """
    proba = np.asarray(proba, dtype=float)
    classes = np.asarray(classes)
    positives = classes >= SEV_PRESENCE
    return proba[:, positives].sum(axis=1)


def auc_binaire(y_bin, score) -> float:
    """AUC du binaire dérivé (présence) vs un score de présence continu.

    Retourne NaN si le fold ne contient qu'une seule classe (AUC indéfinie),
    plutôt que de lever — l'agrégat aval ignore les folds dégénérés.
    """
    from sklearn.metrics import roc_auc_score

    y_bin = np.asarray(y_bin, dtype=int)
    if len(np.unique(y_bin)) < 2:
        return float("nan")
    return float(roc_auc_score(y_bin, np.asarray(score, dtype=float)))


def calibration_table(y_bin, proba, n_bins: int = 10) -> pd.DataFrame:
    """Diagramme de fiabilité : proba moyenne vs fréquence observée par bin.

    Découpe `proba` en `n_bins` intervalles de largeur égale sur [0, 1] et, pour
    chaque bin peuplé, retourne `{proba_moyenne, freq_observee, n}`. Un modèle bien
    calibré a `freq_observee ≈ proba_moyenne` (la diagonale du diagramme).
    """
    y_bin = np.asarray(y_bin, dtype=int)
    proba = np.asarray(proba, dtype=float)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # Affecte chaque proba à un bin [0, n_bins-1] (1.0 inclus dans le dernier bin).
    idx = np.clip(np.digitize(proba, edges[1:-1], right=False), 0, n_bins - 1)

    rows = []
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        rows.append({
            "bin": b,
            "proba_moyenne": float(proba[mask].mean()),
            "freq_observee": float(y_bin[mask].mean()),
            "n": int(mask.sum()),
        })
    return pd.DataFrame(rows)


def gain_lift_table(y_bin, score, n_bins: int = 10) -> pd.DataFrame:
    """Courbe de gain / lift : gain opérationnel d'une prospection priorisée par score.

    Trie les cellules par score décroissant, les découpe en `n_bins` quantiles, et
    cumule. Pour chaque quantile : `{pop_cumulee, gain_cumule, lift}` où
    `gain_cumule` = part des présences captées, `pop_cumulee` = part de population
    prospectée, `lift` = gain / population (× le gain vs prospection aléatoire).
    """
    y_bin = np.asarray(y_bin, dtype=int)
    score = np.asarray(score, dtype=float)

    order = np.argsort(-score, kind="stable")        # score décroissant
    y_sorted = y_bin[order]
    n = len(y_sorted)
    total_pos = int(y_sorted.sum())

    # Bornes des quantiles (n_bins tranches de population aussi égales que possible).
    cuts = np.linspace(0, n, n_bins + 1, dtype=int)
    rows = []
    for b in range(n_bins):
        end = cuts[b + 1]
        if end == 0:
            continue
        pop_cumulee = end / n
        gain_cumule = (float(y_sorted[:end].sum()) / total_pos) if total_pos else float("nan")
        lift = (gain_cumule / pop_cumulee) if (pop_cumulee and total_pos) else float("nan")
        rows.append({
            "quantile": b + 1,
            "pop_cumulee": round(pop_cumulee, 4),
            "gain_cumule": round(gain_cumule, 4) if total_pos else float("nan"),
            "lift": round(lift, 4) if total_pos else float("nan"),
        })
    return pd.DataFrame(rows)


def rapport_par_campagne(folds) -> pd.DataFrame:
    """Rapport ventilé par campagne (fold walk-forward) du modèle retenu.

    `folds` : liste de dicts `{campagne_calc, y_true, y_pred, score}` (un par fold)
    où `y_true`/`y_pred` sont des sévérités ordinales 0–3 et `score` la proba de
    présence. Retourne une ligne par campagne testée : `{campagne_calc, qwk,
    recall_23, auc_binaire, n}` — support de la revue humaine avant production (#09).
    """
    rows = []
    for fold in folds:
        y_true = np.asarray(fold["y_true"], dtype=int)
        y_pred = np.asarray(fold["y_pred"], dtype=int)
        m = evaluate_ordinal(y_true, y_pred)
        rows.append({
            "campagne_calc": fold["campagne_calc"],
            "qwk":         m["qwk"],
            "recall_23":   m["recall_23"],
            "auc_binaire": auc_binaire(derive_binaire(y_true), fold["score"]),
            "n":           int(len(y_true)),
        })
    return pd.DataFrame(rows)


# Métriques résumées par robustesse (moyenne, dispersion, pire campagne).
ROBUSTESSE_METRIQUES = ("qwk", "recall_23", "auc_binaire")


def resume_robustesse(rapport_df: pd.DataFrame) -> dict:
    """Agrège le rapport par campagne en jugeant la **robustesse** (PRD §20/§24).

    Pour chaque métrique (`qwk`, `recall_23`, `auc_binaire`), retourne la moyenne,
    la variance inter-folds et la **pire campagne** (min). On retient un modèle pour
    sa pire campagne et sa stabilité, pas pour sa meilleure moyenne. Les campagnes à
    métrique indéfinie (NaN : fold sans foyer ou à classe unique) sont ignorées.
    """
    out: dict = {}
    for metrique in ROBUSTESSE_METRIQUES:
        vals = rapport_df[metrique].to_numpy(dtype=float)
        out[f"{metrique}_moyen"] = round(float(np.nanmean(vals)), 4)
        out[f"{metrique}_variance_inter_folds"] = round(float(np.nanvar(vals)), 4)
        out[f"{metrique}_pire_campagne"] = round(float(np.nanmin(vals)), 4)
    return out


# ---------------------------------------------------------------------------
# Orchestration I/O (#08) — non testée unitairement (entraînement réel lourd)
# ---------------------------------------------------------------------------

def _lire_modele_retenu(path: Path) -> str:
    """Nom du modèle retenu, lu depuis `07_modele_retenu.txt` (sinon baseline)."""
    if not path.exists():
        print(f"  [!] {path} absent — repli sur le baseline « {BASELINE} ».")
        return BASELINE
    for ligne in path.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("modele_retenu="):
            nom = ligne.split("=", 1)[1].strip()
            if nom and "aucun" not in nom:
                return nom
    return BASELINE


def _predit_fold(spec, X_tr, y_tr, X_te):
    """Entraîne le modèle retenu sur un fold → (sévérité ordinale, score de présence).

    Régression (Ridge/LSTM) : prédiction continue → `to_ordinal` ; score de présence
    par logistique centrée sur la frontière absence/présence (0.5). Multiclasse :
    labels décodés + proba de présence `1 − P(absence)` via `predict_proba`.
    """
    model = spec.factory()
    if spec.framing == "regression":
        weights = compute_class_weights(y_tr)
        sample_weight = np.array([weights[int(v)] for v in y_tr], dtype=float)
        model.fit(X_tr, y_tr, sample_weight=sample_weight)
        pred_cont = np.asarray(model.predict(X_te), dtype=float)
        y_pred = to_ordinal(pred_cont)
        score = 1.0 / (1.0 + np.exp(-(pred_cont - 0.5)))   # proxy présence monotone
        return y_pred, score

    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder().fit(y_tr)
    model.fit(X_tr, le.transform(y_tr))
    y_pred = le.inverse_transform(np.asarray(model.predict(X_te)).ravel()).astype(int)
    proba = model.predict_proba(X_te)
    score = presence_from_proba(proba, le.inverse_transform(model.classes_))
    return y_pred, score


def run() -> None:
    print(f"Chargement table d'entraînement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)

    obs = df[df[TARGET].notna()].copy()
    obs[TARGET] = obs[TARGET].astype(int)
    feature_cols = get_feature_columns(obs)
    obs[feature_cols] = obs[feature_cols].fillna(obs[feature_cols].median(numeric_only=True))

    retenu = _lire_modele_retenu(IN_CHOIX)
    # Mêmes leviers de coût que #07 (mode léger) ; on n'instancie que le modèle retenu.
    n_estimators = int(os.environ.get("BENCH_N_ESTIMATORS", "300"))
    n_jobs       = int(os.environ.get("BENCH_N_JOBS", "-1"))
    spec = build_models(n_estimators=n_estimators, n_jobs=n_jobs, include_lstm=True)[retenu]
    print(f"Modèle évalué : {retenu} (cadrage {spec.framing}) "
          f"sur {len(obs)} lignes observées, {len(feature_cols)} features")

    folds = walk_forward_split(obs[CAMPAIGN_COL].unique())
    fold_results = []
    for train_camps, test_camp in folds:
        tr = obs[obs[CAMPAIGN_COL].isin(train_camps)]
        te = obs[obs[CAMPAIGN_COL] == test_camp]
        try:
            y_pred, score = _predit_fold(
                spec, tr[feature_cols], tr[TARGET].to_numpy(int), te[feature_cols]
            )
            fold_results.append({
                "campagne_calc": test_camp,
                "y_true": te[TARGET].to_numpy(int), "y_pred": y_pred, "score": score,
            })
        except Exception as exc:  # noqa: BLE001 — un fold défaillant ne tue pas le rapport
            print(f"  [!] {retenu} a échoué sur {test_camp} : {exc}")

    rep = rapport_par_campagne(fold_results)
    robust = resume_robustesse(rep)

    # Calibration et gain/lift agrégés sur l'ensemble des folds (binaire dérivé).
    all_bin   = np.concatenate([derive_binaire(f["y_true"]) for f in fold_results])
    all_score = np.concatenate([np.asarray(f["score"], dtype=float) for f in fold_results])
    calib    = calibration_table(all_bin, all_score)
    gainlift = gain_lift_table(all_bin, all_score)

    print("\n=== Rapport par campagne ===")
    print(rep.to_string(index=False))
    print("\n=== Robustesse (moyenne / variance inter-folds / pire campagne) ===")
    for metrique in ROBUSTESSE_METRIQUES:
        print(f"  {metrique:12s} : moy={robust[f'{metrique}_moyen']:.4f}  "
              f"var={robust[f'{metrique}_variance_inter_folds']:.4f}  "
              f"pire={robust[f'{metrique}_pire_campagne']:.4f}")

    OUT_RAPPORT.parent.mkdir(parents=True, exist_ok=True)
    rep.to_csv(OUT_RAPPORT, index=False)
    calib.to_csv(OUT_CALIB, index=False)
    gainlift.to_csv(OUT_GAINLIFT, index=False)
    OUT_RESUME.write_text(
        f"modele_retenu={retenu}\n"
        + "".join(f"{k}={v}\n" for k, v in robust.items()),
        encoding="utf-8",
    )
    print(f"\nSortie rapport     : {OUT_RAPPORT}")
    print(f"Sortie calibration : {OUT_CALIB}")
    print(f"Sortie gain/lift   : {OUT_GAINLIFT}")
    print(f"Sortie résumé      : {OUT_RESUME}")


if __name__ == "__main__":
    run()
