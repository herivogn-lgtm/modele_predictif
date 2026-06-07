"""Pipeline #11 — NeuralProphet multi-horizon (décadaire / mensuel / saisonnier).

Entraîne un NeuralProphet en mode panel (90 séries temporelles par région
naturelle) sur la table unifiée (#06) et produit des prédictions simultanées
à trois horizons temporels en une passe :
  - décadaire  : 1 décade en avance  (≈ 10 jours)
  - mensuel    : 3 décades en avance (≈ 30 jours)
  - saisonnier : 10 décades en avance (≈ 100 jours / 1 trimestre)

Compare les performances walk-forward avec le baseline LightGBM (#07) et
documente la décision de déploiement.

Sorties :
  data/processed/11_rapport_walk_forward.csv  — métriques par campagne + GLOBAL
  data/processed/11_neuralprophet_model.pkl   — modèle final (joblib)
  data/processed/11_decision_deploiement.csv  — comparaison NP vs LightGBM
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

# UTF-8 forcé sur Windows pour éviter UnicodeEncodeError de tqdm (CP1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import joblib
import numpy as np
import pandas as pd

DATA_DIR       = Path(__file__).parent.parent / "data"
IN_PARQUET     = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
IN_RAPPORT_07  = DATA_DIR / "processed" / "07_rapport_walk_forward.csv"
OUT_RAPPORT    = DATA_DIR / "processed" / "11_rapport_walk_forward.csv"
OUT_MODEL      = DATA_DIR / "processed" / "11_neuralprophet_model.pkl"
OUT_DECISION   = DATA_DIR / "processed" / "11_decision_deploiement.csv"

sys.path.insert(0, str(Path(__file__).parent))
from lgbm_baseline_07 import evaluate, optimize_threshold, walk_forward_folds

N_FORECASTS = 10   # cible : NP force n_forecasts=1 si n_lags=0 (voir forecaster.py:1052-1054)
N_LAGS      = 0    # pas de lags AR : modèle tendance+saisonnalité pur, robuste aux séries éparses
# NB : avec n_lags=0, NP override n_forecasts→1 (sans AR, toute date future est prédictible
#      indépendamment). Conséquence : yhat3/yhat10 absents → fallback yhat1.shift(1) pour
#      tous les horizons (pred_k[v] = model(v) = tendance(v)+saisonnalité(v) pour tout k).
EPOCHS      = 100

# horizons évalués : name → step index (1-indexed, correspond à yhat{k})
HORIZONS: dict[str, int] = {"decadaire": 1, "mensuel": 3, "saisonnier": 10}

KEY_COLS  = ["rn_num", "rn_nom", "campagne_calc", "campagne_decade"]
META_COLS = ["split", "effort_prospection", "label"]


# ---------------------------------------------------------------------------
# Mapping temporel
# ---------------------------------------------------------------------------

def decode_decade_to_date(campagne_calc: str, campagne_decade: int) -> pd.Timestamp:
    """Convertit (campagne, décade) en date absolue (1er jour de la décade).

    Calendrier : campagne = octobre (décade 1) à juillet (décade 30).
      décades 1-3   = octobre   (mois 10, start_year)
      décades 4-6   = novembre  (mois 11, start_year)
      décades 7-9   = décembre  (mois 12, start_year)
      décades 10-12 = janvier   (mois  1, start_year+1)
      ...
      décades 28-30 = juillet   (mois  7, start_year+1)
    """
    start_year   = int(campagne_calc.split("-")[0])
    month_offset = (campagne_decade - 1) // 3    # 0=oct, 1=nov, ..., 9=jul
    day          = ((campagne_decade - 1) % 3) * 10 + 1   # 1, 11 ou 21
    if month_offset <= 2:
        month = 10 + month_offset          # octobre=10, novembre=11, décembre=12
        year  = start_year
    else:
        month = month_offset - 2           # janvier=1, …, juillet=7
        year  = start_year + 1
    return pd.Timestamp(year=year, month=month, day=day)


# ---------------------------------------------------------------------------
# Préparation panel NeuralProphet
# ---------------------------------------------------------------------------

_REF_DATE = pd.Timestamp("2001-10-01")
_REF_YEAR = 2001


def _decade_ordinal_date(campagne_calc: str, campagne_decade: int) -> pd.Timestamp:
    """Date synthétique régulière (pas de lacune estivale) pour NeuralProphet.

    Chaque décade reçoit une date fictive espacée de 10 jours à partir du
    01/10/2001, sans saut d'août-septembre entre campagnes. Cela évite que
    NeuralProphet n'insère des lignes manquantes pour les mois d'été.
    """
    start_year = int(campagne_calc.split("-")[0])
    ordinal    = (start_year - _REF_YEAR) * 30 + (campagne_decade - 1)
    return _REF_DATE + pd.Timedelta(days=10) * ordinal


def prepare_panel_df(
    df: pd.DataFrame,
    all_rn_nums: list[int] | None = None,
) -> pd.DataFrame:
    """Construit un panel COMPLET pour NeuralProphet : ds, y, ID.

    Le parquet #06 est sparse (toutes les combinaisons rn_num × campagne ×
    décade ne sont pas présentes). Pour éviter que NeuralProphet n'insère des
    lignes fictives, on construit la grille exhaustive et on remplit les cellules
    manquantes avec y=NaN.

    - ID  = rn_num (str)
    - ds  = date ordinale régulière (10 jours, sans lacune estivale)
    - y   = label (0/1) ou NaN pour les cellules absentes / inférence
    """
    if all_rn_nums is None:
        all_rn_nums = sorted(df["rn_num"].dropna().astype(int).unique())

    camps   = sorted(df["campagne_calc"].unique(), key=lambda c: int(c.split("-")[0]))
    decades = list(range(1, 31))

    # Grille complète : toutes les combinaisons (rn_num, campagne, décade)
    grid = pd.DataFrame(
        [(rn, camp, dec) for rn in all_rn_nums for camp in camps for dec in decades],
        columns=["rn_num", "campagne_calc", "campagne_decade"],
    )
    grid["rn_num"] = grid["rn_num"].astype("Int64")

    data = df[["rn_num", "campagne_calc", "campagne_decade", "label"]].copy()
    data["rn_num"] = data["rn_num"].astype("Int64")

    merged = grid.merge(
        data, on=["rn_num", "campagne_calc", "campagne_decade"], how="left"
    )

    ds_col = [
        _decade_ordinal_date(c, d)
        for c, d in zip(merged["campagne_calc"], merged["campagne_decade"])
    ]
    panel = pd.DataFrame({
        "ID": merged["rn_num"].astype(str).values,
        "ds": ds_col,
        "y":  pd.to_numeric(merged["label"], errors="coerce").astype("float64").values,
    })
    return panel.sort_values(["ID", "ds"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Entraînement NeuralProphet
# ---------------------------------------------------------------------------

def train_neuralprophet(df_panel: pd.DataFrame):
    """Entraîne un NeuralProphet sur le panel complet (90 séries × N décades)."""
    from neuralprophet import NeuralProphet  # import local pour les tests sans NP

    model = NeuralProphet(
        n_forecasts=N_FORECASTS,
        n_lags=N_LAGS,
        epochs=EPOCHS,
        learning_rate=0.001,            # fixe le LR (lr_finder incompatible PyTorch 2.6)
        accelerator="cpu",
        normalize="off",                # labels 0/1 — pas de normalisation nécessaire
        drop_missing=True,              # ignore les samples y=NaN (cellules non prospectées)
        unknown_data_normalization=True,# régions sans labels en train → params globaux
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(df_panel, freq="10D")
    return model


# ---------------------------------------------------------------------------
# Prédictions rolling multi-horizon
# ---------------------------------------------------------------------------

def rolling_forecast(
    model,
    df_train_panel: pd.DataFrame,
    df_val_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Génère des prédictions rolling pour la campagne de validation.

    Approche oracle : combine train + val (y réels inclus) pour que les lags AR
    des derniers timesteps de validation soient correctement alimentés.

    Pour chaque horizon k, la prédiction pour le timestep v est yhat{k} décalé
    de k positions en arrière (pred_{k}[v] = yhat{k}[v-k]).
    Les k premières décades de validation sont prédites sans fuite (contexte
    d'entraînement uniquement).

    Retourne un DataFrame avec colonnes : ID, ds, y, pred_1, pred_3, pred_10.
    """
    df_combined = (
        pd.concat([df_train_panel, df_val_panel])
        .sort_values(["ID", "ds"])
        .reset_index(drop=True)
    )

    # Workaround bug NeuralProphet 0.8 : predict() sur le panel complet supprime
    # 1 ligne en interne (window NaN dans les inputs) mais garde df_forecast de
    # taille originale → ValueError. On prédit région par région pour que chaque
    # série soit indépendante.  Avec n_lags=0, y n'est pas une entrée du modèle
    # → remplir les NaN par 0 n'affecte pas les prédictions yhat*.
    val_ds_set  = set(df_val_panel["ds"].unique())
    true_y_idx  = df_combined.set_index(["ID", "ds"])["y"]
    result_parts: list[pd.DataFrame] = []

    for region_id, grp in df_combined.groupby("ID"):
        grp = grp.sort_values("ds").reset_index(drop=True)
        grp_pred = grp.copy()
        grp_pred["y"] = grp_pred["y"].fillna(0.0)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                forecast = model.predict(grp_pred)
        except Exception:
            continue

        out = forecast[["ID", "ds"]].copy()
        # Restaurer les vraies étiquettes (NaN pour décades non observées)
        out["y"] = out.set_index(["ID", "ds"]).index.map(true_y_idx).values
        for k in HORIZONS.values():
            col = f"yhat{k}"
            if col in forecast.columns:
                # Vrai multi-horizon (n_lags > 0) : pred_k[v] = yhat{k}[v-k]
                out[f"pred_{k}"] = forecast[col].shift(k)
            elif "yhat1" in forecast.columns:
                # NeuralProphet force n_forecasts=1 quand n_lags=0 : sans AR,
                # la prédiction horizon k pour la date v est model(v) = yhat1[v-1]
                # pour tout k (tendance+saisonnalité évaluée à v, indépendante du lag).
                out[f"pred_{k}"] = forecast["yhat1"].shift(1)
        result_parts.append(out)

    if not result_parts:
        return pd.DataFrame()

    all_preds = pd.concat(result_parts, ignore_index=True)
    return all_preds[all_preds["ds"].isin(val_ds_set)].copy()


# ---------------------------------------------------------------------------
# Évaluation par horizon
# ---------------------------------------------------------------------------

def evaluate_horizon(df_preds: pd.DataFrame, step: int) -> dict:
    """Calcule AUC/F1/seuil pour le step-k horizon."""
    pred_col = f"pred_{step}"
    if pred_col not in df_preds.columns:
        nan = float("nan")
        return {"auc_roc": nan, "precision": nan, "recall": nan, "f1": nan, "threshold": nan}

    mask = df_preds["y"].notna() & df_preds[pred_col].notna()
    sub  = df_preds[mask]

    if len(sub) == 0 or sub["y"].nunique() < 2:
        nan = float("nan")
        return {"auc_roc": nan, "precision": nan, "recall": nan, "f1": nan, "threshold": nan}

    y_true = sub["y"].astype(int).to_numpy()
    y_prob = sub[pred_col].to_numpy()
    threshold = optimize_threshold(y_true, y_prob)
    return evaluate(y_true, y_prob, threshold)


# ---------------------------------------------------------------------------
# Boucle walk-forward
# ---------------------------------------------------------------------------

def walk_forward_neuralprophet(df: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward expanding-window sur les 8 folds de validation.

    Réutilise walk_forward_folds() de lgbm_baseline_07 pour le même découpage.
    Inclut les lignes d'inférence (2023-24, y=NaN) dans le panel d'entraînement
    pour alimenter les lags AR sans imputation.
    """
    labeled = df[df["split"].isin({"train", "validation"})].copy()
    labeled["label"] = labeled["label"].astype(int)
    folds = walk_forward_folds(labeled)

    # Liste complète des 90 régions naturelles (fixe pour tous les folds)
    all_rn_nums = sorted(df["rn_num"].dropna().astype(int).unique())

    rapport_rows: list[dict] = []
    pooled: dict[int, list[tuple[np.ndarray, np.ndarray]]] = {
        k: [] for k in HORIZONS.values()
    }

    for i, (_, df_val_labeled, val_camp) in enumerate(folds, 1):
        val_start = int(val_camp.split("-")[0])

        # Panel d'entraînement : toutes lignes (labeled + inference) avant val_camp
        train_mask = (
            df["campagne_calc"].str.split("-").str[0].astype(int) < val_start
        )
        panel_train = prepare_panel_df(df[train_mask], all_rn_nums=all_rn_nums)
        panel_val   = prepare_panel_df(df_val_labeled, all_rn_nums=all_rn_nums)

        n_pos = int((df_val_labeled["label"] == 1).sum())
        n_neg = int((df_val_labeled["label"] == 0).sum())
        print(f"  Fold {i}/{len(folds)} — val={val_camp} "
              f"(pos={n_pos}, neg={n_neg})")

        model     = train_neuralprophet(panel_train)
        val_preds = rolling_forecast(model, panel_train, panel_val)

        row: dict = {
            "campagne_calc": val_camp,
            "n_positifs":    n_pos,
            "n_negatifs":    n_neg,
        }
        for h_name, k in HORIZONS.items():
            metrics = evaluate_horizon(val_preds, k)
            for m_name, m_val in metrics.items():
                row[f"{m_name}_{h_name}"] = m_val

            pred_col = f"pred_{k}"
            if pred_col in val_preds.columns:
                mask = val_preds["y"].notna() & val_preds[pred_col].notna()
                if mask.any():
                    pooled[k].append((
                        val_preds.loc[mask, "y"].astype(int).to_numpy(),
                        val_preds.loc[mask, pred_col].to_numpy(),
                    ))

        rapport_rows.append(row)

    # Ligne GLOBAL : métriques poolées sur tous les folds
    global_row: dict = {"campagne_calc": "GLOBAL"}
    all_y_all: list[np.ndarray] = []
    all_p_all: list[np.ndarray] = []
    for h_name, k in HORIZONS.items():
        if not pooled[k]:
            continue
        all_y = np.concatenate([y for y, _ in pooled[k]])
        all_p = np.concatenate([p for _, p in pooled[k]])
        if h_name == "decadaire":
            all_y_all.append(all_y)
            all_p_all.append(all_p)
        t = optimize_threshold(all_y, all_p)
        global_row["n_positifs"] = int(all_y.sum())
        global_row["n_negatifs"] = int((all_y == 0).sum())
        for m_name, m_val in evaluate(all_y, all_p, t).items():
            global_row[f"{m_name}_{h_name}"] = m_val

    rapport_rows.append(global_row)
    return pd.DataFrame(rapport_rows)


# ---------------------------------------------------------------------------
# Tableau de décision de déploiement
# ---------------------------------------------------------------------------

def build_decision_table(rapport_df: pd.DataFrame, train_minutes: float) -> pd.DataFrame:
    """Construit la comparaison NeuralProphet vs baseline LightGBM #07."""
    rows: list[dict] = []
    global_row = rapport_df[rapport_df["campagne_calc"] == "GLOBAL"].iloc[0]

    for h_name in HORIZONS:
        rows.append({
            "modele":           "NeuralProphet",
            "horizon":          h_name,
            "auc_global":       round(float(global_row.get(f"auc_roc_{h_name}", float("nan"))), 4),
            "f1_global":        round(float(global_row.get(f"f1_{h_name}", float("nan"))), 4),
            "temps_train_min":  round(train_minutes, 1),
        })

    if IN_RAPPORT_07.exists():
        g07 = pd.read_csv(IN_RAPPORT_07)
        g07_row = g07[g07["campagne_calc"] == "GLOBAL"].iloc[0]
        rows.append({
            "modele":           "LightGBM_07",
            "horizon":          "decadaire",
            "auc_global":       round(float(g07_row["auc_roc"]), 4),
            "f1_global":        round(float(g07_row["f1"]), 4),
            "temps_train_min":  float("nan"),
        })

    decision_df = pd.DataFrame(rows)

    # Décision : déployer NeuralProphet si AUC décadaire > LGBM ET budget < 30 min
    np_dec   = decision_df[(decision_df["modele"] == "NeuralProphet") & (decision_df["horizon"] == "decadaire")]
    lgbm_dec = decision_df[(decision_df["modele"] == "LightGBM_07")]

    if len(np_dec) > 0 and len(lgbm_dec) > 0:
        np_auc   = float(np_dec["auc_global"].iloc[0])
        lgbm_auc = float(lgbm_dec["auc_global"].iloc[0])
        deploy   = (not np.isnan(np_auc)) and (np_auc > lgbm_auc) and (train_minutes < 30)
        decision_label = "deploy" if deploy else "keep_lgbm_baseline"
    else:
        decision_label = "indeterminate"

    decision_df["decision"] = decision_label
    return decision_df


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def run() -> None:
    t0 = time.time()
    print(f"Chargement table d'entraînement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)

    print("\n=== Validation walk-forward NeuralProphet ===")
    rapport_df = walk_forward_neuralprophet(df)

    print("\n=== Rapport walk-forward ===")
    print(rapport_df.to_string(index=False))

    elapsed = (time.time() - t0) / 60
    print(f"\nTemps walk-forward : {elapsed:.1f} min")

    # Modèle final entraîné sur toutes les données (train + val + inference pour les lags)
    print("\nEntraînement modèle final sur toutes les données…")
    all_rn_nums = sorted(df["rn_num"].dropna().astype(int).unique())
    panel_all   = prepare_panel_df(df, all_rn_nums=all_rn_nums)
    model_final = train_neuralprophet(panel_all)

    total_min = (time.time() - t0) / 60

    OUT_RAPPORT.parent.mkdir(parents=True, exist_ok=True)
    rapport_df.to_csv(OUT_RAPPORT, index=False)
    joblib.dump(model_final, OUT_MODEL)

    decision_df = build_decision_table(rapport_df, total_min)
    decision_df.to_csv(OUT_DECISION, index=False)

    print(f"\nSortie rapport     : {OUT_RAPPORT}")
    print(f"Sortie modèle      : {OUT_MODEL}")
    print(f"Sortie décision    : {OUT_DECISION}")
    print("\n=== Décision déploiement ===")
    print(decision_df.to_string(index=False))

    budget_ok = total_min < 30
    print(f"\nTemps total : {total_min:.1f} min {'[OK < 30 min]' if budget_ok else '[!! > 30 min]'}")


if __name__ == "__main__":
    run()
