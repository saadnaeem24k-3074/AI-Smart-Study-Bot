import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from platforms import meet_handler as mh
from utils import ai_notes


class Detector:
    def is_name_mentioned(self, t): return "saad" in t.lower()
    def is_roll_mentioned(self, t): return "24k3074" in t.lower().replace(" ", "").replace("-", "")


from detection.attendance_detector import AttendanceDetector

REAL = AttendanceDetector({"student": {"name": "Saad Naeem", "urdu_names": ["saad naeem", "saad"]}})


class CallOnMeTests(unittest.TestCase):
    def setUp(self):
        self.asked = []
        self.h = type("H", (), {})()
        self.h.detector, self.h._pending_name_at = REAL, 0.0
        self.h._queue_live_answer = self.asked.append
        self.h._log_class_question = lambda *a, **k: None
        self.h._process_sentence = lambda s: mh.MeetHandler._process_sentence(self.h, s)
        self.h._me_called = lambda t: mh.MeetHandler._me_called(self.h, t)
        self.say = lambda s: mh.MeetHandler._process_sentence(self.h, s)

    def test_silent_while_another_student_is_asked(self):
        for s in ["Ali, can you answer me a question?", "What is an algorithm?", "Ali are you there?"]:
            self.say(s)
        self.assertEqual(self.asked, [])

    def test_answers_remembered_question_when_my_roll_number_is_called(self):
        for s in ["What is an algorithm?", "Ali did not reply.", "Saad Naeem, you answer 24K3074."]:
            self.say(s)
        self.assertEqual(self.asked, ["What is an algorithm?"])

    def test_direct_question_to_me_is_answered(self):
        self.say("Saad Naeem, why analyse time complexity first?")
        self.assertEqual(len(self.asked), 1)

    def test_first_name_alone_does_not_trigger(self):
        self.say("Saad, why analyse time complexity first?")
        self.assertEqual(self.asked, [])

    def test_roll_number_alone_does_not_reuse_old_question(self):
        for s in ["What is an algorithm?", "24K3074 present?"]:
            self.say(s)
        self.assertEqual(self.asked, [])

    def test_microphone_hearing_a_question_is_silent(self):
        mh.MeetHandler._handle_microphone_transcript(self.h, "What is an algorithm? Ali answer please.")
        self.assertEqual(self.asked, [])


class NotesProviderTests(unittest.TestCase):
    def test_notes_use_gemini_when_chat_provider_is_groq(self):
        cfg = {"ai": {"provider": "groq", "keys": {"groq": "g", "gemini": "k"}}}
        self.assertEqual(ai_notes.config_store.ai_provider(ai_notes._notes_config(cfg)), "gemini")
        self.assertEqual(ai_notes.config_store.ai_provider(cfg), "groq")

    def test_live_reply_has_no_markdown(self):
        self.assertEqual(ai_notes._humanize("**Algorithm** is:\n- a *procedure* [00:01:44]"), "Algorithm is: a procedure")


if __name__ == "__main__":
    unittest.main()
