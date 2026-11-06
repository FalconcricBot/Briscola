from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from keyboards.profile_keyboard import history_kb, profile_kb, settings_kb
from services.statistics import level_for, rank_for
from ui import images, texts
from utils.decorators import ack, deps, guard, respond

log = logging.getLogger(__name__)
PER_PAGE = 6


async def _avatar(context, uid: int) -> bytes | None:
    try:
        photos = await context.bot.get_user_profile_photos(uid, limit=1)
        if photos.total_count:
            f = await photos.photos[0][-1].get_file()
            return bytes(await f.download_as_bytearray())
    except Exception as e:          # privacy settings / network: just fall back to initials
        log.debug("avatar unavailable for %s: %s", uid, e)
    return None


async def send_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, *, fresh: bool = False,
                       force_image: bool = False) -> None:
    """Profile card in the player's chosen template. fresh=True sends a new message instead of editing."""
    import asyncio
    from ui import profile_cards
    c, uid = deps(context), update.effective_user.id
    p = await c.repo.get_player(uid)
    ach = await c.repo.achievements(uid)
    text = texts.profile_text(p, ach)
    photo = None
    if p["hand_images"] or force_image:
        emoji, rank, floor, nxt = rank_for(p["xp"])
        stats = dict(matches=p["matches"], wins=p["wins"], losses=p["losses"], draws=p["draws"],
                     win_pct=(p["wins"] * 100 / p["matches"]) if p["matches"] else 0, streak=p["win_streak"],
                     highest=p["highest_score"], points=p["total_points"])
        av = await _avatar(context, uid)
        # name/username come straight from Telegram (stored on every interaction) - shown exactly as-is
        buf = await asyncio.to_thread(profile_cards.render_profile_card, p["profile_template"], name=p["display_name"],
                                      username=p["username"], player_no=p["player_no"], rank_name=rank,
                                      level=level_for(p["xp"]), xp=p["xp"], xp_floor=floor, xp_next=nxt,
                                      stats=stats, avatar=av)
        photo = buf.getvalue()
        text = (f"{emoji} <b>{texts.esc(p['display_name'])}</b> • 🆔 <code>BA{p['player_no']}</code>\n"
                f"📅 Joined {p['created_at']:%d %b %Y} • 💰 {p['coins']:,} • 🏟 {p['tournament_wins']} titles\n🏅 "
                + (" ".join(texts.ACHIEVEMENTS[a][0] for a in ach if a in texts.ACHIEVEMENTS) or "—"))
    if fresh:
        chat = update.effective_chat.id
        if photo:
            await context.bot.send_photo(chat, photo, caption=text, parse_mode="HTML", reply_markup=profile_kb())
        else:
            await context.bot.send_message(chat, text, parse_mode="HTML", reply_markup=profile_kb())
        return
    await respond(update, context, text, profile_kb(), photo)


@guard()
async def profile_cmd(update, context):
    await send_profile(update, context)


async def _history(update, context, page: int):
    c, uid = deps(context), update.effective_user.id
    rows, total = await c.repo.user_history(uid, PER_PAGE, page * PER_PAGE)
    pages = max(1, -(-total // PER_PAGE))
    await respond(update, context, texts.history_text(rows, page, total, PER_PAGE), history_kb(page, pages))


@guard()
async def history_cmd(update, context):
    await _history(update, context, 0)


@guard()
async def history_cb(update, context):
    await ack(update)
    await _history(update, context, int(update.callback_query.data.split(":")[2]))


async def _settings(update, context):
    p = await deps(context).repo.get_player(update.effective_user.id)
    await respond(update, context, "⚙️ <b>SETTINGS</b>\n"
                                   "🎴 <b>Profile card style</b> — pick one below (your Telegram photo, name and @username "
                                   "appear exactly as in Telegram).\n"
                                   "Images are optional — turn them off for the fastest, lightest experience.",
                  settings_kb(p))


@guard()
async def settings_cmd(update, context):
    await _settings(update, context)


@guard()
async def settings_cb(update, context):
    c, uid = deps(context), update.effective_user.id
    parts = update.callback_query.data.split(":")
    key = parts[1]
    if key == "tpl" and len(parts) == 3 and parts[2] in ("face", "arena", "vip"):
        await c.repo.update_settings(uid, profile_template=parts[2])
        await ack(update, f"🎴 Profile card style: {parts[2].title()}")
    elif key == "preview":
        await ack(update, "Rendering your card...")
        return await send_profile(update, context, fresh=True, force_image=True)
    elif key in ("hand_images", "table_images", "notify"):
        p = await c.repo.get_player(uid)
        await c.repo.update_settings(uid, **{key: not p[key]})
        await ack(update, "Saved. Applies from your next match." if key != "notify" else "Saved.")
    else:
        await ack(update)
    await _settings(update, context)


def register(app) -> None:
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(history_cb, pattern=r"^h:list:\d+$"))
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^s:"))
