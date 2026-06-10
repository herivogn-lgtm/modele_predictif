"""Pipeline #07b — Benchmark étendu : 13 modèles + tests statistiques.

Complète le benchmark #07 avec :
  - 7 nouveaux modèles (ordinal spécifiques, ensembles, deep learning léger)
  - 1 baseline naïf indépendant (DummyClassifier stratifié)
  - Tests de Wilcoxon par paires pour significativité statistique
  - Intervalles de confiance sur recall_23 par bootstrap
  - Analyse de la campagne 2012-2013 (effondrement global)

Modèles ajoutés :
  [nouveau] dummy_stratified     — baseline naïf indépendant (zéro signal)
  [nouveau] histgb               — HistGradientBoosting sklearn (gère NaN nativement)
  [nouveau] extra_trees          — ExtraTreesClassifier (variance/biais différent de RF)
  [nouveau] mlp                  — MLP shallow (128-64-32, ordinal arrondi)
  [nouveau] mord_logistic_at     — Cumulative Link Model All-Thresholds (ordinal théorique)
  [nouveau] mord_ridge           — OrdinalRidge mord (plancher ordinal théorique)
  [nouveau] voting_ensemble      — Vote dur CatBoost + HistGB + LightGBM
  [nouveau] stacking             — Méta-apprenant Ridge sur CatBoost+HistGB+LightGBM

Sortie : data/processed/07b_benchmark_etendu_resume.csv
         data/processed/07b_benchmark_etendu_par_campagne.csv
         data/processed/07b_wilcoxon_pairwise.csv
         data/processed/07b_bootstrap_ci.csv
         data/processed/07b_modele_retenu.txt
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from sklearn.metrics import cohen_kappa_score
from sklearn.utils import resample

sys.path.insert(0, str(Path(__file__).parent))
from validation_seams import select_robust, walk_forward_split  # noqa: E402

DATA_DIR   = Path(__file__).parent.parent / "data"
IN_PARQUET = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
OUT_DIR    = DATA_DIR / "processed"

TARGET       = "severite"
CAMPAIGN_COL = "campagne_calc"
EXCLUDE_COLS = {
    "cell_id", "campagne_calc", "date_start", "date_end", "year",
    "severite", "intensite", "binaire", "a_predire", "effort_prospection",
}
SEV_MIN, SEV_MAX = 0, 3
N_BOOTSTRAP      = 500
RANDOM_STATE     = 42


# ---------------------------------------------------------------------------
# Utilitaires (identiques au pipeline #07 original)
# ---------------------------------------------------------------------------

def to_ordinal(y_continuous) -> np.ndarray:
    rounded = np.rint(np.asarray(y_continuous, dtype=float))
    return np.clip(rounded, SEV_MIN, SEV_MAX).astype(int)


def compute_class_weights(y) -> dict[int, float]:
    counts = pd.Series(y).value_counts()
    n, k = len(y), len(counts)
    return {int(c): float(n) / (k * int(cnt)) for c, cnt in counts.items()}


def evaluate_ordinal(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        qwk = float(cohen_kappa_score(
            y_true, y_pred, weights="quadratic", labels=[0, 1, 2, 3]
        ))
    foyer = np.isin(y_true, (2, 3))
    recall_23 = float((np.isin(y_pred[foyer], (2, 3))).sum() / foyer.sum()) if foyer.any() else float("nan")
    return {"qwk": round(qwk, 4), "recall_23": round(recall_23, 4)}


def aggregate_metrics(per_fold, modele: str, complexite: int) -> dict:
    recalls = np.array([f["recall_23"] for f in per_fold], dtype=float)
    qwks    = np.array([f["qwk"] for f in per_fold], dtype=float)
    return {
        "modele":               modele,
        "recall_23":            round(float(np.nanmean(recalls)), 4),
        "qwk":                  round(float(np.nanmean(qwks)), 4),
        "variance_inter_folds": round(float(np.nanvar(recalls)), 4),
        "pire_campagne":        round(float(np.nanmin(recalls)), 4),
        "complexite":           complexite,
    }


# ---------------------------------------------------------------------------
# Registre étendu (modèles originaux + nouveaux)
# ---------------------------------------------------------------------------

def build_all_models(n_jobs: int = -1) -> dict:
    """Retourne tous les modèles : originaux (#07) + nouveaux (#07b).

    Chaque entrée : (framing, complexite, factory_fn)
      framing = 'regression' | 'multiclass' | 'ordinal_mord'
    """
    models = {}

    # --- Baseline naïf indépendant ---
    def _dummy():
        from sklearn.dummy import DummyClassifier
        return DummyClassifier(strategy="stratified", random_state=RANDOM_STATE)
    models["dummy_stratified"] = ("multiclass", 0, _dummy)

    # --- Modèles originaux #07 ---
    def _reg_ord():
        from sklearn.linear_model import Ridge
        return Ridge(alpha=1.0)
    models["regression_ordinale"] = ("regression", 1, _reg_ord)

    def _rf():
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            n_estimators=300, class_weight="balanced_subsample",
            random_state=RANDOM_STATE, n_jobs=n_jobs,
        )
    models["random_forest"] = ("multiclass", 3, _rf)

    def _xgb():
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=300, learning_rate=0.05, max_depth=6,
            random_state=RANDOM_STATE, n_jobs=n_jobs, tree_method="hist",
        )
    models["xgboost"] = ("multiclass", 4, _xgb)

    def _lgbm():
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            class_weight="balanced", random_state=RANDOM_STATE,
            n_jobs=n_jobs, verbose=-1,
        )
    models["lightgbm"] = ("multiclass", 4, _lgbm)

    def _cat():
        from catboost import CatBoostClassifier
        return CatBoostClassifier(
            loss_function="MultiClass", iterations=300, learning_rate=0.05,
            depth=6, random_seed=RANDOM_STATE, auto_class_weights="Balanced",
            thread_count=(n_jobs if n_jobs and n_jobs > 0 else -1), verbose=False,
        )
    models["catboost"] = ("multiclass", 4, _cat)

    # --- Nouveaux modèles ---

    # HistGradientBoosting sklearn — gère NaN nativement, rapide
    def _histgb():
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
            class_weight="balanced", random_state=RANDOM_STATE,
        )
    models["histgb"] = ("multiclass", 3, _histgb)

    # ExtraTreesClassifier — variance/biais différent de RF
    def _et():
        from sklearn.ensemble import ExtraTreesClassifier
        return ExtraTreesClassifier(
            n_estimators=300, class_weight="balanced_subsample",
            random_state=RANDOM_STATE, n_jobs=n_jobs,
        )
    models["extra_trees"] = ("multiclass", 3, _et)

    # GradientBoosting sklearn — algorithme différent de XGBoost/LightGBM
    def _gb():
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.multiclass import OneVsRestClassifier
        return OneVsRestClassifier(
            GradientBoostingClassifier(
                n_estimators=200, learning_rate=0.05, max_depth=4,
                random_state=RANDOM_STATE,
            ),
            n_jobs=n_jobs,
        )
    models["gradient_boosting"] = ("multiclass", 4, _gb)

    # MLP shallow — réseau dense léger
    def _mlp():
        from sklearn.neural_network import MLPClassifier
        return MLPClassifier(
            hidden_layer_sizes=(128, 64, 32), activation="relu",
            max_iter=300, random_state=RANDOM_STATE, early_stopping=True,
            class_weight="balanced" if False else None,  # MLPClassifier ne supporte pas class_weight
        )
    models["mlp"] = ("multiclass", 4, _mlp)

    # Mord LogisticAT — Cumulative Link Model All-Thresholds (régression ordinale théorique)
    def _mord_at():
        import mord
        return mord.LogisticAT(alpha=1.0)
    models["mord_logistic_at"] = ("regression", 2, _mord_at)

    # Mord OrdinalRidge — alternative ordinale théorique au Ridge sklearn
    def _mord_ridge():
        import mord
        return mord.OrdinalRidge(alpha=1.0)
    models["mord_ridge"] = ("regression", 2, _mord_ridge)

    # Voting Ensemble — vote dur sur les 3 meilleurs modèles originaux
    def _voting():
        from sklearn.ensemble import VotingClassifier
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier
        from sklearn.ensemble import HistGradientBoostingClassifier
        return VotingClassifier(
            estimators=[
                ("lgbm", LGBMClassifier(
                    n_estimators=300, learning_rate=0.05, class_weight="balanced",
                    random_state=RANDOM_STATE, n_jobs=n_jobs, verbose=-1,
                )),
                ("cat", CatBoostClassifier(
                    iterations=300, learning_rate=0.05, depth=6,
                    auto_class_weights="Balanced", random_seed=RANDOM_STATE, verbose=False,
                )),
                ("hgb", HistGradientBoostingClassifier(
                    max_iter=300, learning_rate=0.05, class_weight="balanced",
                    random_state=RANDOM_STATE,
                )),
            ],
            voting="hard", n_jobs=1,
        )
    models["voting_ensemble"] = ("multiclass", 5, _voting)

    # Stacking — méta-apprenant Ridge sur CatBoost+HistGB+LightGBM
    def _stacking():
        from sklearn.ensemble import StackingClassifier
        from sklearn.linear_model import RidgeClassifier
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier
        from sklearn.ensemble import HistGradientBoostingClassifier
        return StackingClassifier(
            estimators=[
                ("lgbm", LGBMClassifier(
                    n_estimators=200, learning_rate=0.05, class_weight="balanced",
                    random_state=RANDOM_STATE, n_jobs=n_jobs, verbose=-1,
                )),
                ("cat", CatBoostClassifier(
                    iterations=200, learning_rate=0.05, depth=6,
                    auto_class_weights="Balanced", random_seed=RANDOM_STATE, verbose=False,
                )),
                ("hgb", HistGradientBoostingClassifier(
                    max_iter=200, learning_rate=0.05, class_weight="balanced",
                    random_state=RANDOM_STATE,
                )),
            ],
            final_estimator=RidgeClassifier(),
            cv=3, n_jobs=1,
        )
    models["stacking"] = ("multiclass", 6, _stacking)

    return models


# ---------------------------------------------------------------------------
# Fit/predict unifié
# ---------------------------------------------------------------------------

def fit_predict(framing: str, factory_fn, X_tr, y_tr, X_te) -> np.ndarray:
    model = factory_fn()

    if framing == "regression":
        weights = compute_class_weights(y_tr)
        sw = np.array([weights[int(v)] for v in y_tr], dtype=float)
        try:
            model.fit(X_tr, y_tr, sample_weight=sw)
        except TypeError:
            model.fit(X_tr, y_tr)
        return to_ordinal(model.predict(X_te))

    # multiclass — encodage LabelEncoder (XGBoost ≥ 2.0 exige classes contiguës)
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder().fit(y_tr)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(X_tr, le.transform(y_tr))
        y_pred = le.inverse_transform(np.asarray(model.predict(X_te)).ravel())
    return np.asarray(y_pred, dtype=int)


# ---------------------------------------------------------------------------
# Benchmark principal
# ---------------------------------------------------------------------------

def run_benchmark(df: pd.DataFrame, feature_cols: list[str], models: dict) -> tuple:
    folds = walk_forward_split(df[CAMPAIGN_COL].unique())
    summary_rows = []
    detail_rows  = []

    total = len(models)
    for idx, (name, (framing, complexite, factory_fn)) in enumerate(models.items(), 1):
        print(f"  [{idx}/{total}] {name} ...")
        per_fold = []
        for train_camps, test_camp in folds:
            tr = df[df[CAMPAIGN_COL].isin(train_camps)]
            te = df[df[CAMPAIGN_COL] == test_camp]
            if len(tr) == 0:
                continue
            try:
                y_pred = fit_predict(
                    framing, factory_fn,
                    tr[feature_cols].values, tr[TARGET].to_numpy(int),
                    te[feature_cols].values,
                )
                m = evaluate_ordinal(te[TARGET].to_numpy(int), y_pred)
            except Exception as exc:
                print(f"    [!] échec {test_camp}: {exc}")
                m = {"qwk": float("nan"), "recall_23": float("nan")}
            per_fold.append({"campagne_calc": test_camp, **m})
            detail_rows.append({"modele": name, "campagne_calc": test_camp, **m})

        row = aggregate_metrics(per_fold, modele=name, complexite=complexite)
        row["n_folds"] = len(per_fold)
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    detail  = pd.DataFrame(detail_rows)
    return summary, detail


# ---------------------------------------------------------------------------
# Tests de Wilcoxon par paires (significativité statistique)
# ---------------------------------------------------------------------------

def wilcoxon_pairwise(detail: pd.DataFrame, metric: str = "recall_23") -> pd.DataFrame:
    """Test de Wilcoxon signé-rang entre chaque paire de modèles sur recall_23 par campagne."""
    modeles = detail["modele"].unique()
    pivot = detail.pivot_table(index="campagne_calc", columns="modele", values=metric)

    rows = []
    modeles_list = list(modeles)
    for i, a in enumerate(modeles_list):
        for b in modeles_list[i+1:]:
            if a not in pivot.columns or b not in pivot.columns:
                continue
            paired = pivot[[a, b]].dropna()
            if len(paired) < 5:
                rows.append({"modele_a": a, "modele_b": b, "n_paires": len(paired),
                              "statistic": np.nan, "p_value": np.nan, "significatif_05": False})
                continue
            diff = paired[a].values - paired[b].values
            if np.all(diff == 0):
                rows.append({"modele_a": a, "modele_b": b, "n_paires": len(paired),
                              "statistic": 0.0, "p_value": 1.0, "significatif_05": False})
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                stat, pval = wilcoxon(diff, zero_method="wilcox", alternative="two-sided")
            mean_a = paired[a].mean()
            mean_b = paired[b].mean()
            rows.append({
                "modele_a": a, "modele_b": b,
                "mean_a": round(mean_a, 4), "mean_b": round(mean_b, 4),
                "diff_a_minus_b": round(mean_a - mean_b, 4),
                "n_paires": len(paired),
                "statistic": round(stat, 2),
                "p_value": round(pval, 4),
                "significatif_05": bool(pval < 0.05),
            })
    return pd.DataFrame(rows).sort_values("p_value")


# ---------------------------------------------------------------------------
# Bootstrap — intervalles de confiance sur recall_23 par modèle
# ---------------------------------------------------------------------------

def bootstrap_ci(detail: pd.DataFrame, n_boot: int = N_BOOTSTRAP) -> pd.DataFrame:
    rows = []
    for name, grp in detail.groupby("modele"):
        recalls = grp["recall_23"].dropna().values
        if len(recalls) < 3:
            rows.append({"modele": name, "recall_mean": np.nan, "ci_low": np.nan, "ci_high": np.nan})
            continue
        boot_means = [resample(recalls, random_state=i).mean() for i in range(n_boot)]
        rows.append({
            "modele": name,
            "recall_mean":  round(float(np.mean(recalls)), 4),
            "ci_low":       round(float(np.percentile(boot_means, 2.5)), 4),
            "ci_high":      round(float(np.percentile(boot_means, 97.5)), 4),
            "ci_width":     round(float(np.percentile(boot_means, 97.5) - np.percentile(boot_means, 2.5)), 4),
        })
    return pd.DataFrame(rows).sort_values("recall_mean", ascending=False)


# ---------------------------------------------------------------------------
# Analyse de la campagne 2012-2013
# ---------------------------------------------------------------------------

def analyse_campagne_effondrement(detail: pd.DataFrame) -> pd.DataFrame:
    camp = "2012-2013"
    subset = detail[detail["campagne_calc"] == camp].copy()
    subset = subset.sort_values("recall_23", ascending=False)
    return subset[["modele", "qwk", "recall_23"]]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    print(f"Chargement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)
    obs = df[df[TARGET].notna()].copy()
    obs[TARGET] = obs[TARGET].astype(int)
    feature_cols = [c for c in obs.columns if c not in EXCLUDE_COLS]
    print(f"Observées : {len(obs)} | Features : {len(feature_cols)} | Campagnes : {obs[CAMPAIGN_COL].nunique()}")

    # Imputation médiane (compatible HistGB qui gère NaN nativement aussi)
    obs[feature_cols] = obs[feature_cols].fillna(obs[feature_cols].median(numeric_only=True))

    models = build_all_models(n_jobs=-1)
    print(f"\n=== Benchmark étendu — {len(models)} modèles ===\n")

    summary, detail = run_benchmark(obs, feature_cols, models)

    # Contrainte QWK = baseline indépendant : dummy_stratified
    dummy_row = summary[summary["modele"] == "dummy_stratified"]
    baseline_qwk_naif = float(dummy_row["qwk"].iloc[0]) if len(dummy_row) else 0.0

    # Contrainte QWK = régression ordinale (fidélité ADR 0005)
    reg_row = summary[summary["modele"] == "regression_ordinale"]
    baseline_qwk_reg = float(reg_row["qwk"].iloc[0]) if len(reg_row) else 0.0

    classement_naif = select_robust(summary, baseline_qwk=baseline_qwk_naif)
    classement_reg  = select_robust(summary, baseline_qwk=baseline_qwk_reg)

    summary_sorted = summary.sort_values("recall_23", ascending=False).reset_index(drop=True)
    print("\n=== Résumé par modèle (trié recall_23) ===")
    print(summary_sorted.to_string(index=False))

    print(f"\n--- Baseline naïf (dummy_stratified) QWK = {baseline_qwk_naif:.4f}")
    print(f"Classement (contrainte naïf) : {classement_naif[:5]}")
    print(f"\n--- Baseline régression ordinale QWK = {baseline_qwk_reg:.4f}")
    print(f"Classement (contrainte reg_ord) : {classement_reg[:5]}")

    print("\n=== Tests de Wilcoxon ===")
    wilcoxon_df = wilcoxon_pairwise(detail)
    print(wilcoxon_df[wilcoxon_df["significatif_05"]].to_string(index=False))

    print("\n=== Bootstrap CI (recall_23, 95%) ===")
    ci_df = bootstrap_ci(detail)
    print(ci_df.to_string(index=False))

    print("\n=== Analyse campagne 2012-2013 ===")
    effondrement = analyse_campagne_effondrement(detail)
    print(effondrement.to_string(index=False))

    # Sauvegarde
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_sorted.to_csv(OUT_DIR / "07b_benchmark_etendu_resume.csv", index=False)
    detail.to_csv(OUT_DIR / "07b_benchmark_etendu_par_campagne.csv", index=False)
    wilcoxon_df.to_csv(OUT_DIR / "07b_wilcoxon_pairwise.csv", index=False)
    ci_df.to_csv(OUT_DIR / "07b_bootstrap_ci.csv", index=False)

    retenu_naif = classement_naif[0] if classement_naif else "(aucun)"
    retenu_reg  = classement_reg[0]  if classement_reg  else "(aucun)"
    (OUT_DIR / "07b_modele_retenu.txt").write_text(
        f"baseline_dummy_qwk={baseline_qwk_naif:.4f}\n"
        f"baseline_reg_ord_qwk={baseline_qwk_reg:.4f}\n"
        f"classement_contrainte_naif={classement_naif}\n"
        f"classement_contrainte_reg={classement_reg}\n"
        f"modele_retenu_naif={retenu_naif}\n"
        f"modele_retenu_reg={retenu_reg}\n",
        encoding="utf-8",
    )

    print(f"\nSorties sauvegardées dans {OUT_DIR}/07b_*")
    print(f"Modèle retenu (contrainte naïf) : {retenu_naif}")
    print(f"Modèle retenu (contrainte reg)  : {retenu_reg}")


if __name__ == "__main__":
    run()
