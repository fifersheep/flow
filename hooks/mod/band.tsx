// Mod 1: the phase rail in the band above the prompt. Always there while the
// session's branch has an active task; framed in periwinkle, or in straw
// while a gate waits on the person.

import type { RenderElement, RenderPropsOf } from 'claude-code'

import type { Snapshot } from '../../types'
import { Bar, GateRow, ink, OpenButtons, Rail } from './look'
import type { Actions, Els } from './look'
import { GLYPH, hereTask, openTarget, plural, statusLine, waitingGate } from './model'

const ROWS = 5 // frame (2) + heading, rail, next

/** The band's tree, or null to leave the band as it is. */
export function bandTree(E: Els, s: Snapshot | null, props: RenderPropsOf['AbovePrompt'], act: Actions): RenderElement | null {
  const task = hereTask(s)
  const elsewhere = s?.tasks.filter(t => t.isActive && !t.isHere) ?? []
  if (!task && elsewhere.length === 0) return null

  if (!task) {
    // nothing on this branch: one quiet line, so other work isn't forgotten
    return (
      <E.Box flexDirection="row" columnGap={2}>
        <E.Text dimColor>{`flow · ${plural(elsewhere.length, 'active task')} on other branches`}</E.Text>
        <E.Button key="band-tasks" label="tasks" hotkey="o" plain dimColor onPress={() => act.openPane('tasks')} />
        {OpenButtons(E, act, openTarget(s), 'band')}
      </E.Box>
    )
  }

  const gate = waitingGate(task)
  if (props.maxRows < ROWS) {
    // no room for the frame: the status line's words, in the rail's colour
    return <E.Text {...ink(E, gate ? 'you' : 'current')} bold wrap="truncate-end">{statusLine(task)}</E.Text>
  }

  return (
    <E.Box flexDirection="column" borderStyle="round" borderColor={gate ? E.paint.you : E.paint.current} paddingX={1}>
      <E.Box flexDirection="row" justifyContent="space-between" columnGap={2}>
        <E.Text wrap="truncate-end">
          <E.Text color={E.paint.current} bold>flow</E.Text>
          <E.Text dimColor>{'  │  '}</E.Text>
          <E.Text bold>{task.slug}</E.Text>
          <E.Text dimColor>{`  ${[task.mode, task.ticketId].filter(Boolean).join(' · ')}`}</E.Text>
          {task.deviations.length > 0 && (
            <E.Text color={E.paint.wrong}>{`  ${GLYPH.deviation} ${plural(task.deviations.length, 'deviation')}`}</E.Text>
          )}
        </E.Text>
        {Bar(E, task)}
      </E.Box>
      {Rail(E, task, Math.max(20, props.bodyColumns - 4))}
      <E.Box flexDirection="row" justifyContent="space-between" columnGap={2}>
        {gate ? (
          GateRow(E, act, task, gate)
        ) : (
          <E.Text wrap="truncate-end">
            <E.Text color={E.paint.current} bold>{`${GLYPH.next} next  `}</E.Text>
            <E.Text>{task.nextAction || '—'}</E.Text>
          </E.Text>
        )}
        <E.Box flexDirection="row" columnGap={2} flexShrink={0}>
          {!gate && <E.Button key="band-open" label="pane" hotkey="o" plain dimColor onPress={() => act.openPane('progress', task.folder)} />}
          {OpenButtons(E, act, openTarget(s), 'band')}
        </E.Box>
      </E.Box>
    </E.Box>
  )
}
