import {
  Button,
  Codicon,
  EmptyState,
  ErrorState,
  host,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  Tip,
  useMutation,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'project-kanban'
const lanes = [
  { id: 'next', label: 'Next', icon: 'arrow-right', token: '--ui-blue' },
  { id: 'doing', label: 'Doing', icon: 'play', token: '--ui-green' },
  { id: 'waiting', label: 'Waiting', icon: 'clock', token: '--ui-orange' },
  { id: 'review', label: 'Review', icon: 'eye', token: '--ui-purple' }
]
const categories = [
  { id: 'main-research', label: 'Main research', icon: 'beaker', token: '--ui-blue' },
  { id: 'student-projects', label: 'Student projects', icon: 'mortar-board', token: '--ui-green' },
  { id: 'systems-admin', label: 'Systems / admin', icon: 'tools', token: '--ui-purple' }
]
const legacyCategory = { id: 'legacy', label: 'Legacy / unlinked', icon: 'history', token: '--ui-text-tertiary' }
const boardCategories = [...categories, legacyCategory]
const categoryOf = item => boardCategories.find(category => category.id === item.category) || legacyCategory
const sourceIcons = { email: 'mail', slack: 'comment-discussion', telegram: 'send', github: 'git-branch', manual: 'edit' }
// The MVP's per-card priority tag. Native lifecycle cards carry the signal that
// raised them; human-managed cards are only tagged once someone says so.
const priorityTags = { github: 'Git activity', email: 'Request', slack: 'Request', telegram: 'Capture' }

// Theme-adaptive colour: a soft fill of the hue, and an ink mixed toward the
// body text so it stays legible in both light and dark themes. Hex is banned
// here — every colour resolves from a theme token.
const tint = (token, percent) => `color-mix(in oklch, var(${token}) ${percent}%, transparent)`
const ink = token => `color-mix(in oklch, var(${token}) 70%, var(--ui-text-primary))`

function priorityOf(task) {
  return task.human_managed ? '' : priorityTags[task.source] || ''
}

function countCategories(items, ids) {
  return Object.fromEntries(ids.map(id => [id, items.filter(item => item.category === id).length]))
}

// Office Inbox's active-candidate count: captured + suggested, the same two
// stages Inbox already renders as "reviewable" work. Accepted/dismissed
// cards are session-only history, not part of the live count.
function inboxActiveCount(inbox) {
  if (!inbox?.available) return 0
  const stages = inbox.stages || {}
  return (stages.captured?.length || 0) + (stages.suggested?.length || 0)
}

function reconciliationLabel(task) {
  if (task.reconciliation === 'linked') return 'Linked to active canonical project'
  if (task.reconciliation === 'category-mismatch') return 'Legacy / unlinked · stored category disagrees with project'
  if (task.reconciliation === 'unavailable-project') return 'Legacy / unlinked · project is inactive, missing, or invalid'
  return 'Legacy / unlinked · no canonical project link'
}

function cardLinks(task) {
  const links = task.links || {}
  const project = task.project || {}
  const badges = [{ icon: 'layout', label: 'Kanban · act', token: '--ui-blue' }]
  if (project.note || links.obsidian) badges.push({ icon: 'book', label: `Obsidian · ${project.note || links.obsidian}`, token: '--ui-purple' })
  if (project.github?.repo || links.github) badges.push({ icon: 'git-branch', label: `GitHub · ${project.github?.repo || links.github}`, token: '--ui-text-tertiary' })
  return badges
}

function useWidth() {
  const [width, setWidth] = useState(() => window.innerWidth)
  useEffect(() => {
    const resize = () => setWidth(window.innerWidth)
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
  return width
}

function IconButton({ icon, label, onClick, disabled = false }) {
  return jsx(Button, {
    variant: 'ghost',
    size: 'icon',
    'aria-label': label,
    title: label,
    disabled,
    onClick,
    children: jsx(Codicon, { name: icon })
  })
}

// A small numeric badge parked on a tab's corner. Zero is hidden entirely
// rather than rendered as "0" — a quieter empty state than a visible zero.
function TabBadge({ count }) {
  if (!count) return null
  return jsx('span', {
    className: 'absolute -right-1 -top-1 grid min-w-[15px] place-items-center rounded-full bg-(--ui-bg-quaternary) px-1 text-[9px] font-bold text-(--ui-text-tertiary)',
    children: count
  })
}

function useKanbanMutation(ctx) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ path, method = 'POST', body }) => ctx.rest(path, { method, body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [ID, 'snapshot'] }),
    onError: error => host.notify({ kind: 'error', message: error?.message || 'Kanban action failed' })
  })
}

function taskTypeOf(task) {
  return task.reconciliation === 'linked' && !!task.project?.github?.repo ? 'tracked' : 'quick'
}

function TaskTypePill({ task, compact = false }) {
  const type = taskTypeOf(task)
  const token = type === 'tracked' ? '--ui-purple' : '--ui-text-tertiary'
  return jsx('span', {
    className: `shrink-0 rounded font-bold uppercase tracking-wide ${compact ? 'px-1 py-px text-[8px]' : 'px-1.5 py-0.5 text-[9px]'}`,
    style: { background: tint(token, 16), color: ink(token) },
    children: type === 'tracked' ? 'Tracked' : 'Quick'
  })
}

// Approaching-deadline threshold, confirmed by Jinliang: ≤7 days out is
// "soon"; a fixed constant, not a per-card or global setting.
const DEADLINE_SOON_DAYS = 7

function deadlineState(dueDate) {
  if (!dueDate) return null
  const due = new Date(`${dueDate}T00:00:00`)
  if (Number.isNaN(due.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((due.getTime() - today.getTime()) / 86400000)
  if (days < 0) return { tone: 'overdue', days }
  if (days <= DEADLINE_SOON_DAYS) return { tone: 'soon', days }
  return { tone: 'plenty', days }
}

function deadlineLabel(state) {
  if (state.tone === 'overdue') return `Overdue ${Math.abs(state.days)} day${Math.abs(state.days) === 1 ? '' : 's'}`
  if (state.days === 0) return 'Due today'
  return `Due in ${state.days} day${state.days === 1 ? '' : 's'}`
}

// Renders nothing (no row, no layout shift) when the card has no due_date —
// the common case today, since due_date entry UI is out of scope for this
// bundle.
function DeadlineRow({ dueDate, compact = false }) {
  const state = deadlineState(dueDate)
  if (!state) return null
  const token = state.tone === 'overdue' ? '--ui-red' : state.tone === 'soon' ? '--ui-orange' : '--ui-text-tertiary'
  return jsx('div', {
    className: `flex items-center font-medium ${compact ? 'mt-1.5 gap-1 rounded px-1 py-0.5 text-[9px]' : 'mt-2 gap-1.5 rounded px-1.5 py-1 text-[10px]'}`,
    style: { background: tint(token, state.tone === 'plenty' ? 8 : 16), color: ink(token) },
    children: deadlineLabel(state)
  })
}

function TaskCard({ task, lane, mutate, onOpen, active, compact = false }) {
  const index = lanes.findIndex(item => item.id === lane)
  const move = destination => mutate.mutate({ path: `/tasks/${task.id}`, method: 'PATCH', body: { lane: destination } })
  const priority = priorityOf(task)
  const category = categoryOf(task)
  const project = task.project
  return jsxs('article', {
    'data-kanban-card': task.category,
    className: `rounded-lg border bg-(--ui-chat-surface-background) ${compact ? 'p-2' : 'p-3'} ${active ? 'border-(--ui-accent)' : 'border-(--ui-stroke-secondary)'}`,
    children: [
      jsxs('div', {
        className: 'flex items-start justify-between gap-2',
        children: [
          jsxs('span', {
            className: 'flex min-w-0 items-center gap-1.5',
            children: [
              jsx('span', {
                className: `truncate rounded font-bold uppercase tracking-wide ${compact ? 'px-1 py-px text-[8px]' : 'px-1.5 py-0.5 text-[9px]'}`,
                style: { background: tint(category.token, 16), color: ink(category.token) },
                children: task.reconciliation === 'linked' ? project?.title : category.label
              }),
              jsx(TaskTypePill, { task, compact })
            ]
          }),
          priority ? jsx('span', {
            className: 'shrink-0 text-[9px] font-bold uppercase tracking-wide',
            style: { color: ink('--ui-red') },
            children: priority
          }) : null
        ]
      }),
      jsx('button', {
        type: 'button',
        onClick: () => onOpen(task),
        className: `mt-1.5 block w-full text-left font-medium leading-snug hover:underline ${compact ? 'text-xs' : 'text-sm'}`,
        children: task.title
      }),
      compact
        ? jsx('div', { className: 'mt-1 text-[9.5px] text-(--ui-text-tertiary)', children: `Active ${relativeTime(task.created_at * 1000)}` })
        : (task.body ? jsx('p', { className: 'mt-1 line-clamp-2 text-xs leading-relaxed text-(--ui-text-secondary)', children: task.body }) : null),
      jsx(DeadlineRow, { dueDate: task.due_date, compact }),
      jsxs('div', {
        className: 'mt-2 flex items-center justify-between gap-2',
        children: [
          jsx('span', {
            className: 'flex items-center gap-1',
            children: cardLinks(task).map(badge => jsx(Tip, {
              label: badge.label,
              children: jsx('span', {
                className: 'grid size-5 place-items-center rounded border',
                style: { background: tint(badge.token, 12), borderColor: tint(badge.token, 35), color: ink(badge.token) },
                children: jsx(Codicon, { name: badge.icon })
              })
            }, badge.icon))
          }),
          task.human_managed ? jsxs('span', {
            className: 'flex items-center',
            children: [
              index > 0 ? jsx(IconButton, { icon: 'chevron-left', label: `Move ${task.title} left`, disabled: mutate.isPending, onClick: () => move(lanes[index - 1].id) }) : null,
              index < lanes.length - 1 ? jsx(IconButton, { icon: 'chevron-right', label: `Move ${task.title} right`, disabled: mutate.isPending, onClick: () => move(lanes[index + 1].id) }) : null
            ]
          }) : jsx('span', { className: 'text-[11px] text-(--ui-text-tertiary)', children: 'Native · read only' })
        ]
      })
    ]
  })
}

function TaskDetail({ task, lane, onClose, docked }) {
  const links = task.links || {}
  const category = categoryOf(task)
  const project = task.project
  const observation = project?.observation
  const rows = [
    ['Kanban', `${lanes.find(item => item.id === lane)?.label || 'Next'} · ${category.label}`],
    ['Reconciliation', reconciliationLabel(task)],
    ['Project', project?.title || 'Unlinked action'],
    ['Goal', project?.goal || 'No canonical goal linked'],
    ['Project next action', project?.next_action || 'No canonical next action linked'],
    ['Blocker', project?.blocker || 'None recorded'],
    ['Obsidian', project?.note || links.obsidian || 'No knowledge note linked'],
    ['GitHub', project?.github?.repo || links.github || 'No repository linked'],
    ['Last observed on', observation ? `${observation.device}${observation.stale ? ' · stale' : ''} · ${observation.dirty_count} dirty · ${observation.ahead} ahead` : 'No device observation'],
    ['Managed by', task.human_managed ? 'You — movable between lanes' : 'Native worker lifecycle — read only']
  ]
  return jsxs('aside', {
    'aria-label': `Details: ${task.title}`,
    className: `flex flex-col overflow-hidden border-l border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) ${docked ? 'w-80 shrink-0' : 'fixed inset-y-0 right-0 z-50 w-full max-w-sm shadow-xl'}`,
    children: [
      jsxs('div', {
        className: 'flex items-start justify-between gap-2 border-b border-(--ui-stroke-secondary) p-3',
        children: [
          jsxs('div', {
            className: 'min-w-0',
            children: [
              jsx('span', {
                className: 'inline-block rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide',
                style: { background: tint(category.token, 16), color: ink(category.token) },
                children: category.label
              }),
              jsx('h2', { className: 'mt-1.5 text-sm font-medium leading-snug', children: task.title })
            ]
          }),
          jsx(IconButton, { icon: 'close', label: 'Close details', onClick: onClose })
        ]
      }),
      jsxs('div', {
        className: 'min-h-0 flex-1 overflow-auto p-3',
        children: [
          task.body ? jsx('p', { className: 'mb-3 text-xs leading-relaxed whitespace-pre-wrap text-(--ui-text-secondary)', children: task.body }) : null,
          jsx('dl', {
            className: 'overflow-hidden rounded-md border border-(--ui-stroke-secondary)',
            children: rows.flatMap(([label, value], row) => [
              jsx('dt', { className: `bg-(--ui-bg-quinary) px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-wide text-(--ui-text-tertiary) ${row ? 'border-t border-(--ui-stroke-secondary)' : ''}`, children: label }, `${label}-l`),
              jsx('dd', { className: 'm-0 px-2.5 py-2 text-xs break-words', children: value }, `${label}-v`)
            ])
          }),
          jsx('div', {
            className: 'mt-3 rounded-r border-l-[3px] px-2.5 py-2 text-[11px] text-(--ui-text-secondary)',
            style: { background: tint('--ui-blue', 10), borderColor: ink('--ui-blue') },
            children: 'Boundary: move the work in Kanban, record reasoning in Obsidian, inspect code in GitHub. This pane links these systems; it does not copy them.'
          })
        ]
      })
    ]
  })
}

function Lane({ lane, tasks, mutate, onOpen, activeId, compact = false }) {
  return jsxs('section', {
    'data-kanban-lane': lane.id,
    className: 'min-w-0 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-quinary) p-2.5',
    children: [
      jsxs('header', {
        className: 'mb-2 flex items-center justify-between px-1',
        children: [
          jsxs('div', {
            className: 'flex items-center gap-2',
            children: [
              jsx('span', { className: 'size-2 shrink-0 rounded-full', style: { background: `var(${lane.token})` } }),
              jsx('h2', { className: 'text-sm font-medium', children: lane.label })
            ]
          }),
          jsx('span', { className: 'rounded-full bg-(--ui-bg-quaternary) px-1.5 text-xs tabular-nums text-(--ui-text-tertiary)', children: tasks.length })
        ]
      }),
      tasks.length
        ? jsx('div', { className: 'flex flex-col gap-2', children: tasks.map(task => jsx(TaskCard, { task, lane: lane.id, mutate, onOpen, active: task.id === activeId, compact }, task.id)) })
        : jsx('div', { className: 'rounded-md border border-dashed border-(--ui-stroke-secondary) px-3 py-8 text-center text-xs text-(--ui-text-tertiary)', children: 'No actions here' })
    ]
  })
}

function ActionForm({ onClose, mutate, projects }) {
  const [title, setTitle] = useState('')
  const [projectId, setProjectId] = useState(projects[0]?.project_id || '')
  const submit = async event => {
    event.preventDefault()
    if (!title.trim() || !projectId) return
    await mutate.mutateAsync({ path: '/tasks', body: { title, project_id: projectId, lane: 'next' } })
    onClose()
  }
  return jsxs('form', {
    onSubmit: submit,
    className: 'grid gap-2 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3 md:grid-cols-[minmax(0,1fr)_180px_auto]',
    children: [
      jsx('input', {
        autoFocus: true,
        value: title,
        onChange: event => setTitle(event.target.value),
        placeholder: 'Next action',
        'aria-label': 'Next action title',
        className: 'min-w-0 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm outline-none focus:border-(--ui-accent)'
      }),
      jsx('select', {
        value: projectId,
        onChange: event => setProjectId(event.target.value),
        'aria-label': 'Canonical project',
        className: 'rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm',
        children: projects.map(item => jsx('option', { value: item.project_id, children: item.title }, item.project_id))
      }),
      jsxs('div', { className: 'flex gap-1', children: [jsx(Button, { type: 'submit', disabled: mutate.isPending || !title.trim() || !projectId, children: 'Add' }), jsx(Button, { type: 'button', variant: 'ghost', onClick: onClose, children: 'Cancel' })] })
    ]
  })
}

const stagePillMeta = {
  captured: { label: 'Captured', token: '--ui-blue' },
  suggested: { label: 'Legacy suggestion', token: '--ui-orange' }
}

function relativeTime(at) {
  const seconds = Math.max(0, Math.floor((Date.now() - at) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

// Static, fixture-derived revision proposal — reuses the backend's existing
// keyword heuristic (`_suggestion` in plugin_api.py, already shipped on every
// task view as suggested_category/suggestion_reason), never a model call.
// Ships the propose -> apply-to-fields-only -> human-confirms interaction
// contract so a real suggester can replace this function later without a UI
// rework (see PK-002 plan, Non-goals).
function suggestRevision(task, projects) {
  const match = projects.find(item => item.category === task.suggested_category)
  return {
    title: task.title,
    projectId: match ? match.project_id : (projects[0]?.project_id || ''),
    projectLabel: match ? match.title : 'No canonical project match',
    reason: task.suggestion_reason || 'No additional signal available; review before accepting.'
  }
}

function InboxCard({ task, stage, mutate, projects, onAchieved }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState(task.title)
  const [projectId, setProjectId] = useState(task.project_id || projects[0]?.project_id || '')
  const [notes, setNotes] = useState(task.body || '')
  const [flash, setFlash] = useState(false)
  const [suggestion, setSuggestion] = useState(null)
  const pill = stagePillMeta[stage] || stagePillMeta.captured

  const save = async () => {
    if (!title.trim()) return
    await mutate.mutateAsync({ path: `/inbox/${task.id}`, method: 'PATCH', body: { title, project_id: projectId, details: notes } })
    setFlash(true)
    setTimeout(() => setFlash(false), 1600)
  }
  const accept = async () => {
    if (!projectId || !title.trim()) return
    await mutate.mutateAsync({ path: `/inbox/${task.id}/accept`, body: { title, project_id: projectId } })
    onAchieved({ id: task.id, title, outcome: 'accepted' })
  }
  const dismiss = async () => {
    await mutate.mutateAsync({ path: `/inbox/${task.id}`, method: 'DELETE' })
    onAchieved({ id: task.id, title, outcome: 'dismissed' })
  }
  const suggest = () => setSuggestion(suggestRevision(task, projects))
  const applySuggestion = () => {
    if (!suggestion) return
    setTitle(suggestion.title)
    setProjectId(suggestion.projectId)
    setSuggestion(null)
  }
  const discardSuggestion = () => setSuggestion(null)

  return jsxs('article', {
    className: `rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3 ${open ? 'pb-2.5' : ''}`,
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('button', {
            type: 'button',
            onClick: () => setOpen(value => !value),
            'aria-label': `${open ? 'Collapse' : 'Edit'} ${task.title}`,
            className: 'min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline',
            children: task.title
          }),
          jsx('span', {
            className: 'shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide',
            style: { background: tint(pill.token, 16), color: ink(pill.token) },
            children: pill.label
          }),
          jsxs('span', {
            className: 'shrink-0 flex items-center gap-1 text-[10px] text-(--ui-text-tertiary)',
            children: [jsx(Codicon, { name: sourceIcons[task.source] || 'inbox' }), task.source]
          })
        ]
      }),
      !open && (task.reason || task.suggestion_reason) ? jsx('div', {
        className: 'mt-1 truncate text-xs text-(--ui-text-secondary)',
        children: task.reason || task.suggestion_reason
      }) : null,
      open ? jsxs('div', {
        className: 'mt-2.5 grid gap-2 border-t border-(--ui-stroke-secondary) pt-2.5',
        children: [
          jsxs('label', { className: 'grid gap-1', children: [
            jsx('span', { className: 'text-[10px] font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Title' }),
            jsx('input', { value: title, onChange: event => setTitle(event.target.value), 'aria-label': 'Inbox candidate title', className: 'w-full rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm' })
          ] }),
          jsxs('label', { className: 'grid gap-1', children: [
            jsx('span', { className: 'text-[10px] font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Project' }),
            jsx('select', { value: projectId, onChange: event => setProjectId(event.target.value), 'aria-label': 'Inbox candidate project', className: 'w-full rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm', children: projects.map(item => jsx('option', { value: item.project_id, children: item.title }, item.project_id)) })
          ] }),
          jsxs('label', { className: 'grid gap-1', children: [
            jsx('span', { className: 'text-[10px] font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Notes' }),
            jsx('textarea', { value: notes, onChange: event => setNotes(event.target.value), 'aria-label': 'Inbox candidate notes', rows: 2, className: 'w-full rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm' })
          ] }),
          jsxs('div', {
            className: 'rounded-md border border-dashed p-2',
            style: { borderColor: tint('--ui-purple', 45), background: tint('--ui-purple', 8) },
            children: [
              jsxs('div', { className: 'flex items-center gap-2 text-[10px] font-bold uppercase tracking-wide', style: { color: ink('--ui-purple') }, children: [
                jsx(Codicon, { name: 'sparkle' }),
                'AI-assisted revision',
                jsx(Button, { variant: 'ghost', className: 'ml-auto', onClick: suggest, children: 'Suggest revision' })
              ] }),
              suggestion ? jsxs('div', {
                className: 'mt-2 rounded-md border p-2 text-xs',
                style: { borderColor: tint('--ui-purple', 30) },
                children: [
                  jsx('div', { className: 'text-[9px] font-bold uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Proposed title' }),
                  jsx('div', { className: 'font-medium', children: suggestion.title }),
                  jsx('div', { className: 'mt-1.5 text-[9px] font-bold uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Proposed project' }),
                  jsx('div', { className: 'font-medium', children: suggestion.projectLabel }),
                  jsx('div', { className: 'mt-1 text-(--ui-text-secondary)', children: `Reason: ${suggestion.reason}` }),
                  jsxs('div', { className: 'mt-2 flex gap-1.5', children: [
                    jsx(Button, { onClick: applySuggestion, children: 'Apply to fields' }),
                    jsx(Button, { variant: 'ghost', onClick: discardSuggestion, children: 'Discard suggestion' })
                  ] }),
                  jsx('div', { className: 'mt-1.5 text-[9.5px]', style: { color: ink('--ui-purple') }, children: 'AI output is a suggestion only. It cannot Save, Accept, Dismiss, or promote the item by itself. A human must still press Save or Accept.' })
                ]
              }) : null
            ]
          }),
          jsxs('div', { className: 'flex items-center justify-end gap-1.5', children: [
            flash ? jsx('span', { className: 'mr-auto text-[10.5px] font-medium', style: { color: ink('--ui-green') }, children: 'Saved — kept in Inbox' }) : null,
            jsx(Button, { variant: 'ghost', disabled: mutate.isPending, onClick: dismiss, children: 'Dismiss' }),
            jsx(Button, { variant: 'secondary', disabled: mutate.isPending || !title.trim(), onClick: save, children: 'Save' }),
            jsx(Button, { disabled: mutate.isPending || !title.trim() || !projectId, onClick: accept, children: 'Accept' })
          ] })
        ]
      }) : null
    ]
  })
}

function AchievedRow({ entry }) {
  const outcomeToken = entry.outcome === 'accepted' ? '--ui-green' : '--ui-red'
  return jsxs('div', {
    className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) py-1.5 text-xs last:border-b-0',
    children: [
      jsx('span', {
        className: 'shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide',
        style: { background: tint(outcomeToken, 16), color: ink(outcomeToken) },
        children: entry.outcome === 'accepted' ? 'Accepted' : 'Dismissed'
      }),
      jsx('span', { className: 'min-w-0 flex-1 truncate text-(--ui-text-secondary)', children: entry.title }),
      jsx('span', { className: 'shrink-0 text-[10px] text-(--ui-text-tertiary)', children: relativeTime(entry.at) })
    ]
  })
}

function AchievedSection({ achieved, open, onToggle }) {
  return jsxs('section', {
    className: 'overflow-hidden rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-quinary)',
    children: [
      jsxs('button', {
        type: 'button',
        onClick: onToggle,
        className: 'flex w-full items-center gap-2 px-3 py-2.5 text-left',
        children: [
          jsx(Codicon, { name: open ? 'chevron-down' : 'chevron-right' }),
          jsx('strong', { className: 'text-xs', children: 'Achieved' }),
          jsx('span', { className: 'rounded-full bg-(--ui-bg-quaternary) px-1.5 text-[10px] text-(--ui-text-tertiary)', children: achieved.length }),
          jsx('span', { className: 'ml-auto text-[10.5px] text-(--ui-text-tertiary)', children: 'folded by default · accepted & dismissed this session' })
        ]
      }),
      open ? jsx('div', { className: 'border-t border-(--ui-stroke-secondary) px-3 py-2', children: achieved.map(entry => jsx(AchievedRow, { entry }, `${entry.id}-${entry.at}`)) }) : null
    ]
  })
}

function ManualCapture({ mutate }) {
  const [title, setTitle] = useState('')
  const submit = async event => {
    event.preventDefault()
    if (!title.trim()) return
    await mutate.mutateAsync({
      path: '/inbox/capture',
      body: { title, source: 'manual', reason: 'Manual quick capture' }
    })
    setTitle('')
  }
  return jsxs('form', {
    onSubmit: submit,
    className: 'mb-2 flex gap-2 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-2',
    children: [
      jsx('input', {
        value: title,
        onChange: event => setTitle(event.target.value),
        placeholder: 'Capture for later review',
        'aria-label': 'Manual Inbox capture',
        className: 'min-w-0 flex-1 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm'
      }),
      jsx(IconButton, { icon: 'add', label: 'Capture in Inbox', disabled: mutate.isPending || !title.trim(), onClick: submit })
    ]
  })
}

function Inbox({ data, mutate, projects }) {
  const [achieved, setAchieved] = useState([])
  const [achievedOpen, setAchievedOpen] = useState(false)
  if (!data.available) {
    return jsx(EmptyState, {
      title: 'Office Inbox lives on the office desktop',
      description: data.reason || 'Inbox boards are gateway-local; Project Kanban does not sync another machine’s board.'
    })
  }
  const captured = data.stages.captured || []
  const suggested = data.stages.suggested || []
  const reviewable = [...captured, ...suggested]
  const recordAchieved = entry => {
    if (achieved.length === 0) setAchievedOpen(true)
    setAchieved(list => [{ ...entry, at: Date.now() }, ...list])
  }
  return jsxs('div', {
    className: 'mx-auto flex w-full max-w-3xl flex-col gap-2',
    children: [
      jsx(ManualCapture, { mutate }),
      jsxs('div', { className: 'mb-1 flex items-center justify-between', children: [jsx('div', { className: 'text-sm text-(--ui-text-secondary)', children: 'Review each candidate before it becomes human-managed work.' }), jsx('span', { className: 'text-xs tabular-nums text-(--ui-text-tertiary)', children: `${reviewable.length} to review` })] }),
      captured.length ? jsxs('section', { children: [
        jsx('h2', { className: 'mb-2 text-xs font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Captured' }),
        jsx('div', { className: 'flex flex-col gap-2', children: captured.map(task => jsx(InboxCard, { task, stage: 'captured', mutate, projects, onAchieved: recordAchieved }, task.id)) })
      ] }) : null,
      suggested.length ? jsxs('section', { className: captured.length ? 'mt-2' : '', children: [
        jsx('h2', { className: 'mb-2 text-xs font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Legacy suggestions' }),
        jsx('div', { className: 'flex flex-col gap-2', children: suggested.map(task => jsx(InboxCard, { task, stage: 'suggested', mutate, projects, onAchieved: recordAchieved }, task.id)) })
      ] }) : null,
      reviewable.length ? null : jsx(EmptyState, { title: 'Inbox clear', description: 'Email, Slack, Telegram, GitHub, and manual captures appear here.' }),
      achieved.length ? jsx(AchievedSection, { achieved, open: achievedOpen, onToggle: () => setAchievedOpen(value => !value) }) : null
    ]
  })
}

function EvidenceChip({ children, warning = false }) {
  const token = warning ? '--ui-orange' : '--ui-text-tertiary'
  return jsx('span', {
    className: 'rounded px-1.5 py-0.5 text-[10px]',
    style: { background: tint(token, 12), color: ink(token) },
    children
  })
}

function ProjectDetail({ project, ctx, onBack }) {
  const observation = project.observation
  const github = project.github || {}
  const openObsidian = () => project.note_path && ctx.os.openExternal(`obsidian://open?path=${encodeURIComponent(project.note_path)}`)
  const revealNote = () => project.note_path && ctx.os.revealPath(project.note_path)
  const openGithub = () => github.repo && ctx.os.openExternal(`https://github.com/${github.repo}`)
  return jsxs('section', {
    'aria-label': `Project: ${project.title}`,
    className: 'min-w-0 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-4',
    children: [
      onBack ? jsx(Button, { variant: 'ghost', onClick: onBack, className: 'mb-2', children: '‹ Projects' }) : null,
      jsxs('div', { className: 'flex items-start justify-between gap-3', children: [
        jsxs('div', { className: 'min-w-0', children: [
          jsx('div', { className: 'text-[10px] font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Canonical project' }),
          jsx('h2', { className: 'mt-1 text-lg font-medium', children: project.title }),
          jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: `${project.project_id} · ${categoryOf(project).label}` })
        ] }),
        jsx(EvidenceChip, { children: 'Read-only' })
      ] }),
      jsx('dl', {
        className: 'mt-4 overflow-hidden rounded-md border border-(--ui-stroke-secondary)',
        children: [
          ['Goal', project.goal || 'No goal recorded'],
          ['Next action', project.next_action || 'No next action recorded'],
          ['Blocker', project.blocker || 'None recorded']
        ].flatMap(([label, value], index) => [
          jsx('dt', { className: `bg-(--ui-bg-quinary) px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-(--ui-text-tertiary) ${index ? 'border-t border-(--ui-stroke-secondary)' : ''}`, children: label }, `${label}-label`),
          jsx('dd', { className: 'm-0 px-3 py-2 text-sm whitespace-pre-wrap', children: value }, `${label}-value`)
        ])
      }),
      jsxs('div', { className: 'mt-3 flex flex-wrap gap-2', children: [
        jsx(Button, { onClick: openObsidian, disabled: !project.note_path, children: 'Open in Obsidian' }),
        jsx(Button, { variant: 'secondary', onClick: revealNote, disabled: !project.note_path, children: 'Reveal note' }),
        jsx(Button, { variant: 'secondary', onClick: openGithub, disabled: !github.repo, children: 'Open GitHub' })
      ] }),
      jsx('h3', { className: 'mt-5 text-[10px] font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Activity evidence · never changes project status' }),
      jsxs('div', { className: 'mt-2 grid gap-2 sm:grid-cols-2', children: [
        jsxs('div', { className: 'rounded-md border border-(--ui-stroke-secondary) p-3', children: [
          jsx('div', { className: 'text-xs font-medium', children: 'GitHub' }),
          jsx('div', { className: 'mt-1 text-sm', children: github.repo || 'No repository linked' }),
          jsx('div', { className: 'mt-1 text-[11px] text-(--ui-text-tertiary)', children: github.pushed_at ? `Last push ${github.pushed_at}` : 'No GitHub activity available' })
        ] }),
        jsxs('div', { className: 'rounded-md border border-(--ui-stroke-secondary) p-3', children: [
          jsxs('div', { className: 'flex items-center justify-between gap-2', children: [
            jsx('div', { className: 'text-xs font-medium', children: 'Device evidence' }),
            observation?.stale ? jsx(EvidenceChip, { warning: true, children: 'Stale' }) : null
          ] }),
          jsx('div', { className: 'mt-1 text-sm', children: observation ? `Last observed on ${observation.device}` : 'No device observation' }),
          observation ? jsx('div', { className: 'mt-1 text-[11px] text-(--ui-text-tertiary)', children: `Observed ${observation.observed_at}` }) : null,
          observation?.activity_at ? jsx('div', { className: 'text-[11px] text-(--ui-text-tertiary)', children: `Activity ${observation.activity_at}` }) : null,
          observation ? jsxs('div', { className: 'mt-2 flex flex-wrap gap-1.5', children: [
            jsx(EvidenceChip, { warning: observation.dirty_count > 0, children: `${observation.dirty_count} dirty` }),
            jsx(EvidenceChip, { warning: observation.ahead > 0, children: `${observation.ahead} ahead` }),
            jsx(EvidenceChip, { warning: observation.behind > 0, children: `${observation.behind} behind` })
          ] }) : null
        ] })
      ] })
    ]
  })
}

function Projects({ data, ctx }) {
  const items = data.items || []
  const unmatched = data.unmatched || []
  const narrow = useWidth() < 720
  const [selectedId, setSelectedId] = useState('')
  const [showUnmatched, setShowUnmatched] = useState(false)
  const selected = narrow
    ? items.find(item => item.project_id === selectedId)
    : items.find(item => item.project_id === selectedId) || items[0]
  useEffect(() => {
    const keydown = event => {
      if (event.key === 'Escape' && narrow && selectedId) setSelectedId('')
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [narrow, selectedId])
  if (!items.length && !unmatched.length) {
    return jsx(EmptyState, { title: 'No managed projects', description: 'Add project_id and project_category to an active Obsidian project note.' })
  }
  const list = showUnmatched ? jsxs('div', { className: 'flex flex-col gap-2', children: [
    jsx('div', { className: 'rounded-md border border-(--ui-stroke-secondary) p-3 text-xs text-(--ui-text-secondary)', children: 'Unmatched evidence is not a managed project and cannot create actions.' }),
    ...unmatched.map(item => jsxs('div', { className: 'rounded-md border border-(--ui-stroke-secondary) p-3', children: [
      jsx('div', { className: 'text-sm font-medium', children: item.source }),
      jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: `${item.kind} · Last observed on ${item.device}${item.stale ? ' · stale' : ''}` })
    ] }, `${item.device}-${item.source}`))
  ] }) : jsx('div', {
    className: 'flex flex-col gap-2',
    children: items.map(project => jsx('button', {
      type: 'button',
      onClick: () => setSelectedId(project.project_id),
      className: `rounded-md border p-3 text-left ${selected?.project_id === project.project_id ? 'border-(--ui-accent) bg-(--ui-bg-quinary)' : 'border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background)'}`,
      children: jsxs('span', { className: 'block min-w-0', children: [
        jsxs('span', { className: 'flex items-start justify-between gap-2', children: [
          jsx('span', { className: 'truncate text-sm font-medium', children: project.title }),
          jsx(EvidenceChip, { children: categoryOf(project).label })
        ] }),
        jsx('span', { className: 'mt-1 block truncate text-xs text-(--ui-text-secondary)', children: `Next: ${project.next_action || 'Not recorded'}` }),
        jsx('span', { className: `mt-1.5 block text-[11px] ${project.observation?.stale ? 'text-(--ui-orange)' : 'text-(--ui-text-tertiary)'}`, children: project.observation ? `Last observed on ${project.observation.device}${project.observation.stale ? ' · stale' : ''}` : 'No device observation' })
      ] })
    }, project.project_id))
  })
  return jsxs('div', { className: 'mx-auto w-full max-w-6xl', children: [
    data.warnings?.length ? jsx('div', { className: 'mb-3 rounded-md border border-(--ui-orange) p-2 text-xs text-(--ui-text-secondary)', children: `${data.warnings.length} project data warning${data.warnings.length === 1 ? '' : 's'}` }) : null,
    jsxs('div', { className: 'mb-3 flex items-center justify-between gap-2', children: [
      jsx('div', { className: 'text-sm text-(--ui-text-secondary)', children: `${items.length} canonical projects · Obsidian truth first` }),
      jsx(Button, { variant: showUnmatched ? 'secondary' : 'ghost', onClick: () => setShowUnmatched(value => !value), children: `Unmatched evidence · ${unmatched.length}` })
    ] }),
    jsxs('div', { className: 'grid min-w-0 gap-3', style: { gridTemplateColumns: narrow ? 'minmax(0, 1fr)' : 'minmax(280px, 2fr) minmax(360px, 3fr)' }, children: [
      !narrow || !selected || showUnmatched ? jsx('div', { className: 'min-w-0', children: list }) : null,
      !showUnmatched && selected ? jsx(ProjectDetail, { project: selected, ctx, onBack: narrow ? () => setSelectedId('') : null }) : null
    ] })
  ] })
}

function Dashboard({ ctx }) {
  const width = useWidth()
  const [view, setView] = useState('board')
  const [selectedLane, setSelectedLane] = useState('next')
  const [category, setCategory] = useState('all')
  const [adding, setAdding] = useState(false)
  const [detail, setDetail] = useState(null)
  // The docked panel takes 320px out of the board, so the lane breakpoints
  // measure the space the board actually keeps.
  const wide = width >= 1180
  const board = width - (detail && wide ? 320 : 0)
  const columns = board >= 1180 ? 4 : board >= 720 ? 2 : 1
  const query = useQuery({ queryKey: [ID, 'snapshot'], queryFn: () => ctx.rest('/snapshot'), refetchInterval: 5000 })
  const mutate = useKanbanMutation(ctx)

  useEffect(() => {
    if (!detail) return undefined
    const escape = event => { if (event.key === 'Escape') setDetail(null) }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [detail])

  if (query.isPending) return jsx('div', { className: 'grid h-full place-items-center text-sm text-(--ui-text-secondary)', children: 'Loading Kanban…' })
  if (query.isError) return jsx(ErrorState, { title: 'Kanban unavailable', description: query.error?.message || 'The backend did not respond.', action: jsx(Button, { onClick: () => query.refetch(), children: 'Retry' }) })

  const data = query.data
  const boardTasks = lanes.flatMap(lane => data.lanes[lane.id] || [])
  const actionCounts = countCategories(boardTasks, boardCategories.map(item => item.id))
  const filterCounts = view === 'board' ? actionCounts : data.projects.categories
  const filterTotal = view === 'board' ? boardTasks.length : data.projects.total_active
  const filterCategories = view === 'board' ? boardCategories : categories
  const filtered = Object.fromEntries(lanes.map(lane => [lane.id, (data.lanes[lane.id] || []).filter(task => category === 'all' || task.category === category)]))
  const projectData = {
    ...data.projects,
    items: (data.projects.items || []).filter(project => category === 'all' || project.category === category)
  }
  return jsxs('div', {
    className: 'flex h-full min-w-0 flex-col overflow-hidden bg-(--ui-sidebar-surface-background)',
    children: [
      jsxs('header', {
        className: 'border-b border-(--ui-stroke-secondary) p-3 md:p-4',
        children: [
          jsxs('div', { className: 'flex flex-wrap items-center justify-between gap-2', children: [
            jsxs('div', { className: 'min-w-0', children: [jsxs('h1', { className: 'flex items-center gap-2 truncate text-lg font-medium', children: [jsx(Codicon, { name: 'project' }), 'Project Kanban'] }), jsx('div', { className: 'mt-0.5 text-xs text-(--ui-text-tertiary)', children: `${data.projects.total_active} canonical projects · Obsidian truth · native local actions` })] }),
            jsxs('div', { className: 'flex items-center gap-1', children: [
              jsxs(Button, { className: 'relative', variant: view === 'board' ? 'secondary' : 'ghost', onClick: () => { setView('board'); setCategory('all'); setDetail(null) }, 'aria-label': 'Show action board', children: ['Board', jsx(TabBadge, { count: boardTasks.length })] }),
              jsxs(Button, { className: 'relative', variant: view === 'projects' ? 'secondary' : 'ghost', onClick: () => { setView('projects'); setCategory('all'); setDetail(null) }, 'aria-label': 'Show canonical projects', children: ['Projects', jsx(TabBadge, { count: data.projects.total_active })] }),
              jsxs(Button, { className: 'relative', variant: view === 'inbox' ? 'secondary' : 'ghost', onClick: () => { setView('inbox'); setCategory('all'); setDetail(null) }, 'aria-label': 'Show Office Inbox', children: ['Office Inbox', jsx(TabBadge, { count: inboxActiveCount(data.inbox) })] }),
              view === 'board' ? jsx(IconButton, { icon: 'add', label: 'Add next action', onClick: () => setAdding(value => !value) }) : null
            ] })
          ] }),
          view !== 'inbox' ? jsxs('div', { className: 'mt-3 flex flex-wrap gap-1.5', children: [
            jsx(Button, { variant: category === 'all' ? 'secondary' : 'ghost', onClick: () => setCategory('all'), 'data-kanban-filter': `${view}:all`, 'aria-label': `${view === 'board' ? 'Board actions' : 'Canonical projects'} · All · ${filterTotal}`, children: `All · ${filterTotal}` }),
            ...filterCategories.map(item => jsx(Button, { variant: category === item.id ? 'secondary' : 'ghost', onClick: () => setCategory(item.id), 'data-kanban-filter': `${view}:${item.id}`, 'aria-label': `${view === 'board' ? 'Board actions' : 'Canonical projects'} · ${item.label} · ${filterCounts[item.id] || 0}`, children: jsxs('span', { className: 'flex items-center gap-1.5', children: [jsx(Codicon, { name: item.icon }), jsx('span', { children: item.label }), jsx('span', { className: 'text-(--ui-text-tertiary)', children: filterCounts[item.id] || 0 })] }) }, item.id))
          ] }) : null,
          view === 'board' && columns === 1 ? jsx('div', { className: 'mt-2 flex gap-1 overflow-auto', children: lanes.map(item => jsx(Button, { variant: selectedLane === item.id ? 'secondary' : 'ghost', onClick: () => setSelectedLane(item.id), children: item.label }, item.id)) }) : null
        ]
      }),
      jsxs('div', {
        className: 'flex min-h-0 flex-1',
        children: [
          jsxs('main', {
            className: 'min-h-0 min-w-0 flex-1 overflow-auto p-3 md:p-4',
            children: [
              view === 'board' && adding ? jsx(ActionForm, { onClose: () => setAdding(false), mutate, projects: data.projects.items || [] }) : null,
              view === 'board' ? jsx('div', {
                className: adding ? 'mt-3 grid min-w-0 gap-3' : 'grid min-w-0 gap-3',
                style: { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` },
                children: lanes.filter(item => columns > 1 || item.id === selectedLane).map(item => jsx(Lane, { lane: item, tasks: filtered[item.id], mutate, activeId: detail?.task.id, onOpen: task => setDetail({ task, lane: item.id }), compact: columns === 1 }, item.id))
              }) : view === 'projects'
                ? jsx(Projects, { data: projectData, ctx })
                : jsx(Inbox, { data: data.inbox, mutate, projects: data.projects.items || [] })
            ]
          }),
          detail ? jsx(TaskDetail, { task: detail.task, lane: detail.lane, docked: wide, onClose: () => setDetail(null) }) : null
        ]
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Project Kanban',
  defaultEnabled: false,
  register(ctx) {
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: '/project-kanban' }, render: () => jsx(Dashboard, { ctx }) })
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, order: 101, data: { path: '/project-kanban', label: 'Project Kanban', codicon: 'layout' } })
    // Mirrors research-dashboard's pattern: a persistent docked pane with the
    // SAME content as the routed page. The route+nav-row pair alone can leave
    // the board invisible behind a pinned session tile on a plain click (a
    // Hermes Desktop tile/route interaction quirk); the always-resident dock
    // guarantees the board is visible without depending on that route swap.
    ctx.register({ id: 'dashboard', area: 'panes', title: 'Project Kanban', data: { placement: 'right', width: '640px' }, render: () => jsx(Dashboard, { ctx }) })
  }
}
