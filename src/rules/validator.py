"""
AssureX Claim Engine - Data Validation & Missing Document Detection Engine
Fulfills:
- Req 1.6.xv: Data Validation (mandatory fields, date formats, numerical values, file types & sizes, duplicate IDs).
- Req 1.6.xxix: Missing Document Detection (identifies missing purchase receipt, warranty card, product image,
  serial-number evidence, fault evidence, or repair report, informing user of required documentation).
- Req 1.6.xxx: Duplicate Claim Detection integration.
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
    """Validates claim intake data, detects missing documents, and enforces upload constraints."""

    MANDATORY_DOCUMENT_SPECS = [
        {
            "key": "receipt",
            "aliases": ["receipt", "invoice_document", "invoice"],
            "name": "Purchase Receipt / Invoice",
            "description": "Proof of purchase detailing transaction date, price, and authorized retailer."
        },
        {
            "key": "warranty_card",
            "aliases": ["warranty_card", "warranty_certificate"],
            "name": "Warranty Card",
            "description": "Manufacturer or retailer warranty card verifying coverage terms."
        },
        {
            "key": "product_photo",
            "aliases": ["product_photo", "product_image"],
            "name": "Product Photograph",
            "description": "Clear photograph of the entire equipment showing current physical condition."
        },
        {
            "key": "serial_photo",
            "aliases": ["serial_photo", "serial_number_evidence"],
            "name": "Serial-Number Evidence",
            "description": "Photograph of the manufacturer serial-number barcode or chassis stamp."
        },
        {
            "key": "fault_evidence",
            "aliases": ["damage_photo", "fault_video", "fault_evidence"],
            "name": "Fault / Damage Evidence",
            "description": "Photo or video capturing the defect, hardware damage, or malfunction."
        }
    ]

    REPAIR_REPORT_SPEC = {
        "key": "repair_report",
        "aliases": ["diagnostic_report", "repair_report"],
        "name": "Service / Repair Report",
        "description": "Service center diagnostic report documenting previous repairs or maintenance."
    }

    @staticmethod
    def parse_date(date_val):
        """Parses date strings across standard formats (YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY)."""
        if not date_val:
            return None
        if isinstance(date_val, datetime):
            return date_val.date()
        if isinstance(date_val, date):
            return date_val
        s = str(date_val).strip()
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def identify_missing_documents(cls, documents_or_files, has_previous_repairs: bool = False) -> dict:
        """
        Req 1.6.xxix: Missing Document Detection.
        Evaluates submitted documents or attached claim files against mandatory requirements:
        - Purchase receipt or invoice
        - Warranty card
        - Product image
        - Serial-number evidence
        - Fault evidence (damage photo or defect video)
        - Repair report (required when product has prior repair history)
        """
        present_types = set()

        if isinstance(documents_or_files, dict):
            # Form files dictionary (e.g. request.files or files_dict)
            for k, v in documents_or_files.items():
                if v:
                    if hasattr(v, "filename") and v.filename:
                        present_types.add(k.lower())
                    elif isinstance(v, str) and v.strip():
                        present_types.add(k.lower())
                    elif isinstance(v, (list, tuple)) and len(v) > 0:
                        present_types.add(k.lower())
        elif isinstance(documents_or_files, (list, tuple)):
            for item in documents_or_files:
                if hasattr(item, "document_type") and item.document_type:
                    present_types.add(item.document_type.lower())
                elif isinstance(item, dict) and item.get("document_type"):
                    present_types.add(item["document_type"].lower())
                elif isinstance(item, str):
                    present_types.add(item.lower())

        missing_documents = []
        for spec in cls.MANDATORY_DOCUMENT_SPECS:
            is_present = any(alias.lower() in present_types for alias in spec["aliases"])
            if not is_present:
                missing_documents.append({
                    "key": spec["key"],
                    "name": spec["name"],
                    "description": spec["description"],
                    "mandatory": True
                })

        # Check repair report requirement
        if has_previous_repairs:
            has_report = any(alias.lower() in present_types for alias in cls.REPAIR_REPORT_SPEC["aliases"])
            if not has_report:
                missing_documents.append({
                    "key": cls.REPAIR_REPORT_SPEC["key"],
                    "name": cls.REPAIR_REPORT_SPEC["name"],
                    "description": cls.REPAIR_REPORT_SPEC["description"],
                    "mandatory": True
                })

        has_missing = len(missing_documents) > 0
        missing_labels = [d["name"] for d in missing_documents]
        user_message = (
            f"Missing mandatory document(s): {', '.join(missing_labels)}."
            if has_missing
            else "All mandatory claim documents are present and verified."
        )

        return {
            "has_missing": has_missing,
            "missing_count": len(missing_documents),
            "missing_documents": missing_documents,
            "missing_labels": missing_labels,
            "present_documents": list(present_types),
            "user_message": user_message
        }

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
        Validates claim intake submission against SRS Req 1.6.xv & xxix specifications.
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
            fault_date = cls.parse_date(fault_date_str)
            if fault_date is not None:
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
            else:
                errors.append(f"Invalid date format for fault occurrence: '{fault_date_str}'. Expected format is YYYY-MM-DD or DD/MM/YYYY.")

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

        # 5. Uploaded File Types & Size Validation & Missing Document Detection (Req 1.6.xxix)
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

        has_repairs = bool(product and (
            (hasattr(product, "repair_records") and len(product.repair_records) > 0) or
            getattr(product, "has_prior_repairs", False)
        ))
        missing_info = cls.identify_missing_documents(files_dict, has_previous_repairs=has_repairs)
        cleaned["missing_documents_info"] = missing_info

        if missing_info["has_missing"]:
            for m_doc in missing_info["missing_documents"]:
                warnings.append(
                    f"Missing Mandatory Document: '{m_doc['name']}' is required. {m_doc['description']}"
                )

        # 6. Duplicate Claim ID Check & Duplicate Claim Safeguard (Req 1.6.xxx)
        # Verify generated / submitted Claim ID does not already exist
        custom_claim_id = form_data.get("custom_claim_id")
        if custom_claim_id:
            existing = Claim.query.filter_by(claim_id=custom_claim_id).first()
            if existing:
                errors.append(f"Duplicate Claim ID collision: Identifier '{custom_claim_id}' is already registered in the system.")

        # Check for duplicate claim submissions on the same product
        if product and fault_date and fault_description:
            dup_check = DuplicateDetector.check_claim_duplicates({
                "claim_id": custom_claim_id,
                "product_serial": product.serial_number,
                "invoice_number": product.invoice_number,
                "fault_description": fault_description,
                "fault_occurrence_date": fault_date.strftime("%Y-%m-%d"),
                "claimant_id": form_data.get("user_id") or form_data.get("claimant_id")
            })
            if dup_check.get("is_duplicate"):
                warnings.append(
                    f"Duplicate Advisory: A claim with matching attributes has been detected "
                    f"(Matched: {', '.join(dup_check.get('conflicting_claim_ids', []))})."
                )

        # Populate remaining cleaned fields
        cleaned["fault_category"] = fault_category
        cleaned["damage_type"] = damage_type
        cleaned["fault_description"] = fault_description
        cleaned["previous_replacement_details"] = (form_data.get("previous_replacement_details") or "").strip() or None

        is_valid = len(errors) == 0
        return is_valid, errors, warnings, cleaned

    @classmethod
    def check_claim_preparation_readiness(cls, form_data: Dict[str, Any], files_dict: Dict[str, Any], product=None) -> Dict[str, Any]:
        """
        Req 1.6.xxxiii: Claim Preparation Assistance.
        Guides the user before final submission by analyzing:
        1. Missing information
        2. Missing documents
        3. Approaching deadlines
        4. Possible contradictions
        5. Recommended corrective actions
        Computes overall claim dossier readiness percentage score.
        """
        missing_information = []
        possible_contradictions = []
        recommended_actions = []

        # 1. Missing Information
        fault_cat = (form_data.get("fault_category") or "").strip()
        damage_type = (form_data.get("damage_type") or "").strip()
        fault_desc = (form_data.get("fault_description") or "").strip()
        fault_date_str = (form_data.get("fault_occurrence_date") or "").strip()

        if not product and not form_data.get("product_id"):
            missing_information.append("Product: No registered equipment selected.")
            recommended_actions.append("Select a registered product from your equipment catalog.")

        if not fault_cat:
            missing_information.append("Defect Category: Failure category must be specified.")
            recommended_actions.append("Select the primary defect category (e.g. Screen Flickering, Battery Degradation).")

        if not damage_type:
            missing_information.append("Damage Nature: Suspected damage nature must be selected.")
            recommended_actions.append("Choose suspected damage nature (e.g. Manufacturing Defect, Normal Wear).")

        if not fault_desc:
            missing_information.append("Defect Description: Detailed fault description is required.")
            recommended_actions.append("Provide a clear description explaining how the hardware defect occurred.")
        elif len(fault_desc) < 10:
            missing_information.append("Defect Description: Description is too brief (minimum 10 characters required).")
            recommended_actions.append("Expand on the defect description with specific details of the hardware malfunction.")

        if not fault_date_str:
            missing_information.append("Fault Date: Date of defect occurrence must be provided.")
            recommended_actions.append("Specify the exact calendar date when the failure occurred.")

        # 2. Missing Documents
        has_repairs = bool(product and (
            (hasattr(product, "repair_records") and len(product.repair_records) > 0) or
            getattr(product, "has_prior_repairs", False)
        ))
        missing_docs_result = cls.identify_missing_documents(files_dict, has_previous_repairs=has_repairs)

        for m_doc in missing_docs_result["missing_documents"]:
            recommended_actions.append(f"Upload '{m_doc['name']}' to fulfill mandatory evidence requirements.")

        # 3. Approaching Deadlines
        deadlines_info = {
            "has_deadline_warning": False,
            "expiry_date": None,
            "days_remaining": None,
            "status": "Unknown",
            "message": "No active warranty record found."
        }
        if product and product.warranty:
            w = product.warranty
            remaining_days = w.remaining_days()
            deadlines_info["expiry_date"] = w.expiry_date.strftime("%Y-%m-%d")
            deadlines_info["days_remaining"] = remaining_days
            deadlines_info["status"] = w.status

            if not w.is_active():
                deadlines_info["has_deadline_warning"] = True
                deadlines_info["message"] = f"Warranty coverage expired on {w.expiry_date.strftime('%Y-%m-%d')} ({abs(remaining_days)} days ago)."
                recommended_actions.append("Check if your equipment qualifies for extended warranty grace periods or paid repair coverage.")
            elif remaining_days <= 30:
                deadlines_info["has_deadline_warning"] = True
                deadlines_info["message"] = f"Urgent: Warranty will expire in {remaining_days} days on {w.expiry_date.strftime('%Y-%m-%d')}."
                recommended_actions.append("Submit your claim promptly before warranty expiration to ensure standard coverage.")
            else:
                deadlines_info["message"] = f"Warranty coverage is active with {remaining_days} days remaining (expires {w.expiry_date.strftime('%Y-%m-%d')})."

        # 4. Possible Contradictions
        fault_date = None
        if fault_date_str:
            try:
                fault_date = datetime.strptime(fault_date_str, "%Y-%m-%d").date()
                if fault_date > date.today():
                    possible_contradictions.append(f"Future Date: Fault occurrence date ({fault_date}) is in the future.")
                    recommended_actions.append("Correct the fault occurrence date to a valid past or present calendar date.")

                if product and product.purchase_date and fault_date < product.purchase_date:
                    possible_contradictions.append(
                        f"Chronological Conflict: Fault occurrence date ({fault_date}) predates product purchase date ({product.purchase_date})."
                    )
                    recommended_actions.append("Verify the fault date against your store purchase invoice to resolve the chronological conflict.")
            except ValueError:
                pass

        # 5. Readiness Score
        penalties = (len(missing_information) * 2) + (len(missing_docs_result["missing_documents"]) * 1.5) + (len(possible_contradictions) * 2)
        score = max(10, int(100 - min(90, penalties * 7)))

        if not recommended_actions:
            recommended_actions.append("All intake criteria satisfied. Proceed to final review and submit for evaluation.")

        return {
            "is_ready_for_submission": len(missing_information) == 0 and len(possible_contradictions) == 0,
            "readiness_score": score,
            "missing_information": missing_information,
            "missing_documents": missing_docs_result["missing_documents"],
            "missing_document_labels": missing_docs_result["missing_labels"],
            "approaching_deadlines": deadlines_info,
            "possible_contradictions": possible_contradictions,
            "recommended_corrective_actions": recommended_actions
        }

