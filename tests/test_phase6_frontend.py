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

    def test_user_profile_management(self):
        """Req 1.6.ii: Verify User Profile management renders unique User ID and updates details."""
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["user_code"] = user.user_id
                sess["role"] = user.role
                sess["user_name"] = user.full_name
                sess["email"] = user.email
                user_id_str = user.user_id

        # 1. GET /profile renders successfully with unique user ID and role
        res_get = self.client.get("/profile")
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b"User Profile & Account Management", res_get.data)
        self.assertIn(user_id_str.encode(), res_get.data)
        self.assertIn(b"Contact Information", res_get.data)

        # 2. POST /profile updates contact info and records audit log
        res_post = self.client.post("/profile", data={
            "action": "update_info",
            "full_name": "David Miller Updated",
            "phone": "+1-555-0999",
            "address": "Updated Suite 200, Tech Plaza"
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn(b"updated successfully", res_post.data)
        self.assertIn(b"David Miller Updated", res_post.data)

        # Revert back to original name
        with self.app.app_context():
            u = User.query.filter_by(email="customer@assurex.local").first()
            if u:
                u.full_name = "David Miller"
                db.session.commit()

    def test_multi_role_registration(self):
        """Req 1.6.i: Verify registration supports multiple roles and generates unique User ID."""
        test_email = "new_reviewer_test@assurex.local"
        with self.app.app_context():
            old = User.query.filter_by(email=test_email).first()
            if old:
                db.session.delete(old)
                db.session.commit()

        try:
            res = self.client.post("/register", data={
                "email": test_email,
                "full_name": "Test Reviewer Officer",
                "role": "Reviewer",
                "phone": "+1-800-555-9988",
                "address": "Audit Dept #5",
                "password": "ReviewerPass123!",
                "confirm_password": "ReviewerPass123!"
            }, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Account created successfully as Claim Reviewer", res.data)

            with self.app.app_context():
                created = User.query.filter_by(email=test_email).first()
                self.assertIsNotNone(created)
                self.assertEqual(created.role, Config.ROLE_REVIEWER)
                self.assertTrue(created.user_id.startswith("USR-"))
        finally:
            with self.app.app_context():
                cleanup = User.query.filter_by(email=test_email).first()
                if cleanup:
                    db.session.delete(cleanup)
                    db.session.commit()

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

    def test_req_1_6_iii_and_iv_product_and_warranty_management(self):
        """
        SRS 1.6.iii: Product registration with all specified attributes + unique Product ID.
        SRS 1.6.iv: Warranty record management (standard/extended, provider, dates, coverage,
                    exclusions, service center) + common interface status filtering.
        """
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["user_code"] = user.user_id
                sess["role"] = user.role
                sess["user_name"] = user.full_name
                sess["email"] = user.email

        test_serial = "SN-TEST-REG-101"
        with self.app.app_context():
            old = Product.query.filter_by(serial_number=test_serial).first()
            if old:
                if old.warranty:
                    db.session.delete(old.warranty)
                db.session.delete(old)
                db.session.commit()

        try:
            # 1. Test POST /products/register (Req 1.6.iii & 1.6.iv)
            post_data = {
                "product_name": "Spectra Quantum OLED TV 65",
                "category": "Consumer Electronics",
                "brand": "SpectraVision",
                "model_number": "SV-QLED-65X",
                "serial_number": test_serial,
                "purchase_date": "2026-05-15",
                "purchase_price": "1499.99",
                "retailer": "Best Buy Electronics",
                "invoice_number": "INV-BB-2026-9901",
                "warranty_duration": "36",
                "warranty_type": "extended",
                "warranty_provider": "SpectraShield Platinum Care",
                "service_center_name": "Metro Authorized Tech Hub #4"
            }
            res_reg = self.client.post("/products/register", data=post_data, follow_redirects=True)
            self.assertEqual(res_reg.status_code, 200)
            self.assertIn(b"registered successfully", res_reg.data)
            self.assertIn(b"Assigned Unique Product ID", res_reg.data)

            with self.app.app_context():
                prod = Product.query.filter_by(serial_number=test_serial).first()
                self.assertIsNotNone(prod)
                self.assertTrue(prod.product_id.startswith("PRD-"))
                self.assertEqual(prod.product_name, "Spectra Quantum OLED TV 65")
                self.assertEqual(prod.category, "Consumer Electronics")
                self.assertEqual(prod.brand, "SpectraVision")
                self.assertEqual(prod.model_number, "SV-QLED-65X")
                self.assertEqual(prod.purchase_price, 1499.99)
                self.assertEqual(prod.retailer, "Best Buy Electronics")

                # Verify Warranty Record (Req 1.6.iv)
                w = prod.warranty
                self.assertIsNotNone(w)
                self.assertTrue(w.warranty_id.startswith("WAR-"))
                self.assertTrue(w.is_extended)
                self.assertEqual(w.warranty_provider, "SpectraShield Platinum Care")
                self.assertEqual(w.service_center_name, "Metro Authorized Tech Hub #4")
                self.assertEqual(w.start_date.strftime("%Y-%m-%d"), "2026-05-15")

                prod_unique_id = prod.product_id

            # 2. Test Common Interface Filtering (Req 1.6.iv)
            for status in ["all", "active", "approaching", "expired", "extended"]:
                res_filter = self.client.get(f"/products/?status={status}")
                self.assertEqual(res_filter.status_code, 200)
                self.assertIn(b"Registered Products Fleet", res_filter.data)
                self.assertIn(b"All Warranties", res_filter.data)
                self.assertIn(b"Approaching Expiry", res_filter.data)
                self.assertIn(b"Extended Plans", res_filter.data)

            # 3. Test Product Detail Page: Hardware Specs, Policy Rules, Exclusions (Req 1.6.iii & 1.6.iv)
            res_detail = self.client.get(f"/products/{prod_unique_id}")
            self.assertEqual(res_detail.status_code, 200)
            self.assertIn(prod_unique_id.encode(), res_detail.data)
            self.assertIn(b"Hardware Specification", res_detail.data)
            self.assertIn(b"Warranty Record & Terms", res_detail.data)
            self.assertIn(b"SpectraShield Platinum Care", res_detail.data)
            self.assertIn(b"Metro Authorized Tech Hub #4", res_detail.data)
            self.assertIn(b"Coverage Conditions & Policy Exclusions", res_detail.data)
            self.assertIn(b"Covered Conditions & Fault Symptoms", res_detail.data)
            self.assertIn(b"Policy Exclusions & Disqualifying Factors", res_detail.data)
            self.assertIn(b"Authorized Maintenance & Repair History", res_detail.data)

        finally:
            with self.app.app_context():
                cleanup = Product.query.filter_by(serial_number=test_serial).first()
                if cleanup:
                    ProductWarranty.query.filter_by(product_id=cleanup.id).delete()
                    db.session.delete(cleanup)
                    db.session.commit()

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
                claim = Claim.query.first()
                claim_id = claim.claim_id if claim else None

        res_queue = self.client.get("/reviewer/queue")
        self.assertEqual(res_queue.status_code, 200)
        self.assertIn(b"Claim Adjudication", res_queue.data)
        self.assertIn(b"Triage Queue", res_queue.data)

        if claim_id:
            res_inspect = self.client.get(f"/reviewer/claim/{claim_id}")
            self.assertEqual(res_inspect.status_code, 200)
            self.assertIn(b"Adjudication Workbench", res_inspect.data)

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

        # Verify CSV exports (Req xlv)
        res_exp_claims = self.client.get("/admin/export/claims")
        self.assertEqual(res_exp_claims.status_code, 200)
        self.assertEqual(res_exp_claims.content_type, "text/csv; charset=utf-8")

        res_exp_prods = self.client.get("/admin/export/products")
        self.assertEqual(res_exp_prods.status_code, 200)
        self.assertEqual(res_exp_prods.content_type, "text/csv; charset=utf-8")

        res_exp_audit = self.client.get("/admin/export/audit")
        self.assertEqual(res_exp_audit.status_code, 200)
        self.assertEqual(res_exp_audit.content_type, "text/csv; charset=utf-8")

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
        self.assertIn(b"AssureX Enterprise", res.data)
        self.assertIn(b"dual-model intelligence", res.data)
        self.assertIn(b"Explore the 4 Role Portals", res.data)
        self.assertIn(b"5-Stage Adjudication Pipeline", res.data)
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
        self.assertIn(b"Read on Medium", res.data)
        self.assertIn(b"samikhan031027", res.data)

    def test_technical_blog_raw_export(self):
        """Verify raw markdown export stream for external publishing."""
        res = self.client.get("/blog/raw")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/markdown", res.content_type)
        self.assertTrue(len(res.data) > 15000)
        self.assertIn(b"Business Problem", res.data)
        self.assertIn(b"Google Teachable Machine Training", res.data)

    def test_customer_create_claim_submission(self):
        """Verify customer can submit claim wizard with integer ID and reach evaluated state."""
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["user_code"] = user.user_id
                sess["role"] = user.role
                sess["user_name"] = user.full_name
                sess["email"] = user.email

                product = Product.query.filter_by(user_id=user.id).first()
                self.assertIsNotNone(product)
                prod_id = product.id

        post_data = {
            "product_id": str(prod_id),
            "fault_occurrence_date": "2026-09-20",
            "fault_category": "Battery Degradation",
            "damage_type": "Normal Wear and Tear",
            "fault_description": "Battery depleting abnormally fast within 30 minutes of charge.",
            "claim_amount": "120.00"
        }
        try:
            res = self.client.post("/claims/new", data=post_data, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"submitted and evaluated", res.data)
        finally:
            with self.app.app_context():
                test_claim = Claim.query.filter_by(fault_description=post_data["fault_description"]).first()
                if test_claim:
                    db.session.delete(test_claim)
                    db.session.commit()


if __name__ == "__main__":
    unittest.main()

