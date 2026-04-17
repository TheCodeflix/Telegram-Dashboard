# Telegram Web Dashboard

A self-hosted web dashboard for your Telegram account. Submit your Pyrogram session string to the bot, receive a private dashboard link, and view your channels, groups, contacts, and messages — right from a browser.

---

## Features

- **Telegram Bot** — Accepts Pyrogram session strings, verifies them (including 2FA), and generates a unique dashboard link
- **Web Dashboard** — View all dialogs (channels, groups, contacts, bots) with live stats
- **Channel View** — Member list, message history, admin list, invite link management, message deletion
- **AJAX Pagination** — Load members and messages on demand, page by page
- **Session Management** — Logout, regenerate link, check status — all via the bot
- **Security** — Rate limiting (100 req/min), security headers, no plain-text secret storage
- **Caching** — 5-minute in-memory cache for Telegram API responses
- **Docker-ready** — Single `docker run` starts both the bot and the Flask web server

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/yourname/telegram-web-dashboard.git
cd telegram-web-dashboard
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set environment variables

Copy `.env` and fill in real values:

```bash
cp .env .env.local
```

Required variables (see [Environment Variables](#environment-variables) below).

### 4. Run locally

In two separate terminals:

```bash
# Terminal 1 — Flask web server
python app.py

# Terminal 2 — Telegram bot
python bot.py
```

Or with Gunicorn:

```bash
python bot.py &
gunicorn --config gunicorn.conf.py app:app
```

---

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `MONGODB_URI` | MongoDB Atlas (or local) connection string | `mongodb+srv://user:pass@cluster/db` |
| `DATABASE_NAME` | MongoDB database name | `telegram_dashboard` |
| `BOT_TOKEN` | Telegram Bot token from @BotFather | `123456:ABC-...` |
| `API_ID` | Telegram API ID from my.telegram.org | `12345678` |
| `API_HASH` | Telegram API hash from my.telegram.org | `abc123def456...` |
| `FLASK_SECRET_KEY` | Flask session secret (random string) | `some-random-secret` |
| `PORT` | Web server port | `8000` |
| `DOMAIN` | Public URL of your deployment | `https://your-app.koyeb.app` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `SESSION_MAX_AGE_HOURS` | Auto-expire sessions after N hours (0 = never) | `0` |

---

## Docker Deployment

### Build and run locally

```bash
docker build -t tg-dashboard .
docker run -p 8000:8000 \
  -e MONGODB_URI="..." \
  -e BOT_TOKEN="..." \
  -e API_ID="..." \
  -e API_HASH="..." \
  -e FLASK_SECRET_KEY="..." \
  -e DOMAIN="http://localhost:8000" \
  tg-dashboard
```

---

## Koyeb Deployment

1. Push your code to a GitHub repository
2. Go to [koyeb.com](https://koyeb.com) and create a new app
3. Connect your GitHub repository
4. Set the **Dockerfile** build method
5. Add all environment variables in the Koyeb dashboard:
   - `MONGODB_URI`, `BOT_TOKEN`, `API_ID`, `API_HASH`, `FLASK_SECRET_KEY`, `DOMAIN`
6. Set `DOMAIN` to your Koyeb app URL (e.g. `https://your-app.koyeb.app`)
7. Deploy and monitor build logs
8. Once live, send `/start` to your bot to test the full flow

---

## Usage

1. Open Telegram and find your bot
2. Send `/start`
3. Paste your **Pyrogram session string**  
   *(Generate one with `python -c "from pyrogram import Client; Client('test').run()"` or use a session string generator)*
4. If 2FA is enabled, enter your password when prompted
5. The bot sends you a private dashboard link
6. Open the link in a browser to explore your Telegram account

### Bot Commands

| Command | Description |
|---|---|
| `/start` | Add or replace your session |
| `/status` | View current session info and dashboard link |
| `/regen` | Generate a new dashboard link (invalidates the old one) |
| `/logout` | Remove your session from the dashboard |
| `/cancel` | Cancel the current operation |
| `/help` | Show all commands |

---

## Project Structure

```
telegram-web-dashboard/
├── app.py                  # Flask web application
├── bot.py                  # Telegram bot (Pyrogram)
├── gunicorn.conf.py        # Gunicorn configuration
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .env                    # Environment variables template
├── database/
│   ├── mongodb.py          # MongoDB connection
│   └── models.py           # DB operations (sessions, user_sessions)
├── plugins/
│   ├── session_manager.py  # Unique link generation + validation
│   ├── telegram_client.py  # All Pyrogram operations (async + sync wrappers)
│   └── channel_utils.py    # Dialog formatting helpers
├── templates/
│   ├── base.html           # Base layout (navbar, toasts, footer)
│   ├── index.html          # Landing page
│   ├── dashboard.html      # Main dashboard
│   ├── channel_view.html   # Channel details + AJAX tabs
│   ├── profile.html        # User profile
│   ├── error.html          # General error page
│   ├── 404.html            # Not found page
│   └── 500.html            # Server error page
├── static/
│   ├── style.css           # Responsive styles
│   └── script.js           # AJAX functions, toasts, pagination
└── logs/
    ├── app.log
    └── bot.log
```

---

## Troubleshooting

**Bot doesn't respond**
- Check `BOT_TOKEN`, `API_ID`, `API_HASH` are set correctly
- Check `logs/bot.log` for errors

**Dashboard shows 503 / "session expired"**
- Your Pyrogram session string may have been revoked by Telegram
- Use `/logout` in the bot then `/start` to submit a new session

**MongoDB connection error**
- Verify `MONGODB_URI` is correct and the IP is whitelisted in Atlas

**FloodWait errors**
- Telegram is rate-limiting your account. The bot and dashboard will automatically wait and retry

**Cannot access dashboard after deployment**
- Ensure `DOMAIN` is set to the correct public URL
- Check that port 8000 is exposed and not blocked

---

## Security Notes

- Dashboard links are UUID-based and private — do not share them
- Session strings grant full access to your Telegram account — handle with care
- Logs are written to `logs/` — exclude them from version control (`.dockerignore` already does this)
