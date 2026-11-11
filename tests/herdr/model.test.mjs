// The flow panel's pure logic (herdr/flow/model.js). Run: node --test tests/herdr/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { cards, events, gateOf, labelled, progressOf, signature, steps, wanted } from "../../herdr/flow/model.js";

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
