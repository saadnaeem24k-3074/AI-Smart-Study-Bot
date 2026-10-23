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


if __name__ == "__main__":
    unittest.main()
