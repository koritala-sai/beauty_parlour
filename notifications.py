import threading

from flask import current_app
from flask_mail import Message

from extensions import mail


def _email_is_configured():
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")

    return bool(username and password)


def _format_date(booking):
    if booking.booking_date:
        return booking.booking_date.strftime("%d %b %Y")
    return "Not available"


def _format_time(booking):
    if booking.booking_time:
        return booking.booking_time.strftime("%I:%M %p")
    return "Not available"


def _get_customer(booking):
    return booking.customer


def _get_service_name(booking):
    if booking.service:
        return booking.service.name
    return "Appointment"


def _get_staff_name(booking):
    if booking.staff:
        return booking.staff.name
    return "No preference"


def _send_email_in_background(app, msg):
    """
    Send email outside the web request.

    SMTP problems must never block booking/cancellation requests.
    """
    with app.app_context():
        try:
            mail.send(msg)

            app.logger.info(
                "Email sent successfully to %s",
                msg.recipients
            )

        except Exception:
            app.logger.exception(
                "Background email sending failed for recipients %s",
                msg.recipients
            )


def _queue_email(msg):
    """
    Queue email in a background thread and immediately return.

    This prevents Railway/Gunicorn request timeouts when Gmail SMTP
    is slow or temporarily unreachable.
    """
    app = current_app._get_current_object()

    thread = threading.Thread(
        target=_send_email_in_background,
        args=(app, msg),
        daemon=True,
    )

    thread.start()
    return True


def send_booking_confirmation_email(booking):
    """
    Queue booking confirmation email.

    Booking is never affected if email cannot be sent.
    """
    try:
        if not _email_is_configured():
            current_app.logger.warning(
                "Email not queued: MAIL_USERNAME or MAIL_PASSWORD is missing."
            )
            return False

        customer = _get_customer(booking)

        if not customer or not customer.email:
            current_app.logger.warning(
                "Booking confirmation email skipped: customer email not available."
            )
            return False

        service_name = _get_service_name(booking)
        date_text = _format_date(booking)
        time_text = _format_time(booking)
        staff_name = _get_staff_name(booking)
        final_price = booking.final_price

        subject = "Glow Studio - Booking Received ✨"

        text_body = f"""
Hello {customer.name},

Thank you for booking with Glow Studio!

Your booking details:

Service: {service_name}
Date: {date_text}
Time: {time_text}
Stylist: {staff_name}
Amount: ₹{final_price}
Status: {booking.status.title()}

Your booking request has been received successfully.
We will confirm your appointment shortly.

Thank you,
Glow Studio
""".strip()

        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2>✨ Booking Received - Glow Studio</h2>

    <p>Hello <strong>{customer.name}</strong>,</p>

    <p>
        Thank you for booking with Glow Studio.
        Your appointment request has been received successfully.
    </p>

    <h3>Booking Details</h3>

    <ul>
        <li><strong>Service:</strong> {service_name}</li>
        <li><strong>Date:</strong> {date_text}</li>
        <li><strong>Time:</strong> {time_text}</li>
        <li><strong>Stylist:</strong> {staff_name}</li>
        <li><strong>Amount:</strong> ₹{final_price}</li>
        <li><strong>Status:</strong> {booking.status.title()}</li>
    </ul>

    <p>We'll confirm your appointment shortly.</p>

    <p>
        Regards,<br>
        <strong>Glow Studio</strong>
    </p>
</body>
</html>
"""

        msg = Message(
            subject=subject,
            recipients=[customer.email],
            body=text_body,
            html=html_body,
        )

        return _queue_email(msg)

    except Exception:
        current_app.logger.exception(
            "Booking confirmation email preparation failed for booking %s",
            getattr(booking, "id", "unknown")
        )
        return False


def send_booking_cancellation_email(booking):
    """
    Queue cancellation email.

    Cancellation is never affected if email cannot be sent.
    """
    try:
        if not _email_is_configured():
            current_app.logger.warning(
                "Cancellation email not queued: email configuration is missing."
            )
            return False

        customer = _get_customer(booking)

        if not customer or not customer.email:
            current_app.logger.warning(
                "Cancellation email skipped: customer email not available."
            )
            return False

        service_name = _get_service_name(booking)
        date_text = _format_date(booking)
        time_text = _format_time(booking)

        reason = booking.cancellation_reason or "No reason was provided."

        subject = "Glow Studio - Booking Cancelled"

        text_body = f"""
Hello {customer.name},

Your appointment has been cancelled.

Booking Details:

Service: {service_name}
Date: {date_text}
Time: {time_text}

Reason:
{reason}

You can book another appointment at a convenient time.

Regards,
Glow Studio
""".strip()

        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2>Booking Cancelled</h2>

    <p>Hello <strong>{customer.name}</strong>,</p>

    <p>Your appointment has been cancelled.</p>

    <h3>Booking Details</h3>

    <ul>
        <li><strong>Service:</strong> {service_name}</li>
        <li><strong>Date:</strong> {date_text}</li>
        <li><strong>Time:</strong> {time_text}</li>
    </ul>

    <p>
        <strong>Reason:</strong><br>
        {reason}
    </p>

    <p>
        You can book another appointment at a convenient time.
    </p>

    <p>
        Regards,<br>
        <strong>Glow Studio</strong>
    </p>
</body>
</html>
"""

        msg = Message(
            subject=subject,
            recipients=[customer.email],
            body=text_body,
            html=html_body,
        )

        return _queue_email(msg)

    except Exception:
        current_app.logger.exception(
            "Cancellation email preparation failed for booking %s",
            getattr(booking, "id", "unknown")
        )
        return False