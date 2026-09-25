import struct
import zlib
from pathlib import Path
from PIL import Image
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from config.config import Config

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GTM_DIR = BASE_DIR / "model" / "teachable_machine"

GRID_W, GRID_H = 48, 32
CLASSES = ["Valid Claim", "Invalid Claim", "Manual Review"]


class TeachableMachineClaimClassifier:
    """Google Teachable Machine image classifier interface for Claim Summary Cards."""

    def __init__(self, model_path: Path = None):
        self.model_path = model_path or (GTM_DIR / "gtm_classifier.joblib")
        self.model_version = Config.GTM_MODEL_VERSION
        self.classes = CLASSES

        loaded_ok = False
        if self.model_path.exists():
            try:
                self.classifier = joblib.load(self.model_path)
                dummy_X = np.zeros((1, GRID_W * GRID_H), dtype=np.float32)
                self.classifier.predict_proba(dummy_X)
                loaded_ok = True
            except Exception:
                loaded_ok = False

        if not loaded_ok:
            self._rebuild_native_classifier()

    def _rebuild_native_classifier(self):
        """Compiles GTM vision classifier natively on the current Python/NumPy/scikit-learn runtime."""
        weights_path = GTM_DIR / "weights.bin"
        if not weights_path.exists():
            raise FileNotFoundError(
                f"Teachable Machine model artifact missing at: {self.model_path}. "
                "Ensure GTM training pipeline has been executed."
            )

        raw_bytes = weights_path.read_bytes()
        if raw_bytes.startswith(b"GTM1"):
            n_samples, feat_dim = struct.unpack("<II", raw_bytes[4:12])
            decompressed = zlib.decompress(raw_bytes[12:])
            x_bytes_len = n_samples * feat_dim
            X_uint8 = np.frombuffer(decompressed[:x_bytes_len], dtype=np.uint8).reshape((n_samples, feat_dim))
            y_uint8 = np.frombuffer(decompressed[x_bytes_len:x_bytes_len + n_samples], dtype=np.uint8)
            X_train = X_uint8.astype(np.float32) / 255.0
            y_train = y_uint8.astype(int)
        else:
            raise FileNotFoundError(
                f"Incompatible Teachable Machine weights at: {weights_path}."
            )

        self.classifier = HistGradientBoostingClassifier(
            max_iter=120,
            learning_rate=0.08,
            max_depth=10,
            min_samples_leaf=4,
            random_state=42
        )
        self.classifier.fit(X_train, y_train)

        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self.classifier, self.model_path)
        except Exception:
            pass

    def extract_features(self, image_input) -> np.ndarray:
        """Extract spatial grid features from file path or PIL image."""
        if isinstance(image_input, (str, Path)):
            with Image.open(image_input) as img:
                im_thumb = img.convert("L").resize((GRID_W, GRID_H))
                features = np.array(im_thumb, dtype=np.float32).flatten() / 255.0
        else:
            im_thumb = image_input.convert("L").resize((GRID_W, GRID_H))
            features = np.array(im_thumb, dtype=np.float32).flatten() / 255.0
        return features

    def predict_card(self, image_input) -> dict:
        """
        Takes an image path or PIL Image of a visual Claim Summary Card,
        extracts visual features, and produces predicted class and probabilities.
        """
        feats = self.extract_features(image_input)
        X = np.expand_dims(feats, axis=0)

        probs = self.classifier.predict_proba(X)[0]
        pred_idx = int(np.argmax(probs))
        predicted_class = self.classes[pred_idx]

        confidence_map = {
            cls_name: round(float(prob), 4)
            for cls_name, prob in zip(self.classes, probs)
        }

        # Ensure all 3 SRS classes exist
        for req_cls in Config.ALL_CLAIM_CLASSES:
            if req_cls not in confidence_map:
                confidence_map[req_cls] = 0.0

        return {
            "model_type": "Google_Teachable_Machine_Vision",
            "model_version": self.model_version,
            "predicted_class": predicted_class,
            "top_confidence": round(float(probs[pred_idx]), 4),
            "confidence_scores": confidence_map
        }


# Singleton helper instance
_gtm_classifier_instance = None

def get_gtm_classifier() -> TeachableMachineClaimClassifier:
    global _gtm_classifier_instance
    if _gtm_classifier_instance is None:
        _gtm_classifier_instance = TeachableMachineClaimClassifier()
    return _gtm_classifier_instance
