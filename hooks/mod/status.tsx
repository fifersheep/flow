// Mod 3: /flow-status — "where was I?" answered with no model turn.
//
// The row's text is the whole answer (a fenced block, so it reads the same
// with no mod drawing it); the CommandOutput hook only colours it, line by
// line from each line's leading glyph. An old row keeps the state it printed
// rather than redrawing from today's snapshot.

import type { RenderElement } from 'claude-code'

import { ink } from './look'
import type { Els } from './look'
import { lineRole } from './model'

export const COMMAND = 'flow-status'
export const FENCE = '```'
const FENCE_LINE = /^(\S+: )?```$/

/** The row /flow-status printed, each line in its glyph's colour. */
export function statusRow(E: Els, text: string): RenderElement {
  // the engine heads the row with the plugin's name, so the first fence reads `flow: ```
  const lines = text.split('\n').filter(l => !FENCE_LINE.test(l))
  return (
    <E.Box flexDirection="column">
      {lines.map(line => {
        const role = lineRole(line)
        if (role === 'title') return <E.Text bold wrap="truncate-end">{line}</E.Text>
        return <E.Text {...ink(E, role)} bold={role === 'current' || role === 'you'} wrap="truncate-end">{line || ' '}</E.Text>
      })}
    </E.Box>
  )
}
