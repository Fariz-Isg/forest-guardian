"""Train Random Forest and XGBoost fire-occurrence classifiers on the
forest-masked, grid-cell x month dataset (grid_cells.csv + monthly_features.csv).

Class imbalance: burned cells are a small minority of cell-months, as expected
for a rare-event problem. We use class weighting (class_weight='balanced' for
RF, scale_pos_weight for XGBoost) rather than SMOTE — tree ensembles handle
weighted imbalance well natively, and weighting avoids the risk of SMOTE
inventing synthetic feature combinations that don't correspond to real
weather/terrain/vegetation states.

Evaluation uses precision/recall/F1/AUC-PR (not plain accuracy or AUC-ROC
alone), since AUC-ROC is misleadingly optimistic for this class imbalance.
"""
import json
import os

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score, classification_report, f1_score,
    precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

HERE = os.path.dirname(__file__)

grid = pd.read_csv(os.path.join(HERE, "grid_cells.csv"))
monthly = pd.read_csv(os.path.join(HERE, "monthly_features.csv"))
df = monthly.merge(grid, on=["row", "col"], how="left")
df = df.sort_values(["row", "col", "month"]).reset_index(drop=True)

# Historical fire frequency: count of burns in this cell strictly BEFORE this
# month (shifted, so it's never leaking the current month's own label).
df["prior_fire_count"] = (
    df.groupby(["row", "col"])["burned"].cumsum().sub(df["burned"])
)

FEATURES = [
    "tmmx", "tmmn", "vs", "rmin", "pr", "pr_90d",
    "elevation", "slope", "aspect", "forest_fraction", "prior_fire_count",
]
df = df.dropna(subset=FEATURES + ["burned"])
print(f"Training rows after dropping incomplete cell-months: {len(df)}")
print(f"Positive rate (burned=1): {df['burned'].mean():.4%}")

X = df[FEATURES].values
y = df["burned"].values

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

results = {}

rf = RandomForestClassifier(
    n_estimators=300, max_depth=12, class_weight="balanced",
    n_jobs=-1, random_state=42,
)
rf.fit(X_train, y_train)
rf_proba = rf.predict_proba(X_test)[:, 1]
rf_pred = rf.predict(X_test)
results["random_forest"] = {
    "precision": precision_score(y_test, rf_pred, zero_division=0),
    "recall": recall_score(y_test, rf_pred, zero_division=0),
    "f1": f1_score(y_test, rf_pred, zero_division=0),
    "auc_roc": roc_auc_score(y_test, rf_proba),
    "auc_pr": average_precision_score(y_test, rf_proba),
}

pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
xgb = XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.1,
    scale_pos_weight=pos_weight, eval_metric="aucpr",
    n_jobs=-1, random_state=42,
)
xgb.fit(X_train, y_train)
xgb_proba = xgb.predict_proba(X_test)[:, 1]
xgb_pred = xgb.predict(X_test)
results["xgboost"] = {
    "precision": precision_score(y_test, xgb_pred, zero_division=0),
    "recall": recall_score(y_test, xgb_pred, zero_division=0),
    "f1": f1_score(y_test, xgb_pred, zero_division=0),
    "auc_roc": roc_auc_score(y_test, xgb_proba),
    "auc_pr": average_precision_score(y_test, xgb_proba),
}

print(json.dumps(results, indent=2))

joblib.dump(rf, os.path.join(HERE, "rf_model.joblib"))
joblib.dump(xgb, os.path.join(HERE, "xgb_model.joblib"))
with open(os.path.join(HERE, "eval_results.json"), "w") as f:
    json.dump({"features": FEATURES, "n_rows": len(df), "positive_rate": float(df["burned"].mean()),
               "results": results}, f, indent=2)

# Feature importance (XGBoost — generally more reliable than RF's impurity-based
# importances, which are biased toward high-cardinality numeric features).
importances = xgb.feature_importances_
order = np.argsort(importances)
plt.figure(figsize=(8, 5))
plt.barh([FEATURES[i] for i in order], importances[order], color="#e8622c")
plt.xlabel("XGBoost feature importance")
plt.title("Forest Guardian fire-risk model — feature importance")
plt.tight_layout()
plt.savefig(os.path.join(HERE, "feature_importance.png"), dpi=150)
print(f"Wrote {os.path.join(HERE, 'feature_importance.png')}")

print("\nClassification report (XGBoost, default 0.5 threshold):")
print(classification_report(y_test, xgb_pred, zero_division=0))
