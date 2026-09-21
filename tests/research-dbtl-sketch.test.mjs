import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import test from 'node:test'

const html = readFileSync(new URL('../sketches/research-dbtl/index.html', import.meta.url), 'utf8')
const model = html.match(/<script id="model">([\s\S]*?)<\/script>/)[1]
const { initialState, transition, isApproved } = runInNewContext(`${model}; ({initialState, transition, isApproved})`)
const step = (state, type, extra = {}) => transition(state, { type, ...extra })
function approvedState() {
  let state = step(step(initialState(), 'correct'), 'revise')
  return step(state, 'approve', { revision: state.revision })
}
function completedState() {
  return ['accept-handoff', 'deliver', 'accept-report'].reduce((state, type) => step(state, type), approvedState())
}

test('correction precedes revision-specific approval; reporting waits for handoff acceptance', () => {
  let state = initialState()
  for (const type of ['accept-handoff', 'deliver', 'accept-report', 'candidate', 'propose']) {
    assert.equal(step(state, type), state)
  }
  assert.equal(step(state, 'approve', { revision: 1 }), state)
  state = step(state, 'correct')
  assert.equal(state.stage, 'correction')
  assert.equal(step(state, 'deliver'), state)
  state = step(state, 'revise')
  assert.equal(state.revision, 2)
  assert.equal(state.stage, 'review')
  assert.equal(step(state, 'approve', { revision: 1 }), state, 'old review cannot approve newer evidence')
  state = step(state, 'approve', { revision: 2 })
  assert.equal(state.stage, 'ready')
  assert.equal(isApproved(state), true)
  assert.equal(step(state, 'deliver'), state, 'assignment must be acknowledged before delivery')
  state = step(state, 'accept-handoff')
  assert.equal(step(state, 'accept-handoff'), state, 'duplicate acceptance does not add a second handoff')
  state = step(state, 'deliver')
  assert.equal(state.stage, 'report-review')
  assert.equal(state.reportRevision, 2)
  assert.equal(step(state, 'candidate'), state)
  state = step(state, 'accept-report')
  assert.equal(state.stage, 'complete')
  assert.equal(state.candidate, false, 'internal acceptance does not trigger independent Test')
  assert.equal(state.history.length, 8)
})

test('upstream change invalidates approval and blocks stale handoffs and report acceptance', () => {
  for (const before of [approvedState(), step(approvedState(), 'accept-handoff'), completedState()]) {
    const stale = step(before, 'upstream-change')
    assert.equal(stale.revision, 3)
    assert.equal(stale.approvedRevision, 2)
    assert.equal(isApproved(stale), false)
    for (const action of ['accept-handoff', 'deliver', 'accept-report', 'candidate', 'propose']) {
      assert.equal(step(stale, action), stale)
    }
  }
  const mismatched = { ...completedState(), stage: 'report-review', reportRevision: 1 }
  assert.equal(step(mismatched, 'accept-report'), mismatched)
})

test('manuscript selection pins a claim; next Design stays a proposal', () => {
  let state = completedState()
  assert.equal(step(state, 'select', { value: 'test' }).selected, 'learn')
  state = step(state, 'candidate')
  assert.equal(state.candidate, 2)
  assert.equal(state.selected, 'test')
  assert.equal(step(state, 'candidate'), state)
  assert.equal(step(state, 'validate'), state, 'selection does not imply a Test verdict')
  const stale = step(state, 'upstream-change')
  assert.equal(stale.candidate, 2, 'claim remains pinned to the original revision')
  state = step(state, 'propose')
  assert.equal(state.proposal, true)
  assert.equal(state.stage, 'complete')
  assert.equal(step(state, 'propose'), state)
})

test('unavailable and isolated stale previews cannot mutate workflow; reset clears all decisions', () => {
  for (const value of ['empty', 'loading', 'failure', 'stale']) {
    const state = step(approvedState(), 'preview', { value })
    for (const type of ['correct', 'revise', 'approve', 'accept-handoff', 'deliver', 'upstream-change']) {
      assert.equal(step(state, type, { revision: 2 }), state)
    }
    assert.equal(step(state, 'preview', { value: 'normal' }).stage, 'ready')
  }
  const reset = step(completedState(), 'reset')
  assert.equal(reset.revision, 1)
  assert.equal(reset.approvedRevision, null)
  assert.equal(reset.reportRevision, null)
  assert.equal(reset.history.length, 2)
})
