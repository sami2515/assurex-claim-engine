import os
import sys
import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from config.config import Config
from src.core.decision_engine import get_decision_engine

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_comparison_reports(sample_size: int = 40):
    """
    Evaluates both Python Tabular ML and Google Teachable Machine Vision models
    on unseen test set claims and generates model_comparison_report.csv & .md
    strictly complying with the SRS-mandated 21-column schema.
    """
    test_csv_path = BASE_DIR / "data" / "splits" / "test.csv"
    if not test_csv_path.exists():
        raise FileNotFoundError(f"Test split dataset not found at: {test_csv_path}")

    df_test = pd.read_csv(test_csv_path)
    engine = get_decision_engine()

    # Stratified selection to ensure balanced representation across all 3 classes
    sample_df = df_test.groupby("claim_class", group_keys=False).apply(
        lambda x: x.head(sample_size // 3 + 1)
    ).head(sample_size)

    fieldnames = [
        "claim_id",
        "product_category",
        "fault_category",
        "reported_damage_type",
        "claim_amount",
        "warranty_status",
        "python_predicted_class",
        "python_conf_valid",
        "python_conf_invalid",
        "python_conf_manual",
        "python_top_confidence",
        "gtm_predicted_class",
        "gtm_conf_valid",
        "gtm_conf_invalid",
        "gtm_conf_manual",
        "gtm_top_confidence",
        "is_class_match",
        "top_confidence_difference",
        "model_consistency_status",
        "master_engine_decision",
        "decision_rationale"
    ]

    records = []
    consistency_counts = {
        Config.CONSISTENCY_STRONG: 0,
        Config.CONSISTENCY_ACCEPTABLE: 0,
        Config.CONSISTENCY_WEAK: 0,
        Config.CONSISTENCY_DISAGREEMENT: 0,
        Config.CONSISTENCY_UNCERTAIN: 0
    }
    match_count = 0

    print(f"[*] Running dual-model inference on {len(sample_df)} unseen test claims...")

    for idx, row in sample_df.iterrows():
        claim_dict = row.to_dict()
        res = engine.adjudicate_claim(claim_dict)

        py_eval = res["dual_model_evaluation"]["python_model"]
        gtm_eval = res["dual_model_evaluation"]["gtm_model"]
        dual_eval = res["dual_model_evaluation"]

        is_match = dual_eval["is_class_match"]
        consistency = dual_eval["model_consistency_status"]
        if is_match:
            match_count += 1
        consistency_counts[consistency] = consistency_counts.get(consistency, 0) + 1

        rem_days = claim_dict.get("remaining_warranty_days", 0)
        warr_status = "Active" if rem_days > 0 else "Expired"

        rec = {
            "claim_id": claim_dict.get("claim_id"),
            "product_category": claim_dict.get("product_category"),
            "fault_category": claim_dict.get("fault_category"),
            "reported_damage_type": claim_dict.get("damage_type"),
            "claim_amount": f"{float(claim_dict.get('purchase_price', 150.0) * 0.25):.2f}",
            "warranty_status": warr_status,
            "python_predicted_class": py_eval["predicted_class"],
            "python_conf_valid": f"{py_eval['confidence_scores'].get('Valid Claim', 0.0):.4f}",
            "python_conf_invalid": f"{py_eval['confidence_scores'].get('Invalid Claim', 0.0):.4f}",
            "python_conf_manual": f"{py_eval['confidence_scores'].get('Manual Review', 0.0):.4f}",
            "python_top_confidence": f"{py_eval['top_confidence']:.4f}",
            "gtm_predicted_class": gtm_eval["predicted_class"],
            "gtm_conf_valid": f"{gtm_eval['confidence_scores'].get('Valid Claim', 0.0):.4f}",
            "gtm_conf_invalid": f"{gtm_eval['confidence_scores'].get('Invalid Claim', 0.0):.4f}",
            "gtm_conf_manual": f"{gtm_eval['confidence_scores'].get('Manual Review', 0.0):.4f}",
            "gtm_top_confidence": f"{gtm_eval['top_confidence']:.4f}",
            "is_class_match": is_match,
            "top_confidence_difference": f"{dual_eval['top_confidence_difference']:.4f}",
            "model_consistency_status": consistency,
            "master_engine_decision": res["final_decision"],
            "decision_rationale": res["decision_summary"].replace(",", ";")
        }
        records.append(rec)

    # 1. Save CSV Report
    csv_file = REPORTS_DIR / "model_comparison_report.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"[+] Successfully wrote CSV comparison report to: {csv_file}")

    # 2. Save Markdown Report
    md_file = REPORTS_DIR / "model_comparison_report.md"
    agreement_rate = (match_count / len(records) * 100) if records else 0.0
    avg_diff = sum(float(r["top_confidence_difference"]) for r in records) / len(records) if records else 0.0

    with open(md_file, "w", encoding="utf-8") as f:
        f.write("# AssureX Dual-Model Consensus Evaluation Report\n\n")
        f.write("Official verification dossier comparing Python Tabular Classifier vs. Google Teachable Machine Vision Classifier on unseen test data.\n\n")
        f.write("## Executive Summary\n\n")
        f.write(f"- **Evaluated Test Claims:** {len(records)}\n")
        f.write(f"- **Dual-Model Class Agreement Rate:** {agreement_rate:.2f}%\n")
        f.write(f"- **Average Confidence Difference (|Δconf|):** {avg_diff:.4f}\n\n")
        f.write("### Consistency Status Distribution\n\n")
        f.write("| Model Consistency Status | Claim Count | Share (%) |\n")
        f.write("|:---|:---:|:---:|\n")
        for status_name, cnt in consistency_counts.items():
            share = (cnt / len(records) * 100) if records else 0.0
            f.write(f"| **{status_name}** | {cnt} | {share:.1f}% |\n")

        f.write("\n## Detailed Claim-by-Claim Adjudication Log (21-Column Schema)\n\n")
        f.write("| Claim ID | Category | Fault Category | Python Pred | Py Conf | GTM Pred | GTM Conf | Class Match | |Δconf| | Consistency Status | Final Decision |\n")
        f.write("|:---|:---|:---|:---|:---:|:---|:---:|:---:|:---:|:---|:---|\n")
        for r in records:
            f.write(
                f"| `{r['claim_id']}` | {r['product_category']} | {r['fault_category']} | "
                f"{r['python_predicted_class']} | {r['python_top_confidence']} | "
                f"{r['gtm_predicted_class']} | {r['gtm_top_confidence']} | "
                f"{'✅ Yes' if r['is_class_match'] else '❌ No'} | {r['top_confidence_difference']} | "
                f"`{r['model_consistency_status']}` | **{r['master_engine_decision']}** |\n"
            )

    print(f"[+] Successfully wrote Markdown comparison report to: {md_file}")
    return records


if __name__ == "__main__":
    generate_comparison_reports(sample_size=36)
