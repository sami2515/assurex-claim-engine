from datetime import datetime, date, timedelta
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template
from config.config import Config
from database.db import db
from src.models.entities import Product, ProductWarranty, WarrantyPolicy, RepairHistory, Notification, AuditLog
from src.api.auth import login_required, get_current_user

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

        # Record Audit Log
        audit = AuditLog(
            user_id=user.id,
            user_role=session.get("role"),
            action="PRODUCT_REGISTERED",
            entity_type="PRODUCT",
            entity_id=product.product_id,
            ip_address=request.remote_addr
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


@product_bp.route("/<string:product_id>", methods=["GET"])
@login_required
def view_product(product_id):
    """
    Detailed product overview showing hardware specifications, warranty lifecycle countdown,
    policy coverage conditions, exclusions, and historical service records (Req iii & iv).
    """
    product = Product.query.filter_by(product_id=product_id).first_or_404()
    policy_rules = product.warranty.policy.get_rules() if product.warranty and product.warranty.policy else {}
    return render_template("customer/product_detail.html", product=product, policy_rules=policy_rules)
