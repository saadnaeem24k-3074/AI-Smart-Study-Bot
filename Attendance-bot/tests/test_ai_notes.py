import json
import unittest
from unittest.mock import patch

from utils import ai_notes


class DeepSeekRequestTests(unittest.TestCase):
    @patch("utils.ai_notes._post")
    @patch("utils.ai_notes.config_store.ai_model", return_value="deepseek-chat")
    @patch("utils.ai_notes.config_store.ai_provider", return_value="deepseek")
    @patch("utils.ai_notes.config_store.ai_key", return_value="test-api-key")
    def test_uses_bearer_api_key(self, _key, _provider, _model, post):
        post.return_value = {"choices": [{"message": {"content": '{"summary": []}'}}]}

        result = ai_notes._call({}, "test prompt", 100)

        self.assertEqual(result, '{"summary": []}')
        self.assertEqual(post.call_args.args[1]["Authorization"], "Bearer test-api-key")


class GeminiDiagramRequestTests(unittest.TestCase):
    @patch("utils.ai_notes._post")
    @patch("utils.ai_notes.config_store.ai_model", return_value="gemini-2.5-flash")
    @patch("utils.ai_notes.config_store.ai_provider", return_value="gemini")
    @patch("utils.ai_notes.config_store.ai_key", return_value="test-gemini-key")
    def test_gemini_key_and_json_output_are_used_for_diagram_notes(
        self, _key, _provider, _model, post
    ):
        content = '{"sections":[{"heading":"Process","diagrams":[{"type":"process"}]}]}'
        post.return_value = {
            "candidates": [{"content": {"parts": [{"text": content}]}}],
        }

        result = ai_notes._call({}, "Generate lecture notes with diagrams.", 1200)

        self.assertEqual(result, content)
        url, headers, body, provider = post.call_args.args
        self.assertEqual(url, ai_notes.GEMINI_URL.format(model="gemini-2.5-flash"))
        self.assertEqual(headers["x-goog-api-key"], "test-gemini-key")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(provider, "Gemini")


class StudyQuestionTests(unittest.TestCase):
    @patch("utils.ai_notes._call")
    def test_question_without_lecture_context_uses_general_knowledge(self, call):
        call.return_value = '{"answer":"A database is an organized collection of data."}'
        config = {"ai": {"provider": "gemini", "keys": {"gemini": "test-key"}}}

        answer = ai_notes.answer_question(config, "", "What is a database?")

        self.assertEqual(answer, "A database is an organized collection of data.")
        prompt = call.call_args.args[1]
        self.assertIn("general knowledge", prompt)
        self.assertIn("(No lecture material is available.)", prompt)
        self.assertIn("What is a database?", prompt)

    @patch("utils.ai_notes._call")
    def test_study_chat_requires_short_answers_and_caps_long_provider_replies(self, call):
        long_answer = "\n".join(
            f"Point {index} explains several details about this topic." for index in range(1, 8)
        )
        call.return_value = json.dumps({"answer": long_answer})
        config = {"ai": {"provider": "gemini", "keys": {"gemini": "test-key"}}}

        answer = ai_notes.answer_question(config, "", "What is a database?")

        self.assertLessEqual(len(answer.splitlines()), 4)
        self.assertLessEqual(len(answer.split()), 35)
        self.assertTrue(answer.endswith("..."))
        prompt = call.call_args.args[1]
        self.assertIn("never more than 4 lines or 35 words", prompt)
        self.assertIn("do not add", prompt)


if __name__ == "__main__":
    unittest.main()
