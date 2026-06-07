"""Pipeline #07 — Modèle LightGBM baseline présence/absence + validation walk-forward.

Entraîne un LGBMClassifier binaire sur la table d'entraînement unifiée (#06),
évalue par validation walk-forward expanding-window (un fold par campagne de
validation), optimise le seuil de décision pour maximiser F1 et exporte le
rapport de performance campagne par campagne.

Sorties :
  data/processed/07_rapport_walk_forward.csv   — métriques par campagne + GLOBAL
  data/processed/07_feature_importances.csv    — importance (gain) moyenne/écart-type
  data/processed/07_lgbm_model.pkl             — modèle final (joblib)
"""

from __future__ import annotations

import warnings
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import train_test_split

DATA_DIR        = Path(__file__).parent.parent / "data"
IN_PARQUET      = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"
OUT_RAPPORT     = DATA_DIR / "processed" / "07_rapport_walk_forward.csv"
OUT_IMPORTANCES = DATA_DIR / "processed" / "07_feature_importances.csv"
OUT_MODEL       = DATA_DIR / "processed" / "07_lgbm_model.pkl"

KEY_COLS  = ["rn_num", "rn_nom", "campagne_calc", "campagne_decade"]
META_COLS = ["split", "effort_prospection", "label", "date_start"]

GREGARITE_CATS = ["absent", "S", "St", "T", "G"]
THRESHOLD_GRID = np.linspace(0.05, 0.50, 46)


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Retourne les colonnes features dans l'ordre du DataFrame."""
    exclude = set(KEY_COLS + META_COLS)
    return [c for c in df.columns if c not in exclude]


def prepare_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Prépare X : encode niveau_gregarite_dominant en catégorie LightGBM."""
    X = df[feature_cols].copy()
    if "niveau_gregarite_dominant" in X.columns:
        X["niveau_gregarite_dominant"] = pd.Categorical(
            X["niveau_gregarite_dominant"], categories=GREGARITE_CATS
        )
    return X


def compute_scale_pos_weight(y: pd.Series) -> float:
    """Ratio négatifs / positifs pour corriger le déséquilibre de classes."""
    n_pos = (y == 1).sum()
    n_neg = (y == 0).sum()
    if n_pos == 0:
        return 1.0
    return float(n_neg) / float(n_pos)


def optimize_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Trouve le seuil dans [0.05, 0.50] qui maximise le score F1."""
    best_f1, best_t = -1.0, 0.20
    for t in THRESHOLD_GRID:
        y_pred = (y_prob >= t).astype(int)
        if y_pred.sum() == 0:
            continue
        p, r, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average="binary", zero_division=0
        )
        if f1 > best_f1:
            best_f1, best_t = f1, float(t)
    return best_t


def evaluate(
    y_true: np.ndarray, y_prob: np.ndarray, threshold: float
) -> dict:
    """Calcule AUC-ROC, précision, rappel, F1 au seuil donné."""
    y_pred = (y_prob >= threshold).astype(int)
    try:
        auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        auc = float("nan")
    p, r, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    return {
        "auc_roc":   round(auc, 4),
        "precision": round(float(p), 4),
        "recall":    round(float(r), 4),
        "f1":        round(float(f1), 4),
        "threshold": round(threshold, 4),
    }


def walk_forward_folds(
    df: pd.DataFrame,
) -> list[tuple[pd.DataFrame, pd.DataFrame, str]]:
    """Génère les folds walk-forward expanding-window.

    Chaque fold : (df_train, df_val, campagne_val).
    df_train inclut toutes les lignes labellisées antérieures à campagne_val.
    df_val contient uniquement les lignes de campagne_val.
    """
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


def train_lgbm(
    X_train: pd.DataFrame, y_train: pd.Series
) -> lgb.LGBMClassifier:
    """Entraîne un LGBMClassifier avec early stopping sur 20 % du train."""
    spw = compute_scale_pos_weight(y_train)
    model = lgb.LGBMClassifier(
        objective="binary",
        metric="auc",
        learning_rate=0.05,
        num_leaves=31,
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
        scale_pos_weight=spw,
    )
    cat_cols = [c for c in X_train.columns if c == "niveau_gregarite_dominant"]
    X_tr, X_ev, y_tr, y_ev = train_test_split(
        X_train, y_train, test_size=0.20, random_state=42, stratify=y_train
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_ev, y_ev)],
            categorical_feature=cat_cols if cat_cols else "auto",
            callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)],
        )
    return model


def run_walk_forward(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[tuple[np.ndarray, np.ndarray]]]:
    """Boucle walk-forward : entraîne un modèle par fold, retourne rapport + importances."""
    feature_cols = get_feature_columns(df)
    folds = walk_forward_folds(df)

    rapport_rows = []
    importances_list: list[pd.Series] = []
    all_val_preds: list[tuple[np.ndarray, np.ndarray]] = []

    for i, (df_train, df_val, val_camp) in enumerate(folds, 1):
        y_train = df_train["label"].astype(int)
        y_val   = df_val["label"].astype(int).to_numpy()
        X_train = prepare_features(df_train, feature_cols)
        X_val   = prepare_features(df_val, feature_cols)

        print(f"  Fold {i}/{len(folds)} — val={val_camp} "
              f"(train={len(df_train)}, val={len(df_val)}, "
              f"pos_val={y_val.sum()})")

        model = train_lgbm(X_train, y_train)
        y_prob = model.predict_proba(X_val)[:, 1]

        threshold = optimize_threshold(y_val, y_prob)
        metrics   = evaluate(y_val, y_prob, threshold)

        rapport_rows.append({
            "campagne_calc": val_camp,
            "n_positifs":    int(y_val.sum()),
            "n_negatifs":    int((y_val == 0).sum()),
            **metrics,
        })
        all_val_preds.append((y_val, y_prob))

        imp = pd.Series(
            model.feature_importances_, index=feature_cols, name=val_camp
        )
        importances_list.append(imp)

    rapport_df = pd.DataFrame(rapport_rows)

    imp_matrix = pd.DataFrame(importances_list)
    importances_df = pd.DataFrame({
        "feature":          feature_cols,
        "importance_mean":  imp_matrix.mean().values.round(2),
        "importance_std":   imp_matrix.std().values.round(2),
    }).sort_values("importance_mean", ascending=False).reset_index(drop=True)

    return rapport_df, importances_df, all_val_preds


def run() -> None:
    print(f"Chargement table d'entraînement : {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)

    labeled = df[df["split"].isin({"train", "validation"})].copy()
    labeled["label"] = labeled["label"].astype(int)
    print(f"Lignes labellisées : {len(labeled)} "
          f"(train={( labeled['split']=='train').sum()}, "
          f"validation={(labeled['split']=='validation').sum()})")

    print("\n=== Validation walk-forward ===")
    rapport_df, importances_df, all_val_preds = run_walk_forward(labeled)

    # Ligne GLOBAL : AUC sur toutes les prédictions de validation poolées
    y_true_all = np.concatenate([y for y, _ in all_val_preds])
    y_prob_all = np.concatenate([p for _, p in all_val_preds])
    threshold_global = optimize_threshold(y_true_all, y_prob_all)
    global_metrics   = evaluate(y_true_all, y_prob_all, threshold_global)
    rapport_df = pd.concat([
        rapport_df,
        pd.DataFrame([{
            "campagne_calc": "GLOBAL",
            "n_positifs":    int(y_true_all.sum()),
            "n_negatifs":    int((y_true_all == 0).sum()),
            **global_metrics,
        }]),
    ], ignore_index=True)

    print("\n=== Rapport walk-forward ===")
    print(rapport_df.to_string(index=False))
    print("\n=== Top 10 features (gain moyen) ===")
    print(importances_df.head(10).to_string(index=False))

    # Modèle final entraîné sur tout le set labellisé (train + validation)
    print("\nEntraînement du modèle final sur toutes les données labellisées…")
    feature_cols = get_feature_columns(labeled)
    X_all = prepare_features(labeled, feature_cols)
    y_all = labeled["label"]
    model_final = train_lgbm(X_all, y_all)

    OUT_RAPPORT.parent.mkdir(parents=True, exist_ok=True)
    rapport_df.to_csv(OUT_RAPPORT, index=False)
    importances_df.to_csv(OUT_IMPORTANCES, index=False)
    joblib.dump(model_final, OUT_MODEL)

    print(f"\nSortie rapport       : {OUT_RAPPORT}")
    print(f"Sortie importances   : {OUT_IMPORTANCES}")
    print(f"Sortie modèle final  : {OUT_MODEL}")

    auc_global = rapport_df.loc[rapport_df["campagne_calc"] == "GLOBAL", "auc_roc"].iloc[0]
    cible_ok = auc_global >= 0.85
    statut = "[OK >= 0.85]" if cible_ok else "[!! < 0.85]"
    print(f"\nAUC global = {auc_global:.4f} {statut}")


if __name__ == "__main__":
    run()
