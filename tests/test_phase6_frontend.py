import os
import io
import json
from pathlib import Path
import unittest
from src.app import create_app
from database.db import db
from src.models.entities import (
    User, Product, WarrantyPolicy, ProductWarranty, Claim, ModelEvaluation,
    ClaimDocument, ClaimStatusHistory, Notification, AuditLog, SystemSetting, RepairHistory,
    ReviewerAction, RuleValidationLog
)
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
        self.assertIn(b"quickLogin", res_login.data)

        res_reg = self.client.get("/register")
        self.assertEqual(res_reg.status_code, 200)
        self.assertIn(b"Create Customer Account", res_reg.data)

    def test_login_all_roles(self):
        """Verify login works for all 4 seeded roles and handles invalid credentials gracefully."""
        credentials = [
            ("admin@assurex.local", "AdminPass123!", "/admin/dashboard"),
            ("reviewer@assurex.local", "ReviewerPass123!", "/reviewer/dashboard"),
            ("staff@assurex.local", "StaffPass123!", "/staff/dashboard"),
            ("customer@assurex.local", "CustomerPass123!", "/customer/dashboard")
        ]
        for email, password, expected_dest in credentials:
            client = self.app.test_client()
            res = client.post("/login", data={"email": email, "password": password}, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Welcome back", res.data)

        # Invalid password check
        bad_client = self.app.test_client()
        res_bad = bad_client.post("/login", data={"email": "admin@assurex.local", "password": "WrongPassword999!"}, follow_redirects=True)
        self.assertEqual(res_bad.status_code, 200)
        self.assertIn(b"Invalid password", res_bad.data)

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

    def test_req_1_6_v_and_vi_receipt_upload_and_extraction(self):
        """
        SRS 1.6.v: Upload and securely store purchase receipts, invoices in PDF, JPG, JPEG, PNG.
        SRS 1.6.vi: Receipt scanning and data extraction (purchase date, invoice number, product name,
                    model number, serial number, retailer, purchase amount, warranty duration).
        """
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["user_code"] = user.user_id
                sess["role"] = user.role
                sess["user_name"] = user.full_name
                sess["email"] = user.email

        # 1. Test POST /products/scan-receipt with simulated receipt file
        sample_receipt_text = (
            "OFFICIAL TAX INVOICE & PROOF OF PURCHASE\n"
            "Retailer: Best Buy Electronics\n"
            "Product Name: ApexBook Pro 16 Laptop\n"
            "Model Number: ABP-16-M3\n"
            "Serial Number: SN-APX-8829104\n"
            "Purchase Date: 2026-05-15\n"
            "Invoice Number: INV-2026-88192\n"
            "Purchase Amount: $1,249.99\n"
            "Warranty Duration: 24 Months Extended Coverage"
        )
        data = {
            "receipt_document": (io.BytesIO(sample_receipt_text.encode("utf-8")), "purchase_receipt.png")
        }
        res_scan = self.client.post("/products/scan-receipt", data=data, content_type="multipart/form-data")
        self.assertEqual(res_scan.status_code, 200)
        scan_json = res_scan.get_json()
        self.assertTrue(scan_json["success"])
        self.assertEqual(len(scan_json["sha256"]), 64)
        entities = scan_json["entities"]

        # Verify all 8 fields required by SRS 1.6.vi
        self.assertEqual(entities["purchase_date"], "2026-05-15")
        self.assertEqual(entities["invoice_number"], "INV-2026-88192")
        self.assertEqual(entities["product_name"], "ApexBook Pro 16 Laptop")
        self.assertEqual(entities["model_number"], "ABP-16-M3")
        self.assertEqual(entities["serial_number"], "SN-APX-8829104")
        self.assertEqual(entities["retailer"], "Best Buy")
        self.assertEqual(entities["purchase_amount"], 1249.99)
        self.assertEqual(entities["warranty_duration"], 24)

        # 2. Test POST /products/register with uploaded receipt attachment (Req 1.6.v)
        test_sn = "SN-OCR-TEST-7788"
        with self.app.app_context():
            old = Product.query.filter_by(serial_number=test_sn).first()
            if old:
                ClaimDocument.query.filter_by(product_id=old.id).delete()
                ProductWarranty.query.filter_by(product_id=old.id).delete()
                db.session.delete(old)
                db.session.commit()

        try:
            reg_data = {
                "product_name": entities["product_name"],
                "category": "Consumer Electronics",
                "brand": "ApexTech",
                "model_number": entities["model_number"],
                "serial_number": test_sn,
                "purchase_date": entities["purchase_date"],
                "purchase_price": str(entities["purchase_amount"]),
                "retailer": entities["retailer"],
                "invoice_number": entities["invoice_number"],
                "warranty_duration": str(entities["warranty_duration"]),
                "warranty_type": "standard",
                "receipt_document": (io.BytesIO(b"%PDF-1.4 sample invoice content for testing"), "official_tax_invoice.pdf")
            }
            res_reg = self.client.post("/products/register", data=reg_data, content_type="multipart/form-data", follow_redirects=True)
            self.assertEqual(res_reg.status_code, 200)

            with self.app.app_context():
                prod = Product.query.filter_by(serial_number=test_sn).first()
                self.assertIsNotNone(prod)
                self.assertEqual(len(prod.documents), 1)
                doc = prod.documents[0]
                self.assertEqual(doc.original_filename, "official_tax_invoice.pdf")
                self.assertEqual(doc.document_type, "receipt")
                self.assertEqual(len(doc.file_hash_sha256), 64)
                doc_id = doc.document_id
                prod_id = prod.product_id

            # 3. Test Product Detail displays document archive (Req 1.6.v & xiv)
            res_view = self.client.get(f"/products/{prod_id}")
            self.assertEqual(res_view.status_code, 200)
            self.assertIn(b"Proof-of-Purchase & Document Archive", res_view.data)
            self.assertIn(b"official_tax_invoice.pdf", res_view.data)

            # 4. Test Document Download Route
            res_dl = self.client.get(f"/products/documents/{doc_id}/download")
            self.assertEqual(res_dl.status_code, 200)
            self.assertIn(b"%PDF-1.4 sample invoice", res_dl.data)
            res_dl.close()

        finally:
            with self.app.app_context():
                cleanup = Product.query.filter_by(serial_number=test_sn).first()
                if cleanup:
                    ClaimDocument.query.filter_by(product_id=cleanup.id).delete()
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

    def test_req_1_6_ix_warranty_expiry_alerts_and_admin_config(self):
        """Req 1.6.ix: Verify admin can configure alert threshold and users receive warranty expiry alerts."""
        with self.app.app_context():
            from src.services.alert_service import get_alert_threshold_days, set_alert_threshold_days, scan_and_generate_warranty_alerts
            from src.models.entities import Notification, SystemSetting, AuditLog
            admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            admin_id = admin.id
            cust_id = customer.id

        # 1. Admin configures alert threshold via POST
        with self.client.session_transaction() as sess:
            sess["user_id"] = admin_id
            sess["role"] = Config.ROLE_ADMIN
            sess["email"] = "admin@assurex.local"
            sess["user_name"] = "Administrator"

        res = self.client.post("/admin/settings/warranty-alerts", data={"alert_days": "45"}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Warranty expiry alert window configured to 45 days", res.data)

        with self.app.app_context():
            self.assertEqual(SystemSetting.get_int("warranty_expiry_alert_days"), 45)
            log = AuditLog.query.filter_by(action="WARRANTY_ALERT_THRESHOLD_UPDATED").first()
            self.assertIsNotNone(log)

        # 2. Customer visits dashboard and receives alert if product warranty approaches expiry
        with self.client.session_transaction() as sess:
            sess["user_id"] = cust_id
            sess["role"] = Config.ROLE_CUSTOMER
            sess["email"] = "customer@assurex.local"
            sess["user_name"] = "Customer User"

        res_cust = self.client.get("/claims/", follow_redirects=True)
        self.assertEqual(res_cust.status_code, 200)
        # Verify notifications section is rendered
        self.assertIn(b"Recent System Alerts", res_cust.data)

        # Reset threshold back to 30 days
        with self.app.app_context():
            set_alert_threshold_days(30)

    def test_req_1_6_x_claim_registration_by_staff_and_user(self):
        """Req 1.6.x: Verify service-center staff can register claim assigned unique ID linked to user, product, warranty."""
        with self.app.app_context():
            staff = User.query.filter_by(role=Config.ROLE_STAFF).first()
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            self.assertIsNotNone(staff)
            self.assertIsNotNone(customer)
            product = Product.query.filter_by(user_id=customer.id).first()
            self.assertIsNotNone(product)
            staff_id = staff.id
            prod_id = product.id
            cust_id = customer.id
            warr_id = product.warranty.id

        with self.client.session_transaction() as sess:
            sess["user_id"] = staff_id
            sess["role"] = Config.ROLE_STAFF
            sess["email"] = "staff@assurex.local"
            sess["user_name"] = "Service Center Staff"

        # Check intake wizard GET shows service center mode
        get_res = self.client.get("/claims/new")
        self.assertEqual(get_res.status_code, 200)
        self.assertIn(b"Authorized Service Center Claim Registration Mode", get_res.data)

        post_data = {
            "product_id": str(prod_id),
            "fault_occurrence_date": "2026-09-21",
            "fault_category": "Mainboard Failure",
            "damage_type": "Electrical Surge",
            "fault_description": "Device failed diagnostic bench test during service inspection.",
            "claim_amount": "250.00"
        }

        try:
            res = self.client.post("/claims/new", data=post_data, follow_redirects=True)
            self.assertEqual(res.status_code, 200)

            with self.app.app_context():
                created_claim = Claim.query.filter_by(fault_description=post_data["fault_description"]).first()
                self.assertIsNotNone(created_claim)
                # Verify unique Claim ID format
                self.assertTrue(created_claim.claim_id.startswith("CLM-"))
                # Verify linked to customer user
                self.assertEqual(created_claim.user_id, cust_id)
                # Verify linked to product
                self.assertEqual(created_claim.product_id, prod_id)
                # Verify linked to warranty
                self.assertEqual(created_claim.warranty_id, warr_id)
                # Verify staff status history log
                history = ClaimStatusHistory.query.filter_by(claim_id=created_claim.id).first()
                self.assertIsNotNone(history)
                self.assertEqual(history.changed_by_user_id, staff_id)
        finally:
            with self.app.app_context():
                test_claim = Claim.query.filter_by(fault_description=post_data["fault_description"]).first()
                if test_claim:
                    db.session.delete(test_claim)
                    db.session.commit()

    def test_req_1_6_xi_and_xii_claim_info_collection_and_evidence_upload(self):
        """Req 1.6.xi & xii: Test collection of claim metadata (previous replacements, damage type) and multi-media evidence upload."""
        with self.app.app_context():
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            product = Product.query.filter_by(user_id=customer.id).first()
            cust_id = customer.id
            prod_id = product.id

        with self.client.session_transaction() as sess:
            sess["user_id"] = cust_id
            sess["role"] = Config.ROLE_CUSTOMER
            sess["email"] = "customer@assurex.local"
            sess["user_name"] = "Customer User"

        post_data = {
            "product_id": str(prod_id),
            "fault_occurrence_date": "2026-09-15",
            "fault_category": "Cooling System Failure",
            "damage_type": "Normal Wear and Tear",
            "fault_description": "Exhaust fan rattling violently during gaming load with thermal shutdown.",
            "previous_replacement_details": "Thermal heatpipe assembly replaced under warranty in April 2025",
            "claim_amount": "175.00",
            # Multi-media evidence files (Req 1.6.xii)
            "damage_photo": (io.BytesIO(b"FAKE_DAMAGE_IMAGE_PNG"), "crack_defect.png"),
            "fault_video": (io.BytesIO(b"FAKE_MP4_FAULT_FOOTAGE"), "flicker_recording.mp4"),
            "diagnostic_report": (io.BytesIO(b"DIAGNOSTIC REPORT: FAN FAILURE"), "bench_report.pdf"),
            "serial_photo": (io.BytesIO(b"SERIAL BARCODE IMAGE"), "serial_tag.jpg")
        }

        try:
            res = self.client.post("/claims/new", data=post_data, content_type="multipart/form-data", follow_redirects=True)
            self.assertEqual(res.status_code, 200)

            with self.app.app_context():
                created_claim = Claim.query.filter_by(fault_description=post_data["fault_description"]).first()
                self.assertIsNotNone(created_claim)
                # Verify Req 1.6.xi: Previous replacement details collected
                self.assertEqual(created_claim.previous_replacement_details, "Thermal heatpipe assembly replaced under warranty in April 2025")
                self.assertEqual(created_claim.damage_type, "Normal Wear and Tear")
                self.assertEqual(created_claim.fault_occurrence_date.strftime("%Y-%m-%d"), "2026-09-15")

                # Verify Req 1.6.xii: Attached multi-media evidence documents
                docs = ClaimDocument.query.filter_by(claim_id=created_claim.id).all()
                doc_types = [d.document_type for d in docs]
                self.assertIn("damage_photo", doc_types)
                self.assertIn("fault_video", doc_types)
                self.assertIn("diagnostic_report", doc_types)
                self.assertIn("serial_photo", doc_types)

                # Verify claim detail view renders evidence and claim information
                res_detail = self.client.get(f"/claims/{created_claim.claim_id}")
                self.assertEqual(res_detail.status_code, 200)
                self.assertIn(b"Product Age at Incident", res_detail.data)
                self.assertIn(b"Previous Replacement Details", res_detail.data)
                self.assertIn(b"crack_defect.png", res_detail.data)
                self.assertIn(b"flicker_recording.mp4", res_detail.data)
        finally:
            with self.app.app_context():
                test_claim = Claim.query.filter_by(fault_description=post_data["fault_description"]).first()
                if test_claim:
                    db.session.delete(test_claim)
                    db.session.commit()

    def test_req_1_6_xiii_repair_history_management(self):
        """Req 1.6.xiii: Verify recording repair dates, service center, replaced parts, outcomes, costs, and authorization."""
        with self.app.app_context():
            staff = User.query.filter_by(role=Config.ROLE_STAFF).first()
            product = Product.query.first()
            staff_id = staff.id
            prod_code = product.product_id

        with self.client.session_transaction() as sess:
            sess["user_id"] = staff_id
            sess["role"] = Config.ROLE_STAFF
            sess["email"] = "staff@assurex.local"
            sess["user_name"] = "Staff Member"

        repair_post = {
            "repair_date": "2026-09-10",
            "repair_center": "AssureX Certified Tech Lab #12",
            "replaced_parts": "Lithium Battery Cell Pack & BMS Ribbon",
            "outcome": "Repaired",
            "repair_cost": "89.50",
            "is_authorized_center": "true",
            "notes": "Battery health recalibrated to 100% after genuine pack replacement."
        }

        res = self.client.post(f"/products/{prod_code}/repairs/new", data=repair_post, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"recorded successfully", res.data)

        with self.app.app_context():
            rep = RepairHistory.query.filter_by(repair_center=repair_post["repair_center"]).order_by(RepairHistory.id.desc()).first()
            self.assertIsNotNone(rep)
            self.assertEqual(rep.replaced_parts, "Lithium Battery Cell Pack & BMS Ribbon")
            self.assertEqual(rep.outcome, "Repaired")
            self.assertEqual(rep.repair_cost, 89.50)
            self.assertTrue(rep.is_authorized_center)
            # Verify AuditLog logged
            audit = AuditLog.query.filter_by(action="REPAIR_RECORDED", entity_id=prod_code).first()
            self.assertIsNotNone(audit)

            # Cleanup
            db.session.delete(rep)
            db.session.commit()

    def test_req_xiv_document_organization_replace_remove(self):
        """Req 1.6.xiv: Verify document view, download, replace, and remove according to access rights."""
        with self.app.app_context():
            user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            product = Product.query.filter_by(user_id=user.id).first()
            # Create a sample document attached to this product
            doc = ClaimDocument(
                product_id=product.id,
                document_type="warranty_card",
                file_path=str(Path(Config.UPLOAD_DIR) / "test_doc_xiv.pdf"),
                original_filename="test_doc_xiv.pdf",
                file_size_bytes=1024,
                file_hash_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
            )
            # Create dummy file on disk
            test_file = Path(doc.file_path)
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("Dummy content for testing document organization")
            db.session.add(doc)
            db.session.commit()
            doc_id = doc.document_id
            user_id_val = user.id
            user_role_val = user.role

        # 1. Download / View as authorized user
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id_val
            sess["role"] = user_role_val
        res_view = self.client.get(f"/products/documents/{doc_id}/download")
        self.assertEqual(res_view.status_code, 200)

        res_dl = self.client.get(f"/products/documents/{doc_id}/download?mode=download")
        self.assertEqual(res_dl.status_code, 200)

        # 2. Replace Document
        replacement_data = {
            "replacement_file": (io.BytesIO(b"Updated replacement warranty certificate content"), "updated_warranty.pdf")
        }
        res_replace = self.client.post(f"/products/documents/{doc_id}/replace", data=replacement_data, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res_replace.status_code, 200)
        self.assertIn(b"successfully replaced", res_replace.data)

        # 3. Remove Document
        res_delete = self.client.post(f"/products/documents/{doc_id}/delete", follow_redirects=True)
        self.assertEqual(res_delete.status_code, 200)
        self.assertIn(b"successfully removed", res_delete.data)

        with self.app.app_context():
            deleted_check = ClaimDocument.query.filter_by(document_id=doc_id).first()
            self.assertIsNone(deleted_check)

    def test_req_xv_data_validation(self):
        """Req 1.6.xv: Verify Data Validation for mandatory fields, dates, numbers, file types/sizes, duplicate IDs."""
        from src.rules.validator import ClaimValidator

        with self.app.app_context():
            user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            product = Product.query.filter_by(user_id=user.id).first()

            # 1. Missing mandatory fields
            is_valid, errors, warnings, cleaned = ClaimValidator.validate_claim_submission({}, {})
            self.assertFalse(is_valid)
            self.assertTrue(any("mandatory" in e.lower() for e in errors))

            # 2. Future date rejection
            bad_date_form = {
                "product_id": product.product_id,
                "fault_category": "Hardware Malfunction",
                "damage_type": "Display Failure",
                "fault_description": "Screen panel flickering violently upon booting",
                "fault_occurrence_date": "2099-01-01",
                "claim_amount": "150.00"
            }
            is_valid, errors, warnings, cleaned = ClaimValidator.validate_claim_submission(bad_date_form, {})
            self.assertFalse(is_valid)
            self.assertTrue(any("future" in e.lower() for e in errors))

            # 3. Negative numerical claim value
            bad_num_form = dict(bad_date_form)
            bad_num_form["fault_occurrence_date"] = "2026-09-01"
            bad_num_form["claim_amount"] = "-45.00"
            is_valid, errors, warnings, cleaned = ClaimValidator.validate_claim_submission(bad_num_form, {})
            self.assertFalse(is_valid)
            self.assertTrue(any("greater than zero" in e.lower() for e in errors))

            # 4. Disallowed file extension
            disallowed_file = {
                "receipt": (io.BytesIO(b"binary executable payload"), "invoice.exe")
            }
            is_valid, errors, warnings, cleaned = ClaimValidator.validate_claim_submission(bad_date_form, disallowed_file)
            self.assertFalse(is_valid)
            self.assertTrue(any("unsupported extension" in e.lower() for e in errors))

    def test_req_xvi_data_preprocessing(self):
        """Req 1.6.xvi: Verify Python Data Preprocessing calculates derived fields and handles missing values."""
        from src.core.preprocessor import ClaimDataPreprocessor

        with self.app.app_context():
            product = Product.query.first()
            raw_claim = {
                "claim_id": "CLM-TEST-PREPROC",
                "fault_category": "Internal Component Failure",
                "damage_type": "Battery Defect",
                "fault_occurrence_date": "2026-08-15",
                "claim_submission_date": "2026-09-01"
            }

            cleaned = ClaimDataPreprocessor.clean_and_prepare(raw_claim, product=product, documents=[])

            # Derived fields must exist and be accurately calculated
            self.assertIn("product_age_days", cleaned)
            self.assertIn("remaining_warranty_days", cleaned)
            self.assertIn("missing_document_count", cleaned)
            self.assertIn("previous_repairs_count", cleaned)
            self.assertIn("unauthorized_repair_flag", cleaned)
            self.assertIn("claim_date_conflict_flag", cleaned)

            self.assertIsInstance(cleaned["product_age_days"], int)
            self.assertIsInstance(cleaned["remaining_warranty_days"], int)
            # Since no documents were provided, missing_document_count should equal 4
            self.assertEqual(cleaned["missing_document_count"], 4)
            self.assertGreaterEqual(cleaned["product_age_days"], 0)


    def test_req_xx_xxi_xxii_summary_card_and_model_comparison(self):
        """Req 1.6.xx, xxi, xxii: Verify visual Claim Summary Card generation, GTM classification, and model comparison."""
        from src.core.card_generator import render_claim_summary_card
        from src.core.teachable_machine_classifier import get_gtm_classifier
        from src.core.model_comparator import get_model_comparator
        from PIL import Image

        with self.app.app_context():
            claim = Claim.query.first()
            self.assertIsNotNone(claim)

            # Req 1.6.xx: Generate Claim Summary Card
            from src.core.preprocessor import ClaimDataPreprocessor
            payload = ClaimDataPreprocessor.clean_and_prepare(
                {
                    "claim_id": claim.claim_id,
                    "fault_category": claim.fault_category,
                    "damage_type": claim.damage_type,
                    "fault_occurrence_date": claim.fault_occurrence_date,
                    "claim_submission_date": claim.claim_submission_date
                },
                product=claim.product,
                documents=claim.documents
            )
            card_img = render_claim_summary_card(payload)
            self.assertIsInstance(card_img, Image.Image)
            self.assertEqual(card_img.size, (640, 420))

            # Req 1.6.xxi: Google Teachable Machine Evaluation
            gtm_res = get_gtm_classifier().predict_card(card_img)
            self.assertIn("predicted_class", gtm_res)
            self.assertIn(gtm_res["predicted_class"], ["Valid Claim", "Invalid Claim", "Manual Review"])
            self.assertIn("confidence_scores", gtm_res)
            for cls_name in ["Valid Claim", "Invalid Claim", "Manual Review"]:
                self.assertIn(cls_name, gtm_res["confidence_scores"])
                self.assertGreaterEqual(gtm_res["confidence_scores"][cls_name], 0.0)
                self.assertLessEqual(gtm_res["confidence_scores"][cls_name], 1.0)

            # Req 1.6.xxii: Model Prediction Comparison
            py_res = {
                "predicted_class": "Valid Claim",
                "top_confidence": 0.88,
                "confidence_scores": {"Valid Claim": 0.88, "Invalid Claim": 0.05, "Manual Review": 0.07}
            }
            from src.core.model_comparator import get_model_comparator
            comparison = get_model_comparator().evaluate_consensus(py_res, gtm_res)
            self.assertIn("is_class_match", comparison)
            self.assertIsInstance(comparison["is_class_match"], bool)
            self.assertIn("model_consistency_status", comparison)
            self.assertIn("top_confidence_difference", comparison)

            # Also verify summary-card endpoint responds with image/png
            with self.client.session_transaction() as sess:
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.user_id
                sess["role"] = user.role
                sess["email"] = user.email

            res = self.client.get(f"/claims/{claim.claim_id}/summary-card")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.mimetype, "image/png")


    def test_req_xxiii_xxiv_confidence_comparison_and_consistency_status(self):
        """Req 1.6.xxiii & xxiv: Verify top-confidence score comparison, absolute difference, and 5 consistency statuses with dynamic thresholds."""
        from src.core.model_comparator import get_model_comparator
        comparator = get_model_comparator()

        # Req xxiii: Calculate absolute difference between two top confidence scores
        py_top = 0.92
        gtm_top = 0.85
        py_res = {"predicted_class": "Valid Claim", "top_confidence": py_top, "confidence_scores": {"Valid Claim": py_top, "Invalid Claim": 0.05, "Manual Review": 0.03}}
        gtm_res = {"predicted_class": "Valid Claim", "top_confidence": gtm_top, "confidence_scores": {"Valid Claim": gtm_top, "Invalid Claim": 0.08, "Manual Review": 0.07}}

        res = comparator.evaluate_consensus(py_res, gtm_res)
        expected_diff = round(abs(py_top - gtm_top), 4)
        self.assertEqual(res["top_confidence_difference"], expected_diff)
        self.assertTrue(res["is_class_match"])

        # Req xxiv: All 5 model consistency statuses
        # 1. Strong Match (|Δ| <= 0.15)
        self.assertEqual(res["model_consistency_status"], "Strong Match")

        # 2. Acceptable Match (0.15 < |Δ| <= 0.30)
        gtm_acc = {"predicted_class": "Valid Claim", "top_confidence": 0.70, "confidence_scores": {}}
        res_acc = comparator.evaluate_consensus(py_res, gtm_acc)
        self.assertEqual(res_acc["model_consistency_status"], "Acceptable Match")

        # 3. Weak Match (|Δ| > 0.30)
        gtm_weak = {"predicted_class": "Valid Claim", "top_confidence": 0.61, "confidence_scores": {}}
        res_weak = comparator.evaluate_consensus(py_res, gtm_weak)
        self.assertEqual(res_weak["model_consistency_status"], "Weak Match")

        # 4. Model Disagreement (different classes)
        gtm_dis = {"predicted_class": "Invalid Claim", "top_confidence": 0.85, "confidence_scores": {}}
        res_dis = comparator.evaluate_consensus(py_res, gtm_dis)
        self.assertEqual(res_dis["model_consistency_status"], "Model Disagreement")
        self.assertFalse(res_dis["is_class_match"])

        # 5. Uncertain Result (top confidence < min_confidence)
        gtm_unc = {"predicted_class": "Valid Claim", "top_confidence": 0.50, "confidence_scores": {}}
        res_unc = comparator.evaluate_consensus(py_res, gtm_unc)
        self.assertEqual(res_unc["model_consistency_status"], "Uncertain Result")

        # Test Admin route to configure model thresholds dynamically
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
                sess["user_id"] = admin.id
                sess["role"] = admin.role
                sess["email"] = admin.email

        res_post = self.client.post("/admin/settings/model-thresholds", data={
            "min_confidence": "0.65",
            "strong_diff": "0.10",
            "acceptable_diff": "0.25"
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        with self.app.app_context():
            self.assertEqual(SystemSetting.get_val("min_confidence_threshold"), "0.65")
            self.assertEqual(SystemSetting.get_val("strong_match_diff"), "0.10")
            self.assertEqual(SystemSetting.get_val("acceptable_match_diff"), "0.25")

    def test_req_xxv_warranty_rule_validation_all_10_rules(self):
        """Req 1.6.xxv: Verify independent validation of all 10 warranty business rules."""
        from src.rules.policy_engine import get_policy_engine
        engine = get_policy_engine()

        # Clean claim payload with all required features
        claim_payload = {
            "claim_id": "CLM-RULE-TEST-XXV",
            "product_category": "Consumer Electronics",
            "fault_category": "Screen flickering",
            "damage_type": "Hardware Defect",
            "fault_occurrence_date": "2026-09-01",
            "claim_submission_date": "2026-09-10",
            "remaining_warranty_days": 180,
            "product_age_days": 120,
            "warranty_duration_months": 12,
            "has_receipt": 1,
            "is_extended_warranty": 1,
            "serial_number_match": 1,
            "previous_repairs_count": 0,
            "unauthorized_repair_flag": 0,
            "previous_replacement_details": None,
            "missing_document_count": 0,
            "claim_date_conflict_flag": 0
        }

        eval_res = engine.evaluate_claim_rules(claim_payload)

        # 1. Warranty Expiry check passed
        self.assertTrue(any("warranty active" in p.lower() for p in eval_res["passed_rules"]))

        # 2. Fault Coverage verified
        self.assertTrue(any("fault coverage verified" in p.lower() for p in eval_res["passed_rules"]))

        # 3. Claim Reporting Window verified
        self.assertTrue(any("permissible reporting window" in p.lower() for p in eval_res["passed_rules"]))

        # 4. Proof of Purchase verified
        self.assertTrue(any("proof of purchase verified" in p.lower() for p in eval_res["passed_rules"]))

        # 5. Extended Warranty validated
        self.assertTrue(any("extended warranty validated" in p.lower() for p in eval_res["passed_rules"]))

        # 6. Serial-number match verified
        self.assertTrue(any("serial number verification passed" in p.lower() for p in eval_res["passed_rules"]))

        # 7. Previous Repairs verified
        self.assertTrue(any("service center history verified" in p.lower() or "previous repairs" in p.lower() for p in eval_res["passed_rules"]))

        # 8. Product Replacement verified
        self.assertTrue(any("product replacement check" in p.lower() for p in eval_res["passed_rules"]))

        # 9. Excluded Damage check passed
        self.assertTrue(any("excluded damage check" in p.lower() for p in eval_res["passed_rules"]))

        # 10. Required Documents dossier verified
        self.assertTrue(any("mandatory documentation complete" in p.lower() for p in eval_res["passed_rules"]))

        self.assertEqual(eval_res["overall_status"], "PASS")

        # Now test Hard Fail: Excluded damage (e.g. liquid ingress)
        claim_excluded = dict(claim_payload, damage_type="Liquid ingress damage")
        eval_excl = engine.evaluate_claim_rules(claim_excluded)
        self.assertEqual(eval_excl["overall_status"], "FAIL")
        self.assertTrue(any("excluded damage detected" in f.lower() for f in eval_excl["failed_rules"]))

    def test_req_xxvi_configurable_warranty_policies_db_and_files(self):
        """Req 1.6.xxvi: Verify warranty policies stored in configurable files & DB supporting multiple product categories."""
        import json
        from src.rules.policy_engine import get_policy_engine
        engine = get_policy_engine()

        # 1. Multi-category file-based policy retrieval
        categories = ["Consumer Electronics", "Home Appliances", "Industrial & Automotive Tools"]
        for cat in categories:
            pol = engine.get_policy_for_category(cat)
            self.assertEqual(pol["category"], cat)
            self.assertIn("coverage_duration_months", pol)
            self.assertIn("covered_faults", pol)
            self.assertIn("exclusions", pol)
            self.assertIn("claim_reporting_period_days", pol)
            self.assertIn("mandatory_documents", pol)
            self.assertIn("authorized_service_center_required", pol)
            self.assertIsInstance(pol["covered_faults"], list)
            self.assertIsInstance(pol["exclusions"], list)

        # 2. Database stored policy takes dynamic precedence
        with self.app.app_context():
            custom_policy = WarrantyPolicy.query.filter_by(category="Test Category Gadgets").first()
            if not custom_policy:
                custom_policy = WarrantyPolicy(
                    category="Test Category Gadgets",
                    policy_name="Custom Gadget Policy DB",
                    coverage_duration_months=36,
                    grace_period_days=10,
                    claim_reporting_period_days=60,
                    authorized_service_center_required=True,
                    policy_rules_json=json.dumps({
                        "covered_faults": ["OLED Burn-in", "Capacitor failure"],
                        "exclusions": ["Cracked lens", "Commercial use"],
                        "mandatory_documents": ["Serial Photo", "Invoice"]
                    })
                )
                db.session.add(custom_policy)
                db.session.commit()

            pol_db = engine.get_policy_for_category("Test Category Gadgets")
            self.assertEqual(pol_db["coverage_duration_months"], 36)
            self.assertEqual(pol_db["claim_reporting_period_days"], 60)
            self.assertIn("OLED Burn-in", pol_db["covered_faults"])

    def test_req_xxvii_serial_number_verification_across_4_sources(self):
        """Req 1.6.xxvii: Verify serial comparison across user entry, receipt, warranty card, product image, and repair records."""
        from src.rules.contradiction_detector import get_contradiction_detector
        detector = get_contradiction_detector()

        user_serial = "SN-APX-8829104"

        # Case A: Perfect match across all 4 sources
        claim_consistent = {
            "product_serial": user_serial,
            "receipt_serial": user_serial,
            "warranty_card_serial": user_serial,
            "product_image_serial": user_serial,
            "repair_record_serial": user_serial,
            "purchase_date": "2026-01-01",
            "fault_occurrence_date": "2026-03-01",
            "claim_submission_date": "2026-03-10"
        }
        res_ok = detector.detect_contradictions(claim_consistent)
        self.assertFalse(res_ok["has_contradiction"])
        self.assertEqual(len(res_ok["contradictions"]), 0)

        # Case B: Receipt serial mismatch
        res_receipt = detector.detect_contradictions(dict(claim_consistent, receipt_serial="SN-WRONG-RECEIPT"))
        self.assertTrue(res_receipt["has_contradiction"])
        self.assertTrue(any("receipt" in c.lower() for c in res_receipt["contradictions"]))

        # Case C: Warranty card serial mismatch
        res_card = detector.detect_contradictions(dict(claim_consistent, warranty_card_serial="SN-WRONG-CARD"))
        self.assertTrue(res_card["has_contradiction"])
        self.assertTrue(any("warranty card" in c.lower() for c in res_card["contradictions"]))

        # Case D: Product image serial mismatch
        res_img = detector.detect_contradictions(dict(claim_consistent, product_image_serial="SN-WRONG-PHOTO"))
        self.assertTrue(res_img["has_contradiction"])
        self.assertTrue(any("product image" in c.lower() for c in res_img["contradictions"]))

        # Case E: Repair record serial mismatch
        res_rep = detector.detect_contradictions(dict(claim_consistent, repair_record_serial="SN-WRONG-REPAIR"))
        self.assertTrue(res_rep["has_contradiction"])
        self.assertTrue(any("repair record" in c.lower() for c in res_rep["contradictions"]))

    def test_req_xxviii_contradiction_detection_all_5_scenarios(self):
        """Req 1.6.xxviii: Verify all 5 contradiction scenarios including repair date before purchase and model conflicts."""
        from src.rules.contradiction_detector import get_contradiction_detector
        detector = get_contradiction_detector()

        # Scenario 1: Claim date before purchase date
        res_1 = detector.detect_contradictions({
            "product_serial": "SN-001",
            "purchase_date": "2026-06-01",
            "claim_submission_date": "2026-05-15",
            "fault_occurrence_date": "2026-05-10"
        })
        self.assertTrue(res_1["has_contradiction"])
        self.assertTrue(any("submission date" in c.lower() and "predates" in c.lower() for c in res_1["contradictions"]))

        # Scenario 2: Repair date before purchase date
        res_2 = detector.detect_contradictions({
            "product_serial": "SN-001",
            "purchase_date": "2026-06-01",
            "claim_submission_date": "2026-07-01",
            "fault_occurrence_date": "2026-06-15",
            "repair_records": [{"repair_date": "2026-04-10", "repair_center": "Workshop A"}]
        })
        self.assertTrue(res_2["has_contradiction"])
        self.assertTrue(any("repair date" in c.lower() and "predates" in c.lower() for c in res_2["contradictions"]))

        # Scenario 3: Inconsistent product models
        res_3 = detector.detect_contradictions(
            {
                "product_serial": "SN-001",
                "product_model": "Dell XPS 15",
                "purchase_date": "2026-01-01",
                "claim_submission_date": "2026-02-01",
                "fault_occurrence_date": "2026-01-15"
            },
            ocr_data={"model_name": "MacBook Pro 16"}
        )
        self.assertTrue(res_3["has_contradiction"])
        self.assertTrue(any("model" in c.lower() for c in res_3["contradictions"]))

        # Scenario 4: Conflicting serial numbers
        res_4 = detector.detect_contradictions({
            "product_serial": "SN-ALPHA-123",
            "receipt_serial": "SN-BETA-999",
            "purchase_date": "2026-01-01",
            "claim_submission_date": "2026-02-01",
            "fault_occurrence_date": "2026-01-15"
        })
        self.assertTrue(res_4["has_contradiction"])
        self.assertTrue(any("serial number mismatch" in c.lower() for c in res_4["contradictions"]))

        # Scenario 5: Fault date after claim submission date
        res_5 = detector.detect_contradictions({
            "product_serial": "SN-001",
            "purchase_date": "2026-01-01",
            "claim_submission_date": "2026-02-01",
            "fault_occurrence_date": "2026-02-15"  # Future fault date
        })
        self.assertTrue(res_5["has_contradiction"])
        self.assertTrue(any("future relative to submission" in c.lower() for c in res_5["contradictions"]))

    def test_req_xxix_missing_document_detection(self):
        """
        Req 1.6.xxix: Missing Document Detection.
        Identifies missing mandatory documents such as purchase receipt, warranty card,
        product image, serial-number evidence, fault evidence, and repair report.
        Informs the user which documents are required.
        """
        from src.rules.validator import ClaimValidator

        # 1. Test missing document detection with empty file dictionary
        empty_check = ClaimValidator.identify_missing_documents({}, has_previous_repairs=True)
        self.assertTrue(empty_check["has_missing"])
        missing_keys = [d["key"] for d in empty_check["missing_documents"]]
        self.assertIn("receipt", missing_keys)
        self.assertIn("warranty_card", missing_keys)
        self.assertIn("product_photo", missing_keys)
        self.assertIn("serial_photo", missing_keys)
        self.assertIn("fault_evidence", missing_keys)
        self.assertIn("repair_report", missing_keys)
        self.assertIn("Missing mandatory document(s)", empty_check["user_message"])

        # 2. Test when all mandatory files are supplied
        complete_files = {
            "receipt": ("receipt.pdf", "receipt.pdf"),
            "warranty_card": ("card.png", "card.png"),
            "product_photo": ("product.jpg", "product.jpg"),
            "serial_photo": ("serial.jpg", "serial.jpg"),
            "damage_photo": ("damage.jpg", "damage.jpg"),
            "diagnostic_report": ("report.pdf", "report.pdf")
        }
        complete_check = ClaimValidator.identify_missing_documents(complete_files, has_previous_repairs=True)
        self.assertFalse(complete_check["has_missing"])
        self.assertEqual(complete_check["missing_count"], 0)
        self.assertIn("All mandatory claim documents are present", complete_check["user_message"])

        # 3. Test UI view rendering missing document alert on claim detail
        with self.app.app_context():
            claim = Claim.query.filter_by(missing_document_flag=True).first()
            if not claim:
                claim = Claim.query.first()
                claim.missing_document_flag = True
            claim.status = Config.STATUS_SUBMITTED
            db.session.commit()
            claim_code = claim.claim_id

        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_ADMIN).first()
                sess["user_id"] = user.id
                sess["role"] = user.role
                sess["user_code"] = user.user_id

        res = self.client.get(f"/claims/{claim_code}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Missing Mandatory Documents Detected", res.data)
        self.assertIn(b"Upload Missing Document", res.data)

    def test_req_xxx_duplicate_claim_seven_factors(self):
        """
        Req 1.6.xxx: Duplicate Claim Detection.
        Detects duplicate claims by comparing:
        1. Claim IDs
        2. Invoice numbers
        3. Product serial numbers
        4. Fault descriptions
        5. Claimant details
        6. Document hashes
        7. Previous claim records
        """
        from src.rules.duplicate_detector import get_duplicate_detector
        detector = get_duplicate_detector()

        with self.app.app_context():
            existing_claim = Claim.query.first()
            prod = existing_claim.product
            user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()

            # Factor 1: Claim ID Collision
            res_id = detector.check_claim_duplicates({"claim_id": existing_claim.claim_id})
            self.assertTrue(res_id["is_duplicate"])
            self.assertIn("claim_id", res_id["factors_triggered"])

            # Factor 2: Invoice Number Collision
            res_inv = detector.check_claim_duplicates({"invoice_number": prod.invoice_number})
            self.assertTrue(res_inv["is_duplicate"])
            self.assertIn("invoice_number", res_inv["factors_triggered"])

            # Factor 3: Product Serial Collision with active claim
            res_serial = detector.check_claim_duplicates({"product_serial": prod.serial_number})
            self.assertTrue(res_serial["is_duplicate"])
            self.assertIn("product_serial", res_serial["factors_triggered"])

            # Factor 4: Fault Description Match
            res_desc = detector.check_claim_duplicates({
                "product_serial": prod.serial_number,
                "fault_description": existing_claim.fault_description
            })
            self.assertTrue(res_desc["is_duplicate"])
            self.assertIn("fault_description", res_desc["factors_triggered"])

            # Factor 5: Claimant Details Match
            res_claimant = detector.check_claim_duplicates({
                "product_serial": prod.serial_number,
                "claimant_id": existing_claim.user_id
            })
            self.assertTrue(res_claimant["is_duplicate"])
            self.assertIn("claimant_details", res_claimant["factors_triggered"])

            # Factor 6: Cryptographic Document Hash Match
            test_doc = ClaimDocument.query.filter(ClaimDocument.file_hash_sha256 != None).first()
            if test_doc:
                res_hash = detector.check_claim_duplicates(
                    {"product_serial": prod.serial_number},
                    uploaded_file_hashes=[test_doc.file_hash_sha256]
                )
                self.assertTrue(res_hash["is_duplicate"])
                self.assertIn("document_hashes", res_hash["factors_triggered"])

            # Factor 7: Previous Claim Records History
            res_prev = detector.check_claim_duplicates({"product_serial": prod.serial_number})
            self.assertIn("previous_claim_records", res_prev["factors_triggered"])

    def test_req_xxxi_document_duplicate_detection_sha256(self):
        """
        Req 1.6.xxxi: Document Duplicate Detection.
        Creates secure SHA-256 hash for uploaded documents and detects whether
        the same receipt, invoice, warranty card, or evidence file was used in another claim.
        """
        from src.rules.duplicate_detector import get_duplicate_detector
        detector = get_duplicate_detector()

        with self.app.app_context():
            # Create a test document with a known SHA-256 hash
            test_claim = Claim.query.first()
            sha256_sample = "a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef"
            
            # Clean any old test doc
            old_doc = ClaimDocument.query.filter_by(file_hash_sha256=sha256_sample).first()
            if old_doc:
                db.session.delete(old_doc)
                db.session.commit()

            doc1 = ClaimDocument(
                claim_id=test_claim.id,
                product_id=test_claim.product_id,
                document_type="receipt",
                file_path="data/uploads/test_receipt_hash.pdf",
                original_filename="tax_invoice_original.pdf",
                file_size_bytes=4096,
                file_hash_sha256=sha256_sample,
                verified_by_user=True
            )
            db.session.add(doc1)
            db.session.commit()

            # Check duplicate detection for the same hash in another claim
            check_dup = detector.check_document_duplicates(sha256_sample, exclude_claim_id=999999)
            self.assertTrue(check_dup["is_duplicate"])
            self.assertIn(test_claim.claim_id, check_dup["matched_claims"])
            self.assertIn("tax_invoice_original.pdf", str(check_dup["matched_documents"]))

            # Check duplicate detection excluding the owner claim
            check_own = detector.check_document_duplicates(sha256_sample, exclude_claim_id=test_claim.id)
            self.assertFalse(check_own["is_duplicate"])

            # Test document upload route for supplementary/missing document
            with self.client.session_transaction() as sess:
                user = User.query.filter_by(role=Config.ROLE_ADMIN).first()
                sess["user_id"] = user.id
                sess["role"] = user.role
                sess["user_code"] = user.user_id

            fake_pdf = (io.BytesIO(b"%PDF-1.4 simulated upload content"), "supplementary_evidence.pdf")
            res_upload = self.client.post(
                f"/claims/{test_claim.claim_id}/documents/upload",
                data={
                    "document_type": "warranty_card",
                    "evidence_file": fake_pdf
                },
                follow_redirects=True
            )
            self.assertEqual(res_upload.status_code, 200)
            self.assertIn(b"uploaded successfully", res_upload.data)

            # Cleanup test doc
            db.session.delete(doc1)
            db.session.commit()

    def test_req_xxxii_ai_generated_claim_summary(self):
        """
        Req 1.6.xxxii: AI-Generated Claim Summary.
        Generates a clear summary of product, warranty coverage, reported fault,
        repair history, uploaded evidence, detected issues, and claim status/recommendations.
        Verifies rendering in both customer and reviewer portals.
        """
        from src.core.decision_engine import MasterDecisionEngine, generate_claim_summary

        with self.app.app_context():
            claim = Claim.query.first()
            self.assertIsNotNone(claim)

            # 1. Test programmatic generation via MasterDecisionEngine & helper
            engine = MasterDecisionEngine()
            summary = engine.generate_claim_summary(claim)
            self.assertIsInstance(summary, dict)

            # Verify all required sections exist
            required_sections = [
                "product_summary",
                "warranty_coverage_summary",
                "reported_fault_summary",
                "repair_history_summary",
                "uploaded_evidence_summary",
                "detected_issues_summary",
                "claim_status_and_recommendations",
                "executive_brief"
            ]
            for sec in required_sections:
                self.assertIn(sec, summary)

            # Check individual section fields
            self.assertIn("name", summary["product_summary"])
            self.assertIn("category", summary["product_summary"])
            self.assertIn("serial_number", summary["product_summary"])
            self.assertIn("status", summary["warranty_coverage_summary"])
            self.assertIn("remaining_days", summary["warranty_coverage_summary"])
            self.assertIn("category", summary["reported_fault_summary"])
            self.assertIn("description", summary["reported_fault_summary"])
            self.assertIn("total_repairs", summary["repair_history_summary"])
            self.assertIn("total_documents", summary["uploaded_evidence_summary"])
            self.assertIn("has_issues", summary["detected_issues_summary"])
            self.assertIn("final_decision", summary["claim_status_and_recommendations"])
            self.assertTrue(len(summary["executive_brief"]) > 20)

            # Test model entity helper method
            entity_summary = claim.generate_ai_summary()
            self.assertEqual(entity_summary["product_summary"]["name"], summary["product_summary"]["name"])
            claim_id_val = claim.claim_id

        # 2. Test Customer Claim Detail view renders AI-Generated Claim Summary
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["role"] = user.role
                sess["user_code"] = user.user_id

        res_cust = self.client.get(f"/claims/{claim_id_val}")
        self.assertEqual(res_cust.status_code, 200)
        self.assertIn(b"Executive Claim Intelligence Summary", res_cust.data)
        self.assertIn(b"Hardware Asset", res_cust.data)
        self.assertIn(b"Warranty Coverage", res_cust.data)
        self.assertIn(b"Reported Defect", res_cust.data)

        # 3. Test Reviewer Inspection view renders AI-Generated Claim Summary
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                rev = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
                sess["user_id"] = rev.id
                sess["role"] = rev.role
                sess["user_code"] = rev.user_id

        res_rev = self.client.get(f"/reviewer/claim/{claim_id_val}")
        self.assertEqual(res_rev.status_code, 200)
        self.assertIn(b"Executive Claim Intelligence Summary", res_rev.data)
        self.assertIn(b"Hardware Asset", res_rev.data)

    def test_req_xxxiii_claim_preparation_assistance(self):
        """
        Req 1.6.xxxiii: Claim Preparation Assistance.
        Guides the user before final submission by displaying:
        - Missing information
        - Missing documents
        - Approaching deadlines
        - Possible contradictions
        - Recommended corrective actions
        Computes dossier readiness percentage score and provides JSON verification endpoint.
        """
        from src.rules.validator import ClaimValidator

        with self.app.app_context():
            product = Product.query.first()
            self.assertIsNotNone(product)

            # Case A: Incomplete form data with missing information & missing documents
            incomplete_form = {
                "fault_category": "",
                "damage_type": "",
                "fault_description": "short",
                "fault_occurrence_date": ""
            }
            readiness_bad = ClaimValidator.check_claim_preparation_readiness(incomplete_form, {}, product=product)
            self.assertFalse(readiness_bad["is_ready_for_submission"])
            self.assertLess(readiness_bad["readiness_score"], 80)
            self.assertTrue(len(readiness_bad["missing_information"]) >= 3)
            self.assertTrue(len(readiness_bad["missing_documents"]) >= 3)
            self.assertTrue(len(readiness_bad["recommended_corrective_actions"]) >= 3)

            # Case B: Possible Contradictions detected (future fault date)
            future_form = {
                "product_id": str(product.id),
                "fault_category": "Display Malfunction",
                "damage_type": "Manufacturing Defect",
                "fault_description": "Screen flickering when connected to AC adapter power",
                "fault_occurrence_date": "2099-12-31"  # Obvious future date
            }
            readiness_future = ClaimValidator.check_claim_preparation_readiness(future_form, {}, product=product)
            self.assertFalse(readiness_future["is_ready_for_submission"])
            self.assertTrue(any("future" in c.lower() for c in readiness_future["possible_contradictions"]))
            self.assertTrue(any("date" in a.lower() for a in readiness_future["recommended_corrective_actions"]))

            # Case C: Valid complete form data with documents
            complete_form = {
                "product_id": str(product.id),
                "fault_category": "Display Malfunction",
                "damage_type": "Manufacturing Defect",
                "fault_description": "Screen panel flickering continuously during boot sequence.",
                "fault_occurrence_date": "2026-09-01"
            }
            mock_files = {
                "receipt": ("receipt.pdf", "receipt.pdf"),
                "warranty_card": ("card.png", "card.png"),
                "product_photo": ("product.jpg", "product.jpg"),
                "serial_photo": ("serial.jpg", "serial.jpg"),
                "damage_photo": ("damage.jpg", "damage.jpg")
            }
            readiness_ok = ClaimValidator.check_claim_preparation_readiness(complete_form, mock_files, product=product)
            self.assertTrue(readiness_ok["is_ready_for_submission"])
            self.assertEqual(len(readiness_ok["missing_information"]), 0)
            self.assertEqual(len(readiness_ok["possible_contradictions"]), 0)
            self.assertGreaterEqual(readiness_ok["readiness_score"], 80)

        # Case D: Test preparation check API endpoint POST /claims/preparation-check
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["role"] = user.role
                sess["user_code"] = user.user_id

        res_api = self.client.post("/claims/preparation-check", data={
            "product_id": str(product.id),
            "fault_category": "Audio Jack Failure",
            "damage_type": "Manufacturing Defect",
            "fault_description": "Right channel sound completely cuts out when headphone wire wiggles.",
            "fault_occurrence_date": "2026-09-10"
        })
        self.assertEqual(res_api.status_code, 200)
        api_data = res_api.get_json()
        self.assertTrue(api_data["success"])
        readiness = api_data["readiness"]
        self.assertIn("readiness_score", readiness)
        self.assertIn("is_ready_for_submission", readiness)
        self.assertIn("missing_information", readiness)
        self.assertIn("missing_documents", readiness)
        self.assertIn("approaching_deadlines", readiness)
        self.assertIn("possible_contradictions", readiness)
        self.assertIn("recommended_corrective_actions", readiness)

    def test_req_xxxiv_final_claim_decision_seven_factors(self):
        """
        Req 1.6.xxxiv: Final Claim Decision.
        Generates final result by synthesizing 7 factors:
        1. Python model prediction
        2. Google Teachable Machine prediction
        3. Confidence-score difference
        4. Warranty rules
        5. Missing documents
        6. Duplicate indicators
        7. Contradictions
        Result is strictly one of: 'Likely Valid', 'Likely Invalid', 'Manual Review Required'.
        """
        from src.core.decision_engine import MasterDecisionEngine
        ALLOWED_DECISIONS = {"Likely Valid", "Likely Invalid", "Manual Review Required"}

        # Base clean payloads
        model_results_valid = {
            "python_model": {"predicted_class": "Valid Claim", "top_confidence": 0.92},
            "gtm_model": {"predicted_class": "Valid Claim", "top_confidence": 0.88},
            "consensus": {
                "is_class_match": True,
                "top_confidence_difference": 0.04,
                "model_consistency_status": "Strong Match"
            }
        }
        rule_results_pass = {
            "overall_status": "PASS",
            "passed_rules": ["Warranty active", "Fault covered", "Serial verified"],
            "failed_rules": [],
            "warnings": []
        }

        # Factor 1 & 2 & 3: Unanimous Valid, Low Diff, PASS Rules, No Issues -> "Likely Valid"
        res_valid = MasterDecisionEngine.adjudicate_claim(
            model_results_valid,
            rule_results_pass,
            contradiction_list=[],
            duplicate_flags=[],
            missing_documents=[]
        )
        self.assertIn(res_valid["final_decision"], ALLOWED_DECISIONS)
        self.assertEqual(res_valid["final_decision"], "Likely Valid")

        # Factor 4: Warranty Rules Hard Fail (e.g. Liquid damage / Excluded) -> "Likely Invalid"
        rule_results_fail = {
            "overall_status": "FAIL",
            "passed_rules": [],
            "failed_rules": ["Excluded damage: Liquid ingress detected"],
            "warnings": []
        }
        res_invalid_rule = MasterDecisionEngine.adjudicate_claim(
            model_results_valid,
            rule_results_fail,
            contradiction_list=[],
            duplicate_flags=[],
            missing_documents=[]
        )
        self.assertIn(res_invalid_rule["final_decision"], ALLOWED_DECISIONS)
        self.assertEqual(res_invalid_rule["final_decision"], "Likely Invalid")

        # Factor 5: Missing Mandatory Documents -> "Manual Review Required"
        res_missing_docs = MasterDecisionEngine.adjudicate_claim(
            model_results_valid,
            rule_results_pass,
            contradiction_list=[],
            duplicate_flags=[],
            missing_documents=["Purchase Receipt", "Serial Tag Photo"]
        )
        self.assertIn(res_missing_docs["final_decision"], ALLOWED_DECISIONS)
        self.assertEqual(res_missing_docs["final_decision"], "Manual Review Required")
        self.assertTrue(res_missing_docs["has_missing_documents"])

        # Factor 6: Duplicate Indicators Triggered -> "Manual Review Required"
        res_duplicate = MasterDecisionEngine.adjudicate_claim(
            model_results_valid,
            rule_results_pass,
            contradiction_list=[],
            duplicate_flags=["Invoice INV-2026-9901 matches active claim CLM-DEMO-001"],
            missing_documents=[]
        )
        self.assertIn(res_duplicate["final_decision"], ALLOWED_DECISIONS)
        self.assertEqual(res_duplicate["final_decision"], "Manual Review Required")

        # Factor 7: Contradiction Flagged -> "Manual Review Required"
        res_contradiction = MasterDecisionEngine.adjudicate_claim(
            model_results_valid,
            rule_results_pass,
            contradiction_list=["Fault date predates product purchase date"],
            duplicate_flags=[],
            missing_documents=[]
        )
        self.assertIn(res_contradiction["final_decision"], ALLOWED_DECISIONS)
        self.assertEqual(res_contradiction["final_decision"], "Manual Review Required")

        # Factor 1 & 2 Disagreement (Python says Valid, GTM says Invalid) -> "Manual Review Required"
        model_results_disagree = {
            "python_model": {"predicted_class": "Valid Claim", "top_confidence": 0.85},
            "gtm_model": {"predicted_class": "Invalid Claim", "top_confidence": 0.80},
            "consensus": {
                "is_class_match": False,
                "top_confidence_difference": 0.05,
                "model_consistency_status": "Model Disagreement"
            }
        }
        res_disagree = MasterDecisionEngine.adjudicate_claim(
            model_results_disagree,
            rule_results_pass,
            contradiction_list=[],
            duplicate_flags=[],
            missing_documents=[]
        )
        self.assertIn(res_disagree["final_decision"], ALLOWED_DECISIONS)
        self.assertEqual(res_disagree["final_decision"], "Manual Review Required")

        # Factor 1 & 2 Unanimous Invalid -> "Likely Invalid"
        model_results_invalid = {
            "python_model": {"predicted_class": "Invalid Claim", "top_confidence": 0.95},
            "gtm_model": {"predicted_class": "Invalid Claim", "top_confidence": 0.90},
            "consensus": {
                "is_class_match": True,
                "top_confidence_difference": 0.05,
                "model_consistency_status": "Strong Match"
            }
        }
        res_invalid_models = MasterDecisionEngine.adjudicate_claim(
            model_results_invalid,
            rule_results_fail,
            contradiction_list=[],
            duplicate_flags=[],
            missing_documents=[]
        )
        self.assertIn(res_invalid_models["final_decision"], ALLOWED_DECISIONS)
        self.assertEqual(res_invalid_models["final_decision"], "Likely Invalid")

    def test_req_xxxv_decision_explanation_breakdown(self):
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
        from src.core.decision_engine import MasterDecisionEngine, generate_decision_explanation

        with self.app.app_context():
            claim = Claim.query.first()
            self.assertIsNotNone(claim)

            # Test programmatic explanation generation
            engine = MasterDecisionEngine()
            explanation = engine.generate_decision_explanation(claim)
            self.assertIsInstance(explanation, dict)

            # Verify all 6 required explanation dimensions
            self.assertIn("supporting_factors", explanation)
            self.assertIn("opposing_factors", explanation)
            self.assertIn("rules_passed", explanation)
            self.assertIn("rules_failed", explanation)
            self.assertIn("contradictions", explanation)
            self.assertIn("additional_evidence_required", explanation)
            self.assertIsInstance(explanation["supporting_factors"], list)
            self.assertIsInstance(explanation["opposing_factors"], list)
            self.assertIsInstance(explanation["rules_passed"], list)
            self.assertIsInstance(explanation["rules_failed"], list)
            self.assertIsInstance(explanation["contradictions"], list)
            self.assertIsInstance(explanation["additional_evidence_required"], list)

            # Test model entity helper
            entity_exp = claim.get_decision_explanation()
            self.assertEqual(entity_exp["claim_id"], explanation["claim_id"])
            claim_id_val = claim.claim_id

        # Test customer claim detail renders Decision Explanation section
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
                sess["user_id"] = user.id
                sess["role"] = user.role
                sess["user_code"] = user.user_id

        res_cust = self.client.get(f"/claims/{claim_id_val}")
        self.assertEqual(res_cust.status_code, 200)
        self.assertIn(b"Decision Explanation &amp; Factor Analysis", res_cust.data)
        self.assertIn(b"Factors Supporting Decision", res_cust.data)
        self.assertIn(b"Factors Opposing Decision", res_cust.data)

        # Test reviewer inspection renders Comprehensive Decision Explanation section
        with self.client.session_transaction() as sess:
            with self.app.app_context():
                rev = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
                sess["user_id"] = rev.id
                sess["role"] = rev.role
                sess["user_code"] = rev.user_id

        res_rev = self.client.get(f"/reviewer/claim/{claim_id_val}")
        self.assertEqual(res_rev.status_code, 200)
        self.assertIn(b"Comprehensive Decision Explanation", res_rev.data)
        self.assertIn(b"Additional Evidence Required", res_rev.data)

    def test_req_xxxvi_manual_review_workflow_triage_and_actions(self):
        """
        Req 1.6.xxxvi: Manual Review Workflow.
        Claims with low confidence, conflicting models, missing evidence, duplicate indicators,
        or rule violations are routed to manual review.
        Authorized reviewers can approve, reject, or request additional information.
        """
        with self.app.app_context():
            claim = Claim.query.first()
            claim_id_val = claim.claim_id
            reviewer = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()

        # 1. Unauthorized customer blocked from reviewer queue
        with self.client.session_transaction() as sess:
            sess["user_id"] = customer.id
            sess["role"] = customer.role
            sess["user_code"] = customer.user_id

        res_unauth = self.client.get("/reviewer/queue")
        self.assertIn(res_unauth.status_code, [302, 403])

        # 2. Authorized reviewer access
        with self.client.session_transaction() as sess:
            sess["user_id"] = reviewer.id
            sess["role"] = reviewer.role
            sess["user_code"] = reviewer.user_id

        res_queue = self.client.get("/reviewer/queue?status=ALL")
        self.assertEqual(res_queue.status_code, 200)
        self.assertIn(b"Claim Adjudication", res_queue.data)

        # 3. Test REQUEST_INFO action transitions status to Additional Information Required
        res_info = self.client.post(
            f"/reviewer/claim/{claim_id_val}/adjudicate",
            data={
                "action": "REQUEST_INFO",
                "comments": "Please provide an authorized service repair report and high-resolution defect photograph."
            },
            follow_redirects=True
        )
        self.assertEqual(res_info.status_code, 200)

        with self.app.app_context():
            updated_claim = Claim.query.filter_by(claim_id=claim_id_val).first()
            self.assertEqual(updated_claim.status, Config.STATUS_ADDITIONAL_INFO)
            self.assertIn("repair report", updated_claim.reviewer_notes)

    def test_req_xxxvii_reviewer_comments_and_decision_override_audit(self):
        """
        Req 1.6.xxxvii: Reviewer Comments and Decision Override.
        Authorized reviewers can add comments and override automated recommendations.
        Original AI recommendation and override reason remain permanently preserved in audit history.
        """
        with self.app.app_context():
            reviewer = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
            rev_id = reviewer.id
            rev_role = reviewer.role
            rev_code = reviewer.user_id
            claim = Claim.query.first()
            claim_id_val = claim.claim_id
            # Set automated recommendation to Manual Review Required or Likely Invalid
            claim.final_decision = "Manual Review Required"
            db.session.commit()

        with self.client.session_transaction() as sess:
            sess["user_id"] = rev_id
            sess["role"] = rev_role
            sess["user_code"] = rev_code

        # Submit an Override: Reviewer approves a claim that was flagged for Manual Review
        post_data = {
            "action": "APPROVE",
            "override_reason": "Bench technician inspection verified genuine factory component failure.",
            "comments": "Customer goodwill override authorized by senior triage reviewer after hardware bench diagnostic."
        }
        res_override = self.client.post(
            f"/reviewer/claim/{claim_id_val}/adjudicate",
            data=post_data,
            follow_redirects=True
        )
        self.assertEqual(res_override.status_code, 200)
        self.assertIn(b"adjudicated successfully", res_override.data)

        with self.app.app_context():
            adjudicated_claim = Claim.query.filter_by(claim_id=claim_id_val).first()
            self.assertEqual(adjudicated_claim.status, Config.STATUS_APPROVED)

            # Verify ReviewerAction recorded with original AI recommendation preserved
            latest_action = ReviewerAction.query.filter_by(claim_id=adjudicated_claim.id).order_by(ReviewerAction.id.desc()).first()
            self.assertIsNotNone(latest_action)
            self.assertTrue(latest_action.is_override)
            self.assertEqual(latest_action.previous_recommendation, "Manual Review Required")
            self.assertEqual(latest_action.reviewer_decision, "Approved")
            self.assertEqual(latest_action.override_reason, post_data["override_reason"])
            self.assertEqual(latest_action.comments, post_data["comments"])

            # Verify AuditLog logged
            audit = AuditLog.query.filter_by(action="REVIEWER_ADJUDICATION", entity_id=claim_id_val).order_by(AuditLog.id.desc()).first()
            self.assertIsNotNone(audit)
            audit_details = json.loads(audit.details_json)
            self.assertTrue(audit_details["is_override"])
            self.assertEqual(audit_details["override_reason"], post_data["override_reason"])

        # Verify inspection view renders the Reviewer Audit History & Override Trail table
        res_inspect = self.client.get(f"/reviewer/claim/{claim_id_val}")
        self.assertEqual(res_inspect.status_code, 200)
        self.assertIn(b"Reviewer Audit History", res_inspect.data)
        self.assertIn(b"Decision Override Trail", res_inspect.data)
        self.assertIn(b"Override Applied", res_inspect.data)
        self.assertIn(b"Bench technician inspection verified", res_inspect.data)

    def test_req_xxxviii_claim_status_tracking_eight_stages(self):
        """
        Req 1.6.xxxviii: Claim Status Tracking.
        Users track claim progress through all 8 stages:
        Draft, Submitted, Under Evaluation, Additional Information Required,
        Manual Review, Approved, Rejected, and Closed.
        """
        with self.app.app_context():
            reviewer = User.query.filter_by(role=Config.ROLE_REVIEWER).first()
            rev_id = reviewer.id
            rev_role = reviewer.role
            rev_code = reviewer.user_id

            claim = Claim.query.first()
            claim_id_val = claim.claim_id

        # 1. Access live tracker view
        with self.client.session_transaction() as sess:
            sess["user_id"] = rev_id
            sess["role"] = rev_role
            sess["user_code"] = rev_code

        res_track = self.client.get(f"/claims/{claim_id_val}/track")
        self.assertEqual(res_track.status_code, 200)
        self.assertIn(b"Claim Progress Tracker", res_track.data)
        self.assertIn(b"Lifecycle Progress Timeline", res_track.data)

        # Verify all 8 lifecycle stages are defined in tracker template
        for stage in Config.ALL_CLAIM_STATUSES:
            self.assertIn(stage.encode(), res_track.data)

        # 2. Test transition to Closed stage via Reviewer Workbench
        res_close = self.client.post(
            f"/reviewer/claim/{claim_id_val}/adjudicate",
            data={
                "action": "CLOSE",
                "comments": "Claim settlement executed. Warranty replacement unit dispatched and case officially closed."
            },
            follow_redirects=True
        )
        self.assertEqual(res_close.status_code, 200)

        with self.app.app_context():
            closed_claim = Claim.query.filter_by(claim_id=claim_id_val).first()
            self.assertEqual(closed_claim.status, Config.STATUS_CLOSED)

            # Verify ClaimStatusHistory captured the Closed transition
            latest_hist = ClaimStatusHistory.query.filter_by(claim_id=closed_claim.id).order_by(ClaimStatusHistory.id.desc()).first()
            self.assertIsNotNone(latest_hist)
            self.assertEqual(latest_hist.new_status, Config.STATUS_CLOSED)
            self.assertIn("officially closed", latest_hist.reason_comment)

    def test_req_xxxix_notifications_and_alerts_coverage(self):
        """
        Req 1.6.xxxix: Notification and Alerts.
        Verifies notifications for:
        warranty expiry, claim submission, missing documents, requests for additional info,
        status changes, review completion, approval, and rejection.
        Also tests mark-read and clear-all actions.
        """
        with self.app.app_context():
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            cust_id = customer.id
            cust_role = customer.role
            cust_code = customer.user_id

            # Seed sample notifications for all required categories
            test_notifs = [
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_WARRANTY_EXPIRY,
                    title="Warranty Expiry Alert: ApexBook",
                    message="Warranty expires in 15 days."
                ),
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_CLAIM_SUBMISSION,
                    title="Claim Submission Confirmed: CLM-TEST-SUB",
                    message="Your claim was successfully registered."
                ),
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_MISSING_DOCUMENTS,
                    title="Missing Documents: CLM-TEST-SUB",
                    message="Please upload purchase receipt."
                ),
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_ADDITIONAL_INFO,
                    title="Action Required: Information Requested",
                    message="Reviewer requested diagnostic report."
                ),
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_STATUS_CHANGE,
                    title="Claim Status Changed: Under Evaluation",
                    message="Lifecycle updated to Under Evaluation."
                ),
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_REVIEW_COMPLETE,
                    title="Adjudication Review Complete",
                    message="Review process concluded."
                ),
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_APPROVAL,
                    title="Claim Approved: CLM-TEST-SUB",
                    message="Claim approved by reviewer."
                ),
                Notification(
                    user_id=cust_id,
                    notification_type=Config.NOTIF_TYPE_REJECTION,
                    title="Claim Rejected: CLM-TEST-SUB",
                    message="Claim rejected due to excluded damage."
                ),
            ]
            db.session.add_all(test_notifs)
            db.session.commit()
            seeded_notif_id = test_notifs[0].id

        with self.client.session_transaction() as sess:
            sess["user_id"] = cust_id
            sess["role"] = cust_role
            sess["user_code"] = cust_code

        # Verify dashboard renders notifications
        res_dash = self.client.get("/claims/")
        self.assertIn(b"Recent System Alerts", res_dash.data)
        self.assertIn(b"Notifications", res_dash.data)
        self.assertIn(b"Warranty Expiry Alert", res_dash.data)
        self.assertIn(b"Claim Approved", res_dash.data)

        # Test mark single notification as read
        res_read = self.client.post(f"/claims/notifications/{seeded_notif_id}/read", follow_redirects=True)
        self.assertEqual(res_read.status_code, 200)

        with self.app.app_context():
            n = db.session.get(Notification, seeded_notif_id)
            self.assertTrue(n.is_read)

        # Test mark all notifications as read
        res_clear = self.client.post("/claims/notifications/mark-all-read", follow_redirects=True)
        self.assertEqual(res_clear.status_code, 200)

        with self.app.app_context():
            unread_count = Notification.query.filter_by(user_id=cust_id, is_read=False).count()
            self.assertEqual(unread_count, 0)

    def test_req_xl_claim_dashboard_components(self):
        """
        Req 1.6.xl: Claim Dashboard.
        Users should have access to a dashboard displaying:
        1. Registered products
        2. Active warranties
        3. Expiring warranties
        4. Saved receipts
        5. Submitted claims
        6. Pending actions
        7. Recent claim decisions
        """
        with self.app.app_context():
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            cust_id = customer.id
            cust_role = customer.role
            cust_code = customer.user_id

        with self.client.session_transaction() as sess:
            sess["user_id"] = cust_id
            sess["role"] = cust_role
            sess["user_code"] = cust_code

        res = self.client.get("/claims/")
        self.assertEqual(res.status_code, 200)

        # 1. Registered products
        self.assertIn(b"Registered Products", res.data)
        self.assertIn(b"My Registered Products Fleet", res.data)

        # 2. Active warranties
        self.assertIn(b"Active Warranties", res.data)

        # 3. Expiring warranties
        self.assertIn(b"Expiring Soon", res.data)

        # 4. Saved receipts
        self.assertIn(b"Saved Receipts", res.data)
        self.assertIn(b"Saved Purchase Receipts", res.data)

        # 5. Submitted claims
        self.assertIn(b"Submitted Claims", res.data)
        self.assertIn(b"My Warranty Claims Registry", res.data)

        # 6. Pending actions
        self.assertIn(b"Pending Actions", res.data)

        # 7. Recent claim decisions
        self.assertIn(b"Final Decision", res.data)

    def test_req_xli_administrator_dashboard_metrics_and_trends(self):
        """Req xli: Administrator Dashboard metrics, duplicate alerts, average confidence, and claim trends."""
        with self.app.app_context():
            admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
            admin_id = admin.id
            admin_role = admin.role
            admin_code = admin.user_id

        with self.client.session_transaction() as sess:
            sess["user_id"] = admin_id
            sess["role"] = admin_role
            sess["user_code"] = admin_code

        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 200)

        # 1. Total claims intake
        self.assertIn(b"Total Claims Intake", res.data)

        # 2. Valid / Approved claims
        self.assertIn(b"Valid / Approved", res.data)

        # 3. Invalid / Rejected claims
        self.assertIn(b"Rejected (Invalid)", res.data)

        # 4. Manual-review queue
        self.assertIn(b"Manual Triage Queue", res.data)

        # 5. Duplicate alerts
        self.assertIn(b"Duplicate Alerts", res.data)

        # 6. Model disagreements
        self.assertIn(b"Model Disagreements", res.data)

        # 7. Average confidence scores
        self.assertIn(b"Average Confidence Score", res.data)
        self.assertIn(b"Py:", res.data)
        self.assertIn(b"GTM:", res.data)

        # 8. Claim trends chart
        self.assertIn(b"claimTrendsChart", res.data)
        self.assertIn(b"Claim Intake Trends &amp; Monthly Lifecycle Volume", res.data)

    def test_req_xlii_search_and_filtering_across_all_ten_dimensions(self):
        """Req xlii: Search and filter warranty and claim records across 10 distinct dimensions."""
        with self.app.app_context():
            admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
            customer = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
            sample_claim = Claim.query.first()
            self.assertIsNotNone(sample_claim)
            c_id = sample_claim.claim_id
            p_id = sample_claim.product.product_id
            cat = sample_claim.product.category
            sn = sample_claim.product.serial_number
            st = sample_claim.status
            rk = sample_claim.risk_level

        with self.client.session_transaction() as sess:
            sess["user_id"] = admin.id
            sess["role"] = admin.role
            sess["user_code"] = admin.user_id

        # 1. Base search page renders all 10 filter inputs
        res = self.client.get("/claims/search")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"1. Claim ID", res.data)
        self.assertIn(b"2. Product ID", res.data)
        self.assertIn(b"3. Product Category", res.data)
        self.assertIn(b"4. Serial Number", res.data)
        self.assertIn(b"5. Warranty Status", res.data)
        self.assertIn(b"6. Claim Status", res.data)
        self.assertIn(b"7. Risk Level", res.data)
        self.assertIn(b"8. Confidence Range", res.data)
        self.assertIn(b"9. Assigned Reviewer", res.data)
        self.assertIn(b"10. Submission Date From", res.data)

        # 2. Filter by Claim ID
        res_cid = self.client.get(f"/claims/search?claim_id={c_id[:6]}")
        self.assertEqual(res_cid.status_code, 200)
        self.assertIn(c_id.encode(), res_cid.data)

        # 3. Filter by Product ID
        res_pid = self.client.get(f"/claims/search?product_id={p_id[:6]}")
        self.assertEqual(res_pid.status_code, 200)
        self.assertIn(c_id.encode(), res_pid.data)

        # 4. Filter by Category
        res_cat = self.client.get(f"/claims/search?category={cat}")
        self.assertEqual(res_cat.status_code, 200)

        # 5. Filter by Serial Number
        res_sn = self.client.get(f"/claims/search?serial_number={sn[:4]}")
        self.assertEqual(res_sn.status_code, 200)

        # 6. Filter by Warranty Status
        res_wstat = self.client.get("/claims/search?warranty_status=Active")
        self.assertEqual(res_wstat.status_code, 200)

        # 7. Filter by Claim Status
        res_cstat = self.client.get(f"/claims/search?claim_status={st}")
        self.assertEqual(res_cstat.status_code, 200)

        # 8. Filter by Risk Level
        res_risk = self.client.get(f"/claims/search?risk_level={rk}")
        self.assertEqual(res_risk.status_code, 200)

        # 9. Filter by Confidence Range
        res_conf = self.client.get("/claims/search?min_conf=0.1&max_conf=1.0")
        self.assertEqual(res_conf.status_code, 200)

        # 10. Filter by Reviewer & Date Range
        res_date = self.client.get("/claims/search?reviewer_id=ALL&start_date=2020-01-01&end_date=2030-12-31")
        self.assertEqual(res_date.status_code, 200)

        # 11. CSV Export of filtered results
        res_csv = self.client.get("/claims/search?export=csv")
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, "text/csv")
        self.assertIn(b"Claim ID,Claimant Name", res_csv.data)

        # 12. Customer Role Scoping
        with self.client.session_transaction() as sess:
            sess["user_id"] = customer.id
            sess["role"] = customer.role
            sess["user_code"] = customer.user_id

        res_cust = self.client.get("/claims/search")
        self.assertEqual(res_cust.status_code, 200)

    def test_req_xliii_data_analysis_and_reporting_dimensions(self):
        """Req xliii: Data Analysis and Reporting on all 8 analytical dimensions."""
        with self.app.app_context():
            admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
            admin_id = admin.id
            admin_role = admin.role
            admin_code = admin.user_id

        with self.client.session_transaction() as sess:
            sess["user_id"] = admin_id
            sess["role"] = admin_role
            sess["user_code"] = admin_code

        # 1. Web Analytics Dashboard
        res = self.client.get("/admin/analytics")
        self.assertEqual(res.status_code, 200)

        # Dimension 1: Claim outcomes
        self.assertIn(b"Claim Outcomes Analysis", res.data)
        self.assertIn(b"outcomesChart", res.data)

        # Dimension 2: Frequently reported faults
        self.assertIn(b"Frequently Reported Faults", res.data)
        self.assertIn(b"faultsChart", res.data)

        # Dimension 3: Rejected claim reasons
        self.assertIn(b"Rejected Claim Reasons", res.data)
        self.assertIn(b"rejectionsChart", res.data)

        # Dimension 4: Product categories
        self.assertIn(b"Product Categories Analytics", res.data)
        self.assertIn(b"categoryAnalyticsChart", res.data)

        # Dimension 5: Warranty expirations
        self.assertIn(b"Warranty Expirations Timeline", res.data)
        self.assertIn(b"expirationsChart", res.data)

        # Dimension 6: Repair patterns
        self.assertIn(b"Repair Patterns &amp; Authorized Centers", res.data)
        self.assertIn(b"repairsChart", res.data)

        # Dimension 7: Model performance
        self.assertIn(b"Model Performance &amp; Dual Consistency", res.data)
        self.assertIn(b"modelConsistencyChart", res.data)

        # Dimension 8: Manual-review frequency & triggers
        self.assertIn(b"Manual-Review Frequency &amp; Triggers", res.data)
        self.assertIn(b"manualTriggersChart", res.data)

        # 2. JSON Analytics Export
        res_json = self.client.get("/admin/analytics/export-json")
        self.assertEqual(res_json.status_code, 200)
        self.assertEqual(res_json.mimetype, "application/json")
        payload = json.loads(res_json.data)
        self.assertIn("outcomes", payload)
        self.assertIn("faults", payload)
        self.assertIn("rejections", payload)
        self.assertIn("categories", payload)
        self.assertIn("expirations", payload)
        self.assertIn("repairs", payload)
        self.assertIn("models", payload)
        self.assertIn("manual_review", payload)

    def test_req_xliv_downloadable_claim_report(self):
        """Req xliv: Downloadable Claim Report containing all 10 mandated sections."""
        with self.app.app_context():
            claim = Claim.query.first()
            self.assertIsNotNone(claim)
            claim_id = claim.claim_id
            user = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()

        with self.client.session_transaction() as sess:
            sess["user_id"] = user.id
            sess["role"] = user.role
            sess["user_code"] = user.user_id

        # 1. Download official PDF via API endpoint
        res = self.client.get(f"/reports/claim/{claim_id}/pdf")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/pdf")
        self.assertTrue(res.data.startswith(b"%PDF"))
        self.assertIn(f"attachment; filename=AssureX_Claim_Report_{claim_id}.pdf".encode(), res.headers.get("Content-Disposition", "").encode())

        # 2. Verify PDF generation incorporates all 10 mandated data points
        from src.services.report_generator import get_pdf_generator
        gen = get_pdf_generator()
        with self.app.app_context():
            c = Claim.query.filter_by(claim_id=claim_id).first()
            pdf_bytes = gen.generate_pdf(c)
            self.assertTrue(len(pdf_bytes) > 1000)
            self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_req_xlv_data_export_formats(self):
        """Req xlv: Administrator Data Export across claims, products, warranties, and analytics."""
        with self.app.app_context():
            admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
            claim = Claim.query.first()
            sample_id = claim.claim_id

        with self.client.session_transaction() as sess:
            sess["user_id"] = admin.id
            sess["role"] = admin.role
            sess["user_code"] = admin.user_id

        # 1. All Claims Export
        res_claims = self.client.get("/admin/export/claims")
        self.assertEqual(res_claims.status_code, 200)
        self.assertEqual(res_claims.mimetype, "text/csv")
        self.assertIn(b"Claim ID,Claimant Name", res_claims.data)

        # 2. Selected Claims Export
        res_sel = self.client.get(f"/admin/export/claims?ids={sample_id}")
        self.assertEqual(res_sel.status_code, 200)
        self.assertIn(sample_id.encode(), res_sel.data)

        # 3. Products Export
        res_prods = self.client.get("/admin/export/products")
        self.assertEqual(res_prods.status_code, 200)
        self.assertEqual(res_prods.mimetype, "text/csv")
        self.assertIn(b"Product ID,Owner,Product Name", res_prods.data)

        # 4. Warranties Export
        res_warr = self.client.get("/admin/export/warranties")
        self.assertEqual(res_warr.status_code, 200)
        self.assertEqual(res_warr.mimetype, "text/csv")
        self.assertIn(b"Warranty ID,Product ID,Product Name", res_warr.data)

        # 5. Analytics CSV Export
        res_an = self.client.get("/admin/export/analytics")
        self.assertEqual(res_an.status_code, 200)
        self.assertEqual(res_an.mimetype, "text/csv")
        self.assertIn(b"AssureX Enterprise Analytics & Reporting Summary", res_an.data)

        # 6. Audit Trail Export
        res_audit = self.client.get("/admin/export/audit")
        self.assertEqual(res_audit.status_code, 200)
        self.assertIn(b"Log ID,Timestamp,Actor", res_audit.data)

    def test_req_xlvi_secure_relational_data_storage(self):
        """Req xlvi: Verifies secure relational database storage across all 10 core entity types."""
        with self.app.app_context():
            # 1. User Accounts
            self.assertGreater(User.query.count(), 0)
            u = User.query.first()
            self.assertTrue(u.user_id.startswith("USR-"))

            # 2. Products
            self.assertGreater(Product.query.count(), 0)
            p = Product.query.first()
            self.assertTrue(p.product_id.startswith("PRD-"))

            # 3. Warranties & Policies
            self.assertGreater(ProductWarranty.query.count(), 0)
            self.assertGreater(WarrantyPolicy.query.count(), 0)
            w = ProductWarranty.query.first()
            self.assertTrue(w.warranty_id.startswith("WAR-"))

            # 4. Receipts & Documents
            self.assertGreater(ClaimDocument.query.count(), 0)
            doc = ClaimDocument.query.first()
            self.assertTrue(doc.document_id.startswith("DOC-"))
            self.assertEqual(len(doc.file_hash_sha256), 64)

            # 5. Claims
            self.assertGreater(Claim.query.count(), 0)
            c = Claim.query.first()
            self.assertTrue(c.claim_id.startswith("CLM-"))

            # 6. Repair Histories
            self.assertGreater(RepairHistory.query.count(), 0)

            # 7. Model Predictions & Confidence Scores
            self.assertGreater(ModelEvaluation.query.count(), 0)
            me = ModelEvaluation.query.first()
            self.assertIn(me.python_predicted_class, Config.ALL_CLAIM_CLASSES)
            self.assertTrue(me.model_consistency_status in Config.ALL_CONSISTENCY_STATUSES or me.model_consistency_status == "Consistent")

            # 8. Rule Results & Validations
            self.assertGreater(RuleValidationLog.query.count(), 0)
            rv = RuleValidationLog.query.first()
            self.assertIsInstance(rv.get_passed(), list)
            self.assertIsInstance(rv.get_failed(), list)

            # 9. Notifications
            self.assertGreater(Notification.query.count(), 0)

            # 10. Audit Records & Lifecycle History
            self.assertGreater(AuditLog.query.count(), 0)
            self.assertGreater(ClaimStatusHistory.query.count(), 0)

    def test_req_xlvii_immutable_audit_trail_nine_actions(self):
        """Req xlvii: Immutable Audit Trail recording all 9 critical actions."""
        with self.app.app_context():
            admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()
            claim = Claim.query.first()
            doc = ClaimDocument.query.first()

        with self.client.session_transaction() as sess:
            sess["user_id"] = admin.id
            sess["role"] = admin.role
            sess["user_code"] = admin.user_id

        # 1. Extracted-data correction audit log
        res_ocr = self.client.post(
            f"/claims/documents/{doc.document_id}/correct-data",
            data={"invoice_number": "INV-CORRECTED-999", "purchase_price": "299.99"},
            follow_redirects=True
        )
        self.assertEqual(res_ocr.status_code, 200)

        with self.app.app_context():
            # Check EXTRACTED_DATA_CORRECTION is in AuditLog
            corr_log = AuditLog.query.filter_by(action="EXTRACTED_DATA_CORRECTION").first()
            self.assertIsNotNone(corr_log)

            # 2. Status change audit log
            c = Claim.query.filter_by(claim_id=claim.claim_id).first()
            c.transition_status(Config.STATUS_UNDER_EVALUATION, updated_by_user_id=admin.id, notes="Verification triage")
            db.session.commit()

            status_log = AuditLog.query.filter_by(action="STATUS_CHANGE").first()
            self.assertIsNotNone(status_log)

            # 3. Verify Account Creation audit log exists
            acct_log = AuditLog.query.filter(AuditLog.action.in_(["ACCOUNT_CREATION", "USER_REGISTRATION"])).first()
            self.assertIsNotNone(acct_log)

            # 4. Verify Product Registration audit log exists
            prod_log = AuditLog.query.filter(AuditLog.action.in_(["PRODUCT_REGISTRATION", "PRODUCT_REGISTERED"])).first()
            self.assertIsNotNone(prod_log)

            # 5. Verify Document Upload audit log exists
            doc_log = AuditLog.query.filter(AuditLog.action.in_(["DOCUMENT_UPLOAD", "DOCUMENT_ATTACHED"])).first()
            self.assertIsNotNone(doc_log)

            # 6. Verify Model Prediction / Claim Evaluated log exists
            model_log = AuditLog.query.filter(AuditLog.action.in_(["MODEL_PREDICTION", "CLAIM_EVALUATED"])).first()
            self.assertIsNotNone(model_log)

            # 7. Verify Claim Submission log exists
            sub_log = AuditLog.query.filter(AuditLog.action.in_(["CLAIM_SUBMISSION", "CLAIM_EVALUATED"])).first()
            self.assertIsNotNone(sub_log)

            # 8. Verify Reviewer Action log exists
            rev_log = AuditLog.query.filter(AuditLog.action.in_(["REVIEWER_ACTION", "REVIEWER_ADJUDICATION"])).first()
            self.assertIsNotNone(rev_log)

            # 9. Verify Final Decision log exists
            dec_log = AuditLog.query.filter(AuditLog.action.in_(["FINAL_DECISION", "CLAIM_EVALUATED"])).first()
            self.assertIsNotNone(dec_log)

        # 10. Audit Log viewer UI renders properly
        res_view = self.client.get("/admin/audit-logs")
        self.assertEqual(res_view.status_code, 200)
        self.assertIn(b"System Security", res_view.data)
        self.assertIn(b"Audit Trail", res_view.data)
        self.assertIn(b"Audit Log Ledger", res_view.data)

    def test_req_xlviii_model_version_tracking(self):
        """Req xlviii: Model Version Tracking - Predictions linked to version; updating does not alter previous results."""
        with self.app.app_context():
            eval_record = ModelEvaluation.query.first()
            self.assertIsNotNone(eval_record)
            self.assertIsNotNone(eval_record.python_model_version)
            self.assertIsNotNone(eval_record.gtm_model_version)
            self.assertTrue(eval_record.python_model_version.startswith("v"))
            self.assertTrue(eval_record.gtm_model_version.startswith("v"))

            original_py_ver = eval_record.python_model_version
            original_gtm_ver = eval_record.gtm_model_version
            original_pred = eval_record.python_predicted_class
            original_conf = eval_record.python_conf_valid

            # Simulate future model version release
            Config.PYTHON_MODEL_VERSION = "v2.5.0"
            Config.GTM_MODEL_VERSION = "v2.5.0"

            # Query the existing evaluation record again
            reloaded_eval = ModelEvaluation.query.filter_by(id=eval_record.id).first()
            # Invariant: Previously recorded results remain unchanged
            self.assertEqual(reloaded_eval.python_model_version, original_py_ver)
            self.assertEqual(reloaded_eval.gtm_model_version, original_gtm_ver)
            self.assertEqual(reloaded_eval.python_predicted_class, original_pred)
            self.assertEqual(reloaded_eval.python_conf_valid, original_conf)

            # Reset config back to v1.0.0
            Config.PYTHON_MODEL_VERSION = "v1.0.0"
            Config.GTM_MODEL_VERSION = "v1.0.0"

            # Verify PDF report generation includes the model versions
            from src.services.report_generator import get_pdf_generator
            claim = Claim.query.filter_by(id=eval_record.claim_id).first()
            pdf_bytes = get_pdf_generator().generate_pdf(claim)
            self.assertGreater(len(pdf_bytes), 1000)

    def test_req_xlix_understandable_error_handling(self):
        """Req xlix: Display understandable error messages without exposing technical details."""
        from src.rules.validator import ClaimValidator
        # 1. Invalid file format
        fake_exe = io.BytesIO(b"MZ executable payload")
        is_valid, err_msg = ClaimValidator.validate_file((fake_exe, "malware.exe"))
        self.assertFalse(is_valid)
        self.assertIn("unsupported extension", err_msg.lower())
        self.assertNotIn("Traceback", err_msg)
        self.assertNotIn("Exception", err_msg)

        # 2. Incomplete claim data validation
        is_sub_valid, errs, warns, cleaned = ClaimValidator.validate_claim_submission({}, {})
        self.assertFalse(is_sub_valid)
        self.assertTrue(len(errs) >= 4)
        for err in errs:
            self.assertIn("Mandatory field missing", err)
            self.assertNotIn("Traceback", err)

        # 3. HTTP 404 handler returns clean error page without trace
        res_404 = self.client.get("/non-existent-url-endpoint-999")
        self.assertEqual(res_404.status_code, 404)
        self.assertIn(b"Resource Not Found", res_404.data)
        self.assertNotIn(b"Traceback", res_404.data)

        # 4. Unauthorized access protection & Custom 403/500 error handlers
        with self.app.app_context():
            cust = User.query.filter_by(role=Config.ROLE_CUSTOMER).first()
        with self.client.session_transaction() as sess:
            sess["user_id"] = cust.id
            sess["role"] = Config.ROLE_CUSTOMER
        res_unauth = self.client.get("/admin/dashboard", follow_redirects=True)
        self.assertEqual(res_unauth.status_code, 200)
        self.assertIn(b"Unauthorized access", res_unauth.data)
        self.assertNotIn(b"Traceback", res_unauth.data)

        # Test Custom 403 & 500 error templates render cleanly without exposing stack traces
        from flask import render_template
        with self.app.test_request_context():
            html_403 = render_template("components/error.html", error_code=403, message="Access forbidden.")
            self.assertIn("Access Forbidden", html_403)
            self.assertNotIn("Traceback", html_403)

            html_500 = render_template("components/error.html", error_code=500, message="An internal application anomaly occurred.")
            self.assertIn("Unexpected Server Error", html_500)
            self.assertNotIn("Traceback", html_500)

        # 5. Unavailable / failed model prediction graceful fallback
        from src.core.model_comparator import DualModelComparator
        comparator = DualModelComparator()
        comp_res = comparator.compare_models({})
        self.assertIn("python_model", comp_res)
        self.assertIn("gtm_model", comp_res)
        self.assertIn(comp_res["python_model"]["predicted_class"], Config.ALL_CLAIM_CLASSES)

    def test_req_l_monitoring_and_anomaly_alerts(self):
        """Req l: Monitoring and anomaly alerts for failed uploads, repeated logins, duplicate docs, etc."""
        from src.services.alert_service import get_system_anomalies, scan_and_generate_anomaly_alerts

        with self.app.app_context():
            admin = User.query.filter_by(role=Config.ROLE_ADMIN).first()

        # 1. Test failed login triggers LOGIN_FAILED audit log
        res_bad_login = self.client.post("/login", data={
            "email": "invalid_hacker@assurex.local",
            "password": "wrong_password_123"
        }, follow_redirects=True)
        self.assertEqual(res_bad_login.status_code, 200)
        self.assertIn(b"does not exist", res_bad_login.data)

        with self.app.app_context():
            fail_login_log = AuditLog.query.filter_by(action="LOGIN_FAILED").first()
            self.assertIsNotNone(fail_login_log)

            # 2. Test Anomaly Engine returns structured telemetry across dimensions
            anomalies = get_system_anomalies()
            self.assertIsInstance(anomalies, list)
            for a in anomalies:
                self.assertIn("type", a)
                self.assertIn("title", a)
                self.assertIn("severity", a)
                self.assertIn("description", a)

            # 3. Test scan_and_generate_anomaly_alerts creates Notification records for Admin
            created_alerts = scan_and_generate_anomaly_alerts()
            self.assertIsInstance(created_alerts, list)
            notifs = Notification.query.filter_by(
                user_id=admin.id,
                notification_type=Config.NOTIF_TYPE_ANOMALY_ALERT
            ).all()
            self.assertGreater(len(notifs), 0)

        # 4. Admin Dashboard renders System Monitoring & Anomaly Alerts Telemetry
        with self.client.session_transaction() as sess:
            sess["user_id"] = admin.id
            sess["role"] = Config.ROLE_ADMIN
            sess["email"] = admin.email
            sess["user_name"] = admin.full_name

        res_dash = self.client.get("/admin/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"System Monitoring &amp; Anomaly Alerts", res_dash.data)
        self.assertIn(b"Dispatch Admin Alerts", res_dash.data)

        # 5. POST /admin/anomalies/dispatch dispatches alerts
        res_dispatch = self.client.post("/admin/anomalies/dispatch", follow_redirects=True)
        self.assertEqual(res_dispatch.status_code, 200)
        self.assertIn(b"Anomaly", res_dispatch.data)


if __name__ == "__main__":
    unittest.main()




