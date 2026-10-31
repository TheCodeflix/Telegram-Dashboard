import logging

logger = logging.getLogger(__name__)

DIALOG_TYPES = ("channel", "supergroup", "group", "bot", "user")


def get_dialog_type(dialog: dict) -> str:
    return dialog.get("type", "user")


def format_dialog(dialog: dict) -> dict:
    chat_id = dialog.get("id")
    username = dialog.get("username") or ""
    chat_link = f"https://t.me/{username}" if username else dialog.get("invite_link") or ""
    return {
        "id": chat_id,
        "chat_id": chat_id,
        "title": dialog.get("title") or "Unknown",
        "username": username,
        "type": get_dialog_type(dialog),
        "role": dialog.get("role", "member"),
        "member_count": dialog.get("member_count"),
        "is_verified": dialog.get("is_verified", False),
        "is_scam": dialog.get("is_scam", False),
        "photo": dialog.get("photo"),
        "chat_link": chat_link,
        "avatar_letter": _avatar_letter(dialog.get("title") or "?"),
        "avatar_color": _avatar_color(dialog.get("id", 0)),
    }


def sort_dialogs_by_type(dialogs: list) -> dict:
    result = {
        "channels": [],
        "groups": [],
        "contacts": [],
        "bots": [],
        "access_categories": {"owner": [], "admin": [], "member": []},
    }
    for raw in dialogs:
        d = format_dialog(raw)
        t = d["type"]
        if d["role"] not in result["access_categories"]:
            d["role"] = "member"
        if t == "channel":
            result["channels"].append(d)
            result["access_categories"][d["role"]].append(d)
        elif t in ("supergroup", "group"):
            result["groups"].append(d)
            result["access_categories"][d["role"]].append(d)
        elif t == "bot":
            result["bots"].append(d)
        else:
            result["contacts"].append(d)

    for key in ("channels", "groups", "contacts", "bots"):
        result[key].sort(key=lambda x: (x["title"] or "").lower())
    for items in result["access_categories"].values():
        items.sort(key=lambda x: (x["title"] or "").lower())

    return result


def count_dialogs(sorted_dialogs: dict) -> dict:
    return {
        "channels": len(sorted_dialogs["channels"]),
        "groups": len(sorted_dialogs["groups"]),
        "contacts": len(sorted_dialogs["contacts"]),
        "bots": len(sorted_dialogs["bots"]),
        "owner": len(sorted_dialogs["access_categories"]["owner"]),
        "admin": len(sorted_dialogs["access_categories"]["admin"]),
        "member": len(sorted_dialogs["access_categories"]["member"]),
    }


def format_member(member: dict) -> dict:
    """Enrich a raw member dict with avatar helpers."""
    return {
        **member,
        "avatar_letter": _avatar_letter(member.get("name") or "?"),
        "avatar_color": _avatar_color(member.get("user_id", 0)),
    }


def format_members_list(members: list) -> list:
    return [format_member(m) for m in members]


def format_message(msg: dict) -> dict:
    """Enrich a raw message dict (truncate text, add media label)."""
    text = msg.get("text") or ""
    return {
        **msg,
        "short_text": text[:400] + ("…" if len(text) > 400 else ""),
        "media_label": _media_label(msg.get("media_type")),
    }


def format_messages_list(messages: list) -> list:
    return [format_message(m) for m in messages]


# ─── Private helpers ──────────────────────────────────────────────────────────

_COLORS = [
    "#1abc9c", "#2ecc71", "#3498db", "#9b59b6", "#e67e22",
    "#e74c3c", "#16a085", "#27ae60", "#2980b9", "#8e44ad",
    "#f39c12", "#d35400", "#c0392b", "#2c3e50", "#7f8c8d",
]

_MEDIA_LABELS = {
    "PHOTO": "📷 Photo",
    "VIDEO": "🎬 Video",
    "AUDIO": "🎵 Audio",
    "VOICE": "🎤 Voice",
    "DOCUMENT": "📄 Document",
    "STICKER": "🎭 Sticker",
    "ANIMATION": "🎞 GIF",
    "POLL": "📊 Poll",
    "LOCATION": "📍 Location",
    "CONTACT": "👤 Contact",
}


def _avatar_letter(title: str) -> str:
    for ch in title:
        if ch.isalnum():
            return ch.upper()
    return "?"


def _avatar_color(chat_id: int) -> str:
    idx = abs(chat_id) % len(_COLORS)
    return _COLORS[idx]


def _media_label(media_type: str | None) -> str:
    if not media_type:
        return ""
    key = (media_type or "").upper().replace("MESSAGEMEDIATYPE.", "")
    return _MEDIA_LABELS.get(key, "📎 Media")
