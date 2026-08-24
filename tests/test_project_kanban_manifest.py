from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectKanbanManifestTest(unittest.TestCase):
    def test_backend_manifest_is_api_only_and_namespaced(self):
        manifest = json.loads(
            (ROOT / "plugins/project-kanban/dashboard/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "project-kanban")
        self.assertEqual(manifest["api"], "plugin_api.py")
        self.assertTrue(manifest["tab"]["hidden"])

    def test_plugin_identity_matches_install_folders(self):
        metadata = (ROOT / "plugins/project-kanban/plugin.yaml").read_text(encoding="utf-8")
        self.assertIn("name: project-kanban", metadata)
        self.assertIn("kind: standalone", metadata)
        self.assertTrue((ROOT / "plugins/project-kanban/__init__.py").is_file())


if __name__ == "__main__":
    unittest.main()
