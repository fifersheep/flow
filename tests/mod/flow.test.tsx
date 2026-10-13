// The flow mod under `claude plugin test .`: the pure model first, then each
// surface drawn through the engine on terminal and desktop. flow_status.py is
// stood in for by a process.run hook beneath the plugin, so the snapshot here
// is the contract tests/test_flow_status.py holds the Python to.

import { describe, expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { Gate, Snapshot, Task } from '../../types'
import { bar, blockReason, changes, lineRole, openTarget, paletteFor, statusLine, statusPin, statusReport, steps, worktreeLabel } from '../../hooks/mod/model'

const FULL = ['setup', 'research', 'planning', 'plan-review', 'implementation', 'code-review', 'reporting', 'wind-down', 'complete']
const LITE = ['setup', 'planning', 'plan-review', 'implementation', 'code-review', 'wind-down', 'complete']
const SURFACES = ['terminal', 'desktop'] as const

function gates(chain: string[], phase: string, passed: number[]): Gate[] {
  return [
    { n: 1, before: 'implementation' },
    { n: 2, before: 'wind-down' },
  ].map(({ n, before }) => {
    const isPassed = passed.includes(n)
    const isWaiting = !isPassed && chain.indexOf(phase) === chain.indexOf(before) - 1
    return { n, before, state: isPassed ? 'passed' : isWaiting ? 'waiting' : 'ahead', date: isPassed ? '2026-10-01' : null }
  })
}

function task(over: Partial<Task> & { passed?: number[] } = {}): Task {
  const chain = over.chain ?? FULL
  const phase = over.phase ?? 'implementation'
  const { passed = [1], ...rest } = over
  return {
    slug: 'add-widget',
    folder: '2026-10-01-add-widget',
    title: 'Add the widget',
    ticket: '',
    ticketId: 'BEE-93',
    mode: chain === LITE ? 'lite' : 'full',
    phase,
    phaseIndex: chain.indexOf(phase),
    chain,
    branch: 'flow/add-widget',
    worktree: '/repo',
    created: '2026-10-01',
    updated: '2026-10-02',
    isActive: phase !== 'complete',
    isHere: true,
    dir: '/repo/docs/tasks/2026-10-01-add-widget',
    workflowPath: '/repo/docs/tasks/2026-10-01-add-widget/workflow.md',
    planPath: '/repo/docs/tasks/2026-10-01-add-widget/plan.md',
    reportPath: null,
    nextAction: 'Finish task 3 — the retry wrapper.',
    progress: {
      done: 2,
      total: 4,
      items: [
        { text: 'Task 1: scaffold', done: true },
        { text: 'Task 2: parser', done: true },
        { text: 'Task 3: retry wrapper', done: false },
        { text: 'Task 4: docs', done: false },
      ],
    },
    gates: gates(chain, phase, passed),
    decisions: ['2026-10-01 Q: per-user or per-team? A: per-user', '2026-10-01 gate 1: plan approved by user'],
    deviations: [],
    plan: '# Plan\n\n## Tasks\n1. scaffold',
    ...rest,
  }
}

function snap(tasks: Task[], current: string | null = tasks.find(t => t.isHere && t.isActive)?.folder ?? null): Snapshot {
  return { schema: 1, root: '/repo', branch: 'flow/add-widget', current, tasks }
}

// --- the pure model ------------------------------------------------------

describe('model', () => {
  test('the full rail puts each gate before the phase it opens', async () => {
    const s = steps(task())
    const names = s.map(x => (x.kind === 'gate' ? `gate${x.gate.n}` : x.phase))
    expect(names).toEqual(['setup', 'research', 'planning', 'plan-review', 'gate1', 'implementation', 'code-review', 'reporting', 'gate2', 'wind-down'])
    expect(s.map(x => x.role)).toEqual(['done', 'done', 'done', 'done', 'done', 'current', 'todo', 'todo', 'todo', 'todo'])
  })

  test('lite has no research and waits on gate 2 from code-review', async () => {
    const t = task({ chain: LITE, phase: 'code-review' })
    expect(steps(t).some(x => x.kind === 'phase' && x.phase === 'research')).toBe(false)
    expect(steps(t).find(x => x.kind === 'gate' && x.gate.n === 2)?.role).toBe('you')
  })

  test('a complete task is done all along the rail', async () => {
    expect(steps(task({ phase: 'complete', passed: [1, 2] })).every(x => x.role === 'done')).toBe(true)
  })

  test('the bar is the status line bar: 20 cells of # and -', async () => {
    expect(bar(2, 4)).toEqual({ filled: '#'.repeat(10), empty: '-'.repeat(10), percent: 50 })
    expect(bar(0, 0).filled).toBe('')
  })

  test('the status line names the phase, or the gate when one waits', async () => {
    expect(statusLine(task())).toBe('flow ● implementation 2/4 · add-widget')
    expect(statusLine(task({ phase: 'plan-review', passed: [] }))).toBe('flow ◈ gate 1 · plan approval waiting · add-widget')
    expect(statusLine(null)).toBe(undefined)
    expect(statusPin(task())).toBe('● implementation 2/4 · add-widget') // the engine adds "flow:"
  })

  test('the terminal gets the status line\'s own ANSI-256 indices; desktop gets hex', async () => {
    expect(paletteFor('terminal')).toEqual({ current: 'ansi256(67)', done: 'ansi256(108)', you: 'ansi256(186)', wrong: 'ansi256(210)' })
    expect(paletteFor('desktop').done).toBe('#87af87')
  })

  test('changes: nothing on a first load', async () => {
    expect(changes(null, snap([task()]))).toEqual([])
  })

  test('changes: a phase move, a gate opening, a gate approved, a deviation', async () => {
    const atReview = task({ phase: 'plan-review', passed: [] })
    expect(changes(snap([task({ phase: 'planning', passed: [] })]), snap([atReview]))).toEqual([
      '◈ add-widget: gate 1 — plan approval is yours to give',
      'flow ▸ add-widget: planning → plan-review',
    ])
    expect(changes(snap([atReview]), snap([task({ deviations: ['used a queue'] })]))).toEqual([
      '◆ add-widget: gate 1 approved',
      'flow ▸ add-widget: plan-review → implementation',
      '▲ add-widget: deviation recorded',
    ])
  })

  test('blockReason reads the validator line out of a refusal', async () => {
    const text = "PreToolUse:Edit hook error: flow: task 'add-widget' is in phase 'planning' — code edits are locked"
    expect(blockReason(text)).toBe("task 'add-widget' is in phase 'planning' — code edits are locked")
    expect(blockReason('some other failure')).toBe(undefined)
  })

  test('every /flow-status line carries the colour of its glyph', async () => {
    const lines = statusReport(snap([task({ deviations: ['x'] })]))
    expect(lines[0]).toBe('▌ add-widget — Add the widget')
    expect(lines.map(lineRole)).toContain('wrong')
    expect(lineRole('  ● implementation — 2/4')).toBe('current')
    expect(lineRole('  ◈ gate 1')).toBe('you')
    expect(lineRole('  ◇ gate 2')).toBe('todo')
    expect(lineRole('  ✓ setup')).toBe('done')
  })

  test("openTarget: the session's task, a named one, else the checkout itself", async () => {
    const side = task({ slug: 'side', folder: 'side', isHere: false, branch: 'flow/side', worktree: '/repo-side', ticketId: 'BEE-7' })
    const s = snap([task(), side])
    expect(openTarget(s)).toEqual({ dir: '/repo', label: 'add-widget' })
    expect(openTarget(s, 'side')).toEqual({ dir: '/repo-side', label: 'side' })
    expect(openTarget(s, 'bee-7')).toEqual({ dir: '/repo-side', label: 'side' })
    expect(openTarget(snap([side]))).toEqual({ dir: '/repo', label: 'this checkout' })
    expect('error' in openTarget(s, 'nope')).toBe(true)
    expect('error' in openTarget(null)).toBe(true)
  })

  test('a worktree beside the repo is named relative to it, any other in full', async () => {
    expect(worktreeLabel('/code/acme-api-audit-log', '/code/acme-api')).toBe('../acme-api-audit-log')
    expect(worktreeLabel('/code/acme-api/.worktrees/x', '/code/acme-api')).toBe('../acme-api/.worktrees/x')
    expect(worktreeLabel('/elsewhere/wt', '/code/acme-api')).toBe('/elsewhere/wt')
  })

  test('openTarget notes a task whose branch no worktree has checked out', async () => {
    const away = task({ slug: 'away', folder: 'away', isHere: false, branch: 'flow/away' })
    expect(openTarget(snap([away]), 'away')).toEqual({ dir: '/repo', label: 'away', note: "branch flow/away isn't checked out here" })
  })
})

// --- through the engine --------------------------------------------------

const ENGINE = 'drawn beneath'

type Seen = { toasts: string[]; status: (string | undefined)[]; filled: string[]; opened: string[]; ran: string[][] }

const OPENED = { ok: true, message: 'opened an iTerm split (right, 50%) in /repo' }

type Opener = { ok: boolean; message: string; setup?: boolean; needsSetup?: boolean; lines?: string[] }

/**
 * Answers the engine calls the mod makes, beneath it, from `doc`; flow_open.py
 * answers `opener`. `ran` keeps the opens themselves, not the dry runs.
 */
function world(on: On, doc: { current: Snapshot }, opener: Opener | ((argv: readonly string[]) => Opener) = OPENED): Seen {
  const seen: Seen = { toasts: [], status: [], filled: [], opened: [], ran: [] }
  on('session.cwd', () => ({ value: '/repo' }))
  on('process.run', ($, e) => {
    const isOpen = e.argv.some(a => a.endsWith('flow_open.py'))
    if (isOpen && !e.argv.includes('--dry-run')) seen.ran.push(e.argv.slice(2))
    const answer = typeof opener === 'function' ? opener(e.argv) : opener
    const stdout = JSON.stringify(isOpen ? { ...answer, argv: [] } : doc.current)
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.toast', ($, e) => {
    seen.toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.status', ($, e) => {
    seen.status.push(e.text)
    return { value: undefined }
  })
  on('prompt.fill', ($, e) => {
    seen.filled.push(e.text)
    return { isFilled: true }
  })
  on('ui.open', ($, e) => {
    seen.opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  // stands in for what the engine (and the mods after flow) draw at a site
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{ENGINE}</Text>
  })
  return seen
}

/** /flow-status refreshes before it answers: the way into a loaded snapshot. */
async function load($: Engine): Promise<string> {
  const ran = await $.command.run({ command: 'flow-status', ...RUN })
  return ran.text ?? ''
}

async function frameColor(ui: { findAll: (q: { type: string }) => Promise<{ props: Record<string, unknown> }[]> }): Promise<unknown> {
  return (await ui.findAll({ type: 'Box' })).find(b => b.props.borderStyle === 'round')?.props.borderColor
}

const RUN = { args: '', origin: { kind: 'composer' } as const, presentation: { isFullscreen: true, columns: 160 } }
const BAND = { hasSurvey: false, isWorking: false, maxRows: 12, bodyColumns: 140, scroll: { offset: 0, bodyRows: 12 }, view: {} }
const PANE_PROPS = { title: 'flow', isFocused: true, bodyColumns: 80, placement: 'dock' as const, scroll: { offset: 0, bodyRows: 40 }, view: {} }

describe('mod 1: the band', () => {
  test('draws the rail, the bar and the next action, framed in periwinkle', async ($, on) => {
    world(on, { current: snap([task()]) })
    await load($)
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'flow', surface, component: 'AbovePrompt', props: BAND })
      expect(await ui.find({ type: 'Text', text: '● implementation' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '◆1' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '#'.repeat(10) })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'Finish task 3 — the retry wrapper.' })).toBeDefined()
      expect(await frameColor(ui)).toBe(paletteFor(surface).current)
      expect(await ui.find({ type: 'Text', text: ENGINE })).toBeDefined() // the others' drawing is kept
      await ui.unmount()
    }
  })

  test('a waiting gate turns the frame straw and offers approve, which only drafts', async ($, on) => {
    const seen = world(on, { current: snap([task({ phase: 'plan-review', passed: [] })]) })
    await load($)
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'flow', surface, component: 'AbovePrompt', props: BAND })
      expect(await ui.find({ type: 'Text', text: /gate 1 · plan approval is yours to give/ })).toBeDefined()
      expect(await frameColor(ui)).toBe(paletteFor(surface).you)
      await ui.press({ key: 'gate-1-approve' })
      await ui.unmount()
    }
    expect(seen.filled).toEqual(['Gate 1: I approve the plan.', 'Gate 1: I approve the plan.'])
  })

  test('steps aside for a survey, and when there is no flow task', async ($, on) => {
    world(on, { current: snap([]) })
    await load($)
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect(await ui.find({ type: 'Text', text: /flow/ })).toBe(undefined)
    expect(await ui.find({ type: 'Text', text: ENGINE })).toBeDefined()
    await ui.unmount()
  })

  test('a narrow band falls back to the one-line status', async ($, on) => {
    world(on, { current: snap([task()]) })
    await load($)
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: { ...BAND, maxRows: 3 } })
    expect(await ui.find({ type: 'Text', text: 'flow ● implementation 2/4 · add-widget' })).toBeDefined()
    await ui.unmount()
  })
})

describe('mod 2: the pane', () => {
  test('/flow-pane opens it; the tabs switch what it shows', async ($, on) => {
    const seen = world(on, { current: snap([task({ deviations: ['used a queue'] })]) })
    await $.command.run({ command: 'flow-pane', ...RUN })
    expect(seen.opened).toEqual(['flow'])
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'flow', surface, component: 'Pane', requestId: 'flow', props: PANE_PROPS })
      expect(await ui.find({ type: 'Text', text: 'Phases' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '▸ ' })).toBeDefined()
      await ui.press({ key: 'tab-plan' })
      expect(await ui.find({ type: 'Markdown', key: 'plan' })).toBeDefined()
      await ui.press({ key: 'tab-deviations' })
      const dev = await ui.find({ type: 'Text', text: '▲ used a queue' })
      expect(dev?.props.color).toBe(paletteFor(surface).wrong)
      await ui.press({ key: 'tab-progress' })
      await ui.unmount()
    }
  })

  test('the tasks tab lists every task, and picking one shows it', async ($, on) => {
    const other = task({ slug: 'side', folder: 'side', isHere: false, branch: 'flow/side', phase: 'planning', passed: [] })
    world(on, { current: snap([task(), other]) })
    await $.command.run({ command: 'flow-pane', ...RUN, args: 'tasks' })
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'Pane', requestId: 'flow', props: PANE_PROPS })
    expect(await ui.find({ type: 'Button', key: 'task-side' })).toBeDefined()
    await ui.press({ key: 'task-side' })
    expect(await ui.find({ type: 'Text', text: 'side' })).toBeDefined()
    await ui.unmount()
  })
})

describe('mod 3: /flow-status', () => {
  test('answers in a fenced block and colours each line', async ($, on) => {
    world(on, { current: snap([task()]) })
    const text = await load($)
    expect(text.startsWith('```\n▌ add-widget')).toBe(true)
    expect(text).toContain('● implementation — 2/4 [##########----------] 50%')
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'flow', surface, component: 'CommandOutput', props: { command: 'flow-status', args: '', text: `flow: ${text}`, isErrored: false } })
      expect(await ui.find({ type: 'Text', text: /```/ })).toBe(undefined) // fences, even the one the engine heads with flow:
      expect((await ui.find({ type: 'Text', text: '  ✓ setup' }))?.props.color).toBe(paletteFor(surface).done)
      expect((await ui.find({ type: 'Text', text: /● implementation/ }))?.props.color).toBe(paletteFor(surface).current)
      await ui.unmount()
    }
  })
})

describe('mod 4: toasts', () => {
  test('a phase move between refreshes is toasted', async ($, on) => {
    const doc = { current: snap([task({ phase: 'planning', passed: [] })]) }
    const seen = world(on, doc)
    await load($)
    doc.current = snap([task({ phase: 'plan-review', passed: [] })])
    await load($)
    expect(seen.toasts).toContain('flow ▸ add-widget: planning → plan-review')
  })

  test("the validator's refusal of an edit is toasted", async ($, on) => {
    const seen = world(on, { current: snap([task()]) })
    on('tool.call', () => ({ deny: "flow: task 'add-widget' is in phase 'planning' — code edits are locked" }))
    await $.tool.call({ tool: 'Edit', file_path: '/repo/a.ts', old_string: 'a', new_string: 'b' })
    expect(seen.toasts).toEqual(["⛔ flow blocked: task 'add-widget' is in phase 'planning' — code edits are locked"])
  })
})

describe('mod 5: status line and spinner', () => {
  test('each change pins the status line', async ($, on) => {
    const seen = world(on, { current: snap([task()]) })
    await load($)
    expect(seen.status).toEqual(['● implementation 2/4 · add-widget'])
  })

  test('the spinner carries the phase after its own drawing', async ($, on) => {
    world(on, { current: snap([task()]) })
    await load($)
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'flow', surface, component: 'Spinner', props: { word: 'Thinking', message: null, suffix: '…', mode: 'thinking' } })
      const line = await ui.find({ type: 'Text', text: /flow ● implementation 2\/4/ })
      expect(line?.props.color).toBe(paletteFor(surface).current)
      await ui.unmount()
    }
  })
})

describe('a terminal or the editor in the worktree', () => {
  test("the band's buttons open the session's task's worktree, and say so", async ($, on) => {
    const seen = world(on, { current: snap([task()]) })
    await load($)
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'flow', surface, component: 'AbovePrompt', props: BAND })
      expect(await ui.find({ type: 'Button', key: 'band-editor' })).toBeDefined()
      await ui.press({ key: 'band-terminal' })
      await ui.unmount()
    }
    expect(seen.ran).toEqual([
      ['terminal', '/repo', '--app', 'iterm-split', '--side', 'right', '--size', '50'],
      ['terminal', '/repo', '--app', 'iterm-split', '--side', 'right', '--size', '50'],
    ])
    expect(seen.toasts).toEqual(['flow ▸ opened an iTerm split (right, 50%) in /repo', 'flow ▸ opened an iTerm split (right, 50%) in /repo'])
  })

  test('they stay on the band while a gate waits', async ($, on) => {
    const seen = world(on, { current: snap([task({ phase: 'plan-review', passed: [] })]) })
    await load($)
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect(await ui.find({ type: 'Button', key: 'gate-1-approve' })).toBeDefined()
    await ui.press({ key: 'band-editor' })
    await ui.unmount()
    expect(seen.ran).toEqual([['editor', '/repo', '--app', 'vscode', '--side', 'right', '--size', '50']])
  })

  test('with no task on this branch, the quiet line opens the checkout itself', async ($, on) => {
    const side = task({ slug: 'side', folder: 'side', isHere: false, branch: 'flow/side', worktree: '/repo-side' })
    const seen = world(on, { current: snap([side]) })
    await load($)
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    await ui.press({ key: 'band-terminal' })
    await ui.unmount()
    expect(seen.ran).toEqual([['terminal', '/repo', '--app', 'iterm-split', '--side', 'right', '--size', '50']])
  })

  test("the pane's buttons follow the task picked in it", async ($, on) => {
    const side = task({ slug: 'side', folder: 'side', isHere: false, branch: 'flow/side', worktree: '/repo-side' })
    const seen = world(on, { current: snap([task(), side]) })
    await $.command.run({ command: 'flow-pane', ...RUN, args: 'tasks' })
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'Pane', requestId: 'flow', props: PANE_PROPS })
    await ui.press({ key: 'task-side' })
    expect(await ui.find({ type: 'Text', text: '/repo-side' })).toBeDefined()
    await ui.press({ key: 'pane-terminal' })
    await ui.unmount()
    expect(seen.ran).toEqual([['terminal', '/repo-side', '--app', 'iterm-split', '--side', 'right', '--size', '50']])
  })

  test('/flow-term and /flow-code take a task, and the settings pick the apps', { options: { terminal: 'tmux', editor: 'cursor', splitSide: 'left', splitSize: 30 } }, async ($, on) => {
    const side = task({ slug: 'side', folder: 'side', isHere: false, branch: 'flow/side', worktree: '/repo-side' })
    const seen = world(on, { current: snap([task(), side]) }, { ok: true, message: 'opened Cursor in /repo-side' })
    const term = await $.command.run({ command: 'flow-term', ...RUN, args: 'side' })
    const code = await $.command.run({ command: 'flow-code', ...RUN, args: 'side' })
    expect(seen.ran).toEqual([
      ['terminal', '/repo-side', '--app', 'tmux', '--side', 'left', '--size', '30'],
      ['editor', '/repo-side', '--app', 'cursor', '--side', 'left', '--size', '30'],
    ])
    expect(code.text).toBe('▸ opened Cursor in /repo-side')
    expect(term.text).toBeDefined()
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect((await ui.find({ type: 'Button', key: 'band-editor' }))?.props.label).toBe('cursor')
    await ui.unmount()
  })

  test('an unknown task is named back, and nothing opens', async ($, on) => {
    const seen = world(on, { current: snap([task()]) })
    const ran = await $.command.run({ command: 'flow-term', ...RUN, args: 'nope' })
    expect(ran.text).toBe('⛔ no task "nope" — add-widget')
    expect(seen.ran).toEqual([])
  })

  test("an opener that fails is toasted as blocked", async ($, on) => {
    const seen = world(on, { current: snap([task()]) }, { ok: false, message: "the terminal setting is tmux, but this session isn't inside tmux" })
    await load($)
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    await ui.press({ key: 'band-terminal' })
    await ui.unmount()
    expect(seen.toasts).toEqual(["⛔ flow: the terminal setting is tmux, but this session isn't inside tmux"])
  })
})

describe('guided setup for a split', () => {
  test('a press that will install the helper says so first', async ($, on) => {
    const seen = world(on, { current: snap([task()]) }, argv =>
      argv.includes('--dry-run') ? { ok: true, message: 'would open', setup: true } : { ok: true, message: 'opened an iTerm split (left, 30%) in /repo' })
    await load($)
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    await ui.press({ key: 'band-terminal' })
    await ui.unmount()
    expect(seen.toasts).toEqual([
      "flow ▸ setting up iTerm's Python API for this split — one time, a few seconds…",
      'flow ▸ opened an iTerm split (left, 30%) in /repo',
    ])
  })

  test('a split that fell back is marked, and points at /flow-term setup', async ($, on) => {
    const seen = world(on, { current: snap([task()]) }, { ok: true, needsSetup: true, message: 'split right at 50% — left at 30% needs setup: run /flow-term setup' })
    await load($)
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    await ui.press({ key: 'band-terminal' })
    await ui.unmount()
    expect(seen.toasts).toEqual(['flow ▲ split right at 50% — left at 30% needs setup: run /flow-term setup'])
  })

  test('/flow-term setup prints the checklist, each line in its colour', { options: { splitSide: 'left', splitSize: 30 } }, async ($, on) => {
    const lines = [
      '▌ terminal setup — iterm-split, left at 30%',
      '  ✓ Claude Code runs in iTerm',
      "  ▲ iTerm's Python API is off — left at 30% needs it",
      '      ▸ iTerm → Settings → General → Magic → tick "Enable Python API"',
      '  ○ helper package — waits on the API',
    ]
    const seen = world(on, { current: snap([task()]) }, { ok: false, message: '', lines })
    const ran = await $.command.run({ command: 'flow-term', ...RUN, args: 'setup' })
    expect(seen.ran).toEqual([['setup', '--app', 'iterm-split', '--side', 'left', '--size', '30']])
    expect(ran.text).toBe(['```', ...lines, '```'].join('\n'))
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'flow', surface, component: 'CommandOutput', props: { command: 'flow-term', args: 'setup', text: `flow: ${ran.text}`, isErrored: false } })
      const p = paletteFor(surface)
      expect((await ui.find({ type: 'Text', text: '  ✓ Claude Code runs in iTerm' }))?.props.color).toBe(p.done)
      expect((await ui.find({ type: 'Text', text: /Python API is off/ }))?.props.color).toBe(p.wrong)
      expect((await ui.find({ type: 'Text', text: /Enable Python API/ }))?.props.color).toBe(p.current)
      expect((await ui.find({ type: 'Text', text: /waits on the API/ }))?.props.dimColor).toBe(true)
      await ui.unmount()
    }
  })

  test("an ordinary /flow-term answer is left to the engine's own drawing", async ($, on) => {
    world(on, { current: snap([task()]) })
    const ui = await $.ui.mount({ plugin: 'flow', surface: 'terminal', component: 'CommandOutput', props: { command: 'flow-term', args: '', text: 'flow: ▸ opened an iTerm split', isErrored: false } })
    expect(await ui.find({ type: 'Text', text: ENGINE })).toBeDefined()
    await ui.unmount()
  })
})
