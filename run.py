import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Development server only. Use Waitress/Gunicorn/a reverse proxy for production.
    debug = os.environ.get("AUTOCARE_DEBUG", "0").lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug)
