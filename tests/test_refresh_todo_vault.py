from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh-todo-vault.py"


def load_script():
    spec = importlib.util.spec_from_file_location("refresh_todo_vault_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RefreshTodoVaultTest(unittest.TestCase):
    def test_carry_over_preserves_project_category(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            note = Path(directory) / "project.md"
            note.write_text(
                "---\nknowledge_status: active\nproject_category: main-research\n---\n"
                "# Project\n\n## Kanban tasks\n\n- `t_1` — Review\n",
                encoding="utf-8",
            )
            status, category, tasks = module.carry_over(note)

        self.assertEqual(status, "active")
        self.assertEqual(category, "main-research")
        self.assertIn("t_1", tasks)

    def test_local_refresh_writes_preserved_project_category(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.VAULT = root / "vault"
            module.MACHINE = "test-machine"
            note = module.VAULT / "Projects/test-machine/Local/demo.md"
            note.parent.mkdir(parents=True)
            note.write_text(
                "---\nknowledge_status: active\nproject_category: main-research\n---\n# Demo\n",
                encoding="utf-8",
            )
            module.local_notes(
                "Local",
                [
                    {
                        "name": "demo",
                        "relative_path": "demo",
                        "path": str(root / "demo"),
                        "version_control": "none",
                        "activity_date": "2026-08-24",
                    }
                ],
                root,
            )
            refreshed = note.read_text(encoding="utf-8")

        self.assertIn("knowledge_status: active", refreshed)
        self.assertIn("project_category: main-research", refreshed)

    def test_github_activity_is_a_reviewable_inbox_capture(self):
        module = load_script()
        module.VAULT = Path("/tmp/test-todo-vault")
        repo = {
            "owner": "jyanglab",
            "name": "maize",
            "pushed_at": "2026-08-24T12:00:00Z",
            "html_url": "https://github.com/jyanglab/maize",
        }
        with patch.object(module.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"id":"t_1"}'
            task_id = module.create_card(repo, module.VAULT / "Projects/project.md")

        self.assertEqual(task_id, "t_1")
        command = run.call_args.args[0]
        self.assertEqual(command[3], "inbox")
        self.assertNotIn("--triage", command)
        self.assertEqual(command[command.index("--initial-status") + 1], "blocked")
        self.assertEqual(command[command.index("--max-retries") + 1], "0")
        body = command[command.index("--body") + 1]
        self.assertEqual(__import__("json").loads(body)["source"], "github")

    def test_legacy_todo_board_env_remains_compatible(self):
        with patch.dict(
            os.environ,
            {"TODO_BOARD": "legacy-review", "TODO_INBOX_BOARD": ""},
            clear=False,
        ):
            module = load_script()

        self.assertEqual(module.BOARD, "legacy-review")


if __name__ == "__main__":
    unittest.main()
