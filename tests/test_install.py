from __future__ import annotations

import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallTest(unittest.TestCase):
    @staticmethod
    def _fake_hermes(
        root: Path, *, board_create_exit: int = 0, existing_boards: tuple[str, ...] = ()
    ) -> tuple[Path, Path]:
        """A stand-in `hermes` that mirrors CURRENT Kanban CLI semantics.

        `kanban boards create` is idempotent in real Hermes: it exits 0 for an
        already-existing board and rewrites `board.json`'s display name. The
        fake therefore succeeds by default, and `board_create_exit` models only
        a genuine creation failure.
        """
        bin_dir = root / "bin"
        bin_dir.mkdir()
        log = root / "hermes.log"
        executable = bin_dir / "hermes"
        executable.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HERMES_LOG\"\n"
            f"if [ \"$1 $2 $3\" = \"kanban boards create\" ]; then exit {board_create_exit}; fi\n"
            "if [ \"$1 $2 $3\" = \"kanban boards list\" ]; then\n"
            f"  printf '%s\\n' '{json.dumps([{'slug': slug} for slug in existing_boards])}'\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return bin_dir, log

    def _run_install(self, home: Path, bin_dir: Path, log: Path, *args: str):
        env = dict(
            os.environ,
            HERMES_HOME=str(home),
            HERMES_LOG=str(log),
            PATH=f"{bin_dir}:/usr/bin:/bin",
        )
        return subprocess.run(
            ["/bin/bash", str(ROOT / "install.sh"), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_existing_board_is_never_passed_to_idempotent_create(self):
        """Real `boards create` succeeds and rewrites metadata, so it must not run."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            bin_dir, log = self._fake_hermes(
                root, board_create_exit=0, existing_boards=("todos",)
            )

            result = self._run_install(
                home, bin_dir, log, "--enable-project-kanban"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text(encoding="utf-8")
            self.assertIn("kanban boards list", calls)
            self.assertNotIn("kanban boards create todos", calls)

    def test_absent_board_is_created_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            bin_dir, log = self._fake_hermes(
                root, board_create_exit=0, existing_boards=()
            )

            result = self._run_install(
                home, bin_dir, log, "--enable-project-kanban"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text(encoding="utf-8")
            self.assertEqual(calls.count("kanban boards create todos"), 1)

    OBSOLETE_RUNNER = (
        "#!/usr/bin/env python3\n"
        '"""Pull shared todo records into this machine\'s local Kanban board."""\n'
        "from __future__ import annotations\n"
        "import runpy\n"
        "from pathlib import Path\n"
        "def main() -> int:\n"
        "    return 0\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n"
    )

    def test_removes_only_the_recognized_obsolete_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            legacy_runner = home / "scripts/sync-todo-kanban.py"
            legacy_runner.parent.mkdir(parents=True)
            legacy_runner.write_text(self.OBSOLETE_RUNNER, encoding="utf-8")
            bin_dir, log = self._fake_hermes(root)

            result = self._run_install(home, bin_dir, log)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(legacy_runner.exists())

    def test_preserves_and_reports_an_unknown_file_at_the_legacy_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            legacy_runner = home / "scripts/sync-todo-kanban.py"
            legacy_runner.parent.mkdir(parents=True)
            user_content = "#!/usr/bin/env python3\n# my own edits\nprint('mine')\n"
            legacy_runner.write_text(user_content, encoding="utf-8")
            bin_dir, log = self._fake_hermes(root)

            result = self._run_install(home, bin_dir, log)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(legacy_runner.exists())
            self.assertEqual(
                legacy_runner.read_text(encoding="utf-8"), user_content
            )
            self.assertIn(
                "sync-todo-kanban.py", result.stdout + result.stderr
            )

    def test_installs_project_kanban_frontend_and_backend_without_enabling_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            legacy_runner = home / "scripts/sync-todo-kanban.py"
            legacy_runner.parent.mkdir(parents=True)
            legacy_runner.write_text(self.OBSOLETE_RUNNER, encoding="utf-8")
            bin_dir, log = self._fake_hermes(root)
            env = dict(
                os.environ,
                HERMES_HOME=str(home),
                HERMES_LOG=str(log),
                PATH=f"{bin_dir}:/usr/bin:/bin",
            )
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "install.sh")],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / "desktop-plugins/project-kanban/plugin.js").is_file())
            self.assertTrue((home / "plugins/project-kanban/dashboard/plugin_api.py").is_file())
            self.assertTrue((home / "plugins/project-kanban/dashboard/manifest.json").is_file())
            publisher = home / "scripts/refresh-todo-vault.py"
            self.assertTrue(publisher.is_file())
            self.assertTrue(os.access(publisher, os.X_OK))
            self.assertIn("--publish-observations", publisher.read_text(encoding="utf-8"))
            hardener = home / "scripts/harden-hermes-python-env.sh"
            self.assertTrue(hardener.is_file())
            self.assertTrue(os.access(hardener, os.X_OK))
            reapply = home / "scripts/reapply-desktop-patch.sh"
            self.assertTrue(reapply.is_file())
            self.assertIn("Documents/projects/hermes-customizations", reapply.read_text(encoding="utf-8"))
            self.assertFalse((home / "scripts/sync-todo-kanban.py").exists())
            calls = log.read_text(encoding="utf-8")
            self.assertNotIn("plugins enable project-kanban", calls)
            self.assertNotIn("kanban boards create", calls)

    def test_explicit_opt_in_enables_plugin_without_renaming_existing_boards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            bin_dir, log = self._fake_hermes(
                root, board_create_exit=0, existing_boards=("todos",)
            )
            env = dict(
                os.environ,
                HERMES_HOME=str(home),
                HERMES_LOG=str(log),
                PATH=f"{bin_dir}:/usr/bin:/bin",
            )
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "install.sh"), "--enable-project-kanban"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text(encoding="utf-8")
            self.assertIn("plugins enable project-kanban --no-allow-tool-override", calls)
            # An existing board is left completely alone: no create (which would
            # rewrite its display name) and no rename.
            self.assertNotIn("kanban boards create", calls)
            self.assertNotIn("kanban boards rename", calls)

    def test_opt_in_fails_when_the_board_list_is_unreadable(self):
        """An unreadable list must not fall through into a metadata-rewriting create."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            log = root / "hermes.log"
            executable = bin_dir / "hermes"
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HERMES_LOG\"\n"
                "if [ \"$1 $2 $3\" = \"kanban boards list\" ]; then\n"
                "  printf '%s\\n' 'not json'\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            result = self._run_install(
                home, bin_dir, log, "--enable-project-kanban"
            )

            self.assertNotEqual(result.returncode, 0)
            calls = log.read_text(encoding="utf-8")
            self.assertNotIn("kanban boards create", calls)

    def test_opt_in_fails_when_the_board_list_is_malformed_json_shape(self):
        """A well-formed JSON doc of the wrong shape must not read as 'absent'."""
        for payload in ('{"a": 1}', '["todos"]', 'null'):
            with self.subTest(payload=payload):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    home = root / ".hermes"
                    bin_dir = root / "bin"
                    bin_dir.mkdir()
                    log = root / "hermes.log"
                    executable = bin_dir / "hermes"
                    executable.write_text(
                        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HERMES_LOG\"\n"
                        "if [ \"$1 $2 $3\" = \"kanban boards list\" ]; then\n"
                        f"  printf '%s\\n' '{payload}'\n"
                        "  exit 0\n"
                        "fi\n"
                        "exit 0\n",
                        encoding="utf-8",
                    )
                    executable.chmod(0o755)

                    result = self._run_install(
                        home, bin_dir, log, "--enable-project-kanban"
                    )

                    self.assertNotEqual(result.returncode, 0)
                    calls = log.read_text(encoding="utf-8")
                    self.assertNotIn("kanban boards create", calls)

    def test_opt_in_refuses_when_boards_list_exits_nonzero_but_prints_the_board(self):
        """A non-zero CLI exit must never be read as 'board absent'.

        Under `set -o pipefail` a pipeline returns the rightmost non-zero
        status, so a warning-then-exit-1 CLI that still prints the board would
        otherwise fall through to the metadata-rewriting create.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            log = root / "hermes.log"
            executable = bin_dir / "hermes"
            listing = json.dumps([{"slug": "todos", "name": "My Custom Board Name"}])
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HERMES_LOG\"\n"
                "if [ \"$1 $2 $3\" = \"kanban boards list\" ]; then\n"
                f"  printf '%s\\n' '{listing}'\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            result = self._run_install(
                home, bin_dir, log, "--enable-project-kanban"
            )

            calls = log.read_text(encoding="utf-8")
            self.assertNotIn("kanban boards create", calls)
            self.assertNotEqual(result.returncode, 0)

    def test_opt_in_fails_when_required_board_cannot_be_created(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            bin_dir, log = self._fake_hermes(root, board_create_exit=2)
            env = dict(
                os.environ,
                HERMES_HOME=str(home),
                HERMES_LOG=str(log),
                PATH=f"{bin_dir}:/usr/bin:/bin",
            )

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "install.sh"), "--enable-project-kanban"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not create required board todos", result.stderr.lower())


class DesktopPatchContentTest(unittest.TestCase):
    """Shape guard for the regenerated Desktop source patch.

    The patch is rebuilt wholesale from a worktree (`git diff --cached`), so a
    section can vanish silently. Pin the profile-avatar-identity sections it
    must carry, and the one file AGENTS.md forbids (apps/desktop/index.html).
    """

    def test_desktop_patch_carries_profile_identity_and_omits_index_html(self):
        patch = (ROOT / "patches" / "desktop-research-workflow.patch").read_text(
            encoding="utf-8"
        )
        for path in (
            "apps/desktop/src/lib/profile-identity.ts",
            "apps/desktop/src/lib/profile-identity.test.ts",
            "apps/desktop/src/components/ui/profile-avatar.tsx",
            "apps/desktop/src/components/ui/profile-avatar.test.tsx",
            "apps/desktop/src/app/chat/sidebar/profile-switcher.tsx",
            "apps/desktop/src/app/chat/sidebar/session-row.tsx",
            "apps/desktop/src/app/chat/sidebar/fleet-rail.ts",
        ):
            self.assertIn(f"diff --git a/{path} b/{path}", patch)
        self.assertNotIn("a/apps/desktop/index.html", patch)


if __name__ == "__main__":
    unittest.main()
