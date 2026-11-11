import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detection.attendance_detector import AttendanceDetector
from utils import notes_recorder, pdf_builder


class AddressedTests(unittest.TestCase):
    def setUp(self):
        self.d = AttendanceDetector({"student": {"name": "Saad Naeem", "urdu_names": ["سعد", "saad"]}})

    def test_full_name_and_roll_only(self):
        for t in ["Saad Naeem, answer this", "sad naim", "24K3074 you answer", "سعد نعیم جواب دیں"]:
            self.assertTrue(self.d.is_addressed(t), t)
        for t in ["Saad, answer this", "Ali answer", "مسدود ہے", "What is an algorithm?"]:
            self.assertFalse(self.d.is_addressed(t), t)

    def test_first_name_opt_in(self):
        d = AttendanceDetector({"student": {"name": "Saad Naeem", "urdu_names": [], "respond_to_first_name": True}})
        self.assertTrue(d.is_addressed("Saad, answer this"))


class RecorderQuestionTests(unittest.TestCase):
    def test_questions_merge_and_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_recorder.NOTES_ROOT = notes_recorder.Path(tmp)
            r = notes_recorder.NotesRecorder({"subject": "AI"}, {"features": {"notes": True}})
            r.add_question("What is an")
            r.add_question("What is an algorithm?")
            r.add_question("What is an algorithm?", to_me=True, answer="A step-by-step procedure.")
            self.assertEqual(len(r.questions), 1)
            self.assertTrue(r.questions[0]["to_me"])
            self.assertIn("Questions asked in class", r._render_md(None))
            html = pdf_builder.build_html({
                "subject": "AI", "title": "AI", "date_str": "", "start_time": "", "end_time": "", "duration_s": 60,
                "words": 5, "speakers": 1, "slides": [], "summary": None, "flags": [],
                "class_questions": [{"time": "10:00:00", "text": "What is an algorithm?", "to_me": True,
                                     "bot_answer": "x", "answer": "A step-by-step procedure."}],
                "keywords": [], "transcript": [], "ai_requested": False}, {})
            self.assertIn("Questions Asked in Class", html)


if __name__ == "__main__":
    unittest.main()
