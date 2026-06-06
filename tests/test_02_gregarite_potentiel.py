"""Tests unitaires — Issue #02 : Niveau de grégarité et potentiel acridien."""

import sys
import math
from pathlib import Path

import pytest
import geopandas as gpd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import gregarite_potentiel_02 as pipeline

DATA_DIR = Path(__file__).parent.parent / "data"
PARQUET_IN = DATA_DIR / "processed" / "01_releves_nettoyes.parquet"
PARQUET_OUT = DATA_DIR / "processed" / "02_gregarite_potentiel.parquet"


# ---------------------------------------------------------------------------
# compute_niveau_gregarite — cinq cas canoniques
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sol,trans,greg,expected", [
    (0,   0,  0, "absent"),   # aucun criquet
    (5,   0,  0, "S"),        # solitaires seuls
    (3,   2,  0, "St"),       # Trans < Sol, Trans > 0 → solitaro-transiens
    (3,   5,  0, "T"),        # Trans >= Sol > 0 → transiens congregans
    (3,   3,  0, "T"),        # Trans == Sol > 0 → transiens (limite)
    (0,   4,  0, "St"),       # Sol=0, Trans>0 : Trans > 0, condition T échoue (Sol=0)
    (2,   1,  3, "G"),        # greg > 0, priorité absolue
    (0,   0,  1, "G"),        # greg seul → G
])
def test_niveau_gregarite_cas_canoniques(sol, trans, greg, expected):
    assert pipeline.compute_niveau_gregarite(sol, trans, greg) == expected


@pytest.mark.parametrize("sol,trans,greg", [
    (None, 0,    0),
    (0,    None, 0),
    (0,    0,    None),
    (float("nan"), 1, 0),
])
def test_niveau_gregarite_nan_input(sol, trans, greg):
    assert pipeline.compute_niveau_gregarite(sol, trans, greg) is None


# ---------------------------------------------------------------------------
# compute_densite_imago — formule DI + DL/9
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("di,dl,expected", [
    (100.0,  90.0,  110.0),     # 100 + 90/9 = 110
    (0.0,    0.0,   0.0),
    (50.0,   0.0,   50.0),
    (0.0,   18.0,   2.0),       # 0 + 18/9 = 2
    (float("nan"), 0.0, 0.0),   # NaN DI traité comme 0
    (0.0, float("nan"), 0.0),   # NaN DL traité comme 0
])
def test_densite_imago_formule(di, dl, expected):
    result = pipeline.compute_densite_imago(di, dl)
    assert math.isclose(result, expected, rel_tol=1e-9)


def test_densite_imago_deux_nan():
    result = pipeline.compute_densite_imago(float("nan"), float("nan"))
    assert math.isnan(result)


def test_densite_imago_none_none():
    result = pipeline.compute_densite_imago(None, None)
    assert math.isnan(result)


# ---------------------------------------------------------------------------
# compute_potentiel_acridien — matrice Annexe 8 (Manuel p. 307)
# Densités test : 0, 5 (]0-10]), 50 (]10-100]), 200 (]100-500]),
#                 800 (]500-1500]), 2000 (]1500-2500]), 5000 (]2500-10000]), 15000 (>10000)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("niveau,densite,expected", [
    # --- absent : toujours 0 quelle que soit la densité ---
    ("absent",  0,      0),
    ("absent",  5000.0, 0),

    # --- S (solitaires) — ligne 1 Manuel Annexe 8 ---
    ("S",     0,       0),
    ("S",     5.0,     1),
    ("S",    50.0,     1),
    ("S",   200.0,     2),
    ("S",   800.0,     2),   # corrigé depuis "6" dans PDF (artefact extraction)
    ("S",  2000.0,     3),
    ("S",  5000.0,     3),
    ("S", 15000.0,     3),

    # --- St (solitaro-transiens) — ligne 2 ---
    ("St",     0,      0),
    ("St",     5.0,    1),
    ("St",    50.0,    2),
    ("St",   200.0,    2),
    ("St",   800.0,    3),
    ("St",  2000.0,    3),
    ("St",  5000.0,    3),
    ("St", 15000.0,    3),

    # --- T → T1 (transiens, niveau conservateur) — ligne 3 ---
    ("T",      0,      0),
    ("T",      5.0,    2),
    ("T",     50.0,    2),
    ("T",    200.0,    2),
    ("T",    800.0,    3),
    ("T",   2000.0,    3),
    ("T",   5000.0,    3),
    ("T",  15000.0,    4),

    # --- T1 explicite (même résultat que T) ---
    ("T1",   200.0,    2),
    ("T1", 15000.0,    4),

    # --- T2 — ligne 4 ---
    ("T2",     0,      0),
    ("T2",     5.0,    2),
    ("T2",   200.0,    2),
    ("T2",   800.0,    3),
    ("T2",  5000.0,    4),
    ("T2", 15000.0,    4),

    # --- T3 — ligne 5 ---
    ("T3",     0,      0),
    ("T3",     5.0,    2),
    ("T3",   200.0,    3),  # T3[col3]=3 : T3 est plus agressif que T1/T2 dès 100-500
    ("T3",   800.0,    3),
    ("T3",  5000.0,    4),
    ("T3", 15000.0,    5),

    # --- G (grégaires) — ligne 6 ---
    ("G",      0,      0),
    ("G",      5.0,    2),
    ("G",     50.0,    2),
    ("G",    200.0,    3),
    ("G",    800.0,    3),
    ("G",   2000.0,    3),
    ("G",   5000.0,    4),
    ("G",  15000.0,    5),
])
def test_potentiel_acridien_matrice_annexe8(niveau, densite, expected):
    result = pipeline.compute_potentiel_acridien(niveau, densite)
    assert result == expected, (
        f"Annexe 8 : niveau={niveau!r}, densite={densite} → attendu {expected}, obtenu {result}"
    )


def test_potentiel_acridien_t_mappe_sur_t1():
    """T terrain est systématiquement mappé sur T1 (valeur conservatrice)."""
    for densite in [0, 5.0, 50.0, 200.0, 800.0, 2000.0, 5000.0, 15000.0]:
        assert pipeline.compute_potentiel_acridien("T", densite) == \
               pipeline.compute_potentiel_acridien("T1", densite), \
               f"T ≠ T1 pour densite={densite}"


@pytest.mark.parametrize("niveau,densite", [
    (None,     100.0),
    ("S",      float("nan")),
    ("inconnu", 100.0),
])
def test_potentiel_acridien_cas_nul(niveau, densite):
    assert pipeline.compute_potentiel_acridien(niveau, densite) is None


def test_potentiel_absent_avec_densite_nan():
    """absent retourne 0 même si la densité est NaN."""
    assert pipeline.compute_potentiel_acridien("absent", float("nan")) == 0


# ---------------------------------------------------------------------------
# Limites des classes de densité (vérification des bornes right-closed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("densite,expected_col,expected_S", [
    (0,      0, 0),  # densité exactement 0 → colonne 0
    (10.0,   1, 1),  # ≤ 10 → col 1
    (10.001, 2, 1),  # > 10 → col 2
    (100.0,  2, 1),  # ≤ 100 → col 2
    (500.0,  3, 2),  # ≤ 500 → col 3
    (1500.0, 4, 2),  # ≤ 1500 → col 4
    (2500.0, 5, 3),  # ≤ 2500 → col 5
    (10000.0,6, 3),  # ≤ 10000 → col 6
    (10001.0,7, 3),  # > 10000 → col 7
])
def test_densite_bornes_classes(densite, expected_col, expected_S):
    result = pipeline.compute_potentiel_acridien("S", densite)
    assert result == expected_S, (
        f"S, densite={densite} (col attendue {expected_col}) → attendu {expected_S}, obtenu {result}"
    )


# ---------------------------------------------------------------------------
# Test d'intégration — requiert le parquet pipeline #01
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gdf_enrichi():
    if not PARQUET_IN.exists():
        pytest.skip("Parquet #01 absent — lancer d'abord : python src/nettoyage_jointure_01.py")
    gdf = gpd.read_parquet(PARQUET_IN)
    return pipeline.enrich(gdf)


def test_colonnes_presentes(gdf_enrichi):
    for col in ("niveau_gregarite", "densite_imago", "potentiel_acridien"):
        assert col in gdf_enrichi.columns, f"Colonne absente : {col}"


def test_niveau_valeurs_valides(gdf_enrichi):
    valeurs_attendues = {"absent", "S", "St", "T", "G", None}
    valeurs_observees = set(gdf_enrichi["niveau_gregarite"].unique())
    assert valeurs_observees <= valeurs_attendues, (
        f"Valeurs inattendues dans niveau_gregarite : {valeurs_observees - valeurs_attendues}"
    )


def test_potentiel_plage_valide(gdf_enrichi):
    pot = gdf_enrichi["potentiel_acridien"].dropna()
    assert pot.between(0, 5).all(), "Des valeurs hors [0, 5] trouvées dans potentiel_acridien"


def test_absent_potentiel_zero(gdf_enrichi):
    absents = gdf_enrichi[gdf_enrichi["niveau_gregarite"] == "absent"]
    assert (absents["potentiel_acridien"] == 0).all(), \
        "Certains absents ont un potentiel_acridien != 0"


def test_gregaire_potentiel_eleve(gdf_enrichi):
    """Les grégaires à densité élevée (> 2500) doivent avoir un potentiel ≥ 4."""
    gregaires_denses = gdf_enrichi[
        (gdf_enrichi["niveau_gregarite"] == "G")
        & (gdf_enrichi["densite_imago"] > 2500)
    ]
    if len(gregaires_denses) == 0:
        pytest.skip("Aucun grégaire avec densite > 2500 dans le jeu de données")
    assert (gregaires_denses["potentiel_acridien"] >= 4).all()
