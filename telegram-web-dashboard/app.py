import os
import asyncio
import logging
from flask import Flask, render_template, jsonify
from dotenv import load_dotenv

load_dotenv()

# Pyrogram's sync module calls asyncio.get_event_loop() at import time.
# Importing here (main thread, where an event loop exists) ensures the module
# is cached before Flask's threaded worker threads touch it.
try:
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        asyncio.set_event_loop(asyncio.new_event_loop())
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import plugins.telegram_client as telegram_client  # noqa: E402
import plugins.channel_utils as channel_utils      # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.environ.get("SESSION_SECRET", "dev-secret"))

DOMAIN = os.environ.get("DOMAIN", "https://your-app.koyeb.app")

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


# ─── Health & Home ────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    db_status = "connected" if get_db() is not None else "disconnected"
    return jsonify({"status": "healthy", "database": db_status})


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/dashboard/<unique_link>", methods=["GET"])
def dashboard(unique_link):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        logger.warning("Dashboard access: invalid unique_link=%s", unique_link)
        return render_template("error.html", message="Invalid or expired link."), 404

    models.update_last_accessed(unique_link)
    session_string = session["session_string"]

    try:
        user_info = telegram_client.get_user_info(session_string)
    except Exception as e:
        logger.error("Failed to get user info for unique_link=%s: %s", unique_link, e)
        return render_template(
            "error.html",
            message="Failed to connect to Telegram. Your session may have expired."
        ), 503

    try:
        raw_dialogs = telegram_client.get_all_dialogs(session_string)
        sorted_dialogs = channel_utils.sort_dialogs_by_type(raw_dialogs)
        counts = channel_utils.count_dialogs(sorted_dialogs)
    except Exception as e:
        logger.error("Failed to fetch dialogs for unique_link=%s: %s", unique_link, e)
        sorted_dialogs = {"channels": [], "groups": [], "contacts": [], "bots": []}
        counts = {"channels": 0, "groups": 0, "contacts": 0, "bots": 0}

    return render_template(
        "dashboard.html",
        user_info=user_info,
        dialogs=sorted_dialogs,
        counts=counts,
        unique_link=unique_link,
        domain=DOMAIN,
    )


# ─── Channel View ─────────────────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>", methods=["GET"])
def channel_view(unique_link, channel_id):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        return render_template("error.html", message="Invalid or expired link."), 404

    models.update_last_accessed(unique_link)
    session_string = session["session_string"]

    try:
        data = telegram_client.get_channel_full(session_string, channel_id)
    except Exception as e:
        logger.error("Failed to fetch channel %s for unique_link=%s: %s", channel_id, unique_link, e)
        return render_template(
            "error.html",
            message="Failed to fetch channel data. Please try again later."
        ), 503

    return render_template(
        "channel_view.html",
        info=data.get("info", {}),
        admins=data.get("admins", []),
        members=data.get("members", []),
        messages=data.get("messages", []),
        unique_link=unique_link,
        channel_id=channel_id,
    )


# ─── Profile ──────────────────────────────────────────────────────────────────

@app.route("/profile/<unique_link>", methods=["GET"])
def profile(unique_link):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        return render_template("error.html", message="Invalid or expired link."), 404

    models.update_last_accessed(unique_link)
    session_string = session["session_string"]

    try:
        user_info = telegram_client.get_user_info(session_string)
    except Exception as e:
        logger.error("Failed to get profile for unique_link=%s: %s", unique_link, e)
        user_info = {}

    return render_template(
        "profile.html",
        session=session,
        user_info=user_info,
        unique_link=unique_link,
        domain=DOMAIN,
    )


# ─── Web Logout ───────────────────────────────────────────────────────────────

@app.route("/logout/<unique_link>", methods=["GET"])
def web_logout(unique_link):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        return render_template("error.html", message="Invalid or expired link."), 404

    user_id = session.get("user_id")
    models.delete_session_by_unique_id(unique_link)
    if user_id:
        models.delete_user_session(user_id)

    logger.info("Web logout: unique_link=%s user_id=%s", unique_link, user_id)
    return render_template(
        "error.html",
        message="Logged out successfully. This dashboard link has been invalidated.",
        title="Logged Out"
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    logger.info("Starting Flask app on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
