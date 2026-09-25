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
    """Load a serialized preprocessor, rebuilding from train.csv if pickle version differs."""
    target = filepath or (MODEL_DIR / "preprocessor.joblib")
    if target.exists():
        try:
            prep = joblib.load(target)
            dummy_df = extract_features(pd.DataFrame([{}]))
            prep.transform(dummy_df)
            return prep
        except Exception:
            pass

    train_csv = BASE_DIR / "data" / "splits" / "train.csv"
    if not train_csv.exists():
        raise FileNotFoundError(f"Preprocessor not found at: {target}")
    train_df = pd.read_csv(train_csv)
    prep = build_preprocessor_pipeline()
    prep.fit(extract_features(train_df))
    try:
        save_preprocessor(prep, target)
    except Exception:
        pass
    return prep


class ClaimDataPreprocessor:
    """
    Fulfills Req 1.6.xvi: Data Pre-Processing.
    Cleans and prepares submitted claim data using Python:
    - Handling missing values
    - Converting date formats (into ISO strings and Python date objects)
    - Creating derived fields (product age, remaining warranty period, missing-document count, repairs count, flags)
    - Encoding categorical values
    - Normalizing numerical values via fitted ColumnTransformer
    """

    @staticmethod
    def clean_and_prepare(
        raw_claim_data: dict,
        product=None,
        documents: list = None
    ) -> dict:
        """
        Cleans and calculates all derived fields from raw claim input.
        """
        from datetime import date, datetime

        cleaned = dict(raw_claim_data)

        # 1. Date Format Conversion & Normalization
        sub_date = cleaned.get("claim_submission_date")
        if not sub_date:
            sub_date = date.today()
        elif isinstance(sub_date, str):
            try:
                sub_date = datetime.strptime(sub_date, "%Y-%m-%d").date()
            except Exception:
                sub_date = date.today()

        purch_date = None
        if product and getattr(product, "purchase_date", None):
            purch_date = product.purchase_date
        elif cleaned.get("purchase_date"):
            pd_val = cleaned.get("purchase_date")
            if isinstance(pd_val, str):
                try:
                    purch_date = datetime.strptime(pd_val, "%Y-%m-%d").date()
                except Exception:
                    purch_date = sub_date
            elif isinstance(pd_val, (date, datetime)):
                purch_date = pd_val.date() if isinstance(pd_val, datetime) else pd_val

        fault_date = None
        fd_val = cleaned.get("fault_occurrence_date")
        if isinstance(fd_val, str):
            try:
                fault_date = datetime.strptime(fd_val, "%Y-%m-%d").date()
            except Exception:
                fault_date = sub_date
        elif isinstance(fd_val, (date, datetime)):
            fault_date = fd_val.date() if isinstance(fd_val, datetime) else fd_val
        else:
            fault_date = sub_date

        # Standardize dates back to ISO strings
        cleaned["claim_submission_date"] = sub_date.strftime("%Y-%m-%d")
        cleaned["fault_occurrence_date"] = fault_date.strftime("%Y-%m-%d")
        if purch_date:
            cleaned["purchase_date"] = purch_date.strftime("%Y-%m-%d")

        # 2. Derived Field: Product Age in Days
        if purch_date:
            product_age_days = max(0, (sub_date - purch_date).days)
        else:
            product_age_days = int(cleaned.get("product_age_days", 0))
        cleaned["product_age_days"] = product_age_days

        # 3. Derived Field: Remaining Warranty Period in Days
        warr = product.warranty if product else None
        if warr and warr.expiry_date:
            rem_days = (warr.expiry_date - sub_date).days
            cleaned["warranty_expiry_date"] = warr.expiry_date.strftime("%Y-%m-%d")
            cleaned["is_extended_warranty"] = 1 if warr.is_extended else 0
            cleaned["warranty_duration_months"] = (
                warr.policy.coverage_duration_months if (warr.policy and hasattr(warr.policy, "coverage_duration_months")) else 12
            )
        elif cleaned.get("warranty_expiry_date"):
            try:
                exp_date = datetime.strptime(cleaned["warranty_expiry_date"], "%Y-%m-%d").date()
                rem_days = (exp_date - sub_date).days
            except Exception:
                rem_days = 0
        else:
            rem_days = int(cleaned.get("remaining_warranty_days", 0))
        cleaned["remaining_warranty_days"] = rem_days

        # 4. Derived Field: Missing-Document Count
        doc_types = set()
        if documents:
            for d in documents:
                dtype = getattr(d, "document_type", None) or (d.get("document_type") if isinstance(d, dict) else str(d))
                if dtype:
                    doc_types.add(dtype)

        has_receipt = 1 if (cleaned.get("has_receipt") or "receipt" in doc_types or "invoice_document" in doc_types) else 0
        has_warranty_card = 1 if (cleaned.get("has_warranty_card") or "warranty_card" in doc_types) else 0
        has_damage_photo = 1 if (cleaned.get("has_damage_photo") or "damage_photo" in doc_types or "product_photo" in doc_types) else 0
        has_serial_photo = 1 if (cleaned.get("has_serial_photo") or "serial_photo" in doc_types) else 0

        cleaned["has_receipt"] = has_receipt
        cleaned["has_warranty_card"] = has_warranty_card
        cleaned["has_damage_photo"] = has_damage_photo
        cleaned["has_serial_photo"] = has_serial_photo

        missing_count = 0
        if not has_receipt: missing_count += 1
        if not has_warranty_card: missing_count += 1
        if not has_damage_photo: missing_count += 1
        if not has_serial_photo: missing_count += 1
        cleaned["missing_document_count"] = missing_count

        # 5. Derived Field: Previous Repairs Count & Flags
        repair_records = getattr(product, "repair_records", []) if product else []
        cleaned["previous_repairs_count"] = len(repair_records)
        cleaned["unauthorized_repair_flag"] = 1 if any(not getattr(r, "is_authorized_center", True) for r in repair_records) else int(cleaned.get("unauthorized_repair_flag", 0))

        # 6. Derived Field: Claim Date Conflict Flag
        if purch_date and fault_date and fault_date < purch_date:
            cleaned["claim_date_conflict_flag"] = 1
        else:
            cleaned["claim_date_conflict_flag"] = int(cleaned.get("claim_date_conflict_flag", 0))

        # 7. Handling Missing Values for Numerical & Categorical Features
        if product:
            cleaned["purchase_price"] = float(product.purchase_price)
            raw_cat = str(product.category)
            cleaned["product_category"] = "Industrial Tools" if "industrial" in raw_cat.lower() else raw_cat
            cleaned["product_model"] = str(product.model_number)
            cleaned["product_serial"] = str(product.serial_number)
            cleaned["retailer"] = str(product.retailer)
        else:
            cleaned["purchase_price"] = float(cleaned.get("purchase_price", 0.0))
            raw_cat = str(cleaned.get("product_category", "Unknown"))
            cleaned["product_category"] = "Industrial Tools" if "industrial" in raw_cat.lower() else raw_cat

        cleaned["damage_type"] = str(cleaned.get("damage_type", "Unknown"))
        cleaned["fault_category"] = str(cleaned.get("fault_category", "Unknown"))
        cleaned["serial_number_match"] = int(cleaned.get("serial_number_match", 1))

        return cleaned

    @classmethod
    def transform_normalized(cls, cleaned_features: dict, preprocessor: ColumnTransformer = None) -> np.ndarray:
        """
        Encodes categorical values and normalizes numerical values
        using the fitted scikit-learn ColumnTransformer.
        """
        import pandas as pd
        df = pd.DataFrame([cleaned_features])
        df_feat = extract_features(df)
        if preprocessor is None:
            preprocessor = load_preprocessor()
        return preprocessor.transform(df_feat)

