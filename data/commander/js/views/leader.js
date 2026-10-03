import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { t } from "../core/format.js";
import { node } from "./dom.js";
import { scenarioText } from "./host.js";
import { sendHostAction } from "../net/host.js";
import { fetchLibrary } from "../net/missions.js";
import { on } from "../core/events.js";

// ---- Server mode: the game leader's lobby controls -----------------------
// The uConsole only serves; the leading browser picks side, mission (scenario,
// daily mission, campaign hotspot or own mission), opponent and start choices
// and starts the countdown. Every choice goes to the host at once as one
// ``host_lobby_set``; the host's lobby view then confirms it. Open selects are
// never rebuilt while they have focus (state pushes would close them).
const OWN = "own:";
const CAMPAIGN = "campaign:";
const DAILY = "daily";
const FIELDS = ["side", "mission", "versus", "weather", "time", "length"];
const LIBRARY_RETRY_MS = 10000;
let libraryAsked = 0;

export const isLeader = () => Boolean(S.session?.host?.leader);

function scenarioTitle(key) { return t(scenarioText[key] ?? "unknown"); }

function missionOptions(view, side) {
  const groups = [[t("leader_group_scenarios"), S.hostView.scenarios.filter((row) => row.side === side)
    .map((row) => [row.key, scenarioTitle(row.key)])]];
  if (view.daily[side] !== null) {
    groups.push([t("leader_group_daily"), [[DAILY, t("lobby_choice_daily", {mission: scenarioTitle(view.daily[side])})]]]);
  }
  const spots = view.campaign[side].hotspots;
  if (spots.length) {
    groups.push([t("leader_group_campaign"), spots.map((spot) => [`${CAMPAIGN}${spot.id}`,
      t("lobby_choice_campaign", {name: spot.name, mission: scenarioTitle(spot.scenario)})])]);
  }
  const own = (S.missionLibrary?.missions ?? []).filter((row) => row.valid && row.side === side);
  if (own.length) groups.push([t("host_new_own_group"), own.map((row) => [OWN + row.key, row.name || row.key])]);
  return groups;
}

function fillMissions(view, side) {
  const select = $("leader-mission");
  const groups = missionOptions(view, side);
  const signature = `${document.documentElement.lang}|${side}|` +
    groups.map(([label, rows]) => `${label}:${rows.map((row) => row.join("=")).join(",")}`).join("|");
  if (select.dataset.options === signature) return;
  select.replaceChildren(...groups.map(([label, rows]) => {
    const group = node("optgroup");
    group.label = label;
    for (const [value, text] of rows) {
      const option = node("option", text);
      option.value = value;
      group.append(option);
    }
    return group;
  }));
  select.dataset.options = signature;
}

function campaignText(campaign, side) {
  const unit = t(`lobby_room_side_${side}`);
  if (campaign.status === "none") return t("leader_campaign_none", {side: unit});
  if (campaign.status !== "active") return t(`leader_campaign_over_${campaign.status}`, {side: unit});
  return t(campaign.port ? "leader_campaign_port" : "leader_campaign_active", {side: unit,
    lage: campaign.lage, mission: campaign.missions, missions: campaign.missions_max});
}

function renderCampaign(view, side, busy) {
  const campaign = view.campaign[side];
  $("leader-campaign-status").textContent = campaignText(campaign, side);
  const port = campaign.status === "active" && campaign.port;
  $("leader-campaign-refit").hidden = !port;
  $("leader-campaign-quick").hidden = !port;
  const armed = $("leader-campaign-new").dataset.armed === "true";
  $("leader-campaign-new").textContent = t(armed ? "leader_campaign_new_confirm" : "leader_campaign_new");
  for (const id of ["leader-campaign-refit", "leader-campaign-quick", "leader-campaign-new"]) $(id).disabled = busy;
}

export function renderLeader(room) {
  const form = $("leader-form");
  const view = S.hostView?.lobby ?? null;
  const show = room !== null && isLeader() && view !== null;
  form.hidden = !show;
  if (!show) return;
  if (!S.missionLibrary && performance.now() - libraryAsked > LIBRARY_RETRY_MS) {
    // The own missions arrive with the library; the list grows once it is read.
    libraryAsked = performance.now();
    fetchLibrary().then(() => renderLeader(S.session?.lobby ?? null)).catch(() => {});
  }
  const counting = view.countdown_s !== null;
  const busy = Boolean(S.hostPending) || counting;
  const focused = FIELDS.some((field) => document.activeElement === $(`leader-${field}`));
  // The side shown decides the list; while the leader edits, keep its choice.
  const side = focused ? $("leader-side").value : view.side;
  fillMissions(view, side);
  if (!focused && !S.hostPending) {
    $("leader-side").value = view.side;
    $("leader-mission").value = view.choice;
    $("leader-versus").value = view.versus;
    $("leader-weather").value = view.weather;
    $("leader-time").value = view.time;
    $("leader-length").value = view.length;
  }
  // The daily mission and an own mission bring their own weather, time and length.
  const choice = $("leader-mission").value;
  const fixed = choice === DAILY || choice.startsWith(OWN);
  for (const field of FIELDS) $(`leader-${field}`).disabled = busy;
  for (const field of ["weather", "time", "length"]) $(`leader-${field}`).disabled = busy || fixed;
  $("leader-fixed-note").hidden = !fixed;
  renderCampaign(view, side, busy);
  $("leader-start").hidden = counting;
  $("leader-start").textContent = t(view.confirm ? "leader_start_anyway" : "leader_start");
  $("leader-start").disabled = Boolean(S.hostPending);
  $("leader-cancel").hidden = !counting;
  $("leader-cancel").disabled = Boolean(S.hostPending);
}

function sendChoices() {
  if (!isLeader() || !S.hostView?.lobby) return;
  sendHostAction("host_lobby_set", {side: $("leader-side").value, choice: $("leader-mission").value,
    versus: $("leader-versus").value, weather: $("leader-weather").value,
    time: $("leader-time").value, length: $("leader-length").value});
}

// A crewmate's row offers the leader to hand over the lead.
export function passLeadButton(player) {
  const button = node("button", t("lobby_pass_lead"));
  button.type = "button";
  button.className = "lobby-pass-lead";
  button.dataset.ordinal = String(player.ordinal);
  button.disabled = Boolean(S.hostPending);
  button.addEventListener("click", () => sendHostAction("host_pass_lead", {ordinal: player.ordinal}));
  return button;
}

export function init() {
  // A mission saved in the planner joins the list at once.
  on("missions-revision", () => {
    if (isLeader() && S.missionLibrary) fetchLibrary().then(() => renderLeader(S.session?.lobby ?? null)).catch(() => {});
  });
  $("leader-side").addEventListener("change", () => {
    // A new side lists its own missions: its first scenario is the choice.
    const view = S.hostView?.lobby;
    if (!view) return;
    fillMissions(view, $("leader-side").value);
    $("leader-mission").selectedIndex = 0;
    sendChoices();
  });
  for (const field of ["mission", "versus", "weather", "time", "length"]) {
    $(`leader-${field}`).addEventListener("change", sendChoices);
  }
  $("leader-form").addEventListener("submit", (event) => {
    event.preventDefault();
    sendHostAction("host_lobby_start", {});
  });
  $("leader-cancel").addEventListener("click", () => sendHostAction("host_lobby_cancel", {}));
  const campaign = (action) => sendHostAction("host_lobby_campaign", {side: $("leader-side").value, action});
  $("leader-campaign-refit").addEventListener("click", () => campaign("refit"));
  $("leader-campaign-quick").addEventListener("click", () => campaign("quick"));
  $("leader-campaign-new").addEventListener("click", () => {
    const button = $("leader-campaign-new");
    const running = S.hostView?.lobby?.campaign?.[$("leader-side").value]?.status === "active";
    // A running campaign is replaced only on a second click.
    if (running && button.dataset.armed !== "true") {
      button.dataset.armed = "true";
      button.textContent = t("leader_campaign_new_confirm");
      return;
    }
    button.dataset.armed = "false";
    campaign("new");
  });
}
