import { Button, cn, haptic, host, ROUTES_AREA, SIDEBAR_NAV_AREA, Tip } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'research-dashboard'
const actions = [
  ['Reconcile Kansas planting map', 'Maya · Aug 25'],
  ['Compare outlier-detection methods', 'Leo · Aug 26'],
  ['Review environmental covariates', 'Alex · Aug 27'],
  ['Regenerate phenotype figures', 'Maya · Aug 28']
]

function Progress({ value }) {
  return jsx('div', {
    className: 'mt-2 h-1 overflow-hidden rounded-full bg-(--ui-stroke-secondary)',
    children: jsx('div', { className: 'h-full rounded-full bg-(--ui-accent)', style: { width: `${value}%` } })
  })
}

function SummaryCard({ label, value, note, progress }) {
  return jsxs('div', {
    className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
    children: [
      jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: label }),
      jsx('div', { className: 'mt-1 text-lg font-medium', children: value }),
      progress == null ? null : jsx(Progress, { value: progress }),
      jsx('div', { className: 'mt-1.5 text-xs text-(--ui-text-tertiary)', children: note })
    ]
  })
}

function Overview() {
  const [done, setDone] = useState({})
  return jsxs('div', {
    className: 'flex flex-col gap-3',
    children: [
      jsxs('div', {
        className: 'grid grid-cols-2 gap-2',
        children: [
          jsx(SummaryCard, { label: 'Overall progress', value: '53%', note: 'Analysis phase', progress: 53 }),
          jsx(SummaryCard, { label: 'Next milestone', value: 'Dataset freeze', note: 'Sep 18 · 28 days' }),
          jsx(SummaryCard, { label: 'Open actions', value: '7', note: '2 blocked · 1 overdue' }),
          jsx(SummaryCard, { label: 'Manuscript', value: '20%', note: '2 of 6 figures', progress: 20 })
        ]
      }),
      jsxs('section', {
        className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
        children: [
          jsxs('div', { className: 'flex items-center justify-between', children: [jsx('h3', { className: 'text-sm font-medium', children: 'Current milestone' }), jsx('span', { className: 'text-xs text-(--ui-accent)', children: '70%' })] }),
          jsx('div', { className: 'mt-2 text-base font-medium', children: 'Freeze phenotype analysis dataset' }),
          jsx('div', { className: 'mt-1 text-xs text-(--ui-text-secondary)', children: 'Owner: Maya Chen · target September 18' }),
          jsx(Progress, { value: 70 }),
          jsxs('div', { className: 'mt-3 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-quinary) p-3', children: [jsx('div', { className: 'text-xs font-medium', children: 'Primary blocker' }), jsx('div', { className: 'mt-1 text-xs leading-relaxed text-(--ui-text-secondary)', children: 'Kansas 2025 plot identifiers must be reconciled before final association models.' })] })
        ]
      }),
      jsxs('section', {
        className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
        children: [
          jsx('h3', { className: 'mb-1 text-sm font-medium', children: 'Priority actions' }),
          ...actions.map(([name, meta], index) => jsx('button', {
            type: 'button',
            className: cn('flex w-full items-start gap-2 border-b border-(--ui-stroke-secondary) py-2.5 text-left last:border-0', done[index] && 'opacity-50'),
            onClick: () => { haptic('tap'); setDone(current => ({ ...current, [index]: !current[index] })) },
            children: jsxs('span', { className: 'flex min-w-0 flex-1 items-start gap-2.5', children: [jsx('span', { className: cn('mt-0.5 grid size-5 shrink-0 place-items-center rounded border border-(--ui-stroke-secondary) text-xs', done[index] && 'bg-(--ui-accent) text-white'), children: done[index] ? '✓' : '' }), jsxs('span', { className: 'min-w-0', children: [jsx('span', { className: cn('block text-sm', done[index] && 'line-through'), children: name }), jsx('span', { className: 'mt-0.5 block text-xs text-(--ui-text-tertiary)', children: meta })] })] })
          }, name))
        ]
      }),
      jsxs('section', {
        className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-3',
        children: [jsx('h3', { className: 'mb-2 text-sm font-medium', children: 'Waiting for' }), jsx('div', { className: 'text-sm', children: 'Corrected Kansas planting map' }), jsx('div', { className: 'mt-0.5 text-xs text-(--ui-text-secondary)', children: 'Field manager · 7 days overdue' }), jsx('div', { className: 'mt-3 text-sm', children: 'Weather-station metadata' }), jsx('div', { className: 'mt-0.5 text-xs text-(--ui-text-secondary)', children: 'Climate office · waiting 2 days' })]
      })
    ]
  })
}

function Decisions() {
  return jsxs('div', { className: 'flex flex-col gap-2', children: [
    jsxs('div', { className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-4', children: [jsx('div', { className: 'text-sm font-medium', children: 'Primary association model' }), jsx('p', { className: 'mt-2 text-xs leading-relaxed text-(--ui-text-secondary)', children: 'Recommendation: joint multi-environment model, with environment-specific GWAS as supporting evidence.' }), jsx('div', { className: 'mt-2 text-xs text-(--ui-accent)', children: 'OPEN · DECIDE BY SEP 11' })] }),
    jsxs('div', { className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) p-4', children: [jsx('div', { className: 'text-sm font-medium', children: 'Outlier policy' }), jsx('p', { className: 'mt-2 text-xs leading-relaxed text-(--ui-text-secondary)', children: 'Compare fixed and environment-specific thresholds before dataset freeze.' }), jsx('div', { className: 'mt-2 text-xs text-(--ui-accent)', children: 'OPEN · DECIDE BY AUG 28' })] })
  ] })
}

function Dashboard() {
  const [tab, setTab] = useState('overview')
  return jsxs('div', {
    className: 'flex h-full flex-col overflow-hidden bg-(--ui-sidebar-surface-background)',
    children: [
      jsxs('header', { className: 'border-b border-(--ui-stroke-secondary) p-4', children: [jsxs('div', { className: 'flex items-center justify-between gap-2', children: [jsx('div', { className: 'min-w-0 truncate text-lg font-medium', children: 'Heat tolerance in maize' }), jsx('span', { className: 'shrink-0 rounded-full border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs text-(--ui-text-secondary)', children: 'AT RISK' })] }), jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: 'HEAT-MAIZE-01 · fictional demo' }), jsxs('div', { className: 'mt-3 flex gap-1', children: [jsx(Button, { variant: tab === 'overview' ? 'secondary' : 'ghost', onClick: () => setTab('overview'), children: 'Overview' }), jsx(Button, { variant: tab === 'decisions' ? 'secondary' : 'ghost', onClick: () => setTab('decisions'), children: 'Decisions' })] })] }),
      jsx('div', { className: 'min-h-0 flex-1 overflow-auto p-3', children: tab === 'overview' ? jsx(Overview, {}) : jsx(Decisions, {}) })
    ]
  })
}

function StatusChip() {
  return jsx(Tip, { label: 'Open Research Dashboard', children: jsx('button', { type: 'button', className: 'inline-flex h-full items-center gap-2 px-2 text-xs text-(--ui-text-secondary) hover:text-foreground', onClick: () => host.navigate('/research-dashboard'), children: 'Research · 1 at risk' }) })
}

export default {
  id: ID,
  name: 'Research Dashboard',
  register(ctx) {
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: '/research-dashboard' }, render: () => jsx(Dashboard, {}) })
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, order: 100, data: { path: '/research-dashboard', label: 'Research', codicon: 'project' } })
    ctx.register({ id: 'dashboard', area: 'panes', title: 'Research Dashboard', data: { placement: 'right', width: '420px' }, render: () => jsx(Dashboard, {}) })
    ctx.register({ id: 'status', area: 'statusBar.right', order: 118, render: () => jsx(StatusChip, {}) })
  }
}
