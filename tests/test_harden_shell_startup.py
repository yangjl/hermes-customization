"""Behaviour contract for scripts/harden-shell-startup.sh.

The guard exists because Cortex XDR terminates Hermes' whole process tree when
a login shell spawns processes in bursts (nvm.sh forks ~40 helpers, and Hermes
sources the rc file twice per terminal session). These tests pin the contract
that makes the guard safe to run unattended on a second machine.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "harden-shell-startup.sh"
MARKER = "xdr-btp-guard"


def run(rc_path, *args):
    env = dict(os.environ, BASHRC_PATH=str(rc_path))
    return subprocess.run(
        [str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=120
    )


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class HardenShellStartupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write_rc(self, name, text):
        rc = self.tmp / name
        rc.write_text(text)
        return rc

    def backups(self, rc):
        return list(rc.parent.glob(rc.name + ".bak-*"))

    def test_guard_is_inserted_at_the_top_so_it_precedes_everything_else(self):
        """The guard only helps if it runs BEFORE the expensive rc body."""
        rc = self.write_rc("rc", 'export MARKPATH=$HOME/.marks\nfunction jump { :; }\n')
        result = run(rc)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(MARKER, rc.read_text().splitlines()[0])

    def test_rerunning_does_not_stack_a_second_guard(self):
        """Installers run repeatedly; the edit must converge, not accumulate."""
        rc = self.write_rc("rc", "export MARKPATH=$HOME/.marks\n")
        run(rc)
        after_first = rc.read_text()
        result = run(rc)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rc.read_text(), after_first)
        self.assertEqual(after_first.count(f"{MARKER} >>>"), 1)

    def test_check_reports_state_without_touching_the_file(self):
        """--check is what install.sh uses to decide whether to nag."""
        rc = self.write_rc("rc", "export MARKPATH=$HOME/.marks\n")
        before = digest(rc)
        self.assertEqual(run(rc, "--check").returncode, 1)
        self.assertEqual(digest(rc), before, "--check must not modify the rc file")

        run(rc)
        self.assertEqual(run(rc, "--check").returncode, 0)

    def test_a_late_path_export_is_refused_and_fully_reverted(self):
        """The guard skips the rc body for non-interactive shells, so a PATH
        export sitting after it would silently vanish from Hermes' terminal.
        Refuse instead, and leave not a trace behind."""
        toolbin = self.tmp / "toolbin"
        toolbin.mkdir()
        rc = self.write_rc("rc", f'export PATH="{toolbin}:$PATH"\n')
        before = digest(rc)

        result = run(rc)

        self.assertEqual(result.returncode, 1, "must refuse to guard this rc")
        self.assertIn(str(toolbin), result.stderr, "must name the offending entry")
        self.assertEqual(digest(rc), before, "rc must be byte-identical after refusal")
        self.assertEqual(self.backups(rc), [], "refusal must leave no backup behind")

    def test_a_stale_path_entry_does_not_block_the_guard(self):
        """A PATH dir that does not exist contributes no commands, so losing it
        from non-interactive shells costs nothing (these accumulate on machines
        whose dotfiles were carried over from another host)."""
        rc = self.write_rc("rc", 'export PATH="/nonexistent/ghost/bin:$PATH"\n')
        result = run(rc)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(MARKER, rc.read_text())

    def test_a_missing_rc_file_is_a_no_op_not_an_error(self):
        """Machines without ~/.bashrc must not fail the installer."""
        result = run(self.tmp / "does-not-exist")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_successful_run_keeps_a_backup(self):
        """The edit is reversible by hand even after it succeeds."""
        rc = self.write_rc("rc", "export MARKPATH=$HOME/.marks\n")
        original = rc.read_text()
        run(rc)
        backups = self.backups(rc)
        self.assertEqual(len(backups), 1, "expected exactly one backup")
        self.assertEqual(backups[0].read_text(), original)


if __name__ == "__main__":
    unittest.main()
