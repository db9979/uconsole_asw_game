import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { t, unit } from "../core/format.js";
import { node } from "./dom.js";

export function renderProposals() {
  const sonar = S.session?.station === "sonar";
  const bridge = S.session?.station === "bridge";
  $("target-proposal-controls").hidden = !sonar;
  $("target-proposal").hidden = !sonar;
  $("navigation-proposal").hidden = !bridge;
  const target = sonar ? S.proposals?.target : null;
  $("proposal-status").textContent = target ? t(`proposal_${target.status}`, {label: target.label}) : "";
  const navigation = bridge ? S.proposals?.navigation : null;
  if (navigation) {
    const summary = t("navigation_summary", {
      course: navigation.course === null ? t("navigation_unchanged") : unit(navigation.course, "\u00b0", 0),
      speed: navigation.speed_kn === null ? t("navigation_unchanged") : unit(navigation.speed_kn, "kn"),
    });
    $("navigation-status").textContent = t(`proposal_${navigation.status}`, {label: summary});
  } else $("navigation-status").textContent = t("navigation_none");
}
// "[08:12] FUNK", as the uConsole's F11 log tags its lines.
export const eventMeta = (event) => `[${event.stamp || "--:--"}] ${event.tag || event.kind}`;
// The mission log, newest first. Rows already shown are kept (and moved),
// so a state push neither rebuilds the list nor loses the reader's place.
export function renderEvents() {
  const list = $("event-list");
  const rows = [...S.eventHistory].reverse();
  const signature = rows.length ? `${rows.length}/${rows[0].seq}/${rows.at(-1).seq}` : "";
  if (list.dataset.signature === signature && list.childElementCount) return;
  list.dataset.signature = signature;
  if (!rows.length) {
    list.replaceChildren(node("li", t("no_events")));
    return;
  }
  const shown = new Map([...list.children].map((item) => [item.dataset.rowKey, item]));
  list.replaceChildren(...rows.map((event) => shown.get(String(event.seq)) ?? eventItem(event)));
}
function eventItem(event) {
  const item = node("li", undefined, event.severity === "warning" ? "warning" : "");
  item.dataset.rowKey = String(event.seq);
  item.dataset.category = event.kind;
  item.append(node("span", eventMeta(event), "event-meta"), node("span", event.message, "event-text"));
  return item;
}
