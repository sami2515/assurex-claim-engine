import json
from datetime import date
from typing import Any, List, Dict, Optional
from config.config import Config
from src.core.model_comparator import get_model_comparator
from src.rules.policy_engine import get_policy_engine
from src.rules.contradiction_detector import get_contradiction_detector
from src.rules.duplicate_detector import get_duplicate_detector
from src.rules.validator import ClaimValidator


class MasterDecisionEngine:
    """
    Master Claim Adjudication & Executive Intelligence Engine.
    Fulfills:
    - Req 1.6.xxxii: AI-Generated Claim Summary (structured synthesis of product, warranty,
      reported fault, repair history, uploaded evidence, detected issues, and claim status).
    - Req 1.6.xxxiv: Final Claim Decision (synthesizing Python model, Teachable Machine model,
      confidence difference, warranty rules, missing documents, duplicate indicators, and contradictions
      into 'Likely Valid', 'Likely Invalid', or 'Manual Review Required').
    - Req 1.6.xxxv: Explanation Factor Generation.
    """

    def __init__(self):
        self._comparator = None
        self._policy_engine = None
        self._contradiction_detector = None
        self._duplicate_detector = None

    @property
    def comparator(self):
        if self._comparator is None:
            self._comparator = get_model_comparator()
        return self._comparator

    @property
    def policy_engine(self):
        if self._policy_engine is None:
            self._policy_engine = get_policy_engine()
        return self._policy_engine

    @property
    def contradiction_detector(self):
        if self._contradiction_detector is None:
            self._contradiction_detector = get_contradiction_detector()
        return self._contradiction_detector

    @property
    def duplicate_detector(self):
        if self._duplicate_detector is None:
            self._duplicate_detector = get_duplicate_detector()
        return self._duplicate_detector

    @classmethod
    def synthesize_final_decision(
        cls,
        model_results: dict,
        rule_results: dict,
        contradiction_list: list = None,
        duplicate_flags: list = None,
        missing_documents: Any = False
    ) -> dict:
        """
        Req 1.6.xxxiv: Synthesizes final decision considering all 7 factors:
        1. Python model prediction
        2. Google Teachable Machine prediction
        3. Confidence-score difference
        4. Warranty rules
        5. Missing documents
        6. Duplicate indicators
        7. Contradictions

        Outputs strictly one of: 'Likely Valid', 'Likely Invalid', 'Manual Review Required'.
        """
        contradiction_list = contradiction_list or []
        duplicate_flags = duplicate_flags or []
        if isinstance(missing_documents, (list, tuple, set)):
            has_missing_documents = len(missing_documents) > 0
        else:
            has_missing_documents = bool(missing_documents)

        # Factor 1, 2, 3
        py_model = model_results.get("python_model", {})
        gtm_model = model_results.get("gtm_model", {})
        consensus = model_results.get("consensus", {})

        py_pred = py_model.get("predicted_class", Config.CLAIM_CLASS_MANUAL_REVIEW)
        py_conf = py_model.get("top_confidence", 0.0)
        gtm_pred = gtm_model.get("predicted_class", Config.CLAIM_CLASS_MANUAL_REVIEW)
        gtm_conf = gtm_model.get("top_confidence", 0.0)
        conf_difference = consensus.get("top_confidence_difference", abs(py_conf - gtm_conf))
        consistency_status = consensus.get("model_consistency_status", "Model Disagreement" if py_pred != gtm_pred else "Strong Match")
        is_class_match = consensus.get("is_class_match", py_pred == gtm_pred)

        # Factor 4
        rule_status = rule_results.get("overall_status", "PASS")
        failed_rules = rule_results.get("failed_rules", [])
        passed_rules = rule_results.get("passed_rules", [])
        warnings = rule_results.get("warnings", [])
        manual_triggers = rule_results.get("manual_review_triggers", [])

        # -------------------------------------------------------------
        # Decision Synthesis Matrix (Req xxxiv)
        # -------------------------------------------------------------
        supporting_factors = []
        opposing_factors = []
        corrective_actions = []

        if len(failed_rules) > 0:
            final_decision = "Likely Invalid"
            decision_summary = f"Claim rejected due to policy violations: {failed_rules[0]}"
            opposing_factors.extend(failed_rules)
            risk_level = "High"

        elif len(contradiction_list) > 0:
            final_decision = "Manual Review Required"
            decision_summary = f"Chronological or serial contradiction detected: {contradiction_list[0]}"
            opposing_factors.extend(contradiction_list)
            corrective_actions.append("Reviewer must verify customer receipt dates and hardware serial stamp.")
            risk_level = "High"

        elif len(duplicate_flags) > 0:
            final_decision = "Manual Review Required"
            decision_summary = f"Potential duplicate claim detected: {duplicate_flags[0]}"
            opposing_factors.extend(duplicate_flags)
            corrective_actions.append("Investigate potential duplicate submission across claimant accounts.")
            risk_level = "High"

        elif has_missing_documents and (is_class_match and py_pred == Config.CLAIM_CLASS_INVALID):
            final_decision = "Likely Invalid"
            decision_summary = "AI models and evidence inspection conclude claim is invalid with missing mandatory proof."
            opposing_factors.append("Supporting documentation incomplete and AI models indicate invalidity.")
            risk_level = "High"

        elif has_missing_documents:
            final_decision = "Manual Review Required"
            decision_summary = "Mandatory documentation missing: Claim routed for customer evidence upload and human verification."
            opposing_factors.append("Required proof of purchase or failure evidence missing.")
            corrective_actions.append("Request claimant to upload missing mandatory documents.")
            risk_level = "Medium"

        elif consistency_status == Config.CONSISTENCY_DISAGREEMENT or (not is_class_match):
            final_decision = "Manual Review Required"
            decision_summary = f"Dual-model divergence: Python model predicted '{py_pred}' while Teachable Machine predicted '{gtm_pred}' (Diff: {conf_difference:.4f})."
            opposing_factors.append(model_results.get("explanation", "Disagreement between Python and Teachable Machine classifiers."))
            corrective_actions.append("Senior claim reviewer inspection required to reconcile conflicting AI model predictions.")
            risk_level = "Medium"

        elif consistency_status == Config.CONSISTENCY_UNCERTAIN:
            final_decision = "Manual Review Required"
            decision_summary = f"Model confidence is below minimum operating threshold ({Config.MIN_CONFIDENCE_THRESHOLD:.2f})."
            opposing_factors.append(model_results.get("explanation", "Model confidence score below configured threshold."))
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

        elif is_class_match and py_pred == Config.CLAIM_CLASS_VALID and rule_status == "PASS" and not has_missing_documents:
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
        return {
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
            "has_missing_documents": has_missing_documents,
            "corrective_actions": corrective_actions,
            "dual_model_evaluation": model_results,
            "rule_evaluation": rule_results
        }

    @classmethod
    def adjudicate_claim(
        cls,
        claim_data: dict = None,
        summary_card_image=None,
        ocr_data: dict = None,
        current_claim_internal_id: int = None,
        **kwargs
    ) -> dict:
        """
        Req 1.6.xxxiv: Executes multi-layer claim evaluation considering all 7 parameters:
        1. Python model prediction
        2. Google Teachable Machine prediction
        3. Confidence-score difference
        4. Warranty rules
        5. Missing documents
        6. Duplicate indicators
        7. Contradictions

        Outputs strictly one of the 3 SRS Final Decisions:
        - 'Likely Valid'
        - 'Likely Invalid'
        - 'Manual Review Required'
        """
        # If called with pre-evaluated models (e.g. for testing synthesis)
        if isinstance(claim_data, dict) and "python_model" in claim_data:
            model_results = claim_data
            rule_results = summary_card_image or kwargs.get("rule_results") or {}
            contradiction_list = kwargs.get("contradiction_list", [])
            duplicate_flags = kwargs.get("duplicate_flags", [])
            missing_documents = kwargs.get("missing_documents", [])
            return cls.synthesize_final_decision(
                model_results=model_results,
                rule_results=rule_results,
                contradiction_list=contradiction_list,
                duplicate_flags=duplicate_flags,
                missing_documents=missing_documents
            )

        engine = get_decision_engine()
        # Factor 1 & 2 & 3: Dual-Model Consensus & Confidence Difference
        model_results = engine.comparator.compare_models(claim_data, summary_card_image=summary_card_image)

        # Factor 4: Warranty Policy Rules
        rule_results = engine.policy_engine.evaluate_claim_rules(claim_data)

        # Factor 7: Contradiction Detection
        contradiction_results = engine.contradiction_detector.detect_contradictions(claim_data, ocr_data=ocr_data)
        contradiction_list = contradiction_results.get("contradictions", [])

        # Factor 6: Duplicate Claim & Document Detection
        duplicate_results = engine.duplicate_detector.check_claim_duplicates(
            claim_data, current_claim_internal_id=current_claim_internal_id
        )
        duplicate_flags = duplicate_results.get("duplicate_flags", [])

        # Factor 5: Missing Mandatory Documents Check (Req xxix & xxxiv)
        # Use the full validator to check all mandatory doc types
        claim_docs = claim_data.get("documents", [])
        has_repairs = bool(claim_data.get("has_prior_repairs") or claim_data.get("repair_count", 0) > 0)
        missing_doc_info = ClaimValidator.identify_missing_documents(claim_docs, has_previous_repairs=has_repairs)
        has_missing_documents = bool(
            missing_doc_info.get("missing_mandatory", []) or
            claim_data.get("missing_document_flag", False) or
            claim_data.get("missing_documents_count", 0) > 0
        )

        return cls.synthesize_final_decision(
            model_results=model_results,
            rule_results=rule_results,
            contradiction_list=contradiction_list,
            duplicate_flags=duplicate_flags,
            missing_documents=has_missing_documents
        )

    @staticmethod
    def generate_claim_summary(claim, adjudication_res: dict = None) -> dict:
        """
        Req 1.6.xxxii: AI-Generated Claim Summary.
        Generates a clear, comprehensive summary of:
        - Product details
        - Warranty coverage
        - Reported fault
        - Repair history
        - Uploaded evidence
        - Detected issues
        - Claim status and decision recommendation
        Provides a synthesized executive narrative for quick comprehension.
        """
        product = claim.product
        warranty = claim.warranty if claim.warranty else (product.warranty if product else None)
        claimant = getattr(claim, "claimant", None)

        # 1. Product Summary
        age_days = 0
        if product and product.purchase_date and claim.fault_occurrence_date:
            age_days = (claim.fault_occurrence_date - product.purchase_date).days

        product_summary = {
            "name": product.product_name if product else "Hardware Asset",
            "category": product.category if product else "General Hardware",
            "model_number": product.model_number if product else "N/A",
            "serial_number": product.serial_number if product else "N/A",
            "purchase_date": product.purchase_date.strftime("%Y-%m-%d") if product and product.purchase_date else "N/A",
            "purchase_price": f"${product.purchase_price:.2f}" if product and product.purchase_price else "$0.00",
            "retailer": product.retailer if product else "Authorized Retailer",
            "age_days": max(0, age_days)
        }

        # 2. Warranty Coverage Summary
        warranty_summary = {
            "policy_id": warranty.policy.policy_id if warranty and warranty.policy else "POL-STANDARD",
            "provider": warranty.warranty_provider if warranty else "Manufacturer",
            "status": warranty.status if warranty else "Active",
            "expiry_date": warranty.expiry_date.strftime("%Y-%m-%d") if warranty and warranty.expiry_date else "N/A",
            "remaining_days": warranty.remaining_days() if warranty else 0,
            "is_extended": bool(warranty.is_extended) if warranty else False
        }

        # 3. Reported Fault Summary
        delay_days = 0
        if claim.claim_submission_date and claim.fault_occurrence_date:
            delay_days = (claim.claim_submission_date - claim.fault_occurrence_date).days

        fault_summary = {
            "category": claim.fault_category,
            "damage_type": claim.damage_type or "Hardware Malfunction",
            "occurrence_date": claim.fault_occurrence_date.strftime("%Y-%m-%d") if claim.fault_occurrence_date else "N/A",
            "description": claim.fault_description,
            "reporting_delay_days": max(0, delay_days)
        }

        # 4. Repair History Summary
        repairs = product.repair_records if product and product.repair_records else []
        unauthorized_count = sum(1 for r in repairs if not r.is_authorized_center)
        authorized_count = len(repairs) - unauthorized_count
        repair_summary = {
            "total_repairs": len(repairs),
            "authorized_count": authorized_count,
            "unauthorized_count": unauthorized_count,
            "has_unauthorized_repairs": unauthorized_count > 0,
            "previous_replacement": claim.previous_replacement_details or "Original factory condition"
        }

        # 5. Uploaded Evidence Summary
        docs = claim.documents if claim.documents else []
        doc_types = [d.document_type for d in docs]
        has_receipt = any(t in ["receipt", "invoice_document", "invoice"] for t in doc_types)
        has_warranty_card = any(t in ["warranty_card"] for t in doc_types)
        has_photos = any("photo" in t or "image" in t for t in doc_types)
        ocr_count = sum(1 for d in docs if d.ocr_extracted_text)
        evidence_summary = {
            "total_documents": len(docs),
            "document_types": list(set(doc_types)),
            "has_receipt": has_receipt,
            "has_warranty_card": has_warranty_card,
            "has_photos": has_photos,
            "ocr_verified_count": ocr_count
        }

        # 6. Detected Issues Summary
        contradictions = []
        duplicate_flags = []
        failed_rules = []
        if claim.rule_validation:
            try:
                if claim.rule_validation.contradictions_json:
                    contradictions = json.loads(claim.rule_validation.contradictions_json)
                if claim.rule_validation.duplicate_flags_json:
                    duplicate_flags = json.loads(claim.rule_validation.duplicate_flags_json)
                if claim.rule_validation.rules_failed_json:
                    failed_rules = json.loads(claim.rule_validation.rules_failed_json)
            except Exception:
                pass

        has_issues = bool(
            claim.missing_document_flag or
            claim.contradiction_flag or
            claim.is_duplicate_flag or
            len(contradictions) > 0 or
            len(duplicate_flags) > 0 or
            len(failed_rules) > 0
        )

        detected_issues_summary = {
            "has_issues": has_issues,
            "missing_document_flag": bool(claim.missing_document_flag),
            "contradiction_flag": bool(claim.contradiction_flag),
            "is_duplicate_flag": bool(claim.is_duplicate_flag),
            "contradictions": contradictions,
            "duplicate_flags": duplicate_flags,
            "failed_rules": failed_rules
        }

        # 7. Claim Status & Recommendation Summary
        eval_obj = claim.model_evaluation
        claim_status_summary = {
            "status": claim.status,
            "final_decision": claim.final_decision or "Pending Evaluation",
            "risk_level": claim.risk_level or "Medium",
            "decision_reason": claim.decision_reason or "",
            "python_predicted_class": eval_obj.python_predicted_class if eval_obj else "Pending",
            "gtm_predicted_class": eval_obj.gtm_predicted_class if eval_obj else "Pending",
            "model_consistency": eval_obj.model_consistency_status if eval_obj else "Pending",
            "top_confidence_difference": eval_obj.top_confidence_difference if eval_obj else 0.0
        }

        # 8. Synthesized Executive Narrative
        claimant_name = claimant.full_name if claimant else "Claimant"
        narrative_parts = [
            f"Warranty claim {claim.claim_id} submitted by {claimant_name} for '{product_summary['name']}' (Serial: {product_summary['serial_number']}).",
            f"Warranty coverage under {warranty_summary['provider']} is {warranty_summary['status'].lower()} with {warranty_summary['remaining_days']} days remaining.",
            f"Reported issue is classified as '{fault_summary['category']}' ({fault_summary['damage_type']}) on {fault_summary['occurrence_date']}.",
            f"Claim dossier contains {evidence_summary['total_documents']} supporting document(s), of which {evidence_summary['ocr_verified_count']} are verified through OCR.",
        ]
        if detected_issues_summary["has_issues"]:
            issues_found = []
            if claim.missing_document_flag:
                issues_found.append("mandatory evidence documents pending")
            if claim.contradiction_flag or len(contradictions) > 0:
                issues_found.append("chronological or hardware contradictions")
            if claim.is_duplicate_flag or len(duplicate_flags) > 0:
                issues_found.append("duplicate indicators")
            if len(failed_rules) > 0:
                issues_found.append("policy rule violations")
            narrative_parts.append(f"Attention items flagged: {', '.join(issues_found)}.")
        else:
            narrative_parts.append("Policy rule compliance and chronological checks verified without discrepancies.")

        narrative_parts.append(
            f"The automated adjudication recommendation is '{claim_status_summary['final_decision']}' with {claim_status_summary['risk_level']} risk assessment."
        )

        executive_narrative = " ".join(narrative_parts)

        return {
            "claim_id": claim.claim_id,
            "product_summary": product_summary,
            "warranty_summary": warranty_summary,
            "warranty_coverage_summary": warranty_summary,
            "fault_summary": fault_summary,
            "reported_fault_summary": fault_summary,
            "repair_history_summary": repair_summary,
            "evidence_summary": evidence_summary,
            "uploaded_evidence_summary": evidence_summary,
            "detected_issues_summary": detected_issues_summary,
            "claim_status_summary": claim_status_summary,
            "claim_status_and_recommendations": claim_status_summary,
            "executive_narrative": executive_narrative,
            "executive_brief": executive_narrative
        }

    @staticmethod
    def generate_decision_explanation(claim) -> dict:
        """
        Req 1.6.xxxv: Decision Explanation.
        Explains:
        1. Factors supporting the decision
        2. Factors opposing the decision
        3. Rules passed
        4. Rules failed
        5. Detected contradictions
        6. Additional evidence required
        """
        supporting_factors = []
        opposing_factors = []
        rules_passed = []
        rules_failed = []
        contradictions = []
        duplicate_flags = []
        additional_evidence_required = []

        # 1. Rule Validation Logs
        if claim.rule_validation:
            try:
                rules_passed = claim.rule_validation.get_passed()
                rules_failed = claim.rule_validation.get_failed()
                contradictions = claim.rule_validation.get_contradictions()
                if claim.rule_validation.duplicate_flags_json:
                    duplicate_flags = json.loads(claim.rule_validation.duplicate_flags_json)
            except Exception:
                pass

        # 2. Model Evaluation
        eval_obj = claim.model_evaluation
        if eval_obj:
            py_class = eval_obj.python_predicted_class
            py_top_conf = max(eval_obj.python_conf_valid, eval_obj.python_conf_invalid, eval_obj.python_conf_manual)
            gtm_class = eval_obj.gtm_predicted_class
            gtm_top_conf = max(eval_obj.gtm_conf_valid, eval_obj.gtm_conf_invalid, eval_obj.gtm_conf_manual)
            consistency = eval_obj.model_consistency_status
            diff = eval_obj.top_confidence_difference

            if eval_obj.is_class_match:
                if py_class == Config.CLAIM_CLASS_VALID:
                    supporting_factors.append(f"Dual AI models unanimously approved claim as 'Valid Claim' (Python: {py_top_conf*100:.1f}%, GTM: {gtm_top_conf*100:.1f}%).")
                    supporting_factors.append(f"Model consistency status verified as '{consistency}' with confidence delta of {diff:.4f}.")
                elif py_class == Config.CLAIM_CLASS_INVALID:
                    opposing_factors.append(f"Dual AI models unanimously rejected claim as 'Invalid Claim' (Python: {py_top_conf*100:.1f}%, GTM: {gtm_top_conf*100:.1f}%).")
                else:
                    opposing_factors.append("Both AI models recommended 'Manual Review' for specialized human inspection.")
            else:
                opposing_factors.append(f"Model disagreement: Python model predicted '{py_class}' ({py_top_conf*100:.1f}%) while Vision model predicted '{gtm_class}' ({gtm_top_conf*100:.1f}%).")

            if consistency == Config.CONSISTENCY_UNCERTAIN:
                opposing_factors.append("Model confidence is below operating minimum threshold.")

        # 3. Rules & Hardware Policy Factors
        product = claim.product
        warranty = claim.warranty if claim.warranty else (product.warranty if product else None)

        if warranty and warranty.is_active(claim.fault_occurrence_date):
            supporting_factors.append(f"Active warranty coverage verified ({warranty.remaining_days()} days remaining until {warranty.expiry_date.strftime('%Y-%m-%d')}).")
        elif warranty and not warranty.is_active(claim.fault_occurrence_date):
            opposing_factors.append(f"Warranty coverage expired on {warranty.expiry_date.strftime('%Y-%m-%d')} before reported defect date.")

        if rules_passed:
            for r in rules_passed[:4]:
                if not any(r.lower() in sf.lower() for sf in supporting_factors):
                    supporting_factors.append(f"Policy Rule Passed: {r}")

        if rules_failed:
            for r in rules_failed:
                opposing_factors.append(f"Policy Violation: {r}")

        # 4. Contradictions & Integrity
        if claim.contradiction_flag or len(contradictions) > 0:
            for c in (contradictions or ["Inconsistent chronological dates or serial number mismatch"]):
                opposing_factors.append(f"Contradiction Detected: {c}")

        if claim.is_duplicate_flag or len(duplicate_flags) > 0:
            for d in (duplicate_flags or ["Duplicate claim attributes or document hash detected"]):
                opposing_factors.append(f"Duplicate Advisory: {d}")

        if not claim.contradiction_flag and len(contradictions) == 0:
            supporting_factors.append("Chronological timeline and hardware serial verification passed without conflicts.")

        # 5. Additional Evidence Required (Missing Documents / Information)
        docs = claim.documents if claim.documents else []
        doc_types = [d.document_type for d in docs]
        has_receipt = any(t in ["receipt", "invoice_document", "invoice"] for t in doc_types)
        has_card = any(t in ["warranty_card"] for t in doc_types)
        has_photo = any("photo" in t or "image" in t for t in doc_types)
        has_diagnostic = any("report" in t or "diagnostic" in t for t in doc_types)

        if not has_receipt:
            additional_evidence_required.append("Purchase Receipt / Tax Invoice: Legible proof of purchase detailing transaction date, price, and authorized retailer.")
        if not has_card:
            additional_evidence_required.append("Warranty Card: Manufacturer or retailer warranty card verifying coverage terms.")
        if not has_photo:
            additional_evidence_required.append("Fault / Damage Photographs: Clear photos or video capturing the hardware defect or physical damage.")
        if not any("serial" in t for t in doc_types):
            additional_evidence_required.append("Serial-Number Photograph: Clear image of the serial-number barcode or hardware chassis stamp.")
        if product and (product.has_unauthorized_repairs or (hasattr(product, "repair_records") and len(product.repair_records) > 0)) and not has_diagnostic:
            additional_evidence_required.append("Service / Repair Report: Official workshop bench report documenting previous repairs or maintenance.")

        if claim.missing_document_flag and not additional_evidence_required:
            additional_evidence_required.append("Mandatory documentation pending verification by claimant.")

        if not additional_evidence_required:
            supporting_factors.append("All mandatory proof documents (receipt, warranty card, photos) successfully attached.")

        return {
            "claim_id": claim.claim_id,
            "final_decision": claim.final_decision or "Pending Evaluation",
            "decision_summary": claim.decision_reason or "Automated multi-factor evaluation completed.",
            "risk_level": claim.risk_level or "Medium",
            "supporting_factors": supporting_factors,
            "opposing_factors": opposing_factors,
            "rules_passed": rules_passed,
            "rules_failed": rules_failed,
            "contradictions": contradictions,
            "duplicate_flags": duplicate_flags,
            "additional_evidence_required": additional_evidence_required,
            "has_missing_evidence": len(additional_evidence_required) > 0
        }


# Singleton master decision engine instance
_decision_engine_instance = None

def get_decision_engine() -> MasterDecisionEngine:
    global _decision_engine_instance
    if _decision_engine_instance is None:
        _decision_engine_instance = MasterDecisionEngine()
    return _decision_engine_instance

def generate_claim_summary(claim, adjudication_res: dict = None) -> dict:
    """Convenience helper to generate structured claim summary (Req xxxii)."""
    return get_decision_engine().generate_claim_summary(claim, adjudication_res=adjudication_res)

def generate_decision_explanation(claim) -> dict:
    """Convenience helper to generate comprehensive decision explanation factors (Req xxxv)."""
    return get_decision_engine().generate_decision_explanation(claim)
