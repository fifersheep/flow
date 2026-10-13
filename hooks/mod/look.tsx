// Drawing helpers every flow surface shares, so the rail, the bar and the gate
// row look the same in the band, the pane and /flow-status.

import type { Elements, RenderElement, TextProps } from 'claude-code'

import type { Gate, PaneTab, Task } from '../../types'
import { bar, GLYPH, glyphOf, gateWord, showsProgress, steps } from './model'
import type { OpenKind, OpenTarget, Palette, Role, Step } from './model'

/** A surface's elements, and the palette that surface draws the roles in. */
export type Els = Pick<Elements['terminal'], 'Box' | 'Text' | 'Button' | 'Markdown'> & { paint: Palette }

export const PANE = 'flow'

/**
 * What a drawing's controls do. The trees are built here, away from `$`;
 * register.tsx makes these from its own functions, where the engine calls are.
 */
export interface Actions {
  openPane(tab?: PaneTab, folder?: string): void
  setTab(tab: PaneTab): void
  pick(folder: string): void
  /**
   * Approve / request changes put the words in the prompt and stop there: the
   * person presses Enter, so the approval the skill records is their own
   * message, and the validator stays the only thing that opens a gate.
   */
  draft(text: string): void
  /** A terminal or the editor in `dir`, the apps the plugin's settings name. */
  open(kind: OpenKind, dir: string): void
  /** The editor setting as the button reads it: `vs code`. */
  editorName: string
}

/** Text props for a role: one of the four colours, or dim for not-yet. */
export function ink(E: Els, role: Role | 'plain'): TextProps {
  if (role === 'todo') return { dimColor: true }
  if (role === 'plain') return {}
  return { color: E.paint[role] }
}

function stepLabel(step: Step, size: 'long' | 'short' | 'glyph'): string {
  const glyph = glyphOf(step)
  if (step.kind === 'gate') return size === 'glyph' ? glyph : `${glyph}${step.gate.n}`
  if (size === 'glyph') return glyph
  return `${glyph} ${size === 'long' ? step.phase : step.short}`
}

/** The horizontal rail, at the widest label set that fits `width`. */
export function Rail(E: Els, task: Task, width: number): RenderElement {
  const all = steps(task)
  const sep = (size: 'long' | 'short' | 'glyph') => (size === 'glyph' ? '' : ' ─ ')
  const fits = (size: 'long' | 'short' | 'glyph') =>
    all.map(s => stepLabel(s, size)).join(sep(size)).length <= width
  const size = fits('long') ? 'long' : fits('short') ? 'short' : 'glyph'
  const parts: RenderElement[] = []
  all.forEach((step, i) => {
    if (i > 0 && sep(size)) parts.push(<E.Text dimColor>{sep(size)}</E.Text>)
    parts.push(
      <E.Text {...ink(E, step.role)} bold={step.role === 'current' || step.role === 'you'}>
        {stepLabel(step, size)}
      </E.Text>,
    )
  })
  if (size === 'glyph') {
    const now = all.find(s => s.role === 'current' || s.role === 'you')
    if (now) parts.push(<E.Text {...ink(E, now.role)} bold>{'  ' + (now.kind === 'gate' ? `gate ${now.gate.n}` : now.phase)}</E.Text>)
  }
  return <E.Text wrap="truncate-end">{parts}</E.Text>
}

/** `2/4 [##########----------] 50%`: the filled part coloured, the rest plain. */
export function Bar(E: Els, task: Task): RenderElement | null {
  if (!showsProgress(task)) return null
  const { done, total } = task.progress
  const b = bar(done, total)
  const role = done >= total ? 'done' : 'current'
  return (
    <E.Text>
      <E.Text {...ink(E, role)}>{`${done}/${total} [`}</E.Text>
      <E.Text {...ink(E, role)}>{b.filled}</E.Text>
      <E.Text>{b.empty}</E.Text>
      <E.Text {...ink(E, role)}>{`] ${b.percent}%`}</E.Text>
    </E.Text>
  )
}

/** `── Title ─────────`: a coloured heading across the width, for separation. */
export function Rule(E: Els, title: string, width: number, role: Role | 'plain' = 'current'): RenderElement {
  const head = `── ${title} `
  return (
    <E.Text wrap="truncate-end">
      <E.Text dimColor>{'── '}</E.Text>
      <E.Text {...ink(E, role)} bold>{title}</E.Text>
      <E.Text dimColor>{' ' + '─'.repeat(Math.max(0, width - head.length))}</E.Text>
    </E.Text>
  )
}

export function approvalText(g: Gate): string {
  return g.n === 1 ? 'Gate 1: I approve the plan.' : 'Gate 2: I approve the merge.'
}

export function changesText(g: Gate): string {
  return `Gate ${g.n}: changes requested — `
}

/** What a waiting gate asks, in straw. */
export function GateTitle(E: Els, g: Gate): RenderElement {
  return <E.Text color={E.paint.you} bold wrap="truncate-end">{`${GLYPH.gateWaiting} gate ${g.n} · ${gateWord(g)} is yours to give`}</E.Text>
}

/** A waiting gate's three actions, together on a row of their own. */
export function GateActions(E: Els, act: Actions, task: Task, g: Gate): RenderElement {
  const you = E.paint.you
  const doc = g.n === 1 ? 'plan' : 'report'
  return (
    <E.Box flexDirection="row" columnGap={3} flexWrap="wrap">
      <E.Button key={`gate-${g.n}-open`} label={`open ${doc}`} hotkey="p" plain
        onPress={() => act.openPane(g.n === 1 ? 'plan' : 'progress', task.folder)}>
        <E.Text color={you}>{`open ${doc}`}</E.Text>
      </E.Button>
      <E.Button key={`gate-${g.n}-approve`} label="approve" hotkey="a" plain onPress={() => act.draft(approvalText(g))}>
        <E.Text color={you} bold>approve</E.Text>
      </E.Button>
      <E.Button key={`gate-${g.n}-changes`} label="request changes" hotkey="r" plain onPress={() => act.draft(changesText(g))}>
        <E.Text color={you}>request changes</E.Text>
      </E.Button>
    </E.Box>
  )
}

/** The straw block a waiting gate draws: what's asked, then the actions. */
export function GateRow(E: Els, act: Actions, task: Task, g: Gate): RenderElement {
  return (
    <E.Box flexDirection="column">
      {GateTitle(E, g)}
      {GateActions(E, act, task, g)}
    </E.Box>
  )
}

/**
 * `t: terminal  e: vs code`, opening `at`'s folder; dim until wanted. `where`
 * keeps the keys apart when the band and the pane both draw a pair.
 */
export function OpenButtons(E: Els, act: Actions, at: OpenTarget, where: string): RenderElement[] {
  if ('error' in at) return []
  return [
    <E.Button key={`${where}-terminal`} label="terminal" hotkey="t" plain dimColor onPress={() => act.open('terminal', at.dir)} />,
    <E.Button key={`${where}-editor`} label={act.editorName} hotkey="e" plain dimColor onPress={() => act.open('editor', at.dir)} />,
  ]
}
