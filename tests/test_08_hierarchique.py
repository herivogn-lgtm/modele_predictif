"""Tests unitaires et intégration — Issue #08 : Modèle hiérarchique densité + phase."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import lgbm_hierarchique_08 as pipeline

DATA_DIR    = Path(__file__).parent.parent / "data"
PARQUET_06  = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
PARQUET_02  = DATA_DIR / "processed" / "02_gregarite_potentiel.parquet"
RAPPORT_CSV = DATA_DIR / "processed" / "08_rapport_walk_forward.csv"
MODEL_DEN   = DATA_DIR / "processed" / "08_lgbm_densite.pkl"
MODEL_PHA   = DATA_DIR / "processed" / "08_lgbm_phase.pkl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame minimal imitant la table #06 enrichie (colonnes garanties)."""
    defaults = {
        "rn_num":                    1,
        "rn_nom":                    "RN1",
        "campagne_calc":             "2014-2015",
        "campagne_decade":           5,
        "split":                     "train",
        "effort_prospection":        2,
        "label":                     1,
        pipeline.DENSITY_COL:        50.0,
        pipeline.PHASE_COL:          "S",
    }
    records = [{**defaults, **r} for r in rows]
    df = pd.DataFrame(records)
    df["rn_num"] = df["rn_num"].astype("Int64")
    df["label"]  = df["label"].astype("Int64")
    return df


def _synthetic_df(with_density: bool = True, with_phase: bool = True) -> pd.DataFrame:
    """Table synthétique : 2 campagnes train + 2 campagnes validation × 5 régions × 2 décades."""
    rng = np.random.default_rng(42)
    phases = pipeline.PHASE_CATEGORIES
    rows = []
    for camp, split in [
        ("2014-2015", "train"), ("2015-2016", "train"),
        ("2016-2017", "validation"), ("2017-2018", "validation"),
    ]:
        for rn in range(1, 6):
            for dec in [5, 15]:
                label = int(rng.integers(0, 2))
                rows.append({
                    "rn_num":             rn,
                    "rn_nom":             f"RN{rn}",
                    "campagne_calc":      camp,
                    "campagne_decade":    dec,
                    "split":              split,
                    "effort_prospection": int(rng.integers(0, 5)),
                    "label":              label,
                    pipeline.DENSITY_COL: float(rng.exponential(100)) if (label == 1 and with_density) else np.nan,
                    pipeline.PHASE_COL:   phases[int(rng.integers(0, len(phases)))] if (label == 1 and with_phase) else None,
                    "chirps_sum_mean":    float(rng.uniform(0, 200)),
                })
    df = pd.DataFrame(rows)
    df["rn_num"] = df["rn_num"].astype("Int64")
    df["label"]  = df["label"].astype("Int64")
    return df


def _make_geo_df(n: int = 50) -> pd.DataFrame:
    """GeoDataFrame minimal imitant le parquet #02."""
    rng = np.random.default_rng(7)
    return pd.DataFrame({
        "rn_num":          pd.array(rng.integers(1, 5, n), dtype="Int64"),
        "campagne_calc":   [f"{2014 + i % 3}-{2015 + i % 3}" for i in range(n)],
        "campagne_decade": rng.integers(1, 30, n).tolist(),
        "densite_imago":   rng.exponential(50, n).tolist(),
        "niveau_gregarite": rng.choice(["S", "St", "T", "G", "absent"], n).tolist(),
    })


# ---------------------------------------------------------------------------
# aggregate_densite
# ---------------------------------------------------------------------------

def test_aggregate_densite_colonnes(tmp_path):
    geo_df = _make_geo_df()
    geo_path = tmp_path / "02_geo.parquet"
    geo_df.to_parquet(geo_path)

    result = pipeline.aggregate_densite(geo_path)
    assert {"rn_num", "campagne_calc", "campagne_decade", pipeline.DENSITY_COL} <= set(result.columns)


def test_aggregate_densite_filtre_nan(tmp_path):
    geo_df = _make_geo_df(20)
    geo_df.loc[:5, "densite_imago"] = np.nan  # 6 NaN introduits
    geo_path = tmp_path / "02_geo.parquet"
    geo_df.to_parquet(geo_path)

    result = pipeline.aggregate_densite(geo_path)
    assert result[pipeline.DENSITY_COL].notna().all(), "La médiane ne doit pas être NaN"


def test_aggregate_densite_valeur_mediane(tmp_path):
    geo_df = pd.DataFrame({
        "rn_num":          pd.array([1, 1, 1], dtype="Int64"),
        "campagne_calc":   ["2014-2015"] * 3,
        "campagne_decade": [5, 5, 5],
        "densite_imago":   [10.0, 20.0, 30.0],
        "niveau_gregarite": ["S", "S", "S"],
    })
    geo_path = tmp_path / "02_geo.parquet"
    geo_df.to_parquet(geo_path)

    result = pipeline.aggregate_densite(geo_path)
    assert result[pipeline.DENSITY_COL].iloc[0] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# get_feature_columns
# ---------------------------------------------------------------------------

def test_get_feature_columns_exclut_cibles():
    df = _make_df([{"chirps_sum_mean": 80.0}])
    cols = pipeline.get_feature_columns(df)
    assert pipeline.DENSITY_COL not in cols
    assert pipeline.PHASE_COL not in cols
    assert "chirps_sum_mean" in cols


def test_get_feature_columns_exclut_meta():
    df = _make_df([{}])
    cols = pipeline.get_feature_columns(df)
    for m in pipeline.META_COLS + pipeline.KEY_COLS:
        assert m not in cols


# ---------------------------------------------------------------------------
# evaluate_density
# ---------------------------------------------------------------------------

def test_evaluate_density_output():
    y_true = np.array([10.0, 20.0, 30.0])
    y_pred = np.array([12.0, 18.0, 35.0])
    result = pipeline.evaluate_density(y_true, y_pred)
    assert {"rmse_densite", "mae_densite"} <= result.keys()
    assert result["rmse_densite"] >= 0
    assert result["mae_densite"] >= 0


def test_evaluate_density_perfect():
    y = np.array([5.0, 15.0, 25.0])
    result = pipeline.evaluate_density(y, y)
    assert result["rmse_densite"] == pytest.approx(0.0)
    assert result["mae_densite"]  == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# optimize_threshold_G / evaluate_phase
# ---------------------------------------------------------------------------

def test_optimize_threshold_G_range():
    rng = np.random.default_rng(3)
    n = 60
    y_enc = rng.integers(0, len(pipeline.PHASE_CATEGORIES), n)
    y_prob = rng.dirichlet(np.ones(len(pipeline.PHASE_CATEGORIES)), n)
    t = pipeline.optimize_threshold_G(y_enc, y_prob)
    assert 0.05 <= t <= 0.50


def test_optimize_threshold_G_classe_G_dominante():
    """Quand G domine, le seuil doit capturer la classe G."""
    n = 40
    g_idx = pipeline.PHASE_CATEGORIES.index("G")
    y_enc = np.full(n, g_idx)
    y_prob = np.zeros((n, len(pipeline.PHASE_CATEGORIES)))
    y_prob[:, g_idx] = 0.9
    y_prob[:, 0] = 0.1

    t = pipeline.optimize_threshold_G(y_enc, y_prob)
    result = pipeline.evaluate_phase(y_enc, y_prob, t)
    assert result["recall_G"] >= 0.70


def test_evaluate_phase_output():
    rng = np.random.default_rng(5)
    n = 30
    y_enc = rng.integers(0, len(pipeline.PHASE_CATEGORIES), n)
    y_prob = rng.dirichlet(np.ones(len(pipeline.PHASE_CATEGORIES)), n)
    result = pipeline.evaluate_phase(y_enc, y_prob, threshold_G=0.15)
    assert {"f1_macro_phase", "recall_G", "threshold_G"} <= result.keys()
    assert 0.0 <= result["f1_macro_phase"] <= 1.0
    assert 0.0 <= result["recall_G"] <= 1.0
    assert result["threshold_G"] == pytest.approx(0.15, abs=1e-4)


# ---------------------------------------------------------------------------
# walk_forward_folds
# ---------------------------------------------------------------------------

def test_walk_forward_count_folds():
    df = _synthetic_df()
    folds = pipeline.walk_forward_folds(df)
    assert len(folds) == 2


def test_walk_forward_no_leakage():
    df = _synthetic_df()
    for df_train, df_val, val_camp in pipeline.walk_forward_folds(df):
        assert val_camp not in df_train["campagne_calc"].unique()


def test_walk_forward_expanding_window():
    df = _synthetic_df()
    folds = pipeline.walk_forward_folds(df)
    sizes = [len(f[0]) for f in folds]
    assert sizes[1] > sizes[0]


def test_walk_forward_val_labeled():
    df = _synthetic_df()
    for _, df_val, _ in pipeline.walk_forward_folds(df):
        assert df_val["label"].notna().all()


# ---------------------------------------------------------------------------
# predict_hierarchical
# ---------------------------------------------------------------------------

def _mock_presence_model(predict_value: int):
    """Crée un faux modèle présence qui retourne toujours predict_value."""
    mock = MagicMock()
    prob = 0.9 if predict_value == 1 else 0.1
    mock.predict_proba.return_value = np.array([[1 - prob, prob]])
    return mock


def test_predict_hierarchical_absence_shortcircuit():
    df = _make_df([{"chirps_sum_mean": 100.0}])
    model_pres = _mock_presence_model(predict_value=0)

    mock_density = MagicMock()
    mock_phase   = MagicMock()

    result = pipeline.predict_hierarchical(
        df, model_pres, mock_density, mock_phase,
        threshold_presence=0.5, threshold_G=0.15,
    )
    assert result["presence_pred"].iloc[0] == 0
    assert np.isnan(result["densite_pred"].iloc[0])
    assert result["phase_pred"].iloc[0] is None
    mock_density.predict.assert_not_called()
    mock_phase.predict_proba.assert_not_called()


def test_predict_hierarchical_presence_pipeline():
    df = _make_df([{"chirps_sum_mean": 100.0}])
    model_pres = _mock_presence_model(predict_value=1)

    g_idx = pipeline.PHASE_CATEGORIES.index("G")
    mock_density = MagicMock()
    mock_density.predict.return_value = np.array([42.0])
    mock_phase = MagicMock()
    y_prob_phase = np.zeros((1, len(pipeline.PHASE_CATEGORIES)))
    y_prob_phase[0, 0] = 1.0  # S prédit
    mock_phase.predict_proba.return_value = y_prob_phase

    result = pipeline.predict_hierarchical(
        df, model_pres, mock_density, mock_phase,
        threshold_presence=0.5, threshold_G=0.15,
    )
    assert result["presence_pred"].iloc[0] == 1
    assert result["densite_pred"].iloc[0] == pytest.approx(42.0)
    assert result["phase_pred"].iloc[0] in pipeline.PHASE_CATEGORIES


# ---------------------------------------------------------------------------
# Tests d'intégration — parquets réels requis
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rapport():
    if not RAPPORT_CSV.exists():
        pytest.skip(
            "Rapport #08 absent — lancer d'abord : python src/lgbm_hierarchique_08.py"
        )
    return pd.read_csv(RAPPORT_CSV)


def test_rapport_colonnes_obligatoires(rapport):
    required = {
        "campagne_calc", "n_presence",
        "rmse_densite", "mae_densite",
        "f1_macro_phase", "recall_G", "threshold_G",
    }
    assert required <= set(rapport.columns)


def test_rapport_contient_global(rapport):
    assert "GLOBAL" in rapport["campagne_calc"].values


def test_rapport_recall_G_global(rapport):
    """Critère d'acceptance principal : rappel classe G ≥ 0.70 (global)."""
    recall = rapport.loc[rapport["campagne_calc"] == "GLOBAL", "recall_G"].iloc[0]
    assert not np.isnan(recall), "recall_G GLOBAL est NaN"
    assert recall >= 0.70, f"recall_G global = {recall:.4f} < 0.70"


def test_rapport_rmse_mae_positifs(rapport):
    par_camp = rapport[rapport["campagne_calc"] != "GLOBAL"]
    evaluables_rmse = par_camp["rmse_densite"].dropna()
    evaluables_mae  = par_camp["mae_densite"].dropna()
    if len(evaluables_rmse) > 0:
        assert (evaluables_rmse >= 0).all()
    if len(evaluables_mae) > 0:
        assert (evaluables_mae >= 0).all()


def test_rapport_f1_macro_present(rapport):
    par_camp = rapport[rapport["campagne_calc"] != "GLOBAL"]
    evaluables = par_camp["f1_macro_phase"].dropna()
    assert len(evaluables) > 0, "Aucun fold avec F1-macro défini"
    assert (evaluables >= 0).all() and (evaluables <= 1).all()


def test_modeles_persistes():
    """Les deux modèles #08 sont persistés en fichiers séparés."""
    if not RAPPORT_CSV.exists():
        pytest.skip("Pipeline #08 non exécuté.")
    assert MODEL_DEN.exists(), f"Modèle densité absent : {MODEL_DEN}"
    assert MODEL_PHA.exists(), f"Modèle phase absent : {MODEL_PHA}"
