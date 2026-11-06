from telegram.ext import CallbackQueryHandler, CommandHandler

from keyboards.misc_keyboard import LB_TABS, leaderboard_kb
from ui import texts
from utils.decorators import ack, deps, guard, respond

PER_PAGE = 10
KINDS = {k for k, _ in LB_TABS}


async def show(update, context, kind: str, page: int):
    c, uid = deps(context), update.effective_user.id
    ids = None
    if kind == "friends":
        ids = [f["id"] for f in await c.repo.friends(uid)] + [uid]
    rows, total = await c.repo.leaderboard(kind, PER_PAGE, page * PER_PAGE, ids)
    pages = max(1, -(-total // PER_PAGE))
    await respond(update, context, texts.leaderboard_text(kind, rows, page, total, PER_PAGE, uid),
                  leaderboard_kb(kind, page, pages))


@guard()
async def leaderboard_cmd(update, context):
    await show(update, context, "global", 0)


@guard()
async def leaderboard_cb(update, context):
    await ack(update)
    _, kind, page = update.callback_query.data.split(":")
    if kind in KINDS:
        await show(update, context, kind, max(0, int(page)))


def register(app) -> None:
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CallbackQueryHandler(leaderboard_cb, pattern=r"^lb:[a-z]+:\d+$"))
