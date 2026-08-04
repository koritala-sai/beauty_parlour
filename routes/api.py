from datetime import datetime

from flask import Blueprint, jsonify, request

from extensions import db
from models import Service, Booking, User
from notifications import send_booking_confirmation_email

api_bp = Blueprint("api", __name__, url_prefix="/api")

# NOTE: These endpoints are unauthenticated on purpose, to make them easy to
# test in Postman while you're learning. Before deploying this for real
# customers, add authentication (e.g. an API key or JWT check) here.


# ---------- SERVICES ----------

@api_bp.route("/services", methods=["GET"])
def get_services():
    services = Service.query.all()
    return jsonify([s.to_dict() for s in services])


@api_bp.route("/services/<int:service_id>", methods=["GET"])
def get_service(service_id):
    service = Service.query.get_or_404(service_id)
    return jsonify(service.to_dict())


@api_bp.route("/services", methods=["POST"])
def create_service():
    data = request.get_json(silent=True) or {}

    name = data.get("name")
    price = data.get("price")

    if not name or price is None:
        return jsonify({"error": "name and price are required"}), 400

    service = Service(
        name=name,
        category=data.get("category"),
        description=data.get("description"),
        price=price,
        duration_minutes=data.get("duration_minutes", 30),
        image_url=data.get("image_url"),
        is_active=data.get("is_active", True),
    )
    db.session.add(service)
    db.session.commit()
    return jsonify(service.to_dict()), 201


@api_bp.route("/services/<int:service_id>", methods=["PUT"])
def update_service(service_id):
    service = Service.query.get_or_404(service_id)
    data = request.get_json(silent=True) or {}

    for field in ["name", "category", "description", "price", "duration_minutes", "image_url", "is_active"]:
        if field in data:
            setattr(service, field, data[field])

    db.session.commit()
    return jsonify(service.to_dict())


@api_bp.route("/services/<int:service_id>", methods=["DELETE"])
def delete_service(service_id):
    service = Service.query.get_or_404(service_id)
    db.session.delete(service)
    db.session.commit()
    return jsonify({"message": f"Service {service_id} deleted"})


# ---------- BOOKINGS ----------

@api_bp.route("/bookings", methods=["GET"])
def get_bookings():
    bookings = Booking.query.all()
    return jsonify([b.to_dict() for b in bookings])


@api_bp.route("/bookings/<int:booking_id>", methods=["GET"])
def get_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return jsonify(booking.to_dict())


@api_bp.route("/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(silent=True) or {}

    required = ["user_id", "service_id", "booking_date", "booking_time"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    try:
        booking_date = datetime.strptime(data["booking_date"], "%Y-%m-%d").date()
        booking_time = datetime.strptime(data["booking_time"], "%H:%M").time()
    except ValueError:
        return jsonify({"error": "booking_date must be YYYY-MM-DD, booking_time must be HH:MM"}), 400

    booking = Booking(
        user_id=data["user_id"],
        service_id=data["service_id"],
        staff_id=data.get("staff_id"),
        booking_date=booking_date,
        booking_time=booking_time,
        status=data.get("status", "pending"),
        payment_status=data.get("payment_status", "unpaid"),
    )
    db.session.add(booking)
    db.session.commit()
    send_booking_confirmation_email(booking)
    return jsonify(booking.to_dict()), 201


@api_bp.route("/bookings/<int:booking_id>", methods=["PUT"])
def update_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    data = request.get_json(silent=True) or {}

    if "booking_date" in data:
        booking.booking_date = datetime.strptime(data["booking_date"], "%Y-%m-%d").date()
    if "booking_time" in data:
        booking.booking_time = datetime.strptime(data["booking_time"], "%H:%M").time()
    for field in ["staff_id", "status", "payment_status"]:
        if field in data:
            setattr(booking, field, data[field])

    db.session.commit()
    return jsonify(booking.to_dict())


@api_bp.route("/bookings/<int:booking_id>", methods=["DELETE"])
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    return jsonify({"message": f"Booking {booking_id} deleted"})


# ---------- USERS (minimal, for creating test customers to book with) ----------

@api_bp.route("/users", methods=["GET"])
def get_users():
    users = User.query.all()
    return jsonify([
        {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "is_admin": u.is_admin}
        for u in users
    ])


@api_bp.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not name or not email or not password:
        return jsonify({"error": "name, email and password are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "a user with that email already exists"}), 409

    user = User(name=name, email=email, phone=data.get("phone"))
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"id": user.id, "name": user.name, "email": user.email}), 201
