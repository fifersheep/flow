// The flow board: the panel's cards across a whole Herdr tab. main.js reads
// the tasks and hands them here when a copy was opened as a board
// (props {view: "stages" | "next"}); what goes where is model.js's.
//
//   stages  lanes by repo (or by hand-made group) across Shape | Gate 1 |
//           Build | Gate 2 | Land. A gate is a column of its own, so a task
//           waiting on you stands in it.
//   next    by who has to act: needs you, agent working, parked, done.
//
// Like the panel it shows and it goes to the agent: it never answers a gate.

import { div } from "gpui-kit";
import { v_flex, h_flex, Scrollbar } from "gpui-base";
import { run, spaces } from "herdr";
import {
  BOARDS, HEX, STAGES, ago, boardKey, boardTab, columns, finished, gateOf, groups, phaseOf,
  progressOf, short, since, slugOf, stageOf, toggleGroup, turnOf,
} from "./model.js";

const GATE_W = 220;
const LANE_W = 170;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Shows a board's tab in the shown space, making it if it isn't there. */
export function openBoard(view) {
  const id = boardTab(spaces(), view);
  if (id) run("tab.select", { id });
  else run("tab.new", { name: BOARDS[view], mod: "flow", props: { view } });
}

/** A whole board: header, the board itself, and the open card in a drawer. */
export function board(v, kind, { list, snaps, g, t, waiting, silent, show, regroup, opened }) {
  const today = new Date().toISOString().slice(0, 10);
  const all = [...list, ...finished(snaps, list, today)];
  const index = new Map(all.map((c, i) => [c.dir, i]));
  const open = all.find((c) => c.dir === opened) ?? null;
  const ctx = { v, g, t, index, show, regroup, open };
  const body = !all.length ? empty(v, t) : kind === "stages" ? stages(ctx, all) : next(ctx, all);
  const done = all.filter((c) => turnOf(c) === "done").length;
  const other = kind === "stages" ? "next" : "stages";

  return v_flex().id(`board-${kind}`).size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(13)
    .child(h_flex().h(44).flex_none().px(16).gap(10).items_center().border_b(1).border_color(t.border)
      .child(div().size(10).rounded(3).bg(HEX.current))
      .child(div().text_size(14).font_semibold().child(BOARDS[kind]))
      .child(div().px(6).py(1).rounded(4).border_1().border_color(t.border).text_size(11).text_color(t.muted)
        .child(`${all.length - done} active${done ? ` · ${done} done this week` : ""}`))
      .when(waiting > 0, (e) => e.child(div().px(6).py(1).rounded(4).bg(HEX.you + "55").text_size(11).font_semibold().child(`${waiting} waiting on you`)))
      .child(div().flex_1())
      .when(kind === "stages", (e) => e.child(div().text_size(11).text_color(t.muted).child("lanes by")).child(v.groupBy(g, t)))
      .child(v.button("other-board", `▦ ${BOARDS[other]}`, t, () => openBoard(other))))
    .child(h_flex().flex_1().min_h(0)
      .child(div().flex_1().min_w(0).h_full().relative() // h_flex centres: say the height
        .child(v_flex().id("board-area").absolute().inset_0().overflow_y_scroll().p(16).gap(16)
          .child(body)
          .when(silent.length > 0, (e) => e.child(div().max_w(560).child(v.silent(silent, t)))))
        .child(Scrollbar.vertical("board-area").absolute().inset_0()))
      .when(Boolean(open), (e) => e.child(drawer(ctx, open))));
}

function empty(v, t) {
  return div().p(6).text_size(12).text_color(t.dim).child(v.error ?? (v.loading.size ? "Reading flow tasks…"
    : "No flow tasks here. A task shows up when a Claude Code session in Herdr works on one, or when this space's repo has one."));
}

/** The open card, whole, at the side. Its own head (or ×) closes it. */
function drawer({ v, g, t, index, show }, c) {
  return div().w(400).flex_none().h_full().relative().border_l(1).border_color(t.border)
    .child(v_flex().id("board-drawer").absolute().inset_0().overflow_y_scroll().p(12).gap(8)
      .child(h_flex().items_center()
        .child(div().flex_1().text_size(11).text_color(t.muted).child(c.repo ? c.repo.split("/").filter(Boolean).pop() : "task"))
        .child(div().id("drawer-close").px(6).rounded(4).text_size(14).text_color(t.muted).cursor_pointer()
          .hover((d) => d.bg(t.hover).text_color(t.foreground)).on_click(() => show(null)).child("×")))
      .child(v.card(c, `d${index.get(c.dir)}`, t, g)))
    .child(Scrollbar.vertical("board-drawer").absolute().inset_0());
}

// ---- stages ---------------------------------------------------------------

/** A column's box in a row: the gates fixed and straw, the stages sharing the rest. */
function cell(e, i, t) {
  const gate = STAGES[i].gate;
  e = e.min_w(0).overflow_hidden(); // a long name truncates; it never widens its column
  if (gate) return e.w(GATE_W).flex_none().bg(HEX.you + "14").border_l(1).border_r(1).border_dashed().border_color(HEX.you + "80");
  return e.flex_1().min_w(0).when(i === 2, (d) => d.flex_grow(1.2));
}

function stages(ctx, all) {
  const { g, t } = ctx;
  const head = h_flex().flex_none().bg(t.surface).border_b(1).border_color(t.border)
    .child(div().w(LANE_W).flex_none().px(14).py(10).text_size(11).text_color(t.muted).child(g.by === "manual" ? "group" : "repo"))
    .children(STAGES.map((s, i) => cell(v_flex().px(12).py(9).gap(1), i, t)
      .child(div().text_size(13).font_semibold().child(s.name))
      .child(div().text_size(11).text_color(t.muted).truncate().child(s.sub))));
  return v_flex().flex_none().rounded(12).border_1().border_color(t.border).overflow_hidden()
    .child(head)
    .children(groups(all, g).map((s, k) => lane(ctx, s, k)));
}

/** A lane: its heading (click to fold), then its cards in their stages. */
function lane(ctx, s, k) {
  const { g, t, regroup } = ctx;
  const key = boardKey(s.key), closed = g.closed.includes(key);
  const done = s.cards.filter((c) => turnOf(c) === "done");
  const live = s.cards.filter((c) => turnOf(c) !== "done");
  const by = [0, 1, 2, 3, 4].map((i) => live.filter((c) => stageOf(c) === i));
  const heading = v_flex().id(`lane-${k}`).w(LANE_W).flex_none().px(14).py(12).gap(6)
    .border_r(1).border_color(t.border).cursor_pointer().hover((d) => d.bg(t.hover))
    .on_click(() => regroup((x) => toggleGroup(x, key)))
    .child(h_flex().gap(6).items_center()
      .child(div().w(10).flex_none().text_size(10).text_color(t.dim).child(closed ? "▸" : "▾"))
      .child(div().flex_1().min_w(0).truncate().font_semibold().child(s.name)))
    .child(h_flex().pl(16).gap(6).flex_wrap()
      .child(div().text_size(11).text_color(t.muted).child([live.length ? `${live.length} active` : "", done.length ? `${done.length} done` : ""].filter(Boolean).join(" · ")))
      .when(s.waiting > 0, (e) => e.child(div().px(5).rounded(4).bg(HEX.you + "55").text_size(10).font_semibold().child(`${s.waiting} waiting`))));
  return h_flex().flex_none().items_stretch().min_h(closed ? 48 : 120).border_b(1).border_color(t.border)
    .child(heading)
    .children(by.map((cards, i) => cell(v_flex().p(8).gap(6), i, t)
      .when(!closed, (e) => e.children(cards.map((c) => chip(ctx, c))))
      .when(!closed && i === 4 && done.length > 0, (e) => e.child(doneList(ctx, done, "done this week")))));
}

/** Finished tasks, a line each: there can be many, and none needs anything. */
function doneList({ t, index, show, open }, cards, label) {
  return v_flex().gap(1).pt(4)
    .when(Boolean(label), (e) => e.child(div().px(4).pb(2).text_size(10).font_semibold().text_color(t.muted).child(label.toUpperCase())))
    .children(cards.map((c) => {
      const isOpen = open?.dir === c.dir, deviations = c.task?.deviations.length ?? 0;
      return h_flex().id(`done-${index.get(c.dir)}`).min_w(0).gap(6).items_center().px(4).py(2).rounded(5)
        .cursor_pointer().hover((d) => d.bg(t.hover)).when(isOpen, (d) => d.bg(t.selected))
        .on_click(() => show(isOpen ? null : c.dir))
        .child(div().flex_none().text_size(11).text_color(HEX.done).child("✓"))
        .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.muted).child(slugOf(c)))
        .when(deviations > 0, (e) => e.child(div().flex_none().text_size(10).text_color(HEX.wrong).child(`▲ ${deviations}`)));
    }));
}

/** A card cut down to a chip: the dot, the name, where it is, how far, what's wrong. */
function chip({ t, index, show, open }, c) {
  const i = index.get(c.dir), gate = gateOf(c), turn = turnOf(c), p = progressOf(c), mode = c.task?.mode ?? c.labels?.mode;
  const you = Boolean(gate) || turn === "turn";
  const dot = you ? HEX.you : turn === "done" ? HEX.done : turn === "working" ? HEX.current : t.dim;
  const tag = gate ? "" : turn === "turn" ? "your turn" : `${short(phaseOf(c))}${mode === "lite" ? " · lite" : ""}`;
  const deviations = c.task?.deviations.length ?? 0;
  const isOpen = open?.dir === c.dir;
  return v_flex().id(`chip-${i}`).flex_none().min_w(0).gap(5).px(9).py(7).rounded(8).bg(t.surface).border_1()
    .border_color(isOpen ? t.input : you ? HEX.you : t.border)
    .cursor_pointer().hover((s) => s.bg(t.hover))
    .on_click(() => show(isOpen ? null : c.dir))
    .child(h_flex().min_w(0).gap(6).items_center()
      .child(div().size(7).rounded(4).flex_none().bg(dot)
        .when(turn === "working", (d) => d.loop("opacity", { from: 0.45, to: 1, period: 1400 })))
      .child(div().flex_1().min_w(0).truncate().text_size(12).font_semibold().child(slugOf(c)))
      .when(Boolean(tag), (e) => e.child(div().flex_none().text_size(10).text_color(t.muted).child(tag))))
    .when(Boolean(p), (e) => e.child(h_flex().gap(6).items_center()
      .child(div().flex_1().h(3).rounded(2).bg(t.border)
        .child(div().h_full().rounded(2).bg(HEX.done).w(`${Math.round(100 * Math.min(1, p.done / p.total))}%`)))
      .child(div().flex_none().text_size(10).text_color(t.muted).child(`${p.done}/${p.total}`))))
    .when(deviations > 0, (e) => e.child(div().text_size(10).text_color(HEX.wrong).child(`▲ ${plural(deviations, "deviation")}`)));
}

// ---- next -----------------------------------------------------------------

const COLOR = { you: HEX.you, working: HEX.current, done: HEX.done };
const GROW = { you: 1.3, working: 1.3, parked: 0.9, done: 0.8 };

function next(ctx, all) {
  const { v, g, t, index } = ctx;
  const tabs = new Map(spaces().flatMap((s) => s.tabs ?? []).map((x) => [x.id, x]));
  const when = (c) => since(c, tabs);
  const now = Date.now();
  return h_flex().flex_none().items_start().gap(12).children(columns(all, when).map((col) => {
    const count = col.sections.reduce((n, s) => n + s.cards.length, 0);
    const mine = col.key === "you";
    return v_flex().min_w(0).flex_grow(GROW[col.key]).flex_basis(0).gap(10).p(12).min_h(320).rounded(12).border_1()
      .border_color(mine ? HEX.you + "80" : t.border).when(mine, (e) => e.bg(HEX.you + "12"))
      .child(h_flex().gap(8).items_center()
        .child(div().size(10).rounded(5).flex_none().bg(COLOR[col.key] ?? t.dim))
        .child(div().flex_1().text_size(14).font_semibold().child(col.name))
        .child(div().text_size(11).text_color(t.muted).child(String(count))))
      .child(div().text_size(11).text_color(t.muted).child(col.sub))
      .children(col.sections.filter((s) => s.cards.length).map((s) => v_flex().gap(8)
        .when(Boolean(s.label), (e) => e.child(div().pt(4).text_size(10).font_semibold().text_color(t.muted).child(s.label.toUpperCase())))
        .when(col.key === "done", (e) => e.child(doneList(ctx, s.cards, "")))
        .children(col.key === "done" ? [] : s.cards.map((c) => {
          const at = mine ? when(c) : null;
          return v.card(c, index.get(c.dir), t, g, {
            inline: false, menu: false, you: mine,
            note: at === null ? "" : `waiting ${ago(at, now)}`,
          });
        }))));
  }));
}
