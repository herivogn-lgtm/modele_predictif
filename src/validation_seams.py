"""Seams de validation — Issue #06.

Fonctions pures, indépendantes de tout algorithme, partagées par les pipelines
modèles (07/08) et le rapport (10) :

  - `walk_forward_split` : génère des folds chronologiques expanding-window à partir
    des campagnes. La campagne 2023-2024 (labels absents) est sautée. Chaque fold teste
    sur une campagne strictement future par rapport à son train — aucun chevauchement.

  - `select_robust` : classe des modèles décrits par des métriques pré-agrégées. Filtre
    sur la contrainte QWK ≥ baseline, puis ordonne par rappel des niveaux 2–3 (priorité
    « ne pas manquer un foyer »), départage par variance inter-folds, pire campagne, et
    enfin simplicité/interprétabilité.
"""

from __future__ import annotations

import pandas as pd

# Campagnes sans labels — exclues de la validation walk-forward (ADR 0004).
SKIP_CAMPAGNES = frozenset({"2023-2024"})


def _annee_debut(campagne: str) -> int:
    """Année de début d'une campagne au format 'YYYY-YYYY'."""
    return int(campagne.split("-")[0])


def walk_forward_split(campagnes) -> list[tuple[list[str], str]]:
    """Folds walk-forward expanding-window à partir d'une collection de campagnes.

    Retourne une liste de `(campagnes_train, campagne_test)`, triée chronologiquement :
    chaque fold entraîne sur toutes les campagnes antérieures et teste sur la suivante.
    Les campagnes de `SKIP_CAMPAGNES` (2023-2024) sont retirées au préalable.
    """
    camps = sorted(set(campagnes) - SKIP_CAMPAGNES, key=_annee_debut)
    return [(camps[:i], camps[i]) for i in range(1, len(camps))]


def select_robust(metrics: pd.DataFrame, baseline_qwk: float) -> list[str]:
    """Classe les modèles du plus robuste au moins robuste (noms, meilleur en tête).

    `metrics` : une ligne par modèle, colonnes `modele`, `recall_23`, `qwk`,
    `variance_inter_folds`, `pire_campagne`, `complexite`.

    Priorité « ne pas manquer un foyer » : meilleur rappel des niveaux 2–3 d'abord.
    """
    eligibles = metrics[metrics["qwk"] >= baseline_qwk]
    ranked = eligibles.sort_values(
        ["recall_23", "variance_inter_folds", "pire_campagne", "complexite"],
        ascending=[False, True, False, True],
    )
    return ranked["modele"].tolist()
