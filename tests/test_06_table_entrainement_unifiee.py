"""Tests unitaires et intégration — Issue #06 : Table d'entraînement ML unifiée."""

import os
import sys
import tempfile
import warnings
from pathlib import Path

import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import table_entrainement_06 as pipeline

DATA_DIR    = Path(__file__).parent.parent / "data"
PARQUET_OUT = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_labels_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame minimal imitant le parquet #03."""
    defaults = {
        "rn_num": 1,
        "rn_nom": "RN1",
        "campagne_calc": "2010-2011",
        "campagne_decade": 5,
        "effort_prospection": 3,
        "label": 1,
    }
    records = [{**defaults, **r} for r in rows]
    df = pd.DataFrame(records)
    df["rn_num"] = df["rn_num"].astype("Int64")
    df["label"]  = df["label"].astype("Int64")
    return df


def _make_features_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame minimal imitant le parquet #05."""
    defaults = {
        "region_id":       1,
        "campaign":        "2010-2011",
        "decade_num":      5,
        "date_start":      pd.Timestamp("2010-10-01"),
        "chirps_sum_mean": 80.0,
        "ndvi_mean":       0.45,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _labels_to_parquet(rows: list[dict]) -> str:
    """Écrit un labels_df synthétique dans un fichier Parquet temporaire."""
    df = _make_labels_df(rows)
    f = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    f.close()
    df.to_parquet(f.name, index=False)
    return f.name


# ---------------------------------------------------------------------------
# assign_split — cas canoniques
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("campagne, label, expected", [
    ("2001-2002", 1,     "train"),
    ("2001-2002", 0,     "train"),
    ("2015-2016", 1,     "train"),        # frontière entraînement
    ("2016-2017", 1,     "validation"),   # frontière validation
    ("2021-2022", 0,     "validation"),
    ("2010-2011", pd.NA, "inference"),    # label NA → inference
    ("2023-2024", pd.NA, "inference"),    # campagne exclue → inference
])
def test_assign_split(campagne, label, expected):
    assert pipeline.assign_split(campagne, label) == expected


# ---------------------------------------------------------------------------
# join_features — alignement des clés et valeurs
# ---------------------------------------------------------------------------

def test_join_features_renames_keys():
    """join_features traduit region_id/campaign/decade_num vers les clés #03."""
    labels   = _make_labels_df([{"rn_num": 1, "campagne_calc": "2010-2011", "campagne_decade": 5}])
    features = _make_features_df([{"region_id": 1, "campaign": "2010-2011", "decade_num": 5}])

    result = pipeline.join_features(labels, features)
    assert "rn_num"          in result.columns
    assert "campagne_calc"   in result.columns
    assert "campagne_decade" in result.columns
    assert "region_id"  not in result.columns
    assert "campaign"   not in result.columns
    assert "decade_num" not in result.columns


def test_join_features_valeurs_transferees():
    """La valeur chirps_sum_mean est bien rattachée après jointure."""
    labels   = _make_labels_df([{"rn_num": 1, "campagne_calc": "2010-2011", "campagne_decade": 5}])
    features = _make_features_df([{"region_id": 1, "campaign": "2010-2011", "decade_num": 5,
                                    "chirps_sum_mean": 99.5}])
    result = pipeline.join_features(labels, features)
    assert result.iloc[0]["chirps_sum_mean"] == pytest.approx(99.5)


def test_join_features_no_match_nan():
    """Absence de correspondance → NaN dans la colonne feature (LEFT JOIN)."""
    labels   = _make_labels_df([{"rn_num": 2, "campagne_calc": "2010-2011", "campagne_decade": 5}])
    features = _make_features_df([{"region_id": 1, "campaign": "2010-2011", "decade_num": 5}])
    result = pipeline.join_features(labels, features)
    assert pd.isna(result.iloc[0]["chirps_sum_mean"])


def test_join_features_effort_preserve():
    """effort_prospection n'est pas altéré par la jointure."""
    labels   = _make_labels_df([{"effort_prospection": 7}])
    features = _make_features_df([{}])
    result = pipeline.join_features(labels, features)
    assert result.iloc[0]["effort_prospection"] == 7


# ---------------------------------------------------------------------------
# build_training_table — propriétés structurelles sur données synthétiques
# ---------------------------------------------------------------------------

_DEFAULT_ROWS = [
    {"campagne_calc": "2010-2011", "campagne_decade": 5,  "label": 1,     "effort_prospection": 2},
    {"campagne_calc": "2010-2011", "campagne_decade": 10, "label": pd.NA, "effort_prospection": 0},
    {"campagne_calc": "2018-2019", "campagne_decade": 5,  "label": 0,     "effort_prospection": 1},
    {"campagne_calc": "2023-2024", "campagne_decade": 5,  "label": pd.NA, "effort_prospection": 0},
]


@pytest.fixture(scope="module")
def df_synthetic():
    tmp = _labels_to_parquet(_DEFAULT_ROWS)
    try:
        yield pipeline.build_training_table(Path(tmp))
    finally:
        os.unlink(tmp)


def test_no_masked_in_train(df_synthetic):
    """Aucune cellule split='train' n'a label=NA."""
    train = df_synthetic[df_synthetic["split"] == "train"]
    assert len(train) > 0, "Aucune ligne train dans les données synthétiques"
    assert train["label"].notna().all()


def test_no_masked_in_validation(df_synthetic):
    """Aucune cellule split='validation' n'a label=NA."""
    val = df_synthetic[df_synthetic["split"] == "validation"]
    assert len(val) > 0, "Aucune ligne validation dans les données synthétiques"
    assert val["label"].notna().all()


def test_inference_a_label_na(df_synthetic):
    """Toutes les cellules split='inference' ont label=NA."""
    inf = df_synthetic[df_synthetic["split"] == "inference"]
    assert len(inf) > 0, "Aucune ligne inference dans les données synthétiques"
    assert inf["label"].isna().all()


def test_split_valeurs_valides(df_synthetic):
    """split contient uniquement les valeurs autorisées."""
    assert set(df_synthetic["split"].unique()) <= {"train", "validation", "inference"}


def test_walk_forward_no_campaign_in_train_and_validation(df_synthetic):
    """Aucune campagne_calc n'apparaît à la fois dans train et dans validation."""
    split_per_camp = df_synthetic.groupby("campagne_calc")["split"].apply(frozenset)
    leaked = split_per_camp[
        split_per_camp.apply(lambda s: "train" in s and "validation" in s)
    ]
    assert len(leaked) == 0, f"Campagnes en fuite : {list(leaked.index)}"


def test_colonnes_garanties_presentes(df_synthetic):
    """Les 7 colonnes garanties sont toujours présentes."""
    required = {"rn_num", "rn_nom", "campagne_calc", "campagne_decade",
                "split", "effort_prospection", "label"}
    assert required <= set(df_synthetic.columns)


def test_features_absent_sans_warning_si_path_none():
    """Aucun avertissement si features_path=None."""
    tmp = _labels_to_parquet([{"campagne_calc": "2010-2011", "label": 1}])
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pipeline.build_training_table(Path(tmp), features_path=None)
        assert len(w) == 0
    finally:
        os.unlink(tmp)


def test_features_absent_warning_si_path_inexistant():
    """Un avertissement est émis si features_path pointe vers un fichier inexistant."""
    tmp = _labels_to_parquet([{"campagne_calc": "2010-2011", "label": 1}])
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pipeline.build_training_table(
                Path(tmp),
                features_path=Path("inexistant.parquet"),
            )
        assert any("features" in str(warning.message).lower() for warning in w)
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Tests d'intégration — requièrent le parquet de sortie
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def df_ml():
    if not PARQUET_OUT.exists():
        pytest.skip(
            "Parquet #06 absent — lancer d'abord : python src/table_entrainement_06.py"
        )
    return pd.read_parquet(PARQUET_OUT)


def test_colonnes_obligatoires_presentes(df_ml):
    required = {"rn_num", "rn_nom", "campagne_calc", "campagne_decade",
                "split", "effort_prospection", "label"}
    assert required <= set(df_ml.columns), (
        f"Colonnes manquantes : {required - set(df_ml.columns)}"
    )


def test_split_valeurs_valides_integration(df_ml):
    valeurs = set(df_ml["split"].unique())
    assert valeurs <= {"train", "validation", "inference"}, (
        f"Valeurs split inattendues : {valeurs - {'train','validation','inference'}}"
    )


def test_train_sans_label_na(df_ml):
    train = df_ml[df_ml["split"] == "train"]
    assert train["label"].notna().all(), "Des cellules train ont label=NA"


def test_validation_sans_label_na(df_ml):
    val = df_ml[df_ml["split"] == "validation"]
    assert val["label"].notna().all(), "Des cellules validation ont label=NA"


def test_inference_label_na(df_ml):
    inf = df_ml[df_ml["split"] == "inference"]
    assert inf["label"].isna().all(), "Des cellules inference ont label non-NA"


def test_campagne_2023_2024_inference(df_ml):
    """Toutes les lignes de la campagne 2023-2024 ont split='inference'."""
    subset = df_ml[df_ml["campagne_calc"] == "2023-2024"]
    if len(subset) > 0:
        assert (subset["split"] == "inference").all(), (
            "Campagne 2023-2024 a des lignes hors split='inference'"
        )


def test_walk_forward_frontieres_campagne(df_ml):
    """Aucune campagne_calc n'est à la fois dans train et validation."""
    split_per_camp = df_ml.groupby("campagne_calc")["split"].apply(frozenset)
    leaked = split_per_camp[
        split_per_camp.apply(lambda s: "train" in s and "validation" in s)
    ]
    assert len(leaked) == 0, f"Campagnes en fuite : {list(leaked.index)}"


def test_effort_prospection_colonne_feature(df_ml):
    """effort_prospection est présent, sans NA, valeurs ≥ 0."""
    assert "effort_prospection" in df_ml.columns
    assert df_ml["effort_prospection"].notna().all()
    assert (df_ml["effort_prospection"] >= 0).all()


def test_90_regions_presentes(df_ml):
    """Les 90 régions naturelles sont représentées."""
    n = df_ml["rn_num"].nunique()
    assert n == 90, f"Nombre de régions naturelles : {n} (attendu 90)"


def test_campagne_decade_plage(df_ml):
    """campagne_decade est dans [1, 30]."""
    assert df_ml["campagne_decade"].between(1, 30).all(), (
        "Des valeurs campagne_decade hors [1, 30] trouvées"
    )
