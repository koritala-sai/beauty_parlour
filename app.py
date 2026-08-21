import os

from flask import Flask

from config import Config, ProductionConfig
from extensions import db, login_manager, csrf, limiter
from models import User


def create_app():
    app = Flask(__name__)

    # Use production configuration when deployed
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Login settings
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            return None

    # Import blueprints
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.booking import booking_bp
    from routes.admin import admin_bp
    from routes.api import api_bp

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    debug_mode = os.environ.get(
        "FLASK_DEBUG",
        "false"
    ).strip().lower() in (
        "1",
        "true",
        "yes",
    )

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=debug_mode,
    )