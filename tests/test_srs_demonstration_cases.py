import os
import unittest
import pandas as pd
from datetime import datetime, timezone, timedelta, date
from src.app import create_app
from database.db import db
from src.models.entities import (
    User, Product, WarrantyPolicy, ProductWarranty, Claim,
    ClaimDocument, ModelEvaluation, ReviewerAction, ClaimStatusHistory
)
from src.core.decision_engine import get_decision_engine
from src.core.model_comparator import DualModelComparator
from src.rules.policy_engine import get_policy_engine
from src.rules.contradiction_detector import get_contradiction_detector
from src.rules.duplicate_detector import get_duplicate_detector
from config.config import Config


class TestSRSDemonstrationCases(unittest.TestCase):
    """
    Verification suite explicitly asserting all 11 Mandatory Demonstration Cases
    from AssureX SRS Section 3.3 (Page 31):
    1. One valid claim
    2. One invalid claim
    3. One manual-review claim
    4. One expired-warranty claim
    5. One missing-document claim
    6. One duplicate claim
    7. One contradictory claim
    8. One serial-number mismatch
    9. One unauthorized-repair claim
    10. One tricky boundary-date claim
    11. One case where the two models disagree
    + Demonstration of Reviewer Adjudication Override (Req xxxvii)
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()
        cls.engine = get_decision_engine()
        cls.test_df = pd.read_csv("data/splits/test.csv")

    def setUp(self):
        # Clean up any leftover test claims
        with self.app.app_context():
            leftovers = Claim.query.filter(Claim.claim_id.like("CLM-TEST-%") | Claim.claim_id.like("CLM-DUP-%") | Claim.claim_id.like("CLM-OVERRIDE-%")).all()
            for c in leftovers:
                db.session.delete(c)
            db.session.commit()

    def test_case_01_valid_claim(self):
        """
        SRS Case 1: One valid claim.
        Active warranty, covered fault, complete evidence, verified serial.
        Expected: Dual model consensus, Valid Claim recommendation, Low risk.
        """
        valid_row = self.test_df[self.test_df["claim_class"] == Config.CLAIM_CLASS_VALID].iloc[0].to_dict()
        res = self.engine.adjudicate_claim(valid_row)

        self.assertEqual(res["final_decision"], "Likely Valid")
        self.assertEqual(res["risk_level"], "Low")
        self.assertEqual(len(res["failed_rules"]), 0)
        self.assertEqual(res["dual_model_evaluation"]["python_model"]["predicted_class"], Config.CLAIM_CLASS_VALID)
        self.assertEqual(res["dual_model_evaluation"]["gtm_model"]["predicted_class"], Config.CLAIM_CLASS_VALID)

    def test_case_02_invalid_claim(self):
        """
        SRS Case 2: One invalid claim.
        Unanimous AI prediction as Invalid Claim and hard policy violation.
        Expected: Invalid Claim recommendation, High risk.
        """
        invalid_row = self.test_df[self.test_df["claim_class"] == Config.CLAIM_CLASS_INVALID].iloc[0].to_dict()
        res = self.engine.adjudicate_claim(invalid_row)

        self.assertEqual(res["final_decision"], "Likely Invalid")
        self.assertEqual(res["risk_level"], "High")

    def test_case_03_manual_review_claim(self):
        """
        SRS Case 3: One manual-review claim.
        Borderline signals or discretionary condition requiring human adjudication.
        Expected: Manual Review Required recommendation, Medium risk.
        """
        manual_row = self.test_df[self.test_df["claim_id"] == "CLM-01419"].iloc[0].to_dict()
        res = self.engine.adjudicate_claim(manual_row)

        self.assertEqual(res["final_decision"], "Manual Review Required")
        self.assertIn(res["risk_level"], ["Medium", "High"])

    def test_case_04_expired_warranty_claim(self):
        """
        SRS Case 4: One expired-warranty claim.
        Fault occurrence date past warranty expiration duration and beyond permissible grace period.
        Expected: Policy engine flags hard expiration, Likely Invalid.
        """
        claim_data = {
            "claim_id": "DEMO-CASE-EXPIRED",
            "product_category": "Consumer Electronics",
            "product_brand": "Sony",
            "product_model": "BRAVIA-XR-65",
            "product_serial": "SN-EXP-9999",
            "purchase_date": "2023-01-01",
            "purchase_price": 1200.0,
            "retailer": "Best Buy",
            "warranty_expiry_date": "2024-01-01",
            "warranty_duration_months": 12,
            "product_age_days": 800,
            "remaining_warranty_days": 0,
            "fault_occurrence_date": "2025-05-01",
            "fault_category": "Screen Flickering",
            "fault_description": "Display lines appearing well after warranty expiration.",
            "damage_type": "Hardware Defect",
            "is_extended_warranty": 0,
            "has_receipt": 1,
            "has_warranty_card": 1,
            "has_damage_photo": 1,
            "has_serial_photo": 1,
            "has_repair_report": 0,
            "missing_document_count": 0,
            "serial_number_match": 1,
            "previous_repairs_count": 0,
            "unauthorized_repair_flag": 0,
            "claim_date_conflict_flag": 0
        }
        res = self.engine.adjudicate_claim(claim_data)
        self.assertEqual(res["final_decision"], "Likely Invalid")
        self.assertTrue(any("expired" in r.lower() for r in res["failed_rules"]))

    def test_case_05_missing_document_claim(self):
        """
        SRS Case 5: One missing-document claim.
        Primary proof of purchase / invoice missing from submission dossier.
        Expected: Policy engine flags missing proof of purchase trigger, Manual Review Required.
        """
        policy_eng = get_policy_engine()
        claim_data = {
            "product_category": "Consumer Electronics",
            "remaining_warranty_days": 100,
            "has_receipt": 0,
            "missing_document_count": 1,
            "unauthorized_repair_flag": 0,
            "serial_number_match": 1,
            "claim_date_conflict_flag": 0,
            "fault_category": "Screen flickering"
        }
        eval_rules = policy_eng.evaluate_claim_rules(claim_data)
        self.assertEqual(eval_rules["overall_status"], "REVIEW")
        self.assertTrue(any("receipt" in t.lower() or "missing" in t.lower() for t in eval_rules["manual_review_triggers"]))

    def test_case_06_duplicate_claim(self):
        """
        SRS Case 6: One duplicate claim.
        Same hardware serial submitted across multiple claims.
        Expected: Duplicate detector flags active duplicate submission.
        """
        with self.app.app_context():
            user = User.query.first()
            prod = Product.query.first()
            warr = prod.warranty

            # Insert original claim
            claim1 = Claim(
                claim_id="CLM-DUP-ORIGINAL",
                user_id=user.id,
                product_id=prod.id,
                warranty_id=warr.id,
                fault_occurrence_date=date.today(),
                fault_description="Original defect report.",
                fault_category="Screen Flickering",
                status=Config.STATUS_UNDER_EVALUATION
            )
            db.session.add(claim1)
            db.session.commit()

            # Test duplicate detector with same product serial
            detector = get_duplicate_detector()
            dup_result = detector.check_claim_duplicates({
                "claim_id": "CLM-DUP-SUBSEQUENT",
                "product_serial": prod.serial_number
            })

            self.assertTrue(dup_result["is_duplicate"])
            self.assertTrue(len(dup_result["duplicate_flags"]) > 0)
            self.assertIn("CLM-DUP-ORIGINAL", dup_result["conflicting_claim_ids"])

            # Clean up
            db.session.delete(claim1)
            db.session.commit()

    def test_case_07_contradictory_claim(self):
        """
        SRS Case 7: One contradictory claim.
        Chronological conflict where fault occurrence date precedes equipment purchase date.
        Expected: Contradiction detector flags chronological conflict.
        """
        detector = get_contradiction_detector()
        claim_data = {
            "purchase_date": "2025-06-01",
            "fault_occurrence_date": "2025-01-01",  # 5 months before purchase!
            "product_serial": "SN-TEST-1234"
        }
        res = detector.detect_contradictions(claim_data)
        self.assertTrue(res["has_contradiction"])
        self.assertTrue(any("prior" in c.lower() or "contradiction" in c.lower() for c in res["contradictions"]))

    def test_case_08_serial_number_mismatch(self):
        """
        SRS Case 8: One serial-number mismatch.
        Hardware serial number in OCR invoice does not match registered equipment.
        Expected: Serial mismatch detected between invoice document and database registration.
        """
        detector = get_contradiction_detector()
        claim_data = {
            "purchase_date": "2025-06-01",
            "fault_occurrence_date": "2025-08-01",
            "product_serial": "REGISTERED-SN-8888"
        }
        ocr_data = {
            "entities": {
                "serial_number": "INVOICE-DIFFERENT-SN-9999",
                "invoice_date": "2025-06-01"
            }
        }
        res = detector.detect_contradictions(claim_data, ocr_data=ocr_data)
        self.assertTrue(res["has_contradiction"])
        self.assertTrue(any("mismatch" in c.lower() for c in res["contradictions"]))

    def test_case_09_unauthorized_repair_claim(self):
        """
        SRS Case 9: One unauthorized-repair claim.
        Equipment was previously serviced or opened by an uncertified third-party repair shop.
        Expected: Policy engine flags unauthorized repair violation.
        """
        policy_eng = get_policy_engine()
        claim_data = {
            "product_category": "Consumer Electronics",
            "remaining_warranty_days": 100,
            "has_receipt": 1,
            "missing_document_count": 0,
            "unauthorized_repair_flag": 1,
            "serial_number_match": 1,
            "claim_date_conflict_flag": 0,
            "fault_category": "Screen flickering"
        }
        eval_rules = policy_eng.evaluate_claim_rules(claim_data)
        self.assertEqual(eval_rules["overall_status"], "REVIEW")
        self.assertTrue(any("unauthorized" in t.lower() for t in eval_rules["manual_review_triggers"]))

    def test_case_10_tricky_boundary_date_claim(self):
        """
        SRS Case 10: One tricky boundary-date claim.
        Claim submitted 3 days after 12-month warranty expiry, but within permissible 7-day grace period.
        With accurate calendar math: 12 months ≈ 365 days, so 368 = 3 days overdue.
        Expected: Eligible for discretionary grace period review, triggers warning and manual review trigger.
        """
        policy_eng = get_policy_engine()
        claim_data = {
            "product_category": "Consumer Electronics",
            "warranty_duration_months": 12,
            "product_age_days": 368,  # 365 days standard (12*30.4375) + 3 days overdue (within 7d grace)
            "remaining_warranty_days": 0,
            "has_receipt": 1,
            "missing_document_count": 0,
            "unauthorized_repair_flag": 0,
            "serial_number_match": 1,
            "claim_date_conflict_flag": 0,
            "fault_category": "Screen flickering"
        }
        eval_rules = policy_eng.evaluate_claim_rules(claim_data)
        self.assertEqual(eval_rules["overall_status"], "REVIEW")
        self.assertTrue(any("grace period" in t.lower() for t in eval_rules["manual_review_triggers"]))
        self.assertTrue(any("grace period" in w.lower() for w in eval_rules["warnings"]))

    def test_case_11_model_disagreement_claim(self):
        """
        SRS Case 11: One case where the two models disagree.
        Python model predicts Valid Claim while Teachable Machine predicts Invalid Claim.
        Expected: is_class_match is False, model_consistency_status is 'Model Disagreement'.
        """
        comparator = DualModelComparator(min_conf=0.60)
        py_output = {
            "predicted_class": Config.CLAIM_CLASS_VALID,
            "top_confidence": 0.94,
            "confidence_scores": {"Valid Claim": 0.94, "Invalid Claim": 0.03, "Manual Review": 0.03}
        }
        gtm_output = {
            "predicted_class": Config.CLAIM_CLASS_INVALID,
            "top_confidence": 0.91,
            "confidence_scores": {"Valid Claim": 0.04, "Invalid Claim": 0.91, "Manual Review": 0.05}
        }

        eval_res = comparator.evaluate_consensus(py_output, gtm_output)
        self.assertFalse(eval_res["is_class_match"])
        self.assertEqual(eval_res["model_consistency_status"], Config.CONSISTENCY_DISAGREEMENT)
        self.assertFalse(eval_res["consensus_reached"])

    def test_case_reviewer_override_workflow(self):
        """
        SRS Req xxxvii: Human Reviewer Adjudication Override.
        Reviewer overrides AI automated decision to 'Approved' with mandatory justification notes.
        Expected: Claim status becomes Approved, ReviewerAction is persisted with is_override=True.
        """
        with self.app.app_context():
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            reviewer = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
            product = Product.query.first()
            warranty = ProductWarranty.query.filter_by(product_id=product.id).first()

            claim_code = f"CLM-OVERRIDE-{datetime.now().strftime('%M%S%f')[:8]}"
            test_claim = Claim(
                claim_id=claim_code,
                user_id=customer.id,
                product_id=product.id,
                warranty_id=warranty.id,
                fault_occurrence_date=datetime.now(timezone.utc).date() - timedelta(days=10),
                fault_description="Testing human reviewer override adjudication.",
                fault_category="Screen Flickering",
                claim_submission_date=datetime.now(timezone.utc).date(),
                status=Config.STATUS_MANUAL_REVIEW,
                final_decision="Manual Review Required",
                decision_reason="Divergent signals flagged for reviewer triage.",
                risk_level="Medium"
            )
            db.session.add(test_claim)
            db.session.commit()

            # Execute override via client POST
            with self.client.session_transaction() as sess:
                sess["user_id"] = reviewer.id
                sess["user_code"] = reviewer.user_id
                sess["role"] = reviewer.role
                sess["user_name"] = reviewer.full_name
                sess["email"] = reviewer.email

            res = self.client.post(
                f"/reviewer/claim/{test_claim.claim_id}/adjudicate",
                data={
                    "action": "APPROVE",
                    "comments": "Inspected customer purchase invoice and service center notes. Defect is legitimate and covered under policy Section 4.2."
                },
                follow_redirects=True
            )
            self.assertEqual(res.status_code, 200)

            # Verify in DB
            updated_claim = Claim.query.filter_by(claim_id=claim_code).first()
            self.assertEqual(updated_claim.status, Config.STATUS_APPROVED)
            self.assertEqual(len(updated_claim.reviewer_actions), 1)
            action = updated_claim.reviewer_actions[0]
            self.assertEqual(action.reviewer_decision, "Approved")
            self.assertTrue(action.is_override)
            self.assertIn("Section 4.2", action.comments)

            # Cleanup
            db.session.delete(updated_claim)
            db.session.commit()


if __name__ == "__main__":
    unittest.main()
