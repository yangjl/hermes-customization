'use strict';
// Settings are handed to the assigned harness; the panel never launches it.
const settingLabels = {folder: 'Working folder', repo: 'Repository', skills: 'Skills', instructions: 'Instructions'};
const settingLimits = {folder: 2000, repo: 2000, skills: 2000, instructions: 10000};
let settingsScope = null, settingsFocus = null;
function settingsList(values, overrides) {
  const list = el('dl', null, 'settings-summary');
  for (const [key, label] of Object.entries(settingLabels)) {
    list.append(el('dt', label + (overrides ? (Object.hasOwn(overrides,key) ? ' · Task override' : ' · Agent default') : '')),
      el('dd', values[key] || 'None'));
  }
  return list;
}
function appendTaskSettings(detail, task) {
  if (!task.settings) return;
  const content = [el('p', 'Settings for the next run. Saved changes do not alter existing results.'),
    settingsList(task.settings.effective, task.settings.overrides),
    button('Edit task settings', () => openSettings({task: task.id, actor: task.actor}), 'secondary')];
  const recorded = task.status === 'running' ? task.run_context?.settings : task.submission?.settings;
  if (recorded) content.push(disclosure(task.status === 'running' ? 'Current run settings · fixed at claim' : 'Submitted run settings', [settingsList(recorded)]));
  else if (task.submission || task.status === 'running') content.push(el('p', 'Execution settings were not recorded for this earlier run.', 'muted'));
  const box = disclosure('Task settings · ' + (actorNames[task.actor] || task.actor), content);
  box.id = 'task-settings'; detail.append(box);
}
function openSettings(scope) {
  if (busy || !snapshot) return;
  if (!$('settings-dialog').open) settingsFocus = document.activeElement;
  settingsScope = scope;
  $('settings-fields').replaceChildren(); $('settings-agents').replaceChildren();
  showError('', 'settings-error'); $('settings-save').hidden = !scope;
  $('settings-title').textContent = scope ? (scope.task ? 'Task settings' : 'Agent defaults · ' + actorNames[scope.actor]) : 'Agent defaults';
  $('settings-description').textContent = scope ? (scope.task ? 'Uncheck a field to override the agent default for this task.' : 'Defaults in this project. Tasks inherit each field unless overridden.') : 'Choose an agent to set its working context in this project.';
  if (!scope) {
    for (const actor of Object.keys(actorNames)) $('settings-agents').append(button(actorNames[actor], () => openSettings({actor}), 'agent-tab'));
  } else {
    const task = scope.task ? snapshot.tasks.find(task => task.id === scope.task) : null;
    const current = task ? task.settings : snapshot.project.agent_settings[scope.actor];
    scope.version = current.version;
    if (task) $('settings-description').textContent = `Cycle ${task.cycle} · ${task.title}. Uncheck a field to override ${actorNames[scope.actor]} defaults.`;
    for (const [key, label] of Object.entries(settingLabels)) {
      const field = el('fieldset', null, 'execution-field'), name = el('label', label);
      name.htmlFor = 'setting-' + key;
      const input = el(key === 'instructions' ? 'textarea' : 'input');
      if (key !== 'instructions') input.type = 'text';
      input.id = 'setting-' + key; input.maxLength = settingLimits[key]; input.value = current.effective[key];
      if (key === 'folder') input.required = true;
      field.append(name);
      if (task) {
        const inherited = el('input'); inherited.type = 'checkbox'; inherited.id = 'inherit-' + key;
        inherited.checked = !Object.hasOwn(current.overrides,key); input.disabled = inherited.checked;
        const toggle = el('label', null, 'inherit-setting');
        toggle.append(inherited, document.createTextNode(`Use ${actorNames[scope.actor]} default for ${label.toLowerCase()}`));
        inherited.addEventListener('change', () => {input.disabled = inherited.checked; if(inherited.checked) input.value = current.defaults[key];});
        field.append(toggle);
      }
      field.append(input);
      if (key === 'skills') field.append(el('small', 'Separate skill names or paths with commas.'));
      if (key === 'repo') field.append(el('small', 'Local repository path or repository URL.'));
      if (key === 'folder') field.append(el('small', 'Absolute local path. Evidence stays in this research project.'));
      $('settings-fields').append(field);
    }
    $('settings-fields').append(el('p', 'Saving sets context for future claims. Existing runs keep their settings. It does not start a worker or clone a repository.', 'muted'));
  }
  if (!$('settings-dialog').open) $('settings-dialog').showModal();
  else $('settings-dialog').querySelector('input:not(:disabled),textarea:not(:disabled),button')?.focus();
}
function closeSettings() {
  if (busy) return;
  $('settings-dialog').close(); if (settingsFocus?.isConnected) settingsFocus.focus();
}
$('settings-button').addEventListener('click', () => openSettings(null));
$('settings-cancel').addEventListener('click', closeSettings);
$('settings-dialog').addEventListener('cancel', event => {event.preventDefault(); closeSettings();});
$('settings-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !settingsScope) return;
  const scope = {...settingsScope}, settings = {};
  for (const key of Object.keys(settingLabels)) {
    if (!scope.task || !$('inherit-' + key).checked) settings[key] = $('setting-' + key).value.trim();
  }
  const controls = [...$('settings-dialog').querySelectorAll('input,textarea,button')].map(node => [node, node.disabled]);
  showError('', 'settings-error'); setBusy(true); for (const [node] of controls) node.disabled = true;
  let saved = false;
  try {
    snapshot = await api('/api/action', {action: scope.task ? 'task-settings' : 'agent-settings',
      ...(scope.task ? {task_id: scope.task} : {actor: scope.actor}), version: scope.version, settings});
    render(); $('settings-dialog').close(); saved = true;
    $('announcement').textContent = scope.task ? 'Task settings saved for the next run.' : 'Agent defaults saved. Existing runs keep their settings.';
  } catch (error) {showError(error.message + ' Close and refresh before retrying if the outcome is uncertain.', 'settings-error');}
  finally {
    for (const [node, disabled] of controls) node.disabled = disabled;
    setBusy(false);
    if (saved && scope.task && $('task-settings')) { $('task-settings').open = true; $('task-settings').querySelector('summary').focus(); }
    else if(saved) $('settings-button').focus();
    else $('settings-save').focus();
  }
});
