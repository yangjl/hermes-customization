import {
  Button,
  Codicon,
  EmptyState,
  ErrorState,
  host,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  useMutation,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'project-kanban'
const lanes = [
  { id: 'next', label: 'Next', icon: 'arrow-right' },
  { id: 'doing', label: 'Doing', icon: 'play' },
  { id: 'waiting', label: 'Waiting', icon: 'clock' },
  { id: 'review', label: 'Review', icon: 'eye' }
]
const categories = [
  { id: 'main-research', label: 'Main research', icon: 'beaker' },
  { id: 'student-projects', label: 'Student projects', icon: 'mortar-board' },
  { id: 'systems-admin', label: 'Systems / admin', icon: 'tools' }
]
const sourceIcons = { email: 'mail', slack: 'comment-discussion', telegram: 'send', github: 'git-branch', manual: 'edit' }

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

function TaskCard({ task, lane, mutate }) {
  const index = lanes.findIndex(item => item.id === lane)
  const move = destination => mutate.mutate({ path: `/tasks/${task.id}`, method: 'PATCH', body: { lane: destination } })
  return jsxs('article', {
    className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
    children: [
      jsx('div', { className: 'text-sm font-medium leading-snug', children: task.title }),
      task.body ? jsx('p', { className: 'mt-1 line-clamp-2 text-xs leading-relaxed text-(--ui-text-secondary)', children: task.body }) : null,
      jsxs('div', {
        className: 'mt-2 flex items-center justify-between gap-2',
        children: [
          jsx('span', { className: 'truncate text-[11px] text-(--ui-text-tertiary)', children: categories.find(item => item.id === task.category)?.label || 'Systems / admin' }),
          task.human_managed ? jsxs('span', {
            className: 'flex items-center',
            children: [
              index > 0 ? jsx(IconButton, { icon: 'chevron-left', label: `Move ${task.title} left`, disabled: mutate.isPending, onClick: () => move(lanes[index - 1].id) }) : null,
              index < lanes.length - 1 ? jsx(IconButton, { icon: 'chevron-right', label: `Move ${task.title} right`, disabled: mutate.isPending, onClick: () => move(lanes[index + 1].id) }) : null
            ]
          }) : jsx('span', { className: 'text-[11px] text-(--ui-text-tertiary)', children: 'Native lifecycle · read only' })
        ]
      })
    ]
  })
}

function Lane({ lane, tasks, mutate }) {
  return jsxs('section', {
    className: 'min-w-0 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-quinary) p-2.5',
    children: [
      jsxs('header', {
        className: 'mb-2 flex items-center justify-between px-1',
        children: [
          jsxs('div', { className: 'flex items-center gap-2', children: [jsx(Codicon, { name: lane.icon }), jsx('h2', { className: 'text-sm font-medium', children: lane.label })] }),
          jsx('span', { className: 'text-xs tabular-nums text-(--ui-text-tertiary)', children: tasks.length })
        ]
      }),
      tasks.length
        ? jsx('div', { className: 'flex flex-col gap-2', children: tasks.map(task => jsx(TaskCard, { task, lane: lane.id, mutate }, task.id)) })
        : jsx('div', { className: 'rounded-md border border-dashed border-(--ui-stroke-secondary) px-3 py-8 text-center text-xs text-(--ui-text-tertiary)', children: 'Clear' })
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
  const wide = width >= 1180
  const medium = width >= 720
  const columns = wide ? 4 : medium ? 2 : 1
  const [view, setView] = useState('board')
  const [selectedLane, setSelectedLane] = useState('next')
  const [category, setCategory] = useState('all')
  const [adding, setAdding] = useState(false)
  const query = useQuery({ queryKey: [ID, 'snapshot'], queryFn: () => ctx.rest('/snapshot'), refetchInterval: 5000 })
  const mutate = useKanbanMutation(ctx)

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
      jsxs('main', {
        className: 'min-h-0 flex-1 overflow-auto p-3 md:p-4',
        children: [
          view === 'board' && adding ? jsx(ActionForm, { onClose: () => setAdding(false), mutate }) : null,
          view === 'board' ? jsx('div', {
            className: adding ? 'mt-3 grid min-w-0 gap-3' : 'grid min-w-0 gap-3',
            style: { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` },
            children: lanes.filter(item => columns > 1 || item.id === selectedLane).map(item => jsx(Lane, { lane: item, tasks: filtered[item.id], mutate }, item.id))
          }) : jsx(Inbox, { data: data.inbox, mutate })
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
