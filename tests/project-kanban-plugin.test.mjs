import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const pluginUrl = new URL('../desktop-plugins/project-kanban/plugin.js', import.meta.url)
const researchUrl = new URL('../desktop-plugins/research-dashboard/plugin.js', import.meta.url)

test('desktop plugin registers the Kanban route below Research', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  const research = await readFile(researchUrl, 'utf8')
  assert.match(source, /SIDEBAR_NAV_AREA/)
  assert.match(source, /path: '\/project-kanban'/)
  assert.match(source, /label: 'Project Kanban'/)
  assert.match(source, /order: 101/)
  assert.match(research, /SIDEBAR_NAV_AREA, order: 100/)
})

test('desktop plugin uses the scoped backend and responsive lanes', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /ctx\.rest\('\/snapshot'/)
  assert.match(source, /board >= 1180 \? 4 : board >= 720 \? 2 : 1/)
  assert.match(source, /project_category/)
  assert.match(source, /Inbox candidate project/)
  assert.match(source, /data\.stages\.suggested/)
  assert.match(source, /\/inbox\/capture/)
  assert.match(source, /gateway-local/)
  assert.match(source, /human_managed/)
  assert.match(source, /aria-label/)
  assert.doesNotMatch(source, /#[0-9a-fA-F]{3,8}\b/)
})

test('cards carry colored badges, a priority tag, and open a docked detail panel', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /function TaskDetail/)
  assert.match(source, /docked \? 'w-80 shrink-0'/)
  assert.match(source, /Escape/)
  assert.match(source, /function cardLinks/)
  assert.match(source, /links\.obsidian/)
  assert.match(source, /links\.github/)
  assert.match(source, /priorityTags/)
  // Colour comes from theme tokens through color-mix, never a literal hex.
  assert.match(source, /color-mix\(in oklch/)
  assert.match(source, /'--ui-blue'/)
  assert.match(source, /'--ui-red'/)
  assert.match(source, /Legacy \/ unlinked/)
  assert.match(source, /category-mismatch/)
  // The detail rows name each tool's role rather than copying its contents.
  assert.match(source, /it does not copy them/)
})

test('desktop plugin is opt-in and does not imply unsupported completion controls', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /defaultEnabled: false/)
  assert.doesNotMatch(source, /Mark complete|Complete task/)
})

test('Board counts visible actions while Projects counts canonical projects', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  const helper = source.match(/function countCategories\(items, ids\) \{([\s\S]*?)\n\}/)
  assert.ok(helper, 'countCategories helper is missing')
  const countCategories = new Function('items', 'ids', helper[1])
  assert.deepEqual(
    countCategories(
      [
        { category: 'main-research' },
        { category: 'main-research' },
        { category: 'legacy' }
      ],
      ['main-research', 'student-projects', 'systems-admin', 'legacy']
    ),
    {
      'main-research': 2,
      'student-projects': 0,
      'systems-admin': 0,
      legacy: 1
    }
  )
  assert.match(source, /const boardTasks = lanes\.flatMap/)
  assert.match(source, /const filterCounts = view === 'board' \? actionCounts : data\.projects\.categories/)
  assert.match(source, /const filterTotal = view === 'board' \? boardTasks\.length : data\.projects\.total_active/)
  assert.match(source, /Legacy \/ unlinked/)
})

test('Kanban v2 keeps Board first and adds global Projects plus the office Inbox boundary', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /Project Kanban/)
  assert.match(source, /children: \['Board', jsx\(TabBadge/)
  assert.match(source, /children: \['Projects', jsx\(TabBadge/)
  assert.match(source, /children: \['Office Inbox', jsx\(TabBadge/)
  assert.match(source, /function Projects/)
  assert.match(source, /function ProjectDetail/)
  assert.match(source, /Unmatched evidence/)
  assert.match(source, /Last observed on/)
  assert.match(source, /Read-only/)
  assert.match(source, /Office Inbox lives on the office desktop/)
  assert.match(source, /project_id/)
  assert.match(source, /aria-label': 'Canonical project'/)
  assert.match(source, /ctx\.os\.openExternal/)
  assert.match(source, /ctx\.os\.revealPath/)
  assert.match(source, /observation\.observed_at/)
  assert.match(source, /observation\.activity_at/)
  assert.match(source, /const selected = narrow/)
  assert.match(source, /gridTemplateColumns: narrow \? 'minmax\(0, 1fr\)' : 'minmax\(280px, 2fr\) minmax\(360px, 3fr\)'/)
  assert.match(source, /onBack \? jsx\(Button/)
  assert.match(source, /onBack: narrow \? \(\) => setSelectedId\(''\) : null/)
  assert.doesNotMatch(source, /mb-2 lg:hidden/)
  assert.match(source, /event\.key === 'Escape' && narrow/)
  assert.match(source, /function InboxCard\(\{ task, stage, mutate, projects, onAchieved \}\)/)
  assert.match(source, /body: \{ title, project_id: projectId \}/)
  assert.match(source, /path: `\/inbox\/\$\{task\.id\}`, method: 'PATCH', body: \{ title, project_id: projectId, details: notes \}/)
  assert.doesNotMatch(source, /Accepted task category/)
  assert.doesNotMatch(source, /children: data\.machine\.name/)
})

test('Inbox card exposes an independent Save action distinct from Accept and Dismiss', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /const save = async \(\) => \{/)
  assert.match(source, /method: 'PATCH'/)
  assert.match(source, /Saved — kept in Inbox/)
  assert.match(source, /const accept = async \(\) => \{/)
  assert.match(source, /const dismiss = async \(\) => \{/)
  assert.match(source, /children: 'Save'/)
  assert.match(source, /children: 'Accept'/)
  assert.match(source, /children: 'Dismiss'/)
})

test('Inbox card ships a static AI-assisted revision affordance that only fills fields', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /function suggestRevision\(task, projects\)/)
  assert.match(source, /AI-assisted revision/)
  assert.match(source, /Suggest revision/)
  assert.match(source, /Apply to fields/)
  assert.match(source, /Discard suggestion/)
  assert.match(source, /It cannot Save, Accept, Dismiss, or promote the item by itself/)
})

test('Achieved candidates fold into a client-side session grouping, never persisted', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /function AchievedSection/)
  assert.match(source, /const \[achieved, setAchieved\] = useState\(\[\]\)/)
  assert.match(source, /const \[achievedOpen, setAchievedOpen\] = useState\(false\)/)
  assert.match(source, /onAchieved: recordAchieved/)
})

test('tab badges show live counts on Board/Projects/Office Inbox and hide when zero', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /function TabBadge\(\{ count \}\) \{/)
  assert.match(source, /if \(!count\) return null/)
  assert.match(source, /jsx\(TabBadge, \{ count: boardTasks\.length \}\)/)
  assert.match(source, /jsx\(TabBadge, \{ count: data\.projects\.total_active \}\)/)
  assert.match(source, /jsx\(TabBadge, \{ count: inboxActiveCount\(data\.inbox\) \}\)/)
  assert.match(source, /function inboxActiveCount\(inbox\) \{/)
  assert.match(source, /stages\.captured\?\.length \|\| 0/)
  assert.match(source, /stages\.suggested\?\.length \|\| 0/)
  assert.doesNotMatch(source, /#[0-9a-fA-F]{3,8}\b/)
})

test('cards carry a Tracked/Quick type pill reusing tint/ink theme tokens', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /function taskTypeOf\(task\) \{/)
  assert.match(source, /task\.reconciliation === 'linked' && !!task\.project\?\.github\?\.repo \? 'tracked' : 'quick'/)
  assert.match(source, /function TaskTypePill\(\{ task, compact = false \}\) \{/)
  assert.match(source, /children: type === 'tracked' \? 'Tracked' : 'Quick'/)
  assert.match(source, /jsx\(TaskTypePill, \{ task, compact \}\)/)
})

test('cards render a neutral/orange/red deadline row from task.due_date, hidden when absent', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /function DeadlineRow\(\{ dueDate, compact = false \}\) \{/)
  assert.match(source, /const state = deadlineState\(dueDate\)/)
  assert.match(source, /if \(!state\) return null/)
  assert.match(source, /const DEADLINE_SOON_DAYS = 7/)
  assert.match(source, /if \(days < 0\) return \{ tone: 'overdue', days \}/)
  assert.match(source, /if \(days <= DEADLINE_SOON_DAYS\) return \{ tone: 'soon', days \}/)
  assert.match(source, /jsx\(DeadlineRow, \{ dueDate: task\.due_date, compact \}\)/)
  // Deadline row lives on the card, below the body — not only in TaskDetail.
  const cardBody = source.match(/function TaskCard\(\{[\s\S]*?\n\}/)
  assert.ok(cardBody, 'TaskCard function body not found')
  assert.match(cardBody[0], /DeadlineRow/)
})

test('TaskCard accepts a compact prop that hides body and shows a relative last-active line', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  const cardBody = source.match(/function TaskCard\(\{[\s\S]*?\n\}/)
  assert.ok(cardBody, 'TaskCard function body not found')
  assert.match(source, /function TaskCard\(\{ task, lane, mutate, onOpen, active, compact = false \}\) \{/)
  // Body text is dropped in compact mode; a relative "Active <date>" line
  // reuses the existing relativeTime helper (originally for AchievedRow) —
  // no new date-formatting function.
  assert.match(cardBody[0], /compact\s*\n\s*\? jsx\('div', \{ className: '[^']*', children: `Active \$\{relativeTime\(task\.created_at \* 1000\)\}` \}\)\s*\n\s*: \(task\.body \?/)
  assert.match(cardBody[0], /jsx\(TaskTypePill, \{ task, compact \}\)/)
  assert.match(cardBody[0], /jsx\(DeadlineRow, \{ dueDate: task\.due_date, compact \}\)/)
})

test('TaskCard bottom-row badges and lane-move chevrons are structurally unchanged by compact', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  const cardBody = source.match(/function TaskCard\(\{[\s\S]*?\n\}/)
  assert.ok(cardBody, 'TaskCard function body not found')
  // Isolate the bottom-row block (badges + lane chevrons) within TaskCard.
  const bottomRow = cardBody[0].match(/jsxs\('div', \{\n\s*className: 'mt-2 flex items-center justify-between gap-2',[\s\S]*?\n {6}\}\)/)
  assert.ok(bottomRow, 'bottom-row block not found in TaskCard')
  const block = bottomRow[0]
  // The block itself never branches on `compact` — same markup and handlers
  // whether the card is compact or regular.
  assert.doesNotMatch(block, /compact/)
  // Badges: same size, same cardLinks() source, same Tip/Codicon wiring.
  assert.match(block, /cardLinks\(task\)\.map\(badge => jsx\(Tip, \{/)
  assert.match(block, /className: 'grid size-5 place-items-center rounded border'/)
  // Lane-move chevrons: same human_managed gate, same move() PATCH call,
  // same disabled/onClick wiring — untouched by the compact variant.
  assert.match(block, /task\.human_managed \? jsxs\('span', \{/)
  assert.match(block, /icon: 'chevron-left', label: `Move \$\{task\.title\} left`, disabled: mutate\.isPending, onClick: \(\) => move\(lanes\[index - 1\]\.id\)/)
  assert.match(block, /icon: 'chevron-right', label: `Move \$\{task\.title\} right`, disabled: mutate\.isPending, onClick: \(\) => move\(lanes\[index \+ 1\]\.id\)/)
  assert.match(source, /const move = destination => mutate\.mutate\(\{ path: `\/tasks\/\$\{task\.id\}`, method: 'PATCH', body: \{ lane: destination \} \}\)/)
})

test('compact is wired from Dashboard\'s existing width detection, not a new breakpoint hook', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  // Reuses the existing columns === 1 narrow-width computation (useWidth ->
  // board width -> columns), no second width hook introduced.
  assert.match(source, /jsx\(Lane, \{ lane: item, tasks: filtered\[item\.id\], mutate, activeId: detail\?\.task\.id, onOpen: task => setDetail\(\{ task, lane: item\.id \}\), compact: columns === 1 \}/)
  assert.match(source, /function Lane\(\{ lane, tasks, mutate, onOpen, activeId, compact = false \}\)/)
  assert.match(source, /jsx\(TaskCard, \{ task, lane: lane\.id, mutate, onOpen, active: task\.id === activeId, compact \}/)
  // Only one width hook exists in the file.
  const widthHookDefs = source.match(/function useWidth\(\)/g) || []
  assert.equal(widthHookDefs.length, 1)
})
