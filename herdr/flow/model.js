// The flow panel's reading of Herdr's live data and flow's snapshot: what each
// card says and which notifications a change is worth. No `herdr`, no
// elements, so node can test it (tests/herdr/).
//
// Two sources, joined by a task's folder:
//   - the `flow.*` labels hooks/flow_herdr.py puts on a Claude Code session's
//     terminal: which agent is on which task, phase and gate, live;
//   - hooks/flow_status.py's snapshot of a repo: each task's chain, gates,
//     progress, plan, decisions and deviations, the same document the Claude
//     Code mod draws from, so the two can't disagree.

// The person's status-line colours, one meaning each (hooks/mod/model.ts).
// Straw is a fill, never text: on a light theme it can't be read.
export const HEX = { current: "#5f87af", done: "#87af87", you: "#d7d787", wrong: "#ff8787" };

const SHORT = {
  setup: "setup", research: "research", planning: "plan", "plan-review": "plan review",
  implementation: "implement", "code-review": "review", reporting: "report", "wind-down": "wrap",
  complete: "complete",
};
export const short = (phase) => SHORT[phase] ?? phase;

/** "3/7" -> {done: 3, total: 7}; anything else -> null. */
function fraction(text) {
  const m = /^(\d+)\/(\d+)$/.exec(text ?? "");
  return m ? { done: Number(m[1]), total: Number(m[2]) } : null;
}

/** Every terminal a flow session labelled, as {address, task, phase, ...}. */
export function labelled(terminals) {
  const out = [];
  for (const t of terminals ?? []) {
    const l = t?.labels ?? {};
    if (!l["flow.task"]) continue;
    const gate = Number(l["flow.gate"]);
    out.push({
      address: t.address,
      task: l["flow.task"],
      phase: l["flow.phase"] ?? "",
      mode: l["flow.mode"] ?? "",
      progress: fraction(l["flow.progress"]),
      gate: Number.isInteger(gate) && gate > 0 ? gate : null,
      dir: l["flow.dir"] ?? "",
    });
  }
  return out;
}

const gateDoc = (n) => (n === 1 ? "the plan" : "the report");
export const gateAsk = (n) => (n === 1 ? "Gate 1 · approve the plan" : "Gate 2 · approve the merge");

/**
 * What changed between two readings of the labels that the person should
 * hear about: a gate opening, a phase moving, a task completing. Only moves
 * of one task on one terminal count; a label appearing (a session starting)
 * or going (it ending) is not news.
 */
export function events(prev, next) {
  const before = new Map((prev ?? []).map((a) => [a.address, a]));
  const out = [];
  for (const a of next) {
    const was = before.get(a.address);
    if (!was || was.task !== a.task) continue;
    const base = { address: a.address, task: a.task };
    if (a.phase === "complete" && was.phase !== "complete") {
      out.push({ ...base, kind: "complete", level: "success", title: `${a.task} is complete` });
    } else if (a.gate && a.gate !== was.gate) {
      out.push({ ...base, kind: "gate", level: "warning", title: gateAsk(a.gate), body: `${a.task}: ${gateDoc(a.gate)} is ready for you` });
    } else if (a.phase !== was.phase) {
      out.push({ ...base, kind: "phase", level: "info", title: `${a.task} → ${short(a.phase)}` });
    }
  }
  return out;
}

const GATE_ROLE = { passed: "done", waiting: "you", ahead: "todo" };

/** A snapshot task's chain as the rail draws it: phases, with gates between. */
export function steps(task) {
  const phases = task.chain.filter((p) => p !== "complete");
  const at = task.phase === "complete" ? phases.length : task.phaseIndex;
  const out = [];
  phases.forEach((phase, i) => {
    const gate = task.gates.find((g) => g.before === phase);
    if (gate) out.push({ kind: "gate", n: gate.n, role: GATE_ROLE[gate.state] ?? "todo" });
    out.push({ kind: "phase", phase, role: i < at ? "done" : i === at ? "current" : "todo" });
  });
  return out;
}

export const waitingGate = (task) => task?.gates?.find((g) => g.state === "waiting")?.n ?? null;

/**
 * The panel's cards: every active task in the loaded snapshots, and every
 * task an agent is labelled with, each with its agents. A gate waiting on the
 * person comes first, then tasks an agent is on, then the rest; newest first.
 */
export function cards(snapshots, agents) {
  const byDir = new Map();
  const card = (dir) => {
    if (!byDir.has(dir)) byDir.set(dir, { dir, task: null, labels: null, agents: [] });
    return byDir.get(dir);
  };
  const tasks = new Map();
  for (const s of snapshots ?? []) for (const t of s?.tasks ?? []) tasks.set(t.dir, t);
  for (const [dir, t] of tasks) if (t.isActive) card(dir).task = t;
  for (const a of agents ?? []) {
    if (!a.dir) continue;
    const c = card(a.dir);
    c.task ??= tasks.get(a.dir) ?? null;
    c.labels ??= a;
    c.agents.push(a);
  }
  const rank = (c) => (gateOf(c) ? 0 : c.agents.length ? 1 : 2);
  const updated = (c) => c.task?.updated ?? "";
  return [...byDir.values()].sort((a, b) =>
    rank(a) - rank(b) || updated(b).localeCompare(updated(a)) || a.dir.localeCompare(b.dir));
}

// The snapshot is read from the files, the labels from the last write a
// session made: once a task's snapshot is in, it has the last word.

/** The gate waiting on the person, or null. */
export const gateOf = (c) => (c.task ? waitingGate(c.task) : c.labels?.gate ?? null);

/** {done, total} of the checklist, or null while it's empty. */
export function progressOf(c) {
  if (!c.task) return c.labels?.progress ?? null;
  const p = c.task.progress;
  return p?.total ? { done: p.done, total: p.total } : null;
}

export const slugOf = (c) => c.task?.slug ?? c.labels?.task ?? c.dir.split("/").pop();
export const phaseOf = (c) => c.task?.phase ?? c.labels?.phase ?? "";

/** The folders whose repos the panel should read: agents' tasks, and where you are. */
export function wanted(agents, cwd) {
  const out = new Set(agents.map((a) => a.dir).filter(Boolean));
  if (cwd) out.add(cwd);
  return [...out];
}

/**
 * The Claude Code agents whose session has labelled nothing: started before
 * this flow was installed, so running hooks that never label. They show no
 * task, which isn't the same as having none.
 */
export function unreporting(terminals, agents) {
  const reports = new Set((terminals ?? [])
    .filter((t) => t?.labels?.["flow.version"] || t?.labels?.["flow.task"]).map((t) => t.address));
  return (agents ?? []).filter((a) => a.app === "claude-code" && !reports.has(a.address));
}

/** A key that changes whenever any agent's flow labels do. */
export const signature = (agents) =>
  JSON.stringify(agents.map((a) => [a.address, a.task, a.phase, a.gate, a.progress?.done, a.dir]));
