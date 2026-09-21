"""Integration checks against a disposable native Hermes board, never user records."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dbtl', Path(__file__).parents[1] / 'plugins/research-dbtl/scripts/dbtl.py')
dbtl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbtl)

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='dbtl-history-project-')
        self.root = Path(self.directory.name) / 'project'
        self.root.mkdir()
        self.env = patch.dict(os.environ, {'HERMES_HOME': str(Path(self.directory.name) / 'hermes')})
        self.env.start()
        self.addCleanup(self.env.stop)
        dbtl.initialize(self.root, 'Test history', 'history-test')
        self.project = dbtl.Project(self.root)
        self.task = self.project.create('design', 'Explore-01 history', 'Reconstruct history', cycle=1)
        self.source = self.root/'run.json'
        self.source.write_text(json.dumps({'cycle':'explore-01','outcome':'completed'}))
        pin = self.project.artifact('run.json')
        self.manifest = {'kind':'historical-evidence-snapshot','cycle':'explore-01','sources':[
            {'snapshot':'run.json','sha256':pin['sha256'],'bytes':pin['size']} ]}
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))
        claim = self.project.claim(self.task, 'codex')
        self.submission = self.project.submit(self.task, claim['token'], claim['run_id'],
                                              'Reconstructed evidence', ['manifest.json'])

    def tearDown(self):
        self.project.close()
        self.directory.cleanup()

    def record(self, **kw):
        args = dict(task_id=self.task, agent='codex', completed_on='2026-09-18',
                    note='User confirmed previous Build was completed; development evidence only.')
        args.update(kw)
        return self.project.record_build_completion(**args)

    def test_completed_build_is_not_approval(self):
        receipt = self.record()
        card = self.project.snapshot()['tasks'][0]
        self.assertEqual((card['phase'], card['status'], card['stale']), ('build','done',False))
        self.assertEqual(receipt['submission_id'], self.submission['id'])
        self.assertIsNone(self.project.receipt(self.task,'approval'))
        self.assertEqual(card['submission'],self.submission)
        with self.assertRaisesRegex(ValueError,'not approval'):
            self.project.current(self.task, approved=True)
        with self.assertRaisesRegex(ValueError,'not approval'):
            self.project.create('learn','New work','Must not run',parents=[self.task])
        with self.assertRaisesRegex(ValueError,'already recorded'):
            self.record()

    def test_changed_indirect_source_blocks_import(self):
        self.source.write_text('changed')
        with self.assertRaisesRegex(ValueError,'source changed'):
            self.record()
        self.assertEqual(self.project.task(self.task)[0].status,'review')

    def test_changed_indirect_source_marks_done_stale(self):
        self.record()
        self.source.write_text('changed')
        self.assertTrue(self.project.snapshot()['tasks'][0]['stale'])

    def test_coordinator_required(self):
        with self.assertRaisesRegex(ValueError,'coordinator'):
            self.record(agent='claude')

    def test_future_date_refused(self):
        with self.assertRaisesRegex(ValueError,'future'):
            self.record(completed_on='2999-01-01')

    def test_ordinary_planning_card_not_importable(self):
        # New ordinary review card has no historical manifest.
        task = self.project.create('design','Future study','Normal planning')
        claim = self.project.claim(task,'codex')
        self.project.submit(task,claim['token'],claim['run_id'],'Proposal',['run.json'])
        with self.assertRaisesRegex(ValueError,'pinned manifest'):
            self.record(task_id=task)

    def test_native_dependents_block_import(self):
        self.project.kb.create_task(self.project.conn,title='Dependent',parents=[self.task])
        with self.assertRaisesRegex(ValueError,'downstream'):
            self.record()

    def test_existing_approval_workflow_unchanged(self):
        # Simulate a human action only in the disposable test board.
        self.project.action({'action':'approve','task_id':self.task,
                             'submission_id':self.submission['id'],'note':'Test fixture'})
        card = self.project.snapshot()['tasks'][0]
        self.assertEqual((card['phase'],card['status'],card['completion']),('design','done',None))
        self.assertFalse(card['stale'])
        self.project.create('build','Normal build','Approved scope',parents=[self.task])

    def make_learn(self, cycle=1, invalid_sources=False):
        self.record()
        task = self.project.create('design', 'Historical Learn reconstruction', 'Preserve prior lessons', cycle=cycle)
        (self.root/'learn').mkdir()
        (self.root/'learn/lessons.md').write_text('Original interpretation and next-step recommendations.')
        pin = self.project.artifact('learn/lessons.md')
        manifest = {'kind':'historical-learning-snapshot','cycle':f'explore-{cycle:02}',
                    'learning_sources':['missing.md' if invalid_sources else pin['path']],
                    'sources':[{'snapshot':pin['path'],'sha256':pin['sha256'],'bytes':pin['size']}]}
        (self.root/'learn/manifest.json').write_text(json.dumps(manifest))
        lease = self.project.claim(task,'codex')
        self.project.submit(task,lease['token'],lease['run_id'],'Preserved lessons',['learn/manifest.json'])
        return task

    def finish_learn(self, task):
        return self.project.record_learn_completion(task,'codex','2026-09-18',
                                                    'User requested restoration of completed Learn results.',self.task)

    def test_learn_history_links_build_without_granting_approval(self):
        roles = self.project.snapshot()['project']['roles']
        task = self.make_learn()
        receipt = self.finish_learn(task)
        card = self.project.card(task)
        self.assertEqual((card['phase'],card['status'],card['stale']),('learn','done',False))
        self.assertEqual(receipt['source_build']['submission_id'],self.submission['id'])
        self.assertEqual(receipt['learning_evidence'],['learn/lessons.md'])
        self.assertEqual(self.project.card(self.task)['phase'],'build')
        self.assertEqual(self.project.snapshot()['project']['roles'],roles)
        self.assertIsNone(self.project.receipt(task,'approval'))
        with self.assertRaisesRegex(ValueError,'not approval'):
            self.project.current(task,approved=True)

    def test_changed_build_evidence_marks_learn_stale(self):
        task = self.make_learn()
        self.finish_learn(task)
        self.source.write_text('Changed prior Build evidence')
        self.assertTrue(self.project.card(task)['stale'])

    def test_changed_learn_output_marks_learn_stale(self):
        task = self.make_learn()
        self.finish_learn(task)
        (self.root/'learn/lessons.md').write_text('Changed interpretation')
        self.assertTrue(self.project.card(task)['stale'])

    def test_wrong_cycle_build_cannot_complete_learn(self):
        task = self.make_learn(cycle=2)
        with self.assertRaisesRegex(ValueError,'same cycle'):
            self.finish_learn(task)
        self.assertEqual(self.project.card(task)['status'],'review')

    def test_unlisted_learning_source_cannot_complete_learn(self):
        task = self.make_learn(invalid_sources=True)
        with self.assertRaisesRegex(ValueError,'identified learning outputs'):
            self.finish_learn(task)

if __name__ == '__main__':
    unittest.main(verbosity=2)
