import os
import json
from pathlib import Path
from datetime import datetime, date
from werkzeug.utils import secure_filename
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, current_app
from config.config import Config
from database.db import db
from src.models.entities import (
    Claim, Product, ProductWarranty, ClaimDocument, ClaimStatusHistory,
    ModelEvaluation, RuleValidationLog, Notification, AuditLog
)
from src.api.auth import login_required, get_current_user
from src.ocr.document_processor import get_document_processor
from src.core.decision_engine import get_decision_engine
from src.core.card_generator import render_claim_summary_card
from src.services.alert_service import scan_and_generate_warranty_alerts

claim_bp = Blueprint("claims", __name__, url_prefix="/claims")


@claim_bp.route("/", methods=["GET"])
@login_required
def customer_dashboard():
    """Req xl & 1.6.ix: Customer dashboard with registered products, warranties, alerts, and claims."""
    user = get_current_user()
    
    # Automatically scan & dispatch expiry alerts for the current customer (Req 1.6.ix)
    if session.get("role") == Config.ROLE_CUSTOMER:
        scan_and_generate_warranty_alerts(user_id=user.id)

    if session.get("role") in [Config.ROLE_ADMIN, Config.ROLE_STAFF, Config.ROLE_REVIEWER]:
        claims = Claim.query.order_by(Claim.created_at.desc()).all()
        products = Product.query.order_by(Product.created_at.desc()).all()
    else:
        claims = Claim.query.filter_by(user_id=user.id).order_by(Claim.created_at.desc()).all()
        products = Product.query.filter_by(user_id=user.id).order_by(Product.created_at.desc()).all()

    notifications = Notification.query.filter_by(user_id=user.id, is_read=False).order_by(Notification.created_at.desc()).all()

    return render_template(
        "customer/dashboard.html",
        claims=claims,
        products=products,
        notifications=notifications,
        all_statuses=Config.ALL_CLAIM_STATUSES
    )


@claim_bp.route("/my-claims", methods=["GET"])
@login_required
def list_my_claims():
    """Alias for customer claims view."""
    return customer_dashboard()


@claim_bp.route("/new", methods=["GET", "POST"])
@claim_bp.route("/intake-wizard", methods=["GET", "POST"], endpoint="intake_wizard")
@login_required
def create_claim_wizard():
    """
    5-Step Interactive Claim Intake Wizard (Req 1.6.x):
    Step 1: Product & Warranty selection (Users or Service-Center Staff)
    Step 2: Fault declaration & details
    Step 3: Document intake & OCR extraction
    Step 4: Claim preparation assistance & pre-submission check (Req xxxiii)
    Step 5: Automated Dual-Model Adjudication & Lifecycle Routing
    """
    user = get_current_user()
    products = Product.query.filter_by(user_id=user.id).all() if session.get("role") == Config.ROLE_CUSTOMER else Product.query.all()

    if request.method == "POST":
        product_id_str = request.form.get("product_id")
        fault_date_str = request.form.get("fault_occurrence_date")
        fault_category = request.form.get("fault_category")
        damage_type = request.form.get("damage_type")
        fault_description = request.form.get("fault_description", "").strip()

        product = None
        if product_id_str:
            if str(product_id_str).isdigit():
                product = db.session.get(Product, int(product_id_str))
            if not product:
                product = Product.query.filter_by(product_id=str(product_id_str)).first()

        if not product or not product.warranty:
            flash("Please select a registered product with an active warranty policy.", "danger")
            return redirect(url_for("claims.create_claim_wizard"))

        try:
            fault_date = datetime.strptime(fault_date_str, "%Y-%m-%d").date()
        except Exception:
            fault_date = date.today()

        # Determine Claim Owner User (Req 1.6.x):
        # Customers file claims for their own assets.
        # Service-center staff or admin filing on customer's behalf link claim directly to the product owner!
        claim_user_id = product.user_id if session.get("role") in [Config.ROLE_STAFF, Config.ROLE_ADMIN] else user.id

        # Collect claim details (Req 1.6.xi)
        previous_replacement = request.form.get("previous_replacement_details", "").strip()

        # 1. Create Initial Claim in 'Submitted' status
        claim = Claim(
            user_id=claim_user_id,
            product_id=product.id,
            warranty_id=product.warranty.id,
            fault_occurrence_date=fault_date,
            fault_description=fault_description,
            fault_category=fault_category,
            damage_type=damage_type,
            previous_replacement_details=previous_replacement or None,
            claim_submission_date=date.today(),
            status=Config.STATUS_SUBMITTED
        )
        db.session.add(claim)
        db.session.flush()

        # Record Initial Status History
        sub_reason = (
            f"Claim dossier registered by authorized service center staff ({user.full_name}) on behalf of customer."
            if session.get("role") == Config.ROLE_STAFF
            else "Claim dossier submitted by claimant."
        )
        status_log = ClaimStatusHistory(
            claim_id=claim.id,
            previous_status=Config.STATUS_DRAFT,
            new_status=Config.STATUS_SUBMITTED,
            changed_by_user_id=user.id,
            reason_comment=sub_reason
        )
        db.session.add(status_log)

        # 2. Process Uploaded Documents & Multi-Media Evidence (Req 1.6.v, xii)
        doc_processor = get_document_processor()
        has_receipt = False
        has_warranty_card = False
        has_damage_photo = False
        has_serial_photo = False
        has_fault_video = False
        has_diagnostic_report = False
        ocr_extracted_data = {}

        upload_folder = Path(Config.UPLOAD_DIR)
        upload_folder.mkdir(parents=True, exist_ok=True)

        evidence_types = [
            "receipt", "warranty_card", "damage_photo", "product_photo",
            "fault_video", "serial_photo", "diagnostic_report", "other_evidence"
        ]

        for doc_key in evidence_types:
            uploaded_file = request.files.get(doc_key)
            if not uploaded_file and doc_key == "receipt":
                uploaded_file = request.files.get("invoice_document")
            if uploaded_file and uploaded_file.filename:
                sec_filename = f"{claim.claim_id}_{doc_key}_{secure_filename(uploaded_file.filename)}"
                save_dest = upload_folder / sec_filename
                uploaded_file.save(save_dest)

                # Process via OCR engine (extracts text from invoices/reports)
                doc_info = doc_processor.process_document(save_dest, document_type=doc_key)

                claim_doc = ClaimDocument(
                    claim_id=claim.id,
                    product_id=product.id,
                    document_type=doc_key,
                    file_path=str(save_dest),
                    original_filename=uploaded_file.filename,
                    file_size_bytes=doc_info["file_size_bytes"],
                    file_hash_sha256=doc_info["sha256_hash"],
                    ocr_extracted_text=doc_info["raw_text"],
                    ocr_data_json=json.dumps(doc_info["entities"]),
                    verified_by_user=True
                )
                db.session.add(claim_doc)

                if doc_key in ["receipt", "invoice_document"]:
                    has_receipt = True
                    ocr_extracted_data = doc_info["entities"]
                elif doc_key == "warranty_card":
                    has_warranty_card = True
                elif doc_key == "damage_photo":
                    has_damage_photo = True
                elif doc_key == "serial_photo":
                    has_serial_photo = True
                elif doc_key == "fault_video":
                    has_fault_video = True
                elif doc_key == "diagnostic_report":
                    has_diagnostic_report = True

        # Calculate document counts
        missing_count = sum([not has_receipt, not has_warranty_card, not has_damage_photo, not has_serial_photo])
        claim.missing_document_flag = bool(missing_count > 0)

        # 3. Transition to 'Under Evaluation'
        claim.status = Config.STATUS_UNDER_EVALUATION
        eval_status_log = ClaimStatusHistory(
            claim_id=claim.id,
            previous_status=Config.STATUS_SUBMITTED,
            new_status=Config.STATUS_UNDER_EVALUATION,
            changed_by_user_id=None,
            reason_comment="Automated dual-model and business rule evaluation initiated."
        )
        db.session.add(eval_status_log)

        # 4. Prepare Feature Payload for Dual-Model Evaluation
        warr = product.warranty
        product_age = (date.today() - product.purchase_date).days
        rem_days = warr.remaining_days()

        claim_feature_payload = {
            "claim_id": claim.claim_id,
            "product_category": product.category,
            "product_model": product.model_number,
            "product_serial": product.serial_number,
            "purchase_date": product.purchase_date.strftime("%Y-%m-%d"),
            "purchase_price": product.purchase_price,
            "retailer": product.retailer,
            "warranty_expiry_date": warr.expiry_date.strftime("%Y-%m-%d"),
            "warranty_duration_months": product.warranty.policy.coverage_duration_months if product.warranty.policy else 12,
            "product_age_days": max(0, product_age),
            "remaining_warranty_days": max(0, rem_days),
            "fault_occurrence_date": fault_date.strftime("%Y-%m-%d"),
            "fault_category": fault_category,
            "damage_type": damage_type,
            "is_extended_warranty": 1 if warr.is_extended else 0,
            "has_receipt": 1 if has_receipt else 0,
            "has_warranty_card": 1 if has_warranty_card else 0,
            "has_damage_photo": 1 if has_damage_photo else 0,
            "has_serial_photo": 1 if has_serial_photo else 0,
            "has_repair_report": 0,
            "missing_document_count": missing_count,
            "serial_number_match": 1,
            "previous_repairs_count": len(product.repair_records),
            "unauthorized_repair_flag": 1 if any(not r.is_authorized_center for r in product.repair_records) else 0,
            "claim_date_conflict_flag": 1 if fault_date < product.purchase_date else 0
        }

        # 5. Execute Master Decision Engine
        engine = get_decision_engine()
        adjudication_res = engine.adjudicate_claim(
            claim_feature_payload,
            ocr_data=ocr_extracted_data,
            current_claim_internal_id=claim.id
        )

        final_rec = adjudication_res["final_decision"]
        claim.final_decision = final_rec
        claim.risk_level = adjudication_res["risk_level"]
        claim.decision_reason = adjudication_res["decision_summary"]

        # Lifecycle routing based on decision
        if final_rec == "Likely Valid":
            next_status = Config.STATUS_APPROVED
            reason_txt = "Automated adjudication: Approved based on dual-model consensus and policy verification."
        elif final_rec == "Likely Invalid":
            next_status = Config.STATUS_REJECTED
            reason_txt = f"Automated adjudication: Rejected due to policy violation ({claim.decision_reason})."
        else:
            next_status = Config.STATUS_MANUAL_REVIEW
            reason_txt = "Automated adjudication: Routed to manual review queue for human triage."

        claim.status = next_status
        routing_log = ClaimStatusHistory(
            claim_id=claim.id,
            previous_status=Config.STATUS_UNDER_EVALUATION,
            new_status=next_status,
            changed_by_user_id=None,
            reason_comment=reason_txt
        )
        db.session.add(routing_log)

        # 6. Persist Model Evaluation Record
        dual_eval = adjudication_res["dual_model_evaluation"]
        py_m = dual_eval["python_model"]
        gtm_m = dual_eval["gtm_model"]

        # Render summary card and save path
        summary_card_img = render_claim_summary_card(claim_feature_payload, variation=1)
        card_filename = f"{claim.claim_id}_card.png"
        card_save_path = upload_folder / card_filename
        summary_card_img.save(card_save_path)

        model_eval_obj = ModelEvaluation(
            claim_id=claim.id,
            python_model_version=py_m.get("model_version", "v1.0.0"),
            python_predicted_class=py_m.get("predicted_class", "Valid Claim"),
            python_conf_valid=py_m["confidence_scores"].get("Valid Claim", 0.0),
            python_conf_invalid=py_m["confidence_scores"].get("Invalid Claim", 0.0),
            python_conf_manual=py_m["confidence_scores"].get("Manual Review", 0.0),
            gtm_model_version=gtm_m.get("model_version", "v1.0.0"),
            gtm_predicted_class=gtm_m.get("predicted_class", "Valid Claim"),
            gtm_conf_valid=gtm_m["confidence_scores"].get("Valid Claim", 0.0),
            gtm_conf_invalid=gtm_m["confidence_scores"].get("Invalid Claim", 0.0),
            gtm_conf_manual=gtm_m["confidence_scores"].get("Manual Review", 0.0),
            is_class_match=dual_eval["is_class_match"],
            top_confidence_difference=dual_eval["top_confidence_difference"],
            model_consistency_status=dual_eval["model_consistency_status"],
            summary_card_image_path=str(card_save_path)
        )
        db.session.add(model_eval_obj)

        # 7. Persist Rule Validation Record
        rules_eval = adjudication_res["rule_evaluation"]
        rule_val_obj = RuleValidationLog(
            claim_id=claim.id,
            policy_id=product.warranty.policy.policy_id if product.warranty.policy else "POL-DEFAULT",
            rules_passed_json=json.dumps(rules_eval["passed_rules"]),
            rules_failed_json=json.dumps(rules_eval["failed_rules"]),
            warnings_json=json.dumps(rules_eval["warnings"]),
            contradictions_json=json.dumps(adjudication_res["contradictions"]),
            duplicate_flags_json=json.dumps(adjudication_res["duplicate_flags"]),
            overall_rule_status=rules_eval["overall_status"]
        )
        db.session.add(rule_val_obj)

        # 8. User Notification & Audit Log
        notif = Notification(
            user_id=claim.user_id,
            notification_type=Config.NOTIF_TYPE_STATUS_CHANGE,
            title=f"Claim {claim.claim_id} Evaluated",
            message=f"Your claim for '{product.product_name}' is currently in '{claim.status}' status ({final_rec}).",
            related_claim_id=claim.claim_id,
            related_product_id=product.product_id
        )
        db.session.add(notif)

        if session.get("role") == Config.ROLE_STAFF:
            staff_notif = Notification(
                user_id=claim.user_id,
                notification_type=Config.NOTIF_TYPE_CLAIM_SUBMISSION,
                title=f"Service Center Claim Filed: {product.product_name}",
                message=f"Authorized service center staff ({user.full_name}) registered warranty claim {claim.claim_id} for your {product.product_name}.",
                related_claim_id=claim.claim_id,
                related_product_id=product.product_id
            )
            db.session.add(staff_notif)

        audit = AuditLog(
            user_id=user.id,
            user_role=session.get("role"),
            action="CLAIM_EVALUATED",
            entity_type="CLAIM",
            entity_id=claim.claim_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({
                "decision": final_rec,
                "status": claim.status,
                "consistency": dual_eval["model_consistency_status"]
            })
        )
        db.session.add(audit)
        db.session.commit()

        flash(f"Claim {claim.claim_id} submitted and evaluated! Final Status: {claim.status}", "success")
        return redirect(url_for("claims.track_claim_status", claim_id=claim.claim_id))

    return render_template("customer/claim_wizard.html", products=products)


@claim_bp.route("/ocr-extract", methods=["POST"])
@login_required
def ocr_extract_preview():
    """
    Req vi & vii: Document scanning and extracted data verification endpoint.
    Accepts an uploaded invoice/receipt and returns OCR parsed entities for user preview/editing.
    """
    if "document" not in request.files:
        return jsonify({"success": False, "error": "No document uploaded."}), 400

    uploaded_file = request.files["document"]
    if not uploaded_file.filename:
        return jsonify({"success": False, "error": "Empty filename."}), 400

    upload_folder = Path(Config.UPLOAD_DIR)
    upload_folder.mkdir(parents=True, exist_ok=True)
    temp_path = upload_folder / f"temp_{secure_filename(uploaded_file.filename)}"
    uploaded_file.save(temp_path)

    doc_processor = get_document_processor()
    doc_info = doc_processor.process_document(temp_path)

    return jsonify({
        "success": True,
        "filename": doc_info["filename"],
        "sha256": doc_info["sha256_hash"],
        "entities": doc_info["entities"],
        "raw_text_snippet": doc_info["raw_text"][:250]
    })


@claim_bp.route("/<string:claim_id>/track", methods=["GET"])
@login_required
def track_claim_status(claim_id):
    """
    Req xxxviii: Real-time progress timeline across all 8 SRS stages.
    """
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    return render_template(
        "customer/claim_track.html",
        claim=claim,
        all_stages=Config.ALL_CLAIM_STATUSES
    )


@claim_bp.route("/<string:claim_id>", methods=["GET"])
@login_required
def view_claim(claim_id):
    """Full claim dossier inspection view with dual-model charts and documents."""
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    return render_template("customer/claim_detail.html", claim=claim)
