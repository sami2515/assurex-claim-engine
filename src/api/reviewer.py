import json
from datetime import datetime
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template
from config.config import Config
from database.db import db
from src.models.entities import Claim, ClaimStatusHistory, ReviewerAction, Notification, AuditLog
from src.api.auth import login_required, role_required, get_current_user

reviewer_bp = Blueprint("reviewer", __name__, url_prefix="/reviewer")


@reviewer_bp.route("/queue", methods=["GET"])
@login_required
@role_required(Config.ROLE_REVIEWER, Config.ROLE_ADMIN)
def queue():
    """Dedicated manual review triage queue with multi-criteria filtering."""
    status_filter = request.args.get("status", Config.STATUS_MANUAL_REVIEW)
    risk_filter = request.args.get("risk", "ALL")
    category_filter = request.args.get("category", "ALL")

    query = Claim.query

    if status_filter != "ALL":
        query = query.filter(Claim.status == status_filter)

    if risk_filter != "ALL":
        query = query.filter(Claim.risk_level == risk_filter)

    if category_filter != "ALL":
        query = query.join(Claim.product).filter(Claim.product.has(category=category_filter))

    claims = query.order_by(Claim.created_at.desc()).all()

    return render_template(
        "reviewer/queue.html",
        claims=claims,
        current_status=status_filter,
        current_risk=risk_filter,
        current_category=category_filter,
        all_statuses=Config.ALL_CLAIM_STATUSES
    )


@reviewer_bp.route("/claim/<string:claim_id>", methods=["GET"])
@login_required
@role_required(Config.ROLE_REVIEWER, Config.ROLE_ADMIN)
def inspect_claim(claim_id):
    """Detailed inspection workspace with side-by-side evidence, AI summary, comparison, and override controls."""
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    from src.core.decision_engine import get_decision_engine
    engine = get_decision_engine()
    ai_summary = engine.generate_claim_summary(claim)
    decision_explanation = engine.generate_decision_explanation(claim)
    return render_template(
        "reviewer/claim_inspect.html",
        claim=claim,
        ai_summary=ai_summary,
        decision_explanation=decision_explanation
    )


@reviewer_bp.route("/claim/<string:claim_id>/adjudicate", methods=["POST"])
@login_required
@role_required(Config.ROLE_REVIEWER, Config.ROLE_ADMIN)
def adjudicate(claim_id):
    """
    Reviewer decision adjudication and override handler.
    Preserves original AI results and logs override justification.
    """
    user = get_current_user()
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()

    action = request.form.get("action")  # 'APPROVE', 'REJECT', 'REQUEST_INFO'
    comments = request.form.get("comments", "").strip()
    override_reason = request.form.get("override_reason", "").strip()

    if not comments:
        flash("Reviewer comments are mandatory for audit compliance.", "warning")
        return redirect(url_for("reviewer.inspect_claim", claim_id=claim_id))

    old_status = claim.status
    automated_rec = claim.final_decision or "Manual Review Required"
    is_override = False

    if action == "APPROVE":
        new_status = Config.STATUS_APPROVED
        new_decision = "Approved"
        if automated_rec != "Likely Valid":
            is_override = True
    elif action == "REJECT":
        new_status = Config.STATUS_REJECTED
        new_decision = "Rejected"
        if automated_rec != "Likely Invalid":
            is_override = True
    elif action == "REQUEST_INFO":
        new_status = Config.STATUS_ADDITIONAL_INFO
        new_decision = "Additional Information Required"
    elif action == "CLOSE":
        new_status = Config.STATUS_CLOSED
        new_decision = "Closed"
    else:
        flash("Invalid reviewer adjudication action.", "danger")
        return redirect(url_for("reviewer.inspect_claim", claim_id=claim_id))

    # Update Claim
    claim.status = new_status
    claim.reviewer_notes = comments
    claim.assigned_reviewer_id = user.id

    # Record ClaimStatusHistory
    status_log = ClaimStatusHistory(
        claim_id=claim.id,
        previous_status=old_status,
        new_status=new_status,
        changed_by_user_id=user.id,
        reason_comment=f"Reviewer Action: {new_decision}. Notes: {comments}"
    )
    db.session.add(status_log)

    # Record ReviewerAction with override audit trail
    action_log = ReviewerAction(
        claim_id=claim.id,
        reviewer_id=user.id,
        previous_recommendation=automated_rec,
        reviewer_decision=new_decision,
        is_override=is_override,
        override_reason=(override_reason or comments) if is_override else None,
        comments=comments
    )
    db.session.add(action_log)

    # Notify Claimant across all SRS 1.6.xxxix event types:
    # (status changes, requests for additional info, approval, rejection, review completion)
    product_name = claim.product.product_name if claim.product else "Asset"
    product_id_val = claim.product.product_id if claim.product else None

    # 1. Primary Action Notification (Approval / Rejection / Additional Info / Closure)
    if action == "APPROVE":
        primary_notif = Notification(
            user_id=claim.user_id,
            notification_type=Config.NOTIF_TYPE_APPROVAL,
            title=f"Claim Approved: {claim.claim_id}",
            message=f"Official Approval: Your warranty claim {claim.claim_id} for '{product_name}' has been approved by authorized reviewer {user.full_name}. Adjudication notes: {comments}",
            related_claim_id=claim.claim_id,
            related_product_id=product_id_val
        )
        db.session.add(primary_notif)
    elif action == "REJECT":
        primary_notif = Notification(
            user_id=claim.user_id,
            notification_type=Config.NOTIF_TYPE_REJECTION,
            title=f"Claim Rejected: {claim.claim_id}",
            message=f"Adjudication Notice: Claim {claim.claim_id} for '{product_name}' has been rejected by authorized reviewer {user.full_name}. Rationale: {comments}",
            related_claim_id=claim.claim_id,
            related_product_id=product_id_val
        )
        db.session.add(primary_notif)
    elif action == "REQUEST_INFO":
        primary_notif = Notification(
            user_id=claim.user_id,
            notification_type=Config.NOTIF_TYPE_ADDITIONAL_INFO,
            title=f"Action Required: Information Requested for Claim {claim.claim_id}",
            message=f"Reviewer {user.full_name} has requested additional evidence for '{product_name}': {comments}. Please upload requested documents via the claim dossier.",
            related_claim_id=claim.claim_id,
            related_product_id=product_id_val
        )
        db.session.add(primary_notif)

    # 2. General Lifecycle Status Change Notification
    status_notif = Notification(
        user_id=claim.user_id,
        notification_type=Config.NOTIF_TYPE_STATUS_CHANGE,
        title=f"Claim {claim.claim_id} Status: {new_status}",
        message=f"Claim status for '{product_name}' transitioned from '{old_status}' to '{new_status}'. Reviewer note: {comments}",
        related_claim_id=claim.claim_id,
        related_product_id=product_id_val
    )
    db.session.add(status_notif)

    # 3. Review Completion Notification
    if action in ["APPROVE", "REJECT", "CLOSE"]:
        review_comp_notif = Notification(
            user_id=claim.user_id,
            notification_type=Config.NOTIF_TYPE_REVIEW_COMPLETE,
            title=f"Adjudication Review Completed: {claim.claim_id}",
            message=f"The formal warranty review process for claim {claim.claim_id} has concluded with adjudication outcome: '{new_decision}'.",
            related_claim_id=claim.claim_id,
            related_product_id=product_id_val
        )
        db.session.add(review_comp_notif)

    # System Audit
    audit = AuditLog(
        user_id=user.id,
        user_role=user.role,
        action="REVIEWER_ADJUDICATION",
        entity_type="Claim",
        entity_id=claim.claim_id,
        ip_address=request.remote_addr,
        details_json=json.dumps({
            "action": action,
            "new_status": new_status,
            "is_override": is_override,
            "override_reason": override_reason
        })
    )
    db.session.add(audit)

    if new_status in [Config.STATUS_APPROVED, Config.STATUS_REJECTED]:
        final_audit = AuditLog(
            user_id=user.id,
            user_role=user.role,
            action="FINAL_DECISION",
            entity_type="Claim",
            entity_id=claim.claim_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({
                "outcome": new_status,
                "decision": new_decision,
                "adjudicated_by": user.full_name
            })
        )
        db.session.add(final_audit)

    db.session.commit()

    flash(f"Claim {claim.claim_id} adjudicated successfully as '{new_status}'!", "success")
    return redirect(url_for("reviewer.queue"))
