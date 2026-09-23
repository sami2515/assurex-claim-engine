from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db(app):
    """Initialize database with the Flask application context."""
    db.init_app(app)
    with app.app_context():
        # Import models so SQLAlchemy registers all tables
        import src.models.entities  # noqa: F401
        db.create_all()
