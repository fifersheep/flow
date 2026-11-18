// The flow panel's pure logic (herdr/flow/model.js). Run: node --test tests/herdr/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { ago, assign, boardKey, boardOf, boardTab, cards, columns, dropGroup, events, finished, gateOf, groupBy, grouping, groups, labelled, progressOf, signature, since, stageOf, steps, toggleGroup, turnOf, unreporting, wanted } from "../../herdr/flow/model.js";

const term = (address, labels) => ({ address, labels });
const flow = (over = {}) => ({ "flow.task": "add-widget", "flow.phase": "implementation", "flow.mode": "full", "flow.progress": "3/7", "flow.dir": "/r/docs/tasks/a", ...over });

const task = (over = {}) => ({
  slug: "add-widget", dir: "/r/docs/tasks/a", phase: "implementation", phaseIndex: 4, isActive: true, updated: "2026-11-10",
  chain: ["setup", "research", "planning", "plan-review", "implementation", "code-review", "reporting", "wind-down", "complete"],
  gates: [{ n: 1, before: "implementation", state: "passed" }, { n: 2, before: "wind-down", state: "ahead" }],
  progress: { done: 3, total: 7, items: [] }, decisions: [], deviations: [], plan: null, ...over,
});

test("labelled reads flow's labels and skips the rest", () => {
  const out = labelled([term("t1", {}), term("t2", flow({ "flow.gate": "1" })), term("t3", flow({ "flow.progress": "" }))]);
  assert.equal(out.length, 2);
  assert.deepEqual(out[0], { address: "t2", task: "add-widget", phase: "implementation", mode: "full", progress: { done: 3, total: 7 }, gate: 1, dir: "/r/docs/tasks/a" });
  assert.equal(out[1].progress, null);
  assert.equal(out[1].gate, null);
});

test("a gate opening is news; a phase moving is news; completing is news", () => {
  const before = labelled([term("t2", flow({ "flow.phase": "plan-review" })), term("t3", flow({ "flow.task": "b" })), term("t4", flow({ "flow.task": "c" }))]);
  const after = labelled([
    term("t2", flow({ "flow.phase": "plan-review", "flow.gate": "1" })),
    term("t3", flow({ "flow.task": "b", "flow.phase": "code-review" })),
    term("t4", flow({ "flow.task": "c", "flow.phase": "complete" })),
  ]);
  const news = events(before, after);
  assert.deepEqual(news.map((e) => [e.address, e.kind, e.level]), [["t2", "gate", "warning"], ["t3", "phase", "info"], ["t4", "complete", "success"]]);
  assert.equal(news[0].title, "Gate 1 · approve the plan");
  assert.equal(news[1].title, "b → review");
});

test("a session starting, ending or switching task is not news", () => {
  const one = labelled([term("t2", flow({ "flow.gate": "2" }))]);
  assert.deepEqual(events([], one), []);
  assert.deepEqual(events(one, []), []);
  assert.deepEqual(events(one, labelled([term("t2", flow({ "flow.task": "other", "flow.gate": "1" }))])), []);
  assert.deepEqual(events(one, one), []);
});

test("steps put each gate before the phase it opens", () => {
  const s = steps(task());
  assert.deepEqual(s.slice(3, 6), [{ kind: "phase", phase: "plan-review", role: "done" }, { kind: "gate", n: 1, role: "done" }, { kind: "phase", phase: "implementation", role: "current" }]);
  assert.equal(s.length, 10); // eight phases and two gates; complete isn't drawn
  const waiting = steps(task({ phase: "plan-review", phaseIndex: 3, gates: [{ n: 1, before: "implementation", state: "waiting" }] }));
  assert.equal(waiting.find((x) => x.kind === "gate").role, "you");
});

test("cards join snapshots and agents by folder; a waiting gate comes first", () => {
  const snaps = [{ tasks: [
    task(),
    task({ slug: "b", dir: "/r/docs/tasks/b", updated: "2026-11-11" }),
    task({ slug: "done", dir: "/r/docs/tasks/c", isActive: false }),
  ] }];
  const agents = labelled([term("t9", flow({ "flow.task": "x", "flow.dir": "/s/docs/tasks/x", "flow.gate": "1" })), term("t2", flow())]);
  const list = cards(snaps, agents);
  assert.deepEqual(list.map((c) => c.dir), ["/s/docs/tasks/x", "/r/docs/tasks/a", "/r/docs/tasks/b"]);
  assert.equal(gateOf(list[0]), 1); // from the label: its repo isn't read yet
  assert.equal(list[1].agents[0].address, "t2");
  assert.equal(list[1].task.slug, "add-widget");
  assert.deepEqual(progressOf(list[0]), { done: 3, total: 7 });
});

test("the snapshot's gate wins over a label's", () => {
  const [c] = cards([{ tasks: [task({ gates: [{ n: 1, before: "implementation", state: "passed" }] })] }], labelled([term("t2", flow({ "flow.gate": "1" }))]));
  assert.equal(gateOf(c), null);
});

test("wanted asks for agents' folders and where you are, once each", () => {
  const agents = labelled([term("t2", flow()), term("t3", flow())]);
  assert.deepEqual(wanted(agents, "/here"), ["/r/docs/tasks/a", "/here"]);
  assert.notEqual(signature(agents), signature(labelled([term("t2", flow({ "flow.progress": "4/7" }))])));
});

test("unreporting is the Claude Code agents whose terminal has no flow label", () => {
  const terminals = [
    { address: "t1", labels: { "flow.version": "0.10.2" } },
    { address: "t2", labels: {} },
    { address: "t3", labels: { "flow.version": "0.10.2", "flow.task": "x" } },
  ];
  const agents = [
    { address: "t1", app: "claude-code" }, { address: "t2", app: "claude-code" },
    { address: "t3", app: "claude-code" }, { address: "t4", app: "codex" }, { address: "t5", app: "claude-code" },
  ];
  assert.deepEqual(unreporting(terminals, agents).map((a) => a.address), ["t2", "t5"]);
  // a task's labels from a session that started before flow.version existed
  assert.deepEqual(unreporting([{ address: "t2", labels: { "flow.task": "x" } }], agents.slice(1, 2)), []);
  assert.deepEqual(unreporting(undefined, undefined), []);
});

const card = (dir, repo, gate = null) => ({ dir, repo, task: null, labels: gate ? { gate } : null, agents: [] });

test("cards carry the repo of the snapshot they came from", () => {
  const list = cards([{ root: "/wt", repo: "/r", tasks: [task()] }, { root: "/s", tasks: [task({ dir: "/s/docs/tasks/b" })] }],
    labelled([term("t9", flow({ "flow.dir": "/x/docs/tasks/x" }))]));
  assert.deepEqual(list.map((c) => [c.dir, c.repo]), [["/x/docs/tasks/x", null], ["/r/docs/tasks/a", "/r"], ["/s/docs/tasks/b", "/s"]]);
});

test("grouping reads anything, keeping only what makes sense", () => {
  assert.deepEqual(grouping(undefined), { by: "repo", names: [], member: {}, closed: [] });
  assert.deepEqual(grouping({ by: "manual", names: ["a", "a", 3, " "], member: { "/d": "a", "/e": "gone" }, closed: ["k", 1] }),
    { by: "manual", names: ["a"], member: { "/d": "a" }, closed: ["k"] });
  assert.equal(groupBy(grouping({}), "manual").by, "manual");
  assert.equal(groupBy(grouping({}), "nonsense").by, "repo");
});

test("by repo, a group per repo in the order its first card comes", () => {
  const list = [card("/a/1", "/w/app", 1), card("/b/1", "/w/api"), card("/a/2", "/w/app"), card("/c/1", null)];
  const out = groups(list, grouping({}));
  assert.deepEqual(out.map((x) => [x.key, x.name, x.cards.length, x.waiting]),
    [["repo:/w/app", "app", 2, 1], ["repo:/w/api", "api", 1, 0], ["repo:", "reading…", 1, 0]]);
  // two repos with one name show their parent too
  assert.deepEqual(groups([card("/1", "/x/app"), card("/2", "/y/app")], grouping({})).map((x) => x.name), ["x/app", "y/app"]);
});

test("by hand, the person's groups in order, empty ones too, then the rest", () => {
  let g = groupBy(grouping({}), "manual");
  const list = [card("/a/1", "/w/app"), card("/b/1", "/w/api"), card("/c/1", "/w/web")];
  assert.deepEqual(groups(list, g).map((x) => [x.name, x.cards.length]), [["all tasks", 3]]);
  g = assign(g, "/b/1", " checkout ");
  g = assign(g, "/a/1", "checkout");
  g = assign(g, "/c/1", "later");
  g = assign(g, "/c/1", null);
  assert.deepEqual(g.names, ["checkout", "later"]);
  assert.deepEqual(groups(list, g).map((x) => [x.key, x.cards.map((c) => c.dir)]),
    [["group:checkout", ["/a/1", "/b/1"]], ["group:later", []], ["ungrouped", ["/c/1"]]]);
  g = toggleGroup(g, "group:checkout");
  assert.equal(groups(list, g)[0].closed, true);
  g = dropGroup(g, "checkout");
  assert.deepEqual(g, { by: "manual", names: ["later"], member: {}, closed: [] });
  assert.equal(toggleGroup(toggleGroup(g, "k"), "k").closed.length, 0);
});

// The board

const on = (over = {}, ...agents) => ({ dir: "/r/docs/tasks/a", task: task(over), labels: null, agents, repo: "/r" });
const agent = (status, tab = "tb1") => ({ address: "t1", info: { status, tab } });
const gate = (n) => ({ phase: n === 1 ? "plan-review" : "reporting", gates: [{ n, state: "waiting", before: n === 1 ? "implementation" : "wind-down" }] });

// The gates as hooks/flow_status.py gates() reads them, with none approved
// yet: the one ahead of the phase is waiting as soon as the phase starts.
const FULL = ["setup", "research", "planning", "plan-review", "implementation", "code-review", "reporting", "wind-down", "complete"];
const LITE = ["setup", "planning", "plan-review", "implementation", "code-review", "wind-down", "complete"];
function snap(phase, chain = FULL) {
  const at = chain.indexOf(phase);
  const gates = [[1, "implementation"], [2, "wind-down"]].map(([n, before]) => {
    const i = chain.indexOf(before);
    return { n, before, state: at >= i ? "passed" : at === i - 1 ? "waiting" : "ahead" };
  });
  return { phase, phaseIndex: at, chain, mode: chain === LITE ? "lite" : "full", gates };
}

test("removing a group forgets its folds, the board's too", () => {
  let g = assign(groupBy(grouping({}), "manual"), "/a", "x");
  g = toggleGroup(toggleGroup(g, "group:x"), boardKey("group:x"));
  assert.deepEqual(g.closed, ["group:x", "board:group:x"]);
  g = assign(dropGroup(g, "x"), "/a", "x");
  assert.deepEqual(g.closed, []);
});

test("boardOf takes only the boards it knows from the props", () => {
  assert.equal(boardOf({ view: "stages" }), "stages");
  assert.equal(boardOf({ view: "next" }), "next");
  for (const p of [undefined, null, {}, { view: "toString" }, { view: "list" }]) assert.equal(boardOf(p), null);
});

test("a card's stage: its phase, or the gate's column once the gate is the person's", () => {
  // while its agent works, a task in the phase before a gate is still in that phase's stage
  assert.deepEqual(FULL.map((phase) => stageOf(on(snap(phase), agent("working")))), [0, 0, 0, 0, 2, 2, 2, 4, 4]);
  assert.deepEqual(LITE.map((phase) => stageOf(on(snap(phase, LITE), agent("working")))), [0, 0, 0, 2, 2, 4, 4]);
  // when it stops, or with no session, the gate is waiting on the person
  assert.deepEqual(FULL.map((phase) => stageOf(on(snap(phase), agent("idle")))), [0, 0, 0, 1, 2, 2, 3, 4, 4]);
  assert.deepEqual(LITE.map((phase) => stageOf(on(snap(phase, LITE)))), [0, 0, 1, 2, 3, 4, 4]);
  assert.equal(stageOf({ dir: "/x", task: null, labels: { phase: "", gate: null }, agents: [] }), 0);
  assert.equal(stageOf({ dir: "/x", task: null, labels: { phase: "reporting", gate: 2 }, agents: [] }), 3);
});

test("a gate isn't the person's while an agent on the task is still working", () => {
  const working = on(snap("plan-review"), agent("working"));
  assert.equal(gateOf(working), null); // the critic is still running
  assert.equal(gateOf(on(snap("plan-review"), agent("idle"))), 1);
  assert.equal(gateOf(on(snap("plan-review"), agent("idle"), agent("working"))), null);
  assert.equal(gateOf({ dir: "/x", task: null, labels: { gate: 2 }, agents: [agent("working")] }), null);
  // so it neither ranks first nor counts as waiting in its group
  const list = cards([{ repo: "/r", tasks: [task({ dir: "/a", ...snap("plan-review"), updated: "2026-11-01" })] }],
    [{ address: "t1", dir: "/a", task: "a", info: { status: "working" } }]);
  assert.equal(groups(list, grouping({}))[0].waiting, 0);
});

test("whose turn: a gate, an agent that stopped, one working, none on it, or done", () => {
  assert.equal(turnOf(on(gate(1), agent("idle"))), "gate");
  assert.equal(turnOf(on(gate(1))), "gate");
  assert.equal(turnOf(on(gate(1), agent("working"))), "working"); // still on the phase before it
  assert.equal(turnOf(on({}, agent("idle"))), "turn");
  assert.equal(turnOf(on({}, agent("blocked"))), "turn");
  assert.equal(turnOf(on({}, agent("idle"), agent("working"))), "working");
  assert.equal(turnOf(on({})), "parked");
  assert.equal(turnOf(on({ phase: "complete", isActive: false })), "done");
});

test("finished is this week's completed tasks that aren't cards yet, newest first", () => {
  const done = (dir, updated) => task({ dir, updated, phase: "complete", isActive: false });
  const snaps = [{ repo: "/r", tasks: [done("/a", "2026-11-17"), done("/b", "2026-11-01"), done("/c", "2026-11-12"), task({ dir: "/d" }), done("/e", "2026-11-18")] }];
  const out = finished(snaps, [{ dir: "/e" }], "2026-11-18");
  assert.deepEqual(out.map((c) => c.dir), ["/a", "/c"]);
  assert.equal(out[0].repo, "/r");
  assert.deepEqual(out[0].agents, []);
});

test("since is the latest change among a card's agents' tabs; ago says it roughly", () => {
  const tabs = new Map([["tb1", { changed_at: 1000 }], ["tb2", { changed_at: 5000 }]]);
  assert.equal(since(on({}, agent("idle", "tb1"), agent("idle", "tb2")), tabs), 5000);
  assert.equal(since(on({}, agent("idle", "nope")), tabs), null);
  const min = 60000;
  assert.deepEqual([0, 4 * min, 125 * min, 3 * 1440 * min].map((d) => ago(0, d)), ["<1m", "4m", "2h", "3d"]);
});

test("the next board: gates then your turn, longest wait first; then working, parked, done", () => {
  const c = (dir, over, ...agents) => ({ ...on(over, ...agents), dir });
  const list = [c("/w", {}, agent("working")), c("/g", gate(2), agent("idle")), c("/t1", {}, agent("idle")),
    c("/t2", {}, agent("done")), c("/p", {}), c("/d", { phase: "complete" })];
  const when = (x) => ({ "/t1": 300, "/t2": 100 })[x.dir] ?? null;
  const cols = columns(list, when);
  assert.deepEqual(cols.map((k) => k.sections.map((s) => s.cards.map((x) => x.dir))),
    [[["/g"], ["/t2", "/t1"]], [["/w"]], [["/p"]], [["/d"]]]);
});

test("boardTab finds a board's tab by name in the shown space only", () => {
  const spaces = [
    { active: false, tabs: [{ id: "x", name: "flow · stages" }] },
    { active: true, tabs: [{ id: "a", name: "1" }, { id: "b", name: "flow · next up" }] },
  ];
  assert.equal(boardTab(spaces, "next"), "b");
  assert.equal(boardTab(spaces, "stages"), null);
  assert.equal(boardTab([], "next"), null);
});
