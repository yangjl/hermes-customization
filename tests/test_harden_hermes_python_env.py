from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "harden-hermes-python-env.sh"


class HardenHermesPythonEnvTest(unittest.TestCase):
    def test_patches_current_thin_path_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / ".local" / "bin" / "hermes"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "#!/bin/sh\nexec /tmp/hermes-agent/.hermes/bin/hermes \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(SCRIPT)],
                cwd=ROOT,
                env=dict(
                    os.environ,
                    HOME=str(root),
                    HERMES_HOME=str(root / ".hermes"),
                ),
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            hardened = wrapper.read_text(encoding="utf-8")
            self.assertIn("unset __PYVENV_LAUNCHER__", hardened)
            self.assertIn(
                'exec /tmp/hermes-agent/.hermes/bin/hermes "$@"',
                hardened,
            )


if __name__ == "__main__":
    unittest.main()
