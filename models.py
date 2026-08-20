from urllib.parse import quote
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(UserMixin, db.Model):
    """Customers and the admin/owner both live in this table, told apart
    by the is_admin flag. Keeps things simple for a solo project."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship("Booking", backref="customer", lazy=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80))
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    image_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    bookings = db.relationship("Booking", backref="service", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "price": float(self.price) if self.price is not None else None,
            "duration_minutes": self.duration_minutes,
            "image_url": self.image_url,
            "is_active": self.is_active,
        }

    @property
    def average_rating(self):
        visible = [r for r in self.reviews if not r.is_hidden]
        if not visible:
            return None
        return round(sum(r.rating for r in visible) / len(visible), 1)

    @property
    def review_count(self):
        return len([r for r in self.reviews if not r.is_hidden])


class Staff(db.Model):
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialties = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    bookings = db.relationship("Booking", backref="staff", lazy=True)


class PromoCode(db.Model):
    """Discount codes the admin can create. Supports percentage-based or
    flat-amount discounts, with optional min-order and usage caps."""

    __tablename__ = "promo_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)   # e.g. 20.00 = 20%
    discount_flat = db.Column(db.Numeric(10, 2), default=0)      # e.g. 100 = ₹100 off
    min_order = db.Column(db.Numeric(10, 2), default=0)          # minimum service price
    max_uses = db.Column(db.Integer, nullable=True)               # None = unlimited
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    valid_from = db.Column(db.Date, nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship("Booking", backref="promo_code", lazy=True)

    def is_valid(self, order_total=0):
        """Check whether this code can be applied right now."""
        if not self.is_active:
            return False, "This promo code is no longer active."

        today = datetime.now().date()
        if self.valid_from and today < self.valid_from:
            return False, "This promo code is not yet valid."
        if self.valid_until and today > self.valid_until:
            return False, "This promo code has expired."

        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False, "This promo code has reached its usage limit."

        if order_total < float(self.min_order or 0):
            return False, f"Minimum order of ₹{self.min_order} required for this code."

        return True, "Valid"

    def calculate_discount(self, original_price):
        """Return the discount amount for a given price."""
        original = float(original_price)
        discount = 0

        if self.discount_percent and float(self.discount_percent) > 0:
            discount = original * float(self.discount_percent) / 100

        if self.discount_flat and float(self.discount_flat) > 0:
            discount = max(discount, float(self.discount_flat))

        # Never discount more than the price itself
        return round(min(discount, original), 2)


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=True)

    booking_date = db.Column(db.Date, nullable=False)
    booking_time = db.Column(db.Time, nullable=False)

    status = db.Column(db.String(20), default="pending")
    # expected values: pending, confirmed, completed, cancelled, no_show

    payment_status = db.Column(db.String(20), default="unpaid")
    # expected values: unpaid, paid, refunded

    notes = db.Column(db.Text, nullable=True)  # special requests from customer
    cancellation_reason = db.Column(db.Text, nullable=True)  # reason if cancelled by admin

    # Promo / discount tracking
    promo_code_id = db.Column(db.Integer, db.ForeignKey("promo_codes.id"), nullable=True)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_cancellation_message_text(self):
        reason_str = f"\n*Reason:* {self.cancellation_reason}" if self.cancellation_reason else ""
        date_str = self.booking_date.strftime("%d %b %Y") if self.booking_date else ""
        time_str = self.booking_time.strftime("%I:%M %p") if self.booking_time else ""
        service_str = self.service.name if self.service else "Appointment"
        cust_name = self.customer.name if self.customer else "Customer"
        return (
            f"Hello {cust_name},\n"
            f"Your booking for *{service_str}* on {date_str} at {time_str} at Glow Studio has been *CANCELLED*.{reason_str}\n\n"
            f"If you have any questions or would like to reschedule, please contact us."
        )

    def get_whatsapp_cancellation_link(self):
        if not self.customer or not self.customer.phone:
            return None
        phone_digits = "".join(c for c in str(self.customer.phone) if c.isdigit())
        if not phone_digits:
            return None
        if len(phone_digits) == 10:
            phone_digits = "91" + phone_digits
        msg = self.get_cancellation_message_text()
        return f"https://wa.me/{phone_digits}?text={quote(msg)}"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "service_id": self.service_id,
            "staff_id": self.staff_id,
            "booking_date": self.booking_date.isoformat() if self.booking_date else None,
            "booking_time": self.booking_time.strftime("%H:%M") if self.booking_time else None,
            "status": self.status,
            "payment_status": self.payment_status,
            "notes": self.notes,
            "discount_amount": float(self.discount_amount) if self.discount_amount else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @property
    def final_price(self):
        """Service price minus any promo discount."""
        base = float(self.service.price) if self.service else 0
        disc = float(self.discount_amount) if self.discount_amount else 0
        return round(max(base - disc, 0), 2)


class Review(db.Model):
    """A review is tied to one specific completed booking — this keeps
    reviews honest (only customers who actually had that service can
    leave one) and caps it at one review per booking."""

    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)

    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    added_by_admin = db.Column(db.Boolean, default=False)
    is_hidden = db.Column(db.Boolean, default=False)  # admin moderation flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    booking = db.relationship("Booking", backref=db.backref("review", uselist=False))
    user = db.relationship("User", backref="reviews")
    service = db.relationship("Service", backref="reviews")

    def to_dict(self):
        return {
            "id": self.id,
            "booking_id": self.booking_id,
            "user_id": self.user_id,
            "service_id": self.service_id,
            "rating": self.rating,
            "comment": self.comment,
            "is_hidden": self.is_hidden,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def auto_complete_past_bookings():
    """Automatically marks bookings as 'completed' if their date/time has passed."""
    now = datetime.now()
    today = now.date()
    current_time = now.time()

    past_bookings = Booking.query.filter(
        Booking.status == "pending",
        (Booking.booking_date < today) |
        ((Booking.booking_date == today) & (Booking.booking_time <= current_time))
    ).all()

    if past_bookings:
        for b in past_bookings:
            b.status = "completed"
        db.session.commit()
