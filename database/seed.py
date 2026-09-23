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
    AuditLog
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

        db.session.commit()
        print("-> Seeding completed successfully.")

if __name__ == "__main__":
    seed_database()
