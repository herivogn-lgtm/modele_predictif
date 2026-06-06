"""Pipeline #02 — Reconstruction du niveau de grégarité et du potentiel acridien.

Charge le Parquet de relevés nettoyés (pipeline #01), calcule pour chaque ligne :
  - niveau_gregarite (absent / S / St / T / G) depuis les comptages Sol/Trans/Greg
  - densite_imago (ind/ha) : DI_dif_moy + DL_dif_moy / 9
  - potentiel_acridien (0–5) via la matrice Annexe 8 du Manuel de lutte préventive
et sauvegarde le résultat enrichi en Parquet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
IN_PARQUET = DATA_DIR / "processed" / "01_releves_nettoyes.parquet"
OUT_PARQUET = DATA_DIR / "processed" / "02_gregarite_potentiel.parquet"

# Annexe 8 : potentiel acridien selon le niveau de grégarité et la densité (ind/ha).
# Source : Manuel de Lutte Préventive (VF), p. 307.
# Colonnes 0–7 → classes de densité :
#   0=d=0, 1=]0–10], 2=]10–100], 3=]100–500],
#   4=]500–1500], 5=]1500–2500], 6=]2500–10000], 7=>10000
# Note : la case S × col4 apparaît comme "6" dans l'extraction PDF (hors plage 0–5) ;
#        corrigée à 2 par monotonie avec les colonnes adjacentes.
_ANNEXE_8: dict[str, list[int]] = {
    "absent": [0, 0, 0, 0, 0, 0, 0, 0],
    "S":      [0, 1, 1, 2, 2, 3, 3, 3],
    "St":     [0, 1, 2, 2, 3, 3, 3, 3],
    "T1":     [0, 2, 2, 2, 3, 3, 3, 4],
    "T2":     [0, 2, 2, 2, 3, 3, 4, 4],
    "T3":     [0, 2, 2, 3, 3, 3, 4, 5],
    "G":      [0, 2, 2, 3, 3, 3, 4, 5],
}
# T terrain → T1 (sous-niveaux T1/T2/T3 non distingués en prospection)
_ANNEXE_8["T"] = _ANNEXE_8["T1"]

# Bornes right-closed des classes de densité (ind/ha)
_DENSITY_BINS = np.array([0.0, 10.0, 100.0, 500.0, 1500.0, 2500.0, 10_000.0])

# Matrice numpy pour lookup vectorisé : lignes = niveaux, colonnes = classes densité
_NIVEAU_ORDER = ["absent", "S", "St", "T1", "T2", "T3", "G"]
_NIVEAU_IDX: dict[str, int] = {n: i for i, n in enumerate(_NIVEAU_ORDER)}
_NIVEAU_IDX["T"] = _NIVEAU_IDX["T1"]
_ANNEXE_8_ARRAY = np.array([_ANNEXE_8[n] for n in _NIVEAU_ORDER], dtype=np.int8)


def compute_niveau_gregarite(sol, trans, greg) -> str | None:
    """Niveau de grégarité simplifié depuis les comptages imagos Sol/Trans/Greg.

    Retourne 'absent' | 'S' | 'St' | 'T' | 'G', ou None si entrée manquante.
    T est la valeur brute terrain ; elle sera mappée sur T1 dans la matrice Annexe 8.
    """
    if pd.isna(sol) or pd.isna(trans) or pd.isna(greg):
        return None
    total = sol + trans + greg
    if total == 0:
        return "absent"
    if greg > 0:
        return "G"
    if trans >= sol > 0:
        return "T"
    if trans > 0:
        return "St"
    return "S"


def compute_densite_imago(di_dif_moy, dl_dif_moy) -> float:
    """Densité totale équivalent imago (ind/ha) : DI_dif_moy + DL_dif_moy / 9.

    Si les deux valeurs sont NaN, retourne NaN.
    Si une seule est NaN, la NaN est traitée comme 0 dans la somme.
    """
    di_nan = pd.isna(di_dif_moy)
    dl_nan = pd.isna(dl_dif_moy)
    if di_nan and dl_nan:
        return float("nan")
    di = 0.0 if di_nan else float(di_dif_moy)
    dl = 0.0 if dl_nan else float(dl_dif_moy)
    return di + dl / 9.0


def compute_potentiel_acridien(niveau: str | None, densite: float) -> int | None:
    """Potentiel acridien (0–5) via la matrice Annexe 8 du Manuel de lutte préventive.

    T est systématiquement mappé sur T1 (valeur conservatrice).
    Retourne None si niveau est inconnu ou None, ou si densite est NaN
    (sauf pour 'absent' qui retourne toujours 0).
    """
    if niveau is None:
        return None
    if niveau == "absent":
        return 0
    if pd.isna(densite):
        return None
    niveau_idx = _NIVEAU_IDX.get(niveau)
    if niveau_idx is None:
        return None
    col = int(np.digitize(float(densite), _DENSITY_BINS, right=True))
    return int(_ANNEXE_8_ARRAY[niveau_idx, col])


def enrich(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Ajoute niveau_gregarite, densite_imago et potentiel_acridien au GeoDataFrame."""
    gdf = gdf.copy()
    gdf["niveau_gregarite"] = gdf.apply(
        lambda r: compute_niveau_gregarite(r["Sol"], r["Trans"], r["Greg"]), axis=1
    )
    gdf["densite_imago"] = gdf.apply(
        lambda r: compute_densite_imago(r["DI_dif_moy"], r["DL_dif_moy"]), axis=1
    )
    gdf["potentiel_acridien"] = gdf.apply(
        lambda r: compute_potentiel_acridien(r["niveau_gregarite"], r["densite_imago"]),
        axis=1,
    )
    return gdf


def run():
    gdf = gpd.read_parquet(IN_PARQUET)
    print(f"Parquet chargé : {len(gdf)} lignes x {len(gdf.columns)} colonnes")

    gdf = enrich(gdf)

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(OUT_PARQUET, index=False)

    dist_niv = gdf["niveau_gregarite"].value_counts(dropna=False).to_dict()
    dist_pot = gdf["potentiel_acridien"].value_counts(dropna=False).to_dict()
    print(f"Distribution niveau_gregarite : {dist_niv}")
    print(f"Distribution potentiel_acridien : {dist_pot}")
    print(f"Sortie : {OUT_PARQUET}")
    print(f"  {len(gdf)} lignes x {len(gdf.columns)} colonnes")


if __name__ == "__main__":
    run()
