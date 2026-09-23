import joblib
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "model" / "python_model"

# Feature definitions for tabular ML model
NUMERICAL_FEATURES = [
    "purchase_price",
    "warranty_duration_months",
    "product_age_days",
    "remaining_warranty_days",
    "missing_document_count",
    "previous_repairs_count"
]

BINARY_FEATURES = [
    "is_extended_warranty",
    "has_receipt",
    "has_warranty_card",
    "has_damage_photo",
    "has_serial_photo",
    "has_repair_report",
    "serial_number_match",
    "unauthorized_repair_flag",
    "claim_date_conflict_flag"
]

CATEGORICAL_FEATURES = [
    "product_category",
    "damage_type"
]

ALL_INPUT_FEATURES = NUMERICAL_FEATURES + BINARY_FEATURES + CATEGORICAL_FEATURES
TARGET_COLUMN = "claim_class"


def build_preprocessor_pipeline() -> ColumnTransformer:
    """Constructs a robust scikit-learn preprocessing ColumnTransformer."""
    num_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler())
    ])

    bin_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent"))
    ])

    cat_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False))
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", num_pipeline, NUMERICAL_FEATURES),
            ("bin", bin_pipeline, BINARY_FEATURES),
            ("cat", cat_pipeline, CATEGORICAL_FEATURES)
        ],
        remainder="drop"
    )
    return preprocessor


def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Ensures all expected feature columns are present and typed correctly."""
    df_clean = df.copy()
    for col in NUMERICAL_FEATURES:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce").fillna(0.0)
        else:
            df_clean[col] = 0.0

    for col in BINARY_FEATURES:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce").fillna(0).astype(int)
        else:
            df_clean[col] = 0

    for col in CATEGORICAL_FEATURES:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].astype(str).fillna("Unknown")
        else:
            df_clean[col] = "Unknown"

    return df_clean[ALL_INPUT_FEATURES]


def save_preprocessor(preprocessor, filepath: Path = None):
    """Serialize the fitted preprocessor."""
    target = filepath or (MODEL_DIR / "preprocessor.joblib")
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(preprocessor, target)
    print(f"   [+] Preprocessor serialized to: {target}")


def load_preprocessor(filepath: Path = None) -> ColumnTransformer:
    """Load a serialized preprocessor."""
    target = filepath or (MODEL_DIR / "preprocessor.joblib")
    if not target.exists():
        raise FileNotFoundError(f"Preprocessor not found at: {target}")
    return joblib.load(target)
