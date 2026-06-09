"""Tests — Issue #06 : seams de validation walk_forward_split + select_robust.

Deux fonctions pures, indépendantes de tout algorithme :
  - `walk_forward_split(campagnes)` : folds chronologiques expanding-window, campagne
    2023-2024 sautée (labels absents), sans chevauchement temporel train/test ;
  - `select_robust(metrics, baseline_qwk)` : classe les modèles par rappel des niveaux
    2–3 sous contrainte QWK ≥ baseline, départage par variance inter-folds puis simplicité.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import validation_seams as seams


# ---------------------------------------------------------------------------
# walk_forward_split — folds chronologiques expanding-window
# ---------------------------------------------------------------------------

def test_walk_forward_folds_chronologiques():
    """Campagnes désordonnées → folds triés, train = passé, test = campagne suivante."""
    camps = ["2016-2017", "2014-2015", "2015-2016"]
    folds = seams.walk_forward_split(camps)
    assert folds == [
        (["2014-2015"], "2015-2016"),
        (["2014-2015", "2015-2016"], "2016-2017"),
    ]


def test_walk_forward_saute_2023_2024():
    """La campagne 2023-2024 (labels absents) n'apparaît ni en test ni dans un train."""
    camps = ["2022-2023", "2023-2024", "2024-2025"]
    folds = seams.walk_forward_split(camps)
    tests  = [test for _, test in folds]
    trains = [c for train, _ in folds for c in train]
    assert "2023-2024" not in tests
    assert "2023-2024" not in trains
    # 2024-2025 teste directement après 2022-2023, sans 2023-2024 intercalée
    assert folds == [(["2022-2023"], "2024-2025")]


def test_walk_forward_aucun_chevauchement_temporel():
    """Pour chaque fold, toutes les campagnes du train précèdent strictement le test."""
    camps = [f"{y}-{y + 1}" for y in range(2010, 2020)]
    folds = seams.walk_forward_split(camps)
    for train, test in folds:
        test_year = int(test.split("-")[0])
        assert all(int(c.split("-")[0]) < test_year for c in train)


def test_walk_forward_une_seule_campagne_aucun_fold():
    """Une seule campagne exploitable → pas de fold possible (pas de passé à tester)."""
    assert seams.walk_forward_split(["2014-2015"]) == []
    assert seams.walk_forward_split(["2023-2024"]) == []   # tout sauté


# ---------------------------------------------------------------------------
# select_robust — classement des modèles sur métriques pré-agrégées
# ---------------------------------------------------------------------------

def _metrics(rows: list[dict]) -> pd.DataFrame:
    """Une ligne par modèle, métriques pré-agrégées."""
    defaults = {
        "modele":               "M",
        "recall_23":            0.50,   # rappel niveaux 2–3 (↑ meilleur)
        "qwk":                  0.60,   # quadratic weighted kappa (↑ meilleur)
        "variance_inter_folds": 0.01,   # dispersion entre folds (↓ meilleur)
        "pire_campagne":        0.40,   # rappel 2–3 de la pire campagne (↑ meilleur)
        "complexite":           2,      # simplicité/interprétabilité (↓ meilleur)
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def test_select_robust_classe_par_rappel_23():
    """À contrainte QWK respectée, le meilleur rappel 2–3 passe en tête."""
    metrics = _metrics([
        {"modele": "A", "recall_23": 0.60},
        {"modele": "B", "recall_23": 0.80},
    ])
    assert seams.select_robust(metrics, baseline_qwk=0.40) == ["B", "A"]


def test_select_robust_filtre_qwk_sous_baseline():
    """Un modèle au meilleur rappel mais QWK < baseline est écarté du classement."""
    metrics = _metrics([
        {"modele": "A", "recall_23": 0.90, "qwk": 0.30},   # QWK trop bas → exclu
        {"modele": "B", "recall_23": 0.50, "qwk": 0.70},
    ])
    assert seams.select_robust(metrics, baseline_qwk=0.50) == ["B"]


def test_select_robust_qwk_egal_baseline_inclus():
    """QWK exactement égal à la baseline satisfait la contrainte (≥)."""
    metrics = _metrics([{"modele": "A", "qwk": 0.50}])
    assert seams.select_robust(metrics, baseline_qwk=0.50) == ["A"]


def test_select_robust_departage_variance_inter_folds():
    """Rappel 2–3 égal → la variance inter-folds la plus faible (plus robuste) gagne."""
    metrics = _metrics([
        {"modele": "A", "recall_23": 0.70, "variance_inter_folds": 0.05},
        {"modele": "B", "recall_23": 0.70, "variance_inter_folds": 0.01},
    ])
    assert seams.select_robust(metrics, baseline_qwk=0.40) == ["B", "A"]


def test_select_robust_departage_pire_campagne():
    """Rappel et variance égaux → la meilleure 'pire campagne' (↑) gagne."""
    metrics = _metrics([
        {"modele": "A", "recall_23": 0.70, "variance_inter_folds": 0.02, "pire_campagne": 0.30},
        {"modele": "B", "recall_23": 0.70, "variance_inter_folds": 0.02, "pire_campagne": 0.55},
    ])
    assert seams.select_robust(metrics, baseline_qwk=0.40) == ["B", "A"]


def test_select_robust_departage_simplicite():
    """Tout égal → le modèle le plus simple/interprétable (complexite ↓) gagne."""
    metrics = _metrics([
        {"modele": "A", "recall_23": 0.70, "variance_inter_folds": 0.02,
         "pire_campagne": 0.40, "complexite": 5},
        {"modele": "B", "recall_23": 0.70, "variance_inter_folds": 0.02,
         "pire_campagne": 0.40, "complexite": 1},
    ])
    assert seams.select_robust(metrics, baseline_qwk=0.40) == ["B", "A"]
