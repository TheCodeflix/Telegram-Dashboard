import logging
import asyncio
import base64
import functools
import hashlib
import threading
import time
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
_PEER_CACHE_TTL = 600
_peer_cache: dict[tuple[str, int], tuple[float, int, str, int]] = {}
_peer_cache_lock = threading.Lock()


def _session_peer_namespace(session_string: str) -> str:
    return hashlib.sha256(session_string.encode("utf-8")).hexdigest()


def clear_peer_cache(session_string: str) -> None:
    namespace = _session_peer_namespace(session_string)
    with _peer_cache_lock:
        for key in [key for key in _peer_cache if key[0] == namespace]:
            del _peer_cache[key]


async def _remember_chat_peer(client: Client, chat_id: int, namespace: str) -> None:
    try:
        peer = await client.storage.get_peer_by_id(chat_id)
    except (KeyError, ValueError):
        return

    if isinstance(peer, raw.types.InputPeerUser):
        peer_type, access_hash = "user", peer.access_hash
    elif isinstance(peer, raw.types.InputPeerChat):
        peer_type, access_hash = "group", 0
    elif isinstance(peer, raw.types.InputPeerChannel):
        peer_type, access_hash = "channel", peer.access_hash
    else:
        return

    now = time.monotonic()
    with _peer_cache_lock:
        expired = [
            key for key, (expires_at, _, _, _) in _peer_cache.items()
            if now >= expires_at
        ]
        for key in expired:
            del _peer_cache[key]
        _peer_cache[(namespace, chat_id)] = (
            now + _PEER_CACHE_TTL, chat_id, peer_type, access_hash
        )


async def _restore_chat_peer(client: Client, chat_id: int, namespace: str) -> bool:
    key = (namespace, chat_id)
    now = time.monotonic()
    with _peer_cache_lock:
        cached = _peer_cache.get(key)
        if cached and now < cached[0]:
            _, peer_id, peer_type, access_hash = cached
        else:
            _peer_cache.pop(key, None)
            return False

    await client.storage.update_peers([
        (peer_id, access_hash, peer_type, None, None)
    ])
    return True


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
async def _get_user_info(client: Client, me=None) -> dict:
    if me is None:
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
        "photo": None,
    }


@_retry_flood
async def _get_all_dialogs(
    client: Client, limit: int = 0, me=None, peer_cache_namespace: str | None = None
) -> list:
    if me is None:
        me = await client.get_me()
    role_semaphore = asyncio.Semaphore(4)
    tasks = []
    entries = []

    async def build_dialog(chat):
        try:
            chat_type = _resolve_chat_type(chat)
            role = "owner" if getattr(chat, "is_creator", False) else "member"
            if chat_type in ("channel", "supergroup", "group"):
                if role != "owner":
                    try:
                        async with role_semaphore:
                            member = await client.get_chat_member(chat.id, me.id)
                        status = str(member.status).split(".")[-1].upper()
                        if status == "OWNER":
                            role = "owner"
                        elif status == "ADMINISTRATOR":
                            role = "admin"
                    except Exception as e:
                        logger.debug("Could not resolve role in chat %s: %s", chat.id, e)
            return {
                "id": chat.id,
                "title": getattr(chat, "title", None) or _full_name(chat),
                "username": getattr(chat, "username", None) or "",
                "type": chat_type,
                "role": role,
                "member_count": getattr(chat, "members_count", None),
                "is_verified": getattr(chat, "is_verified", False),
                "is_scam": getattr(chat, "is_scam", False),
                "invite_link": getattr(chat, "invite_link", None) or "",
                "photo": None,
            }
        except Exception as e:
            logger.warning("Skipping dialog %s: %s", getattr(chat, "id", "?"), e)
            return None

    async for dialog in client.get_dialogs(limit=limit):
        if peer_cache_namespace:
            await _remember_chat_peer(client, dialog.chat.id, peer_cache_namespace)
        tasks.append(asyncio.create_task(build_dialog(dialog.chat)))
        if len(tasks) == 4:
            entries.extend(await asyncio.gather(*tasks))
            tasks.clear()
    if tasks:
        entries.extend(await asyncio.gather(*tasks))
    return [entry for entry in entries if entry is not None]


@_retry_flood
async def _get_channel_info(client: Client, channel_id: int, include_photo: bool = True) -> dict:
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
        "photo": await _get_chat_photo(client, chat) if include_photo else None,
    }


@_retry_flood
async def _get_channel_admins(client: Client, channel_id: int) -> list:
    admins = []
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
    return admins


@_retry_flood
async def _get_channel_members(client: Client, channel_id: int,
                                limit: int = 50, offset: int = 0) -> dict:
    members = []
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
    return {"members": members, "count": len(members), "offset": offset, "limit": limit}


@_retry_flood
async def _get_channel_messages(client: Client, channel_id: int,
                                 limit: int = 30, offset: int = 0) -> list:
    messages = []
    async for msg in client.get_chat_history(channel_id, limit=limit, offset=offset):
        sender_name = ""
        if msg.from_user:
            sender_name = _full_name(msg.from_user)
        elif msg.sender_chat:
            sender_name = getattr(msg.sender_chat, "title", "") or ""
        media_data = await _get_message_media_data(client, msg, include_preview=False)
        messages.append({
            "id": msg.id,
            "text": msg.text or msg.caption or "",
            "date": msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "",
            "sender": sender_name,
            "views": getattr(msg, "views", None),
            "is_pinned": getattr(msg, "pinned", False),
            "has_media": bool(msg.media),
            **media_data,
        })
    messages.reverse()
    return messages


@_retry_flood
async def _get_channel_message_thumbnails(
    client: Client, channel_id: int, message_ids: list[int]
) -> dict[int, str]:
    messages = await client.get_messages(channel_id, message_ids)
    if not isinstance(messages, list):
        messages = [messages]
    semaphore = asyncio.Semaphore(3)

    async def get_preview(message):
        if not message or not getattr(message, "media", None):
            return None
        async with semaphore:
            media_data = await _get_message_media_data(
                client, message, include_preview=True
            )
        return message.id, media_data.get("media_preview")

    results = await asyncio.gather(*(get_preview(message) for message in messages))
    previews = {}
    for result in results:
        if result:
            message_id, preview = result
            if preview:
                previews[message_id] = preview
    return previews


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


async def _get_chat_photo(client: Client, chat):
    """Return a chat's small profile photo as an in-memory data URI."""
    photo = getattr(chat, "photo", None)
    if not photo or not getattr(photo, "small_file_id", None):
        return None

    try:
        image = await client.download_media(photo.small_file_id, in_memory=True)
        return _image_data_uri(image)
    except Exception as e:
        logger.warning("Could not load profile photo for chat %s: %s", getattr(chat, "id", "?"), e)
    return None


async def _get_chat_photos(client: Client, chat_ids: list[int]) -> dict[int, str]:
    requested = set(chat_ids)
    photos = {}
    me = await client.get_me()
    if me.id in requested:
        photo = await _get_chat_photo(client, me)
        if photo:
            photos[me.id] = photo

    for_dialogs = client.get_dialogs(limit=0)
    async for dialog in for_dialogs:
        chat = dialog.chat
        if chat.id not in requested or chat.id in photos:
            continue
        photo = await _get_chat_photo(client, chat)
        if photo:
            photos[chat.id] = photo
        if len(photos) == len(requested):
            break
    return photos


async def _get_message_media_data(client: Client, message, include_preview: bool = True) -> dict:
    media_type = getattr(message.media, "name", "") if message.media else ""
    media_type = media_type or (str(message.media).split(".")[-1] if message.media else "")
    media_type = media_type.upper()
    media_obj = None
    for kind in (
        "photo", "video", "animation", "sticker", "document", "audio",
        "voice", "video_note", "contact", "location", "venue", "poll",
        "dice", "game", "web_page",
    ):
        value = getattr(message, kind, None)
        if value is not None:
            if not media_type:
                media_type = kind.upper()
            media_obj = value
            break

    if media_type == "WEB_PAGE" and media_obj:
        media_obj = (
            getattr(media_obj, "photo", None)
            or getattr(media_obj, "video", None)
            or getattr(media_obj, "document", None)
        )

    thumbnails = getattr(media_obj, "thumbs", None) or []
    preview = None
    candidates = sorted(
        (thumb for thumb in thumbnails if getattr(thumb, "file_size", 0) <= 96_000),
        key=lambda thumb: getattr(thumb, "file_size", 0),
    )
    if candidates and include_preview:
        thumbnail = candidates[-1]
        try:
            image = await client.download_media(thumbnail.file_id, in_memory=True)
            preview = _image_data_uri(image, max_size=96_000)
        except Exception as e:
            logger.warning("Could not load thumbnail for message %s: %s", message.id, e)

    return {
        "media_type": media_type or None,
        "media_label": _media_label(media_type),
        "media_preview": preview,
        "media_name": (
            getattr(media_obj, "file_name", None)
            or getattr(media_obj, "emoji", None)
            or ""
        ),
        "media_mime_type": getattr(media_obj, "mime_type", None) or "",
        "media_duration": getattr(media_obj, "duration", None),
        "media_size": getattr(media_obj, "file_size", None),
    }


def _image_data_uri(image, max_size: int = 160_000):
    if not image:
        return None
    if isinstance(image, bytes):
        data = image
    else:
        data = image.getvalue() if hasattr(image, "getvalue") else image.read()
    if not data or len(data) > max_size:
        return None

    if data.startswith(b"\xff\xd8\xff"):
        mime_type = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif data.startswith((b"RIFF",)) and data[8:12] == b"WEBP":
        mime_type = "image/webp"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        mime_type = "image/gif"
    else:
        logger.warning("Ignoring Telegram image with unknown format")
        return None

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


_MEDIA_LABELS = {
    "PHOTO": "Photo",
    "VIDEO": "Video",
    "ANIMATION": "GIF",
    "STICKER": "Sticker",
    "DOCUMENT": "Document",
    "AUDIO": "Audio",
    "VOICE": "Voice message",
    "VIDEO_NOTE": "Video message",
    "CONTACT": "Contact",
    "LOCATION": "Location",
    "VENUE": "Place",
    "POLL": "Poll",
    "DICE": "Dice",
    "GAME": "Game",
    "WEB_PAGE": "Link preview",
}


def _media_label(media_type: str) -> str:
    return _MEDIA_LABELS.get(media_type, "Media")


# ─── Sync wrapper (one fresh event loop per call) ────────────────────────────

async def _cache_chat_peer(client: Client, chat_id: int, namespace: str) -> None:
    if await _restore_chat_peer(client, chat_id, namespace):
        return

    async for dialog in client.get_dialogs(limit=0):
        if dialog.chat.id == chat_id:
            await _remember_chat_peer(client, chat_id, namespace)
            return
    raise ValueError(
        f"Chat {chat_id} is not available in this Telegram account's dialogs."
    )


def run_in_session(session_string: str, coro_factory, chat_id: int | None = None):
    """
    Creates a Pyrogram client, connects, runs coro_factory(client),
    disconnects, and returns the result. Always runs in a brand-new event loop.
    """
    async def _runner():
        client = create_client(session_string)
        try:
            await client.start()
            if chat_id is not None:
                await _cache_chat_peer(
                    client, chat_id, _session_peer_namespace(session_string)
                )
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


def get_all_dialogs(session_string: str, limit: int = 0) -> list:
    namespace = _session_peer_namespace(session_string)
    return run_in_session(
        session_string,
        lambda client: _get_all_dialogs(
            client, limit, peer_cache_namespace=namespace
        ),
    )


def get_dashboard_data(session_string: str) -> tuple[dict, list]:
    async def _dashboard_data(client):
        me = await client.get_me()
        user_info = await _get_user_info(client, me)
        dialogs = await _get_all_dialogs(
            client,
            me=me,
            peer_cache_namespace=_session_peer_namespace(session_string),
        )
        return user_info, dialogs

    return run_in_session(session_string, _dashboard_data)


def get_channel_info(session_string: str, channel_id: int) -> dict:
    return run_in_session(
        session_string, lambda c: _get_channel_info(c, channel_id), chat_id=channel_id
    )


def get_channel_full(session_string: str, channel_id: int) -> dict:
    async def _all(client):
        info = await _get_channel_info(client, channel_id)
        admins = []
        members = []
        messages = []
        errors = {}
        if info["type"] in ("channel", "supergroup", "group"):
            try:
                admins = await _get_channel_admins(client, channel_id)
            except Exception as e:
                logger.warning("Error fetching admins for %s: %s", channel_id, e)
                errors["admins"] = str(e)
            try:
                members = (await _get_channel_members(client, channel_id, limit=50))["members"]
            except Exception as e:
                logger.warning("Error fetching members for %s: %s", channel_id, e)
                errors["members"] = str(e)
        try:
            messages = await _get_channel_messages(client, channel_id, limit=30)
        except Exception as e:
            logger.warning("Error fetching messages for %s: %s", channel_id, e)
            errors["messages"] = str(e)
        return {
            "info": info,
            "admins": admins,
            "members": members,
            "messages": messages,
            "photo": info.get("photo"),
            "errors": errors,
        }
    return run_in_session(session_string, _all, chat_id=channel_id)


def get_channel_preview(session_string: str, channel_id: int) -> dict:
    async def _preview(client):
        info = await _get_channel_info(client, channel_id, include_photo=False)
        return {
            "info": info,
            "admins": [],
            "members": [],
            "messages": [],
            "photo": None,
            "errors": {},
        }

    return run_in_session(session_string, _preview, chat_id=channel_id)


def get_channel_admins(session_string: str, channel_id: int) -> list:
    return run_in_session(
        session_string, lambda client: _get_channel_admins(client, channel_id),
        chat_id=channel_id,
    )


def get_channel_message_thumbnails(
    session_string: str, channel_id: int, message_ids: list[int]
) -> dict[int, str]:
    return run_in_session(
        session_string,
        lambda client: _get_channel_message_thumbnails(client, channel_id, message_ids),
        chat_id=channel_id,
    )


def get_channel_members_page(session_string: str, channel_id: int,
                              limit: int = 50, offset: int = 0) -> dict:
    return run_in_session(
        session_string,
        lambda c: _get_channel_members(c, channel_id, limit=limit, offset=offset),
        chat_id=channel_id,
    )


def get_channel_messages_page(session_string: str, channel_id: int,
                               limit: int = 30, offset: int = 0) -> list:
    return run_in_session(
        session_string,
        lambda c: _get_channel_messages(c, channel_id, limit=limit, offset=offset),
        chat_id=channel_id,
    )


def get_pinned_messages(session_string: str, channel_id: int) -> list:
    return run_in_session(
        session_string, lambda c: _get_pinned_messages(c, channel_id), chat_id=channel_id
    )


def create_invite_link(session_string: str, channel_id: int,
                        expire_date=None, member_limit=None) -> str:
    return run_in_session(
        session_string,
        lambda c: _create_invite_link(c, channel_id, expire_date, member_limit),
        chat_id=channel_id,
    )


def revoke_invite_link(session_string: str, channel_id: int, invite_link: str) -> bool:
    return run_in_session(
        session_string,
        lambda c: _revoke_invite_link(c, channel_id, invite_link),
        chat_id=channel_id,
    )


def delete_message(session_string: str, channel_id: int, message_id: int) -> bool:
    return run_in_session(
        session_string,
        lambda c: _delete_message(c, channel_id, message_id),
        chat_id=channel_id,
    )


def transfer_ownership(session_string: str, channel_id: int,
                        target_user_id: int, password: str) -> bool:
    return run_in_session(
        session_string,
        lambda c: _transfer_ownership(c, channel_id, target_user_id, password),
        chat_id=channel_id,
    )


def get_chat_photo(session_string: str, chat_id: int):
    async def _get_photo(client):
        chat = await client.get_chat(chat_id)
        return await _get_chat_photo(client, chat)

    return run_in_session(
        session_string, _get_photo, chat_id=chat_id
    )


def get_chat_photos(session_string: str, chat_ids: list[int]) -> dict[int, str]:
    return run_in_session(
        session_string, lambda client: _get_chat_photos(client, chat_ids)
    )


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
