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
 *
 * A gate is news once its agent stops working (`working`, from Herdr's agent
 * status): flow labels the gate as soon as the phase before it starts, while
 * the critic, or the report and PR, is still to come. It's news once per gate:
 * each reading carries `told`, the gate already announced, into the next.
 */
export function events(prev, next) {
  const before = new Map((prev ?? []).map((a) => [a.address, a]));
  const out = [];
  for (const a of next) {
    const was = before.get(a.address);
    a.told = was && was.task === a.task && was.gate === a.gate ? was.told ?? null : null;
    if (!was || was.task !== a.task) {
      if (a.gate && !a.working) a.told = a.gate; // already waiting when first seen: not news
      continue;
    }
    const base = { address: a.address, task: a.task };
    const ready = a.gate && !a.working && a.told !== a.gate;
    if (ready) a.told = a.gate;
    if (a.phase === "complete" && was.phase !== "complete") {
      out.push({ ...base, kind: "complete", level: "success", title: `${a.task} is complete` });
    } else if (ready) {
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
  const repoOf = new Map();
  for (const s of snapshots ?? []) for (const t of s?.tasks ?? []) { tasks.set(t.dir, t); repoOf.set(t.dir, s.repo ?? s.root ?? null); }
  for (const [dir, t] of tasks) if (t.isActive) card(dir).task = t;
  for (const a of agents ?? []) {
    if (!a.dir) continue;
    const c = card(a.dir);
    c.task ??= tasks.get(a.dir) ?? null;
    c.labels ??= a;
    c.agents.push(a);
  }
  for (const c of byDir.values()) c.repo = repoOf.get(c.dir) ?? null;
  const rank = (c) => (gateOf(c) ? 0 : c.agents.length ? 1 : 2);
  const updated = (c) => c.task?.updated ?? "";
  return [...byDir.values()].sort((a, b) =>
    rank(a) - rank(b) || updated(b).localeCompare(updated(a)) || a.dir.localeCompare(b.dir));
}

// The snapshot is read from the files, the labels from the last write a
// session made: once a task's snapshot is in, it has the last word.

/**
 * The gate waiting on the person, or null. flow marks a gate waiting as soon
 * as the phase before it starts, and the agent still has that phase's work to
 * do (the critic in plan review, the report and PR in reporting), so while an
 * agent on the task is working, the gate isn't the person's yet.
 */
export const gateOf = (c) => (c.agents?.some((a) => a.info?.status === "working") ? null
  : c.task ? waitingGate(c.task) : c.labels?.gate ?? null);

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

// Grouping. The panel groups its cards by repo, or into groups the person
// makes (work that spans repos). How, and the groups, are Herdr's shared
// state (`flow.groups`), so every copy agrees and it outlasts a restart:
//   {by: "repo" | "manual", names: [group, ...], member: {dir: group}, closed: [key, ...]}
// A card is keyed by its task folder, as the open card is.

export const UNGROUPED = "ungrouped";

/** Whatever shared() held, as a grouping state; anything malformed is dropped. */
export function grouping(v) {
  const names = Array.isArray(v?.names) ? [...new Set(v.names.filter((n) => typeof n === "string" && n.trim()))] : [];
  const member = {};
  for (const [dir, name] of Object.entries(v?.member ?? {})) if (names.includes(name)) member[dir] = name;
  const closed = Array.isArray(v?.closed) ? v.closed.filter((k) => typeof k === "string") : [];
  return { by: v?.by === "manual" ? "manual" : "repo", names, member, closed };
}

export const groupBy = (g, by) => ({ ...g, by: by === "manual" ? "manual" : "repo" });

/** Opens a group if it's closed, closes it if it's open. */
export const toggleGroup = (g, key) =>
  ({ ...g, closed: g.closed.includes(key) ? g.closed.filter((k) => k !== key) : [...g.closed, key] });

/** Puts a card in a group, making the group if it's new; null takes it out of any. */
export function assign(g, dir, name) {
  const member = { ...g.member };
  const n = typeof name === "string" ? name.trim() : "";
  if (!n) { delete member[dir]; return { ...g, member }; }
  member[dir] = n;
  return { ...g, names: g.names.includes(n) ? g.names : [...g.names, n], member };
}

/** Removes a group; its cards go back to ungrouped. */
export function dropGroup(g, name) {
  const member = Object.fromEntries(Object.entries(g.member).filter(([, n]) => n !== name));
  const key = `group:${name}`, gone = new Set([key, boardKey(key)]);
  return { ...g, names: g.names.filter((n) => n !== name), member, closed: g.closed.filter((k) => !gone.has(k)) };
}

/** A lane's key in `closed` on the stages board: folded apart from the panel's group. */
export const boardKey = (key) => `board:${key}`;

/** A repo's name: its folder's, with its parent's when two repos share one. */
function repoNames(repos) {
  const base = (r) => r.split("/").filter(Boolean).pop() ?? r;
  const count = new Map();
  for (const r of repos) count.set(base(r), (count.get(base(r)) ?? 0) + 1);
  return new Map(repos.map((r) => [r, count.get(base(r)) > 1 ? r.split("/").filter(Boolean).slice(-2).join("/") : base(r)]));
}

/**
 * The cards, in groups: [{key, name, kind, cards, waiting, closed}].
 * By repo, a group per repo in the order its first card comes (so a gate
 * waiting brings its repo up); a card whose repo isn't read yet waits in
 * "reading". By hand, the person's groups in the order they made them, empty
 * ones too (so they can be filled or removed), then the ungrouped cards.
 */
export function groups(list, g) {
  const out = [];
  const add = (key, name, kind, cards) =>
    out.push({ key, name, kind, cards, waiting: cards.filter(gateOf).length, closed: g.closed.includes(key) });
  if (g.by === "manual") {
    for (const name of g.names) add(`group:${name}`, name, "group", list.filter((c) => g.member[c.dir] === name));
    const rest = list.filter((c) => !g.names.includes(g.member[c.dir]));
    if (rest.length) add(UNGROUPED, g.names.length ? "ungrouped" : "all tasks", "ungrouped", rest);
    return out;
  }
  const order = [];
  const by = new Map();
  for (const c of list) {
    const r = c.repo ?? "";
    if (!by.has(r)) { by.set(r, []); order.push(r); }
    by.get(r).push(c);
  }
  const names = repoNames(order.filter(Boolean));
  for (const r of order) add(r ? `repo:${r}` : "repo:", r ? names.get(r) : "reading…", "repo", by.get(r));
  return out;
}

// The board: the panel's cards across a whole Herdr tab, two ways. "stages"
// lays them out by where they are (Shape | Gate 1 | Build | Gate 2 | Land),
// in lanes by repo or by hand-made group; "next" by who has to act next. Each
// opens as its own tab (tab.new {mod: "flow", props: {view}}), named so a
// second ask finds the first instead of making another.

export const BOARDS = { stages: "flow · stages", next: "flow · next up" };

/** The board a copy was opened as, from its props; null for the panel. */
export const boardOf = (props) => (Object.hasOwn(BOARDS, props?.view ?? "") ? props.view : null);

export const STAGES = [
  { name: "Shape", sub: "setup · research · plan · review" },
  { name: "Gate 1", sub: "approve the plan", gate: 1 },
  { name: "Build", sub: "implement · review · report" },
  { name: "Gate 2", sub: "approve the merge", gate: 2 },
  { name: "Land", sub: "wrap · done" },
];
const BUILD = new Set(["implementation", "code-review", "reporting"]);
const LAND = new Set(["wind-down", "complete"]);

/** Which of STAGES a card sits in: a waiting gate is a column of its own. */
export function stageOf(c) {
  const gate = gateOf(c), phase = phaseOf(c);
  if (gate === 1) return 1;
  if (gate === 2) return 3;
  return BUILD.has(phase) ? 2 : LAND.has(phase) ? 4 : 0;
}

/**
 * Who has the ball. "gate": a gate waits on you. "turn": its agent stopped
 * (blocked, done or idle), so it's waiting on you too. "working": an agent is
 * on it. "parked": active, but no session is. "done": complete.
 */
export function turnOf(c) {
  if (phaseOf(c) === "complete") return "done";
  if (gateOf(c)) return "gate";
  if (!c.agents.length) return "parked";
  return c.agents.some((a) => a.info?.status === "working") ? "working" : "turn";
}

/**
 * Tasks completed in the last `days` days that aren't cards already: a done
 * task has no card unless an agent is still labelled with it. Newest first.
 */
export function finished(snapshots, list, today, days = 7) {
  const have = new Set(list.map((c) => c.dir));
  const from = new Date(Date.parse(today) - days * 86400000).toISOString().slice(0, 10);
  const out = [];
  for (const s of snapshots ?? []) for (const t of s?.tasks ?? []) {
    if (t.phase !== "complete" || have.has(t.dir) || (t.updated ?? "") < from) continue;
    have.add(t.dir);
    out.push({ dir: t.dir, task: t, labels: null, agents: [], repo: s.repo ?? s.root ?? null });
  }
  return out.sort((a, b) => b.task.updated.localeCompare(a.task.updated));
}

/** When a card's agents last changed state (ms), from their tabs; null if unknown. */
export function since(c, tabs) {
  const at = c.agents.map((a) => tabs.get(a.info?.tab)?.changed_at).filter((n) => typeof n === "number");
  return at.length ? Math.max(...at) : null;
}

/** "4m", "2h", "3d": how long ago, roughly. */
export function ago(ms, now) {
  const m = Math.max(0, Math.floor((now - ms) / 60000));
  return m < 1 ? "<1m" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`;
}

/**
 * The "next" board's columns: [{key, name, sub, sections: [{label, cards}]}].
 * Waiting on you comes first, the longest wait at the top; `when` is since().
 */
export function columns(list, when = () => null) {
  const by = (turn) => list.filter((c) => turnOf(c) === turn);
  const oldest = (a, b) => (when(a) ?? Infinity) - (when(b) ?? Infinity);
  return [
    { key: "you", name: "Needs you", sub: "A gate is open, or an agent stopped for you.",
      sections: [{ label: "at a gate", cards: by("gate").sort(oldest) }, { label: "your turn", cards: by("turn").sort(oldest) }] },
    { key: "working", name: "Agent working", sub: "Nothing to do. The current phase breathes.", sections: [{ label: "", cards: by("working") }] },
    { key: "parked", name: "Parked", sub: "Active, with no session on it.", sections: [{ label: "", cards: by("parked") }] },
    { key: "done", name: "Done", sub: "Completed this week.", sections: [{ label: "", cards: by("done") }] },
  ];
}

/** The tab a board already has in the shown space, by its name; null if none. */
export function boardTab(spaces, view) {
  const space = (spaces ?? []).find((s) => s.active);
  return space?.tabs?.find((t) => t.name === BOARDS[view])?.id ?? null;
}

// Sessions, from a board: starting a task, resuming a parked one, ending one.
// Starting and resuming open a tab running claude with its first message
// (tab.new); ending types /exit and closes the pane once claude has quit
// (flow_herdr.py end). Nothing here answers anything for the person: after
// the first message, the session is theirs.

/**
 * What ending an agent's session takes: "end" (its task is complete),
 * "confirm" (it isn't: ask first), "answer" (it's asking the person
 * something, so /exit would land in the question: answer it first), or null
 * (it's working, or isn't an agent Herdr knows).
 */
export function endable(c, a) {
  const s = a?.info?.status;
  if (!s || s === "working") return null;
  if (s === "blocked") return "answer";
  return phaseOf(c) === "complete" ? "end" : "confirm";
}

/** Completed tasks whose session is still open: the finished-sessions tray. */
export const lingering = (list) => list.filter((c) => phaseOf(c) === "complete" && c.agents.length > 0);

export const MODES = ["suggest", "full", "lite"];

/** A new task's first message: /flow and the text, saying the mode when one was picked. */
export function startMessage(text, mode) {
  const t = (text ?? "").trim().replace(/\s+/g, " ");
  if (!t) return null;
  return mode === "full" || mode === "lite" ? `/flow ${t} (run this ${mode})` : `/flow ${t}`;
}

/** A new task's tab name: its ticket ID when the text starts with one, else its first words. */
export function tabName(text) {
  const t = (text ?? "").trim();
  const id = /^([A-Z][A-Z0-9]*-\d+)\b/.exec(t)?.[1];
  if (id) return id;
  return t.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(" ").slice(0, 4).join("-").slice(0, 28) || "flow";
}

/** tab.new's args for a new task in `folder`; null without text. */
export function startArgs(folder, text, mode) {
  const task = startMessage(text, mode);
  return task && folder ? { name: tabName(text), folder, argv: ["claude"], task } : null;
}

/** tab.new's args to resume a task in its own checkout, where /flow finds it; null without one. */
export function resumeArgs(c) {
  const folder = c.task?.worktree;
  return folder ? { name: slugOf(c), folder, argv: ["claude"], task: "/flow" } : null;
}

/**
 * The repos a new task can start in: each snapshot's repo (a worktree's main
 * checkout) first, where the work is, then the rest of `below`, the repos in
 * the board's folder (flow_herdr.py repos); named.
 */
export function startRepos(snapshots, below = []) {
  const roots = [...new Set([...(snapshots ?? []).map((s) => s?.repo ?? s?.root), ...(below ?? [])].filter(Boolean))];
  const names = repoNames(roots);
  return roots.map((root) => ({ root, name: names.get(root) }));
}

/** The repos the start bar's menu lists: by name, those whose name has `text` in it. */
export function pickable(repos, text) {
  const q = (text ?? "").trim().toLowerCase();
  return [...(repos ?? [])].filter((r) => !q || r.name.toLowerCase().includes(q)).sort((x, y) => x.name.localeCompare(y.name));
}
