# 🃏 BriscolaArenaBot

Premium multiplayer **Briscola** inside Telegram — messages, inline buttons and images only (no Mini App, no website).
2-player and 4-player (2 vs 2) matches, private rooms, quick match, AI practice, tournaments, profiles, leaderboards,
missions, friends and an admin panel. Python 3.11+, python-telegram-bot 21+, SQLAlchemy 2 (SQLite or PostgreSQL),
Alembic, Pillow, Docker.

## How the game works in Telegram
* Your cards arrive **privately** in your chat with the bot (as an image or text — your choice in ⚙️ Settings).
  Card buttons only work for the player who owns that hand. Server-side validation + a move counter reject
  wrong turns, foreign cards and double-taps.
* In a **group**, one live table message (image or text) is edited after every move.
* Games are saved after every move. After a crash/restart the bot reloads unfinished matches and resends hands.

## Project layout
```
main.py  config.py  alembic.ini  Dockerfile  docker-compose.yml  .env.example
game/        deck, cards, rules (configurable), scoring, state, engine (pure, no Telegram), ai
database/    models, database (engine), repository, migrations/ (Alembic)
services/    game_manager (live matches, timers, AI, recovery), matchmaking (rooms+queue),
             tournament (knockout brackets), rewards, statistics, notifications
handlers/    start menu profile game matchmaking room leaderboard tournament rewards friends admin
keyboards/   inline keyboards          ui/  images.py (Pillow) + texts.py
utils/       logger validators helpers decorators      tests/   61 tests
```

## 1. Local setup on Windows + VS Code
1. Install Python 3.11+ from python.org (tick **Add to PATH**), and VS Code with the Python extension.
2. Open the project folder in VS Code → terminal:
   ```
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```
3. Create the bot: in Telegram open **@BotFather** → `/newbot` → name `Briscola Arena`, username `BriscolaArenaBot`
   (must end in *bot*; pick another if taken and set `BOT_USERNAME`). Copy the token into `.env` as `BOT_TOKEN`.
4. Optional BotFather polish: `/setdescription`, `/setabouttext`, `/setuserpic`. For group play keep
   **Group Privacy ON** (default) — the bot only needs commands. The command menu is set automatically at startup.
5. Put your numeric Telegram ID(s) in `ADMIN_IDS` (get it from @userinfobot), comma-separated.
6. Run: `python main.py` → send `/start` to your bot.

## Profile cards (3 styles)
`/profile` shows a game-style image card with the player's real Telegram photo, name and @username exactly as in
Telegram (Latin, Hindi/Devanagari, Cyrillic, colour emoji). Players pick **Face Card / Arena / VIP Pass** in
⚙️ Settings (👁 Preview shows it instantly). Hindi needs Pillow's Raqm layout: it is included in the Docker image
(`libraqm0`); on a Linux VPS run `apt install libraqm0`; Windows/macOS Pillow wheels already bundle it.
The bot logs a warning at startup if Raqm is missing. `python make_demo_cards.py out_dir` renders demo cards.

## 2. Database
* **SQLite (default):** `DATABASE_URL=sqlite+aiosqlite:///briscola.db` — nothing to install; WAL mode is enabled.
* **PostgreSQL (production):** `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/briscola`
  (hosts that give `postgres://…` are converted automatically).
* **Migrations:** `alembic upgrade head` creates/updates the schema (the Docker image runs it on every start).
  After changing `database/models.py`: `alembic revision --autogenerate -m "what changed"`.
  The bot also creates missing tables/columns on startup, so `python main.py` works without running Alembic first
  (migration `0002` adds the profile-card style column and is safe to run on a fresh or existing database).

## 3. Docker / VPS (runs 24/7 even when your laptop is off)
```
cp .env.example .env        # fill BOT_TOKEN, ADMIN_IDS, POSTGRES_PASSWORD
docker compose up -d --build
docker compose logs -f bot
```
Any small VPS (1 vCPU / 1 GB) is enough for hundreds of concurrent matches. Update: `git pull && docker compose up -d --build`.
Without Docker on a Linux VPS, use a systemd unit:
```
[Service]
WorkingDirectory=/opt/BriscolaArenaBot
ExecStart=/opt/BriscolaArenaBot/.venv/bin/python main.py
Restart=always
```
**Free hosting:** the bot uses long polling and must stay awake. Platforms that put free apps to sleep will make it
unresponsive. Oracle Cloud "Always Free" VMs or a small paid plan on Railway / Render / Fly.io / Hetzner work well;
free tiers change often, so check current terms. Use PostgreSQL (or a persistent volume for SQLite) so data survives redeploys.
Only run **one** instance per token (two instances cause a `Conflict` error).

## 4. Restart & recovery
* Crash, deploy or reboot → `restart: unless-stopped` / systemd restarts the bot → unfinished matches are reloaded
  from the database, players get a fresh hand message ("♻️ The bot restarted"), turn timers restart.
* Lost your hand message? `/hand`. Old buttons are rejected safely and refresh your hand.
* Rooms and quick-match searches are short-lived and are *not* persisted (players just create/search again).
* Logs: `logs/bot.log` (also `/logs` for admins). Back up the database regularly (`pg_dump` / copy the `.db` file).

## 5. Admin commands
`/admin /stats /playerinfo <id|@user> /ban <id> [reason] /unban /announcement <text|off> /maintenance on|off
/broadcast <text> /create_tournament Name | capacity | start_min | deadline_min | description
/end_tournament <id> /remove_player <tournament_id> <user> /logs`

## 6. Settings (.env)
`TURN_TIMEOUT` (seconds, default 45) • `TIMEOUT_POLICY` = `auto_play` | `forfeit` • `AFK_STRIKES_LIMIT` (default 2) •
`TRUMP_MODE` = `bottom_card` (traditional) | `random_suit` • `ROOM_TTL_MINUTES` • `DEFAULT_IMAGES` = 1|0

## 7. Tests
`python -m unittest discover -s tests -t . -v` (no extra packages needed; `pytest` also works).
`python benchmark_ai.py` compares AI levels.

## Rules implemented
40 cards (no 8/9/10) • power A>3>K>Q>J>7>6>5>4>2 • points A11 3→10 K4 Q3 J2 (120 total) • 3 cards each •
bottom card shows the Briscola, last drawer takes it • trump beats all, otherwise highest of led suit wins, no obligation to follow suit •
winner draws first and leads • more than 60 wins, 60-60 draw • 4 players: seats 1+3 vs 2+4, points are pooled.
