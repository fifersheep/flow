// flow, in Herdr: a panel of flow tasks, and notifications when one needs you.
//
// Installed by `/flow-herdr install` (hooks/flow_herdr.py), which copies this
// folder to ~/.config/herdr-app/mods/flow/ and writes flow.json with the
// plugin's folder, so the panel reads the snapshot flow's own scripts print.
// It shows, and it goes to the agent: it never answers a gate. The gates stay
// in the Claude Code session, where the validator holds them.

import { View, div } from "gpui-kit";
import { v_flex, h_flex, TextView, Scrollbar } from "gpui-base";
import { agents, appHome, exec, focused, notify, panes, readTextFile, run, spaces, terminals, theme, watchFolder, window as appWindow } from "herdr";
import { HEX, cards, events, gateAsk, gateOf, labelled, phaseOf, progressOf, short, signature, slugOf, steps, wanted } from "./model.js";

const TABS = ["progress", "plan", "decisions", "deviations"];
const ROLE = { done: HEX.done, current: HEX.current, you: HEX.you };
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// Notifications belong to the module, not to a copy: module code runs once and
// is shared by every copy, so two open panels toast once. A copy that isn't on
// screen isn't drawn, but its timers run, so a timer listens, not render.
let heard = null; // the labels as last read; null until the first reading

function listen() {
  const now = labelled(terminals());
  if (heard === null) { heard = now; return; } // what was already so isn't news
  const news = events(heard, now);
  heard = now;
  const f = focused(), w = appWindow();
  for (const e of news) {
    if (w?.active && f?.terminal === e.address) continue; // you're looking at it
    notify({ title: e.title, body: e.body ?? "", level: e.level, action: { name: "agent.focus", args: { terminal: e.address } } });
  }
}

/** Where you are: the focused terminal's folder, else the tab's first, else the space's. */
function here() {
  const f = focused();
  if (f?.cwd) return f.cwd;
  const pane = panes().find((p) => p.tab === f?.tab && p.terminal && p.cwd);
  return pane?.cwd ?? spaces().find((s) => s.active)?.folder ?? null;
}

export default class Flow extends View {
  init(_props, cx) {
    this.plugin = null; //        the flow plugin's folder, from flow.json
    this.snaps = new Map(); //    repo root -> snapshot
    this.rootOf = new Map(); //   folder asked about -> its repo root (null: none)
    this.loading = new Set();
    this.watching = new Set();
    this.sig = null;
    this.open = null; //          the expanded card's folder
    this.tab = "progress";
    this.error = null;
    cx.spawn(async (cx) => {
      try {
        const cfg = JSON.parse((await readTextFile(`${appHome()}/mods/flow/flow.json`)) ?? "null");
        this.plugin = cfg?.root ?? null;
      } catch { this.plugin = null; }
      if (!this.plugin) this.error = "flow.json is missing. Run /flow-herdr install in Claude Code.";
      cx.notify();
    });
    // reads labels and compares; it draws nothing, so it costs no redraw
    cx.timer.every(1000, () => listen());
    // a task folder appearing changes no label: look again now and then
    cx.timer.every(30000, (cx) => { for (const dir of [...this.rootOf.keys()]) this.load(dir, cx); });
  }

  load(dir, cx) {
    if (!this.plugin || this.loading.has(dir)) return;
    this.loading.add(dir);
    cx.spawn(async (cx) => {
      try {
        const r = await exec("python3", [`${this.plugin}/hooks/flow_status.py`, "--cwd", dir], { timeout: 15000 });
        const s = JSON.parse(r.stdout);
        this.rootOf.set(dir, s.root ?? null);
        if (s.root) { this.snaps.set(s.root, s); this.watch(s, cx); }
      } catch { this.rootOf.set(dir, null); }
      finally { this.loading.delete(dir); cx.notify(); }
    });
  }

  /** Re-read a repo when anything under one of its task folders changes. */
  watch(s, cx) {
    const parents = new Set(s.tasks.map((t) => t.dir.slice(0, t.dir.lastIndexOf("/"))));
    for (const folder of parents) {
      if (this.watching.has(folder)) continue;
      this.watching.add(folder);
      cx.spawn(async (cx) => {
        try { for (;;) { await watchFolder(folder); this.load(s.root, cx); } }
        catch { this.watching.delete(folder); }
      });
    }
  }

  render(cx) {
    listen();
    const t = theme();
    const live = labelled(terminals());
    const status = new Map(agents().map((a) => [a.address, a]));
    const want = wanted(live, here());
    for (const dir of want) if (!this.rootOf.has(dir)) this.load(dir, cx);
    const sig = signature(live);
    if (sig !== this.sig) { // a label moved: those repos changed
      if (this.sig !== null) for (const a of live) this.load(a.dir, cx);
      this.sig = sig;
    }
    const roots = new Set(want.map((d) => this.rootOf.get(d)).filter(Boolean));
    const list = cards([...roots].map((r) => this.snaps.get(r)), live.map((a) => ({ ...a, info: status.get(a.address) })));
    const waiting = list.filter(gateOf).length;

    return v_flex().id("flow").size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(13)
      .child(h_flex().h(36).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().px(5).py(1).rounded(4).border_1().border_color(t.border).text_size(10).text_color(t.muted).child(plural(list.length, "task")))
        .child(div().flex_1())
        .when(waiting > 0, (e) => e.child(div().px(6).py(1).rounded(4).bg(HEX.you + "55").text_size(11).font_semibold().child(`${waiting} waiting on you`))))
      .child(div().flex_1().min_h(0).relative()
        .child(v_flex().id("flow-list").absolute().inset_0().overflow_y_scroll().p(10).gap(10)
          .children(list.map((c, i) => this.card(c, i, t)))
          .when(!list.length, (e) => e.child(div().p(6).text_size(12).text_color(t.dim).child(this.error ?? (
            this.loading.size ? "Reading flow tasks…" : "No flow tasks here. A task shows up when a Claude Code session in Herdr works on one, or when this space's repo has one.")))))
        .child(Scrollbar.vertical("flow-list").absolute().inset_0()));
  }

  card(c, i, t) {
    const task = c.task, gate = gateOf(c), open = this.open === c.dir, phase = phaseOf(c);
    const done = phase === "complete";
    const working = c.agents.some((a) => a.info?.status === "working");
    const meta = [task?.mode ?? c.labels?.mode, task?.ticketId].filter(Boolean).join(" · ");
    return v_flex().id(`card-${i}`).flex_none().p(12).gap(8).rounded(10).border_1()
      .border_color(gate ? HEX.you : open ? t.input : t.border).bg(t.surface)
      .child(v_flex().id(`card-head-${i}`).gap(2).cursor_pointer()
        .on_click((_e, cx) => { this.open = open ? null : c.dir; this.tab = "progress"; cx.notify(); })
        .child(h_flex().gap(8).items_center()
          .child(div().size(8).rounded(4).flex_none().bg(done ? HEX.done : gate ? HEX.you : HEX.current))
          .child(div().flex_1().min_w(0).truncate().font_semibold().child(slugOf(c)))
          .when(Boolean(meta), (e) => e.child(div().flex_none().text_size(11).text_color(t.dim).child(meta)))
          .child(div().flex_none().w(10).text_size(10).text_color(t.dim).child(open ? "▾" : "▸")))
        .when(Boolean(task?.title), (e) => e.child(div().pl(16).truncate().text_size(12).text_color(t.muted).child(task.title))))
      .child(this.rail(c, t, working))
      .child(this.where(c, t, phase, done))
      .when(Boolean(task?.nextAction) && !done, (e) => e.child(div().when(!open, (d) => d.truncate()).text_size(12).text_color(t.muted).child(`▸ ${task.nextAction}`)))
      .when(Boolean(gate), (e) => e.child(this.gate(c, i, gate, t)))
      .when((task?.deviations.length ?? 0) > 0, (e) => e.child(div().text_size(11).text_color(HEX.wrong).child(`▲ ${plural(task.deviations.length, "deviation")}`)))
      .child(this.sessions(c, i, t))
      .when(open, (e) => e.child(this.detail(c, i, t)));
  }

  /** The chain: a bar per phase, a square per gate; the current phase breathes while its agent works. */
  rail(c, t, working) {
    if (!c.task) return div().h(6).rounded(3).bg(t.border);
    return h_flex().h(8).gap(3).items_center().children(steps(c.task).map((s) => s.kind === "gate"
      ? div().flex_none().size(8).rounded(2).bg(ROLE[s.role] ?? t.border)
      : div().flex_1().h(6).rounded(3).bg(ROLE[s.role] ?? t.border)
        .when(working && s.role === "current", (d) => d.loop("opacity", { from: 0.45, to: 1, period: 1400 }))));
  }

  /** The phase it's in, and how far through the checklist. */
  where(c, t, phase, done) {
    const p = progressOf(c);
    return h_flex().gap(8).items_center()
      .child(div().flex_1().text_size(12).text_color(done ? t.muted : HEX.current).child(short(phase)))
      .when(Boolean(p), (e) => e
        .child(div().flex_none().w(56).h(4).rounded(2).bg(t.border)
          .child(div().h_full().rounded(2).bg(HEX.done).w(Math.round(56 * Math.min(1, p.done / p.total)))))
        .child(div().flex_none().text_size(11).text_color(t.muted).child(`${p.done}/${p.total}`)));
  }

  gate(c, i, n, t) {
    const agent = c.agents[0];
    return h_flex().gap(6).items_center().px(10).py(7).rounded(7).bg(HEX.you + "40")
      .child(div().flex_1().min_w(0).text_size(12).font_semibold().child(gateAsk(n)))
      .when(n === 1 && Boolean(c.task?.plan), (e) => e.child(this.button(`plan-${i}`, "Plan", t, (cx) => { this.open = c.dir; this.tab = "plan"; cx.notify(); })))
      .when(Boolean(agent), (e) => e.child(this.button(`go-${i}`, "Go to agent", t, () => run("agent.focus", { terminal: agent.address }))));
  }

  /** The Claude Code sessions on the task: click one to go there. */
  sessions(c, i, t) {
    if (!c.agents.length) return div().text_size(11).text_color(t.dim).child("no session on it");
    return v_flex().gap(2).children(c.agents.map((a, k) => h_flex().id(`agent-${i}-${k}`).gap(6).items_center().rounded(5).px(4).mx(-4).py(1)
      .cursor_pointer().hover((s) => s.bg(t.hover)).on_click(() => run("agent.focus", { terminal: a.address }))
      .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.muted)
        .child(a.info ? `${a.info.space_name} / ${a.info.tab_name}` : a.address))
      .child(div().flex_none().text_size(11).text_color(t.dim).child(a.info?.status ?? ""))));
  }

  detail(c, i, t) {
    const task = c.task;
    if (!task) return div().text_size(12).text_color(t.dim).child("Reading the task…");
    const count = { progress: task.progress.total ? `${task.progress.done}/${task.progress.total}` : "",
      plan: "", decisions: task.decisions.length || "", deviations: task.deviations.length || "" };
    return v_flex().gap(8).pt(8).border_t(1).border_color(t.border)
      .child(h_flex().gap(4).children(TABS.map((name) => div().id(`tab-${i}-${name}`).px(8).py(3).rounded(5)
        .text_size(11).cursor_pointer().hover((s) => s.bg(t.hover))
        .when(this.tab === name, (d) => d.bg(t.selected).text_color(t.foreground))
        .when(this.tab !== name, (d) => d.text_color(t.muted))
        .on_click((_e, cx) => { this.tab = name; cx.notify(); })
        .child(count[name] ? `${name} ${count[name]}` : name))))
      .child(this.tabBody(task, i, t));
  }

  tabBody(task, i, t) {
    const empty = (text) => div().text_size(12).text_color(t.dim).child(text);
    if (this.tab === "plan") {
      return task.plan ? TextView.markdown(`plan-text-${i}`, task.plan).selectable(true).text_size(12) : empty("No plan yet.");
    }
    if (this.tab === "progress") {
      if (!task.progress.items.length) return empty("No checklist yet.");
      return v_flex().gap(3).children(task.progress.items.map((it) => h_flex().gap(6).items_start()
        .child(div().flex_none().w(12).text_size(12).text_color(it.done ? HEX.done : t.dim).child(it.done ? "✓" : "○"))
        .child(div().flex_1().min_w(0).text_size(12).text_color(it.done ? t.muted : t.foreground).child(it.text))));
    }
    const items = this.tab === "decisions" ? task.decisions : task.deviations;
    if (!items.length) return empty(this.tab === "decisions" ? "No decisions logged." : "No deviations.");
    return v_flex().gap(4).children(items.map((text) => h_flex().gap(6).items_start()
      .child(div().flex_none().w(12).text_size(12).text_color(this.tab === "deviations" ? HEX.wrong : t.dim).child(this.tab === "deviations" ? "▲" : "•"))
      .child(div().flex_1().min_w(0).text_size(12).child(text))));
  }

  button(id, label, t, act) {
    return div().id(id).flex_none().px(8).py(3).rounded(5).bg(t.background).border_1().border_color(t.border)
      .text_size(11).cursor_pointer().hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => act(cx))
      .child(label);
  }
}
