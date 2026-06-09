"""Tests — Issue #04 : Feature engineering à la maille cellule 1 km × décade.

Pipeline #05 construit les features prédictives sur la table cellule × décade (#04 GEE) :
  - `compute_pop`  : compteur de mois consécutifs en Plage d'Optimum Pluviométrique
                     (CHIRPS 50–125 mm/mois), par (cell_id × campagne_calc) ;
  - `build_lags`   : lags temporels D-1/D-2, cumul pluie roulant 2–3 décades,
                     sévérité historique de la cellule (≤ T-1) — sans aucune fuite T+1 ;
  - `AIRE_CODE`    : prédicteur catégoriel conservé tel quel (codes 1–4).
"""

import sys
from pathlib import Path

import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import feature_engineering_05 as pipeline

DATA_DIR    = Path(__file__).parent.parent / "data"
PARQUET_OUT = DATA_DIR / "processed" / "05_features_engineering.parquet"

KEYS = ["cell_id", "campagne_calc", "campagne_decade"]


# ---------------------------------------------------------------------------
# consecutive_counter — compteur de True consécutifs (pure, maille-agnostique)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bools, expected", [
    ([True, True, True],          [1, 2, 3]),
    ([True, True, False, True],   [1, 2, 0, 1]),
    ([False, False, False],       [0, 0, 0]),
    ([False, True, True, True],   [0, 1, 2, 3]),
    ([True],                      [1]),
    ([True, True, None, True],    [1, 2, 0, 1]),   # NaN agit comme rupture
])
def test_consecutive_counter(bools, expected):
    result = pipeline.consecutive_counter(pd.Series(bools))
    assert list(result) == expected, f"{bools!r} → {list(result)!r}, attendu {expected!r}"


# ---------------------------------------------------------------------------
# compute_pop — compteur POP par (cell_id × campagne_calc)
# ---------------------------------------------------------------------------

def _make_pop_df(cell_id, campagne_calc, year_month_chirps: list[tuple]) -> pd.DataFrame:
    """3 décades par mois, chirps_sum_mean = tiers de la pluie mensuelle."""
    rows = []
    d = 1
    for year, month, chirps_monthly in year_month_chirps:
        for part in (1, 2, 3):
            date = pd.Timestamp(f"{year}-{month:02d}-{(part - 1) * 10 + 1:02d}")
            rows.append({
                "cell_id":         cell_id,
                "campagne_calc":   campagne_calc,
                "campagne_decade": d,
                "year":            year,
                "month":           month,
                "decade_part":     part,
                "date_start":      date,
                "date_end":        date + pd.Timedelta(days=9),
                "chirps_sum_mean": chirps_monthly / 3.0,
                "ndvi_mean":       0.5,
                "evi_mean":        0.4,
                "lst_mean":        300.0,
            })
            d += 1
    return pd.DataFrame(rows)


def test_pop_trois_mois_consecutifs():
    """3 mois consécutifs en POP → pop_consecutive = 1, 2, 3 (toutes les décades du mois)."""
    df = _make_pop_df("526_7171", "2010-2011",
                      [(2010, 10, 80), (2010, 11, 90), (2010, 12, 70)])
    result = pipeline.compute_pop(df)
    assert (result[result["month"] == 10]["pop_consecutive"] == 1).all()
    assert (result[result["month"] == 11]["pop_consecutive"] == 2).all()
    assert (result[result["month"] == 12]["pop_consecutive"] == 3).all()


def test_pop_bornes_incluses():
    """50 et 125 mm/mois sont inclus dans la POP."""
    df = _make_pop_df("c", "2010-2011", [(2010, 10, 50), (2010, 11, 125)])
    result = pipeline.compute_pop(df)
    assert result[result["month"] == 10]["pop_consecutive"].iloc[0] == 1
    assert result[result["month"] == 11]["pop_consecutive"].iloc[0] == 2


def test_pop_reinitialise_par_campagne():
    """Le compteur repart à 1 au début d'une nouvelle campagne pour la même cellule."""
    df = pd.concat([
        _make_pop_df("c", "2010-2011", [(2010, 10, 80), (2010, 11, 80)]),
        _make_pop_df("c", "2011-2012", [(2011, 10, 90)]),
    ], ignore_index=True)
    result = pipeline.compute_pop(df)
    camp10 = result[result["campagne_calc"] == "2010-2011"]
    camp11 = result[result["campagne_calc"] == "2011-2012"]
    assert camp10[camp10["month"] == 11]["pop_consecutive"].iloc[0] == 2
    assert camp11[camp11["month"] == 10]["pop_consecutive"].iloc[0] == 1


# ---------------------------------------------------------------------------
# build_lags — lags temporels par cellule, anti-fuite T+1
# ---------------------------------------------------------------------------

def _make_lag_df(cells=("a", "b"), n_decades=5, campagne="2010-2011") -> pd.DataFrame:
    """N cellules × n_decades décades consécutives, chirps distinct par cellule/décade."""
    rows = []
    base = pd.Timestamp("2010-10-01")
    for ci, cell in enumerate(cells, start=1):
        for i in range(n_decades):
            rows.append({
                "cell_id":         cell,
                "campagne_calc":   campagne,
                "campagne_decade": i + 1,
                "year": 2010, "month": 10, "decade_part": (i % 3) + 1,
                "date_start":      base + pd.Timedelta(days=10 * i),
                "date_end":        base + pd.Timedelta(days=10 * i + 9),
                "chirps_sum_mean": float(100 * ci + i),
                "ndvi_mean": 0.5, "evi_mean": 0.4, "lst_mean": 300.0,
            })
    return pd.DataFrame(rows)


def test_build_lags_pas_de_fuite_t_plus_1():
    """lag1d à t = valeur de t-1 ; aucune feature ne reflète une décade future."""
    df = _make_lag_df(cells=("a",), n_decades=5)
    result = pipeline.build_lags(df).sort_values("campagne_decade").reset_index(drop=True)
    for i in range(1, len(result)):
        assert result.iloc[i]["chirps_sum_mean_lag1d"] == result.iloc[i - 1]["chirps_sum_mean"]
        if i >= 2:
            assert result.iloc[i]["chirps_sum_mean_lag2d"] == result.iloc[i - 2]["chirps_sum_mean"]


def test_build_lags_premiere_decade_nan():
    """La première décade d'une cellule n'a pas de passé : lags = NaN."""
    df = _make_lag_df(cells=("a", "b"), n_decades=5)
    result = pipeline.build_lags(df)
    for cell in ("a", "b"):
        first = result[result["cell_id"] == cell].sort_values("campagne_decade").iloc[0]
        assert pd.isna(first["chirps_sum_mean_lag1d"])
        assert pd.isna(first["chirps_sum_mean_lag2d"])


def test_build_lags_isolation_entre_cellules():
    """Le lag de la cellule a ne contamine pas la cellule b."""
    df = _make_lag_df(cells=("a", "b"), n_decades=5)
    result = pipeline.build_lags(df)
    b_first = result[result["cell_id"] == "b"].sort_values("campagne_decade").iloc[0]
    assert pd.isna(b_first["chirps_sum_mean_lag1d"])


def test_build_lags_cumul_pluie_roulant():
    """chirps_cumul_2d/3d = somme roulante des 2–3 décades jusqu'à T inclus (≤ T)."""
    df = _make_lag_df(cells=("a",), n_decades=5)   # chirps = 100,101,102,103,104
    result = pipeline.build_lags(df).sort_values("campagne_decade").reset_index(drop=True)
    # cumul_2d à T = chirps[T] + chirps[T-1]
    assert result.iloc[1]["chirps_cumul_2d"] == pytest.approx(100 + 101)
    assert result.iloc[4]["chirps_cumul_2d"] == pytest.approx(103 + 104)
    # cumul_3d à T = chirps[T] + chirps[T-1] + chirps[T-2]
    assert result.iloc[2]["chirps_cumul_3d"] == pytest.approx(100 + 101 + 102)
    # Fenêtre incomplète en début de série → NaN (pas de fuite, pas de valeur partielle)
    assert pd.isna(result.iloc[0]["chirps_cumul_2d"])
    assert pd.isna(result.iloc[1]["chirps_cumul_3d"])


def _make_severite_labels(cell, campagne, severites: list[int]) -> pd.DataFrame:
    """Labels #03 minimaux : une sévérité par décade pour une cellule."""
    return pd.DataFrame([
        {"cell_id": cell, "campagne_calc": campagne, "campagne_decade": d + 1,
         "severite": s}
        for d, s in enumerate(severites)
    ])


def test_build_lags_severite_historique():
    """severite_lag1 à T = sévérité de la cellule à T-1 (strictement passé)."""
    df = _make_lag_df(cells=("a",), n_decades=5)
    labels = _make_severite_labels("a", "2010-2011", [0, 1, 2, 3, 1])
    result = pipeline.build_lags(df, labels=labels).sort_values("campagne_decade").reset_index(drop=True)

    assert result.iloc[2]["severite_lag1"] == 1   # T=3 → sévérité de T=2
    assert result.iloc[3]["severite_lag2"] == 1   # T=4 → sévérité de T=2
    assert pd.isna(result.iloc[0]["severite_lag1"])   # première décade : pas de passé


def test_build_lags_ne_fuit_pas_la_cible_courante():
    """La sévérité de la décade T (la cible) ne doit pas rester dans les features."""
    df = _make_lag_df(cells=("a",), n_decades=5)
    labels = _make_severite_labels("a", "2010-2011", [0, 1, 2, 3, 1])
    result = pipeline.build_lags(df, labels=labels)
    assert "severite" not in result.columns, "cible courante présente → fuite vers le modèle"


def test_build_lags_cellule_non_prospectee_severite_nan():
    """Cellule absente des labels : severite_lag1 = NaN (pas d'erreur)."""
    df = _make_lag_df(cells=("a", "b"), n_decades=3)
    labels = _make_severite_labels("a", "2010-2011", [0, 1, 2])   # b non prospectée
    result = pipeline.build_lags(df, labels=labels)
    assert result[result["cell_id"] == "b"]["severite_lag1"].isna().all()


# ---------------------------------------------------------------------------
# AIRE_CODE — prédicteur catégoriel conservé
# ---------------------------------------------------------------------------

def test_aire_code_conserve_comme_predicteur():
    """AIRE_CODE (codes 1–4) traverse compute_pop puis build_lags sans être perdu."""
    df = _make_lag_df(cells=("a",), n_decades=4)
    df["AIRE_CODE"] = 4
    out = pipeline.build_lags(df)
    assert "AIRE_CODE" in out.columns
    assert (out["AIRE_CODE"] == 4).all()


# ---------------------------------------------------------------------------
# Intégration — requiert le parquet de sortie #05 (skip sinon)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def df_out():
    if not PARQUET_OUT.exists():
        pytest.skip("Parquet #05 absent — lancer d'abord : python src/feature_engineering_05.py")
    return pd.read_parquet(PARQUET_OUT)


def test_maille_cellule_integration(df_out):
    assert set(KEYS) <= set(df_out.columns)
    assert "region_id" not in df_out.columns   # migration maille cellule effective


def test_features_attendues_integration(df_out):
    attendues = {"pop_consecutive", "chirps_cumul_2d", "chirps_cumul_3d",
                 "chirps_sum_mean_lag1d", "severite_lag1", "AIRE_CODE"}
    assert attendues <= set(df_out.columns), attendues - set(df_out.columns)


def test_cible_courante_absente_integration(df_out):
    """La sévérité courante (cible) ne doit pas figurer dans la table de features."""
    assert "severite" not in df_out.columns
