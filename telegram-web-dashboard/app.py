import os
import asyncio
import logging
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

load_dotenv()

# Pyrogram's sync module calls asyncio.get_event_loop() at import time.
# Importing here (main thread) ensures the module is cached before Flask's
# threaded worker threads touch it.
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


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _get_session_or_404(unique_link):
    """Return (session_doc, None) on success or (None, error_response) on failure."""
    from database import models
    session = models.get_session_by_unique_id(unique_link)
    if not session:
        return None, (jsonify({"success": False, "error": "Invalid or expired link."}), 404)
    return session, None


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

    members = channel_utils.format_members_list(data.get("members", []))
    messages = channel_utils.format_messages_list(data.get("messages", []))

    return render_template(
        "channel_view.html",
        info=data.get("info", {}),
        admins=data.get("admins", []),
        members=members,
        messages=messages,
        photo=data.get("photo"),
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


# ─── AJAX: Generate invite link ───────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/invite", methods=["POST"])
def channel_invite(unique_link, channel_id):
    session, err = _get_session_or_404(unique_link)
    if err:
        return err

    try:
        invite_link = telegram_client.create_invite_link(session["session_string"], channel_id)
        logger.info("Invite link created for channel=%s unique_link=%s", channel_id, unique_link)
        return jsonify({"success": True, "invite_link": invite_link})
    except Exception as e:
        logger.error("Failed to create invite link: %s", e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Revoke invite link ─────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/revoke_invite", methods=["POST"])
def channel_revoke_invite(unique_link, channel_id):
    session, err = _get_session_or_404(unique_link)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    invite_link = data.get("invite_link", "").strip()
    if not invite_link:
        return jsonify({"success": False, "error": "invite_link is required"}), 400

    try:
        telegram_client.revoke_invite_link(session["session_string"], channel_id, invite_link)
        logger.info("Invite link revoked for channel=%s", channel_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to revoke invite link: %s", e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Transfer ownership ─────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/transfer", methods=["POST"])
def channel_transfer(unique_link, channel_id):
    session, err = _get_session_or_404(unique_link)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        return jsonify({"success": False, "error": "target_user_id is required"}), 400

    try:
        target_user_id = int(target_user_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "target_user_id must be a number"}), 400

    # Ownership transfer requires the user's 2FA password via the Telegram API.
    # This is intentionally not implemented server-side for security reasons.
    # Advise user to use the official Telegram app for this action.
    return jsonify({
        "success": False,
        "error": (
            "Ownership transfer requires your Telegram 2FA password and cannot be performed "
            "safely via the web dashboard. Please use the official Telegram app to transfer ownership."
        )
    }), 400


# ─── AJAX: Delete message ─────────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/delete_message", methods=["POST"])
def channel_delete_message(unique_link, channel_id):
    session, err = _get_session_or_404(unique_link)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id")
    if not message_id:
        return jsonify({"success": False, "error": "message_id is required"}), 400

    try:
        message_id = int(message_id)
        telegram_client.delete_message(session["session_string"], channel_id, message_id)
        logger.info("Message %s deleted in channel=%s", message_id, channel_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete message %s: %s", message_id, e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Members pagination ─────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/members", methods=["GET"])
def channel_members_ajax(unique_link, channel_id):
    session, err = _get_session_or_404(unique_link)
    if err:
        return err

    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, max(10, int(request.args.get("limit", 50))))
    offset = (page - 1) * limit

    try:
        result = telegram_client.get_channel_members_page(
            session["session_string"], channel_id, limit=limit, offset=offset
        )
        members = channel_utils.format_members_list(result.get("members", []))
        return jsonify({
            "success": True,
            "members": members,
            "count": len(members),
            "page": page,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.error("Failed to fetch members page for channel=%s: %s", channel_id, e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Messages pagination ────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/messages", methods=["GET"])
def channel_messages_ajax(unique_link, channel_id):
    session, err = _get_session_or_404(unique_link)
    if err:
        return err

    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, max(10, int(request.args.get("limit", 30))))
    offset = (page - 1) * limit

    try:
        raw = telegram_client.get_channel_messages_page(
            session["session_string"], channel_id, limit=limit, offset=offset
        )
        messages = channel_utils.format_messages_list(raw)
        return jsonify({
            "success": True,
            "messages": messages,
            "count": len(messages),
            "page": page,
            "limit": limit,
        })
    except Exception as e:
        logger.error("Failed to fetch messages page for channel=%s: %s", channel_id, e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    logger.info("Starting Flask app on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
