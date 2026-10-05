import { S } from "../state/store.js";
import { $, affiliations, classes, domains, isSonar } from "../core/base.js";
import { affClass, chartMatches, classificationText, domainClass, enumText, hasPosition, number, selectedTrack, t, unit } from "../core/format.js";
import { sendStationAction } from "../net/commands.js";
import { mapRoles, roleMapViews } from "../state/shared.js";
import { queueDraw } from "./chart.js";
import { renderActionState } from "./controls.js";
import { actionButton, metrics, node } from "./dom.js";
import { queueVisualDraw } from "./role-visuals.js";
import { autoDocks } from "./layout.js";
import { stationActionAvailable } from "../state/availability.js";

// The listening focus the host will hold once this client's own focus command
// lands: the published focus lags a sent command, so comparing against it alone
// drops a quick reselection of the previous track (A, B, A leaves B).
function expectedSonarFocus() {
  const shown = S.v2State.sonar.settings.focus_ref;
  if (S.requestedSonarFocus === shown) S.requestedSonarFocus = null;
  return S.requestedSonarFocus ?? shown;
}
export function flushSonarFocus() {
  if (!S.queuedSonarFocus) return;
  if (!(S.connected && isSonar(S.session?.station) &&
        S.session.grants.command === true && isSonar(S.v2State?.role) && S.v2State.phase === "live" &&
        chartMatches(S.snapshot) && S.snapshot.tracks.some((track) => track.ref === S.queuedSonarFocus))) {
    S.queuedSonarFocus = null;
    return;
  }
  if (expectedSonarFocus() === S.queuedSonarFocus) {
    S.queuedSonarFocus = null;
    return;
  }
  if (!stationActionAvailable()) return;
  const ref = S.queuedSonarFocus;
  S.queuedSonarFocus = null;
  sendStationAction("sonar_set_focus", {ref});
}
export function selectTrack(ref) {
  const changed = S.selected !== ref;
  S.selected = ref;
  const track = selectedTrack();
  const role = S.v2State?.role;
  if (mapRoles.has(role) && hasPosition(track)) {
    Object.assign(roleMapViews[role], {x: track.x, y: track.y, follow: false});
  }
  renderTracks();
  renderDetail(true);
  queueDraw();
  queueVisualDraw();
  if (changed && isSonar(role) && track && expectedSonarFocus() !== ref &&
      S.connected && S.session?.grants.command === true && S.v2State.phase === "live" && chartMatches(S.snapshot))
    S.queuedSonarFocus = ref;
  flushSonarFocus();
}
export function renderTracks() {
  const list = $("track-list");
  const term = $("contact-filter").value.trim().toLocaleLowerCase(S.language).slice(0, 48);
  const visibleTracks = S.snapshot.tracks.filter((track) => !term ||
    (`${track.label} ${track.source} ${track.domain} ${enumText(domains, track.domain)} ` +
     `${track.affiliation} ${enumText(affiliations, track.affiliation)} ${classificationText(track.classification)}`)
      .toLocaleLowerCase(S.language).includes(term));
  const current = new Map([...list.children].filter((element) => element.dataset.ref).map((element) => [element.dataset.ref, element]));
  const expected = new Set(visibleTracks.map((track) => track.ref));
  for (const child of [...list.children]) if (!expected.has(child.dataset.ref)) child.remove();
  visibleTracks.forEach((track, index) => {
    let button = current.get(track.ref);
    if (!button) {
      button = node("button");
      button.type = "button";
      button.dataset.ref = track.ref;
      button.addEventListener("click", () => selectTrack(track.ref));
    }
    button.className = `track ${affClass(track.affiliation)}`;
    button.setAttribute("aria-pressed", String(track.ref === S.selected));
    const symbol = node("span", undefined, `domain-symbol ${domainClass(track.domain)}`);
    symbol.setAttribute("aria-hidden", "true");
    const body = node("span");
    if (track.eloka) {
      // A radar intercept: what was measured, not a domain nobody knows.
      const signal = track.eloka;
      body.append(node("span", track.label, "track-name"),
        node("span", signal.annotation || t(`eloka_modulation_${signal.modulation}`), signal.annotation ? "track-info track-classified" : "track-info"),
        node("span", t("eloka_track_signal", {frequency: number(signal.frequency_hz / 1e9, 3),
          band: signal.frequency_band.toUpperCase().replace("_", "/")}), "track-info"),
        node("span", t("eloka_track_bearing", {bearing: number(track.bearing, 0), age: number(track.age_s, 0),
          state: t(`eloka_signal_state_${signal.signal_state.toLowerCase()}`)}), "track-info"));
    } else {
      body.append(node("span", track.label, "track-name"), node("span", `${enumText(domains, track.domain)} / ${enumText(affiliations, track.affiliation)}`, "track-info"));
      body.append(node("span", `${unit(track.bearing, "\u00b0", 0)} / ${unit(track.range_nm, "NM")} / ${unit(track.age_s, "s", 0)}`, "track-info"));
    }
    const flags = [];
    if (track.ref === S.selected) flags.push(t("selected"));
    if (["sonar", "helicopter"].includes(S.session?.station))
      flags.push(t(track.released_to_opz ? "opz_release_active" : "opz_release_private"));
    if (S.session?.station === "eloka") {
      if (track.eloka?.members.length > 1) flags.push(t("eloka_group_flag", {count: number(track.eloka.members.length, 0)}));
      flags.push(t(track.eloka_annotated ? "opz_release_active" : "opz_release_private"));
    }
    if (S.opzMarked.has(track.ref)) flags.push(t("opz_marked"));
    if (S.opzSuppressed.has(track.ref)) flags.push(t("opz_suppressed"));
    if (flags.length) body.append(node("span", flags.join(" / "), "track-flags"));
    button.replaceChildren(symbol, body);
    // Preserve focused buttons across the two-Hz refresh, including reordering.
    if (list.children[index] !== button) list.insertBefore(button, list.children[index] || null);
  });
  if (!visibleTracks.length) list.replaceChildren(node("p", t(S.snapshot.tracks.length ? "contact_filter_empty" : "no_contacts"), "empty"));
  autoDocks();
  $("track-count").textContent = term ? `${number(visibleTracks.length, 0)} / ${number(S.snapshot.tracks.length, 0)}` : number(S.snapshot.tracks.length, 0);
}
export function renderDetail(resetDraft = false) {
  const track = selectedTrack();
  $("classification-form").hidden = !["sonar", "uboot_sonar", "helicopter", "opz"].includes(S.session?.station);
  $("affiliation-form").hidden = S.session?.station !== "opz";
  $("no-selection").hidden = Boolean(track);
  autoDocks();
  $("track-detail").hidden = !track;
  if (track) {
    let stationActions = document.getElementById("selection-station-actions");
    if (!stationActions) { stationActions = node("div", undefined, "station-row-actions"); stationActions.id = "selection-station-actions"; $("track-detail").append(stationActions); }
    if (isSonar(S.session?.station)) {
      const key = `${track.ref}:${stationActionAvailable()}:${S.language}`;
      if (stationActions.dataset.key !== key) {
        stationActions.replaceChildren(actionButton("sonar_focus", "sonar_set_focus", {ref: track.ref}),
          actionButton("sonar_designate", "sonar_designate_target", {ref: track.ref}));
        stationActions.dataset.key = key;
      }
    } else { stationActions.replaceChildren(); delete stationActions.dataset.key; }
    $("detail-label").textContent = track.label;
    $("detail-badges").replaceChildren(node("span", enumText(domains, track.domain), "badge"), node("span", enumText(affiliations, track.affiliation), `badge ${affClass(track.affiliation)}`), node("span", classificationText(track.classification), "badge"));
    const detailEntries = [
      ["source", track.source], ["quality", number(track.quality, 2)],
      ["bearing", unit(track.bearing, "\u00b0", 0)], ["range", unit(track.range_nm, "NM")],
      ["depth", unit(track.depth_m, "m", 0)], ["course", unit(track.course, "\u00b0", 0)],
      ["speed", unit(track.speed_kn, "kn")],
      ...(track.domain === "AIR" ? [["altitude", unit(track.altitude_m, "m", 0)]] : []),
      ["age", unit(track.age_s, "s", 0)],
      ["fix_age", unit(track.fix_age_s, "s", 0)], ["bearing_uncertainty", unit(track.bearing_uncertainty_deg, "\u00b0")],
      ["range_uncertainty", unit(track.range_uncertainty_nm, "NM")],
    ];
    for (const fix of track.fixes) {
      detailEntries.push([`fix_${fix.source.toLowerCase()}`,
        `${t("measurement_age")} ${unit(fix.measurement_age_s, "s", 0)} / ${t("fix_age")} ${unit(fix.fix_age_s, "s", 0)} / +/-${unit(fix.uncertainty_nm, "NM")}`]);
    }
    metrics($("detail-metrics"), detailEntries);
    if (resetDraft) {
      $("classification").value = Object.hasOwn(classes, track.classification) ? track.classification : "";
      $("affiliation").value = Object.hasOwn(affiliations, track.affiliation) ? track.affiliation : "UNKNOWN";
    }
    if (S.session?.station === "sonar" || S.session?.station === "helicopter") {
      const buoyContact = S.session.station === "helicopter" &&
        S.v2State?.helicopter?.buoy_observations.some((row) => row.ref === track.ref);
      const dipContact = S.session.station === "helicopter" &&
        S.v2State?.helicopter?.dip_observations.some((row) => row.ref === track.ref);
      const heliContact = buoyContact || dipContact;
      const qualified = Boolean(S.v2State?.helicopter?.buoy_observations.find((row) => row.ref === track.ref)?.qualified ||
        S.v2State?.helicopter?.dip_observations.find((row) => row.ref === track.ref)?.qualified);
      $("helicopter-qualify").hidden = !heliContact;
      $("helicopter-qualify").textContent = t(qualified ? "helicopter_unqualify" : "helicopter_qualify");
      $("helicopter-buoy-release").hidden = !buoyContact;
      $("helicopter-buoy-release").textContent = t(track.released_to_opz ? "sonar_withdraw_opz" : "sonar_release_to_opz");
      $("opz-release-status").hidden = false;
      const reportStatus = dipContact
        ? (track.released_to_opz ? "dip_released" : "dip_withdrawn")
        : buoyContact
          ? (track.released_to_opz ? "buoy_released" : "buoy_withdrawn")
          : (track.released_to_opz ? "sonar_released" : "sonar_withdrawn");
      $("opz-release-status").textContent = t(reportStatus);
      $("sonar-release").hidden = S.session.station === "helicopter" && !dipContact;
      $("sonar-release").textContent = t(track.released_to_opz ? "sonar_withdraw_opz" : "sonar_release_to_opz");
    } else if (S.session?.station === "eloka") {
      $("helicopter-qualify").hidden = true;
      $("helicopter-buoy-release").hidden = true;
      $("opz-release-status").hidden = false;
      $("opz-release-status").textContent = t(track.eloka_annotated
        ? "opz_release_annotated" : "opz_release_unannotated");
      $("sonar-release").hidden = true;
    } else { $("opz-release-status").hidden = true; $("sonar-release").hidden = true;
      $("helicopter-qualify").hidden = true; $("helicopter-buoy-release").hidden = true; }
  }
  renderActionState();
}
