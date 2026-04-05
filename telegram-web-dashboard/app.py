import os
import logging
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.environ.get("SESSION_SECRET", "dev-secret"))

_db = None


def get_db():
    global _db
    if _db is None:
        try:
            from database.mongodb import connect_to_mongodb
            _db = connect_to_mongodb()
            logger.info("MongoDB connection established")
        except Exception as e:
            logger.error("MongoDB connection failed: %s", str(e))
    return _db


with app.app_context():
    get_db()


@app.route("/health", methods=["GET"])
def health():
    db_status = "connected" if get_db() is not None else "disconnected"
    return jsonify({"status": "healthy", "database": db_status})


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    logger.info("Starting Flask app on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
