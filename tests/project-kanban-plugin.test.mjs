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
  assert.match(source, /label: 'Kanban'/)
  assert.match(source, /order: 101/)
  assert.match(research, /SIDEBAR_NAV_AREA, order: 100/)
})

test('desktop plugin uses the scoped backend and responsive lanes', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /ctx\.rest\('\/snapshot'/)
  assert.match(source, /board >= 1180 \? 4 : board >= 720 \? 2 : 1/)
  assert.match(source, /needs_category/)
  assert.match(source, /suggested_category/)
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
  // The detail rows name each tool's role rather than copying its contents.
  assert.match(source, /it does not copy them/)
})

test('desktop plugin is opt-in and does not imply unsupported completion controls', async () => {
  const source = await readFile(pluginUrl, 'utf8')
  assert.match(source, /defaultEnabled: false/)
  assert.doesNotMatch(source, /Mark complete|Complete task/)
})
