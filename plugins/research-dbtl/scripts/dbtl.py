#!/usr/bin/env python3
"""Single-project DBTL policy over the existing Hermes Kanban (stdlib transport)."""
import argparse
import base64
import binascii
from datetime import date
from contextlib import contextmanager
import fcntl
from functools import wraps
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import time
import struct
import zlib

CONFIG = '.research-dbtl.json'
ROLES = {'coordinator': 'codex', 'design': 'codex', 'build': 'codex',
         'test': 'hermes', 'learn': 'claude'}
ACTORS = {'codex', 'claude', 'hermes'}
PHASES = ('design', 'build', 'test', 'learn')
PREFIX = 'research-dbtl/v1\n'
TTL = 900
AVATAR_BYTES = 300 * 1024
REQUEST_BYTES = 1300000
SETTING_LIMITS = {'folder': 2000, 'repo': 2000, 'skills': 2000, 'instructions': 10000}


def avatar_image(value: object) -> str | None:
    """Accept only the bounded square PNG produced by the local upload control."""
    if value is None:
        return None
    prefix = 'data:image/png;base64,'
    if not isinstance(value, str) or not value.startswith(prefix) or len(value) > AVATAR_BYTES * 4 // 3 + len(prefix):
        raise ValueError('Avatar must be a 256px PNG under 300 KiB')
    try:
        raw = base64.b64decode(value[len(prefix):], validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid PNG signature')
        offset, channels, compressed, ended = 8, None, bytearray(), False
        idat_finished = False
        while offset < len(raw):
            size = int.from_bytes(raw[offset:offset + 4], 'big')
            kind = raw[offset + 4:offset + 8]
            data = raw[offset + 8:offset + 8 + size]
            end = offset + 12 + size
            if end > len(raw) or zlib.crc32(kind + data) != int.from_bytes(raw[end - 4:end], 'big'):
                raise ValueError('Invalid PNG chunk')
            if offset == 8:
                if kind != b'IHDR' or len(data) != 13:
                    raise ValueError('Missing PNG header')
                width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
                if (width, height, depth, compression, filtering, interlace) != (256, 256, 8, 0, 0, 0) or color not in (2, 6):
                    raise ValueError('Expected a 256px RGB or RGBA PNG')
                channels = 4 if color == 6 else 3
            elif kind == b'IDAT':
                if idat_finished:
                    raise ValueError('Noncontiguous PNG pixels')
                compressed.extend(data)
            elif kind == b'IEND':
                ended = size == 0 and end == len(raw)
                break
            elif kind == b'IHDR':
                raise ValueError('Duplicate PNG header')
            elif len(kind) != 4 or not kind.isalpha() or not kind[0] & 32:
                raise ValueError('Unsupported critical PNG chunk')
            elif compressed:
                idat_finished = True
            offset = end
        if not ended or channels is None:
            raise ValueError('Incomplete PNG')
        expected = 256 * (1 + 256 * channels)
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(compressed), expected + 1)
        if not decoder.eof or decoder.unused_data or len(pixels) != expected or any(pixels[i] > 4 for i in range(0, expected, 1 + 256 * channels)):
            raise ValueError('Invalid PNG pixels')
    except (ValueError, binascii.Error, struct.error, zlib.error) as exc:
        raise ValueError('Avatar must be a valid 256px PNG under 300 KiB') from exc
    return value


def native():
    source = Path(os.environ.get('HERMES_SOURCE_DIR', Path.home() / '.hermes/hermes-agent'))
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        from hermes_cli import kanban_db
    except ImportError as exc:
        raise ValueError('Use the Hermes venv Python and set HERMES_SOURCE_DIR to its checkout') from exc
    return kanban_db


def nonblank(value, label, maximum=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{label} must be nonempty text (maximum {maximum} characters)')
    return value.strip()


def actor(value):
    if value not in ACTORS:
        raise ValueError('Agent must be codex, claude or hermes')
    return value


def settings_values(values):
    """Settings are bounded handoff text, never executed by the panel."""
    if not isinstance(values, dict) or set(values) - SETTING_LIMITS.keys():
        raise ValueError('Unknown execution settings')
    result = {}
    for key, value in values.items():
        if not isinstance(value, str) or len(value) > SETTING_LIMITS[key] or '\x00' in value:
            raise ValueError(f'Invalid {key}: expected bounded text')
        value = value.strip()
        if key == 'folder' and (not value or not Path(value).is_absolute()):
            raise ValueError('Working folder must be an absolute local path')
        if key in ('folder', 'repo') and any(c in value for c in '\r\n'):
            raise ValueError(f'{key} must be one line')
        result[key] = value
    return result


def settings_version(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def write_config(root, config):
    temporary = root / (CONFIG + '.tmp')
    with temporary.open('w') as stream:
        json.dump(config, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(root / CONFIG)


@contextmanager
def project_lock(root):
    # ponytail: one-machine flock; remote agents need a shared transactional API.
    with (root / '.research-dbtl.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def initialize(root, name, board):
    root = Path(root).resolve(strict=True)
    with project_lock(root):
        if (root / CONFIG).exists():
            raise ValueError('Project already initialized; existing configuration preserved')
        kb = native()
        if not kb.board_exists(board):
            kb.create_board(board, name=board)
        config = {'version': 1, 'id': secrets.token_hex(12),
                  'name': nonblank(name, 'Project name', 200), 'board': board, 'roles': dict(ROLES)}
        write_config(root, config)
        return config


def serialized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with project_lock(self.root):
            self.config = json.loads((self.root / CONFIG).read_text())
            if (self.config['id'], self.config['board']) != self.identity:
                raise ValueError('Project identity changed; restart the panel')
            with self.kb.scoped_current_board(self.config['board']):
                return method(self, *args, **kwargs)
    return wrapped


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.config = json.loads((self.root / CONFIG).read_text())
        if self.config.get('version') != 1:
            raise ValueError('Unsupported project configuration version')
        self.identity = (self.config['id'], self.config['board'])
        self.kb = native()
        if not self.kb.board_exists(self.config['board']):
            raise ValueError('Configured native board is missing; check HERMES_HOME')
        from hermes_cli.kanban_db_connect import connect
        self.conn = connect(board=self.config['board'])

    def close(self):
        self.conn.close()

    def assignment(self, agent):
        name = f'dbtl-{self.config["id"]}-{actor(agent)}'
        from hermes_cli.profiles import profile_exists
        if profile_exists(name):
            raise ValueError('External task lane collides with a native Hermes profile')
        return name

    def task(self, task_id):
        task = self.kb.get_task(self.conn, task_id)
        if not task or task.tenant != 'dbtl-' + self.config['id'] or not (task.body or '').startswith(PREFIX):
            raise ValueError('Task is not part of this research project')
        data = json.loads(task.body[len(PREFIX):])
        return task, data

    def agent_settings(self, agent):
        defaults = {'folder': str(self.root), 'repo': str(self.root),
                    'skills': 'research-dbtl', 'instructions': ''}
        values = self.config.get('agent_settings', {}).get(actor(agent), {})
        return {'effective': {**defaults, **values}, 'overrides': values,
                'version': settings_version(values)}

    def task_settings(self, task, data):
        owner = (task.assignee or '').rsplit('-', 1)[-1]
        defaults = self.agent_settings(owner)['effective']
        overrides = data.get('settings', {})
        return {'effective': {**defaults, **overrides}, 'defaults': defaults,
                'overrides': overrides,
                'version': settings_version([owner, defaults, overrides])}

    def receipt(self, task_id, kind):
        for run in reversed(self.kb.list_runs(self.conn, task_id)):
            receipt = (run.metadata or {}).get('research_dbtl', {})
            if receipt.get('kind') == kind:
                return receipt
        return None

    def artifact(self, relative):
        relative = nonblank(relative, 'Artifact path', 2000)
        candidate = Path(relative)
        if candidate.is_absolute() or '..' in candidate.parts:
            raise ValueError('Evidence must use a path inside the project')
        try:
            path = (self.root / candidate).resolve(strict=True)
            path.relative_to(self.root)
        except (OSError, ValueError) as exc:
            raise ValueError('Evidence missing or outside project') from exc
        if not path.is_file():
            raise ValueError('Evidence must be a regular file')
        # Bounded per-file hashing keeps the small local review panel responsive.
        if path.stat().st_size > 256 * 1024 * 1024:
            raise ValueError('Evidence exceeds 256 MiB; pin a manifest of large datasets')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Evidence changed during hashing; retry')
        return {'path': str(candidate), 'sha256': digest.hexdigest(), 'size': after.st_size}

    def check_inputs(self, data, seen=None):
        for parent, pin in data['inputs'].items():
            if self.current(parent, seen, approved=True)['id'] != pin:
                raise ValueError('Upstream approval changed; handoff is stale')

    def historical_completion(self, task_id):
        return self.receipt(task_id, 'historical-learn') or self.receipt(task_id, 'historical-build')

    def current(self, task_id, seen=None, approved=False):
        seen = set() if seen is None else set(seen)
        if task_id in seen:
            raise ValueError('Cyclic research dependency')
        seen.add(task_id)
        task, data = self.task(task_id)
        submission = self.receipt(task_id, 'submission')
        completion = self.historical_completion(task_id)
        if completion and (not submission or completion['submission_id'] != submission['id']):
            raise ValueError('Historical completion evidence changed')
        if approved:
            if completion:
                raise ValueError('Historical completion is not approval for new work')
            approval = self.receipt(task_id, 'approval')
            if task.status != 'done' or not submission or not approval or approval['submission_id'] != submission['id']:
                raise ValueError('Upstream task needs human approval')
        self.check_inputs(data, seen)
        if completion and completion.get('source_build'):
            self.historical_build_input(completion['source_build'], data['cycle'], seen)
        if submission:
            for item in submission['artifacts']:
                if self.artifact(item['path']) != item:
                    raise ValueError('Evidence changed; submission is stale')
        return submission

    def card(self, task_id):
        task, data = self.task(task_id)
        completion = self.historical_completion(task_id)
        historical_phase = completion['kind'].removeprefix('historical-') if completion else None
        problem = None
        try:
            if task.status in ('review', 'done'):
                self.current(task_id, approved=task.status == 'done' and not completion)
                if completion:
                    self.historical_sources(task_id, historical_phase)
            else:
                self.check_inputs(data)
        except (ValueError, OSError) as exc:
            problem = str(exc)
        owner = (task.assignee or '').rsplit('-', 1)[-1]
        return {'id': task.id, 'title': task.title, 'phase': historical_phase or data['phase'], 'cycle': data['cycle'],
                'actor': owner, 'status': task.status, 'brief': data['brief'], 'claim': data['claim'],
                'completion': completion, 'settings': self.task_settings(task, data),
                'run_context': data.get('run_context'),
                'parents': list(data['inputs']), 'submission': self.receipt(task_id, 'submission'),
                'stale': problem is not None, 'problem': problem,
                'history': [{'author': c.author, 'body': c.body, 'created_at': c.created_at}
                            for c in self.kb.list_comments(self.conn, task_id)]}

    @serialized
    def snapshot(self):
        return {'project': {**{key: self.config[key] for key in ('name', 'board', 'roles')},
                            'avatars': self.config.get('avatars', {}), 'id': self.config['id'],
                            'agent_settings': {agent: self.agent_settings(agent) for agent in sorted(ACTORS)}},
                'tasks': [self.card(t.id) for t in self.kb.list_tasks(
                    self.conn, tenant='dbtl-' + self.config['id'])]}

    def historical_sources(self, task_id, phase='build'):
        """Verify the pinned historical manifest and its completed run evidence."""
        _, data = self.task(task_id)
        submission = self.current(task_id)
        if not submission:
            raise ValueError('Historical completion requires submitted evidence')
        manifests, completed = 0, []
        for pin in submission['artifacts']:
            if Path(pin['path']).name != 'manifest.json':
                continue
            manifest = json.loads((self.root / pin['path']).read_text())
            kind = 'historical-learning-snapshot' if phase == 'learn' else 'historical-evidence-snapshot'
            if manifest.get('kind') != kind:
                continue
            if manifest.get('cycle') != f'explore-{data["cycle"]:02}':
                raise ValueError('Historical manifest belongs to another cycle')
            sources = manifest.get('sources')
            if not isinstance(sources, list) or not 1 <= len(sources) <= 1000:
                raise ValueError('Historical manifest must contain bounded evidence')
            manifests += 1
            for source in sources:
                actual = self.artifact(source['snapshot'])
                expected = {'path': source['snapshot'], 'sha256': source['sha256'], 'size': source['bytes']}
                if actual != expected:
                    raise ValueError('Historical source changed; completion is stale')
                if phase == 'build' and Path(source['snapshot']).name == 'run.json':
                    run = json.loads((self.root / source['snapshot']).read_text())
                    if run.get('outcome') == 'completed':
                        run_cycle = run.get('cycle', '')
                        base = manifest['cycle']
                        if run_cycle not in (base, base + 'p', base + 'c', base + '-nopc'):
                            raise ValueError('Completed run belongs to another cycle')
                        completed.append(source['snapshot'])
            if phase == 'learn':
                learning = manifest.get('learning_sources')
                available = {s['snapshot'] for s in sources if s['bytes'] > 0}
                if not isinstance(learning, list) or not learning or not all(isinstance(p, str) and p in available for p in learning):
                    raise ValueError('Historical Learn requires identified learning outputs in its manifest')
                completed.extend(learning)
        if manifests != 1 or not completed:
            raise ValueError(f'Historical {phase.title()} needs one pinned manifest and completed evidence')
        return completed

    def historical_build_input(self, reference, cycle, seen=None):
        """Historical lineage verifies evidence, never grants execution approval."""
        task, data = self.task(reference['task_id'])
        completion = self.receipt(task.id, 'historical-build')
        if task.status != 'done' or not completion or data['cycle'] != cycle:
            raise ValueError('Learn history requires a completed historical Build in the same cycle')
        submission = self.current(task.id, seen)
        if not submission or submission['id'] != reference['submission_id']:
            raise ValueError('Historical Build evidence changed')
        self.historical_sources(task.id)

    @serialized
    def record_build_completion(self, task_id, agent, completed_on, note):
        return self.record_historical_completion(task_id, agent, completed_on, note, 'build')

    @serialized
    def record_learn_completion(self, task_id, agent, completed_on, note, build):
        return self.record_historical_completion(task_id, agent, completed_on, note, 'learn', build)

    def record_historical_completion(self, task_id, agent, completed_on, note, phase, build=None):
        """Record a human-requested historical fact, never a scientific approval."""
        if actor(agent) != self.config['roles']['coordinator']:
            raise ValueError('Only the assigned coordinator may import history')
        note = nonblank(note, 'Human instruction and completion scope')
        if date.fromisoformat(completed_on) > date.today():
            raise ValueError('Historical completion date cannot be in the future')
        task, data = self.task(task_id)
        if self.historical_completion(task_id):
            raise ValueError('Historical completion is already recorded; do not duplicate it')
        if task.status != 'review' or data['phase'] != 'design' or data['inputs']:
            raise ValueError('Only an unparented historical reconstruction in review can be imported')
        # Refuse any native downstream edges before changing the meaning of this card.
        if self.kb.child_ids(self.conn, task_id) or self.kb.parent_ids(self.conn, task_id):
            raise ValueError('Historical reconstruction already has downstream tasks')
        completed = self.historical_sources(task_id, phase)
        source_build = None
        if phase == 'learn':
            upstream = self.current(build)
            if not upstream:
                raise ValueError('Historical Build has no evidence')
            source_build = {'task_id': build, 'submission_id': upstream['id']}
            self.historical_build_input(source_build, data['cycle'])
        submission = self.receipt(task_id, 'submission')
        receipt = {'kind': 'historical-' + phase, 'submission_id': submission['id'],
                   'completed_on': completed_on, 'recorded_at': int(time.time()),
                   'recorded_by': agent, 'note': note,
                   ('learning_evidence' if phase == 'learn' else 'completed_run_evidence'): completed,
                   'source_build': source_build,
                   'summary': f'Historical {phase.title()} completed. ' + note,
                   'scope': 'development evidence; no scientific approval or independent validation'}
        if not self.kb.complete_task(self.conn, task_id, summary=receipt['summary'],
                                     metadata={'research_dbtl': receipt}, fire_lifecycle_hook=False):
            raise ValueError('Task changed during historical import')
        self.kb.add_comment(self.conn, task_id, agent,
                            f'Historical {phase.title()} completed {completed_on}; recorded now at human request. '
                            'Original reconstruction submission retained. No approval receipt created. ' + note)
        return receipt

    @serialized
    def create(self, phase, title, brief, parents=(), claim='', cycle=1):
        if phase not in PHASES or not isinstance(cycle, int) or cycle < 1:
            raise ValueError('Choose a DBTL phase and positive cycle number')
        title = nonblank(title, 'Title', 300)
        brief = nonblank(brief, 'Brief')
        assigned = actor(self.config['roles'][phase])
        inputs = {}
        phases = []
        for parent in dict.fromkeys(parents):
            upstream = self.current(parent, approved=True)
            task, data = self.task(parent)
            phases.append(data['phase'])
            if phase == 'test' and task.assignee == self.assignment(assigned):
                raise ValueError('Independent Test needs a different agent from its evidence producer')
            inputs[parent] = upstream['id']
        required = {'build': 'design', 'learn': 'build', 'test': 'build'}.get(phase)
        if required and required not in phases:
            raise ValueError(f'{phase.title()} requires an approved {required.title()} parent')
        if phase == 'test':
            claim = nonblank(claim, 'Writer-selected manuscript claim')
        elif claim:
            raise ValueError('Manuscript claim belongs only on an independent Test task')
        data = {'phase': phase, 'cycle': cycle, 'brief': brief, 'claim': claim, 'inputs': inputs}
        task_id = self.kb.create_task(self.conn, title=title, body=PREFIX + json.dumps(data),
            assignee=self.assignment(assigned), created_by=self.config['roles']['coordinator'],
            tenant='dbtl-' + self.config['id'], workspace_kind='dir', workspace_path=str(self.root),
            parents=list(inputs), completion_contract='local-only', max_retries=0)
        self.kb.add_comment(self.conn, task_id, self.config['roles']['coordinator'],
                            f'Assigned {phase} to {assigned}. Human review required after submission.')
        return task_id

    @serialized
    def claim(self, task_id, agent):
        task, data = self.task(task_id)
        if task.assignee != self.assignment(agent):
            raise ValueError('Agent does not own this task')
        self.check_inputs(data)
        settings = self.task_settings(task, data)['effective']
        if task.status != 'ready':
            raise ValueError('Task is not ready or is already claimed')
        from hermes_cli.kanban_db_workspace import set_workspace_path
        set_workspace_path(self.conn, task_id, settings['folder'])
        token = secrets.token_urlsafe(32)
        claimed = self.kb.claim_task(self.conn, task_id, ttl_seconds=TTL, claimer=token)
        if not claimed:
            raise ValueError('Task is not ready or is already claimed')
        data['run_context'] = {'run_id': claimed.current_run_id, 'settings': settings}
        if not self.kb.edit_task(self.conn, task_id, body=PREFIX + json.dumps(data)):
            raise ValueError('Task changed while recording execution settings; stop the worker')
        return {'task_id': task_id, 'settings': settings, 'evidence_root': str(self.root), 'token': token, 'run_id': claimed.current_run_id,
                'expires': claimed.claim_expires, 'brief': self.card(task_id)['brief']}

    def ownership(self, task_id, token, run_id):
        task, _ = self.task(task_id)
        if task.status != 'running' or task.claim_lock != token or task.current_run_id != run_id:
            raise ValueError('Claim ownership changed')
        if not task.claim_expires or task.claim_expires <= int(time.time()):
            raise ValueError('Claim expired; stop and ask the coordinator to recover it')
        return task

    @serialized
    def heartbeat(self, task_id, token, run_id):
        self.ownership(task_id, token, run_id)
        self.check_inputs(self.task(task_id)[1])
        if not self.kb.heartbeat_claim(self.conn, task_id, ttl_seconds=TTL, claimer=token):
            raise ValueError('Claim ownership changed')
        return {'expires': self.kb.get_task(self.conn, task_id).claim_expires}

    @serialized
    def recover(self, task_id, note):
        task, _ = self.task(task_id)
        note = nonblank(note, 'Recovery reason')
        run = self.kb.latest_run(self.conn, task_id)
        native_expiry = (task.status == 'blocked' and run and run.outcome == 'reclaimed'
                         and (run.error or '').startswith('stale_lock=')
                         and (task.last_failure_error or '').startswith('stale_lock='))
        if native_expiry:
            recovered = self.kb.unblock_task(self.conn, task_id)
        elif task.status == 'running' and task.claim_expires and task.claim_expires <= int(time.time()):
            recovered = self.kb.reclaim_task(self.conn, task_id, reason=note)
        else:
            raise ValueError('Only expired claims can be recovered; stop the old worker first')
        if not recovered:
            raise ValueError('Claim changed during recovery')
        self.kb.add_comment(self.conn, task_id, self.config['roles']['coordinator'],
                            f'Recovered expired worker: {note}')
        return {'task_id': task_id, 'status': self.task(task_id)[0].status}

    @serialized
    def submit(self, task_id, token, run_id, summary, artifacts):
        task = self.ownership(task_id, token, run_id)
        summary = nonblank(summary, 'Handoff summary')
        _, data = self.task(task_id)
        # A correction may intentionally replace this task's earlier output.
        # Only its approved upstream inputs must remain unchanged at submission.
        self.check_inputs(data)
        if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 20:
            raise ValueError('Submit one to twenty evidence files')
        receipt = {'kind': 'submission', 'id': secrets.token_hex(16), 'run_id': run_id,
                   'summary': summary,
                   'settings': data.get('run_context', {}).get('settings') if data.get('run_context', {}).get('run_id') == run_id else None,
                   'artifacts': [self.artifact(p) for p in dict.fromkeys(artifacts)]}
        if not self.kb.request_review(self.conn, task_id, summary=summary,
                                     metadata={'research_dbtl': receipt}, expected_run_id=run_id):
            raise ValueError('Submission rejected: task changed')
        self.kb.add_comment(self.conn, task_id, task.assignee, f'Submitted evidence {receipt["id"][:8]} for human review.')
        return receipt

    @serialized
    def action(self, request):
        action = request.get('action')
        if action == 'agent-settings':
            agent = actor(request.get('actor'))
            current = self.agent_settings(agent)
            if request.get('version') != current['version']:
                raise ValueError('Agent settings changed; refresh and reopen the editor')
            values = settings_values(request.get('settings'))
            self.config.setdefault('agent_settings', {})[agent] = values
            write_config(self.root, self.config)
            return
        if action == 'avatars':
            changes = request.get('avatars')
            if not isinstance(changes, dict) or not changes or set(changes) - ACTORS:
                raise ValueError('Unknown or empty avatar settings')
            validated = {agent: avatar_image(value) for agent, value in changes.items()}
            avatars = dict(self.config.get('avatars', {}))
            for agent, value in validated.items():
                if value is None:
                    avatars.pop(agent, None)
                else:
                    avatars[agent] = value
            self.config['avatars'] = avatars
            write_config(self.root, self.config)
            return
        if action == 'roles':
            changes = request.get('roles')
            if not isinstance(changes, dict) or not changes or set(changes) - set(ROLES):
                raise ValueError('Unknown or empty role settings')
            self.config['roles'].update({role: actor(value) for role, value in changes.items()})
            write_config(self.root, self.config)
            return
        task_id = request.get('task_id')
        task, data = self.task(task_id)
        if action == 'task-settings':
            current = self.task_settings(task, data)
            if request.get('version') != current['version']:
                raise ValueError('Task settings changed; refresh and reopen the editor')
            data['settings'] = settings_values(request.get('settings'))
            if not self.kb.edit_task(self.conn, task_id, body=PREFIX + json.dumps(data)):
                raise ValueError('Task changed during settings update')
            self.kb.add_comment(self.conn, task_id, 'human',
                                'Updated settings for a future run. Existing execution records and evidence unchanged.')
            return
        if action == 'reassign':
            if task.status not in ('ready', 'todo'):
                raise ValueError('Only queued tasks can be reassigned; active ownership is preserved')
            assigned = self.assignment(request.get('actor'))
            if data['phase'] == 'test' and any(self.task(p)[0].assignee == assigned for p in data['inputs']):
                raise ValueError('Independent Test needs a different agent')
            if not self.kb.reassign_task(self.conn, task_id, assigned):
                raise ValueError('Task changed during reassignment')
            return
        if action not in ('approve', 'correct'):
            raise ValueError('Unknown action')
        submission = self.receipt(task_id, 'submission')
        if task.status != 'review' or not submission or submission['id'] != request.get('submission_id'):
            raise ValueError('Review changed; refresh before deciding')
        note = request.get('note', '')
        if action == 'correct':
            note = nonblank(note, 'Correction')
            self.kb.add_comment(self.conn, task_id, 'human', note)
            if not self.kb.reopen_review_task(self.conn, task_id):
                raise ValueError('Review changed; refresh')
        else:
            self.current(task_id)
            scope = 'manuscript claim review' if data['phase'] == 'test' else 'internal research only'
            receipt = {'kind': 'approval', 'submission_id': submission['id'], 'scope': scope,
                       'note': str(note)[:10000], 'actor': 'human'}
            if not self.kb.complete_task(self.conn, task_id, summary=f'Human approved: {scope}',
                                         metadata={'research_dbtl': receipt}):
                raise ValueError('Task changed during approval')
            self.kb.add_comment(self.conn, task_id, 'human', f'Approved {submission["id"][:8]}: {scope}. {receipt["note"]}')


def server_for(project, port=0):
    token = secrets.token_urlsafe(32)
    assets = Path(__file__).resolve().parents[1] / 'assets'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Avoid task contents or capability URLs in access logs.

        def respond(self, code, body, content_type='application/json'):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, mutation=False):
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != host:
                self.respond(403, {'error': 'Invalid local host'})
                return False
            if mutation and self.headers.get('Origin') != 'http://' + host:
                self.respond(403, {'error': 'Only the local review panel may make decisions'})
                return False
            if self.path.startswith('/api/') and not secrets.compare_digest(
                    self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.respond(401, {'error': 'Open the URL printed by the local server'})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            try:
                if self.path == '/api/snapshot':
                    self.respond(200, project.snapshot())
                elif self.path in ('/', '/index.html', '/app.js', '/style.css', '/board-model.js', '/settings.js'):
                    filename = 'index.html' if self.path == '/' else self.path[1:]
                    mime = {'html': 'text/html; charset=utf-8', 'js': 'text/javascript; charset=utf-8', 'css': 'text/css; charset=utf-8'}
                    self.respond(200, (assets / filename).read_bytes(), mime[filename.rsplit('.', 1)[1]])
                else:
                    self.respond(404, {'error': 'Not found'})
            except (ValueError, OSError) as exc:
                self.respond(400, {'error': str(exc)})

        def do_POST(self):
            if not self.allowed(mutation=True):
                return
            if self.path != '/api/action':
                self.respond(404, {'error': 'Not found'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= REQUEST_BYTES or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Expected a bounded JSON request')
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError('Expected a JSON object')
                limit = 100000 if request.get('action') in ('agent-settings', 'task-settings') else 20000
                if request.get('action') != 'avatars' and length > limit:
                    raise ValueError('Expected a bounded JSON request')
                project.action(request)
                self.respond(200, project.snapshot())
            except (ValueError, OSError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})

    server = HTTPServer(('127.0.0.1', port), Handler)
    return server, f'http://127.0.0.1:{server.server_port}/#token={token}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--name', required=True)
    init.add_argument('--board', required=True)
    commands.add_parser('status')
    history = commands.add_parser('record-build-completion')
    history.add_argument('--task', required=True)
    history.add_argument('--actor', choices=sorted(ACTORS), required=True)
    history.add_argument('--completed-on', required=True)
    history.add_argument('--note', required=True)
    learn_history = commands.add_parser('record-learn-completion')
    learn_history.add_argument('--task', required=True)
    learn_history.add_argument('--actor', choices=sorted(ACTORS), required=True)
    learn_history.add_argument('--completed-on', required=True)
    learn_history.add_argument('--note', required=True)
    learn_history.add_argument('--build', required=True)
    create = commands.add_parser('create')
    create.add_argument('--phase', choices=PHASES, required=True)
    create.add_argument('--title', required=True)
    create.add_argument('--brief', required=True)
    create.add_argument('--parent', action='append', default=[])
    create.add_argument('--claim', default='')
    create.add_argument('--cycle', type=int, default=1)
    claim = commands.add_parser('claim')
    claim.add_argument('--task', required=True)
    claim.add_argument('--actor', choices=sorted(ACTORS), required=True)
    for command in ('heartbeat', 'submit'):
        cmd = commands.add_parser(command)
        cmd.add_argument('--task', required=True)
        cmd.add_argument('--token', required=True)
        cmd.add_argument('--run', type=int, required=True)
        if command == 'submit':
            cmd.add_argument('--summary', required=True)
            cmd.add_argument('--artifact', action='append', required=True)
    recover = commands.add_parser('recover')
    recover.add_argument('--task', required=True)
    recover.add_argument('--note', required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    project = None
    try:
        if args.command == 'init':
            output = initialize(args.project, args.name, args.board)
        else:
            project = Project(args.project)
            if args.command == 'status':
                output = project.snapshot()
            elif args.command == 'record-build-completion':
                output = project.record_build_completion(args.task, args.actor, args.completed_on, args.note)
            elif args.command == 'record-learn-completion':
                output = project.record_learn_completion(args.task, args.actor, args.completed_on, args.note, args.build)
            elif args.command == 'create':
                output = {'task_id': project.create(args.phase, args.title, args.brief, args.parent, args.claim, args.cycle)}
            elif args.command == 'claim':
                output = project.claim(args.task, args.actor)
            elif args.command == 'heartbeat':
                output = project.heartbeat(args.task, args.token, args.run)
            elif args.command == 'recover':
                output = project.recover(args.task, args.note)
            elif args.command == 'submit':
                output = project.submit(args.task, args.token, args.run, args.summary, args.artifact)
            else:
                server, url = server_for(project, args.port)
                print(url, flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
                return
        print(json.dumps(output, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    finally:
        if project:
            project.close()


if __name__ == '__main__':
    main()
