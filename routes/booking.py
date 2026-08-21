from datetime import datetime, date
from urllib.parse import quote

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from extensions import db, limiter, csrf
from models import Service, Staff, Booking, Review, PromoCode, auto_complete_past_bookings
from notifications import send_booking_confirmation_email

# The salon's WhatsApp number for the "share your feedback" link.
# Format: country code + number, no spaces, no leading +
# UPDATE THIS to your real business WhatsApp number before going live.
SALON_WHATSAPP_NUMBER = "9059302359"

booking_bp = Blueprint("booking", __name__)


def build_whatsapp_review_link(booking, review=None):
    """Builds a wa.me click-to-chat link pre-filled with the customer's
    feedback, ready for them to just hit send in WhatsApp."""
    if review:
        stars = "⭐" * review.rating
        message = (
            f"Hi Glow Studio! I just left a review for my {booking.service.name} "
            f"appointment on {booking.booking_date.strftime('%d %b %Y')}.\n"
            f"Rating: {stars} ({review.rating}/5)\n"
        )
        if review.comment:
            message += f"Comment: {review.comment}"
    else:
        message = (
            f"Hi Glow Studio! I recently had a {booking.service.name} appointment "
            f"on {booking.booking_date.strftime('%d %b %Y')}. Here's my feedback: "
        )
    return f"https://wa.me/{SALON_WHATSAPP_NUMBER}?text={quote(message)}"


@booking_bp.route("/book/<int:service_id>", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per minute")
def book_service(service_id):
    if current_user.is_admin:
        flash("Admins cannot book appointments as customers. Use the Admin Dashboard to manage bookings.", "error")
        return redirect(url_for("admin.dashboard"))

    auto_complete_past_bookings()

    service = Service.query.get_or_404(service_id)
    staff_members = Staff.query.filter_by(is_active=True).all()

    all_promos = PromoCode.query.filter_by(is_active=True).all()
    active_promos = [p for p in all_promos if p.is_valid(order_total=float(service.price))[0]]
    discount_amount = 0

    if request.method == "POST":
        date_str = request.form.get("booking_date")
        time_str = request.form.get("booking_time")
        staff_id_raw = request.form.get("staff_id")
        staff_id = int(staff_id_raw) if staff_id_raw and staff_id_raw.isdigit() else None
        notes = (request.form.get("notes", "").strip() or None)
        if notes:
            notes = notes[:500]  # cap notes length

        promo_code_str = request.form.get("promo_code", "").strip().upper()

        try:
            booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            booking_time = datetime.strptime(time_str, "%H:%M").time()
        except (ValueError, TypeError):
            flash("Please choose a valid date and time.", "error")
            return render_template("booking.html", service=service, staff_members=staff_members,
                                   active_promos=active_promos, today=date.today().strftime("%Y-%m-%d"))

        # Server-side past-date validation
        if booking_date < date.today():
            flash("You cannot book an appointment in the past. Please choose today or a future date.", "error")
            return render_template("booking.html", service=service, staff_members=staff_members,
                                   active_promos=active_promos, today=date.today().strftime("%Y-%m-%d"))

        # Staff-specific time-conflict check: only blocks this slot if the
        # SAME staff member already has a booking at this exact time.
        # If no staff was chosen ("No preference"), no conflict check applies
        # since the booking isn't tied to any specific person yet.
        conflict = None
        if staff_id:
            conflict = Booking.query.filter_by(
                booking_date=booking_date,
                booking_time=booking_time,
                staff_id=staff_id,
            ).filter(Booking.status.in_(["pending", "completed"])).first()

        if conflict:
            flash("This stylist is already booked at that time. Please choose a different time or stylist.", "error")
            return render_template("booking.html", service=service, staff_members=staff_members,
                                   active_promos=active_promos, today=date.today().strftime("%Y-%m-%d"))

        # --- Promo code handling ---
        promo = None
        if promo_code_str:
            promo = PromoCode.query.filter_by(code=promo_code_str).first()
            if not promo:
                flash("Invalid promo code.", "error")
                return render_template("booking.html", service=service, staff_members=staff_members,
                                       active_promos=active_promos, today=date.today().strftime("%Y-%m-%d"))

            valid, msg = promo.is_valid(order_total=float(service.price))
            if not valid:
                flash(msg, "error")
                return render_template("booking.html", service=service, staff_members=staff_members,
                                       active_promos=active_promos, today=date.today().strftime("%Y-%m-%d"))

            discount_amount = promo.calculate_discount(service.price)

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
        db.session.add(new_booking)

        if promo:
            promo.used_count = (promo.used_count or 0) + 1

        try:
           db.session.commit()
        except Exception as e:
            db.session.rollback()
            from flask import current_app
            current_app.logger.error(f"Error saving booking: {e}")
            flash("Unable to save your booking. Please try again.", "error")
            return redirect(url_for("booking.book_service", service_id=service.id))

        try:
            send_booking_confirmation_email(new_booking)
        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Error sending confirmation email: {e}")

        if discount_amount > 0:
            flash(
                f"Booking submitted with ₹{discount_amount} discount applied! We'll confirm it shortly.",
                "success"
            )
        else:
            flash("Booking request submitted! We'll confirm it shortly.", "success")

        return redirect(url_for("booking.my_bookings"))

    return render_template("booking.html", service=service, staff_members=staff_members,
                           active_promos=active_promos, today=date.today().strftime("%Y-%m-%d"))


@booking_bp.route("/my-bookings")
@login_required
def my_bookings():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    auto_complete_past_bookings()

    bookings = (
        Booking.query.filter_by(user_id=current_user.id)
        .order_by(Booking.booking_date.desc())
        .all()
    )

    # For bookings that already have a review, pre-build their WhatsApp
    # share link so the template can offer a "Share again" button.
    whatsapp_links = {
        b.id: build_whatsapp_review_link(b, review=b.review)
        for b in bookings if b.review
    }

    return render_template("my_bookings.html", bookings=bookings, whatsapp_links=whatsapp_links)


@booking_bp.route("/booking/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash("You can't cancel someone else's booking.", "error")
        return redirect(url_for("booking.my_bookings"))

    booking.status = "cancelled"
    db.session.commit()
    flash("Booking cancelled.", "success")
    return redirect(url_for("booking.my_bookings"))


@booking_bp.route("/api/booked-slots")
@login_required
def get_booked_slots():
    date_str = request.args.get("date")
    staff_id_raw = request.args.get("staff_id")

    # No staff selected yet ("No preference") — nothing to check against,
    # so no slots are considered booked.
    if not date_str or not staff_id_raw:
        return jsonify({"booked_slots": []})

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        staff_id = int(staff_id_raw)
    except (ValueError, TypeError):
        return jsonify({"booked_slots": []})

    auto_complete_past_bookings()

    bookings = Booking.query.filter_by(booking_date=target_date, staff_id=staff_id) \
        .filter(Booking.status.in_(["pending", "completed"])).all()

    booked_slots = [b.booking_time.strftime("%H:%M") for b in bookings if b.booking_time]
    return jsonify({"booked_slots": booked_slots})


@booking_bp.route("/api/validate-promo")
@login_required
def validate_promo():
    """AJAX endpoint: checks a promo code and returns the discount amount."""
    code = request.args.get("code", "").strip().upper()
    service_id = request.args.get("service_id", type=int)

    if not code or not service_id:
        return jsonify({"valid": False, "message": "Missing code or service."})

    promo = PromoCode.query.filter_by(code=code).first()
    if not promo:
        return jsonify({"valid": False, "message": "Invalid promo code."})

    service = Service.query.get(service_id)
    if not service:
        return jsonify({"valid": False, "message": "Service not found."})

    valid, msg = promo.is_valid(order_total=float(service.price))
    if not valid:
        return jsonify({"valid": False, "message": msg})

    discount = promo.calculate_discount(service.price)
    final_price = round(float(service.price) - discount, 2)

    return jsonify({
        "valid": True,
        "message": f"₹{discount} off applied!",
        "discount": discount,
        "final_price": final_price,
        "code": promo.code,
    })


@booking_bp.route("/booking/<int:booking_id>/review", methods=["GET", "POST"])
@login_required
def leave_review(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash("You can't review someone else's booking.", "error")
        return redirect(url_for("booking.my_bookings"))

    if booking.status != "completed":
        flash("You can only review a booking after it's completed.", "error")
        return redirect(url_for("booking.my_bookings"))

    if booking.review:
        flash("You've already reviewed this booking.", "error")
        return redirect(url_for("booking.my_bookings"))

    if request.method == "POST":
        try:
            rating = int(request.form.get("rating", 0))
        except ValueError:
            rating = 0
        comment = (request.form.get("comment", "").strip() or None)
        if comment:
            comment = comment[:1000]  # cap comment length

        if rating < 1 or rating > 5:
            flash("Please choose a rating between 1 and 5 stars.", "error")
            return render_template("leave_review.html", booking=booking,
                                   whatsapp_link=build_whatsapp_review_link(booking))

        review = Review(
            booking_id=booking.id,
            user_id=current_user.id,
            service_id=booking.service_id,
            rating=rating,
            comment=comment,
        )
        db.session.add(review)
        db.session.commit()

        flash("Thanks for your review!", "success")
        whatsapp_link = build_whatsapp_review_link(booking, review=review)
        return render_template("review_thanks.html", booking=booking, review=review, whatsapp_link=whatsapp_link)

    return render_template("leave_review.html", booking=booking,
                           whatsapp_link=build_whatsapp_review_link(booking))