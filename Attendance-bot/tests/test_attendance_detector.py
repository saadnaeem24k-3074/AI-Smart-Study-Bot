import unittest

from detection.attendance_detector import AttendanceDetector


class AttendanceDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = AttendanceDetector({
            "student": {"urdu_names": ["سعد نعیم"]},
        })

    def test_name_alone_never_triggers_a_chat_response(self):
        self.assertEqual(self.detector.analyze("Saad"), "nothing")
        self.assertEqual(self.detector.analyze("Saad, can you answer?"), "nothing")

    def test_attendance_word_triggers_once_without_name(self):
        self.assertEqual(self.detector.analyze("Teacher: attendance is being taken"), "mark_present")
        self.assertEqual(self.detector.analyze("attendance is being taken"), "nothing")

    def test_full_roll_number_triggers_but_bare_suffix_does_not(self):
        self.assertEqual(self.detector.analyze("My roll number is 24K-3074"), "mark_present")
        self.detector.reset()
        self.assertEqual(self.detector.analyze("Roll number 3074"), "nothing")

    def test_roll_number_mention_accepts_alternate_digit_grouping(self):
        self.assertTrue(self.detector.is_roll_mentioned("Saad, what is this? 24K3-074"))
        self.assertTrue(self.detector.is_roll_mentioned("24K-3074"))
        self.assertFalse(self.detector.is_roll_mentioned("Roll number 3074"))
        self.assertEqual(self.detector.analyze("24K3-074"), "nothing")

    def test_english_attendance_must_be_a_complete_word(self):
        self.assertEqual(self.detector.analyze("The attendances were recorded"), "nothing")


if __name__ == "__main__":
    unittest.main()
