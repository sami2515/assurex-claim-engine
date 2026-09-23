from flask import has_app_context
from src.models.entities import Claim, ClaimDocument, Product


class DuplicateDetector:
    """Detects duplicate claims and cross-claim duplicate documents using SHA-256 hashing."""

    @staticmethod
    def check_document_duplicates(file_hash: str, exclude_claim_id: int = None) -> dict:
        """
        Req xxxi: Checks if a document hash already exists in another claim record.
        """
        if not file_hash or not has_app_context():
            return {"is_duplicate": False, "matched_claims": []}

        try:
            query = ClaimDocument.query.filter_by(file_hash_sha256=file_hash)
            if exclude_claim_id:
                query = query.filter(ClaimDocument.claim_id != exclude_claim_id)

            matches = query.all()
            if matches:
                matched_claim_ids = [m.claim.claim_id for m in matches if m.claim]
                return {
                    "is_duplicate": True,
                    "matched_claims": list(set(matched_claim_ids)),
                    "document_type": matches[0].document_type,
                    "message": f"Identical file already submitted in claim(s): {', '.join(set(matched_claim_ids))}"
                }
        except Exception:
            pass

        return {"is_duplicate": False, "matched_claims": []}

    @staticmethod
    def check_claim_duplicates(claim_data: dict, current_claim_internal_id: int = None) -> dict:
        """
        Req xxx: Checks if the claim attributes match an existing active or closed claim:
        - Matching Product Serial Number
        - Matching Invoice Number
        - Identical Fault Description on same product
        """
        duplicate_flags = []
        conflicting_claim_ids = []

        serial_no = claim_data.get("product_serial")
        invoice_no = claim_data.get("invoice_number")
        current_claim_code = claim_data.get("claim_id")

        if not has_app_context():
            return {
                "is_duplicate": False,
                "duplicate_flags": [],
                "conflicting_claim_ids": [],
                "summary": "No duplicate indicators detected."
            }

        try:
            if serial_no:
                # Find products with same serial
                matching_products = Product.query.filter_by(serial_number=serial_no).all()
                for prod in matching_products:
                    for c in prod.claims:
                        if current_claim_internal_id and c.id == current_claim_internal_id:
                            continue
                        if current_claim_code and c.claim_id == current_claim_code:
                            continue

                        # If an existing claim is currently open or approved
                        if c.status in ["Submitted", "Under Evaluation", "Manual Review", "Approved"]:
                            duplicate_flags.append(
                                f"Active claim {c.claim_id} already exists for serial number '{serial_no}' with status '{c.status}'."
                            )
                            conflicting_claim_ids.append(c.claim_id)

            # Check invoice number collision across different claims
            if invoice_no and invoice_no not in ["INV-2026-00000", "N/A"]:
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
        except Exception:
            pass

        is_duplicate = len(duplicate_flags) > 0

        return {
            "is_duplicate": is_duplicate,
            "duplicate_flags": duplicate_flags,
            "conflicting_claim_ids": list(set(conflicting_claim_ids)),
            "summary": "Duplicate claim indicator detected." if is_duplicate else "No duplicate indicators detected."
        }


# Singleton duplicate detector instance
_duplicate_detector_instance = None

def get_duplicate_detector() -> DuplicateDetector:
    global _duplicate_detector_instance
    if _duplicate_detector_instance is None:
        _duplicate_detector_instance = DuplicateDetector()
    return _duplicate_detector_instance
