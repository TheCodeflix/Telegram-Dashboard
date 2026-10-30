import os
import asyncio
import logging
import time
import threading
from functools import wraps
from flask import Flask, render_template, jsonify, request
import config

# ─── Logging ──────────────────────────────────────────────────────────────────

os.makedirs("logs", exist_ok=True)

_log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
_log_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(level=_log_level, format=_log_fmt)

_file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(_log_fmt))
logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger(__name__)

# ─── Pyrogram import guard ────────────────────────────────────────────────────
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

# ─── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY or config.SESSION_SECRET or "dev-secret"

DOMAIN = config.DOMAIN
SESSION_MAX_AGE_HOURS = config.SESSION_MAX_AGE_HOURS  # 0 = no expiry

# ─── MongoDB ──────────────────────────────────────────────────────────────────

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
    try:
        from database.models import ensure_indexes
        ensure_indexes()
    except Exception as e:
        logger.warning("Could not ensure DB indexes: %s", e)

# ─── In-memory Rate Limiter ───────────────────────────────────────────────────
# Simple sliding-window rate limiter keyed on unique_link (or IP for anon).

_rl_store: dict[str, list[float]] = {}
_rl_lock = threading.Lock()
_RL_MAX = 100
_RL_WINDOW = 60  # seconds


def _rate_limit_key() -> str:
    return (
        request.view_args.get("unique_link")
        or request.headers.get("X-Forwarded-For", request.remote_addr)
    )


def rate_limit(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        key = _rate_limit_key()
        now = time.monotonic()
        with _rl_lock:
            calls = [t for t in _rl_store.get(key, []) if now - t < _RL_WINDOW]
            if len(calls) >= _RL_MAX:
                logger.warning("Rate limit hit for key=%s", key)
                if request.is_json or request.path.startswith("/channel/"):
                    return jsonify({"success": False, "error": "Rate limit exceeded. Please wait a moment."}), 429
                return render_template("error.html",
                                       message="Too many requests. Please wait a moment before retrying.",
                                       title="Rate Limit"), 429
            calls.append(now)
            _rl_store[key] = calls
        return f(*args, **kwargs)
    return wrapper


# ─── Simple In-memory Cache ───────────────────────────────────────────────────

_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 5 minutes


def cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
        if entry:
            ts, data = entry
            if time.monotonic() - ts < _CACHE_TTL:
                return data
            del _cache[key]
    return None


def cache_set(key: str, data):
    with _cache_lock:
        _cache[key] = (time.monotonic(), data)


def cache_bust(key: str):
    with _cache_lock:
        _cache.pop(key, None)


# ─── Security Headers ─────────────────────────────────────────────────────────

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


# ─── Session validation helper ────────────────────────────────────────────────

def _get_session_or_fail(unique_link):
    """
    Returns (session_doc, None) on success.
    Returns (None, error_response_tuple) on failure.
    Session is also checked for max-age expiry if SESSION_MAX_AGE_HOURS > 0.
    """
    from database import models
    from datetime import datetime, timezone, timedelta

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        logger.warning("Invalid unique_link=%s", unique_link)
        return None, (jsonify({"success": False, "error": "Invalid or expired link."}), 404)

    if SESSION_MAX_AGE_HOURS > 0:
        created = session.get("created_at")
        if created:
            age = datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc)
            if age > timedelta(hours=SESSION_MAX_AGE_HOURS):
                models.delete_session_by_unique_id(unique_link)
                logger.info("Expired session cleaned up: unique_link=%s", unique_link)
                return None, (jsonify({"success": False, "error": "Session expired."}), 410)

    return session, None


# ─── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"error": "Not found."}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    logger.error("500 Internal Server Error: %s", str(e), exc_info=True)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"error": "Internal server error."}), 500
    return render_template("500.html"), 500


@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({"success": False, "error": "Rate limit exceeded."}), 429


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
@rate_limit
def dashboard(unique_link):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        logger.warning("Dashboard access: invalid unique_link=%s", unique_link)
        return render_template("404.html"), 404

    models.update_last_accessed(unique_link)
    session_string = session["session_string"]

    cache_key = f"user_info:{unique_link}"
    user_info = cache_get(cache_key)
    if user_info is None:
        try:
            user_info = telegram_client.get_user_info(session_string)
            cache_set(cache_key, user_info)
        except Exception as e:
            logger.error("Failed to get user info for unique_link=%s: %s", unique_link, e)
            return render_template(
                "500.html",
                message="Failed to connect to Telegram. Your session may have expired."
            ), 503

    dialogs_key = f"dialogs:{unique_link}"
    dialogs_data = cache_get(dialogs_key)
    if dialogs_data is None:
        try:
            raw_dialogs = telegram_client.get_all_dialogs(session_string)
            sorted_dialogs = channel_utils.sort_dialogs_by_type(raw_dialogs)
            counts = channel_utils.count_dialogs(sorted_dialogs)
            dialogs_data = {"sorted": sorted_dialogs, "counts": counts}
            cache_set(dialogs_key, dialogs_data)
        except Exception as e:
            logger.error("Failed to fetch dialogs for unique_link=%s: %s", unique_link, e)
            dialogs_data = {
                "sorted": {
                    "channels": [], "groups": [], "contacts": [], "bots": [],
                    "access_categories": {"owner": [], "admin": [], "member": []},
                },
                "counts": {"channels": 0, "groups": 0, "contacts": 0, "bots": 0,
                           "owner": 0, "admin": 0, "member": 0},
            }

    return render_template(
        "dashboard.html",
        user_info=user_info,
        dialogs=dialogs_data["sorted"],
        counts=dialogs_data["counts"],
        unique_link=unique_link,
        domain=DOMAIN,
    )


# ─── Channel View ─────────────────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>", methods=["GET"])
@rate_limit
def channel_view(unique_link, channel_id):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        return render_template("404.html"), 404

    models.update_last_accessed(unique_link)
    session_string = session["session_string"]

    cache_key = f"channel:{unique_link}:{channel_id}"
    data = cache_get(cache_key)
    if data is None:
        try:
            data = telegram_client.get_channel_full(session_string, channel_id)
            cache_set(cache_key, data)
        except Exception as e:
            logger.error("Failed to fetch channel %s for unique_link=%s: %s", channel_id, unique_link, e)
            return render_template("500.html"), 503

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
@rate_limit
def profile(unique_link):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        return render_template("404.html"), 404

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
@rate_limit
def web_logout(unique_link):
    from database import models

    session = models.get_session_by_unique_id(unique_link)
    if not session:
        return render_template("404.html"), 404

    models.delete_session_by_unique_id(unique_link)
    models.delete_user_session_by_unique_id(unique_link)

    cache_bust(f"user_info:{unique_link}")
    cache_bust(f"dialogs:{unique_link}")

    logger.info("Web logout: unique_link=%s", unique_link)
    return render_template(
        "error.html",
        message="Dashboard session removed. Your Telegram account remains active in other apps and devices.",
        title="Logged Out"
    )


# ─── AJAX: Generate invite link ───────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/invite", methods=["POST"])
@rate_limit
def channel_invite(unique_link, channel_id):
    session, err = _get_session_or_fail(unique_link)
    if err:
        return err
    try:
        invite_link = telegram_client.create_invite_link(session["session_string"], channel_id)
        logger.info("Invite link created: channel=%s unique_link=%s", channel_id, unique_link)
        return jsonify({"success": True, "invite_link": invite_link})
    except Exception as e:
        logger.error("Failed to create invite link: %s", e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Revoke invite link ─────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/revoke_invite", methods=["POST"])
@rate_limit
def channel_revoke_invite(unique_link, channel_id):
    session, err = _get_session_or_fail(unique_link)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    invite_link = data.get("invite_link", "").strip()
    if not invite_link:
        return jsonify({"success": False, "error": "invite_link is required"}), 400

    try:
        telegram_client.revoke_invite_link(session["session_string"], channel_id, invite_link)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to revoke invite link: %s", e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Transfer ownership ─────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/transfer", methods=["POST"])
@rate_limit
def channel_transfer(unique_link, channel_id):
    session, err = _get_session_or_fail(unique_link)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    target_user_id = data.get("target_user_id", "").strip()
    password       = data.get("password", "").strip()

    if not target_user_id:
        return jsonify({"success": False, "error": "target_user_id is required"}), 400
    if not password:
        return jsonify({"success": False, "error": "2FA password is required"}), 400

    try:
        target_user_id = int(target_user_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "target_user_id must be a number"}), 400

    try:
        telegram_client.transfer_ownership(
            session["session_string"], channel_id, target_user_id, password
        )
        logger.info(
            "Ownership transferred: channel=%s -> user=%s by unique_link=%s",
            channel_id, target_user_id, unique_link,
        )
        return jsonify({"success": True})
    except Exception as e:
        err_msg = str(e)
        logger.error("Ownership transfer failed: %s", err_msg)
        if "PASSWORD_HASH_INVALID" in err_msg:
            return jsonify({"success": False, "error": "Wrong 2FA password. Please try again."}), 400
        if "CHAT_ADMIN_REQUIRED" in err_msg:
            return jsonify({"success": False, "error": "You are not the owner of this chat."}), 403
        if "USER_NOT_MUTUAL_CONTACT" in err_msg:
            return jsonify({"success": False,
                            "error": "Target user must be in your contacts and have you as a contact."}), 400
        if "CHANNELS_TOO_MUCH" in err_msg:
            return jsonify({"success": False, "error": "Target user has too many channels/groups."}), 400
        return jsonify({"success": False, "error": f"Transfer failed: {err_msg}"}), 400


# ─── AJAX: Delete message ─────────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/delete_message", methods=["POST"])
@rate_limit
def channel_delete_message(unique_link, channel_id):
    session, err = _get_session_or_fail(unique_link)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id")
    if not message_id:
        return jsonify({"success": False, "error": "message_id is required"}), 400

    try:
        message_id = int(message_id)
        telegram_client.delete_message(session["session_string"], channel_id, message_id)
        cache_bust(f"channel:{unique_link}:{channel_id}")
        logger.info("Message %s deleted in channel=%s", message_id, channel_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete message %s: %s", message_id, e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Members pagination ─────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/members", methods=["GET"])
@rate_limit
def channel_members_ajax(unique_link, channel_id):
    session, err = _get_session_or_fail(unique_link)
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
        logger.error("Members fetch error for channel=%s: %s", channel_id, e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── AJAX: Messages pagination ────────────────────────────────────────────────

@app.route("/channel/<unique_link>/<int:channel_id>/messages", methods=["GET"])
@rate_limit
def channel_messages_ajax(unique_link, channel_id):
    session, err = _get_session_or_fail(unique_link)
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
        logger.error("Messages fetch error for channel=%s: %s", channel_id, e)
        return jsonify({"success": False, "error": str(e)}), 400


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = config.PORT
    debug = config.FLASK_ENV == "development"
    logger.info("Starting Flask app on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
