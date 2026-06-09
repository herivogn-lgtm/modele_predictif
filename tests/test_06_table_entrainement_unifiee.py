"""Tests — Issue #05 : Table d'entraînement cellule 1 km × décade + surface de prédiction.

Pipeline #06 assemble la table unifiée à la maille cellule 1 km × décade :
  - features laggées (#05) comme épine dorsale (toute la grille × décades) ;
  - cible ordinale `severite` 0–3 + `binaire` dérivé + `intensite` optionnelle (#03)
    jointes en LEFT sur cell_id × campagne_calc × campagne_decade ;
  - cellules non prospectées = surface de prédiction (covariables présentes, label NA),
    distinctes des vraies absences (severite=0).

Le découpage walk-forward (split) relève de l'issue #06, pas de #05.
"""

import sys
from pathlib import Path

import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import table_entrainement_06 as pipeline

DATA_DIR    = Path(__file__).parent.parent / "data"
PARQUET_OUT = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"

KEYS = ["cell_id", "campagne_calc", "campagne_decade"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_features(rows: list[dict]) -> pd.DataFrame:
    """Épine dorsale features (#05) : grille cellule × décade + covariables."""
    defaults = {
        "cell_id":         1,
        "campagne_calc":   "2010-2011",
        "campagne_decade": 5,
        "AIRE_CODE":       "AMI",
        "ndvi_mean":       0.45,
        "chirps_sum_mean": 80.0,
    }
    df = pd.DataFrame([{**defaults, **r} for r in rows])
    df["cell_id"] = df["cell_id"].astype("Int64")
    return df


def _make_labels(rows: list[dict]) -> pd.DataFrame:
    """Cellules prospectées (#03) : severite / binaire / intensite / effort."""
    defaults = {
        "cell_id":            1,
        "campagne_calc":      "2010-2011",
        "campagne_decade":    5,
        "severite":           1,
        "intensite":          float("nan"),
        "effort_prospection": 2,
    }
    df = pd.DataFrame([{**defaults, **r} for r in rows])
    df["cell_id"]   = df["cell_id"].astype("Int64")
    df["severite"]  = df["severite"].astype("Int64")
    df["binaire"]   = df["severite"].apply(
        lambda s: pd.NA if pd.isna(s) else (1 if s >= 1 else 0)
    ).astype("Int64")
    return df


# ---------------------------------------------------------------------------
# assemble_table — jointure features ↔ labels
# ---------------------------------------------------------------------------

def test_assemble_joint_severite_sur_cellule_observee():
    """Une cellule observée hérite de sa sévérité après jointure."""
    features = _make_features([{"cell_id": 1}])
    labels   = _make_labels([{"cell_id": 1, "severite": 2}])

    result = pipeline.assemble_table(features, labels)

    assert len(result) == 1
    assert result.iloc[0]["severite"] == 2


def test_assemble_colonnes_attendues_presentes():
    """Clés, covariable et les trois cibles (severite/binaire/intensite) présentes."""
    result = pipeline.assemble_table(_make_features([{}]), _make_labels([{}]))
    attendues = set(KEYS) | {"ndvi_mean", "severite", "binaire", "intensite"}
    assert attendues <= set(result.columns), attendues - set(result.columns)


def test_cellule_non_prospectee_est_surface_de_prediction():
    """Cellule présente en features mais absente des labels : covariable gardée, label NA."""
    features = _make_features([
        {"cell_id": 1, "ndvi_mean": 0.30},   # prospectée
        {"cell_id": 2, "ndvi_mean": 0.70},   # non prospectée
    ])
    labels = _make_labels([{"cell_id": 1, "severite": 1}])

    result = pipeline.assemble_table(features, labels)
    cell2 = result[result["cell_id"] == 2].iloc[0]

    assert cell2["ndvi_mean"] == pytest.approx(0.70)   # covariable présente
    assert pd.isna(cell2["severite"])                  # label inconnu → à prédire
    assert pd.isna(cell2["binaire"])


def test_absence_distincte_de_non_observee():
    """severite=0 (relevé à zéro) ≠ severite=NA (non prospectée) via la colonne a_predire."""
    features = _make_features([
        {"cell_id": 1},   # observée à zéro → vraie absence
        {"cell_id": 2},   # non prospectée → surface de prédiction
    ])
    labels = _make_labels([{"cell_id": 1, "severite": 0}])

    result = pipeline.assemble_table(features, labels)
    absence    = result[result["cell_id"] == 1].iloc[0]
    a_predire  = result[result["cell_id"] == 2].iloc[0]

    assert absence["severite"] == 0           # absence vérifiée
    assert bool(absence["a_predire"]) is False

    assert pd.isna(a_predire["severite"])      # jamais observée
    assert bool(a_predire["a_predire"]) is True


# ---------------------------------------------------------------------------
# Tests d'intégration — requièrent le parquet de sortie (skip sinon)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def df_ml():
    if not PARQUET_OUT.exists():
        pytest.skip(
            "Parquet #06 absent — lancer d'abord : python src/table_entrainement_06.py "
            "(nécessite des features #05 à la maille cell_id, issue #04)"
        )
    return pd.read_parquet(PARQUET_OUT)


def test_colonnes_obligatoires_integration(df_ml):
    required = set(KEYS) | {"severite", "binaire", "intensite", "a_predire"}
    assert required <= set(df_ml.columns), required - set(df_ml.columns)


def test_surface_de_prediction_presente_integration(df_ml):
    """La table réelle contient une surface de prédiction (cellules non observées)."""
    assert df_ml["a_predire"].any(), "Aucune cellule à prédire — surface absente"


def test_absences_et_predictions_disjointes_integration(df_ml):
    """a_predire est exactement l'ensemble des severite NA (absences=0 exclues)."""
    assert (df_ml["a_predire"] == df_ml["severite"].isna()).all()
