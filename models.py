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
        if not self.reviews:
            return None
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 1)

    @property
    def review_count(self):
        return len(self.reviews)


class Staff(db.Model):
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialties = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    bookings = db.relationship("Booking", backref="staff", lazy=True)


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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


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
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def auto_complete_past_bookings():
    """Automatically marks bookings as 'completed' if their date/time has passed."""
    now = datetime.now()
    today = now.date()
    current_time = now.time()

    past_bookings = Booking.query.filter(
        Booking.status.in_(["pending", "confirmed"]),
        (Booking.booking_date < today) |
        ((Booking.booking_date == today) & (Booking.booking_time <= current_time))
    ).all()

    if past_bookings:
        for b in past_bookings:
            b.status = "completed"
        db.session.commit()
