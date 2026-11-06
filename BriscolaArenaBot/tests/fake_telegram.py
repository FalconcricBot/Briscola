"""Minimal stand-ins for python-telegram-bot so the game manager can be tested offline.
Only installed when the real library is missing."""
import sys
import types


def install() -> bool:
    try:
        import telegram  # noqa: F401
        return False
    except ImportError:
        pass
    tg = types.ModuleType("telegram")

    class _Obj:
        def __init__(self, *a, **kw):
            self.args, self.kw = a, kw

    class InlineKeyboardButton(_Obj):
        def __init__(self, text, callback_data=None, url=None, **kw):
            self.text, self.callback_data, self.url = text, callback_data, url

    class InlineKeyboardMarkup(_Obj):
        def __init__(self, rows):
            self.inline_keyboard = rows

    class InputMediaPhoto(_Obj):
        def __init__(self, media, caption=None, parse_mode=None):
            self.media, self.caption = media, caption

    tg.InlineKeyboardButton, tg.InlineKeyboardMarkup, tg.InputMediaPhoto = InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
    tg.Update = _Obj
    tg.BotCommand = _Obj

    const = types.ModuleType("telegram.constants")
    const.ParseMode = types.SimpleNamespace(HTML="HTML")
    const.ChatAction = types.SimpleNamespace(TYPING="typing")
    const.ChatType = types.SimpleNamespace(PRIVATE="private")

    err = types.ModuleType("telegram.error")

    class TelegramError(Exception): ...
    class BadRequest(TelegramError): ...
    class Forbidden(TelegramError): ...
    class NetworkError(TelegramError): ...
    class TimedOut(NetworkError): ...
    class Conflict(TelegramError): ...

    class RetryAfter(TelegramError):
        def __init__(self, retry_after=1):
            super().__init__("retry")
            self.retry_after = retry_after

    for c in (TelegramError, BadRequest, Forbidden, NetworkError, TimedOut, RetryAfter, Conflict):
        setattr(err, c.__name__, c)

    ext = types.ModuleType("telegram.ext")
    ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    sys.modules.update({"telegram": tg, "telegram.constants": const, "telegram.error": err, "telegram.ext": ext})
    return True
