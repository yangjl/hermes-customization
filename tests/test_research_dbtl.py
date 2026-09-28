"""Behavioral integration checks against an isolated native Hermes Kanban."""
import importlib.util
import base64
import os
from pathlib import Path
import tempfile
import struct
import unittest
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('research_dbtl', ROOT / 'plugins/research-dbtl/scripts/dbtl.py')
dbtl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dbtl)


class ResearchDBTLTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.env = patch.dict(os.environ, {'HERMES_HOME': str(Path(self.tmp.name) / 'hermes')})
        self.env.start()
        self.addCleanup(self.env.stop)
        dbtl.initialize(self.root, 'Synthetic research', 'research')
        self.app = dbtl.Project(self.root)
        self.addCleanup(self.app.close)

    def create(self, phase='design', parents=(), **extra):
        return self.app.create(phase=phase, title='Bounded work', brief='Local fixture only', parents=list(parents), **extra)

    def submit(self, task, path='evidence.txt'):
        (self.root / path).write_text('Measured fixture result')
        owner = self.app.card(task)['actor']
        lease = self.app.claim(task, owner)
        return self.app.submit(task, lease['token'], lease['run_id'], 'Scope and checks described', [path])

    def approve(self, task):
        submission = self.app.card(task)['submission']
        self.app.action({'action': 'approve', 'task_id': task, 'submission_id': submission['id'], 'note': 'Reviewed'})

    @staticmethod
    def picture():
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 6, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress((b'\0' + b'\x20\x80\x40\xff' * 256) * 256))
               + chunk(b'IEND', b''))
        return 'data:image/png;base64,' + base64.b64encode(png).decode()

    def test_avatars_persist_without_changing_tasks_or_roles(self):
        task = self.create()
        self.submit(task)
        before = self.app.snapshot()
        self.assertEqual(before['project'].get('avatars', {}), {})
        picture = self.picture()
        self.app.action({'action': 'avatars', 'avatars': {'codex': picture, 'claude': picture}})
        other = dbtl.Project(self.root)
        try:
            after = other.snapshot()
            self.assertEqual(after['project']['avatars'], {'codex': picture, 'claude': picture})
            self.assertEqual(before['tasks'], after['tasks'])
            self.assertEqual(before['project']['roles'], after['project']['roles'])
            other.action({'action': 'avatars', 'avatars': {'hermes': picture}})
            self.app.action({'action': 'avatars', 'avatars': {'codex': None}})
            self.assertEqual(other.snapshot()['project']['avatars'], {'claude': picture, 'hermes': picture})
        finally:
            other.close()

    def test_avatar_rejection_is_atomic(self):
        picture = self.picture()
        original = (self.root / dbtl.CONFIG).read_bytes()
        for invalid in ({}, {'unknown': picture}, {'codex': 'https://example.com/a.png'},
                        {'codex': 'data:image/svg+xml,<svg/>'}, {'codex': 42},
                        {'codex': 'data:image/png;base64,@@@@'},
                        {'codex': 'data:image/png;base64,' + base64.b64encode(b'not PNG').decode()},
                        {'codex': 'data:image/png;base64,' + 'A' * 500000},
                        {'codex': picture, 'claude': 'invalid'}):
            with self.subTest(invalid=str(invalid)[:70]), self.assertRaises(ValueError):
                self.app.action({'action': 'avatars', 'avatars': invalid})
            self.assertEqual((self.root / dbtl.CONFIG).read_bytes(), original)

    def test_avatar_rejects_unknown_critical_png_chunk(self):
        raw = base64.b64decode(self.picture().split(',')[1])
        kind = b'BOOM'
        chunk = struct.pack('>I', 0) + kind + struct.pack('>I', zlib.crc32(kind))
        malformed = 'data:image/png;base64,' + base64.b64encode(raw[:33] + chunk + raw[33:]).decode()
        with self.assertRaisesRegex(ValueError, 'valid 256px PNG'):
            self.app.action({'action': 'avatars', 'avatars': {'codex': malformed}})

    def test_native_workflow_and_stale_upstream(self):
        design = self.create()
        self.submit(design)
        self.approve(design)
        build = self.create('build', [design])
        self.assertEqual(self.app.card(build)['status'], 'ready')
        (self.root / 'evidence.txt').write_text('Changed after approval')
        self.assertTrue(self.app.card(design)['stale'])
        with self.assertRaisesRegex(ValueError, 'stale|changed'):
            self.app.claim(build, 'codex')

    def test_revision_approval_and_correction(self):
        task = self.create()
        first = self.submit(task)
        with self.assertRaises(ValueError):
            self.app.action({'action': 'approve', 'task_id': task, 'submission_id': 'old'})
        self.app.action({'action': 'correct', 'task_id': task, 'submission_id': first['id'], 'note': 'Narrow the claim'})
        second = self.submit(task)
        self.assertNotEqual(first['id'], second['id'])
        with self.assertRaises(ValueError):
            self.app.action({'action': 'approve', 'task_id': task, 'submission_id': first['id']})
        self.approve(task)
        self.assertEqual(self.app.card(task)['status'], 'done')

    def test_native_hooks_use_project_board_without_switching_global_board(self):
        task = self.create()
        before = self.app.kb.get_current_board()
        observed = []
        with patch.object(self.app.kb, '_fire_task_hook',
                          side_effect=lambda *a, **k: observed.append(self.app.kb.get_current_board())):
            self.app.claim(task, 'codex')
        self.assertEqual(observed, ['research'])
        self.assertEqual(self.app.kb.get_current_board(), before)

    def test_roles_do_not_steal_active_work(self):
        task = self.create()
        lease = self.app.claim(task, 'codex')
        self.app.action({'action': 'roles', 'roles': {'coordinator': 'hermes', 'design': 'claude'}})
        self.assertEqual(self.app.card(task)['actor'], 'codex')
        with self.assertRaises(ValueError):
            self.app.action({'action': 'reassign', 'task_id': task, 'actor': 'claude'})
        with self.assertRaises(ValueError):
            self.app.claim(task, 'codex')
        with self.assertRaises(ValueError):
            self.app.heartbeat(task, 'wrong', lease['run_id'])
        self.assertEqual(self.app.card(self.create())['actor'], 'claude')

    def test_phase_gates_and_path_escape(self):
        with self.assertRaises(ValueError):
            self.create('build')
        with self.assertRaises(ValueError):
            self.create('test')
        task = self.create()
        lease = self.app.claim(task, 'codex')
        (self.root.parent / 'outside.txt').write_text('private')
        (self.root / 'escape').symlink_to(self.root.parent / 'outside.txt')
        for path in ['../outside.txt', 'escape']:
            with self.assertRaises(ValueError):
                self.app.submit(task, lease['token'], lease['run_id'], 'Evidence', [path])
        self.assertEqual(self.app.card(task)['status'], 'running')

    def test_full_exploration_and_independent_manuscript_test(self):
        design = self.create()
        self.submit(design, 'design.txt')
        self.approve(design)
        build = self.create('build', [design])
        self.submit(build, 'build.txt')
        self.approve(build)
        learn = self.create('learn', [build])
        self.submit(learn, 'report.txt')
        self.approve(learn)
        self.assertEqual(self.app.card(learn)['status'], 'done')
        self.app.action({'action': 'roles', 'roles': {'test': 'codex'}})
        with self.assertRaisesRegex(ValueError, 'different agent'):
            self.create('test', [build], claim='Writer-selected bounded claim')
        self.app.action({'action': 'roles', 'roles': {'test': 'hermes'}})
        test = self.create('test', [build], claim='Writer-selected bounded claim')
        with self.assertRaises(ValueError):
            self.app.action({'action': 'reassign', 'task_id': test, 'actor': 'codex'})
        (self.root / 'design.txt').write_text('Upstream protocol changed')
        self.assertTrue(self.app.card(learn)['stale'])
        with self.assertRaises(ValueError):
            self.app.claim(test, 'hermes')

    def test_corrected_output_can_change_during_new_run(self):
        task = self.create()
        first = self.submit(task)
        self.app.action({'action': 'correct', 'task_id': task,
                         'submission_id': first['id'], 'note': 'Revise interpretation'})
        (self.root / 'evidence.txt').write_text('Revision in progress')
        lease = self.app.claim(task, 'codex')
        (self.root / 'evidence.txt').write_text('Corrected result')
        self.app.heartbeat(task, lease['token'], lease['run_id'])
        self.app.submit(task, lease['token'], lease['run_id'], 'Corrected scope', ['evidence.txt'])
        self.approve(task)
        self.assertFalse(self.app.card(task)['stale'])

    def test_native_janitor_recovery_rejects_old_worker(self):
        task = self.create()
        old = self.app.claim(task, 'codex')
        (self.root / 'evidence.txt').write_text('Result')
        with patch.object(dbtl.time, 'time', return_value=dbtl.time.time() + 1000):
            self.assertEqual(self.app.kb.release_stale_claims(self.app.conn), 1)
            self.assertEqual(self.app.card(task)['status'], 'blocked')
            self.app.recover(task, 'Old session stopped by coordinator')
            new = self.app.claim(task, 'codex')
            self.assertNotEqual(old['run_id'], new['run_id'])
            with self.assertRaisesRegex(ValueError, 'ownership'):
                self.app.submit(task, old['token'], old['run_id'], 'Late result', ['evidence.txt'])
            self.app.submit(task, new['token'], new['run_id'], 'Recovered result', ['evidence.txt'])

    def test_expired_claim_cannot_submit(self):
        task = self.create()
        lease = self.app.claim(task, 'codex')
        (self.root / 'evidence.txt').write_text('Result')
        with patch.object(dbtl.time, 'time', return_value=dbtl.time.time() + 1000):
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.app.submit(task, lease['token'], lease['run_id'], 'Evidence', ['evidence.txt'])


if __name__ == '__main__':
    unittest.main()
