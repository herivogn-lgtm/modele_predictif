"""Tests — Issue #09 : sorties opérationnelles, carte de sévérité-phase 0–3 à 1 km.

Fonctions pures de restitution, sur entrées synthétiques :
  - `derive_binary`     : binaire présence dérivé de la sévérité ordinale (sév ≥ 1) ;
  - `to_severity_map`   : agrégation décade → mois (sévérité = phase max du mois) ;
  - `aggregate_by_aire` : agrégat mensuel par aire complémentaire AMI/ATM/AD/AGT.

La qualité prédictive réelle se mesure hors pytest (rapport #08 sur données réelles) ;
ici on vérifie le comportement des transformations de restitution.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import sorties_operationnelles_09 as sorties


# ---------------------------------------------------------------------------
# derive_binary — binaire présence dérivé (sévérité ≥ 1)
# ---------------------------------------------------------------------------

def test_derive_binary_presence_des_le_niveau_1():
    """Absence (0) → 0 ; tout niveau 1–3 → 1 (présence), conforme PRD (sév ≥ 1)."""
    severite = np.array([0, 1, 2, 3, 0, 2])
    assert list(sorties.derive_binary(severite)) == [0, 1, 1, 1, 0, 1]


# ---------------------------------------------------------------------------
# to_severity_map — agrégation décade → mois (sévérité = phase max du mois)
# ---------------------------------------------------------------------------

def test_to_severity_map_phase_max_par_mois():
    """La sévérité mensuelle d'une cellule = phase max sur les 3 décades du mois (PRD)."""
    # Cellule A : décades 1–3 (mois 1) sévérités 1/3/0 → mois 1 = 3 ; décade 4 (mois 2) = 2.
    df = pd.DataFrame({
        "cell_id":         ["A", "A", "A", "A"],
        "AIRE_CODE":       [1, 1, 1, 1],
        "campagne_calc":   ["2025-2026"] * 4,
        "campagne_decade": [1, 2, 3, 4],
        "severite":        [1, 3, 0, 2],
    })
    carte = sorties.to_severity_map(df)

    # Une ligne par (cellule × campagne × mois), avec la colonne mois_campagne.
    assert "mois_campagne" in carte.columns
    m = carte.set_index("mois_campagne")["severite"]
    assert m.loc[1] == 3      # max(1, 3, 0) sur le mois 1
    assert m.loc[2] == 2      # décade 4 isolée → mois 2
    # L'aire est conservée pour l'agrégat opérationnel aval.
    assert (carte["AIRE_CODE"] == 1).all()


# ---------------------------------------------------------------------------
# aggregate_by_aire — agrégat mensuel par aire complémentaire (AMI/ATM/AD/AGT)
# ---------------------------------------------------------------------------

def test_aggregate_by_aire_severite_max_et_comptage_foyers():
    """Par aire × campagne × mois : sévérité max + nombre de cellules-foyer (sév ≥ 2)."""
    # Aire 1, mois 1 : cellules sévérité 0/2/3 → max 3, 2 foyers (niveaux 2–3) sur 3 cellules.
    carte = pd.DataFrame({
        "cell_id":       ["A", "B", "C", "D"],
        "AIRE_CODE":     [1, 1, 1, 2],
        "campagne_calc": ["2025-2026"] * 4,
        "mois_campagne": [1, 1, 1, 1],
        "severite":      [0, 2, 3, 1],
    })
    agg = sorties.aggregate_by_aire(carte)

    a1 = agg[(agg["AIRE_CODE"] == 1) & (agg["mois_campagne"] == 1)].iloc[0]
    assert a1["severite_max"] == 3
    assert a1["n_cellules"] == 3
    assert a1["n_cellules_foyer"] == 2          # niveaux 2 et 3
    # L'aire 2 (sévérité 1 seule) : présence mais aucun foyer.
    a2 = agg[agg["AIRE_CODE"] == 2].iloc[0]
    assert a2["severite_max"] == 1
    assert a2["n_cellules_foyer"] == 0
