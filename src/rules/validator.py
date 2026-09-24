"""
AssureX Claim Engine - Data Validation Engine
Fulfills Req 1.6.xv: Data Validation.
Checks mandatory fields, date formats, numerical values, uploaded file types,
file sizes, and duplicate Claim IDs. Prevents incomplete or invalid information
from being submitted without appropriate warnings.
"""

import os
from datetime import datetime, date
from pathlib import Path
from typing import Tuple, List, Dict, Any
from config.config import Config
from src.models.entities import Claim, Product, ProductWarranty
from src.rules.duplicate_detector import DuplicateDetector

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "mp4", "mov", "webm"}
MAX_FILE_SIZE_BYTES = 16 * 1024 * 1024  # 16 MB max per evidence item


class ClaimValidator:
    """Validates claim intake data and supporting documents."""

    @staticmethod
    def validate_file(file_storage) -> Tuple[bool, str]:
        """
        Validates an uploaded file's extension and size.
        Returns (is_valid, error_message).
        """
        if not file_storage:
            return True, ""

        filename = ""
        if hasattr(file_storage, "filename") and file_storage.filename:
            filename = file_storage.filename
        elif isinstance(file_storage, tuple) and len(file_storage) > 1 and isinstance(file_storage[1], str):
            filename = file_storage[1]
        elif isinstance(file_storage, str):
            filename = file_storage

        if not filename:
            return True, ""

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext not in ALLOWED_EXTENSIONS:
            return False, f"File '{filename}' has an unsupported extension (.{ext}). Allowed formats: PDF, PNG, JPG, JPEG, MP4, MOV, WEBM."

        # Check file length/size if seekable
        try:
            stream = file_storage[0] if isinstance(file_storage, tuple) else file_storage
            if hasattr(stream, "seek") and hasattr(stream, "tell"):
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(0)
                if size > MAX_FILE_SIZE_BYTES:
                    size_mb = size / (1024 * 1024)
                    return False, f"File '{filename}' exceeds maximum allowed size of 16 MB (Size: {size_mb:.2f} MB)."
        except Exception:
            pass

        return True, ""

    @classmethod
    def validate_claim_submission(
        cls,
        form_data: Dict[str, Any],
        files_dict: Dict[str, Any],
        user_role: str = Config.ROLE_CUSTOMER
    ) -> Tuple[bool, List[str], List[str], Dict[str, Any]]:
        """
        Validates claim intake submission against SRS Req 1.6.xv specifications.
        Returns:
            - is_valid (bool): True if all mandatory checks pass.
            - errors (List[str]): Critical blocking validation failures.
            - warnings (List[str]): Non-blocking informational advisories.
            - cleaned_data (Dict[str, Any]): Type-coerced, validated fields.
        """
        errors = []
        warnings = []
        cleaned = {}

        # 1. Mandatory Fields Validation
        product_id_str = form_data.get("product_id")
        fault_category = (form_data.get("fault_category") or "").strip()
        damage_type = (form_data.get("damage_type") or "").strip()
        fault_description = (form_data.get("fault_description") or "").strip()
        fault_date_str = (form_data.get("fault_occurrence_date") or "").strip()

        if not product_id_str:
            errors.append("Mandatory field missing: Please select a registered product for this claim.")

        if not fault_category:
            errors.append("Mandatory field missing: Defect category must be specified.")

        if not damage_type:
            errors.append("Mandatory field missing: Damage type must be selected.")

        if not fault_description:
            errors.append("Mandatory field missing: Detailed fault description is required.")
        elif len(fault_description) < 10:
            errors.append("Fault description is too brief. Please provide at least 10 characters detailing the failure.")

        # 2. Product & Warranty Verification
        product = None
        if product_id_str:
            if str(product_id_str).isdigit():
                from database.db import db
                product = db.session.get(Product, int(product_id_str))
            if not product:
                product = Product.query.filter_by(product_id=str(product_id_str)).first()

            if not product:
                errors.append(f"Invalid product identifier: Product '{product_id_str}' was not found in records.")
            elif not product.warranty:
                errors.append(f"Product '{product.product_name}' does not have an associated warranty policy.")
            else:
                cleaned["product"] = product

        # 3. Date Formats & Logical Consistency
        fault_date = None
        if not fault_date_str:
            errors.append("Mandatory field missing: Date of fault occurrence must be provided.")
        else:
            try:
                fault_date = datetime.strptime(fault_date_str, "%Y-%m-%d").date()
                cleaned["fault_occurrence_date"] = fault_date

                # Logic check: Cannot be in the future
                if fault_date > date.today():
                    errors.append(f"Invalid date: Fault occurrence date ({fault_date}) cannot be in the future.")

                # Logic check: Cannot be earlier than product purchase date
                if product and product.purchase_date and fault_date < product.purchase_date:
                    warnings.append(
                        f"Date Conflict: Fault date ({fault_date}) is earlier than product purchase date "
                        f"({product.purchase_date}). This may affect claim eligibility."
                    )
            except ValueError:
                errors.append(f"Invalid date format for fault occurrence: '{fault_date_str}'. Expected format is YYYY-MM-DD.")

        # 4. Numerical Values Validation
        claim_amount_str = form_data.get("claim_amount")
        if claim_amount_str:
            try:
                claim_amount = float(claim_amount_str)
                if claim_amount <= 0:
                    errors.append("Numerical error: Estimated claim amount must be greater than zero.")
                elif product and claim_amount > (product.purchase_price * 2.5):
                    warnings.append(
                        f"High Valuation Warning: Claim amount (${claim_amount:.2f}) significantly exceeds product "
                        f"original purchase price (${product.purchase_price:.2f})."
                    )
                cleaned["claim_amount"] = claim_amount
            except ValueError:
                errors.append(f"Numerical error: Claim amount '{claim_amount_str}' is not a valid monetary number.")
        else:
            # Default to product purchase price if omitted
            cleaned["claim_amount"] = product.purchase_price if product else 0.0

        # 5. Uploaded File Types & Size Validation
        evidence_keys = [
            "invoice_document", "receipt", "warranty_card", "damage_photo",
            "product_photo", "fault_video", "serial_photo", "diagnostic_report", "other_evidence"
        ]

        has_any_proof = False
        for key in evidence_keys:
            f = files_dict.get(key)
            if f:
                has_any_proof = True
                ok, file_err = cls.validate_file(f)
                if not ok:
                    errors.append(file_err)

        if not has_any_proof:
            warnings.append("Advisory: No supporting purchase receipt or photo evidence was attached. Document verification score will be reduced.")

        # 6. Duplicate Claim ID Check & Duplicate Claim Safeguard
        # Verify generated / submitted Claim ID does not already exist
        custom_claim_id = form_data.get("custom_claim_id")
        if custom_claim_id:
            existing = Claim.query.filter_by(claim_id=custom_claim_id).first()
            if existing:
                errors.append(f"Duplicate Claim ID collision: Identifier '{custom_claim_id}' is already registered in the system.")

        # Check for duplicate claim submissions on the same product
        if product and fault_date and fault_description:
            dup_check = DuplicateDetector.check_claim_duplicates({
                "product_serial": product.serial_number,
                "invoice_number": product.invoice_number,
                "fault_description": fault_description,
                "fault_occurrence_date": fault_date.strftime("%Y-%m-%d")
            })
            if dup_check.get("is_duplicate"):
                warnings.append(
                    f"Duplicate Advisory: A claim with identical attributes has been detected "
                    f"(Matched: {', '.join(dup_check.get('conflicting_claim_ids', []))})."
                )

        # Populate remaining cleaned fields
        cleaned["fault_category"] = fault_category
        cleaned["damage_type"] = damage_type
        cleaned["fault_description"] = fault_description
        cleaned["previous_replacement_details"] = (form_data.get("previous_replacement_details") or "").strip() or None

        is_valid = len(errors) == 0
        return is_valid, errors, warnings, cleaned
