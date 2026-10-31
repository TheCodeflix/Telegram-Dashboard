# Telegram Web Dashboard

A self-hosted web dashboard for your Telegram account. Submit your Pyrogram session string to the bot, receive a private dashboard link, and view your channels, groups, contacts, and messages — right from a browser.


## Features

- Browse every Telegram dialog (channels, groups, bots, and contacts) using its Telegram chat ID.
- Open chat history, channel/group details, administrators, and members from the dashboard.
- Load older messages from Telegram history on demand.
- Display chat avatars and in-memory media thumbnails with captions and media types; full media files are not saved.
- Load chat details first, then fetch message history, admin/member lists, and visible media previews on demand. Dashboard data is cached in memory for 10 minutes.
- Copy Telegram message links or delete messages from each message's action menu.


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

### 3. Configure the application

Create your private config file from the template:

```bash
cp config.example.py config.py
```

Set your Telegram API credentials, bot token, MongoDB URI, and Flask secret in `config.py`. Keep this file private; it is excluded from Git.

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


## Configuration

| Setting | Description |
|---|---|---|
| `MONGODB_URI` | MongoDB Atlas (or local) connection string |
| `DATABASE_NAME` | MongoDB database name |
| `BOT_TOKEN` | Telegram Bot token from @BotFather |
| `BOT_OWNER` | Telegram user ID allowed to manage the bot |
| `API_ID` | Telegram API ID from my.telegram.org |
| `API_HASH` | Telegram API hash from my.telegram.org |
| `FLASK_SECRET_KEY` | Flask session secret |
| `SESSION_SECRET` | Fallback Flask session secret |
| `FLASK_ENV` | Flask runtime mode |
| `PORT` | Web server port |
| `DOMAIN` | Public URL of your deployment |
| `LOG_LEVEL` | Logging level |
| `SESSION_MAX_AGE_HOURS` | Auto-expire sessions after N hours (0 = never) |


## Docker Deployment

### Build and run locally

```bash
docker build -t tg-dashboard .
docker run -p 8080:8080 \
  -e MONGODB_URI="..." \
  -e BOT_TOKEN="..." \
  -e API_ID="..." \
  -e API_HASH="..." \
  -e FLASK_SECRET_KEY="..." \
  -e DOMAIN="http://localhost:8000" \
  tg-dashboard
```


## Koyeb Deployment

1. Push your code to a GitHub repository
2. Go to [koyeb.com](https://koyeb.com) and create a new app
3. Connect your GitHub repository
4. Set the **Dockerfile** build method
5. Provide a private `config.py` to the deployment build with the required settings.
6. Set `DOMAIN` in `config.py` to your Koyeb app URL (e.g. `https://your-app.koyeb.app`)
7. Deploy and monitor build logs
8. Once live, send `/start` to your bot to test the full flow


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


## Project Structure

```
telegram-web-dashboard/
├── app.py                  # Flask web application
├── bot.py                  # Telegram bot (Pyrogram)
├── gunicorn.conf.py        # Gunicorn configuration
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── config.example.py       # Configuration template
├── config.py               # Private local configuration (not tracked by Git)
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


## Troubleshooting

**Bot doesn't respond**

**Dashboard shows 503 / "session expired"**

**MongoDB connection error**

**FloodWait errors**

**Cannot access dashboard after deployment**


## Security Notes
