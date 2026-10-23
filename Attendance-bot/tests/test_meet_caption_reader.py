import unittest

from platforms.meet_handler import MeetHandler, _parse_caption_blocks
from utils.selectors import MEET


class FakePage:
    async def evaluate(self, _script, selectors):
        self.selectors = selectors
        return ["Teacher\nThe derivative of x squared is two x."]


class MeetCaptionReaderTests(unittest.IsolatedAsyncioTestCase):
    def test_discards_meet_ui_text_but_keeps_caption(self):
        self.assertEqual(
            _parse_caption_blocks([
                "No chat messages yet",
                "language English (India) format_size Font size circle Font colour settings Open caption settings",
                "Clasher Gamer!\nThe software testing phase checks for bugs.",
            ]),
            [("Clasher Gamer!", "The software testing phase checks for bugs.")],
        )

    async def test_reads_speaker_blocks_and_uses_selector_fallbacks(self):
        handler = object.__new__(MeetHandler)
        handler.page = FakePage()

        blocks = await handler._read_caption_blocks()

        self.assertEqual(
            blocks,
            [("Teacher", "The derivative of x squared is two x.")],
        )
        self.assertEqual(handler.page.selectors[0], MEET["caption_container"])
        self.assertIn(".iOzk7", handler.page.selectors)
        self.assertTrue(set(MEET["caption_fallbacks"]).issubset(handler.page.selectors))
        self.assertNotIn('[aria-live="polite"]', handler.page.selectors)


if __name__ == "__main__":
    unittest.main()
