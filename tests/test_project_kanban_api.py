from __future__ import annotations

import importlib.util
import datetime
import json
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
        kb.create_board("inbox", name="Inbox")
        kb.init_db(board="inbox")
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
            "---\nproject_id: research\nknowledge_status: active\n"
            "project_category: main-research\ngithub_repo: jyanglab/research\n---\n"
            "# Research\n\n## Goal\nShip the study.\n\n"
            "## Next action\nReview GWAS figures.\n\n## Blocker\nNone.\n",
            encoding="utf-8",
        )
        (self.vault / "Projects" / "student.md").write_text(
            "---\nproject_id: student\nknowledge_status: active\n"
            "project_category: student-projects\n---\n# Student\n\n"
            "## Goal\nComplete the thesis.\n\n## Next action\nReview chapter.\n\n"
            "## Blocker\nNone.\n",
            encoding="utf-8",
        )
        (self.vault / "Projects" / "uncategorized.md").write_text(
            "---\nproject_id: uncategorized\nknowledge_status: active\n---\n"
            "# Needs category\n\n## Goal\nFix metadata.\n\n## Next action\nChoose category.\n",
            encoding="utf-8",
        )
        (self.vault / "Projects" / "paused.md").write_text(
            "---\nknowledge_status: paused\nproject_category: systems-admin\n---\n# Paused\n",
            encoding="utf-8",
        )
        duplicate = self.vault / "Projects" / "Generated" / "device-copy.md"
        duplicate.parent.mkdir()
        duplicate.write_text(
            "---\nproject: device-copy\nknowledge_status: active\n"
            "machine: MacLaptop-new\n---\n# Generated device record\n",
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

    def test_snapshot_maps_native_board_and_canonical_obsidian_projects(self):
        response = self.client.get("/api/plugins/project-kanban/snapshot")

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["machine"], {"board": "todos", "name": "Office Desktop"})
        self.assertEqual(data["projects"]["total_active"], 2)
        self.assertEqual(data["projects"]["categories"], {
            "main-research": 1,
            "student-projects": 1,
            "systems-admin": 0,
        })
        self.assertEqual([item["project_id"] for item in data["projects"]["items"]], ["research", "student"])
        research = data["projects"]["items"][0]
        self.assertEqual(research["goal"], "Ship the study.")
        self.assertEqual(research["next_action"], "Review GWAS figures.")
        self.assertEqual(research["blocker"], "None.")
        self.assertEqual(research["github_repo"], "jyanglab/research")
        self.assertEqual(research["note"], "Projects/research.md")
        self.assertTrue(any("uncategorized.md" in warning for warning in data["projects"]["warnings"]))
        self.assertFalse(any("device-copy" in item["project_id"] for item in data["projects"]["items"]))
        self.assertEqual([task["title"] for task in data["lanes"]["next"]], ["Review GWAS figures"])
        self.assertEqual([task["title"] for task in data["lanes"]["waiting"]], ["Wait for sequencing quote"])
        self.assertEqual(data["lanes"]["doing"], [])
        self.assertEqual(data["lanes"]["review"], [])
        self.assertTrue(data["inbox"]["available"])
        self.assertEqual(data["inbox"]["stages"], {
            "captured": [],
            "suggested": [],
            "accepted": [],
        })

    def test_snapshot_moves_unlinked_task_to_legacy(self):
        conn = kb.connect(board="todos")
        try:
            task_id = kb.create_task(
                conn,
                title="Review uncategorized vault project",
                tenant="unsorted",
                created_by="vault-hydrate",
                board="todos",
            )
            with kb.write_txn(conn):
                conn.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (task_id,))
        finally:
            conn.close()

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        task = next(item for item in snapshot["lanes"]["next"] if item["id"] == task_id)

        self.assertEqual(task["category"], "legacy")
        self.assertEqual(task["reconciliation"], "unlinked")

    def test_snapshot_derives_linked_action_category_from_active_project(self):
        conn = kb.connect(board="todos")
        try:
            task_id = kb.create_task(
                conn,
                title="Review student chapter",
                body=self.module._human_task_body(
                    "",
                    "next",
                    project_id="student",
                ),
                tenant="student-projects",
                created_by="project-kanban",
                initial_status="blocked",
                board="todos",
            )
        finally:
            conn.close()

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        task = next(item for item in snapshot["lanes"]["next"] if item["id"] == task_id)

        self.assertEqual(task["category"], "student-projects")
        self.assertEqual(task["project"]["project_id"], "student")
        self.assertEqual(task["reconciliation"], "linked")

    def test_snapshot_moves_unavailable_and_mismatched_project_links_to_legacy(self):
        (self.vault / "Projects" / "paused.md").write_text(
            "---\nproject_id: paused\nknowledge_status: paused\n"
            "project_category: systems-admin\n---\n# Paused\n",
            encoding="utf-8",
        )
        cases = (
            ("Inactive project", "paused", "systems-admin", "unavailable-project"),
            ("Missing project", "does-not-exist", "main-research", "unavailable-project"),
            ("Mismatched project", "research", "student-projects", "category-mismatch"),
        )
        task_ids = {}
        conn = kb.connect(board="todos")
        try:
            for title, project_id, tenant, _ in cases:
                task_ids[title] = kb.create_task(
                    conn,
                    title=title,
                    body=self.module._human_task_body("", "next", project_id=project_id),
                    tenant=tenant,
                    created_by="project-kanban",
                    initial_status="blocked",
                    board="todos",
                )
        finally:
            conn.close()

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        visible = {
            item["id"]: item
            for lane in snapshot["lanes"].values()
            for item in lane
        }

        for title, _, _, reconciliation in cases:
            with self.subTest(title=title):
                task = visible[task_ids[title]]
                self.assertEqual(task["category"], "legacy")
                self.assertEqual(task["reconciliation"], reconciliation)

    def test_malformed_canonical_note_is_warned_excluded_and_not_actionable(self):
        (self.vault / "Projects" / "malformed.md").write_text(
            "---\nproject_id: malformed\nknowledge_status: active\n"
            "project_category: systems-admin\n---\n# Malformed\n\n"
            "## Goal\nTest.\n\n## Next action\nReview.\n",
            encoding="utf-8",
        )

        projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Must not attach", "project_id": "malformed"},
        )

        self.assertNotIn("malformed", [item["project_id"] for item in projects["items"]])
        self.assertTrue(any("malformed.md: missing Blocker heading" in warning for warning in projects["warnings"]))
        self.assertEqual(created.status_code, 422, created.text)

    def test_duplicate_and_invalid_project_ids_are_excluded_with_warnings(self):
        for name, project_id in (("duplicate.md", "research"), ("invalid.md", "Bad ID")):
            (self.vault / "Projects" / name).write_text(
                "---\n"
                f"project_id: {project_id}\n"
                "knowledge_status: active\nproject_category: systems-admin\n---\n"
                f"# {name}\n\n## Goal\nTest.\n\n## Next action\nReview.\n\n"
                "## Blocker\nNone.\n",
                encoding="utf-8",
            )

        projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]

        self.assertNotIn("research", [item["project_id"] for item in projects["items"]])
        self.assertNotIn("Bad ID", [item["project_id"] for item in projects["items"]])
        self.assertTrue(any("duplicate project_id" in warning for warning in projects["warnings"]))
        self.assertTrue(any("invalid project_id" in warning for warning in projects["warnings"]))

    def test_duplicate_id_is_excluded_even_when_one_claimant_is_malformed(self):
        """Ambiguity must be resolved before category/heading validation.

        A malformed duplicate previously failed validation first, so the valid
        note survived and the ambiguous ID stayed actionable.
        """
        (self.vault / "Projects" / "malformed-duplicate.md").write_text(
            "---\nproject_id: research\nknowledge_status: active\n"
            "project_category: not-a-category\n---\n"
            "# Malformed duplicate\n\nNo headings here.\n",
            encoding="utf-8",
        )

        projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]

        self.assertNotIn("research", [item["project_id"] for item in projects["items"]])
        self.assertTrue(
            any("duplicate project_id" in warning for warning in projects["warnings"]),
            projects["warnings"],
        )

    def test_ambiguous_project_id_cannot_be_used_to_create_an_action(self):
        (self.vault / "Projects" / "malformed-duplicate.md").write_text(
            "---\nproject_id: research\nknowledge_status: active\n"
            "project_category: not-a-category\n---\n"
            "# Malformed duplicate\n\nNo headings here.\n",
            encoding="utf-8",
        )

        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Ambiguous", "project_id": "research", "lane": "next"},
        )

        self.assertEqual(created.status_code, 422, created.text)

    def test_duplicate_headings_missing_on_both_claimants_still_excludes_the_id(self):
        (self.vault / "Projects" / "twin-a.md").write_text(
            "---\nproject_id: twin\nknowledge_status: active\n"
            "project_category: systems-admin\n---\n# Twin A\n",
            encoding="utf-8",
        )
        (self.vault / "Projects" / "twin-b.md").write_text(
            "---\nproject_id: twin\nknowledge_status: active\n"
            "project_category: systems-admin\n---\n# Twin B\n",
            encoding="utf-8",
        )

        projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]

        self.assertNotIn("twin", [item["project_id"] for item in projects["items"]])
        self.assertTrue(
            any("duplicate project_id" in warning for warning in projects["warnings"]),
            projects["warnings"],
        )

    def test_heading_presence_and_extraction_agree_on_spacing(self):
        """A note whose heading passes the presence gate must also yield its text."""
        (self.vault / "Projects" / "spaced.md").write_text(
            "---\nproject_id: spaced\nknowledge_status: active\n"
            "project_category: systems-admin\n---\n# Spaced\n\n"
            "##  Goal\nShip it.\n\n##  Next action\nDo the thing.\n\n"
            "##  Blocker\nNone.\n",
            encoding="utf-8",
        )

        projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]
        item = next(
            (i for i in projects["items"] if i["project_id"] == "spaced"), None
        )

        self.assertIsNotNone(item, projects["warnings"])
        self.assertEqual(item["goal"], "Ship it.")
        self.assertEqual(item["next_action"], "Do the thing.")
        self.assertEqual(item["blocker"], "None.")

    def test_tab_separated_headings_do_not_swallow_following_sections(self):
        """The section terminator must match the same headings as the start."""
        (self.vault / "Projects" / "tabbed.md").write_text(
            "---\nproject_id: tabbed\nknowledge_status: active\n"
            "project_category: systems-admin\n---\n# Tabbed\n\n"
            "##\tGoal\nShip it.\n\n##\tNext action\nDo the thing.\n\n"
            "##\tBlocker\nNone.\n",
            encoding="utf-8",
        )

        projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]
        item = next(
            (i for i in projects["items"] if i["project_id"] == "tabbed"), None
        )

        self.assertIsNotNone(item, projects["warnings"])
        self.assertEqual(item["goal"], "Ship it.")
        self.assertEqual(item["next_action"], "Do the thing.")
        self.assertEqual(item["blocker"], "None.")

    def test_snapshot_joins_newest_device_observation_without_overwriting_project_truth(self):
        observations = self.vault / "Observations" / "devices"
        observations.mkdir(parents=True)
        (observations / "old.json").write_text(json.dumps({
            "schema_version": 1,
            "device": "Office Desktop",
            "observed_at": "2026-08-10T08:00:00-05:00",
            "projects": [{
                "project_id": "research",
                "github_repo": "jyanglab/research",
                "github_pushed_at": "2026-08-10T11:00:00Z",
                "activity_at": "2026-08-10T10:00:00Z",
                "head": "old",
                "dirty_count": 0,
                "ahead": 0,
                "behind": 0,
            }],
            "unmatched": [],
        }), encoding="utf-8")
        (observations / "new.json").write_text(json.dumps({
            "schema_version": 1,
            "device": "MacLaptop-new",
            "observed_at": "2026-08-24T08:00:00-05:00",
            "projects": [{
                "project_id": "research",
                "github_repo": "jyanglab/research",
                "github_pushed_at": "2026-08-23T23:00:00Z",
                "activity_at": "2026-08-23T22:00:00Z",
                "head": "new",
                "dirty_count": 3,
                "ahead": 1,
                "behind": 0,
                "status": "blocked",
                "next_action": "Must not overwrite Obsidian",
            }],
            "unmatched": [{"source": "example/unmanaged", "kind": "github"}],
        }), encoding="utf-8")
        (observations / "broken.json").write_text("{broken", encoding="utf-8")

        with patch.object(
            self.module,
            "_now",
            return_value=datetime.datetime(2026, 8, 24, 14, 0, tzinfo=datetime.timezone.utc),
        ):
            projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]

        research = next(item for item in projects["items"] if item["project_id"] == "research")
        self.assertEqual(research["status"], "active")
        self.assertEqual(research["next_action"], "Review GWAS figures.")
        self.assertEqual(research["github"], {
            "repo": "jyanglab/research",
            "pushed_at": "2026-08-23T23:00:00Z",
        })
        self.assertEqual(research["observation"]["device"], "MacLaptop-new")
        self.assertEqual(research["observation"]["observed_at"], "2026-08-24T08:00:00-05:00")
        self.assertEqual(research["observation"]["activity_at"], "2026-08-23T22:00:00Z")
        self.assertEqual(research["observation"]["dirty_count"], 3)
        self.assertEqual(research["observation"]["ahead"], 1)
        self.assertFalse(research["observation"]["stale"])
        self.assertEqual(projects["unmatched"][0]["source"], "example/unmanaged")
        self.assertEqual(projects["unmatched"][0]["device"], "MacLaptop-new")
        self.assertTrue(any("broken.json" in warning for warning in projects["warnings"]))

    def test_malformed_observation_counts_warn_instead_of_breaking_snapshot(self):
        observations = self.vault / "Observations" / "devices"
        observations.mkdir(parents=True)
        (observations / "bad-count.json").write_text(
            json.dumps({
                "schema_version": 1,
                "device": "MacLaptop-new",
                "observed_at": "2026-08-24T12:00:00Z",
                "projects": [{
                    "project_id": "research",
                    "dirty_count": "many",
                    "ahead": 0,
                    "behind": 0,
                }],
                "unmatched": [],
            }),
            encoding="utf-8",
        )

        response = self.client.get("/api/plugins/project-kanban/snapshot")

        self.assertEqual(response.status_code, 200)
        projects = response.json()["projects"]
        research = next(item for item in projects["items"] if item["project_id"] == "research")
        self.assertIsNone(research["observation"])
        self.assertTrue(any("invalid evidence counts" in warning for warning in projects["warnings"]))

    def test_non_list_observation_collections_warn_instead_of_breaking_snapshot(self):
        observations = self.vault / "Observations" / "devices"
        observations.mkdir(parents=True)
        (observations / "bad-shape.json").write_text(
            json.dumps({
                "schema_version": 1,
                "device": "MacLaptop-new",
                "observed_at": "2026-08-24T12:00:00Z",
                "projects": None,
                "unmatched": 42,
            }),
            encoding="utf-8",
        )

        response = self.client.get("/api/plugins/project-kanban/snapshot")

        self.assertEqual(response.status_code, 200)
        projects = response.json()["projects"]
        self.assertEqual(projects["total_active"], 2)
        self.assertTrue(any("projects must be a list" in warning for warning in projects["warnings"]))
        self.assertTrue(any("unmatched must be a list" in warning for warning in projects["warnings"]))

    def test_missing_canonical_headings_are_reported_individually(self):
        (self.vault / "Projects" / "missing-headings.md").write_text(
            "---\nproject_id: missing-headings\nknowledge_status: active\n"
            "project_category: systems-admin\n---\n# Missing headings\n",
            encoding="utf-8",
        )

        projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]

        warnings = "\n".join(projects["warnings"])
        for heading in ("Goal", "Next action", "Blocker"):
            self.assertIn(f"missing-headings.md: missing {heading} heading", warnings)

    def test_observation_is_stale_after_seven_days(self):
        observations = self.vault / "Observations" / "devices"
        observations.mkdir(parents=True)
        (observations / "old.json").write_text(json.dumps({
            "schema_version": 1,
            "device": "Office Desktop",
            "observed_at": "2026-08-16T08:00:00-05:00",
            "projects": [{"project_id": "student"}],
            "unmatched": [],
        }), encoding="utf-8")

        with patch.object(
            self.module,
            "_now",
            return_value=datetime.datetime(2026, 8, 24, 14, 0, tzinfo=datetime.timezone.utc),
        ):
            projects = self.client.get("/api/plugins/project-kanban/snapshot").json()["projects"]

        student = next(item for item in projects["items"] if item["project_id"] == "student")
        self.assertTrue(student["observation"]["stale"])

    def test_task_view_exposes_obsidian_and_github_links_from_details(self):
        details = "\n".join([
            "jyanglab/GreenDB was pushed on 2026-08-22.",
            "",
            "GitHub: https://github.com/jyanglab/GreenDB",
            "Note: Projects/GitHub/jyanglab--GreenDB.md",
        ])

        self.assertEqual(
            self.module._links(details),
            {
                "github": "https://github.com/jyanglab/GreenDB",
                "obsidian": "Projects/GitHub/jyanglab--GreenDB.md",
            },
        )

    def test_task_view_reports_empty_links_when_details_carry_none(self):
        self.assertEqual(self.module._links(""), {"obsidian": "", "github": ""})
        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        self.assertEqual(
            snapshot["lanes"]["next"][0]["links"], {"obsidian": "", "github": ""}
        )

    def test_create_and_move_task_uses_non_dispatchable_human_workflow_metadata(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={
                "title": "Draft maize grant aims",
                "project_id": "research",
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

        unlinked = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Do not create an unlinked action"},
        )
        self.assertEqual(unlinked.status_code, 422)

    def test_create_task_links_canonical_project_and_derives_its_category(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={
                "title": "Approve validation cohort",
                "project_id": "research",
                "category": "student-projects",
                "lane": "next",
            },
        )

        self.assertEqual(created.status_code, 201, created.text)
        task = created.json()
        self.assertEqual(task["project_id"], "research")
        self.assertEqual(task["category"], "main-research")
        self.assertEqual(task["project"]["title"], "Research")
        self.assertEqual(task["project"]["goal"], "Ship the study.")
        self.assertEqual(task["project"]["next_action"], "Review GWAS figures.")
        self.assertEqual(task["project"]["github"]["repo"], "jyanglab/research")

        unknown = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Do not create", "project_id": "missing-project"},
        )
        self.assertEqual(unknown.status_code, 422)

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
                "project_id": "student",
            },
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        action = accepted.json()["task"]
        self.assertEqual(action["title"], "Review Maya's draft and reply")
        self.assertEqual(action["category"], "student-projects")
        self.assertEqual(action["project_id"], "student")
        self.assertEqual(action["project"]["title"], "Student")
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

    def test_title_only_inbox_edit_preserves_legacy_plain_text_body(self):
        original_body = "Legacy notes that must survive a title correction."
        conn = kb.connect(board="inbox")
        try:
            task_id = kb.create_task(
                conn,
                title="Original title",
                body=original_body,
                created_by="user",
                initial_status="blocked",
                board="inbox",
            )
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET status = 'ready', block_kind = NULL WHERE id = ?",
                    (task_id,),
                )
        finally:
            conn.close()

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{task_id}",
            json={"title": "Corrected title"},
        )

        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["body"], original_body)
        conn = kb.connect(board="inbox")
        try:
            stored = kb.get_task(conn, task_id)
            assert stored is not None
            self.assertEqual(stored.body, original_body)
        finally:
            conn.close()

    def test_project_assignment_migrates_legacy_body_without_losing_notes(self):
        original_body = "Legacy notes that must survive project assignment."
        conn = kb.connect(board="inbox")
        try:
            task_id = kb.create_task(
                conn,
                title="Legacy candidate",
                body=original_body,
                created_by="user",
                initial_status="blocked",
                board="inbox",
            )
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET status = 'ready', block_kind = NULL WHERE id = ?",
                    (task_id,),
                )
        finally:
            conn.close()

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{task_id}",
            json={"project_id": "research"},
        )

        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["body"], original_body)
        self.assertEqual(edited.json()["project_id"], "research")
        conn = kb.connect(board="inbox")
        try:
            stored = kb.get_task(conn, task_id)
            assert stored is not None
            metadata = json.loads(stored.body or "")
            self.assertEqual(metadata["details"], original_body)
            self.assertEqual(metadata["project_kanban"]["project_id"], "research")
        finally:
            conn.close()

    def test_inbox_capture_does_not_create_office_authority(self):
        with patch.object(self.module.kb, "board_exists", return_value=False), patch.object(
            self.module.kb, "create_board"
        ) as create_board:
            response = self.client.post(
                "/api/plugins/project-kanban/inbox/capture",
                json={"title": "Must stay on the office host", "source": "manual"},
            )

        self.assertEqual(response.status_code, 404, response.text)
        create_board.assert_not_called()

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
                json={"title": "Do not write here", "project_id": "research"},
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

    def test_human_managed_lane_move_succeeds_regardless_of_native_status(self):
        # PK-001 regression: a human-managed card's lane must be movable
        # through this endpoint independent of native worker-lifecycle
        # status. This synthetic case keeps human_managed true and lane
        # "doing", while native status is "ready" (not "blocked"). Before
        # the fix this PATCH returned 409 "Native worker lifecycle tasks are
        # read-only".
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Launch example research portal", "project_id": "research", "lane": "doing"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        task = created.json()
        self.assertTrue(task["human_managed"])

        conn = kb.connect(board="todos")
        try:
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET status = 'ready', block_kind = NULL WHERE id = ?",
                    (task["id"],),
                )
            unchanged = kb.get_task(conn, task["id"])
            assert unchanged is not None
            self.assertEqual(unchanged.status, "ready")
        finally:
            conn.close()

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task['id']}",
            json={"lane": "review"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["workflow_lane"], "review")

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        self.assertIn(task["id"], [item["id"] for item in snapshot["lanes"]["review"]])

    def test_pk003_externally_created_human_card_at_ready_status_moves(self):
        # PK-003 investigation mirrors an externally created human-managed
        # card. Unlike the case above, it was not created through this plugin,
        # so it was never parked to native "blocked" and sits at native
        # "ready" with no claim. The synthetic project_id is intentionally not
        # resolvable here; reconciliation must not gate the move. This PATCH
        # must return 200 on the fixed gate; the
        # pre-PK-001-fix gate (native status must be 'blocked') returns the
        # reported 409 "Native worker lifecycle tasks are read-only".
        body = json.dumps({
            "details": (
                "Add a chat feature to an example research portal. Scope and "
                "design are not yet defined and require a plan before "
                "implementation starts. Project note: "
                "Projects/Systems/example-research-portal.md"
            ),
            "project_kanban": {
                "human_managed": True,
                "lane": "next",
                "project_id": "systems-example-portal",
            },
        })
        conn = kb.connect(board="todos")
        try:
            task_id = kb.create_task(
                conn,
                title="Build chat feature for example research portal",
                body=body,
                tenant="systems-admin",
                created_by="user",
                board="todos",
            )
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET status = 'ready', block_kind = NULL, "
                    "claim_lock = NULL, worker_pid = NULL WHERE id = ?",
                    (task_id,),
                )
        finally:
            conn.close()

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task_id}",
            json={"lane": "review"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["workflow_lane"], "review")

    def test_pk003_dispatcher_claim_race_reclaims_stale_claim_and_moves(self):
        # PK-003, fixed: a human-managed card sitting at native "ready" with
        # no active claim moves fine (see
        # test_pk003_externally_created_human_card_at_ready_status_moves).
        # But nothing in hermes_cli.kanban_db's claim path (kb.claim_task,
        # and the dispatcher's ready-loop that calls it) knows about the
        # project_kanban.human_managed body convention -- it is a plugin-side
        # JSON convention layered entirely inside the `body` column, which
        # the native claim/dispatch machinery never inspects. So the native
        # dispatcher (or a worker/terminal pulling its lane) can claim a
        # human-managed ready card the instant before a human drags it,
        # setting claim_lock/worker_pid non-null.
        #
        # Before the fix, _move_human_lane's guard treated that claim as
        # sacrosanct and 409'd the human's own move -- indistinguishable from
        # the PK-001 symptom, but with a different precondition (the original
        # bug and repro are documented in the issue log). After the fix, a
        # stale/racing claim on a human_managed card is cleared as part of
        # the same move transaction and the move proceeds normally.
        body = json.dumps({
            "details": "Build AI-chat feature for jyanglab.com",
            "project_kanban": {
                "human_managed": True,
                "lane": "next",
                "project_id": "research",
            },
        })
        conn = kb.connect(board="todos")
        try:
            task_id = kb.create_task(
                conn,
                title="Build AI-chat feature for jyanglab.com",
                body=body,
                tenant="main-research",
                created_by="user",
                board="todos",
            )
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET status = 'ready', block_kind = NULL, "
                    "claim_lock = NULL, worker_pid = NULL WHERE id = ?",
                    (task_id,),
                )
            # Simulate the native dispatcher (or a worker/terminal claiming
            # its assigned lane) racing the human: it has no idea this card
            # is human_managed, because that flag lives only in the body
            # JSON, which claim_task never reads.
            claimed = kb.claim_task(conn, task_id, claimer="test-dispatcher")
            self.assertIsNotNone(claimed, "dispatcher claim should succeed on a bare 'ready' row")
            self.assertEqual(claimed.status, "running")
            self.assertIsNotNone(claimed.claim_lock)
        finally:
            conn.close()

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task_id}",
            json={"lane": "doing"},
        )
        # Fixed behavior: the stale/racing native claim is reclaimed for the
        # human move instead of 409ing.
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["workflow_lane"], "doing")

        conn = kb.connect(board="todos")
        try:
            after = kb.get_task(conn, task_id)
        finally:
            conn.close()
        assert after is not None
        self.assertIsNone(after.claim_lock)
        self.assertIsNone(after.worker_pid)

    def test_non_human_managed_task_at_ready_status_remains_read_only(self):
        # A native/autonomous task (no project_kanban.human_managed metadata)
        # must still be rejected by this endpoint, even at a non-blocked
        # native status and with no active claim — native worker lifecycle
        # semantics are unchanged by the PK-001 fix.
        conn = kb.connect(board="todos")
        try:
            task_id = kb.create_task(conn, title="Native task", board="todos")
            with kb.write_txn(conn):
                conn.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (task_id,))
        finally:
            conn.close()

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task_id}",
            json={"lane": "doing"},
        )
        self.assertEqual(moved.status_code, 409, moved.text)
        self.assertIn("read-only", moved.json()["detail"])

    def test_human_lane_move_preserves_parent_dependencies(self):
        conn = kb.connect(board="todos")
        try:
            parent_id = kb.create_task(conn, title="Parent", board="todos")
        finally:
            conn.close()
        child = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Child", "project_id": "research"},
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
            json={"title": "Must not exist", "project_id": "research"},
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
                    json={"title": "Accepted once", "project_id": "research"},
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

    def _hidden_blocked_inbox_task(self, *, locked: bool = False) -> str:
        """A blocked Inbox task that is NOT a review candidate, so it is never listed."""
        conn = kb.connect(board="inbox")
        try:
            task_id = kb.create_task(
                conn,
                title="Native worker task",
                body=json.dumps({"details": "internal"}),
                board="inbox",
            )
            with kb.write_txn(conn):
                if locked:
                    conn.execute(
                        "UPDATE tasks SET status = 'blocked', claim_lock = 'worker-1', "
                        "worker_pid = 4242 WHERE id = ?",
                        (task_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE tasks SET status = 'blocked' WHERE id = ?", (task_id,)
                    )
        finally:
            conn.close()
        return task_id

    def test_hidden_blocked_task_is_not_listed_as_a_candidate(self):
        task_id = self._hidden_blocked_inbox_task()

        stages = self.client.get("/api/plugins/project-kanban/snapshot").json()["inbox"]["stages"]

        listed = {task["id"] for stage in stages.values() for task in stage}
        self.assertNotIn(task_id, listed)

    def test_hidden_blocked_task_cannot_be_accepted(self):
        task_id = self._hidden_blocked_inbox_task()

        response = self.client.post(
            f"/api/plugins/project-kanban/inbox/{task_id}/accept",
            json={"title": "Sneaky", "project_id": "research"},
        )

        self.assertEqual(response.status_code, 409, response.text)
        conn = kb.connect(board="inbox")
        try:
            task = kb.get_task(conn, task_id)
        finally:
            conn.close()
        self.assertEqual(task.status, "blocked")

    def test_hidden_blocked_task_cannot_be_dismissed(self):
        task_id = self._hidden_blocked_inbox_task()

        response = self.client.delete(f"/api/plugins/project-kanban/inbox/{task_id}")

        self.assertEqual(response.status_code, 409, response.text)
        conn = kb.connect(board="inbox")
        try:
            task = kb.get_task(conn, task_id)
        finally:
            conn.close()
        self.assertEqual(task.status, "blocked")

    def test_dismiss_does_not_clear_worker_locks(self):
        task_id = self._hidden_blocked_inbox_task(locked=True)

        response = self.client.delete(f"/api/plugins/project-kanban/inbox/{task_id}")

        self.assertEqual(response.status_code, 409, response.text)
        conn = kb.connect(board="inbox")
        try:
            row = conn.execute(
                "SELECT status, claim_lock, worker_pid FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["claim_lock"], "worker-1")
        self.assertEqual(row["worker_pid"], 4242)

    def test_dismissing_a_listed_candidate_claimed_mid_flight_preserves_its_lock(self):
        """Pins the SQL compare-and-swap, not just the eligibility gate.

        _candidate_stage re-reads inside the transaction, so it normally
        rejects a claimed task first. To prove the UPDATE itself also refuses
        to touch a claimed row, the eligibility gate is stubbed to admit it —
        simulating a worker that claims the row after the gate has passed.
        """
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Claimed mid-flight", "source": "manual"},
        ).json()
        task_id = candidate["id"]

        conn = kb.connect(board="inbox")
        try:
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET claim_lock = 'worker-9', worker_pid = 777 "
                    "WHERE id = ?",
                    (task_id,),
                )

            with patch.object(self.module, "_candidate_stage", return_value="captured"):
                response = self.client.delete(
                    f"/api/plugins/project-kanban/inbox/{task_id}"
                )

            self.assertEqual(response.status_code, 409, response.text)
            row = conn.execute(
                "SELECT status, claim_lock, worker_pid FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertNotEqual(row["status"], "archived")
        self.assertEqual(row["claim_lock"], "worker-9")
        self.assertEqual(row["worker_pid"], 777)

    def test_worker_claimed_candidate_is_not_listed_in_the_inbox(self):
        """A claimed task belongs to its worker and must vanish from listing."""
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Claimed candidate", "source": "manual"},
        ).json()
        task_id = candidate["id"]

        conn = kb.connect(board="inbox")
        try:
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET claim_lock = 'worker-3', worker_pid = 99 "
                    "WHERE id = ?",
                    (task_id,),
                )
        finally:
            conn.close()

        stages = self.client.get("/api/plugins/project-kanban/snapshot").json()["inbox"]["stages"]

        listed = {task["id"] for stage in stages.values() for task in stage}
        self.assertNotIn(task_id, listed)

    def test_listed_candidate_remains_acceptable_and_dismissible(self):
        acceptable = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Real candidate", "source": "manual"},
        ).json()
        dismissable = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Second candidate", "source": "manual"},
        ).json()

        accepted = self.client.post(
            f"/api/plugins/project-kanban/inbox/{acceptable['id']}/accept",
            json={"title": "Real candidate", "project_id": "research"},
        )
        dismissed = self.client.delete(
            f"/api/plugins/project-kanban/inbox/{dismissable['id']}"
        )

        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(dismissed.status_code, 200, dismissed.text)

    # -- PK-002: PATCH /inbox/{task_id} (independent Save, no accept/dismiss) --

    def test_edit_captured_candidate_saves_title_and_project_visible_in_snapshot(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Reply to Maya", "source": "email"},
        ).json()

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{candidate['id']}",
            json={
                "title": "Reply to Maya about draft figures",
                "project_id": "research",
                "details": "Maya wants feedback before Friday.",
            },
        )

        self.assertEqual(edited.status_code, 200, edited.text)
        body = edited.json()
        self.assertEqual(body["title"], "Reply to Maya about draft figures")
        self.assertEqual(body["project_id"], "research")
        self.assertEqual(body["body"], "Maya wants feedback before Friday.")

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        saved = next(
            item for item in snapshot["inbox"]["stages"]["captured"]
            if item["id"] == candidate["id"]
        )
        self.assertEqual(saved["title"], "Reply to Maya about draft figures")
        self.assertEqual(saved["project_id"], "research")

    def test_edit_succeeds_on_suggested_stage_candidate_native_todo_ready_status(self):
        conn = kb.connect(board="inbox")
        try:
            task_id = kb.create_task(conn, title="Legacy suggestion", board="inbox")
            with kb.write_txn(conn):
                conn.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (task_id,))
        finally:
            conn.close()

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{task_id}",
            json={"title": "Legacy suggestion, revised"},
        )

        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["title"], "Legacy suggestion, revised")
        conn = kb.connect(board="inbox")
        try:
            task = kb.get_task(conn, task_id)
        finally:
            conn.close()
        self.assertEqual(task.status, "ready")

    def test_edit_rejects_claimed_candidate(self):
        task_id = self._hidden_blocked_inbox_task(locked=True)

        response = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{task_id}",
            json={"title": "Sneaky edit"},
        )

        self.assertEqual(response.status_code, 409, response.text)

    def test_edit_rejects_archived_dismissed_candidate(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Ignore newsletter", "source": "email"},
        ).json()
        dismissed = self.client.delete(f"/api/plugins/project-kanban/inbox/{candidate['id']}")
        self.assertEqual(dismissed.status_code, 200, dismissed.text)

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{candidate['id']}",
            json={"title": "Must not save"},
        )

        self.assertEqual(edited.status_code, 409, edited.text)

    def test_edit_rejects_blank_title_after_strip(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Real candidate", "source": "manual"},
        ).json()

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{candidate['id']}",
            json={"title": "   "},
        )

        self.assertEqual(edited.status_code, 422, edited.text)

    def test_edit_rejects_unknown_project_id(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Real candidate", "source": "manual"},
        ).json()

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{candidate['id']}",
            json={"project_id": "does-not-exist"},
        )

        self.assertEqual(edited.status_code, 422, edited.text)

    def test_edit_does_not_change_status_candidate_stage_or_review_candidate(self):
        candidate = self.client.post(
            "/api/plugins/project-kanban/inbox/capture",
            json={"title": "Real candidate", "source": "manual"},
        ).json()

        edited = self.client.patch(
            f"/api/plugins/project-kanban/inbox/{candidate['id']}",
            json={"title": "Real candidate, revised", "details": "More context"},
        )
        self.assertEqual(edited.status_code, 200, edited.text)

        conn = kb.connect(board="inbox")
        try:
            task = kb.get_task(conn, candidate["id"])
        finally:
            conn.close()
        self.assertEqual(task.status, candidate["status"])
        metadata = self.module._metadata(task.body)
        self.assertEqual(metadata.get("candidate_stage"), "captured")
        self.assertIs(metadata.get("review_candidate"), True)
        self.assertEqual(metadata.get("details"), "More context")
        self.assertEqual(task.title, "Real candidate, revised")

    def test_move_task_sets_due_date_and_snapshot_reflects_it(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Draft grant renewal", "project_id": "research", "lane": "next"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        task = created.json()
        self.assertIsNone(task["due_date"])

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task['id']}",
            json={"lane": "doing", "due_date": "2026-09-15"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["due_date"], "2026-09-15")

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        snapshot_task = next(
            item for item in snapshot["lanes"]["doing"] if item["id"] == task["id"]
        )
        self.assertEqual(snapshot_task["due_date"], "2026-09-15")

    def test_move_task_due_date_null_clears_previously_set_value(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Draft grant renewal", "project_id": "research", "lane": "next"},
        )
        task = created.json()
        first = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task['id']}",
            json={"lane": "doing", "due_date": "2026-09-15"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["due_date"], "2026-09-15")

        cleared = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task['id']}",
            json={"lane": "review", "due_date": None},
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["due_date"])

        conn = kb.connect(board="todos")
        try:
            stored = kb.get_task(conn, task["id"])
        finally:
            conn.close()
        metadata = self.module._metadata(stored.body)
        self.assertNotIn("due_date", metadata["project_kanban"])

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        snapshot_task = next(
            item for item in snapshot["lanes"]["review"] if item["id"] == task["id"]
        )
        self.assertIsNone(snapshot_task["due_date"])

    def test_move_task_without_due_date_key_leaves_existing_value_untouched(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Draft grant renewal", "project_id": "research", "lane": "next"},
        )
        task = created.json()
        self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task['id']}",
            json={"lane": "doing", "due_date": "2026-09-15"},
        )

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task['id']}",
            json={"lane": "review"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["due_date"], "2026-09-15")

    def test_move_task_rejects_malformed_due_date_with_422(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Draft grant renewal", "project_id": "research", "lane": "next"},
        )
        task = created.json()

        for bad_value in ("15-09-2026", "2026/09/15", "not-a-date", "2026-13-40", ""):
            response = self.client.patch(
                f"/api/plugins/project-kanban/tasks/{task['id']}",
                json={"lane": "doing", "due_date": bad_value},
            )
            self.assertEqual(response.status_code, 422, f"{bad_value!r}: {response.text}")

        conn = kb.connect(board="todos")
        try:
            stored = kb.get_task(conn, task["id"])
        finally:
            conn.close()
        metadata = self.module._metadata(stored.body)
        self.assertNotIn("due_date", metadata["project_kanban"])
        self.assertEqual(metadata["project_kanban"]["lane"], "next")

    def test_move_task_with_due_date_still_409s_for_native_worker_lifecycle_task(self):
        conn = kb.connect(board="todos")
        try:
            task_id = kb.create_task(conn, title="Worker task", board="todos")
            claimed = kb.claim_task(conn, task_id, claimer="test-worker")
            self.assertIsNotNone(claimed)
        finally:
            conn.close()

        moved = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task_id}",
            json={"lane": "waiting", "due_date": "2026-09-15"},
        )
        self.assertEqual(moved.status_code, 409, moved.text)

        moved_without_due_date = self.client.patch(
            f"/api/plugins/project-kanban/tasks/{task_id}",
            json={"lane": "waiting"},
        )
        self.assertEqual(moved_without_due_date.status_code, 409, moved_without_due_date.text)

        conn = kb.connect(board="todos")
        try:
            unchanged = kb.get_task(conn, task_id)
            self.assertEqual(unchanged.status, "running")
            self.assertIsNotNone(unchanged.claim_lock)
        finally:
            conn.close()

    def test_task_view_due_date_is_none_when_absent(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "No deadline yet", "project_id": "research", "lane": "next"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertIsNone(created.json()["due_date"])

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot").json()
        snapshot_task = next(
            item for item in snapshot["lanes"]["next"] if item["id"] == created.json()["id"]
        )
        self.assertIn("due_date", snapshot_task)
        self.assertIsNone(snapshot_task["due_date"])

    def test_task_view_treats_malformed_stored_due_date_as_absent(self):
        created = self.client.post(
            "/api/plugins/project-kanban/tasks",
            json={"title": "Corrupted deadline", "project_id": "research", "lane": "next"},
        )
        task_id = created.json()["id"]

        conn = kb.connect(board="todos")
        try:
            current = conn.execute(
                "SELECT body FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            metadata = self.module._metadata(current["body"])
            metadata["project_kanban"]["due_date"] = "not-a-real-date"
            with kb.write_txn(conn):
                conn.execute(
                    "UPDATE tasks SET body = ? WHERE id = ?",
                    (json.dumps(metadata), task_id),
                )
        finally:
            conn.close()

        snapshot = self.client.get("/api/plugins/project-kanban/snapshot")
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        snapshot_task = next(
            item for item in snapshot.json()["lanes"]["next"] if item["id"] == task_id
        )
        self.assertIsNone(snapshot_task["due_date"])


if __name__ == "__main__":
    unittest.main()
