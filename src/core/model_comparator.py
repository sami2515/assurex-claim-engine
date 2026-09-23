from config.config import Config
from src.core.python_classifier import get_python_classifier
from src.core.teachable_machine_classifier import get_gtm_classifier
from src.core.card_generator import render_claim_summary_card


class DualModelComparator:
    """
    Orchestrates the Dual-Model Consensus Architecture according to SRS Step 10.
    Compares the Python Tabular Classifier with the Google Teachable Machine Vision Model.
    """

    def __init__(self, min_conf: float = None, strong_diff: float = None, acceptable_diff: float = None):
        # Load configurable thresholds from Config (or override dynamically)
        self.min_confidence = min_conf if min_conf is not None else Config.MIN_CONFIDENCE_THRESHOLD
        self.strong_diff = strong_diff if strong_diff is not None else Config.STRONG_MATCH_DIFF
        self.acceptable_diff = acceptable_diff if acceptable_diff is not None else Config.ACCEPTABLE_MATCH_DIFF

        self.python_classifier = get_python_classifier()
        self.gtm_classifier = get_gtm_classifier()

    def compare_models(self, claim_data: dict, summary_card_image=None) -> dict:
        """
        Runs both models on the claim evidence and computes the consensus matrix.
        
        Args:
            claim_data: Dictionary containing raw and preprocessed claim features.
            summary_card_image: Optional PIL Image or path to existing Claim Summary Card.
                                If None, generates the card dynamically from claim_data.
        Returns:
            dict containing python_result, gtm_result, match_status, confidence_diff,
            model_consistency_status, and explanation.
        """
        # 1. Run Python Tabular Classifier
        py_result = self.python_classifier.predict_single(claim_data)
        py_pred_class = py_result["predicted_class"]
        py_top_conf = py_result["top_confidence"]

        # 2. Obtain / Render Claim Summary Card and run GTM Vision Classifier
        if summary_card_image is None:
            summary_card_image = render_claim_summary_card(claim_data, variation=1)

        gtm_result = self.gtm_classifier.predict_card(summary_card_image)
        gtm_pred_class = gtm_result["predicted_class"]
        gtm_top_conf = gtm_result["top_confidence"]

        # 3. Class Match Evaluation
        is_class_match = bool(py_pred_class == gtm_pred_class)

        # 4. Confidence Difference: |Python Top Conf - GTM Top Conf|
        confidence_diff = round(abs(py_top_conf - gtm_top_conf), 4)

        # 5. Evaluate Formal Consistency Status from Decision Matrix
        if (py_top_conf < self.min_confidence) or (gtm_top_conf < self.min_confidence):
            consistency_status = Config.CONSISTENCY_UNCERTAIN
            explanation = (
                f"Confidence is below minimum threshold ({self.min_confidence:.2f}). "
                f"Python Top: {py_top_conf:.4f}, GTM Top: {gtm_top_conf:.4f}."
            )
        elif not is_class_match:
            consistency_status = Config.CONSISTENCY_DISAGREEMENT
            explanation = (
                f"Model divergence detected: Python model predicted '{py_pred_class}' "
                f"while Google Teachable Machine predicted '{gtm_pred_class}'."
            )
        elif confidence_diff <= self.strong_diff:
            consistency_status = Config.CONSISTENCY_STRONG
            explanation = (
                f"Both models unanimously predicted '{py_pred_class}' with low confidence "
                f"differential ({confidence_diff:.4f} <= {self.strong_diff:.2f})."
            )
        elif confidence_diff <= self.acceptable_diff:
            consistency_status = Config.CONSISTENCY_ACCEPTABLE
            explanation = (
                f"Both models predicted '{py_pred_class}' with acceptable confidence "
                f"differential ({confidence_diff:.4f} <= {self.acceptable_diff:.2f})."
            )
        else:
            consistency_status = Config.CONSISTENCY_WEAK
            explanation = (
                f"Both models predicted '{py_pred_class}' but with high confidence "
                f"divergence ({confidence_diff:.4f} > {self.acceptable_diff:.2f})."
            )

        return {
            "is_class_match": is_class_match,
            "top_confidence_difference": confidence_diff,
            "model_consistency_status": consistency_status,
            "explanation": explanation,
            "python_model": py_result,
            "gtm_model": gtm_result,
            "thresholds_used": {
                "min_confidence": self.min_confidence,
                "strong_diff": self.strong_diff,
                "acceptable_diff": self.acceptable_diff
            }
        }


# Singleton comparator
_comparator_instance = None

def get_model_comparator() -> DualModelComparator:
    global _comparator_instance
    if _comparator_instance is None:
        _comparator_instance = DualModelComparator()
    return _comparator_instance
