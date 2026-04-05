import os
import logging
import asyncio
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")


def create_client(session_string: str) -> Client:
    return Client(
        name="dashboard_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
    )


async def _get_user_info(client: Client) -> dict:
    me = await client.get_me()
    return {
        "user_id": me.id,
        "user_name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
        "first_name": me.first_name or "",
        "last_name": me.last_name or "",
        "username": me.username or "",
        "phone": me.phone_number or "",
        "is_premium": getattr(me, "is_premium", False),
        "dc_id": getattr(me, "dc_id", None),
    }


async def _get_all_dialogs(client: Client, limit: int = 200) -> list:
    dialogs = []
    try:
        async for dialog in client.get_dialogs(limit=limit):
            chat = dialog.chat
            try:
                chat_type = _resolve_chat_type(chat)
                entry = {
                    "id": chat.id,
                    "title": getattr(chat, "title", None) or _full_name(chat),
                    "username": getattr(chat, "username", None) or "",
                    "type": chat_type,
                    "member_count": getattr(chat, "members_count", None),
                    "is_verified": getattr(chat, "is_verified", False),
                    "is_scam": getattr(chat, "is_scam", False),
                }
                dialogs.append(entry)
            except Exception as e:
                logger.debug("Skipping dialog %s: %s", getattr(chat, "id", "?"), e)
    except FloodWait as e:
        logger.warning("FloodWait getting dialogs: %s seconds", e.value)
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error("Error fetching dialogs: %s", e)
    return dialogs


async def _get_channel_info(client: Client, channel_id: int) -> dict:
    try:
        chat = await client.get_chat(channel_id)
        return {
            "id": chat.id,
            "title": getattr(chat, "title", "") or _full_name(chat),
            "username": getattr(chat, "username", "") or "",
            "description": getattr(chat, "description", "") or "",
            "member_count": getattr(chat, "members_count", 0) or 0,
            "type": _resolve_chat_type(chat),
            "is_verified": getattr(chat, "is_verified", False),
            "is_scam": getattr(chat, "is_scam", False),
            "linked_chat": getattr(chat, "linked_chat", None),
            "invite_link": getattr(chat, "invite_link", None) or "",
        }
    except Exception as e:
        logger.error("Error fetching channel info for %s: %s", channel_id, e)
        return {}


async def _get_channel_admins(client: Client, channel_id: int) -> list:
    admins = []
    try:
        async for member in client.get_chat_members(channel_id, filter="administrators"):
            user = member.user
            admins.append({
                "user_id": user.id,
                "name": _full_name(user),
                "username": user.username or "",
                "status": str(member.status).split(".")[-1].replace("ChatMemberStatus.", ""),
                "is_bot": user.is_bot,
                "custom_title": getattr(member, "custom_title", "") or "",
            })
    except Exception as e:
        logger.warning("Error fetching admins for %s: %s", channel_id, e)
    return admins


async def _get_channel_members(client: Client, channel_id: int, limit: int = 50) -> list:
    members = []
    try:
        async for member in client.get_chat_members(channel_id, limit=limit):
            user = member.user
            members.append({
                "user_id": user.id,
                "name": _full_name(user),
                "username": user.username or "",
                "is_bot": user.is_bot,
                "status": str(member.status).split(".")[-1],
            })
    except Exception as e:
        logger.warning("Error fetching members for %s: %s", channel_id, e)
    return members


async def _get_channel_messages(client: Client, channel_id: int, limit: int = 30) -> list:
    messages = []
    try:
        async for msg in client.get_chat_history(channel_id, limit=limit):
            sender_name = ""
            if msg.from_user:
                sender_name = _full_name(msg.from_user)
            elif msg.sender_chat:
                sender_name = getattr(msg.sender_chat, "title", "") or ""

            messages.append({
                "id": msg.id,
                "text": msg.text or msg.caption or "",
                "date": msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "",
                "sender": sender_name,
                "views": getattr(msg, "views", None),
                "is_pinned": getattr(msg, "pinned", False),
                "has_media": bool(msg.media),
            })
    except Exception as e:
        logger.warning("Error fetching messages for %s: %s", channel_id, e)
    return messages


# ─── Public sync wrappers (for Flask routes) ─────────────────────────────────

def run_in_session(session_string: str, coro_factory):
    """
    Creates a Pyrogram client, connects, runs coro_factory(client),
    disconnects, and returns the result. Runs in a fresh event loop.
    """
    async def _runner():
        client = create_client(session_string)
        try:
            await client.start()
            return await coro_factory(client)
        finally:
            try:
                await client.stop()
            except Exception:
                pass
    return asyncio.run(_runner())


def get_user_info(session_string: str) -> dict:
    return run_in_session(session_string, _get_user_info)


def get_all_dialogs(session_string: str, limit: int = 200) -> list:
    return run_in_session(session_string, lambda c: _get_all_dialogs(c, limit))


def get_channel_info(session_string: str, channel_id: int) -> dict:
    return run_in_session(session_string, lambda c: _get_channel_info(c, channel_id))


def get_channel_full(session_string: str, channel_id: int) -> dict:
    async def _all(client):
        info = await _get_channel_info(client, channel_id)
        admins = await _get_channel_admins(client, channel_id)
        members = await _get_channel_members(client, channel_id)
        messages = await _get_channel_messages(client, channel_id)
        return {
            "info": info,
            "admins": admins,
            "members": members,
            "messages": messages,
        }
    return run_in_session(session_string, _all)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _full_name(user) -> str:
    parts = [getattr(user, "first_name", "") or "", getattr(user, "last_name", "") or ""]
    return " ".join(p for p in parts if p).strip() or "Unknown"


def _resolve_chat_type(chat) -> str:
    try:
        t = chat.type
        if t == ChatType.CHANNEL:
            return "channel"
        if t == ChatType.SUPERGROUP:
            return "supergroup"
        if t == ChatType.GROUP:
            return "group"
        if t == ChatType.BOT:
            return "bot"
        if t == ChatType.PRIVATE:
            return "bot" if getattr(chat, "is_bot", False) else "user"
    except Exception:
        pass
    return "user"
