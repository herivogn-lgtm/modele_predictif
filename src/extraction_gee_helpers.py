"""Logique pure du pipeline #04 — sans dépendance Google Earth Engine.

Isole les transformations testables unitairement (calendrier décadaire,
construction des specs annuelles, assemblage des résultats, anomalie CHIRPS,
garde-fous) de la couche GEE qui reste dans `04_extraction_variables_gee.py`.

Importable sans `ee` installé → testable en CI sans authentification.
"""

import calendar
from datetime import date, timedelta

import pandas as pd

# Mois de la campagne acridienne : octobre–juillet
CAMPAIGN_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7]


def decade_bounds(year: int, month: int, part: int) -> tuple[date, date]:
    """Retourne (date_start, date_end) pour la décade (year, month, part∈{1,2,3})."""
    if part == 1:
        start, end = date(year, month, 1), date(year, month, 10)
    elif part == 2:
        start, end = date(year, month, 11), date(year, month, 20)
    else:
        last = calendar.monthrange(year, month)[1]
        start, end = date(year, month, 21), date(year, month, last)
    return start, end


def campaign_label(year: int, month: int) -> str | None:
    """Étiquette de campagne (ex. "2010-2011"). None hors campagne (août-sept)."""
    if month >= 10:
        return f"{year}-{year + 1}"
    if 1 <= month <= 7:
        return f"{year - 1}-{year}"
    return None


def build_decade_calendar(years: list[int]) -> pd.DataFrame:
    """Génère toutes les décades de campagne pour les années civiles données.

    Chaque ligne = une décade avec ses métadonnées temporelles et un
    `decade_id = year * 100 + decade_num` (clé de jointure stable).
    Retourne uniquement les décades des mois de campagne (oct–jul).
    """
    records = []
    for year in years:
        for month in CAMPAIGN_MONTHS:
            campaign = campaign_label(year, month)
            if campaign is None:
                continue
            # Numéro de mois dans la campagne (oct=1 … jul=10)
            month_offset = CAMPAIGN_MONTHS.index(month) + 1
            for part in (1, 2, 3):
                d_start, d_end = decade_bounds(year, month, part)
                decade_num = (month_offset - 1) * 3 + part
                records.append({
                    "year": year,
                    "month": month,
                    "decade_part": part,
                    "date_start": d_start,
                    "date_end": d_end,
                    "midpoint": d_start + timedelta(days=(d_end - d_start).days // 2),
                    "campaign": campaign,
                    "decade_num": decade_num,
                    "decade_id": year * 100 + decade_num,
                })
    df = pd.DataFrame(records)
    df["date_start"] = pd.to_datetime(df["date_start"])
    df["date_end"] = pd.to_datetime(df["date_end"])
    df["midpoint"] = pd.to_datetime(df["midpoint"])
    return df


def build_specs(
    calendar_df: pd.DataFrame, lead_days: int, lag_days: int
) -> dict[int, list[dict]]:
    """Regroupe les décades par année civile en specs GEE prêtes à mapper.

    Chaque spec = {"start", "end", "id"} où start/end sont des dates ISO
    (YYYY-MM-DD) passables à `ee.ImageCollection.filterDate` (borne haute
    exclusive). La fenêtre temporelle est élargie de `lead_days` avant le
    début de la décade et `lag_days` après sa fin — utile pour capter le
    composite MODIS le plus proche.
    """
    specs: dict[int, list[dict]] = {}
    for row in calendar_df.itertuples(index=False):
        start = (row.date_start - pd.Timedelta(days=lead_days)).strftime("%Y-%m-%d")
        end = (row.date_end + pd.Timedelta(days=lag_days)).strftime("%Y-%m-%d")
        specs.setdefault(int(row.year), []).append(
            {"start": start, "end": end, "id": int(row.decade_id)}
        )
    return specs


def parse_reduce_features(
    props_list: list[dict], rename_map: dict[str, str], keep_cols: list[str]
) -> pd.DataFrame:
    """Convertit les properties d'un FeatureCollection.getInfo() en DataFrame.

    Applique `rename_map` (noms bruts du réducteur GEE → noms métier), ne
    garde que `keep_cols` (dans cet ordre) et retourne un DataFrame vide mais
    correctement colonné si `props_list` est vide.
    """
    if not props_list:
        return pd.DataFrame(columns=keep_cols)
    df = pd.DataFrame(props_list).rename(columns=rename_map)
    return df[[c for c in keep_cols if c in df.columns]]


def compute_chirps_anomaly(df: pd.DataFrame, baseline_df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute `chirps_anomaly_mean = chirps_sum_mean − baseline` par région×décade-of-year.

    Jointure sur (region_id, month, decade_part). NaN si la somme courante ou la
    baseline manque. La colonne baseline intermédiaire est retirée de la sortie.
    """
    out = df.merge(
        baseline_df[["region_id", "month", "decade_part", "chirps_baseline_mean"]],
        on=["region_id", "month", "decade_part"],
        how="left",
    )
    out["chirps_anomaly_mean"] = out["chirps_sum_mean"] - out["chirps_baseline_mean"]
    return out.drop(columns=["chirps_baseline_mean"])


# Métadonnées temporelles/spatiales en tête de la table de sortie
_META_COLS = [
    "region_id", "region_nom", "campaign", "decade_num",
    "date_start", "date_end", "year", "month", "decade_part",
]


def assemble_decades(
    calendar_df: pd.DataFrame,
    regions_df: pd.DataFrame,
    source_dfs: list[pd.DataFrame],
) -> pd.DataFrame:
    """Assemble la table décadaire : produit (décades × régions) ⋈ sources.

    `regions_df` : colonnes region_id, region_nom. Chaque DataFrame de
    `source_dfs` est keyé sur (decade_id, region_id) ; merge gauche → NaN pour
    les couples absents. Les colonnes techniques (decade_id, midpoint) sont
    retirées pour préserver le schéma de sortie historique.
    """
    base = calendar_df.merge(regions_df, how="cross")
    for src in source_dfs:
        if src is not None and not src.empty and "region_id" in src.columns:
            base = base.merge(src, on=["decade_id", "region_id"], how="left")
    dyn = [c for c in base.columns if c not in _META_COLS + ["decade_id", "midpoint"]]
    return base[_META_COLS + dyn]


def assert_decade_completeness(df: pd.DataFrame, n_regions: int) -> None:
    """Garde-fou : chaque décade (year, decade_num) doit couvrir n_regions régions.

    Remplace l'ancienne sonde `_collection_empty` par une vérification unique a
    posteriori. Lève AssertionError si une décade a un nombre de régions distinct
    inattendu (extraction partielle, doublons, décade perdue).
    """
    counts = df.groupby(["year", "decade_num"])["region_id"].nunique()
    bad = counts[counts != n_regions]
    assert bad.empty, (
        f"Décades incomplètes (≠ {n_regions} régions) : "
        f"{bad.to_dict()}"
    )
