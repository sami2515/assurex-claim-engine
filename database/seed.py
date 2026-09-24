import os
import json
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from config.config import Config
from database.db import db, init_db
from src.models.entities import (
    User,
    Product,
    WarrantyPolicy,
    ProductWarranty,
    Claim,
    ClaimDocument,
    RepairHistory,
    Notification,
    ClaimStatusHistory,
    AuditLog,
    ModelEvaluation,
    RuleValidationLog
)

def create_seed_app():
    """Create a minimal Flask application context for seeding."""
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db(app)
    return app


def seed_database():
    """Populate database with baseline administrative, policy, and sample data."""
    app = create_seed_app()

    with app.app_context():
        print("-> Initializing database tables...")
        db.create_all()

        # -------------------------------------------------------------
        # 1. Seed Core Role Users
        # -------------------------------------------------------------
        users_data = [
            {
                "email": "admin@assurex.local",
                "password": "AdminPass123!",
                "full_name": "System Administrator",
                "role": Config.ROLE_ADMIN,
                "phone": "+1-800-555-0100",
                "address": "AssureX HQ, Suite 100, Tech District"
            },
            {
                "email": "reviewer@assurex.local",
                "password": "ReviewerPass123!",
                "full_name": "Sarah Jenkins",
                "role": Config.ROLE_REVIEWER,
                "phone": "+1-800-555-0101",
                "address": "Claims Adjudication Dept, Floor 4"
            },
            {
                "email": "staff@assurex.local",
                "password": "StaffPass123!",
                "full_name": "Marcus Vance",
                "role": Config.ROLE_STAFF,
                "phone": "+1-800-555-0102",
                "address": "Metro Authorized Service Center #12"
            },
            {
                "email": "customer@assurex.local",
                "password": "CustomerPass123!",
                "full_name": "David Miller",
                "role": Config.ROLE_CUSTOMER,
                "phone": "+1-800-555-0103",
                "address": "742 Evergreen Terrace, Springfield"
            }
        ]

        seeded_users = {}
        for u in users_data:
            existing = User.query.filter_by(email=u["email"]).first()
            if not existing:
                user = User(
                    email=u["email"],
                    full_name=u["full_name"],
                    role=u["role"],
                    phone_number=u["phone"],
                    address=u["address"]
                )
                user.set_password(u["password"])
                db.session.add(user)
                db.session.flush()
                seeded_users[u["role"]] = user
                print(f"   [+] Seeded user: {u['email']} ({u['role']})")
            else:
                seeded_users[u["role"]] = existing
                print(f"   [*] User already exists: {u['email']}")

        # -------------------------------------------------------------
        # 2. Seed Baseline Category Warranty Policies
        # -------------------------------------------------------------
        policies_data = [
            {
                "category": "Consumer Electronics",
                "policy_name": "Standard Electronics Protection Policy",
                "duration": 12,
                "grace": 7,
                "reporting": 30,
                "auth_required": True,
                "rules": {
                    "covered_faults": [
                        "Screen flickering", "Motherboard failure", "Battery failure to charge",
                        "Speaker malfunction", "Unresponsive touch panel", "Bluetooth/Wi-Fi failure"
                    ],
                    "exclusions": [
                        "Liquid damage", "Screen shattering from drops", "Third-party unauthorized disassembly",
                        "Cosmetic dents and scratches", "Power surge damage", "Rooted/modified firmware"
                    ],
                    "mandatory_documents": [
                        "Purchase Invoice", "Warranty Card", "Serial Number Photo", "Fault Evidence Photo"
                    ],
                    "hard_fail_rules": [
                        "Claim submitted after warranty expiry and grace period",
                        "Liquid/water ingress detected",
                        "Disassembly by non-authorized technician"
                    ],
                    "warning_rules": [
                        "Claim filed within 3 days of grace period expiration",
                        "Multiple repairs logged within 6 months"
                    ],
                    "manual_review_rules": [
                        "Model prediction disagreement",
                        "Confidence score below threshold",
                        "Serial number OCR confidence mismatch"
                    ]
                }
            },
            {
                "category": "Home Appliances",
                "policy_name": "Major Home Appliance Comprehensive Coverage",
                "duration": 24,
                "grace": 14,
                "reporting": 45,
                "auth_required": True,
                "rules": {
                    "covered_faults": [
                        "Compressor failure", "Motor burnout", "Thermostat failure",
                        "Drum spin malfunction", "Electronic PCB failure", "Water pump leakage"
                    ],
                    "exclusions": [
                        "Commercial utilization of domestic appliance", "Pest infestation damage",
                        "Rust and environmental corrosion", "Improper electrical supply rating",
                        "Third-party modifications"
                    ],
                    "mandatory_documents": [
                        "Original Tax Invoice", "Installation Certificate", "Model Serial Plate Photo"
                    ],
                    "hard_fail_rules": [
                        "Product operated beyond domestic home environment limits",
                        "Corrosion due to hazardous chemical exposure",
                        "Missing purchase date verification"
                    ],
                    "warning_rules": [
                        "High frequency repair history",
                        "Installation certificate unverified"
                    ],
                    "manual_review_rules": [
                        "Previous compressor replacement under dispute",
                        "Duplicate claim serial detection"
                    ]
                }
            },
            {
                "category": "Industrial & Automotive Tools",
                "policy_name": "Heavy Duty Industrial Equipment Warranty",
                "duration": 36,
                "grace": 10,
                "reporting": 30,
                "auth_required": True,
                "rules": {
                    "covered_faults": [
                        "Armature burning", "Hydraulic pressure seal failure", "Gearbox seizure",
                        "Chuck bearing breakdown", "Trigger switch failure"
                    ],
                    "exclusions": [
                        "Abnormal overload beyond specified torque limits", "Normal consumable wear (brushes, chuck teeth)",
                        "Unlubricated operation", "Use of non-spec hydraulic oil"
                    ],
                    "mandatory_documents": [
                        "Commercial Tax Invoice", "Authorized Service Logbook", "Damage Site Photo"
                    ],
                    "hard_fail_rules": [
                        "Operating without oil/lubrication",
                        "Serial number plate altered, removed, or defaced"
                    ],
                    "warning_rules": [
                        "Service interval exceeded recommended hours"
                    ],
                    "manual_review_rules": [
                        "Discrepancy in hours of operation vs claim date"
                    ]
                }
            }
        ]

        seeded_policies = {}
        for pol in policies_data:
            existing_pol = WarrantyPolicy.query.filter_by(category=pol["category"]).first()
            if not existing_pol:
                p_obj = WarrantyPolicy(
                    category=pol["category"],
                    policy_name=pol["policy_name"],
                    coverage_duration_months=pol["duration"],
                    grace_period_days=pol["grace"],
                    claim_reporting_period_days=pol["reporting"],
                    authorized_service_center_required=pol["auth_required"],
                    policy_rules_json=json.dumps(pol["rules"], indent=2)
                )
                db.session.add(p_obj)
                db.session.flush()
                seeded_policies[pol["category"]] = p_obj
                print(f"   [+] Seeded policy: {pol['policy_name']} ({pol['category']})")
            else:
                seeded_policies[pol["category"]] = existing_pol
                print(f"   [*] Policy already exists: {pol['policy_name']}")

        # -------------------------------------------------------------
        # 3. Seed Sample Products & Active Warranties for Customer
        # -------------------------------------------------------------
        customer_user = seeded_users.get(Config.ROLE_CUSTOMER)
        if customer_user:
            today = date.today()
            sample_products = [
                {
                    "name": "ApexBook Pro 16 Laptop",
                    "category": "Consumer Electronics",
                    "brand": "ApexTech",
                    "model": "ABP-16-M3",
                    "serial": "SN-APX-8829104",
                    "purchase_date": today - timedelta(days=120),
                    "price": 1899.99,
                    "retailer": "TechMegaStore Downtown",
                    "invoice": "INV-2026-08122",
                    "duration_months": 12,
                    "provider": "ApexTech Official Care"
                },
                {
                    "name": "FrostGuard Smart Refrigerator 450L",
                    "category": "Home Appliances",
                    "brand": "FrostGuard",
                    "model": "FG-450-INV",
                    "serial": "SN-FG-5519283",
                    "purchase_date": today - timedelta(days=340),
                    "price": 1249.00,
                    "retailer": "HomeComfort Appliances",
                    "invoice": "INV-2025-99211",
                    "duration_months": 24,
                    "provider": "FrostGuard Home Warranty"
                },
                {
                    "name": "TitanDrill Industrial 20V Cordless",
                    "category": "Industrial & Automotive Tools",
                    "brand": "TitanPower",
                    "model": "TD-20V-HD",
                    "serial": "SN-TP-1102938",
                    "purchase_date": today - timedelta(days=200),
                    "price": 389.50,
                    "retailer": "Industrial Supply Direct",
                    "invoice": "INV-2025-44019",
                    "duration_months": 36,
                    "provider": "Titan Heavy Duty Warranty"
                }
            ]

            for sp in sample_products:
                existing_prd = Product.query.filter_by(serial_number=sp["serial"]).first()
                if not existing_prd:
                    prd = Product(
                        user_id=customer_user.id,
                        product_name=sp["name"],
                        category=sp["category"],
                        brand=sp["brand"],
                        model_number=sp["model"],
                        serial_number=sp["serial"],
                        purchase_date=sp["purchase_date"],
                        purchase_price=sp["price"],
                        retailer=sp["retailer"],
                        invoice_number=sp["invoice"]
                    )
                    db.session.add(prd)
                    db.session.flush()

                    # Attach warranty
                    pol = seeded_policies.get(sp["category"])
                    w_start = sp["purchase_date"]
                    w_expiry = w_start + timedelta(days=sp["duration_months"] * 30)

                    warr = ProductWarranty(
                        product_id=prd.id,
                        policy_id=pol.id if pol else 1,
                        warranty_provider=sp["provider"],
                        start_date=w_start,
                        expiry_date=w_expiry,
                        service_center_name="Metro Authorized Care Center"
                    )
                    db.session.add(warr)

                    # Add sample repair record for the laptop
                    if "Laptop" in sp["name"]:
                        rep = RepairHistory(
                            product_id=prd.id,
                            repair_date=today - timedelta(days=60),
                            repair_center="Metro Authorized Care Center",
                            replaced_parts="Cooling Fan Assembly",
                            outcome="Repaired",
                            repair_cost=45.00,
                            is_authorized_center=True,
                            notes="Standard authorized thermal fan cleaning and replacement under warranty."
                        )
                        db.session.add(rep)

                    print(f"   [+] Seeded product & warranty: {sp['name']} ({sp['serial']})")

        # -------------------------------------------------------------
        # 4. Seed Initial Notification
        # -------------------------------------------------------------
        if customer_user:
            notif = Notification(
                user_id=customer_user.id,
                notification_type=Config.NOTIF_TYPE_WARRANTY_EXPIRY,
                title="Welcome to AssureX Claim Engine",
                message="Your registered products and warranty records are active and protected."
            )
            db.session.add(notif)

        # -------------------------------------------------------------
        # 5. Seed System Audit Entry
        # -------------------------------------------------------------
        admin_user = seeded_users.get(Config.ROLE_ADMIN)
        audit = AuditLog(
            user_id=admin_user.id if admin_user else None,
            user_role=Config.ROLE_ADMIN,
            action="SYSTEM_INIT_SEED",
            entity_type="DATABASE",
            entity_id="ALL_TABLES",
            ip_address="127.0.0.1",
            details_json=json.dumps({"status": "SUCCESS", "message": "Baseline system seeded successfully."})
        )
        db.session.add(audit)

        # -------------------------------------------------------------
        # 6. Seed Baseline Demonstration Claims for Workbenches
        # -------------------------------------------------------------
        existing_claim_count = Claim.query.count()
        if existing_claim_count == 0 and customer_user:
            demo_claims_data = [
                {
                    "claim_id": "CLM-DEMO-001",
                    "product_name": "ApexBook Studio 14 Display",
                    "serial_number": "SN-DEMO-APX-001",
                    "brand": "ApexTech",
                    "model": "ABS-14-DISP",
                    "price": 899.00,
                    "category": "Consumer Electronics",
                    "fault_desc": "Intermittent screen display flickering and GPU thermal throttling under medium load.",
                    "fault_cat": "Screen flickering",
                    "damage_type": "Internal Component Failure",
                    "status": Config.STATUS_MANUAL_REVIEW,
                    "risk": "Medium",
                    "final_decision": "Manual Review Required",
                    "reason": "Borderline dual-model confidence score (0.71) requires expert human verification.",
                    "py_conf": (0.71, 0.19, 0.10),
                    "gtm_conf": (0.65, 0.22, 0.13),
                    "match": True,
                    "diff": 0.06,
                    "status_text": "Consistent",
                    "passed_rules": ["Warranty active at occurrence date", "Category fault eligible", "Authorized retailer purchase verified"],
                    "failed_rules": [],
                    "warnings": ["Notice: Prior authorized fan service recorded on unit"],
                    "rule_status": "PASSED"
                },
                {
                    "claim_id": "CLM-DEMO-002",
                    "product_name": "FrostGuard Beverage Cooler 90L",
                    "serial_number": "SN-DEMO-FG-002",
                    "brand": "FrostGuard",
                    "model": "FG-90-COOL",
                    "price": 549.00,
                    "category": "Home Appliances",
                    "fault_desc": "Refrigerator compressor failed to maintain cooling temperature.",
                    "fault_cat": "Compressor failure",
                    "damage_type": "Mechanical Breakdown",
                    "status": Config.STATUS_APPROVED,
                    "risk": "Low",
                    "final_decision": "Likely Valid",
                    "reason": "All automated policy rules passed; high dual-model confidence consensus (0.94).",
                    "py_conf": (0.94, 0.04, 0.02),
                    "gtm_conf": (0.92, 0.05, 0.03),
                    "match": True,
                    "diff": 0.02,
                    "status_text": "Consistent",
                    "passed_rules": ["Domestic home use verified", "Compressor fault covered", "Within 24 month duration"],
                    "failed_rules": [],
                    "warnings": [],
                    "rule_status": "PASSED"
                },
                {
                    "claim_id": "CLM-DEMO-003",
                    "product_name": "TitanImpact Pneumatic Wrench 24V",
                    "serial_number": "SN-DEMO-TP-003",
                    "brand": "TitanPower",
                    "model": "TI-24V-WR",
                    "price": 420.00,
                    "category": "Industrial & Automotive Tools",
                    "fault_desc": "Armature burned out following continuous commercial hydraulic torque overload.",
                    "fault_cat": "Armature burning",
                    "damage_type": "Overload Misuse",
                    "status": Config.STATUS_REJECTED,
                    "risk": "High",
                    "final_decision": "Likely Invalid",
                    "reason": "Hard policy exclusion violated: abnormal commercial overload beyond torque threshold.",
                    "py_conf": (0.12, 0.82, 0.06),
                    "gtm_conf": (0.15, 0.79, 0.06),
                    "match": True,
                    "diff": 0.03,
                    "status_text": "Consistent",
                    "passed_rules": ["Serial number authentic"],
                    "failed_rules": ["Hard Fail: Abnormal continuous torque overloading detected", "Hard Fail: Commercial duty cycle on standard tool"],
                    "warnings": [],
                    "rule_status": "FAILED"
                }
            ]

            for dcd in demo_claims_data:
                # Find or create dedicated demo product
                p_item = Product.query.filter_by(serial_number=dcd["serial_number"]).first()
                if not p_item:
                    p_item = Product(
                        user_id=customer_user.id,
                        product_name=dcd["product_name"],
                        category=dcd["category"],
                        brand=dcd["brand"],
                        model_number=dcd["model"],
                        serial_number=dcd["serial_number"],
                        purchase_date=date.today() - timedelta(days=180),
                        purchase_price=dcd["price"],
                        retailer="Authorized Direct Store",
                        invoice_number=f"INV-{dcd['serial_number']}"
                    )
                    db.session.add(p_item)
                    db.session.flush()

                    pol = seeded_policies.get(dcd["category"])
                    warr = ProductWarranty(
                        product_id=p_item.id,
                        policy_id=pol.id if pol else 1,
                        warranty_provider="AssureX Shield Comprehensive",
                        start_date=date.today() - timedelta(days=180),
                        expiry_date=date.today() + timedelta(days=185),
                        service_center_name="Metro Authorized Care Center"
                    )
                    db.session.add(warr)
                    db.session.flush()
                else:
                    warr = p_item.warranty

                demo_claim = Claim(
                    claim_id=dcd["claim_id"],
                    user_id=customer_user.id,
                    product_id=p_item.id,
                    warranty_id=warr.id,
                    fault_occurrence_date=date.today() - timedelta(days=7),
                    fault_description=dcd["fault_desc"],
                    fault_category=dcd["fault_cat"],
                    damage_type=dcd["damage_type"],
                    claim_submission_date=date.today() - timedelta(days=2),
                    status=dcd["status"],
                    risk_level=dcd["risk"],
                    final_decision=dcd["final_decision"],
                    decision_reason=dcd["reason"]
                )
                db.session.add(demo_claim)
                db.session.flush()

                # Status History
                hist_sub = ClaimStatusHistory(
                    claim_id=demo_claim.id,
                    previous_status=Config.STATUS_DRAFT,
                    new_status=Config.STATUS_SUBMITTED,
                    changed_by_user_id=customer_user.id,
                    reason_comment="Claim intake wizard completed by customer."
                )
                hist_eval = ClaimStatusHistory(
                    claim_id=demo_claim.id,
                    previous_status=Config.STATUS_SUBMITTED,
                    new_status=dcd["status"],
                    changed_by_user_id=None,
                    reason_comment=f"Automated evaluation: {dcd['reason']}"
                )
                db.session.add_all([hist_sub, hist_eval])

                # Model Evaluation
                me = ModelEvaluation(
                    claim_id=demo_claim.id,
                    python_model_version=Config.PYTHON_MODEL_VERSION,
                    python_predicted_class="Valid Claim" if dcd["py_conf"][0] > 0.5 else "Invalid Claim",
                    python_conf_valid=dcd["py_conf"][0],
                    python_conf_invalid=dcd["py_conf"][1],
                    python_conf_manual=dcd["py_conf"][2],
                    gtm_model_version=Config.GTM_MODEL_VERSION,
                    gtm_predicted_class="Valid Claim" if dcd["gtm_conf"][0] > 0.5 else "Invalid Claim",
                    gtm_conf_valid=dcd["gtm_conf"][0],
                    gtm_conf_invalid=dcd["gtm_conf"][1],
                    gtm_conf_manual=dcd["gtm_conf"][2],
                    is_class_match=dcd["match"],
                    top_confidence_difference=dcd["diff"],
                    model_consistency_status=dcd["status_text"]
                )
                db.session.add(me)

                # Rule Validation Log
                rv = RuleValidationLog(
                    claim_id=demo_claim.id,
                    policy_id=p_item.warranty.policy.policy_id if p_item.warranty and p_item.warranty.policy else "POL-DEFAULT",
                    rules_passed_json=json.dumps(dcd["passed_rules"]),
                    rules_failed_json=json.dumps(dcd["failed_rules"]),
                    warnings_json=json.dumps(dcd["warnings"]),
                    contradictions_json=json.dumps([]),
                    duplicate_flags_json=json.dumps([]),
                    overall_rule_status=dcd["rule_status"]
                )
                db.session.add(rv)
                print(f"   [+] Seeded demo claim: {demo_claim.claim_id} ({demo_claim.status})")

        db.session.commit()
        print("-> Seeding completed successfully.")

if __name__ == "__main__":
    seed_database()
