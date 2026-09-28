'use strict';

// ponytail: one local project and manual refresh; native Kanban owns task state.
const $ = id => document.getElementById(id);
const phases = {
  design: ['Design', 'blue', 'pen'], build: ['Build', 'green', 'tool'],
  test: ['Test', 'purple', 'flask'], learn: ['Learn', 'amber', 'book'],
};
const actorNames = {codex: 'Codex', claude: 'Claude', hermes: 'Hermes'};
const paths = {
  pen: 'M12 19H5v-7L16 1l7 7L12 19Z M14 3l7 7 M5 12l7 7',
  tool: 'M14 6a5 5 0 0 0-6 6L2 18l4 4 6-6a5 5 0 0 0 6-6l-3 3-4-4 3-3Z',
  flask: 'M9 2h6 M10 2v7L4 19q-1 3 2 3h12q3 0 2-3L14 9V2 M7 15h10',
  book: 'M3 3h7q2 0 2 2v17q0-3-3-3H3V3Z M21 3h-7q-2 0-2 2 M21 3v16h-6q-3 0-3 3',
  check: 'm5 12 4 4L19 6', clock: 'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  lock: 'M7 10V7a5 5 0 0 1 10 0v3 M5 10h14v11H5Z',
  alert: 'm12 3 10 18H2L12 3Z M12 9v5 M12 17v1',
  arrow: 'M4 12h16 m-6-6 6 6-6 6', repeat: 'M20 7a9 9 0 1 0 1 10 M20 2v6h-6',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  play: 'm8 4 12 8-12 8V4Z', file: 'M5 2h9l5 5v15H5Z M14 2v6h5 M8 13h8 M8 17h5',
};
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
};
function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [key, value] of Object.entries({viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true'})) svg.setAttribute(key, value);
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', paths[name] || paths.file);
  svg.append(path);
  return svg;
}
function button(label, onClick, className, glyph) {
  const node = el('button', null, className);
  node.type = 'button';
  if (glyph) node.append(icon(glyph));
  node.append(document.createTextNode(label));
  node.addEventListener('click', onClick);
  return node;
}
function badge(task) {
  const states = {
    ready: ['Ready', 'blue', 'arrow'], todo: ['Waiting', 'gray', 'lock'],
    running: ['Working', 'blue', 'play'], review: ['Review', 'amber', 'eye'],
    done: [task.completion ? 'Completed' : 'Approved', 'green', 'check'], blocked: ['Blocked', 'gray', 'lock'],
  };
  const [label, tone, glyph] = task.stale ? ['Stale', 'red', 'alert'] : (states[task.status] || [task.status, 'gray', 'clock']);
  const node = el('span', null, `badge ${tone}`);
  node.append(icon(glyph), document.createTextNode(label));
  return node;
}
function avatar(actor, collection = snapshot?.project.avatars || {}) {
  const node = el('span', null, `avatar ${actorNames[actor] ? actor : ''}`);
  node.setAttribute('aria-hidden', 'true');
  const fallback = () => node.replaceChildren(document.createTextNode({codex: 'Cx', claude: 'Cl', hermes: 'H'}[actor] || '?'));
  if (collection[actor]) {
    const image = el('img');
    image.alt = '';
    image.addEventListener('error', fallback, {once: true});
    image.src = collection[actor];
    node.append(image);
  } else fallback();
  return node;
}
function owner(actor) {
  const node = el('span', null, 'owner');
  node.append(avatar(actor), document.createTextNode(actorNames[actor] || actor || 'Unassigned'));
  return node;
}
function disclosure(label, children) {
  const node = el('details');
  node.append(el('summary', label), ...children);
  return node;
}
function selectActor(value, id) {
  const select = el('select');
  select.id = id;
  for (const [key, name] of Object.entries(actorNames)) {
    const option = el('option', name);
    option.value = key;
    select.append(option);
  }
  select.value = value;
  return select;
}

let token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
try {
  if (token) sessionStorage.setItem('research-dbtl-token', token);
  else token = sessionStorage.getItem('research-dbtl-token') || '';
} catch { /* The current tab still works when browser storage is unavailable. */ }
if (location.hash) history.replaceState(null, '', location.pathname + location.search);
let snapshot = null;
let selectedId = null;
let busy = false;
let historyProject = null, historyOpen = false;
const openCycles = new Set();

async function api(path, data) {
  if (!token) throw new Error('Session key missing. Open the full URL printed by the DBTL server.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, {
      method: data ? 'POST' : 'GET', cache: 'no-store', credentials: 'omit',
      headers: {'Authorization': `Bearer ${token}`, ...(data ? {'Content-Type': 'application/json'} : {})},
      body: data ? JSON.stringify(data) : undefined, signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok || result.error) throw new Error(result.error || `Request failed (${response.status}).`);
    if (!result.project || !Array.isArray(result.tasks)) throw new Error('Unexpected response. Restart the DBTL server and refresh.');
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The local server did not respond. Check it is running, then retry.');
    if (error instanceof TypeError) throw new Error('Cannot reach the local server. Check it is running, then retry.');
    throw error;
  } finally { clearTimeout(timer); }
}
function showError(message, target = 'error') {
  $(target).textContent = message;
  $(target).hidden = !message;
}
function setBusy(value) {
  busy = value;
  $('refresh').disabled = value;
  $('roles-button').disabled = value || !snapshot;
  $('avatars-button').disabled = value || !snapshot;
  $('settings-button').disabled = value || !snapshot;
  $('active-button').disabled = value || !snapshot || !groupCycles(snapshot.tasks).some(group => !group.completed);
  $('save-roles').disabled = value;
  $('close-roles').disabled = value;
  $('board').setAttribute('aria-busy', String(value));
  for (const node of $('detail').querySelectorAll('button, select, textarea')) node.disabled = value || node.dataset.unavailable === 'true';
}
function focusDetail() {
  $('detail').querySelector('h2')?.focus({preventScroll: true});
  if (innerWidth <= 740) $('detail').scrollIntoView({block: 'start'});
}
function showTask(id) {
  if (busy) return;
  selectedId = id;
  const group = groupCycles(snapshot.tasks).find(group => group.completed && group.tasks.some(task => task.id === id));
  if (group) { historyOpen = true; openCycles.add(group.cycle); }
  render();
  focusDetail();
}
function renderPaused(title, text, failure = false) {
  $('decision').className = 'decision';
  $('decision').replaceChildren(el('h2', 'Decisions paused'));
  const empty = el('div', null, 'empty');
  empty.append(icon(failure ? 'alert' : 'clock'), el('h2', title), el('p', text));
  if (failure) empty.append(button('Retry', refresh));
  $('board').replaceChildren(empty);
  $('completed-cycles').hidden = true;
  $('completed-list').replaceChildren();
  const heading = el('h2', 'No card selected');
  heading.tabIndex = -1;
  $('detail').replaceChildren(heading);
}
function render() {
  if (!snapshot) return;
  const {project, tasks} = snapshot;
  const groups = groupCycles(tasks), activeTasks = groups.filter(group => !group.completed).flatMap(group => group.tasks);
  if (historyProject !== project.id) {
    historyProject = project.id; openCycles.clear(); historyOpen = false;
    try { historyOpen = localStorage.getItem('dbtl-history-' + project.id) === 'open'; } catch {}
  }
  if (!tasks.some(task => task.id === selectedId)) selectedId = activeTasks.find(task => task.status === 'review')?.id || activeTasks[0]?.id || tasks[0]?.id || null;
  $('project-name').textContent = project.name;
  $('board-name').textContent = project.board;
  $('agents').replaceChildren();
  for (const role of ['coordinator', 'design', 'build', 'test', 'learn']) {
    const chip = el('span', null, 'agent');
    chip.append(document.createTextNode(`${role === 'coordinator' ? 'Lead' : phases[role][0]} · `), owner(project.roles[role]));
    $('agents').append(chip);
  }
  const cycles = new Set(tasks.map(task => task.cycle));
  $('cycle-summary').textContent = tasks.length ? `${groups.filter(group => !group.completed).length} active cycles · ${groups.filter(group => group.completed).length} completed cycles · ${tasks.length} tasks` : 'No active cycle';
  const needsReview = tasks.filter(task => task.status === 'review');
  const stale = tasks.find(task => task.stale);
  const next = needsReview.find(task => !task.stale) || needsReview[0] || stale;
  const decision = $('decision');
  decision.className = `decision${next ? '' : ' clear'}`;
  const lead = el('div', null, 'lead');
  const message = el('div');
  message.append(el('h2', next ? (next.stale ? 'Evidence changed' : `Your review · ${needsReview.length}`) : tasks.length ? 'No decisions waiting' : 'Start with a research question'), el('small', next ? next.title : tasks.length ? 'Refresh after the next worker submission.' : 'Create a task in Codex.'));
  lead.append(icon(next ? (next.stale ? 'alert' : 'eye') : 'check'), message);
  decision.replaceChildren(lead);
  if (next) decision.append(button('Open', () => showTask(next.id), null, 'arrow'));
  $('board').replaceChildren();
  for (const [phase, [name, tone, glyph]] of Object.entries(phases)) {
    const lane = el('div', null, 'lane');
    const heading = el('div', null, 'lane-head');
    const stage = el('span', null, `stage-icon ${tone}`);
    stage.append(icon(glyph));
    const phaseTasks = activeTasks.filter(task => task.phase === phase);
    heading.append(stage, el('h2', name), el('small', phaseTasks.length));
    lane.append(heading);
    for (const task of phaseTasks) {
      lane.append(taskCard(task));
    }
    if (!phaseTasks.length) {
      const empty = el('div', null, 'conditional');
      empty.append(icon(glyph), el('strong', phase === 'test' ? 'Manuscript only' : 'No active tasks'), el('small', phase === 'test' ? 'Selected claims only' : 'Completed work is folded below'));
      lane.append(empty);
    }
    $('board').append(lane);
  }
  renderCycles(groups);
  renderDetail(tasks.find(task => task.id === selectedId));
}
function taskCard(task) {
  const card = button('', () => showTask(task.id), 'card');
  card.dataset.taskId = task.id;
  card.setAttribute('aria-pressed', String(task.id === selectedId));
  card.setAttribute('aria-controls', 'detail');
  const footer = el('span', null, 'card-footer');
  footer.append(owner(task.actor), el('span', `Cycle ${task.cycle} · ${phases[task.phase][0]}`));
  card.append(badge(task), el('strong', task.title), footer);
  return card;
}
function renderCycles(groups) {
  const completed = groups.filter(group => group.completed).sort((a,b) => b.cycle-a.cycle);
  $('completed-cycles').hidden = !completed.length;
  $('completed-cycles').open = historyOpen;
  $('completed-summary').textContent = `Completed cycles (${completed.length})`;
  $('completed-list').replaceChildren();
  for (const group of completed) {
    const counts = Object.keys(phases).filter(phase => group.tasks.some(task => task.phase === phase))
      .map(phase => `${phases[phase][0]} ${group.tasks.filter(task => task.phase === phase).length}`).join(' · ');
    const record = el('details', null, 'cycle-record'); record.dataset.cycle = group.cycle;
    const summary = el('summary'), row = el('span', null, 'cycle-record-row');
    row.append(el('strong', `Cycle ${group.cycle}`), el('small', counts + ' · Completed')); summary.append(row);
    const cards = el('div', null, 'cycle-cards');
    for (const task of group.tasks) cards.append(taskCard(task));
    record.append(summary, cards); record.open = openCycles.has(group.cycle);
    record.addEventListener('toggle', () => { if (!record.isConnected) return; if(record.open) openCycles.add(group.cycle); else openCycles.delete(group.cycle); });
    $('completed-list').append(record);
  }
}
$('completed-cycles').addEventListener('toggle', () => {
  historyOpen = $('completed-cycles').open;
  if (historyProject) try {localStorage.setItem('dbtl-history-' + historyProject, historyOpen ? 'open' : 'closed');} catch {}
});
$('active-button').addEventListener('click', () => {
  const active = groupCycles(snapshot?.tasks || []).filter(group => !group.completed).flatMap(group => group.tasks);
  const task = active.find(task => task.status === 'review') || active[0]; if (task) showTask(task.id);
});
function renderDetail(task) {
  const detail = $('detail');
  detail.replaceChildren();
  const heading = el('h2', task ? task.title : 'No card selected');
  heading.tabIndex = -1;
  if (!task) { detail.append(heading, el('p', 'Create a task in Codex, then refresh.')); return; }
  detail.append(button('← Board', () => {
    const group = groupCycles(snapshot.tasks).find(group => group.completed && group.tasks.some(item => item.id === task.id));
    if (group) { historyOpen = true; openCycles.add(group.cycle); render(); }
    [...document.querySelectorAll('[data-task-id]')].find(card => card.dataset.taskId === task.id)?.focus();
  }, 'back'));
  const top = el('div', null, 'detail-top');
  top.append(owner(task.actor), el('small', `Cycle ${task.cycle} · ${phases[task.phase]?.[0] || task.phase}`));
  detail.append(top, heading, badge(task));
  const scope = el('p', null, 'scope');
  scope.append(icon('lock'), document.createTextNode(task.completion ? `Historical ${phases[task.phase][0]} · completed ${task.completion.completed_on} · development evidence` : task.phase === 'test' ? 'Manuscript claim review · human decision' : 'Internal development · no manuscript admission'));
  detail.append(scope);
  if (task.claim) detail.append(el('div', `Claim: ${task.claim}`, 'change'));
  if (task.completion) {
    detail.append(el('div', task.completion.summary, 'change'));
    detail.append(el('p', 'Completion records previous work. It does not approve a new run or validate a manuscript claim.', 'note'));
    if (task.completion.source_build) detail.append(button('Open source Build', () => showTask(task.completion.source_build.task_id), 'secondary', 'arrow'));
    if (task.submission) detail.append(disclosure('Original reconstruction submission', [el('p', task.submission.summary)]));
  }
  else if (task.submission) detail.append(el('div', task.submission.summary, 'change'));
  else if (task.brief) detail.append(el('div', task.brief, 'change'));
  if (task.stale || task.problem) detail.append(el('div', task.problem || 'Evidence changed. Request a new submission before approval.', 'note'));
  if (task.status === 'review' && task.submission) {
    const label = el('label', 'Decision note', 'note-label');
    label.htmlFor = 'decision-note';
    const note = el('textarea');
    note.id = 'decision-note';
    note.placeholder = 'Required for corrections';
    note.maxLength = 4000;
    detail.append(label, note);
    const approve = button('Approve submission', () => mutate({action: 'approve', task_id: task.id, submission_id: task.submission.id, note: note.value.trim()}, 'Submission approved.'), 'primary', 'check');
    approve.disabled = task.stale || !!task.problem;
    approve.dataset.unavailable = String(approve.disabled);
    const correct = button('Request correction', () => {
      if (!note.value.trim()) { note.setCustomValidity('Describe the correction.'); note.reportValidity(); note.focus(); return; }
      mutate({action: 'correct', task_id: task.id, submission_id: task.submission.id, note: note.value.trim()}, 'Correction requested.');
    }, 'secondary', 'repeat');
    note.addEventListener('input', () => note.setCustomValidity(''));
    detail.append(approve, correct);
  }
  if (task.submission) {
    const evidence = [];
    for (const artifact of task.submission.artifacts || []) {
      const item = el('div', null, 'artifact');
      item.append(el('strong', artifact.path), el('span', `SHA-256 ${artifact.sha256}`, 'file'), el('small', `${artifact.size} bytes`));
      evidence.push(item);
    }
    if (!evidence.length) evidence.push(el('p', 'No files attached.'));
    evidence.unshift(el('span', `Submission ${task.submission.id}`, 'file'));
    const artifactCount = task.submission.artifacts?.length || 0;
    detail.append(disclosure(`Evidence · ${artifactCount} file${artifactCount === 1 ? '' : 's'}`, evidence));
  }
  const assignment = [el('p', task.brief || 'No brief recorded.'), el('span', task.id, 'file')];
  if (task.parents?.length) assignment.push(el('p', `Inputs: ${task.parents.join(', ')}`));
  if (['ready', 'todo'].includes(task.status)) {
    const label = el('label', 'Task owner', 'note-label');
    label.htmlFor = 'task-owner';
    const select = selectActor(task.actor, 'task-owner');
    assignment.push(label, select, button('Reassign task', () => mutate({action: 'reassign', task_id: task.id, actor: select.value}, 'Task reassigned.'), 'secondary'));
  }
  detail.append(disclosure('Assignment', assignment));
  appendTaskSettings(detail, task);
  const list = el('ol', null, 'history');
  for (const event of task.history || []) {
    const item = el('li');
    item.append(el('strong', event.author), el('small', event.created_at), el('p', event.body));
    list.append(item);
  }
  detail.append(disclosure(`History · ${task.history?.length || 0}`, [list]));
}
async function refresh() {
  if (busy) return;
  showError('');
  $('announcement').textContent = 'Refreshing…';
  setBusy(true);
  try {
    snapshot = await api('/api/snapshot');
    render();
    $('announcement').textContent = 'Up to date.';
  } catch (error) {
    snapshot = null;
    renderPaused('Records unavailable', error.message, true);
    $('announcement').textContent = '';
    showError(error.message);
  } finally { setBusy(false); $('refresh').focus({preventScroll: true}); }
}
async function mutate(action, message) {
  if (busy) return;
  const previousFocus = document.activeElement;
  showError('');
  setBusy(true);
  try {
    snapshot = await api('/api/action', action);
    render();
    $('announcement').textContent = message;
    focusDetail();
  } catch (error) {
    showError(`${error.message} Refresh before retrying if the outcome is uncertain.`);
  } finally {
    setBusy(false);
    if (previousFocus?.isConnected) previousFocus.focus({preventScroll: true});
  }
}
$('refresh').addEventListener('click', refresh);
$('roles-button').addEventListener('click', () => {
  if (!snapshot || busy) return;
  $('role-fields').replaceChildren();
  for (const role of ['coordinator', ...Object.keys(phases)]) {
    const label = el('label', role === 'coordinator' ? 'Coordinator' : phases[role][0], 'field');
    label.append(selectActor(snapshot.project.roles[role], `role-${role}`));
    $('role-fields').append(label);
  }
  showError('', 'roles-error');
  $('roles-dialog').showModal();
});
$('close-roles').addEventListener('click', () => $('roles-dialog').close());
$('roles-dialog').addEventListener('cancel', event => { if (busy) event.preventDefault(); });
$('roles-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const roles = Object.fromEntries(['coordinator', ...Object.keys(phases)].map(role => [role, $(`role-${role}`).value]));
  showError('', 'roles-error');
  setBusy(true);
  try {
    snapshot = await api('/api/action', {action: 'roles', roles});
    render();
    $('roles-dialog').close();
    $('announcement').textContent = 'Role defaults saved. Existing task owners are unchanged.';
  } catch (error) { showError(error.message, 'roles-error'); }
  finally { setBusy(false); if (!$('roles-dialog').open) $('roles-button').focus(); }
});
// ponytail: one small PNG per agent in the existing private project config.
let avatarDraft = {}, avatarOriginal = {}, avatarAgent = 'codex';
let avatarVersion = 0, avatarDecoding = false, avatarSaving = false;
function renderAvatarEditor() {
  $('avatar-tabs').replaceChildren();
  for (const actor of Object.keys(actorNames)) {
    const tab = button('', () => {
      if (avatarSaving) return;
      avatarVersion++;
      avatarDecoding = false;
      avatarAgent = actor;
      showError('', 'avatars-error');
      renderAvatarEditor();
      $('avatar-tabs').querySelector(`[data-agent="${actor}"]`).focus();
    }, 'agent-tab');
    tab.dataset.agent = actor;
    tab.setAttribute('aria-pressed', String(actor === avatarAgent));
    tab.disabled = avatarSaving;
    tab.append(avatar(actor, avatarDraft), el('span', actorNames[actor]));
    $('avatar-tabs').append(tab);
  }
  $('large-avatar').replaceChildren(avatar(avatarAgent, avatarDraft));
  $('avatar-agent-name').textContent = actorNames[avatarAgent];
  $('upload-avatar').disabled = avatarDecoding || avatarSaving;
  $('remove-avatar').disabled = avatarDecoding || avatarSaving || !avatarDraft[avatarAgent];
  $('save-avatars').disabled = avatarDecoding || avatarSaving;
  $('cancel-avatars').disabled = avatarSaving;
  $('avatar-loading').textContent = avatarSaving ? 'Saving avatars…' : avatarDecoding ? 'Loading picture…' : '';
}
function closeAvatars() {
  if (avatarSaving) return;
  avatarVersion++;
  avatarDecoding = false;
  $('avatars-dialog').close();
  $('avatars-button').focus();
}
$('avatars-button').addEventListener('click', () => {
  if (!snapshot || busy) return;
  avatarOriginal = {...snapshot.project.avatars};
  avatarDraft = {...avatarOriginal};
  avatarAgent = 'codex';
  showError('', 'avatars-error');
  renderAvatarEditor();
  $('avatars-dialog').showModal();
});
$('cancel-avatars').addEventListener('click', closeAvatars);
$('avatars-dialog').addEventListener('cancel', event => { event.preventDefault(); closeAvatars(); });
$('upload-avatar').addEventListener('click', () => { $('avatar-file').value = ''; $('avatar-file').click(); });
$('remove-avatar').addEventListener('click', () => {
  avatarVersion++;
  avatarDraft[avatarAgent] = null;
  showError('', 'avatars-error');
  renderAvatarEditor();
  $('upload-avatar').focus();
});
$('avatar-file').addEventListener('change', async () => {
  const file = $('avatar-file').files[0];
  if (!file || avatarSaving || !$('avatars-dialog').open) return;
  const request = ++avatarVersion, actor = avatarAgent;
  showError('', 'avatars-error');
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
    showError('Choose a PNG, JPG or WebP image under 5 MB.', 'avatars-error');
    return;
  }
  avatarDecoding = true;
  renderAvatarEditor();
  let url;
  try {
    url = URL.createObjectURL(file);
    const image = new Image();
    image.src = url;
    await image.decode();
    if (request !== avatarVersion) return;
    if (!image.naturalWidth || !image.naturalHeight) throw new Error('Empty image');
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const size = Math.min(image.naturalWidth, image.naturalHeight);
    canvas.getContext('2d').drawImage(image, (image.naturalWidth - size) / 2, (image.naturalHeight - size) / 2, size, size, 0, 0, 256, 256);
    avatarDraft[actor] = canvas.toDataURL('image/png');
  } catch {
    if (request === avatarVersion) showError('This image could not be opened. Try another picture.', 'avatars-error');
  } finally {
    if (url) URL.revokeObjectURL(url);
    if (request === avatarVersion) {
      avatarDecoding = false;
      renderAvatarEditor();
      $('upload-avatar').focus();
    }
  }
});
$('save-avatars').addEventListener('click', async () => {
  if (busy || avatarDecoding || avatarSaving) return;
  // Send only edited actors so another editor's unrelated changes survive.
  const avatars = Object.fromEntries(Object.keys(actorNames)
    .filter(actor => (avatarDraft[actor] || null) !== (avatarOriginal[actor] || null))
    .map(actor => [actor, avatarDraft[actor] || null]));
  if (!Object.keys(avatars).length) { closeAvatars(); return; }
  avatarSaving = true;
  setBusy(true);
  showError('', 'avatars-error');
  renderAvatarEditor();
  try {
    snapshot = await api('/api/action', {action: 'avatars', avatars});
    render();
    avatarSaving = false;
    $('avatars-dialog').close();
    $('announcement').textContent = 'Agent avatars saved.';
  } catch (error) { showError(error.message, 'avatars-error'); }
  finally {
    avatarSaving = false;
    setBusy(false);
    renderAvatarEditor();
    if ($('avatars-dialog').open) $('save-avatars').focus();
    else $('avatars-button').focus();
  }
});
renderPaused('Loading evidence…', 'Connecting to the local project.');
document.addEventListener('DOMContentLoaded', refresh, {once: true});
