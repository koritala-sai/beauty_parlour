from flask import Blueprint, render_template, send_from_directory, current_app

from models import Service, Review

main_bp = Blueprint("main", __name__)


@main_bp.route("/sw.js")
def service_worker():
    # Served from root (not /static/sw.js) so its scope covers the whole
    # site, not just the /static folder.
    response = send_from_directory(current_app.static_folder, "sw.js")
    response.headers["Content-Type"] = "application/javascript"
    return response


@main_bp.route("/")
def home():
    featured_services = Service.query.filter_by(is_active=True).limit(6).all()

    # Real customer reviews, best/most recent first. Falls back to nothing
    # (template should handle an empty list gracefully) until customers
    # start leaving reviews.
    reviews = (
        Review.query.filter(Review.rating >= 4)
        .order_by(Review.created_at.desc())
        .limit(3)
        .all()
    )

    return render_template("index.html", services=featured_services, reviews=reviews)


@main_bp.route("/services")
def services():
    all_services = Service.query.filter_by(is_active=True).all()

    # Average rating + review count per service, for star display on cards
    ratings = {}
    for s in all_services:
        service_reviews = Review.query.filter_by(service_id=s.id).all()
        if service_reviews:
            avg = sum(r.rating for r in service_reviews) / len(service_reviews)
            ratings[s.id] = {"avg": round(avg, 1), "count": len(service_reviews)}

    return render_template("services.html", services=all_services, ratings=ratings)