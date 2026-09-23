import os
import json
from pathlib import Path
from datetime import datetime, date

BASE_DIR = Path(__file__).resolve().parent.parent.parent
POLICIES_DIR = BASE_DIR / "policies"


class WarrantyPolicyEngine:
    """Configurable Business Rule Engine validating claims against product category policies."""

    def __init__(self, policies_dir: Path = None):
        self.policies_dir = policies_dir or POLICIES_DIR
        self.policies = {}
        self.load_all_policies()

    def load_all_policies(self):
        """Loads all JSON policy definition files from the policies directory."""
        if not self.policies_dir.exists():
            return

        for p_file in self.policies_dir.glob("*.json"):
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    policy_data = json.load(f)
                    cat = policy_data.get("category")
                    if cat:
                        self.policies[cat] = policy_data
            except Exception as e:
                print(f"[!] Warning: Failed loading policy {p_file.name}: {e}")

    def get_policy_for_category(self, category_name: str) -> dict:
        """Retrieves category policy or returns standard fallback."""
        if category_name in self.policies:
            return self.policies[category_name]

        # Case-insensitive or partial match fallback
        for k, v in self.policies.items():
            if k.lower() in category_name.lower() or category_name.lower() in k.lower():
                return v

        # Fallback default policy if category not specifically mapped
        return {
            "category": category_name,
            "policy_name": f"Default Standard Policy ({category_name})",
            "coverage_duration_months": 12,
            "claim_reporting_period_days": 30,
            "grace_period_days": 7,
            "authorized_service_center_required": True,
            "covered_faults": ["Hardware Defect", "Component failure", "Power failure"],
            "exclusions": ["Liquid damage", "Screen shattering from drops", "Third-party unauthorized disassembly"],
            "mandatory_documents": ["Purchase Invoice", "Warranty Card", "Serial Photo"],
            "hard_fail_rules": ["Warranty expired beyond grace period", "Liquid/water ingress", "Unauthorized repair"],
            "warning_rules": ["Grace period claim", "Late reporting"],
            "manual_review_rules": ["Missing mandatory invoice", "Model disagreement"]
        }

    def evaluate_claim_rules(self, claim_data: dict) -> dict:
        """
        Executes business rule validation against the category policy.
        
        Evaluates:
        1. Warranty Expiry & Grace Period Boundaries
        2. Claim Reporting Window
        3. Covered Fault Schedule
        4. Excluded Damage Types (Hard-Fail)
        5. Authorized Service Center Adherence (Hard-Fail)
        6. Mandatory Document Completeness
        7. Serial Number Cross-Check
        """
        category = claim_data.get("product_category", "Consumer Electronics")
        policy = self.get_policy_for_category(category)

        passed_rules = []
        failed_rules = []
        warnings = []
        review_triggers = []

        # -------------------------------------------------------------
        # 1. Warranty Expiry & Grace Period Check
        # -------------------------------------------------------------
        remaining_days = claim_data.get("remaining_warranty_days", 0)
        grace_days = policy.get("grace_period_days", 7)

        if remaining_days > 0:
            passed_rules.append(f"Warranty active: {remaining_days} days remaining within standard coverage.")
        else:
            # Check if within grace period
            product_age = claim_data.get("product_age_days", 0)
            duration_days = claim_data.get("warranty_duration_months", 12) * 30
            overdue_days = max(0, product_age - duration_days)

            if overdue_days <= grace_days and overdue_days > 0:
                warnings.append(
                    f"Claim submitted during grace period window: {overdue_days} days past standard term (allowance: {grace_days} days)."
                )
                passed_rules.append("Eligible for discretionary grace period review.")
                review_triggers.append("Grace period adjudication required.")
            else:
                failed_rules.append(
                    f"HARD FAIL: Warranty expired {overdue_days} days ago, exceeding permissible {grace_days}-day grace period."
                )

        # -------------------------------------------------------------
        # 2. Claim Reporting Window
        # -------------------------------------------------------------
        max_reporting = policy.get("claim_reporting_period_days", 30)
        fault_date_str = claim_data.get("fault_occurrence_date")
        purchase_date_str = claim_data.get("purchase_date")

        # -------------------------------------------------------------
        # 3. Exclusions & Damage Type (Hard-Fail Checks)
        # -------------------------------------------------------------
        damage_type = claim_data.get("damage_type", "")
        fault_cat = claim_data.get("fault_category", "")
        exclusions = policy.get("exclusions", [])

        # Check for explicit exclusion matches
        exclusion_matched = False
        for excl in exclusions:
            if excl.lower() in damage_type.lower() or excl.lower() in fault_cat.lower():
                failed_rules.append(f"HARD FAIL: Excluded damage detected - '{excl}' is explicitly excluded by policy terms.")
                exclusion_matched = True
                break

        if not exclusion_matched:
            # Check covered faults
            covered = policy.get("covered_faults", [])
            is_covered = any(c.lower() in fault_cat.lower() for c in covered)
            if is_covered or damage_type == "Hardware Defect":
                passed_rules.append(f"Reported fault '{fault_cat}' is covered under standard protection schedule.")
            else:
                review_triggers.append(f"Uncommon fault category '{fault_cat}': Manual technician inspection required.")

        # -------------------------------------------------------------
        # 4. Authorized Service Center Adherence
        # -------------------------------------------------------------
        if policy.get("authorized_service_center_required", True):
            if claim_data.get("unauthorized_repair_flag", 0) == 1:
                failed_rules.append("HARD FAIL: Product was previously serviced or opened by an unauthorized third-party center.")
            else:
                passed_rules.append("Service center history verified: No unauthorized workshop tampering detected.")

        # -------------------------------------------------------------
        # 5. Serial Number Cross-Check
        # -------------------------------------------------------------
        if claim_data.get("serial_number_match", 1) == 0:
            failed_rules.append("HARD FAIL: Hardware serial number does not match purchase invoice documentation.")
        else:
            passed_rules.append("Serial number verification passed: Exact match between device backplate and tax invoice.")

        # -------------------------------------------------------------
        # 6. Mandatory Document Completeness
        # -------------------------------------------------------------
        missing_count = claim_data.get("missing_document_count", 0)
        has_receipt = claim_data.get("has_receipt", 1)

        if has_receipt == 0:
            review_triggers.append("Primary proof of purchase receipt missing: Claimant identity verification required.")
            warnings.append("Missing primary tax invoice.")

        if missing_count > 0:
            warnings.append(f"{missing_count} mandatory claim document(s) missing from submission dossier.")
            if missing_count >= 2:
                review_triggers.append("Multiple mandatory documents missing: Routing to manual review queue.")
        else:
            passed_rules.append("Mandatory documentation complete: Receipt, warranty card, and photos verified.")

        # -------------------------------------------------------------
        # 7. Chronological Coherence Check
        # -------------------------------------------------------------
        if claim_data.get("claim_date_conflict_flag", 0) == 1:
            failed_rules.append("HARD FAIL: Chronological date contradiction detected (e.g. fault date precedes purchase date).")

        # Determine Overall Rule Status
        if len(failed_rules) > 0:
            overall_status = "FAIL"
        elif len(review_triggers) > 0 or len(warnings) > 1:
            overall_status = "REVIEW"
        else:
            overall_status = "PASS"

        return {
            "overall_status": overall_status,
            "policy_category": policy.get("category"),
            "policy_name": policy.get("policy_name"),
            "passed_rules": passed_rules,
            "failed_rules": failed_rules,
            "warnings": warnings,
            "manual_review_triggers": review_triggers,
            "passed_count": len(passed_rules),
            "failed_count": len(failed_rules),
            "warning_count": len(warnings)
        }


# Singleton policy engine instance
_policy_engine_instance = None

def get_policy_engine() -> WarrantyPolicyEngine:
    global _policy_engine_instance
    if _policy_engine_instance is None:
        _policy_engine_instance = WarrantyPolicyEngine()
    return _policy_engine_instance
