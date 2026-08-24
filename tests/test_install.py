from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallTest(unittest.TestCase):
    @staticmethod
    def _fake_hermes(root: Path, *, board_create_exit: int = 0) -> tuple[Path, Path]:
        bin_dir = root / "bin"
        bin_dir.mkdir()
        log = root / "hermes.log"
        executable = bin_dir / "hermes"
        executable.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HERMES_LOG\"\n"
            f"if [ \"$1 $2 $3\" = \"kanban boards create\" ]; then exit {board_create_exit}; fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return bin_dir, log

    def test_installs_project_kanban_frontend_and_backend_without_enabling_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
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
            calls = log.read_text(encoding="utf-8")
            self.assertNotIn("plugins enable project-kanban", calls)
            self.assertNotIn("kanban boards create", calls)

    def test_explicit_opt_in_enables_plugin_without_renaming_existing_boards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".hermes"
            bin_dir, log = self._fake_hermes(root, board_create_exit=1)
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
            self.assertIn("kanban boards create todos", calls)
            self.assertNotIn("kanban boards rename", calls)


if __name__ == "__main__":
    unittest.main()
