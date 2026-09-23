from config.config import Config
from src.core.model_comparator import get_model_comparator
from src.rules.policy_engine import get_policy_engine
from src.rules.contradiction_detector import get_contradiction_detector
from src.rules.duplicate_detector import get_duplicate_detector


class MasterDecisionEngine:
    """
    Master Claim Adjudication Engine (SRS Step 12, Req xxxiv & Req xxxv).
    Synthesizes Dual-Model Consensus, Warranty Policies, Contradiction Checks,
    and Duplicate Indicators into a finalized 3-class decision with full explanation.
    """

    def __init__(self):
        self.comparator = get_model_comparator()
        self.policy_engine = get_policy_engine()
        self.contradiction_detector = get_contradiction_detector()
        self.duplicate_detector = get_duplicate_detector()

    def adjudicate_claim(self, claim_data: dict, summary_card_image=None, ocr_data: dict = None, current_claim_internal_id: int = None) -> dict:
        """
        Executes end-to-end multi-layer claim evaluation.
        
        Outputs one of three SRS Final Decisions:
        - 'Likely Valid'
        - 'Likely Invalid'
        - 'Manual Review Required'
        """
        # Layer 1: Dual-Model Consensus
        model_results = self.comparator.compare_models(claim_data, summary_card_image=summary_card_image)
        py_pred = model_results["python_model"]["predicted_class"]
        py_conf = model_results["python_model"]["top_confidence"]
        gtm_pred = model_results["gtm_model"]["predicted_class"]
        gtm_conf = model_results["gtm_model"]["top_confidence"]
        consistency_status = model_results["model_consistency_status"]
        is_class_match = model_results["is_class_match"]

        # Layer 2: Warranty Policy Rules
        rule_results = self.policy_engine.evaluate_claim_rules(claim_data)
        rule_status = rule_results["overall_status"]  # PASS, FAIL, REVIEW
        failed_rules = rule_results["failed_rules"]
        passed_rules = rule_results["passed_rules"]
        warnings = rule_results["warnings"]
        manual_triggers = rule_results["manual_review_triggers"]

        # Layer 3: Contradiction Detection
        contradiction_results = self.contradiction_detector.detect_contradictions(claim_data, ocr_data=ocr_data)
        has_contradictions = contradiction_results["has_contradiction"]
        contradiction_list = contradiction_results["contradictions"]

        # Layer 4: Duplicate Claim & Document Detection
        duplicate_results = self.duplicate_detector.check_claim_duplicates(
            claim_data, current_claim_internal_id=current_claim_internal_id
        )
        is_duplicate = duplicate_results["is_duplicate"]
        duplicate_flags = duplicate_results["duplicate_flags"]

        # -------------------------------------------------------------
        # Layer 5: Master Decision Synthesis Matrix
        # -------------------------------------------------------------
        supporting_factors = []
        opposing_factors = []
        corrective_actions = []

        # Decision Branching
        if len(failed_rules) > 0:
            final_decision = "Likely Invalid"
            decision_summary = f"Claim rejected due to policy violations: {failed_rules[0]}"
            opposing_factors.extend(failed_rules)
            risk_level = "High"

        elif has_contradictions:
            final_decision = "Manual Review Required"
            decision_summary = f"Chronological or serial contradiction detected: {contradiction_list[0]}"
            opposing_factors.extend(contradiction_list)
            corrective_actions.append("Reviewer must verify customer receipt dates and hardware serial stamp.")
            risk_level = "High"

        elif is_duplicate:
            final_decision = "Manual Review Required"
            decision_summary = f"Potential duplicate claim detected: {duplicate_flags[0]}"
            opposing_factors.extend(duplicate_flags)
            corrective_actions.append("Investigate potential duplicate submission across claimant accounts.")
            risk_level = "High"

        elif consistency_status == Config.CONSISTENCY_DISAGREEMENT:
            final_decision = "Manual Review Required"
            decision_summary = f"Dual-model divergence: Python model predicted '{py_pred}' while Teachable Machine predicted '{gtm_pred}'."
            opposing_factors.append(model_results["explanation"])
            corrective_actions.append("Senior claim reviewer inspection required to reconcile conflicting AI model predictions.")
            risk_level = "Medium"

        elif consistency_status == Config.CONSISTENCY_UNCERTAIN:
            final_decision = "Manual Review Required"
            decision_summary = f"Model confidence is below minimum operating threshold ({Config.MIN_CONFIDENCE_THRESHOLD:.2f})."
            opposing_factors.append(model_results["explanation"])
            corrective_actions.append("Manual evidence verification required due to low model confidence.")
            risk_level = "Medium"

        elif len(manual_triggers) > 0:
            final_decision = "Manual Review Required"
            decision_summary = f"Policy review trigger active: {manual_triggers[0]}"
            opposing_factors.extend(manual_triggers)
            corrective_actions.append("Adjudicate discretionary policy exception (e.g. grace period or missing proof of purchase).")
            risk_level = "Medium"

        elif is_class_match and py_pred == Config.CLAIM_CLASS_INVALID:
            final_decision = "Likely Invalid"
            decision_summary = "Both AI models and warranty inspection independently conclude claim is invalid."
            opposing_factors.append(f"AI models unanimously predicted Invalid Claim (Python: {py_conf:.2f}, GTM: {gtm_conf:.2f}).")
            risk_level = "High"

        elif is_class_match and py_pred == Config.CLAIM_CLASS_MANUAL_REVIEW:
            final_decision = "Manual Review Required"
            decision_summary = "Both AI models flagged claim as requiring manual human review."
            opposing_factors.append(f"AI models unanimously recommended Manual Review (Python: {py_conf:.2f}, GTM: {gtm_conf:.2f}).")
            corrective_actions.append("Reviewer adjudication required.")
            risk_level = "Medium"

        elif is_class_match and py_pred == Config.CLAIM_CLASS_VALID and rule_status == "PASS":
            final_decision = "Likely Valid"
            decision_summary = "All warranty conditions satisfied, serial verified, and both AI models unanimously approve claim."
            supporting_factors.append(f"Dual AI models unanimously predicted Valid Claim (Python: {py_conf:.2f}, GTM: {gtm_conf:.2f}).")
            supporting_factors.append(f"Model consistency status verified as '{consistency_status}'.")
            supporting_factors.extend(passed_rules[:3])
            risk_level = "Low"

        else:
            final_decision = "Manual Review Required"
            decision_summary = "Claim routed to manual review queue based on combined risk matrix."
            corrective_actions.append("Reviewer triage required.")
            risk_level = "Medium"

        # Construct comprehensive explanation factor report (Req xxxv)
        explanation_report = {
            "final_decision": final_decision,
            "decision_summary": decision_summary,
            "risk_level": risk_level,
            "supporting_factors": supporting_factors,
            "opposing_factors": opposing_factors,
            "passed_rules": passed_rules,
            "failed_rules": failed_rules,
            "warnings": warnings,
            "contradictions": contradiction_list,
            "duplicate_flags": duplicate_flags,
            "corrective_actions": corrective_actions,
            "dual_model_evaluation": model_results,
            "rule_evaluation": rule_results
        }

        return explanation_report


# Singleton master decision engine instance
_decision_engine_instance = None

def get_decision_engine() -> MasterDecisionEngine:
    global _decision_engine_instance
    if _decision_engine_instance is None:
        _decision_engine_instance = MasterDecisionEngine()
    return _decision_engine_instance
