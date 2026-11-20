import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detection.attendance_detector import AttendanceDetector
from platforms import meet_handler as mh
from utils import ai_notes

DET = AttendanceDetector({"student": {"name": "Saad Naeem", "urdu_names": ["saad naeem", "saad"]}})
H = mh.MeetHandler


def make():
    h = type("H", (), {})()
    h.asked, h.detector, h._pending_name_at = [], DET, 0.0
    h._pending_live_question_at, h._pending_live_question, h._question_caption_texts = 0.0, "", {}
    h._queue_live_answer = lambda q: (h.asked.append(q), setattr(h, "_followup_until", time.time() + 75))
    h._log_class_question = lambda *a, **k: None
    h._me_called = lambda t: H._me_called(h, t)
    h._is_recent_duplicate = lambda q, now: False
    h._can_recall = lambda item, now: H._can_recall(h, item, now)
    h._calls_someone_else = lambda s: H._calls_someone_else(h, s)
    h.say = lambda s: H._process_sentence(h, s)
    return h


class FollowUpTests(unittest.TestCase):
    def test_follow_up_questions_need_no_name_after_i_was_called(self):
        h = make()
        h.say("Saad Naeem, what is an algorithm?")
        h.say("What is a flowchart?")
        h.say("Why do we test software early?")
        self.assertEqual(len(h.asked), 3)

    def test_follow_up_stops_when_another_student_is_called(self):
        h = make()
        h.say("Saad Naeem, what is an algorithm?")
        h.say("Ali, can you tell me what a flowchart is?")
        h.say("What is a pseudocode?")
        self.assertEqual(len(h.asked), 1)

    def test_roll_number_of_someone_else_stops_follow_up(self):
        h = make()
        h.say("Saad Naeem, what is an algorithm?")
        h.say("24K3001, what is a flowchart?")
        self.assertEqual(len(h.asked), 1)

    def test_no_follow_up_without_being_called_first(self):
        h = make()
        h.say("What is a flowchart?")
        self.assertEqual(h.asked, [])

    def test_name_only_call_recalls_question_asked_to_someone_else(self):
        h = make()
        h.say("What is an algorithm?")
        h.say("Ali did not answer.")
        h.say("Saad Naeem?")
        self.assertEqual(h.asked, [])                      # waits a beat for a fresh question
        self.assertEqual(h._recall[1], "What is an algorithm?")
        h._recall = (time.time() - 5, h._recall[1])        # no new question arrived
        H._check_for_addressed_question(h, [])
        self.assertEqual(h.asked, ["What is an algorithm?"])

    def test_new_question_after_name_beats_the_recalled_one(self):
        h = make()
        h.say("What is an algorithm?")
        h.say("Saad Naeem.")
        h.say("What is a database?")
        self.assertEqual(h.asked, ["What is a database?"])
        self.assertIsNone(h._recall)

    def test_explicit_you_answer_is_immediate(self):
        h = make()
        h.say("What is an algorithm?")
        h.say("Saad Naeem, you answer.")
        self.assertEqual(h.asked, ["What is an algorithm?"])


class ProviderTests(unittest.TestCase):
    def test_dead_provider_is_skipped_for_live_replies(self):
        ai_notes._DEAD["deepseek"] = time.time() + 100
        try:
            self.assertTrue(ai_notes._is_dead("deepseek"))
            self.assertFalse(ai_notes._is_dead("gemini"))
        finally:
            ai_notes._DEAD.clear()

    def test_sentence_like_diagram_is_dropped_and_labels_are_short(self):
        long = "A unit is defined as the smallest element of software, such as a single function or module"
        self.assertEqual(ai_notes._normalize_diagrams(
            [{"type": "analogy", "title": "Unit", "nodes": [long, long + " again", long + " more"]}]), [])
        good = ai_notes._normalize_diagrams(
            [{"type": "process", "title": "Testing levels in the software life cycle phases today",
              "nodes": ["Unit testing in the coding phase of work", "Integration", "System"]}])
        self.assertEqual(len(good), 1)
        self.assertTrue(all(len(n) <= 34 for n in good[0]["nodes"]))

    def test_foreign_script_detected(self):
        self.assertTrue(ai_notes.has_foreign_script("तो यह point जो है"))
        self.assertTrue(ai_notes.has_foreign_script("یہ بہت اہم ہے"))
        self.assertFalse(ai_notes.has_foreign_script("This is important."))


class LiveProviderTests(unittest.TestCase):
    CFG = {"ai": {"provider": "gemini", "keys": {"gemini": "g", "groq": "q", "deepseek": "d"}}}

    def _run(self, cfg, fail=()):
        from unittest import mock
        calls = []

        def fake(config, user, max_tokens, system=None, timeout=12, **k):
            prov = ai_notes.config_store.ai_provider(config)
            calls.append(prov)
            return None if prov in fail else '{"answer": "ok"}'
        with mock.patch.object(ai_notes, "_call", fake):
            out = ai_notes._call_live(cfg, "q", 100)
        return out, calls

    def test_groq_answers_live_questions_first(self):
        out, calls = self._run(self.CFG)
        self.assertEqual(calls[0], "groq")
        self.assertEqual(ai_notes.LAST_LIVE_REPLY["provider"], "groq")

    def test_falls_back_to_main_provider_when_groq_fails(self):
        out, calls = self._run(self.CFG, fail=("groq",))
        self.assertEqual(ai_notes.LAST_LIVE_REPLY["provider"], "gemini")

    def test_auto_uses_main_provider(self):
        cfg = {**self.CFG, "features": {"live_reply_provider": "auto"}}
        out, calls = self._run(cfg)
        self.assertEqual(calls[0], "gemini")




class AnswerToggleTests(unittest.TestCase):
    def _handler(self, features):
        h = make()
        h.features = features
        h._answers_off_logged = False
        h._answers_enabled = lambda: H._answers_enabled(h)
        logged = []
        h._log_class_question = lambda q, **k: logged.append((q, k))
        h.logged = logged
        return h

    def test_off_means_no_answer_but_question_is_still_noted(self):
        h = self._handler({"answer_questions": False})
        H._queue_live_answer(h, "What is an algorithm?")
        self.assertEqual(h.logged, [("What is an algorithm?", {"to_me": True})])

    def test_default_is_on(self):
        self.assertTrue(H._answers_enabled(self._handler({})))
        self.assertTrue(ai_notes.config_store.get_features({})["answer_questions"])


if __name__ == "__main__":
    unittest.main()
