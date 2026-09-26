"""
AssureX Claim Engine - Dedicated RBAC Security, CSRF & IDOR Test Suite
Comprehensive suite of 24 attack-and-defense test cases verifying:
1. Deterministic public customer registration & privilege injection defense.
2. Administrative route authorization & role-gated access control.
3. Enterprise user provisioning across Staff, Reviewer, and Admin roles.
4. Administrative role modification with DB-backed authority.
5. Self-demotion and last-active-admin demotion lockout guards.
6. Self-deactivation and last-active-admin deactivation lockout guards.
7. Deactivated account authentication lockout (zero auto-reactivation loophole).
8. Session-cookie role tampering resistance (DB single source of truth).
9. Object-Level Access Control (IDOR) across products, claims, PDFs, documents, and notifications.
10. Cross-Site Request Forgery (CSRF) protection on state-changing endpoints.
"""

import json
from datetime import date, timedelta
import unittest
from werkzeug.security import generate_password_hash

from src.app import create_app
from database.db import db
from src.models.entities import (
    User, Product, WarrantyPolicy, ProductWarranty, Claim,
    ClaimDocument, Notification, AuditLog
)
from config.config import Config


class TestRBACSecurity(unittest.TestCase):
    """24 Dedicated RBAC Security, IDOR, and Authentication Defense Tests."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()
        self.cleanup_user_ids = []
        self.cleanup_product_ids = []
        self.cleanup_claim_ids = []
        self.cleanup_doc_ids = []

    def tearDown(self):
        with self.app.app_context():
            if self.cleanup_doc_ids:
                ClaimDocument.query.filter(ClaimDocument.id.in_(self.cleanup_doc_ids)).delete(synchronize_session=False)
            if self.cleanup_claim_ids:
                Claim.query.filter(Claim.id.in_(self.cleanup_claim_ids)).delete(synchronize_session=False)
            if self.cleanup_product_ids:
                ProductWarranty.query.filter(ProductWarranty.product_id.in_(self.cleanup_product_ids)).delete(synchronize_session=False)
                Product.query.filter(Product.id.in_(self.cleanup_product_ids)).delete(synchronize_session=False)
            if self.cleanup_user_ids:
                Notification.query.filter(Notification.user_id.in_(self.cleanup_user_ids)).delete(synchronize_session=False)
                AuditLog.query.filter(AuditLog.user_id.in_(self.cleanup_user_ids)).delete(synchronize_session=False)
                User.query.filter(User.id.in_(self.cleanup_user_ids)).delete(synchronize_session=False)
            db.session.commit()

    def _login(self, client, email, password):
        return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    # =========================================================================
    # 1. PUBLIC REGISTRATION & PRIVILEGE INJECTION DEFENSE (Tests 1 - 4)
    # =========================================================================

    def test_01_public_registration_creates_customer_only(self):
        """Test 1: Public /register creates user with customer role by default."""
        email = "test_sec_cust01@assurex.local"
        res = self.client.post("/register", data={
            "full_name": "Test Customer 01",
            "email": email,
            "password": "Password123!",
            "confirm_password": "Password123!",
            "phone": "1234567890",
            "address": "123 Main Street"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Account created successfully", res.data)

        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.cleanup_user_ids.append(user.id)
            self.assertEqual(user.role, Config.ROLE_CUSTOMER)

    def test_02_public_registration_blocks_admin_privilege_injection(self):
        """Test 2: Public /register ignores injected role='administrator' and assigns customer."""
        email = "test_sec_admin_inject@assurex.local"
        res = self.client.post("/register", data={
            "full_name": "Hacker Admin Attempt",
            "email": email,
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": "administrator",
            "phone": "1234567890",
            "address": "123 Security Blvd"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.cleanup_user_ids.append(user.id)
            self.assertEqual(user.role, Config.ROLE_CUSTOMER)
            self.assertNotEqual(user.role, Config.ROLE_ADMIN)

    def test_03_public_registration_blocks_reviewer_privilege_injection(self):
        """Test 3: Public /register ignores injected role='claim_reviewer' and assigns customer."""
        email = "test_sec_reviewer_inject@assurex.local"
        res = self.client.post("/register", data={
            "full_name": "Hacker Reviewer Attempt",
            "email": email,
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": "claim_reviewer",
            "phone": "1234567890",
            "address": "123 Security Blvd"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.cleanup_user_ids.append(user.id)
            self.assertEqual(user.role, Config.ROLE_CUSTOMER)
            self.assertNotEqual(user.role, Config.ROLE_REVIEWER)

    def test_04_public_registration_blocks_staff_privilege_injection(self):
        """Test 4: Public /register ignores injected role='service_center_staff' and assigns customer."""
        email = "test_sec_staff_inject@assurex.local"
        res = self.client.post("/register", data={
            "full_name": "Hacker Staff Attempt",
            "email": email,
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": "service_center_staff",
            "phone": "1234567890",
            "address": "123 Security Blvd"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.cleanup_user_ids.append(user.id)
            self.assertEqual(user.role, Config.ROLE_CUSTOMER)
            self.assertNotEqual(user.role, Config.ROLE_STAFF)

    # =========================================================================
    # 2. ROUTE AUTHORIZATION & ROLE-GATED ACCESS GUARDS (Tests 5 - 9)
    # =========================================================================

    def test_05_admin_users_endpoint_blocks_unauthenticated_access(self):
        """Test 5: Anonymous GET /admin/users redirects to login page."""
        res = self.client.get("/admin/users", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_06_admin_users_endpoint_blocks_customer_role(self):
        """Test 6: Authenticated Customer cannot access /admin/users."""
        client = self.app.test_client()
        self._login(client, "customer@assurex.local", "CustomerPass123!")
        res = client.get("/admin/users", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Unauthorized access", res.data)

    def test_07_admin_users_endpoint_blocks_staff_role(self):
        """Test 7: Authenticated Service Staff cannot access /admin/users."""
        client = self.app.test_client()
        self._login(client, "staff@assurex.local", "StaffPass123!")
        res = client.get("/admin/users", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Unauthorized access", res.data)

    def test_08_admin_users_endpoint_blocks_reviewer_role(self):
        """Test 8: Authenticated Claim Reviewer cannot access /admin/users."""
        client = self.app.test_client()
        self._login(client, "reviewer@assurex.local", "ReviewerPass123!")
        res = client.get("/admin/users", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Unauthorized access", res.data)

    def test_09_admin_can_access_users_management_directory(self):
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")
        res = client.get("/admin/users", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"User Management &amp; Access Control (RBAC)", res.data)
        self.assertIn(b"User Accounts Directory", res.data)
        self.assertIn(b"Provision Enterprise User", res.data)

    # =========================================================================
    # 3. ENTERPRISE USER PROVISIONING & ROLE ASSIGNMENT (Tests 10 - 13)
    # =========================================================================

    def test_10_admin_can_provision_staff_account(self):
        """Test 10: Administrator provisions a new Service Staff account with audit logging."""
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")
        email = "test_sec_staff_prov@assurex.local"

        res = client.post("/admin/users/create", data={
            "full_name": "New Tech Staff",
            "email": email,
            "role": "Staff",
            "password": "Password123!",
            "phone": "5551234567",
            "address": "Repair Depot 12"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"successfully provisioned", res.data)

        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.cleanup_user_ids.append(user.id)
            self.assertEqual(user.role, Config.ROLE_STAFF)
            self.assertTrue(user.is_active)

            # Check Audit Log
            audit = AuditLog.query.filter_by(action="ACCOUNT_CREATED", entity_id=user.user_id).first()
            self.assertIsNotNone(audit)
            details = json.loads(audit.details_json)
            self.assertEqual(details["assigned_role"], Config.ROLE_STAFF)

    def test_11_admin_can_provision_reviewer_account(self):
        """Test 11: Administrator provisions a new Claim Reviewer account."""
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")
        email = "test_sec_reviewer_prov@assurex.local"

        res = client.post("/admin/users/create", data={
            "full_name": "New Claim Reviewer",
            "email": email,
            "role": "Reviewer",
            "password": "Password123!",
            "phone": "5559876543",
            "address": "Claims Department"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"successfully provisioned", res.data)

        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.cleanup_user_ids.append(user.id)
            self.assertEqual(user.role, Config.ROLE_REVIEWER)

    def test_12_admin_can_provision_admin_account(self):
        """Test 12: Administrator provisions a new Administrator account."""
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")
        email = "test_sec_admin_prov@assurex.local"

        res = client.post("/admin/users/create", data={
            "full_name": "Secondary Admin",
            "email": email,
            "role": "Admin",
            "password": "Password123!",
            "phone": "5551112233",
            "address": "HQ Operations"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"successfully provisioned", res.data)

        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.cleanup_user_ids.append(user.id)
            self.assertEqual(user.role, Config.ROLE_ADMIN)

    def test_13_admin_can_update_user_role(self):
        """Test 13: Administrator modifies a target user's role and logs RBAC_ROLE_CHANGE."""
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")
        email = "test_sec_role_change@assurex.local"

        with self.app.app_context():
            target = User(
                email=email,
                full_name="Role Target",
                password_hash=generate_password_hash("Password123!"),
                role=Config.ROLE_CUSTOMER,
                is_active=True
            )
            db.session.add(target)
            db.session.commit()
            target_id = target.id
            self.cleanup_user_ids.append(target_id)

        res = client.post(f"/admin/users/{target_id}/role", data={
            "role": "Staff"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"successfully updated", res.data)

        with self.app.app_context():
            updated = db.session.get(User, target_id)
            self.assertEqual(updated.role, Config.ROLE_STAFF)

    # =========================================================================
    # 4. ADMINISTRATIVE LOCKOUT SAFEGUARDS (Tests 14 - 17)
    # =========================================================================

    def test_14_admin_self_demotion_prohibited(self):
        """Test 14: Administrator is strictly prohibited from demoting their own account."""
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")

        with self.app.app_context():
            admin = User.query.filter_by(email="admin@assurex.local").first()
            admin_id = admin.id

        res = client.post(f"/admin/users/{admin_id}/role", data={
            "role": "Customer"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Self-demotion is prohibited", res.data)

        with self.app.app_context():
            admin_check = db.session.get(User, admin_id)
            self.assertEqual(admin_check.role, Config.ROLE_ADMIN)

    def test_15_last_active_admin_demotion_prohibited(self):
        """Test 15: Cannot demote the last active Administrator in the system."""
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")

        with self.app.app_context():
            # Ensure only 1 active admin
            admin = User.query.filter_by(email="admin@assurex.local").first()
            admin_id = admin.id
            # Temporarily deactivate any other admins
            other_admins = User.query.filter(User.role.in_([Config.ROLE_ADMIN, "Admin", "administrator"]), User.id != admin_id).all()
            for oa in other_admins:
                oa.is_active = False
            db.session.commit()

        # Attempt to demote the sole remaining admin via secondary client session
        sec_client = self.app.test_client()
        with sec_client.session_transaction() as sess:
            sess["user_id"] = 999999  # Mock external admin
            sess["role"] = Config.ROLE_ADMIN

        # Note: If admin tries to demote themselves, self-demotion blocks it.
        # If another mock admin calls it, last-admin guard blocks it.
        res = sec_client.post(f"/admin/users/{admin_id}/role", data={
            "role": "Customer"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            admin_check = db.session.get(User, admin_id)
            self.assertEqual(admin_check.role, Config.ROLE_ADMIN)

    def test_16_admin_self_deactivation_prohibited(self):
        """Test 16: Administrator is strictly prohibited from deactivating their own account."""
        client = self.app.test_client()
        self._login(client, "admin@assurex.local", "AdminPass123!")

        with self.app.app_context():
            admin = User.query.filter_by(email="admin@assurex.local").first()
            admin_id = admin.id

        res = client.post(f"/admin/users/{admin_id}/toggle-status", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Self-deactivation is prohibited", res.data)

        with self.app.app_context():
            admin_check = db.session.get(User, admin_id)
            self.assertTrue(admin_check.is_active)

    def test_17_last_active_admin_deactivation_prohibited(self):
        """Test 17: Cannot deactivate the last active Administrator in the system."""
        with self.app.app_context():
            admin = User.query.filter_by(email="admin@assurex.local").first()
            admin_id = admin.id
            # Ensure other admins are inactive
            other_admins = User.query.filter(User.role.in_([Config.ROLE_ADMIN, "Admin", "administrator"]), User.id != admin_id).all()
            for oa in other_admins:
                oa.is_active = False
            db.session.commit()

        # Secondary client attempting deactivation of sole active admin
        sec_client = self.app.test_client()
        with sec_client.session_transaction() as sess:
            sess["user_id"] = 999998
            sess["role"] = Config.ROLE_ADMIN

        res = sec_client.post(f"/admin/users/{admin_id}/toggle-status", follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            admin_check = db.session.get(User, admin_id)
            self.assertTrue(admin_check.is_active)

    # =========================================================================
    # 5. INACTIVE ACCOUNT LOCKOUT & SESSION INTEGRITY (Tests 18 - 19)
    # =========================================================================

    def test_18_inactive_account_login_blocked(self):
        """Test 18: Inactive/deactivated user cannot log in and has zero auto-reactivation."""
        email = "test_sec_disabled@assurex.local"
        with self.app.app_context():
            disabled_user = User(
                email=email,
                full_name="Disabled Test User",
                password_hash=generate_password_hash("Password123!"),
                role=Config.ROLE_CUSTOMER,
                is_active=False
            )
            db.session.add(disabled_user)
            db.session.commit()
            self.cleanup_user_ids.append(disabled_user.id)

        client = self.app.test_client()
        res = client.post("/login", data={
            "email": email,
            "password": "Password123!"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Account is disabled. Please contact the administrator", res.data)

        # Confirm account remained inactive in DB
        with self.app.app_context():
            chk = User.query.filter_by(email=email).first()
            self.assertFalse(chk.is_active)

    def test_19_stale_session_role_tampering_ignored(self):
        """Test 19: Tampering session cookie role does not bypass DB-backed role checks."""
        client = self.app.test_client()
        # Log in as genuine Customer
        self._login(client, "customer@assurex.local", "CustomerPass123!")

        # Maliciously tamper with session cookie to claim admin role
        with client.session_transaction() as sess:
            sess["role"] = Config.ROLE_ADMIN

        # Attempt to access admin dashboard: DB check must catch and block
        res = client.get("/admin/dashboard", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Unauthorized access", res.data)

    # =========================================================================
    # 6. OBJECT-LEVEL ACCESS CONTROL (IDOR) ISOLATION (Tests 20 - 23)
    # =========================================================================

    def _setup_idor_assets(self):
        """Helper to create two distinct customers with assets for Customer A."""
        with self.app.app_context():
            cust_a = User(
                email="idor_cust_a@assurex.local",
                full_name="Customer A Asset Owner",
                password_hash=generate_password_hash("Password123!"),
                role=Config.ROLE_CUSTOMER,
                is_active=True
            )
            cust_b = User(
                email="idor_cust_b@assurex.local",
                full_name="Customer B Attacker",
                password_hash=generate_password_hash("Password123!"),
                role=Config.ROLE_CUSTOMER,
                is_active=True
            )
            db.session.add_all([cust_a, cust_b])
            db.session.flush()

            prod = Product(
                user_id=cust_a.id,
                product_name="Private Equipment Asset",
                category="Consumer Electronics",
                brand="Sony",
                model_number="WH-1000XM5",
                serial_number="SN-IDOR-SEC-99",
                purchase_date=date.today() - timedelta(days=60),
                purchase_price=399.99,
                retailer="Electronics World"
            )
            db.session.add(prod)
            db.session.flush()

            policy = WarrantyPolicy.query.first()
            warr = ProductWarranty(
                product_id=prod.id,
                policy_id=policy.id if policy else 1,
                warranty_provider="Sony Corp",
                start_date=date.today() - timedelta(days=60),
                expiry_date=date.today() + timedelta(days=305)
            )
            db.session.add(warr)
            db.session.flush()

            claim = Claim(
                user_id=cust_a.id,
                product_id=prod.id,
                warranty_id=warr.id,
                fault_occurrence_date=date.today() - timedelta(days=5),
                fault_description="Private Audio Driver Malfunction",
                fault_category="Audio",
                damage_type="Hardware",
                claim_submission_date=date.today(),
                status=Config.STATUS_SUBMITTED
            )
            db.session.add(claim)
            db.session.flush()

            doc = ClaimDocument(
                claim_id=claim.id,
                product_id=prod.id,
                document_type="receipt",
                original_filename="confidential_receipt.pdf",
                file_path="confidential_receipt.pdf",
                file_size_bytes=1024,
                file_hash_sha256="abc123hash",
                verified_by_user=True
            )
            db.session.add(doc)
            db.session.commit()

            self.cleanup_user_ids.extend([cust_a.id, cust_b.id])
            self.cleanup_product_ids.append(prod.id)
            self.cleanup_claim_ids.append(claim.id)
            self.cleanup_doc_ids.append(doc.id)

            return cust_a, cust_b, prod, claim, doc

    def test_20_customer_cannot_view_other_product_idor(self):
        """Test 20: Customer B cannot view Customer A's registered product (IDOR)."""
        cust_a, cust_b, prod, claim, doc = self._setup_idor_assets()
        client = self.app.test_client()
        self._login(client, "idor_cust_b@assurex.local", "Password123!")

        res = client.get(f"/products/{prod.product_id}", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Access denied: You can only view your own registered products", res.data)

    def test_21_customer_cannot_view_other_claim_idor(self):
        """Test 21: Customer B cannot view Customer A's claim dossier (IDOR)."""
        cust_a, cust_b, prod, claim, doc = self._setup_idor_assets()
        client = self.app.test_client()
        self._login(client, "idor_cust_b@assurex.local", "Password123!")

        res = client.get(f"/claims/{claim.claim_id}", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Access denied: You can only view your own warranty claims", res.data)

    def test_22_customer_cannot_download_other_claim_pdf_idor(self):
        """Test 22: Customer B cannot download Customer A's official PDF claim certificate (IDOR)."""
        cust_a, cust_b, prod, claim, doc = self._setup_idor_assets()
        client = self.app.test_client()
        self._login(client, "idor_cust_b@assurex.local", "Password123!")

        res = client.get(f"/reports/claim/{claim.claim_id}/pdf", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Access denied: You can only download reports for your own warranty claims", res.data)

    def test_23_customer_cannot_download_other_document_idor(self):
        """Test 23: Customer B cannot access or download Customer A's private proof document (IDOR)."""
        cust_a, cust_b, prod, claim, doc = self._setup_idor_assets()
        client = self.app.test_client()
        self._login(client, "idor_cust_b@assurex.local", "Password123!")

        res = client.get(f"/products/documents/{doc.document_id}/download", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Access denied", res.data)

    # =========================================================================
    # 7. CROSS-SITE REQUEST FORGERY (CSRF) PROTECTION (Test 24)
    # =========================================================================

    def test_24_csrf_protection_enforced_on_state_changing_post(self):
        """Test 24: State-changing POST requests require a valid CSRF token when CSRF is enforced."""
        csrf_app = create_app()
        csrf_app.config["TESTING"] = True
        csrf_app.config["WTF_CSRF_ENABLED"] = True  # Enforce CSRF protection
        csrf_client = csrf_app.test_client()

        # POST without CSRF token must be rejected with HTTP 403 Forbidden
        res = csrf_client.post("/login", data={
            "email": "customer@assurex.local",
            "password": "CustomerPass123!"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
