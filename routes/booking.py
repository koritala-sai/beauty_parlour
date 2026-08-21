from datetime import datetime, date
from urllib.parse import quote

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user

from extensions import db, limiter
from models import (
    Service,
    Staff,
    Booking,
    Review,
    PromoCode,
    auto_complete_past_bookings,
)
from notifications import (
    send_booking_confirmation_email,
    send_booking_cancellation_email,
)


# The salon's WhatsApp number for the "share your feedback" link.
# Format: country code + number, no spaces, no leading +
SALON_WHATSAPP_NUMBER = "9059302359"


booking_bp = Blueprint("booking", __name__)


def build_whatsapp_review_link(booking, review=None):
    """Build a WhatsApp click-to-chat link for sharing feedback."""
    if review:
        stars = "⭐" * review.rating
        message = (
            f"Hi Glow Studio! I just left a review for my "
            f"{booking.service.name} appointment on "
            f"{booking.booking_date.strftime('%d %b %Y')}.\n"
            f"Rating: {stars} ({review.rating}/5)\n"
        )

        if review.comment:
            message += f"Comment: {review.comment}"
    else:
        message = (
            f"Hi Glow Studio! I recently had a "
            f"{booking.service.name} appointment on "
            f"{booking.booking_date.strftime('%d %b %Y')}. "
            f"Here's my feedback: "
        )

    return (
        f"https://wa.me/{SALON_WHATSAPP_NUMBER}"
        f"?text={quote(message)}"
    )


def render_booking_page(service, staff_members, active_promos):
    """Render booking page with common values."""
    return render_template(
        "booking.html",
        service=service,
        staff_members=staff_members,
        active_promos=active_promos,
        today=date.today().strftime("%Y-%m-%d"),
    )


@booking_bp.route("/book/<int:service_id>", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per minute")
def book_service(service_id):
    if current_user.is_admin:
        flash(
            "Admins cannot book appointments as customers. "
            "Use the Admin Dashboard to manage bookings.",
            "error",
        )
        return redirect(url_for("admin.dashboard"))

    auto_complete_past_bookings()

    service = Service.query.get_or_404(service_id)
    staff_members = Staff.query.filter_by(is_active=True).all()

    all_promos = PromoCode.query.filter_by(is_active=True).all()
    active_promos = [
        promo
        for promo in all_promos
        if promo.is_valid(order_total=float(service.price))[0]
    ]

    if request.method == "POST":
        date_str = request.form.get("booking_date")
        time_str = request.form.get("booking_time")

        staff_id_raw = request.form.get("staff_id")
        staff_id = (
            int(staff_id_raw)
            if staff_id_raw and staff_id_raw.isdigit()
            else None
        )

        notes = request.form.get("notes", "").strip() or None
        if notes:
            notes = notes[:500]

        promo_code_str = request.form.get(
            "promo_code", ""
        ).strip().upper()

        # Validate date and time
        try:
            booking_date = datetime.strptime(
                date_str, "%Y-%m-%d"
            ).date()
            booking_time = datetime.strptime(
                time_str, "%H:%M"
            ).time()
        except (ValueError, TypeError):
            flash(
                "Please choose a valid date and time.",
                "error",
            )
            return render_booking_page(
                service,
                staff_members,
                active_promos,
            )

        # Prevent past dates
        if booking_date < date.today():
            flash(
                "You cannot book an appointment in the past. "
                "Please choose today or a future date.",
                "error",
            )
            return render_booking_page(
                service,
                staff_members,
                active_promos,
            )

        # Verify selected staff exists and is active
        if staff_id:
            selected_staff = Staff.query.filter_by(
                id=staff_id,
                is_active=True,
            ).first()

            if not selected_staff:
                flash(
                    "Selected stylist is not available. "
                    "Please choose another stylist.",
                    "error",
                )
                return render_booking_page(
                    service,
                    staff_members,
                    active_promos,
                )

            # Check same staff + same date + same time
            conflict = (
                Booking.query.filter_by(
                    booking_date=booking_date,
                    booking_time=booking_time,
                    staff_id=staff_id,
                )
                .filter(
                    Booking.status.in_(["pending", "confirmed"])
                )
                .first()
            )

            if conflict:
                flash(
                    "This stylist is already booked at that time. "
                    "Please choose a different time or stylist.",
                    "error",
                )
                return render_booking_page(
                    service,
                    staff_members,
                    active_promos,
                )

        # Promo code validation
        promo = None
        discount_amount = 0

        if promo_code_str:
            promo = PromoCode.query.filter_by(
                code=promo_code_str,
                is_active=True,
            ).first()

            if not promo:
                flash("Invalid or inactive promo code.", "error")
                return render_booking_page(
                    service,
                    staff_members,
                    active_promos,
                )

            valid, message = promo.is_valid(
                order_total=float(service.price)
            )

            if not valid:
                flash(message, "error")
                return render_booking_page(
                    service,
                    staff_members,
                    active_promos,
                )

            discount_amount = promo.calculate_discount(
                service.price
            )

        # Create booking
        new_booking = Booking(
            user_id=current_user.id,
            service_id=service.id,
            staff_id=staff_id,
            booking_date=booking_date,
            booking_time=booking_time,
            status="pending",
            payment_status="unpaid",
            notes=notes,
            promo_code_id=promo.id if promo else None,
            discount_amount=discount_amount,
        )

        # Save booking FIRST
        try:
            db.session.add(new_booking)

            if promo:
                promo.used_count = (promo.used_count or 0) + 1

            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Database error while creating booking"
            )

            flash(
                "Unable to save your booking. Please try again.",
                "error",
            )

            return render_booking_page(
                service,
                staff_members,
                active_promos,
            )

        # Booking is safely saved now.
        # Email failure must NEVER affect the booking.
        email_sent = send_booking_confirmation_email(new_booking)

        if email_sent:
            current_app.logger.info(
                "Confirmation email sent for booking %s",
                new_booking.id,
            )
        else:
            current_app.logger.warning(
                "Booking %s saved, but confirmation email could not be sent.",
                new_booking.id,
            )

        if discount_amount > 0:
            flash(
                f"Booking submitted with ₹{discount_amount} discount applied! "
                "We'll confirm it shortly.",
                "success",
            )
        else:
            flash(
                "Booking request submitted! We'll confirm it shortly.",
                "success",
            )

        return redirect(url_for("booking.my_bookings"))

    return render_booking_page(
        service,
        staff_members,
        active_promos,
    )


@booking_bp.route("/my-bookings")
@login_required
def my_bookings():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    auto_complete_past_bookings()

    bookings = (
        Booking.query
        .filter_by(user_id=current_user.id)
        .order_by(
            Booking.booking_date.desc(),
            Booking.booking_time.desc(),
        )
        .all()
    )

    whatsapp_links = {
        booking.id: build_whatsapp_review_link(
            booking,
            review=booking.review,
        )
        for booking in bookings
        if booking.review
    }

    return render_template(
        "my_bookings.html",
        bookings=bookings,
        whatsapp_links=whatsapp_links,
    )


@booking_bp.route(
    "/booking/<int:booking_id>/cancel",
    methods=["POST"],
)
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # User can only cancel their own booking
    if booking.user_id != current_user.id:
        flash(
            "You can't cancel someone else's booking.",
            "error",
        )
        return redirect(url_for("booking.my_bookings"))

    # Prevent repeated cancellation
    if booking.status == "cancelled":
        flash(
            "This booking is already cancelled.",
            "error",
        )
        return redirect(url_for("booking.my_bookings"))

    # Prevent cancellation after completion
    if booking.status == "completed":
        flash(
            "Completed bookings cannot be cancelled.",
            "error",
        )
        return redirect(url_for("booking.my_bookings"))

    # Save cancellation FIRST
    try:
        booking.status = "cancelled"

        # Only set this if your Booking model contains cancellation_reason
        if hasattr(booking, "cancellation_reason"):
            booking.cancellation_reason = "Cancelled by customer"

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Database error while cancelling booking %s",
            booking_id,
        )

        flash(
            "Unable to cancel the booking. Please try again.",
            "error",
        )
        return redirect(url_for("booking.my_bookings"))

    # Cancellation is already saved.
    # Email failure will not undo the cancellation.
    email_sent = send_booking_cancellation_email(booking)

    if email_sent:
        current_app.logger.info(
            "Cancellation email sent for booking %s",
            booking.id,
        )
    else:
        current_app.logger.warning(
            "Booking %s cancelled, but cancellation email could not be sent.",
            booking.id,
        )

    flash("Booking cancelled successfully.", "success")

    return redirect(url_for("booking.my_bookings"))


@booking_bp.route("/api/booked-slots")
@login_required
def get_booked_slots():
    date_str = request.args.get("date")
    staff_id_raw = request.args.get("staff_id")

    # No specific staff selected
    if not date_str or not staff_id_raw:
        return jsonify({"booked_slots": []})

    try:
        target_date = datetime.strptime(
            date_str,
            "%Y-%m-%d",
        ).date()

        staff_id = int(staff_id_raw)

    except (ValueError, TypeError):
        return jsonify({"booked_slots": []})

    auto_complete_past_bookings()

    bookings = (
        Booking.query
        .filter_by(
            booking_date=target_date,
            staff_id=staff_id,
        )
        .filter(
            Booking.status.in_(["pending", "confirmed"])
        )
        .all()
    )

    booked_slots = [
        booking.booking_time.strftime("%H:%M")
        for booking in bookings
        if booking.booking_time
    ]

    return jsonify({"booked_slots": booked_slots})


@booking_bp.route("/api/validate-promo")
@login_required
def validate_promo():
    """AJAX endpoint to validate a promo code."""

    code = request.args.get(
        "code",
        "",
    ).strip().upper()

    service_id = request.args.get(
        "service_id",
        type=int,
    )

    if not code or not service_id:
        return jsonify({
            "valid": False,
            "message": "Missing code or service.",
        })

    promo = PromoCode.query.filter_by(
        code=code,
        is_active=True,
    ).first()

    if not promo:
        return jsonify({
            "valid": False,
            "message": "Invalid or inactive promo code.",
        })

    service = Service.query.get(service_id)

    if not service:
        return jsonify({
            "valid": False,
            "message": "Service not found.",
        })

    valid, message = promo.is_valid(
        order_total=float(service.price)
    )

    if not valid:
        return jsonify({
            "valid": False,
            "message": message,
        })

    discount = promo.calculate_discount(
        service.price
    )

    final_price = round(
        float(service.price) - discount,
        2,
    )

    return jsonify({
        "valid": True,
        "message": f"₹{discount} off applied!",
        "discount": discount,
        "final_price": final_price,
        "code": promo.code,
    })


@booking_bp.route(
    "/booking/<int:booking_id>/review",
    methods=["GET", "POST"],
)
@login_required
def leave_review(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash(
            "You can't review someone else's booking.",
            "error",
        )
        return redirect(url_for("booking.my_bookings"))

    if booking.status != "completed":
        flash(
            "You can only review a booking after it's completed.",
            "error",
        )
        return redirect(url_for("booking.my_bookings"))

    if booking.review:
        flash(
            "You've already reviewed this booking.",
            "error",
        )
        return redirect(url_for("booking.my_bookings"))

    if request.method == "POST":
        try:
            rating = int(
                request.form.get("rating", 0)
            )
        except (ValueError, TypeError):
            rating = 0

        comment = (
            request.form.get("comment", "").strip()
            or None
        )

        if comment:
            comment = comment[:1000]

        if rating < 1 or rating > 5:
            flash(
                "Please choose a rating between 1 and 5 stars.",
                "error",
            )
            return render_template(
                "leave_review.html",
                booking=booking,
                whatsapp_link=build_whatsapp_review_link(booking),
            )

        try:
            review = Review(
                booking_id=booking.id,
                user_id=current_user.id,
                service_id=booking.service_id,
                rating=rating,
                comment=comment,
            )

            db.session.add(review)
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Database error while saving review for booking %s",
                booking_id,
            )

            flash(
                "Unable to save your review. Please try again.",
                "error",
            )

            return render_template(
                "leave_review.html",
                booking=booking,
                whatsapp_link=build_whatsapp_review_link(booking),
            )

        flash("Thanks for your review!", "success")

        whatsapp_link = build_whatsapp_review_link(
            booking,
            review=review,
        )

        return render_template(
            "review_thanks.html",
            booking=booking,
            review=review,
            whatsapp_link=whatsapp_link,
        )

    return render_template(
        "leave_review.html",
        booking=booking,
        whatsapp_link=build_whatsapp_review_link(booking),
    )