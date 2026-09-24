import io
import csv
from datetime import datetime


class DataExportService:
    """Exports system records in CSV / tabular formats for reporting and auditing (Req xlv)."""

    @staticmethod
    def export_claims_csv(claims) -> str:
        """Exports claims registry into standardized CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Claim ID", "Claimant Name", "Product Name", "Product Serial",
            "Category", "Submission Date", "Status", "Risk Level",
            "Final Decision", "Decision Reason", "Python Prediction",
            "GTM Prediction", "Confidence Difference", "Consistency Status"
        ]
        writer.writerow(headers)

        for c in claims:
            eval_data = c.model_evaluation
            py_pred = eval_data.python_predicted_class if eval_data else "N/A"
            gtm_pred = eval_data.gtm_predicted_class if eval_data else "N/A"
            conf_diff = eval_data.top_confidence_difference if eval_data else "N/A"
            consistency = eval_data.model_consistency_status if eval_data else "N/A"

            row = [
                c.claim_id,
                c.claimant.full_name if c.claimant else "N/A",
                c.product.product_name if c.product else "N/A",
                c.product.serial_number if c.product else "N/A",
                c.product.category if c.product else "N/A",
                c.claim_submission_date.strftime("%Y-%m-%d") if c.claim_submission_date else "N/A",
                c.status,
                c.risk_level or "Medium",
                c.final_decision or "Pending",
                c.decision_reason or "",
                py_pred,
                gtm_pred,
                conf_diff,
                consistency
            ]
            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def export_products_csv(products) -> str:
        """Exports registered products and warranties to CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Product ID", "Owner", "Product Name", "Category", "Brand",
            "Model", "Serial Number", "Purchase Date", "Price ($)",
            "Retailer", "Warranty Start", "Warranty Expiry", "Active Status"
        ]
        writer.writerow(headers)

        for p in products:
            warr = p.warranty
            row = [
                p.product_id,
                p.owner.full_name if p.owner else "N/A",
                p.product_name,
                p.category,
                p.brand,
                p.model_number,
                p.serial_number,
                p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "N/A",
                f"{p.purchase_price:.2f}",
                p.retailer,
                warr.start_date.strftime("%Y-%m-%d") if warr else "N/A",
                warr.expiry_date.strftime("%Y-%m-%d") if warr else "N/A",
                "Active" if warr and warr.is_active() else "Expired"
            ]
            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def export_audit_logs_csv(audit_logs) -> str:
        """Exports system operational audit trail to CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        headers = ["Log ID", "Timestamp", "Actor", "Role", "Action", "Entity", "IP Address"]
        writer.writerow(headers)

        for log in audit_logs:
            row = [
                log.id,
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "N/A",
                log.actor.full_name if log.actor else "System",
                log.user_role or "System",
                log.action,
                f"{log.entity_type}:{log.entity_id}",
                log.ip_address or "127.0.0.1"
            ]
            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def export_warranties_csv(warranties) -> str:
        """Exports warranty policies and active/expired warranties to CSV (Req xlv)."""
        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Warranty ID", "Product ID", "Product Name", "Owner Name",
            "Category", "Provider", "Start Date", "Expiry Date",
            "Extended Coverage", "Extended Months", "Remaining Days", "Active Status"
        ]
        writer.writerow(headers)

        for w in warranties:
            prod = w.product
            owner_name = prod.owner.full_name if prod and prod.owner else "N/A"
            prod_name = prod.product_name if prod else "N/A"
            prod_id = prod.product_id if prod else "N/A"
            cat = prod.category if prod else "N/A"

            row = [
                w.warranty_id,
                prod_id,
                prod_name,
                owner_name,
                cat,
                w.warranty_provider,
                w.start_date.strftime("%Y-%m-%d") if w.start_date else "N/A",
                w.expiry_date.strftime("%Y-%m-%d") if w.expiry_date else "N/A",
                "Yes" if w.is_extended else "No",
                w.extended_months or 0,
                w.remaining_days(),
                w.status
            ]
            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def export_analytics_csv(analytics_payload) -> str:
        """Exports 8-dimension analytics summary to CSV (Req xlv)."""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["AssureX Enterprise Analytics & Reporting Summary"])
        writer.writerow(["Generated At", analytics_payload.get("generated_at", "N/A")])
        writer.writerow([])

        # Section 1: Outcomes
        writer.writerow(["--- 1. Claim Outcomes ---"])
        writer.writerow(["Status", "Count", "Percentage (%)"])
        outcomes = analytics_payload.get("outcomes", {})
        counts = outcomes.get("counts", {})
        pcts = outcomes.get("percentages", {})
        for st, cnt in counts.items():
            writer.writerow([st, cnt, f"{pcts.get(st, 0.0)}%"])
        writer.writerow([])

        # Section 2: Faults
        writer.writerow(["--- 2. Top Frequently Reported Faults ---"])
        writer.writerow(["Category", "Count"])
        for cat, cnt in analytics_payload.get("faults", {}).get("categories", {}).items():
            writer.writerow([cat, cnt])
        writer.writerow([])

        # Section 3: Rejections
        writer.writerow(["--- 3. Rejected Claim Reasons ---"])
        writer.writerow(["Reason", "Count", "Percentage (%)"])
        rejections = analytics_payload.get("rejections", {})
        r_counts = rejections.get("reasons", {})
        r_pcts = rejections.get("percentages", {})
        for rsn, cnt in r_counts.items():
            writer.writerow([rsn, cnt, f"{r_pcts.get(rsn, 0.0)}%"])
        writer.writerow([])

        # Section 4: Product Categories
        writer.writerow(["--- 4. Product Category Claim Rates ---"])
        writer.writerow(["Category", "Fleet Size", "Claims Count", "Claim Rate (%)", "Approved", "Rejected"])
        for cat, d in analytics_payload.get("categories", {}).get("categories", {}).items():
            writer.writerow([cat, d.get("product_count"), d.get("claim_count"), f"{d.get('claim_rate')}%", d.get("approved_count"), d.get("rejected_count")])
        writer.writerow([])

        # Section 5: Expirations
        writer.writerow(["--- 5. Warranty Expirations Horizon ---"])
        exp = analytics_payload.get("expirations", {})
        writer.writerow(["Active (>60d)", exp.get("active_count", 0)])
        writer.writerow(["Expiring (31-60d)", exp.get("approaching_60d_count", 0)])
        writer.writerow(["Expiring (<=30d)", exp.get("approaching_30d_count", 0)])
        writer.writerow(["Expired", exp.get("expired_count", 0)])
        writer.writerow([])

        # Section 6: Repairs
        writer.writerow(["--- 6. Repair Patterns ---"])
        rep = analytics_payload.get("repairs", {})
        writer.writerow(["Total Repairs", rep.get("total_repairs", 0)])
        writer.writerow(["Authorized Workshop Rate (%)", f"{rep.get('authorized_rate', 0)}%"])
        writer.writerow(["Average Repair Cost ($)", f"${rep.get('avg_cost', 0)}"])
        writer.writerow([])

        # Section 7: Models
        writer.writerow(["--- 7. Dual-Model Performance ---"])
        mod = analytics_payload.get("models", {})
        writer.writerow(["Dual-Model Agreement Rate (%)", f"{mod.get('agreement_rate', 0)}%"])
        writer.writerow(["Mean Delta Conf |Δconf|", mod.get("avg_conf_diff", 0)])
        writer.writerow(["Python Model Avg Conf", mod.get("avg_python_conf", 0)])
        writer.writerow(["GTM Model Avg Conf", mod.get("avg_gtm_conf", 0)])
        writer.writerow([])

        # Section 8: Manual Review
        writer.writerow(["--- 8. Manual Review Frequency ---"])
        mr = analytics_payload.get("manual_review", {})
        writer.writerow(["Manual Triage Count", mr.get("manual_review_count", 0)])
        writer.writerow(["Incidence Rate (%)", f"{mr.get('incidence_rate', 0)}%"])

        return output.getvalue()
