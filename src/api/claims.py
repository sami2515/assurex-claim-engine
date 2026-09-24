import os
import json
from pathlib import Path
from datetime import datetime, date
from werkzeug.utils import secure_filename
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, current_app, send_file
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
from src.rules.validator import ClaimValidator
from src.rules.duplicate_detector import DuplicateDetector, get_duplicate_detector
from src.core.preprocessor import ClaimDataPreprocessor

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
        # Req 1.6.xv: Data Validation - Check mandatory fields, dates, numbers, files, duplicate IDs
        is_valid, val_errors, val_warnings, cleaned_data = ClaimValidator.validate_claim_submission(
            request.form, request.files, user_role=session.get("role")
        )
        if not is_valid:
            for err in val_errors:
                flash(err, "danger")
            for warn in val_warnings:
                flash(warn, "warning")
            return redirect(url_for("claims.create_claim_wizard"))

        for warn in val_warnings:
            flash(warn, "info")

        product = cleaned_data["product"]
        fault_date = cleaned_data["fault_occurrence_date"]
        fault_category = cleaned_data["fault_category"]
        damage_type = cleaned_data["damage_type"]
        fault_description = cleaned_data["fault_description"]
        previous_replacement = cleaned_data.get("previous_replacement_details")
        claim_amount = cleaned_data.get("claim_amount", product.purchase_price)

        # Determine Claim Owner User (Req 1.6.x):
        # Customers file claims for their own assets.
        # Service-center staff or admin filing on customer's behalf link claim directly to the product owner!
        claim_user_id = product.user_id if session.get("role") in [Config.ROLE_STAFF, Config.ROLE_ADMIN] else user.id

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

        # Calculate document counts & detect missing mandatory documents (Req 1.6.xxix)
        has_prior_repairs = bool(product and ((hasattr(product, "repair_records") and len(product.repair_records) > 0) or getattr(product, "has_prior_repairs", False)))
        missing_docs_check = ClaimValidator.identify_missing_documents(claim.documents, has_previous_repairs=has_prior_repairs)
        claim.missing_document_flag = missing_docs_check["has_missing"]

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

        # 4. Data Pre-Processing using Python (Req 1.6.xvi)
        # Cleans, handles missing values, converts date formats, and computes derived fields:
        # product age, remaining warranty period, and missing-document count.
        claim_feature_payload = ClaimDataPreprocessor.clean_and_prepare(
            {
                "claim_id": claim.claim_id,
                "fault_category": fault_category,
                "damage_type": damage_type,
                "fault_occurrence_date": fault_date,
                "claim_submission_date": date.today(),
                "claim_amount": claim_amount,
                "has_receipt": 1 if has_receipt else 0,
                "has_warranty_card": 1 if has_warranty_card else 0,
                "has_damage_photo": 1 if has_damage_photo else 0,
                "has_serial_photo": 1 if has_serial_photo else 0,
                "has_repair_report": 1 if has_diagnostic_report else 0
            },
            product=product,
            documents=claim.documents
        )

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

        # Notify user regarding missing mandatory documents (Req 1.6.xxix)
        if claim.missing_document_flag and missing_docs_check["has_missing"]:
            missing_names = missing_docs_check["missing_labels"]
            missing_notif = Notification(
                user_id=claim.user_id,
                notification_type=Config.NOTIF_TYPE_MISSING_DOCUMENTS,
                title=f"Missing Documents: Claim {claim.claim_id}",
                message=(
                    f"Your claim for '{product.product_name}' requires the following documents: "
                    f"{', '.join(missing_names)}. Please upload them to avoid delays in adjudication."
                ),
                related_claim_id=claim.claim_id,
                related_product_id=product.product_id
            )
            db.session.add(missing_notif)

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


@claim_bp.route("/preparation-check", methods=["POST"])
@login_required
def claim_preparation_check():
    """
    Req 1.6.xxxiii: Claim Preparation Assistance.
    Pre-submission API that analyzes intake form parameters and uploaded files,
    returning guidance on missing information, missing documents, approaching deadlines,
    possible contradictions, and recommended corrective actions.
    """
    user = get_current_user()
    product_id_str = request.form.get("product_id")
    product = None
    if product_id_str:
        if str(product_id_str).isdigit():
            product = db.session.get(Product, int(product_id_str))
        if not product:
            product = Product.query.filter_by(product_id=str(product_id_str)).first()

    readiness = ClaimValidator.check_claim_preparation_readiness(
        form_data=request.form.to_dict(),
        files_dict=request.files.to_dict(),
        product=product
    )
    return jsonify({"success": True, "readiness": readiness})


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
    """Full claim dossier inspection view with dual-model charts, missing documents alert, and verification."""
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    has_repairs = bool(claim.product and ((hasattr(claim.product, "repair_records") and len(claim.product.repair_records) > 0) or getattr(claim.product, "has_prior_repairs", False)))
    missing_docs_info = ClaimValidator.identify_missing_documents(claim.documents, has_previous_repairs=has_repairs)
    
    # Check duplicate flags for dossier inspection (Req 1.6.xxx & xxxi)
    dup_detector = get_duplicate_detector()
    dup_report = dup_detector.check_claim_duplicates(
        {
            "claim_id": claim.claim_id,
            "product_serial": claim.product.serial_number if claim.product else None,
            "invoice_number": claim.product.invoice_number if claim.product else None,
            "fault_description": claim.fault_description,
            "claimant_id": claim.user_id
        },
        current_claim_internal_id=claim.id
    )

    # Generate AI-Generated Claim Summary (Req 1.6.xxxii)
    engine = get_decision_engine()
    ai_summary = engine.generate_claim_summary(claim)

    return render_template(
        "customer/claim_detail.html",
        claim=claim,
        missing_docs_info=missing_docs_info,
        dup_report=dup_report,
        ai_summary=ai_summary
    )


@claim_bp.route("/<string:claim_id>/documents/upload", methods=["POST"])
@login_required
def upload_claim_document(claim_id):
    """
    Req 1.6.xxix & Req 1.6.xiv: Allows claimant or authorized staff to upload missing
    or supplementary mandatory evidence files (receipts, warranty cards, photos, diagnostic reports)
    to an existing claim dossier. Automatically computes SHA-256 hash, runs OCR if applicable,
    checks for cross-claim duplicate documents (Req xxxi), and updates missing document status.
    """
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    user = get_current_user()
    role = session.get("role")

    # Permission check: claimant owner, staff, or admin
    if role not in [Config.ROLE_ADMIN, Config.ROLE_STAFF] and claim.user_id != user.id:
        flash("Access denied: You do not have permission to attach documents to this claim.", "danger")
        return redirect(url_for("claims.view_claim", claim_id=claim.claim_id))

    if claim.status in [Config.STATUS_APPROVED, Config.STATUS_REJECTED, Config.STATUS_CLOSED]:
        flash("Documents cannot be added to closed or finalized claims.", "warning")
        return redirect(url_for("claims.view_claim", claim_id=claim.claim_id))

    doc_type = request.form.get("document_type", "other_evidence").strip()
    uploaded_file = request.files.get("evidence_file")

    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a valid document or media file to upload.", "warning")
        return redirect(url_for("claims.view_claim", claim_id=claim.claim_id))

    # Validate file extension and size
    is_valid_file, file_err = ClaimValidator.validate_file(uploaded_file)
    if not is_valid_file:
        flash(file_err, "danger")
        return redirect(url_for("claims.view_claim", claim_id=claim.claim_id))

    upload_folder = Path(Config.UPLOAD_DIR)
    upload_folder.mkdir(parents=True, exist_ok=True)
    sec_filename = f"{claim.claim_id}_{doc_type}_{secure_filename(uploaded_file.filename)}"
    save_dest = upload_folder / sec_filename
    uploaded_file.save(save_dest)

    # Process document via OCR & SHA-256 Hashing engine
    doc_processor = get_document_processor()
    doc_info = doc_processor.process_document(save_dest, document_type=doc_type)

    # Check duplicate document hash (Req 1.6.xxxi)
    dup_check = DuplicateDetector.check_document_duplicates(
        file_hash=doc_info["sha256_hash"],
        exclude_claim_id=claim.id
    )
    if dup_check["is_duplicate"]:
        flash(
            f"Duplicate Document Warning: Identical file has already been used in claim(s): "
            f"{', '.join(dup_check['matched_claims'])}.",
            "warning"
        )

    # Persist ClaimDocument
    claim_doc = ClaimDocument(
        claim_id=claim.id,
        product_id=claim.product_id,
        document_type=doc_type,
        file_path=str(save_dest),
        original_filename=uploaded_file.filename,
        file_size_bytes=doc_info["file_size_bytes"],
        file_hash_sha256=doc_info["sha256_hash"],
        ocr_extracted_text=doc_info.get("raw_text"),
        ocr_data_json=json.dumps(doc_info.get("entities", {})),
        verified_by_user=True
    )
    db.session.add(claim_doc)
    db.session.flush()

    # Re-evaluate missing documents status (Req 1.6.xxix)
    has_repairs = bool(claim.product and ((hasattr(claim.product, "repair_records") and len(claim.product.repair_records) > 0) or getattr(claim.product, "has_prior_repairs", False)))
    missing_check = ClaimValidator.identify_missing_documents(claim.documents, has_previous_repairs=has_repairs)
    claim.missing_document_flag = missing_check["has_missing"]

    # Log audit event
    audit = AuditLog(
        user_id=user.id,
        user_role=role,
        action="DOCUMENT_ATTACHED",
        entity_type="CLAIM_DOCUMENT",
        entity_id=claim_doc.document_id,
        ip_address=request.remote_addr,
        details_json=json.dumps({
            "claim_id": claim.claim_id,
            "document_type": doc_type,
            "sha256": doc_info["sha256_hash"],
            "missing_documents_remaining": missing_check["missing_labels"]
        })
    )
    db.session.add(audit)
    db.session.commit()

    if not missing_check["has_missing"]:
        flash(f"Document '{uploaded_file.filename}' uploaded successfully. All mandatory documents are now verified!", "success")
    else:
        flash(
            f"Document '{uploaded_file.filename}' uploaded successfully. Remaining required document(s): "
            f"{', '.join(missing_check['missing_labels'])}.",
            "info"
        )

    return redirect(url_for("claims.view_claim", claim_id=claim.claim_id))


@claim_bp.route("/<string:claim_id>/summary-card", methods=["GET"])
@login_required
def view_summary_card(claim_id):
    """
    Req 1.6.xx: Serves the standardized visual Claim Summary Card image.
    Strictly contains raw claim evidence (product age, warranty status, fault type,
    repair history, document availability, serial-number status) without AI predictions.
    """
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    upload_folder = Path(Config.UPLOAD_DIR)
    card_path = upload_folder / f"{claim.claim_id}_card.png"

    if not card_path.exists():
        payload = ClaimDataPreprocessor.clean_and_prepare(
            {
                "claim_id": claim.claim_id,
                "fault_category": claim.fault_category,
                "damage_type": claim.damage_type,
                "fault_occurrence_date": claim.fault_occurrence_date,
                "claim_submission_date": claim.claim_submission_date
            },
            product=claim.product,
            documents=claim.documents
        )
        card_img = render_claim_summary_card(payload, variation=1)
        upload_folder.mkdir(parents=True, exist_ok=True)
        card_img.save(card_path)

    return send_file(card_path, mimetype="image/png")

