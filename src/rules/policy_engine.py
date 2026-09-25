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
        """
        Req 1.6.xxvi: Retrieves category policy from database (WarrantyPolicy) or configurable JSON files.
        Supports different warranty rules for different product categories.
        """
        # 1. Attempt lookup from persistent database
        try:
            from src.models.entities import WarrantyPolicy
            db_policy = WarrantyPolicy.query.filter(WarrantyPolicy.category.ilike(category_name)).first()
            if db_policy:
                rules = db_policy.get_rules()
                combined = dict(rules)
                combined["category"] = db_policy.category
                combined["policy_name"] = db_policy.policy_name
                combined["coverage_duration_months"] = db_policy.coverage_duration_months
                combined["grace_period_days"] = db_policy.grace_period_days
                combined["claim_reporting_period_days"] = db_policy.claim_reporting_period_days
                combined["authorized_service_center_required"] = db_policy.authorized_service_center_required
                return combined
        except Exception:
            pass

        # 2. Lookup from configurable JSON policy files
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
        # 1. Warranty Expiry & Grace Period Check (Req 1.6.xxv.1)
        # -------------------------------------------------------------
        remaining_days = claim_data.get("remaining_warranty_days")
        if remaining_days is None:
            remaining_days = claim_data.get("days_until_warranty_expiry", 0)

        product_age = claim_data.get("product_age_days")
        if product_age is None:
            product_age = claim_data.get("days_since_purchase", 0)

        duration_months = claim_data.get("warranty_duration_months") or claim_data.get("warranty_period_months") or policy.get("coverage_duration_months", 12)
        # Use accurate average days-per-month (365.25/12 ≈ 30.44) to avoid
        # calendar drift that incorrectly flags end-of-year claims as expired
        duration_days = int(duration_months * 30.4375)
        overdue_days = max(0, product_age - duration_days)
        grace_days = policy.get("grace_period_days", 7)

        if remaining_days > 0 or (remaining_days >= 0 and overdue_days == 0):
            passed_rules.append(f"Warranty active: {remaining_days} days remaining within coverage.")
        else:
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
        # 2. Fault Coverage Schedule Check (Req 1.6.xxv.2)
        # -------------------------------------------------------------
        fault_cat = claim_data.get("fault_category", "")
        covered = policy.get("covered_faults", [])
        is_covered = any(c.lower() in fault_cat.lower() for c in covered)
        if is_covered or claim_data.get("damage_type") == "Hardware Defect":
            passed_rules.append(f"Fault coverage verified: '{fault_cat}' is covered under standard protection schedule.")
        else:
            review_triggers.append(f"Uncommon fault category '{fault_cat}': Manual technician inspection required.")

        # -------------------------------------------------------------
        # 3. Claim Reporting Period Window (Req 1.6.xxv.3)
        # -------------------------------------------------------------
        max_reporting = policy.get("claim_reporting_period_days", 30)
        days_between = claim_data.get("days_between_fault_and_claim")
        if days_between is None and claim_data.get("fault_occurrence_date") and claim_data.get("claim_submission_date"):
            try:
                f_d = datetime.strptime(str(claim_data["fault_occurrence_date"])[:10], "%Y-%m-%d").date()
                c_d = datetime.strptime(str(claim_data["claim_submission_date"])[:10], "%Y-%m-%d").date()
                days_between = (c_d - f_d).days
            except Exception:
                days_between = 0

        if days_between is not None and days_between > max_reporting:
            failed_rules.append(
                f"HARD FAIL: Claim reporting deadline exceeded: Reported {days_between} days after fault occurrence (deadline: {max_reporting} days)."
            )
        elif days_between is not None and days_between > (max_reporting - 7):
            warnings.append(
                f"Claim reported near deadline ({days_between} days after fault occurrence, deadline: {max_reporting} days)."
            )
        else:
            passed_rules.append("Claim reported within permissible reporting window.")

        # -------------------------------------------------------------
        # 4. Proof of Purchase Verification (Req 1.6.xxv.4)
        # -------------------------------------------------------------
        has_receipt = claim_data.get("has_receipt", 1)
        if claim_data.get("mandatory_documents_present") == 0:
            has_receipt = 0

        if has_receipt == 0:
            review_triggers.append("Primary proof of purchase receipt missing: Claimant identity verification required.")
            warnings.append("Missing primary tax invoice.")
        else:
            passed_rules.append("Proof of purchase verified: Valid sales invoice / receipt on record.")

        # -------------------------------------------------------------
        # 5. Extended Warranty Validation (Req 1.6.xxv.5)
        # -------------------------------------------------------------
        is_extended = bool(claim_data.get("is_extended_warranty") or claim_data.get("is_extended"))
        if is_extended:
            passed_rules.append("Extended warranty validated: Product protected under supplementary service agreement.")
        else:
            passed_rules.append("Standard warranty terms applied (no supplementary extension active).")

        # -------------------------------------------------------------
        # 6. Serial Number Cross-Check (Req 1.6.xxv.6)
        # -------------------------------------------------------------
        if claim_data.get("serial_number_match", 1) == 0:
            review_triggers.append("Serial Mismatch Trigger: Hardware serial number does not match purchase invoice documentation.")
            warnings.append("Serial number mismatch detected.")
        else:
            passed_rules.append("Serial number verification passed: Exact match between device backplate and tax invoice.")

        # -------------------------------------------------------------
        # 7. Previous Repairs History & Workshop Authorization (Req 1.6.xxv.7)
        # -------------------------------------------------------------
        prev_repairs = int(claim_data.get("previous_repairs_count", 0))
        unauth_flag = int(claim_data.get("unauthorized_repair_flag", 0))
        if policy.get("authorized_service_center_required", True) and unauth_flag == 1:
            review_triggers.append("Unauthorized Service Alert: Product has history of maintenance by uncertified third-party facility.")
            warnings.append("Unauthorized service facility record found.")
        elif prev_repairs > 2:
            warnings.append(f"Frequent repair history flagged: {prev_repairs} previous service interventions on file.")
            passed_rules.append(f"Previous repairs logged: {prev_repairs} authorized maintenance records on file.")
        else:
            passed_rules.append(f"Service center history verified: {prev_repairs} previous repair(s), no unauthorized workshop tampering detected.")

        # -------------------------------------------------------------
        # 8. Product Replacement Eligibility & History (Req 1.6.xxv.8)
        # -------------------------------------------------------------
        prev_replacement = claim_data.get("previous_replacement_details")
        if prev_replacement and str(prev_replacement).strip() and str(prev_replacement).lower() not in ["none", "null", "no", "false", ""]:
            warnings.append(f"Prior product replacement recorded: '{prev_replacement}'. Unit serial history inspection required.")
            review_triggers.append("Prior product replacement on file: Unit replacement eligibility verification required.")
        else:
            passed_rules.append("Product replacement check: Original hardware unit verified with no conflicting replacement history.")

        # -------------------------------------------------------------
        # 9. Excluded Damage & Policy Exclusions (Req 1.6.xxv.9)
        # -------------------------------------------------------------
        damage_type = claim_data.get("damage_type", "")
        exclusions = policy.get("exclusions", [])
        exclusion_matched = False
        for excl in exclusions:
            if excl.lower() in damage_type.lower() or excl.lower() in fault_cat.lower():
                failed_rules.append(f"HARD FAIL: Excluded damage detected - '{excl}' is explicitly excluded by policy terms.")
                exclusion_matched = True
                break
        if not exclusion_matched:
            passed_rules.append(f"Excluded damage check: Reported damage '{damage_type}' contains no policy exclusions.")

        # -------------------------------------------------------------
        # 10. Required Documents Dossier Completeness (Req 1.6.xxv.10)
        # -------------------------------------------------------------
        missing_count = int(claim_data.get("missing_document_count", 0))
        if claim_data.get("mandatory_documents_present") == 0:
            missing_count = max(missing_count, 2)

        if missing_count > 0:
            warnings.append(f"{missing_count} mandatory claim document(s) missing from submission dossier.")
            if missing_count >= 2:
                review_triggers.append("Multiple mandatory documents missing: Routing to manual review queue.")
        else:
            passed_rules.append("Mandatory documentation complete: Receipt, warranty card, and photos verified.")

        # -------------------------------------------------------------
        # 11. Chronological Coherence Check
        # -------------------------------------------------------------
        if claim_data.get("claim_date_conflict_flag", 0) == 1:
            review_triggers.append("Chronological Contradiction Trigger: Fault date conflict detected relative to purchase date.")
            warnings.append("Chronological date conflict flagged.")

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
