"""Pipeline #09 — Sorties opérationnelles : niveau de risque 0–4 par acrido-région.

À partir du modèle hiérarchique (#07 + #08), calcule le niveau de risque
acridien 0–4 pour chacune des 90 régions naturelles, puis agrège vers les 12
secteurs du shapefile `aire_gregarigene`. Produit trois horizons temporels :

  - Décadaire  : par (secteur × campagne_calc × campagne_decade)
  - Mensuel    : agrégé par mois-campagne (3 décades consécutives)
  - Saisonnier : agrégé par campagne complète

Chaque horizon est exporté en CSV et en GeoJSON (géométrie des secteurs).

Entrées :
  data/processed/06_table_entrainement_unifiee.parquet
  data/processed/07_lgbm_model.pkl + 07_rapport_walk_forward.csv
  data/processed/08_lgbm_densite.pkl + 08_lgbm_phase.pkl + 08_rapport_walk_forward.csv
  data/aire_gregarigene/        — 12 polygones secteurs
  data/region_naturelle/        — 90 polygones régions naturelles

Sorties :
  data/processed/09_rn_risque_decade.parquet   — risque par région × décade (intermédiaire)
  data/processed/09_sorties_decadaire.{csv,geojson}
  data/processed/09_sorties_mensuelle.{csv,geojson}
  data/processed/09_sorties_saisonniere.{csv,geojson}
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

# Forcer UTF-8 sur stdout pour les terminaux Windows (cp1252 ne couvre pas →, ≥, …)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import geopandas as gpd
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

DATA_DIR          = Path(__file__).parent.parent / "data"
IN_PARQUET        = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
IN_MODEL_PRESENCE = DATA_DIR / "processed" / "07_lgbm_model.pkl"
IN_RAPPORT_07     = DATA_DIR / "processed" / "07_rapport_walk_forward.csv"
IN_MODEL_DENSITE  = DATA_DIR / "processed" / "08_lgbm_densite.pkl"
IN_MODEL_PHASE    = DATA_DIR / "processed" / "08_lgbm_phase.pkl"
IN_RAPPORT_08     = DATA_DIR / "processed" / "08_rapport_walk_forward.csv"
IN_AIRE           = DATA_DIR / "aire_gregarigene"
IN_RN             = DATA_DIR / "region_naturelle"

OUT_DIR               = DATA_DIR / "processed"
OUT_RN_DECADE         = OUT_DIR / "09_rn_risque_decade.parquet"
OUT_DECADAIRE_CSV     = OUT_DIR / "09_sorties_decadaire.csv"
OUT_MENSUELLE_CSV     = OUT_DIR / "09_sorties_mensuelle.csv"
OUT_SAISONNIERE_CSV   = OUT_DIR / "09_sorties_saisonniere.csv"
OUT_DECADAIRE_GEO     = OUT_DIR / "09_sorties_decadaire.geojson"
OUT_MENSUELLE_GEO     = OUT_DIR / "09_sorties_mensuelle.geojson"
OUT_SAISONNIERE_GEO   = OUT_DIR / "09_sorties_saisonniere.geojson"

PHASE_CATEGORIES  = ["S", "St", "T", "G"]
GREGARITE_CATS    = ["absent", "S", "St", "T", "G"]

# Annexe 8 — potentiel acridien (0–5) selon phase × densité (Manuel de lutte préventive)
_ANNEXE_8: dict[str, list[int]] = {
    "absent": [0, 0, 0, 0, 0, 0, 0, 0],
    "S":      [0, 1, 1, 2, 2, 3, 3, 3],
    "St":     [0, 1, 2, 2, 3, 3, 3, 3],
    "T1":     [0, 2, 2, 2, 3, 3, 3, 4],
    "T2":     [0, 2, 2, 2, 3, 3, 4, 4],
    "T3":     [0, 2, 2, 3, 3, 3, 4, 5],
    "G":      [0, 2, 2, 3, 3, 3, 4, 5],
}
_ANNEXE_8["T"] = _ANNEXE_8["T1"]
_DENSITY_BINS   = np.array([0.0, 10.0, 100.0, 500.0, 1500.0, 2500.0, 10_000.0])
_NIVEAU_ORDER   = ["absent", "S", "St", "T1", "T2", "T3", "G"]
_NIVEAU_IDX: dict[str, int] = {n: i for i, n in enumerate(_NIVEAU_ORDER)}
_NIVEAU_IDX["T"] = _NIVEAU_IDX["T1"]
_ANNEXE_8_ARRAY = np.array([_ANNEXE_8[n] for n in _NIVEAU_ORDER], dtype=np.int8)

# Seuil effort de prospection : <= SEUIL_EFFORT_BAS → zone peu prospectée
SEUIL_EFFORT_BAS = 1


# ---------------------------------------------------------------------------
# Annexe 8 — potentiel acridien prédit
# ---------------------------------------------------------------------------

def compute_potentiel_acridien(niveau: str | None, densite: float) -> int:
    """Potentiel acridien 0–5 via Annexe 8. Retourne 0 si données insuffisantes."""
    if niveau is None or (isinstance(niveau, float) and np.isnan(niveau)):
        return 0
    if niveau == "absent":
        return 0
    niveau_idx = _NIVEAU_IDX.get(str(niveau))
    if niveau_idx is None:
        return 0
    if np.isnan(densite):
        col = 0
    else:
        col = int(np.digitize(float(densite), _DENSITY_BINS, right=True))
    return int(_ANNEXE_8_ARRAY[niveau_idx, col])


def potentiel_to_risque(pa: int | float) -> int:
    """Mappe le potentiel acridien (0–5) vers le niveau de risque (0–4).

    PA 5 → risque 4 (transiens congregans confirmés, niveau maximal).
    """
    return int(min(int(pa), 4))


# ---------------------------------------------------------------------------
# Chargement des modèles
# ---------------------------------------------------------------------------

def load_models() -> tuple[
    lgb.LGBMClassifier, lgb.LGBMRegressor, lgb.LGBMClassifier, float, float
]:
    """Charge les 3 modèles LightGBM et lit les seuils depuis les rapports."""
    model_pres = joblib.load(IN_MODEL_PRESENCE)
    model_den  = joblib.load(IN_MODEL_DENSITE)
    model_ph   = joblib.load(IN_MODEL_PHASE)

    rapp07 = pd.read_csv(IN_RAPPORT_07)
    threshold_pres = float(
        rapp07.loc[rapp07["campagne_calc"] == "GLOBAL", "threshold"].iloc[0]
    )

    rapp08 = pd.read_csv(IN_RAPPORT_08)
    threshold_G = float(
        rapp08.loc[rapp08["campagne_calc"] == "GLOBAL", "threshold_G"].iloc[0]
    )
    return model_pres, model_den, model_ph, threshold_pres, threshold_G


# ---------------------------------------------------------------------------
# Préparation des features (identique aux pipelines #07/#08)
# ---------------------------------------------------------------------------

def _align_features(df: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Retourne X aligné sur les features attendues par le modèle.

    Les colonnes manquantes sont ajoutées avec NaN.
    Les colonnes supplémentaires sont ignorées.
    Encode niveau_gregarite_dominant en catégorie si présente.
    """
    X = pd.DataFrame(index=df.index)
    for col in feature_names:
        if col in df.columns:
            X[col] = df[col]
        else:
            X[col] = np.nan

    if "niveau_gregarite_dominant" in X.columns:
        X["niveau_gregarite_dominant"] = pd.Categorical(
            X["niveau_gregarite_dominant"], categories=GREGARITE_CATS
        )
    return X


def _apply_threshold_G(y_prob: np.ndarray, threshold_G: float) -> np.ndarray:
    """Applique un seuil abaissé sur P(G) et retourne les indices de classe."""
    g_idx = PHASE_CATEGORIES.index("G")
    y_pred = np.full(len(y_prob), -1, dtype=int)
    g_mask = y_prob[:, g_idx] >= threshold_G
    y_pred[g_mask] = g_idx
    non_g_idx = np.where(~g_mask)[0]
    if len(non_g_idx) > 0:
        sub_prob    = y_prob[non_g_idx]
        sub_no_g    = np.delete(sub_prob, g_idx, axis=1)
        argmax_no_g = np.argmax(sub_no_g, axis=1)
        remapped    = np.where(argmax_no_g >= g_idx, argmax_no_g + 1, argmax_no_g)
        y_pred[non_g_idx] = remapped
    return y_pred


# ---------------------------------------------------------------------------
# Inférence hiérarchique
# ---------------------------------------------------------------------------

def predict_risk_per_rn(
    df: pd.DataFrame,
    model_pres: lgb.LGBMClassifier,
    model_den:  lgb.LGBMRegressor,
    model_ph:   lgb.LGBMClassifier,
    threshold_pres: float,
    threshold_G:    float,
) -> pd.DataFrame:
    """Chaîne les 3 modèles et calcule le niveau de risque 0–4 par ligne.

    Une prédiction d'absence court-circuite les étapes densité et phase.

    Colonnes de sortie :
      rn_num, rn_nom, campagne_calc, campagne_decade, split, effort_prospection,
      presence_pred, densite_pred, phase_pred, potentiel_predit, niveau_risque
    """
    feat_pres = list(model_pres.feature_name_)
    feat_den  = list(model_den.feature_name_)
    feat_ph   = list(model_ph.feature_name_)

    X_pres_all = _align_features(df, feat_pres)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y_prob_pres = model_pres.predict_proba(X_pres_all)[:, 1]

    presence_pred = (y_prob_pres >= threshold_pres).astype(int)

    n = len(df)
    densite_pred = np.full(n, np.nan)
    phase_pred   = np.full(n, None, dtype=object)

    pres_mask = presence_pred == 1
    if pres_mask.any():
        df_pres      = df[pres_mask]
        X_den_pres   = _align_features(df_pres, feat_den)
        X_ph_pres    = _align_features(df_pres, feat_ph)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            den_pred_pres  = model_den.predict(X_den_pres)
            y_prob_ph      = model_ph.predict_proba(X_ph_pres)

        densite_pred[pres_mask] = den_pred_pres
        y_ph_enc = _apply_threshold_G(y_prob_ph, threshold_G)
        phase_pred[pres_mask] = [PHASE_CATEGORIES[i] for i in y_ph_enc]

    potentiel_predit = np.array([
        compute_potentiel_acridien(phase_pred[i], densite_pred[i])
        if presence_pred[i] == 1 else 0
        for i in range(n)
    ], dtype=int)

    niveau_risque = np.array([potentiel_to_risque(p) for p in potentiel_predit], dtype=int)

    result = df[["rn_num", "rn_nom", "campagne_calc", "campagne_decade",
                 "split", "effort_prospection"]].copy()
    result["presence_pred"]   = presence_pred
    result["densite_pred"]    = densite_pred
    result["phase_pred"]      = phase_pred
    result["potentiel_predit"] = potentiel_predit
    result["niveau_risque"]   = niveau_risque
    result["effort_bas"]      = (
        df["effort_prospection"].isna() | (df["effort_prospection"] <= SEUIL_EFFORT_BAS)
    ).values
    return result


# ---------------------------------------------------------------------------
# Jointure spatiale régions naturelles → secteurs acrido-régionaux
# ---------------------------------------------------------------------------

def build_rn_to_secteur_map() -> pd.DataFrame:
    """Affecte chacune des 90 régions naturelles à l'un des 12 secteurs.

    En cas de chevauchement multiple, le secteur avec la plus grande surface
    d'intersection est retenu. Les régions hors `aire_gregarigene` sont
    conservées avec SECT_NO = NaN.
    """
    rn   = gpd.read_file(IN_RN)
    aire = gpd.read_file(IN_AIRE)

    joined = gpd.sjoin(
        rn[["rn_num", "geometry"]].copy(),
        aire[["AIRE_CODE", "AIRE_NOM", "SECT_NO", "SECT_NOM", "geometry"]].copy(),
        how="left",
        predicate="intersects",
    )

    # Dédoublonnage : conserver la paire avec la plus grande intersection
    if joined.index.duplicated().any():
        rn_proj   = rn.to_crs(epsg=32738)   # UTM 38S — projection métrique Madagascar
        aire_proj = aire.to_crs(epsg=32738)

        rows = []
        for _, rn_row in rn_proj.iterrows():
            best = {"area": -1.0, "AIRE_CODE": None, "AIRE_NOM": None,
                    "SECT_NO": None, "SECT_NOM": None}
            for _, aire_row in aire_proj.iterrows():
                inter = rn_row.geometry.intersection(aire_row.geometry)
                if inter.is_empty:
                    continue
                a = inter.area
                if a > best["area"]:
                    best = {
                        "area":      a,
                        "AIRE_CODE": aire_row["AIRE_CODE"],
                        "AIRE_NOM":  aire_row["AIRE_NOM"],
                        "SECT_NO":   aire_row["SECT_NO"],
                        "SECT_NOM":  aire_row["SECT_NOM"],
                    }
            rows.append({
                "rn_num":    rn_row["rn_num"],
                "AIRE_CODE": best["AIRE_CODE"],
                "AIRE_NOM":  best["AIRE_NOM"],
                "SECT_NO":   best["SECT_NO"],
                "SECT_NOM":  best["SECT_NOM"],
            })
        mapping = pd.DataFrame(rows)
        mapping["rn_num"] = pd.array(mapping["rn_num"], dtype="Int64")
        return mapping

    mapping = joined[["rn_num", "AIRE_CODE", "AIRE_NOM", "SECT_NO", "SECT_NOM"]].reset_index(drop=True)
    mapping["rn_num"] = pd.array(mapping["rn_num"], dtype="Int64")
    return mapping


# ---------------------------------------------------------------------------
# Agrégation régions → secteurs
# ---------------------------------------------------------------------------

def _risque_dominant(s: pd.Series) -> int:
    """Niveau de risque maximal parmi les régions du secteur."""
    return int(s.max()) if s.notna().any() else 0


def _phase_dominante(s: pd.Series) -> str | None:
    """Phase la plus fréquente parmi les prédictions non-None."""
    vals = s.dropna()
    if vals.empty:
        return None
    return str(vals.mode().iloc[0])


def aggregate_to_secteur(
    rn_risque: pd.DataFrame,
    rn_map: pd.DataFrame,
    group_cols: list[str],
) -> pd.DataFrame:
    """Agrège le risque des 90 régions naturelles vers les 12 secteurs.

    group_cols : colonnes temporelles à conserver (ex. ['campagne_calc',
                 'campagne_decade'] pour le niveau décadaire).

    Colonnes de sortie :
      AIRE_CODE, AIRE_NOM, SECT_NO, SECT_NOM, <group_cols>,
      niveau_risque_max, phase_dominante, n_regions,
      n_regions_risque_eleve (niveaux 3–4),
      n_regions_effort_bas, faible_couverture
    """
    merged = rn_risque.merge(rn_map, on="rn_num", how="left")

    agg_keys = ["AIRE_CODE", "AIRE_NOM", "SECT_NO", "SECT_NOM"] + group_cols

    agg = (
        merged.groupby(agg_keys, dropna=False, observed=True)
        .apply(
            lambda g: pd.Series({
                "niveau_risque_max":      _risque_dominant(g["niveau_risque"]),
                "phase_dominante":        _phase_dominante(g["phase_pred"]),
                "n_regions":              len(g),
                "n_regions_risque_eleve": int((g["niveau_risque"] >= 3).sum()),
                "n_regions_effort_bas":   int(g["effort_bas"].sum()),
            }),
            include_groups=False,
        )
        .reset_index()
    )

    agg["faible_couverture"] = agg["n_regions_effort_bas"] > (agg["n_regions"] // 2)
    agg["risque_eleve"] = (agg["niveau_risque_max"] >= 3).astype(int)
    return agg


# ---------------------------------------------------------------------------
# Horizons temporels
# ---------------------------------------------------------------------------

def add_mois_campagne(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute mois_campagne = (campagne_decade - 1) // 3 + 1 (mois 1 = octobre)."""
    df = df.copy()
    df["mois_campagne"] = ((df["campagne_decade"] - 1) // 3 + 1).astype(int)
    return df


def aggregate_mensuel(rn_risque: pd.DataFrame, rn_map: pd.DataFrame) -> pd.DataFrame:
    """Agrège vers le niveau mensuel en groupant 3 décades consécutives."""
    rn_m = add_mois_campagne(rn_risque)
    return aggregate_to_secteur(rn_m, rn_map, ["campagne_calc", "mois_campagne"])


def aggregate_saisonnier(rn_risque: pd.DataFrame, rn_map: pd.DataFrame) -> pd.DataFrame:
    """Agrège vers le niveau saisonnier (une ligne par secteur × campagne)."""
    return aggregate_to_secteur(rn_risque, rn_map, ["campagne_calc"])


def aggregate_decadaire(rn_risque: pd.DataFrame, rn_map: pd.DataFrame) -> pd.DataFrame:
    """Agrège vers le niveau décadaire (une ligne par secteur × campagne × décade)."""
    return aggregate_to_secteur(rn_risque, rn_map, ["campagne_calc", "campagne_decade"])


# ---------------------------------------------------------------------------
# Export GeoJSON
# ---------------------------------------------------------------------------

def build_secteur_geodf() -> gpd.GeoDataFrame:
    """GeoDataFrame des 12 secteurs (géométrie brute, sans agrégation temporelle)."""
    aire = gpd.read_file(IN_AIRE)
    return aire[["AIRE_CODE", "AIRE_NOM", "SECT_NO", "SECT_NOM", "SUP_HA", "geometry"]].copy()


def export_geojson(agg: pd.DataFrame, secteur_gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Joint le tableau agrégé avec les géométries et exporte en GeoJSON."""
    joined = secteur_gdf.merge(agg, on=["AIRE_CODE", "AIRE_NOM", "SECT_NO", "SECT_NOM"], how="right")
    gdf = gpd.GeoDataFrame(joined, geometry="geometry", crs="EPSG:4326")
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GeoJSON")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def run() -> None:
    print("=== Pipeline #09 — Sorties opérationnelles ===\n")

    # — Modèles
    print("Chargement des modèles #07 / #08…")
    model_pres, model_den, model_ph, t_pres, t_G = load_models()
    print(f"  Seuil présence : {t_pres:.2f}   |   Seuil G : {t_G:.2f}")

    # — Données
    print(f"\nChargement table d'entraînement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)
    print(f"  {len(df)} lignes × {len(df.columns)} colonnes")
    print(f"  Distribution splits : {df['split'].value_counts().to_dict()}")

    # — Inférence sur toutes les lignes
    print("\nInférence hiérarchique sur l'ensemble des régions × décades…")
    rn_risque = predict_risk_per_rn(df, model_pres, model_den, model_ph, t_pres, t_G)

    dist_risque = pd.Series(rn_risque["niveau_risque"]).value_counts().sort_index()
    print(f"  Distribution niveau de risque :\n{dist_risque.to_string()}")
    n_eleve = (rn_risque["niveau_risque"] >= 3).sum()
    print(f"  Risque eleve (>=3) : {n_eleve} lignes ({100*n_eleve/len(rn_risque):.1f} %)")
    n_bas_effort = rn_risque["effort_bas"].sum()
    print(f"  Effort prospection bas : {n_bas_effort} lignes ({100*n_bas_effort/len(rn_risque):.1f} %)")

    # — Jointure spatiale régions → secteurs
    print("\nJointure spatiale régions naturelles → secteurs acrido-régionaux…")
    rn_map = build_rn_to_secteur_map()
    n_mapped = rn_map["SECT_NO"].notna().sum()
    print(f"  {n_mapped}/{len(rn_map)} régions naturelles affectées à un secteur")
    print(f"  Secteurs couverts : {rn_map['SECT_NO'].dropna().nunique()}")

    # — Sauvegarde intermédiaire
    OUT_RN_DECADE.parent.mkdir(parents=True, exist_ok=True)
    rn_risque.to_parquet(OUT_RN_DECADE, index=False)
    print(f"\nIntermédiaire enregistré : {OUT_RN_DECADE}")

    # — Trois horizons
    secteur_gdf = build_secteur_geodf()

    print("\n--- Horizon décadaire ---")
    dec = aggregate_decadaire(rn_risque, rn_map)
    print(f"  {len(dec)} lignes (secteurs × campagnes × décades)")
    dec.to_csv(OUT_DECADAIRE_CSV, index=False, encoding="utf-8-sig")
    export_geojson(dec, secteur_gdf, OUT_DECADAIRE_GEO)
    print(f"  -> {OUT_DECADAIRE_CSV}")
    print(f"  -> {OUT_DECADAIRE_GEO}")

    print("\n--- Horizon mensuel ---")
    men = aggregate_mensuel(rn_risque, rn_map)
    print(f"  {len(men)} lignes (secteurs × campagnes × mois)")
    men.to_csv(OUT_MENSUELLE_CSV, index=False, encoding="utf-8-sig")
    export_geojson(men, secteur_gdf, OUT_MENSUELLE_GEO)
    print(f"  -> {OUT_MENSUELLE_CSV}")
    print(f"  -> {OUT_MENSUELLE_GEO}")

    print("\n--- Horizon saisonnier ---")
    sai = aggregate_saisonnier(rn_risque, rn_map)
    print(f"  {len(sai)} lignes (secteurs × campagnes)")
    sai.to_csv(OUT_SAISONNIERE_CSV, index=False, encoding="utf-8-sig")
    export_geojson(sai, secteur_gdf, OUT_SAISONNIERE_GEO)
    print(f"  -> {OUT_SAISONNIERE_CSV}")
    print(f"  -> {OUT_SAISONNIERE_GEO}")

    # — Résumé opérationnel : campagnes récentes (inférence) niveaux élevés
    print("\n=== Résumé opérationnel — Risque élevé (niveaux 3–4) ===")
    inf_dec = dec[
        dec["campagne_calc"].isin(
            rn_risque.loc[rn_risque["split"] == "inference", "campagne_calc"].unique()
        )
        & (dec["niveau_risque_max"] >= 3)
    ]
    if inf_dec.empty:
        print("  Aucun secteur a risque eleve sur les campagnes d'inference.")
    else:
        cols_show = ["SECT_NO", "AIRE_NOM", "campagne_calc", "campagne_decade",
                     "niveau_risque_max", "phase_dominante", "faible_couverture"]
        cols_show = [c for c in cols_show if c in inf_dec.columns]
        print(inf_dec[cols_show].sort_values(
            ["campagne_calc", "niveau_risque_max"], ascending=[True, False]
        ).to_string(index=False))


if __name__ == "__main__":
    run()
