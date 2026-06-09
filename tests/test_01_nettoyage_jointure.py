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
GRID = DATA_DIR / "processed" / "01_grille_1km.parquet"

# Point de référence Androka (1re ligne du XLS, vérifiée empiriquement)
ANDROKA_LAT = -24.95
ANDROKA_LNG = 44.166666666666664
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


# ---------------------------------------------------------------------------
# snap_to_grid — rattachement point → cellule 1 km (grille régulière UTM)
# ---------------------------------------------------------------------------

def _points(coords: list[tuple[float, float]]) -> gpd.GeoDataFrame:
    """GeoDataFrame de points depuis une liste de (lng, lat) en WGS84."""
    return gpd.GeoDataFrame(
        {"geometry": [Point(lng, lat) for lng, lat in coords]}, crs="EPSG:4326"
    )


def test_snap_to_grid_meme_cellule_meme_id():
    """Deux points dans la même cellule 1 km partagent le cell_id ; un point
    à ~1,5 km à l'est tombe dans une colonne différente."""
    # Androka, +~100 m est (même cellule), +~1,5 km est (cellule différente)
    base = (ANDROKA_LNG, ANDROKA_LAT)
    proche = (ANDROKA_LNG + 0.001, ANDROKA_LAT)   # ~100 m
    loin = (ANDROKA_LNG + 0.015, ANDROKA_LAT)      # ~1,5 km
    result = pipeline.snap_to_grid(_points([base, proche, loin]))

    assert result.iloc[0]["cell_id"] == result.iloc[1]["cell_id"]
    assert result.iloc[2]["cell_id"] != result.iloc[0]["cell_id"]
    assert result.iloc[2]["cell_col"] != result.iloc[0]["cell_col"]


def _aire_carre(code="AD", sect="AD-S", nom="AD") -> gpd.GeoDataFrame:
    """Polygone aire synthétique : carré 0,1° autour d'Androka."""
    from shapely.geometry import box
    poly = box(ANDROKA_LNG - 0.05, ANDROKA_LAT - 0.05,
               ANDROKA_LNG + 0.05, ANDROKA_LAT + 0.05)
    return gpd.GeoDataFrame(
        {"AIRE_CODE": [code], "SECT_NO": [sect], "AIRE_NOM": [nom], "geometry": [poly]},
        crs="EPSG:4326",
    )


def test_clip_to_aire_exclut_hors_polygone():
    """Un point dans le polygone est gardé, un point à l'extérieur est exclu."""
    dedans = (ANDROKA_LNG, ANDROKA_LAT)
    dehors = (ANDROKA_LNG + 1.0, ANDROKA_LAT)  # ~100 km à l'est, hors carré
    result = pipeline.clip_to_aire(_points([dedans, dehors]), _aire_carre())

    assert len(result) == 1
    assert result.iloc[0].geometry.x == pytest.approx(ANDROKA_LNG)


def test_clip_to_aire_rattache_aire_code():
    """Le point gardé hérite de l'AIRE_CODE/SECT_NO du polygone qui le contient."""
    result = pipeline.clip_to_aire(
        _points([(ANDROKA_LNG, ANDROKA_LAT)]),
        _aire_carre(code="AD", sect="AD-S"),
    )
    assert result.iloc[0]["AIRE_CODE"] == "AD"
    assert result.iloc[0]["SECT_NO"] == "AD-S"


def test_build_grid_round_trip_avec_snap():
    """La grille 1 km partage l'emprise de snap_to_grid : snapper le centroïde
    d'une cellule redonne son cell_id."""
    grid = pipeline.build_grid(_aire_carre())
    assert len(grid) > 0
    assert "cell_id" in grid.columns

    centroids = gpd.GeoDataFrame(geometry=grid.geometry.centroid, crs=grid.crs)
    snapped = pipeline.snap_to_grid(centroids)
    assert (snapped["cell_id"].values == grid["cell_id"].values).all()


def test_build_grid_couvre_les_4_aires():
    """La grille couvre tous les secteurs/aires fournis (pas un seul polygone)."""
    from shapely.geometry import box
    polys = []
    for i, code in enumerate(["AGT", "AMI", "ATM", "AD"]):
        x0 = ANDROKA_LNG + i  # carrés disjoints, 1° d'écart
        polys.append({
            "AIRE_CODE": code, "SECT_NO": f"{code}-X", "AIRE_NOM": code,
            "geometry": box(x0 - 0.02, ANDROKA_LAT - 0.02, x0 + 0.02, ANDROKA_LAT + 0.02),
        })
    aire = gpd.GeoDataFrame(polys, crs="EPSG:4326")
    grid = pipeline.build_grid(aire)
    assert set(grid["AIRE_CODE"].unique()) == {"AGT", "AMI", "ATM", "AD"}


def test_androka_dans_aire_direct():
    """Teste le shapefile aire grégarigène indépendamment du pipeline (non-circulaire)."""
    ag = gpd.read_file(DATA_DIR / "aire_gregarigene" / "aire_gregarigene.shp")
    pt = gpd.GeoDataFrame(
        {"geometry": [Point(ANDROKA_LNG, ANDROKA_LAT)]}, crs="EPSG:4326"
    )
    result = gpd.sjoin(pt, ag[["AIRE_NOM", "geometry"]], how="inner", predicate="within")
    assert len(result) == 1
    assert result.iloc[0]["AIRE_NOM"] == EXPECTED_AIRE_NOM


# ---------------------------------------------------------------------------
# Tests d'intégration — requièrent le parquet généré par le pipeline
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gdf():
    if not PARQUET.exists():
        pytest.skip("Parquet absent — lancer d'abord : python src/nettoyage_jointure_01.py")
    return gpd.read_parquet(PARQUET)


@pytest.fixture(scope="module")
def grid():
    if not GRID.exists():
        pytest.skip("Grille absente — lancer d'abord : python src/nettoyage_jointure_01.py")
    return gpd.read_parquet(GRID)


def test_no_nse_columns(gdf):
    nse_cols = [c for c in gdf.columns if "_NSE" in str(c) or c == "NSE.Sup_inf"]
    assert nse_cols == [], f"Colonnes NSE présentes : {nse_cols}"


def test_gps_bounds(gdf):
    assert gdf["LAT_DD"].notna().all(), "LAT_DD contient des NaN"
    assert gdf["LNG_DD"].notna().all(), "LNG_DD contient des NaN"
    assert gdf["LAT_DD"].between(-26.0, -11.0).all(), "LAT_DD hors bornes Madagascar"
    assert gdf["LNG_DD"].between(43.0, 51.0).all(), "LNG_DD hors bornes Madagascar"


def test_colonnes_conservees(gdf):
    """La table nettoyée conserve les colonnes clés + l'identifiant de cellule."""
    required = {"LAT_DD", "LNG_DD", "Date_", "Decade", "campagne_xls", "cell_id"}
    assert required <= set(gdf.columns), (
        f"Colonnes manquantes : {required - set(gdf.columns)}"
    )
    assert gdf["cell_id"].notna().all(), "Des relevés conservés n'ont pas de cell_id"


def test_tous_dans_aire(gdf):
    """Clip strict : tous les relevés conservés ont un AIRE_CODE (within polygone)."""
    assert gdf["AIRE_CODE"].notna().all(), "Des relevés conservés sont hors aire"


def test_parquet_androka_row(gdf):
    """Ligne Androka 2002-03-10 : cell_id présent + rattachement aire correct."""
    androka = gdf[
        (gdf["PA"] == "Androka")
        & (gdf["date"].dt.date == pd.Timestamp("2002-03-10").date())
    ]
    assert len(androka) >= 1, "Ligne Androka 2002-03-10 introuvable dans la sortie"
    row = androka.iloc[0]
    assert row["AIRE_NOM"] == EXPECTED_AIRE_NOM
    assert row["campagne_calc"] == EXPECTED_CAMPAGNE
    assert row["campagne_decade"] == EXPECTED_CAMPAGNE_DECADE
    assert isinstance(row["cell_id"], str) and "_" in row["cell_id"]


def test_hors_aire_antsohihy_exclu(gdf):
    """Les relevés d'Antsohihy (hors aire grégarigène) sont écartés par le clip."""
    assert (gdf["ZA"] == "Antsohihy").sum() == 0, (
        "Des relevés Antsohihy subsistent malgré le clip strict"
    )


def test_grille_couvre_12_secteurs(grid):
    """La grille 1 km couvre les 12 secteurs / 4 aires complémentaires."""
    assert grid["SECT_NO"].nunique() == 12, "Les 12 secteurs ne sont pas tous couverts"
    assert set(grid["AIRE_CODE"].unique()) == {1, 2, 3, 4}


def test_grille_taille_realiste(grid):
    """Ordre de grandeur : ~181 000 cellules 1 km.

    NB : aire grégarigène réelle ≈ 181 500 km² (vérifié UTM + géodésique,
    SUP_HA en km²). Le « ~1 800 cellules » de l'ADR 0003/PRD/CONTEXT est une
    erreur d'un facteur 100 (ha↔km²) — correction doc à traiter en ticket séparé.
    """
    assert 150_000 <= len(grid) <= 210_000, f"Nombre de cellules inattendu : {len(grid)}"
