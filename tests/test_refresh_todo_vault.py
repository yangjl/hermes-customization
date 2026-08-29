from __future__ import annotations

import datetime
import importlib.util
import json
import os
import subprocess
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
    def test_local_setting_reads_machine_name_without_exposing_other_env_values(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("SECRET=do-not-return\nTODO_MACHINE=MacLaptop-new\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                value = module.local_setting("TODO_MACHINE", env)

        self.assertEqual(value, "MacLaptop-new")

    def test_sync_project_notes_marks_only_recent_immediate_folders_active(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            source = root / "projects"
            recent = source / "Recent Study"
            old = source / "Old Study"
            nested = recent / "nested-repo"
            old.mkdir(parents=True)
            nested.mkdir(parents=True)
            existing = vault / "Projects" / "Desktop" / "Main Research" / "Recent Study.md"
            existing.parent.mkdir(parents=True)
            existing.write_text(
                "---\nproject_id: main-research-recent-study\n"
                "project_category: main-research\nknowledge_status: unreviewed\n"
                "status: unreviewed\n---\n# Recent Study\n\n"
                "## Goal\nKeep this human-authored goal.\n\n"
                "## Next action\nReview results.\n\n## Blocker\nNone.\n",
                encoding="utf-8",
            )
            now = datetime.datetime(2026, 8, 25, 8, tzinfo=datetime.timezone.utc)
            rows = [
                {
                    "name": "nested-repo",
                    "path": str(nested),
                    "version_control": "git",
                    "remote": "git@github.com:jyanglab/recent.git",
                    "last_epoch": int((now - datetime.timedelta(days=10)).timestamp()),
                },
                {
                    "name": "Old Study",
                    "path": str(old),
                    "version_control": "none",
                    "remote": "",
                    "last_epoch": int((now - datetime.timedelta(days=91)).timestamp()),
                },
            ]
            roots = ((source, "Main Research", "main-research", "Main research"),)
            with patch.object(module, "scan_root", return_value=rows):
                result = module.sync_project_notes(
                    vault=vault,
                    roots=roots,
                    now=now,
                    github_activity={},
                    machine_folder="Desktop",
                )

            recent_text = existing.read_text(encoding="utf-8")
            old_text = (vault / "Projects" / "Desktop" / "Main Research" / "Old Study.md").read_text(encoding="utf-8")
            index_text = (vault / "Projects" / "Desktop" / "Project Roots.md").read_text(encoding="utf-8")

        self.assertEqual(result["active"], 1)
        self.assertEqual(result["unreviewed"], 1)
        self.assertIn("knowledge_status: active", recent_text)
        self.assertIn("Keep this human-authored goal.", recent_text)
        self.assertIn("knowledge_status: unreviewed", old_text)
        self.assertIn("project_id: main-research-old-study", old_text)
        self.assertIn("activity_window_days: 90", index_text)

    def test_default_mode_syncs_project_notes_without_publishing(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            module, "VAULT", Path(directory)
        ), patch.object(
            module, "sync_project_notes", return_value={"active": 0}
        ) as sync, patch.object(module, "publish_observations") as publish:
            self.assertEqual(module.main([]), 0)

        sync.assert_called_once()
        publish.assert_not_called()

    def test_normalize_github_remote_supports_https_and_ssh(self):
        module = load_script()

        self.assertEqual(module.normalize_github_remote("https://github.com/Example/Repo.git"), "example/repo")
        self.assertEqual(module.normalize_github_remote("git@github.com:Example/Repo.git"), "example/repo")
        self.assertEqual(module.normalize_github_remote("ssh://git@github.com/Example/Repo.git"), "example/repo")
        self.assertEqual(module.normalize_github_remote("ssh://git@example.com/other/repo"), "")

    def test_observation_snapshot_matches_only_canonical_projects_and_never_leaks_paths(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.VAULT = root / "vault"
            projects = module.VAULT / "Projects"
            projects.mkdir(parents=True)
            (projects / "research.md").write_text(
                "---\nproject_id: research\nknowledge_status: active\n"
                "project_category: main-research\ngithub_repo: Example/Repo\n---\n# Research\n",
                encoding="utf-8",
            )
            (projects / "ignored.md").write_text(
                "---\nknowledge_status: active\ngithub_repo: example/ignored\n---\n# Ignored\n",
                encoding="utf-8",
            )
            (projects / "plain.md").write_text(
                "---\nproject_id: plain-project\nknowledge_status: active\n"
                "project_category: systems-admin\n---\n# Plain project\n",
                encoding="utf-8",
            )
            plain = root / "private-home" / "plain-project"
            unmanaged = root / "private-home" / "unmanaged"
            mapping = root / "project-map.json"
            mapping.write_text(
                json.dumps({str(plain): "plain-project", str(unmanaged): "plain-project"}),
                encoding="utf-8",
            )
            rows = [
                {
                    "name": "repo",
                    "path": str(root / "private-home" / "repo"),
                    "version_control": "git",
                    "remote": "git@github.com:Example/Repo.git",
                    "last_epoch": 1_700_000_000,
                    "last_commit_sha": "abc1234",
                    "dirty_files": 3,
                    "ahead": 1,
                    "behind": 0,
                },
                {
                    "name": "plain-project",
                    "path": str(plain),
                    "version_control": "none",
                    "remote": "",
                    "last_epoch": 0,
                    "last_commit_sha": "",
                    "dirty_files": None,
                    "ahead": 0,
                    "behind": 0,
                },
                {
                    "name": "unmanaged",
                    "path": str(unmanaged),
                    "version_control": "git",
                    "remote": "https://github.com/example/unmanaged.git",
                    "last_epoch": 0,
                    "last_commit_sha": "",
                    "dirty_files": 0,
                    "ahead": 0,
                    "behind": 0,
                },
                {
                    "name": "jyang21-private-notes",
                    "path": str(root / "private-home" / "jyang21-private-notes"),
                    "version_control": "none",
                    "remote": "",
                    "last_epoch": 0,
                    "last_commit_sha": "",
                    "dirty_files": None,
                    "ahead": 0,
                    "behind": 0,
                },
            ]

            snapshot = module.project_observation_snapshot(
                rows,
                machine="MacLaptop-new",
                observed_at="2026-08-24T08:00:00-05:00",
                mapping_path=mapping,
            )

        self.assertEqual([row["project_id"] for row in snapshot["projects"]], ["plain-project", "research"])
        self.assertEqual(snapshot["projects"][1]["github_repo"], "example/repo")
        self.assertEqual(snapshot["projects"][1]["dirty_count"], 3)
        self.assertEqual(snapshot["projects"][1]["ahead"], 1)
        self.assertEqual(snapshot["unmatched"][0]["source"], "example/unmanaged")
        self.assertRegex(snapshot["unmatched"][1]["source"], r"^local-[0-9a-f]{12}$")
        serialized = json.dumps(snapshot)
        self.assertNotIn(str(root), serialized)
        self.assertNotIn("private-home", serialized)
        self.assertNotIn("jyang21", serialized)

    def test_observation_snapshot_leaves_duplicate_canonical_repository_unmatched(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            projects = vault / "Projects"
            projects.mkdir(parents=True)
            for project_id in ("alpha", "zeta"):
                (projects / f"{project_id}.md").write_text(
                    "---\n"
                    f"project_id: {project_id}\n"
                    "knowledge_status: active\n"
                    "github_repo: Example/Shared.git\n"
                    "---\n",
                    encoding="utf-8",
                )
            with patch.object(module, "VAULT", vault):
                snapshot = module.project_observation_snapshot(
                    [{
                        "path": str(root / "shared"),
                        "version_control": "git",
                        "remote": "git@github.com:Example/Shared.git",
                    }],
                    machine="MacLaptop-new",
                    observed_at="2026-08-24T08:00:00-05:00",
                    mapping_path=root / "missing-map.json",
                )

        self.assertEqual(snapshot["projects"], [])
        self.assertEqual(snapshot["unmatched"][0]["source"], "example/shared")

    def test_observation_snapshot_leaves_duplicate_project_ids_unmatched(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            projects = vault / "Projects"
            projects.mkdir(parents=True)
            for name, repo in (("one", "example/one"), ("two", "example/two")):
                (projects / f"{name}.md").write_text(
                    "---\nproject_id: duplicate\nknowledge_status: active\n"
                    f"github_repo: {repo}\n---\n",
                    encoding="utf-8",
                )
            rows = [
                {"path": str(root / name), "version_control": "git", "remote": f"https://github.com/{repo}"}
                for name, repo in (("one", "example/one"), ("two", "example/two"))
            ]
            with patch.object(module, "VAULT", vault):
                snapshot = module.project_observation_snapshot(
                    rows,
                    machine="MacLaptop-new",
                    observed_at="2026-08-24T08:00:00-05:00",
                    mapping_path=root / "missing-map.json",
                )

        self.assertEqual(snapshot["projects"], [])
        self.assertEqual(
            [row["source"] for row in snapshot["unmatched"]],
            ["example/one", "example/two"],
        )

    def test_scan_root_does_not_emit_a_container_that_only_holds_a_nested_repository(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "container" / "repo"
            (repository / ".git").mkdir(parents=True)

            with patch.object(module, "git", return_value=""):
                rows = module.scan_root(root)

        self.assertEqual([row["name"] for row in rows], ["repo"])

    def test_scan_root_reports_checked_out_head_separately_from_all_ref_activity(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repo"
            (repository / ".git").mkdir(parents=True)

            def git_result(_path, arguments):
                if arguments == ["log", "-1", "--format=%ct%x00%h", "--all"]:
                    return "1700000000\x00deadbee"
                if arguments == ["log", "-1", "--format=%ct", "--all"]:
                    return "1700000000"
                if arguments == ["rev-parse", "--short", "HEAD"]:
                    return "abc1234"
                if arguments and arguments[0] == "rev-list":
                    return "0 0"
                return ""

            with patch.object(module, "git", side_effect=git_result):
                rows = module.scan_root(root)

        self.assertEqual(rows[0]["last_epoch"], 1_700_000_000)
        self.assertEqual(rows[0]["last_commit_sha"], "abc1234")

    def test_write_observation_snapshot_is_deterministic_and_scoped_to_one_device_file(self):
        module = load_script()
        snapshot = {
            "schema_version": 1,
            "device": "MacLaptop-new",
            "observed_at": "2026-08-24T08:00:00-05:00",
            "projects": [{"project_id": "z"}, {"project_id": "a"}],
            "unmatched": [{"source": "z"}, {"source": "a"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            first = module.write_observation_snapshot(snapshot, vault=vault)
            first_bytes = first.read_bytes()
            second = module.write_observation_snapshot(snapshot, vault=vault)

            self.assertEqual(first, vault / "Observations/devices/MacLaptop-new.json")
            self.assertEqual(second.read_bytes(), first_bytes)
            stored = json.loads(second.read_text(encoding="utf-8"))

        self.assertEqual([row["project_id"] for row in stored["projects"]], ["a", "z"])
        self.assertEqual([row["source"] for row in stored["unmatched"]], ["a", "z"])

    def test_write_observation_snapshot_rejects_a_traversing_device_name(self):
        """The device name becomes a filename, so it must not escape the folder."""
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            for device in ("../../evil", "sub/dir", "..", "with space"):
                with self.subTest(device=device):
                    snapshot = {
                        "schema_version": 1,
                        "device": device,
                        "observed_at": "2026-08-24T08:00:00-05:00",
                        "projects": [],
                        "unmatched": [],
                    }
                    with self.assertRaises(ValueError):
                        module.write_observation_snapshot(snapshot, vault=vault)

            written = list(vault.rglob("*.json"))
            self.assertEqual(written, [], written)

    def test_observation_validator_rejects_wrong_field_types(self):
        module = load_script()
        snapshot = {
            "schema_version": 1,
            "device": "MacLaptop-new",
            "observed_at": "2026-08-24T08:00:00-05:00",
            "projects": [{
                "project_id": None,
                "github_repo": "example/repo",
                "activity_at": "",
                "github_pushed_at": "",
                "head": "abc1234",
                "dirty_count": 0,
                "ahead": 0,
                "behind": 0,
            }],
            "unmatched": [],
        }

        self.assertFalse(module._valid_observation_snapshot(snapshot, "MacLaptop-new"))

    def test_publish_requires_an_explicit_machine_name_before_scanning(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module, "VAULT", Path(directory)), patch.object(
                module, "MACHINE", ""
            ), patch.object(
                module, "scan_root"
            ) as scan, patch.object(module, "collect_github", return_value={}), patch.object(
                module, "publish_snapshot"
            ):
                with self.assertRaisesRegex(RuntimeError, "TODO_MACHINE is required"):
                    module.publish_observations()

        scan.assert_not_called()

    def test_publish_checks_upstream_before_scanning_or_writing(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            module, "VAULT", Path(directory)
        ), patch.object(module, "MACHINE", "MacLaptop-new"), patch.object(
            module, "_publication_state", side_effect=RuntimeError("upstream unavailable")
        ), patch.object(module, "scan_root") as scan, patch.object(
            module, "collect_github", return_value={}
        ), patch.object(module, "write_observation_snapshot") as write:
            with self.assertRaisesRegex(RuntimeError, "upstream unavailable"):
                module.publish_observations()

        scan.assert_not_called()
        write.assert_not_called()

    def test_publish_mode_commits_only_the_current_device_snapshot(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            module.VAULT = Path(directory)
            rows = [{"name": "demo", "path": "/tmp/demo", "version_control": "none", "remote": ""}]
            with patch.object(module, "scan_root", return_value=rows) as scan, patch.object(
                module, "collect_github", return_value={}
            ), patch.object(
                module, "project_observation_snapshot", return_value={
                    "schema_version": 1,
                    "device": "MacLaptop-new",
                    "observed_at": "2026-08-24T08:00:00-05:00",
                    "projects": [],
                    "unmatched": [],
                },
            ) as build, patch.object(module.subprocess, "run") as run:
                state = {"ahead": 0, "head": "base-oid", "remote": "origin", "branch": "main"}
                run.side_effect = [
                    module.subprocess.CompletedProcess([], 0),
                    module.subprocess.CompletedProcess([], 0, stdout="base-oid\n"),
                    module.subprocess.CompletedProcess([], 1),
                    module.subprocess.CompletedProcess([], 0),
                    module.subprocess.CompletedProcess([], 0, stdout="snapshot-oid\n"),
                    module.subprocess.CompletedProcess([], 0, stdout="base-oid\n"),
                    module.subprocess.CompletedProcess([], 0),
                ]
                with patch.object(module, "MACHINE", "MacLaptop-new"), patch.object(
                    module, "_publication_state", return_value=state
                ), patch.object(
                    module, "_validate_observation_commit"
                ):
                    result = module.publish_observations()

            self.assertEqual(result, module.VAULT / "Observations/devices/MacLaptop-new.json")
            self.assertEqual(scan.call_count, len(module.SCAN_ROOTS))
            build.assert_called_once()
            relative = "Observations/devices/MacLaptop-new.json"
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands, [
                ["git", "-C", str(module.VAULT), "add", "--", relative],
                ["git", "-C", str(module.VAULT), "rev-parse", "HEAD"],
                ["git", "-C", str(module.VAULT), "diff", "--cached", "--quiet", "--", relative],
                ["git", "-C", str(module.VAULT), "commit", "-m", "chore: observe projects from MacLaptop-new", "--", relative],
                ["git", "-C", str(module.VAULT), "rev-parse", "HEAD"],
                ["git", "-C", str(module.VAULT), "rev-parse", "HEAD^"],
                ["git", "-C", str(module.VAULT), "push", "origin", "snapshot-oid:refs/heads/main"],
            ])
            self.assertFalse(any("kanban" in " ".join(command).lower() for command in commands))
            self.assertFalse(any("Projects/" in " ".join(command) for command in commands))

    def test_publish_aborts_before_staging_when_vault_is_behind(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            target = vault / "Observations/devices/MacLaptop-new.json"
            with patch.object(module.subprocess, "run") as run:
                run.side_effect = [
                    module.subprocess.CompletedProcess([], 0),
                    module.subprocess.CompletedProcess([], 0, stdout="1 0"),
                ]
                with self.assertRaisesRegex(RuntimeError, "behind its upstream"):
                    module.publish_snapshot(target, vault=vault)

        self.assertFalse(any("add" in call.args[0] for call in run.call_args_list))

    def test_publish_retries_a_pending_push_when_snapshot_is_unchanged(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            target = vault / "Observations/devices/MacLaptop-new.json"
            state = {"ahead": 1, "head": "pending-oid", "remote": "origin", "branch": "main"}
            with patch.object(module.subprocess, "run") as run:
                run.side_effect = [
                    module.subprocess.CompletedProcess([], 0),
                    module.subprocess.CompletedProcess([], 0, stdout="pending-oid\n"),
                    module.subprocess.CompletedProcess([], 0),
                    module.subprocess.CompletedProcess([], 0),
                ]
                module.publish_snapshot(target, vault=vault, publication_state=state)

        self.assertEqual(
            run.call_args_list[-1].args[0],
            ["git", "-C", str(vault), "push", "origin", "pending-oid:refs/heads/main"],
        )

    def test_publish_rejects_unrelated_commits_ahead_of_upstream(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            vault = root / "vault"

            def git(*args: str, cwd: Path | None = None) -> str:
                return subprocess.run(
                    ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
                ).stdout.strip()

            git("init", "--bare", str(remote))
            git("symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)
            git("clone", str(remote), str(vault))
            git("config", "user.name", "Test", cwd=vault)
            git("config", "user.email", "test@example.invalid", cwd=vault)
            (vault / "README.md").write_text("initial\n", encoding="utf-8")
            git("add", "README.md", cwd=vault)
            git("commit", "-m", "initial", cwd=vault)
            git("push", "-u", "origin", "HEAD:main", cwd=vault)
            upstream = git("rev-parse", "origin/main", cwd=vault)

            (vault / "private.md").write_text("must not publish\n", encoding="utf-8")
            git("add", "private.md", cwd=vault)
            git("commit", "-m", "private local work", cwd=vault)
            target = vault / "Observations/devices/MacLaptop-new.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"device":"MacLaptop-new"}\n', encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "unrelated local commits"):
                module.publish_snapshot(target, vault=vault)

            self.assertEqual(git("rev-parse", "origin/main", cwd=vault), upstream)

    def test_publish_rejects_unsafe_observation_blob_in_pending_history(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            vault = root / "vault"

            def git(*args: str, cwd: Path | None = None) -> str:
                return subprocess.run(
                    ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
                ).stdout.strip()

            git("init", "--bare", str(remote))
            git("symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)
            git("clone", str(remote), str(vault))
            git("config", "user.name", "Test", cwd=vault)
            git("config", "user.email", "test@example.invalid", cwd=vault)
            (vault / "README.md").write_text("initial\n", encoding="utf-8")
            git("add", "README.md", cwd=vault)
            git("commit", "-m", "initial", cwd=vault)
            git("push", "-u", "origin", "HEAD:main", cwd=vault)
            upstream = git("rev-parse", "origin/main", cwd=vault)
            target = vault / "Observations/devices/MacLaptop-new.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"secret":"PRIVATE-TOKEN"}\n', encoding="utf-8")
            git("add", str(target.relative_to(vault)), cwd=vault)
            git("commit", "-m", "chore: observe projects from MacLaptop-new", cwd=vault)

            with self.assertRaisesRegex(RuntimeError, "unsafe observation snapshot"):
                module.publish_snapshot(target, vault=vault)

            self.assertEqual(git("rev-parse", "origin/main", cwd=vault), upstream)

    def test_publish_pushes_the_validated_oid_when_head_moves_after_commit(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            vault = root / "vault"

            def git(*args: str, cwd: Path | None = None) -> str:
                return subprocess.run(
                    ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
                ).stdout.strip()

            git("init", "--bare", str(remote))
            git("symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)
            git("clone", str(remote), str(vault))
            git("config", "user.name", "Test", cwd=vault)
            git("config", "user.email", "test@example.invalid", cwd=vault)
            (vault / "README.md").write_text("initial\n", encoding="utf-8")
            git("add", "README.md", cwd=vault)
            git("commit", "-m", "initial", cwd=vault)
            git("push", "-u", "origin", "HEAD:main", cwd=vault)
            target = vault / "Observations/devices/MacLaptop-new.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({
                "schema_version": 1,
                "device": "MacLaptop-new",
                "observed_at": "2026-08-24T08:00:00-05:00",
                "projects": [],
                "unmatched": [],
            }) + "\n", encoding="utf-8")
            original_push = module._push_snapshot

            def move_head_then_push(base, state, commit):
                (vault / "private.md").write_text("must stay local\n", encoding="utf-8")
                git("add", "private.md", cwd=vault)
                git("commit", "-m", "private race commit", cwd=vault)
                original_push(base, state, commit)

            with patch.object(module, "_push_snapshot", side_effect=move_head_then_push):
                module.publish_snapshot(target, vault=vault)

            remote_head = git("rev-parse", "origin/main", cwd=vault)
            self.assertNotEqual(git("rev-parse", "HEAD", cwd=vault), remote_head)
            self.assertIn(
                "Observations/devices/MacLaptop-new.json",
                git("ls-tree", "-r", "--name-only", remote_head, cwd=vault).splitlines(),
            )
            self.assertNotIn(
                "private.md",
                git("ls-tree", "-r", "--name-only", remote_head, cwd=vault).splitlines(),
            )

    def test_publish_reports_an_actionable_push_race(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            target = vault / "Observations/devices/MacLaptop-new.json"
            state = {"ahead": 0, "head": "base-oid", "remote": "origin", "branch": "main"}
            with patch.object(module.subprocess, "run") as run:
                run.side_effect = [
                    module.subprocess.CompletedProcess([], 0),
                    module.subprocess.CompletedProcess([], 0, stdout="base-oid\n"),
                    module.subprocess.CompletedProcess([], 1),
                    module.subprocess.CompletedProcess([], 0),
                    module.subprocess.CompletedProcess([], 0, stdout="snapshot-oid\n"),
                    module.subprocess.CompletedProcess([], 0, stdout="base-oid\n"),
                    module.subprocess.CalledProcessError(1, ["git", "push"]),
                ]
                with patch.object(module, "_validate_observation_commit"):
                    with self.assertRaisesRegex(RuntimeError, "commit remains local"):
                        module.publish_snapshot(target, vault=vault, publication_state=state)

    def test_rejected_hydration_and_device_note_publishers_are_absent(self):
        module = load_script()

        for name in (
            "vault_task_records",
            "hydrate_vault_tasks",
            "sync_vault_tasks",
            "publish_local_inventory",
            "sync_machine_inventory",
            "local_notes",
            "local_index",
        ):
            self.assertFalse(hasattr(module, name), name)

    def test_tokens_falls_back_to_the_existing_gh_login(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as directory, patch.object(module.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "existing-gh-token\n"

            found = module.tokens(Path(directory) / "missing.env")

        self.assertEqual(found, ["existing-gh-token"])
        self.assertEqual(run.call_args.args[0], ["gh", "auth", "token"])


if __name__ == "__main__":
    unittest.main()