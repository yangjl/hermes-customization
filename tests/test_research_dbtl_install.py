"""Codex-only installation never changes Hermes or unrelated plugins."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CREATOR = Path(os.environ.get(
    "CODEX_PLUGIN_CREATOR",
    str(Path.home() / ".codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py"),
))


class ResearchDbtlInstallTest(unittest.TestCase):
    def run_install(self, base, *extra, creator=CREATOR):
        env = dict(
            os.environ,
            HOME=str(base),
            HERMES_HOME=str(base / "hermes"),
            CODEX_PLUGIN_PARENT=str(base / "plugins"),
            CODEX_MARKETPLACE_PATH=str(base / ".agents/plugins/marketplace.json"),
            CODEX_PLUGIN_CREATOR=str(creator),
            PATH=f"{base / 'bin'}:{os.environ['PATH']}",
        )
        return subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--codex-dbtl-only", *extra],
            env=env, capture_output=True, text=True, timeout=30,
        )

    def test_codex_only_installs_twice_and_preserves_other_plugins(self):
        if not CREATOR.is_file():
            self.skipTest("Codex plugin-creator is required for integration install test")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            marketplace = base / ".agents/plugins/marketplace.json"
            marketplace.parent.mkdir(parents=True)
            other = {"name": "other", "source": {"source": "local", "path": "./plugins/other"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
                     "category": "Productivity"}
            marketplace.write_text(json.dumps({"name": "personal", "interface": {
                "displayName": "My research"}, "plugins": [other]}))
            sibling = base / "plugins/other/keep.txt"
            sibling.parent.mkdir(parents=True)
            sibling.write_text("preserve me")
            executable = base / "bin/hermes"
            executable.parent.mkdir()
            executable.write_text('#!/bin/sh\ntouch "$HOME/hermes-called"\nexit 91\n')
            executable.chmod(0o755)
            for _ in range(2):
                result = self.run_install(base)
                self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(marketplace.read_text())
            self.assertEqual(data["plugins"][0], other)
            self.assertEqual(data["interface"]["displayName"], "My research")
            self.assertEqual([p["name"] for p in data["plugins"]], ["other", "research-dbtl"])
            self.assertEqual(sibling.read_text(), "preserve me")
            installed = base / "plugins/research-dbtl"
            self.assertEqual((installed / ".codex-plugin/plugin.json").read_bytes(),
                             (ROOT / "plugins/research-dbtl/.codex-plugin/plugin.json").read_bytes())
            self.assertFalse(list(installed.rglob("__pycache__")))
            self.assertFalse((base / "hermes").exists())
            self.assertFalse((base / "hermes-called").exists())
            # Existing policies are user settings, not installer defaults.
            data["plugins"][1]["policy"]["authentication"] = "ON_USE"
            marketplace.write_text(json.dumps(data))
            before = marketplace.read_bytes()
            result = self.run_install(base)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marketplace.read_bytes(), before)

    def test_missing_helper_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            result = self.run_install(base, creator=base / "missing.py")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CODEX_PLUGIN_CREATOR", result.stderr)
            self.assertFalse((base / "plugins").exists())
            self.assertFalse((base / "hermes").exists())

    def test_codex_only_rejects_mixed_hermes_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            result = self.run_install(base, "--enable-project-kanban")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((base / "plugins").exists())
            self.assertFalse((base / "hermes").exists())

    def test_conflicting_marketplace_source_is_not_replaced(self):
        if not CREATOR.is_file():
            self.skipTest("Codex plugin-creator is required for integration install test")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            marketplace = base / ".agents/plugins/marketplace.json"
            marketplace.parent.mkdir(parents=True)
            marketplace.write_text(json.dumps({"name": "personal", "plugins": [{
                "name": "research-dbtl", "source": {"source": "local", "path": "./other"}}]}))
            before = marketplace.read_bytes()
            result = self.run_install(base)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("different source", result.stderr)
            self.assertEqual(marketplace.read_bytes(), before)
            self.assertFalse((base / "plugins").exists())

    def test_nested_symlinks_fail_before_scaffold_or_copy(self):
        if not CREATOR.is_file():
            self.skipTest("Codex plugin-creator is required for integration install test")
        for kind in ("file", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                installed = base / "plugins/research-dbtl"
                outside = base / "outside"
                outside.mkdir()
                protected = outside / "app.js"
                protected.write_text("private content")
                if kind == "file":
                    link = installed / "assets/app.js"
                    link.parent.mkdir(parents=True)
                    link.symlink_to(protected)
                else:
                    link = installed / "assets"
                    link.parent.mkdir(parents=True)
                    link.symlink_to(outside, target_is_directory=True)
                result = self.run_install(base)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("symlink", result.stderr)
                self.assertEqual(protected.read_text(), "private content")
                self.assertTrue(link.is_symlink())
                self.assertEqual(sorted(p.name for p in outside.iterdir()), ["app.js"])
                self.assertFalse((installed / ".codex-plugin").exists())
                self.assertFalse((base / ".agents").exists())
