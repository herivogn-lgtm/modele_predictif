"""Tests unitaires — Pipeline #04 : logique pure d'extraction GEE (sans ee).

Ces tests couvrent la couche pure de `extraction_gee_helpers` : calendrier
décadaire + decade_id, construction des specs annuelles, assemblage des
résultats par région/décade, anomalie CHIRPS et garde-fous de complétude.
La couche GEE elle-même (reduceRegions, builders) est testée en live via
`python src/04_extraction_variables_gee.py --test-only`.
"""

import sys
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import extraction_gee_helpers as h


# ── decade_id ─────────────────────────────────────────────────────────────────

def test_build_decade_calendar_decade_id_unique_and_encoded():
    cal = h.build_decade_calendar([2010])
    # decade_id = year * 100 + decade_num
    expected = cal["year"] * 100 + cal["decade_num"]
    assert (cal["decade_id"] == expected).all()
    assert cal["decade_id"].is_unique


# ── build_specs (regroupement par année, fenêtre lead/lag) ──────────────────────

def test_build_specs_groups_by_year_with_iso_window():
    cal = h.build_decade_calendar([2010, 2011])
    # CHIRPS : lead=0, lag=1 (borne haute exclusive = date_end + 1 jour)
    specs = h.build_specs(cal, lead_days=0, lag_days=1)

    assert set(specs.keys()) == {2010, 2011}
    n_per_year = len(cal[cal["year"] == 2010])
    assert len(specs[2010]) == n_per_year

    # Première décade de 2010 (octobre D1) : 2010-10-01 → 2010-10-11 exclusif
    first = next(s for s in specs[2010] if s["id"] == 201001)
    assert first["start"] == "2010-10-01"
    assert first["end"] == "2010-10-11"

    # NDVI : lead=8, lag=9
    specs_ndvi = h.build_specs(cal, lead_days=8, lag_days=9)
    first_ndvi = next(s for s in specs_ndvi[2010] if s["id"] == 201001)
    assert first_ndvi["start"] == "2010-09-23"  # 2010-10-01 - 8j
    assert first_ndvi["end"] == "2010-10-19"    # 2010-10-10 + 9j


# ── parse_reduce_features (properties getInfo → DataFrame) ───────────────────────

CHIRPS_RENAME = {
    "mean": "chirps_sum_mean", "stdDev": "chirps_sum_std",
    "min": "chirps_sum_min", "max": "chirps_sum_max",
}
CHIRPS_KEEP = ["region_id", "decade_id", "chirps_sum_mean", "chirps_sum_min",
               "chirps_sum_max", "chirps_sum_std"]


def test_parse_reduce_features_renames_and_drops_region_nom():
    props = [
        {"region_id": 1, "decade_id": 201001, "region_nom": "RN1",
         "mean": 5.0, "stdDev": 1.0, "min": 0.0, "max": 9.0},
        {"region_id": 2, "decade_id": 201001, "region_nom": "RN2",
         "mean": 3.0, "stdDev": 0.5, "min": 1.0, "max": 4.0},
    ]
    df = h.parse_reduce_features(props, CHIRPS_RENAME, CHIRPS_KEEP)
    assert list(df.columns) == CHIRPS_KEEP
    assert "region_nom" not in df.columns
    assert df.loc[df["region_id"] == 1, "chirps_sum_mean"].iloc[0] == 5.0


def test_parse_reduce_features_empty_returns_keep_columns():
    df = h.parse_reduce_features([], CHIRPS_RENAME, CHIRPS_KEEP)
    assert df.empty
    assert list(df.columns) == CHIRPS_KEEP


# ── compute_chirps_anomaly ──────────────────────────────────────────────────────

def test_compute_chirps_anomaly_subtracts_baseline():
    df = pd.DataFrame([
        {"region_id": 1, "month": 10, "decade_part": 1, "chirps_sum_mean": 50.0},
        {"region_id": 1, "month": 10, "decade_part": 2, "chirps_sum_mean": np.nan},
        {"region_id": 2, "month": 10, "decade_part": 1, "chirps_sum_mean": 30.0},
        {"region_id": 9, "month": 10, "decade_part": 1, "chirps_sum_mean": 12.0},  # pas de baseline
    ])
    baseline = pd.DataFrame([
        {"region_id": 1, "month": 10, "decade_part": 1, "chirps_baseline_mean": 40.0},
        {"region_id": 1, "month": 10, "decade_part": 2, "chirps_baseline_mean": 35.0},
        {"region_id": 2, "month": 10, "decade_part": 1, "chirps_baseline_mean": 20.0},
    ])
    out = h.compute_chirps_anomaly(df, baseline)

    by = out.set_index(["region_id", "month", "decade_part"])["chirps_anomaly_mean"]
    assert by[(1, 10, 1)] == 10.0
    assert np.isnan(by[(1, 10, 2)])   # somme NaN → anomalie NaN
    assert by[(2, 10, 1)] == 10.0
    assert np.isnan(by[(9, 10, 1)])   # baseline absente → NaN
    # la colonne baseline intermédiaire ne fuit pas dans la sortie
    assert "chirps_baseline_mean" not in out.columns


# ── assemble_decades (calendrier × régions ⋈ sources) ───────────────────────────

def _regions_df():
    return pd.DataFrame({"region_id": [1, 2], "region_nom": ["RN1", "RN2"]})


def test_assemble_decades_cross_product_and_left_merge():
    cal = h.build_decade_calendar([2010])
    n_dec = len(cal)
    chirps = pd.DataFrame([
        {"decade_id": 201001, "region_id": 1, "chirps_sum_mean": 5.0},
        {"decade_id": 201001, "region_id": 2, "chirps_sum_mean": 7.0},
        {"decade_id": 201002, "region_id": 1, "chirps_sum_mean": 3.0},
        # (201002, région 2) absent → doit devenir NaN
    ])
    out = h.assemble_decades(cal, _regions_df(), [chirps])

    # une ligne par (décade × région)
    assert len(out) == n_dec * 2
    # métadonnées présentes
    for col in ["region_nom", "campaign", "decade_num", "date_start", "year", "month"]:
        assert col in out.columns

    # valeurs jointes correctement
    present = out[(out["month"] == 10) & (out["decade_part"] == 1) & (out["region_id"] == 1)]
    assert present["chirps_sum_mean"].iloc[0] == 5.0
    missing = out[(out["month"] == 10) & (out["decade_part"] == 2) & (out["region_id"] == 2)]
    assert np.isnan(missing["chirps_sum_mean"].iloc[0])


def test_assemble_decades_merges_multiple_sources():
    cal = h.build_decade_calendar([2010])
    chirps = pd.DataFrame([{"decade_id": 201001, "region_id": 1, "chirps_sum_mean": 5.0}])
    ndvi = pd.DataFrame([{"decade_id": 201001, "region_id": 1, "ndvi_mean": 0.4}])
    out = h.assemble_decades(cal, _regions_df(), [chirps, ndvi])
    row = out[(out["month"] == 10) & (out["decade_part"] == 1) & (out["region_id"] == 1)]
    assert row["chirps_sum_mean"].iloc[0] == 5.0
    assert row["ndvi_mean"].iloc[0] == 0.4


# ── assert_decade_completeness (garde-fou) ──────────────────────────────────────

def test_assert_decade_completeness_passes_when_full():
    cal = h.build_decade_calendar([2010])
    out = h.assemble_decades(cal, _regions_df(), [])
    # ne doit pas lever
    h.assert_decade_completeness(out, n_regions=2)


def test_assert_decade_completeness_raises_on_missing_region():
    cal = h.build_decade_calendar([2010])
    out = h.assemble_decades(cal, _regions_df(), [])
    broken = out.iloc[1:]  # retire une ligne → une décade n'a plus que 1 région
    with pytest.raises(AssertionError):
        h.assert_decade_completeness(broken, n_regions=2)
