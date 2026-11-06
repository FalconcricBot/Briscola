"""Game-style profile cards that show the user's real Telegram photo, name and @username
exactly as they appear in Telegram (Latin, Hindi/Devanagari, Cyrillic, colour emoji...).

Templates: "face" (portrait playing card), "arena" (landscape, fan of cards), "vip" (casino pass).
All functions return PNG BytesIO; call via asyncio.to_thread()."""
from __future__ import annotations

import io
import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ui.images import (CARD_H, CARD_W, GOLD, INK, PINK, PURPLE, SUIT_SYM, VIOLET, WHITE, RED_SUIT, BLACK_SUIT,
                       _card_face, _glow, background, font as dj_font)

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SYS = [Path("/usr/share/fonts/truetype"), Path("C:/Windows/Fonts"), Path("/Library/Fonts"), Path("/System/Library/Fonts")]
INK2, CREAM, LAVENDER = (34, 20, 62), (249, 246, 252), (200, 190, 235)
RANK_CARD = {"Bronze": "4", "Silver": "7", "Gold": "J", "Platinum": "Q", "Diamond": "K", "Master": "3", "Grandmaster": "A"}


def _find(*names: str) -> str | None:
    for n in names:
        if (FONTS / n).exists():
            return str(FONTS / n)
    for root in SYS:
        for n in names:
            hit = next(root.rglob(n), None) if root.exists() else None
            if hit:
                return str(hit)
    return None


@lru_cache(maxsize=96)
def _font(kind: str, size: int):
    path = {"main": _find("Poppins-Bold.ttf", "DejaVuSans-Bold.ttf"),
            "medium": _find("Poppins-Medium.ttf", "DejaVuSans.ttf"),
            "dj": _find("DejaVuSans-Bold.ttf"),
            "free": _find("FreeSansBold.ttf", "FreeSans.ttf", "arialbd.ttf"),
            "emoji": _find("NotoColorEmoji.ttf", "seguiemj.ttf")}[kind]
    if path is None:
        return None
    try:
        if kind == "emoji":
            return ImageFont.truetype(path, 109)
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return None


@lru_cache(maxsize=4096)
def _has(kind: str, ch: str) -> bool:
    f = _font(kind, 40)
    if f is None:
        return False
    def sig(c):
        im = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(im).text((6, 6), c, font=f, fill=255)
        return im.tobytes()
    return sig(ch) != sig("\U0010ffff")


def _is_emoji(cp: int) -> bool:
    if cp in (0x2660, 0x2661, 0x2662, 0x2663, 0x2664, 0x2665, 0x2666, 0x2667, 0x2605, 0x2606):
        return False
    return (cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF or 0x2190 <= cp <= 0x21FF
            or cp in (0x203C, 0x2049, 0x2122, 0x2139, 0x231A, 0x231B, 0x23E9, 0x23F0, 0x23F3, 0x24C2, 0x3030, 0x303D))


def _clusters(text: str):
    """Split into grapheme-ish clusters so emoji sequences (ZWJ, skin tones, flags) stay together."""
    out, i = [], 0
    while i < len(text):
        c = text[i]; i += 1
        cl = c
        ri = 0x1F1E6 <= ord(c) <= 0x1F1FF
        while i < len(text):
            n, cp = text[i], ord(text[i])
            if cp in (0x200D, 0xFE0F, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF or (ri and 0x1F1E6 <= cp <= 0x1F1FF and len(cl) == 1):
                cl += n; i += 1
                if cp == 0x200D and i < len(text):
                    cl += text[i]; i += 1
            else:
                break
        out.append(cl)
    return out


def _runs(text: str):
    """-> [(kind, string)] where kind is a font key or 'emoji'. Unsupported characters are dropped."""
    runs: list[list] = []
    for cl in _clusters(" ".join(text.split())):
        base = ord(cl[0])
        if cl.isspace():
            kind = None
        elif _is_emoji(base) or "\ufe0f" in cl:
            kind = "emoji" if _has("emoji", cl[0]) else None
        else:
            kind = next((k for k in ("main", "dj", "free") if all(_has(k, ch) or ch in "\u200d\u200c" or ord(ch) < 32 for ch in cl)), None)
        if kind is None and cl.isspace():
            kind = runs[-1][0] if runs and runs[-1][0] != "emoji" else "main"
        if kind is None:
            continue
        if runs and runs[-1][0] == kind and kind != "emoji":
            runs[-1][1] += cl
        else:
            runs.append([kind, cl])
    return runs


def rich_width(text: str, size: int) -> float:
    w = 0.0
    for kind, s in _runs(text):
        w += size * 1.12 if kind == "emoji" else _font(kind, size).getlength(s)
        if kind == "emoji":
            w += size * 1.12 * (len(_clusters(s)) - 1)
    return w


def draw_rich(img: Image.Image, xy, text: str, size: int, fill, anchor: str = "l", max_width: int | None = None,
              min_size: int = 16) -> int:
    """Draw mixed-script text. anchor: l/m/r (horizontal) around xy=(x, y_center). Shrinks to fit max_width.
    Returns the size actually used."""
    text = " ".join((text or "").split()) or "Player"
    if max_width:
        while size > min_size and rich_width(text, size) > max_width:
            size -= 1
        if rich_width(text, size) > max_width:           # still too wide: trim with an ellipsis
            while len(text) > 1 and rich_width(text + "…", size) > max_width:
                text = text[:-1]
            text = text.rstrip() + "…"
    total = rich_width(text, size)
    x, y = xy
    x = x - total / 2 if anchor == "m" else (x - total if anchor == "r" else x)
    base = y + size * 0.36
    d = ImageDraw.Draw(img)
    for kind, s in _runs(text):
        if kind == "emoji":
            f = _font("emoji", 109)
            for cl in _clusters(s):
                tile = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
                ImageDraw.Draw(tile).text((0, 0), cl, font=f, embedded_color=True)
                bb = tile.getbbox() or (0, 0, 136, 128)
                tile = tile.crop(bb)
                sc = (size * 1.05) / max(tile.height, 1)
                tile = tile.resize((max(1, int(tile.width * sc)), max(1, int(tile.height * sc))), Image.LANCZOS)
                img.alpha_composite(tile, (int(x), int(y - tile.height / 2)))
                x += size * 1.12
        else:
            f = _font(kind, size)
            d.text((x, base), s, font=f, fill=fill, anchor="ls")
            x += f.getlength(s)
    return size


# --------------------------------------------------------------------------- pieces
def _avatar(avatar: bytes | None, name: str, w: int, h: int | None = None, radius: int | None = None) -> Image.Image:
    """Circle (radius=None, w==h) or rounded rectangle avatar. Falls back to a monogram of the first character."""
    h = h or w
    im = None
    if avatar:
        try:
            im = ImageOps.fit(Image.open(io.BytesIO(avatar)).convert("RGBA"), (w, h), Image.LANCZOS, centering=(0.5, 0.35))
        except Exception:
            im = None
    if im is None:
        g = Image.linear_gradient("L").resize((w, h))
        im = ImageOps.colorize(g, black=VIOLET, white=PINK).convert("RGBA")
        cl = next((c for c in _clusters(name.strip()) if not c.isspace()), "?")
        draw_rich(im, (w // 2, h // 2), cl.upper(), int(min(w, h) * 0.5), WHITE, "m")
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    if radius is None:
        md.ellipse([0, 0, w - 1, h - 1], fill=255)
    else:
        md.rounded_rectangle([0, 0, w - 1, h - 1], radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def _tilt(code: str, angle: float, scale: float, trump: bool = False) -> Image.Image:
    face = _card_face(code, trump).resize((int(CARD_W * scale), int(CARD_H * scale)), Image.LANCZOS)
    return face.rotate(angle, expand=True, resample=Image.BICUBIC)


def _pill(img, box, fill, outline=None, width=2):
    ImageDraw.Draw(img).rounded_rectangle(box, (box[3] - box[1]) // 2, fill=fill, outline=outline, width=width)


def _stat_chips(img, x0, y0, total_w, h, items, gap=10, dark=True):
    n = len(items)
    cw = (total_w - gap * (n - 1)) // n
    d = ImageDraw.Draw(img)
    for i, (lab, val) in enumerate(items):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([x, y0, x + cw, y0 + h], 14, fill=INK2 if dark else (20, 8, 40), outline=VIOLET, width=2)
        d.text((x + cw // 2, y0 + h * 0.27), lab, font=dj_font(max(11, int(h * 0.19))), fill=LAVENDER, anchor="mm")
        draw_rich(img, (x + cw // 2, y0 + h * 0.65), str(val), int(h * 0.38), GOLD, "m", max_width=cw - 12)


def _xp_bar(img, x0, x1, y, h, xp, floor, nxt):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y, x1, y + h], h // 2, fill=(20, 8, 40), outline=VIOLET, width=2)
    frac = 1.0 if nxt is None else max(0.0, min(1.0, (xp - floor) / max(nxt - floor, 1)))
    if frac > 0:
        d.rounded_rectangle([x0, y, x0 + max(h, int((x1 - x0) * frac)), y + h], h // 2, fill=PINK)


def _png(img) -> io.BytesIO:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    buf.seek(0); buf.name = "profile.png"
    return buf


def _suit_for(player_no: int) -> str:
    return "HDCS"[player_no % 4]


def _suit_color(s: str):
    return RED_SUIT if s in "HD" else BLACK_SUIT


def _pct(stats):
    return f"{stats['win_pct']:.0f}%"


# --------------------------------------------------------------------------- template A: playing card
def _face(name, username, player_no, rank_name, level, xp, floor, nxt, stats, avatar):
    W, H = 680, 940
    img = background(W, H)
    suit = _suit_for(player_no)
    col = _suit_color(suit)
    rank = RANK_CARD.get(rank_name, "A")
    d = ImageDraw.Draw(img)
    _glow(img, (40, 40, 640, 900), PINK, radius=18, grow=6)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 40, 640, 900], 38, fill=GOLD)
    d.rounded_rectangle([48, 48, 632, 892], 32, fill=CREAM)
    d.rounded_rectangle([62, 62, 618, 878], 24, outline=VIOLET, width=3)
    # watermark suit
    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(wm).text((340, 620), SUIT_SYM[suit], font=dj_font(520), fill=col + (22,), anchor="mm")
    img.alpha_composite(wm)
    # corner indices (bottom-right is the top-left rotated 180°)
    idx = Image.new("RGBA", (110, 170), (0, 0, 0, 0))
    idd = ImageDraw.Draw(idx)
    idd.text((55, 52), rank, font=dj_font(78 if rank != "10" else 60), fill=col, anchor="mm")
    idd.text((55, 128), SUIT_SYM[suit], font=dj_font(66), fill=col, anchor="mm")
    img.alpha_composite(idx, (68, 74))
    img.alpha_composite(idx.rotate(180), (W - 68 - 110, H - 74 - 170))
    # avatar in a face-card panel
    fx0, fy0, fx1, fy1 = 160, 118, 520, 560
    d.rounded_rectangle([fx0, fy0, fx1, fy1], 30, fill=PURPLE)
    d.rounded_rectangle([fx0 + 8, fy0 + 8, fx1 - 8, fy1 - 8], 24, outline=PINK, width=3)
    av = _avatar(avatar, name, fx1 - fx0 - 36, fy1 - fy0 - 36, radius=18)
    img.alpha_composite(av, (fx0 + 18, fy0 + 18))
    for (sx, sy) in ((fx0 + 4, fy0 + 4), (fx1 - 4, fy0 + 4), (fx0 + 4, fy1 - 4), (fx1 - 4, fy1 - 4)):
        d.ellipse([sx - 22, sy - 22, sx + 22, sy + 22], fill=CREAM, outline=GOLD, width=3)
        d.text((sx, sy + 1), SUIT_SYM[suit], font=dj_font(26), fill=col, anchor="mm")
    # rank banner
    _pill(img, (190, 536, 490, 588), INK2, PINK, 3)
    d = ImageDraw.Draw(img)
    d.text((340, 562), f"{rank_name.upper()}  •  LV {level}", font=dj_font(24), fill=WHITE, anchor="mm")
    # name + username (exactly as in Telegram)
    draw_rich(img, (340, 650), name, 54, INK2, "m", max_width=440, min_size=22)
    if username:
        draw_rich(img, (340, 710), f"@{username}", 30, VIOLET, "m", max_width=420, min_size=16)
    _xp_bar(img, 170, 510, 746, 16, xp, floor, nxt)
    ImageDraw.Draw(img).text((340, 786), f"{xp:,} XP" + (f"  /  {nxt:,}" if nxt else "  •  MAX"), font=dj_font(15), fill=VIOLET, anchor="mm")
    _stat_chips(img, 160, 806, 360, 66, [("MATCHES", stats["matches"]), ("WINS", stats["wins"]), ("WIN %", _pct(stats))], gap=8)
    return img


# --------------------------------------------------------------------------- template B: arena + fan
def _arena(name, username, player_no, rank_name, level, xp, floor, nxt, stats, avatar):
    W, H = 1000, 560
    img = background(W, H)
    suit = _suit_for(player_no)
    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(wm).text((840, 300), SUIT_SYM[suit], font=dj_font(460), fill=(255, 255, 255, 14), anchor="mm")
    img.alpha_composite(wm)
    rank = RANK_CARD.get(rank_name, "A")
    # fan of cards behind the avatar: your "rank card" in the middle
    fan = [(f"3{'HDCS'[(player_no + 1) % 4]}", 26, False), (f"A{'HDCS'[(player_no + 2) % 4]}", -26, False), (f"{rank}{suit}", 0, True)]
    for code, ang, top in fan:
        t = _tilt(code, ang, 0.74, trump=top)
        cx = 205 + int(math.sin(math.radians(-ang)) * 150)
        cy = 215 - int(math.cos(math.radians(ang)) * 40)
        if top:
            _glow(img, (cx - t.width // 2 + 18, cy - t.height // 2 + 18, cx + t.width // 2 - 18, cy + t.height // 2 - 18), GOLD, 14, 2)
        img.alpha_composite(t, (cx - t.width // 2, cy - t.height // 2))
    # avatar disc
    S = 250
    _glow(img, (80, 250, 80 + S, 250 + S), PINK, radius=16, grow=6)
    d = ImageDraw.Draw(img)
    d.ellipse([74, 244, 80 + S + 6, 250 + S + 6], fill=PINK)
    d.ellipse([80, 250, 80 + S, 250 + S], fill=INK)
    img.alpha_composite(_avatar(avatar, name, S - 12), (86, 256))
    # texts
    draw_rich(img, (400, 150), name, 66, WHITE, "l", max_width=560, min_size=26)
    if username:
        draw_rich(img, (402, 212), f"@{username}", 32, (255, 150, 205), "l", max_width=520, min_size=16)
    _pill(img, (400, 252, 640, 302), PURPLE, PINK, 3)
    d = ImageDraw.Draw(img)
    d.text((520, 277), rank_name.upper(), font=dj_font(24), fill=WHITE, anchor="mm")
    d.text((662, 277), f"LEVEL {level}", font=dj_font(28), fill=GOLD, anchor="lm")
    _xp_bar(img, 400, 940, 322, 20, xp, floor, nxt)
    d.text((400, 362), f"{xp:,} XP" + (f" / {nxt:,}" if nxt else "  (MAX)"), font=dj_font(16), fill=WHITE, anchor="lm")
    _stat_chips(img, 400, 392, 540, 78, [("MATCHES", stats["matches"]), ("WINS", stats["wins"]),
                                         ("WIN %", _pct(stats)), ("STREAK", stats["streak"])])
    d.text((400, 506), f"PLAYER ID  BA{player_no}", font=dj_font(18), fill=LAVENDER, anchor="lm")
    d.text((940, 506), "BRISCOLA ARENA", font=dj_font(18), fill=PINK, anchor="rm")
    return img


# --------------------------------------------------------------------------- template C: VIP pass
def _vip(name, username, player_no, rank_name, level, xp, floor, nxt, stats, avatar):
    W, H = 1000, 520
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bg = ImageOps.colorize(Image.linear_gradient("L").rotate(90).resize((W, H)), black=(10, 6, 22), white=(40, 14, 70)).convert("RGBA")
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([6, 6, W - 7, H - 7], 34, fill=255)
    for cx in (330,):                                   # ticket notches
        md.ellipse([cx - 22, -22, cx + 22, 22], fill=0)
        md.ellipse([cx - 22, H - 22, cx + 22, H + 22], fill=0)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, W - 7, H - 7], 34, outline=GOLD, width=4)
    d.rounded_rectangle([18, 18, W - 19, H - 19], 26, outline=(120, 90, 30), width=1)
    for y in range(40, H - 40, 16):                     # perforation
        d.ellipse([327, y, 333, y + 6], fill=GOLD)
    # stub (left): avatar + barcode
    d.text((165, 52), "V I P   P A S S", font=dj_font(20), fill=GOLD, anchor="mm")
    _glow(img, (65, 80, 265, 280), GOLD, 14, 4)
    d = ImageDraw.Draw(img)
    d.ellipse([60, 75, 270, 285], fill=GOLD)
    img.alpha_composite(_avatar(avatar, name, 198), (66, 81))
    rnd = random.Random(player_no)
    x = 50
    while x < 280:
        w = rnd.choice((2, 2, 3, 5)); d.rectangle([x, 350, x + w, 440], fill=(240, 235, 250)); x += w + rnd.choice((2, 3, 4))
    d.text((165, 462), f"BA{player_no}", font=dj_font(22), fill=GOLD, anchor="mm")
    # main
    d.text((370, 62), "BRISCOLA ARENA  •  PREMIUM CARD CLUB", font=dj_font(17), fill=PINK, anchor="lm")
    draw_rich(img, (370, 140), name, 64, WHITE, "l", max_width=420, min_size=26)
    if username:
        draw_rich(img, (372, 202), f"@{username}", 30, (255, 150, 205), "l", max_width=420, min_size=16)
    rank = RANK_CARD.get(rank_name, "A")
    suit = _suit_for(player_no)
    t = _tilt(f"{rank}{suit}", 8, 0.62, trump=True)
    _glow(img, (820, 60, 820 + t.width, 60 + t.height), GOLD, 12, 2)
    img.alpha_composite(t, (820, 56))
    _pill(img, (370, 240, 600, 288), PURPLE, GOLD, 3)
    d = ImageDraw.Draw(img)
    d.text((485, 264), rank_name.upper(), font=dj_font(22), fill=WHITE, anchor="mm")
    d.text((622, 264), f"LV {level}", font=dj_font(26), fill=GOLD, anchor="lm")
    _xp_bar(img, 370, 780, 312, 16, xp, floor, nxt)
    d.text((370, 346), f"{xp:,} XP" + (f" / {nxt:,}" if nxt else "  (MAX)"), font=dj_font(15), fill=WHITE, anchor="lm")
    _stat_chips(img, 370, 376, 590, 84, [("MATCHES", stats["matches"]), ("WINS", stats["wins"]), ("WIN %", _pct(stats)),
                                         ("BEST", stats["highest"])])
    return img


TEMPLATES = {"face": _face, "arena": _arena, "vip": _vip}


def render_profile_card(template: str = "face", *, name: str, username: str | None, player_no: int, rank_name: str,
                        level: int, xp: int, xp_floor: int, xp_next: int | None, stats: dict,
                        avatar: bytes | None = None) -> io.BytesIO:
    fn = TEMPLATES.get(template, _face)
    return _png(fn(name, username, player_no, rank_name, level, xp, xp_floor, xp_next, stats, avatar))
