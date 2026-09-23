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
