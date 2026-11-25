// flow, in Herdr: a panel of flow tasks, and notifications when one needs you.
//
// Installed by `/flow-herdr install` (hooks/flow_herdr.py), which copies this
// folder to ~/.config/herdr-app/mods/flow/ and writes flow.json with the
// plugin's folder, so the panel reads the snapshot flow's own scripts print.
// It shows, and it goes to the agent: it never answers a gate. The gates stay
// in the Claude Code session, where the validator holds them.

import { View, div } from "gpui-kit";
import { v_flex, h_flex, Input, InputState, Popover, TextView, Scrollbar } from "gpui-base";
import { agents, appHome, checking, exec, focused, home, notify, panes, props, readTextFile, run, setShared, shared, spaces, terminals, theme, watchFolder, window as appWindow, writeTextFile } from "herdr";
import { board, openBoard } from "./board.js";
import { HEX, MODES, assign, boardOf, cards, duplicateBoard, folderDoc, movedTo, typedFolder, endable, resumeArgs, startArgs, turnOf, dropGroup, events, gateAsk, gateOf, groupBy, grouping, groups, labelled, phaseOf, progressOf, short, signature, slugOf, steps, toggleGroup, unreporting, wanted } from "./model.js";

const TABS = ["progress", "plan", "decisions", "deviations"];
const ROLE = { done: HEX.done, current: HEX.current, you: HEX.you };
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// Which card is open, and on which tab, is Herdr's shared state, not a copy's:
// every flow panel shows the same, and setShared redraws them all at once.
// Herdr keeps it in shared.json, so it outlasts a restart too.
const VIEW = "flow.view";
function view() {
  const v = shared(VIEW);
  return { open: typeof v?.open === "string" ? v.open : null, tab: TABS.includes(v?.tab) ? v.tab : "progress" };
}
const show = (open, tab = "progress") => setShared(VIEW, { open, tab });

// How the cards are grouped (by repo, or by hand) and the groups made by hand:
// shared the same way, so every copy groups alike. See grouping() in model.js.
const GROUPS = "flow.groups";
const groupState = () => grouping(shared(GROUPS));
const regroup = (change) => setShared(GROUPS, change(groupState()));

// The start bar's repo and mode (board.js), shared the same way, so both
// boards start in the repo and mode last picked.
const START = "flow.start";
function startState() {
  const v = shared(START);
  return { repo: typeof v?.repo === "string" ? v.repo : null, mode: MODES.includes(v?.mode) ? v.mode : "suggest" };
}
const setStart = (change) => setShared(START, { ...startState(), ...change });

// Notifications belong to the module, not to a copy: module code runs once and
// is shared by every copy, so two open panels toast once. A copy that isn't on
// screen isn't drawn, but its timers run, so a timer listens, not render.
let heard = null; // the labels as last read; null until the first reading

function listen() {
  const status = new Map(agents().map((a) => [a.address, a.status]));
  const now = labelled(terminals()).map((a) => ({ ...a, working: status.get(a.address) === "working" }));
  const news = events(heard ?? [], now); // the first reading: what was already so isn't news
  heard = now;
  const f = focused(), w = appWindow();
  for (const e of news) {
    if (w?.active && f?.terminal === e.address) continue; // you're looking at it
    notify({ title: e.title, body: e.body ?? "", level: e.level, action: { name: "agent.focus", args: { terminal: e.address } } });
  }
}

// The folder a board reads, {folder, recent} (model.js folderDoc): set by
// `/flow-herdr board` (flow_herdr.py board_file, the session's folder) or the
// board's folder menu. A board's tab has no terminal, so without it a board
// reads the space's folder.
const BOARD_DIR = () => `${home()}/.cache/flow`;
const BOARD_FILE = () => `${BOARD_DIR()}/herdr-board.json`;

/** Where you are: the focused terminal's folder, else the tab's first, else the space's. */
function here() {
  const f = focused();
  if (f?.cwd) return f.cwd;
  const pane = panes().find((p) => p.tab === f?.tab && p.terminal && p.cwd);
  return pane?.cwd ?? spaces().find((s) => s.active)?.folder ?? null;
}

export default class Flow extends View {
  init(given, cx) {
    this.board = boardOf(given ?? props()); // "stages" or "next" when opened as a board tab
    this.plugin = null; //        the flow plugin's folder, from flow.json
    this.snaps = new Map(); //    repo root -> snapshot
    this.rootOf = new Map(); //   folder asked about -> the repo roots it shows
    this.loading = new Set();
    this.watching = new Set();
    this.sig = null;
    this.error = null;
    this.menu = null; //          the card whose group menu is open (this copy's)
    this.ending = new Set(); //   terminals sent /exit, until flow_herdr.py end returns
    this.confirming = null; //    the terminal whose "End session…" is asking first
    this.folder = null; //        a board's folder (BOARD_FILE), when one was recorded
    this.folderText = null; //    BOARD_FILE as last read, for writeTextFile's check
    this.recent = []; //          the folders it was last set to, newest first
    this.folderMenu = false; //   the header's folder menu, open
    this.folderNote = null; //    why a typed folder wasn't taken
    this.folderInput = InputState.new({ placeholder: "Type a folder: ~/dev, Enter" });
    this.folderInput.on("submit", (_e, cx) => this.typeFolder(cx));
    this.below = new Map(); //    folder -> the repos in or under it (flow_herdr.py repos)
    this.repos = []; //           where a new task can start: the repos this copy reads, and the folder's
    this.repoMenu = false; //     the start bar's repo menu, open
    this.repoFilter = InputState.new({ placeholder: "Filter repos" });
    this.repoFilter.on("change", (_e, cx) => cx.notify());
    this.repoFilter.on("submit", (_e, cx) => this.repoPick?.(cx));
    this.repoPick = null; //      what Enter in the filter picks (board.js)
    this.trayOpen = false; //     the finished-sessions tray, open
    this.startText = InputState.new({ placeholder: "Start a task: describe it, a ticket ID first if it has one" });
    this.startText.on("submit", (_e, cx) => this.startTask(cx));
    this.newGroup = InputState.new({ placeholder: "New group" });
    this.newGroup.on("submit", (_e, cx) => {
      const name = this.newGroup.value().trim(), dir = this.menu;
      this.newGroup.set_value("");
      this.menu = null;
      if (name && dir) regroup((g) => assign(g, dir, name));
      cx.notify();
    });
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
    cx.timer.every(30000, (cx) => {
      for (const dir of [...this.rootOf.keys()]) this.load(dir, cx);
      for (const dir of [...this.below.keys()]) this.loadRepos(dir, cx);
    });
    // a board follows the folder last set, by /flow-herdr board or its menu
    if (this.board) {
      this.readFolder(cx);
      cx.timer.every(2000, (cx) => this.readFolder(cx));
      // a key bound to tab.new makes a board even when there is one: show that one
      if (!checking()) cx.timer.after(300, () => {
        const dup = duplicateBoard(spaces(), this.board);
        if (dup) { run("tab.select", { id: dup.keep }); run("tab.close", { id: dup.close }); }
      });
    }
    // a board says how long each task has waited on you: keep that current
    if (this.board) cx.timer.every(60000, (cx) => cx.notify());
  }

  load(dir, cx) {
    if (!this.plugin || this.loading.has(dir)) return;
    this.loading.add(dir);
    cx.spawn(async (cx) => {
      try {
        // its repo's snapshot, or those of the repos under a folder that isn't one
        const r = await exec("python3", [`${this.plugin}/hooks/flow_herdr.py`, "snapshots", dir], { timeout: 15000 });
        const found = JSON.parse(r.stdout).filter((s) => s?.root);
        this.rootOf.set(dir, found.map((s) => s.root));
        for (const s of found) { this.snaps.set(s.root, s); this.watch(s, cx); }
      } catch { this.rootOf.set(dir, []); }
      finally { this.loading.delete(dir); cx.notify(); }
    });
  }

  /** A board's folder, from BOARD_FILE; redraws only when it moved. */
  readFolder(cx) {
    cx.spawn(async (cx) => {
      let text = null;
      try { text = await readTextFile(BOARD_FILE()); } catch { return; }
      this.folderText = text;
      const doc = folderDoc(text);
      if (doc.folder !== this.folder || doc.recent.join("\n") !== (this.recent ?? []).join("\n")) {
        this.folder = doc.folder;
        this.recent = doc.recent;
        cx.notify();
      }
    });
  }

  /** Moves both boards to a folder: BOARD_FILE, which every board copy reads. */
  setFolder(folder, cx) {
    this.folderMenu = false;
    this.folderNote = null;
    cx.spawn(async (cx) => {
      for (let tries = 0; tries < 2; tries++) {
        try {
          const text = await readTextFile(BOARD_FILE());
          const doc = movedTo(folderDoc(text), folder);
          if (text === null) await exec("mkdir", ["-p", BOARD_DIR()]);
          await writeTextFile(BOARD_FILE(), JSON.stringify(doc) + "\n", text);
          this.folder = doc.folder;
          this.recent = doc.recent;
          break;
        } catch { /* changed under us: read it again */ }
      }
      cx.notify();
    });
    cx.notify();
  }

  /** The folder menu's typed folder: taken when it's a folder, else said why. */
  typeFolder(cx) {
    const folder = typedFolder(this.folderInput.value(), home());
    if (!folder) { this.folderNote = "Type a full path, or one starting with ~"; cx.notify(); return; }
    cx.spawn(async (cx) => {
      let ok = false;
      try { ok = (await exec("test", ["-d", folder])).code === 0; } catch { ok = false; }
      if (ok) { this.folderInput.set_value(""); this.setFolder(folder, cx); }
      else { this.folderNote = `No folder at ${folder}`; cx.notify(); }
    });
  }

  /** The repos a board's start bar offers for a folder: its repo, or every one under it. */
  loadRepos(dir, cx) {
    if (!this.plugin) return;
    if (!this.below.has(dir)) this.below.set(dir, []);
    cx.spawn(async (cx) => {
      try {
        const r = await exec("python3", [`${this.plugin}/hooks/flow_herdr.py`, "repos", dir], { timeout: 15000 });
        const found = JSON.parse(r.stdout).filter((x) => typeof x === "string");
        if (found.join("\n") !== (this.below.get(dir) ?? []).join("\n")) { this.below.set(dir, found); cx.notify(); }
      } catch { /* keep what it had */ }
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
    const all = agents();
    const status = new Map(all.map((a) => [a.address, a]));
    const silent = unreporting(terminals(), all);
    // a board reads the folder it was opened from; the panel, where you are
    const at = (this.board && this.folder) || here();
    const want = wanted(live, at);
    for (const dir of want) if (!this.rootOf.has(dir)) this.load(dir, cx);
    const sig = signature(live);
    if (sig !== this.sig) { // a label moved: those repos changed
      if (this.sig !== null) for (const a of live) this.load(a.dir, cx);
      this.sig = sig;
    }
    // where you are first: a board's start bar defaults to the first repo
    const roots = new Set([...(this.rootOf.get(at) ?? []), ...want.flatMap((d) => this.rootOf.get(d) ?? [])]);
    const list = cards([...roots].map((r) => this.snaps.get(r)), live.map((a) => ({ ...a, info: status.get(a.address) })));
    const waiting = list.filter(gateOf).length;
    const g = groupState();
    const index = new Map(list.map((c, i) => [c.dir, i]));
    if (this.board) {
      const snaps = [...roots].map((r) => this.snaps.get(r));
      if (at && !this.below.has(at)) this.loadRepos(at, cx);
      return board(this, this.board, { list, snaps, below: this.below.get(at) ?? [], at, g, t, waiting, silent, show, regroup, opened: view().open, start: startState(), setStart });
    }

    return v_flex().id("flow").size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(13)
      .child(h_flex().h(36).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().px(5).py(1).rounded(4).border_1().border_color(t.border).text_size(10).text_color(t.muted).child(plural(list.length, "task")))
        .child(div().flex_1())
        .when(waiting > 0, (e) => e.child(div().px(6).py(1).rounded(4).bg(HEX.you + "55").text_size(11).font_semibold().child(`${waiting} waiting on you`)))
        .child(this.groupBy(g, t))
        .child(this.button("open-board", "▦ board", t, () => openBoard("stages"))))
      .child(div().flex_1().min_h(0).relative()
        .child(v_flex().id("flow-list").absolute().inset_0().overflow_y_scroll().p(10).gap(10)
          .children(list.length ? groups(list, g).map((s, k) => this.group(s, k, g, index, t)) : [])
          .when(!list.length, (e) => e.child(div().p(6).text_size(12).text_color(t.dim).child(this.error ?? (
            this.loading.size ? "Reading flow tasks…" : "No flow tasks here. A task shows up when a Claude Code session in Herdr works on one, or when this space's repo has one."))))
          .when(silent.length > 0, (e) => e.child(this.silent(silent, t))))
        .child(Scrollbar.vertical("flow-list").absolute().inset_0()));
  }

  /** The switch between grouping by repo and grouping by hand. */
  groupBy(g, t) {
    return h_flex().flex_none().rounded(5).border_1().border_color(t.border).children(["repo", "manual"].map((by) =>
      div().id(`by-${by}`).px(6).py(1).text_size(10).cursor_pointer().hover((s) => s.bg(t.hover))
        .when(g.by === by, (d) => d.bg(t.selected).text_color(t.foreground))
        .when(g.by !== by, (d) => d.text_color(t.muted))
        .on_click(() => regroup((x) => groupBy(x, by)))
        .child(by)));
  }

  /** A group's heading (click to fold it) and its cards. */
  group(s, k, g, index, t) {
    const head = h_flex().id(`group-${k}`).flex_1().min_w(0).gap(6).items_center().cursor_pointer()
      .on_click(() => regroup((x) => toggleGroup(x, s.key)))
      .child(div().flex_none().w(10).text_size(10).text_color(t.dim).child(s.closed ? "▸" : "▾"))
      .child(div().flex_1().min_w(0).truncate().text_size(11).font_semibold().text_color(t.muted).child(s.name))
      .when(s.waiting > 0, (e) => e.child(div().flex_none().px(5).rounded(4).bg(HEX.you + "55").text_size(10).child(`${s.waiting} waiting`)))
      .child(div().flex_none().text_size(10).text_color(t.dim).child(String(s.cards.length)));
    return v_flex().flex_none().gap(8)
      .child(h_flex().gap(6).items_center().px(2)
        .child(head)
        .when(s.kind === "group", (e) => e.child(div().id(`drop-${k}`).flex_none().px(4).rounded(4).text_size(11).text_color(t.dim)
          .cursor_pointer().hover((d) => d.bg(t.hover).text_color(t.foreground))
          .on_click(() => regroup((x) => dropGroup(x, s.name)))
          .child("×"))))
      .when(!s.closed && !s.cards.length, (e) => e.child(div().px(18).text_size(11).text_color(t.dim)
        .child("No tasks in it. Use a card's group menu to put one here; × removes the group.")))
      .when(!s.closed, (e) => e.children(s.cards.map((c) => this.card(c, index.get(c.dir), t, g))));
  }

  /** A card's group menu, grouping by hand: its groups, none, or a new one. */
  groupMenu(c, i, g, t) {
    const mine = g.member[c.dir] ?? null, open = this.menu === c.dir;
    const pick = (id, label, on, name) => h_flex().id(id).gap(6).px(6).py(3).rounded(4).text_size(12)
      .cursor_pointer().hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => { this.menu = null; regroup((x) => assign(x, c.dir, name)); cx.notify(); })
      .child(div().flex_none().w(10).text_color(HEX.done).child(on ? "✓" : ""))
      .child(div().flex_1().min_w(0).truncate().child(label));
    return Popover.new(`grp-${i}`).anchor("top_right").open(open)
      .on_open_change((o, cx) => { this.menu = o ? c.dir : null; cx.notify(); })
      .trigger(div().id(`grp-btn-${i}`).flex_none().px(5).py(1).rounded(4).border_1().border_color(t.border)
        .text_size(10).text_color(t.muted).cursor_pointer().hover((s) => s.bg(t.hover))
        .child(mine ? "move ▾" : "group ▾"))
      .content(v_flex().w(220).p(4).gap(1).rounded(8).border_1().border_color(t.border).bg(t.background).text_color(t.foreground)
        .children(g.names.map((n, k) => pick(`grp-${i}-${k}`, n, n === mine, n)))
        .when(Boolean(mine), (e) => e.child(pick(`grp-${i}-none`, "no group", false, null)))
        .child(div().p(2).when(g.names.length > 0, (d) => d.mt(2).pt(6).border_t(1).border_color(t.border))
          .child(Input.new(this.newGroup))));
  }

  /** Claude Code sessions that can't label their terminal: no task shows for them, so say why. */
  silent(list, t) {
    const one = list.length === 1;
    return v_flex().flex_none().gap(4).p(12).rounded(10).border_1().border_color(t.border)
      .child(div().text_size(12).text_color(t.muted).child(one
        ? "1 Claude Code session isn't reporting to flow: it started before flow was updated, so its task can't show here. Restart it with claude --continue."
        : `${list.length} Claude Code sessions aren't reporting to flow: they started before flow was updated, so their tasks can't show here. Restart each with claude --continue.`))
      .children(list.map((a, k) => h_flex().id(`silent-${k}`).gap(6).items_center().rounded(5).px(4).mx(-4).py(1)
        .cursor_pointer().hover((d) => d.bg(t.hover)).on_click(() => run("agent.focus", { terminal: a.address }))
        .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.foreground).child(`${a.space_name} / ${a.tab_name}`))
        .child(div().max_w(180).truncate().text_size(11).text_color(t.dim).child(a.title ?? ""))));
  }

  /**
   * A task's card. On a board, `inline: false` opens it in the drawer rather
   * than under itself, `menu: false` leaves out the group menu, `you` borders
   * it straw (its agent is waiting on you) and `note` joins the meta line.
   */
  card(c, i, t, g, { inline = true, menu = true, you = false, note = "" } = {}) {
    const task = c.task, gate = gateOf(c), open = view().open === c.dir, phase = phaseOf(c);
    const done = phase === "complete";
    const working = c.agents.some((a) => a.info?.status === "working");
    const meta = [task?.mode ?? c.labels?.mode, task?.ticketId, note].filter(Boolean).join(" · ");
    return v_flex().id(`card-${i}`).flex_none().p(12).gap(8).rounded(10).border_1()
      .border_color(gate || you ? HEX.you : open ? t.input : t.border).bg(t.surface)
      .child(h_flex().gap(6).items_start()
       .child(v_flex().id(`card-head-${i}`).flex_1().min_w(0).gap(2).cursor_pointer()
        .on_click(() => show(open ? null : c.dir))
        .child(h_flex().gap(8).items_center()
          .child(div().size(8).rounded(4).flex_none().bg(done ? HEX.done : gate ? HEX.you : HEX.current))
          .child(div().flex_1().min_w(0).truncate().font_semibold().child(slugOf(c)))
          .when(Boolean(meta), (e) => e.child(div().flex_none().text_size(11).text_color(t.dim).child(meta)))
          .child(div().flex_none().w(10).text_size(10).text_color(t.dim).child(open ? "▾" : "▸")))
        .when(Boolean(task?.title), (e) => e.child(div().pl(16).truncate().text_size(12).text_color(t.muted).child(task.title))))
       .when(menu && g.by === "manual", (e) => e.child(this.groupMenu(c, i, g, t))))
      .child(this.rail(c, t, working))
      .child(this.where(c, t, phase, done))
      .when(Boolean(task?.nextAction) && !done, (e) => e.child(div().when(!open, (d) => d.truncate()).text_size(12).text_color(t.muted).child(`▸ ${task.nextAction}`)))
      .when(Boolean(gate), (e) => e.child(this.gate(c, i, gate, t)))
      .when((task?.deviations.length ?? 0) > 0, (e) => e.child(div().text_size(11).text_color(HEX.wrong).child(`▲ ${plural(task.deviations.length, "deviation")}`)))
      .child(this.sessions(c, i, t))
      .when(open && inline, (e) => e.child(this.detail(c, i, t)));
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
      .when(n === 1 && Boolean(c.task?.plan), (e) => e.child(this.button(`plan-${i}`, "Plan", t, () => show(c.dir, "plan"))))
      .when(Boolean(agent), (e) => e.child(this.button(`go-${i}`, "Go to agent", t, () => run("agent.focus", { terminal: agent.address }))));
  }

  /** The Claude Code sessions on the task: click one to go there. */
  /**
   * The Claude Code sessions on the task: click one to go there. Each can be
   * ended once it has stopped (model.js endable); a parked task can be resumed.
   */
  sessions(c, i, t) {
    if (!c.agents.length) {
      const resume = turnOf(c) === "parked" && Boolean(resumeArgs(c));
      return h_flex().gap(6).items_center()
        .child(div().flex_1().text_size(11).text_color(t.dim).child("no session on it"))
        .when(resume, (e) => e.child(this.button(`resume-${i}`, "Resume in a new tab", t, () => this.resume(c))));
    }
    return v_flex().gap(2).children(c.agents.map((a, k) => {
      const can = endable(c, a), ending = this.ending.has(a.address), asking = this.confirming === a.address;
      const row = h_flex().id(`agent-${i}-${k}`).gap(6).items_center().rounded(5).px(4).mx(-4).py(1)
        .cursor_pointer().hover((s) => s.bg(t.hover)).on_click(() => run("agent.focus", { terminal: a.address }))
        .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.muted)
          .child(a.info ? `${a.info.space_name} / ${a.info.tab_name}` : a.address))
        .child(div().flex_none().text_size(11).text_color(t.dim).child(ending ? "sent /exit…" : can === "answer" ? "answer it first" : a.info?.status ?? ""))
        .when(!ending && !asking && (can === "end" || can === "confirm"), (e) => e.child(this.button(`end-${i}-${k}`,
          can === "end" ? "End session" : "End session…", t, (cx) => {
            cx.stop_propagation(); // the row behind goes to the agent
            if (can === "end") this.endSession(a.address, cx);
            else { this.confirming = a.address; cx.notify(); }
          })));
      if (!asking) return row;
      return v_flex().gap(6).child(row)
        .child(v_flex().gap(6).p(8).rounded(6).bg(t.hover)
          .child(div().text_size(11).text_color(t.foreground)
            .child(`End this session? ${slugOf(c)} stays at ${short(phaseOf(c))}, and Resume can start a new one on it.`))
          .child(h_flex().gap(6)
            .child(this.button(`end-yes-${i}-${k}`, "End session", t, (cx) => this.endSession(a.address, cx)))
            .child(this.button(`end-no-${i}-${k}`, "Cancel", t, (cx) => { this.confirming = null; cx.notify(); }))));
    }));
  }

  /** Opens a tab running claude with /flow and the start bar's text, in the chosen repo. */
  startTask(cx) {
    const s = startState();
    const repo = this.repos.find((r) => r.root === s.repo) ?? this.repos[0];
    const args = startArgs(repo?.root, this.startText.value(), s.mode);
    if (!args) return;
    run("tab.new", args);
    this.startText.set_value("");
    cx.notify();
  }

  /** A new session on a parked task, in its own checkout, where /flow finds it. */
  resume(c) {
    const args = resumeArgs(c);
    if (args) run("tab.new", args);
  }

  /** Types /exit into the session and closes its pane once claude quits (flow_herdr.py end). */
  endSession(address, cx) {
    if (!this.plugin || this.ending.has(address)) return;
    this.ending.add(address);
    this.confirming = null;
    cx.notify();
    cx.spawn(async (cx) => {
      let doc;
      try {
        const r = await exec("python3", [`${this.plugin}/hooks/flow_herdr.py`, "end", address], { timeout: 45000 });
        doc = JSON.parse(r.stdout);
      } catch (e) { doc = { ok: false, message: String(e?.message ?? e) }; }
      this.ending.delete(address);
      if (!doc.ok) notify({ title: "The session wasn't ended", body: doc.message, level: "warning" });
      cx.notify();
    });
  }

  detail(c, i, t) {
    const task = c.task, tab = view().tab;
    if (!task) return div().text_size(12).text_color(t.dim).child("Reading the task…");
    const count = { progress: task.progress.total ? `${task.progress.done}/${task.progress.total}` : "",
      plan: "", decisions: task.decisions.length || "", deviations: task.deviations.length || "" };
    return v_flex().gap(8).pt(8).border_t(1).border_color(t.border)
      .child(h_flex().gap(4).children(TABS.map((name) => div().id(`tab-${i}-${name}`).px(8).py(3).rounded(5)
        .text_size(11).cursor_pointer().hover((s) => s.bg(t.hover))
        .when(tab === name, (d) => d.bg(t.selected).text_color(t.foreground))
        .when(tab !== name, (d) => d.text_color(t.muted))
        .on_click(() => show(c.dir, name))
        .child(count[name] ? `${name} ${count[name]}` : name))))
      .child(this.tabBody(task, tab, i, t));
  }

  tabBody(task, tab, i, t) {
    const empty = (text) => div().text_size(12).text_color(t.dim).child(text);
    if (tab === "plan") {
      return task.plan ? TextView.markdown(`plan-text-${i}`, task.plan).selectable(true).text_size(12) : empty("No plan yet.");
    }
    if (tab === "progress") {
      if (!task.progress.items.length) return empty("No checklist yet.");
      return v_flex().gap(3).children(task.progress.items.map((it) => h_flex().gap(6).items_start()
        .child(div().flex_none().w(12).text_size(12).text_color(it.done ? HEX.done : t.dim).child(it.done ? "✓" : "○"))
        .child(div().flex_1().min_w(0).text_size(12).text_color(it.done ? t.muted : t.foreground).child(it.text))));
    }
    const items = tab === "decisions" ? task.decisions : task.deviations;
    if (!items.length) return empty(tab === "decisions" ? "No decisions logged." : "No deviations.");
    return v_flex().gap(4).children(items.map((text) => h_flex().gap(6).items_start()
      .child(div().flex_none().w(12).text_size(12).text_color(tab === "deviations" ? HEX.wrong : t.dim).child(tab === "deviations" ? "▲" : "•"))
      .child(div().flex_1().min_w(0).text_size(12).child(text))));
  }

  button(id, label, t, act) {
    return div().id(id).flex_none().px(8).py(3).rounded(5).bg(t.background).border_1().border_color(t.border)
      .text_size(11).cursor_pointer().hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => act(cx))
      .child(label);
  }
}
