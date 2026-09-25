import json
from collections import Counter
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from sqlalchemy import func
from config.config import Config
from database.db import db
from src.models.entities import (
    Claim, Product, ProductWarranty, ModelEvaluation,
    RepairHistory, RuleValidationLog, User
)


class AnalyticsService:
    """
    Req xliii: Enterprise Analytics and Reporting Engine.
    Generates structured analytics across 8 core dimensions:
    1. Claim outcomes
    2. Frequently reported faults
    3. Rejected claim reasons
    4. Product categories
    5. Warranty expirations
    6. Repair patterns
    7. Model performance
    8. Manual-review frequency & triggers
    """

    @staticmethod
    def get_claim_outcomes() -> dict:
        """Dimension 1: Claim outcomes distribution and percentages."""
        total = Claim.query.count()
        if total == 0:
            return {
                "total": 0,
                "counts": {},
                "percentages": {},
                "chart_labels": [],
                "chart_data": []
            }

        counts = {}
        for status in Config.ALL_CLAIM_STATUSES:
            cnt = Claim.query.filter(Claim.status == status).count()
            if cnt > 0:
                counts[status] = cnt

        # Also account for any other status present
        all_claims = Claim.query.all()
        for c in all_claims:
            if c.status not in counts:
                counts[c.status] = counts.get(c.status, 0) + 1

        percentages = {k: round((v / total) * 100, 2) for k, v in counts.items()}
        labels = list(counts.keys())
        data = [counts[k] for k in labels]

        return {
            "total": total,
            "counts": counts,
            "percentages": percentages,
            "chart_labels": labels,
            "chart_data": data,
            "approved_count": counts.get(Config.STATUS_APPROVED, 0),
            "rejected_count": counts.get(Config.STATUS_REJECTED, 0),
            "manual_review_count": counts.get(Config.STATUS_MANUAL_REVIEW, 0),
            "pending_count": (
                counts.get(Config.STATUS_SUBMITTED, 0) +
                counts.get(Config.STATUS_UNDER_EVALUATION, 0)
            )
        }

    @staticmethod
    def get_frequently_reported_faults(limit: int = 10) -> dict:
        """Dimension 2: Frequently reported fault categories and common descriptions."""
        claims = Claim.query.all()
        if not claims:
            return {
                "total_faults": 0,
                "categories": {},
                "top_descriptions": [],
                "chart_labels": [],
                "chart_data": []
            }

        cat_counter = Counter(c.fault_category for c in claims if c.fault_category)
        top_cats = dict(cat_counter.most_common(limit))

        # Fault descriptions / symptoms frequency
        desc_counter = Counter(c.fault_description.strip() for c in claims if c.fault_description)
        top_descs = [
            {"description": desc, "count": count, "category": next((c.fault_category for c in claims if c.fault_description == desc), "General")}
            for desc, count in desc_counter.most_common(limit)
        ]

        return {
            "total_faults": len(claims),
            "categories": top_cats,
            "top_descriptions": top_descs,
            "chart_labels": list(top_cats.keys()),
            "chart_data": list(top_cats.values())
        }

    @staticmethod
    def get_rejected_claim_reasons() -> dict:
        """Dimension 3: Rejected claim reasons and policy failure categorizations."""
        rejected_claims = Claim.query.filter(Claim.status == Config.STATUS_REJECTED).all()
        total_rejected = len(rejected_claims)

        if total_rejected == 0:
            return {
                "total_rejected": 0,
                "reasons": {},
                "percentages": {},
                "chart_labels": [],
                "chart_data": []
            }

        reason_counts = {
            "Warranty Expired": 0,
            "Physical / Liquid / Accidental Damage": 0,
            "Unauthorized Service Center Repair": 0,
            "Claim Reporting Deadline Exceeded": 0,
            "Missing Purchase Receipt / Invoice": 0,
            "Serial Number Mismatch": 0,
            "Duplicate Claim Detected": 0,
            "Policy Exclusion / Other": 0
        }

        for claim in rejected_claims:
            reason_text = (claim.decision_reason or "").lower()
            validation_log = claim.rule_validation

            matched = False
            if "expired" in reason_text or (validation_log and "RULE_WARRANTY_EXPIRY" in validation_log.rules_failed_json):
                reason_counts["Warranty Expired"] += 1
                matched = True
            elif "damage" in reason_text or (validation_log and "RULE_FAULT_COVERAGE" in validation_log.rules_failed_json):
                reason_counts["Physical / Liquid / Accidental Damage"] += 1
                matched = True
            elif "unauthorized" in reason_text or (validation_log and "RULE_UNAUTHORIZED_REPAIR" in validation_log.rules_failed_json):
                reason_counts["Unauthorized Service Center Repair"] += 1
                matched = True
            elif "deadline" in reason_text or "reporting period" in reason_text or (validation_log and "RULE_REPORTING_PERIOD" in validation_log.rules_failed_json):
                reason_counts["Claim Reporting Deadline Exceeded"] += 1
                matched = True
            elif "receipt" in reason_text or "proof of purchase" in reason_text or (validation_log and "RULE_PROOF_OF_PURCHASE" in validation_log.rules_failed_json):
                reason_counts["Missing Purchase Receipt / Invoice"] += 1
                matched = True
            elif "serial" in reason_text or (validation_log and "RULE_SERIAL_NUMBER_MATCH" in validation_log.rules_failed_json):
                reason_counts["Serial Number Mismatch"] += 1
                matched = True
            elif claim.is_duplicate_flag or (validation_log and "duplicate" in validation_log.duplicate_flags_json.lower()):
                reason_counts["Duplicate Claim Detected"] += 1
                matched = True

            if not matched:
                reason_counts["Policy Exclusion / Other"] += 1

        # Remove zero entries for chart cleanliness
        filtered_reasons = {k: v for k, v in reason_counts.items() if v > 0}
        if not filtered_reasons:
            filtered_reasons = {"Policy Exclusion / General": total_rejected}

        percentages = {k: round((v / total_rejected) * 100, 2) for k, v in filtered_reasons.items()}

        return {
            "total_rejected": total_rejected,
            "reasons": filtered_reasons,
            "percentages": percentages,
            "chart_labels": list(filtered_reasons.keys()),
            "chart_data": list(filtered_reasons.values())
        }

    @staticmethod
    def get_product_categories_analytics() -> dict:
        """Dimension 4: Claims distribution, volume, and approval rates by product category."""
        products = Product.query.all()
        claims = Claim.query.all()

        categories = sorted(list({p.category for p in products} | {c.product.category for c in claims if c.product}))
        if not categories:
            categories = ["Consumer Electronics", "Home Appliances", "Industrial Tools"]

        cat_data = {}
        for cat in categories:
            prods = [p for p in products if p.category == cat]
            cat_claims = [c for c in claims if c.product and c.product.category == cat]

            total_cat_claims = len(cat_claims)
            approved = sum(1 for c in cat_claims if c.status == Config.STATUS_APPROVED)
            rejected = sum(1 for c in cat_claims if c.status == Config.STATUS_REJECTED)
            manual = sum(1 for c in cat_claims if c.status == Config.STATUS_MANUAL_REVIEW)

            claim_rate = round((total_cat_claims / len(prods) * 100), 2) if prods else 0.0

            cat_data[cat] = {
                "product_count": len(prods),
                "claim_count": total_cat_claims,
                "claim_rate": claim_rate,
                "approved_count": approved,
                "rejected_count": rejected,
                "manual_count": manual
            }

        chart_labels = list(cat_data.keys())
        chart_claims = [cat_data[k]["claim_count"] for k in chart_labels]
        chart_products = [cat_data[k]["product_count"] for k in chart_labels]

        return {
            "categories": cat_data,
            "chart_labels": chart_labels,
            "chart_claims": chart_claims,
            "chart_products": chart_products
        }

    @staticmethod
    def get_warranty_expirations_analytics() -> dict:
        """Dimension 5: Warranty expiration timeline, active vs expiring vs expired."""
        warranties = ProductWarranty.query.all()
        today = date.today()

        total = len(warranties)
        if total == 0:
            return {
                "total": 0,
                "active_count": 0,
                "approaching_30d_count": 0,
                "approaching_60d_count": 0,
                "expired_count": 0,
                "monthly_expirations": {},
                "chart_labels": ["Active (>60d)", "Expiring (31-60d)", "Expiring (≤30d)", "Expired"],
                "chart_data": [0, 0, 0, 0]
            }

        active = 0
        approaching_30 = 0
        approaching_60 = 0
        expired = 0

        monthly_exp = {}

        for w in warranties:
            if not w.is_active(today):
                expired += 1
            else:
                rem = w.remaining_days(today)
                if rem <= 30:
                    approaching_30 += 1
                elif rem <= 60:
                    approaching_60 += 1
                else:
                    active += 1

            if w.expiry_date:
                month_str = w.expiry_date.strftime("%b %Y")
                monthly_exp[month_str] = monthly_exp.get(month_str, 0) + 1

        chart_labels = ["Active (>60d)", "Expiring (31-60d)", "Expiring (≤30d)", "Expired"]
        chart_data = [active, approaching_60, approaching_30, expired]

        return {
            "total": total,
            "active_count": active,
            "approaching_30d_count": approaching_30,
            "approaching_60d_count": approaching_60,
            "expired_count": expired,
            "monthly_expirations": monthly_exp,
            "chart_labels": chart_labels,
            "chart_data": chart_data
        }

    @staticmethod
    def get_repair_patterns_analytics() -> dict:
        """Dimension 6: Repair patterns, workshop authorization, parts replaced, and costs."""
        repairs = RepairHistory.query.all()
        total_repairs = len(repairs)

        if total_repairs == 0:
            return {
                "total_repairs": 0,
                "authorized_count": 0,
                "unauthorized_count": 0,
                "authorized_rate": 0.0,
                "outcomes": {},
                "top_parts": [],
                "avg_cost": 0.0,
                "total_cost": 0.0,
                "chart_labels": ["Authorized Center", "Unauthorized Center"],
                "chart_data": [0, 0]
            }

        auth_count = sum(1 for r in repairs if r.is_authorized_center)
        unauth_count = total_repairs - auth_count
        auth_rate = round((auth_count / total_repairs) * 100, 2)

        outcomes = Counter(r.outcome for r in repairs if r.outcome)
        parts_list = []
        for r in repairs:
            if r.replaced_parts:
                for part in r.replaced_parts.split(","):
                    p_clean = part.strip()
                    if p_clean:
                        parts_list.append(p_clean)

        parts_counter = Counter(parts_list)
        top_parts = [{"part": p, "count": c} for p, c in parts_counter.most_common(8)]

        total_cost = sum(r.repair_cost for r in repairs if r.repair_cost)
        avg_cost = round(total_cost / total_repairs, 2)

        return {
            "total_repairs": total_repairs,
            "authorized_count": auth_count,
            "unauthorized_count": unauth_count,
            "authorized_rate": auth_rate,
            "outcomes": dict(outcomes),
            "top_parts": top_parts,
            "avg_cost": avg_cost,
            "total_cost": round(total_cost, 2),
            "chart_labels": ["Authorized Service", "Unauthorized Service"],
            "chart_data": [auth_count, unauth_count]
        }

    @staticmethod
    def get_model_performance_analytics() -> dict:
        """Dimension 7: Dual-model consensus, accuracy benchmarks, and consistency stats."""
        evals = ModelEvaluation.query.all()
        total_evals = len(evals)

        if total_evals == 0:
            agreement_count = 0
            disagreement_count = 0
            agreement_rate = 0.0
            disagreement_rate = 0.0
            avg_conf_diff = 0.0
            avg_python_conf = 0.0
            avg_gtm_conf = 0.0
            status_dist = {}
        else:
            agreement_count = sum(1 for e in evals if e.is_class_match)
            disagreement_count = total_evals - agreement_count
            agreement_rate = round((agreement_count / total_evals) * 100, 2)
            disagreement_rate = round((disagreement_count / total_evals) * 100, 2)

            avg_conf_diff = round(sum(e.top_confidence_difference for e in evals) / total_evals, 4)

            python_confs = [max(e.python_conf_valid, e.python_conf_invalid, e.python_conf_manual) for e in evals]
            gtm_confs = [max(e.gtm_conf_valid, e.gtm_conf_invalid, e.gtm_conf_manual) for e in evals]

            avg_python_conf = round(sum(python_confs) / len(python_confs), 4)
            avg_gtm_conf = round(sum(gtm_confs) / len(gtm_confs), 4)

            status_counter = Counter(e.model_consistency_status for e in evals)
            status_dist = dict(status_counter)

        # Ensure all 5 standard consistency statuses are represented
        consistency_breakdown = {
            s: status_dist.get(s, 0) for s in Config.ALL_CONSISTENCY_STATUSES
        }

        # Load benchmark telemetry if present
        benchmark_path = Path(Config.BASE_DIR) / "model" / "python_model" / "benchmark_results.json"
        benchmark_data = {}
        if benchmark_path.exists():
            try:
                benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        return {
            "total_evaluations": total_evals,
            "agreement_count": agreement_count,
            "disagreement_count": disagreement_count,
            "agreement_rate": agreement_rate,
            "disagreement_rate": disagreement_rate,
            "avg_conf_diff": avg_conf_diff,
            "avg_python_conf": avg_python_conf,
            "avg_gtm_conf": avg_gtm_conf,
            "consistency_breakdown": consistency_breakdown,
            "benchmark_data": benchmark_data,
            "chart_labels": list(consistency_breakdown.keys()),
            "chart_data": list(consistency_breakdown.values())
        }

    @staticmethod
    def get_manual_review_frequency_analytics() -> dict:
        """Dimension 8: Manual-review triage incidence rate and routing trigger breakdown."""
        total_claims = Claim.query.count()
        manual_claims = Claim.query.filter(Claim.status == Config.STATUS_MANUAL_REVIEW).all()
        manual_count = len(manual_claims)

        incidence_rate = round((manual_count / total_claims * 100), 2) if total_claims > 0 else 0.0

        # Triage Triggers Breakdown
        triggers = {
            "Model Disagreement": 0,
            "Low Confidence Score": 0,
            "Missing Documents Flag": 0,
            "Duplicate Claim Flag": 0,
            "Contradiction Detected": 0,
            "Reviewer Re-Evaluation": 0
        }

        for c in manual_claims:
            e = c.model_evaluation
            counted = False
            if e and not e.is_class_match:
                triggers["Model Disagreement"] += 1
                counted = True
            if e and e.top_confidence_difference > Config.ACCEPTABLE_MATCH_DIFF:
                triggers["Low Confidence Score"] += 1
                counted = True
            if c.missing_document_flag:
                triggers["Missing Documents Flag"] += 1
                counted = True
            if c.is_duplicate_flag:
                triggers["Duplicate Claim Flag"] += 1
                counted = True
            if c.contradiction_flag:
                triggers["Contradiction Detected"] += 1
                counted = True

            if not counted:
                triggers["Reviewer Re-Evaluation"] += 1

        chart_labels = list(triggers.keys())
        chart_data = list(triggers.values())

        return {
            "total_claims": total_claims,
            "manual_review_count": manual_count,
            "incidence_rate": incidence_rate,
            "triggers": triggers,
            "chart_labels": chart_labels,
            "chart_data": chart_data
        }

    @classmethod
    def get_comprehensive_analytics(cls) -> dict:
        """Assembles all 8 reporting dimensions into an integrated executive payload."""
        outcomes = cls.get_claim_outcomes()
        faults = cls.get_frequently_reported_faults()
        rejections = cls.get_rejected_claim_reasons()
        categories = cls.get_product_categories_analytics()
        expirations = cls.get_warranty_expirations_analytics()
        repairs = cls.get_repair_patterns_analytics()
        models = cls.get_model_performance_analytics()
        manual_review = cls.get_manual_review_frequency_analytics()

        return {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "outcomes": outcomes,
            "faults": faults,
            "rejections": rejections,
            "categories": categories,
            "expirations": expirations,
            "repairs": repairs,
            "models": models,
            "manual_review": manual_review
        }
