from datetime import datetime, date


class ContradictionDetector:
    """Detects chronological, serial-number, and model-level inconsistencies (Req xxvii & xxviii)."""

    @staticmethod
    def parse_date(d_val):
        """Safely parses a string or date object into a datetime.date."""
        if not d_val:
            return None
        if isinstance(d_val, (date, datetime)):
            return d_val if isinstance(d_val, date) else d_val.date()
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
            try:
                return datetime.strptime(str(d_val).strip(), fmt).date()
            except ValueError:
                continue
        return None

    def detect_contradictions(self, claim_data: dict, ocr_data: dict = None) -> dict:
        """
        Executes comprehensive coherence and integrity checks:
        1. Fault date after claim submission date
        2. Claim submission date before purchase date
        3. Fault occurrence date before purchase date
        4. Serial number mismatch between user entry and OCR extracted receipt
        5. Inconsistent product model declarations
        """
        contradictions = []
        warnings = []

        purchase_date = self.parse_date(claim_data.get("purchase_date"))
        fault_date = self.parse_date(claim_data.get("fault_occurrence_date"))
        submission_date = self.parse_date(claim_data.get("claim_submission_date")) or date.today()

        # -------------------------------------------------------------
        # 1. Chronological Checks
        # -------------------------------------------------------------
        if purchase_date and submission_date:
            if submission_date < purchase_date:
                contradictions.append(
                    f"Chronological Contradiction: Claim submission date ({submission_date}) "
                    f"predates product purchase date ({purchase_date})."
                )

        if purchase_date and fault_date:
            if fault_date < purchase_date:
                contradictions.append(
                    f"Chronological Contradiction: Reported fault occurrence ({fault_date}) "
                    f"is prior to retail purchase date ({purchase_date})."
                )

        if fault_date and submission_date:
            if fault_date > submission_date:
                contradictions.append(
                    f"Chronological Contradiction: Reported fault occurrence date ({fault_date}) "
                    f"is in the future relative to submission date ({submission_date})."
                )

        # -------------------------------------------------------------
        # 2. Serial Number Cross-Verification
        # -------------------------------------------------------------
        registered_serial = str(claim_data.get("product_serial", "")).strip().upper()
        if ocr_data:
            extracted_serial = str(ocr_data.get("serial_number", "")).strip().upper()
            if extracted_serial and extracted_serial not in ["SN-UNKNOWN", "N/A", ""]:
                if registered_serial != extracted_serial:
                    contradictions.append(
                        f"Serial Number Mismatch: Entered registration serial '{registered_serial}' "
                        f"does not match OCR extracted receipt serial '{extracted_serial}'."
                    )

        if claim_data.get("serial_number_match", 1) == 0:
            if not any("Serial Number Mismatch" in c for c in contradictions):
                contradictions.append(
                    "Serial Number Discrepancy: Hardware backplate serial differs from registered warranty documentation."
                )

        # -------------------------------------------------------------
        # 3. Model Consistency Check
        # -------------------------------------------------------------
        model_name = str(claim_data.get("product_model", "")).strip()
        if ocr_data and ocr_data.get("model_name"):
            ocr_model = str(ocr_data.get("model_name", "")).strip()
            if ocr_model and ocr_model.lower() not in model_name.lower() and model_name.lower() not in ocr_model.lower():
                warnings.append(
                    f"Potential Model Variance: Claim model '{model_name}' differs from invoice model '{ocr_model}'."
                )

        has_contradictions = len(contradictions) > 0

        return {
            "has_contradiction": has_contradictions,
            "contradiction_count": len(contradictions),
            "contradictions": contradictions,
            "warnings": warnings,
            "severity": "CRITICAL" if has_contradictions else ("WARNING" if warnings else "CLEAN")
        }


# Singleton contradiction detector
_contradiction_detector_instance = None

def get_contradiction_detector() -> ContradictionDetector:
    global _contradiction_detector_instance
    if _contradiction_detector_instance is None:
        _contradiction_detector_instance = ContradictionDetector()
    return _contradiction_detector_instance
