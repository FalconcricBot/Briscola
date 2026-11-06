"""BriscolaArenaBot entry point."""
from __future__ import annotations

import logging
import sys
import time

from telegram import BotCommand, Update
from telegram.error import Conflict, NetworkError
from telegram.ext import Application, ContextTypes

from config import settings
from database.database import init_db, make_engine, make_session_factory
from database.repository import Repo
from handlers import admin, friends, game, leaderboard, matchmaking, menu, profile, rewards as rewards_h, room, start, tournament
from services.game_manager import GameManager
from services.matchmaking import Lobby
from services.notifications import Notifier
from services.rewards import RewardsService
from services.tournament import TournamentService
from utils.logger import setup_logging

log = logging.getLogger("briscola")

COMMANDS = [
    ("start", "Start the bot"), ("menu", "Main menu"), ("help", "Help guide"), ("profile", "Player profile"),
    ("play", "Play game"), ("quickmatch", "Find a match"), ("createroom", "Create private room"),
    ("joinroom", "Join room"), ("leave", "Leave room / match"), ("hand", "View private cards"),
    ("score", "Current score"), ("leaderboard", "Rankings"), ("history", "Match history"),
    ("missions", "Daily missions"), ("tournaments", "Tournament list"), ("invite", "Invite friends"),
    ("settings", "Settings"), ("rules", "Briscola rules"), ("cancel", "Cancel matchmaking / room"),
]


class Container:
    """Shared services, reachable from every handler via context.application.bot_data['c']."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.maintenance = False
        self.announcement = ""
        self.search_msgs: dict[int, tuple[int, int]] = {}


async def housekeeping(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every 30 s: abandoned rooms, stale searches, stalled AI turns, tournament scheduling."""
    c: Container = context.application.bot_data["c"]
    try:
        for r in c.lobby.expire_rooms(settings.room_ttl_minutes * 60):
            await room.refresh_card(context.bot, r, f"⌛ Room <code>{r.code}</code> expired (inactive).", kb=None)
        for uid in c.lobby.expire_queue(10 * 60):
            await c.notifier.dm(uid, "⌛ No match found. Try again or play vs AI.")
        await c.games.tick()
        await c.tournaments.tick()
    except Exception:
        log.exception("housekeeping failed")


async def post_init(app: Application) -> None:
    from PIL import features
    if not features.check("raqm"):
        log.warning("Pillow has no Raqm: Hindi/Devanagari names on profile cards will not shape correctly. "
                    "Install libraqm (Linux: apt install libraqm0) or use the Docker image.")
    engine = make_engine()
    await init_db(engine)
    app.bot_data["engine"] = engine
    repo = Repo(make_session_factory(engine))
    lobby, notifier = Lobby(), Notifier(app.bot)
    rewards = RewardsService(repo)
    games = GameManager(app, repo, lobby, rewards, notifier)
    tours = TournamentService(repo, games, lobby, app.bot)
    games.tournaments = tours
    c = Container(repo=repo, lobby=lobby, games=games, rewards=rewards, notifier=notifier, tournaments=tours)
    c.maintenance = (await repo.get_setting("maintenance", "0")) == "1"
    c.announcement = await repo.get_setting("announcement", "")
    app.bot_data["c"] = c
    restored = await games.restore()
    log.info("Restored %d unfinished match(es)", restored)
    app.job_queue.run_repeating(housekeeping, interval=30, first=15, name="housekeeping")
    await app.bot.set_my_commands([BotCommand(n, d) for n, d in COMMANDS])
    me = await app.bot.get_me()
    log.info("Online as @%s", me.username)


async def post_shutdown(app: Application) -> None:
    c = app.bot_data.get("c")
    if c:
        await c.games.stop_all()
    engine = app.bot_data.get("engine")
    if engine:
        await engine.dispose()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        log.error("Another bot instance is polling with this token. Stop the other one.")
        return
    if isinstance(err, NetworkError):
        log.warning("Network problem: %s", err)           # PTB retries by itself
        return
    log.error("Unhandled error", exc_info=err)
    if isinstance(update, Update) and update.effective_user:
        try:
            if update.callback_query:
                await update.callback_query.answer("⚠️ Something went wrong. Try again.", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text("⚠️ Something went wrong. Try again.")
        except Exception:
            pass


def main() -> None:
    setup_logging(settings.log_level)
    if not settings.bot_token:
        sys.exit("BOT_TOKEN is missing. Copy .env.example to .env and fill it in.")
    app = (Application.builder().token(settings.bot_token).concurrent_updates(True)
           .post_init(post_init).post_shutdown(post_shutdown).build())
    for module in (start, menu, room, matchmaking, game, profile, leaderboard, rewards_h, friends, tournament, admin):
        module.register(app)
    app.add_error_handler(on_error)
    log.info("Starting polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
