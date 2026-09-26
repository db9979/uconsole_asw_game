"use strict";
const $ = (id) => document.getElementById(id);
let strings = {}, csrf = "", lastRoom = null;
const t = (key) => strings[`commander.web.${key}`] || key;
// crypto.randomUUID exists only in secure contexts (HTTPS or localhost); the
// LAN host is plain HTTP, so fall back to a v4 UUID from getRandomValues.
function requestId() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
async function api(path, body) {
  const options = {credentials:"same-origin", cache:"no-store"};
  if (body !== undefined) {
    options.method="POST";
    options.headers={"Content-Type":"application/json",
      "X-U-Jagd-Request-ID":requestId()};
    if (csrf) options.headers["X-U-Jagd-CSRF"]=csrf;
    options.body=JSON.stringify(body);
  }
  const response=await fetch(path, options);
  let value={};
  try { value=await response.json(); } catch (_) {}
  if (!response.ok) {
    const key=`commander.web.admin_error_${value.error}`;
    throw new Error(strings[key] || t("admin_error_generic"));
  }
  return value;
}
function say(value) { $("message").textContent=value; }
function button(label, handler) {
  const element=document.createElement("button");
  element.type="button"; element.textContent=t(label); element.addEventListener("click", handler);
  return element;
}
async function action(name, client_id="", station="", value=false) {
  try {
    const queued=await api("/api/v2/web/admin", {action:name, client_id, station, value});
    const result=await waitResult(queued.id);
    say(result===true || result?.ok===true?t("admin_applied"):t("admin_failed"));
    await refresh();
  }
  catch (error) { say(error.message); }
}
function render(room) {
  lastRoom=room; csrf=room.csrf; $("room").hidden=false; $("setup").hidden=true; $("login").hidden=true;
  $("room-code").textContent=room.code;
  const clients=$("clients"); clients.replaceChildren();
  for (const client of room.clients) {
    const article=document.createElement("article"); article.className="client";
    const name=document.createElement("strong"); name.textContent=client.name; article.append(name);
    article.append(button("admin_revoke_client",()=>action("revoke_client",client.client_id)));
    const simlog=button(client.simlog?"admin_disable":"admin_enable",
      ()=>action("simlog",client.client_id,"",!client.simlog));
    simlog.textContent=`${t("admin_simlog_grant")}: ${t(client.simlog?"admin_disable":"admin_enable")}`;
    article.append(simlog);
    for (const [station, detail] of Object.entries(client.stations)) {
      if (!detail.requested && !detail.leased) continue;
      const row=document.createElement("div"); row.className="station";
      const label=document.createElement("span"); label.textContent=t(`station_${station}`); row.append(label);
      if (detail.requested || detail.leased) row.append(button("admin_assign",()=>action("assign",client.client_id,station)));
      if (detail.leased) {
        row.append(button("admin_revoke",()=>action("revoke",client.client_id,station)));
        for (const capability of ["command","direct_fire","sonar_audio"]) {
          if (capability==="direct_fire" && !["weapons","opz","helicopter","uboot"].includes(station)) continue;
          if (capability==="sonar_audio" && !["sonar","helicopter","uboot_sonar"].includes(station)) continue;
          const current=detail.grants[capability];
          const control=button(current?"admin_disable":"admin_enable",
            ()=>action(capability,client.client_id,station,!current));
          control.textContent=`${t(`admin_${capability}`)}: ${t(current?"admin_disable":"admin_enable")}`;
          row.append(control);
        }
      }
      article.append(row);
    }
    clients.append(article);
  }
  const proposals=$("proposals"); proposals.replaceChildren();
  for (const [kind, proposal] of Object.entries(room.proposals||{})) {
    if (!proposal || proposal.status!=="pending") continue;
    const row=document.createElement("div"); row.className="station";
    const detail=document.createElement("span");
    detail.textContent=kind==="target"?`${t("admin_target")}: ${proposal.label}`:
      `${t("admin_navigation")}: ${proposal.course??"-"}° / ${proposal.speed_kn??"-"} kn`;
    row.append(detail,button("admin_accept",()=>action(kind==="target"?"accept_target":"accept_navigation")),
      button("admin_reject",()=>action(kind==="target"?"reject_target":"reject_navigation")));
    proposals.append(row);
  }
  if (!proposals.children.length) proposals.textContent=t("admin_no_proposals");
}
async function refresh() {
  try { render(await api("/api/v2/web/room")); }
  catch (_) {
    csrf=""; $("room").hidden=true;
    const status=await api("/api/v2/web/status");
    $("setup").hidden=status.configured; $("login").hidden=!status.configured;
  }
}
async function language(value) {
  strings=await api(`/api/v2/ui?lang=${value}`);
  document.documentElement.lang=value;
  for (const element of document.querySelectorAll("[data-i18n]")) element.textContent=t(element.dataset.i18n);
  for (const element of document.querySelectorAll("[data-i18n-aria]"))
    element.setAttribute("aria-label",t(element.dataset.i18nAria));
  if (lastRoom) render(lastRoom);
  for (const element of document.querySelectorAll(".feed-status[data-status]"))
    element.textContent=t(`admin_live_status_${element.dataset.status}`);
}
function renderLiveStatus(state) {
  for (const [id, key] of [["option-ais-status", "live_ais_status"],
                           ["option-adsb-status", "live_adsb_status"]]) {
    const element=$(id), status=state[key]||"unavailable";
    element.dataset.status=status;
    element.textContent=t(`admin_live_status_${status}`);
  }
}
async function loadLiveStatus() { renderLiveStatus(await api("/api/v2/web/options")); }
async function loadOptions() {
  const state=await api("/api/v2/web/options");
  $("option-language").value=state.language;
  $("option-simlog").checked=state.simlog;
  $("option-voice").checked=state.voice_enabled;
  $("option-ais").checked=state.live_ais_enabled;
  $("option-adsb").checked=state.live_adsb_enabled;
  $("option-ais-key").placeholder=state.aisstream_api_key_set?t("admin_key_saved"):"";
  $("option-opensky-key").placeholder=state.opensky_credentials_set?t("admin_key_saved"):"";
  renderLiveStatus(state);
}
async function waitResult(id) {
  for (let attempt=0; attempt<20; attempt++) {
    await new Promise((resolve)=>setTimeout(resolve,250));
    const room=await api("/api/v2/web/room");
    if (Object.hasOwn(room.results,id)) return room.results[id];
  }
  return {ok:false,error:"pending"};
}
$("options-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const fields=[
    ["language",$("option-language").value],
    ["simlog",$("option-simlog").checked],
    ["voice_enabled",$("option-voice").checked],
    ["live_ais_enabled",$("option-ais").checked],
    ["live_adsb_enabled",$("option-adsb").checked],
  ];
  if ($("option-ais-key").value) fields.push(["aisstream_api_key",$("option-ais-key").value]);
  if ($("option-opensky-key").value) fields.push(["opensky_credentials",$("option-opensky-key").value]);
  try {
    for (const [name,value] of fields) {
      const queued=await api("/api/v2/web/options",{name,value});
      const result=await waitResult(queued.id);
      if (!result.ok) throw new Error(result.error||t("admin_options_failed"));
    }
    $("option-ais-key").value=""; $("option-opensky-key").value="";
    $("options-status").textContent=t("admin_options_saved");
    await loadOptions();
  } catch(error) { $("options-status").textContent=error.message; }
});
for (const [id,name] of [["clear-ais-key","aisstream_api_key"],
                         ["clear-opensky-key","opensky_credentials"]]) {
  $(id).addEventListener("click",async()=>{
    if (!confirm(t("admin_confirm_clear_key"))) return;
    try {
      const queued=await api("/api/v2/web/options",{name,value:""});
      const result=await waitResult(queued.id);
      if (!result.ok) throw new Error(result.error||t("admin_options_failed"));
      await loadOptions(); $("options-status").textContent=t("admin_options_saved");
    } catch(error) { $("options-status").textContent=error.message; }
  });
}
$("language").value=(navigator.language||"").startsWith("de")?"de":"en";
$("language").addEventListener("change",()=>language($("language").value));
$("setup-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  try { await api("/api/v2/web/setup",{code:$("setup-code").value,password:$("setup-password").value}); $("setup-password").value=""; await refresh(); }
  catch(error) { say(error.message); }
});
$("login-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  try { const session=await api("/api/v2/web/login",{password:$("login-password").value}); $("login-password").value=""; csrf=session.csrf; await refresh(); await loadOptions(); }
  catch(error) { say(error.message); }
});
$("rotate-code").addEventListener("click",()=>action("rotate_code"));
Promise.all([language($("language").value), refresh()]).then(()=>{
  if (!$("room").hidden) loadOptions().catch((error)=>say(error.message));
});
setInterval(()=>{if(!$("room").hidden) {
  refresh(); loadLiveStatus().catch(()=>{});
}},3000);
