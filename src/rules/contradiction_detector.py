from datetime import datetime, date


class ContradictionDetector:
    """Detects chronological, serial-number, and model-level inconsistencies."""

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
        Executes comprehensive coherence, serial verification, and contradiction checks:
        1. Claim submission date before purchase date
        2. Repair date before purchase date
        3. Fault occurrence date after claim submission date
        4. Fault occurrence date before purchase date
        5. Inconsistent product model declarations
        6. Serial number comparison across receipt, warranty card, product image, and repair records
        """
        import json
        contradictions = []
        warnings = []

        purchase_date = self.parse_date(claim_data.get("purchase_date"))
        fault_date = self.parse_date(claim_data.get("fault_occurrence_date"))
        submission_date = self.parse_date(claim_data.get("claim_submission_date")) or date.today()

        # -------------------------------------------------------------
        # 1. Chronological Checks
        # -------------------------------------------------------------
        # 1.a Claim date before purchase date
        if purchase_date and submission_date:
            if submission_date < purchase_date:
                contradictions.append(
                    f"Chronological Contradiction: Claim submission date ({submission_date}) "
                    f"predates product purchase date ({purchase_date})."
                )

        # 1.b Fault date before purchase date
        if purchase_date and fault_date:
            if fault_date < purchase_date:
                contradictions.append(
                    f"Chronological Contradiction: Reported fault occurrence ({fault_date}) "
                    f"predates / is prior to retail purchase date ({purchase_date})."
                )

        # 1.c Fault date after claim submission date
        if fault_date and submission_date:
            if fault_date > submission_date:
                contradictions.append(
                    f"Chronological Contradiction: Reported fault occurrence date ({fault_date}) "
                    f"is in the future relative to submission date ({submission_date})."
                )

        # 1.d Repair date before purchase date
        repairs_list = claim_data.get("repair_records") or claim_data.get("repairs") or []
        for rep in repairs_list:
            rep_date_val = rep.get("repair_date") if isinstance(rep, dict) else getattr(rep, "repair_date", None)
            rep_date = self.parse_date(rep_date_val)
            if rep_date and purchase_date and rep_date < purchase_date:
                contradictions.append(
                    f"Chronological Contradiction: Prior repair date ({rep_date}) "
                    f"predates product purchase date ({purchase_date})."
                )

        for r_d_val in claim_data.get("repair_dates", []):
            r_d = self.parse_date(r_d_val)
            if r_d and purchase_date and r_d < purchase_date:
                contradictions.append(
                    f"Chronological Contradiction: Prior repair date ({r_d}) "
                    f"predates product purchase date ({purchase_date})."
                )

        # -------------------------------------------------------------
        # 2. Comprehensive Serial-Number Verification
        # Compares user/registered serial with:
        # - receipt,
        # - warranty card,
        # - product image / serial photo,
        # - repair records
        # -------------------------------------------------------------
        registered_serial = str(claim_data.get("product_serial") or claim_data.get("serial_number") or "").strip().upper()
        doc_serials = {}

        # 2.a Direct keys in claim payload
        if claim_data.get("receipt_serial"):
            doc_serials["Receipt"] = str(claim_data["receipt_serial"]).strip().upper()
        if claim_data.get("warranty_card_serial"):
            doc_serials["Warranty Card"] = str(claim_data["warranty_card_serial"]).strip().upper()
        if claim_data.get("product_image_serial") or claim_data.get("serial_photo_serial"):
            doc_serials["Product Image"] = str(claim_data.get("product_image_serial") or claim_data.get("serial_photo_serial")).strip().upper()
        if claim_data.get("repair_record_serial"):
            doc_serials["Repair Record"] = str(claim_data["repair_record_serial"]).strip().upper()

        # 2.b Extract from attached claim documents
        docs = claim_data.get("documents") or []
        for doc in docs:
            dtype = getattr(doc, "document_type", None) or (doc.get("document_type") if isinstance(doc, dict) else "")
            ocr_json = getattr(doc, "ocr_data_json", None) or (doc.get("ocr_data_json") if isinstance(doc, dict) else None)
            doc_entities = {}
            if ocr_json:
                try:
                    doc_entities = json.loads(ocr_json) if isinstance(ocr_json, str) else ocr_json
                except Exception:
                    pass
            sn = doc_entities.get("serial_number")
            if sn and str(sn).strip().upper() not in ["SN-UNKNOWN", "N/A", "UNKNOWN", "NONE", ""]:
                clean_sn = str(sn).strip().upper()
                if dtype in ["receipt", "invoice", "invoice_document"]:
                    doc_serials.setdefault("Receipt", clean_sn)
                elif dtype == "warranty_card":
                    doc_serials.setdefault("Warranty Card", clean_sn)
                elif dtype in ["serial_photo", "product_photo", "product_image", "damage_photo"]:
                    doc_serials.setdefault("Product Image", clean_sn)
                elif dtype in ["repair_report", "repair_record"]:
                    doc_serials.setdefault("Repair Record", clean_sn)

        # 2.c Extract from ocr_data argument if passed
        if ocr_data:
            extracted_receipt_sn = ocr_data.get("serial_number") or ocr_data.get("entities", {}).get("serial_number")
            if extracted_receipt_sn and str(extracted_receipt_sn).strip().upper() not in ["SN-UNKNOWN", "N/A", "UNKNOWN", ""]:
                doc_serials.setdefault("Receipt", str(extracted_receipt_sn).strip().upper())

        # 2.d Extract from repair history records
        for rep in repairs_list:
            rep_sn = rep.get("serial_number") if isinstance(rep, dict) else getattr(rep, "serial_number", None)
            if rep_sn and str(rep_sn).strip().upper() not in ["SN-UNKNOWN", "N/A", "UNKNOWN", ""]:
                doc_serials.setdefault("Repair Record", str(rep_sn).strip().upper())

        # Perform cross-checks across all sources
        for source_name, doc_sn in doc_serials.items():
            if registered_serial and doc_sn and registered_serial != doc_sn:
                mismatch_msg = (
                    f"Serial Number Mismatch: Entered registration serial '{registered_serial}' "
                    f"does not match {source_name} serial '{doc_sn}'."
                )
                if mismatch_msg not in contradictions:
                    contradictions.append(mismatch_msg)
                warnings.append(f"Serial number mismatch against {source_name} documentation.")

        if claim_data.get("serial_number_match", 1) == 0:
            if not any("Serial Number Mismatch" in c for c in contradictions):
                contradictions.append(
                    "Serial Number Discrepancy: Hardware backplate serial differs from registered warranty documentation."
                )
                warnings.append("Serial number discrepancy flagged in claim dossier.")

        # -------------------------------------------------------------
        # 3. Model Consistency Check
        # -------------------------------------------------------------
        model_name = str(claim_data.get("product_model") or claim_data.get("model_number") or "").strip()
        ocr_models_to_check = []
        if ocr_data:
            raw_ocr_model = ocr_data.get("model_name") or ocr_data.get("model_number") or ocr_data.get("entities", {}).get("model_name")
            if raw_ocr_model and str(raw_ocr_model).strip().lower() not in ["none", "null", ""]:
                ocr_models_to_check.append(str(raw_ocr_model).strip())

        if claim_data.get("invoice_model"):
            ocr_models_to_check.append(str(claim_data["invoice_model"]).strip())
        if claim_data.get("extracted_model"):
            ocr_models_to_check.append(str(claim_data["extracted_model"]).strip())

        for ocr_model in ocr_models_to_check:
            if model_name and ocr_model.lower() not in model_name.lower() and model_name.lower() not in ocr_model.lower():
                contra_model_msg = (
                    f"Product Model Contradiction: Claimed model '{model_name}' differs from invoice model '{ocr_model}'."
                )
                if contra_model_msg not in contradictions:
                    contradictions.append(contra_model_msg)

        has_contradictions = len(contradictions) > 0

        return {
            "has_contradiction": has_contradictions,
            "contradiction_count": len(contradictions),
            "contradictions": contradictions,
            "warnings": warnings,
            "serial_verifications": doc_serials,
            "severity": "CRITICAL" if has_contradictions else ("WARNING" if warnings else "CLEAN")
        }


# Singleton contradiction detector
_contradiction_detector_instance = None

def get_contradiction_detector() -> ContradictionDetector:
    global _contradiction_detector_instance
    if _contradiction_detector_instance is None:
        _contradiction_detector_instance = ContradictionDetector()
    return _contradiction_detector_instance
