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
  const badges = [{ icon: 'layout', label: 'Kanban · act', token: '--ui-blue' }]
  if (links.obsidian) badges.push({ icon: 'book', label: `Obsidian · ${links.obsidian}`, token: '--ui-purple' })
  if (links.github) badges.push({ icon: 'git-branch', label: `GitHub · ${links.github}`, token: '--ui-text-tertiary' })
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
  const category = categories.find(item => item.id === task.category) || categories[2]
  return jsxs('article', {
    className: `rounded-lg border bg-(--ui-chat-surface-background) p-3 ${active ? 'border-(--ui-accent)' : 'border-(--ui-stroke-secondary)'}`,
    children: [
      jsxs('div', {
        className: 'flex items-start justify-between gap-2',
        children: [
          jsx('span', {
            className: 'truncate rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide',
            style: { background: tint(category.token, 16), color: ink(category.token) },
            children: category.label
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
  const category = categories.find(item => item.id === task.category) || categories[2]
  const rows = [
    ['Kanban', `${lanes.find(item => item.id === lane)?.label || 'Next'} · ${category.label}`],
    ['Obsidian', links.obsidian || 'No knowledge note linked'],
    ['GitHub', links.github || 'No repository linked'],
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

function ActionForm({ onClose, mutate }) {
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('main-research')
  const submit = async event => {
    event.preventDefault()
    if (!title.trim()) return
    await mutate.mutateAsync({ path: '/tasks', body: { title, category, lane: 'next' } })
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
        value: category,
        onChange: event => setCategory(event.target.value),
        'aria-label': 'Project category',
        className: 'rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm',
        children: categories.map(item => jsx('option', { value: item.id, children: item.label }, item.id))
      }),
      jsxs('div', { className: 'flex gap-1', children: [jsx(Button, { type: 'submit', disabled: mutate.isPending || !title.trim(), children: 'Add' }), jsx(Button, { type: 'button', variant: 'ghost', onClick: onClose, children: 'Cancel' })] })
    ]
  })
}

function InboxCard({ task, mutate }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(task.suggested_title || task.title)
  const [category, setCategory] = useState(task.suggested_category || 'main-research')
  const accept = async event => {
    event.preventDefault()
    await mutate.mutateAsync({ path: `/inbox/${task.id}/accept`, body: { title, category } })
    setEditing(false)
  }
  if (editing) {
    return jsxs('form', {
      onSubmit: accept,
      className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
      children: [
        jsx('input', { value: title, onChange: event => setTitle(event.target.value), 'aria-label': 'Accepted task title', className: 'w-full rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm' }),
        jsxs('div', { className: 'mt-2 flex flex-wrap items-center gap-2', children: [
          jsx('select', { value: category, onChange: event => setCategory(event.target.value), 'aria-label': 'Accepted task category', className: 'min-w-40 flex-1 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-editor) px-3 py-2 text-sm', children: categories.map(item => jsx('option', { value: item.id, children: item.label }, item.id)) }),
          jsx(Button, { type: 'submit', disabled: mutate.isPending || !title.trim(), children: 'Accept' }),
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

function Inbox({ data, mutate }) {
  if (!data.available) {
    return jsx(EmptyState, {
      title: 'Inbox unavailable',
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
        jsx('div', { className: 'flex flex-col gap-2', children: captured.map(task => jsx(InboxCard, { task, mutate }, task.id)) })
      ] }) : null,
      suggested.length ? jsxs('section', { className: captured.length ? 'mt-2' : '', children: [
        jsx('h2', { className: 'mb-2 text-xs font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children: 'Legacy suggestions' }),
        jsx('div', { className: 'flex flex-col gap-2', children: suggested.map(task => jsx(InboxCard, { task, mutate }, task.id)) })
      ] }) : null,
      reviewable.length ? null : jsx(EmptyState, { title: 'Inbox clear', description: 'Email, Slack, Telegram, GitHub, and manual captures appear here.' })
    ]
  })
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
            jsxs('div', { className: 'min-w-0', children: [jsxs('h1', { className: 'flex items-center gap-2 truncate text-lg font-medium', children: [jsx(Codicon, { name: data.machine.board === 'todos' ? 'device-desktop' : 'device-mobile' }), data.machine.name] }), jsx('div', { className: 'mt-0.5 text-xs text-(--ui-text-tertiary)', children: `${data.projects.total_active} active projects${data.projects.needs_category ? ` · ${data.projects.needs_category} need category` : ''}` })] }),
            jsxs('div', { className: 'flex items-center gap-1', children: [
              jsx(Button, { variant: view === 'board' ? 'secondary' : 'ghost', onClick: () => setView('board'), 'aria-label': 'Show action board', children: jsx(Codicon, { name: 'layout' }) }),
              jsx(Button, { variant: view === 'inbox' ? 'secondary' : 'ghost', onClick: () => setView('inbox'), 'aria-label': 'Show Inbox', children: jsxs('span', { className: 'flex items-center gap-1.5', children: [jsx(Codicon, { name: 'inbox' }), data.inbox.available ? jsx('span', { className: 'text-xs tabular-nums', children: (data.inbox.stages.captured?.length || 0) + (data.inbox.stages.suggested?.length || 0) }) : null] }) }),
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
              view === 'board' && adding ? jsx(ActionForm, { onClose: () => setAdding(false), mutate }) : null,
              view === 'board' ? jsx('div', {
                className: adding ? 'mt-3 grid min-w-0 gap-3' : 'grid min-w-0 gap-3',
                style: { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` },
                children: lanes.filter(item => columns > 1 || item.id === selectedLane).map(item => jsx(Lane, { lane: item, tasks: filtered[item.id], mutate, activeId: detail?.task.id, onOpen: task => setDetail({ task, lane: item.id }) }, item.id))
              }) : jsx(Inbox, { data: data.inbox, mutate })
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
