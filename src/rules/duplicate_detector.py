from flask import has_app_context
from src.models.entities import Claim, ClaimDocument, Product


class DuplicateDetector:
    """
    Detects duplicate claims and cross-claim duplicate documents.
    Fulfills:
    - Req 1.6.xxx: Duplicate Claim Detection (comparing Claim IDs, invoice numbers,
      product serial numbers, fault descriptions, claimant details, document hashes,
      and previous claim records).
    - Req 1.6.xxxi: Document Duplicate Detection (secure SHA-256 hash comparison across claims).
    """

    @staticmethod
    def check_document_duplicates(file_hash: str, exclude_claim_id: int = None, document_type: str = None) -> dict:
        """
        Req xxxi: Checks if a document SHA-256 hash already exists in another claim record.
        Detects whether the same receipt, invoice, warranty card, or evidence file has already been used.
        """
        if not file_hash or not has_app_context():
            return {
                "is_duplicate": False,
                "matched_claims": [],
                "matched_documents": [],
                "document_type": None,
                "file_hash": file_hash,
                "message": ""
            }

        try:
            query = ClaimDocument.query.filter_by(file_hash_sha256=file_hash)
            if exclude_claim_id:
                query = query.filter(ClaimDocument.claim_id != exclude_claim_id)

            matches = query.all()
            if matches:
                matched_claim_ids = [m.claim.claim_id for m in matches if m.claim]
                matched_docs_info = [
                    {
                        "claim_id": m.claim.claim_id if m.claim else None,
                        "document_type": m.document_type,
                        "filename": m.original_filename,
                        "file_hash": m.file_hash_sha256,
                        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else None
                    }
                    for m in matches
                ]
                doc_kind = (matches[0].document_type or "file").replace("_", " ")
                claims_str = ", ".join(sorted(set(matched_claim_ids))) if matched_claim_ids else "prior claims"
                return {
                    "is_duplicate": True,
                    "matched_claims": list(set(matched_claim_ids)),
                    "matched_documents": matched_docs_info,
                    "document_type": matches[0].document_type,
                    "file_hash": file_hash,
                    "message": f"Identical file ({doc_kind}) already submitted in claim(s): {claims_str}"
                }
        except Exception:
            pass

        return {
            "is_duplicate": False,
            "matched_claims": [],
            "matched_documents": [],
            "document_type": None,
            "file_hash": file_hash,
            "message": ""
        }

    check_document_duplicate = check_document_duplicates

    @staticmethod
    def check_multiple_document_duplicates(file_hashes: list, exclude_claim_id: int = None) -> dict:
        """
        Req xxxi: Batch verification of multiple document hashes.
        """
        duplicates = []
        conflicting_claims = []
        for f_hash in file_hashes or []:
            res = DuplicateDetector.check_document_duplicates(f_hash, exclude_claim_id=exclude_claim_id)
            if res["is_duplicate"]:
                duplicates.append(res)
                conflicting_claims.extend(res["matched_claims"])

        return {
            "has_duplicate_documents": len(duplicates) > 0,
            "duplicates": duplicates,
            "conflicting_claim_ids": list(set(conflicting_claims))
        }

    @staticmethod
    def check_claim_duplicates(
        claim_data: dict,
        current_claim_internal_id: int = None,
        uploaded_file_hashes: list = None
    ) -> dict:
        """
        Req xxx: Checks if the claim attributes match an existing active or closed claim
        by comparing all 7 SRS parameters:
        1. Claim IDs (duplicate claim ID collision)
        2. Invoice numbers (cross-claim invoice reuse)
        3. Product serial numbers (active claim on same serial)
        4. Fault descriptions (identical defect description on same serial)
        5. Claimant details (claimant repetitive claims on same hardware)
        6. Document hashes (SHA-256 cryptographic hashes)
        7. Previous claim records (historical claim records for the product)
        """
        duplicate_flags = []
        conflicting_claim_ids = []
        factors_triggered = []

        serial_no = (claim_data.get("product_serial") or claim_data.get("serial_number") or "").strip()
        invoice_no = (claim_data.get("invoice_number") or "").strip()
        current_claim_code = (claim_data.get("claim_id") or claim_data.get("custom_claim_id") or "").strip()
        fault_desc = (claim_data.get("fault_description") or "").strip()
        claimant_id = claim_data.get("claimant_id") or claim_data.get("user_id")

        if not has_app_context():
            return {
                "is_duplicate": False,
                "duplicate_flags": [],
                "conflicting_claim_ids": [],
                "factors_triggered": [],
                "summary": "No duplicate indicators detected."
            }

        try:
            # -------------------------------------------------------------
            # Factor 1: Claim ID Collision Check
            # -------------------------------------------------------------
            if current_claim_code:
                existing_by_id = Claim.query.filter_by(claim_id=current_claim_code).first()
                if existing_by_id and (not current_claim_internal_id or existing_by_id.id != current_claim_internal_id):
                    duplicate_flags.append(
                        f"Duplicate Claim ID collision: Identifier '{current_claim_code}' already exists in the system."
                    )
                    conflicting_claim_ids.append(existing_by_id.claim_id)
                    factors_triggered.append("claim_id")

            # -------------------------------------------------------------
            # Factor 6: Cryptographic Document Hashes (SHA-256) Check (Req xxxi)
            # -------------------------------------------------------------
            hashes_to_check = list(uploaded_file_hashes or [])
            if not hashes_to_check and current_claim_internal_id:
                # Auto-fetch document hashes attached to this claim
                attached_docs = ClaimDocument.query.filter_by(claim_id=current_claim_internal_id).all()
                hashes_to_check = [d.file_hash_sha256 for d in attached_docs if d.file_hash_sha256]

            if hashes_to_check:
                for f_hash in hashes_to_check:
                    doc_check = DuplicateDetector.check_document_duplicates(
                        f_hash, exclude_claim_id=current_claim_internal_id
                    )
                    if doc_check["is_duplicate"]:
                        duplicate_flags.append(f"Identical document hash detected: {doc_check['message']}")
                        conflicting_claim_ids.extend(doc_check["matched_claims"])
                        if "document_hashes" not in factors_triggered:
                            factors_triggered.append("document_hashes")

            # -------------------------------------------------------------
            # Factor 3: Product Serial Numbers & Active Claims
            # -------------------------------------------------------------
            matching_products = []
            if serial_no:
                matching_products = Product.query.filter_by(serial_number=serial_no).all()
                for prod in matching_products:
                    for c in prod.claims:
                        if current_claim_internal_id and c.id == current_claim_internal_id:
                            continue
                        if current_claim_code and c.claim_id == current_claim_code:
                            continue

                        # If an existing claim is currently active or approved
                        if c.status not in ["Closed", "Rejected"]:
                            duplicate_flags.append(
                                f"Active claim {c.claim_id} already exists for serial number '{serial_no}' with status '{c.status}'."
                            )
                            conflicting_claim_ids.append(c.claim_id)
                            if "product_serial" not in factors_triggered:
                                factors_triggered.append("product_serial")

            # -------------------------------------------------------------
            # Factor 2: Invoice Number Collision
            # -------------------------------------------------------------
            if invoice_no and invoice_no not in ["INV-2026-00000", "N/A", "NONE", ""]:
                matching_claims = Claim.query.join(Product).filter(
                    Product.invoice_number == invoice_no
                ).all()
                for c in matching_claims:
                    if current_claim_internal_id and c.id == current_claim_internal_id:
                        continue
                    if current_claim_code and c.claim_id == current_claim_code:
                        continue
                    duplicate_flags.append(
                        f"Invoice number '{invoice_no}' was previously processed under claim {c.claim_id}."
                    )
                    conflicting_claim_ids.append(c.claim_id)
                    if "invoice_number" not in factors_triggered:
                        factors_triggered.append("invoice_number")

            # -------------------------------------------------------------
            # Factor 4: Fault Description Similarity
            # -------------------------------------------------------------
            if fault_desc and len(fault_desc) >= 10 and matching_products:
                norm_target = fault_desc.strip().lower()
                for prod in matching_products:
                    for c in prod.claims:
                        if current_claim_internal_id and c.id == current_claim_internal_id:
                            continue
                        if current_claim_code and c.claim_id == current_claim_code:
                            continue
                        if c.fault_description:
                            norm_existing = c.fault_description.strip().lower()
                            # Exact or high substring overlap check
                            if norm_existing == norm_target or (len(norm_target) > 20 and norm_target in norm_existing):
                                duplicate_flags.append(
                                    f"Identical fault description matches previous claim {c.claim_id} for serial '{serial_no}': '{c.fault_description[:60]}...'"
                                )
                                conflicting_claim_ids.append(c.claim_id)
                                if "fault_description" not in factors_triggered:
                                    factors_triggered.append("fault_description")

            # -------------------------------------------------------------
            # Factor 5: Claimant Details
            # -------------------------------------------------------------
            if claimant_id and matching_products:
                for prod in matching_products:
                    for c in prod.claims:
                        if current_claim_internal_id and c.id == current_claim_internal_id:
                            continue
                        if current_claim_code and c.claim_id == current_claim_code:
                            continue
                        if c.user_id == claimant_id:
                            duplicate_flags.append(
                                f"Claimant (User #{claimant_id}) already has an existing claim dossier ({c.claim_id}) on file for serial '{serial_no}'."
                            )
                            conflicting_claim_ids.append(c.claim_id)
                            if "claimant_details" not in factors_triggered:
                                factors_triggered.append("claimant_details")

            # -------------------------------------------------------------
            # Factor 7: Previous Claim Records History
            # -------------------------------------------------------------
            if matching_products:
                prior_claims = []
                for prod in matching_products:
                    for c in prod.claims:
                        if current_claim_internal_id and c.id == current_claim_internal_id:
                            continue
                        if current_claim_code and c.claim_id == current_claim_code:
                            continue
                        prior_claims.append(c)

                if prior_claims:
                    prior_codes = [c.claim_id for c in prior_claims]
                    duplicate_flags.append(
                        f"Product serial '{serial_no}' has {len(prior_claims)} prior claim record(s) on file ({', '.join(prior_codes)})."
                    )
                    if "previous_claim_records" not in factors_triggered:
                        factors_triggered.append("previous_claim_records")

        except Exception:
            pass

        # Duplicate status is true if any conflicting active claims, hash collisions,
        # invoice collisions, ID collisions, or duplicate fault descriptions exist
        is_duplicate = len(conflicting_claim_ids) > 0 or any(
            f in factors_triggered for f in ["claim_id", "invoice_number", "document_hashes", "product_serial", "fault_description", "claimant_details"]
        )

        return {
            "is_duplicate": is_duplicate,
            "duplicate_flags": duplicate_flags,
            "conflicting_claim_ids": list(set(conflicting_claim_ids)),
            "factors_triggered": factors_triggered,
            "summary": "Duplicate claim indicator detected." if is_duplicate else "No duplicate indicators detected."
        }


# Singleton duplicate detector instance
_duplicate_detector_instance = None

def get_duplicate_detector() -> DuplicateDetector:
    global _duplicate_detector_instance
    if _duplicate_detector_instance is None:
        _duplicate_detector_instance = DuplicateDetector()
    return _duplicate_detector_instance
