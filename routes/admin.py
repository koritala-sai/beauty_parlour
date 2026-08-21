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
    current_app,
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
    """Restrict admin pages to admin users only."""

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
        .order_by(
            Booking.booking_date.desc(),
            Booking.booking_time.desc()
        )
        .limit(50)
        .all()
    )

    cancelled_bookings = (
        Booking.query
        .filter_by(status="cancelled")
        .order_by(
            Booking.booking_date.desc(),
            Booking.booking_time.desc()
        )
        .all()
    )

    total_revenue = (
        db.session.query(func.sum(Service.price))
        .join(Booking, Booking.service_id == Service.id)
        .filter(Booking.payment_status == "paid")
        .scalar()
    )

    stats = {
        "today": Booking.query.filter_by(
            booking_date=date.today()
        ).count(),

        "total": Booking.query.count(),

        "pending": Booking.query.filter_by(
            status="pending"
        ).count(),

        "completed": Booking.query.filter_by(
            status="completed"
        ).count(),

        "cancelled": Booking.query.filter_by(
            status="cancelled"
        ).count(),

        "customers": User.query.filter_by(
            is_admin=False
        ).count(),

        "staff": Staff.query.count(),

        "services": Service.query.count(),

        "reviews": Review.query.count(),

        "revenue": total_revenue or 0,
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
        services=services,
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
            "Invalid price or duration (minimum duration is 5 minutes).",
            "error"
        )
        return redirect(url_for("admin.manage_services"))

    try:
        service = Service(
            name=name,
            category=category,
            description=description or None,
            price=price,
            duration_minutes=duration,
        )

        db.session.add(service)
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Database error while adding service"
        )

        flash(
            "Unable to add service. Please try again.",
            "error"
        )
        return redirect(url_for("admin.manage_services"))

    flash(
        f"{name} added successfully.",
        "success"
    )

    return redirect(url_for("admin.manage_services"))


@admin_bp.route(
    "/services/<int:service_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_service(service_id):

    service = Service.query.get_or_404(service_id)

    try:
        service.is_active = not service.is_active
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Database error while toggling service %s",
            service_id
        )

        flash(
            "Unable to update service status.",
            "error"
        )
        return redirect(url_for("admin.manage_services"))

    flash(
        f"{service.name} is now "
        f"{'Active' if service.is_active else 'Inactive'}.",
        "success"
    )

    return redirect(url_for("admin.manage_services"))


# ===========================================================
# Booking Status
# ===========================================================

@admin_bp.route(
    "/booking/<int:booking_id>/status",
    methods=["POST"]
)
@admin_required
def update_booking_status(booking_id):

    booking = Booking.query.get_or_404(booking_id)

    new_status = request.form.get(
        "status",
        ""
    ).strip().lower()

    allowed = {
        "pending",
        "confirmed",
        "completed",
        "cancelled",
    }

    if new_status not in allowed:
        flash("Invalid booking status.", "error")
        return redirect(url_for("admin.dashboard"))

    # Do not allow changes after completion
    if booking.status == "completed" and new_status != "completed":
        flash(
            "Completed bookings cannot be changed.",
            "error"
        )
        return redirect(url_for("admin.dashboard"))

    # Do not allow changing cancelled booking back accidentally
    if booking.status == "cancelled" and new_status != "cancelled":
        flash(
            "Cancelled bookings cannot be changed.",
            "error"
        )
        return redirect(url_for("admin.dashboard"))

    reason = request.form.get(
        "cancellation_reason",
        ""
    ).strip()[:500]

    if new_status == "cancelled" and not reason:
        flash(
            "Please enter a reason for cancelling this customer booking.",
            "error"
        )
        return redirect(url_for("admin.dashboard"))

    try:
        booking.status = new_status

        if new_status == "cancelled":
            if hasattr(booking, "cancellation_reason"):
                booking.cancellation_reason = reason

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while updating booking %s",
            booking_id
        )

        flash(
            "Unable to update booking status. Please try again.",
            "error"
        )

        return redirect(url_for("admin.dashboard"))

    # Database update succeeded.
    # Only now send cancellation email.
    if new_status == "cancelled":

        try:
            email_sent = send_booking_cancellation_email(booking)
        except Exception:
            # Extra safety even though notifications.py
            # should handle its own errors.
            current_app.logger.exception(
                "Unexpected cancellation email error for booking %s",
                booking_id
            )
            email_sent = False

        if email_sent:
            flash(
                "Booking cancelled successfully and "
                "a cancellation email was sent to the customer.",
                "success"
            )
        else:
            flash(
                "Booking cancelled successfully. "
                "The booking was saved, but the cancellation email "
                "could not be sent.",
                "success"
            )

    else:
        flash(
            f"Booking status updated to {new_status.title()} successfully.",
            "success"
        )

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
        staff_members=staff_members,
    )


@admin_bp.route("/staff/add", methods=["POST"])
@admin_required
def add_staff():

    name = request.form.get(
        "name",
        ""
    ).strip()[:120]

    specialties = request.form.get(
        "specialties",
        ""
    ).strip()[:255]

    if not name:
        flash("Staff name is required.", "error")
        return redirect(url_for("admin.manage_staff"))

    try:
        staff = Staff(
            name=name,
            specialties=specialties,
        )

        db.session.add(staff)
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while adding staff"
        )

        flash(
            "Unable to add staff member. Please try again.",
            "error"
        )

        return redirect(url_for("admin.manage_staff"))

    flash(
        f"{name} added successfully.",
        "success"
    )

    return redirect(url_for("admin.manage_staff"))


@admin_bp.route(
    "/staff/<int:staff_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_staff(staff_id):

    staff = Staff.query.get_or_404(staff_id)

    try:
        staff.is_active = not staff.is_active
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while toggling staff %s",
            staff_id
        )

        flash(
            "Unable to update staff status.",
            "error"
        )

        return redirect(url_for("admin.manage_staff"))

    state = "Active" if staff.is_active else "Inactive"

    flash(
        f"{staff.name} is now {state}.",
        "success"
    )

    return redirect(url_for("admin.manage_staff"))


@admin_bp.route(
    "/staff/edit/<int:staff_id>",
    methods=["GET", "POST"]
)
@admin_required
def edit_staff(staff_id):

    staff = Staff.query.get_or_404(staff_id)

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()[:120]

        specialties = request.form.get(
            "specialties",
            ""
        ).strip()[:255]

        if not name:
            flash("Staff name is required.", "error")
            return render_template(
                "admin/edit_staff.html",
                staff=staff,
            )

        try:
            staff.name = name
            staff.specialties = specialties

            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Database error while editing staff %s",
                staff_id
            )

            flash(
                "Unable to update staff member.",
                "error"
            )

            return render_template(
                "admin/edit_staff.html",
                staff=staff,
            )

        flash(
            "Staff updated successfully.",
            "success"
        )

        return redirect(url_for("admin.manage_staff"))

    return render_template(
        "admin/edit_staff.html",
        staff=staff,
    )


@admin_bp.route(
    "/staff/delete/<int:staff_id>",
    methods=["POST"]
)
@admin_required
def delete_staff(staff_id):

    staff = Staff.query.get_or_404(staff_id)

    if staff.bookings:
        flash(
            "Cannot delete this staff member because previous "
            "bookings exist.",
            "error"
        )
        return redirect(url_for("admin.manage_staff"))

    try:
        db.session.delete(staff)
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while deleting staff %s",
            staff_id
        )

        flash(
            "Unable to delete staff member.",
            "error"
        )

        return redirect(url_for("admin.manage_staff"))

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

    return render_template(
        "admin/reviews.html",
        reviews=reviews,
    )


@admin_bp.route(
    "/reviews/<int:review_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_review_visibility(review_id):

    review = Review.query.get_or_404(review_id)

    try:
        review.is_hidden = not review.is_hidden
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while toggling review %s",
            review_id
        )

        flash(
            "Unable to update review visibility.",
            "error"
        )

        return redirect(url_for("admin.manage_reviews"))

    state = "hidden" if review.is_hidden else "visible"

    flash(
        f"Review #{review.id} is now {state}.",
        "success"
    )

    return redirect(url_for("admin.manage_reviews"))


@admin_bp.route(
    "/reviews/<int:review_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_review(review_id):

    review = Review.query.get_or_404(review_id)

    try:
        db.session.delete(review)
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while deleting review %s",
            review_id
        )

        flash(
            "Unable to delete review.",
            "error"
        )

        return redirect(url_for("admin.manage_reviews"))

    flash(
        "Review deleted permanently.",
        "success"
    )

    return redirect(url_for("admin.manage_reviews"))


# ===========================================================
# Promo Code Management
# ===========================================================

@admin_bp.route("/promos")
@admin_required
def manage_promos():

    promos = (
        PromoCode.query
        .order_by(PromoCode.created_at.desc())
        .all()
    )

    return render_template(
        "admin/promos.html",
        promos=promos,
    )


@admin_bp.route("/promos/add", methods=["POST"])
@admin_required
def add_promo():

    code = request.form.get(
        "code",
        ""
    ).strip().upper()[:30]

    if not code:
        flash(
            "Promo code is required.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    if PromoCode.query.filter_by(code=code).first():
        flash(
            "A promo code with that name already exists.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    try:
        discount_percent = Decimal(
            request.form.get(
                "discount_percent",
                "0"
            ) or "0"
        )

        discount_flat = Decimal(
            request.form.get(
                "discount_flat",
                "0"
            ) or "0"
        )

        min_order = Decimal(
            request.form.get(
                "min_order",
                "0"
            ) or "0"
        )

    except InvalidOperation:
        flash(
            "Invalid numeric value.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    if (
        discount_percent < 0
        or discount_percent > 100
        or discount_flat < 0
        or min_order < 0
    ):
        flash(
            "Please enter valid positive discount values.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    max_uses_raw = request.form.get(
        "max_uses",
        ""
    ).strip()

    max_uses = (
        int(max_uses_raw)
        if max_uses_raw.isdigit()
        else None
    )

    valid_from_raw = request.form.get(
        "valid_from",
        ""
    ).strip()

    valid_until_raw = request.form.get(
        "valid_until",
        ""
    ).strip()

    try:
        valid_from = (
            datetime.strptime(
                valid_from_raw,
                "%Y-%m-%d"
            ).date()
            if valid_from_raw
            else None
        )

        valid_until = (
            datetime.strptime(
                valid_until_raw,
                "%Y-%m-%d"
            ).date()
            if valid_until_raw
            else None
        )

    except ValueError:
        flash(
            "Invalid date format.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    if (
        valid_from
        and valid_until
        and valid_until < valid_from
    ):
        flash(
            "Expiry date cannot be before the start date.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    try:
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

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while creating promo %s",
            code
        )

        flash(
            "Unable to create promo code.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    flash(
        f"Promo code '{code}' created successfully.",
        "success"
    )

    return redirect(url_for("admin.manage_promos"))


@admin_bp.route(
    "/promos/<int:promo_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_promo(promo_id):

    promo = PromoCode.query.get_or_404(promo_id)

    try:
        promo.is_active = not promo.is_active
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while toggling promo %s",
            promo_id
        )

        flash(
            "Unable to update promo status.",
            "error"
        )

        return redirect(url_for("admin.manage_promos"))

    state = "Active" if promo.is_active else "Inactive"

    flash(
        f"Promo '{promo.code}' is now {state}.",
        "success"
    )

    return redirect(url_for("admin.manage_promos"))


@admin_bp.route(
    "/promos/<int:promo_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_promo(promo_id):

    promo = PromoCode.query.get_or_404(promo_id)

    if promo.bookings:
        flash(
            "Cannot delete this code because it has already "
            "been used in bookings. Deactivate it instead.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    try:
        db.session.delete(promo)
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while deleting promo %s",
            promo_id
        )

        flash(
            "Unable to delete promo code.",
            "error"
        )
        return redirect(url_for("admin.manage_promos"))

    flash(
        "Promo code deleted.",
        "success"
    )

    return redirect(url_for("admin.manage_promos"))