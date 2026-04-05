import os
import asyncio
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    SessionPasswordNeeded,
    AuthKeyUnregistered,
    UserDeactivated,
    AuthKeyInvalid,
    FloodWait,
    BadRequest,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DOMAIN = os.environ.get("DOMAIN", "https://your-app.koyeb.app")

# ─── Conversation States ─────────────────────────────────────────────────────

IDLE = 0
WAITING_FOR_SESSION = 1
WAITING_FOR_2FA = 2
WAITING_FOR_REPLACE_CONFIRM = 3

# ─── In-memory State Storage ─────────────────────────────────────────────────
# user_id (int) -> state (int)
user_states: dict[int, int] = {}

# user_id (int) -> {session_string, user_info, temp_client}
user_temp_data: dict[int, dict] = {}

# ─── Bot Client ──────────────────────────────────────────────────────────────

bot = Client(
    name="telegram_dashboard_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_state(user_id: int) -> int:
    return user_states.get(user_id, IDLE)


def set_state(user_id: int, state: int) -> None:
    user_states[user_id] = state


def clear_user(user_id: int) -> None:
    user_states.pop(user_id, None)
    data = user_temp_data.pop(user_id, {})
    temp_client = data.get("temp_client")
    if temp_client and temp_client.is_connected:
        asyncio.create_task(temp_client.stop())


async def safe_disconnect(client: Client) -> None:
    try:
        if client.is_connected:
            await client.stop()
    except Exception:
        pass


# ─── /start ──────────────────────────────────────────────────────────────────

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    logger.info("/start from user_id=%s username=%s", user.id, user.username)
    clear_user(user.id)
    set_state(user.id, WAITING_FOR_SESSION)

    await message.reply_text(
        f"👋 <b>Hello, {user.first_name}!</b>\n\n"
        "Welcome to the <b>Telegram Web Dashboard</b>.\n\n"
        "⚠️ <b>Security Warning:</b>\n"
        "Your Pyrogram session string gives full access to your Telegram account. "
        "Only use this bot if you trust it and understand the risks. "
        "Never share your session string with anyone else.\n\n"
        "Please send your <b>Pyrogram session string</b> to continue.\n\n"
        "Use /cancel to stop at any time.",
        parse_mode="html",
    )


# ─── /cancel ─────────────────────────────────────────────────────────────────

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client: Client, message: Message):
    user = message.from_user
    logger.info("/cancel from user_id=%s", user.id)
    clear_user(user.id)
    await message.reply_text(
        "❌ Operation cancelled.\n\nUse /start to begin again or /help to see all commands.",
        parse_mode="html",
    )


# ─── /logout ─────────────────────────────────────────────────────────────────

@bot.on_message(filters.command("logout") & filters.private)
async def logout_handler(client: Client, message: Message):
    from database import models
    user_id = message.from_user.id
    logger.info("/logout from user_id=%s", user_id)

    if models.user_has_active_session(user_id):
        models.delete_session_by_user_id(user_id)
        models.delete_user_session(user_id)
        await message.reply_text(
            "✅ Logged out successfully. Your dashboard link has been invalidated.",
            parse_mode="html",
        )
    else:
        await message.reply_text(
            "❌ You don't have any active session.",
            parse_mode="html",
        )


# ─── /regen ──────────────────────────────────────────────────────────────────

@bot.on_message(filters.command("regen") & filters.private)
async def regen_handler(client: Client, message: Message):
    from database import models
    from plugins.session_manager import generate_unique_link
    user_id = message.from_user.id
    logger.info("/regen from user_id=%s", user_id)

    if not models.user_has_active_session(user_id):
        await message.reply_text(
            "❌ You don't have an active session. Use /start to create one.",
            parse_mode="html",
        )
        return

    existing = models.get_session_by_user_id(user_id)
    if not existing:
        await message.reply_text("❌ Session data not found. Use /start to create one.")
        return

    new_link = generate_unique_link()
    models.delete_session_by_user_id(user_id)
    models.create_session(
        unique_id=new_link,
        session_string=existing["session_string"],
        user_id=existing["user_id"],
        user_name=existing["user_name"],
        user_username=existing["user_username"],
    )
    models.create_user_session(user_id, new_link)

    dashboard_url = f"{DOMAIN}/dashboard/{new_link}"
    logger.info("Regenerated link for user_id=%s new_link=%s", user_id, new_link)

    await message.reply_text(
        "🔄 <b>New dashboard link generated!</b>\n\n"
        "Your old link has been invalidated.\n\n"
        f"🔗 <b>New Dashboard Link:</b>\n<code>{dashboard_url}</code>",
        parse_mode="html",
    )


# ─── /status ─────────────────────────────────────────────────────────────────

@bot.on_message(filters.command("status") & filters.private)
async def status_handler(client: Client, message: Message):
    from database import models
    user_id = message.from_user.id
    logger.info("/status from user_id=%s", user_id)

    session = models.get_session_by_user_id(user_id)
    if not session:
        await message.reply_text(
            "❌ No active session found.\n\nUse /start to create one.",
            parse_mode="html",
        )
        return

    created = session.get("created_at")
    last_acc = session.get("last_accessed")
    created_str = created.strftime("%Y-%m-%d %H:%M UTC") if created else "Unknown"
    last_str = last_acc.strftime("%Y-%m-%d %H:%M UTC") if last_acc else "Unknown"
    unique_id = session.get("unique_id", "")
    dashboard_url = f"{DOMAIN}/dashboard/{unique_id}"

    await message.reply_text(
        "📊 <b>Session Status</b>\n\n"
        f"👤 <b>Name:</b> {session.get('user_name', 'N/A')}\n"
        f"🔖 <b>Username:</b> @{session.get('user_username', 'N/A')}\n"
        f"🕐 <b>Created:</b> {created_str}\n"
        f"🕑 <b>Last Accessed:</b> {last_str}\n\n"
        f"🔗 <b>Dashboard Link:</b>\n<code>{dashboard_url}</code>",
        parse_mode="html",
    )


# ─── /help ───────────────────────────────────────────────────────────────────

@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    await message.reply_text(
        "<b>Available Commands</b>\n\n"
        "/start  — Add / replace your Telegram session\n"
        "/status — View your current session info\n"
        "/regen  — Generate a new dashboard link\n"
        "/logout — Remove your session from the dashboard\n"
        "/cancel — Cancel the current operation\n"
        "/help   — Show this message",
        parse_mode="html",
    )


# ─── Central Text Handler (State Machine) ────────────────────────────────────

@bot.on_message(filters.text & filters.private & ~filters.command(
    ["start", "cancel", "logout", "regen", "status", "help"]
))
async def text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == WAITING_FOR_SESSION:
        await handle_session_input(client, message)
    elif state == WAITING_FOR_2FA:
        await handle_2fa_input(client, message)
    elif state == WAITING_FOR_REPLACE_CONFIRM:
        await handle_replace_confirm(client, message)
    else:
        await message.reply_text(
            "Send /start to add your session, or /help for all commands.",
            parse_mode="html",
        )


# ─── Session String Handler ───────────────────────────────────────────────────

async def handle_session_input(client: Client, message: Message):
    from plugins.session_manager import validate_session_string
    user_id = message.from_user.id
    session_string = message.text.strip()

    if not validate_session_string(session_string):
        await message.reply_text(
            "❌ <b>Invalid session string.</b>\n\n"
            "A Pyrogram session string should be between 20 and 500 characters long. "
            "Please send a valid session string, or use /cancel to stop.",
            parse_mode="html",
        )
        return

    wait_msg = await message.reply_text("⏳ Verifying session string, please wait...")

    temp_client = Client(
        name=f"verify_{user_id}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
    )

    try:
        await temp_client.start()
        me = await temp_client.get_me()

        user_info = {
            "user_id": me.id,
            "user_name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_username": me.username or "",
        }

        user_temp_data[user_id] = {
            "session_string": session_string,
            "user_info": user_info,
            "temp_client": temp_client,
        }

        await safe_disconnect(temp_client)
        await wait_msg.delete()
        await handle_successful_connection(client, message, user_id)

    except SessionPasswordNeeded:
        user_temp_data[user_id] = {
            "session_string": session_string,
            "temp_client": temp_client,
        }
        set_state(user_id, WAITING_FOR_2FA)
        await wait_msg.delete()
        await message.reply_text(
            "🔐 <b>Two-Factor Authentication required.</b>\n\n"
            "Please send your <b>2FA password</b> to continue, or /cancel to stop.",
            parse_mode="html",
        )

    except (AuthKeyUnregistered, AuthKeyInvalid):
        await safe_disconnect(temp_client)
        await wait_msg.delete()
        await message.reply_text(
            "❌ <b>Session string is invalid or has been revoked.</b>\n\n"
            "Please generate a new Pyrogram session string and try again, "
            "or use /cancel to stop.",
            parse_mode="html",
        )

    except UserDeactivated:
        await safe_disconnect(temp_client)
        await wait_msg.delete()
        await message.reply_text(
            "❌ <b>The Telegram account linked to this session has been deactivated.</b>\n\n"
            "Use /cancel to stop.",
            parse_mode="html",
        )

    except FloodWait as e:
        await safe_disconnect(temp_client)
        await wait_msg.delete()
        await message.reply_text(
            f"⏳ <b>Too many requests.</b> Please wait {e.value} seconds before trying again.",
            parse_mode="html",
        )

    except Exception as e:
        logger.error("Session verification error for user_id=%s: %s", user_id, str(e))
        await safe_disconnect(temp_client)
        await wait_msg.delete()
        await message.reply_text(
            "❌ <b>Failed to verify session string.</b>\n\n"
            f"Error: <code>{str(e)[:200]}</code>\n\n"
            "Please check your session string and try again, or use /cancel.",
            parse_mode="html",
        )


# ─── 2FA Handler ─────────────────────────────────────────────────────────────

async def handle_2fa_input(client: Client, message: Message):
    user_id = message.from_user.id
    password = message.text.strip()
    data = user_temp_data.get(user_id, {})
    session_string = data.get("session_string")
    temp_client = data.get("temp_client")

    if not session_string:
        clear_user(user_id)
        await message.reply_text(
            "❌ Session data lost. Please use /start to begin again.",
            parse_mode="html",
        )
        return

    wait_msg = await message.reply_text("⏳ Verifying 2FA password, please wait...")

    try:
        if temp_client is None or not temp_client.is_connected:
            temp_client = Client(
                name=f"verify_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True,
            )
            await temp_client.start()

        await temp_client.check_password(password)
        me = await temp_client.get_me()

        user_info = {
            "user_id": me.id,
            "user_name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_username": me.username or "",
        }

        user_temp_data[user_id]["user_info"] = user_info
        user_temp_data[user_id]["temp_client"] = temp_client

        await safe_disconnect(temp_client)
        await wait_msg.delete()
        await handle_successful_connection(client, message, user_id)

    except BadRequest:
        await wait_msg.delete()
        await message.reply_text(
            "❌ <b>Incorrect 2FA password.</b>\n\n"
            "Please try again, or use /cancel to stop.",
            parse_mode="html",
        )

    except Exception as e:
        logger.error("2FA error for user_id=%s: %s", user_id, str(e))
        if temp_client:
            await safe_disconnect(temp_client)
        await wait_msg.delete()
        await message.reply_text(
            "❌ <b>2FA verification failed.</b>\n\n"
            f"Error: <code>{str(e)[:200]}</code>\n\n"
            "Use /cancel to stop or try again.",
            parse_mode="html",
        )


# ─── Replace Confirm Handler ─────────────────────────────────────────────────

async def handle_replace_confirm(client: Client, message: Message):
    from database import models
    user_id = message.from_user.id
    response = message.text.strip().lower()

    if response in ("yes", "y"):
        models.delete_session_by_user_id(user_id)
        models.delete_user_session(user_id)
        logger.info("User %s confirmed session replacement", user_id)
        await _finalize_session(client, message, user_id)
    elif response in ("no", "n"):
        clear_user(user_id)
        await message.reply_text(
            "✅ Kept your existing session.\n\n"
            "Use /status to view it or /regen to refresh your link.",
            parse_mode="html",
        )
    else:
        await message.reply_text(
            "Please reply with <b>yes</b> or <b>no</b>.",
            parse_mode="html",
        )


# ─── Successful Connection Handler ────────────────────────────────────────────

async def handle_successful_connection(client: Client, message: Message, user_id: int):
    from database import models

    if models.user_has_active_session(user_id):
        set_state(user_id, WAITING_FOR_REPLACE_CONFIRM)
        existing = models.get_session_by_user_id(user_id)
        existing_link = f"{DOMAIN}/dashboard/{existing['unique_id']}" if existing else "N/A"
        await message.reply_text(
            "⚠️ <b>You already have an active session.</b>\n\n"
            f"Existing dashboard: <code>{existing_link}</code>\n\n"
            "Do you want to replace it with the new session?\n"
            "Reply with <b>yes</b> to replace or <b>no</b> to keep the existing one.",
            parse_mode="html",
        )
    else:
        await _finalize_session(client, message, user_id)


async def _finalize_session(client: Client, message: Message, user_id: int):
    from database import models
    from plugins.session_manager import generate_unique_link
    data = user_temp_data.get(user_id, {})
    session_string = data.get("session_string", "")
    user_info = data.get("user_info", {})

    unique_link = generate_unique_link()
    models.create_session(
        unique_id=unique_link,
        session_string=session_string,
        user_id=user_info.get("user_id", user_id),
        user_name=user_info.get("user_name", ""),
        user_username=user_info.get("user_username", ""),
    )
    models.create_user_session(user_id, unique_link)

    dashboard_url = f"{DOMAIN}/dashboard/{unique_link}"
    logger.info("Session saved for user_id=%s unique_link=%s", user_id, unique_link)

    clear_user(user_id)

    await message.reply_text(
        "✅ <b>Session saved successfully!</b>\n\n"
        f"👤 <b>Account:</b> {user_info.get('user_name', 'Unknown')}\n"
        f"🔖 <b>Username:</b> @{user_info.get('user_username', 'N/A')}\n\n"
        "🔗 <b>Your Dashboard Link:</b>\n"
        f"<code>{dashboard_url}</code>\n\n"
        "Keep this link private — it provides access to your Telegram account data.\n\n"
        "Use /status to view session info, /regen to refresh the link, "
        "or /logout to remove it.",
        parse_mode="html",
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    logger.info("Starting Telegram bot...")
    async with bot:
        me = await bot.get_me()
        logger.info("Bot running as @%s (id=%s)", me.username, me.id)
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
