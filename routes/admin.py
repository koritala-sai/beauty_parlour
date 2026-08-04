from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import Booking, Service, Staff, auto_complete_past_bookings

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view_func):
    """Blocks non-admin users from admin routes, even if they're logged in."""

    @wraps(view_func)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash("Admin access only.", "error")
            return redirect(url_for("main.home"))
        return view_func(*args, **kwargs)

    return wrapped


@admin_bp.route("/")
@admin_required
def dashboard():
    auto_complete_past_bookings()

    # Active bookings table (excludes cancelled)
    active_bookings = (
        Booking.query.filter(Booking.status != "cancelled")
        .order_by(Booking.booking_date.desc())
        .limit(50)
        .all()
    )

    # Cancelled bookings table
    cancelled_bookings = (
        Booking.query.filter_by(status="cancelled")
        .order_by(Booking.booking_date.desc())
        .all()
    )

    # Quick stats for admin dashboard cards
    from datetime import date
    stats = {
        "total": Booking.query.count(),
        "pending": Booking.query.filter_by(status="pending").count(),
        "confirmed": Booking.query.filter_by(status="confirmed").count(),
        "today": Booking.query.filter_by(booking_date=date.today()).count(),
        "completed": Booking.query.filter_by(status="completed").count(),
        "cancelled": Booking.query.filter_by(status="cancelled").count(),
    }
    return render_template(
        "admin/dashboard.html",
        bookings=active_bookings,
        cancelled_bookings=cancelled_bookings,
        stats=stats
    )


@admin_bp.route("/services")
@admin_required
def manage_services():
    services = Service.query.all()
    return render_template("admin/services.html", services=services)


@admin_bp.route("/services/add", methods=["POST"])
@admin_required
def add_service():
    name = request.form.get("name", "").strip()
    price = request.form.get("price", "0")
    duration = request.form.get("duration_minutes", "30")
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip() or None

    if not name:
        flash("Service name is required.", "error")
        return redirect(url_for("admin.manage_services"))

    try:
        price_val = float(price)
        duration_val = int(duration)
    except ValueError:
        flash("Price and duration must be valid numbers.", "error")
        return redirect(url_for("admin.manage_services"))

    service = Service(
        name=name,
        category=category,
        description=description,
        price=price_val,
        duration_minutes=duration_val,
    )
    db.session.add(service)
    db.session.commit()
    flash(f"Added service: {name}", "success")
    return redirect(url_for("admin.manage_services"))


@admin_bp.route("/services/<int:service_id>/toggle", methods=["POST"])
@admin_required
def toggle_service(service_id):
    service = Service.query.get_or_404(service_id)
    service.is_active = not service.is_active
    db.session.commit()
    state = "active" if service.is_active else "inactive"
    flash(f"'{service.name}' is now {state}.", "success")
    return redirect(url_for("admin.manage_services"))


@admin_bp.route("/bookings/<int:booking_id>/status", methods=["POST"])
@admin_required
def update_booking_status(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    new_status = request.form.get("status")

    if new_status in ("pending", "confirmed", "completed", "cancelled", "no_show"):
        booking.status = new_status
        db.session.commit()
        flash("Booking status updated.", "success")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/staff")
@admin_required
def manage_staff():
    staff_members = Staff.query.all()
    return render_template("admin/staff.html", staff_members=staff_members)


@admin_bp.route("/staff/add", methods=["POST"])
@admin_required
def add_staff():
    name = request.form.get("name", "").strip()
    specialties = request.form.get("specialties", "").strip()

    if not name:
        flash("Staff name is required.", "error")
        return redirect(url_for("admin.manage_staff"))

    staff = Staff(name=name, specialties=specialties)
    db.session.add(staff)
    db.session.commit()
    flash(f"Added staff member: {name}", "success")
    return redirect(url_for("admin.manage_staff"))


@admin_bp.route("/staff/<int:staff_id>/toggle", methods=["POST"])
@admin_required
def toggle_staff(staff_id):
    staff = Staff.query.get_or_404(staff_id)
    staff.is_active = not staff.is_active
    db.session.commit()
    flash(f"{staff.name} is now {'active' if staff.is_active else 'inactive'}.", "success")
    return redirect(url_for("admin.manage_staff"))
