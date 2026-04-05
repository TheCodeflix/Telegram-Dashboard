import random
import string
import logging
from datetime import datetime, timezone
from database.mongodb import get_collection

logger = logging.getLogger(__name__)

SESSIONS_COLLECTION = "sessions"
UNIQUE_ID_LENGTH = 12
SESSION_MIN_LENGTH = 20
SESSION_MAX_LENGTH = 500


def generate_unique_link():
    chars = string.ascii_letters + string.digits
    collection = get_collection(SESSIONS_COLLECTION)

    while True:
        unique_id = "".join(random.choices(chars, k=UNIQUE_ID_LENGTH))
        existing = collection.find_one({"unique_id": unique_id})
        if not existing:
            logger.debug("Generated unique link: %s", unique_id)
            return unique_id


def validate_session_string(session_string):
    if not isinstance(session_string, str):
        return False
    length = len(session_string.strip())
    valid = SESSION_MIN_LENGTH <= length <= SESSION_MAX_LENGTH
    if not valid:
        logger.warning(
            "Session string validation failed: length=%d (expected %d-%d)",
            length, SESSION_MIN_LENGTH, SESSION_MAX_LENGTH,
        )
    return valid


def format_session_for_db(session_string, user_info, unique_link):
    now = datetime.now(timezone.utc)
    return {
        "unique_id": unique_link,
        "session_string": session_string.strip(),
        "user_id": user_info.get("user_id"),
        "user_name": user_info.get("user_name", ""),
        "user_username": user_info.get("user_username", ""),
        "created_at": now,
        "last_accessed": now,
    }
