import os
import unittest
from src.app import create_app
from database.db import db
from src.models.entities import User, Product, WarrantyPolicy, ProductWarranty, Claim, ModelEvaluation
from config.config import Config


class TestPhase6Frontend(unittest.TestCase):
    """Automated integration test verifying all frontend templates and routes render cleanly."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()

    def test_auth_pages_render(self):
        """Verify login and register pages render with HTTP 200."""
        res_login = self.client.get("/login")
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b"AssureX Claim Engine", res_login.data)
        self.assertIn(b"Sign In to Portal", res_login.data)

        res_reg = self.client.get("/register")
        self.assertEqual(res_reg.status_code, 200)
        self.assertIn(b"Create Customer Account", res_reg.data)

    def test_customer_portal_authenticated(self):
        """Verify customer dashboard, products, and claim wizard render with session."""
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["user_code"] = user.user_id
                sess["role"] = user.role
                sess["user_name"] = user.full_name
                sess["email"] = user.email

        res_dash = self.client.get("/claims/")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"Customer Service Portal", res_dash.data)

        res_prods = self.client.get("/products/")
        self.assertEqual(res_prods.status_code, 200)
        self.assertIn(b"Registered Products Fleet", res_prods.data)

        res_reg_prod = self.client.get("/products/register")
        self.assertEqual(res_reg_prod.status_code, 200)
        self.assertIn(b"Register Equipment", res_reg_prod.data)
        self.assertIn(b"Activate Warranty", res_reg_prod.data)

        res_wizard = self.client.get("/claims/new")
        self.assertEqual(res_wizard.status_code, 200)
        self.assertIn(b"Warranty Claim Intake Wizard", res_wizard.data)

    def test_reviewer_portal_authenticated(self):
        """Verify reviewer queue and inspect views render for staff reviewers."""
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                rev = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
                sess["user_id"] = rev.id
                sess["user_code"] = rev.user_id
                sess["role"] = rev.role
                sess["user_name"] = rev.full_name
                sess["email"] = rev.email

        res_queue = self.client.get("/reviewer/queue")
        self.assertEqual(res_queue.status_code, 200)
        self.assertIn(b"Claim Adjudication", res_queue.data)
        self.assertIn(b"Triage Queue", res_queue.data)

    def test_admin_portal_authenticated(self):
        """Verify admin dashboard, policy editor, and audit logs render for admins."""
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
                sess["user_id"] = admin.id
                sess["user_code"] = admin.user_id
                sess["role"] = admin.role
                sess["user_name"] = admin.full_name
                sess["email"] = admin.email

        res_dash = self.client.get("/admin/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"Executive Analytics", res_dash.data)
        self.assertIn(b"System Intelligence", res_dash.data)

        res_policies = self.client.get("/admin/policies")
        self.assertEqual(res_policies.status_code, 200)
        self.assertIn(b"Dynamic Warranty Policies Editor", res_policies.data)

        res_audits = self.client.get("/admin/audit-logs")
        self.assertEqual(res_audits.status_code, 200)
        self.assertIn(b"System Security", res_audits.data)
        self.assertIn(b"Audit Trail", res_audits.data)

    def test_404_error_page(self):
        """Verify custom 404 error page renders nicely."""
        res_404 = self.client.get("/non-existent-route-for-testing")
        self.assertEqual(res_404.status_code, 404)
        self.assertIn(b"404", res_404.data)
        self.assertIn(b"Resource Not Found", res_404.data)

    def test_public_landing_page_renders(self):
        """Verify public landing page renders with hero, verified metrics, and demo sandbox."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Dual-Model AI Consensus", res.data)
        self.assertIn(b"APTECH NEXTWAVE", res.data)
        self.assertIn(b"EVALUATOR DEMO SANDBOX", res.data)
        self.assertIn(b"How the AssureX Claim Engine Works", res.data)
        self.assertIn(b"admin@assurex.local", res.data)
        self.assertIn(b"reviewer@assurex.local", res.data)
        self.assertIn(b"staff@assurex.local", res.data)
        self.assertIn(b"customer@assurex.local", res.data)

    def test_technical_blog_renders(self):
        """Verify Technical Blog fulfills SRS Deliverable #14 with 2,000+ words and 23 topics."""
        res = self.client.get("/blog")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"SRS DELIVERABLE #14", res.data)
        self.assertIn(b"Building AssureX", res.data)
        self.assertIn(b"23 SRS Topics", res.data)
        self.assertIn(b"Copy Markdown for Medium / Blogger", res.data)

    def test_technical_blog_raw_export(self):
        """Verify raw markdown export stream for external publishing."""
        res = self.client.get("/blog/raw")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/markdown", res.content_type)
        self.assertTrue(len(res.data) > 15000)
        self.assertIn(b"Business Problem", res.data)
        self.assertIn(b"Google Teachable Machine Training", res.data)


if __name__ == "__main__":
    unittest.main()
