import io
import unittest

from tests import fake_telegram

fake_telegram.install()

from PIL import Image, ImageDraw                                     # noqa: E402

from keyboards.profile_keyboard import settings_kb                   # noqa: E402
from ui import profile_cards as pc                                    # noqa: E402

STATS = dict(matches=10, wins=6, win_pct=60.0, streak=2, highest=88, losses=3, draws=1, points=500)


def card(tpl, name="Nihar", username="nihar", avatar=None, rank="Gold", xp_next=3500):
    return pc.render_profile_card(tpl, name=name, username=username, player_no=10001, rank_name=rank, level=5, xp=2000,
                                  xp_floor=1500, xp_next=xp_next, stats=STATS, avatar=avatar)


def jpeg() -> bytes:
    im = Image.new("RGB", (300, 400), (30, 120, 160))
    ImageDraw.Draw(im).ellipse([80, 60, 220, 220], fill=(230, 180, 150))
    b = io.BytesIO(); im.save(b, "JPEG"); return b.getvalue()


class ProfileCardTests(unittest.TestCase):
    def test_all_templates_render_png_with_and_without_photo(self):
        for tpl in ("face", "arena", "vip"):
            for av in (None, jpeg(), b"not an image"):                    # bad bytes fall back to the monogram
                buf = card(tpl, avatar=av)
                self.assertEqual(buf.getvalue()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(Image.open(card("face")).size, (680, 940))
        self.assertEqual(Image.open(card("arena")).size, (1000, 560))
        self.assertEqual(Image.open(card("vip")).size, (1000, 520))

    def test_unusual_names_never_crash(self):
        names = ["निहार 🔥 Sharma", "Aisha ✨ अंजलि 💎", "👨‍👩‍👧 family", "🇮🇳 India", "Ünïcödé Ñame", "Иван Петров",
                 "x" * 100, "Very Long Display Name That Keeps Going And Going Forever 🙂", "   ", "", "\u200b", "عربي"]
        for tpl in ("face", "arena", "vip"):
            for n in names:
                card(tpl, name=n, username="u" * 32)
                card(tpl, name=n, username=None, rank="Grandmaster", xp_next=None)

    def test_exact_text_is_preserved(self):
        runs = pc._runs("निहार 🔥 Sharma")
        self.assertEqual([k for k, _ in runs if k == "emoji"], ["emoji"])
        joined = "".join(s for _, s in runs)
        self.assertEqual(joined.replace(" ", ""), "निहार🔥Sharma")            # nothing dropped, order kept
        self.assertGreater(pc.rich_width("Hello", 40), pc.rich_width("Hi", 40))
        self.assertEqual(pc._runs("   "), [])

    def test_long_name_is_fitted(self):
        im = Image.new("RGBA", (800, 100))
        used = pc.draw_rich(im, (10, 50), "W" * 60, 60, (255, 255, 255, 255), "l", max_width=300, min_size=20)
        self.assertLessEqual(used, 60)
        right_edge = im.getbbox()[2]
        self.assertLessEqual(right_edge, 10 + 300 + 6)                       # shrunk / trimmed to the box

    def test_rank_maps_to_card_and_suit_is_stable(self):
        self.assertEqual(pc.RANK_CARD["Grandmaster"], "A")
        self.assertEqual(pc._suit_for(10001), pc._suit_for(10001))
        self.assertEqual({pc._suit_for(i) for i in range(4)}, set("HDCS"))


class SettingsKeyboardTests(unittest.TestCase):
    def test_template_buttons_and_selection_mark(self):
        p = dict(hand_images=True, table_images=True, notify=True, profile_template="arena")
        rows = settings_kb(p).inline_keyboard
        styles = rows[0]
        self.assertEqual([b.callback_data for b in styles], ["s:tpl:face", "s:tpl:arena", "s:tpl:vip"])
        self.assertTrue(styles[1].text.startswith("✅"))
        self.assertFalse(styles[0].text.startswith("✅"))
        self.assertEqual(rows[1][0].callback_data, "s:preview")
        self.assertTrue(all(len(b.callback_data.encode()) <= 64 for r in rows for b in r if b.callback_data))
        # old players without the key default to 'face'
        self.assertTrue(settings_kb(dict(hand_images=1, table_images=1, notify=1)).inline_keyboard[0][0].text.startswith("✅"))


if __name__ == "__main__":
    unittest.main()
