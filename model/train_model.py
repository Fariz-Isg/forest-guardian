"""Train a lightweight logistic regression fire-risk model on the spatially
binned FIRMS + Open-Meteo dataset (model/spatial_training_data.csv) — one row
per (grid cell, day), labeled by whether a fire was detected in that cell that
day, with that cell's own weather as features. Exported as plain JSON weights
so the frontend can run inference with a single dot product + sigmoid, no ML
runtime required in the browser.
"""
import csv
import json
import os

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

HERE = os.path.dirname(__file__)
FEATURES = ["temp_max", "temp_min", "wind_max", "precip_sum", "humidity_mean"]

rows = list(csv.DictReader(open(os.path.join(HERE, "spatial_training_data.csv"))))
X = np.array([[float(r[f]) for f in FEATURES] for r in rows])
y = np.array([int(r["fire_detected"]) for r in rows])

mean = X.mean(axis=0)
std = X.std(axis=0)
std[std == 0] = 1.0
Xn = (X - mean) / std

X_train, X_test, y_train, y_test = train_test_split(
    Xn, y, test_size=0.2, random_state=42, stratify=y
)

model = LogisticRegression(class_weight="balanced")
model.fit(X_train, y_train)

train_auc = roc_auc_score(y_train, model.predict_proba(X_train)[:, 1])
test_auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
print(f"Train AUC: {train_auc:.3f}  Test AUC: {test_auc:.3f}")
print(f"Base rate (fire cell-days / total): {y.mean():.3f}")
print("Coefficients:", dict(zip(FEATURES, model.coef_[0].round(3))))
print("Intercept:", round(model.intercept_[0], 3))

weights = {
    "features": FEATURES,
    "mean": mean.tolist(),
    "std": std.tolist(),
    "coef": model.coef_[0].tolist(),
    "intercept": float(model.intercept_[0]),
    "trained_on": {
        "rows": len(rows),
        "positive_rows": int(y.sum()),
        "grid": "12x12 cells over the California bbox, land-masked",
        "test_auc": round(test_auc, 3),
    },
    "notes": (
        "Logistic regression trained on (grid cell, day) pairs: was a VIIRS "
        "fire detected in that specific cell that day, given that cell's own "
        "weather (temp, wind, precipitation, humidity) that day. This gives "
        "genuine spatial contrast, unlike a whole-region daily aggregate. At "
        "inference time the same model is evaluated against each map grid "
        "point's live forecast weather."
    ),
}

out_path = os.path.join(HERE, "fire_risk_model.json")
with open(out_path, "w") as f:
    json.dump(weights, f, indent=2)
print(f"Wrote model weights to {out_path}")
