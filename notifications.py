from flask import current_app
from flask_mail import Message

from extensions import mail


def send_booking_confirmation_email(booking):
    """Sends a confirmation email to the customer right after they book.
    Failures are logged but never crash the booking flow — a booking
    should still succeed even if the email fails to send."""

    if not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.warning("MAIL_USERNAME not configured — skipping confirmation email.")
        return False

    customer = booking.customer
    service = booking.service

    subject = f"Booking Confirmed — {service.name} at Glow Studio"

    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
        <h2 style="color:#6b2737;">Glow Studio</h2>
        <p>Hi {customer.name},</p>
        <p>Your appointment has been booked. Here are the details:</p>
        <table style="width:100%; border-collapse:collapse; margin:16px 0;">
            <tr><td style="padding:6px 0;"><strong>Service</strong></td><td>{service.name}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Date</strong></td><td>{booking.booking_date}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Time</strong></td><td>{booking.booking_time}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Status</strong></td><td>{booking.status}</td></tr>
        </table>
        <p>We'll see you soon!</p>
        <p style="color:#8a7a76; font-size:0.85rem;">— Glow Studio</p>
    </div>
    """

    text_body = (
        f"Hi {customer.name},\n\n"
        f"Your appointment is booked.\n"
        f"Service: {service.name}\n"
        f"Date: {booking.booking_date}\n"
        f"Time: {booking.booking_time}\n"
        f"Status: {booking.status}\n\n"
        f"— Glow Studio"
    )

    try:
        msg = Message(subject=subject, recipients=[customer.email])
        msg.body = text_body
        msg.html = html_body
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send confirmation email: {e}")
        return False


def send_booking_cancellation_email(booking, reason=None):
    """Sends a cancellation email to the customer with the cancellation reason."""

    if not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.warning("MAIL_USERNAME not configured — skipping cancellation email.")
        return False

    customer = booking.customer
    service = booking.service

    if not customer or not customer.email:
        return False

    service_name = service.name if service else "Appointment"
    subject = f"Booking Cancelled — {service_name} at Glow Studio"

    reason_html = f"<div style='background:#f6e6e7; border-left:4px solid #8a2f37; padding:12px; margin:16px 0; border-radius:4px;'><strong style='color:#8a2f37;'>Reason for cancellation:</strong> {reason}</div>" if reason else ""
    reason_text = f"\nReason for cancellation: {reason}\n" if reason else ""

    date_str = booking.booking_date.strftime('%d %b %Y') if booking.booking_date else str(booking.booking_date)
    time_str = booking.booking_time.strftime('%I:%M %p') if booking.booking_time else str(booking.booking_time)

    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; border: 1px solid #e8dcd4; padding: 24px; border-radius: 8px;">
        <h2 style="color:#6b2737; margin-top:0;">Glow Studio</h2>
        <p>Dear {customer.name},</p>
        <p>Your booking has been <strong style="color:#8a2f37;">CANCELLED</strong>. Here are the details:</p>
        <table style="width:100%; border-collapse:collapse; margin:16px 0;">
            <tr><td style="padding:6px 0;"><strong>Service</strong></td><td>{service_name}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Date</strong></td><td>{date_str}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Time</strong></td><td>{time_str}</td></tr>
        </table>
        {reason_html}
        <p>If you have any questions or would like to reschedule, please contact us at <strong>+91 9059302359</strong> or reply to this email.</p>
        <p style="color:#8a7a76; font-size:0.85rem; margin-top:24px;">— Glow Studio Team</p>
    </div>
    """

    text_body = (
        f"Dear {customer.name},\n\n"
        f"Your booking for {service_name} on {date_str} at {time_str} has been CANCELLED.\n"
        f"{reason_text}\n"
        f"To reschedule or ask any questions, please contact us at +91 9059302359.\n\n"
        f"— Glow Studio Team"
    )

    try:
        msg = Message(subject=subject, recipients=[customer.email])
        msg.body = text_body
        msg.html = html_body
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send cancellation email: {e}")
        return False
