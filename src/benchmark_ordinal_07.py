"""Pipeline #07 — Benchmark de modèles ordinaux (sévérité-phase 0–3).

Remplace le « LightGBM seul » binaire par un benchmark de modèles entraînés et
évalués via les seams `walk_forward_split` + `select_robust` (issue #06) sur la
table cellule × décade (#06). Cadrage ordinal par modèle :

  - régression ordinale (baseline) : score continu arrondi par `to_ordinal` ;
  - Random Forest / LightGBM / XGBoost / CatBoost : classification multiclasse 0–3 ;
  - LSTM (torch) : régression arrondie.

Pondération de classe pour le niveau 3 minoritaire (~6,6 %). Sortie = métriques par
campagne et par modèle, prêtes pour `select_robust` et le rapport (#08).

Les fonctions de ce module sont pures (cadrage, pondération, métriques, agrégation,
registre) ; seul `run()` orchestre l'I/O et l'entraînement réel.
"""

from __future__ import annotations

import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

sys.path.insert(0, str(Path(__file__).parent))
from validation_seams import select_robust, walk_forward_split  # noqa: E402  (seams #06)

DATA_DIR    = Path(__file__).parent.parent / "data"
IN_PARQUET  = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
OUT_RESUME  = DATA_DIR / "processed" / "07_benchmark_resume.csv"
OUT_CAMPS   = DATA_DIR / "processed" / "07_benchmark_par_campagne.csv"
OUT_CHOIX   = DATA_DIR / "processed" / "07_modele_retenu.txt"

TARGET       = "severite"
CAMPAIGN_COL = "campagne_calc"
BASELINE     = "regression_ordinale"  # modèle de référence pour la contrainte QWK

# Colonnes non-prédictives : identifiants, temps absolu, cible et dérivés de la cible.
EXCLUDE_COLS = {
    "cell_id", "campagne_calc", "date_start", "date_end", "year",
    "severite", "intensite", "binaire", "a_predire", "effort_prospection",
}

# Niveaux de sévérité-phase ordinale (0 absence … 3 grégaire).
SEV_MIN, SEV_MAX = 0, 3


def to_ordinal(y_continuous) -> np.ndarray:
    """Cadre un score continu en niveau ordinal entier borné à [0, 3].

    Arrondi à l'entier le plus proche puis clip. Utilisé par les modèles de
    régression (baseline ordinale, LSTM) pour produire une sévérité-phase.
    """
    rounded = np.rint(np.asarray(y_continuous, dtype=float))
    return np.clip(rounded, SEV_MIN, SEV_MAX).astype(int)


def compute_class_weights(y) -> dict[int, float]:
    """Poids inverse-fréquence par niveau (style sklearn « balanced »).

    `n / (n_classes * count(c))` : surpondère le niveau 3 minoritaire (~6,6 %)
    pour qu'il ne soit pas écrasé, allège les niveaux fréquents. Moyenne ≈ 1.
    """
    counts = pd.Series(y).value_counts()
    n = len(y)
    k = len(counts)
    return {int(c): float(n) / (k * int(cnt)) for c, cnt in counts.items()}


def evaluate_ordinal(y_true, y_pred) -> dict:
    """Métriques ordinales d'un fold : QWK + rappel des niveaux 2–3.

    - `qwk` : quadratic weighted kappa (sklearn, pénalise les écarts ordinaux).
    - `recall_23` : rappel sur les vrais niveaux 2–3 (« ne pas manquer un foyer »),
      cible prioritaire de `select_robust`. NaN si aucun vrai 2–3 dans le fold.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)

    # QWK indéfini sur un fold dégénéré (un seul niveau en commun) → NaN, agrégé
    # par nanmean en aval. On tait le warning sklearn correspondant (bruit).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        qwk = float(cohen_kappa_score(
            y_true, y_pred, weights="quadratic", labels=[0, 1, 2, 3]
        ))

    foyer = np.isin(y_true, (2, 3))
    if foyer.any():
        recall_23 = float(
            (np.isin(y_pred[foyer], (2, 3))).sum() / foyer.sum()
        )
    else:
        recall_23 = float("nan")

    return {"qwk": round(qwk, 4), "recall_23": round(recall_23, 4)}


def aggregate_model_metrics(per_fold, modele: str, complexite: int) -> dict:
    """Agrège les métriques par fold d'un modèle en une ligne pour `select_robust`.

    `per_fold` : liste de dicts `{campagne_calc, qwk, recall_23}` (un par fold).
    Retourne `{modele, recall_23, qwk, variance_inter_folds, pire_campagne,
    complexite}` — schéma exact consommé par `validation_seams.select_robust`.

    Robustesse jugée sur la dispersion (variance inter-folds) et la pire campagne,
    pas sur la meilleure moyenne (PRD §20). Folds sans vrai niveau 2–3 (recall_23
    NaN) sont ignorés par les agrégats.
    """
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
# Registre des modèles du benchmark (PRD §17)
# ---------------------------------------------------------------------------

@dataclass
class ModelSpec:
    """Spécification d'un modèle du benchmark.

    - `framing` : « regression » (score continu → `to_ordinal`) ou « multiclass »
      (classification directe 0–3) ;
    - `complexite` : indice de simplicité/interprétabilité, tie-break de
      `select_robust` (plus bas = plus interprétable) ;
    - `factory` : fabrique paresseuse de l'estimateur (instanciée seulement à
      l'entraînement, garde l'import du module léger).
    """
    framing: Literal["regression", "multiclass"]
    complexite: int
    factory: Callable[[], object]


def build_models(
    n_estimators: int = 300,
    n_jobs: int = -1,
    include_lstm: bool = True,
) -> dict[str, ModelSpec]:
    """Registre des modèles du benchmark, cadrés par modèle (PRD §17).

    Complexités croissantes (tie-break simplicité de `select_robust`) : régression
    ordinale (1) < arbres (3–4) < LSTM (5). Les estimateurs sont fabriqués
    paresseusement par `factory`.

    Leviers de coût (mode léger) :
      - `n_estimators` : nombre d'arbres des ensembles (RF/XGBoost/LightGBM/CatBoost) ;
      - `n_jobs` : cœurs utilisés (-1 = tous ; baisser pour moins chauffer) ;
      - `include_lstm` : inclure ou non le LSTM torch (le plus lent/capricieux).
    """
    def _regression_ordinale():
        from sklearn.linear_model import Ridge
        return Ridge(alpha=1.0)

    def _random_forest():
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            n_estimators=n_estimators, class_weight="balanced_subsample",
            random_state=42, n_jobs=n_jobs,
        )

    def _xgboost():
        from xgboost import XGBClassifier
        # Sans num_class/objective forcés : XGBoost infère le nombre de classes.
        return XGBClassifier(
            n_estimators=n_estimators, learning_rate=0.05, max_depth=6,
            random_state=42, n_jobs=n_jobs, tree_method="hist",
        )

    def _lightgbm():
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=n_estimators, learning_rate=0.05, num_leaves=31,
            class_weight="balanced", random_state=42, n_jobs=n_jobs, verbose=-1,
        )

    def _catboost():
        from catboost import CatBoostClassifier
        return CatBoostClassifier(
            loss_function="MultiClass", iterations=n_estimators, learning_rate=0.05,
            depth=6, random_seed=42, auto_class_weights="Balanced",
            thread_count=(n_jobs if n_jobs and n_jobs > 0 else -1), verbose=False,
        )

    def _lstm():
        from lstm_ordinal import LSTMOrdinalRegressor
        return LSTMOrdinalRegressor(random_state=42)

    models = {
        "regression_ordinale": ModelSpec("regression", 1, _regression_ordinale),
        "random_forest":       ModelSpec("multiclass", 3, _random_forest),
        "lightgbm":            ModelSpec("multiclass", 4, _lightgbm),
        "xgboost":             ModelSpec("multiclass", 4, _xgboost),
        "catboost":            ModelSpec("multiclass", 4, _catboost),
    }
    if include_lstm:
        models["lstm"] = ModelSpec("regression", 5, _lstm)
    return models


# ---------------------------------------------------------------------------
# Orchestration walk-forward du benchmark
# ---------------------------------------------------------------------------

def _fit_predict(spec: ModelSpec, X_tr, y_tr, X_te) -> np.ndarray:
    """Entraîne un modèle sur un fold et prédit une sévérité ordinale 0–3.

    Cadrage par modèle : « regression » → score continu arrondi (`to_ordinal`),
    pondéré par classe ; « multiclass » → labels prédits directement (pondération
    de classe portée par l'estimateur).
    """
    model = spec.factory()
    if spec.framing == "regression":
        weights = compute_class_weights(y_tr)
        sample_weight = np.array([weights[int(v)] for v in y_tr], dtype=float)
        model.fit(X_tr, y_tr, sample_weight=sample_weight)
        return to_ordinal(model.predict(X_te))

    # Multiclasse : encodage des labels en classes contiguës 0..k-1 (XGBoost ≥ 2.0
    # exige des classes contiguës ; inoffensif pour LightGBM/RF/CatBoost), puis
    # décodage des prédictions vers les niveaux d'origine 0–3.
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder().fit(y_tr)
    model.fit(X_tr, le.transform(y_tr))
    y_pred = le.inverse_transform(np.asarray(model.predict(X_te)).ravel())
    return np.asarray(y_pred, dtype=int)


def run_benchmark(
    df: pd.DataFrame,
    feature_cols: list[str],
    target: str,
    campaign_col: str,
    models: dict[str, ModelSpec] | None = None,
    return_detail: bool = False,
):
    """Benchmark walk-forward : entraîne et évalue chaque modèle par fold.

    Folds générés par `walk_forward_split` (#06, saut 2023-2024). Pour chaque
    modèle et chaque fold, entraînement sur les campagnes antérieures et
    évaluation ordinale sur la campagne test. Retourne une ligne par modèle au
    schéma de `select_robust` (+ `n_folds`), prête pour la sélection.

    Avec `return_detail=True`, retourne aussi le détail ventilé par
    `(modele, campagne_calc)` — support du rapport par campagne (#07/#08).
    """
    if models is None:
        models = build_models()

    campagnes = df[campaign_col].unique()
    folds = walk_forward_split(campagnes)

    rows = []
    detail_rows = []
    for name, spec in models.items():
        per_fold = []
        for train_camps, test_camp in folds:
            tr = df[df[campaign_col].isin(train_camps)]
            te = df[df[campaign_col] == test_camp]
            try:
                y_pred = _fit_predict(
                    spec, tr[feature_cols], tr[target].to_numpy(int),
                    te[feature_cols],
                )
                m = evaluate_ordinal(te[target].to_numpy(int), y_pred)
            except Exception as exc:  # noqa: BLE001  — un modèle ne doit pas tuer le benchmark
                print(f"  [!] {name} a échoué sur {test_camp} : {exc}")
                m = {"qwk": float("nan"), "recall_23": float("nan")}
            per_fold.append({"campagne_calc": test_camp, **m})
            detail_rows.append({"modele": name, "campagne_calc": test_camp, **m})
        row = aggregate_model_metrics(per_fold, modele=name, complexite=spec.complexite)
        row["n_folds"] = len(per_fold)
        rows.append(row)

    summary = pd.DataFrame(rows)
    if return_detail:
        return summary, pd.DataFrame(detail_rows)
    return summary


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Colonnes prédictives : tout sauf identifiants, temps absolu, cible et dérivés."""
    return [c for c in df.columns if c not in EXCLUDE_COLS]


# ---------------------------------------------------------------------------
# Orchestration I/O (#07) — non testée unitairement (entraînement réel lourd)
# ---------------------------------------------------------------------------

def run() -> None:
    print(f"Chargement table d'entraînement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)

    # Observées uniquement : la surface de prédiction (severite NaN) n'entraîne pas.
    obs = df[df[TARGET].notna()].copy()
    obs[TARGET] = obs[TARGET].astype(int)
    print(f"Lignes observées : {len(obs)} / {len(df)} "
          f"(campagnes : {obs[CAMPAIGN_COL].nunique()})")

    feature_cols = get_feature_columns(obs)
    # Imputation médiane : Ridge/RF/LSTM n'acceptent pas les NaN des lags précoces.
    obs[feature_cols] = obs[feature_cols].fillna(obs[feature_cols].median(numeric_only=True))

    # Leviers de coût (mode léger) pilotés par variables d'environnement :
    #   BENCH_N_ESTIMATORS (défaut 300), BENCH_N_JOBS (défaut -1 = tous les cœurs),
    #   BENCH_LSTM (0 pour retirer le LSTM torch).
    n_estimators = int(os.environ.get("BENCH_N_ESTIMATORS", "300"))
    n_jobs       = int(os.environ.get("BENCH_N_JOBS", "-1"))
    include_lstm = os.environ.get("BENCH_LSTM", "1") != "0"
    models = build_models(n_estimators=n_estimators, n_jobs=n_jobs,
                          include_lstm=include_lstm)

    print(f"\n=== Benchmark walk-forward ({len(feature_cols)} features) ===")
    print(f"Config : n_estimators={n_estimators}, n_jobs={n_jobs}, "
          f"lstm={'oui' if include_lstm else 'non'}, modèles={list(models)}")
    summary, detail = run_benchmark(
        obs, feature_cols=feature_cols, target=TARGET,
        campaign_col=CAMPAIGN_COL, models=models, return_detail=True,
    )

    # Contrainte QWK = QWK du modèle baseline (régression ordinale).
    base_row = summary.loc[summary["modele"] == BASELINE]
    baseline_qwk = float(base_row["qwk"].iloc[0]) if len(base_row) else 0.0
    classement = select_robust(summary, baseline_qwk=baseline_qwk)

    summary = summary.sort_values("recall_23", ascending=False).reset_index(drop=True)
    print("\n=== Résumé par modèle ===")
    print(summary.to_string(index=False))
    print(f"\nContrainte QWK ≥ baseline ({BASELINE}) = {baseline_qwk:.4f}")
    print(f"Classement select_robust : {classement}")
    retenu = classement[0] if classement else "(aucun éligible)"
    print(f"Modèle retenu : {retenu}")

    OUT_RESUME.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_RESUME, index=False)
    detail.to_csv(OUT_CAMPS, index=False)
    OUT_CHOIX.write_text(
        f"baseline_qwk={baseline_qwk:.4f}\n"
        f"classement={classement}\n"
        f"modele_retenu={retenu}\n",
        encoding="utf-8",
    )
    print(f"\nSortie résumé        : {OUT_RESUME}")
    print(f"Sortie par campagne  : {OUT_CAMPS}")
    print(f"Sortie choix modèle  : {OUT_CHOIX}")


if __name__ == "__main__":
    run()
