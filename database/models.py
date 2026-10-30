import logging
from datetime import datetime, timezone
from database.mongodb import get_collection

logger = logging.getLogger(__name__)

SESSIONS_COLLECTION = "sessions"
USER_SESSIONS_COLLECTION = "user_sessions"


# ─── Indexes ──────────────────────────────────────────────────────────────────

def ensure_indexes():
    """Create indexes for fast lookups. Safe to call multiple times (idempotent)."""
    try:
        sessions = get_collection(SESSIONS_COLLECTION)
        sessions.create_index("unique_id", unique=True, background=True)
        sessions.create_index("user_id", background=True)

        user_sessions = get_collection(USER_SESSIONS_COLLECTION)
        user_sessions.create_index("user_id", unique=True, background=True)

        logger.info("MongoDB indexes ensured for sessions and user_sessions collections")
    except Exception as e:
        logger.warning("Could not create indexes: %s", e)


# ─── Session Model ───────────────────────────────────────────────────────────

def create_session(unique_id, session_string, user_id, user_name, user_username):
    collection = get_collection(SESSIONS_COLLECTION)
    now = datetime.now(timezone.utc)
    document = {
        "unique_id": unique_id,
        "session_string": session_string,
        "user_id": user_id,
        "user_name": user_name,
        "user_username": user_username,
        "created_at": now,
        "last_accessed": now,
    }
    result = collection.insert_one(document)
    logger.info("Created session for user_id=%s with unique_id=%s", user_id, unique_id)
    return str(result.inserted_id)


def get_session_by_unique_id(unique_id):
    collection = get_collection(SESSIONS_COLLECTION)
    session = collection.find_one({"unique_id": unique_id})
    if session:
        session["_id"] = str(session["_id"])
    return session


def get_session_by_user_id(user_id):
    collection = get_collection(SESSIONS_COLLECTION)
    session = collection.find_one({"user_id": user_id})
    if session:
        session["_id"] = str(session["_id"])
    return session


def delete_session_by_unique_id(unique_id):
    collection = get_collection(SESSIONS_COLLECTION)
    result = collection.delete_one({"unique_id": unique_id})
    deleted = result.deleted_count > 0
    if deleted:
        logger.info("Deleted session with unique_id=%s", unique_id)
    else:
        logger.warning("No session found with unique_id=%s to delete", unique_id)
    return deleted


def delete_session_by_user_id(user_id):
    collection = get_collection(SESSIONS_COLLECTION)
    result = collection.delete_one({"user_id": user_id})
    deleted = result.deleted_count > 0
    if deleted:
        logger.info("Deleted session for user_id=%s", user_id)
    else:
        logger.warning("No session found for user_id=%s to delete", user_id)
    return deleted


def update_last_accessed(unique_id):
    collection = get_collection(SESSIONS_COLLECTION)
    result = collection.update_one(
        {"unique_id": unique_id},
        {"$set": {"last_accessed": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0


def user_has_active_session(user_id):
    collection = get_collection(SESSIONS_COLLECTION)
    return collection.count_documents({"user_id": user_id}) > 0


# ─── UserSession Model ────────────────────────────────────────────────────────

def create_user_session(user_id, unique_id):
    collection = get_collection(USER_SESSIONS_COLLECTION)
    now = datetime.now(timezone.utc)
    collection.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "unique_id": unique_id, "created_at": now}},
        upsert=True,
    )
    logger.info("User session mapping updated: user_id=%s -> unique_id=%s", user_id, unique_id)


def get_user_session(user_id):
    collection = get_collection(USER_SESSIONS_COLLECTION)
    doc = collection.find_one({"user_id": user_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def delete_user_session(user_id):
    collection = get_collection(USER_SESSIONS_COLLECTION)
    result = collection.delete_one({"user_id": user_id})
    deleted = result.deleted_count > 0
    if deleted:
        logger.info("Deleted user session for user_id=%s", user_id)
    return deleted


def delete_user_session_by_unique_id(unique_id):
    collection = get_collection(USER_SESSIONS_COLLECTION)
    result = collection.delete_one({"unique_id": unique_id})
    deleted = result.deleted_count > 0
    if deleted:
        logger.info("Deleted user session mapping for unique_id=%s", unique_id)
    return deleted
