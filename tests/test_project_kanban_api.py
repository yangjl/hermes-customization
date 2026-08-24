from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_cli import kanban_db as kb


PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "project-kanban" / "dashboard" / "plugin_api.py"


def load_plugin():
    spec = importlib.util.spec_from_file_location("project_kanban_plugin_api_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProjectKanbanApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / ".hermes"
        self.home.mkdir()
        self.vault = self.root / "todo-list"
        (self.vault / "Projects").mkdir(parents=True)
        self.env = patch.dict(
            os.environ,
            {"HERMES_HOME": str(self.home), "TODO_VAULT": str(self.vault)},
            clear=False,
        )
        self.home_patch = patch.object(Path, "home", return_value=self.root)
        self.env.start()
        self.home_patch.start()

        kb.create_board("todos", name="Office Desktop")
        kb.init_db(board="todos")
        conn = kb.connect(board="todos")
        try:
            ready_id = kb.create_task(
                conn,
                title="Review GWAS figures",
                tenant="main-research",
                created_by="user",
                board="todos",
            )
            waiting_id = kb.create_task(
                conn,
                title="Wait for sequencing quote",
                tenant="systems-admin",
                created_by="user",
                board="todos",
            )
            with kb.write_txn(conn):
                conn.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (ready_id,))
                conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = ?", (waiting_id,))
        finally:
            conn.close()

        (self.vault / "Projects" / "research.md").write_text(
            "---\nproject: research\nknowledge_status: active\nproject_category: main-research\n---\n# Research\n",
            encoding="utf-8",
        )
        (self.vault / "Projects" / "student.md").write_text(
            "---\nproject: student\nknowledge_status: active\nproject_category: student-projects\n---\n# Student\n",
            encoding="utf-8",
        )
        (self.vault / "Projects" / "uncategorized.md").write_text(
            "---\nproject: uncategorized\nknowledge_status: active\n---\n# Needs category\n",
            encoding="utf-8",
        )
        (self.vault / "Projects" / "paused.md").write_text(
            "---\nknowledge_status: paused\nproject_category: systems-admin\n---\n# Paused\n",
            encoding="utf-8",
        )
        duplicate = self.vault / "Projects" / "Generated" / "research.md"
        duplicate.parent.mkdir()
        duplicate.write_text(
            "---\nproject: research\nknowledge_status: active\n---\n# Generated research record\n",
            encoding="utf-8",
        )

        module = load_plugin()
        self.module = module
        app = FastAPI()
        app.include_router(module.router, prefix="/api/plugins/project-kanban")
        self.client = TestClient(app)

    def tearDown(self):
        self.home_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def test_snapshot_maps_native_board_and_obsidian_counts(self):
        response = self.client.get("/api/plugins/project-kanban/snapshot")

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["machine"], {"board": "todos", "name": "Office Desktop"})
        self.assertEqual(
            data["projects"],
            {
                "total_active": 3,
                "categories": {
                    "main-research": 1,
                    "student-projects": 1,
                    "systems-admin": 0,
                },
                "needs_category": 1,
            },
        )
        self.assertEqual([task["title"] for task in data["lanes"]["next"]], ["Review GWAS figures"])
        self.assertEqual([task["title"] for task in data["lanes"]["waiting"]], ["Wait for sequencing quote"])
        self.assertEqual(data["lanes"]["doing"], [])
        self.assertEqual(data["lanes"]["review"], [])
        self.assertFalse(data["inbox"]["available"])
        self.assertEqual(data["inbox"]["stages"], {})
        self.assertIn("gateway-local", data["inbox"]["reason"])

    def test_create_and_move_task_uses_non_dispatchable_human_workflow_metadata(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={
                "title": "Draft maize grant aims",
                "category": "main-research",
                "lane": "next",
            },
        )

        self.assertEqual(created.status_code, 201, created.text)
        task = created.json()
        self.assertEqual(task["status"], "blocked")
        self.assertEqual(task["category"], "main-research")
        self.assertTrue(task["human_managed"])
        self.assertEqual(task["workflow_lane"], "next")

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task['id']}",
            json={"lane": "doing"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["status"], "blocked")
        self.assertEqual(moved.json()["workflow_lane"], "doing")

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        self.assertIn(task["id"], [item["id"] for item in snapshot["lanes"]["doing"]])

    def test_inbox_capture_is_reviewable_before_acceptance(self):
        captured = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={
                "title": "Reply to Maya about draft",
                "source": "email",
                "reason": "Direct request with a deliverable",
                "idempotency_key": "email:maya:42",
            },
        )

        self.assertEqual(captured.status_code, 201, captured.text)
        candidate = captured.json()
        self.assertEqual(candidate["status"], "blocked")
        self.assertEqual(candidate["source"], "email")
        self.assertEqual(candidate["suggested_title"], "Reply to Maya about draft")
        self.assertEqual(candidate["suggested_category"], "student-projects")
        self.assertIn("draft", candidate["suggestion_reason"].lower())
        duplicate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={
                "title": "Reply to Maya about draft",
                "source": "email",
                "reason": "Direct request with a deliverable",
                "idempotency_key": "email:maya:42",
            },
        ).json()
        self.assertEqual(duplicate["id"], candidate["id"])

        accepted = self.client.post(
            f"/api/plugins/project-kanban/inbox/{candidate['id']}/accept",
            json={
                "title": "Review Maya's draft and reply",
                "category": "student-projects",
            },
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        action = accepted.json()["task"]
        self.assertEqual(action["title"], "Review Maya's draft and reply")
        self.assertEqual(action["category"], "student-projects")
        self.assertEqual(action["status"], "blocked")

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        self.assertEqual(snapshot["inbox"]["stages"]["captured"], [])
        self.assertIn(candidate["id"], [item["id"] for item in snapshot["inbox"]["stages"]["accepted"]])
        self.assertIn(action["id"], [item["id"] for item in snapshot["lanes"]["next"]])

        repeated = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={
                "title": "Reply to Maya about draft",
                "source": "email",
                "idempotency_key": "email:maya:42",
            },
        )
        self.assertEqual(repeated.status_code, 201, repeated.text)
        self.assertNotEqual(repeated.json()["id"], candidate["id"])

    def test_dismiss_archives_inbox_candidate(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Ignore newsletter", "source": "email"},
        ).json()

        dismissed = self.client.delete(f"/api/plugins/project-kanban/inbox/{candidate['id']}")

        self.assertEqual(dismissed.status_code, 200, dismissed.text)
        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        self.assertEqual(snapshot["inbox"]["stages"]["captured"], [])

    def test_only_local_todos_board_is_authorized(self):
        kb.create_board("private", name="Private")
        kb.init_db(board="private")

        self.assertEqual(
            self.client.get("/api/plugins/project-kanban/snapshot?board=private").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/plugins/project-kanban/tasks?board=private",
                json={"title": "Do not write here", "category": "systems-admin"},
            ).status_code,
            403,
        )

    def test_native_worker_lifecycle_tasks_are_read_only(self):
        conn = kb.connect(board="todos")
        try:
            task_id = kb.create_task(conn, title="Worker task", board="todos")
            task = kb.claim_task(conn, task_id, claimer="test-worker")
            self.assertIsNotNone(task)
        finally:
            conn.close()

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task_id}",
            json={"lane": "waiting"},
        )
        self.assertEqual(moved.status_code, 409, moved.text)
        conn = kb.connect(board="todos")
        try:
            unchanged = kb.get_task(conn, task_id)
            assert unchanged is not None
            self.assertEqual(unchanged.status, "running")
            self.assertIsNotNone(unchanged.claim_lock)
        finally:
            conn.close()

    def test_human_lane_move_preserves_parent_dependencies(self):
        conn = kb.connect(board="todos")
        try:
            parent_id = kb.create_task(conn, title="Parent", board="todos")
        finally:
            conn.close()
        child = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Child", "category": "main-research"},
        ).json()
        conn = kb.connect(board="todos")
        try:
            kb.link_tasks(conn, parent_id, child["id"])
        finally:
            conn.close()

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{child['id']}",
            json={"lane": "review"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        conn = kb.connect(board="todos")
        try:
            link = conn.execute(
                "SELECT 1 FROM task_links WHERE parent_id = ? AND child_id = ?",
                (parent_id, child["id"]),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(link)

    def test_dismiss_wins_before_accept_without_creating_destination_task(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Race candidate", "source": "manual"},
        ).json()
        dismissed = self.client.delete(f"/api/plugins/project-kanban/inbox/{candidate['id']}")
        self.assertEqual(dismissed.status_code, 200, dismissed.text)

        accepted = self.client.post(
            f"/api/plugins/project-kanban/inbox/{candidate['id']}/accept",
            json={"title": "Must not exist", "category": "systems-admin"},
        )
        self.assertIn(accepted.status_code, {404, 409})
        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        self.assertNotIn(
            "Must not exist",
            [task["title"] for lane in snapshot["lanes"].values() for task in lane],
        )

    def test_accept_holds_candidate_lock_against_concurrent_dismiss(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Concurrent candidate", "source": "manual"},
        ).json()
        target_started = threading.Event()
        release_target = threading.Event()
        original_create = self.module.kb.create_task

        def delayed_create(conn, **kwargs):
            if kwargs.get("board") == "todos" and kwargs.get("created_by") == "project-kanban":
                target_started.set()
                self.assertTrue(release_target.wait(timeout=5))
            return original_create(conn, **kwargs)

        with patch.object(self.module.kb, "create_task", side_effect=delayed_create):
            with ThreadPoolExecutor(max_workers=2) as pool:
                accepting = pool.submit(
                    self.client.post,
                    f"/api/plugins/project-kanban/inbox/{candidate['id']}/accept",
                    json={"title": "Accepted once", "category": "systems-admin"},
                )
                self.assertTrue(target_started.wait(timeout=5))
                dismissing = pool.submit(
                    self.client.delete,
                    f"/api/plugins/project-kanban/inbox/{candidate['id']}",
                )
                self.assertFalse(dismissing.done())
                release_target.set()
                accepted = accepting.result(timeout=5)
                dismissed = dismissing.result(timeout=5)

        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertIn(dismissed.status_code, {404, 409})

    def test_inbox_read_failure_is_isolated_from_local_board(self):
        kb.create_board("inbox", name="Inbox")
        with patch.object(self.module, "_read_inbox_tasks", side_effect=OSError("offline")):
            response = self.client.get("/api/plugins/project-kanban/snapshot")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["inbox"]["available"])
        self.assertIn("gateway-local", response.json()["inbox"]["reason"])

    def test_inbox_snapshot_exposes_captured_and_legacy_suggested_stages(self):
        captured = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Captured", "source": "manual"},
        ).json()
        conn = kb.connect(board="inbox")
        try:
            suggested_id = kb.create_task(conn, title="Legacy suggestion", board="inbox")
        finally:
            conn.close()

        stages = self.client.get("/api/plugins/project-kanban/snapshot").json()["inbox"]["stages"]
        self.assertIn(captured["id"], [task["id"] for task in stages["captured"]])
        self.assertIn(suggested_id, [task["id"] for task in stages["suggested"]])


if __name__ == "__main__":
    unittest.main()
