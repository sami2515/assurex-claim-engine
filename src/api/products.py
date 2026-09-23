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
    """Displays registered products and warranty statuses for the active user."""
    user = get_current_user()
    if session.get("role") in [Config.ROLE_ADMIN, Config.ROLE_STAFF, Config.ROLE_REVIEWER]:
        products = Product.query.order_by(Product.created_at.desc()).all()
    else:
        products = Product.query.filter_by(user_id=user.id).order_by(Product.created_at.desc()).all()

    return render_template("customer/products_list.html", products=products)


@product_bp.route("/register", methods=["GET", "POST"])
@login_required
def register_product():
    """Req iii & iv: Product intake and automatic warranty record assignment."""
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

        if not product_name or not serial_number or not purchase_date_str:
            flash("Product name, serial number, and purchase date are mandatory.", "warning")
            return render_template("customer/product_register.html", categories=Config.ALL_CLAIM_CLASSES)

        # Parse purchase date
        try:
            p_date = datetime.strptime(purchase_date_str, "%Y-%m-%d").date()
        except ValueError:
            p_date = date.today()

        # Check existing serial
        existing = Product.query.filter_by(serial_number=serial_number).first()
        if existing:
            flash(f"A product with serial number '{serial_number}' is already registered.", "danger")
            return render_template("customer/product_register.html")

        # 1. Create Product Entity
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

        # 2. Attach Warranty Policy Based on Category (Req iv)
        policy = WarrantyPolicy.query.filter_by(category=category).first()
        duration_months = policy.coverage_duration_months if policy else 12
        w_start = p_date
        w_expiry = w_start + timedelta(days=duration_months * 30)

        warranty = ProductWarranty(
            product_id=product.id,
            policy_id=policy.id if policy else 1,
            warranty_provider=f"{brand} Official Care",
            start_date=w_start,
            expiry_date=w_expiry,
            service_center_name="Authorized National Service Network"
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

        flash(f"Product '{product_name}' registered successfully with active warranty coverage!", "success")
        return redirect(url_for("products.list_products"))

    policies = WarrantyPolicy.query.all()
    return render_template("customer/product_register.html", policies=policies)


@product_bp.route("/<string:product_id>", methods=["GET"])
@login_required
def view_product(product_id):
    """Detailed product overview showing warranty lifecycle countdown and repair history."""
    product = Product.query.filter_by(product_id=product_id).first_or_404()
    return render_template("customer/product_detail.html", product=product)
