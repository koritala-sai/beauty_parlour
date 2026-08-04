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
