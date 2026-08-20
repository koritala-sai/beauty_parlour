from functools import wraps
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
)

from flask_login import login_required, current_user

from sqlalchemy import func

from extensions import db

from models import (
    Booking,
    Service,
    Staff,
    User,
    Review,
    PromoCode,
    auto_complete_past_bookings,
)

from notifications import send_booking_cancellation_email

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view_func):
    """
    Restrict admin pages to admin users only.
    """

    @wraps(view_func)
    @login_required
    def wrapped(*args, **kwargs):

        if not current_user.is_admin:
            flash("Admin access only.", "error")
            return redirect(url_for("main.home"))

        return view_func(*args, **kwargs)

    return wrapped


# ===========================================================
# Dashboard
# ===========================================================

@admin_bp.route("/")
@admin_required
def dashboard():

    auto_complete_past_bookings()

    active_bookings = (
        Booking.query
        .filter(Booking.status != "cancelled")
        .order_by(Booking.booking_date.desc())
        .limit(50)
        .all()
    )

    cancelled_bookings = (
        Booking.query
        .filter_by(status="cancelled")
        .order_by(Booking.booking_date.desc())
        .all()
    )

    total_revenue = (
        db.session.query(func.sum(Service.price))
        .join(Booking, Booking.service_id == Service.id)
        .filter(Booking.payment_status == "paid")
        .scalar()
    )

    stats = {
        "today":
        Booking.query.filter_by(
            booking_date=date.today()
        ).count(),

        "total":
        Booking.query.count(),

        "pending":
        Booking.query.filter_by(
            status="pending"
        ).count(),

        "completed":
        Booking.query.filter_by(
            status="completed"
        ).count(),

        "cancelled":
        Booking.query.filter_by(
            status="cancelled"
        ).count(),

        "customers":
        User.query.filter_by(
            is_admin=False
        ).count(),

        "staff":
        Staff.query.count(),

        "services":
        Service.query.count(),

        "reviews":
        Review.query.count(),

        "revenue":
        total_revenue or 0,
    }

    return render_template(
        "admin/dashboard.html",
        bookings=active_bookings,
        cancelled_bookings=cancelled_bookings,
        stats=stats,
    )


# ===========================================================
# Services
# ===========================================================

@admin_bp.route("/services")
@admin_required
def manage_services():

    services = Service.query.order_by(Service.name).all()

    return render_template(
        "admin/services.html",
        services=services
    )


@admin_bp.route("/services/add", methods=["POST"])
@admin_required
def add_service():

    name = request.form.get("name", "").strip()[:120]

    category = request.form.get(
        "category",
        ""
    ).strip()[:80]

    description = request.form.get(
        "description",
        ""
    ).strip()[:500]

    price = request.form.get(
        "price",
        "0"
    )

    duration = request.form.get(
        "duration_minutes",
        "30"
    )

    if not name:
        flash("Service name is required.", "error")
        return redirect(url_for("admin.manage_services"))

    try:

        price = float(price)
        duration = int(duration)

        if price < 0 or duration < 5:
            raise ValueError

    except ValueError:

        flash(
            "Invalid price or duration (min 5 minutes).",
            "error"
        )

        return redirect(url_for("admin.manage_services"))

    service = Service(
        name=name,
        category=category,
        description=description or None,
        price=price,
        duration_minutes=duration,
    )

    db.session.add(service)
    db.session.commit()

    flash(
        f"{name} added successfully.",
        "success"
    )

    return redirect(url_for("admin.manage_services"))


@admin_bp.route("/services/<int:service_id>/toggle", methods=["POST"])
@admin_required
def toggle_service(service_id):

    service = Service.query.get_or_404(service_id)

    service.is_active = not service.is_active

    db.session.commit()

    flash(
        f"{service.name} is now {'Active' if service.is_active else 'Inactive'}",
        "success"
    )

    return redirect(url_for("admin.manage_services"))


# ===========================================================
# Booking Status
# ===========================================================

@admin_bp.route("/booking/<int:booking_id>/status", methods=["POST"])
@admin_required
def update_booking_status(booking_id):

    booking = Booking.query.get_or_404(booking_id)

    new_status = request.form.get("status")

    allowed = {"pending", "completed", "cancelled"}
    if new_status and new_status in allowed:
        reason = request.form.get("cancellation_reason", "").strip()
        if new_status == "cancelled":
            if not reason:
                flash("Please enter a reason for cancelling this customer booking.", "error")
                return redirect(url_for("admin.dashboard"))
            booking.cancellation_reason = reason
        booking.status = new_status
        db.session.commit()

        if new_status == "cancelled":
            sent = send_booking_cancellation_email(booking, reason=booking.cancellation_reason)
            if sent:
                flash("Booking status updated to Cancelled. Cancellation email sent to customer.", "success")
            else:
                flash("Booking status updated to Cancelled.", "success")
        else:
            flash("Booking status updated successfully.", "success")
    else:
        flash("Invalid booking status.", "error")

    return redirect(url_for("admin.dashboard"))


# ===========================================================
# Staff Management
# ===========================================================

@admin_bp.route("/staff")
@admin_required
def manage_staff():

    staff_members = Staff.query.order_by(Staff.name).all()

    return render_template(
        "admin/staff.html",
        staff_members=staff_members
    )


# -----------------------------------------------------------

@admin_bp.route("/staff/add", methods=["POST"])
@admin_required
def add_staff():

    name = request.form.get("name", "").strip()[:120]
    specialties = request.form.get("specialties", "").strip()[:255]

    if not name:
        flash("Staff name is required.", "error")
        return redirect(url_for("admin.manage_staff"))

    staff = Staff(
        name=name,
        specialties=specialties
    )

    db.session.add(staff)
    db.session.commit()

    flash(
        f"{name} added successfully.",
        "success"
    )

    return redirect(url_for("admin.manage_staff"))


# -----------------------------------------------------------

@admin_bp.route("/staff/<int:staff_id>/toggle", methods=["POST"])
@admin_required
def toggle_staff(staff_id):

    staff = Staff.query.get_or_404(staff_id)

    staff.is_active = not staff.is_active

    db.session.commit()

    state = "Active" if staff.is_active else "Inactive"

    flash(
        f"{staff.name} is now {state}.",
        "success"
    )

    return redirect(url_for("admin.manage_staff"))


# -----------------------------------------------------------

@admin_bp.route("/staff/edit/<int:staff_id>", methods=["GET", "POST"])
@admin_required
def edit_staff(staff_id):

    staff = Staff.query.get_or_404(staff_id)

    if request.method == "POST":

        staff.name = request.form.get("name", "").strip()[:120]

        staff.specialties = request.form.get(
            "specialties",
            ""
        ).strip()[:255]

        db.session.commit()

        flash(
            "Staff updated successfully.",
            "success"
        )

        return redirect(url_for("admin.manage_staff"))

    return render_template(
        "admin/edit_staff.html",
        staff=staff
    )


# -----------------------------------------------------------

@admin_bp.route("/staff/delete/<int:staff_id>", methods=["POST"])
@admin_required
def delete_staff(staff_id):

    staff = Staff.query.get_or_404(staff_id)

    # Don't allow deleting if bookings exist
    if staff.bookings:

        flash(
            "Cannot delete this staff member because previous bookings exist.",
            "error"
        )

        return redirect(url_for("admin.manage_staff"))

    db.session.delete(staff)
    db.session.commit()

    flash(
        "Staff deleted successfully.",
        "success"
    )

    return redirect(url_for("admin.manage_staff"))


# ===========================================================
# Review Moderation
# ===========================================================

@admin_bp.route("/reviews")
@admin_required
def manage_reviews():
    reviews = (
        Review.query
        .order_by(Review.created_at.desc())
        .all()
    )
    return render_template("admin/reviews.html", reviews=reviews)


@admin_bp.route("/reviews/<int:review_id>/toggle", methods=["POST"])
@admin_required
def toggle_review_visibility(review_id):
    review = Review.query.get_or_404(review_id)
    review.is_hidden = not review.is_hidden
    db.session.commit()

    state = "hidden" if review.is_hidden else "visible"
    flash(f"Review #{review.id} is now {state}.", "success")
    return redirect(url_for("admin.manage_reviews"))


@admin_bp.route("/reviews/<int:review_id>/delete", methods=["POST"])
@admin_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    db.session.delete(review)
    db.session.commit()

    flash("Review deleted permanently.", "success")
    return redirect(url_for("admin.manage_reviews"))


# ===========================================================
# Promo Code Management
# ===========================================================

@admin_bp.route("/promos")
@admin_required
def manage_promos():
    promos = PromoCode.query.order_by(PromoCode.created_at.desc()).all()
    return render_template("admin/promos.html", promos=promos)


@admin_bp.route("/promos/add", methods=["POST"])
@admin_required
def add_promo():
    code = request.form.get("code", "").strip().upper()[:30]

    if not code:
        flash("Promo code is required.", "error")
        return redirect(url_for("admin.manage_promos"))

    if PromoCode.query.filter_by(code=code).first():
        flash("A promo code with that name already exists.", "error")
        return redirect(url_for("admin.manage_promos"))

    try:
        discount_percent = Decimal(request.form.get("discount_percent", "0") or "0")
        discount_flat = Decimal(request.form.get("discount_flat", "0") or "0")
        min_order = Decimal(request.form.get("min_order", "0") or "0")
    except InvalidOperation:
        flash("Invalid numeric value.", "error")
        return redirect(url_for("admin.manage_promos"))

    max_uses_raw = request.form.get("max_uses", "").strip()
    max_uses = int(max_uses_raw) if max_uses_raw.isdigit() else None

    valid_from_raw = request.form.get("valid_from", "").strip()
    valid_until_raw = request.form.get("valid_until", "").strip()

    try:
        valid_from = datetime.strptime(valid_from_raw, "%Y-%m-%d").date() if valid_from_raw else None
        valid_until = datetime.strptime(valid_until_raw, "%Y-%m-%d").date() if valid_until_raw else None
    except ValueError:
        flash("Invalid date format.", "error")
        return redirect(url_for("admin.manage_promos"))

    promo = PromoCode(
        code=code,
        discount_percent=discount_percent,
        discount_flat=discount_flat,
        min_order=min_order,
        max_uses=max_uses,
        valid_from=valid_from,
        valid_until=valid_until,
    )

    db.session.add(promo)
    db.session.commit()

    flash(f"Promo code '{code}' created successfully.", "success")
    return redirect(url_for("admin.manage_promos"))


@admin_bp.route("/promos/<int:promo_id>/toggle", methods=["POST"])
@admin_required
def toggle_promo(promo_id):
    promo = PromoCode.query.get_or_404(promo_id)
    promo.is_active = not promo.is_active
    db.session.commit()

    state = "Active" if promo.is_active else "Inactive"
    flash(f"Promo '{promo.code}' is now {state}.", "success")
    return redirect(url_for("admin.manage_promos"))


@admin_bp.route("/promos/<int:promo_id>/delete", methods=["POST"])
@admin_required
def delete_promo(promo_id):
    promo = PromoCode.query.get_or_404(promo_id)

    if promo.bookings:
        flash("Cannot delete — this code has been used in bookings. Deactivate it instead.", "error")
        return redirect(url_for("admin.manage_promos"))

    db.session.delete(promo)
    db.session.commit()

    flash("Promo code deleted.", "success")
    return redirect(url_for("admin.manage_promos"))