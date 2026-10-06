import { S } from "../state/store.js";
import { $, opforRoles } from "../core/base.js";
import { emit } from "../core/events.js";
import { t } from "../core/format.js";
import { node } from "./dom.js";
import { renderDisabledReasons } from "./controls.js";
import { sendHostAction, sendHostActionWhenReady } from "../net/host.js";
import { mutateStation } from "./lobby.js";
import { scenarioText } from "./host.js";

// The main menu's service record and training lessons for the solo host (and
// the logbook for the server-mode leader), as the uConsole shows them: the
// game texts come from the game catalog (``commander.web.game.*``). Both
// dialogs are built when opened, never on a state push.
let logbookSide = "frigate";

const scenarioLabel = (key) => scenarioText[key] ? t(scenarioText[key]) : t("logbook_custom");

function listOrNone(list, items) {
  list.replaceChildren(...(items.length ? items : [node("li", t("game.logbook.none"), "fine")]));
}

export function renderLogbook() {
  const book = S.hostView?.logbook;
  if (!book) return;
  const side = book.sides[logbookSide];
  $("logbook-title").textContent = t(`game.logbook.title.${logbookSide}`);
  for (const button of $("logbook-dialog").querySelectorAll(".logbook-sides button"))
    button.setAttribute("aria-pressed", String(button.dataset.side === logbookSide));
  const won = side.ribbons.filter((row) => row.won).length;
  $("logbook-totals").textContent = t("game.logbook.totals_ribbons", {
    totals: t("game.logbook.totals", {missions: side.missions, wins: side.wins}), won, total: side.ribbons.length});
  $("logbook-ribbons").replaceChildren(...side.ribbons.map((row) => {
    const label = t("game.logbook.ribbon", {scenario: scenarioLabel(row.scenario),
      state: t(row.won ? "game.logbook.ribbon_won" : "game.logbook.ribbon_open")});
    const item = node("li", row.scenario.split("_")[0].replace(/^s/, ""), row.won ? "won" : "open");
    item.title = label;
    item.setAttribute("aria-label", label);
    return item;
  }));
  listOrNone($("logbook-awards"), side.awards.map((row) => {
    const award = t(`game.logbook.award.${row.award}`);
    const item = node("li", row.date === null ? t("game.logbook.award_open", {award})
      : t("game.logbook.award_earned", {award, date: row.date}), row.date === null ? "logbook-open" : "logbook-earned");
    item.title = t(`game.logbook.award_hint.${row.award}`);
    item.append(node("small", t(`game.logbook.award_hint.${row.award}`)));
    return item;
  }));
  listOrNone($("logbook-best"), side.best.map((row) =>
    node("li", t("game.logbook.best_row", {scenario: scenarioLabel(row.scenario), score: row.score}))));
  listOrNone($("logbook-recent"), side.recent.map((row) => {
    const text = t("game.logbook.row", {date: row.date, scenario: scenarioLabel(row.scenario),
      level: t(`game.level.${row.level}`), result: t(row.won ? "game.logbook.won" : "game.logbook.lost"),
      score: row.score, minutes: row.minutes});
    const marked = row.marks.reduce((line, mark) => t("game.logbook.row_mark", {row: line,
      mark: t(`game.logbook.mark.${mark}`)}), text);
    return node("li", marked, row.won ? "logbook-won" : "logbook-lost");
  }));
  $("logbook-learns").textContent = t("game.logbook.learns", {state: t(book.learns ? "yes" : "no")});
  $("logbook-knows").textContent = !book.learns ? "" : side.known.length
    ? t("game.logbook.knows", {habits: side.known.map((habit) => t(`game.habit.${habit}`)).join(", ")})
    : t("game.logbook.knows_none");
}

function openDialog(dialog, focus) {
  renderDisabledReasons();
  dialog.hidden = false;
  if (!dialog.open) dialog.showModal();
  focus?.focus();
}

function openLogbook() {
  if (!S.hostView?.logbook) return;
  logbookSide = opforRoles.has(S.session?.station) ? "boat" : "frigate";
  renderLogbook();
  openDialog($("logbook-dialog"), $(`logbook-side-${logbookSide}`));
}

async function startLesson(lesson) {
  if ($("training-dialog").open) $("training-dialog").close();
  // The side is the solo session's: switch it first, as for an own mission.
  const boat = opforRoles.has(S.session?.station);
  if ((lesson.side === "uboot") !== boat) {
    await mutateStation("/stations/request", {station: boat ? "bridge" : "uboot"});
    if (opforRoles.has(S.session?.station) === boat) return;
    sendHostActionWhenReady("host_start_training", {lesson: lesson.key});
    return;
  }
  sendHostAction("host_start_training", {lesson: lesson.key});
}

function openTraining() {
  if (!S.hostView || S.session?.host?.leader) return;
  $("training-list").replaceChildren(...S.hostView.lessons.map((lesson, index) => {
    const title = t(`game.training.lesson.${lesson.key}`);
    const button = node("button", undefined, `training-lesson${lesson.done ? " training-done" : ""}${lesson.next ? " training-next" : ""}`);
    button.type = "button";
    button.dataset.lesson = lesson.key;
    const name = lesson.side === "uboot" ? t("game.training.boat_title", {title}) : title;
    button.append(node("strong", `${index + 1}. ${lesson.next ? t("game.training.title_next", {title: name})
      : lesson.done ? t("game.training.title_done", {title: name}) : name}`),
      node("small", t(`game.training.lesson_note.${lesson.key}`)));
    button.addEventListener("click", () => startLesson(lesson));
    const item = node("li");
    item.append(button);
    return item;
  }));
  $("training-progress").textContent = t("game.training.progress", {
    done: S.hostView.lessons.filter((lesson) => lesson.done).length, lessons: S.hostView.lessons.length});
  emit("host");
  openDialog($("training-dialog"), $("training-list").querySelector(".training-next:not(:disabled)") ||
    $("training-list").querySelector("button:not(:disabled)"));
}

export function init() {
  for (const id of ["logbook-dialog", "training-dialog"])
    $(id).addEventListener("close", () => { $(id).hidden = true; });
  $("logbook-close").addEventListener("click", () => $("logbook-dialog").close());
  $("training-cancel").addEventListener("click", () => $("training-dialog").close());
  for (const button of $("logbook-dialog").querySelectorAll(".logbook-sides button")) {
    button.addEventListener("click", () => {
      logbookSide = button.dataset.side;
      renderLogbook();
    });
  }
  for (const id of ["host-logbook", "host-screen-logbook"]) $(id).addEventListener("click", openLogbook);
  for (const id of ["host-training", "host-screen-training"]) $(id).addEventListener("click", openTraining);
}
