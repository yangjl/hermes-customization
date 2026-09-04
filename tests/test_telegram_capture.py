from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Upstream commit 5e01b8fa7a added hermes_state_holders.py without declaring it
# in pyproject's py-modules, so the venv's editable finder can't see it. Put
# the source checkout on sys.path until upstream fixes the manifest.
sys.path.insert(0, os.path.expanduser(os.environ.get("HERMES_SOURCE_DIR", "~/.hermes/hermes-agent")))

from hermes_cli import kanban_db as kb


HANDLER = Path(__file__).resolve().parents[1] / "hooks/telegram-idea-capture/handler.py"


def load_handler():
    spec = importlib.util.spec_from_file_location("telegram_capture_test", HANDLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TelegramCaptureTest(unittest.TestCase):
    def test_capture_lands_in_non_dispatchable_review_state_with_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"HERMES_HOME": str(Path(directory) / ".hermes")},
            clear=False,
        ):
            handler = load_handler()
            task_id = handler._capture("Review the new maize figures", {"platform": "telegram", "chat_id": "42"})
            duplicate_id = handler._capture("Review the new maize figures", {"platform": "telegram", "chat_id": "42"})
            conn = kb.connect(board="inbox")
            try:
                task = kb.get_task(conn, task_id)
            finally:
                conn.close()

        assert task is not None
        self.assertEqual(task.status, "blocked")
        self.assertEqual(task.block_kind, "needs_input")
        self.assertEqual(duplicate_id, task_id)
        metadata = json.loads(task.body)
        self.assertEqual(metadata["source"], "telegram")
        self.assertIn("Chat: 42", metadata["details"])

    def test_identical_capture_can_recur_after_prior_candidate_is_archived(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"HERMES_HOME": str(Path(directory) / ".hermes")},
            clear=False,
        ):
            handler = load_handler()
            first_id = handler._capture("Review the new maize figures", {"platform": "telegram", "chat_id": "42"})
            conn = kb.connect(board="inbox")
            try:
                self.assertTrue(kb.archive_task(conn, first_id))
            finally:
                conn.close()
            second_id = handler._capture("Review the new maize figures", {"platform": "telegram", "chat_id": "42"})

        self.assertNotEqual(second_id, first_id)

    def test_capture_records_slack_and_email_sources(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"HERMES_HOME": str(Path(directory) / ".hermes")},
            clear=False,
        ):
            handler = load_handler()
            captured = {}
            for platform in ("slack", "email"):
                task_id = handler._capture(
                    f"Follow up from {platform}",
                    {"platform": platform, "chat_id": platform},
                )
                conn = kb.connect(board="inbox")
                try:
                    captured[platform] = json.loads(kb.get_task(conn, task_id).body)["source"]
                finally:
                    conn.close()

        self.assertEqual(captured, {"slack": "slack", "email": "email"})


if __name__ == "__main__":
    unittest.main()
