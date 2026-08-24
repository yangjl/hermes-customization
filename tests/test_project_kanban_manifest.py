from __future__ import annotations

import json
import importlib.util
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
        package = ROOT / "plugins/project-kanban/__init__.py"
        self.assertTrue(package.is_file())
        spec = importlib.util.spec_from_file_location("project_kanban_package_test", package)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.register))


if __name__ == "__main__":
    unittest.main()
