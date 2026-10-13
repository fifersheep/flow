// Mod 2: the flow pane. /flow-pane (or the band's buttons) opens it; five
// tabs, each under its own coloured heading: Progress, Plan, Decisions,
// Deviations, and every task across the repo's worktrees.

import type { RenderElement } from 'claude-code'

import type { PaneTab, Snapshot, Task } from '../../types'
import { Bar, GateRow, ink, OpenButtons, Rule } from './look'
import type { Actions, Els } from './look'
import { bar, focusTask, GLYPH, glyphOf, meta, openTarget, plural, showsProgress, steps, taskTarget, waitingGate } from './model'

const TABS: { id: PaneTab; label: string; hotkey: string }[] = [
  { id: 'progress', label: 'Progress', hotkey: '1' },
  { id: 'plan', label: 'Plan', hotkey: '2' },
  { id: 'decisions', label: 'Decisions', hotkey: '3' },
  { id: 'deviations', label: 'Deviations', hotkey: '4' },
  { id: 'tasks', label: 'Tasks', hotkey: '5' },
]

/** The pane's whole body: tabs, a rule, then the open tab. */
export function paneTree(E: Els, s: Snapshot | null, tab: PaneTab, picked: string | null, columns: number, act: Actions): RenderElement {
  const task = focusTask(s, picked)
  const width = Math.max(20, columns)
  return (
    <E.Box flexDirection="column">
      {Tabs(E, act, tab, task)}
      <E.Text dimColor>{'─'.repeat(width)}</E.Text>
      {s && OpenRow(E, act, s, task)}
      {tab !== 'tasks' && task && Heading(E, task)}
      {tab === 'tasks' ? TasksTab(E, act, s, task, width) : !task ? NoTask(E, s) : body(E, act, tab, task, width)}
    </E.Box>
  )
}

function body(E: Els, act: Actions, tab: PaneTab, task: Task, width: number): RenderElement {
  if (tab === 'plan') return PlanTab(E, task, width)
  if (tab === 'decisions') return DecisionsTab(E, task, width)
  if (tab === 'deviations') return DeviationsTab(E, task, width)
  return ProgressTab(E, act, task, width)
}

function Tabs(E: Els, act: Actions, tab: PaneTab, task: Task | null): RenderElement {
  return (
    <E.Box flexDirection="row" columnGap={3} flexWrap="wrap">
      {TABS.map(t => {
        const isOn = t.id === tab
        const count = !task ? '' : t.id === 'decisions' ? ` ${task.decisions.length}` : t.id === 'deviations' ? ` ${task.deviations.length}` : ''
        const alarm = t.id === 'deviations' && (task?.deviations.length ?? 0) > 0
        return (
          <E.Button key={`tab-${t.id}`} label={t.label} hotkey={t.hotkey} plain onPress={() => act.setTab(t.id)}>
            <E.Text {...(isOn ? ink(E, 'current') : { dimColor: true })} bold={isOn} underline={isOn}>{t.label}</E.Text>
            {count && <E.Text {...(alarm ? ink(E, 'wrong') : { dimColor: true })}>{count}</E.Text>}
          </E.Button>
        )
      })}
    </E.Box>
  )
}

/** Where the shown task's worktree is, and a terminal or the editor there. */
function OpenRow(E: Els, act: Actions, s: Snapshot, task: Task | null): RenderElement | null {
  const at = task ? taskTarget(s, task) : openTarget(s)
  if ('error' in at) return null
  return (
    <E.Box flexDirection="row" justifyContent="space-between" columnGap={2} marginBottom={1}>
      <E.Text dimColor wrap="truncate-start">{at.dir}</E.Text>
      <E.Box flexDirection="row" columnGap={2} flexShrink={0}>{OpenButtons(E, act, at, 'pane')}</E.Box>
    </E.Box>
  )
}

function Heading(E: Els, task: Task): RenderElement {
  return (
    <E.Box flexDirection="column" marginBottom={1}>
      <E.Text wrap="truncate-end">
        <E.Text color={E.paint.current} bold>{task.slug}</E.Text>
        {task.title && <E.Text>{`  ${task.title}`}</E.Text>}
      </E.Text>
      <E.Text dimColor wrap="truncate-end">{meta(task)}</E.Text>
    </E.Box>
  )
}

function NoTask(E: Els, s: Snapshot | null): RenderElement {
  const others = s?.tasks.filter(t => t.isActive).length ?? 0
  return (
    <E.Box flexDirection="column">
      <E.Text dimColor>{`No active flow task on ${s?.branch ?? 'this checkout'}.`}</E.Text>
      <E.Text dimColor>{others ? `${plural(others, 'active task')} elsewhere — see 5: Tasks.` : '/flow <description> starts one.'}</E.Text>
    </E.Box>
  )
}

function ProgressTab(E: Els, act: Actions, task: Task, width: number): RenderElement {
  const gate = waitingGate(task)
  const items = task.progress.items
  const firstOpen = items.findIndex(i => !i.done)
  return (
    <E.Box flexDirection="column">
      {Rule(E, 'Phases', width)}
      <E.Box flexDirection="column" paddingLeft={1} marginBottom={1}>
        {steps(task).map(step => {
          const label = step.kind === 'gate' ? `gate ${step.gate.n}` : step.phase
          const strong = step.role === 'current' || step.role === 'you'
          let tail: RenderElement | null = null
          if (step.kind === 'gate' && step.gate.state === 'passed') tail = <E.Text dimColor>{`  approved ${step.gate.date}`}</E.Text>
          if (step.kind === 'gate' && step.gate.state === 'waiting') tail = <E.Text color={E.paint.you}>{'  waiting on you'}</E.Text>
          if (step.kind === 'phase' && step.role === 'current' && showsProgress(task)) tail = <E.Text>{'  '}{Bar(E, task)}</E.Text>
          return (
            <E.Text wrap="truncate-end">
              <E.Text {...ink(E, step.role)} bold={strong}>{`${glyphOf(step)} ${label}`}</E.Text>
              {tail}
            </E.Text>
          )
        })}
        {task.phase === 'complete' && <E.Text color={E.paint.done} bold>{`${GLYPH.done} complete`}</E.Text>}
      </E.Box>

      {Rule(E, gate ? 'Waiting on you' : 'Next', width, gate ? 'you' : 'current')}
      <E.Box flexDirection="column" paddingLeft={1} marginBottom={1}>
        <E.Text>{task.nextAction || '—'}</E.Text>
        {gate && GateRow(E, act, task, gate)}
      </E.Box>

      {items.length > 0 && Rule(E, `Checklist ${task.progress.done}/${task.progress.total}`, width, task.progress.done === task.progress.total ? 'done' : 'current')}
      {items.length > 0 && (
        <E.Box flexDirection="column" paddingLeft={1} marginBottom={1}>
          {items.map((item, i) => {
            const role = item.done ? 'done' : i === firstOpen ? 'current' : 'todo'
            const glyph = item.done ? GLYPH.done : i === firstOpen ? GLYPH.next : GLYPH.todo
            return (
              <E.Text wrap="truncate-end">
                <E.Text {...ink(E, role)} bold={role === 'current'}>{`${glyph} `}</E.Text>
                <E.Text {...(role === 'todo' ? { dimColor: true } : {})}>{item.text}</E.Text>
              </E.Text>
            )
          })}
        </E.Box>
      )}

      {task.deviations.length > 0 && Rule(E, plural(task.deviations.length, 'deviation'), width, 'wrong')}
      {task.deviations.length > 0 && (
        <E.Box flexDirection="column" paddingLeft={1}>
          {task.deviations.map(d => <E.Text color={E.paint.wrong} wrap="truncate-end">{`${GLYPH.deviation} ${d}`}</E.Text>)}
        </E.Box>
      )}
    </E.Box>
  )
}

function PlanTab(E: Els, task: Task, width: number): RenderElement {
  if (!task.plan) {
    return (
      <E.Box flexDirection="column">
        {Rule(E, 'Plan', width, 'todo')}
        <E.Text dimColor>No plan.md yet — the planning phase writes it.</E.Text>
      </E.Box>
    )
  }
  return (
    <E.Box flexDirection="column">
      {Rule(E, 'Plan', width)}
      <E.Text dimColor wrap="truncate-start">{task.planPath ?? ''}</E.Text>
      <E.Markdown key="plan" text={task.plan} />
    </E.Box>
  )
}

function DecisionsTab(E: Els, task: Task, width: number): RenderElement {
  return (
    <E.Box flexDirection="column">
      {Rule(E, 'Decision log', width)}
      {task.decisions.length === 0 && <E.Text dimColor>Nothing logged yet.</E.Text>}
      {task.decisions.map(d => {
        const isGate = /\bgate \d:/.test(d)
        const isQa = /\bQ:/.test(d)
        const glyph = isGate ? GLYPH.gatePassed : isQa ? '?' : '•'
        return (
          <E.Text wrap="wrap">
            <E.Text {...ink(E, isGate ? 'done' : isQa ? 'current' : 'todo')} bold={isGate}>{`${glyph} `}</E.Text>
            <E.Text {...(isGate ? ink(E, 'done') : {})}>{d}</E.Text>
          </E.Text>
        )
      })}
    </E.Box>
  )
}

function DeviationsTab(E: Els, task: Task, width: number): RenderElement {
  if (task.deviations.length === 0) {
    return (
      <E.Box flexDirection="column">
        {Rule(E, 'Deviations', width, 'done')}
        <E.Text color={E.paint.done}>{`${GLYPH.done} None recorded — the work matches the plan.`}</E.Text>
      </E.Box>
    )
  }
  return (
    <E.Box flexDirection="column">
      {Rule(E, plural(task.deviations.length, 'deviation'), width, 'wrong')}
      {task.deviations.map(d => <E.Text color={E.paint.wrong} wrap="wrap">{`${GLYPH.deviation} ${d}`}</E.Text>)}
    </E.Box>
  )
}

/** One glyph per step, coloured: the whole chain at a glance. */
function MiniRail(E: Els, task: Task): RenderElement[] {
  return steps(task).map(step => <E.Text {...ink(E, step.role)}>{glyphOf(step)}</E.Text>)
}

function TasksTab(E: Els, act: Actions, s: Snapshot | null, shown: Task | null, width: number): RenderElement {
  const tasks = s?.tasks ?? []
  const active = tasks.filter(t => t.isActive)
  const done = tasks.filter(t => !t.isActive)
  const row = (t: Task) => {
    const isShown = t.folder === shown?.folder
    const gate = waitingGate(t)
    const where = t.isHere ? 'here' : t.worktree === s?.root ? `branch ${t.branch}` : `${t.branch} · ${t.worktree}`
    return (
      <E.Button key={`task-${t.folder}`} label={t.slug} onPress={() => act.pick(t.folder)} plain>
        <E.Text {...ink(E, isShown ? 'current' : 'todo')} bold>{isShown ? `${GLYPH.next} ` : '  '}</E.Text>
        {t.isActive ? MiniRail(E, t) : [<E.Text color={E.paint.done}>{GLYPH.done}</E.Text>]}
        <E.Text bold={isShown}>{`  ${t.slug}`}</E.Text>
        <E.Text {...ink(E, gate ? 'you' : t.isActive ? 'current' : 'done')}>{`  ${gate ? `gate ${gate.n} waiting` : t.phase}`}</E.Text>
        {showsProgress(t) && t.isActive && <E.Text dimColor>{`  ${t.progress.done}/${t.progress.total} ${bar(t.progress.done, t.progress.total).percent}%`}</E.Text>}
        <E.Text dimColor>{`  ${where}`}</E.Text>
      </E.Button>
    )
  }
  return (
    <E.Box flexDirection="column">
      {Rule(E, `Active ${active.length}`, width)}
      <E.Box flexDirection="column" marginBottom={1}>
        {active.length === 0 ? <E.Text dimColor>None.</E.Text> : active.map(row)}
      </E.Box>
      {done.length > 0 && Rule(E, `Complete ${done.length}`, width, 'done')}
      {done.length > 0 && <E.Box flexDirection="column">{done.map(row)}</E.Box>}
      <E.Text dimColor>{'Enter on a task shows it in the other tabs.'}</E.Text>
    </E.Box>
  )
}
