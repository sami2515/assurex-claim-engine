from pathlib import Path
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from config.config import Config
from src.core.preprocessor import (
    extract_features, build_preprocessor_pipeline, TARGET_COLUMN
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "model" / "python_model"


class PythonClaimClassifier:
    """Production Python ML Classifier for warranty claim adjudication."""

    def __init__(self, model_path: Path = None, preprocessor_path: Path = None):
        self.model_path = model_path or (MODEL_DIR / "best_model.joblib")
        self.preprocessor_path = preprocessor_path or (MODEL_DIR / "preprocessor.joblib")
        self.model_version = Config.PYTHON_MODEL_VERSION

        loaded_ok = False
        if self.model_path.exists() and self.preprocessor_path.exists():
            try:
                self.model = joblib.load(self.model_path)
                self.preprocessor = joblib.load(self.preprocessor_path)
                self.classes = list(self.model.classes_)
                dummy_X = self.preprocessor.transform(extract_features(pd.DataFrame([{}])))
                self.model.predict_proba(dummy_X)
                loaded_ok = True
            except Exception:
                loaded_ok = False

        if not loaded_ok:
            self._rebuild_native_artifacts()

    def _rebuild_native_artifacts(self):
        """Compiles preprocessor and model natively on the current Python/NumPy/scikit-learn runtime."""
        train_csv = BASE_DIR / "data" / "splits" / "train.csv"
        if not train_csv.exists():
            raise FileNotFoundError(
                "Model or preprocessor artifact missing. Ensure training has been executed."
            )
        train_df = pd.read_csv(train_csv)
        X_train_raw = extract_features(train_df)
        y_train = train_df[TARGET_COLUMN].values

        self.preprocessor = build_preprocessor_pipeline()
        X_train = self.preprocessor.fit_transform(X_train_raw)

        self.model = HistGradientBoostingClassifier(
            max_iter=160,
            learning_rate=0.08,
            max_depth=8,
            min_samples_leaf=5,
            random_state=42
        )
        self.model.fit(X_train, y_train)
        self.classes = list(self.model.classes_)

        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self.preprocessor, self.preprocessor_path)
            joblib.dump(self.model, self.model_path)
        except Exception:
            pass

    def predict_single(self, claim_data: dict) -> dict:
        """
        Takes raw claim dictionary, preprocesses features, and produces
        the predicted class alongside confidence scores for all 3 classes.
        """
        df = pd.DataFrame([claim_data])
        X_raw = extract_features(df)
        X_proc = self.preprocessor.transform(X_raw)

        probs = self.model.predict_proba(X_proc)[0]
        pred_idx = int(np.argmax(probs))
        predicted_class = self.classes[pred_idx]

        confidence_map = {
            cls_name: round(float(prob), 4)
            for cls_name, prob in zip(self.classes, probs)
        }

        # Ensure all 3 SRS classes exist in output
        for req_cls in Config.ALL_CLAIM_CLASSES:
            if req_cls not in confidence_map:
                confidence_map[req_cls] = 0.0

        return {
            "model_type": "Python_ML_Tabular",
            "model_version": self.model_version,
            "predicted_class": predicted_class,
            "top_confidence": round(float(probs[pred_idx]), 4),
            "confidence_scores": confidence_map
        }


# Singleton helper instance
_classifier_instance = None

def get_python_classifier() -> PythonClaimClassifier:
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = PythonClaimClassifier()
    return _classifier_instance
