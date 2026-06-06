"""Pipeline #08 — Modèle hiérarchique LightGBM : densité + phase acridienne.

Ajoute deux étapes conditionnelles au modèle de présence/absence (#07) :
  1. Régression LightGBM — densité équivalent imago (ind/ha), entraînée sur
     les cellules avec présence confirmée (label == 1) uniquement.
  2. Classification LightGBM — phase acridienne (S/St/T/G), entraînée sur
     les mêmes cellules. Le déséquilibre sévère de la classe grégaire (G ≈ 5,8 %)
     est corrigé par class_weight="balanced" et un seuil de décision abaissé.

Les trois modèles sont enchaînés en inférence : une prédiction d'absence en
étape 1 court-circuite les étapes 2 et 3 (densité et phase restent à NaN/None).

Sorties :
  data/processed/08_rapport_walk_forward.csv  — métriques par campagne + GLOBAL
  data/processed/08_lgbm_densite.pkl          — modèle régression densité (joblib)
  data/processed/08_lgbm_phase.pkl            — modèle classification phase (joblib)
"""

from __future__ import annotations

import warnings
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    f1_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

DATA_DIR           = Path(__file__).parent.parent / "data"
IN_PARQUET         = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
IN_GEO             = DATA_DIR / "processed" / "02_gregarite_potentiel.parquet"
IN_MODEL_PRESENCE  = DATA_DIR / "processed" / "07_lgbm_model.pkl"
OUT_RAPPORT        = DATA_DIR / "processed" / "08_rapport_walk_forward.csv"
OUT_MODEL_DENSITE  = DATA_DIR / "processed" / "08_lgbm_densite.pkl"
OUT_MODEL_PHASE    = DATA_DIR / "processed" / "08_lgbm_phase.pkl"

KEY_COLS  = ["rn_num", "rn_nom", "campagne_calc", "campagne_decade"]
META_COLS = ["split", "effort_prospection", "label"]

DENSITY_COL      = "densite_imago_median"
PHASE_COL        = "niveau_gregarite_dominant"
PHASE_CATEGORIES = ["S", "St", "T", "G"]
GREGARITE_CATS   = ["absent", "S", "St", "T", "G"]

THRESHOLD_GRID = np.linspace(0.05, 0.50, 46)


# ---------------------------------------------------------------------------
# Préparation des données
# ---------------------------------------------------------------------------

def aggregate_densite(geo_path: Path) -> pd.DataFrame:
    """Agrège la densité médiane depuis le parquet #02 par (rn_num × campagne × décade).

    Filtre les lignes sans région naturelle assignée et sans valeur de densité.
    """
    gdf = pd.read_parquet(geo_path)

    valid = gdf[
        gdf["rn_num"].notna()
        & gdf["campagne_calc"].notna()
        & gdf["campagne_decade"].notna()
        & gdf["densite_imago"].notna()
    ].copy()
    valid["rn_num"] = valid["rn_num"].astype("Int64")
    valid["campagne_decade"] = valid["campagne_decade"].astype(int)

    agg = (
        valid.groupby(
            ["rn_num", "campagne_calc", "campagne_decade"],
            observed=True,
            dropna=False,
        )["densite_imago"]
        .median()
        .reset_index()
        .rename(columns={"densite_imago": DENSITY_COL})
    )
    return agg


def enrich_table(df_06: pd.DataFrame, geo_path: Path) -> pd.DataFrame:
    """Joint densite_imago_median sur la table #06."""
    if not geo_path.exists():
        warnings.warn(
            f"Parquet #02 absent ({geo_path}) — colonne {DENSITY_COL} non disponible.",
            stacklevel=2,
        )
        df_06[DENSITY_COL] = np.nan
        return df_06

    density_agg = aggregate_densite(geo_path)
    return df_06.merge(
        density_agg,
        on=["rn_num", "campagne_calc", "campagne_decade"],
        how="left",
    )


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Colonnes features : tout sauf clés, méta et variables cibles #08."""
    exclude = set(KEY_COLS + META_COLS + [DENSITY_COL, PHASE_COL])
    return [c for c in df.columns if c not in exclude]


def prepare_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Prépare X : encode niveau_gregarite_dominant en catégorie LightGBM."""
    X = df[feature_cols].copy()
    if "niveau_gregarite_dominant" in X.columns:
        X["niveau_gregarite_dominant"] = pd.Categorical(
            X["niveau_gregarite_dominant"], categories=GREGARITE_CATS
        )
    return X


# ---------------------------------------------------------------------------
# Entraînement
# ---------------------------------------------------------------------------

def train_density_model(
    X_train: pd.DataFrame, y_train: pd.Series
) -> lgb.LGBMRegressor:
    """Entraîne LGBMRegressor MAE avec early stopping sur 20 % holdout."""
    model = lgb.LGBMRegressor(
        objective="regression_l1",
        metric="mae",
        learning_rate=0.05,
        num_leaves=31,
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    X_tr, X_ev, y_tr, y_ev = train_test_split(
        X_train, y_train, test_size=0.20, random_state=42
    )
    cat_cols = [c for c in X_train.columns if c == "niveau_gregarite_dominant"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_ev, y_ev)],
            categorical_feature=cat_cols if cat_cols else "auto",
            callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)],
        )
    return model


def train_phase_model(
    X_train: pd.DataFrame, y_train: pd.Series
) -> lgb.LGBMClassifier:
    """Entraîne LGBMClassifier multiclass (S/St/T/G) avec class_weight='balanced'."""
    y_encoded = y_train.map({p: i for i, p in enumerate(PHASE_CATEGORIES)})
    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(PHASE_CATEGORIES),
        metric="multi_logloss",
        class_weight="balanced",
        learning_rate=0.05,
        num_leaves=31,
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    X_tr, X_ev, y_tr, y_ev = train_test_split(
        X_train, y_encoded, test_size=0.20, random_state=42,
        stratify=y_encoded,
    )
    cat_cols = [c for c in X_train.columns if c == "niveau_gregarite_dominant"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_ev, y_ev)],
            categorical_feature=cat_cols if cat_cols else "auto",
            callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)],
        )
    return model


# ---------------------------------------------------------------------------
# Évaluation
# ---------------------------------------------------------------------------

def evaluate_density(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """RMSE et MAE sur les relevés avec présence."""
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae  = float(mean_absolute_error(y_true, y_pred))
    return {"rmse_densite": round(rmse, 4), "mae_densite": round(mae, 4)}


def optimize_threshold_G(
    y_true_encoded: np.ndarray, y_prob: np.ndarray
) -> float:
    """Trouve le seuil P(G) dans [0.05, 0.50] maximisant recall_G (F1-macro ≥ 0.30)."""
    g_idx = PHASE_CATEGORIES.index("G")
    best_recall, best_t = -1.0, 0.15

    for t in THRESHOLD_GRID:
        y_pred = np.where(
            y_prob[:, g_idx] >= t,
            g_idx,
            np.argmax(
                np.concatenate(
                    [y_prob[:, :g_idx], y_prob[:, g_idx + 1:]], axis=1
                ),
                axis=1,
            ).clip(0, g_idx - 1),
        )
        # Assurer que argmax sur sous-tableau est remappé correctement
        non_g_mask = y_prob[:, g_idx] < t
        if non_g_mask.any():
            sub_prob = y_prob[non_g_mask]
            sub_prob_no_g = np.delete(sub_prob, g_idx, axis=1)
            argmax_no_g = np.argmax(sub_prob_no_g, axis=1)
            remapped = np.where(argmax_no_g >= g_idx, argmax_no_g + 1, argmax_no_g)
            y_pred[non_g_mask] = remapped

        if y_pred.sum() == 0:
            continue

        f1_mac = f1_score(y_true_encoded, y_pred, average="macro", zero_division=0)
        if f1_mac < 0.30:
            continue

        recall_g = recall_score(
            y_true_encoded == g_idx,
            y_pred == g_idx,
            zero_division=0,
        )
        if recall_g > best_recall:
            best_recall, best_t = recall_g, float(t)

    return best_t


def _apply_threshold_G(y_prob: np.ndarray, threshold_G: float) -> np.ndarray:
    """Prédit la classe en appliquant un seuil abaissé pour G."""
    g_idx = PHASE_CATEGORIES.index("G")
    y_pred = np.full(len(y_prob), -1, dtype=int)
    g_mask = y_prob[:, g_idx] >= threshold_G
    y_pred[g_mask] = g_idx
    non_g_idx = np.where(~g_mask)[0]
    if len(non_g_idx) > 0:
        sub_prob = y_prob[non_g_idx]
        sub_prob_no_g = np.delete(sub_prob, g_idx, axis=1)
        argmax_no_g = np.argmax(sub_prob_no_g, axis=1)
        remapped = np.where(argmax_no_g >= g_idx, argmax_no_g + 1, argmax_no_g)
        y_pred[non_g_idx] = remapped
    return y_pred


def evaluate_phase(
    y_true_encoded: np.ndarray, y_prob: np.ndarray, threshold_G: float
) -> dict:
    """F1-macro et rappel sur la classe G au seuil donné."""
    y_pred = _apply_threshold_G(y_prob, threshold_G)
    f1_mac = f1_score(
        y_true_encoded, y_pred,
        average="macro", labels=list(range(len(PHASE_CATEGORIES))),
        zero_division=0,
    )
    g_idx = PHASE_CATEGORIES.index("G")
    recall_g = recall_score(
        y_true_encoded == g_idx,
        y_pred == g_idx,
        zero_division=0,
    )
    return {
        "f1_macro_phase": round(float(f1_mac), 4),
        "recall_G":       round(float(recall_g), 4),
        "threshold_G":    round(threshold_G, 4),
    }


# ---------------------------------------------------------------------------
# Walk-forward (identique à #07)
# ---------------------------------------------------------------------------

def walk_forward_folds(
    df: pd.DataFrame,
) -> list[tuple[pd.DataFrame, pd.DataFrame, str]]:
    """Génère les folds walk-forward expanding-window par campagne de validation."""
    val_campaigns = sorted(
        df.loc[df["split"] == "validation", "campagne_calc"].unique(),
        key=lambda c: int(c.split("-")[0]),
    )
    folds = []
    for val_camp in val_campaigns:
        val_start = int(val_camp.split("-")[0])
        train_mask = (df["split"] == "train") | (
            (df["split"] == "validation")
            & (df["campagne_calc"].str.split("-").str[0].astype(int) < val_start)
        )
        val_mask = df["campagne_calc"] == val_camp
        folds.append((df[train_mask].copy(), df[val_mask].copy(), val_camp))
    return folds


def run_walk_forward(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Boucle walk-forward pour densité et phase.

    Pour chaque fold, filtre les cellules présence (label==1), entraîne les
    modèles densité et phase et évalue les métriques sur la validation.
    """
    feature_cols = get_feature_columns(df)
    folds = walk_forward_folds(df)

    rapport_rows: list[dict] = []
    imp_density_list: list[pd.Series] = []
    imp_phase_list: list[pd.Series] = []
    all_density_preds: list[tuple[np.ndarray, np.ndarray]] = []
    all_phase_preds:   list[tuple[np.ndarray, np.ndarray]] = []

    for i, (df_train, df_val, val_camp) in enumerate(folds, 1):
        # — Sous-ensemble présence uniquement
        pres_train = df_train[df_train["label"] == 1].copy()
        pres_val   = df_val[df_val["label"] == 1].copy()

        n_pres = len(pres_val)
        print(f"  Fold {i}/{len(folds)} — val={val_camp} "
              f"(train_pres={len(pres_train)}, val_pres={n_pres})")

        # — Modèle densité
        y_den_train = pres_train[DENSITY_COL].dropna()
        X_den_train = prepare_features(
            pres_train.loc[y_den_train.index], feature_cols
        )
        y_den_val = pres_val[DENSITY_COL].dropna()
        X_den_val = prepare_features(pres_val.loc[y_den_val.index], feature_cols)

        density_metrics = {"rmse_densite": float("nan"), "mae_densite": float("nan")}
        if len(X_den_train) >= 10 and len(X_den_val) >= 2:
            mdl_density = train_density_model(X_den_train, y_den_train)
            y_den_pred  = mdl_density.predict(X_den_val)
            density_metrics = evaluate_density(y_den_val.to_numpy(), y_den_pred)
            all_density_preds.append((y_den_val.to_numpy(), y_den_pred))
            imp_density_list.append(
                pd.Series(mdl_density.feature_importances_, index=feature_cols, name=val_camp)
            )
        else:
            print(f"    [SKIP densité] train={len(X_den_train)}, val={len(X_den_val)} — trop peu de données")

        # — Modèle phase (filtre "absent" et NaN)
        phase_mask_train = (
            pres_train[PHASE_COL].notna()
            & (pres_train[PHASE_COL] != "absent")
            & (pres_train[PHASE_COL].isin(PHASE_CATEGORIES))
        )
        phase_mask_val = (
            pres_val[PHASE_COL].notna()
            & (pres_val[PHASE_COL] != "absent")
            & (pres_val[PHASE_COL].isin(PHASE_CATEGORIES))
        )
        ph_train = pres_train[phase_mask_train].copy()
        ph_val   = pres_val[phase_mask_val].copy()

        phase_metrics = {
            "f1_macro_phase": float("nan"),
            "recall_G":       float("nan"),
            "threshold_G":    float("nan"),
        }
        if len(ph_train) >= 10 and len(ph_val) >= 2:
            X_ph_train = prepare_features(ph_train, feature_cols)
            y_ph_train = ph_train[PHASE_COL]
            X_ph_val   = prepare_features(ph_val, feature_cols)
            y_ph_val   = ph_val[PHASE_COL]

            # Vérifie qu'au moins 2 classes dans train
            if y_ph_train.nunique() >= 2:
                mdl_phase = train_phase_model(X_ph_train, y_ph_train)
                y_prob_phase = mdl_phase.predict_proba(X_ph_val)

                y_enc_val = y_ph_val.map(
                    {p: i for i, p in enumerate(PHASE_CATEGORIES)}
                ).to_numpy()
                threshold_G = optimize_threshold_G(y_enc_val, y_prob_phase)
                phase_metrics = evaluate_phase(y_enc_val, y_prob_phase, threshold_G)
                all_phase_preds.append((y_enc_val, y_prob_phase))

                imp_phase_list.append(
                    pd.Series(mdl_phase.feature_importances_, index=feature_cols, name=val_camp)
                )
        else:
            print(f"    [SKIP phase] train={len(ph_train)}, val={len(ph_val)} — trop peu de données")

        rapport_rows.append({
            "campagne_calc": val_camp,
            "n_presence":    n_pres,
            **density_metrics,
            **phase_metrics,
        })

    rapport_df = pd.DataFrame(rapport_rows)

    def _make_importances(imp_list: list[pd.Series], feature_cols: list[str]) -> pd.DataFrame:
        if not imp_list:
            return pd.DataFrame(columns=["feature", "importance_mean", "importance_std"])
        mat = pd.DataFrame(imp_list)
        return pd.DataFrame({
            "feature":         feature_cols,
            "importance_mean": mat.mean().values.round(2),
            "importance_std":  mat.std().values.round(2),
        }).sort_values("importance_mean", ascending=False).reset_index(drop=True)

    imp_density_df = _make_importances(imp_density_list, feature_cols)
    imp_phase_df   = _make_importances(imp_phase_list, feature_cols)

    return rapport_df, imp_density_df, imp_phase_df, all_density_preds, all_phase_preds


# ---------------------------------------------------------------------------
# Inférence hiérarchique
# ---------------------------------------------------------------------------

def predict_hierarchical(
    df: pd.DataFrame,
    model_presence: lgb.LGBMClassifier,
    model_density: lgb.LGBMRegressor,
    model_phase: lgb.LGBMClassifier,
    threshold_presence: float,
    threshold_G: float,
) -> pd.DataFrame:
    """Chaîne les trois modèles sur un DataFrame de lignes à prédire.

    Une prédiction d'absence court-circuite les étapes densité et phase
    (densite_pred = NaN, phase_pred = None).
    """
    feature_cols = get_feature_columns(df)
    X = prepare_features(df, feature_cols)

    y_prob_pres = model_presence.predict_proba(X)[:, 1]
    presence_pred = (y_prob_pres >= threshold_presence).astype(int)

    n = len(df)
    densite_pred = np.full(n, np.nan)
    phase_pred   = np.full(n, None, dtype=object)

    pres_mask = presence_pred == 1
    if pres_mask.any():
        X_pres = X[pres_mask]
        densite_pred[pres_mask] = model_density.predict(X_pres)

        y_prob_phase = model_phase.predict_proba(X_pres)
        y_phase_enc  = _apply_threshold_G(y_prob_phase, threshold_G)
        phase_pred[pres_mask] = [PHASE_CATEGORIES[i] for i in y_phase_enc]

    result = df[KEY_COLS].copy() if all(c in df.columns for c in KEY_COLS) else df.copy()
    result["presence_pred"] = presence_pred
    result["densite_pred"]  = densite_pred
    result["phase_pred"]    = phase_pred
    return result


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def run() -> None:
    print(f"Chargement table d'entraînement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)

    print(f"Enrichissement avec densité depuis : {IN_GEO}")
    df = enrich_table(df, IN_GEO)

    labeled = df[df["split"].isin({"train", "validation"})].copy()
    labeled["label"] = labeled["label"].astype(int)
    print(f"Lignes labellisées : {len(labeled)} "
          f"(train={( labeled['split']=='train').sum()}, "
          f"validation={(labeled['split']=='validation').sum()})")
    print(f"Lignes avec présence (label=1) : {(labeled['label']==1).sum()}")
    if DENSITY_COL in labeled.columns:
        print(f"Densité disponible : {labeled[DENSITY_COL].notna().sum()} lignes")
    if PHASE_COL in labeled.columns:
        n_phase = labeled.loc[
            labeled["label"] == 1,
            PHASE_COL,
        ].isin(PHASE_CATEGORIES).sum()
        print(f"Phase disponible (présence + S/St/T/G) : {n_phase} lignes")

    print("\n=== Validation walk-forward — densité + phase ===")
    rapport_df, imp_density_df, imp_phase_df, all_density_preds, all_phase_preds = (
        run_walk_forward(labeled)
    )

    # Ligne GLOBAL — métriques poolées sur toutes prédictions val
    global_density = {"rmse_densite": float("nan"), "mae_densite": float("nan")}
    if all_density_preds:
        y_true_d = np.concatenate([y for y, _ in all_density_preds])
        y_pred_d = np.concatenate([p for _, p in all_density_preds])
        global_density = evaluate_density(y_true_d, y_pred_d)

    global_phase = {
        "f1_macro_phase": float("nan"),
        "recall_G":       float("nan"),
        "threshold_G":    float("nan"),
    }
    if all_phase_preds:
        y_true_p  = np.concatenate([y for y, _ in all_phase_preds])
        y_prob_p  = np.concatenate([p for _, p in all_phase_preds], axis=0)
        threshold_G_global = optimize_threshold_G(y_true_p, y_prob_p)
        global_phase = evaluate_phase(y_true_p, y_prob_p, threshold_G_global)

    rapport_df = pd.concat([
        rapport_df,
        pd.DataFrame([{
            "campagne_calc": "GLOBAL",
            "n_presence":    int((labeled["label"] == 1).sum()),
            **global_density,
            **global_phase,
        }]),
    ], ignore_index=True)

    print("\n=== Rapport walk-forward ===")
    print(rapport_df.to_string(index=False))

    if not imp_density_df.empty:
        print("\n=== Top 10 features densité (gain moyen) ===")
        print(imp_density_df.head(10).to_string(index=False))
    if not imp_phase_df.empty:
        print("\n=== Top 10 features phase (gain moyen) ===")
        print(imp_phase_df.head(10).to_string(index=False))

    # Modèles finaux entraînés sur toutes les données labellisées (train + val)
    print("\nEntraînement des modèles finaux sur toutes les données labellisées…")
    feature_cols = get_feature_columns(labeled)
    pres_all = labeled[labeled["label"] == 1].copy()

    # Densité finale
    y_den_all = pres_all[DENSITY_COL].dropna()
    X_den_all = prepare_features(pres_all.loc[y_den_all.index], feature_cols)
    if len(X_den_all) >= 10:
        model_density_final = train_density_model(X_den_all, y_den_all)
        joblib.dump(model_density_final, OUT_MODEL_DENSITE)
        print(f"Modèle densité final   : {OUT_MODEL_DENSITE}")
    else:
        print("[WARN] Pas assez de données pour le modèle densité final.")
        model_density_final = None

    # Phase finale
    phase_all_mask = (
        pres_all[PHASE_COL].notna()
        & (pres_all[PHASE_COL] != "absent")
        & (pres_all[PHASE_COL].isin(PHASE_CATEGORIES))
    )
    ph_all = pres_all[phase_all_mask].copy()
    X_ph_all = prepare_features(ph_all, feature_cols)
    y_ph_all = ph_all[PHASE_COL]
    if len(X_ph_all) >= 10 and y_ph_all.nunique() >= 2:
        model_phase_final = train_phase_model(X_ph_all, y_ph_all)
        joblib.dump(model_phase_final, OUT_MODEL_PHASE)
        print(f"Modèle phase final     : {OUT_MODEL_PHASE}")
    else:
        print("[WARN] Pas assez de données pour le modèle phase final.")
        model_phase_final = None

    OUT_RAPPORT.parent.mkdir(parents=True, exist_ok=True)
    rapport_df.to_csv(OUT_RAPPORT, index=False)
    print(f"\nSortie rapport         : {OUT_RAPPORT}")

    recall_G_global = rapport_df.loc[
        rapport_df["campagne_calc"] == "GLOBAL", "recall_G"
    ].iloc[0]
    cible_ok = (not np.isnan(recall_G_global)) and recall_G_global >= 0.70
    statut = "[OK >= 0.70]" if cible_ok else "[!! < 0.70]"
    print(f"\nRappel G global = {recall_G_global:.4f} {statut}")


if __name__ == "__main__":
    run()
