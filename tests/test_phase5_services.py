import os
import unittest
from datetime import datetime, timezone, timedelta
from src.app import create_app
from database.db import db
from src.models.entities import User, Product, WarrantyPolicy, ProductWarranty, Claim, ModelEvaluation, AuditLog
from src.services.report_generator import get_pdf_generator
from src.services.export_service import DataExportService
from config.config import Config


class TestPhase5Services(unittest.TestCase):
    """Unit tests for Phase 5 services: PDF generator, CSV export, and lifecycle state tracking."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()

    def test_pdf_report_generation(self):
        """Req xliv: Verify PDF report generation produces valid binary PDF document."""
        with self.app.app_context():
            user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            product = Product.query.first()
            warranty = ProductWarranty.query.filter_by(product_id=product.id).first()

            test_claim = Claim(
                claim_id="CLM-UNIT-TEST-PDF",
                user_id=user.id,
                product_id=product.id,
                warranty_id=warranty.id,
                fault_occurrence_date=datetime.now(timezone.utc).date() - timedelta(days=5),
                fault_description="Unit test fault description for PDF generation.",
                fault_category="Screen Flickering",
                claim_submission_date=datetime.now(timezone.utc).date(),
                status=Config.STATUS_APPROVED,
                final_decision=Config.CLAIM_CLASS_VALID,
                decision_reason="Dual AI strong match with verified active warranty.",
                risk_level="Low"
            )
            db.session.add(test_claim)
            db.session.flush()

            eval_rec = ModelEvaluation(
                claim_id=test_claim.id,
                python_predicted_class=Config.CLAIM_CLASS_VALID,
                python_conf_valid=0.98,
                python_conf_invalid=0.01,
                python_conf_manual=0.01,
                gtm_predicted_class=Config.CLAIM_CLASS_VALID,
                gtm_conf_valid=0.95,
                gtm_conf_invalid=0.03,
                gtm_conf_manual=0.02,
                is_class_match=True,
                top_confidence_difference=0.03,
                model_consistency_status=Config.CONSISTENCY_STRONG
            )
            db.session.add(eval_rec)
            db.session.commit()

            # Generate PDF
            pdf_gen = get_pdf_generator()
            pdf_bytes = pdf_gen.generate_pdf(test_claim)

            self.assertIsNotNone(pdf_bytes)
            self.assertGreater(len(pdf_bytes), 1000)
            # Verify valid PDF signature
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

            # Cleanup
            db.session.delete(test_claim)
            db.session.commit()

    def test_csv_data_export(self):
        """Req xlv: Verify data export service exports valid CSV strings."""
        with self.app.app_context():
            claims = Claim.query.all()
            products = Product.query.all()

            csv_claims = DataExportService.export_claims_csv(claims)
            csv_products = DataExportService.export_products_csv(products)

            self.assertIn("Claim ID,Claimant Name,Product Name", csv_claims)
            self.assertIn("Product ID,Owner,Product Name", csv_products)

    def test_status_transitions_tracking(self):
        """Req xxxviii: Verify all 8 statuses are supported and trackable."""
        self.assertEqual(len(Config.ALL_CLAIM_STATUSES), 8)
        expected_statuses = [
            "Draft", "Submitted", "Under Evaluation", "Additional Information Required",
            "Manual Review", "Approved", "Rejected", "Closed"
        ]
        for status in expected_statuses:
            self.assertIn(status, Config.ALL_CLAIM_STATUSES)


if __name__ == "__main__":
    unittest.main()
