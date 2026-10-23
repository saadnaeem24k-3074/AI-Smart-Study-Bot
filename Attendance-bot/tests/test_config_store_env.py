import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from core import config_store


class AIKeyEnvironmentTests(unittest.TestCase):
    def test_dashboard_key_is_saved_to_env_not_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            config = {"ai": {"provider": "deepseek", "keys": {}, "models": {}}}
            with (
                patch.object(config_store, "ENV_PATH", env_path),
                patch.object(config_store, "load_raw", return_value=config),
                patch.object(config_store, "save_raw") as save_raw,
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}),
            ):
                config_store.update_settings({
                    "ai": {"provider": "deepseek", "api_key": "test-secret"}
                })

                saved_config = save_raw.call_args.args[0]
                self.assertNotIn("deepseek", saved_config["ai"]["keys"])
                self.assertEqual(
                    dotenv_values(env_path)["DEEPSEEK_API_KEY"], "test-secret"
                )

    def test_dashboard_clear_removes_key_from_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            config = {
                "ai": {
                    "provider": "deepseek",
                    "keys": {"deepseek": "legacy-secret"},
                    "models": {},
                }
            }
            with (
                patch.object(config_store, "ENV_PATH", env_path),
                patch.object(config_store, "load_raw", return_value=config),
                patch.object(config_store, "save_raw"),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}),
            ):
                config_store.update_settings({
                    "ai": {"provider": "deepseek", "clear_key": True}
                })

                self.assertNotIn("DEEPSEEK_API_KEY", dotenv_values(env_path))


if __name__ == "__main__":
    unittest.main()
