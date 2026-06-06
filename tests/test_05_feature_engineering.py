"""Tests unitaires — Pipeline #05 : Feature engineering acridologique."""

import sys
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import feature_engineering_05 as pipeline

DATA_DIR    = Path(__file__).parent.parent / "data"
PARQUET_IN  = DATA_DIR / "processed" / "04_variables_environnementales.parquet"
PARQUET_OUT = DATA_DIR / "processed" / "05_features_engineering.parquet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_env_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame minimal imitant le parquet #04."""
    defaults = {
        "region_id": 1,
        "region_nom": "RN1",
        "campaign": "2010-2011",
        "decade_num": 1,
        "year": 2010,
        "month": 10,
        "decade_part": 1,
        "date_start": pd.Timestamp("2010-10-01"),
        "date_end":   pd.Timestamp("2010-10-10"),
        "chirps_sum_mean": 0.0,
        "ndvi_mean": 0.5,
        "evi_mean": 0.4,
        "lst_mean": 300.0,
        "soil_moisture_mean": 0.2,
        "chirps_anomaly_mean": 0.0,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


# ---------------------------------------------------------------------------
# consecutive_counter — 6 séquences pluviométriques connues
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bools, expected", [
    # Séquence 1 : 3 mois consécutifs en POP
    ([True, True, True],          [1, 2, 3]),
    # Séquence 2 : rupture au milieu
    ([True, True, False, True],   [1, 2, 0, 1]),
    # Séquence 3 : tout hors POP
    ([False, False, False],       [0, 0, 0]),
    # Séquence 4 : démarre après une rupture initiale
    ([False, True, True, True],   [0, 1, 2, 3]),
    # Séquence 5 : valeur unique True
    ([True],                      [1]),
    # Séquence 6 : NaN intercalé agit comme rupture
    ([True, True, None, True],    [1, 2, 0, 1]),
])
def test_consecutive_counter(bools, expected):
    s = pd.Series(bools)
    result = pipeline.consecutive_counter(s)
    assert list(result) == expected, f"Entrée {bools!r} → {list(result)!r}, attendu {expected!r}"


def test_consecutive_counter_preserve_index():
    """L'index de la série d'entrée est préservé en sortie."""
    s = pd.Series([True, False, True], index=[10, 20, 30])
    result = pipeline.consecutive_counter(s)
    assert list(result.index) == [10, 20, 30]


# ---------------------------------------------------------------------------
# compute_pop — compteur POP via agrégation mensuelle
# ---------------------------------------------------------------------------

def _make_pop_df(region_id, campaign, year_month_chirps: list[tuple]) -> pd.DataFrame:
    """Construit un DataFrame de 3 décades par mois avec chirps_sum_mean = tiers de la somme."""
    rows = []
    d = 1
    for year, month, chirps_monthly in year_month_chirps:
        # Répartit la pluie mensuelle en 3 décades égales
        val_per_decade = chirps_monthly / 3.0
        for part in (1, 2, 3):
            date = pd.Timestamp(f"{year}-{month:02d}-{(part - 1) * 10 + 1:02d}")
            rows.append({
                "region_id": region_id,
                "campaign": campaign,
                "year": year,
                "month": month,
                "decade_part": part,
                "decade_num": d,
                "date_start": date,
                "date_end":   date + pd.Timedelta(days=9),
                "chirps_sum_mean": val_per_decade,
                "chirps_anomaly_mean": 0.0,
                "ndvi_mean": 0.5,
                "evi_mean": 0.4,
                "lst_mean": 300.0,
                "soil_moisture_mean": 0.2,
            })
            d += 1
    return pd.DataFrame(rows)


def test_pop_trois_mois_consecutifs():
    """3 mois consécutifs à 80 mm/mois → pop_consecutive = [1, 2, 3] pour chaque décade."""
    df = _make_pop_df(1, "2010-2011", [(2010, 10, 80), (2010, 11, 90), (2010, 12, 70)])
    result = pipeline.compute_pop(df)

    # Les 3 décades d'octobre → pop_consecutive = 1
    oct_rows = result[(result["year"] == 2010) & (result["month"] == 10)]
    assert (oct_rows["pop_consecutive"] == 1).all()

    # Novembre → 2
    nov_rows = result[(result["year"] == 2010) & (result["month"] == 11)]
    assert (nov_rows["pop_consecutive"] == 2).all()

    # Décembre → 3
    dec_rows = result[(result["year"] == 2010) & (result["month"] == 12)]
    assert (dec_rows["pop_consecutive"] == 3).all()


def test_pop_rupture_remet_a_zero():
    """Mois hors POP (40 mm) remet le compteur à 0, suivi d'un nouveau mois POP → 1."""
    df = _make_pop_df(1, "2010-2011", [
        (2010, 10, 80),   # in POP
        (2010, 11, 40),   # hors POP → reset
        (2010, 12, 60),   # in POP de nouveau
    ])
    result = pipeline.compute_pop(df)
    assert result[result["month"] == 10]["pop_consecutive"].iloc[0] == 1
    assert result[result["month"] == 11]["pop_consecutive"].iloc[0] == 0
    assert result[result["month"] == 12]["pop_consecutive"].iloc[0] == 1


def test_pop_bornes_incluses():
    """50 mm/mois et 125 mm/mois sont inclus dans la POP."""
    df = _make_pop_df(1, "2010-2011", [(2010, 10, 50), (2010, 11, 125)])
    result = pipeline.compute_pop(df)
    assert result[result["month"] == 10]["pop_consecutive"].iloc[0] == 1
    assert result[result["month"] == 11]["pop_consecutive"].iloc[0] == 2


def test_pop_reinitialise_par_campagne():
    """Le compteur repart à 1 en début de nouvelle campagne, même si la fin de l'ancienne était en POP."""
    df = pd.concat([
        _make_pop_df(1, "2010-2011", [(2010, 10, 80), (2010, 11, 80)]),
        _make_pop_df(1, "2011-2012", [(2011, 10, 90)]),  # nouvelle campagne
    ], ignore_index=True)
    result = pipeline.compute_pop(df)

    camp_2010 = result[result["campaign"] == "2010-2011"]
    camp_2011 = result[result["campaign"] == "2011-2012"]
    # Fin de la campagne 2010-2011 → compteur = 2 pour novembre
    assert camp_2010[camp_2010["month"] == 11]["pop_consecutive"].iloc[0] == 2
    # Début de la campagne 2011-2012 → repart à 1
    assert camp_2011[camp_2011["month"] == 10]["pop_consecutive"].iloc[0] == 1


# ---------------------------------------------------------------------------
# compute_temporal_lags — absence de fuite et isolation entre régions
# ---------------------------------------------------------------------------

def _make_lag_df(n_regions=2, n_decades=5) -> pd.DataFrame:
    """DataFrame avec 2 régions × 5 décades."""
    rows = []
    base = pd.Timestamp("2010-10-01")
    for rid in range(1, n_regions + 1):
        for i in range(n_decades):
            rows.append({
                "region_id": rid,
                "campaign": "2010-2011",
                "year": 2010, "month": 10, "decade_part": (i % 3) + 1,
                "decade_num": i + 1,
                "date_start": base + pd.Timedelta(days=10 * i),
                "date_end":   base + pd.Timedelta(days=10 * i + 9),
                "chirps_sum_mean": float(10 * rid + i),
                "ndvi_mean": 0.5,
                "evi_mean": 0.4,
                "lst_mean": 300.0,
                "soil_moisture_mean": 0.2,
            })
    return pd.DataFrame(rows)


def test_temporal_lags_pas_de_fuite():
    """lag1d à t ne doit pas contenir la valeur de t ou d'un instant futur."""
    df = _make_lag_df(n_regions=1, n_decades=5)
    result = pipeline.compute_temporal_lags(df)
    # Les valeurs du lag1d décalées de 1 correspondent à la feature d-1
    for i in range(1, len(result)):
        assert result.iloc[i]["chirps_sum_mean_lag1d"] == result.iloc[i - 1]["chirps_sum_mean"]


def test_temporal_lags_premiere_ligne_nan():
    """La première décade de chaque région n'a pas de passé : lag1d = NaN."""
    df = _make_lag_df(n_regions=2, n_decades=5)
    result = pipeline.compute_temporal_lags(df)
    for rid in [1, 2]:
        first_row = result[result["region_id"] == rid].sort_values("date_start").iloc[0]
        assert pd.isna(first_row["chirps_sum_mean_lag1d"])
        assert pd.isna(first_row["chirps_sum_mean_lag2d"])
        assert pd.isna(first_row["chirps_sum_mean_lag1m"])


def test_temporal_lags_isolation_entre_regions():
    """Le lag de la région 1 ne doit pas contaminer la région 2."""
    df = _make_lag_df(n_regions=2, n_decades=5)
    result = pipeline.compute_temporal_lags(df)
    # La première décade de la région 2 doit avoir lag1d=NaN (pas la dernière valeur de la région 1)
    r2_first = result[result["region_id"] == 2].sort_values("date_start").iloc[0]
    assert pd.isna(r2_first["chirps_sum_mean_lag1d"])


def test_temporal_lags_colonnes_presentes():
    """Toutes les colonnes de lag attendues sont créées."""
    df = _make_lag_df()
    result = pipeline.compute_temporal_lags(df)
    for feat in pipeline.TEMPORAL_LAG_FEATURES:
        if feat not in df.columns:
            continue
        for sfx in ("_lag1d", "_lag2d", "_lag1m"):
            col = f"{feat}{sfx}"
            assert col in result.columns, f"Colonne manquante : {col}"


# ---------------------------------------------------------------------------
# compute_spatial_lags — moyenne des voisins contigus
# ---------------------------------------------------------------------------

def _make_spatial_df(dates: list[pd.Timestamp], values_by_region: dict) -> pd.DataFrame:
    """DataFrame avec N dates × M régions."""
    rows = []
    for dt in dates:
        for rid, vals in values_by_region.items():
            idx = dates.index(dt)
            rows.append({
                "region_id": rid,
                "date_start": dt,
                "chirps_sum_mean": vals[idx],
                "ndvi_mean": 0.5,
                "evi_mean": 0.4,
                "lst_mean": 300.0,
                "soil_moisture_mean": 0.2,
            })
    return pd.DataFrame(rows)


def test_spatial_lag_moyenne_deux_voisins():
    """Région 1 avec voisins 2 et 3 → spatial_lag = moyenne des valeurs 2 et 3."""
    dates = [pd.Timestamp("2010-10-01")]
    df = _make_spatial_df(dates, {1: [10.0], 2: [20.0], 3: [30.0]})
    neighbors = {1: [2, 3], 2: [1], 3: [1]}

    result = pipeline.compute_spatial_lags(df, neighbors, ["chirps_sum_mean"])
    val = result[result["region_id"] == 1]["chirps_sum_mean_spatial_lag"].iloc[0]
    assert abs(val - 25.0) < 1e-9, f"Attendu 25.0, obtenu {val}"


def test_spatial_lag_region_isolee_nan():
    """Région sans voisin dans le dict → spatial_lag = NaN (aucune erreur)."""
    dates = [pd.Timestamp("2010-10-01")]
    df = _make_spatial_df(dates, {1: [10.0], 2: [20.0]})
    neighbors = {1: [], 2: []}  # aucun voisin

    result = pipeline.compute_spatial_lags(df, neighbors, ["chirps_sum_mean"])
    assert result["chirps_sum_mean_spatial_lag"].isna().all()


def test_spatial_lag_ignore_nan_voisin():
    """Si un voisin a NaN pour la feature, il est ignoré dans la moyenne."""
    dates = [pd.Timestamp("2010-10-01")]
    df = _make_spatial_df(dates, {1: [10.0], 2: [float("nan")], 3: [30.0]})
    neighbors = {1: [2, 3], 2: [1], 3: [1]}

    result = pipeline.compute_spatial_lags(df, neighbors, ["chirps_sum_mean"])
    val = result[result["region_id"] == 1]["chirps_sum_mean_spatial_lag"].iloc[0]
    # Seul voisin 3 (=30) est valide → moyenne = 30
    assert abs(val - 30.0) < 1e-9, f"Attendu 30.0, obtenu {val}"


def test_spatial_lag_colonnes_presentes():
    """Chaque feature de SPATIAL_LAG_FEATURES donne naissance à *_spatial_lag."""
    dates = [pd.Timestamp("2010-10-01")]
    df = _make_spatial_df(dates, {1: [10.0], 2: [20.0]})
    neighbors = {1: [2], 2: [1]}

    result = pipeline.compute_spatial_lags(df, neighbors, pipeline.SPATIAL_LAG_FEATURES)
    for feat in pipeline.SPATIAL_LAG_FEATURES:
        if feat in df.columns:
            col = f"{feat}_spatial_lag"
            assert col in result.columns, f"Colonne manquante : {col}"


# ---------------------------------------------------------------------------
# Tests d'intégration — requièrent les parquets sur disque
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def df_out():
    if not PARQUET_OUT.exists():
        pytest.skip("Parquet #05 absent — lancer d'abord : python src/05_feature_engineering.py")
    return pd.read_parquet(PARQUET_OUT)


def test_colonnes_pop_presentes(df_out):
    assert "pop_consecutive" in df_out.columns


def test_colonnes_lags_presentes(df_out):
    for feat in pipeline.TEMPORAL_LAG_FEATURES:
        if feat not in df_out.columns:
            continue
        for sfx in ("_lag1d", "_lag2d", "_lag1m"):
            assert f"{feat}{sfx}" in df_out.columns


def test_colonnes_spatial_lag_presentes(df_out):
    for feat in pipeline.SPATIAL_LAG_FEATURES:
        if feat not in df_out.columns:
            continue
        assert f"{feat}_spatial_lag" in df_out.columns


def test_pop_valeurs_coherentes(df_out):
    """pop_consecutive est un entier >= 0 et ne dépasse pas 10 (max mois/campagne)."""
    col = df_out["pop_consecutive"].dropna()
    assert (col >= 0).all(), "pop_consecutive contient des valeurs négatives"
    assert col.max() <= 10, f"pop_consecutive max = {col.max()} > 10 mois/campagne"


def test_lags_nan_uniquement_en_debut_de_serie(df_out):
    """Les NaN dans lag1d sont bornés aux premières décades de chaque région."""
    col_lag = "chirps_sum_mean_lag1d"
    if col_lag not in df_out.columns:
        pytest.skip(f"{col_lag} absent")
    max_nan = (
        df_out.groupby("region_id")[col_lag]
        .apply(lambda s: s.sort_index().isna().sum())
        .max()
    )
    # Au plus 3 NaN en tête de série par région (1 pour lag1d + 2 pour lag2d + 3 pour lag1m)
    assert max_nan <= 3, f"Trop de NaN dans lag1d : {max_nan} pour une région"
