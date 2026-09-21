"""Settings checks over disposable native cards; no real project mutations."""
import unittest
import test_research_dbtl as fixture
dbtl = fixture.dbtl


class SettingsTests(unittest.TestCase):
    setUp = fixture.ResearchDBTLTests.setUp
    create = fixture.ResearchDBTLTests.create
    approve = fixture.ResearchDBTLTests.approve
    def save_agent(self, values, agent='codex', version=None):
        current = self.app.snapshot()['project']['agent_settings'][agent]
        self.app.action({'action': 'agent-settings', 'actor': agent, 'settings': values,
                         'version': current['version'] if version is None else version})

    def save_task(self, task, values, version=None):
        current = self.app.card(task)['settings']
        self.app.action({'action': 'task-settings', 'task_id': task, 'settings': values,
                         'version': current['version'] if version is None else version})

    def test_inheritance_persistence_and_explicit_blank(self):
        task = self.create()
        self.save_agent({'instructions': 'Default checks', 'skills': 'research-dbtl'})
        self.save_task(task, {'instructions': '', 'repo': '/example/repo'})
        current = self.app.card(task)['settings']
        self.assertEqual(current['effective']['instructions'], '')
        self.assertEqual(current['effective']['skills'], 'research-dbtl')
        other = dbtl.Project(self.root)
        try:
            self.assertEqual(other.snapshot()['tasks'][0]['settings'], current)
        finally:
            other.close()
        self.save_agent({'instructions': 'Changed default', 'skills': 'research-dbtl, check'})
        self.assertEqual(self.app.card(task)['settings']['effective']['instructions'], '')
        self.save_task(task, {})
        self.assertEqual(self.app.card(task)['settings']['effective']['instructions'], 'Changed default')

    def test_conflicts_and_validation_are_atomic(self):
        task = self.create()
        old = self.app.card(task)['settings']['version']
        self.save_task(task, {'skills': ''})
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.save_task(task, {'skills': 'lost'}, old)
        before = self.app.snapshot()
        for values in ({'folder': 'relative'}, {'folder': ''}, {'unknown': 'bad'}, {'skills': []}, {'instructions': 'x'*10001}, {'repo': 'x\x00y'}):
            with self.subTest(values=str(values)[:60]), self.assertRaises(ValueError):
                self.save_task(task, values)
        self.assertEqual(self.app.snapshot(), before)
        with self.assertRaisesRegex(ValueError, 'part of'):
            self.save_task('foreign-task', {})

    def test_claim_freezes_settings_and_submission_keeps_them(self):
        task = self.create()
        self.save_agent({'instructions': 'Original'})
        lease = self.app.claim(task, 'codex')
        self.assertEqual(lease['settings']['instructions'], 'Original')
        self.save_agent({'instructions': 'Later'})
        self.save_task(task, {'instructions': 'Next run'})
        card = self.app.card(task)
        self.assertEqual(card['settings']['effective']['instructions'], 'Next run')
        self.assertEqual(card['run_context']['settings']['instructions'], 'Original')
        (self.root/'pin.txt').write_text('fixture')
        self.app.submit(task, lease['token'], lease['run_id'], 'fixture', ['pin.txt'])
        self.assertEqual(self.app.card(task)['submission']['settings']['instructions'], 'Original')
        self.approve(task)
        pin = self.app.card(task)['submission']
        self.save_task(task, {'instructions': 'Future'})
        self.assertEqual(self.app.card(task)['submission'], pin)
        self.assertFalse(self.app.card(task)['stale'])

    def test_reassignment_inherits_new_agent_with_overrides_retained(self):
        task = self.create()
        self.save_agent({'instructions': 'Claude instructions'}, 'claude')
        self.save_task(task, {'repo': '/example/repo'})
        self.app.action({'action': 'reassign', 'task_id': task, 'actor': 'claude'})
        values = self.app.card(task)['settings']['effective']
        self.assertEqual(values['instructions'], 'Claude instructions')
        self.assertEqual(values['repo'], '/example/repo')

    def test_http_accepts_valid_unicode_settings(self):
        import json
        from concurrent.futures import ThreadPoolExecutor
        from urllib.request import Request, urlopen
        server, url = dbtl.server_for(self.app)
        server.timeout = 5
        self.addCleanup(server.server_close)
        origin, token = url.split('/#token=')
        values = {'instructions': '漢' * 7000}
        current = self.app.snapshot()['project']['agent_settings']['codex']
        payload = json.dumps({'action': 'agent-settings', 'actor': 'codex',
                              'version': current['version'], 'settings': values}).encode()
        request = Request(origin + '/api/action', data=payload, headers={
            'Authorization': 'Bearer ' + token, 'Origin': origin, 'Content-Type': 'application/json'})
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: urlopen(request, timeout=10).read())
            server.handle_request()
            response = json.loads(future.result())
        self.assertEqual(response['project']['agent_settings']['codex']['effective']['instructions'], values['instructions'])
