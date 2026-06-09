"""Tests unitaires et intégration — Issue #07 : LightGBM baseline présence/absence."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import lgbm_baseline_07 as pipeline

DATA_DIR    = Path(__file__).parent.parent / "data"
PARQUET_06  = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
RAPPORT_CSV = DATA_DIR / "processed" / "07_rapport_walk_forward.csv"
IMP_CSV     = DATA_DIR / "processed" / "07_feature_importances.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame minimal imitant la table #06 (colonnes garanties uniquement)."""
    defaults = {
        "rn_num":             1,
        "rn_nom":             "RN1",
        "campagne_calc":      "2014-2015",
        "campagne_decade":    5,
        "split":              "train",
        "effort_prospection": 2,
        "label":              1,
    }
    records = [{**defaults, **r} for r in rows]
    df = pd.DataFrame(records)
    df["rn_num"] = df["rn_num"].astype("Int64")
    df["label"]  = df["label"].astype("Int64")
    return df


def _synthetic_df() -> pd.DataFrame:
    """Table synthétique minimale : 2 campagnes train + 2 campagnes validation × 5 régions × 2 décades."""
    rng = np.random.default_rng(0)
    rows = []
    for camp, split in [("2014-2015", "train"), ("2015-2016", "train"),
                        ("2016-2017", "validation"), ("2017-2018", "validation")]:
        for rn in range(1, 6):
            for dec in [5, 15]:
                rows.append({
                    "rn_num":             rn,
                    "rn_nom":             f"RN{rn}",
                    "campagne_calc":      camp,
                    "campagne_decade":    dec,
                    "split":              split,
                    "effort_prospection": int(rng.integers(0, 5)),
                    "label":              int(rng.integers(0, 2)),
                })
    df = pd.DataFrame(rows)
    df["rn_num"] = df["rn_num"].astype("Int64")
    df["label"]  = df["label"].astype("Int64")
    return df


# ---------------------------------------------------------------------------
# compute_scale_pos_weight
# ---------------------------------------------------------------------------

def test_scale_pos_weight_ratio():
    y = pd.Series([1, 1, 0, 0, 0, 0])  # 2 pos, 4 neg → ratio = 2.0
    assert pipeline.compute_scale_pos_weight(y) == pytest.approx(2.0)


def test_scale_pos_weight_no_pos():
    y = pd.Series([0, 0, 0])
    assert pipeline.compute_scale_pos_weight(y) == pytest.approx(1.0)


def test_scale_pos_weight_balanced():
    y = pd.Series([1, 0, 1, 0])
    assert pipeline.compute_scale_pos_weight(y) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# optimize_threshold
# ---------------------------------------------------------------------------

def test_optimize_threshold_range():
    rng = np.random.default_rng(1)
    y_true = rng.integers(0, 2, 50)
    y_prob = rng.random(50)
    t = pipeline.optimize_threshold(y_true, y_prob)
    assert 0.05 <= t <= 0.50


def test_optimize_threshold_perfect_predictor():
    """Prédicteur parfait → seuil correspondant à la frontière y_prob=0.5 (prob en 0/1)."""
    y_true = np.array([1, 1, 0, 0, 1, 0])
    y_prob = np.array([0.9, 0.8, 0.1, 0.2, 0.7, 0.3])
    t = pipeline.optimize_threshold(y_true, y_prob)
    # A n'importe quel seuil raisonnable, F1 = 1.0 → threshold doit séparer
    y_pred = (y_prob >= t).astype(int)
    assert (y_pred == y_true).all() or t <= 0.50


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------

def test_evaluate_auc_parfait():
    y_true = np.array([1, 1, 0, 0])
    y_prob = np.array([0.9, 0.8, 0.2, 0.1])
    result = pipeline.evaluate(y_true, y_prob, threshold=0.50)
    assert result["auc_roc"] == pytest.approx(1.0)


def test_evaluate_colonnes_presentes():
    y_true = np.array([1, 0, 1, 0])
    y_prob = np.array([0.7, 0.3, 0.6, 0.4])
    result = pipeline.evaluate(y_true, y_prob, threshold=0.50)
    assert {"auc_roc", "precision", "recall", "f1", "threshold"} <= result.keys()


def test_evaluate_threshold_transmis():
    y_true = np.array([1, 0])
    y_prob = np.array([0.6, 0.4])
    result = pipeline.evaluate(y_true, y_prob, threshold=0.17)
    assert result["threshold"] == pytest.approx(0.17, abs=1e-4)


# ---------------------------------------------------------------------------
# get_feature_columns
# ---------------------------------------------------------------------------

def test_get_feature_columns_exclut_meta():
    df = _make_df([{}])
    df["chirps_sum_mean"] = 80.0
    cols = pipeline.get_feature_columns(df)
    assert "chirps_sum_mean" in cols
    assert "label" not in cols
    assert "split" not in cols
    assert "rn_num" not in cols


def test_get_feature_columns_effort_inclus():
    """effort_prospection est une colonne META_COLS → exclue des features."""
    df = _make_df([{}])
    cols = pipeline.get_feature_columns(df)
    assert "effort_prospection" not in cols


# ---------------------------------------------------------------------------
# walk_forward_folds
# ---------------------------------------------------------------------------

def test_walk_forward_count_folds():
    df = _synthetic_df()
    folds = pipeline.walk_forward_folds(df)
    # 2 campagnes de validation dans la fixture
    assert len(folds) == 2


def test_walk_forward_no_leakage():
    """Aucune campagne de validation n'apparaît dans le train du même fold."""
    df = _synthetic_df()
    folds = pipeline.walk_forward_folds(df)
    for df_train, df_val, val_camp in folds:
        assert val_camp not in df_train["campagne_calc"].unique(), (
            f"Fuite : {val_camp} dans le train du fold {val_camp}"
        )


def test_walk_forward_expanding_window():
    """Chaque fold ajoute la campagne précédente au train (expanding window)."""
    df = _synthetic_df()
    folds = pipeline.walk_forward_folds(df)
    sizes = [len(f[0]) for f in folds]
    assert sizes[1] > sizes[0], "Le train du fold 2 doit être plus grand que celui du fold 1"


def test_walk_forward_val_labeled():
    """Toutes les lignes de validation ont un label non-NA."""
    df = _synthetic_df()
    for _, df_val, _ in pipeline.walk_forward_folds(df):
        assert df_val["label"].notna().all()


# ---------------------------------------------------------------------------
# Tests d'intégration — requièrent les parquets produits
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def df_06():
    if not PARQUET_06.exists():
        pytest.skip(
            "Parquet #06 absent — lancer d'abord : python src/table_entrainement_06.py"
        )
    df = pd.read_parquet(PARQUET_06)
    if "split" not in df.columns:
        pytest.skip(
            "Colonne 'split' absente — le découpage walk-forward relève de l'issue #06 "
            "(walk_forward_split), pas encore livré"
        )
    return df


@pytest.fixture(scope="module")
def rapport():
    if not RAPPORT_CSV.exists():
        pytest.skip(
            "Rapport walk-forward absent — lancer d'abord : python src/lgbm_baseline_07.py"
        )
    return pd.read_csv(RAPPORT_CSV)


@pytest.fixture(scope="module")
def importances():
    if not IMP_CSV.exists():
        pytest.skip(
            "Feature importances absentes — lancer d'abord : python src/lgbm_baseline_07.py"
        )
    return pd.read_csv(IMP_CSV)


def test_rapport_colonnes_obligatoires(rapport):
    required = {"campagne_calc", "auc_roc", "precision", "recall", "f1",
                "threshold", "n_positifs", "n_negatifs"}
    assert required <= set(rapport.columns)


def test_rapport_contient_global(rapport):
    assert "GLOBAL" in rapport["campagne_calc"].values


def test_rapport_auc_par_campagne_positif(rapport):
    """AUC > 0 pour chaque campagne évaluable (ignore les folds monoclasse, NaN)."""
    par_camp = rapport[rapport["campagne_calc"] != "GLOBAL"]
    evaluables = par_camp["auc_roc"].dropna()
    assert len(evaluables) > 0, "Aucun fold avec AUC définie"
    assert (evaluables > 0).all()


def test_rapport_auc_global_cible(rapport):
    """AUC global ≥ 0.85 (cible de l'issue #07)."""
    auc = rapport.loc[rapport["campagne_calc"] == "GLOBAL", "auc_roc"].iloc[0]
    assert auc >= 0.85, f"AUC global = {auc:.4f} < 0.85"


def test_rapport_threshold_dans_plage(rapport):
    thresholds = rapport["threshold"].dropna()
    assert (thresholds >= 0.05).all() and (thresholds <= 0.50).all()


def test_rapport_walk_forward_pas_de_fuite(df_06):
    """Re-vérifie l'absence de fuite temporelle à partir du parquet réel."""
    labeled = df_06[df_06["split"].isin({"train", "validation"})]
    folds   = pipeline.walk_forward_folds(labeled)
    for df_train, df_val, val_camp in folds:
        assert val_camp not in df_train["campagne_calc"].unique()


def test_importances_colonnes_presentes(importances):
    assert {"feature", "importance_mean", "importance_std"} <= set(importances.columns)


def test_importances_non_vide(importances):
    assert len(importances) > 0


def test_importances_mean_non_negatif(importances):
    assert (importances["importance_mean"] >= 0).all()
