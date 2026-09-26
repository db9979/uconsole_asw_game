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
export function renderEvents() {
  $("event-list").replaceChildren(...[...S.eventHistory].reverse().map((event) => {
    const item = node("li", undefined, event.severity === "warning" ? "warning" : "");
    item.append(node("span", `${event.seq} / ${event.kind}`, "event-meta"), node("span", event.message));
    return item;
  }));
  if (!S.eventHistory.length) $("event-list").append(node("li", t("no_events")));
}
