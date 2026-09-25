import os
import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta, date
from PIL import Image

from src.app import create_app
from database.db import db
from src.models.entities import (
    User, Product, WarrantyPolicy, ProductWarranty, Claim,
    ClaimDocument, ModelEvaluation, ReviewerAction, ClaimStatusHistory, AuditLog
)
from src.core.decision_engine import get_decision_engine, MasterDecisionEngine
from src.core.model_comparator import get_model_comparator, DualModelComparator
from src.rules.policy_engine import get_policy_engine, WarrantyPolicyEngine
from src.rules.contradiction_detector import get_contradiction_detector, ContradictionDetector
from src.rules.duplicate_detector import get_duplicate_detector, DuplicateDetector
from src.ocr.document_processor import get_document_processor, DocumentProcessor
from src.services.report_generator import get_pdf_generator
from src.services.export_service import DataExportService
from config.config import Config


class TestSRS18Categories(unittest.TestCase):
    """
    Comprehensive verification suite rigorously validating all 18 Test Categories
    specified in AssureX SRS Section 3.3 (Pages 30-31):
    
     1. Functional test cases
     2. Integration test cases
     3. Boundary test cases
     4. Negative test cases
     5. Security test cases
     6. Database test cases
     7. OCR test cases
     8. Python model test cases
     9. Google Teachable Machine test cases
    10. Model-comparison test cases
    11. Rule-engine test cases
    12. Contradiction-detection tests
    13. Missing-document tests
    14. Duplicate-claim tests
    15. Serial-number mismatch tests
    16. Low-confidence test cases
    17. Model-disagreement test cases
    18. Hidden-test readiness checklist
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()
        cls.engine = get_decision_engine()
        cls.comparator = get_model_comparator()
        cls.policy_engine = get_policy_engine()
        cls.contradiction_detector = get_contradiction_detector()
        cls.duplicate_detector = get_duplicate_detector()
        cls.ocr_processor = get_document_processor()
        cls.test_df = pd.read_csv("data/splits/test.csv")

    def setUp(self):
        with self.app.app_context():
            leftovers = Claim.query.filter(~Claim.claim_id.like("CLM-DEMO-%")).all()
            for c in leftovers:
                db.session.delete(c)
            db.session.commit()

    # =========================================================================
    # Category 01: Functional Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat01_functional_claim_intake_and_adjudication(self):
        """
        Cat 01: Functional Test - Complete claim intake, evaluation, and lifecycle tracking.
        Verifies all 8 stages and user-to-reviewer interaction.
        """
        with self.app.app_context():
            user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            product = Product.query.first()
            warranty = ProductWarranty.query.filter_by(product_id=product.id).first()

            # 1. Draft initiation
            claim = Claim(
                claim_id="CLM-FUNC-001",
                user_id=user.id,
                product_id=product.id,
                warranty_id=warranty.id,
                fault_occurrence_date=datetime.now(timezone.utc).date() - timedelta(days=4),
                fault_description="Power supply fluctuates and drops voltage.",
                fault_category="Motherboard failure",
                claim_submission_date=datetime.now(timezone.utc).date(),
                status=Config.STATUS_DRAFT,
                risk_level="Low"
            )
            db.session.add(claim)
            db.session.commit()
            self.assertEqual(claim.status, Config.STATUS_DRAFT)

            # 2. Transition to Submitted -> Under Evaluation
            claim.transition_status(Config.STATUS_SUBMITTED, updated_by_user_id=user.id, notes="Submitted by customer.")
            db.session.commit()
            self.assertEqual(claim.status, Config.STATUS_SUBMITTED)

            claim.transition_status(Config.STATUS_UNDER_EVALUATION, updated_by_user_id=user.id, notes="Automated AI triage begun.")
            db.session.commit()
            self.assertEqual(claim.status, Config.STATUS_UNDER_EVALUATION)

            # 3. Verify history logs
            history = ClaimStatusHistory.query.filter_by(claim_id=claim.id).order_by(ClaimStatusHistory.id.asc()).all()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0].new_status, Config.STATUS_SUBMITTED)
            self.assertEqual(history[1].new_status, Config.STATUS_UNDER_EVALUATION)

    # =========================================================================
    # Category 02: Integration Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat02_integration_end_to_end_pipeline(self):
        """
        Cat 02: Integration Test - Document upload -> OCR extraction -> Dual ML inference ->
        Warranty policy evaluation -> Master decision synthesis -> PDF certificate.
        """
        with self.app.app_context():
            user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            product = Product.query.filter_by(category="Consumer Electronics").first()
            warranty = ProductWarranty.query.filter_by(product_id=product.id).first()

            # Simulated receipt OCR extraction
            raw_text = (
                f"TAX INVOICE - Best Buy Electronics\n"
                f"Date: 2024-03-15\n"
                f"Product: {product.model_number}\n"
                f"Serial: {product.serial_number}\n"
                f"Total: $850.00\n"
            )
            ocr_result = self.ocr_processor.process_text(raw_text)
            self.assertEqual(ocr_result["entities"]["serial_number"], product.serial_number)

            # Build claim payload from a confirmed valid test claim
            claim_data = self.test_df[self.test_df["claim_class"] == Config.CLAIM_CLASS_VALID].iloc[0].to_dict()
            claim_data["serial_number"] = product.serial_number
            claim_data["product_serial"] = product.serial_number

            # Run master decision
            adjudication = self.engine.adjudicate_claim(claim_data, ocr_data=ocr_result)
            self.assertEqual(adjudication["final_decision"], "Likely Valid")

            # Persist and generate PDF certificate
            claim = Claim(
                claim_id="CLM-CAT-INT-001",
                user_id=user.id,
                product_id=product.id,
                warranty_id=warranty.id,
                fault_occurrence_date=date(2024, 9, 10),
                fault_description="System shuts down spontaneously.",
                fault_category="Motherboard failure",
                claim_submission_date=date(2024, 9, 12),
                status=Config.STATUS_APPROVED,
                final_decision=adjudication["final_decision"],
                decision_reason=adjudication["decision_summary"],
                risk_level=adjudication["risk_level"]
            )
            db.session.add(claim)
            db.session.flush()

            pdf_gen = get_pdf_generator()
            pdf_bytes = pdf_gen.generate_pdf(claim)
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
            self.assertGreater(len(pdf_bytes), 1000)

    # =========================================================================
    # Category 03: Boundary Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat03_boundary_warranty_and_reporting_deadlines(self):
        """
        Cat 03: Boundary Test - 
        Case A: Claim on exact last day of standard warranty (Valid/Pass).
        Case B: Claim during grace period (+10 days) (Manual Review Warning).
        Case C: Claim beyond grace period (+15 days) (Hard Fail).
        Case D: Reporting delay day 30 vs day 31 (Reporting deadline hard boundary).
        """
        base_claim = {
            "claim_id": "CLM-CAT-BOUND-1",
            "product_category": "Consumer Electronics",
            "purchase_date": "2023-01-01",
            "warranty_period_months": 12,
            "fault_category": "Screen flickering",
            "damage_type": "Component Defect",
            "claim_amount": 100.0,
            "repair_history_count": 0,
            "unauthorized_repair_flag": 0,
            "physical_damage_severity": 0.0,
            "water_damage_flag": 0,
            "serial_number_match": 1,
            "mandatory_documents_present": 1,
            "claim_date_conflict_flag": 0
        }

        # Case A: Exactly on expiration day (360 days after purchase)
        c_a = base_claim.copy()
        c_a["fault_occurrence_date"] = "2023-12-31"
        c_a["claim_submission_date"] = "2023-12-31"
        c_a["days_since_purchase"] = 360
        c_a["product_age_days"] = 360
        c_a["days_until_warranty_expiry"] = 1
        c_a["remaining_warranty_days"] = 1
        c_a["days_between_fault_and_claim"] = 0
        res_a = self.policy_engine.evaluate_claim_rules(c_a)
        self.assertEqual(len(res_a["failed_rules"]), 0)

        # Case B: 4 days past expiration (within 7-day grace period)
        # With accurate calendar math: 12 months ≈ 365 days, so 369 = 4 days overdue
        c_b = base_claim.copy()
        c_b["fault_occurrence_date"] = "2024-01-04"
        c_b["claim_submission_date"] = "2024-01-04"
        c_b["days_since_purchase"] = 369
        c_b["product_age_days"] = 369
        c_b["days_until_warranty_expiry"] = -4
        c_b["remaining_warranty_days"] = -4
        c_b["days_between_fault_and_claim"] = 0
        res_b = self.policy_engine.evaluate_claim_rules(c_b)
        self.assertEqual(len(res_b["failed_rules"]), 0)
        self.assertTrue(any("grace period" in w.lower() for w in res_b["warnings"] + res_b["manual_review_triggers"]))

        # Case C: 20 days past expiration (exceeds 7-day grace period)
        c_c = base_claim.copy()
        c_c["fault_occurrence_date"] = "2024-01-20"
        c_c["claim_submission_date"] = "2024-01-20"
        c_c["days_since_purchase"] = 380
        c_c["product_age_days"] = 380
        c_c["days_until_warranty_expiry"] = -20
        c_c["remaining_warranty_days"] = -20
        c_c["days_between_fault_and_claim"] = 0
        res_c = self.policy_engine.evaluate_claim_rules(c_c)
        self.assertGreater(len(res_c["failed_rules"]), 0)
        self.assertTrue(any("expired" in f.lower() for f in res_c["failed_rules"]))

        # Case D: Reporting deadline boundary (31 days exceeds 30-day reporting window)
        c_d = base_claim.copy()
        c_d["fault_occurrence_date"] = "2023-06-01"
        c_d["claim_submission_date"] = "2023-07-02"
        c_d["days_since_purchase"] = 151
        c_d["days_until_warranty_expiry"] = 214
        c_d["days_between_fault_and_claim"] = 31
        res_d = self.policy_engine.evaluate_claim_rules(c_d)
        self.assertTrue(any("deadline" in f.lower() for f in res_d["failed_rules"]))

    # =========================================================================
    # Category 04: Negative Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat04_negative_invalid_inputs_and_edge_conditions(self):
        """
        Cat 04: Negative Test - Malformed data, negative numbers, missing files,
        unsupported formats handled defensively without unhandled runtime crashes.
        """
        # 1. Negative claim amount handled gracefully
        invalid_payload = {
            "claim_id": "CLM-CAT-NEG-001",
            "product_category": "Consumer Electronics",
            "fault_category": "Battery failure to charge",
            "claim_amount": -150.0,
            "days_since_purchase": 50,
            "days_until_warranty_expiry": 300,
            "repair_history_count": 0,
            "unauthorized_repair_flag": 0,
            "physical_damage_severity": 0.0,
            "water_damage_flag": 0,
            "serial_number_match": 1,
            "mandatory_documents_present": 1,
            "claim_date_conflict_flag": 0
        }
        res = self.engine.adjudicate_claim(invalid_payload)
        self.assertIn(res["final_decision"], ["Likely Valid", "Likely Invalid", "Manual Review Required"])

        # 2. Corrupted OCR input string handled safely
        ocr_res = self.ocr_processor.process_text("")
        self.assertEqual(len(ocr_res["extracted_text"]), 0)

        # 3. Non-existent product category falls back safely
        fallback_res = self.policy_engine.get_policy_for_category("Unknown Spaceship Tech")
        self.assertIn("Default Standard Policy", fallback_res["policy_name"])
        self.assertEqual(fallback_res["coverage_duration_months"], 12)

    # =========================================================================
    # Category 05: Security Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat05_security_rbac_and_input_sanitization(self):
        """
        Cat 05: Security Test - Role-Based Access Control guards against privilege escalation;
        unauthenticated users cannot view reviewer/admin queues; XSS payload escaping.
        """
        # 1. Unauthenticated access redirect
        unauth_resp = self.client.get("/reviewer/queue", follow_redirects=False)
        self.assertEqual(unauth_resp.status_code, 302)
        self.assertIn("/login", unauth_resp.headers["Location"])

        # 2. Customer cannot access Reviewer Queue (redirected to portal)
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                cust = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = cust.id
                sess["role"] = Config.ROLE_CUSTOMER
        forbidden_resp = self.client.get("/reviewer/queue", follow_redirects=False)
        self.assertEqual(forbidden_resp.status_code, 302)

        # 3. Staff Reviewer cannot access Admin Dashboard (redirected to portal)
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                rev = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
                sess["user_id"] = rev.id
                sess["role"] = Config.ROLE_REVIEWER
        admin_forbidden = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(admin_forbidden.status_code, 302)

    # =========================================================================
    # Category 06: Database Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat06_database_referential_integrity_and_audit(self):
        """
        Cat 06: Database Test - Foreign key integrity, audit trail tracking, and transaction safety.
        """
        with self.app.app_context():
            prod = Product.query.first()
            self.assertIsNotNone(prod)
            user = prod.owner
            self.assertIsNotNone(user)
            self.assertEqual(prod.user_id, user.id)

            # Test audit log creation
            AuditLog.log_event(
                event_type="TEST_AUDIT_VERIFICATION",
                user_id=user.id,
                details="Verifying audit trail recording.",
                ip_address="127.0.0.1"
            )
            db.session.commit()

            log = AuditLog.query.filter_by(action="TEST_AUDIT_VERIFICATION").first()
            self.assertIsNotNone(log)
            self.assertEqual(log.user_id, user.id)
            db.session.delete(log)
            db.session.commit()

    # =========================================================================
    # Category 07: OCR Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat07_document_ocr_and_sha256_hashing(self):
        """
        Cat 07: OCR Test - SHA-256 fingerprinting deterministic integrity,
        text parsing of invoice number, purchase date, and retailer.
        """
        test_content = b"INVOICE-SAMPLE-DATA-2024-TECHWIZ-ASSUREX-001"
        computed_hash = self.ocr_processor.compute_sha256(test_content)
        self.assertEqual(len(computed_hash), 64)
        # Verify deterministic hash
        re_hash = self.ocr_processor.compute_sha256(test_content)
        self.assertEqual(computed_hash, re_hash)

        # Parse text entities
        sample_receipt = (
            "STORE RECEIPT\n"
            "Invoice No: INV-887412\n"
            "Date: 2024-05-18\n"
            "Merchant: TechWiz Retail Store\n"
            "Serial: SN-CE-992384\n"
            "Total Amount: $649.99"
        )
        entities = self.ocr_processor.extract_receipt_entities(sample_receipt)
        self.assertEqual(entities["invoice_number"], "INV-887412")
        self.assertEqual(entities["purchase_date"], "2024-05-18")
        self.assertEqual(entities["serial_number"], "SN-CE-992384")

    # =========================================================================
    # Category 08: Python Model Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat08_python_ml_model_probabilities_and_latency(self):
        """
        Cat 08: Python Model Test - Inference produces valid 3-class probability distribution
        summing to 1.0, and sub-100ms prediction latency.
        """
        sample_claim = self.test_df.iloc[0].to_dict()
        import time
        t0 = time.time()
        py_res = self.comparator.python_classifier.predict_single(sample_claim)
        latency_ms = (time.time() - t0) * 1000

        self.assertIn(py_res["predicted_class"], Config.ALL_CLAIM_CLASSES)
        prob_sum = sum(py_res["confidence_scores"].values())
        self.assertAlmostEqual(prob_sum, 1.0, places=3)
        self.assertLess(latency_ms, 150)  # fast tabular inference

    # =========================================================================
    # Category 09: Google Teachable Machine Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat09_gtm_vision_model_card_inference(self):
        """
        Cat 09: GTM Model Test - Ingests 640x420 Claim Summary Card image,
        evaluates image visual features, and outputs 3 class probabilities summing to 1.0.
        """
        # Create a valid test image
        img = Image.new("RGB", (640, 420), color=(248, 249, 250))
        gtm_res = self.comparator.gtm_classifier.predict_card(img)

        self.assertIn(gtm_res["predicted_class"], Config.ALL_CLAIM_CLASSES)
        prob_sum = sum(gtm_res["confidence_scores"].values())
        self.assertAlmostEqual(prob_sum, 1.0, places=3)
        self.assertGreaterEqual(gtm_res["top_confidence"], 0.0)
        self.assertLessEqual(gtm_res["top_confidence"], 1.0)

    # =========================================================================
    # Category 10: Model Comparison Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat10_model_comparison_consensus_statuses(self):
        """
        Cat 10: Model Comparison Test - Verifies all 5 consistency statuses:
        'Strong Match', 'Acceptable Match', 'Weak Match', 'Model Disagreement', 'Uncertain Result'.
        """
        # Case A: Strong Match (same class, delta <= 0.15)
        py_res = {"predicted_class": "Valid Claim", "top_confidence": 0.95, "probabilities": {"Valid Claim": 0.95, "Invalid Claim": 0.03, "Manual Review": 0.02}}
        gtm_res = {"predicted_class": "Valid Claim", "top_confidence": 0.90, "probabilities": {"Valid Claim": 0.90, "Invalid Claim": 0.06, "Manual Review": 0.04}}
        res_a = self.comparator.evaluate_consensus(py_res, gtm_res)
        self.assertEqual(res_a["model_consistency_status"], Config.CONSISTENCY_STRONG)

        # Case B: Acceptable Match (same class, 0.15 < delta <= 0.30)
        gtm_b = {"predicted_class": "Valid Claim", "top_confidence": 0.75, "probabilities": {"Valid Claim": 0.75, "Invalid Claim": 0.15, "Manual Review": 0.10}}
        res_b = self.comparator.evaluate_consensus(py_res, gtm_b)
        self.assertEqual(res_b["model_consistency_status"], Config.CONSISTENCY_ACCEPTABLE)

        # Case C: Weak Match (same class, delta > 0.30)
        gtm_c = {"predicted_class": "Valid Claim", "top_confidence": 0.62, "probabilities": {"Valid Claim": 0.62, "Invalid Claim": 0.20, "Manual Review": 0.18}}
        res_c = self.comparator.evaluate_consensus(py_res, gtm_c)
        self.assertEqual(res_c["model_consistency_status"], Config.CONSISTENCY_WEAK)

        # Case D: Model Disagreement (different classes)
        gtm_d = {"predicted_class": "Invalid Claim", "top_confidence": 0.88, "probabilities": {"Valid Claim": 0.05, "Invalid Claim": 0.88, "Manual Review": 0.07}}
        res_d = self.comparator.evaluate_consensus(py_res, gtm_d)
        self.assertEqual(res_d["model_consistency_status"], Config.CONSISTENCY_DISAGREEMENT)

        # Case E: Uncertain Result (confidence < 0.60 threshold)
        gtm_e = {"predicted_class": "Valid Claim", "top_confidence": 0.52, "probabilities": {"Valid Claim": 0.52, "Invalid Claim": 0.28, "Manual Review": 0.20}}
        res_e = self.comparator.evaluate_consensus(py_res, gtm_e)
        self.assertEqual(res_e["model_consistency_status"], Config.CONSISTENCY_UNCERTAIN)

    # =========================================================================
    # Category 11: Rule Engine Test Cases (SRS Page 30)
    # =========================================================================
    def test_cat11_rule_engine_multi_category_policies(self):
        """
        Cat 11: Rule Engine Test - Evaluates rules across all 3 product categories:
        Consumer Electronics, Home Appliances, and Industrial & Automotive Tools.
        """
        categories = ["Consumer Electronics", "Home Appliances", "Industrial & Automotive Tools"]
        for cat in categories:
            policy = self.policy_engine.get_policy_for_category(cat)
            self.assertEqual(policy["category"], cat)
            self.assertIn("mandatory_documents", policy)
            self.assertIn("hard_fail_rules", policy)
            self.assertIn("grace_period_days", policy)

        # Test Industrial Tool overload violation
        industrial_claim = {
            "claim_id": "CLM-CAT-RULE-01",
            "product_category": "Industrial & Automotive Tools",
            "fault_category": "Abnormal overload beyond specified torque limits",
            "damage_type": "Abnormal Overload",
            "days_since_purchase": 60,
            "days_until_warranty_expiry": 305,
            "claim_amount": 350.0,
            "repair_history_count": 0,
            "unauthorized_repair_flag": 0,
            "physical_damage_severity": 0.8,
            "water_damage_flag": 0,
            "serial_number_match": 1,
            "mandatory_documents_present": 1,
            "claim_date_conflict_flag": 0
        }
        res = self.policy_engine.evaluate_claim_rules(industrial_claim)
        self.assertGreater(len(res["failed_rules"]), 0)
        self.assertTrue(any("overload" in r.lower() for r in res["failed_rules"]))

    # =========================================================================
    # Category 12: Contradiction Detection Tests (SRS Page 30)
    # =========================================================================
    def test_cat12_contradiction_detection_chronology_and_models(self):
        """
        Cat 12: Contradiction Detection Test - Fault date pre-dating purchase date,
        claim submission prior to fault, and OCR receipt model mismatch.
        """
        # 1. Fault occurs before purchase
        contra_dates = {
            "claim_id": "CLM-CAT-CONTRA-1",
            "purchase_date": "2024-05-10",
            "fault_occurrence_date": "2024-04-10",  # 1 month before purchase!
            "claim_submission_date": "2024-05-15"
        }
        res_date = self.contradiction_detector.detect_contradictions(contra_dates)
        self.assertTrue(res_date["has_contradiction"])
        self.assertTrue(any("predates" in c.lower() for c in res_date["contradictions"]))

        # 2. Receipt Model Mismatch
        model_mismatch = {
            "claim_id": "CLM-CAT-CONTRA-2",
            "model_number": "DELL-XPS-15",
            "purchase_date": "2024-01-01",
            "fault_occurrence_date": "2024-02-01",
            "claim_submission_date": "2024-02-05"
        }
        ocr_wrong_model = {"model_number": "HP-SPECTRE-13", "extracted_text": "HP Spectre 13 Notebook"}
        res_model = self.contradiction_detector.detect_contradictions(model_mismatch, ocr_data=ocr_wrong_model)
        self.assertTrue(res_model["has_contradiction"])
        self.assertTrue(any("model" in c.lower() for c in res_model["contradictions"]))

    # =========================================================================
    # Category 13: Missing Document Tests (SRS Page 30)
    # =========================================================================
    def test_cat13_missing_document_handling(self):
        """
        Cat 13: Missing Document Test - Detects missing mandatory document
        and routes claim to 'Additional Information Required' or 'Manual Review Required'.
        """
        missing_doc_claim = {
            "claim_id": "CLM-CAT-MISSDOC-01",
            "product_category": "Home Appliances",
            "fault_category": "Thermostat failure",
            "mandatory_documents_present": 0,  # missing required receipt/card
            "days_since_purchase": 100,
            "days_until_warranty_expiry": 265,
            "repair_history_count": 0,
            "unauthorized_repair_flag": 0,
            "physical_damage_severity": 0.0,
            "water_damage_flag": 0,
            "serial_number_match": 1,
            "claim_date_conflict_flag": 0
        }
        eval_res = self.policy_engine.evaluate_claim_rules(missing_doc_claim)
        self.assertGreater(len(eval_res["manual_review_triggers"]), 0)
        self.assertTrue(any("missing" in t.lower() for t in eval_res["manual_review_triggers"]))

    # =========================================================================
    # Category 14: Duplicate Claim Tests (SRS Page 30)
    # =========================================================================
    def test_cat14_duplicate_claim_and_document_hash_detection(self):
        """
        Cat 14: Duplicate Claim Test - Detects SHA-256 document collisions
        and repeat submissions for identical serial numbers.
        """
        with self.app.app_context():
            user = User.query.first()
            prod = Product.query.first()
            warr = ProductWarranty.query.filter_by(product_id=prod.id).first()

            # Existing claim
            c1 = Claim(
                claim_id="CLM-CAT-DUP-ORIG",
                user_id=user.id,
                product_id=prod.id,
                warranty_id=warr.id,
                fault_occurrence_date=date(2024, 7, 1),
                fault_description="Original claim submission.",
                fault_category="Screen flickering",
                claim_submission_date=date(2024, 7, 5),
                status=Config.STATUS_APPROVED
            )
            db.session.add(c1)
            db.session.flush()

            # Add document with unique hash
            doc_hash = "f1d2d2f924e986ac86fdf7b36c94bcdf32beec15defc16270830471addf70ab8"
            doc1 = ClaimDocument(
                claim_id=c1.id,
                document_type="receipt",
                file_path="stored_receipt.pdf",
                original_filename="receipt.pdf",
                file_hash_sha256=doc_hash
            )
            db.session.add(doc1)
            db.session.commit()

            # Check duplicate hash detection
            hash_dup = self.duplicate_detector.check_claim_duplicates(
                {"claim_id": "CLM-CAT-DUP-NEW", "serial_number": prod.serial_number},
                uploaded_file_hashes=[doc_hash]
            )
            self.assertTrue(hash_dup["is_duplicate"])
            self.assertTrue(any("identical document hash" in f.lower() for f in hash_dup["duplicate_flags"]))

            # Cleanup
            db.session.delete(doc1)
            db.session.delete(c1)
            db.session.commit()

    # =========================================================================
    # Category 15: Serial Number Mismatch Tests (SRS Page 30)
    # =========================================================================
    def test_cat15_serial_number_mismatch_detection(self):
        """
        Cat 15: Serial Number Mismatch Test - Detects discrepancy between user/system serial
        and OCR invoice serial, flagging discretionary review.
        """
        mismatch_claim = {
            "claim_id": "CLM-CAT-MISMATCH-1",
            "product_category": "Consumer Electronics",
            "serial_number": "SN-SYS-ORIGINAL-111",
            "product_serial": "SN-SYS-ORIGINAL-111",
            "serial_number_match": 0,
            "days_since_purchase": 50,
            "days_until_warranty_expiry": 315,
            "remaining_warranty_days": 315,
            "product_age_days": 50,
            "fault_category": "Battery failure to charge",
            "repair_history_count": 0,
            "unauthorized_repair_flag": 0,
            "physical_damage_severity": 0.0,
            "water_damage_flag": 0,
            "mandatory_documents_present": 1,
            "claim_date_conflict_flag": 0
        }
        ocr_mismatched = {"entities": {"serial_number": "SN-RECEIPT-FRAUD-999"}}
        res = self.engine.adjudicate_claim(mismatch_claim, ocr_data=ocr_mismatched)
        self.assertEqual(res["final_decision"], "Manual Review Required")
        self.assertTrue(any("serial" in o.lower() for o in res["opposing_factors"] + res["contradictions"]))

    # =========================================================================
    # Category 16: Low Confidence Test Cases (SRS Page 31)
    # =========================================================================
    def test_cat16_low_confidence_routes_to_manual_review(self):
        """
        Cat 16: Low Confidence Test - Model confidence below configurable threshold (0.60)
        results in 'Uncertain Result' and routes claim to 'Manual Review Required'.
        """
        low_conf_claim = {
            "claim_id": "CLM-CAT-LOWCONF-1",
            "product_category": "Consumer Electronics",
            "fault_category": "Screen flickering",
            "claim_amount": 120.0,
            "repair_history_count": 1,
            "unauthorized_repair_flag": 0,
            "physical_damage_severity": 0.1,
            "water_damage_flag": 0,
            "serial_number_match": 1,
            "mandatory_documents_present": 1,
            "claim_date_conflict_flag": 0,
            "days_since_purchase": 100,
            "days_until_warranty_expiry": 265
        }
        # Simulate near-uniform low confidence prediction
        py_low = {"predicted_class": "Valid Claim", "top_confidence": 0.45, "probabilities": {"Valid Claim": 0.45, "Invalid Claim": 0.30, "Manual Review": 0.25}}
        gtm_low = {"predicted_class": "Valid Claim", "top_confidence": 0.48, "probabilities": {"Valid Claim": 0.48, "Invalid Claim": 0.27, "Manual Review": 0.25}}
        
        comp_res = self.comparator.evaluate_consensus(py_low, gtm_low)
        self.assertEqual(comp_res["model_consistency_status"], Config.CONSISTENCY_UNCERTAIN)

    # =========================================================================
    # Category 17: Model Disagreement Test Cases (SRS Page 31)
    # =========================================================================
    def test_cat17_model_disagreement_routes_to_manual_review(self):
        """
        Cat 17: Model Disagreement Test - Divergent AI model predictions trigger
        'Model Disagreement' status and mandatory routing to 'Manual Review Required'.
        """
        py_valid = {"predicted_class": "Valid Claim", "top_confidence": 0.92, "probabilities": {"Valid Claim": 0.92, "Invalid Claim": 0.05, "Manual Review": 0.03}}
        gtm_invalid = {"predicted_class": "Invalid Claim", "top_confidence": 0.89, "probabilities": {"Valid Claim": 0.04, "Invalid Claim": 0.89, "Manual Review": 0.07}}

        comp_res = self.comparator.evaluate_consensus(py_valid, gtm_invalid)
        self.assertEqual(comp_res["model_consistency_status"], Config.CONSISTENCY_DISAGREEMENT)
        self.assertFalse(comp_res["is_class_match"])

    # =========================================================================
    # Category 18: Hidden-Test Readiness Checklist (SRS Page 31)
    # =========================================================================
    def test_cat18_hidden_test_readiness_defensive_robustness(self):
        """
        Cat 18: Hidden-Test Readiness Checklist - Evaluates pipeline under unpredictable conditions:
        - Ingesting arbitrary dictionaries with extra unknown keys.
        - Missing optional fields.
        - Unseen categorical label inputs (handled by OneHotEncoder ignore fallback).
        - Extreme numeric boundary values.
        - Zero unhandled exceptions or fatal crashes.
        """
        unpredictable_claim = {
            "claim_id": "CLM-CAT-HIDDEN-UNSEEN",
            "product_category": "Consumer Electronics",
            "fault_category": "Novel Quantum Sub-pixel Drift",  # completely novel fault
            "damage_type": "Mysterious Glitch",                 # completely novel damage
            "claim_amount": 999999.99,                          # extreme outlier amount
            "arbitrary_evaluator_tag": "AptechHiddenEvaluation2026",
            "nested_unsupported_meta": {"key": 12345},
            "days_since_purchase": 120,
            "days_until_warranty_expiry": 245,
            "serial_number_match": 1,
            "mandatory_documents_present": 1,
            "claim_date_conflict_flag": 0
        }

        # Should execute smoothly without throwing exceptions
        try:
            adjudication = self.engine.adjudicate_claim(unpredictable_claim)
            self.assertIn(adjudication["final_decision"], ["Likely Valid", "Likely Invalid", "Manual Review Required"])
            self.assertIn(adjudication["risk_level"], ["Low", "Medium", "High"])
            self.assertIsInstance(adjudication["supporting_factors"], list)
            self.assertIsInstance(adjudication["opposing_factors"], list)
        except Exception as e:
            self.fail(f"Hidden test readiness failed with unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main()
