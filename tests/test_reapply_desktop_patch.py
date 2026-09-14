"""Regression tests for the Desktop patch reconciler."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "reapply-desktop-patch.sh"


class ReapplyDesktopPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.source = self.tmp / "hermes-agent"
        self.overlay = self.tmp / "overlay"
        (self.source / ".git").mkdir(parents=True)
        (self.overlay / "scripts").mkdir(parents=True)
        (self.overlay / "patches").mkdir()
        shutil.copy2(SCRIPT, self.overlay / "scripts" / SCRIPT.name)
        hardener = self.overlay / "scripts" / "harden-hermes-python-env.sh"
        hardener.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        hardener.chmod(0o755)

    def write_applied_patch(self, name: str, filename: str) -> None:
        (self.source / filename).write_text("new\n", encoding="utf-8")
        (self.overlay / "patches" / f"{name}.patch").write_text(
            f"diff --git a/{filename} b/{filename}\n"
            f"--- a/{filename}\n"
            f"+++ b/{filename}\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n",
            encoding="utf-8",
        )

    def test_already_applied_patches_are_silent_on_macos_bash(self):
        self.write_applied_patch("desktop-research-workflow", "desktop.txt")
        self.write_applied_patch("terminal-theme-fields", "terminal.txt")
        env = {
            **os.environ,
            "HERMES_CUSTOMIZATION_DIR": str(self.overlay),
            "HERMES_SOURCE_DIR": str(self.source),
        }

        result = subprocess.run(
            ["/bin/bash", str(self.overlay / "scripts" / SCRIPT.name)],
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_first_patch_conflict_reports_patch_name_not_empty_array_error(self):
        (self.source / "desktop.txt").write_text("upstream drift\n", encoding="utf-8")
        (self.overlay / "patches" / "desktop-research-workflow.patch").write_text(
            "diff --git a/desktop.txt b/desktop.txt\n"
            "--- a/desktop.txt\n"
            "+++ b/desktop.txt\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n",
            encoding="utf-8",
        )
        self.write_applied_patch("terminal-theme-fields", "terminal.txt")
        subprocess.run(["git", "init", "-q"], cwd=self.source, check=True)
        subprocess.run(["git", "add", "desktop.txt", "terminal.txt"], cwd=self.source, check=True)
        subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"],
            cwd=self.source,
            check=True,
        )
        env = {
            **os.environ,
            "HERMES_CUSTOMIZATION_DIR": str(self.overlay),
            "HERMES_SOURCE_DIR": str(self.source),
        }

        result = subprocess.run(
            ["/bin/bash", str(self.overlay / "scripts" / SCRIPT.name)],
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 1)
        self.assertNotIn("unbound variable", result.stderr)
        self.assertIn("desktop-research-workflow no longer applies", result.stderr)


if __name__ == "__main__":
    unittest.main()
