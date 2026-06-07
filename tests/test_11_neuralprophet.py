"""Tests unitaires et intégration — Issue #11 : NeuralProphet multi-horizon."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import neuralprophet_11 as pipeline

DATA_DIR     = Path(__file__).parent.parent / "data"
PARQUET_06   = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
RAPPORT_CSV  = DATA_DIR / "processed" / "11_rapport_walk_forward.csv"
DECISION_CSV = DATA_DIR / "processed" / "11_decision_deploiement.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_df() -> pd.DataFrame:
    """Table synthétique : 2 campagnes train + 2 validation × 5 régions × 3 décades."""
    rng = np.random.default_rng(0)
    rows = []
    for camp, split in [
        ("2014-2015", "train"),
        ("2015-2016", "train"),
        ("2016-2017", "validation"),
        ("2017-2018", "validation"),
    ]:
        for rn in range(1, 6):
            for dec in [1, 10, 20]:
                rows.append({
                    "rn_num":             rn,
                    "rn_nom":             f"RN{rn}",
                    "campagne_calc":      camp,
                    "campagne_decade":    dec,
                    "split":             split,
                    "effort_prospection": int(rng.integers(0, 5)),
                    "label":              int(rng.integers(0, 2)),
                })
    df = pd.DataFrame(rows)
    df["rn_num"] = df["rn_num"].astype("Int64")
    df["label"]  = df["label"].astype("Int64")
    return df


# ---------------------------------------------------------------------------
# decode_decade_to_date
# ---------------------------------------------------------------------------

def test_decode_decade_to_date_premiere_decade():
    ts = pipeline.decode_decade_to_date("2016-2017", 1)
    assert ts == pd.Timestamp("2016-10-01")


def test_decode_decade_to_date_fin_octobre():
    ts = pipeline.decode_decade_to_date("2016-2017", 3)
    assert ts == pd.Timestamp("2016-10-21")


def test_decode_decade_to_date_changement_annee():
    """Décade 10 = 1er janvier de start_year+1."""
    ts = pipeline.decode_decade_to_date("2016-2017", 10)
    assert ts == pd.Timestamp("2017-01-01")


def test_decode_decade_to_date_derniere_decade():
    """Décade 30 = 21 juillet de start_year+1."""
    ts = pipeline.decode_decade_to_date("2016-2017", 30)
    assert ts == pd.Timestamp("2017-07-21")


def test_decode_decade_to_date_novembre():
    """Décade 4 = 1er novembre de start_year."""
    ts = pipeline.decode_decade_to_date("2010-2011", 4)
    assert ts == pd.Timestamp("2010-11-01")


def test_decode_decade_to_date_ordre_croissant():
    """Les 30 décades d'une campagne sont en ordre chronologique strict."""
    dates = [pipeline.decode_decade_to_date("2015-2016", d) for d in range(1, 31)]
    assert all(dates[i] < dates[i + 1] for i in range(len(dates) - 1))


# ---------------------------------------------------------------------------
# prepare_panel_df
# ---------------------------------------------------------------------------

def test_prepare_panel_df_colonnes():
    df = _synthetic_df()
    panel = pipeline.prepare_panel_df(df)
    assert {"ds", "y", "ID"} <= set(panel.columns)


def test_prepare_panel_df_nan_pour_inference():
    """Lignes split=inference → y=NaN dans le panel."""
    df = _synthetic_df()
    inf_row = pd.DataFrame([{
        "rn_num": 1, "rn_nom": "RN1",
        "campagne_calc": "2023-2024", "campagne_decade": 1,
        "split": "inference", "effort_prospection": 0, "label": pd.NA,
    }])
    inf_row["rn_num"] = inf_row["rn_num"].astype("Int64")
    inf_row["label"]  = inf_row["label"].astype("Int64")
    df_full = pd.concat([df, inf_row], ignore_index=True)

    panel = pipeline.prepare_panel_df(df_full)
    target_ds = pipeline.decode_decade_to_date("2023-2024", 1)
    inf_panel = panel[panel["ds"] == target_ds]
    assert inf_panel["y"].isna().all(), "Les lignes inference doivent avoir y=NaN"


def test_prepare_panel_df_trié():
    """Panel trié par (ID, ds)."""
    df = _synthetic_df()
    panel = pipeline.prepare_panel_df(df)
    for _, grp in panel.groupby("ID"):
        assert grp["ds"].is_monotonic_increasing


def test_prepare_panel_df_id_est_string():
    df = _synthetic_df()
    panel = pipeline.prepare_panel_df(df)
    # pandas 2.x retourne StringDtype ; on vérifie juste que c'est string-compatible
    assert pd.api.types.is_string_dtype(panel["ID"])


# ---------------------------------------------------------------------------
# walk_forward (découpage identique à lgbm_baseline_07)
# ---------------------------------------------------------------------------

def test_walk_forward_no_leakage():
    """Aucune campagne de validation n'apparaît dans le train du même fold."""
    from lgbm_baseline_07 import walk_forward_folds
    df = _synthetic_df()
    labeled = df[df["split"].isin({"train", "validation"})].copy()
    folds = walk_forward_folds(labeled)
    for df_train, df_val, val_camp in folds:
        assert val_camp not in df_train["campagne_calc"].unique()


def test_walk_forward_deux_folds():
    """La fixture synthétique produit 2 folds (2 campagnes de validation)."""
    from lgbm_baseline_07 import walk_forward_folds
    df = _synthetic_df()
    labeled = df[df["split"].isin({"train", "validation"})].copy()
    folds = walk_forward_folds(labeled)
    assert len(folds) == 2


# ---------------------------------------------------------------------------
# evaluate_horizon
# ---------------------------------------------------------------------------

def test_evaluate_horizon_colonnes():
    df_preds = pd.DataFrame({
        "y":      [1, 0, 1, 0, 1, 0],
        "pred_1": [0.9, 0.1, 0.8, 0.2, 0.7, 0.3],
    })
    result = pipeline.evaluate_horizon(df_preds, step=1)
    assert {"auc_roc", "precision", "recall", "f1", "threshold"} <= result.keys()


def test_evaluate_horizon_auc_parfait():
    df_preds = pd.DataFrame({
        "y":      [1, 1, 0, 0],
        "pred_1": [0.9, 0.8, 0.2, 0.1],
    })
    result = pipeline.evaluate_horizon(df_preds, step=1)
    assert result["auc_roc"] == pytest.approx(1.0)


def test_evaluate_horizon_nan_si_monoclasse():
    """AUC = NaN si une seule classe présente."""
    df_preds = pd.DataFrame({
        "y":      [1, 1, 1],
        "pred_1": [0.9, 0.8, 0.7],
    })
    result = pipeline.evaluate_horizon(df_preds, step=1)
    assert np.isnan(result["auc_roc"])


def test_evaluate_horizon_colonne_absente():
    """Colonne pred_{k} absente → dict de NaN (pas d'exception)."""
    df_preds = pd.DataFrame({"y": [1, 0]})
    result = pipeline.evaluate_horizon(df_preds, step=5)
    assert np.isnan(result["auc_roc"])


def test_evaluate_horizon_ignore_nan_y():
    """Lignes avec y=NaN exclues du calcul."""
    df_preds = pd.DataFrame({
        "y":      [1.0, float("nan"), 0.0, 1.0],
        "pred_1": [0.9, 0.5,          0.2, 0.8],
    })
    result = pipeline.evaluate_horizon(df_preds, step=1)
    assert not np.isnan(result["auc_roc"])


# ---------------------------------------------------------------------------
# Tests d'intégration — skip si parquets absents
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rapport():
    if not RAPPORT_CSV.exists():
        pytest.skip("Rapport #11 absent — lancer : python src/neuralprophet_11.py")
    return pd.read_csv(RAPPORT_CSV)


@pytest.fixture(scope="module")
def decision():
    if not DECISION_CSV.exists():
        pytest.skip("Décision #11 absente — lancer : python src/neuralprophet_11.py")
    return pd.read_csv(DECISION_CSV)


def test_rapport_trois_horizons_presentes(rapport):
    for h in ["decadaire", "mensuel", "saisonnier"]:
        assert f"auc_roc_{h}" in rapport.columns, f"Colonne auc_roc_{h} absente"


def test_rapport_contient_global(rapport):
    assert "GLOBAL" in rapport["campagne_calc"].values


def test_rapport_colonnes_meta(rapport):
    assert {"campagne_calc", "n_positifs", "n_negatifs"} <= set(rapport.columns)


def test_rapport_auc_decadaire_positif(rapport):
    par_camp = rapport[rapport["campagne_calc"] != "GLOBAL"]
    evaluables = par_camp["auc_roc_decadaire"].dropna()
    assert len(evaluables) > 0, "Aucun fold avec AUC décadaire définie"
    assert (evaluables > 0).all()


def test_rapport_threshold_dans_plage(rapport):
    for h in ["decadaire", "mensuel", "saisonnier"]:
        col = f"threshold_{h}"
        if col in rapport.columns:
            thresholds = rapport[col].dropna()
            assert (thresholds >= 0.05).all() and (thresholds <= 0.50).all()


def test_decision_deploiement_colonnes(decision):
    required = {"modele", "horizon", "auc_global", "f1_global", "temps_train_min", "decision"}
    assert required <= set(decision.columns)


def test_decision_contient_neuralprophet(decision):
    assert "NeuralProphet" in decision["modele"].values


def test_decision_contient_trois_horizons(decision):
    np_rows = decision[decision["modele"] == "NeuralProphet"]
    assert set(np_rows["horizon"].values) >= {"decadaire", "mensuel", "saisonnier"}


def test_decision_label_valide(decision):
    valid = {"deploy", "keep_lgbm_baseline", "indeterminate"}
    assert set(decision["decision"].unique()) <= valid
