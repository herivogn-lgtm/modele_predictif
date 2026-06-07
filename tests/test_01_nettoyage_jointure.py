"""Tests d'intégration — Issue #01 : Nettoyage et jointure spatiale."""

import sys
from pathlib import Path
import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import nettoyage_jointure_01 as pipeline

DATA_DIR = Path(__file__).parent.parent / "data"
PARQUET = DATA_DIR / "processed" / "01_releves_nettoyes.parquet"

# Point de référence Androka (1re ligne du XLS, vérifiée empiriquement)
ANDROKA_LAT = -24.95
ANDROKA_LNG = 44.166666666666664
EXPECTED_RN_NUM = 86
EXPECTED_RN_NOM = "plaine cotiere Mahafaly sud (Saodona-Bevoalava)"
EXPECTED_AIRE_NOM = "AD"
EXPECTED_CAMPAGNE = "2001-2002"
EXPECTED_CAMPAGNE_DECADE = 16  # mars offset=6, decade_intra=1 → (6-1)*3+1


# ---------------------------------------------------------------------------
# Tests unitaires purs — pas besoin du parquet
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("month,year,expected", [
    (10, 2001, "2001-2002"),
    (7,  2002, "2001-2002"),
    (1,  2002, "2001-2002"),
    (12, 2001, "2001-2002"),
    (8,  2002, None),
    (9,  2002, None),
])
def test_campagne_calcul(month, year, expected):
    date = pd.Timestamp(year=year, month=month, day=15)
    assert pipeline.compute_campagne(date) == expected


def test_campagne_decade_androka():
    """2002-03-10 : mars (offset=6), jour 10 → decade_intra=1, campagne_decade=16."""
    date = pd.Timestamp("2002-03-10")
    result = pipeline.compute_temporal_fields(date)
    assert result["decade_intra"] == 1
    assert result["campagne_decade"] == 16


def test_androka_sjoin_direct():
    """Teste le shapefile indépendamment du pipeline (non-circulaire)."""
    rn = gpd.read_file(DATA_DIR / "region_naturelle" / "region_naturelle.shp")
    pt = gpd.GeoDataFrame(
        {"geometry": [Point(ANDROKA_LNG, ANDROKA_LAT)]}, crs="EPSG:4326"
    )
    result = gpd.sjoin(pt, rn[["rn_nom", "rn_num", "geometry"]], how="left", predicate="within")
    assert str(result.iloc[0]["rn_num"]) == str(EXPECTED_RN_NUM)
    assert result.iloc[0]["rn_nom"] == EXPECTED_RN_NOM


# ---------------------------------------------------------------------------
# Tests d'intégration — requièrent le parquet généré par le pipeline
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gdf():
    if not PARQUET.exists():
        pytest.skip("Parquet absent — lancer d'abord : python src/nettoyage_jointure_01.py")
    return gpd.read_parquet(PARQUET)


def test_no_nse_columns(gdf):
    nse_cols = [c for c in gdf.columns if "_NSE" in str(c) or c == "NSE.Sup_inf"]
    assert nse_cols == [], f"Colonnes NSE présentes : {nse_cols}"


def test_gps_bounds(gdf):
    assert gdf["LAT_DD"].notna().all(), "LAT_DD contient des NaN"
    assert gdf["LNG_DD"].notna().all(), "LNG_DD contient des NaN"
    assert gdf["LAT_DD"].between(-26.0, -11.0).all(), "LAT_DD hors bornes Madagascar"
    assert gdf["LNG_DD"].between(43.0, 51.0).all(), "LNG_DD hors bornes Madagascar"


def test_no_row_duplication(gdf):
    """Le sjoin ne doit pas créer de doublons (shapefiles sans overlap)."""
    assert len(gdf) <= 29706


def test_parquet_androka_row(gdf):
    """Ligne Androka 2002-03-10 : vérifie l'ensemble des colonnes clés."""
    androka = gdf[
        (gdf["PA"] == "Androka")
        & (gdf["date"].dt.date == pd.Timestamp("2002-03-10").date())
    ]
    assert len(androka) >= 1, "Ligne Androka 2002-03-10 introuvable dans la sortie"
    row = androka.iloc[0]
    assert row["rn_num"] == EXPECTED_RN_NUM
    assert row["AIRE_NOM"] == EXPECTED_AIRE_NOM
    assert row["campagne_calc"] == EXPECTED_CAMPAGNE
    assert row["campagne_decade"] == EXPECTED_CAMPAGNE_DECADE
    assert row["hors_aire"] is False or row["hors_aire"] == False


def test_hors_aire_antsohihy(gdf):
    """Les relevés d'Antsohihy sont hors de l'aire grégarigène."""
    antsohihy = gdf[gdf["ZA"] == "Antsohihy"]
    if len(antsohihy) == 0:
        pytest.skip("Pas de relevés Antsohihy dans la sortie")
    assert antsohihy["hors_aire"].all(), "Relevés Antsohihy devraient être hors_aire=True"
