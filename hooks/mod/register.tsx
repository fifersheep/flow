// The flow mod: five views of a task's state, all display, none of them a gate.
//
//   1. band.tsx     the phase rail above the prompt
//   2. pane.tsx     /flow-pane: progress, plan, decisions, deviations, tasks
//   3. status.tsx   /flow-status, answered without a model turn
//   4. here         toasts when a phase moves, a gate opens, or the validator blocks
//   5. here + spinner.tsx  the status line and the spinner carry the phase
//
// and, from the band, the pane, /flow-term and /flow-code, a terminal or the
// editor opened in a task's worktree (hooks/flow_open.py does the opening).
//
// Every view reads one snapshot, printed by hooks/flow_status.py on the same
// parsing the validator uses. Mods can be switched off (policy, a rollout,
// `claude -p`), so nothing here may be load-bearing: the gates stay in
// flow_validate.py, and flow without this module works exactly as before.
//
// The other files build trees and never touch `$`; every engine call is in
// this file, as the engine's static scan of a hooks module requires.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, ResolveInput } from 'claude-code'

import type { PaneTab, Snapshot } from '../../types'
import { bandTree } from './band'
import { PANE } from './look'
import type { Actions, Els } from './look'
import { blockReason, changes, EDITOR_NAME, focusTask, GLYPH, hereTask, openTarget, paletteFor, statusPin, statusReport } from './model'
import type { OpenKind } from './model'
import { paneTree } from './pane'
import { spinnerTree } from './spinner'
import { COMMAND, FENCE, statusRow } from './status'

const TICK_MS = 1000
const POLL_TICKS = 5 //   a task in the repo: catch other sessions' edits within 5 s
const QUIET_TICKS = 30 // no flow tasks here: look again every 30 s
const TABS: readonly PaneTab[] = ['progress', 'plan', 'decisions', 'deviations', 'tasks']

// The session's values: a drawing that reads one redraws when it changes.
// /clear, /resume and /branch reset them, and the next refresh fills them in.
const snapshot = atom({ plugin: 'flow', key: 'snapshot' } as const, null)
const paneTab = atom({ plugin: 'flow', key: 'tab' } as const, 'progress')
const picked = atom({ plugin: 'flow', key: 'picked' } as const, null)

let isDirty = true
let hasTasks = false
let running: Promise<void> | null = null
let pinned: string | undefined | null = null // null: nothing pinned by this load of the module
let terminalApp = 'iterm-split' // the plugin's settings, read as the module loads
let editorApp = 'vscode'
let splitSide = 'right'
let splitSize = 50

async function load($: EngineInterface): Promise<void> {
  const cwd = await $.session.cwd()
  const run = await $.process.run(['python3', `${$.plugin.root}/hooks/flow_status.py`, '--cwd', cwd], { timeoutMs: 15000 })
  if (run.exitCode !== 0) return
  let next: Snapshot
  try {
    next = JSON.parse(run.stdout) as Snapshot
  } catch {
    return
  }
  hasTasks = next.tasks.length > 0
  const pin = statusPin(hereTask(next))
  if (pin !== pinned) $.ui.status(pin) // mod 5; a reload pins it afresh once
  pinned = pin
  const prev = await read($, snapshot)
  if (JSON.stringify(prev) === JSON.stringify(next)) return
  await update($, snapshot, () => next)
  for (const line of changes(prev, next)) $.ui.toast(line) // mod 4
}

/** One snapshot at a time; a call while one runs shares it. */
function refresh($: EngineInterface): Promise<void> {
  isDirty = false
  running ??= load($)
    .catch(() => undefined)
    .finally(() => {
      running = null
    })
  return running
}

async function openPane($: EngineInterface, tab?: PaneTab, folder?: string): Promise<void> {
  if (tab) await update($, paneTab, () => tab)
  if (folder !== undefined) await update($, picked, () => folder)
  await $.ui.open({ id: PANE, title: 'flow', focus: true, closeOnEscape: true })
}

async function setTab($: EngineInterface, tab: PaneTab): Promise<void> {
  await update($, paneTab, () => tab)
}

async function pick($: EngineInterface, folder: string): Promise<void> {
  await update($, picked, () => folder)
  await update($, paneTab, () => 'progress')
}

async function draft($: EngineInterface, text: string): Promise<void> {
  const { isFilled } = await $.prompt.fill({ text })
  if (!isFilled) $.ui.toast('flow: answer the open dialog first, then try again')
}

/** The surface's elements, with the palette that surface draws roles in. */
function kit($: EngineInterface, e: ResolveInput & { surface: string }): Els {
  return { ...$.ui.resolve(e), paint: paletteFor(e.surface) }
}

type Opened = { ok: boolean; message: string; setup?: boolean; needsSetup?: boolean; lines?: string[] }

/** flow_open.py, with the settings: `setup` or a kind and a folder. */
async function opener($: EngineInterface, args: string[], timeoutMs = 30000): Promise<Opened> {
  const settings = ['--side', splitSide, '--size', String(splitSize)]
  try {
    const run = await $.process.run(['python3', `${$.plugin.root}/hooks/flow_open.py`, ...args, ...settings], { timeoutMs })
    return JSON.parse(run.stdout) as Opened
  } catch {
    return { ok: false, message: 'flow_open.py could not be run' }
  }
}

async function openIn($: EngineInterface, kind: OpenKind, dir: string): Promise<Opened> {
  const args = [kind, dir, '--app', kind === 'terminal' ? terminalApp : editorApp]
  if (kind === 'terminal' && (await opener($, [...args, '--dry-run'])).setup) {
    $.ui.toast(`flow ${GLYPH.next} setting up iTerm's Python API for this split — one time, a few seconds…`)
  }
  // the first split AppleScript can't make installs the helper package: allow for it
  return opener($, args, 300000)
}

/** A button's open: the outcome is said in a toast, a fallback or a failure marked. */
async function openFromButton($: EngineInterface, kind: OpenKind, dir: string): Promise<void> {
  const r = await openIn($, kind, dir)
  if (!r.ok) $.ui.toast(`${GLYPH.blocked} flow: ${r.message}`)
  else $.ui.toast(`flow ${r.needsSetup ? GLYPH.deviation : GLYPH.next} ${r.message}`)
}

/** /flow-term setup: the checklist the terminal setting needs, in a fenced block. */
async function terminalSetup($: EngineInterface): Promise<{ text: string }> {
  const r = await opener($, ['setup', '--app', terminalApp], 300000)
  const lines = r.lines ?? [`${GLYPH.blocked} ${r.message}`]
  return { text: [FENCE, ...lines, FENCE].join('\n') }
}

/** /flow-term and /flow-code: the named task's worktree, else the session's. */
async function openFromCommand($: EngineInterface, kind: OpenKind, args: string): Promise<{ text: string }> {
  if (kind === 'terminal' && args.trim().toLowerCase() === 'setup') return terminalSetup($)
  await refresh($)
  const at = openTarget(await read($, snapshot), args)
  if ('error' in at) return { text: `${GLYPH.blocked} ${at.error}` }
  const r = await openIn($, kind, at.dir)
  const note = at.note ? ` (${at.note})` : ''
  const glyph = !r.ok ? GLYPH.blocked : r.needsSetup ? GLYPH.deviation : GLYPH.next
  return { text: `${glyph} ${r.message}${r.ok ? note : ''}` }
}

function actions($: EngineInterface): Actions {
  return {
    openPane: (tab, folder) => void openPane($, tab, folder),
    setTab: tab => void setTab($, tab),
    pick: folder => void pick($, folder),
    draft: text => void draft($, text),
    open: (kind, dir) => void openFromButton($, kind, dir),
    editorName: EDITOR_NAME[editorApp] ?? editorApp,
  }
}

// Nothing here guards anything, so each .catch fails open: a hook that throws
// lets the event go on as if the mod weren't there, and where it had already
// called next(e), next(e) replays that answer, so nothing runs twice.
export const register: Register = (on, options) => {
  if (typeof options.terminal === 'string' && options.terminal) terminalApp = options.terminal
  if (typeof options.editor === 'string' && options.editor) editorApp = options.editor
  if (typeof options.splitSide === 'string' && options.splitSide) splitSide = options.splitSide
  if (typeof options.splitSize === 'number') splitSize = options.splitSize

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await $.command.register({
      name: COMMAND,
      description: 'Where the flow task stands: phases, gates, progress (no model turn)',
      immediate: true,
    })
    await $.command.register({
      name: 'flow-pane',
      description: 'Open the flow pane: progress, plan, decisions, deviations, tasks',
      argumentHint: '[progress|plan|decisions|deviations|tasks]',
      immediate: true,
    })
    await $.command.register({
      name: 'flow-term',
      description: "Open a terminal in the flow task's worktree, beside this session (an iTerm split unless the plugin's settings say otherwise)",
      argumentHint: '[task | setup]',
      immediate: true,
    })
    await $.command.register({
      name: 'flow-code',
      description: "Open the flow task's worktree in the editor (VS Code unless the plugin's settings say otherwise)",
      argumentHint: '[task]',
      immediate: true,
    })
    if (!e.isInteractive) return started
    await refresh($)
    let ticks = 0
    $.clock.every(TICK_MS, () => {
      ticks += 1
      if (isDirty || ticks % (hasTasks ? POLL_TICKS : QUIET_TICKS) === 0) void refresh($)
    })
    return started
  })

  // /clear, /resume and /branch reset $.state; the next tick fills it again
  on('classic.SessionStart', { source: ['clear', 'resume', 'fork'] }, ($, e, next) => {
    isDirty = true
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', ($, e, next) => {
    isDirty = true
    return next(e)
  })

  // Edits, shell commands and worktree moves can change a task. Mod 4: a
  // refusal from the validator is said where the person will see it.
  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    if (e.tool === 'Write' || e.tool === 'Edit' || e.tool === 'NotebookEdit' || e.tool === 'Bash'
      || e.tool === 'EnterWorktree' || e.tool === 'ExitWorktree') {
      isDirty = true
    }
    if (e.tool === 'Write' || e.tool === 'Edit' || e.tool === 'Bash') {
      const why = blockReason(result.deny ?? (result.isError ? result.text : undefined), e.tool)
      if (why) $.ui.toast(`${GLYPH.blocked} flow blocked: ${why}`)
    }
    return result
  }).catch(($, e, next) => next(e))

  // Mod 1: the band
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const mine = bandTree(kit($, e), await read($, snapshot), e.props, actions($))
    if (!mine) return next(e)
    const { Box } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {mine}
        {await next(e)}
      </Box>
    )
  })

  // Mod 2: the pane
  on('command.run', { command: 'flow-pane' }, async ($, e) => {
    const asked = e.args.trim().toLowerCase()
    const tab = TABS.find(t => t === asked)
    await update($, picked, () => null)
    await refresh($)
    await openPane($, tab)
    return asked && !tab ? { text: `flow-pane: no tab "${asked}" — try ${TABS.join(', ')}` } : {}
  })

  on('ui.render', { component: 'Pane', requestId: 'flow' }, async ($, e) =>
    paneTree(kit($, e), await read($, snapshot), await read($, paneTab), await read($, picked), e.props.bodyColumns, actions($)),
  )

  // a closed pane follows the session's task again next time it opens
  on('ui.close', { id: 'flow' }, async ($, e, next) => {
    await update($, picked, () => null)
    return next(e)
  }).catch(($, e, next) => next(e))

  // Mod 3: /flow-status
  on('command.run', { command: 'flow-status' }, async $ => {
    await refresh($)
    return { text: [FENCE, ...statusReport(await read($, snapshot)), FENCE].join('\n') }
  }).catch(() => ({ text: `${GLYPH.blocked} flow-status: the task state could not be read` }))

  // /flow-status, and /flow-term setup's checklist, coloured line by line
  on('ui.render', { component: 'CommandOutput' }, async ($, e, next) => {
    const isMine = e.props.command.endsWith(COMMAND) || (e.props.command.endsWith('flow-term') && e.props.text.includes(FENCE))
    if (!isMine || e.props.isErrored) return next(e)
    return statusRow(kit($, e), e.props.text)
  })

  // A terminal or the editor in a worktree, by command; the buttons are in look.tsx
  on('command.run', { command: 'flow-term' }, async ($, e) => {
    return openFromCommand($, 'terminal', e.args)
  }).catch(() => ({ text: `${GLYPH.blocked} flow-term: the terminal could not be opened` }))

  on('command.run', { command: 'flow-code' }, async ($, e) => {
    return openFromCommand($, 'editor', e.args)
  }).catch(() => ({ text: `${GLYPH.blocked} flow-code: the editor could not be opened` }))

  // Mod 5: the spinner (the status line is set by each refresh)
  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    const task = focusTask(await read($, snapshot))
    if (!task) return next(e)
    return spinnerTree(kit($, e), task, await next(e))
  })
}
