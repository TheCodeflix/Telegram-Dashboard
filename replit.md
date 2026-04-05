# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Telegram Web Dashboard (Python)

A standalone Python project at `telegram-web-dashboard/`.

### Stack
- **Framework**: Flask 2.3.0
- **Telegram**: Pyrogram 2.0.106 + TgCrypto
- **Database**: MongoDB via pymongo 4.5.0
- **Templates**: Jinja2 with Bootstrap 5 + Font Awesome

### Project Structure
```
telegram-web-dashboard/
├── app.py                    # Flask app (routes: /, /health)
├── bot.py                    # Telegram bot (/start, /help handlers)
├── requirements.txt
├── Dockerfile
├── .env                      # Placeholder values (real values in Replit Secrets)
├── database/
│   ├── mongodb.py            # connect_to_mongodb, get_collection, close_connection
│   └── models.py             # Session and UserSession CRUD functions
├── plugins/
│   └── session_manager.py    # generate_unique_link, validate_session_string, format_session_for_db
├── templates/
│   ├── base.html             # Bootstrap 5 + Font Awesome layout
│   └── index.html
└── static/
    ├── style.css
    └── script.js
```

### Required Secrets
- `MONGODB_URI` — MongoDB Atlas connection string
- `BOT_TOKEN` — Telegram bot token
- `API_ID` — Telegram API ID
- `API_HASH` — Telegram API Hash

### Running
- Flask: `cd telegram-web-dashboard && python app.py` (port 8000)
- Bot: `cd telegram-web-dashboard && python bot.py`
- Workflow: "Telegram Dashboard - Flask" (configured in Replit)
