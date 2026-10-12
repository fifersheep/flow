// Mod 5 (half): the spinner carries the task's phase while Claude works.
// The other half, $.ui.status, is set by every refresh in register.tsx.

import type { RenderElement } from 'claude-code'

import type { Task } from '../../types'
import { ink } from './look'
import type { Els } from './look'
import { statusLine, waitingGate } from './model'

/**
 * The engine's spinner, and under it the task's phase in the rail's colour.
 * Under, not beside: the spinner takes the row's width, so a line beside it
 * is pushed to the far edge and cut.
 */
export function spinnerTree(E: Els, task: Task, theirs: RenderElement): RenderElement {
  return (
    <E.Box flexDirection="column">
      {theirs}
      <E.Box paddingLeft={2}>
        <E.Text {...ink(E, waitingGate(task) ? 'you' : 'current')} wrap="truncate-end">{statusLine(task)}</E.Text>
      </E.Box>
    </E.Box>
  )
}
