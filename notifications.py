import threading

import resend
from flask import current_app


# =========================================================
# EMAIL CONFIGURATION CHECK
# =========================================================

def _email_is_configured():
    api_key = (current_app.config.get("RESEND_API_KEY") or "").strip()
    mail_from = (current_app.config.get("MAIL_FROM") or "").strip()

    return bool(api_key and mail_from)


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _format_date(booking):
    if getattr(booking, "booking_date", None):
        return booking.booking_date.strftime("%d %b %Y")
    return "Not available"


def _format_time(booking):
    if getattr(booking, "booking_time", None):
        return booking.booking_time.strftime("%I:%M %p")
    return "Not available"


def _get_customer(booking):
    return getattr(booking, "customer", None)


def _get_service_name(booking):
    service = getattr(booking, "service", None)

    if service and getattr(service, "name", None):
        return service.name

    return "Appointment"


def _get_staff_name(booking):
    staff = getattr(booking, "staff", None)

    if staff and getattr(staff, "name", None):
        return staff.name

    return "No preference"


# =========================================================
# SEND EMAIL IN BACKGROUND
# =========================================================

def _send_email_in_background(app, email_data):
    """
    Sends email using Resend HTTP API.

    IMPORTANT:
    Email failure must NEVER affect booking or cancellation.
    """

    try:
        with app.app_context():

            resend_api_key = (
                current_app.config.get("RESEND_API_KEY") or ""
            ).strip()

            if not resend_api_key:
                current_app.logger.warning(
                    "Email skipped: RESEND_API_KEY is missing."
                )
                return

            resend.api_key = resend_api_key

            response = resend.Emails.send(email_data)

            current_app.logger.info(
                "Email sent successfully to %s. Response: %s",
                email_data.get("to", []),
                response
            )

    except Exception as e:

        try:
            app.logger.error(
                "Background Resend email failed for recipients %s: %s",
                email_data.get("to", []),
                str(e),
                exc_info=True
            )
        except Exception:
            pass


# =========================================================
# QUEUE EMAIL SAFELY
# =========================================================

def _queue_email(email_data):
    """
    Starts email sending in a background thread.

    Booking/cancellation continues immediately.
    Email failure will NOT create an Internal Server Error.
    """

    try:
        app = current_app._get_current_object()

        thread = threading.Thread(
            target=_send_email_in_background,
            args=(app, email_data),
            daemon=True,
            name="GlowStudioEmailThread"
        )

        thread.start()

        app.logger.info(
            "Email queued successfully for %s",
            email_data.get("to", [])
        )

        return True

    except Exception as e:

        try:
            current_app.logger.error(
                "Failed to queue email for %s: %s",
                email_data.get("to", []),
                str(e),
                exc_info=True
            )
        except Exception:
            pass

        return False


# =========================================================
# BOOKING CONFIRMATION EMAIL
# =========================================================

def send_booking_confirmation_email(booking):
    """
    Sends booking confirmation email.

    Booking will NEVER fail if email sending fails.
    """

    try:

        if not _email_is_configured():
            current_app.logger.warning(
                "Booking email skipped: "
                "RESEND_API_KEY or MAIL_FROM is missing."
            )
            return False

        customer = _get_customer(booking)

        if not customer:
            current_app.logger.warning(
                "Booking email skipped: customer not found."
            )
            return False

        customer_email = (
            getattr(customer, "email", "") or ""
        ).strip()

        if not customer_email:
            current_app.logger.warning(
                "Booking email skipped: customer email is missing."
            )
            return False

        customer_name = (
            getattr(customer, "name", None)
            or "Customer"
        )

        service_name = _get_service_name(booking)
        date_text = _format_date(booking)
        time_text = _format_time(booking)
        staff_name = _get_staff_name(booking)

        final_price = getattr(booking, "final_price", None)

        if final_price is None:
            final_price = 0

        status = (
            getattr(booking, "status", "pending")
            or "pending"
        )

        mail_from = (
            current_app.config.get("MAIL_FROM") or ""
        ).strip()

        subject = "Glow Studio - Booking Confirmed"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif;
                     line-height: 1.6;
                     color: #333;">

            <h2>Booking Confirmed - Glow Studio</h2>

            <p>Hello <strong>{customer_name}</strong>,</p>

            <p>
                Thank you for booking with Glow Studio.
                Your appointment request has been confirmed successfully.
            </p>

            <h3>Booking Details</h3>

            <ul>
                <li>
                    <strong>Service:</strong>
                    {service_name}
                </li>

                <li>
                    <strong>Date:</strong>
                    {date_text}
                </li>

                <li>
                    <strong>Time:</strong>
                    {time_text}
                </li>

                <li>
                    <strong>Stylist:</strong>
                    {staff_name}
                </li>

                <li>
                    <strong>Amount:</strong>
                    ₹{final_price}
                </li>

                <li>
                    <strong>Status:</strong>
                    {str(status).title()}
                </li>
            </ul>

            <p>
                Regards,<br>
                <strong>Glow Studio</strong>
            </p>

        </body>
        </html>
        """

        text_body = f"""
Hello {customer_name},

Thank you for booking with Glow Studio!

Your booking details:

Service: {service_name}
Date: {date_text}
Time: {time_text}
Stylist: {staff_name}
Amount: ₹{final_price}
Status: {str(status).title()}

Your booking request has been confirmed successfully.

Regards,
Glow Studio
        """.strip()

        email_data = {
            "from": mail_from,
            "to": [customer_email],
            "subject": subject,
            "html": html_body,
            "text": text_body
        }

        _queue_email(email_data)

        # Booking must continue even if email fails
        return True

    except Exception:

        try:
            current_app.logger.exception(
                "Booking confirmation email preparation failed "
                "for booking %s",
                getattr(booking, "id", "unknown")
            )
        except Exception:
            pass

        return False


# =========================================================
# BOOKING CANCELLATION EMAIL
# =========================================================

def send_booking_cancellation_email(booking):
    """
    Sends cancellation email to the customer.

    Works for both:
    1. Customer cancellation
    2. Admin cancellation

    Cancellation will NEVER fail if email sending fails.
    """

    try:

        if not _email_is_configured():
            current_app.logger.warning(
                "Cancellation email skipped: "
                "RESEND_API_KEY or MAIL_FROM is missing."
            )
            return False

        customer = _get_customer(booking)

        if not customer:
            current_app.logger.warning(
                "Cancellation email skipped: customer not found."
            )
            return False

        customer_email = (
            getattr(customer, "email", "") or ""
        ).strip()

        if not customer_email:
            current_app.logger.warning(
                "Cancellation email skipped: customer email is missing."
            )
            return False

        customer_name = (
            getattr(customer, "name", None)
            or "Customer"
        )

        service_name = _get_service_name(booking)
        date_text = _format_date(booking)
        time_text = _format_time(booking)

        reason = (
            getattr(booking, "cancellation_reason", None)
            or "No reason was provided."
        ).strip()

        mail_from = (
            current_app.config.get("MAIL_FROM") or ""
        ).strip()

        subject = "Glow Studio - Booking Cancelled"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif;
                     line-height: 1.6;
                     color: #333;">

            <h2>Booking Cancelled - Glow Studio</h2>

            <p>Hello <strong>{customer_name}</strong>,</p>

            <p>
                Your appointment has been cancelled.
            </p>

            <h3>Booking Details</h3>

            <ul>
                <li>
                    <strong>Service:</strong>
                    {service_name}
                </li>

                <li>
                    <strong>Date:</strong>
                    {date_text}
                </li>

                <li>
                    <strong>Time:</strong>
                    {time_text}
                </li>
            </ul>

            <p>
                <strong>Cancellation Reason:</strong><br>
                {reason}
            </p>

            <p>
                You can book another appointment
                at a convenient time.
            </p>

            <p>
                Regards,<br>
                <strong>Glow Studio</strong>
            </p>

        </body>
        </html>
        """

        text_body = f"""
Hello {customer_name},

Your appointment has been cancelled.

Booking Details:

Service: {service_name}
Date: {date_text}
Time: {time_text}

Cancellation Reason:
{reason}

You can book another appointment at a convenient time.

Regards,
Glow Studio
        """.strip()

        email_data = {
            "from": mail_from,
            "to": [customer_email],
            "subject": subject,
            "html": html_body,
            "text": text_body
        }

        _queue_email(email_data)

        # Cancellation must continue even if email fails
        return True

    except Exception:

        try:
            current_app.logger.exception(
                "Cancellation email preparation failed "
                "for booking %s",
                getattr(booking, "id", "unknown")
            )
        except Exception:
            pass

        return False