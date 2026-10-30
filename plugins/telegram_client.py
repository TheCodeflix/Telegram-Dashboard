import logging
import asyncio
import base64
import functools
import config
from pyrogram import Client, raw
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait
from pyrogram.utils import compute_password_check

logger = logging.getLogger(__name__)

API_ID = config.API_ID
API_HASH = config.API_HASH

_MAX_FLOOD_WAIT = 30   # cap how long we'll sleep on a single FloodWait
_MAX_RETRIES = 3


# ─── Retry decorator ─────────────────────────────────────────────────────────

def _retry_flood(coro_fn):
    """Wraps an async function to auto-retry on FloodWait up to _MAX_RETRIES times."""
    @functools.wraps(coro_fn)
    async def wrapper(*args, **kwargs):
        for attempt in range(_MAX_RETRIES):
            try:
                return await coro_fn(*args, **kwargs)
            except FloodWait as e:
                wait = min(e.value, _MAX_FLOOD_WAIT)
                logger.warning(
                    "FloodWait in %s: sleeping %ds (attempt %d/%d)",
                    coro_fn.__name__, wait, attempt + 1, _MAX_RETRIES,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(wait)
                else:
                    raise
    return wrapper


# ─── Client factory ──────────────────────────────────────────────────────────

def create_client(session_string: str) -> Client:
    return Client(
        name="dashboard_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
    )


# ─── Async operations ─────────────────────────────────────────────────────────

@_retry_flood
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
        "photo": await _get_chat_photo(client, me.id),
    }


@_retry_flood
async def _get_all_dialogs(client: Client, limit: int = 200) -> list:
    dialogs = []
    me = await client.get_me()
    try:
        async for dialog in client.get_dialogs(limit=limit):
            chat = dialog.chat
            try:
                chat_type = _resolve_chat_type(chat)
                role = "member"
                if chat_type in ("channel", "supergroup", "group"):
                    try:
                        member = await client.get_chat_member(chat.id, me.id)
                        status = str(member.status).split(".")[-1].upper()
                        if status == "OWNER":
                            role = "owner"
                        elif status == "ADMINISTRATOR":
                            role = "admin"
                    except Exception as e:
                        logger.debug("Could not resolve role in chat %s: %s", chat.id, e)
                entry = {
                    "id": chat.id,
                    "title": getattr(chat, "title", None) or _full_name(chat),
                    "username": getattr(chat, "username", None) or "",
                    "type": chat_type,
                    "role": role,
                    "member_count": getattr(chat, "members_count", None),
                    "is_verified": getattr(chat, "is_verified", False),
                    "is_scam": getattr(chat, "is_scam", False),
                    "invite_link": getattr(chat, "invite_link", None) or "",
                    "photo": await _get_chat_photo(client, chat.id),
                }
                dialogs.append(entry)
            except Exception as e:
                logger.debug("Skipping dialog %s: %s", getattr(chat, "id", "?"), e)
    except Exception as e:
        logger.error("Error fetching dialogs: %s", e)
    return dialogs


@_retry_flood
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


@_retry_flood
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


@_retry_flood
async def _get_channel_members(client: Client, channel_id: int,
                                limit: int = 50, offset: int = 0) -> dict:
    members = []
    try:
        count = 0
        async for member in client.get_chat_members(channel_id, limit=limit + offset):
            if count < offset:
                count += 1
                continue
            user = member.user
            members.append({
                "user_id": user.id,
                "name": _full_name(user),
                "username": user.username or "",
                "is_bot": user.is_bot,
                "status": str(member.status).split(".")[-1],
            })
            if len(members) >= limit:
                break
    except Exception as e:
        logger.warning("Error fetching members for %s: %s", channel_id, e)
    return {"members": members, "count": len(members), "offset": offset, "limit": limit}


@_retry_flood
async def _get_channel_messages(client: Client, channel_id: int,
                                 limit: int = 30, offset: int = 0) -> list:
    messages = []
    try:
        async for msg in client.get_chat_history(channel_id, limit=limit, offset=offset):
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
                "media_type": str(msg.media).split(".")[-1] if msg.media else None,
            })
    except Exception as e:
        logger.warning("Error fetching messages for %s: %s", channel_id, e)
    messages.reverse()
    return messages


@_retry_flood
async def _get_pinned_messages(client: Client, channel_id: int) -> list:
    pinned = []
    try:
        async for msg in client.get_chat_history(channel_id, limit=100):
            if getattr(msg, "pinned", False):
                sender_name = ""
                if msg.from_user:
                    sender_name = _full_name(msg.from_user)
                elif msg.sender_chat:
                    sender_name = getattr(msg.sender_chat, "title", "") or ""
                pinned.append({
                    "id": msg.id,
                    "text": msg.text or msg.caption or "",
                    "date": msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "",
                    "sender": sender_name,
                    "has_media": bool(msg.media),
                })
    except Exception as e:
        logger.warning("Error fetching pinned messages for %s: %s", channel_id, e)
    return pinned


@_retry_flood
async def _create_invite_link(client: Client, channel_id: int,
                               expire_date=None, member_limit=None) -> str:
    link = await client.create_chat_invite_link(
        channel_id,
        expire_date=expire_date,
        member_limit=member_limit,
    )
    return link.invite_link


@_retry_flood
async def _revoke_invite_link(client: Client, channel_id: int, invite_link: str) -> bool:
    await client.revoke_chat_invite_link(channel_id, invite_link)
    return True


@_retry_flood
async def _delete_message(client: Client, channel_id: int, message_id: int) -> bool:
    await client.delete_messages(channel_id, message_id)
    return True


async def _transfer_ownership(client: Client, channel_id: int,
                               target_user_id: int, password: str) -> bool:
    """
    Transfer ownership of a channel/supergroup to another user.
    Requires the current account's 2FA password.
    """
    # Step 1: Get 2FA password SRP parameters
    pwd_info = await client.invoke(raw.functions.account.GetPassword())

    # Step 2: Compute the SRP check using the provided password
    pwd_check = compute_password_check(pwd_info, password)

    # Step 3: Resolve peers
    channel_peer = await client.resolve_peer(channel_id)
    user_peer    = await client.resolve_peer(target_user_id)

    # Step 4: Call EditCreator to transfer ownership
    await client.invoke(
        raw.functions.channels.EditCreator(
            channel=channel_peer,
            user_id=user_peer,
            password=pwd_check,
        )
    )
    return True


async def _get_chat_photo(client: Client, chat_id: int):
    """Download chat photo and return base64 data URI, or None."""
    try:
        path = await client.download_profile_photo(chat_id, in_memory=True)
        if path:
            data = path.getvalue()
            b64 = base64.b64encode(data).decode()
            return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.debug("Could not download chat photo for %s: %s", chat_id, e)
    return None


# ─── Sync wrapper (one fresh event loop per call) ────────────────────────────

def run_in_session(session_string: str, coro_factory):
    """
    Creates a Pyrogram client, connects, runs coro_factory(client),
    disconnects, and returns the result. Always runs in a brand-new event loop.
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


# ─── Public sync wrappers ────────────────────────────────────────────────────

def get_user_info(session_string: str) -> dict:
    return run_in_session(session_string, _get_user_info)


def get_all_dialogs(session_string: str, limit: int = 200) -> list:
    return run_in_session(session_string, lambda c: _get_all_dialogs(c, limit))


def get_channel_info(session_string: str, channel_id: int) -> dict:
    return run_in_session(session_string, lambda c: _get_channel_info(c, channel_id))


def get_channel_full(session_string: str, channel_id: int) -> dict:
    async def _all(client):
        info    = await _get_channel_info(client, channel_id)
        admins  = await _get_channel_admins(client, channel_id)
        members = await _get_channel_members(client, channel_id, limit=50)
        msgs    = await _get_channel_messages(client, channel_id, limit=30)
        photo   = await _get_chat_photo(client, channel_id)
        return {
            "info": info,
            "admins": admins,
            "members": members.get("members", []),
            "messages": msgs,
            "photo": photo,
        }
    return run_in_session(session_string, _all)


def get_channel_members_page(session_string: str, channel_id: int,
                              limit: int = 50, offset: int = 0) -> dict:
    return run_in_session(
        session_string,
        lambda c: _get_channel_members(c, channel_id, limit=limit, offset=offset),
    )


def get_channel_messages_page(session_string: str, channel_id: int,
                               limit: int = 30, offset: int = 0) -> list:
    return run_in_session(
        session_string,
        lambda c: _get_channel_messages(c, channel_id, limit=limit, offset=offset),
    )


def get_pinned_messages(session_string: str, channel_id: int) -> list:
    return run_in_session(session_string, lambda c: _get_pinned_messages(c, channel_id))


def create_invite_link(session_string: str, channel_id: int,
                        expire_date=None, member_limit=None) -> str:
    return run_in_session(
        session_string,
        lambda c: _create_invite_link(c, channel_id, expire_date, member_limit),
    )


def revoke_invite_link(session_string: str, channel_id: int, invite_link: str) -> bool:
    return run_in_session(
        session_string,
        lambda c: _revoke_invite_link(c, channel_id, invite_link),
    )


def delete_message(session_string: str, channel_id: int, message_id: int) -> bool:
    return run_in_session(
        session_string,
        lambda c: _delete_message(c, channel_id, message_id),
    )


def transfer_ownership(session_string: str, channel_id: int,
                        target_user_id: int, password: str) -> bool:
    return run_in_session(
        session_string,
        lambda c: _transfer_ownership(c, channel_id, target_user_id, password),
    )


def get_chat_photo(session_string: str, chat_id: int):
    return run_in_session(session_string, lambda c: _get_chat_photo(c, chat_id))


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
