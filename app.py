import logging
from flask import Flask
from flask_migrate import Migrate
from config import Config
from models import db
from models.user import User
from models.validation import Validation
from routes.auth import auth_bp
from routes.views import views_bp
from routes.api import api_bp
from services.official_reference_service import get_reference_status

logging.basicConfig(level=logging.INFO)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.logger.info("Groq configured: %s (model=%s)",
                     bool(app.config.get("GROQ_API_KEY")), app.config.get("GROQ_MODEL"))
    db.init_app(app)
    Migrate(app, db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
    with app.app_context():
        db.create_all()
    # Build/validate the local whole-India reference index once at startup.
    # If the reference files are missing, keep the app usable and let the
    # validation layer report the missing-data condition instead of crashing.
    try:
        ref_status = get_reference_status()
        app.logger.info(
            "Reference data: India Post=%s (%s rows), LGD villages=%s (%s rows), mapping=%s (%s rows)",
            ref_status.get("india_post_file"), ref_status.get("india_post_rows", 0),
            ref_status.get("lgd_villages_file"), ref_status.get("lgd_village_rows", 0),
            ref_status.get("postal_lgd_mapping_file"), ref_status.get("postal_lgd_mapping_rows", 0),
        )
    except Exception as exc:
        app.logger.warning("Reference-data index unavailable at startup: %s", type(exc).__name__)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
