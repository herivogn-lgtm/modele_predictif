"""Tests — Issue #08 : rapport de performance walk-forward par campagne (Pipeline 10).

Fonctions pures de métriques, sur entrées synthétiques :
  - `derive_binaire`     : binaire présence dérivé de la sévérité ordinale (sév ≥ 1) ;
  - `auc_binaire`        : AUC du binaire dérivé vs score de présence ;
  - `calibration_table`  : fiabilité des probabilités (proba moyenne vs fréquence observée) ;
  - `gain_lift_table`    : courbe de gain / lift (gain opérationnel) ;
  - `rapport_par_campagne` : assemblage du rapport ventilé par campagne + robustesse.

La qualité prédictive réelle se mesure hors pytest (run sur données réelles) ; ici on
vérifie le comportement des calculs de métriques.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import rapport_performance_08 as rapport


# ---------------------------------------------------------------------------
# derive_binaire — binaire présence dérivé (sévérité ≥ 1)
# ---------------------------------------------------------------------------

def test_derive_binaire_presence_des_le_niveau_1():
    """Absence (0) → 0 ; tout niveau 1–3 → 1 (présence), conforme PRD (sév ≥ 1)."""
    severite = np.array([0, 1, 2, 3, 0, 2])
    assert list(rapport.derive_binaire(severite)) == [0, 1, 1, 1, 0, 1]


# ---------------------------------------------------------------------------
# auc_binaire — AUC du binaire dérivé vs score de présence
# ---------------------------------------------------------------------------

def test_auc_binaire_separation_parfaite():
    """Un score qui ordonne parfaitement présences au-dessus des absences → AUC = 1."""
    y_bin = np.array([0, 0, 0, 1, 1, 1])
    score = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
    assert rapport.auc_binaire(y_bin, score) == 1.0


def test_auc_binaire_classe_unique_nan():
    """Aucune présence dans le fold → AUC indéfinie (NaN), pas d'exception."""
    y_bin = np.array([0, 0, 0, 0])
    score = np.array([0.1, 0.4, 0.2, 0.9])
    assert np.isnan(rapport.auc_binaire(y_bin, score))


# ---------------------------------------------------------------------------
# calibration_table — fiabilité des probabilités (proba moyenne vs fréquence)
# ---------------------------------------------------------------------------

def test_calibration_parfaite_freq_egale_proba():
    """Probabilités parfaitement calibrées → fréquence observée = proba moyenne par bin."""
    # Deux groupes : proba 0.2 (2/10 positifs), proba 0.8 (8/10 positifs).
    proba = np.array([0.2] * 10 + [0.8] * 10)
    y_bin = np.array([1, 1] + [0] * 8 + [1] * 8 + [0, 0])
    table = rapport.calibration_table(y_bin, proba, n_bins=10)

    # Une ligne par bin non vide, schéma du diagramme de fiabilité.
    assert {"proba_moyenne", "freq_observee", "n"} <= set(table.columns)
    assert (table["n"] > 0).all()                       # bins vides exclus
    # Dans chaque bin peuplé, fréquence observée = proba moyenne (calibration parfaite).
    np.testing.assert_allclose(
        table["freq_observee"].to_numpy(), table["proba_moyenne"].to_numpy(), atol=1e-9
    )


# ---------------------------------------------------------------------------
# gain_lift_table — courbe de gain / lift (gain opérationnel)
# ---------------------------------------------------------------------------

def test_gain_lift_modele_parfait():
    """Un modèle parfait concentre les positifs en tête → lift maximal au 1er décile."""
    # 100 cellules, 20 vraies présences = les 20 plus hauts scores.
    score = np.arange(100, dtype=float)
    y_bin = (score >= 80).astype(int)               # 20 positifs (taux base = 0.2)
    table = rapport.gain_lift_table(y_bin, score, n_bins=10)

    assert {"pop_cumulee", "gain_cumule", "lift"} <= set(table.columns)
    # Gain cumulé monotone croissant, atteint 1.0 (tous les positifs captés au final).
    gains = table["gain_cumule"].to_numpy()
    assert np.all(np.diff(gains) >= -1e-9)
    assert gains[-1] == 1.0
    # 1er décile = 10 % de la population mais 50 % des positifs → lift = 5 (= 1/0.2, max).
    first = table.iloc[0]
    assert first["lift"] == 5.0
    assert first["gain_cumule"] == 0.5


# ---------------------------------------------------------------------------
# rapport_par_campagne — assemblage du rapport ventilé par campagne
# ---------------------------------------------------------------------------

def _fold(campagne, y_true, y_pred, score):
    return {"campagne_calc": campagne, "y_true": np.array(y_true),
            "y_pred": np.array(y_pred), "score": np.array(score)}


def test_rapport_par_campagne_une_ligne_par_fold():
    """Une ligne par campagne testée, avec QWK, rappel 2–3 et AUC binaire dérivé."""
    folds = [
        _fold("2014-2015", [0, 1, 2, 3], [0, 1, 2, 3], [0.1, 0.6, 0.8, 0.9]),
        _fold("2015-2016", [0, 1, 2, 3], [0, 1, 2, 3], [0.2, 0.7, 0.85, 0.95]),
    ]
    rep = rapport.rapport_par_campagne(folds)

    assert list(rep["campagne_calc"]) == ["2014-2015", "2015-2016"]
    assert {"qwk", "recall_23", "auc_binaire"} <= set(rep.columns)
    # Prédictions parfaites + score séparant l'absence → métriques idéales par campagne.
    np.testing.assert_allclose(rep["qwk"], 1.0)
    np.testing.assert_allclose(rep["recall_23"], 1.0)
    np.testing.assert_allclose(rep["auc_binaire"], 1.0)


# ---------------------------------------------------------------------------
# resume_robustesse — robustesse = variance inter-folds + pire campagne (critère #3)
# ---------------------------------------------------------------------------

def test_resume_robustesse_pire_campagne_et_variance():
    """La robustesse est jugée sur la pire campagne et la dispersion, pas la moyenne."""
    rep = pd.DataFrame({
        "campagne_calc": ["2014-2015", "2015-2016"],
        "qwk":         [0.6, 0.4],
        "recall_23":   [1.0, 0.5],
        "auc_binaire": [0.9, 0.7],
    })
    r = rapport.resume_robustesse(rep)

    assert r["auc_binaire_moyen"] == 0.8
    assert r["auc_binaire_pire_campagne"] == 0.7      # min, pas la meilleure
    assert r["recall_23_pire_campagne"] == 0.5
    assert r["auc_binaire_variance_inter_folds"] > 0  # dispersion entre campagnes


def test_resume_robustesse_ignore_campagnes_degenerees():
    """Une campagne à métrique indéfinie (NaN) n'écrase pas les agrégats."""
    rep = pd.DataFrame({
        "campagne_calc": ["2014-2015", "2015-2016"],
        "qwk":         [0.6, 0.4],
        "recall_23":   [0.8, np.nan],                 # fold sans foyer
        "auc_binaire": [0.9, np.nan],                 # fold à classe unique
    })
    r = rapport.resume_robustesse(rep)
    assert r["recall_23_pire_campagne"] == 0.8        # NaN ignoré
    assert r["auc_binaire_moyen"] == 0.9


# ---------------------------------------------------------------------------
# presence_from_proba — proba multiclasse 0–3 → proba de présence (sév ≥ 1)
# ---------------------------------------------------------------------------

def test_presence_from_proba_somme_des_niveaux_positifs():
    """Proba de présence = somme des probas des niveaux ≥ 1 (= 1 − P(absence))."""
    proba = np.array([[0.7, 0.2, 0.1],
                      [0.1, 0.3, 0.6]])
    classes = np.array([0, 1, 2])
    np.testing.assert_allclose(rapport.presence_from_proba(proba, classes), [0.3, 0.9])


def test_presence_from_proba_classes_partielles():
    """Si un fold n'a pas le niveau 0, toute la masse est de la présence."""
    proba = np.array([[0.4, 0.6],
                      [0.9, 0.1]])
    classes = np.array([2, 3])                        # aucun niveau 0/1
    np.testing.assert_allclose(rapport.presence_from_proba(proba, classes), [1.0, 1.0])
