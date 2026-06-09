"""Tests unitaires et intégration — Issue #02 : Cible ordinale sévérité-phase 0–3.

Pipeline #03 agrège les relevés à la maille cellule 1 km × décade et produit :
  - severite : ordinale 0–3 = phase maximale observée (imago + larve)
  - binaire  : sévérité ≥ 1 (présence), dérivé pour l'AUC
  - intensite: log1p(densité moyenne), optionnelle et non bloquante (~35 % NaN)
"""

import sys
from pathlib import Path

import math
import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import labels_entrainement_03 as pipeline

DATA_DIR    = Path(__file__).parent.parent / "data"
PARQUET_OUT = DATA_DIR / "processed" / "03_labels_cellule_decade.parquet"

PHASE_COLS = ["Sol", "Sol_larve", "Trans", "Trans_larve", "Greg", "Greg_larve"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_group(rows: list[dict]) -> pd.DataFrame:
    """Groupe de relevés ; colonnes de phase absentes → 0.0, densité → NaN."""
    defaults = {c: 0.0 for c in PHASE_COLS}
    defaults["densite_imago"] = float("nan")
    return pd.DataFrame([{**defaults, **r} for r in rows])


# ---------------------------------------------------------------------------
# compute_severite
# ---------------------------------------------------------------------------

def test_severite_greg_donne_3():
    group = _make_group([{"Greg": 4.0}])
    assert pipeline.compute_severite(group) == 3


@pytest.mark.parametrize("row, expected", [
    ({"Greg": 4.0},        3),
    ({"Greg_larve": 1.0},  3),  # larve compte autant que l'imago
    ({"Trans": 2.0},       2),
    ({"Trans_larve": 5.0}, 2),
    ({"Sol": 1.0},         1),
    ({"Sol_larve": 3.0},   1),
    ({},                   0),  # tous les comptages observés à zéro → vraie absence
])
def test_severite_cas_canoniques(row, expected):
    assert pipeline.compute_severite(_make_group([row])) == expected


def test_severite_phase_max_quand_plusieurs():
    """Plusieurs phases présentes → la phase la plus haute gouverne."""
    group = _make_group([{"Sol": 10.0, "Trans": 4.0, "Greg": 1.0}])
    assert pipeline.compute_severite(group) == 3


def test_severite_phase_max_entre_lignes():
    """Le max porte sur l'ensemble du groupe, pas une seule ligne."""
    group = _make_group([{"Sol": 5.0}, {"Trans": 2.0}, {}])
    assert pipeline.compute_severite(group) == 2


def test_severite_tout_nan_donne_na():
    """Aucune valeur observée (tout NaN) → NA, pas une absence (0)."""
    nan = float("nan")
    group = _make_group([{c: nan for c in PHASE_COLS}])
    assert pd.isna(pipeline.compute_severite(group))


def test_severite_zero_explicite_nest_pas_na():
    """Des zéros explicites → vraie absence (0), distinct du NaN."""
    group = _make_group([{}])  # toutes les phases à 0.0
    assert pipeline.compute_severite(group) == 0


def test_severite_nan_partiel_nempeche_pas_detection():
    """NaN sur certaines colonnes n'empêche pas de détecter une phase observée."""
    nan = float("nan")
    group = _make_group([{"Sol": nan, "Trans": nan, "Greg": 2.0}])
    assert pipeline.compute_severite(group) == 3


# ---------------------------------------------------------------------------
# derive_binary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("severite, expected", [
    (0, 0),
    (1, 1),
    (2, 1),
    (3, 1),
])
def test_derive_binary_scalaire(severite, expected):
    assert pipeline.derive_binary(severite) == expected


def test_derive_binary_na_reste_na():
    assert pd.isna(pipeline.derive_binary(pd.NA))


# ---------------------------------------------------------------------------
# compute_intensite — optionnelle, non bloquante
# ---------------------------------------------------------------------------

def test_intensite_log1p_densite_moyenne():
    group = _make_group([{"densite_imago": 99.0}, {"densite_imago": 199.0}])
    assert pipeline.compute_intensite(group) == pytest.approx(math.log1p(149.0))


def test_intensite_ignore_nan_partiel():
    """La moyenne ignore les densités manquantes (ne bloque pas)."""
    group = _make_group([{"densite_imago": float("nan")}, {"densite_imago": 9.0}])
    assert pipeline.compute_intensite(group) == pytest.approx(math.log1p(9.0))


def test_intensite_tout_nan_donne_nan():
    """Densité absente partout (~35 % des cas) → NaN, jamais bloquant."""
    group = _make_group([{"densite_imago": float("nan")}])
    assert math.isnan(pipeline.compute_intensite(group))


def test_intensite_densite_zero_donne_zero():
    """log1p(0) = 0 : une densité nulle ne produit pas -inf."""
    group = _make_group([{"densite_imago": 0.0}])
    assert pipeline.compute_intensite(group) == 0.0


# ---------------------------------------------------------------------------
# aggregate_per_cell — maille cellule 1 km × décade
# ---------------------------------------------------------------------------

def _make_survey_df(rows: list[dict]) -> pd.DataFrame:
    """Relevés synthétiques pour aggregate_per_cell (clé cell_id × campagne × décade)."""
    defaults = {
        "cell_id": "100_200", "campagne_calc": "2010-2011", "campagne_decade": 5,
        "densite_imago": float("nan"),
        **{c: 0.0 for c in PHASE_COLS},
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def test_aggregate_severite_max_sur_cellule_decade():
    """Plusieurs relevés d'une même cellule × décade → sévérité = phase max."""
    df = _make_survey_df([
        {"Sol": 5.0},
        {"Trans": 1.0},
        {"Greg": 2.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    assert len(result) == 1
    assert result.iloc[0]["severite"] == 3


def test_aggregate_une_ligne_par_cellule_decade():
    """Deux cellules distinctes → deux lignes agrégées."""
    df = _make_survey_df([
        {"cell_id": "1_1", "Sol": 1.0},
        {"cell_id": "2_2", "Greg": 1.0},
    ])
    result = pipeline.aggregate_per_cell(df).set_index("cell_id")
    assert result.loc["1_1", "severite"] == 1
    assert result.loc["2_2", "severite"] == 3


def test_aggregate_binaire_derive_present():
    df = _make_survey_df([{"Trans": 1.0}])
    row = pipeline.aggregate_per_cell(df).iloc[0]
    assert row["severite"] == 2
    assert row["binaire"] == 1


def test_aggregate_binaire_zero_pour_absence():
    df = _make_survey_df([{}])  # vraie absence
    row = pipeline.aggregate_per_cell(df).iloc[0]
    assert row["severite"] == 0
    assert row["binaire"] == 0


def test_aggregate_intensite_presente():
    df = _make_survey_df([{"densite_imago": 9.0}])
    row = pipeline.aggregate_per_cell(df).iloc[0]
    assert row["intensite"] == pytest.approx(math.log1p(9.0))


def test_aggregate_intensite_nan_ne_bloque_pas():
    """Densité absente → intensite NaN mais la ligne est produite (sévérité OK)."""
    df = _make_survey_df([{"Greg": 1.0}])  # densite_imago par défaut NaN
    row = pipeline.aggregate_per_cell(df).iloc[0]
    assert row["severite"] == 3
    assert pd.isna(row["intensite"])


def test_aggregate_effort_compte_lignes():
    df = _make_survey_df([{"Sol": 0.0}, {"Sol": 1.0}, {"Sol": 0.0}])
    row = pipeline.aggregate_per_cell(df).iloc[0]
    assert row["effort_prospection"] == 3


def test_aggregate_exclut_cell_id_manquant():
    """Relevés sans rattachement spatial (cell_id NA) écartés."""
    df = _make_survey_df([
        {"cell_id": pd.NA, "Greg": 9.0},
        {"cell_id": "1_1", "Sol": 0.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    assert len(result) == 1
    assert result.iloc[0]["cell_id"] == "1_1"


def test_aggregate_exclut_campagne_manquante():
    """Relevés inter-campagne (campagne_calc None / décade NA) écartés."""
    df = _make_survey_df([
        {"campagne_calc": None, "campagne_decade": pd.NA, "Greg": 9.0},
        {"campagne_calc": "2010-2011", "campagne_decade": 5, "Sol": 0.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    assert len(result) == 1
    assert result.iloc[0]["severite"] == 0


def test_aggregate_conserve_annees_gregaires_precoces():
    """Fenêtre 2001–2026 préservée : pas de coupe des campagnes grégaires précoces."""
    df = _make_survey_df([
        {"campagne_calc": "2003-2004", "Greg": 1.0},
        {"campagne_calc": "2007-2008", "Greg": 2.0},
    ])
    result = pipeline.aggregate_per_cell(df)
    campagnes = set(result["campagne_calc"])
    assert {"2003-2004", "2007-2008"} <= campagnes


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
    required = {"cell_id", "campagne_calc", "campagne_decade",
                "severite", "binaire", "intensite", "effort_prospection"}
    assert required <= set(df_labels.columns), (
        f"Colonnes manquantes : {required - set(df_labels.columns)}"
    )


def test_severite_valeurs_valides(df_labels):
    """severite est uniquement 0, 1, 2, 3 ou NA."""
    valeurs = set(df_labels["severite"].dropna().unique())
    assert valeurs <= {0, 1, 2, 3}, f"Valeurs inattendues : {valeurs - {0, 1, 2, 3}}"


def test_binaire_coherent_avec_severite(df_labels):
    """binaire == 1 ssi severite >= 1 (sur les lignes labellisées)."""
    labelled = df_labels[df_labels["severite"].notna()]
    attendu = (labelled["severite"] >= 1).astype("Int64")
    assert (labelled["binaire"] == attendu).all()


def test_fenetre_2001_2026_annees_gregaires_precoces(df_labels):
    """Les campagnes grégaires précoces (2004/2007/2008) sont conservées."""
    campagnes = set(df_labels["campagne_calc"].dropna())
    for camp in ("2003-2004", "2007-2008"):
        assert camp in campagnes, f"Campagne précoce {camp} absente de la fenêtre"


def test_effort_toujours_positif(df_labels):
    """Chaque cellule × décade émise correspond à au moins un relevé."""
    assert (df_labels["effort_prospection"] >= 1).all()
