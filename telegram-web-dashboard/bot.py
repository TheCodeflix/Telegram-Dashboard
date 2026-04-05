import os
import asyncio
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

bot = Client(
    name="telegram_dashboard_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    logger.info("Received /start from user_id=%s username=%s", user.id, user.username)
    await message.reply_text(
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the <b>Telegram Web Dashboard</b>.\n\n"
        "I help you manage your Telegram sessions securely.\n\n"
        "Use /help to see available commands.",
        parse_mode="html",
    )


@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    await message.reply_text(
        "<b>Available Commands</b>\n\n"
        "/start — Start the bot\n"
        "/help  — Show this help message\n",
        parse_mode="html",
    )


async def main():
    logger.info("Starting Telegram bot...")
    async with bot:
        logger.info("Bot is running. Press Ctrl+C to stop.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
