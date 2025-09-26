"""
Run:
  cd modeling
  pip install -r requirements.txt
  python train_models.py --csv ../data/melbourne_housing.csv
"""
import argparse, os, json, math, joblib, warnings
from pathlib import Path
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.svm import SVR

warnings.filterwarnings("ignore")

def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    if "sold_price" not in df.columns:
        raise ValueError("CSV must contain a 'sold_price' column as the target.")
    df = df[~df["sold_price"].isna()]
    numeric_like = ["bedrooms","bathrooms","car_spaces","land_size_sqm","building_size_sqm",
                    "latitude","longitude","year_built","nearby_schools_count","distance_to_cbd_km",
                    "lot_frontage_m","sold_price"]
    for col in df.columns:
        if col in numeric_like:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "sale_date" in df.columns:
        df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
        df["sale_year"] = df["sale_date"].dt.year
        df["sale_month"] = df["sale_date"].dt.month
    else:
        df["sale_year"] = np.nan
        df["sale_month"] = np.nan
    return df

def build_features(df: pd.DataFrame):
    cat_cols = [c for c in ["suburb","property_type","postcode","agency","has_garage","has_aircon","has_heating"] if c in df.columns]
    num_cols = [c for c in [
        "bedrooms","bathrooms","car_spaces","land_size_sqm","building_size_sqm",
        "latitude","longitude","year_built","nearby_schools_count","distance_to_cbd_km",
        "lot_frontage_m","sale_year","sale_month"
    ] if c in df.columns]
    X = df[cat_cols + num_cols].copy()
    y = df["sold_price"].copy()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
            ("num", StandardScaler(), num_cols),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return X_train, X_test, y_train, y_test, preprocessor, cat_cols, num_cols

def eval_model(name, pipeline, X_train, y_train, X_test, y_test, k=5):
    kf = KFold(n_splits=k, shuffle=True, random_state=42)
    import math
    mae_cv = -cross_val_score(pipeline, X_train, y_train, cv=kf, scoring="neg_mean_absolute_error").mean()
    rmse_cv = math.sqrt(-cross_val_score(pipeline, X_train, y_train, cv=kf, scoring="neg_mean_squared_error").mean())
    r2_cv = cross_val_score(pipeline, X_train, y_train, cv=kf, scoring="r2").mean()
    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    rmse = math.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)
    return {
        "model": name,
        "mae_cv": round(mae_cv, 2),
        "rmse_cv": round(rmse_cv, 2),
        "r2_cv": round(r2_cv, 4),
        "mae_test": round(mae, 2),
        "rmse_test": round(rmse, 2),
        "r2_test": round(r2, 4),
    }, pipeline

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default=str(Path(__file__).resolve().parents[1] / "data" / "melbourne_housing.csv"))
    args = parser.parse_args()
    csv_path = Path(args.csv)
    out_dir = Path(__file__).resolve().parent / "outputs"
    (out_dir / "eda").mkdir(parents=True, exist_ok=True)
    df = load_data(csv_path)
    # EDA plots
    if "sold_price" in df.columns:
        plt.figure(); df["sold_price"].dropna().plot(kind="hist", bins=50, edgecolor="black")
        plt.title("Sold Price Distribution"); plt.xlabel("Price"); plt.ylabel("Count"); plt.tight_layout()
        plt.savefig(out_dir / "eda" / "price_distribution.png"); plt.close()
    num_df = df.select_dtypes(include=[float, int])
    if num_df.shape[1] > 1:
        corr = num_df.corr(numeric_only=True)
        plt.figure(); plt.imshow(corr, interpolation="nearest"); plt.title("Correlation Heatmap (numeric)")
        plt.xticks(range(corr.shape[1]), corr.columns, rotation=90); plt.yticks(range(corr.shape[0]), corr.index)
        plt.colorbar(); plt.tight_layout(); plt.savefig(out_dir / "eda" / "correlation_heatmap.png"); plt.close()
    X_train, X_test, y_train, y_test, preprocessor, cat_cols, num_cols = build_features(df)
    results = []
    # Linear Regression
    from sklearn.linear_model import LinearRegression
    lr_pipe = Pipeline(steps=[("prep", preprocessor), ("model", LinearRegression())])
    res_lr, _ = eval_model("LinearRegression", lr_pipe, X_train, y_train, X_test, y_test); results.append(res_lr)
    # Random Forest
    from sklearn.ensemble import RandomForestRegressor
    rf = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1)
    rf_pipe = Pipeline(steps=[("prep", preprocessor), ("model", rf)])
    res_rf, rf_fitted = eval_model("RandomForest", rf_pipe, X_train, y_train, X_test, y_test); results.append(res_rf)
    # SVR
    from sklearn.svm import SVR
    svr = SVR(C=10.0, epsilon=0.2, kernel="rbf")
    svr_pipe = Pipeline(steps=[("prep", preprocessor), ("model", svr)])
    res_svr, _ = eval_model("SVR_rbf", svr_pipe, X_train, y_train, X_test, y_test); results.append(res_svr)
    compare_df = pd.DataFrame(results).sort_values(by="rmse_test")
    compare_df.to_csv(out_dir / "model_compare.csv", index=False)
    best_name = compare_df.iloc[0]["model"]
    X_all = pd.concat([X_train, X_test], axis=0); y_all = pd.concat([y_train, y_test], axis=0)
    final_model = rf_pipe if best_name=="RandomForest" else (svr_pipe if best_name=="SVR_rbf" else lr_pipe)
    final_model.fit(X_all, y_all)
    import joblib; joblib.dump(final_model, out_dir / "pipeline.pkl")
    # Optional: feature importance for tree
    try:
        ohe = final_model.named_steps["prep"].named_transformers_["cat"]
        cat_features = list(ohe.get_feature_names_out(final_model.named_steps["prep"].transformers_[0][2]))
        num_features = final_model.named_steps["prep"].transformers_[1][2]
        feat_names = cat_features + num_features
        model = final_model.named_steps["model"]
        if hasattr(model, "feature_importances_"):
            importances = pd.Series(model.feature_importances_, index=feat_names).sort_values(ascending=False)
            importances.to_csv(out_dir / "feature_importance.csv")
    except Exception as e:
        print("Feature importance skipped:", e)
    summary = {"best_model": str(best_name), "results": results, "csv_used": str(csv_path), "features_used": {"categorical": cat_cols, "numeric": num_cols}}
    with open(out_dir / "metrics.json", "w") as f: json.dump(summary, f, indent=2)
    print("Done. Outputs in:", out_dir)

if __name__ == "__main__":
    main()
