// The flow mod's contract: the snapshot hooks/flow_status.py prints, and the
// values the mod keeps in $.state. `claude plugin validate` holds every
// $.state key hooks/mod/ names to the PluginState entry below.

export type GateState = 'passed' | 'waiting' | 'ahead'

export interface Gate {
  n: number
  /** the phase this gate opens */
  before: string
  /** waiting: the phase before it is current, so the next step is the user's */
  state: GateState
  date: string | null
}

export interface ProgressItem {
  text: string
  done: boolean
}

export interface Task {
  slug: string
  /** the task's folder name under the artifacts dir; the key tasks are told apart by */
  folder: string
  title: string
  ticket: string
  ticketId: string
  mode: string
  phase: string
  phaseIndex: number
  chain: string[]
  branch: string
  worktree: string
  created: string
  updated: string
  isActive: boolean
  /** on the session's branch, in the session's own checkout */
  isHere: boolean
  dir: string
  workflowPath: string
  planPath: string | null
  reportPath: string | null
  nextAction: string
  progress: { done: number; total: number; items: ProgressItem[] }
  gates: Gate[]
  decisions: string[]
  deviations: string[]
  plan: string | null
}

export interface Snapshot {
  schema: number
  root: string
  branch: string | null
  /** folder of the active task on the session's branch, if any */
  current: string | null
  tasks: Task[]
  error?: string
}

export type PaneTab = 'progress' | 'plan' | 'decisions' | 'deviations' | 'tasks'

declare module 'claude-code' {
  interface PluginState {
    flow: {
      snapshot: Snapshot | null
      tab: PaneTab
      /** folder the pane shows; null follows the current task */
      picked: string | null
    }
  }
}
