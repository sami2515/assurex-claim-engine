import os
from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SPLITS_DIR = DATA_DIR / "splits"
CARDS_DIR = DATA_DIR / "summary_cards"


def get_default_font(size: int = 14):
    """Safely obtain a standard TrueType or bitmap font."""
    try:
        # Standard Windows fonts
        for font_name in ["segoeui.ttf", "arial.ttf", "calibri.ttf", "tahoma.ttf"]:
            font_path = Path("C:/Windows/Fonts") / font_name
            if font_path.exists():
                return ImageFont.truetype(str(font_path), size)
    except Exception:
        pass
    return ImageFont.load_default()


def render_claim_summary_card(record: dict, variation: int = 1, width: int = 640, height: int = 420) -> Image.Image:
    """
    Renders a standardized visual Claim Summary Card strictly using claim information.
    
    IMPORTANT SRS COMPLIANCE (Page 7 & 14):
    The Claim Summary Card contains ONLY claim information (product age, warranty period,
    fault category, repair history, receipt availability, serial-number status, missing documents).
    It does NOT contain any Python prediction, confidence score, or final claim result.
    """
    # Variation color palettes and styling
    if variation == 1:
        # Style 1: Modern Slate Theme
        bg_color = (24, 32, 47)         # Deep slate
        card_bg = (33, 44, 63)          # Dark card container
        header_bg = (15, 23, 42)        # Very dark header
        text_primary = (248, 250, 252)  # White
        text_secondary = (148, 163, 184)# Muted cyan/gray
        accent_color = (56, 189, 248)   # Electric cyan
        box_border = (51, 65, 85)       # Border slate
        date_format = "iso"             # YYYY-MM-DD
    else:
        # Style 2: Classic Enterprise Theme
        bg_color = (241, 245, 249)      # Slate light
        card_bg = (255, 255, 255)       # Pure white container
        header_bg = (30, 41, 59)        # Navy header
        text_primary = (15, 23, 42)     # Navy dark
        text_secondary = (71, 85, 105)  # Muted slate
        accent_color = (37, 99, 235)    # Royal blue
        box_border = (203, 213, 225)    # Light gray border
        date_format = "standard"        # DD/MM/YYYY

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    title_font = get_default_font(18)
    label_font = get_default_font(12)
    val_font = get_default_font(13)
    header_val_font = get_default_font(14)

    # Outer container with border
    margin = 12
    draw.rectangle(
        [(margin, margin), (width - margin, height - margin)],
        fill=card_bg,
        outline=box_border,
        width=2
    )

    # Header banner
    header_h = 52
    draw.rectangle(
        [(margin, margin), (width - margin, margin + header_h)],
        fill=header_bg
    )

    # Header texts
    draw.text((margin + 16, margin + 10), "ASSUREX CLAIM ENGINE", fill=accent_color, font=title_font)
    draw.text((margin + 16, margin + 32), "STANDARDIZED CLAIM SUMMARY CARD", fill=(203, 213, 225), font=label_font)

    claim_id_str = f"CLAIM ID: {record.get('claim_id', 'UNKNOWN')}"
    draw.text((width - margin - 220, margin + 18), claim_id_str, fill=(255, 255, 255), font=header_val_font)

    # Helper function to format date
    def fmt_d(d_str):
        if not d_str:
            return "N/A"
        if date_format == "standard":
            try:
                parts = d_str.split("-")
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
            except Exception:
                return d_str
        return d_str

    # 4 Structured Data Quadrants
    quad_top = margin + header_h + 10
    quad_w = (width - 2 * margin - 30) // 2
    quad_h = 135

    # ---------------------------------------------------------
    # Quadrant 1: Product & Warranty Specifications (Top-Left)
    # ---------------------------------------------------------
    q1_x0, q1_y0 = margin + 10, quad_top
    draw.rectangle([(q1_x0, q1_y0), (q1_x0 + quad_w, q1_y0 + quad_h)], outline=box_border, width=1)
    draw.text((q1_x0 + 8, q1_y0 + 6), "1. PRODUCT & WARRANTY", fill=accent_color, font=label_font)

    prod_str = f"{record.get('product_category', '')} - {record.get('product_model', '')}"[:34]
    draw.text((q1_x0 + 8, q1_y0 + 26), f"Device: {prod_str}", fill=text_primary, font=val_font)
    draw.text((q1_x0 + 8, q1_y0 + 46), f"Serial: {record.get('product_serial', 'N/A')}", fill=text_secondary, font=val_font)
    draw.text((q1_x0 + 8, q1_y0 + 66), f"Purchased: {fmt_d(record.get('purchase_date', ''))} (${record.get('purchase_price', 0.0):.2f})", fill=text_secondary, font=val_font)
    draw.text((q1_x0 + 8, q1_y0 + 86), f"Product Age: {record.get('product_age_days', 0)} Days", fill=text_primary, font=val_font)
    draw.text((q1_x0 + 8, q1_y0 + 106), f"Coverage End: {fmt_d(record.get('warranty_expiry_date', ''))}", fill=text_secondary, font=val_font)

    # ---------------------------------------------------------
    # Quadrant 2: Reported Defect & Timeline (Top-Right)
    # ---------------------------------------------------------
    q2_x0, q2_y0 = margin + quad_w + 20, quad_top
    draw.rectangle([(q2_x0, q2_y0), (q2_x0 + quad_w, q2_y0 + quad_h)], outline=box_border, width=1)
    draw.text((q2_x0 + 8, q2_y0 + 6), "2. DEFECT INTENSITY & TIMELINE", fill=accent_color, font=label_font)

    fault_cat = str(record.get('fault_category', 'General Defect'))[:30]
    draw.text((q2_x0 + 8, q2_y0 + 26), f"Fault: {fault_cat}", fill=text_primary, font=val_font)
    draw.text((q2_x0 + 8, q2_y0 + 46), f"Damage Type: {record.get('damage_type', 'Hardware')}", fill=text_secondary, font=val_font)
    draw.text((q2_x0 + 8, q2_y0 + 66), f"Manifest Date: {fmt_d(record.get('fault_occurrence_date', ''))}", fill=text_secondary, font=val_font)
    
    rem_days = record.get('remaining_warranty_days', 0)
    rem_str = f"{rem_days} Days Active" if rem_days > 0 else "Coverage Expired (0 Days)"
    draw.text((q2_x0 + 8, q2_y0 + 86), f"Warranty Life: {rem_str}", fill=text_primary, font=val_font)
    
    ext_str = "Extended Tier (Yes)" if record.get('is_extended_warranty') else "Standard Tier (No)"
    draw.text((q2_x0 + 8, q2_y0 + 106), f"Tier Policy: {ext_str}", fill=text_secondary, font=val_font)

    # ---------------------------------------------------------
    # Quadrant 3: Evidence & Mandatory Intake (Bottom-Left)
    # ---------------------------------------------------------
    q3_x0, q3_y0 = margin + 10, quad_top + quad_h + 10
    draw.rectangle([(q3_x0, q3_y0), (q3_x0 + quad_w, q3_y0 + quad_h)], outline=box_border, width=1)
    draw.text((q3_x0 + 8, q3_y0 + 6), "3. DOCUMENT OPERATIONS", fill=accent_color, font=label_font)

    has_rec = "Present [OK]" if record.get('has_receipt') else "MISSING [FAIL]"
    has_card = "Present [OK]" if record.get('has_warranty_card') else "MISSING [FAIL]"
    has_photo = "Present [OK]" if record.get('has_damage_photo') else "MISSING [FAIL]"
    has_ser = "Present [OK]" if record.get('has_serial_photo') else "MISSING [FAIL]"

    draw.text((q3_x0 + 8, q3_y0 + 26), f"Proof of Purchase: {has_rec}", fill=text_primary, font=val_font)
    draw.text((q3_x0 + 8, q3_y0 + 46), f"Warranty Certificate: {has_card}", fill=text_secondary, font=val_font)
    draw.text((q3_x0 + 8, q3_y0 + 66), f"Damage Evidence: {has_photo}", fill=text_secondary, font=val_font)
    draw.text((q3_x0 + 8, q3_y0 + 86), f"Serial Photograph: {has_ser}", fill=text_secondary, font=val_font)
    draw.text((q3_x0 + 8, q3_y0 + 106), f"Missing Docs Tally: {record.get('missing_document_count', 0)} Missing", fill=text_primary, font=val_font)

    # ---------------------------------------------------------
    # Quadrant 4: Service History & Integrity Checks (Bottom-Right)
    # ---------------------------------------------------------
    q4_x0, q4_y0 = margin + quad_w + 20, quad_top + quad_h + 10
    draw.rectangle([(q4_x0, q4_y0), (q4_x0 + quad_w, q4_y0 + quad_h)], outline=box_border, width=1)
    draw.text((q4_x0 + 8, q4_y0 + 6), "4. SERVICE HISTORY & INTEGRITY", fill=accent_color, font=label_font)

    ser_match_str = "SERIAL MATCHED" if record.get('serial_number_match') else "MISMATCH FLAGGED"
    draw.text((q4_x0 + 8, q4_y0 + 26), f"Serial Cross-Check: {ser_match_str}", fill=text_primary, font=val_font)
    
    rep_count = record.get('previous_repairs_count', 0)
    draw.text((q4_x0 + 8, q4_y0 + 46), f"Prior Service History: {rep_count} logged", fill=text_secondary, font=val_font)

    unauth_str = "UNAUTHORIZED (FLAGGED)" if record.get('unauthorized_repair_flag') else "Authorized / None"
    draw.text((q4_x0 + 8, q4_y0 + 66), f"Service Centers: {unauth_str}", fill=text_secondary, font=val_font)

    conflict_str = "CONTRADICTION DETECTED" if record.get('claim_date_conflict_flag') else "Chronology Consistent"
    draw.text((q4_x0 + 8, q4_y0 + 86), f"Date Coherence: {conflict_str}", fill=text_primary, font=val_font)

    retailer_str = str(record.get('retailer', 'Retail Store'))[:30]
    draw.text((q4_x0 + 8, q4_y0 + 106), f"Intake Channel: {retailer_str}", fill=text_secondary, font=val_font)

    # Bottom footer note (Mandatory reminder of card neutrality)
    footer_y = height - margin - 22
    draw.text(
        (margin + 10, footer_y),
        "Official Evaluation Artifact: Visual Summary Card strictly containing raw claim evidence. Excludes all AI predictions.",
        fill=(100, 116, 139),
        font=label_font
    )

    return img


def generate_all_summary_cards():
    """
    Generates standardized Claim Summary Cards for train, validation, and testing splits.
    
    - Training Set: 1,050 records x 2 visual variations = 2,100 images
      Divided into:
        - data/summary_cards/train/valid/ (700 images)
        - data/summary_cards/train/invalid/ (700 images)
        - data/summary_cards/train/manual_review/ (700 images)
    - Validation Set: 225 records = 225 images in data/summary_cards/val/
    - Testing Set: 225 records = 225 images in data/summary_cards/test/
    - Mapping manifest: data/claim_id_to_card_mapping.csv
    """
    print("-> Generating standardized visual Claim Summary Cards...")

    train_df = pd.read_csv(SPLITS_DIR / "train.csv")
    val_df = pd.read_csv(SPLITS_DIR / "val.csv")
    test_df = pd.read_csv(SPLITS_DIR / "test.csv")

    mapping_records = []

    # Map class labels to directory names
    class_folder_map = {
        "Valid Claim": "valid",
        "Invalid Claim": "invalid",
        "Manual Review": "manual_review"
    }

    # 1. Training Set with at least 2 visual variations per claim (>= 2,100 images)
    print(f"   Generating training card images (2 visual variations per claim, total {len(train_df) * 2} images)...")
    for _, row in train_df.iterrows():
        rec = row.to_dict()
        claim_id = rec["claim_id"]
        claim_cls = rec["claim_class"]
        subfolder = class_folder_map[claim_cls]
        target_dir = CARDS_DIR / "train" / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        for var_idx in [1, 2]:
            img = render_claim_summary_card(rec, variation=var_idx)
            img_filename = f"{claim_id}_v{var_idx}.png"
            img_path = target_dir / img_filename
            img.save(img_path, format="PNG")

            mapping_records.append({
                "claim_id": claim_id,
                "split": "train",
                "claim_class": claim_cls,
                "variation": var_idx,
                "filename": img_filename,
                "relative_path": f"train/{subfolder}/{img_filename}"
            })

    # 2. Validation Set (225 images held out)
    print(f"   Generating validation card images ({len(val_df)} held-out images)...")
    val_target = CARDS_DIR / "val"
    val_target.mkdir(parents=True, exist_ok=True)
    for _, row in val_df.iterrows():
        rec = row.to_dict()
        claim_id = rec["claim_id"]
        claim_cls = rec["claim_class"]
        img = render_claim_summary_card(rec, variation=1)
        img_filename = f"{claim_id}.png"
        img_path = val_target / img_filename
        img.save(img_path, format="PNG")

        mapping_records.append({
            "claim_id": claim_id,
            "split": "validation",
            "claim_class": claim_cls,
            "variation": 1,
            "filename": img_filename,
            "relative_path": f"val/{img_filename}"
        })

    # 3. Testing Set (225 images held out)
    print(f"   Generating test card images ({len(test_df)} held-out images)...")
    test_target = CARDS_DIR / "test"
    test_target.mkdir(parents=True, exist_ok=True)
    for _, row in test_df.iterrows():
        rec = row.to_dict()
        claim_id = rec["claim_id"]
        claim_cls = rec["claim_class"]
        img = render_claim_summary_card(rec, variation=1)
        img_filename = f"{claim_id}.png"
        img_path = test_target / img_filename
        img.save(img_path, format="PNG")

        mapping_records.append({
            "claim_id": claim_id,
            "split": "test",
            "claim_class": claim_cls,
            "variation": 1,
            "filename": img_filename,
            "relative_path": f"test/{img_filename}"
        })

    # Save mapping manifest
    manifest_df = pd.DataFrame(mapping_records)
    manifest_path = DATA_DIR / "claim_id_to_card_mapping.csv"
    manifest_df.to_csv(manifest_path, index=False)

    print(f"   [+] Claim Summary Card generation complete!")
    print(f"   [+] Total Card Images: {len(manifest_df)} images (2,100 Train, 225 Val, 225 Test)")
    print(f"   [+] Mapping Manifest:  {manifest_path}")

    return manifest_df

if __name__ == "__main__":
    generate_all_summary_cards()
