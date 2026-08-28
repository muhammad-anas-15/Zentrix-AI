"""
Loads a saved model and reports detailed evaluation + SHAP feature
importance — helps identify noisy/low-value features to prune.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pickle
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from ml_model.dataset_builder import build_dataset

MODEL_DIR = os.path.join(os.path.dirname(__file__), "model_registry")


def load_model(symbol: str, interval: str):
    path = os.path.join(MODEL_DIR, f"{symbol}_{interval}_xgb.pkl")
    with open(path, "rb") as f:
        payload = pickle.load(f)
    return payload["model"], payload["feature_cols"]


def evaluate_model(symbol: str = "BTCUSDT", interval: str = "15m"):
    model, feature_cols = load_model(symbol, interval)
    df = build_dataset(symbol, interval).sort_values("time").reset_index(drop=True)

    # evaluate on most recent 15% as an unseen holdout
    split = int(len(df) * 0.85)
    test = df.iloc[split:]
    X_test, y_test = test[feature_cols], test["label"]

    preds = model.predict(X_test)
    print("Classification report:\n", classification_report(y_test, preds, zero_division=0))
    print("Confusion matrix:\n", confusion_matrix(y_test, preds))

    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_test)
        importance = pd.DataFrame({
            "feature": feature_cols,
            "mean_abs_shap": abs(shap_values).mean(axis=0)
        }).sort_values("mean_abs_shap", ascending=False)
        print("\nTop features by SHAP importance:\n", importance.head(10))
    except ImportError:
        print("\n(install 'shap' package for feature importance: pip install shap)")


if __name__ == "__main__":
    evaluate_model("BTCUSDT", "15m")