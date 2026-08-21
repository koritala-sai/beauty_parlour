from urllib.parse import quote
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship(
        "Booking",
        backref="customer",
        lazy=True,
    )

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(
            self.password_hash,
            raw_password,
        )


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80))
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_minutes = db.Column(
        db.Integer,
        nullable=False,
        default=30,
    )
    image_url = db.Column(db.String(255))
    is_active = db.Column(
        db.Boolean,
        default=True,
    )

    bookings = db.relationship(
        "Booking",
        backref="service",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "price": (
                float(self.price)
                if self.price is not None
                else None
            ),
            "duration_minutes": self.duration_minutes,
            "image_url": self.image_url,
            "is_active": self.is_active,
        }

    @property
    def average_rating(self):
        visible_reviews = [
            review
            for review in self.reviews
            if not review.is_hidden
        ]

        if not visible_reviews:
            return None

        return round(
            sum(
                review.rating
                for review in visible_reviews
            ) / len(visible_reviews),
            1,
        )

    @property
    def review_count(self):
        return len([
            review
            for review in self.reviews
            if not review.is_hidden
        ])


class Staff(db.Model):
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialties = db.Column(db.String(255))
    is_active = db.Column(
        db.Boolean,
        default=True,
    )

    bookings = db.relationship(
        "Booking",
        backref="staff",
        lazy=True,
    )


class PromoCode(db.Model):
    __tablename__ = "promo_codes"

    id = db.Column(db.Integer, primary_key=True)

    code = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
    )

    discount_percent = db.Column(
        db.Numeric(5, 2),
        default=0,
    )

    discount_flat = db.Column(
        db.Numeric(10, 2),
        default=0,
    )

    min_order = db.Column(
        db.Numeric(10, 2),
        default=0,
    )

    max_uses = db.Column(
        db.Integer,
        nullable=True,
    )

    used_count = db.Column(
        db.Integer,
        default=0,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
    )

    valid_from = db.Column(
        db.Date,
        nullable=True,
    )

    valid_until = db.Column(
        db.Date,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    bookings = db.relationship(
        "Booking",
        backref="promo_code",
        lazy=True,
    )

    def is_valid(self, order_total=0):
        """Check whether this promo code can currently be used."""

        if not self.is_active:
            return (
                False,
                "This promo code is no longer active.",
            )

        today = datetime.now().date()

        if self.valid_from and today < self.valid_from:
            return (
                False,
                "This promo code is not yet valid.",
            )

        if self.valid_until and today > self.valid_until:
            return (
                False,
                "This promo code has expired.",
            )

        if (
            self.max_uses is not None
            and (self.used_count or 0) >= self.max_uses
        ):
            return (
                False,
                "This promo code has reached its usage limit.",
            )

        minimum_order = float(self.min_order or 0)

        if float(order_total) < minimum_order:
            return (
                False,
                f"Minimum order of ₹{self.min_order} "
                "required for this code.",
            )

        return True, "Valid"

    def calculate_discount(self, original_price):
        """Calculate discount without exceeding original price."""

        original = float(original_price)
        discount = 0.0

        if (
            self.discount_percent
            and float(self.discount_percent) > 0
        ):
            discount = (
                original
                * float(self.discount_percent)
                / 100
            )

        if (
            self.discount_flat
            and float(self.discount_flat) > 0
        ):
            discount = max(
                discount,
                float(self.discount_flat),
            )

        return round(
            min(discount, original),
            2,
        )


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
    )

    service_id = db.Column(
        db.Integer,
        db.ForeignKey("services.id"),
        nullable=False,
    )

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
    )

    booking_date = db.Column(
        db.Date,
        nullable=False,
    )

    booking_time = db.Column(
        db.Time,
        nullable=False,
    )

    # pending / confirmed / completed / cancelled / no_show
    status = db.Column(
        db.String(20),
        default="pending",
    )

    # unpaid / paid / refunded
    payment_status = db.Column(
        db.String(20),
        default="unpaid",
    )

    notes = db.Column(
        db.Text,
        nullable=True,
    )

    cancellation_reason = db.Column(
        db.Text,
        nullable=True,
    )

    promo_code_id = db.Column(
        db.Integer,
        db.ForeignKey("promo_codes.id"),
        nullable=True,
    )

    discount_amount = db.Column(
        db.Numeric(10, 2),
        default=0,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    def get_cancellation_message_text(self):
        reason_text = (
            f"\n*Reason:* {self.cancellation_reason}"
            if self.cancellation_reason
            else ""
        )

        date_text = (
            self.booking_date.strftime("%d %b %Y")
            if self.booking_date
            else "Not available"
        )

        time_text = (
            self.booking_time.strftime("%I:%M %p")
            if self.booking_time
            else "Not available"
        )

        service_name = (
            self.service.name
            if self.service
            else "Appointment"
        )

        customer_name = (
            self.customer.name
            if self.customer
            else "Customer"
        )

        return (
            f"Hello {customer_name},\n\n"
            f"Your booking for *{service_name}* on "
            f"{date_text} at {time_text} at Glow Studio "
            f"has been *CANCELLED*."
            f"{reason_text}\n\n"
            "If you have any questions or would like to "
            "reschedule, please contact us."
        )

    def get_whatsapp_cancellation_link(self):
        if not self.customer or not self.customer.phone:
            return None

        phone_digits = "".join(
            character
            for character in str(self.customer.phone)
            if character.isdigit()
        )

        if not phone_digits:
            return None

        # Indian 10-digit phone number
        if len(phone_digits) == 10:
            phone_digits = "91" + phone_digits

        message = self.get_cancellation_message_text()

        return (
            f"https://wa.me/{phone_digits}"
            f"?text={quote(message)}"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "service_id": self.service_id,
            "staff_id": self.staff_id,
            "booking_date": (
                self.booking_date.isoformat()
                if self.booking_date
                else None
            ),
            "booking_time": (
                self.booking_time.strftime("%H:%M")
                if self.booking_time
                else None
            ),
            "status": self.status,
            "payment_status": self.payment_status,
            "notes": self.notes,
            "cancellation_reason": self.cancellation_reason,
            "discount_amount": (
                float(self.discount_amount)
                if self.discount_amount
                else 0
            ),
            "final_price": self.final_price,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
        }

    @property
    def final_price(self):
        """Service price minus applied promo discount."""

        base_price = (
            float(self.service.price)
            if self.service
            else 0
        )

        discount = (
            float(self.discount_amount)
            if self.discount_amount
            else 0
        )

        return round(
            max(base_price - discount, 0),
            2,
        )


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id"),
        nullable=False,
        unique=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
    )

    service_id = db.Column(
        db.Integer,
        db.ForeignKey("services.id"),
        nullable=False,
    )

    rating = db.Column(
        db.Integer,
        nullable=False,
    )

    comment = db.Column(
        db.Text,
        nullable=True,
    )

    added_by_admin = db.Column(
        db.Boolean,
        default=False,
    )

    is_hidden = db.Column(
        db.Boolean,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    booking = db.relationship(
        "Booking",
        backref=db.backref(
            "review",
            uselist=False,
        ),
    )

    user = db.relationship(
        "User",
        backref="reviews",
    )

    service = db.relationship(
        "Service",
        backref="reviews",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "booking_id": self.booking_id,
            "user_id": self.user_id,
            "service_id": self.service_id,
            "rating": self.rating,
            "comment": self.comment,
            "is_hidden": self.is_hidden,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
        }


def auto_complete_past_bookings():
    """
    Mark past pending or confirmed appointments as completed.

    Cancelled appointments are never changed.
    """

    now = datetime.now()
    today = now.date()
    current_time = now.time()

    past_bookings = Booking.query.filter(
        Booking.status.in_(["pending", "confirmed"]),
        (
            (Booking.booking_date < today)
            |
            (
                (Booking.booking_date == today)
                & (Booking.booking_time <= current_time)
            )
        ),
    ).all()

    if not past_bookings:
        return 0

    try:
        for booking in past_bookings:
            booking.status = "completed"

        db.session.commit()
        return len(past_bookings)

    except Exception:
        db.session.rollback()
        raise