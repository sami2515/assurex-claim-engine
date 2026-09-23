import os
import json
import random
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

# Set random seed for perfect reproducibility across all 1500 records
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
SPLITS_DIR = DATA_DIR / "splits"

# Product domain definitions across 3 SRS categories
CATEGORIES_CATALOG = {
    "Consumer Electronics": {
        "brands": ["ApexTech", "NovaSound", "VividDisplay", "QuantumCompute", "PixelCraft"],
        "models": {
            "Laptop": ["ApexBook Pro 16", "ApexBook Air 14", "QuantumBook Ultra 15"],
            "Smartphone": ["NovaPhone 12 Pro", "NovaPhone 12 Lite", "QuantumPixel 8"],
            "Tablet": ["VividTab 11 Max", "NovaPad Pro 10", "PixelSlate 12"],
            "Smartwatch": ["NovaWatch Ultra", "ApexFit Chrono 3"]
        },
        "prices": (199.0, 2499.0),
        "warranty_months": [12, 24],
        "faults": [
            "Screen flickering", "Motherboard failure", "Battery failure to charge",
            "Speaker malfunction", "Unresponsive touch panel", "Bluetooth/Wi-Fi failure"
        ],
        "exclusions": [
            "Liquid ingress damage", "Screen shattering from drops", "Third-party unauthorized disassembly",
            "Cosmetic casing cracks", "Power surge overvoltage", "Rooted firmware malfunction"
        ]
    },
    "Home Appliances": {
        "brands": ["FrostGuard", "AeroBreeze", "ThermaPure", "CleanCycle", "KitchenPro"],
        "models": {
            "Refrigerator": ["FrostGuard 450L Smart", "FrostGuard Side-by-Side 600L", "ThermaCold 320L"],
            "Washing Machine": ["CleanCycle FrontLoad 8kg", "CleanCycle QuickWash 7kg", "ThermaWash Eco"],
            "Air Conditioner": ["AeroBreeze Inverter 1.5T", "AeroBreeze DualCool 2.0T", "ThermaAir Silent"],
            "Microwave": ["KitchenPro Convection 30L", "KitchenPro Grill 25L"]
        },
        "prices": (299.0, 1899.0),
        "warranty_months": [24, 36],
        "faults": [
            "Compressor failure", "Motor burnout", "Thermostat failure",
            "Drum spin malfunction", "Electronic PCB failure", "Water pump leakage"
        ],
        "exclusions": [
            "Commercial heavy utilization", "Pest infestation inside chassis",
            "Rust and environmental corrosion", "Improper electrical supply rating",
            "Third-party modifications"
        ]
    },
    "Industrial & Automotive Tools": {
        "brands": ["TitanPower", "TorqueMaster", "IronForge", "ApexIndustrial", "MegaWrench"],
        "models": {
            "Cordless Drill": ["TitanDrill 20V HD", "TorqueMaster Brushless 18V", "IronForge Impact 24V"],
            "Air Compressor": ["TitanAir 50L Heavy Duty", "IronForge TwinPiston 100L"],
            "Pressure Washer": ["MegaWash Pro 2500PSI", "TitanPressure 3000PSI Commercial"],
            "Angle Grinder": ["IronGrind 9-inch Industrial", "TorqueGrinder 1500W"]
        },
        "prices": (149.0, 1299.0),
        "warranty_months": [24, 36],
        "faults": [
            "Armature burning", "Hydraulic pressure seal failure", "Gearbox seizure",
            "Chuck bearing breakdown", "Trigger switch failure"
        ],
        "exclusions": [
            "Abnormal overload beyond specified torque limits", "Normal consumable wear (brushes, chuck teeth)",
            "Unlubricated operation", "Use of non-spec hydraulic oil"
        ]
    }
}

RETAILERS = [
    "TechMegaStore Downtown", "Electronics Hub Metro", "National Appliance Depot",
    "Industrial Supply Direct", "Prime Retail Express", "Official Brand Store"
]

SERVICE_CENTERS = [
    "Metro Authorized Care Center", "Official Central Service Depot",
    "Apex Authorized Technical Hub", "National Warranty Service Center"
]

UNAUTHORIZED_SHOPS = [
    "Local QuickFix Electronics", "Downtown Third-Party Repair Stall",
    "Joe's Unofficial Fix Shop", "Corner Hardware & Mobile Repairs"
]


def generate_single_claim(claim_idx: int, target_class: str) -> dict:
    """Generate a single realistic claim record tailored to the target class."""
    claim_id = f"CLM-{claim_idx:05d}"
    category_name = random.choice(list(CATEGORIES_CATALOG.keys()))
    cat_info = CATEGORIES_CATALOG[category_name]

    product_type = random.choice(list(cat_info["models"].keys()))
    product_model = random.choice(cat_info["models"][product_type])
    brand = random.choice(cat_info["brands"])
    serial_number = f"SN-{brand[:3].upper()}-{random.randint(1000000, 9999999)}"
    product_id = f"PRD-{claim_idx:05d}"

    price_range = cat_info["prices"]
    purchase_price = round(random.uniform(price_range[0], price_range[1]), 2)
    retailer = random.choice(RETAILERS)
    invoice_number = f"INV-202{random.randint(4, 6)}-{random.randint(10000, 99999)}"

    # Warranty duration
    warranty_months = random.choice(cat_info["warranty_months"])
    is_extended = random.choice([True, False]) if target_class != "Invalid Claim" else False
    effective_months = warranty_months + (12 if is_extended else 0)

    # Reference today date for simulation
    simulated_today = date(2026, 9, 20)

    # -------------------------------------------------------------
    # Class-specific feature assignment
    # -------------------------------------------------------------
    if target_class == "Valid Claim":
        # Purchase date between 30 and (effective_months * 30 - 30) days ago
        max_age = max(40, effective_months * 30 - 60)
        product_age_days = random.randint(30, max_age)
        purchase_date = simulated_today - timedelta(days=product_age_days)
        warranty_start_date = purchase_date
        warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
        remaining_warranty_days = (warranty_expiry_date - simulated_today).days

        # Fault occurred recently within active warranty
        fault_occurrence_days_ago = random.randint(2, min(25, product_age_days))
        fault_occurrence_date = simulated_today - timedelta(days=fault_occurrence_days_ago)
        fault_category = random.choice(cat_info["faults"])
        fault_description = f"Reported genuine hardware failure: {fault_category} under regular domestic usage."
        damage_type = "Hardware Defect"

        # Evidence & documents: Complete
        has_receipt = True
        has_warranty_card = True
        has_damage_photo = True
        has_serial_photo = True
        has_repair_report = True if random.random() < 0.3 else False
        serial_number_match = True

        previous_repairs_count = random.choice([0, 0, 1])
        unauthorized_repair_flag = False
        claim_date_conflict_flag = False

    elif target_class == "Invalid Claim":
        # Invalid reasons: Expired warranty, liquid/drop damage, unauthorized repair, or serial mismatch
        invalid_mode = random.choice(["expired", "excluded_damage", "unauthorized_repair", "serial_mismatch"])

        if invalid_mode == "expired":
            # Expired warranty: age is beyond warranty duration + grace period
            product_age_days = (effective_months * 30) + random.randint(20, 180)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = 0
            fault_occurrence_date = simulated_today - timedelta(days=random.randint(5, 20))
            fault_category = random.choice(cat_info["faults"])
            fault_description = f"Failure: {fault_category}. Note: product warranty expired {abs((warranty_expiry_date - simulated_today).days)} days ago."
            damage_type = "Hardware Wear"
            has_receipt = True
            has_warranty_card = True
            has_damage_photo = True
            has_serial_photo = True
            has_repair_report = False
            serial_number_match = True
            previous_repairs_count = random.choice([0, 1, 2])
            unauthorized_repair_flag = False
            claim_date_conflict_flag = False

        elif invalid_mode == "excluded_damage":
            # Excluded damage: liquid or drop
            product_age_days = random.randint(40, effective_months * 30 - 30)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = (warranty_expiry_date - simulated_today).days
            fault_occurrence_date = simulated_today - timedelta(days=random.randint(2, 20))
            fault_category = random.choice(cat_info["exclusions"])
            fault_description = f"Physical inspection reveals clear {fault_category} violating warranty coverage terms."
            damage_type = "Customer Induced Damage"
            has_receipt = True
            has_warranty_card = True
            has_damage_photo = True
            has_serial_photo = True
            has_repair_report = False
            serial_number_match = True
            previous_repairs_count = 0
            unauthorized_repair_flag = False
            claim_date_conflict_flag = False

        elif invalid_mode == "unauthorized_repair":
            product_age_days = random.randint(60, effective_months * 30 - 30)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = (warranty_expiry_date - simulated_today).days
            fault_occurrence_date = simulated_today - timedelta(days=random.randint(3, 15))
            fault_category = random.choice(cat_info["faults"])
            fault_description = f"Unit previously opened and tampered with at non-authorized workshop ({random.choice(UNAUTHORIZED_SHOPS)})."
            damage_type = "Tampering"
            has_receipt = True
            has_warranty_card = True
            has_damage_photo = True
            has_serial_photo = True
            has_repair_report = True
            serial_number_match = True
            previous_repairs_count = random.randint(1, 3)
            unauthorized_repair_flag = True
            claim_date_conflict_flag = False

        else:  # serial mismatch
            product_age_days = random.randint(30, effective_months * 30 - 30)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = (warranty_expiry_date - simulated_today).days
            fault_occurrence_date = simulated_today - timedelta(days=random.randint(2, 10))
            fault_category = random.choice(cat_info["faults"])
            fault_description = f"Device submitted does not match registered unit. Serial on invoice differs from backplate."
            damage_type = "Serial Mismatch"
            has_receipt = True
            has_warranty_card = False
            has_damage_photo = True
            has_serial_photo = True
            has_repair_report = False
            serial_number_match = False
            previous_repairs_count = 0
            unauthorized_repair_flag = False
            claim_date_conflict_flag = False

    else:  # Manual Review
        # Review reasons: Borderline date (within 3 days of expiry), missing mandatory receipt/photo, conflicting dates, complex history
        review_mode = random.choice(["borderline_date", "missing_document", "conflicting_dates", "unclear_diagnostics"])

        if review_mode == "borderline_date":
            # Expiry was 2 days ago, within grace period
            product_age_days = (effective_months * 30) + random.randint(1, 5)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = (warranty_expiry_date - simulated_today).days  # slightly negative or 0
            fault_occurrence_date = simulated_today - timedelta(days=random.randint(1, 4))
            fault_category = random.choice(cat_info["faults"])
            fault_description = f"Fault occurred near warranty expiration boundary. Customer requests grace period evaluation."
            damage_type = "Borderline Lifecycle"
            has_receipt = True
            has_warranty_card = True
            has_damage_photo = True
            has_serial_photo = True
            has_repair_report = False
            serial_number_match = True
            previous_repairs_count = 1
            unauthorized_repair_flag = False
            claim_date_conflict_flag = False

        elif review_mode == "missing_document":
            product_age_days = random.randint(30, effective_months * 30 - 60)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = (warranty_expiry_date - simulated_today).days
            fault_occurrence_date = simulated_today - timedelta(days=random.randint(2, 10))
            fault_category = random.choice(cat_info["faults"])
            fault_description = f"Claim submitted without primary proof of purchase receipt. Customer submitted affidavit instead."
            damage_type = "Incomplete Documentation"
            has_receipt = False  # missing!
            has_warranty_card = True
            has_damage_photo = True
            has_serial_photo = False  # missing!
            has_repair_report = False
            serial_number_match = True
            previous_repairs_count = 0
            unauthorized_repair_flag = False
            claim_date_conflict_flag = False

        elif review_mode == "conflicting_dates":
            product_age_days = random.randint(40, effective_months * 30 - 30)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = (warranty_expiry_date - simulated_today).days
            # Contradiction: Fault date claims to be before purchase date or in future
            fault_occurrence_date = purchase_date - timedelta(days=random.randint(5, 20))
            fault_category = random.choice(cat_info["faults"])
            fault_description = f"Discrepancy detected: Claimed fault occurrence date predates registered purchase date."
            damage_type = "Date Inconsistency"
            has_receipt = True
            has_warranty_card = True
            has_damage_photo = True
            has_serial_photo = True
            has_repair_report = False
            serial_number_match = True
            previous_repairs_count = 0
            unauthorized_repair_flag = False
            claim_date_conflict_flag = True

        else:  # unclear diagnostics
            product_age_days = random.randint(40, effective_months * 30 - 30)
            purchase_date = simulated_today - timedelta(days=product_age_days)
            warranty_start_date = purchase_date
            warranty_expiry_date = warranty_start_date + timedelta(days=effective_months * 30)
            remaining_warranty_days = (warranty_expiry_date - simulated_today).days
            fault_occurrence_date = simulated_today - timedelta(days=random.randint(2, 15))
            fault_category = random.choice(cat_info["faults"])
            fault_description = f"Diagnostic report inconclusive regarding whether component failure was thermal surge or defect."
            damage_type = "Ambiguous Diagnostic"
            has_receipt = True
            has_warranty_card = True
            has_damage_photo = True
            has_serial_photo = True
            has_repair_report = True
            serial_number_match = True
            previous_repairs_count = random.randint(1, 2)
            unauthorized_repair_flag = False
            claim_date_conflict_flag = False

    # Calculate missing documents count
    docs_present = [has_receipt, has_warranty_card, has_damage_photo, has_serial_photo]
    missing_document_count = sum(1 for d in docs_present if not d)

    return {
        "claim_id": claim_id,
        "product_id": product_id,
        "product_category": category_name,
        "product_brand": brand,
        "product_model": product_model,
        "product_serial": serial_number,
        "purchase_date": purchase_date.strftime("%Y-%m-%d"),
        "purchase_price": purchase_price,
        "retailer": retailer,
        "invoice_number": invoice_number,
        "warranty_start_date": warranty_start_date.strftime("%Y-%m-%d"),
        "warranty_expiry_date": warranty_expiry_date.strftime("%Y-%m-%d"),
        "warranty_duration_months": effective_months,
        "product_age_days": max(0, product_age_days),
        "remaining_warranty_days": max(0, remaining_warranty_days),
        "is_extended_warranty": 1 if is_extended else 0,
        "fault_occurrence_date": fault_occurrence_date.strftime("%Y-%m-%d"),
        "fault_category": fault_category,
        "fault_description": fault_description,
        "damage_type": damage_type,
        "has_receipt": 1 if has_receipt else 0,
        "has_warranty_card": 1 if has_warranty_card else 0,
        "has_damage_photo": 1 if has_damage_photo else 0,
        "has_serial_photo": 1 if has_serial_photo else 0,
        "has_repair_report": 1 if has_repair_report else 0,
        "missing_document_count": missing_document_count,
        "serial_number_match": 1 if serial_number_match else 0,
        "previous_repairs_count": previous_repairs_count,
        "unauthorized_repair_flag": 1 if unauthorized_repair_flag else 0,
        "claim_date_conflict_flag": 1 if claim_date_conflict_flag else 0,
        "claim_class": target_class
    }


def generate_full_dataset():
    """Generate 1500 balanced records and perform stratified 70/15/15 train/val/test split."""
    print("-> Generating 1,500 unique balanced warranty claim records...")
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    classes = ["Valid Claim", "Invalid Claim", "Manual Review"]
    records_per_class = 500

    claim_idx = 1
    for cls in classes:
        for _ in range(records_per_class):
            record = generate_single_claim(claim_idx, cls)
            records.append(record)
            claim_idx += 1

    # Shuffle deterministically
    random.shuffle(records)
    df = pd.DataFrame(records)

    # Save full raw dataset
    raw_path = RAW_DATA_DIR / "common_warranty_claims_1500.csv"
    df.to_csv(raw_path, index=False)
    print(f"   [+] Full raw dataset written to: {raw_path} ({len(df)} rows)")

    # -------------------------------------------------------------
    # Stratified Split (70% Train, 15% Val, 15% Test)
    # Train: 1,050 (350 per class)
    # Val: 225 (75 per class)
    # Test: 225 (75 per class)
    # -------------------------------------------------------------
    train_records = []
    val_records = []
    test_records = []

    for cls in classes:
        cls_df = df[df["claim_class"] == cls]
        # Stratified sampling
        train_cls = cls_df.iloc[:350]
        val_cls = cls_df.iloc[350:425]
        test_cls = cls_df.iloc[425:500]

        train_records.append(train_cls)
        val_records.append(val_cls)
        test_records.append(test_cls)

    train_df = pd.concat(train_records).sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    val_df = pd.concat(val_records).sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    test_df = pd.concat(test_records).sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)

    train_path = SPLITS_DIR / "train.csv"
    val_path = SPLITS_DIR / "val.csv"
    test_path = SPLITS_DIR / "test.csv"

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    print(f"   [+] Stratified Train split: {train_path} ({len(train_df)} rows)")
    print(f"   [+] Stratified Val split:   {val_path} ({len(val_df)} rows)")
    print(f"   [+] Stratified Test split:  {test_path} ({len(test_df)} rows)")

    # Dataset statistics metadata
    stats = {
        "total_records": len(df),
        "classes": {cls: int((df["claim_class"] == cls).sum()) for cls in classes},
        "categories": {cat: int((df["product_category"] == cat).sum()) for cat in df["product_category"].unique()},
        "splits": {
            "train": {"total": len(train_df), "by_class": {cls: int((train_df["claim_class"] == cls).sum()) for cls in classes}},
            "validation": {"total": len(val_df), "by_class": {cls: int((val_df["claim_class"] == cls).sum()) for cls in classes}},
            "test": {"total": len(test_df), "by_class": {cls: int((test_df["claim_class"] == cls).sum()) for cls in classes}}
        },
        "created_at": datetime.now().isoformat()
    }

    with open(DATA_DIR / "dataset_statistics.json", "w") as f:
        json.dump(stats, f, indent=2)

    # Data dictionary
    data_dict = {
        "claim_id": "Unique Claim Identifier (CLM-XXXXX)",
        "product_id": "Unique Registered Product Identifier (PRD-XXXXX)",
        "product_category": "Product Category (Consumer Electronics, Home Appliances, Industrial & Automotive Tools)",
        "product_brand": "Manufacturer Brand Name",
        "product_model": "Device Model Specification",
        "product_serial": "Manufacturer Hardware Serial Number",
        "purchase_date": "Original Retail Purchase Date (YYYY-MM-DD)",
        "purchase_price": "Retail Purchase Price in USD",
        "retailer": "Retail merchant or distributor channel",
        "invoice_number": "Official tax invoice or receipt serial",
        "warranty_start_date": "Warranty coverage effective commencement date",
        "warranty_expiry_date": "Warranty standard coverage termination date",
        "warranty_duration_months": "Total active warranty protection span in months",
        "product_age_days": "Elapsed lifespan in days from purchase to claim",
        "remaining_warranty_days": "Number of days remaining in coverage period",
        "is_extended_warranty": "Binary flag indicating active extended protection tier (1=Yes, 0=No)",
        "fault_occurrence_date": "Reported date when physical fault manifested",
        "fault_category": "Standardized classification of defect or component failure",
        "fault_description": "Descriptive narrative of customer reported symptom",
        "damage_type": "Primary root cause category (Hardware Defect, Wear, Incomplete, Tampering, etc.)",
        "has_receipt": "Binary indicator of uploaded purchase receipt (1=Yes, 0=No)",
        "has_warranty_card": "Binary indicator of uploaded warranty certificate (1=Yes, 0=No)",
        "has_damage_photo": "Binary indicator of uploaded damage photo (1=Yes, 0=No)",
        "has_serial_photo": "Binary indicator of uploaded serial plate photograph (1=Yes, 0=No)",
        "has_repair_report": "Binary indicator of service center diagnostic report (1=Yes, 0=No)",
        "missing_document_count": "Total count of missing mandatory submission documents",
        "serial_number_match": "Binary check comparing invoice, claim and hardware serial (1=Match, 0=Mismatch)",
        "previous_repairs_count": "Historical count of previous service operations logged for product",
        "unauthorized_repair_flag": "Binary indicator of previous service by unauthorized third-party (1=Yes, 0=No)",
        "claim_date_conflict_flag": "Chronological conflict indicator (1=Contradiction, 0=Consistent)",
        "claim_class": "Target 3-Class Ground Truth Label (Valid Claim, Invalid Claim, Manual Review)"
    }

    with open(DATA_DIR / "data_dictionary.json", "w") as f:
        json.dump(data_dict, f, indent=2)

    print("   [+] dataset_statistics.json and data_dictionary.json generated successfully.")
    return df, train_df, val_df, test_df

if __name__ == "__main__":
    generate_full_dataset()
