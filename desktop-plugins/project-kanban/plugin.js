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
const uncategorized = { id: 'unsorted', label: 'Needs category', icon: 'question', token: '--ui-text-tertiary' }
const categoryOf = task => task.category === 'unsorted' ? uncategorized : categories.find(item => item.id === task.category) || uncategorized
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

function useKanbanMutation(ctx) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ path, method = 'POST', body }) => ctx.rest(path, { method, body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [ID, 'snapshot'] }),
    onError: error => host.notify({ kind: 'error', message: error?.message || 'Kanban action failed' })
  })
}

function TaskCard({ task, lane, mutate, onOpen, active }) {
  const index = lanes.findIndex(item => item.id === lane)
  const move = destination => mutate.mutate({ path: `/tasks/${task.id}`, method: 'PATCH', body: { lane: destination } })
  const priority = priorityOf(task)
  const category = categoryOf(task)
  const project = task.project
  return jsxs('article', {
    className: `rounded-lg border bg-(--ui-chat-surface-background) p-3 ${active ? 'border-(--ui-accent)' : 'border-(--ui-stroke-secondary)'}`,
    children: [
      jsxs('div', {
        className: 'flex items-start justify-between gap-2',
        children: [
          jsx('span', {
            className: 'truncate rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide',
            style: { background: tint(category.token, 16), color: ink(category.token) },
            children: project?.title || category.label
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
        className: 'mt-1.5 block w-full text-left text-sm font-medium leading-snug hover:underline',
        children: task.title
      }),
      task.body ? jsx('p', { className: 'mt-1 line-clamp-2 text-xs leading-relaxed text-(--ui-text-secondary)', children: task.body }) : null,
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

function Lane({ lane, tasks, mutate, onOpen, activeId }) {
  return jsxs('section', {
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
        ? jsx('div', { className: 'flex flex-col gap-2', children: tasks.map(task => jsx(TaskCard, { task, lane: lane.id, mutate, onOpen, active: task.id === activeId }, task.id)) })
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

function InboxCard({ task, mutate, projects }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(task.suggested_title || task.title)
  const [projectId, setProjectId] = useState(projects[0]?.project_id || '')
  const accept = async event => {
    event.preventDefault()
    if (!projectId) return
    await mutate.mutateAsync({ path: `/inbox/${task.id}/accept`, body: { title, project_id: projectId } })
    setEditing(false)
  }
  if (editing) {
    return jsxs('form', {
      onSubmit: accept,
      className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
      children: [
        jsx('input', { value: title, onChange: event => setTitle(event.target.value), 'aria-label': 'Accepted task title', className: 'w-full rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm' }),
        jsxs('div', { className: 'mt-2 flex flex-wrap items-center gap-2', children: [
          jsx('select', { value: projectId, onChange: event => setProjectId(event.target.value), 'aria-label': 'Accepted task project', className: 'min-w-40 flex-1 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm', children: projects.map(item => jsx('option', { value: item.project_id, children: item.title }, item.project_id)) }),
          jsx(Button, { type: 'submit', disabled: mutate.isPending || !title.trim() || !projectId, children: 'Accept' }),
          jsx(Button, { type: 'button', variant: 'ghost', onClick: () => setEditing(false), children: 'Cancel' })
        ] })
      ]
    })
  }
  return jsxs('article', {
    className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
    children: [
      jsxs('div', { className: 'flex items-start gap-2', children: [jsx(Codicon, { name: sourceIcons[task.source] || 'inbox' }), jsxs('div', { className: 'min-w-0 flex-1', children: [jsx('div', { className: 'text-sm font-medium', children: task.title }), task.reason ? jsx('div', { className: 'mt-1 text-xs text-(--ui-text-secondary)', children: task.reason }) : null, task.suggestion_reason ? jsxs('div', { className: 'mt-1 flex items-start gap-1 text-[11px] text-(--ui-text-tertiary)', children: [jsx(Codicon, { name: 'sparkle' }), task.suggestion_reason] }) : null] })] }),
      jsxs('div', { className: 'mt-2 flex justify-end gap-1', children: [
        jsx(IconButton, { icon: 'check', label: `Review and accept ${task.title}`, onClick: () => setEditing(true) }),
        jsx(IconButton, { icon: 'trash', label: `Dismiss ${task.title}`, disabled: mutate.isPending, onClick: () => mutate.mutate({ path: `/inbox/${task.id}`, method: 'DELETE' }) })
      ] })
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
  if (!data.available) {
    return jsx(EmptyState, {
      title: 'Office Inbox lives on the office desktop',
      description: data.reason || 'Inbox boards are gateway-local; Project Kanban does not sync another machine’s board.'
    })
  }
  const captured = data.stages.captured || []
  const suggested = data.stages.suggested || []
  const reviewable = [...captured, ...suggested]
  return jsxs('div', {
    className: 'mx-auto flex w-full max-w-3xl flex-col gap-2',
    children: [
      jsx(ManualCapture, { mutate }),
      jsxs('div', { className: 'mb-1 flex items-center justify-between', children: [jsx('div', { className: 'text-sm text-(--ui-text-secondary)', children: 'Review each candidate before it becomes human-managed work.' }), jsx('span', { className: 'text-xs tabular-nums text-(--ui-text-tertiary)', children: `${reviewable.length} to review` })] }),
      captured.length ? jsxs('section', { children: [
        jsx('h2', { className: 'mb-2 text-xs font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Captured' }),
        jsx('div', { className: 'flex flex-col gap-2', children: captured.map(task => jsx(InboxCard, { task, mutate, projects }, task.id)) })
      ] }) : null,
      suggested.length ? jsxs('section', { className: captured.length ? 'mt-2' : '', children: [
        jsx('h2', { className: 'mb-2 text-xs font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Legacy suggestions' }),
        jsx('div', { className: 'flex flex-col gap-2', children: suggested.map(task => jsx(InboxCard, { task, mutate, projects }, task.id)) })
      ] }) : null,
      reviewable.length ? null : jsx(EmptyState, { title: 'Inbox clear', description: 'Email, Slack, Telegram, GitHub, and manual captures appear here.' })
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
  const filtered = Object.fromEntries(lanes.map(lane => [lane.id, (data.lanes[lane.id] || []).filter(task => category === 'all' || task.category === category)]))
  return jsxs('div', {
    className: 'flex h-full min-w-0 flex-col overflow-hidden bg-(--ui-sidebar-surface-background)',
    children: [
      jsxs('header', {
        className: 'border-b border-(--ui-stroke-secondary) p-3 md:p-4',
        children: [
          jsxs('div', { className: 'flex flex-wrap items-center justify-between gap-2', children: [
            jsxs('div', { className: 'min-w-0', children: [jsxs('h1', { className: 'flex items-center gap-2 truncate text-lg font-medium', children: [jsx(Codicon, { name: 'project' }), 'Project Kanban'] }), jsx('div', { className: 'mt-0.5 text-xs text-(--ui-text-tertiary)', children: `${data.projects.total_active} canonical projects · Obsidian truth · native local actions` })] }),
            jsxs('div', { className: 'flex items-center gap-1', children: [
              jsx(Button, { variant: view === 'board' ? 'secondary' : 'ghost', onClick: () => { setView('board'); setDetail(null) }, 'aria-label': 'Show action board', children: 'Board' }),
              jsx(Button, { variant: view === 'projects' ? 'secondary' : 'ghost', onClick: () => { setView('projects'); setDetail(null) }, 'aria-label': 'Show canonical projects', children: 'Projects' }),
              jsx(Button, { variant: view === 'inbox' ? 'secondary' : 'ghost', onClick: () => { setView('inbox'); setDetail(null) }, 'aria-label': 'Show Office Inbox', children: 'Office Inbox' }),
              view === 'board' ? jsx(IconButton, { icon: 'add', label: 'Add next action', onClick: () => setAdding(value => !value) }) : null
            ] })
          ] }),
          view === 'board' ? jsxs('div', { className: 'mt-3 flex flex-wrap gap-1.5', children: [
            jsx(Button, { variant: category === 'all' ? 'secondary' : 'ghost', onClick: () => setCategory('all'), children: `All · ${data.projects.total_active}` }),
            ...categories.map(item => jsx(Button, { variant: category === item.id ? 'secondary' : 'ghost', onClick: () => setCategory(item.id), children: jsxs('span', { className: 'flex items-center gap-1.5', children: [jsx(Codicon, { name: item.icon }), jsx('span', { children: item.label }), jsx('span', { className: 'text-(--ui-text-tertiary)', children: data.projects.categories[item.id] || 0 })] }) }, item.id))
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
                children: lanes.filter(item => columns > 1 || item.id === selectedLane).map(item => jsx(Lane, { lane: item, tasks: filtered[item.id], mutate, activeId: detail?.task.id, onOpen: task => setDetail({ task, lane: item.id }) }, item.id))
              }) : view === 'projects'
                ? jsx(Projects, { data: data.projects, ctx })
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
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, order: 101, data: { path: '/project-kanban', label: 'Kanban', codicon: 'layout' } })
  }
}
