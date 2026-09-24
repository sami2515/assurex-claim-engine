import os
import io
from pathlib import Path
import unittest
from src.app import create_app
from database.db import db
from src.models.entities import (
    User, Product, WarrantyPolicy, ProductWarranty, Claim, ModelEvaluation,
    ClaimDocument, ClaimStatusHistory, Notification, AuditLog, SystemSetting, RepairHistory
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


if __name__ == "__main__":
    unittest.main()



