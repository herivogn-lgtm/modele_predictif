"""Pipeline #05 — Feature engineering acridologique à la maille cellule 1 km × décade.

À partir des variables environnementales GEE (#04, maille cellule), calcule :
  - pop_consecutive       : mois consécutifs en Plage d'Optimum Pluviométrique
                            (CHIRPS 50–125 mm/mois), réinitialisé par campagne, par cellule ;
  - *_lag1d / *_lag2d     : lags temporels décadaires (D-1, D-2) par cellule ;
  - chirps_cumul_2d / _3d : cumul de pluie roulant sur 2–3 décades (≤ T) ;
  - severite_lag1 / _lag2 : sévérité historique de la cellule (#03), strictement ≤ T-1 ;
  - AIRE_CODE             : prédicteur catégoriel (codes 1–4) conservé tel quel.

Anti-fuite temporelle : aucune feature n'utilise une covariable de la décade T+1.

Sortie : data/processed/05_features_engineering.parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR  = Path(__file__).parent.parent / "data"
IN_DIR    = DATA_DIR / "processed" / "04_variables_environnementales"
IN_LABELS = DATA_DIR / "processed" / "03_labels_cellule_decade.parquet"
OUT_PATH  = DATA_DIR / "processed" / "05_features_engineering.parquet"

POP_MIN = 50    # mm/mois, borne inférieure de la Plage d'Optimum Pluviométrique
POP_MAX = 125   # mm/mois, borne supérieure

LAG_FEATURES = ["chirps_sum_mean", "ndvi_mean", "evi_mean", "lst_mean"]


# ── 1. Compteur POP ────────────────────────────────────────────────────────────

def consecutive_counter(series: pd.Series) -> pd.Series:
    """Compteur de True consécutifs, remis à 0 à chaque rupture ou NaN.

    Entrée : série booléenne (True = mois en POP). Sortie : série entière, même index.
    """
    result = []
    count = 0
    for v in series:
        if pd.isna(v) or not bool(v):
            count = 0
        else:
            count += 1
        result.append(count)
    return pd.Series(result, index=series.index)


def compute_pop(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute pop_consecutive : mois consécutifs en POP par (cell_id × campagne_calc).

    Agrège les décades → mois, applique le compteur consécutif POP, puis rejoint au
    DataFrame décadaire (les 3 décades d'un mois partagent la même valeur).
    """
    monthly = (
        df.groupby(["cell_id", "campagne_calc", "year", "month"], sort=True)["chirps_sum_mean"]
        .sum()
        .reset_index()
        .rename(columns={"chirps_sum_mean": "chirps_monthly_sum"})
    )
    monthly["in_pop"] = monthly["chirps_monthly_sum"].between(POP_MIN, POP_MAX)
    monthly = monthly.sort_values(
        ["cell_id", "campagne_calc", "year", "month"]
    ).reset_index(drop=True)
    monthly["pop_consecutive"] = (
        monthly.groupby(["cell_id", "campagne_calc"])["in_pop"]
        .transform(consecutive_counter)
    )

    pop_cols = monthly[["cell_id", "campagne_calc", "year", "month", "pop_consecutive"]]
    return df.merge(pop_cols, on=["cell_id", "campagne_calc", "year", "month"], how="left")


# ── 2. Lags temporels et cumuls ────────────────────────────────────────────────

def build_lags(df: pd.DataFrame, labels: pd.DataFrame | None = None) -> pd.DataFrame:
    """Ajoute lags temporels D-1/D-2, cumuls roulants et sévérité historique par cellule.

    `shift(k)` ne regarde que le passé : aucune valeur de la décade T+1 n'entre
    dans une feature de la décade T (anti-fuite temporelle). Le groupby par
    `cell_id` empêche toute contamination entre cellules.

    Si `labels` (#03) est fourni, la sévérité de la cellule est jointe puis décalée
    en `severite_lag1`/`severite_lag2` (≤ T-1) ; la **sévérité courante T (la cible)
    est ensuite retirée** pour qu'elle ne fuite pas dans les features.
    """
    df = df.sort_values(["cell_id", "date_start"]).reset_index(drop=True)

    for feat in LAG_FEATURES:
        if feat not in df.columns:
            continue
        grp = df.groupby("cell_id", sort=False)[feat]
        df[f"{feat}_lag1d"] = grp.shift(1)
        df[f"{feat}_lag2d"] = grp.shift(2)

    # Cumul de pluie roulant sur 2–3 décades (jusqu'à T inclus, fenêtre fermée à droite)
    if "chirps_sum_mean" in df.columns:
        rain = df.groupby("cell_id", sort=False)["chirps_sum_mean"]
        df["chirps_cumul_2d"] = rain.transform(lambda s: s.rolling(2).sum())
        df["chirps_cumul_3d"] = rain.transform(lambda s: s.rolling(3).sum())

    # Sévérité historique de la cellule (strictement passé, ≤ T-1)
    if labels is not None:
        sev = labels[["cell_id", "campagne_calc", "campagne_decade", "severite"]]
        df = df.merge(sev, on=["cell_id", "campagne_calc", "campagne_decade"], how="left")
        grp_sev = df.groupby("cell_id", sort=False)["severite"]
        df["severite_lag1"] = grp_sev.shift(1)
        df["severite_lag2"] = grp_sev.shift(2)
        df = df.drop(columns="severite")   # la cible courante ne reste pas dans X

    return df


# ── 3. Point d'entrée ──────────────────────────────────────────────────────────

def run() -> None:
    print(f"Chargement variables GEE : {IN_DIR}")
    df = pd.read_parquet(IN_DIR)
    print(f"  {len(df)} lignes × {len(df.columns)} colonnes")
    df["date_start"] = pd.to_datetime(df["date_start"])

    print("Chargement labels #03 (sévérité historique) ...")
    labels = pd.read_parquet(IN_LABELS) if IN_LABELS.exists() else None
    if labels is None:
        print("  ⚠ labels #03 absents — severite_lag* non calculés")

    print("Calcul du compteur POP consécutifs ...")
    df = compute_pop(df)

    print("Calcul des lags (D-1/D-2, cumuls roulants, sévérité historique) ...")
    df = build_lags(df, labels=labels)

    df = df.sort_values(["cell_id", "date_start"]).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)

    print(f"\nSortie : {OUT_PATH}")
    print(f"  {len(df)} lignes × {len(df.columns)} colonnes")

    new_cols = [c for c in df.columns if any(
        c.endswith(sfx) for sfx in ("_lag1d", "_lag2d", "_lag1", "_lag2")
    ) or c in ("pop_consecutive", "chirps_cumul_2d", "chirps_cumul_3d")]
    print("\nTaux de NaN des nouvelles features :")
    print(df[new_cols].isna().mean().round(3).to_string())


if __name__ == "__main__":
    run()
