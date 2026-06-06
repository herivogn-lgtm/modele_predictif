"""Tests unitaires et intégration — Issue #03 : Labels d'entraînement par région × décade."""

import sys
from pathlib import Path

import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import labels_entrainement_03 as pipeline

DATA_DIR   = Path(__file__).parent.parent / "data"
PARQUET_OUT = DATA_DIR / "processed" / "03_labels_region_decade.parquet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_group(*sol_trans_greg_tuples):
    """Construit un DataFrame groupe depuis des tuples (Sol, Trans, Greg)."""
    rows = [{"Sol": s, "Trans": t, "Greg": g} for s, t, g in sol_trans_greg_tuples]
    return pd.DataFrame(rows)


def _make_survey_df(rows: list[dict]) -> pd.DataFrame:
    """Construit un DataFrame de relevés minimal pour les tests aggregate_per_cell."""
    defaults = {"rn_num": 1, "rn_nom": "RN1", "campagne_calc": "2010-2011",
                "campagne_decade": 5, "Sol": 0.0, "Trans": 0.0, "Greg": 0.0}
    return pd.DataFrame([{**defaults, **r} for r in rows]).assign(
        rn_num=lambda df: df["rn_num"].astype("Int64")
    )


# ---------------------------------------------------------------------------
# compute_label — cas canoniques
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tuples, expected", [
    # Présence : au moins une ligne non nulle
    ([(1, 0, 0), (0, 0, 0)], 1),
    ([(0, 2, 0)],            1),
    ([(0, 0, 3)],            1),
    # Absence vérifiée : toutes les lignes à zéro
    ([(0, 0, 0)],            0),
    ([(0, 0, 0), (0, 0, 0)], 0),
    # NaN traité comme 0 → ligne full-NaN ne génère pas de présence
    ([(float("nan"), float("nan"), float("nan"))], 0),
    # Présence malgré NaN partiel
    ([(1.0, float("nan"), 0.0)], 1),
])
def test_compute_label(tuples, expected):
    group = _make_group(*tuples)
    assert pipeline.compute_label(group) == expected


# ---------------------------------------------------------------------------
# aggregate_per_cell — filtrage et effort
# ---------------------------------------------------------------------------

def test_aggregate_exclut_rn_num_na():
    """Lignes avec rn_num=NA exclues même si Sol > 0 ; ne contaminent pas les voisines."""
    df = _make_survey_df([
        {"rn_num": pd.NA, "Sol": 10.0},  # doit être ignoré
        {"rn_num": 1,     "Sol": 0.0},
        {"rn_num": 1,     "Sol": 0.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    assert len(result) == 1
    assert result.iloc[0]["label"] == 0
    assert result.iloc[0]["effort_prospection"] == 2


def test_aggregate_exclut_campagne_none():
    """Lignes avec campagne_calc=None (inter-campagne) exclues."""
    df = _make_survey_df([
        {"campagne_calc": None,      "campagne_decade": pd.NA, "Sol": 5.0},
        {"campagne_calc": "2010-2011", "campagne_decade": 5,  "Sol": 0.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    assert len(result) == 1
    assert result.iloc[0]["label"] == 0


def test_aggregate_effort_exact():
    """effort_prospection = nombre exact de lignes (compte toutes les lignes du groupe)."""
    df = _make_survey_df([
        {"Sol": 0.0}, {"Sol": 1.0}, {"Sol": 0.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    assert result.iloc[0]["effort_prospection"] == 3
    assert result.iloc[0]["label"] == 1


def test_aggregate_presence_une_ligne_parmi_plusieurs():
    """Une seule ligne avec Greg > 0 suffit pour label=1."""
    df = _make_survey_df([
        {"Sol": 0.0, "Trans": 0.0, "Greg": 0.0},
        {"Sol": 0.0, "Trans": 0.0, "Greg": 2.0},
        {"Sol": 0.0, "Trans": 0.0, "Greg": 0.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    assert result.iloc[0]["label"] == 1


# ---------------------------------------------------------------------------
# build_full_grid — cellules masquées
# ---------------------------------------------------------------------------

def _make_rn_ref(rn_nums: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "rn_num": pd.array(rn_nums, dtype="Int64"),
        "rn_nom": [f"RN{n}" for n in rn_nums],
    })


def _make_observed(rn_nums: list[int], campagnes: list[str],
                   decades: list[int], labels: list) -> pd.DataFrame:
    return pd.DataFrame({
        "rn_num": pd.array(rn_nums, dtype="Int64"),
        "campagne_calc": campagnes,
        "campagne_decade": decades,
        "label": pd.array(labels, dtype="Int64"),
        "effort_prospection": [1] * len(rn_nums),
    })


def test_build_full_grid_cellules_masquees():
    """Régions non prospectées → label=NA, effort=0."""
    rn_ref = _make_rn_ref([1, 2, 3])
    observed = _make_observed([1], ["2010-2011"], [5], [1])

    result = pipeline.build_full_grid(observed, rn_ref)
    assert len(result) == 3  # 3 régions × 1 (campagne, décade)

    rn1 = result[result["rn_num"] == 1].iloc[0]
    assert rn1["label"] == 1
    assert rn1["effort_prospection"] == 1

    for rn in [2, 3]:
        row = result[result["rn_num"] == rn].iloc[0]
        assert pd.isna(row["label"]), f"rn_num={rn} devrait avoir label=NA"
        assert row["effort_prospection"] == 0


def test_build_full_grid_rn_nom_pour_masques():
    """rn_nom est présent même pour les cellules masquées."""
    rn_ref = _make_rn_ref([99])
    observed = _make_observed([1], ["2010-2011"], [1], [0])

    # rn_ref contient uniquement rn_num=99 (non présente dans observed)
    result = pipeline.build_full_grid(observed, rn_ref)
    row = result[result["rn_num"] == 99].iloc[0]
    assert row["rn_nom"] == "RN99"
    assert pd.isna(row["label"])


def test_build_full_grid_taille():
    """Grille = len(rn_ref) × len(décades uniques dans observed)."""
    rn_ref = _make_rn_ref([1, 2, 3, 4, 5])
    observed = _make_observed(
        [1, 1, 2],
        ["2010-2011", "2010-2011", "2011-2012"],
        [5, 10, 5],
        [1, 0, 1],
    )
    result = pipeline.build_full_grid(observed, rn_ref)
    # 3 décades uniques : (2010-2011, 5), (2010-2011, 10), (2011-2012, 5)
    assert len(result) == 5 * 3


# ---------------------------------------------------------------------------
# apply_exclusions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("campagne, label_initial, expect_na", [
    ("2023-2024", 1, True),
    ("2023-2024", 0, True),
    ("2010-2011", 1, False),
    ("2001-2002", 0, False),
])
def test_apply_exclusions_label(campagne, label_initial, expect_na):
    df = pd.DataFrame({
        "campagne_calc": [campagne],
        "label": pd.array([label_initial], dtype="Int64"),
        "effort_prospection": [3],
    })
    result = pipeline.apply_exclusions(df)
    if expect_na:
        assert pd.isna(result.iloc[0]["label"])
    else:
        assert result.iloc[0]["label"] == label_initial


def test_apply_exclusions_conserve_effort():
    """apply_exclusions ne modifie pas effort_prospection."""
    df = pd.DataFrame({
        "campagne_calc": ["2023-2024"],
        "label": pd.array([1], dtype="Int64"),
        "effort_prospection": [7],
    })
    result = pipeline.apply_exclusions(df)
    assert result.iloc[0]["effort_prospection"] == 7


def test_apply_exclusions_ne_modifie_pas_original():
    """apply_exclusions opère sur une copie (pas de mutation en place)."""
    df = pd.DataFrame({
        "campagne_calc": ["2023-2024"],
        "label": pd.array([1], dtype="Int64"),
        "effort_prospection": [1],
    })
    pipeline.apply_exclusions(df)
    assert df.iloc[0]["label"] == 1


# ---------------------------------------------------------------------------
# Tests d'intégration — requièrent le parquet de sortie
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def df_labels():
    if not PARQUET_OUT.exists():
        pytest.skip(
            "Parquet #03 absent — lancer d'abord : python src/labels_entrainement_03.py"
        )
    return pd.read_parquet(PARQUET_OUT)


def test_colonnes_presentes(df_labels):
    required = {"rn_num", "rn_nom", "campagne_calc", "campagne_decade",
                "effort_prospection", "label"}
    assert required <= set(df_labels.columns), (
        f"Colonnes manquantes : {required - set(df_labels.columns)}"
    )


def test_label_valeurs_valides(df_labels):
    """label est uniquement 0, 1 ou NA."""
    valeurs = set(df_labels["label"].dropna().unique())
    assert valeurs <= {0, 1}, f"Valeurs inattendues dans label : {valeurs - {0, 1}}"


def test_sans_effort_implique_masque(df_labels):
    """Toute cellule avec effort_prospection=0 doit avoir label=NA."""
    zero_effort = df_labels[df_labels["effort_prospection"] == 0]
    assert zero_effort["label"].isna().all(), (
        "Des cellules sans prospection ont un label non-NA"
    )


def test_avec_effort_implique_label_ou_exclusion(df_labels):
    """Toute cellule prospectée (effort >= 1) a label non-NA OU est une campagne exclue."""
    with_effort = df_labels[df_labels["effort_prospection"] >= 1]
    unlabeled = with_effort[with_effort["label"].isna()]
    assert unlabeled["campagne_calc"].isin(pipeline._EXCLUDED_CAMPAIGNS).all(), (
        "Des cellules prospectées ont label=NA hors campagnes exclues"
    )


def test_90_regions_presentes(df_labels):
    """Les 90 régions naturelles sont représentées dans la grille."""
    n = df_labels["rn_num"].nunique()
    assert n == 90, f"Nombre de régions naturelles : {n} (attendu 90)"


def test_campagne_decade_plage(df_labels):
    """campagne_decade est dans [1, 30]."""
    assert df_labels["campagne_decade"].between(1, 30).all(), (
        "Des valeurs de campagne_decade hors [1, 30] trouvées"
    )


def test_campagnes_exclues_toutes_na(df_labels):
    """Les campagnes exclues ont exclusivement label=NA."""
    for camp in pipeline._EXCLUDED_CAMPAIGNS:
        subset = df_labels[df_labels["campagne_calc"] == camp]
        if len(subset) == 0:
            continue
        assert subset["label"].isna().all(), (
            f"Campagne exclue {camp!r} a des labels non-NA"
        )


def test_rn_nom_jamais_vide(df_labels):
    """rn_nom est renseigné pour toutes les lignes, y compris les cellules masquées."""
    assert df_labels["rn_nom"].notna().all(), "Des lignes ont rn_nom manquant"
