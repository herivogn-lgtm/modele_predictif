"""Tests — Issue #07 : benchmark de modèles ordinaux (sévérité-phase 0–3).

Fonctions pures, indépendantes des modèles entraînés, sur entrées synthétiques :
  - `to_ordinal`            : cadrage d'un score continu en niveau ordinal 0–3 ;
  - `compute_class_weights` : pondération inverse-fréquence (surpondère niv. 3 minoritaire) ;
  - `evaluate_ordinal`      : QWK + rappel des niveaux 2–3 + rappel par niveau ;
  - `aggregate_model_metrics` : agrège les métriques par fold au schéma de `select_robust` ;
  - `build_models`          : registre des estimateurs disponibles.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import benchmark_ordinal_07 as bench


# ---------------------------------------------------------------------------
# to_ordinal — cadrage score continu → niveau ordinal 0–3
# ---------------------------------------------------------------------------

def test_to_ordinal_arrondit_et_borne():
    """Score continu arrondi à l'entier le plus proche puis borné à [0, 3]."""
    y = np.array([-0.4, 0.6, 1.5, 2.49, 3.8])
    assert list(bench.to_ordinal(y)) == [0, 1, 2, 2, 3]


# ---------------------------------------------------------------------------
# compute_class_weights — pondération inverse-fréquence
# ---------------------------------------------------------------------------

def test_class_weights_surpondere_niveau_minoritaire():
    """Le niveau le plus rare reçoit le poids le plus fort, le plus fréquent le plus faible."""
    y = pd.Series([0] * 70 + [1] * 18 + [2] * 6 + [3] * 6)  # niv. 3 minoritaire
    w = bench.compute_class_weights(y)
    assert w[3] > w[0]                      # niveau rare surpondéré vs fréquent
    assert w[3] == max(w.values())          # le plus rare = poids max
    assert w[0] == min(w.values())          # le plus fréquent = poids min


# ---------------------------------------------------------------------------
# evaluate_ordinal — QWK + rappel niveaux 2–3
# ---------------------------------------------------------------------------

def test_evaluate_ordinal_prediction_parfaite():
    """Prédiction parfaite → QWK = 1 et rappel des niveaux 2–3 = 1."""
    y_true = np.array([0, 1, 2, 3, 2, 3])
    y_pred = y_true.copy()
    m = bench.evaluate_ordinal(y_true, y_pred)
    assert m["qwk"] == 1.0
    assert m["recall_23"] == 1.0


def test_evaluate_ordinal_recall_23_ignore_niveaux_01():
    """Le rappel 2–3 ne compte que les vrais niveaux 2 et 3, pas les 0/1."""
    # 4 vrais foyers (2,2,3,3) ; 2 retrouvés → recall_23 = 0.5. Les 0/1 sont ignorés.
    y_true = np.array([0, 1, 2, 2, 3, 3])
    y_pred = np.array([3, 3, 2, 0, 3, 1])   # niv. 0/1 mal prédits mais hors rappel 2–3
    m = bench.evaluate_ordinal(y_true, y_pred)
    assert m["recall_23"] == 0.5


# ---------------------------------------------------------------------------
# aggregate_model_metrics — folds → ligne au schéma select_robust (#06)
# ---------------------------------------------------------------------------

def test_aggregate_model_metrics_schema_select_robust():
    """Les métriques par fold s'agrègent en une ligne consommable par select_robust."""
    import validation_seams as seams

    per_fold = [
        {"campagne_calc": "2015-2016", "qwk": 0.60, "recall_23": 0.80},
        {"campagne_calc": "2016-2017", "qwk": 0.50, "recall_23": 0.40},
    ]
    row = bench.aggregate_model_metrics(per_fold, modele="RF", complexite=3)

    assert row["modele"] == "RF"
    assert row["recall_23"] == 0.60          # moyenne (0.80 + 0.40) / 2
    assert row["qwk"] == 0.55                 # moyenne (0.60 + 0.50) / 2
    assert row["pire_campagne"] == 0.40       # rappel 2–3 de la pire campagne
    assert row["variance_inter_folds"] > 0    # dispersion du rappel entre folds
    assert row["complexite"] == 3

    # La ligne alimente directement select_robust sans transformation.
    metrics = pd.DataFrame([row])
    assert seams.select_robust(metrics, baseline_qwk=0.50) == ["RF"]


# ---------------------------------------------------------------------------
# build_models — registre des estimateurs du benchmark
# ---------------------------------------------------------------------------

def test_build_models_six_modeles_du_prd():
    """Le benchmark enregistre les 6 modèles du PRD §17."""
    models = bench.build_models()
    attendus = {"regression_ordinale", "random_forest", "xgboost",
                "lightgbm", "catboost", "lstm"}
    assert attendus <= set(models)


def test_build_models_cadrage_par_modele():
    """Cadrage ordinal par modèle : baseline/LSTM en régression, arbres en multiclasse."""
    models = bench.build_models()
    assert models["regression_ordinale"].framing == "regression"
    assert models["lstm"].framing == "regression"
    assert models["random_forest"].framing == "multiclass"
    assert models["lightgbm"].framing == "multiclass"


def test_build_models_complexite_pour_tie_break():
    """La complexité (tie-break simplicité de select_robust) classe baseline < … < LSTM."""
    models = bench.build_models()
    comps = {n: m.complexite for n, m in models.items()}
    assert comps["regression_ordinale"] == min(comps.values())  # le plus interprétable
    assert comps["lstm"] == max(comps.values())                 # le moins interprétable


# ---------------------------------------------------------------------------
# run_benchmark — orchestration : folds × modèles × métriques (cœur testable)
# ---------------------------------------------------------------------------

def _synthetic_table(n_campagnes=3, seed=0):
    """Table cellule × décade minimale : features + cible ordinale + campagne."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_campagnes):
        camp = f"{2014 + k}-{2015 + k}"
        for cell in range(40):
            x = rng.normal(size=3)
            # cible corrélée aux features → modèle apprenable
            sev = int(np.clip(round(x[0] + x[1] + 1.5), 0, 3))
            rows.append({
                "cell_id": f"c{cell}", "campagne_calc": camp,
                "f0": x[0], "f1": x[1], "f2": x[2], "severite": sev,
            })
    return pd.DataFrame(rows)


def test_run_benchmark_une_ligne_par_modele():
    """run_benchmark renvoie une ligne de métriques par modèle, au schéma select_robust."""
    import validation_seams as seams

    df = _synthetic_table()
    only = {"regression_ordinale": bench.build_models()["regression_ordinale"]}
    metrics = bench.run_benchmark(
        df, feature_cols=["f0", "f1", "f2"], target="severite",
        campaign_col="campagne_calc", models=only,
    )
    assert list(metrics["modele"]) == ["regression_ordinale"]
    expected = {"modele", "recall_23", "qwk", "variance_inter_folds",
                "pire_campagne", "complexite"}
    assert expected <= set(metrics.columns)
    # consommable tel quel par select_robust
    assert isinstance(seams.select_robust(metrics, baseline_qwk=-1.0), list)


def test_run_benchmark_respecte_le_walk_forward():
    """Le nombre de folds évalués = nombre de campagnes - 1 (expanding window)."""
    df = _synthetic_table(n_campagnes=4)
    only = {"regression_ordinale": bench.build_models()["regression_ordinale"]}
    metrics = bench.run_benchmark(
        df, feature_cols=["f0", "f1", "f2"], target="severite",
        campaign_col="campagne_calc", models=only,
    )
    # 4 campagnes → 3 folds agrégés dans la ligne du modèle
    assert metrics.loc[0, "n_folds"] == 3


def test_run_benchmark_resiste_a_un_modele_defaillant():
    """Un modèle qui lève en entraînement est consigné (qwk NaN) sans tuer le benchmark."""
    def _boom():
        raise RuntimeError("entraînement impossible")

    df = _synthetic_table()
    models = {
        "regression_ordinale": bench.build_models()["regression_ordinale"],
        "defaillant": bench.ModelSpec("multiclass", 9, _boom),
    }
    metrics = bench.run_benchmark(
        df, feature_cols=["f0", "f1", "f2"], target="severite",
        campaign_col="campagne_calc", models=models,
    )
    assert set(metrics["modele"]) == {"regression_ordinale", "defaillant"}
    row = metrics.set_index("modele").loc["defaillant"]
    assert np.isnan(row["qwk"])              # consigné en échec, pas de crash
    # le modèle sain reste évalué normalement
    assert not np.isnan(metrics.set_index("modele").loc["regression_ordinale"]["qwk"])


def test_run_benchmark_detail_par_campagne():
    """return_detail=True ajoute les métriques ventilées par (modèle, campagne) (critère #07)."""
    df = _synthetic_table(n_campagnes=3)
    only = {"regression_ordinale": bench.build_models()["regression_ordinale"]}
    summary, detail = bench.run_benchmark(
        df, feature_cols=["f0", "f1", "f2"], target="severite",
        campaign_col="campagne_calc", models=only, return_detail=True,
    )
    # une ligne par (modèle, campagne testée) — 3 campagnes → 2 folds
    assert len(detail) == 2
    assert set(detail["modele"]) == {"regression_ordinale"}
    assert {"modele", "campagne_calc", "qwk", "recall_23"} <= set(detail.columns)
    # le résumé reste une ligne par modèle
    assert list(summary["modele"]) == ["regression_ordinale"]
