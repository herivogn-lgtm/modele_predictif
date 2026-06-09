"""Pipeline #09 — Sorties opérationnelles : carte de sévérité-phase 0–3 à 1 km (OS3).

À partir du modèle retenu (#07, `07_modele_retenu.txt`), restitue les prédictions de
sévérité-phase ordinale **0–3** pour la **décade T+1** sur la grille **1 km** de l'aire
grégarigène, en support à la prospection (HITL : le modèle a été validé par un humain via
le rapport #08 avant cette génération de cartes) :

  - Carte de sévérité 0–3 à 1 km (alerte précoce, décade à venir)
  - Agrégat mensuel par aire complémentaire AMI/ATM/AD/AGT (planification)
  - Binaire dérivé (probabilité de présence, sév ≥ 1) pour comparaison AUC littérature
  - Export PNG + SIG (GeoJSON vectoriel + GeoTIFF raster) pour les supports terrain

Les fonctions de restitution (`to_severity_map`, `aggregate_by_aire`, `derive_binary`)
sont pures et testées sur entrées synthétiques (`tests/test_09_sorties_operationnelles.py`).
La qualité prédictive réelle se mesure hors pytest (rapport #08 sur données réelles).

Entrées :
  data/processed/06_table_entrainement_unifiee.parquet
  data/processed/07_modele_retenu.txt
  data/processed/01_grille_1km.parquet           — polygones cellule 1 km (EPSG:32738)

Sorties :
  data/processed/09_carte_severite_decade.csv     — sévérité 0–3 par cellule × décade (T+1)
  data/processed/09_carte_severite_mensuelle.csv  — sévérité agrégée au mois (phase max)
  data/processed/09_agregat_aire_mensuel.csv      — agrégat mensuel par AIRE_CODE
  data/processed/09_carte_severite.geojson        — carte 1 km vectorielle
  data/processed/09_carte_severite.tif            — carte 1 km rasterisée (GeoTIFF)
  data/processed/09_carte_severite.png            — rendu cartographique
"""

from __future__ import annotations

import sys
from pathlib import Path

# Forcer UTF-8 sur stdout pour les terminaux Windows (cp1252 ne couvre pas →, ≥, …)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

DATA_DIR     = Path(__file__).parent.parent / "data"
IN_PARQUET   = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
IN_CHOIX     = DATA_DIR / "processed" / "07_modele_retenu.txt"
IN_GRILLE    = DATA_DIR / "processed" / "01_grille_1km.parquet"
IN_AIRE      = DATA_DIR / "aire_gregarigene"   # secteurs grégarigènes (contour de contexte)
IN_RN        = DATA_DIR / "region_naturelle"   # régions naturelles (fond de carte de base)

OUT_DIR              = DATA_DIR / "processed"
OUT_CARTE_DECADE     = OUT_DIR / "09_carte_severite_decade.csv"
OUT_CARTE_MOIS       = OUT_DIR / "09_carte_severite_mensuelle.csv"
OUT_AIRE_MOIS        = OUT_DIR / "09_agregat_aire_mensuel.csv"
OUT_GEOJSON          = OUT_DIR / "09_carte_severite.geojson"
OUT_RASTER           = OUT_DIR / "09_carte_severite.tif"
OUT_PNG              = OUT_DIR / "09_carte_severite.png"

# Colonnes du domaine (cohérentes avec #06/#07)
CELL_COL    = "cell_id"
AIRE_COL    = "AIRE_CODE"
CAMP_COL    = "campagne_calc"
DECADE_COL  = "campagne_decade"
SEV_COL     = "severite"

SEV_PRESENCE    = 1   # binaire dérivé : présence = sévérité ≥ 1 (PRD)
SEV_FOYER       = 2   # foyer à prospecter en priorité = sévérité ≥ 2 (transiens/grégaire)
DECADES_PAR_MOIS = 3  # mois-campagne = 3 décades consécutives (décade 1–36 → mois 1–12)
PNG_ALPHA        = 0.75  # transparence des cellules sur le fond de carte (0=invisible, 1=opaque)


# ---------------------------------------------------------------------------
# derive_binary — binaire présence dérivé (sévérité ≥ 1), exigence AUC thèse §31/§33
# ---------------------------------------------------------------------------

def derive_binary(severite) -> np.ndarray:
    """Binaire présence = (sévérité ≥ 1) : absence (0) → 0, niveaux 1–3 → 1."""
    return (np.asarray(severite) >= SEV_PRESENCE).astype(int)


# ---------------------------------------------------------------------------
# to_severity_map — agrégation décade → mois (sévérité = phase max du mois)
# ---------------------------------------------------------------------------

def mois_campagne(campagne_decade) -> np.ndarray:
    """Mois-campagne 1–12 = 3 décades consécutives (décade 1–3 → mois 1, …)."""
    return (np.asarray(campagne_decade) - 1) // DECADES_PAR_MOIS + 1


def to_severity_map(df: pd.DataFrame) -> pd.DataFrame:
    """Agrège la sévérité décadaire au mois : sévérité mensuelle = **phase max**.

    Conserve la maille cellule (`cell_id`) et l'aire (`AIRE_CODE`) pour l'agrégat aval.
    Une ligne de sortie par (cellule × campagne × mois-campagne).
    """
    out = df.copy()
    out["mois_campagne"] = mois_campagne(out[DECADE_COL])
    keys = [c for c in (CELL_COL, AIRE_COL, CAMP_COL) if c in out.columns] + ["mois_campagne"]
    return out.groupby(keys, observed=True)[SEV_COL].max().reset_index()


# ---------------------------------------------------------------------------
# aggregate_by_aire — agrégat mensuel par aire complémentaire (planification)
# ---------------------------------------------------------------------------

def aggregate_by_aire(carte_mois: pd.DataFrame) -> pd.DataFrame:
    """Agrège la carte mensuelle cellule par aire complémentaire (AMI/ATM/AD/AGT).

    Une ligne par (aire × campagne × mois) : sévérité max, nombre de cellules et nombre
    de cellules-foyer (sévérité ≥ 2, à prospecter en priorité).
    """
    keys = [c for c in (AIRE_COL, CAMP_COL) if c in carte_mois.columns] + ["mois_campagne"]

    def _resume(g: pd.DataFrame) -> pd.Series:
        return pd.Series({
            "severite_max":     int(g[SEV_COL].max()),
            "n_cellules":       len(g),
            "n_cellules_foyer": int((g[SEV_COL] >= SEV_FOYER).sum()),
        })

    return (
        carte_mois.groupby(keys, observed=True)
        .apply(_resume, include_groups=False)
        .reset_index()
    )


# ---------------------------------------------------------------------------
# Carte cellule (emprise spatiale) + exports SIG/PNG
# ---------------------------------------------------------------------------

def to_cell_map(carte_decade: pd.DataFrame) -> pd.DataFrame:
    """Réduit la carte décadaire à une valeur par cellule pour l'emprise spatiale.

    Sévérité = phase max sur la campagne (alerte pire cas) ; proba présence = max.
    """
    g = carte_decade.groupby([CELL_COL, AIRE_COL], observed=True)
    out = g.agg(severite=(SEV_COL, "max")).reset_index()
    if "proba_presence" in carte_decade.columns:
        out = out.merge(
            g["proba_presence"].max().reset_index(), on=[CELL_COL, AIRE_COL], how="left"
        )
    return out


def export_sig(carte_cellule: pd.DataFrame) -> None:
    """Joint la carte cellule à la géométrie 1 km et exporte GeoJSON + GeoTIFF + PNG."""
    import geopandas as gpd

    grille = gpd.read_parquet(IN_GRILLE)[[CELL_COL, "geometry"]]
    gdf = grille.merge(carte_cellule, on=CELL_COL, how="inner")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"  -> {OUT_GEOJSON} ({len(gdf)} cellules)")

    _export_raster(gdf)
    _export_png(gdf)


def _export_raster(gdf) -> None:
    """Rasterise la sévérité 0–3 en GeoTIFF 1 km (nodata = 255)."""
    import rasterio
    from rasterio import features, transform

    res = 1000.0  # 1 km, grille en mètres (UTM 38S)
    minx, miny, maxx, maxy = gdf.total_bounds
    width  = int(np.ceil((maxx - minx) / res))
    height = int(np.ceil((maxy - miny) / res))
    tf = transform.from_origin(minx, maxy, res, res)

    shapes = ((geom, int(sev)) for geom, sev in zip(gdf.geometry, gdf[SEV_COL]))
    raster = features.rasterize(
        shapes, out_shape=(height, width), transform=tf, fill=255, dtype="uint8"
    )
    with rasterio.open(
        OUT_RASTER, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="uint8", crs=gdf.crs, transform=tf, nodata=255,
    ) as dst:
        dst.write(raster, 1)
    print(f"  -> {OUT_RASTER} ({width}×{height} px)")


def _export_png(gdf) -> None:
    """Rendu cartographique PNG : cellules de sévérité 0–3 sur un fond de cartes locales.

    Fond de carte = couches locales (pas de tuiles web) : `region_naturelle` (fond gris
    clair) puis `aire_gregarigene` (contour des secteurs). Les cellules prédites sont
    tracées en semi-transparence (`PNG_ALPHA`) par-dessus. La vue est cadrée sur l'emprise
    des cellules (zoom sur la zone de prédiction), les couches de fond servant de repères.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    import geopandas as gpd

    cmap = ListedColormap(["#e8e8e8", "#ffe08a", "#fb8c3c", "#c0202a"])  # 0/1/2/3
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)

    crs = gdf.crs
    fig, ax = plt.subplots(figsize=(9, 11))

    # Fond de carte local : régions naturelles (remplissage) + secteurs grégarigènes (contour).
    try:
        rn = gpd.read_file(IN_RN).to_crs(crs)
        rn.plot(ax=ax, facecolor="#f0ede6", edgecolor="#c8c2b6", linewidth=0.4, zorder=0)
    except Exception:  # noqa: BLE001 — fond facultatif
        pass
    try:
        aire = gpd.read_file(IN_AIRE).to_crs(crs)
        aire.boundary.plot(ax=ax, color="#6b6157", linewidth=0.8, zorder=1)
    except Exception:  # noqa: BLE001 — contour facultatif
        pass

    # Cellules prédites au-dessus du fond.
    gdf.plot(column=SEV_COL, cmap=cmap, norm=norm, ax=ax,
             linewidth=0, alpha=PNG_ALPHA, zorder=2)

    # Cadrer sur l'emprise des cellules (+ marge), le fond servant de contexte.
    minx, miny, maxx, maxy = gdf.total_bounds
    mx, my = (maxx - minx) * 0.06, (maxy - miny) * 0.06
    ax.set_xlim(minx - mx, maxx + mx)
    ax.set_ylim(miny - my, maxy + my)

    ax.set_title("Sévérité-phase prédite 0–3 (décade T+1) — aire grégarigène 1 km")
    ax.set_axis_off()
    cbar = fig.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax,
        ticks=[0, 1, 2, 3], fraction=0.03, pad=0.02,
    )
    cbar.ax.set_yticklabels(["0 absence", "1 solitaire", "2 transiens", "3 grégaire"])
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT_PNG}  (fond cartes locales)")


# ---------------------------------------------------------------------------
# Point d'entrée — entraînement modèle retenu + prédiction décade T+1
# ---------------------------------------------------------------------------

def run() -> None:
    import os

    from benchmark_ordinal_07 import (
        CAMPAIGN_COL, TARGET, build_models, get_feature_columns,
    )
    from rapport_performance_08 import _lire_modele_retenu, _predit_fold

    print("=== Pipeline #09 — Sorties opérationnelles (sévérité 0–3, 1 km) ===\n")
    print(f"Chargement table d'entraînement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)

    obs = df[df[TARGET].notna()].copy()
    obs[TARGET] = obs[TARGET].astype(int)
    feature_cols = get_feature_columns(obs)
    medians = obs[feature_cols].median(numeric_only=True)
    obs[feature_cols] = obs[feature_cols].fillna(medians)

    # Emprise = dernière campagne à prédire (décade T+1, alerte précoce).
    a_pred = df[df["a_predire"].astype(bool)].copy()
    campagne_cible = sorted(a_pred[CAMPAIGN_COL].dropna().unique())[-1]
    pred = a_pred[a_pred[CAMPAIGN_COL] == campagne_cible].copy()
    pred[feature_cols] = pred[feature_cols].fillna(medians)
    print(f"  {len(obs)} lignes observées | campagne cible {campagne_cible} : "
          f"{len(pred)} cellules-décades à prédire")

    retenu = _lire_modele_retenu(IN_CHOIX)
    n_estimators = int(os.environ.get("BENCH_N_ESTIMATORS", "300"))
    n_jobs       = int(os.environ.get("BENCH_N_JOBS", "-1"))
    spec = build_models(n_estimators=n_estimators, n_jobs=n_jobs, include_lstm=True)[retenu]
    print(f"  Modèle retenu : {retenu} (cadrage {spec.framing})\n")

    print("Entraînement sur l'historique observé + prédiction décade T+1…")
    severite_pred, proba_presence = _predit_fold(
        spec, obs[feature_cols], obs[TARGET].to_numpy(int), pred[feature_cols]
    )

    carte_decade = pred[[CELL_COL, AIRE_COL, CAMP_COL, DECADE_COL]].copy()
    carte_decade[SEV_COL]         = np.asarray(severite_pred, dtype=int)
    carte_decade["proba_presence"] = np.asarray(proba_presence, dtype=float)
    carte_decade["presence"]       = derive_binary(carte_decade[SEV_COL])

    dist = pd.Series(carte_decade[SEV_COL]).value_counts().sort_index()
    print(f"  Distribution sévérité prédite :\n{dist.to_string()}")
    n_foyer = int((carte_decade[SEV_COL] >= SEV_FOYER).sum())
    print(f"  Cellules-foyer (sév ≥ 2) : {n_foyer} "
          f"({100 * n_foyer / max(len(carte_decade), 1):.1f} %)\n")

    carte_mois  = to_severity_map(carte_decade)
    aire_mois   = aggregate_by_aire(carte_mois)
    carte_cell  = to_cell_map(carte_decade)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    carte_decade.to_csv(OUT_CARTE_DECADE, index=False, encoding="utf-8-sig")
    carte_mois.to_csv(OUT_CARTE_MOIS, index=False, encoding="utf-8-sig")
    aire_mois.to_csv(OUT_AIRE_MOIS, index=False, encoding="utf-8-sig")
    print(f"  -> {OUT_CARTE_DECADE}")
    print(f"  -> {OUT_CARTE_MOIS}")
    print(f"  -> {OUT_AIRE_MOIS}")

    print("\nExports SIG (GeoJSON + GeoTIFF) + carte PNG…")
    export_sig(carte_cell)

    print("\n=== Agrégat mensuel par aire (foyers sév ≥ 2) ===")
    print(aire_mois.sort_values(["AIRE_CODE", "mois_campagne"]).to_string(index=False))


if __name__ == "__main__":
    run()
