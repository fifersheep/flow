// Pure reading of a flow snapshot: what each surface says, before any drawing.
// No `$`, no elements, so every surface agrees on what a task's state *is* and
// differs only in how it draws it.

import type { Gate, GateState, Snapshot, Task } from '../../types'

// The four colours of the progress bars in the person's own status line
// (~/.claude/statusline-command.sh), each given one meaning here and nowhere
// else. Anything not yet reached is drawn dim.
export const ANSI = {
  current: 67, // periwinkle: where the task is now
  done: 108, //   sage: finished, approved
  you: 186, //    straw: waiting on the person (a gate)
  wrong: 210, //  rose: blocked, a deviation
} as const

// The same four as the xterm palette defines them, for surfaces that take hex.
export const HEX = { current: '#5f87af', done: '#87af87', you: '#d7d787', wrong: '#ff8787' } as const

export type Palette = Record<keyof typeof ANSI, string>

/**
 * The terminal is given the ANSI-256 index itself: hex there is downsampled,
 * and #87af87 lands on 145, a grey, not the status line's 108.
 */
export function paletteFor(surface: string): Palette {
  if (surface !== 'terminal') return HEX
  return {
    current: `ansi256(${ANSI.current})`,
    done: `ansi256(${ANSI.done})`,
    you: `ansi256(${ANSI.you})`,
    wrong: `ansi256(${ANSI.wrong})`,
  }
}

export type Role = keyof typeof ANSI | 'todo'

export const GLYPH = {
  done: '✓',
  current: '●',
  todo: '○',
  gatePassed: '◆',
  gateWaiting: '◈',
  gateAhead: '◇',
  next: '▸',
  deviation: '▲',
  blocked: '⛔',
} as const

const SHORT: Record<string, string> = {
  setup: 'setup',
  research: 'research',
  planning: 'plan',
  'plan-review': 'plan-rev',
  implementation: 'impl',
  'code-review': 'review',
  reporting: 'report',
  'wind-down': 'wrap',
}

export type PhaseStep = { kind: 'phase'; phase: string; short: string; role: 'done' | 'current' | 'todo' }
export type GateStep = { kind: 'gate'; gate: Gate; role: 'done' | 'you' | 'todo' }
export type Step = PhaseStep | GateStep

const GATE_ROLE: Record<GateState, GateStep['role']> = { passed: 'done', waiting: 'you', ahead: 'todo' }

/** The task's chain as the rail draws it: phases with their gates between. */
export function steps(task: Task): Step[] {
  const phases = task.chain.filter(p => p !== 'complete')
  const at = task.phase === 'complete' ? phases.length : task.phaseIndex
  const out: Step[] = []
  phases.forEach((phase, i) => {
    const gate = task.gates.find(g => g.before === phase)
    if (gate) out.push({ kind: 'gate', gate, role: GATE_ROLE[gate.state] })
    const role = i < at ? 'done' : i === at ? 'current' : 'todo'
    out.push({ kind: 'phase', phase, short: SHORT[phase] ?? phase, role })
  })
  return out
}

export function glyphOf(step: Step): string {
  if (step.kind === 'phase') return GLYPH[step.role]
  return step.role === 'done' ? GLYPH.gatePassed : step.role === 'you' ? GLYPH.gateWaiting : GLYPH.gateAhead
}

export function waitingGate(task: Task): Gate | undefined {
  return task.gates.find(g => g.state === 'waiting')
}

/** The task a surface shows: the one picked in the pane, else the session's. */
export function focusTask(s: Snapshot | null, picked: string | null = null): Task | null {
  if (!s) return null
  return s.tasks.find(t => t.folder === picked) ?? s.tasks.find(t => t.folder === s.current) ?? null
}

export function hereTask(s: Snapshot | null): Task | null {
  return focusTask(s, null)
}

/** `[##########----------]` split at the fill, the status line's bar exactly. */
export function bar(done: number, total: number, width = 20): { filled: string; empty: string; percent: number } {
  const ratio = total > 0 ? Math.min(1, done / total) : 0
  const n = Math.floor(ratio * width)
  return { filled: '#'.repeat(n), empty: '-'.repeat(width - n), percent: Math.round(ratio * 100) }
}

/** Progress shows from implementation on, once there is a checklist to count. */
export function showsProgress(task: Task): boolean {
  const at = task.chain.indexOf('implementation')
  return task.progress.total > 0 && at >= 0 && (task.phase === 'complete' || task.phaseIndex >= at)
}

export function gateWord(g: Gate): string {
  return g.n === 1 ? 'plan approval' : 'merge approval'
}

/** The status line's words, which the engine heads with the plugin's name. */
export function statusPin(task: Task | null): string | undefined {
  return statusLine(task)?.replace(/^flow /, '')
}

/** One line for the spinner and the band's collapsed form. */
export function statusLine(task: Task | null): string | undefined {
  if (!task) return undefined
  const g = waitingGate(task)
  if (g) return `flow ${GLYPH.gateWaiting} gate ${g.n} · ${gateWord(g)} waiting · ${task.slug}`
  const count = showsProgress(task) ? ` ${task.progress.done}/${task.progress.total}` : ''
  return `flow ${GLYPH.current} ${task.phase}${count} · ${task.slug}`
}

/** The lines /flow-status prints; each one's leading glyph names its colour. */
export function statusReport(s: Snapshot | null): string[] {
  if (!s || s.error) return [`${GLYPH.blocked} flow: no snapshot${s?.error ? ` — ${s.error}` : ''}`]
  const task = hereTask(s)
  const lines: string[] = []
  if (!task) {
    lines.push(`flow · no active task on ${s.branch ?? 'this checkout'}`)
  } else {
    lines.push(`▌ ${task.slug}${task.title ? ` — ${task.title}` : ''}`)
    lines.push(`  ${meta(task)}`)
    for (const step of steps(task)) {
      if (step.kind === 'gate') {
        const g = step.gate
        const tail = g.state === 'passed' ? ` — approved ${g.date}` : g.state === 'waiting' ? ` — ${gateWord(g)} is yours to give` : ''
        lines.push(`  ${glyphOf(step)} gate ${g.n}${tail}`)
      } else {
        let tail = ''
        if (step.role === 'current' && showsProgress(task)) {
          const b = bar(task.progress.done, task.progress.total)
          tail = ` — ${task.progress.done}/${task.progress.total} [${b.filled}${b.empty}] ${b.percent}%`
        }
        lines.push(`  ${glyphOf(step)} ${step.phase}${tail}`)
      }
    }
    if (task.phase === 'complete') lines.push(`  ${GLYPH.done} complete`)
    if (task.nextAction) lines.push(`  ${GLYPH.next} next: ${task.nextAction}`)
    if (task.deviations.length) lines.push(`  ${GLYPH.deviation} ${plural(task.deviations.length, 'deviation')}`)
  }
  const others = s.tasks.filter(t => t.isActive && t !== task)
  if (others.length) {
    lines.push('')
    lines.push(`  other active tasks`)
    for (const t of others) lines.push(`  · ${t.slug} — ${t.phase} · branch ${t.branch}`)
  }
  if (!task && !others.length) lines.push('  no flow tasks in this repo — /flow <description> starts one')
  return lines
}

/**
 * A worktree as the Tasks tab names it: beside the repo's root it reads
 * `../acme-api-audit-log`, and elsewhere in full.
 */
export function worktreeLabel(worktree: string, root: string): string {
  const parent = root.slice(0, root.lastIndexOf('/') + 1)
  return parent.length > 1 && worktree.startsWith(parent) ? `../${worktree.slice(parent.length)}` : worktree
}

export function meta(task: Task): string {
  return [task.mode, task.ticketId, task.branch && `branch ${task.branch}`, task.updated && `updated ${task.updated}`]
    .filter(Boolean)
    .join(' · ')
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** What changed between two snapshots, as toast lines. None on a first load. */
export function changes(prev: Snapshot | null, next: Snapshot): string[] {
  if (!prev) return []
  const before = new Map(prev.tasks.map(t => [t.folder, t]))
  const out: string[] = []
  for (const t of next.tasks) {
    const was = before.get(t.folder)
    if (!was) {
      if (t.isActive) out.push(`flow ${GLYPH.next} new task ${t.slug} · ${t.phase}`)
      continue
    }
    for (const g of t.gates) {
      const old = was.gates.find(o => o.n === g.n)
      if (g.state === 'passed' && old?.state !== 'passed') out.push(`${GLYPH.gatePassed} ${t.slug}: gate ${g.n} approved`)
      if (g.state === 'waiting' && old?.state !== 'waiting') out.push(`${GLYPH.gateWaiting} ${t.slug}: gate ${g.n} — ${gateWord(g)} is yours to give`)
    }
    if (t.phase !== was.phase) out.push(`flow ${GLYPH.next} ${t.slug}: ${was.phase} → ${t.phase}`)
    if (t.deviations.length > was.deviations.length) out.push(`${GLYPH.deviation} ${t.slug}: deviation recorded`)
  }
  return out
}

/**
 * The validator's refusal text, when a tool result is one. A failed shell
 * command's own output can say 'flow: ' too (a CI log's "workflow: ci"), so
 * for Bash only the lockdown's own wording counts.
 */
export function blockReason(text: string | undefined, tool = 'Edit'): string | undefined {
  if (!text) return undefined
  const line = text.split('\n').find(l => l.includes('flow: ')
    && (tool !== 'Bash' || l.includes('code edits are locked')))
  if (!line) return undefined
  const reason = line.slice(line.indexOf('flow: ') + 'flow: '.length).trim()
  return reason.length > 140 ? `${reason.slice(0, 139)}…` : reason
}

/** Which role colours a /flow-status line, read off its leading glyph. */
export function lineRole(line: string): Role | 'title' | 'plain' {
  const head = line.trimStart().slice(0, 1)
  if (head === '▌') return 'title'
  if (head === GLYPH.done || head === GLYPH.gatePassed) return 'done'
  if (head === GLYPH.current || head === GLYPH.next) return 'current'
  if (head === GLYPH.gateWaiting) return 'you'
  if (head === GLYPH.deviation || head === GLYPH.blocked) return 'wrong'
  if (head === GLYPH.todo || head === GLYPH.gateAhead) return 'todo'
  return 'plain'
}

export type OpenKind = 'terminal' | 'editor'

/** The editor setting's values, as the buttons name them. */
export const EDITOR_NAME: Record<string, string> = { vscode: 'vs code', cursor: 'cursor', zed: 'zed' }

export type OpenTarget = { dir: string; label: string; note?: string } | { error: string }

/**
 * Where a terminal or an editor opens: the named task's worktree (by slug,
 * folder or ticket id), else the session's task's, else the session's own
 * checkout, so the buttons and /flow-term, /flow-code always have somewhere.
 */
export function openTarget(s: Snapshot | null, asked = ''): OpenTarget {
  if (!s || s.error || !s.root) return { error: 'the repo has not been read yet — try again in a moment' }
  const a = asked.trim().toLowerCase()
  if (!a) {
    const t = hereTask(s)
    return t ? taskTarget(s, t) : { dir: s.root, label: 'this checkout' }
  }
  const t = s.tasks.find(x => [x.slug, x.folder, x.ticketId].some(n => n && n.toLowerCase() === a))
  if (!t) return { error: `no task "${asked.trim()}" — ${s.tasks.map(x => x.slug).join(', ') || 'this repo has no flow tasks'}` }
  return taskTarget(s, t)
}

export function taskTarget(s: Snapshot, t: Task): OpenTarget {
  // a task whose branch no worktree has checked out lives only in the root
  const isAway = t.worktree === s.root && !t.isHere && !!t.branch && t.branch !== s.branch
  return { dir: t.worktree, label: t.slug, ...(isAway ? { note: `branch ${t.branch} isn't checked out here` } : {}) }
}
