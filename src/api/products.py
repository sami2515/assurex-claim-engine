import json
from pathlib import Path
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, send_file
from config.config import Config
from database.db import db
from src.models.entities import Product, ProductWarranty, WarrantyPolicy, RepairHistory, Notification, AuditLog, ClaimDocument
from src.api.auth import login_required, get_current_user
from src.ocr.document_processor import get_document_processor

product_bp = Blueprint("products", __name__, url_prefix="/products")


@product_bp.route("/", methods=["GET"])
@login_required
def list_products():
    """
    Req iv: Displays registered products and warranty statuses from a common interface.
    Supports viewing all active, expired, approaching expiry, and extended warranties.
    """
    user = get_current_user()
    status_filter = request.args.get("status", "all").strip().lower()

    if session.get("role") in [Config.ROLE_ADMIN, Config.ROLE_STAFF, Config.ROLE_REVIEWER]:
        query = Product.query
    else:
        query = Product.query.filter_by(user_id=user.id)

    all_products = query.order_by(Product.created_at.desc()).all()

    # Calculate status counts for the common interface dashboard (Req iv)
    counts = {
        "all": len(all_products),
        "active": 0,
        "approaching": 0,
        "expired": 0,
        "extended": 0
    }
    for p in all_products:
        if p.warranty:
            if p.warranty.is_extended:
                counts["extended"] += 1
            if not p.warranty.is_active():
                counts["expired"] += 1
            elif p.warranty.is_approaching_expiry(threshold_days=30):
                counts["approaching"] += 1
            else:
                counts["active"] += 1

    # Filter products based on selected status tab
    if status_filter == "active":
        filtered_products = [p for p in all_products if p.warranty and p.warranty.is_active() and not p.warranty.is_approaching_expiry(30)]
    elif status_filter == "approaching":
        filtered_products = [p for p in all_products if p.warranty and p.warranty.is_approaching_expiry(30)]
    elif status_filter == "expired":
        filtered_products = [p for p in all_products if p.warranty and not p.warranty.is_active()]
    elif status_filter == "extended":
        filtered_products = [p for p in all_products if p.warranty and p.warranty.is_extended]
    else:
        filtered_products = all_products

    return render_template(
        "customer/products_list.html",
        products=filtered_products,
        counts=counts,
        current_status=status_filter
    )


@product_bp.route("/register", methods=["GET", "POST"])
@login_required
def register_product():
    """
    Req iii: Product Registration - Allows users to register products with details:
    product name, category, brand, model number, serial number, purchase date,
    purchase price, retailer, and warranty duration. Assigns unique Product ID.
    
    Req iv: Warranty Record Management - Stores standard and extended warranty
    information including warranty provider, start date, expiry date, coverage conditions,
    exclusions, and service-center details.
    """
    user = get_current_user()

    if request.method == "POST":
        product_name = request.form.get("product_name", "").strip()
        category = request.form.get("category", "").strip()
        brand = request.form.get("brand", "").strip()
        model_number = request.form.get("model_number", "").strip()
        serial_number = request.form.get("serial_number", "").strip()
        purchase_date_str = request.form.get("purchase_date", "").strip()
        purchase_price = float(request.form.get("purchase_price", "0.0") or 0.0)
        retailer = request.form.get("retailer", "").strip()
        invoice_number = request.form.get("invoice_number", "").strip()

        # Warranty specifications (Req iii & iv)
        warranty_duration_str = request.form.get("warranty_duration", "").strip()
        warranty_type = request.form.get("warranty_type", "standard").strip().lower()
        warranty_provider = request.form.get("warranty_provider", "").strip()
        service_center_name = request.form.get("service_center_name", "").strip()

        if not product_name or not serial_number or not purchase_date_str:
            flash("Product name, serial number, and purchase date are mandatory.", "warning")
            policies = WarrantyPolicy.query.all()
            return render_template("customer/product_register.html", policies=policies)

        # Parse purchase date
        try:
            p_date = datetime.strptime(purchase_date_str, "%Y-%m-%d").date()
        except ValueError:
            p_date = date.today()

        # Check existing serial to avoid collisions
        existing = Product.query.filter_by(serial_number=serial_number).first()
        if existing:
            flash(f"A product with serial number '{serial_number}' is already registered.", "danger")
            policies = WarrantyPolicy.query.all()
            return render_template("customer/product_register.html", policies=policies)

        # 1. Create Product Entity with System Unique Product ID (Req iii)
        product = Product(
            user_id=user.id,
            product_name=product_name,
            category=category,
            brand=brand,
            model_number=model_number,
            serial_number=serial_number,
            purchase_date=p_date,
            purchase_price=purchase_price,
            retailer=retailer,
            invoice_number=invoice_number
        )
        db.session.add(product)
        db.session.flush()

        # 2. Attach Warranty Record (Req iv)
        policy = WarrantyPolicy.query.filter_by(category=category).first()
        
        # Determine duration: user input or default from policy
        if warranty_duration_str and warranty_duration_str.isdigit():
            duration_months = int(warranty_duration_str)
        else:
            duration_months = policy.coverage_duration_months if policy else 12

        is_extended = (warranty_type == "extended")
        extended_months = max(0, duration_months - (policy.coverage_duration_months if policy else 12)) if is_extended else 0

        provider_name = warranty_provider if warranty_provider else f"{brand} Official Care"
        service_center = service_center_name if service_center_name else "Authorized National Service Network"

        w_start = p_date
        w_expiry = w_start + timedelta(days=duration_months * 30)

        warranty = ProductWarranty(
            product_id=product.id,
            policy_id=policy.id if policy else 1,
            warranty_provider=provider_name,
            start_date=w_start,
            expiry_date=w_expiry,
            is_extended=is_extended,
            extended_months=extended_months,
            service_center_name=service_center
        )
        db.session.add(warranty)

        # 3. Securely Store Uploaded Receipt / Invoice Document (Req 1.6.v & vi)
        receipt_file = request.files.get("receipt_document") or request.files.get("receipt_file") or request.files.get("invoice_document")
        if receipt_file and receipt_file.filename:
            ext = receipt_file.filename.rsplit(".", 1)[-1].lower() if "." in receipt_file.filename else ""
            if ext in Config.ALLOWED_DOCUMENT_EXTENSIONS:
                upload_folder = Path(Config.UPLOAD_DIR)
                upload_folder.mkdir(parents=True, exist_ok=True)
                sec_filename = f"{product.product_id}_receipt_{secure_filename(receipt_file.filename)}"
                save_dest = upload_folder / sec_filename
                receipt_file.save(save_dest)

                doc_processor = get_document_processor()
                doc_info = doc_processor.process_document(save_dest, document_type="receipt")

                claim_doc = ClaimDocument(
                    product_id=product.id,
                    claim_id=None,
                    document_type="receipt",
                    file_path=str(save_dest),
                    original_filename=receipt_file.filename,
                    file_size_bytes=doc_info["file_size_bytes"],
                    file_hash_sha256=doc_info["sha256_hash"],
                    ocr_extracted_text=doc_info["raw_text"],
                    ocr_data_json=json.dumps(doc_info["entities"]),
                    verified_by_user=True
                )
                db.session.add(claim_doc)

        # Record Audit Log (Req xlvii)
        audit = AuditLog(
            user_id=user.id,
            user_role=session.get("role"),
            action="PRODUCT_REGISTRATION",
            entity_type="PRODUCT",
            entity_id=product.product_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({"product_name": product.product_name, "serial": product.serial_number})
        )
        db.session.add(audit)
        db.session.commit()

        flash(
            f"Product '{product_name}' registered successfully! Assigned Unique Product ID: {product.product_id} with {duration_months}-month warranty coverage.",
            "success"
        )
        return redirect(url_for("products.list_products"))

    policies = WarrantyPolicy.query.all()
    return render_template("customer/product_register.html", policies=policies)


@product_bp.route("/scan-receipt", methods=["POST"])
@login_required
def scan_receipt():
    """
    Req vi & vii: Document scanning and extracted data verification endpoint for product registration.
    Extracts purchase date, invoice number, product name, model number, serial number,
    retailer, purchase amount, and warranty duration from PDF, JPG, JPEG, and PNG files.
    """
    uploaded_file = request.files.get("receipt_document") or request.files.get("document") or request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"success": False, "error": "No file uploaded. Please select an invoice or receipt."}), 400

    ext = uploaded_file.filename.rsplit(".", 1)[-1].lower() if "." in uploaded_file.filename else ""
    if ext not in Config.ALLOWED_DOCUMENT_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": f"Unsupported format '.{ext}'. Allowed formats: PDF, JPG, JPEG, PNG (Req 1.6.v)."
        }), 400

    upload_folder = Path(Config.UPLOAD_DIR)
    upload_folder.mkdir(parents=True, exist_ok=True)
    temp_filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(uploaded_file.filename)}"
    temp_path = upload_folder / temp_filename
    uploaded_file.save(temp_path)

    doc_processor = get_document_processor()
    doc_info = doc_processor.process_document(temp_path, document_type="receipt")

    return jsonify({
        "success": True,
        "filename": doc_info["filename"],
        "temp_path": str(temp_path),
        "sha256": doc_info["sha256_hash"],
        "file_size_bytes": doc_info["file_size_bytes"],
        "entities": doc_info["entities"],
        "raw_text_snippet": doc_info["raw_text"][:250]
    })


@product_bp.route("/documents/<string:document_id>/download", methods=["GET"])
@login_required
def download_document(document_id):
    """
    Req 1.6.v & xiv: Securely serves or downloads uploaded purchase receipts,
    invoices, warranty cards, damage photos, and repair reports.
    Enforces user access rights before serving.
    """
    doc = ClaimDocument.query.filter_by(document_id=document_id).first_or_404()
    user_id = session.get("user_id")
    user_role = session.get("role")

    # Access control verification (Req 1.6.xiv)
    is_authorized = False
    if user_role in [Config.ROLE_ADMIN, Config.ROLE_REVIEWER, Config.ROLE_STAFF]:
        is_authorized = True
    elif doc.product and doc.product.user_id == user_id:
        is_authorized = True
    elif doc.claim and doc.claim.user_id == user_id:
        is_authorized = True

    if not is_authorized:
        flash("Access denied: You do not possess permissions to view or download this document.", "danger")
        return redirect(request.referrer or url_for("auth.portal_redirect"))

    file_path = Path(doc.file_path)
    if not file_path.exists():
        flash("Document file not found on disk.", "warning")
        return redirect(request.referrer or url_for("products.list_products"))

    as_attachment = request.args.get("mode") == "download" or request.args.get("download") == "1"
    return send_file(
        file_path,
        as_attachment=as_attachment,
        download_name=doc.original_filename
    )


@product_bp.route("/documents/<string:document_id>/replace", methods=["POST"])
@login_required
def replace_document(document_id):
    """
    Req 1.6.xiv: Document Organization - Replace document.
    Allows authorized users (owner, staff, admin) to replace an existing document file
    with an updated version, recalculating checksum, file size, and re-running OCR extraction.
    """
    doc = ClaimDocument.query.filter_by(document_id=document_id).first_or_404()
    user_id = session.get("user_id")
    user_role = session.get("role")

    # Access control verification
    is_authorized = False
    if user_role in [Config.ROLE_ADMIN, Config.ROLE_STAFF]:
        is_authorized = True
    elif doc.product and doc.product.user_id == user_id:
        is_authorized = True
    elif doc.claim and doc.claim.user_id == user_id:
        if doc.claim.status not in [Config.STATUS_APPROVED, Config.STATUS_REJECTED]:
            is_authorized = True
        else:
            flash("Evidence documents cannot be altered on finalized claims.", "warning")
            return redirect(request.referrer or url_for("claims.view_claim_detail", claim_id=doc.claim.claim_id))

    if not is_authorized:
        flash("Access denied: You do not possess permissions to replace this document.", "danger")
        return redirect(request.referrer or url_for("auth.portal_redirect"))

    uploaded_file = request.files.get("replacement_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a valid replacement file.", "warning")
        return redirect(request.referrer or url_for("products.list_products"))

    from src.rules.validator import ClaimValidator
    ok, err_msg = ClaimValidator.validate_file(uploaded_file)
    if not ok:
        flash(err_msg, "danger")
        return redirect(request.referrer or url_for("products.list_products"))

    upload_folder = Path(Config.UPLOAD_DIR)
    upload_folder.mkdir(parents=True, exist_ok=True)
    clean_filename = secure_filename(uploaded_file.filename)
    dest_filename = f"rep_{doc.document_id}_{clean_filename}"
    save_path = upload_folder / dest_filename
    uploaded_file.save(save_path)

    # Recalculate file metadata & SHA-256
    doc_processor = get_document_processor()
    doc_info = doc_processor.process_document(save_path, document_type=doc.document_type)

    # Delete old file safely if different
    try:
        old_path = Path(doc.file_path)
        if old_path.exists() and old_path.resolve() != save_path.resolve():
            old_path.unlink()
    except Exception:
        pass

    prev_name = doc.original_filename
    doc.file_path = str(save_path)
    doc.original_filename = clean_filename
    doc.file_size_bytes = doc_info["file_size_bytes"]
    doc.file_hash_sha256 = doc_info["sha256_hash"]
    if doc_info.get("raw_text"):
        doc.ocr_extracted_text = doc_info["raw_text"]
        doc.ocr_data_json = json.dumps(doc_info.get("entities", {}))

    audit = AuditLog(
        user_id=user_id,
        user_role=user_role,
        action="DOCUMENT_REPLACED",
        entity_type="CLAIM_DOCUMENT",
        entity_id=doc.document_id,
        details_json=json.dumps({
            "previous_file": prev_name,
            "new_file": clean_filename,
            "new_sha256": doc.file_hash_sha256
        }),
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f"Document successfully replaced with '{clean_filename}'.", "success")
    return redirect(request.referrer or url_for("products.list_products"))


@product_bp.route("/documents/<string:document_id>/delete", methods=["POST"])
@login_required
def delete_document(document_id):
    """
    Req 1.6.xiv: Document Organization - Remove document.
    Allows authorized users (owner, staff, admin) to remove an uploaded document
    according to their access rights.
    """
    doc = ClaimDocument.query.filter_by(document_id=document_id).first_or_404()
    user_id = session.get("user_id")
    user_role = session.get("role")

    # Access control verification
    is_authorized = False
    if user_role in [Config.ROLE_ADMIN, Config.ROLE_STAFF]:
        is_authorized = True
    elif doc.product and doc.product.user_id == user_id:
        is_authorized = True
    elif doc.claim and doc.claim.user_id == user_id:
        if doc.claim.status not in [Config.STATUS_APPROVED, Config.STATUS_REJECTED]:
            is_authorized = True
        else:
            flash("Evidence documents cannot be deleted from finalized claims.", "warning")
            return redirect(request.referrer or url_for("claims.view_claim_detail", claim_id=doc.claim.claim_id))

    if not is_authorized:
        flash("Access denied: You do not possess permissions to remove this document.", "danger")
        return redirect(request.referrer or url_for("auth.portal_redirect"))

    # Safely remove file on disk
    try:
        f_path = Path(doc.file_path)
        if f_path.exists():
            f_path.unlink()
    except Exception:
        pass

    doc_name = doc.original_filename
    doc_id_val = doc.document_id

    audit = AuditLog(
        user_id=user_id,
        user_role=user_role,
        action="DOCUMENT_REMOVED",
        entity_type="CLAIM_DOCUMENT",
        entity_id=doc_id_val,
        details_json=json.dumps({"filename": doc_name}),
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.delete(doc)
    db.session.commit()

    flash(f"Document '{doc_name}' has been successfully removed.", "success")
    return redirect(request.referrer or url_for("products.list_products"))



@product_bp.route("/<string:product_id>", methods=["GET"])
@login_required
def view_product(product_id):
    """
    Detailed product overview showing hardware specifications, warranty lifecycle countdown,
    policy coverage conditions, exclusions, historical service records, and uploaded proof documents (Req iii, iv, v).
    """
    product = Product.query.filter_by(product_id=product_id).first_or_404()
    policy_rules = product.warranty.policy.get_rules() if product.warranty and product.warranty.policy else {}
    return render_template("customer/product_detail.html", product=product, policy_rules=policy_rules)


@product_bp.route("/<string:product_id>/repairs/new", methods=["POST"])
@login_required
def add_repair_record(product_id):
    """
    Req 1.6.xiii: Repair History Management
    Records previous repair dates, repair-center details, replaced parts, repair outcomes,
    repair costs, and whether each repair was completed by an authorized or unauthorized service center.
    """
    user = get_current_user()
    product = Product.query.filter_by(product_id=product_id).first_or_404()

    # Permission check: owner, service center staff, or administrator
    if session.get("role") not in [Config.ROLE_ADMIN, Config.ROLE_STAFF] and product.user_id != user.id:
        flash("You do not have authorization to log repairs for this equipment asset.", "danger")
        return redirect(url_for("products.view_product", product_id=product.product_id))

    repair_date_str = request.form.get("repair_date")
    repair_center = request.form.get("repair_center", "").strip()
    replaced_parts = request.form.get("replaced_parts", "").strip()
    outcome = request.form.get("outcome", "Repaired").strip()
    repair_cost_str = request.form.get("repair_cost", "0.0")
    is_authorized = request.form.get("is_authorized_center") in ["true", "1", "on", "yes", True]
    notes = request.form.get("notes", "").strip()

    try:
        repair_date = datetime.strptime(repair_date_str, "%Y-%m-%d").date()
    except Exception:
        repair_date = date.today()

    try:
        repair_cost = float(repair_cost_str)
    except ValueError:
        repair_cost = 0.0

    repair = RepairHistory(
        product_id=product.id,
        repair_date=repair_date,
        repair_center=repair_center or "Authorized Service Center",
        replaced_parts=replaced_parts or "None / Inspection Only",
        outcome=outcome,
        repair_cost=repair_cost,
        is_authorized_center=is_authorized,
        notes=notes
    )
    db.session.add(repair)

    AuditLog.log_event(
        action="REPAIR_RECORDED",
        user_id=user.id,
        user_role=session.get("role"),
        entity_type="Product",
        entity_id=product.product_id,
        details={
            "repair_id": repair.repair_id,
            "repair_center": repair_center,
            "is_authorized": is_authorized,
            "outcome": outcome,
            "cost": repair_cost
        }
    )
    db.session.commit()

    flash(f"Service and maintenance record {repair.repair_id} recorded successfully (Req 1.6.xiii).", "success")
    return redirect(url_for("products.view_product", product_id=product.product_id))

