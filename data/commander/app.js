"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const prefix = "commander.web.";
  const domains = { UNKNOWN: "domain_unknown", SURFACE: "domain_surface", SUBSURFACE: "domain_subsurface", AIR: "domain_air" };
  const affiliations = { UNKNOWN: "aff_unknown", FRIEND: "aff_friend", NEUTRAL: "aff_neutral", HOSTILE: "aff_hostile" };
  const classes = { U_BOOT: "class_submarine", KAMPFSCHIFF: "class_warship", BIOLOGISCH: "class_biological", FAHRZEUG: "class_vehicle" };
  const phases = { live: "phase_live", paused: "phase_paused", menu: "phase_menu", blocked: "phase_blocked", ended: "phase_ended" };
  const damageStates = { OK: "damage_ok", FLUTEND: "damage_flooding", BESCHAEDIGT: "damage_damaged", ZERSTOERT: "damage_destroyed" };
  const heloStates = { HANGAR: "helo_stowed", AUF: "helo_airborne", ZURUECK: "helo_returning", VERLOREN: "helo_lost" };
  const stationNames = ["bridge", "sonar", "weapons", "damage", "opz", "radio", "engine", "helicopter", "eloka"];
  const reasons = {
    invalid_schema: "reason_invalid_schema", unauthorized: "reason_unauthorized",
    stale_session: "reason_stale_session", stale_epoch: "reason_stale_epoch",
    commands_blocked: "reason_commands_blocked", duplicate_id: "reason_duplicate_id",
    revision_conflict: "reason_revision_conflict", unknown_track: "reason_unknown_track",
    ineligible_track: "reason_ineligible_track", proposal_pending: "reason_proposal_pending",
    stale_generation: "reason_stale_generation", grant_revoked: "reason_grant_revoked",
    role_revoked: "reason_role_revoked", phase_blocked: "reason_phase_blocked",
    stale_world_session: "reason_stale_world_session", stale_world_epoch: "reason_stale_world_epoch",
    bridge_down: "reason_bridge_down", invalid_value: "reason_invalid_value",
    sonar_down: "reason_sonar_down", opz_down: "reason_opz_down",
    engine_down: "reason_engine_down", radio_down: "reason_radio_down",
    flightdeck_down: "reason_flightdeck_down", not_ready: "reason_not_ready",
    no_solution: "reason_no_solution", no_buoys: "reason_no_buoys",
    water_required: "reason_water_required", tas_fault: "reason_tas_fault",
    unknown_ref: "reason_unknown_ref", stale_ref: "reason_stale_ref",
    source_owned: "reason_source_owned", fusion_rejected: "reason_fusion_rejected",
    action_rejected: "reason_action_rejected", expired: "reason_expired",
    context_invalidated: "reason_context_invalidated",
    direct_fire_unavailable: "reason_direct_fire_unavailable",
    ok: "reason_ok",
  };
  const colors = { UNKNOWN: "#f3cf79", FRIEND: "#81c5ff", NEUTRAL: "#8fdfab", HOSTILE: "#ff9090" };
  let language = (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
  let catalog = {};
  // Legacy credentials and v2 session metadata stay closure-local: no URL, DOM or persistence.
  let protocolMode = "detecting";
  let token = null;
  let session = null;
  let generation = 0;
  let snapshot = null;
  let chart = null;
  let chartSession = null;
  let chartEpoch = null;
  let chartRole = null;
  let selected = null;
  let connected = false;
  let linkState = "unpaired";
  let lastSuccess = 0;
  let lastSessionFetch = 0;
  let failures = 0;
  let pollTimer = null;
  let polling = false;
  let pending = null;
  let v2State = null;
  let stationRenderSignature = null;
  let nextCommandSeq = 0;
  let stationMutation = false;
  let stationPickerOpen = false;
  let lobbyMessage = null;
  let commandMessage = null;
  let opzMarked = new Set();
  let opzSuppressed = new Set();
  let opzManage = false;
  let stationDrafts = new Set();
  let requestQueue = Promise.resolve();
  let activeRequest = null;
  let languageRequest = 0;
  let audio = null;
  let soundEnabled = false;
  let sonarAudioEnabled = false;
  let sonarAudioController = null;
  let sonarAudioTimer = null;
  let sonarAudioSequence = null;
  let sonarAudioNextTime = 0;
  let sonarAudioSources = [];
  let sonarAudioGain = null;
  let seenEvents = new Set();
  let eventHighWater = -1;
  let eventHistory = [];
  let suppressNextEvents = true;
  const view = { x: 0, y: 0, zoom: 1, follow: false, initialized: false };
  const canvas = $("chart");
  const ctx = canvas.getContext("2d");
  let drawQueued = false;
  let chartHits = [];
  let drag = null;
  const lookoutCanvas = $("lookout");
  const lookoutCtx = lookoutCanvas.getContext("2d");
  const lookoutRanges = [5, 10, 25, 50, 100, 200];
  const lookoutView = { rangeNm: 100 };
  let lookoutDrawQueued = false;
  const maxCanvasPixels = 8000000;
  const tabNames = ["operations", "lookout", "guide", "contacts"];
  let activeTab = "operations";
  let contactAnalysis = null;
  let analysisSelected = null;
  let analysisImageKey = null;
  let lastSimlogFetch = 0;
  let analysisError = false;
  const simlogMapCanvas = $("simlog-map");
  const simlogMapCtx = simlogMapCanvas.getContext("2d");
  let latestSimlogState = null;
  let simlogMapData = null;
  let simlogMapSeq = null;
  let simlogMapLatest = false;
  let simlogMapFit = "world";
  let simlogMapDrawQueued = false;
  const visualCanvasIds = ["role-map", "sonar-broadband", "sonar-lofar", "sonar-spectrum", "sonar-demon",
    "sonar-tma-plot", "sonar-environment", "sonar-active", "damage-schematic",
    "engine-instruments", "eloka-scope", "weapons-system"];
  const mapRoles = new Set(["bridge", "weapons", "opz", "radio", "helicopter"]);
  const roleMapViews = Object.fromEntries([...mapRoles].map((role) => [role, {x: 250, y: 250, zoom: 1}]));
  const maxRoleMapHits = 512;
  let roleMapHits = [];
  let damageHits = [];
  let sonarVisualPage = "broadband";
  let visualDrawQueued = false;
  let roleMapDrag = null;
  let opzSweepFrame = null;
  let opzSweepSample = null;
  let fireConfirmation = null;
  let fireConfirmationTimer = null;
  let sonarAudioGeneration = 0;

  const t = (key, values = {}) => (catalog[prefix + key] || "").replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_, name) => String(values[name] ?? ""));
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const hasPosition = (entity) => finite(entity?.x) && finite(entity?.y);
  const number = (value, digits = 1) => finite(value) ? value.toLocaleString(language, { minimumFractionDigits: digits, maximumFractionDigits: digits }) : t("unavailable");
  const unit = (value, symbol, digits = 1) => finite(value) ? `${number(value, digits)} ${symbol}` : t("unavailable");
  const enumText = (map, value) => t(map[value] || "unknown");
  const classificationText = (value) => Object.hasOwn(classes, value) ? enumText(classes, value) :
    typeof value === "string" && value ? value : t("unknown");
  const affClass = (value) => `aff-${Object.hasOwn(affiliations, value) ? value.toLowerCase() : "unknown"}`;
  const domainClass = (value) => `domain-${Object.hasOwn(domains, value) ? value.toLowerCase() : "unknown"}`;
  const selectedTrack = () => snapshot?.tracks.find((track) => track.ref === selected);
  const sameContext = (a, b) => a && b && a.session === b.session && a.epoch === b.epoch;
  const chartMatches = (state) => chart && chartSession === state.session && chartEpoch === state.epoch &&
    chartRole === state.role && chart.revision === state.chart_revision;
  const authenticated = () => protocolMode === "v2" ? session !== null : protocolMode === "v1" && token !== null;
  const canCommand = () => connected && (protocolMode === "v1" || session?.grants.command === true) &&
    snapshot?.commands_allowed === true && chartMatches(snapshot) && !pending;
  const navigationLive = () => snapshot?.phase === "live" && hasPosition(snapshot?.ownship);

  const sonarAudioAuthorized = () => protocolMode === "v2" && connected && !document.hidden && navigator.onLine !== false &&
    session?.station === "sonar" && session.grants.sonar_audio === true && v2State?.role === "sonar" &&
    v2State.phase === "live" && v2State.clock?.time_scale === 1 && v2State.sonar?.settings?.station_down === false;
  const sonarAudioStartLead = .3;
  const sonarAudioTargetAhead = .65;
  const sonarAudioMaxSources = 3;
  const sonarGainValue = () => {
    const value = Number($("volume").value) / 200;
    return finite(value) ? Math.max(0, Math.min(.5, value)) : 0;
  };

  function renderSonarAudio(key) {
    const button = $("sonar-live-toggle");
    button.textContent = t(sonarAudioEnabled ? "sonar_live_stop" : "sonar_live_start");
    button.setAttribute("aria-pressed", String(sonarAudioEnabled));
    button.disabled = !sonarAudioEnabled && !(session?.station === "sonar" && session?.grants.sonar_audio === true);
    $("sonar-live-status").textContent = t(key || (sonarAudioEnabled ? "sonar_live_waiting" : "sonar_live_off"));
  }

  function stopSonarAudio(key = "sonar_live_off") {
    sonarAudioGeneration += 1;
    sonarAudioEnabled = false;
    clearTimeout(sonarAudioTimer);
    sonarAudioTimer = null;
    sonarAudioController?.abort();
    sonarAudioController = null;
    for (const source of sonarAudioSources) { try { source.stop(); } catch (_) {} source.disconnect(); }
    sonarAudioSources = [];
    sonarAudioSequence = null;
    sonarAudioNextTime = 0;
    sonarAudioGain?.disconnect();
    sonarAudioGain = null;
    renderSonarAudio(key);
  }

  function scheduleSonarAudioPoll(delay = 0) {
    clearTimeout(sonarAudioTimer);
    if (sonarAudioEnabled) sonarAudioTimer = setTimeout(pollSonarAudio, delay);
  }

  function flushSonarAudioQueue() {
    for (const source of sonarAudioSources) { try { source.stop(); } catch (_) {} source.disconnect(); }
    sonarAudioSources = [];
    sonarAudioNextTime = audio?.currentTime || 0;
  }

  async function pollSonarAudio() {
    if (!sonarAudioEnabled || sonarAudioController) return;
    if (!sonarAudioAuthorized()) { stopSonarAudio("sonar_live_unavailable"); return; }
    sonarAudioSources = sonarAudioSources.filter((source) => !source.__ended);
    const queuedAhead = Math.max(0, sonarAudioNextTime - audio.currentTime);
    if (sonarAudioSources.length >= sonarAudioMaxSources || queuedAhead >= sonarAudioTargetAhead) {
      scheduleSonarAudioPoll(Math.max(20, Math.min(80,
        (queuedAhead - sonarAudioTargetAhead) * 1000)));
      return;
    }
    const context = generation;
    const streamGeneration = sonarAudioGeneration;
    const expectedSession = {client_id: session.client_id, csrf: session.csrf,
      station_generation: session.station_generation, active_generation: session.active_generation,
      world: v2State.session, epoch: v2State.epoch};
    const currentStream = () => context === generation && streamGeneration === sonarAudioGeneration &&
      sonarAudioEnabled && session?.client_id === expectedSession.client_id &&
      session?.station_generation === expectedSession.station_generation &&
      session?.active_generation === expectedSession.active_generation &&
      v2State?.session === expectedSession.world && v2State?.epoch === expectedSession.epoch;
    const controller = new AbortController();
    sonarAudioController = controller;
    const timeout = setTimeout(() => controller.abort(), 2000);
    let response;
    try {
      response = await fetch("/api/v2/sonar/audio", {
        method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", mode: "same-origin",
        signal: controller.signal,
        headers: {Accept: "audio/pcm", "Content-Type": "application/json", "X-U-Jagd-CSRF": expectedSession.csrf},
        body: JSON.stringify({protocol: 2, after: sonarAudioSequence, world_session: expectedSession.world,
          world_epoch: expectedSession.epoch, station_generation: expectedSession.station_generation,
          active_generation: expectedSession.active_generation}),
      });
      if (!currentStream()) return;
      if (response.status === 204) {
        if (response.headers.get("content-length") !== "0") throw new Error("audio_protocol");
        renderSonarAudio("sonar_live_waiting");
        scheduleSonarAudioPoll(60);
        return;
      }
      if ([401, 403, 409, 503].includes(response.status)) { stopSonarAudio("sonar_live_unavailable"); return; }
      if (response.status >= 500 || response.status === 429) {
        renderSonarAudio("sonar_live_waiting");
        return;
      }
      const sequence = Number(response.headers.get("x-u-jagd-audio-sequence"));
      const discontinuity = response.headers.get("x-u-jagd-audio-discontinuity");
      if (response.status !== 200 || response.headers.get("content-type") !== "audio/pcm" ||
          response.headers.get("x-u-jagd-pcm") !== "s16le" || response.headers.get("x-u-jagd-sample-rate") !== "4096" ||
          response.headers.get("x-u-jagd-audio-frames") !== "1024" || response.headers.get("content-length") !== "2048" ||
          !Number.isSafeInteger(sequence) || sequence < 1 || !["0", "1"].includes(discontinuity)) throw new Error("audio_protocol");
      const bytes = await response.arrayBuffer();
      if (!currentStream()) return;
      if (bytes.byteLength !== 2048) throw new Error("audio_protocol");
      const gap = discontinuity === "1" || sonarAudioSequence !== null && sequence !== sonarAudioSequence + 1;
      if (gap) flushSonarAudioQueue();
      sonarAudioSequence = sequence;
      const view = new DataView(bytes);
      const outputFrames = Math.max(1, Math.round(1024 * audio.sampleRate / 4096));
      const buffer = audio.createBuffer(1, outputFrames, audio.sampleRate);
      const channel = buffer.getChannelData(0);
      for (let index = 0; index < outputFrames; index++) {
        const position = index * 4096 / audio.sampleRate;
        const left = Math.min(1023, Math.floor(position));
        const right = Math.min(1023, left + 1);
        const fraction = position - left;
        channel[index] = (view.getInt16(left * 2, true) * (1 - fraction) + view.getInt16(right * 2, true) * fraction) / 32768;
      }
      sonarAudioSources = sonarAudioSources.filter((source) => !source.__ended);
      if (sonarAudioSources.length >= sonarAudioMaxSources) throw new Error("audio_protocol");
      sonarAudioGain.gain.value = sonarGainValue();
      const start = sonarAudioNextTime > audio.currentTime + .03
        ? sonarAudioNextTime : audio.currentTime + sonarAudioStartLead;
      if (start > audio.currentTime + 1.0) throw new Error("audio_protocol");
      const source = audio.createBufferSource();
      source.buffer = buffer;
      source.connect(sonarAudioGain);
      source.__ended = false;
      source.onended = () => {
        source.__ended = true;
        source.disconnect();
        scheduleSonarAudioPoll(0);
      };
      source.start(start);
      sonarAudioNextTime = start + buffer.duration;
      sonarAudioSources.push(source);
      renderSonarAudio("sonar_live_playing");
      scheduleSonarAudioPoll(0);
    } catch (error) {
      if (currentStream()) {
        if (error.message === "audio_protocol") stopSonarAudio("sonar_live_failed");
        else renderSonarAudio("sonar_live_waiting");
      }
    } finally {
      clearTimeout(timeout);
      if (sonarAudioController === controller) sonarAudioController = null;
      // Every nonterminal exit must keep the stream alive, including timeouts
      // and session metadata refreshes concurrent with this request.
      if (currentStream()) scheduleSonarAudioPoll(response?.status === 200 ? 20 : 100);
    }
  }

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = String(text ?? "");
    if (className) element.className = className;
    return element;
  }

  function metrics(element, entries) {
    entries.forEach(([key, value], index) => {
      let group = element.children[index];
      if (!group) { group = node("div"); group.append(node("dt"), node("dd")); element.append(group); }
      const label = t(key), text = String(value ?? "");
      if (group.firstChild.textContent !== label) group.firstChild.textContent = label;
      if (group.lastChild.textContent !== text) group.lastChild.textContent = text;
    });
    while (element.children.length > entries.length) element.lastChild.remove();
  }

  const yesNo = (value) => typeof value === "boolean" ? t(value ? "yes" : "no") : t("unavailable");
  const position = (value) => `${unit(value?.x, "NM")} / ${unit(value?.y, "NM")}`;
  const rawFields = (value) => Object.entries(value || {}).map(([key, item]) =>
    `${key}: ${Array.isArray(item) ? item.join(", ") : String(item ?? t("unavailable"))}`).join(" / ");

  function actionButton(labelKey, action, params, ready = true, values = {}) {
    const button = node("button", t(labelKey, values), "station-action");
    button.type = "button";
    button.dataset.stationAction = action;
    button.dataset.ready = String(ready);
    button.disabled = !stationActionAvailable() || !ready;
    button.addEventListener("click", () => sendStationAction(action, params));
    return button;
  }

  function clearFireConfirmation() {
    fireConfirmation = null;
    clearTimeout(fireConfirmationTimer);
    fireConfirmationTimer = null;
  }

  function clearFireDrafts() {
    clearFireConfirmation();
    for (const id of ["weapons-fire-target", "weapons-fire-depth", "helicopter-fire-target",
      "helicopter-fire-depth", "opz-fire-target"]) {
      stationDrafts.delete(id);
      $(id).value = "";
    }
  }

  function fillFireTargets(id, rows) {
    const select = $(id);
    const previous = stationDrafts.has(id) ? select.value : "";
    select.replaceChildren(node("option", t("fire_select_target")));
    select.firstElementChild.value = "";
    for (const row of rows) {
      const option = node("option", t("fire_target_option", {
        label: row.label || row.ref, bearing: number(row.bearing, 0), range: number(row.range_nm, 1),
      }));
      option.value = row.ref;
      select.append(option);
    }
    select.value = rows.some((row) => row.ref === previous) ? previous : "";
    if (previous && !select.value) clearFireConfirmation();
  }

  function stationRows(element, rows, entryBuilder, emptyKey = "station_none", actionBuilder = null) {
    const existing = new Map([...element.children].map((child) => [child.dataset.rowKey, child]));
    const live = new Set();
    rows.forEach((row, index) => {
      const key = String(row.ref ?? row.key ?? row.team ?? row.tube ?? index);
      live.add(key);
      let article = existing.get(key);
      if (!article) {
        article = node("article", undefined, "station-row"); article.dataset.rowKey = key;
        article.append(node("h4"), node("dl", undefined, "detail-metrics"), node("div", undefined, "station-row-actions"));
      }
      const entries = entryBuilder(row);
      const title = entries.shift();
      article.firstChild.textContent = String(title[1] ?? "");
      metrics(article.children[1], entries);
      const actions = actionBuilder?.(row) || [];
      const signature = JSON.stringify(actions.map((button) => [button.textContent, button.dataset, button.disabled]));
      if (signature !== article.dataset.actions) { article.lastChild.replaceChildren(...actions); article.dataset.actions = signature; }
      article.lastChild.hidden = !actions.length;
      if (element.children[index] !== article) element.insertBefore(article, element.children[index] || null);
    });
    for (const child of [...element.children]) if (!live.has(child.dataset.rowKey)) child.remove();
    if (!rows.length) element.replaceChildren(node("p", t(emptyKey), "empty"));
  }

  function clearVisuals() {
    visualDrawQueued = false;
    stopOpzSweepAnimation();
    roleMapHits = [];
    damageHits = [];
    for (const id of visualCanvasIds) releaseCanvas($(id));
    for (const element of document.querySelectorAll(".visual-equivalent")) element.replaceChildren();
    $("role-visual-state").textContent = "";
    $("role-map-scale").textContent = "";
  }

  function tacticalEntries(row) {
    return [["reference", row.label], ["domain", enumText(domains, row.domain)],
      ["source", row.source], ["affiliation", enumText(affiliations, row.affiliation)],
      ["bearing", unit(row.bearing, "\u00b0", 0)], ["range", unit(row.range_nm, "NM")],
      ["position", position(row)], ["course", unit(row.course, "\u00b0", 0)], ["speed", unit(row.speed_kn, "kn")],
      ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
      ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
      ["range_uncertainty", unit(row.range_uncertainty_nm, "NM")]];
  }

  function sonarEntries(row) {
    return [["reference", row.label], ["source", row.source],
      ["classification", classificationText(row.classification)], ["bearing", unit(row.bearing, "\u00b0", 0)],
      ["range", unit(row.range_nm, "NM")], ["position", position(row)], ["depth", unit(row.depth_m, "m", 0)],
      ["course", unit(row.course, "\u00b0", 0)], ["speed", unit(row.speed_kn, "kn")],
      ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
      ["fix_age", unit(row.fix_age_s, "s", 0)], ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
      ["range_uncertainty", unit(row.range_uncertainty_nm, "NM")],
      ["station_fixes", row.fixes.map((fix) => rawFields(fix)).join(" | ") || t("station_none")]];
  }

  function weaponTargetEntries(row) {
    return [["reference", row.label], ["domain", enumText(domains, row.domain)],
      ["source", row.source], ["affiliation", enumText(affiliations, row.affiliation)],
      ["classification", classificationText(row.classification)], ["bearing", unit(row.bearing, "\u00b0", 0)],
      ["range", unit(row.range_nm, "NM")], ["position", position(row)], ["depth", unit(row.depth_m, "m", 0)],
      ["course", unit(row.course, "\u00b0", 0)], ["speed", unit(row.speed_kn, "kn")],
      ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)], ["fix_age", unit(row.fix_age_s, "s", 0)],
      ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
      ["range_uncertainty", unit(row.range_uncertainty_nm, "NM")]];
  }

  function renderBridgeStation(payload) {
    const navigation = payload.navigation;
    metrics($("bridge-navigation"), [["position", position(navigation)], ["course", unit(navigation.course, "\u00b0", 0)],
      ["speed", unit(navigation.speed, "kn")], ["ordered_course", unit(navigation.target_course, "\u00b0", 0)],
      ["ordered_speed", unit(navigation.target_speed, "kn")], ["rudder_angle", unit(navigation.rudder_angle, "\u00b0")],
      ["yaw_rate", unit(navigation.yaw_rate, "\u00b0/s")]]);
    metrics($("bridge-orders-summary"), [["station_down", yesNo(payload.orders.station_down)],
      ["speed_max", unit(payload.orders.speed_max_kn, "kn")], ["telegraph", payload.orders.telegraph],
      ["noise", number(payload.orders.noise, 2)], ["cavitating", yesNo(payload.orders.cavitating)],
      ["threat_count", number(payload.threat.count, 0)], ["flood", unit(payload.threat.average_flood, "%")]]);
    stationRows($("bridge-tactical"), payload.tactical_summary, tacticalEntries);
  }

  function renderSonarStation(payload) {
    const settings = payload.settings;
    metrics($("sonar-settings"), [["sonar_mode", settings.mode], ["sonar_page", number(settings.page, 0)],
      ["sonar_listen_bearing", unit(settings.listen_bearing, "\u00b0", 0)], ["sonar_focus", settings.focus_ref || t("station_none")],
      ["sonar_target", settings.target_ref || t("station_none")], ["station_down", yesNo(settings.station_down)],
      ["sonar_tow_state", settings.tow.state], ["sonar_tow_depth", unit(settings.tow.depth_m, "m", 0)],
      ["sonar_bt_ready", yesNo(settings.bt.ready)], ["sonar_ping_ready", yesNo(settings.ping.ready)],
      ["sonar_tma", yesNo(settings.tma_enabled)], ["sonar_gain", unit(settings.gain_db, "dB")],
      ["sonar_band", settings.band_preset || settings.band_hz.map((value) => number(value, 0)).join("-")],
      ["sonar_notch", yesNo(settings.notch)], ["sonar_peak_hold", yesNo(settings.peak_hold)],
      ["sonar_harmonic", unit(settings.harmonic_hz, "Hz")], ["sonar_audio", yesNo(settings.audio_enabled)],
      ["sonar_volume", number(settings.volume, 2)], ["quiet_mode", yesNo(settings.quiet_mode)]]);
    const live = !settings.station_down;
    if (!stationDrafts.has("sonar-array-mode")) $("sonar-array-mode").value = settings.mode;
    const tasDeployed = ["DEPLOYING", "STREAMED"].includes(settings.tow.state);
    $("sonar-tas").textContent = t(tasDeployed ? "sonar_tas_retrieve" : "sonar_tas_deploy");
    $("sonar-tas").dataset.deployed = String(tasDeployed);
    $("sonar-tma").checked = settings.tma_enabled;
    $("sonar-notch").checked = settings.notch;
    $("sonar-peak").checked = settings.peak_hold;
    if (settings.band_preset && !stationDrafts.has("sonar-band")) $("sonar-band").value = settings.band_preset;
    $("sonar-harmonic-candidates").replaceChildren(...settings.harmonic_candidates_hz.map((value) => {
      const option = node("option"); option.value = String(value); return option;
    }));
    $("sonar-ping").dataset.ready = String(live && settings.ping.ready &&
      (settings.mode !== "TOWED" || settings.tow.available));
    $("sonar-bt").dataset.ready = String(live && settings.bt.ready);
    $("sonar-tas").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state !== "FAULT");
    $("sonar-depth-submit").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state === "STREAMED");
    $("sonar-depth").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state === "STREAMED");
    stationRows($("sonar-observations"), payload.observations, sonarEntries, "station_none", (row) => [
      actionButton("sonar_focus", "sonar_set_focus", {ref: row.ref}, live),
      actionButton("sonar_designate", "sonar_designate_target", {ref: row.ref}, live),
      actionButton(row.released_to_opz ? "sonar_withdraw_opz" : "sonar_release_to_opz",
        "sonar_set_release", {ref: row.ref, released: !row.released_to_opz}, live),
    ]);
  }

  function renderWeaponsStation(payload) {
    const inventory = payload.inventory;
    metrics($("weapons-inventory"), [["torpedoes", number(inventory.torpedoes, 0)], ["vls", number(inventory.vls, 0)],
      ["ciws", number(inventory.ciws, 0)], ["aa", number(inventory.aa, 0)], ["chaff", yesNo(inventory.chaff_ready)],
      ["nixies", number(inventory.nixies, 0)]]);
    const readiness = payload.readiness;
    metrics($("weapons-readiness"), [["station_down", yesNo(readiness.station_down)], ["roe", readiness.roe],
      ["ciws_ready", yesNo(readiness.ciws_ready)], ["aa_ready", yesNo(readiness.aa_ready)],
      ["state", readiness.state], ["interlock", readiness.interlock], ["reload", unit(readiness.reload_s, "s", 0)]]);
    stationRows($("weapons-target"), payload.designated_target ? [payload.designated_target] : [], weaponTargetEntries, "station_no_target");
    stationRows($("weapons-tubes"), payload.tubes, (row) => [["weapons_tube", number(row.tube, 0)],
      ["state", row.state], ["reload", unit(row.reload_s, "s", 0)]]);
    fillFireTargets("weapons-fire-target", payload.target_choices);
    if (!stationDrafts.has("weapons-fire-depth")) $("weapons-fire-depth").value = String(payload.depth_m);
    stationRows($("weapons-own"), payload.own_weapons, (row) => [["reference", row.ref], ["position", position(row)],
      ["depth", unit(row.depth_m, "m", 0)], ["course", unit(row.course, "\u00b0", 0)], ["state", row.state]]);
  }

  function renderDamageStation(payload) {
    metrics($("damage-summary"), [["damage_total", unit(payload.total, "%")], ["sunk", yesNo(payload.sunk)]]);
    const selector = $("damage-team");
    const selectedTeam = selector.value;
    selector.replaceChildren(...payload.teams.map((team) => {
      const option = node("option", number(team.team, 0));
      option.value = String(team.team);
      return option;
    }));
    if (payload.teams.some((team) => String(team.team) === selectedTeam)) selector.value = selectedTeam;
    stationRows($("damage-teams"), payload.teams, (team) => [["team", team.team], ["compartment", team.compartment]]);
    stationRows($("damage-compartments"), payload.compartments, (room) => [["compartment", room.name],
      ["reference", room.key], ["state", enumText(damageStates, room.state)], ["flood", unit(room.flood, "%")],
      ["fire", unit(room.fire, "%")], ["flood_trend", number(room.trend.flood_rate, 2)],
      ["fire_trend", number(room.trend.fire_rate, 2)], ["damage_repairable", yesNo(room.repairable)]], "station_none", (room) =>
      payload.teams.map((team) => actionButton(team.compartment === room.key ? "damage_unassign" : "damage_assign",
        team.compartment === room.key ? "damage_unassign_team" : "damage_assign_team",
        {team: team.team, compartment: room.key}, team.compartment === room.key || room.repairable)));
  }

  function renderOpzStation(payload) {
    const radar = payload.radar;
    metrics($("opz-radar-summary"), [["opz_surface_radar", yesNo(radar.surface)], ["opz_air_radar", yesNo(radar.air)],
      ["opz_range", unit(radar.range_nm, "NM")], ["radar_live", yesNo(radar.live)],
      ["radar_sweep", unit(radar.sweep_bearing, "\u00b0", 0)], ["weather_severity", number(radar.weather_severity, 2)],
      ["surface_range", unit(radar.surface_effective_range_nm, "NM")], ["air_range", unit(radar.air_effective_range_nm, "NM")],
      ["sonar_target", payload.designated_target_ref || t("station_no_target")]]);
    metrics($("opz-defense"), [["vls", number(payload.defense.vls, 0)], ["ciws", number(payload.defense.ciws, 0)],
      ["aa", number(payload.defense.aa, 0)], ["chaff", yesNo(payload.defense.chaff_ready)],
      ["ciws_ready", yesNo(payload.defense.ciws_ready)], ["aa_ready", yesNo(payload.defense.aa_ready)]]);
    fillFireTargets("opz-fire-target", payload.asm_observations);
    stationRows($("opz-observations"), payload.observations, tacticalEntries);
    stationRows($("opz-fusions"), payload.fusions, (row) => [...tacticalEntries(row), ["fusion_members", row.members.join(", ")]]);
    stationRows($("opz-classifications"), payload.source_classifications, (row) => [["reference", row.ref],
      ["source", row.source], ["classification", row.classification]]);
    const ship = payload.own_assets.ship;
    const helicopter = payload.own_assets.helicopter;
    stationRows($("opz-assets"), [{name: t("ownship"), ...ship}, {name: t("helicopter"), ...helicopter}], (asset) =>
      asset.name === t("ownship") ? [["reference", asset.name], ["position", position(asset)],
        ["course", unit(asset.course, "\u00b0", 0)], ["speed", unit(asset.speed, "kn")],
        ["ordered_course", unit(asset.target_course, "\u00b0", 0)], ["ordered_speed", unit(asset.target_speed, "kn")],
        ["rudder_angle", unit(asset.rudder_angle, "\u00b0")], ["yaw_rate", unit(asset.yaw_rate, "\u00b0/s")]] :
        [["reference", asset.name], ["state", enumText(heloStates, asset.state)], ["airborne", yesNo(asset.airborne)],
          ["position", position(asset)], ["course", unit(asset.course, "\u00b0", 0)], ["fuel", unit(asset.fuel_s, "s", 0)],
          ["torpedoes", number(asset.torpedoes, 0)], ["buoys", number(asset.buoys, 0)]]);
  }

  function renderRadioStation(payload) {
    stationRows($("radio-observations"), payload.observations, (row) => [["reference", row.label],
      ["bearing", unit(row.bearing, "\u00b0", 0)], ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
      ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")], ["radio_can_capture", yesNo(row.can_capture)]],
      "station_none", (row) => [actionButton("radio_capture", "radio_capture_hfdf", {ref: row.ref}, row.can_capture)]);
    stationRows($("radio-fixes"), payload.logged_fixes, (row) => [["reference", row.ref], ["position", position(row)],
      ["uncertainty", unit(row.uncertainty_nm, "NM")], ["age", unit(row.age_s, "s", 0)],
      ["covariance", row.covariance_nm2 ? row.covariance_nm2.map((value) => number(value, 2)).join(" / ") : t("unavailable")]]);
    stationRows($("radio-bearings"), payload.logged_bearings, (row) => [["reference", row.ref],
      ["bearing", unit(row.bearing, "\u00b0", 0)], ["observer_position", `${unit(row.observer_x, "NM")} / ${unit(row.observer_y, "NM")}`],
      ["age", unit(row.age_s, "s", 0)]]);
    stationRows($("radio-messages"), payload.messages, (row) => [["reference", row.stamp], ["message", row.text]]);
    if (payload.station_down) $("radio-observations").prepend(node("p", t("station_down_state"), "station-alert"));
  }

  function renderEngineStation(payload) {
    const propulsion = payload.propulsion;
    metrics($("engine-propulsion"), [["speed", unit(propulsion.speed, "kn")], ["ordered_speed", unit(propulsion.target_speed, "kn")],
      ["telegraph", propulsion.telegraph], ["rpm", unit(propulsion.rpm, "RPM", 0)], ["quiet_mode", yesNo(propulsion.quiet_mode)],
      ["cavitating", yesNo(propulsion.cavitating)]]);
    const machinery = payload.machinery;
    metrics($("engine-machinery"), [["station_state", machinery.station_state], ["speed_cap", unit(machinery.speed_cap, "kn")],
      ["effective_speed_cap", unit(machinery.effective_speed_cap, "kn")], ["flood", unit(machinery.flood, "%")],
      ["fire", unit(machinery.fire, "%")], ["noise", number(machinery.noise, 2)], ["grounded", yesNo(machinery.grounded)]]);
    const effects = payload.environment_effects;
    metrics($("engine-environment"), [["sea_state", number(effects.sea_state, 0)], ["roll", unit(effects.roll, "\u00b0")],
      ["pitch", unit(effects.pitch, "\u00b0")], ["tas_available", yesNo(effects.tas_available)],
      ["tas_performance", number(effects.tas_performance, 2)]]);
    const controls = payload.controls;
    if (!$("engine-telegraph").options.length) $("engine-telegraph").replaceChildren(...controls.orders.map((order) => {
      const option = node("option", order); option.value = order; return option;
    }));
    if (!stationDrafts.has("engine-telegraph")) $("engine-telegraph").value = propulsion.telegraph;
    $("engine-speed").max = String(Math.min(controls.speed_max_kn, machinery.speed_cap));
    $("engine-quiet").textContent = t(propulsion.quiet_mode ? "engine_quiet_disable" : "engine_quiet_enable");
    $("engine-quiet").setAttribute("aria-pressed", String(propulsion.quiet_mode));
  }

  function renderHelicopterStation(payload) {
    const asset = payload.asset;
    metrics($("helicopter-asset"), [["state", enumText(heloStates, asset.state)], ["airborne", yesNo(asset.airborne)],
      ["position", position(asset)], ["course", unit(asset.course, "\u00b0", 0)], ["fuel", unit(asset.fuel_s, "s", 0)],
      ["torpedoes", number(asset.torpedoes, 0)], ["buoys", number(asset.buoys, 0)],
      ["helicopter_hovering", yesNo(asset.hovering)], ["helicopter_dip_state", asset.dip_state],
      ["helicopter_dip_depth", unit(asset.dip_depth_m, "m", 0)],
      ["helicopter_dip_water", unit(asset.dip_water_depth_m, "m", 0)],
      ["helicopter_dip_cooldown", unit(asset.dip_ping_cooldown_s, "s", 0)]]);
    metrics($("helicopter-waypoint"), [["position", payload.waypoint ? position(payload.waypoint) : t("station_none")]]);
    const ready = payload.readiness;
    metrics($("helicopter-readiness"), [["flightdeck_down", yesNo(ready.flightdeck_down)],
      ["helicopter_can_launch", yesNo(ready.can_launch)], ["helicopter_can_return", yesNo(ready.can_return)],
      ["deck_state", ready.deck_state], ["helicopter_can_waypoint", yesNo(ready.can_set_waypoint)],
      ["helicopter_can_buoy", yesNo(ready.can_deploy_buoy)],
      ["helicopter_can_dipping", yesNo(ready.can_set_dipping)],
      ["helicopter_can_dip_ping", yesNo(ready.can_dipping_ping)],
      ["rtb_margin", unit(ready.rtb_margin_s, "s", 0)]]);
    $("helicopter-launch").dataset.ready = String(ready.can_launch);
    $("helicopter-return").dataset.ready = String(ready.can_return);
    $("helicopter-waypoint-submit").dataset.ready = String(ready.can_set_waypoint);
    $("helicopter-x").dataset.ready = String(ready.can_set_waypoint);
    $("helicopter-y").dataset.ready = String(ready.can_set_waypoint);
    $("helicopter-buoy").dataset.ready = String(ready.can_deploy_buoy);
    const dipping = asset.dip_state !== "STOWED";
    $("helicopter-dip-toggle").textContent = t(dipping ? "helicopter_dip_retrieve" : "helicopter_dip_deploy");
    $("helicopter-dip-toggle").dataset.deployed = String(dipping);
    $("helicopter-dip-toggle").dataset.ready = String(ready.can_set_dipping);
    $("helicopter-dip-ping").dataset.ready = String(ready.can_dipping_ping);
    $("helicopter-dip-depth").dataset.ready = String(ready.can_set_dip_depth);
    $("helicopter-dip-depth-submit").dataset.ready = String(ready.can_set_dip_depth);
    if (!stationDrafts.has("helicopter-dip-depth")) {
      $("helicopter-dip-depth").value = String(asset.dip_depth_target_m);
    }
    fillFireTargets("helicopter-fire-target", payload.target_choices);
    if (!stationDrafts.has("helicopter-fire-depth")) $("helicopter-fire-depth").value = "80";
    stationRows($("helicopter-buoys"), payload.buoys, (row) => [["reference", row.ref], ["position", position(row)],
      ["battery", unit(row.battery_s, "s", 0)], ["active", yesNo(row.active)]]);
  }

  function renderElokaStation(payload) {
    stationRows($("eloka-intercepts"), payload.intercepts, (row) => [["reference", row.label],
      ["bearing", unit(row.bearing, "\u00b0", 0)], ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
      ["frequency", unit(row.frequency_hz, "Hz", 0)], ["prf", unit(row.prf_hz, "Hz", 0)],
      ["modulation", row.modulation], ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
      ["annotation", row.annotation || t("station_none")],
      ["candidates", row.candidates.map((item) => `${item.name}: ${number(item.score, 2)}`).join(" / ") || t("station_none")],
      ["correlations", row.correlations.map((item) => `${item.ref} / ${item.source}: ${number(item.score, 2)} (${t(item.ambiguous ? "ambiguous" : "unambiguous")}); ${unit(item.evidence.bearing, "\u00b0", 0)} / ${unit(item.evidence.age_s, "s", 0)}`).join(" / ") || t("station_none")]],
      "station_none", (row) => [...row.candidates.map((candidate) => actionButton("eloka_annotate_candidate",
        "eloka_annotate", {ref: row.ref, candidate_ref: candidate.ref}, !payload.station_down, {candidate: candidate.name})),
      actionButton("eloka_clear", "eloka_clear_annotation", {ref: row.ref}, !payload.station_down && row.annotation !== null)]);
    if (payload.station_down) $("eloka-intercepts").prepend(node("p", t("station_down_state"), "station-alert"));
  }

  function visualContext(id) {
    const element = $(id);
    if (element.closest("[hidden]")) { releaseCanvas(element); return null; }
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (!width || !height) return null;
    const context = element.getContext("2d");
    resizeCanvas(element, context, width, height);
    context.fillStyle = "#07151c";
    context.fillRect(0, 0, width, height);
    context.font = `${Math.max(11, parseFloat(getComputedStyle(document.documentElement).fontSize) * .68)}px ui-monospace, monospace`;
    context.lineWidth = 1.5;
    return {element, context, width, height};
  }

  function drawEmpty(plot, key = "visual_empty") {
    plot.context.fillStyle = "#a7b9bf";
    plot.context.textAlign = "center";
    plot.context.fillText(t(key), plot.width / 2, plot.height / 2);
  }

  function plotAxes(plot, xmax, ymax, xunit, yunit, xorigin = 0, reverseY = false) {
    const context = plot.context;
    const {left, top, width, height} = plotArea(plot.width, plot.height);
    context.fillStyle = "#a7b9bf"; context.strokeStyle = "#30434e"; context.textAlign = "center";
    for (let tick = 0; tick <= 4; tick++) {
      const x = left + tick * width / 4, y = top + tick * height / 4;
      context.fillText(`${number(xorigin + xmax * tick / 4, 0)}${tick === 4 ? xunit : ""}`, x, top + height + 20);
      context.textAlign = "right"; context.fillText(`${number(ymax * (reverseY ? 1 - tick / 4 : tick / 4), ymax < 2 ? 1 : 0)}`, left - 6, y + 4); context.textAlign = "center";
      context.beginPath(); context.moveTo(x, top); context.lineTo(x, top + height); context.stroke();
    }
    context.fillText(yunit, left, 14);
    context.translate(left, top);
    return {...plot, width, height};
  }

  function plotArea(width, height) {
    const left = 46, top = 22;
    return {left, top, width: Math.max(1, width - left - 18),
      height: Math.max(1, height - top - 30)};
  }

  function heatmap(id, rows, frequencies = null) {
    const plot = visualContext(id);
    if (!plot) return null;
    if (!rows.length || !rows.some((row) => row.bins.length)) { drawEmpty(plot); return null; }
    const maxAge = Math.max(20, ...rows.map((row) => row.age_s));
    const area = plotAxes(plot, frequencies ? 300 : 360, maxAge, frequencies ? " Hz" : "°", "s");
    const count = Math.max(...rows.map((row) => row.bins.length));
    rows.forEach((row) => row.bins.forEach((value, x) => {
      const level = Math.max(0, Math.min(1, value));
      area.context.fillStyle = `rgb(${Math.round(7 + level ** .72 * 110)} ${Math.round(21 + level ** .72 * 200)} ${Math.round(28 + level ** .72 * 160)})`;
      const start = frequencies ? frequencies[x] / 300 : x / count;
      const end = frequencies ? (frequencies[x + 1] ?? 300) / 300 : (x + 1) / count;
      area.context.fillRect(start * area.width, row.age_s / maxAge * area.height,
        Math.max(1, (end - start) * area.width), Math.max(1, .25 / maxAge * area.height));
    }));
    return area;
  }

  function spectrum(id, values, markers = [], frequencies = null, xmax = 80) {
    let plot = visualContext(id);
    if (!plot) return;
    if (!values.length) { drawEmpty(plot); return; }
    const maximum = Math.max(1e-6, ...values.map((value) => Math.abs(value)));
    plot = plotAxes(plot, xmax, maximum, " Hz", "rel.", 0, true);
    plot.context.strokeStyle = "#a1e7cc";
    plot.context.beginPath();
    values.forEach((value, index) => {
      const x = frequencies ? frequencies[index] / xmax * plot.width : values.length === 1 ? 0 : index / (values.length - 1) * plot.width;
      const y = plot.height - Math.max(0, value) / maximum * (plot.height - 12);
      index ? plot.context.lineTo(x, y) : plot.context.moveTo(x, y);
    });
    plot.context.stroke();
    plot.context.fillStyle = "#f3c577";
    for (const marker of markers.slice(0, 20)) plot.context.fillText(marker.text, Math.max(2, Math.min(plot.width - 50, marker.x * plot.width)), 14);
  }

  function drawSonarVisuals() {
    const visual = v2State.sonar.visualization;
    const broadband = heatmap("sonar-broadband", visual.broadband.history);
    if (broadband) {
      const bearing = visual.receiver.listen_bearing % 360;
      const half = visual.receiver.beam_width_deg / 2;
      broadband.context.strokeStyle = "#a7b9bf";
      for (const value of [(bearing - half + 360) % 360, (bearing + half) % 360]) {
        const x = value / 360 * broadband.width;
        broadband.context.beginPath(); broadband.context.moveTo(x, 0);
        broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
      }
      broadband.context.strokeStyle = "#f3c577";
      const x = bearing / 360 * broadband.width;
      broadband.context.beginPath(); broadband.context.moveTo(x, 0);
      broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
    }
    heatmap("sonar-lofar", visual.lofar.history, visual.lofar.bin_frequencies_hz);
    spectrum("sonar-spectrum", visual.lofar.spectrum, [], visual.lofar.bin_frequencies_hz, 300);
    const peak = visual.demon.analysis?.modulation_peak_hz;
    spectrum("sonar-demon", visual.demon.spectrum, finite(peak) ? [{x: peak / 80, text: `${number(peak, 1)} Hz`}] : []);
    let tma = visualContext("sonar-tma-plot");
    if (tma) {
      const contacts = visual.tma.filter((row) => row.bearings.length);
      if (!contacts.length) drawEmpty(tma);
      const maxAge = Math.max(1, ...contacts.flatMap((track) => track.bearings.map((point) => point.age_s)));
      tma = plotAxes(tma, maxAge, 360, " s", "°");
      contacts.forEach((track, index) => {
        tma.context.strokeStyle = ["#a1e7cc", "#f3c577", "#81c5ff", "#ff9090"][index % 4];
        tma.context.beginPath();
        track.bearings.forEach((point, pointIndex) => {
          const x = point.age_s / maxAge * tma.width;
          const y = point.bearing / 360 * tma.height;
          pointIndex && Math.abs(point.bearing - track.bearings[pointIndex - 1].bearing) < 180 ? tma.context.lineTo(x, y) : tma.context.moveTo(x, y);
        });
        tma.context.stroke();
      });
    }
    let bt = visualContext("sonar-environment");
    if (bt) {
      if (!visual.bt || !visual.bt.depths_m.length) drawEmpty(bt);
      else {
        const min = Math.min(...visual.bt.speeds_m_s), max = Math.max(...visual.bt.speeds_m_s, min + 1);
        const depth = Math.max(1, ...visual.bt.depths_m);
        bt = plotAxes(bt, max - min, depth, " m/s", "m", min);
        bt.context.fillStyle = "#a7b9bf";
        bt.context.fillText(`${number(min, 0)}–${number(max, 0)} m/s`, bt.width / 2, -7);
        if (finite(visual.bt.thermocline_m)) { const y = visual.bt.thermocline_m / depth * bt.height; bt.context.strokeStyle = "#f3c577"; bt.context.setLineDash([4, 4]); bt.context.beginPath(); bt.context.moveTo(0, y); bt.context.lineTo(bt.width, y); bt.context.stroke(); bt.context.setLineDash([]); }
        bt.context.strokeStyle = "#81c5ff"; bt.context.beginPath();
        visual.bt.depths_m.forEach((value, index) => {
          const x = 12 + (visual.bt.speeds_m_s[index] - min) / (max - min) * (bt.width - 24);
          const y = value / depth * bt.height;
          index ? bt.context.lineTo(x, y) : bt.context.moveTo(x, y);
        });
        bt.context.stroke();
      }
    }
    const active = visualContext("sonar-active");
    if (active) {
      const radius = Math.min(active.width, active.height) * .44, cx = active.width / 2, cy = active.height / 2;
      active.context.strokeStyle = "#30434e";
      for (const scale of [.25, .5, .75, 1]) { active.context.beginPath(); active.context.arc(cx, cy, radius * scale, 0, Math.PI * 2); active.context.stroke(); }
      const maxRange = Math.max(5, Math.ceil(Math.max(0, ...visual.active_echoes.map((echo) => echo.range_nm)) / 5) * 5);
      active.context.fillStyle = "#a7b9bf"; active.context.fillText(`N · ${number(maxRange, 0)} NM`, cx, 18);
      for (const echo of visual.active_echoes) {
        const angle = echo.bearing * Math.PI / 180;
        const r = echo.range_nm / maxRange * radius;
        active.context.fillStyle = "#f3c577"; active.context.beginPath();
        active.context.arc(cx + Math.sin(angle) * r, cy - Math.cos(angle) * r, 3, 0, Math.PI * 2); active.context.fill();
      }
      if (!visual.active_echoes.length) drawEmpty(active);
    }
    $("sonar-broadband-text").textContent = t("sonar_broadband_equivalent", {rows: visual.broadband.history.length, bins: visual.broadband.history.at(-1)?.bins.length || 0});
    $("sonar-lofar-text").textContent = t("sonar_lofar_equivalent", {rows: visual.lofar.history.length, bins: visual.lofar.spectrum.length, held: yesNo(visual.lofar.held)});
    $("sonar-demon-text").textContent = t("sonar_demon_equivalent", {bins: visual.demon.spectrum.length, hypotheses: visual.demon.analysis?.hypotheses.length || 0});
    for (const item of visual.demon.analysis?.hypotheses || []) $("sonar-demon-text").append(node("p",
      t("sonar_rpm_hypothesis", {blades: item.blades, order: item.order, rpm: number(item.rpm, 1)})));
    $("sonar-tma-text").replaceChildren(...visual.tma.map((row) => node("p", t("sonar_tma_equivalent", {ref: row.ref, points: row.bearings.length, solution: row.solution ? `${position(row.solution)} / ${unit(row.solution.course, "\u00b0", 0)} / ${unit(row.solution.speed_kn, "kn")}` : t("station_none")}))));
    if (!visual.tma.length) $("sonar-tma-text").textContent = t("visual_empty");
    $("sonar-environment-text").textContent = visual.bt ? t("sonar_environment_equivalent", {age: number(visual.bt.age_s, 0), depth: number(visual.bt.water_depth_m, 0), thermocline: number(visual.bt.thermocline_m, 0), array: visual.receiver.array}) : t("visual_empty");
    $("sonar-active-text").textContent = t("sonar_active_equivalent", {count: visual.active_echoes.length});
    for (const echo of visual.active_echoes) $("sonar-active-text").append(node("p", `${unit(echo.bearing, "°", 0)} · ${unit(echo.range_nm, "NM")} ± ${unit(echo.range_uncertainty_nm, "NM")} · ${unit(echo.depth_m, "m", 0)} · ${unit(echo.snr_db, "dB")} · ${unit(echo.age_s, "s")}`));
  }

  function mapPayload(role) {
    const payload = v2State[role];
    if (role === "bridge") return {own: payload.navigation, observations: payload.tactical_summary, assets: [], bearingLogs: [], fixes: []};
    if (role === "weapons") return {own: payload.navigation, observations: payload.tactical, assets: payload.active_assets, bearingLogs: [], fixes: []};
    if (role === "opz") return {own: payload.own_assets.ship, observations: [...payload.observations, ...payload.fusions], assets: payload.own_assets.helicopter.airborne ? [payload.own_assets.helicopter] : [], bearingLogs: [], fixes: []};
    if (role === "radio") return {own: payload.navigation, observations: payload.tactical, assets: [], bearingLogs: payload.logged_bearings, fixes: payload.logged_fixes};
    return {own: payload.navigation, observations: payload.tactical, assets: [payload.asset, ...payload.buoys, ...(payload.waypoint ? [{...payload.waypoint, waypoint: true}] : [])], bearingLogs: [], fixes: []};
  }

  function currentOpzSweepBearing() {
    if (!opzSweepSample) return null;
    return (opzSweepSample.bearing + Math.max(0, performance.now() - opzSweepSample.receivedAt) / 1000 * opzSweepSample.rate) % 360;
  }

  function updateOpzSweepSample(state) {
    const radar = state?.role === "opz" ? state.opz.radar : null;
    if (!radar || !finite(radar.sweep_bearing)) { opzSweepSample = null; stopOpzSweepAnimation(); return; }
    opzSweepSample = {bearing: radar.sweep_bearing, receivedAt: performance.now(),
      rate: finite(radar.sweep_rate_deg_s) ? radar.sweep_rate_deg_s : 90};
  }

  function opzSweepActive() {
    const radar = v2State?.role === "opz" ? v2State.opz.radar : null;
    return connected && !document.hidden && navigator.onLine !== false && opzSweepSample?.rate > 0 && v2State?.phase === "live" &&
      radar?.live === true && (radar.surface || radar.air) && !$("role-map").closest("[hidden]") &&
      $("role-map").clientWidth > 0 && $("role-map").clientHeight > 0;
  }

  function stopOpzSweepAnimation() {
    if (opzSweepFrame !== null) cancelAnimationFrame(opzSweepFrame);
    opzSweepFrame = null;
  }

  function syncOpzSweepAnimation() {
    if (!opzSweepActive()) { stopOpzSweepAnimation(); return; }
    if (opzSweepFrame !== null) return;
    const animate = () => {
      opzSweepFrame = null;
      if (!opzSweepActive()) return;
      drawRoleMap("opz");
      opzSweepFrame = requestAnimationFrame(animate);
    };
    opzSweepFrame = requestAnimationFrame(animate);
  }

  function roleMapGeometry(role, width = $("role-map").clientWidth, height = $("role-map").clientHeight) {
    const viewState = roleMapViews[role];
    if (!chart || !viewState || !width || !height) return null;
    const scale = Math.min(width, height) / chart.size_nm * viewState.zoom;
    return {scale, point: (x, y) => [width / 2 + (x - viewState.x) * scale,
      height / 2 + (y - viewState.y) * scale]};
  }

  function addRoleMapHit(ref, x, y) {
    if (roleMapHits.length < maxRoleMapHits && x >= -26 && y >= -26 &&
        x <= $("role-map").clientWidth + 26 && y <= $("role-map").clientHeight + 26) {
      roleMapHits.push({ref, x, y});
    }
  }

  function drawRoleMap(role) {
    const plot = visualContext("role-map");
    roleMapHits = [];
    if (!plot || !chart) return;
    const payload = v2State[role], data = mapPayload(role), viewState = roleMapViews[role];
    if (!viewState.initialized) { viewState.initialized = true; viewState.follow = true; viewState.zoom = role === "opz" ? chart.size_nm / (2 * payload.radar.range_nm) : 2; }
    if (viewState.follow && hasPosition(data.own)) { viewState.x = data.own.x; viewState.y = data.own.y; }
    $("role-map-follow").setAttribute("aria-pressed", String(Boolean(viewState.follow)));
    const {scale, point} = roleMapGeometry(role, plot.width, plot.height);
    const geo = chart.geography;
    if (geo?.depths.length) {
      const size = geo.depths.length, cell = chart.size_nm / Math.max(1, size - 1);
      for (let y = 0; y < size - 1; y++) for (let x = 0; x < geo.depths[y].length - 1; x++) {
        const [px, py] = point(x * cell, y * cell);
        if (px > plot.width || py > plot.height || px + cell * scale < 0 || py + cell * scale < 0) continue;
        const deep = Math.max(0, Math.min(1, geo.depths[y][x] / 900));
        plot.context.fillStyle = `rgb(${Math.round(16 - 9 * deep)} ${Math.round(45 - 24 * deep)} ${Math.round(58 - 30 * deep)})`;
        plot.context.fillRect(px, py, cell * scale + 1, cell * scale + 1);
      }
    }
    const step = viewState.zoom >= 8 ? 10 : viewState.zoom >= 3 ? 25 : 50;
    plot.context.strokeStyle = "#243b46"; plot.context.fillStyle = "#829ba5";
    for (let value = 0; value <= chart.size_nm; value += step) {
      const [x, y] = point(value, value);
      if (x >= 0 && x <= plot.width) { plot.context.beginPath(); plot.context.moveTo(x, 0); plot.context.lineTo(x, plot.height); plot.context.stroke(); plot.context.fillText(String(value), x + 2, plot.height - 5); }
      if (y >= 0 && y <= plot.height) { plot.context.beginPath(); plot.context.moveTo(0, y); plot.context.lineTo(plot.width, y); plot.context.stroke(); plot.context.fillText(String(value), 2, y + 12); }
    }
    plot.context.strokeStyle = "#30434e"; plot.context.fillStyle = "#233d38";
    for (const land of chart.landmasses) {
      plot.context.beginPath(); land.points.forEach(([x, y], index) => { const p = point(x, y); index ? plot.context.lineTo(...p) : plot.context.moveTo(...p); });
      plot.context.closePath(); plot.context.fill(); plot.context.stroke();
    }
    plot.context.fillStyle = "#a7b9bf";
    for (const label of [...(geo?.labels || []), ...(geo?.airbases || [])]) {
      const [x, y] = point(label.x, label.y);
      if (x >= 0 && x <= plot.width && y >= 0 && y <= plot.height) plot.context.fillText(label.name, x + 5, y - 5);
    }
    for (const base of geo?.airbases || []) { const [x, y] = point(base.x, base.y); plot.context.strokeRect(x - 3, y - 3, 6, 6); }
    const [ox, oy] = hasPosition(data.own) ? point(data.own.x, data.own.y) : [plot.width / 2, plot.height / 2];
    if (hasPosition(data.own)) {
      addRoleMapHit(null, ox, oy);
      plot.context.save(); plot.context.translate(ox, oy); plot.context.rotate(data.own.course * Math.PI / 180);
      plot.context.strokeStyle = "#a1e7cc"; plot.context.fillStyle = "#a1e7cc"; plot.context.beginPath();
      plot.context.moveTo(0, -9); plot.context.lineTo(-5, 6); plot.context.lineTo(5, 6); plot.context.closePath(); plot.context.fill();
      plot.context.beginPath(); plot.context.moveTo(0, -9); plot.context.lineTo(0, -35); plot.context.stroke(); plot.context.restore();
    }
    for (const row of data.observations) {
      plot.context.strokeStyle = colors[row.affiliation] || colors.UNKNOWN;
      if (hasPosition(row)) {
        const [x, y] = point(row.x, row.y);
        addRoleMapHit(row.ref, x, y);
        if (finite(row.range_uncertainty_nm)) { plot.context.beginPath(); plot.context.arc(x, y, row.range_uncertainty_nm * scale, 0, Math.PI * 2); plot.context.stroke(); }
        plot.context.fillStyle = plot.context.strokeStyle; plot.context.beginPath(); plot.context.arc(x, y, 4, 0, Math.PI * 2); plot.context.fill();
        plot.context.fillText(row.label || row.ref, x + 6, y - 6);
        if (finite(row.course)) { const angle = row.course * Math.PI / 180; plot.context.beginPath(); plot.context.moveTo(x, y); plot.context.lineTo(x + Math.sin(angle) * 22, y - Math.cos(angle) * 22); plot.context.stroke(); }
      } else if (finite(row.bearing) && (hasPosition(data.own) ||
          finite(row.observer_x) && finite(row.observer_y))) {
        const [bx, by] = finite(row.observer_x) && finite(row.observer_y) ?
          point(row.observer_x, row.observer_y) : [ox, oy];
        const angle = row.bearing * Math.PI / 180;
        if (finite(row.bearing_uncertainty_deg)) {
          const delta = row.bearing_uncertainty_deg * Math.PI / 180, length = Math.max(plot.width, plot.height);
          plot.context.fillStyle = "rgb(243 197 119 / .08)"; plot.context.beginPath(); plot.context.moveTo(bx, by);
          plot.context.lineTo(bx + Math.sin(angle - delta) * length, by - Math.cos(angle - delta) * length);
          plot.context.lineTo(bx + Math.sin(angle + delta) * length, by - Math.cos(angle + delta) * length); plot.context.closePath(); plot.context.fill();
        }
        plot.context.setLineDash([5, 5]); plot.context.beginPath(); plot.context.moveTo(bx, by);
        plot.context.lineTo(bx + Math.sin(angle) * Math.max(plot.width, plot.height), by - Math.cos(angle) * Math.max(plot.width, plot.height)); plot.context.stroke(); plot.context.setLineDash([]);
      }
    }
    for (const log of data.bearingLogs) {
      const [x, y] = point(log.observer_x, log.observer_y), angle = log.bearing * Math.PI / 180;
      plot.context.strokeStyle = "#f3c577"; plot.context.setLineDash([3, 4]); plot.context.beginPath(); plot.context.moveTo(x, y); plot.context.lineTo(x + Math.sin(angle) * plot.width, y - Math.cos(angle) * plot.width); plot.context.stroke(); plot.context.setLineDash([]);
    }
    for (const item of [...data.fixes, ...data.assets]) if (hasPosition(item)) {
      const [x, y] = point(item.x, item.y);
      addRoleMapHit(null, x, y);
      plot.context.strokeStyle = item.waypoint ? "#f3c577" : "#81c5ff";
      if (finite(item.uncertainty_nm)) { plot.context.beginPath(); plot.context.arc(x, y, item.uncertainty_nm * scale, 0, Math.PI * 2); plot.context.stroke(); }
      plot.context.strokeRect(x - 4, y - 4, 8, 8);
      plot.context.fillStyle = plot.context.strokeStyle; plot.context.fillText(item.waypoint ? t("station_waypoint") : item.ref || t("helicopter"), x + 6, y + 12);
    }
    if (role === "opz" && hasPosition(data.own)) {
      if (payload.radar.live && (payload.radar.surface || payload.radar.air)) {
        for (const range of [payload.radar.surface_effective_range_nm, payload.radar.air_effective_range_nm]) if (finite(range)) { plot.context.strokeStyle = "#365d69"; plot.context.beginPath(); plot.context.arc(ox, oy, range * scale, 0, Math.PI * 2); plot.context.stroke(); }
        const sweepBearing = currentOpzSweepBearing() ?? payload.radar.sweep_bearing;
        if (finite(sweepBearing)) { const angle = sweepBearing * Math.PI / 180; plot.context.strokeStyle = "#a1e7cc"; plot.context.beginPath(); plot.context.moveTo(ox, oy); plot.context.lineTo(ox + Math.sin(angle) * payload.radar.range_nm * scale, oy - Math.cos(angle) * payload.radar.range_nm * scale); plot.context.stroke(); }
      }
      const byRef = new Map(data.observations.map((row) => [row.ref, row]));
      for (const fusion of payload.fusions) if (hasPosition(fusion)) for (const ref of fusion.members) { const member = byRef.get(ref); if (hasPosition(member)) { plot.context.strokeStyle = "#697f88"; plot.context.beginPath(); plot.context.moveTo(...point(fusion.x, fusion.y)); plot.context.lineTo(...point(member.x, member.y)); plot.context.stroke(); } }
    }
    $("role-map-scale").textContent = t("role_map_scale", {distance: number(chart.size_nm / viewState.zoom, 0)});
    plot.context.textAlign = "right"; plot.context.fillStyle = "#e9eee8"; plot.context.fillText("N ↑", plot.width - 10, 18);
    const equivalent = [t("role_map_own", {position: hasPosition(data.own) ? position(data.own) : t("unavailable")})];
    equivalent.push(...data.observations.map((row) => t("role_map_observation", {ref: row.ref, bearing: number(row.bearing, 0), position: hasPosition(row) ? position(row) : t("bearing_only")})));
    equivalent.push(...data.fixes.map((row) => t("role_map_fix", {ref: row.ref, position: position(row), uncertainty: number(row.uncertainty_nm, 1)})));
    $("role-map-text").replaceChildren(...equivalent.slice(0, 256).map((text) => node("li", text)));
  }

  function gauge(context, x, y, radius, value, maximum, label) {
    context.strokeStyle = "#30434e"; context.lineWidth = 6; context.beginPath(); context.arc(x, y, radius, Math.PI, Math.PI * 2); context.stroke();
    context.strokeStyle = "#a1e7cc"; context.beginPath(); context.arc(x, y, radius, Math.PI, Math.PI + Math.PI * Math.max(0, Math.min(1, value / Math.max(1e-6, maximum)))); context.stroke();
    context.fillStyle = "#e9eee8"; context.textAlign = "center"; context.fillText(label, x, y + 18);
  }

  function drawDamageVisual() {
    const plot = visualContext("damage-schematic"), payload = v2State.damage;
    damageHits = [];
    if (!plot) return;
    const columns = Math.max(1, Math.min(4, Math.ceil(Math.sqrt(payload.compartments.length * plot.width / Math.max(1, plot.height)))));
    const rows = Math.max(1, Math.ceil(payload.compartments.length / columns));
    const roomW = (plot.width - 32) / columns, roomH = (plot.height - 24) / rows;
    const selectedTeam = Number($("damage-team").value);
    payload.compartments.forEach((room, index) => {
      const x = 16 + (index % columns) * roomW, y = 12 + Math.floor(index / columns) * roomH;
      const width = roomW - 6, height = roomH - 6;
      damageHits.push({key: room.key, x, y, width, height});
      const assigned = payload.teams.some((team) => team.team === selectedTeam && team.compartment === room.key);
      plot.context.strokeStyle = assigned ? "#a1e7cc" : room.state === "ZERSTOERT" ? "#ff9090" : "#536873";
      plot.context.lineWidth = assigned ? 3 : 1.5; plot.context.strokeRect(x, y, width, height);
      plot.context.fillStyle = "#e9eee8"; plot.context.textAlign = "left"; plot.context.fillText(room.name, x + 6, y + 20, roomW - 18);
      plot.context.fillText(enumText(damageStates, room.state), x + 6, y + 38, roomW - 18);
      plot.context.fillStyle = "#397fa5"; plot.context.fillRect(x + 6, y + height - 29, (roomW - 18) * room.flood / 100, 10);
      plot.context.fillStyle = "#c95d43"; plot.context.fillRect(x + 6, y + height - 14, (roomW - 18) * room.fire / 100, 10);
    });
    $("damage-schematic-text").replaceChildren(...payload.compartments.map((room) => node("p", t("damage_compartment_equivalent", {name: room.name, flood: number(room.flood, 0), fire: number(room.fire, 0), flood_trend: number(room.trend.flood_rate, 2), fire_trend: number(room.trend.fire_rate, 2), teams: payload.teams.filter((team) => team.compartment === room.key).map((team) => team.team).join(", ") || t("station_none")}))));
    if (!payload.compartments.length) $("damage-schematic-text").textContent = t("visual_empty");
  }

  function drawEngineVisual() {
    const plot = visualContext("engine-instruments"), payload = v2State.engine;
    if (!plot) return;
    const p = payload.propulsion, m = payload.machinery, e = payload.environment_effects;
    const radius = Math.min(65, plot.width / 10, plot.height / 3);
    gauge(plot.context, plot.width * .18, plot.height * .55, radius, p.rpm, 300, `${number(p.rpm, 0)} RPM`);
    gauge(plot.context, plot.width * .5, plot.height * .55, radius, p.speed, payload.controls.speed_max_kn, `${number(p.speed, 1)} kn`);
    gauge(plot.context, plot.width * .82, plot.height * .55, radius, m.noise, 1, t("noise"));
    plot.context.fillStyle = p.cavitating ? "#ff9090" : "#a1e7cc"; plot.context.textAlign = "center"; plot.context.fillText(`${p.telegraph} / ${t(p.cavitating ? "cavitating" : "not_cavitating")}`, plot.width / 2, 22);
    $("engine-instruments-text").textContent = t("engine_equivalent", {telegraph: p.telegraph, rpm: number(p.rpm, 0), speed: number(p.speed, 1), target: number(p.target_speed, 1), cap: number(m.effective_speed_cap, 1), noise: number(m.noise, 2), roll: number(e.roll, 1), pitch: number(e.pitch, 1)});
  }

  function drawElokaVisual() {
    const plot = visualContext("eloka-scope"), payload = v2State.eloka;
    if (!plot) return;
    const radius = Math.min(plot.width, plot.height) * .42, cx = plot.width / 2, cy = plot.height / 2;
    plot.context.strokeStyle = "#30434e"; plot.context.beginPath(); plot.context.arc(cx, cy, radius, 0, Math.PI * 2); plot.context.stroke();
    for (const row of payload.intercepts) { const angle = row.bearing * Math.PI / 180; plot.context.strokeStyle = "#f3c577"; plot.context.lineWidth = 2 + row.quality * 3; plot.context.beginPath(); plot.context.moveTo(cx, cy); plot.context.lineTo(cx + Math.sin(angle) * radius, cy - Math.cos(angle) * radius); plot.context.stroke(); }
    if (!payload.intercepts.length) drawEmpty(plot);
    $("eloka-scope-text").replaceChildren(...payload.intercepts.map((row) => node("p", t("eloka_equivalent", {ref: row.label, bearing: number(row.bearing, 0), frequency: number(row.frequency_hz, 0), prf: number(row.prf_hz, 0), modulation: row.modulation, candidates: row.candidates.map((item) => item.name).join(", ") || t("station_none"), correlations: row.correlations.map((item) => item.ref).join(", ") || t("station_none")}))));
    if (!payload.intercepts.length) $("eloka-scope-text").textContent = t("visual_empty");
  }

  function drawWeaponsVisual() {
    const plot = visualContext("weapons-system"), payload = v2State.weapons;
    if (!plot) return;
    const stages = [payload.readiness.station_down ? t("station_down_state") : t("station_live_state"), payload.readiness.roe, payload.readiness.interlock];
    stages.forEach((text, index) => { const x = 10 + index * plot.width / 3; plot.context.fillStyle = index === 2 && payload.readiness.interlock ? "#53421f" : "#24493f"; plot.context.fillRect(x, 20, plot.width / 3 - 20, 45); plot.context.fillStyle = "#e9eee8"; plot.context.textAlign = "center"; plot.context.fillText(text, x + plot.width / 6 - 10, 48, plot.width / 3 - 28); });
    payload.tubes.forEach((tube, index) => { const x = 10 + index * Math.max(36, (plot.width - 20) / Math.max(1, payload.tubes.length)); plot.context.strokeStyle = tube.state === "ready" ? "#a1e7cc" : "#f3c577"; plot.context.strokeRect(x, 90, 28, 55); plot.context.fillStyle = "#e9eee8"; plot.context.fillText(String(tube.tube), x + 14, 122); });
    $("weapons-system-text").textContent = t("weapons_equivalent", {state: payload.readiness.state, interlock: payload.readiness.interlock, tubes: payload.tubes.map((tube) => `${tube.tube}:${tube.state}/${number(tube.reload_s, 0)}s`).join(", ") || t("station_none"), nixies: number(payload.inventory.nixies, 0), active: payload.active_assets.length});
  }

  function visualStationDown(role) {
    const payload = v2State?.[role];
    return role === "sonar" ? payload.settings.station_down : role === "weapons" ? payload.readiness.station_down :
      role === "opz" ? !payload.radar.live : role === "radio" ? payload.station_down :
      role === "engine" ? payload.machinery.station_state === "ZERSTOERT" : role === "eloka" ? payload.station_down : false;
  }

  function drawRoleVisuals() {
    const role = v2State?.role;
    if (!role || $("role-visuals").hidden) return;
    if (mapRoles.has(role)) drawRoleMap(role);
    if (role === "sonar") drawSonarVisuals();
    if (role === "damage") drawDamageVisual();
    if (role === "engine") drawEngineVisual();
    if (role === "eloka") drawElokaVisual();
    if (role === "weapons") drawWeaponsVisual();
  }

  function queueVisualDraw() {
    if (visualDrawQueued) return;
    visualDrawQueued = true;
    requestAnimationFrame(() => { visualDrawQueued = false; drawRoleVisuals(); });
  }

  function renderRoleVisuals(role) {
    $("role-visuals").hidden = !role;
    for (const [id, active] of [["map-visual", mapRoles.has(role)], ["sonar-visual", role === "sonar"],
      ["damage-visual", role === "damage"], ["engine-visual", role === "engine"],
      ["eloka-visual", role === "eloka"], ["weapons-visual", role === "weapons"]]) $(id).hidden = !active;
    if (!role) { clearVisuals(); return; }
    const stateKey = !connected ? "visual_stale" : v2State.phase !== "live" ? (v2State.phase === "paused" ? "visual_paused" : "visual_inactive") : visualStationDown(role) ? "visual_station_down" : "visual_live";
    $("role-visual-state").textContent = t(stateKey);
    for (const button of $("sonar-page-tabs").querySelectorAll("button")) {
      const selectedPage = button.dataset.sonarVisual === sonarVisualPage;
      button.setAttribute("aria-selected", String(selectedPage)); button.tabIndex = selectedPage ? 0 : -1;
    }
    for (const panel of document.querySelectorAll("[data-sonar-plot]")) panel.hidden = panel.dataset.sonarPlot !== sonarVisualPage;
    queueVisualDraw();
    syncOpzSweepAnimation();
  }

  function renderStationView() {
    const active = protocolMode === "v2" && v2State?.role;
    document.body.classList.toggle("workstation-mode", Boolean(active));
    $("workstation-tools").hidden = !active;
    $("workstation-station-label").hidden = !active;
    for (const name of ["lookout", "guide", "contacts"]) $(`tab-${name}`).hidden = Boolean(active);
    $("tab-operations").textContent = active ? t(`station_${active}`) : t("tab_operations");
    $("workstation-lookout").hidden = active !== "bridge";
    $("workstation-guide").hidden = !active;
    $("panel-guide").querySelector(".guide-layout").hidden = Boolean(active);
    if (active) {
      $("workstation-guide-title").textContent = t(`station_${active}`);
      $("workstation-guide-body").textContent = t(`workstation_help_${active}`);
    }
    if (active) {
      const section = $(`station-${active}`), grid = section.querySelector(".station-grid");
      if ($("role-visuals").parentElement !== section) section.insertBefore($("role-visuals"), grid);
      if (active === "bridge" && $("bridge-orders").parentElement !== grid) grid.prepend($("bridge-orders"));
      if (active === "opz" && $("opz-controls").parentElement !== grid) grid.prepend($("opz-controls"));
      if (active === "helicopter" && $("helicopter-dipping-controls").parentElement !== grid) {
        grid.prepend($("helicopter-dipping-controls"));
        $("helicopter-dipping-controls").hidden = false;
      }
      if (["sonar", "opz"].includes(active) && $("operations-workspace").parentElement !== grid) grid.prepend($("operations-workspace"));
      const controls = grid.querySelector(":scope > .station-controls");
      if (controls && grid.firstElementChild !== controls) grid.prepend(controls);
      const fire = grid.querySelector(":scope > .direct-fire-controls");
      if (active === "weapons" && fire && grid.firstElementChild !== fire) grid.prepend(fire);
    } else {
      // Return shared nodes to their v1/lobby homes before hiding role panels.
      if ($("role-visuals").parentElement !== $("station-view")) $("station-view").append($("role-visuals"));
      if ($("operations-workspace").parentElement !== $("legacy-support").parentElement)
        $("legacy-support").before($("bridge-orders"), $("opz-controls"), $("operations-workspace"));
      $("helicopter-dipping-controls").hidden = true;
    }
    $("station-view").hidden = !active;
    for (const section of document.querySelectorAll("[data-station-role]")) {
      section.hidden = section.dataset.stationRole !== active;
      if (section.hidden) for (const container of section.querySelectorAll("dl, .station-list")) container.replaceChildren();
    }
    $("operations-workspace").hidden = Boolean(active) && !["sonar", "opz"].includes(active);
    $("legacy-support").hidden = Boolean(active);
    for (const element of document.querySelectorAll(".v2-irrelevant")) element.hidden = Boolean(active);
    renderRoleVisuals(active);
    if (!active) return;
    const signature = `${language}:${active}:${JSON.stringify(v2State[active])}`;
    if (signature === stationRenderSignature) return;
    stationRenderSignature = signature;
    const renderers = {bridge: renderBridgeStation, sonar: renderSonarStation, weapons: renderWeaponsStation,
      damage: renderDamageStation, opz: renderOpzStation, radio: renderRadioStation, engine: renderEngineStation,
      helicopter: renderHelicopterStation, eloka: renderElokaStation};
    renderers[active](v2State[active]);
    queueVisualDraw();
  }

  function clearRoleState() {
    stopSonarAudio();
    document.body.classList.remove("workstation-mode");
    $("station-view").append($("role-visuals"));
    $("legacy-support").before($("bridge-orders"), $("opz-controls"), $("operations-workspace"));
    $("workstation-tools").hidden = true;
    $("workstation-station-label").hidden = true;
    for (const name of tabNames) $(`tab-${name}`).hidden = false;
    snapshot = null;
    chart = null;
    chartSession = null;
    chartEpoch = null;
    chartRole = null;
    selected = null;
    pending = null;
    v2State = null;
    stationDrafts.clear();
    clearFireDrafts();
    stationRenderSignature = null;
    sonarVisualPage = "broadband";
    clearVisuals();
    for (const state of Object.values(roleMapViews)) { state.initialized = false; state.follow = false; }
    $("role-visuals").hidden = true;
    commandMessage = null;
    opzMarked.clear();
    opzSuppressed.clear();
    opzManage = false;
    $("opz-manage").checked = false;
    latestSimlogState = null;
    lastSimlogFetch = 0;
    view.initialized = false;
    view.follow = false;
    lookoutView.rangeNm = 100;
    activeTab = "operations";
    eventHistory = [];
    seenEvents.clear();
    eventHighWater = -1;
    suppressNextEvents = true;
    $("navigation-form").reset();
    $("bridge-course-form").reset();
    $("bridge-speed-form").reset();
    for (const id of ["sonar-bearing-form", "sonar-depth-form", "sonar-gain-form", "sonar-harmonic-form",
      "engine-speed-form", "helicopter-waypoint-form", "helicopter-dip-depth-form"]) $(id).reset();
    $("sonar-control-page").value = "listen";
    renderSonarControlPage();
    $("navigation-status").textContent = "";
    $("track-list").replaceChildren();
    $("station-view").hidden = true;
    $("operations-workspace").hidden = false;
    $("legacy-support").hidden = false;
    for (const section of document.querySelectorAll("[data-station-role]")) {
      section.hidden = true;
      for (const container of section.querySelectorAll("dl, .station-list")) container.replaceChildren();
    }
    $("track-detail").hidden = true;
    for (const id of ["detail-label", "detail-badges", "detail-metrics", "mission-name", "objective",
      "mission-metrics", "own-metrics", "inventory", "helo-metrics", "damage-list", "event-list",
      "chart-disclaimer", "proposal-status", "command-status", "snapshot-meta", "lookout-sea",
      "lookout-light", "lookout-own", "lookout-observations", "bridge-order-values",
      "bridge-order-status", "opz-mark-status", "sonar-release-status", "station-command-status"]) $(id).replaceChildren();
    $("simlog-list").replaceChildren();
    $("simlog-current").replaceChildren();
    closeSimlogMap();
    releaseCanvas(canvas);
    releaseCanvas(lookoutCanvas);
    activateTab("operations", false);
  }

  function renderLobby() {
    if (protocolMode !== "v2" || !session) return;
    const assigned = session.station !== null;
    $("pairing").hidden = true;
    $("lobby").hidden = assigned && !stationPickerOpen;
    $("lobby-back").hidden = !assigned;
    $("role-rail").hidden = !assigned || stationPickerOpen;
    $("mobile-role").hidden = !assigned || stationPickerOpen;
    const rolePublished = protocolMode !== "v2" || v2State?.role === session.station;
    $("operations").hidden = !assigned || stationPickerOpen || !rolePublished || simlogActive();
    $("simlog-view").hidden = !assigned || stationPickerOpen || !simlogActive();
    document.body.dataset.remoteRole = assigned ? "assigned" : "lobby";
    const requested = session.requested_station;
    $("lobby-status").textContent = lobbyMessage ? t(lobbyMessage) : requested ?
      t("lobby_pending", { station: t(`station_${requested}`) }) : t("lobby_waiting");
    if ($("station-cards").children.length !== stationNames.length ||
        stationNames.some((station, index) => $("station-cards").children[index]?.dataset.station !== station)) {
      $("station-cards").replaceChildren(...stationNames.map((station) => {
        const card = node("section");
        card.dataset.station = station;
        const button = node("button");
        button.type = "button";
        button.dataset.station = station;
        button.addEventListener("click", () => requestStation(station));
        card.append(node("h2"), node("p", undefined, "station-occupancy"), button);
        return card;
      }));
    }
    stationNames.forEach((station, index) => {
      const record = session.stations[station];
      const state = record.status;
      const card = $("station-cards").children[index];
      const [heading, occupancy, button] = card.children;
      card.className = `station-card station-${state}`;
      heading.textContent = t(`station_${station}`);
      occupancy.textContent = t(`occupancy_${state}`);
      button.textContent = record.requested ? t("station_requested") : t("station_request");
      button.disabled = stationMutation || requested !== null || state !== "available";
    });
    if (!assigned) return;
    const role = t(`station_${session.station}`);
    $("role-rail-title").textContent = role;
    $("role-grants").textContent = t(session.grants.command ? "role_commands" : "role_read_only");
    $("role-status").textContent = lobbyMessage ? t(lobbyMessage) : requested ?
      t("lobby_pending", { station: t(`station_${requested}`) }) : "";
    $("release-station").disabled = stationMutation;
    $("mobile-release-station").disabled = stationMutation;
    for (const id of ["add-station", "mobile-add-station", "workstation-add-station"]) {
      $(id).disabled = stationMutation || requested !== null;
    }
    for (const id of ["mobile-station", "workstation-station"]) {
      const select = $(id);
      select.replaceChildren(...stationNames.filter(
        (station) => session.stations[station].status === "mine").map((station) => {
        const option = node("option", t(`station_${station}`));
        option.value = station;
        option.selected = station === session.station;
        return option;
      }));
      select.disabled = stationMutation;
    }
  }

  function acceptSession(next) {
    validateSession(next);
    const previous = session;
    const changed = previous && (previous.station !== next.station ||
      previous.station_generation !== next.station_generation ||
      previous.active_generation !== next.active_generation);
    const lostRole = previous?.station !== null && next.station === null;
    if (changed) clearRoleState();
    if (previous?.requested_station &&
        next.stations[previous.requested_station]?.status === "mine") stationPickerOpen = false;
    session = next;
    if (sonarAudioEnabled && !sonarAudioAuthorized()) stopSonarAudio("sonar_live_unavailable");
    nextCommandSeq = next.next_command_seq;
    lastSessionFetch = performance.now();
    if (lostRole) lobbyMessage = "role_revoked";
    else if (next.station !== null) lobbyMessage = null;
    else if (previous?.requested_station && next.requested_station === null) lobbyMessage = "lobby_request_cleared";
    renderLobby();
    renderSonarAudio();
  }

  async function mutateStation(path, body) {
    if (protocolMode !== "v2" || !session || stationMutation) return;
    stationMutation = true;
    lobbyMessage = null;
    renderLobby();
    const context = generation;
    const csrf = session.csrf;
    try {
      const result = await request(path, { method: "POST", body, csrf, guard: () => context === generation });
      if (context !== generation) return;
      acceptSession(result);
    } catch (error) {
      if (context !== generation || error.message === "cancelled") return;
      if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
      else if (error.status === 409) {
        try { acceptSession(await request("/session")); } catch (_) { setConnection("stale"); }
      } else {
        lobbyMessage = "station_mutation_failed";
        setConnection("stale");
      }
    } finally {
      if (context === generation) {
        stationMutation = false;
        renderLobby();
      }
    }
  }

  function requestStation(station) {
    if (!stationNames.includes(station) ||
        session?.stations[station]?.status !== "available" ||
        session.requested_station !== null) return;
    mutateStation("/stations/request", { station });
  }

  function chooseStation(station) {
    const record = session?.stations?.[station];
    if (!record || stationMutation || station === session.station) return;
    if (record.status === "mine") mutateStation("/stations/activate", {
      station, station_generation: record.station_generation,
      active_generation: session.active_generation,
    });
  }

  function activateTab(name, focus = true) {
    if (!tabNames.includes(name)) return;
    activeTab = name;
    for (const candidate of tabNames) {
      const selectedTab = candidate === name;
      const tab = $(`tab-${candidate}`);
      tab.setAttribute("aria-selected", String(selectedTab));
      tab.tabIndex = selectedTab ? 0 : -1;
      $(`panel-${candidate}`).hidden = !selectedTab;
    }
    if (name !== "operations") releaseCanvas(canvas);
    if (name !== "lookout") {
      releaseCanvas(lookoutCanvas);
      $("lookout-observations").replaceChildren();
    }
    if (focus) (protocolMode === "v2" && name !== "operations" ? $(`panel-${name}`) : $(`tab-${name}`)).focus();
    if (name === "operations") { queueDraw(); queueVisualDraw(); }
    if (name === "lookout") { renderLookoutStatus(); queueLookoutDraw(); }
    if (name === "contacts") renderContactAnalysis();
    syncOpzSweepAnimation();
  }

  function validateContactAnalysis(data) {
    const scalar = (value) => value === null || typeof value === "string" || typeof value === "boolean" || finite(value);
    const record = (value, fields) => value && typeof value === "object" && !Array.isArray(value) &&
      Object.keys(value).sort().join(",") === [...fields].sort().join(",");
    const textList = (value) => Array.isArray(value) && value.length <= 128 &&
      value.every((item) => typeof item === "string" && item.length <= 128);
    const numberList = (value) => value === null || (Array.isArray(value) && value.length <= 128 && value.every(finite));
    const boundedObject = (value, depth = 0) => {
      if (depth > 5) return false;
      if (scalar(value)) return typeof value !== "string" || value.length <= 512;
      if (Array.isArray(value)) return value.length <= 128 && value.every((item) => boundedObject(item, depth + 1));
      return value && typeof value === "object" && Object.keys(value).length <= 32 &&
        Object.entries(value).every(([key, item]) => key.length <= 64 && boundedObject(item, depth + 1));
    };
    if (!data || typeof data !== "object" || Array.isArray(data) ||
        Object.keys(data).sort().join(",") !== "profiles,version" || data.version !== 1 ||
        !Array.isArray(data.profiles) || data.profiles.length > 4096) throw new Error("analysis_schema");
    const keys = new Set();
    for (const profile of data.profiles) {
      const referenceFields = ["variant", "variant_year", "refit_year", "aliases", "roles", "hull_type", "displacement_tonnes", "displacement_basis", "length_m", "beam_waterline_m", "beam_overall_m", "flight_deck_width_m", "draft_m", "ship_crew", "air_group_crew"];
      const machineFields = ["cruise_speed_kn", "maximum_speed_kn", "quiet_speed_kn", "propulsion_codes", "motor_rpm", "shaft_rpm", "propulsor_type", "blade_count", "cruise_lines", "high_speed_lines", "cruise_broadband", "high_speed_broadband"];
      if (!profile || typeof profile !== "object" || Array.isArray(profile) ||
          Object.keys(profile).sort().join(",") !== "assets,components,key,machine,name,reference,resource" ||
          typeof profile.key !== "string" || !/^[a-z0-9][a-z0-9_.-]{0,95}$/.test(profile.key) || keys.has(profile.key) ||
          typeof profile.name !== "string" || !profile.name || profile.name.length > 256 ||
          typeof profile.resource !== "string" || !["subs.json", "warships.json", "civilians.json", "aircraft.json", "animals.json", "torpedoes.json", "decoys.json"].includes(profile.resource) ||
          !profile.assets || typeof profile.assets !== "object" || Array.isArray(profile.assets) ||
          Object.keys(profile.assets).some((kind) => !["acoustic_cruise", "acoustic_high"].includes(kind)) ||
          Object.entries(profile.assets).some(([kind, route]) => {
            const suffix = { acoustic_cruise: "cruise", acoustic_high: "high" }[kind];
            return typeof route !== "string" || route !== `/contact-analysis/${profile.key}-${suffix}.png`;
          }) ||
          !profile.components || typeof profile.components !== "object" || Array.isArray(profile.components) ||
          Object.keys(profile.components).sort().join(",") !== "countermeasures,emitters,launchers,magazines,sensors,weapons" ||
          Object.values(profile.components).some((items) => !Array.isArray(items) || items.length > 128 || items.some((item) => !boundedObject(item))) ||
          !record(profile.reference, referenceFields) || !record(profile.machine, machineFields) ||
          typeof profile.reference.variant !== "string" || profile.reference.variant.length > 256 ||
          !textList(profile.reference.aliases) || !textList(profile.reference.roles) ||
          !referenceFields.slice(1).every((field) => ["aliases", "roles", "ship_crew", "air_group_crew"].includes(field) || scalar(profile.reference[field])) ||
          !numberList(profile.reference.ship_crew) || !numberList(profile.reference.air_group_crew) ||
          !textList(profile.machine.propulsion_codes) || !numberList(profile.machine.motor_rpm) || !numberList(profile.machine.shaft_rpm) ||
          !["cruise_lines", "high_speed_lines"].every((field) => Array.isArray(profile.machine[field]) && profile.machine[field].length <= 128 && profile.machine[field].every((line) => Array.isArray(line) && line.length === 3 && line.every(finite))) ||
          !["cruise_broadband", "high_speed_broadband"].every((field) => profile.machine[field] === null || (Array.isArray(profile.machine[field]) && profile.machine[field].length === 3 && profile.machine[field].every(finite))) ||
          !machineFields.filter((field) => !["propulsion_codes", "motor_rpm", "shaft_rpm", "cruise_lines", "high_speed_lines", "cruise_broadband", "high_speed_broadband"].includes(field)).every((field) => scalar(profile.machine[field])) ||
          !boundedObject(profile.components)) throw new Error("analysis_schema");
      keys.add(profile.key);
    }
  }

  async function loadContactAnalysis() {
    try {
      const data = await request("/contacts", { auth: false });
      validateContactAnalysis(data);
      contactAnalysis = data;
      analysisError = false;
    } catch (_) {
      contactAnalysis = null;
      analysisError = true;
    }
    renderContactAnalysis();
  }

  function analysisProfile() {
    return contactAnalysis?.profiles.find((profile) => profile.key === analysisSelected) || null;
  }

  function renderContactAnalysis() {
    const status = $("analysis-status");
    const detail = $("analysis-profile");
    const list = $("analysis-list");
    if (!contactAnalysis) {
      analysisImageKey = null;
      list.replaceChildren();
      detail.hidden = true;
      status.hidden = false;
      status.textContent = t(analysisError ? "analyzer_error" : "analyzer_loading");
      $("analysis-count").textContent = "";
      return;
    }
    const term = $("analysis-filter").value.trim().toLocaleLowerCase(language).slice(0, 96);
    const category = $("analysis-category").value;
    const visible = contactAnalysis.profiles.filter((profile) => (!category || profile.resource === category) &&
      (!term || `${profile.name} ${profile.key} ${profile.reference.variant || ""} ${(profile.reference.aliases || []).join(" ")} ${(profile.reference.roles || []).join(" ")}`.toLocaleLowerCase(language).includes(term)));
    list.replaceChildren(...visible.map((profile) => {
      const button = node("button", undefined, "analysis-item");
      button.type = "button";
      button.dataset.key = profile.key;
      button.setAttribute("aria-pressed", String(profile.key === analysisSelected));
      button.append(node("span", profile.name), node("small", `${profile.key} / ${t(`analyzer_${profile.resource.slice(0, -5)}`)}`));
      button.addEventListener("click", () => { analysisSelected = profile.key; renderContactAnalysis(); });
      return button;
    }));
    if (!visible.length) list.append(node("p", t("analyzer_no_results"), "empty"));
    $("analysis-count").textContent = t("analyzer_count", { count: number(visible.length, 0), total: number(contactAnalysis.profiles.length, 0) });
    const profile = analysisProfile();
    status.hidden = Boolean(profile);
    detail.hidden = !profile;
    if (!profile) { status.textContent = t("analyzer_select"); return; }
    $("analysis-key").textContent = profile.key;
    $("analysis-name").textContent = profile.name;
    $("analysis-resource").textContent = t(`analyzer_${profile.resource.slice(0, -5)}`);
    const reference = profile.reference;
    const machine = profile.machine;
    const joined = (items) => Array.isArray(items) && items.length ? items.join(", ") : t("unavailable");
    metrics($("analysis-metrics"), [
      ["analyzer_variant", reference.variant || t("unavailable")],
      ["analyzer_roles", joined(reference.roles)],
      ["analyzer_hull", reference.hull_type || t("unavailable")],
      ["analyzer_length", unit(reference.length_m, "m")],
      ["analyzer_beam", unit(reference.beam_overall_m ?? reference.beam_waterline_m, "m")],
      ["analyzer_draft", unit(reference.draft_m, "m")],
      ["analyzer_displacement", unit(reference.displacement_tonnes, "t", 0)],
      ["analyzer_speed_band", `${unit(machine.cruise_speed_kn, "kn")} / ${unit(machine.maximum_speed_kn, "kn")}`],
      ["analyzer_propulsion", joined(machine.propulsion_codes)],
      ["analyzer_propulsor", machine.propulsor_type || t("unavailable")],
    ]);
    metrics($("analysis-systems"), Object.entries(profile.components).map(([kind, items]) =>
      [`analyzer_${kind}`, number(items.length, 0)]));
    const componentRows = (element, rows, titleKey, fields) => {
      element.replaceChildren(...rows.map((row, index) => {
        const article = node("article", undefined, "analysis-component");
        article.append(node("h4", t(titleKey, {number: index + 1})));
        const list = node("dl", undefined, "detail-metrics");
        for (const [field, value] of fields(row)) {
          const group = node("div");
          const labels = {domain: "domain", frequency_band_hz: "frequency", prf_band_hz: "prf",
            synthetic_range_nm: "range", bearing_uncertainty_deg: "bearing_uncertainty",
            range_uncertainty_nm: "range_uncertainty", modulation_codes: "modulation",
            modes: "analyzer_modes", emits: "analyzer_emits", sensitivity_db: "analyzer_sensitivity",
            cadence_s: "analyzer_cadence", depth_uncertainty_m: "analyzer_depth_uncertainty"};
          group.append(node("dt", t(labels[field]) || field), node("dd", value));
          list.append(group);
        }
        article.append(list);
        return article;
      }));
    };
    const band = (values, symbol) => Array.isArray(values) ? values.map((value) => unit(value, symbol, 0)).join(" - ") : t("unavailable");
    componentRows($("analysis-sensors"), profile.components.sensors,
      "analyzer_sensor_title", (sensor) => [
      ["domain", sensor.domain], ["modes", joined(sensor.modes)], ["emits", yesNo(sensor.emits)],
      ["synthetic_range_nm", unit(sensor.synthetic_range_nm, "NM")], ["sensitivity_db", unit(sensor.sensitivity_db, "dB")],
      ["cadence_s", unit(sensor.cadence_s, "s")], ["bearing_uncertainty_deg", unit(sensor.bearing_uncertainty_deg, "\u00b0")],
      ["range_uncertainty_nm", unit(sensor.range_uncertainty_nm, "NM")], ["depth_uncertainty_m", unit(sensor.depth_uncertainty_m, "m")],
    ]);
    componentRows($("analysis-emitters"), profile.components.emitters,
      "analyzer_emitter_title", (emitter) => [
      ["domain", emitter.domain], ["frequency_band_hz", band(emitter.frequency_band_hz, "Hz")],
      ["prf_band_hz", band(emitter.prf_band_hz, "Hz")], ["modulation_codes", joined(emitter.modulation_codes)],
    ]);
    const imageLabels = { acoustic_cruise: "analyzer_acoustic_cruise", acoustic_high: "analyzer_acoustic_high" };
    const imageKey = `${language}:${profile.key}`;
    if (analysisImageKey !== imageKey) {
      $("analysis-images").replaceChildren(...Object.entries(profile.assets).map(([kind, route]) => {
        const figure = node("figure", undefined, "analysis-image");
        const image = node("img");
        const cruise = kind === "acoustic_cruise";
        const lines = cruise ? machine.cruise_lines : machine.high_speed_lines;
        const broadband = cruise ? machine.cruise_broadband : machine.high_speed_broadband;
        const descriptions = [t("analyzer_image_alt_base", { speed: t(imageLabels[kind]) })];
        if (Array.isArray(lines) && lines.length) descriptions.push(t("analyzer_image_alt_tonals"));
        if (Array.isArray(broadband)) descriptions.push(t("analyzer_image_alt_broadband"));
        if (cruise && Array.isArray(machine.shaft_rpm)) {
          descriptions.push(t(machine.blade_count == null ? "analyzer_image_alt_shaft" : "analyzer_image_alt_shaft_bpf"));
        } else if (!Array.isArray(machine.shaft_rpm)) {
          descriptions.push(t("analyzer_image_alt_no_hypothesis"));
        } else {
          descriptions.push(t("analyzer_image_alt_not_repeated"));
        }
        image.src = route;
        image.alt = descriptions.join(" ");
        image.loading = "lazy";
        image.decoding = "async";
        figure.append(image, node("figcaption", t(imageLabels[kind])));
        return figure;
      }));
      analysisImageKey = imageKey;
    }
  }

  // All requests, including commands and language changes, share one lane. The
  // deadline covers JSON consumption as well as headers, including stalled bodies.
  function request(path, { method = "GET", body, auth = true, expected = 200, guard, version, csrf } = {}) {
    const requestVersion = version || (auth && protocolMode === "v2" ? 2 : 1);
    const credential = auth && protocolMode === "v1" ? token : null;
    const cookieSession = auth && protocolMode === "v2" ? session : null;
    const requestGeneration = generation;
    const run = async () => {
      if (auth && ((!credential && !cookieSession) || requestGeneration !== generation)) throw new Error("cancelled");
      if (guard && !guard()) throw new Error("cancelled");
      const controller = new AbortController();
      activeRequest = controller;
      const timeout = setTimeout(() => controller.abort(), 4000);
      let response;
      try {
        const headers = { Accept: "application/json" };
        if (credential) headers.Authorization = `Bearer ${credential}`;
        if (csrf) headers["X-U-Jagd-CSRF"] = csrf;
        if (body !== undefined) headers["Content-Type"] = "application/json";
        response = await fetch(`/api/v${requestVersion}${path}`, {
          method, headers, body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal, cache: "no-store", credentials: "same-origin", redirect: "error", mode: "same-origin",
        });
        if (response.status !== expected) {
          const error = new Error("http");
          error.status = response.status;
          throw error;
        }
        // A queued command acknowledgement need not contain a JSON body.
        if (expected === 202) { await response.text(); return null; }
        return await response.json();
      } catch (error) {
        if (response) error.endpointAvailable = true;
        throw error;
      } finally {
        clearTimeout(timeout);
        if (activeRequest === controller) activeRequest = null;
      }
    };
    const result = requestQueue.then(run, run);
    requestQueue = result.catch(() => {});
    return result;
  }

  async function loadLanguage(nextLanguage) {
    const serial = ++languageRequest;
    $("language").disabled = true;
    try {
      const translations = await request(`/ui?lang=${nextLanguage}`, { auth: false });
      if (serial !== languageRequest) return false;
      if (!translations || typeof translations[prefix + "pair_title"] !== "string" ||
          Object.entries(translations).some(([key, value]) => !key.startsWith(prefix) || typeof value !== "string")) throw new Error("catalog");
      catalog = translations;
      language = nextLanguage;
      document.documentElement.lang = language;
      $("language").value = language;
      for (const element of document.querySelectorAll("[data-i18n]")) element.textContent = t(element.dataset.i18n);
      for (const element of document.querySelectorAll("[data-i18n-aria]")) element.setAttribute("aria-label", t(element.dataset.i18nAria));
      for (const element of document.querySelectorAll("[data-i18n-placeholder]")) element.placeholder = t(element.dataset.i18nPlaceholder);
      if (!$("name").value) $("name").value = t("pair_name_default").slice(0, 32);
      $("bootstrap").hidden = true;
      $("shell").hidden = false;
      renderConnection();
      renderSound();
      if (snapshot && chartMatches(snapshot)) renderSnapshot();
      renderContactAnalysis();
      renderLobby();
      return true;
    } catch (_) {
      $("language").value = language;
      if (Object.keys(catalog).length) $("connection").textContent = t("language_failed");
      return false;
    } finally {
      if (serial === languageRequest) $("language").disabled = false;
    }
  }

  function renderConnection() {
    $("connection").dataset.state = linkState;
    const age = lastSuccess ? Math.max(0, Math.floor((performance.now() - lastSuccess) / 1000)) : 0;
    $("connection").textContent = t(linkState === "stale" ? "connection_stale" : `connection_${linkState}`, { age });
  }

  function setConnection(state) {
    linkState = state;
    connected = state === "connected";
    renderConnection();
    renderActionState();
    if (v2State?.role) renderRoleVisuals(v2State.role);
    if (sonarAudioEnabled && !sonarAudioAuthorized()) stopSonarAudio("sonar_live_unavailable");
  }

  function forgetSession(message = "connection_unpaired") {
    stopSonarAudio();
    generation += 1;
    token = null;
    session = null;
    stationPickerOpen = false;
    lastSessionFetch = 0;
    activeRequest?.abort();
    clearTimeout(pollTimer);
    clearRoleState();
    snapshot = null;
    chart = null;
    chartSession = null;
    chartEpoch = null;
    chartRole = null;
    selected = null;
    pending = null;
    commandMessage = null;
    view.initialized = false;
    lookoutView.rangeNm = 100;
    eventHistory = [];
    seenEvents.clear();
    eventHighWater = -1;
    suppressNextEvents = true;
    failures = 0;
    lastSuccess = 0;
    $("operations").hidden = true;
    $("lobby").hidden = true;
    $("role-rail").hidden = true;
    $("mobile-role").hidden = true;
    $("simlog-view").hidden = true;
    $("simlog-list").replaceChildren();
    $("simlog-current").replaceChildren();
    $("simlog-count").textContent = "";
    latestSimlogState = null;
    $("simlog-current-map").disabled = true;
    closeSimlogMap();
    $("pairing").hidden = false;
    $("disconnect").hidden = true;
    $("pair-error").textContent = "";
    $("code").value = "";
    $("navigation-form").reset();
    $("navigation-status").textContent = "";
    document.body.dataset.remoteRole = "";
    lobbyMessage = null;
    stationMutation = false;
    activateTab("operations", false);
    for (const id of ["track-list", "detail-label", "detail-badges", "detail-metrics", "mission-name", "objective", "mission-metrics", "own-metrics", "inventory", "helo-metrics", "damage-list", "event-list", "chart-disclaimer", "proposal-status", "command-status", "snapshot-meta", "lookout-sea", "lookout-light", "lookout-own", "lookout-observations"]) $(id).replaceChildren();
    $("lookout-scope").dataset.light = "unknown";
    releaseCanvas(canvas);
    releaseCanvas(lookoutCanvas);
    setConnection("unpaired");
    $("connection").textContent = t(message);
  }

  function validateSession(value) {
    const fields = ["active_generation", "active_station", "client_id", "csrf", "grants", "name", "next_command_seq", "ordinal", "presence", "protocol", "requested_station", "simlog", "station", "station_generation", "stations"];
    if (!value || typeof value !== "object" || Array.isArray(value) ||
        Object.keys(value).sort().join(",") !== fields.sort().join(",") || value.protocol !== 2 ||
        typeof value.client_id !== "string" || !value.client_id || value.client_id.length > 128 ||
        typeof value.name !== "string" || value.name.length < 1 || value.name.length > 32 ||
        typeof value.csrf !== "string" || !value.csrf || value.csrf.length > 256 ||
         !Number.isSafeInteger(value.ordinal) || value.ordinal < 0 ||
        !Number.isSafeInteger(value.active_generation) || value.active_generation < 0 ||
        !Number.isSafeInteger(value.station_generation) || value.station_generation < 0 ||
        !Number.isSafeInteger(value.next_command_seq) || value.next_command_seq < 0 ||
        !finite(value.presence) || value.presence < 0 ||
        (value.station !== null && !stationNames.includes(value.station)) ||
        (value.requested_station !== null && !stationNames.includes(value.requested_station)) ||
        !value.grants || typeof value.grants !== "object" || Array.isArray(value.grants) ||
        Object.keys(value.grants).sort().join(",") !== "command,direct_fire,simlog,sonar_audio" ||
        Object.values(value.grants).some((grant) => typeof grant !== "boolean") ||
        (value.grants.command && value.station === null) ||
        (value.grants.direct_fire && (!value.grants.command || !["weapons", "helicopter", "opz"].includes(value.station))) ||
        (value.grants.sonar_audio && value.station !== "sonar") ||
        typeof value.simlog !== "boolean" || value.grants.simlog !== value.simlog ||
        value.active_station !== value.station ||
        !value.stations || typeof value.stations !== "object" || Array.isArray(value.stations) ||
        Object.keys(value.stations).join(",") !== stationNames.join(",")) throw new Error("session");
    for (const station of stationNames) {
      const record = value.stations[station];
      if (!exactKeys(record, ["status", "requested", "request_generation", "station_generation", "grants"]) ||
          !["available", "occupied", "mine"].includes(record.status) ||
          typeof record.requested !== "boolean" ||
          !Number.isSafeInteger(record.request_generation) || record.request_generation < 0 ||
          (record.station_generation !== null && (!Number.isSafeInteger(record.station_generation) || record.station_generation < 0)) ||
          !exactKeys(record.grants, ["command", "direct_fire", "sonar_audio"]) ||
          Object.values(record.grants).some((grant) => typeof grant !== "boolean") ||
          (record.status === "mine") !== (record.station_generation !== null) ||
          record.grants.direct_fire && (!record.grants.command || !["weapons", "helicopter", "opz"].includes(station)) ||
          record.grants.sonar_audio && station !== "sonar") throw new Error("session");
    }
    const mine = stationNames.filter((station) => value.stations[station].status === "mine");
    if ((value.station === null) !== (mine.length === 0) ||
        value.station !== null && !mine.includes(value.station) ||
        value.requested_station !== null && !value.stations[value.requested_station].requested ||
        value.station !== null && (value.station_generation !== value.stations[value.station].station_generation ||
          value.grants.command !== value.stations[value.station].grants.command ||
          value.grants.direct_fire !== value.stations[value.station].grants.direct_fire ||
          value.grants.sonar_audio !== value.stations[value.station].grants.sonar_audio)) throw new Error("session");
  }

  async function detectSession() {
    try {
      const resumed = await request("/session", { auth: false, version: 2 });
      validateSession(resumed);
      protocolMode = "v2";
      acceptSession(resumed);
      return true;
    } catch (error) {
      if (error.status === 401) {
        protocolMode = "v2";
        return false;
      }
      protocolMode = [404, 503].includes(error.status) ? "v1" : "v2";
      return false;
    }
  }

  const exactKeys = (value, keys) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).sort().join(",") === [...keys].sort().join(",");
  const boundedArray = (value, maximum) => Array.isArray(value) && value.length <= maximum;
  function v2Observation(row, fields) {
    if (!exactKeys(row, fields) || typeof row.ref !== "string" || !row.ref || row.ref.length > 64) throw new Error("protocol");
  }
  function validateV2State(state) {
    const status = ["protocol", "version", "session", "epoch", "revision", "seq", "phase", "role", "chart_revision"];
    if (!state || state.protocol !== 2 || typeof state.version !== "string" ||
        typeof state.session !== "string" || !state.session || state.session.length > 64 ||
        ![state.epoch, state.revision, state.seq].every((value) => Number.isSafeInteger(value) && value >= 0) ||
        state.chart_revision !== state.session) throw new Error("protocol");
    if (state.role === null) {
      if (!exactKeys(state, status)) throw new Error("protocol");
      return;
    }
    const common = [...status, "clock", "environment", "mission"];
    if (!stationNames.includes(state.role) || state.role !== session?.station ||
        !exactKeys(state, [...common, state.role]) || !exactKeys(state.clock, ["sim", "mission", "time_scale", "world"]) ||
        !exactKeys(state.environment, ["sea_state", "is_night"]) ||
        !exactKeys(state.mission, ["name", "objective", "remaining_s"])) throw new Error("protocol");
    const payload = state[state.role];
    const shapes = {
      bridge: ["navigation", "orders", "threat", "systems", "tactical_summary"], sonar: ["observations", "settings", "visualization"],
      weapons: ["inventory", "readiness", "designated_target", "navigation", "tactical", "target_choices", "depth_m", "tubes", "own_weapons", "active_assets"],
      damage: ["compartments", "teams", "total", "sunk"],
      opz: ["observations", "fusions", "radar", "defense", "asm_observations", "source_classifications", "designated_target_ref", "own_assets"],
      radio: ["observations", "logged_fixes", "logged_bearings", "messages", "station_down", "navigation", "tactical"],
      engine: ["propulsion", "machinery", "controls", "environment_effects"],
      helicopter: ["asset", "waypoint", "buoys", "navigation", "tactical", "target_choices", "readiness"], eloka: ["intercepts", "station_down", "status"],
    };
    if (!exactKeys(payload, shapes[state.role])) throw new Error("protocol");
    const rowsExact = (rows, maximum, fields) => {
      if (!boundedArray(rows, maximum)) throw new Error("protocol");
      rows.forEach((row) => v2Observation(row, fields));
    };
    const tacticalFields = ["ref", "label", "domain", "source", "affiliation", "bearing", "range_nm", "x", "y", "course", "speed_kn", "observer_x", "observer_y", "quality", "age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"];
    const tacticalRows = (rows, maximum, extraFields = []) => {
      if (!boundedArray(rows, maximum)) throw new Error("protocol");
      rows.forEach((row) => {
        v2Observation(row, [...tacticalFields, ...extraFields]);
        if (row.speed_kn !== null && !finite(row.speed_kn)) throw new Error("protocol");
      });
    };
    const sonarFields = ["ref", "label", "source", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "observer_x", "observer_y", "released_to_opz", "fixes"];
    if (state.role === "bridge") {
      if (!exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate"])) throw new Error("protocol");
      if (!exactKeys(payload.orders, ["station_down", "speed_max_kn", "telegraph", "noise", "cavitating"]) ||
          typeof payload.orders.station_down !== "boolean" || !finite(payload.orders.speed_max_kn) ||
          typeof payload.orders.cavitating !== "boolean" || payload.orders.speed_max_kn < 0 || payload.orders.speed_max_kn > 100 ||
          !exactKeys(payload.threat, ["observations", "count", "average_flood"]) ||
          !boundedArray(payload.systems, 32) || payload.systems.some((row) => !exactKeys(row, ["key", "state", "down"]) || typeof row.down !== "boolean")) throw new Error("protocol");
      tacticalRows(payload.threat.observations, 128);
      tacticalRows(payload.tactical_summary, 256);
    } else if (state.role === "sonar") {
      rowsExact(payload.observations, 256, sonarFields);
      const settings = payload.settings;
      if (!exactKeys(settings, ["mode", "page", "listen_bearing", "focus_ref", "target_ref", "station_down", "tow", "bt", "ping", "tma_enabled", "gain_db", "band_preset", "band_hz", "notch", "peak_hold", "harmonic_hz", "harmonic_candidates_hz", "audio_enabled", "volume", "quiet_mode"]) ||
          !["BOW", "TOWED"].includes(settings.mode) || typeof settings.station_down !== "boolean" ||
          !exactKeys(settings.tow, ["state", "payout", "available", "handling_ok", "depth_m", "depth_target_m"]) ||
          !exactKeys(settings.bt, ["ready", "cooldown_s", "thermocline_m"]) ||
          !exactKeys(settings.ping, ["ready", "cooldown_s"]) ||
          !boundedArray(settings.band_hz, 2) || settings.band_hz.length !== 2 ||
          !boundedArray(settings.harmonic_candidates_hz, 64) ||
          [settings.tow.available, settings.tow.handling_ok, settings.bt.ready, settings.ping.ready,
            settings.tma_enabled, settings.notch, settings.peak_hold, settings.audio_enabled,
            settings.quiet_mode].some((value) => typeof value !== "boolean")) throw new Error("protocol");
      const visual = payload.visualization;
      if (!exactKeys(visual, ["broadband", "lofar", "demon", "tma", "bt", "active_echoes", "receiver"]) ||
          !exactKeys(visual.broadband, ["bearing_start_deg", "bearing_step_deg", "history"]) ||
          !boundedArray(visual.broadband.history, 80) || visual.broadband.history.some((row) => !exactKeys(row, ["age_s", "bins"]) || !boundedArray(row.bins, 180)) ||
          !exactKeys(visual.lofar, ["frequency_min_hz", "frequency_max_hz", "bin_frequencies_hz", "history", "spectrum", "held"]) ||
          !boundedArray(visual.lofar.bin_frequencies_hz, 256) || !boundedArray(visual.lofar.spectrum, 256) ||
          !boundedArray(visual.lofar.history, 80) || visual.lofar.history.some((row) => !exactKeys(row, ["age_s", "bearing", "bins"]) || !boundedArray(row.bins, 110)) || typeof visual.lofar.held !== "boolean" ||
          !exactKeys(visual.demon, ["frequency_min_hz", "frequency_max_hz", "bin_step_hz", "spectrum", "analysis"]) || !boundedArray(visual.demon.spectrum, 80) ||
          (visual.demon.analysis !== null && (!exactKeys(visual.demon.analysis, ["modulation_peak_hz", "detection_confidence", "cavitation", "tonal_hz", "hypotheses"]) || !boundedArray(visual.demon.analysis.hypotheses, 20) || visual.demon.analysis.hypotheses.some((row) => !exactKeys(row, ["blades", "order", "rpm"])))) ||
          !boundedArray(visual.tma, 32) || visual.tma.some((row) => !exactKeys(row, ["ref", "bearings", "solution"]) || !boundedArray(row.bearings, 24) || row.bearings.some((point) => !exactKeys(point, ["age_s", "bearing", "uncertainty_deg", "own_x", "own_y", "own_course"])) || row.solution !== null && !exactKeys(row.solution, ["x", "y", "course", "speed_kn", "quality", "age_s", "uncertainty_nm"])) ||
          (visual.bt !== null && (!exactKeys(visual.bt, ["age_s", "thermocline_m", "water_depth_m", "sea_state", "depths_m", "speeds_m_s", "cz_bands_nm"]) || !boundedArray(visual.bt.depths_m, 64) || !boundedArray(visual.bt.speeds_m_s, 64) || visual.bt.depths_m.length !== visual.bt.speeds_m_s.length || !boundedArray(visual.bt.cz_bands_nm, 8) || visual.bt.cz_bands_nm.some((band) => !boundedArray(band, 2) || band.length !== 2))) ||
          !boundedArray(visual.active_echoes, 40) || visual.active_echoes.some((row) => !exactKeys(row, ["age_s", "bearing", "range_nm", "depth_m", "range_uncertainty_nm", "depth_uncertainty_m", "snr_db", "array"])) ||
          !exactKeys(visual.receiver, ["array", "listen_bearing", "beam_width_deg", "listen_mode", "focus_locked", "audio_enabled"]) || typeof visual.receiver.focus_locked !== "boolean" || typeof visual.receiver.audio_enabled !== "boolean") throw new Error("protocol");
    } else if (state.role === "weapons") {
      if (!exactKeys(payload.inventory, ["torpedoes", "vls", "ciws", "aa", "chaff_ready", "nixies"]) ||
          !exactKeys(payload.readiness, ["station_down", "roe", "ciws_ready", "aa_ready", "state", "interlock", "reload_s"]) ||
          (payload.designated_target !== null && !exactKeys(payload.designated_target, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"])) ||
          !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate"]) ||
          !boundedArray(payload.tubes, 16) || payload.tubes.some((row) => !exactKeys(row, ["tube", "state", "reload_s"])) ||
          !boundedArray(payload.own_weapons, 96) || payload.own_weapons.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"])) ||
          !boundedArray(payload.active_assets, 104) || payload.active_assets.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"]))) throw new Error("protocol");
      tacticalRows(payload.tactical, 128);
      rowsExact(payload.target_choices, 128, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"]);
    } else if (state.role === "damage") {
      if (!boundedArray(payload.compartments, 16) || payload.compartments.some((row) => !exactKeys(row, ["key", "name", "state", "flood", "fire", "repairable", "trend"]) || typeof row.repairable !== "boolean" || !exactKeys(row.trend, ["flood_rate", "fire_rate", "repairable"])) ||
          !boundedArray(payload.teams, 16) || payload.teams.some((row) => !exactKeys(row, ["team", "compartment"]))) throw new Error("protocol");
    } else if (state.role === "opz") {
      tacticalRows(payload.observations, 256);
      tacticalRows(payload.fusions, 32, ["members"]);
      const rawRefs = new Set(payload.observations.map((row) => row.ref));
      const pictureRefs = new Set([...rawRefs, ...payload.fusions.map((row) => row.ref)]);
      const radarFields = ["surface", "air", "range_nm", "live", "sweep_bearing", "sweep_rate_deg_s", "weather_severity", "surface_effective_range_nm", "air_effective_range_nm"];
      if (!exactKeys(payload.radar, radarFields) ||
          typeof payload.radar.surface !== "boolean" || typeof payload.radar.air !== "boolean" ||
          typeof payload.radar.live !== "boolean" || ![10, 20, 40, 80, 120].includes(payload.radar.range_nm) ||
          (!finite(payload.radar.sweep_rate_deg_s) || payload.radar.sweep_rate_deg_s < 0 || payload.radar.sweep_rate_deg_s > 720) ||
          payload.fusions.some((row) => !boundedArray(row.members, 8) || row.members.length < 2 ||
            row.source !== "FUSION" || new Set(row.members).size !== row.members.length ||
            row.members.some((ref) => typeof ref !== "string" || !rawRefs.has(ref))) ||
          !boundedArray(payload.source_classifications, 256) ||
          payload.source_classifications.some((row) => !exactKeys(row, ["ref", "source", "classification"]) ||
            !pictureRefs.has(row.ref) || typeof row.source !== "string" ||
            typeof row.classification !== "string" || !row.classification || row.classification.length > 128) ||
           new Set(payload.source_classifications.map((row) => row.ref)).size !== payload.source_classifications.length ||
           !exactKeys(payload.defense, ["vls", "ciws", "aa", "chaff_ready", "ciws_ready", "aa_ready"])) throw new Error("protocol");
      tacticalRows(payload.asm_observations, 128);
      if (payload.designated_target_ref !== null && (typeof payload.designated_target_ref !== "string" || !pictureRefs.has(payload.designated_target_ref))) throw new Error("protocol");
      if (!exactKeys(payload.own_assets, ["ship", "helicopter"]) ||
          !exactKeys(payload.own_assets.ship, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate"]) ||
          !exactKeys(payload.own_assets.helicopter, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s"])) throw new Error("protocol");
    } else if (state.role === "radio") {
      rowsExact(payload.observations, 256, ["ref", "label", "bearing", "quality", "age_s", "bearing_uncertainty_deg", "can_capture"]);
      if (!boundedArray(payload.logged_fixes, 256) || payload.logged_fixes.some((row) => !exactKeys(row, ["ref", "x", "y", "uncertainty_nm", "age_s", "covariance_nm2"]) || row.covariance_nm2 !== null && (!boundedArray(row.covariance_nm2, 3) || row.covariance_nm2.length !== 3)) ||
          !boundedArray(payload.logged_bearings, 256) || payload.logged_bearings.some((row) => !exactKeys(row, ["ref", "bearing", "observer_x", "observer_y", "age_s"])) ||
          !boundedArray(payload.messages, 40) || payload.messages.some((row) => !exactKeys(row, ["stamp", "text"])) ||
          typeof payload.station_down !== "boolean" || payload.observations.some((row) => typeof row.can_capture !== "boolean") ||
          !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate"])) throw new Error("protocol");
      tacticalRows(payload.tactical, 128);
    } else if (state.role === "engine") {
      if (!exactKeys(payload.propulsion, ["speed", "target_speed", "telegraph", "rpm", "quiet_mode", "cavitating"]) ||
          !exactKeys(payload.machinery, ["station_state", "speed_cap", "effective_speed_cap", "flood", "fire", "noise", "grounded"]) ||
          !exactKeys(payload.controls, ["orders", "speed_max_kn"]) || !boundedArray(payload.controls.orders, 6) ||
          payload.controls.orders.join(",") !== "ASTERN,STOP,SLOW,HALF,FULL,FLANK" ||
          !exactKeys(payload.environment_effects, ["sea_state", "roll", "pitch", "tas_available", "tas_performance"])) throw new Error("protocol");
    } else if (state.role === "helicopter") {
      if (!exactKeys(payload.asset, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s"]) ||
          (payload.waypoint !== null && !exactKeys(payload.waypoint, ["x", "y"])) ||
          !boundedArray(payload.buoys, 64) || payload.buoys.some((row) => !exactKeys(row, ["ref", "x", "y", "battery_s", "active"])) ||
          !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate"]) ||
          !exactKeys(payload.readiness, ["flightdeck_down", "deck_state", "can_launch", "can_return", "can_set_waypoint", "can_deploy_buoy", "can_set_dipping", "can_set_dip_depth", "can_dipping_ping", "rtb_margin_s"]) ||
          [payload.readiness.flightdeck_down, payload.readiness.can_launch, payload.readiness.can_return, payload.readiness.can_set_waypoint, payload.readiness.can_deploy_buoy, payload.readiness.can_set_dipping, payload.readiness.can_set_dip_depth, payload.readiness.can_dipping_ping].some((value) => typeof value !== "boolean")) throw new Error("protocol");
      tacticalRows(payload.tactical, 128);
      rowsExact(payload.target_choices, 128, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"]);
    } else if (state.role === "eloka") {
      if (!boundedArray(payload.intercepts, 64) || payload.intercepts.some((row) => !exactKeys(row, ["ref", "label", "bearing", "bearing_uncertainty_deg", "frequency_hz", "prf_hz", "modulation", "quality", "age_s", "annotation", "candidates", "correlations"]) ||
          !boundedArray(row.candidates, 5) || row.candidates.some((item) => !exactKeys(item, ["ref", "name", "score"])) ||
          !boundedArray(row.correlations, 8) || row.correlations.some((item) => !exactKeys(item, ["ref", "source", "score", "ambiguous", "evidence"]) || !exactKeys(item.evidence, ["bearing", "bearing_uncertainty_deg", "age_s", "position_available"])))) throw new Error("protocol");
      if (typeof payload.station_down !== "boolean" || !["down", "live"].includes(payload.status)) throw new Error("protocol");
    }
    const arrays = [];
    for (const key of ["tactical_summary", "observations", "own_weapons", "compartments", "teams", "logged_fixes", "logged_bearings", "messages", "buoys", "intercepts"]) {
      if (Object.hasOwn(payload, key)) arrays.push(payload[key]);
    }
    if (arrays.some((rows) => !boundedArray(rows, 256))) throw new Error("protocol");
    const forbidden = new Set(["target_id", "track_id", "kind", "signature", "emitter_key", "seed", "rng"]);
    const inspect = (value, depth = 0) => {
      if (depth > 8) throw new Error("protocol");
      if (value === null || typeof value === "boolean" || typeof value === "string") return;
      if (typeof value === "number") { if (!finite(value)) throw new Error("protocol"); return; }
      if (Array.isArray(value)) { if (value.length > 256) throw new Error("protocol"); value.forEach((item) => inspect(item, depth + 1)); return; }
      if (!value || typeof value !== "object") throw new Error("protocol");
      for (const [key, item] of Object.entries(value)) { if (forbidden.has(key)) throw new Error("protocol"); inspect(item, depth + 1); }
    };
    inspect(state);
  }

  function useV2State(state) {
    v2State = state;
    updateOpzSweepSample(state);
  }

  function adaptV2State(state) {
    const emptyOwn = {x: null, y: null, course: null, speed: null, target_course: null, target_speed: null, damage: [], inventory: {}, helo: {}};
    const ownship = structuredClone(emptyOwn);
    let observations = [];
    const payload = state[state.role];
    if (state.role === "bridge") { Object.assign(ownship, payload.navigation); observations = payload.tactical_summary; }
    if (state.role === "sonar") observations = payload.observations;
    if (state.role === "weapons") { Object.assign(ownship, payload.navigation); ownship.inventory = payload.inventory; observations = payload.tactical; }
    if (state.role === "damage") ownship.damage = payload.compartments.map((room) => ({...room, teams: payload.teams.filter((team) => team.compartment === room.key).map((team) => team.team)}));
    if (state.role === "opz") {
      const sourceClasses = new Map(payload.source_classifications.map((row) => [row.ref, row.classification]));
      observations = [...payload.observations, ...payload.fusions].map((row) => ({...row,
        classification: sourceClasses.get(row.ref) ?? null}));
      Object.assign(ownship, payload.own_assets.ship);
      ownship.helo = payload.own_assets.helicopter;
      const current = new Set(observations.map((row) => row.ref));
      opzMarked = new Set([...opzMarked].filter((ref) => current.has(ref) &&
        observations.find((row) => row.ref === ref)?.source !== "FUSION"));
      opzSuppressed = new Set([...opzSuppressed].filter((ref) => current.has(ref)));
    }
    if (state.role === "radio") { Object.assign(ownship, payload.navigation); observations = payload.tactical; }
    if (state.role === "engine") { ownship.speed = payload.propulsion.speed; ownship.target_speed = payload.propulsion.target_speed; }
    if (state.role === "helicopter") { Object.assign(ownship, payload.navigation); ownship.helo = payload.asset; observations = payload.tactical; }
    if (state.role === "eloka") observations = payload.intercepts;
    const tracks = observations.map((row) => ({ref: row.ref, label: row.label || row.ref,
      domain: row.domain || "UNKNOWN", source: row.source || (state.role === "eloka" ? "ESM" : "HFDF"),
      affiliation: row.affiliation || "UNKNOWN", classification: row.classification ?? null,
      bearing: row.bearing ?? null, range_nm: row.range_nm ?? null, x: row.x ?? null, y: row.y ?? null,
      depth_m: row.depth_m ?? null, course: row.course ?? null, speed_kn: row.speed_kn ?? null,
      observer_x: row.observer_x ?? null, observer_y: row.observer_y ?? null,
      released_to_opz: row.released_to_opz === true,
      quality: row.quality ?? null, age_s: row.age_s ?? null, fix_age_s: row.fix_age_s ?? null,
      bearing_uncertainty_deg: row.bearing_uncertainty_deg ?? null,
      range_uncertainty_nm: row.range_uncertainty_nm ?? null, fixes: row.fixes || [],
      members: row.members || [],
      can_classify: state.role === "sonar" || (state.role === "opz" &&
        (row.source.startsWith("RADAR") || ["HOJ", "FUSION"].includes(row.source))),
      can_propose: false})).filter((row) => state.role !== "opz" || opzManage || !opzSuppressed.has(row.ref));
    return {...state, protocol: 1, commands_allowed: false, ownship, tracks,
      crew_target: null, proposal: null, events: [], results: []};
  }

  function validateState(state) {
    if (protocolMode === "v2") {
      validateV2State(state);
      if (state.role === null) return;
      state = adaptV2State(state);
    }
    if (!state || state.protocol !== 1 || typeof state.session !== "string" || !state.session ||
        !Number.isSafeInteger(state.epoch) || !Number.isSafeInteger(state.revision) || !Number.isSafeInteger(state.seq) ||
        state.chart_revision == null || typeof state.commands_allowed !== "boolean" ||
        !state.ownship || ["x", "y"].some((key) => state.ownship[key] !== null && !finite(state.ownship[key])) ||
        !state.clock || !state.mission || !Array.isArray(state.tracks) || !Array.isArray(state.events) || !Array.isArray(state.results) ||
        state.tracks.some((track) => !track || typeof track.ref !== "string" || !track.ref ||
          !Array.isArray(track.fixes) || track.fixes.length > 4 || track.fixes.some((fix) => !fix ||
            !["PING", "DIPPING", "TMA", "SONOBUOY"].includes(fix.source) ||
            ![fix.x, fix.y, fix.measured_at, fix.fixed_at, fix.measurement_age_s,
              fix.fix_age_s, fix.uncertainty_nm, fix.quality].every(finite) ||
            fix.fixed_at < fix.measured_at || fix.measurement_age_s < 0 || fix.fix_age_s < 0 ||
            fix.uncertainty_nm <= 0 || fix.uncertainty_nm > 100 ||
            Math.abs(fix.x) > 1000000 || Math.abs(fix.y) > 1000000 ||
            fix.measured_at < 0 || fix.measured_at > 1000000000000 ||
            fix.fixed_at > 1000000000000 || fix.quality < 0 || fix.quality > 1 ||
            ((fix.depth_m === null) !== (fix.depth_uncertainty_m === null)) ||
            (fix.depth_m !== null && (!finite(fix.depth_m) || !finite(fix.depth_uncertainty_m) ||
              fix.depth_m < 0 || fix.depth_uncertainty_m <= 0))))) throw new Error("protocol");
    if (new Set(state.tracks.map((track) => track.ref)).size !== state.tracks.length) throw new Error("protocol");
    if (state.tracks.some((track) => new Set(track.fixes.map((fix) => fix.source)).size !== track.fixes.length)) throw new Error("protocol");
    const environment = state.environment;
    if (environment != null && (typeof environment !== "object" || Array.isArray(environment) ||
        Object.keys(environment).sort().join(",") !== "is_night,sea_state" ||
        (environment.sea_state !== null && (!Number.isInteger(environment.sea_state) || environment.sea_state < 0 || environment.sea_state > 9)) ||
        (environment.is_night !== null && typeof environment.is_night !== "boolean"))) throw new Error("protocol");
    const navigation = state.navigation_proposal;
    if (navigation != null && (typeof navigation !== "object" || Array.isArray(navigation) ||
        Object.keys(navigation).sort().join(",") !== "course,speed_kn,status" ||
        !["pending", "accepted", "rejected", "expired"].includes(navigation.status) ||
        (navigation.course === null && navigation.speed_kn === null) ||
        (navigation.course !== null && (!finite(navigation.course) || navigation.course < 0 || navigation.course >= 360)) ||
        (navigation.speed_kn !== null && (!finite(navigation.speed_kn) || navigation.speed_kn < 0 || navigation.speed_kn > 25)))) throw new Error("protocol");
  }

  function validateChart(data, state) {
    if (!data || (protocolMode === "v2" && data.protocol !== 2) ||
        data.revision !== state.chart_revision || !finite(data.size_nm) || data.size_nm <= 0 ||
        !Array.isArray(data.landmasses) || data.landmasses.some((land) => !Array.isArray(land.points) ||
          land.points.some((point) => !Array.isArray(point) || point.length !== 2 || !point.every(finite)))) throw new Error("chart");
    if (data.geography !== undefined) {
      const geo = data.geography;
      if (!exactKeys(geo, ["labels", "airbases", "depths"]) ||
          ![geo.labels, geo.airbases].every((rows) => Array.isArray(rows) && rows.length <= 128 && rows.every((row) =>
            exactKeys(row, ["name", "x", "y"]) && typeof row.name === "string" && row.name.length <= 96 && finite(row.x) && finite(row.y))) ||
          !Array.isArray(geo.depths) || geo.depths.length > 64 || geo.depths.some((row) =>
            !Array.isArray(row) || row.length > 64 || !row.every(finite))) throw new Error("chart");
    }
  }

  async function poll() {
    if (!authenticated() || polling) return;
    polling = true;
    const context = generation;
    const started = performance.now();
    let delay = 500;
    try {
      if (protocolMode === "v2" && started - lastSessionFetch >= 1000) {
        const metadata = await request("/session");
        if (context !== generation) return;
        acceptSession(metadata);
      }
      if (protocolMode === "v2" && session.station === null) {
        failures = 0;
        lastSuccess = performance.now();
        setConnection("lobby");
        renderLobby();
        return;
      }
      let next = await request("/state");
      if (context !== generation) return;
      if (protocolMode === "v2" && next?.role !== null && next?.role !== session.station) {
        const metadata = await request("/session");
        if (context !== generation) return;
        acceptSession(metadata);
      }
      validateState(next);
      if (protocolMode === "v2" && next.role !== null) { useV2State(next); next = adaptV2State(next); }
      if (!chartMatches(next)) {
        // Chart has no session field. Sandwich it between matching snapshots;
        // never display a previous session with a new session's geography.
        $("operations").hidden = true;
        setConnection("syncing");
        const candidate = await request("/chart");
        if (context !== generation) return;
        validateChart(candidate, next);
        let confirmed = await request("/state");
        if (context !== generation) return;
        validateState(confirmed);
        if (protocolMode === "v2" && confirmed.role !== null) { useV2State(confirmed); confirmed = adaptV2State(confirmed); }
        if (!sameContext(next, confirmed) || confirmed.role !== next.role ||
            confirmed.chart_revision !== candidate.revision || confirmed.seq < next.seq) {
          // An active-station switch may race the chart sandwich. Discard both
          // snapshots and retry without treating the expected race as a fault.
          return;
        }
        chart = candidate;
        chartSession = confirmed.session;
        chartEpoch = confirmed.epoch;
        chartRole = confirmed.role;
        next = confirmed;
      }
      if (protocolMode === "v2" && next.role === null) {
        const redactedChart = chart;
        const redactedChartSession = chartSession;
        const redactedChartEpoch = chartEpoch;
        clearRoleState();
        chart = redactedChart;
        chartSession = redactedChartSession;
        chartEpoch = redactedChartEpoch;
        chartRole = null;
        useV2State(next);
        failures = 0;
        lastSuccess = performance.now();
        setConnection("syncing");
        renderLobby();
        return;
      }
      if (sameContext(snapshot, next) && next.seq < snapshot.seq) throw new Error("sequence");
      const hadSnapshot = Boolean(snapshot);
      const sessionChanged = hadSnapshot && snapshot.session !== next.session;
      const epochChanged = hadSnapshot && !sessionChanged && snapshot.epoch !== next.epoch;
      const redacted = !hasPosition(next.ownship) && next.tracks.length === 0;
      const changed = !sameContext(snapshot, next);
      const quiet = !connected || changed || suppressNextEvents;
      const advanced = changed || !snapshot || next.seq > snapshot.seq;
      if (changed) {
        if (sonarAudioEnabled) stopSonarAudio("sonar_live_unavailable");
        if (pending) commandMessage = { key: "command_context_changed", status: "rejected" };
        pending = null;
        clearFireDrafts();
        if (epochChanged || sessionChanged) {
          $("navigation-form").reset();
          $("bridge-course-form").reset();
          $("bridge-speed-form").reset();
          opzMarked.clear();
          opzSuppressed.clear();
          opzManage = false;
          $("opz-manage").checked = false;
          stationDrafts.clear();
          for (const id of ["sonar-bearing-form", "sonar-depth-form", "sonar-gain-form", "sonar-harmonic-form",
            "engine-speed-form", "helicopter-waypoint-form"]) $(id).reset();
          $("sonar-control-page").value = "listen";
          renderSonarControlPage();
        }
        if (sessionChanged || redacted || protocolMode === "v2" && epochChanged) {
          selected = null;
          eventHistory = [];
          seenEvents.clear();
          eventHighWater = -1;
          view.initialized = false;
          lookoutView.rangeNm = 100;
        }
      }
      snapshot = next;
      if (sonarAudioEnabled && !sonarAudioAuthorized()) stopSonarAudio("sonar_live_unavailable");
      if (protocolMode === "v2" && pending) await pollV2Result(context);
      if (!view.initialized) fitChart();
      if (selected && !selectedTrack()) selected = null;
      for (const result of next.results) {
        if (pending && result.id === pending.id && ["applied", "rejected"].includes(result.status)) {
          commandMessage = { key: result.status === "applied" ? (pending.body.action === "propose_navigation" ? "navigation_queued" : "command_applied") : "command_rejected", status: result.status, reasoncode: result.reasoncode };
          pending = null;
        }
      }
      processEvents(next.events, quiet);
      suppressNextEvents = document.hidden;
      failures = 0;
      if (advanced) lastSuccess = performance.now();
      setConnection(performance.now() - lastSuccess > 4500 ? "stale" : "connected");
      $("pairing").hidden = true;
      renderLobby();
      applySimlogView();
      renderSnapshot(epochChanged);
      loadSimlog();
    } catch (error) {
      if (context !== generation) return;
      console.error("Commander poll failed", error);
      if (error.status === 401 || error.status === 403) {
        forgetSession("connection_expired");
      } else {
        failures += 1;
        delay = Math.min(8000, 500 * (2 ** Math.min(failures, 4)));
        setConnection("stale");
      }
    } finally {
      polling = false;
      if (authenticated()) {
        const cadence = protocolMode === "v2" && session?.station === null ? 1000 : delay;
        pollTimer = setTimeout(poll, context !== generation ? 0 : failures ? delay : Math.max(0, cadence - (performance.now() - started)));
      }
    }
  }

  function selectTrack(ref) {
    selected = ref;
    renderTracks();
    renderDetail(true);
    queueDraw();
  }

  function renderTracks() {
    const list = $("track-list");
    const current = new Map([...list.children].filter((element) => element.dataset.ref).map((element) => [element.dataset.ref, element]));
    const expected = new Set(snapshot.tracks.map((track) => track.ref));
    for (const child of [...list.children]) if (!expected.has(child.dataset.ref)) child.remove();
    snapshot.tracks.forEach((track, index) => {
      let button = current.get(track.ref);
      if (!button) {
        button = node("button");
        button.type = "button";
        button.dataset.ref = track.ref;
        button.addEventListener("click", () => selectTrack(track.ref));
      }
      button.className = `track ${affClass(track.affiliation)}`;
      button.setAttribute("aria-pressed", String(track.ref === selected));
      const symbol = node("span", undefined, `domain-symbol ${domainClass(track.domain)}`);
      symbol.setAttribute("aria-hidden", "true");
      const body = node("span");
      body.append(node("span", track.label, "track-name"), node("span", `${enumText(domains, track.domain)} / ${enumText(affiliations, track.affiliation)}`, "track-info"));
      body.append(node("span", `${unit(track.bearing, "\u00b0", 0)} / ${unit(track.range_nm, "NM")} / ${unit(track.age_s, "s", 0)}`, "track-info"));
      const flags = [];
      if (track.ref === selected) flags.push(t("selected"));
      if (track.ref === snapshot.crew_target) flags.push(t("crew_target"));
      if (track.ref === snapshot.proposal?.ref) flags.push(t("proposal"));
      if (opzMarked.has(track.ref)) flags.push(t("opz_marked"));
      if (opzSuppressed.has(track.ref)) flags.push(t("opz_suppressed"));
      if (flags.length) body.append(node("span", flags.join(" / "), "track-flags"));
      button.replaceChildren(symbol, body);
      // Preserve focused buttons across the two-Hz refresh, including reordering.
      if (list.children[index] !== button) list.insertBefore(button, list.children[index] || null);
    });
    if (!snapshot.tracks.length) list.replaceChildren(node("p", t("no_contacts"), "empty"));
    $("track-count").textContent = number(snapshot.tracks.length, 0);
  }

  function renderDetail(resetDraft = false) {
    const track = selectedTrack();
    $("no-selection").hidden = Boolean(track);
    $("track-detail").hidden = !track;
    if (track) {
      let stationActions = document.getElementById("selection-station-actions");
      if (!stationActions) { stationActions = node("div", undefined, "station-row-actions"); stationActions.id = "selection-station-actions"; $("track-detail").append(stationActions); }
      if (protocolMode === "v2" && session?.station === "sonar") {
        const key = `${track.ref}:${track.released_to_opz}:${stationActionAvailable()}:${language}`;
        if (stationActions.dataset.key !== key) {
          stationActions.replaceChildren(actionButton("sonar_focus", "sonar_set_focus", {ref: track.ref}),
            actionButton("sonar_designate", "sonar_designate_target", {ref: track.ref}),
            actionButton(track.released_to_opz ? "sonar_withdraw_opz" : "sonar_release_to_opz",
              "sonar_set_release", {ref: track.ref, released: !track.released_to_opz}));
          stationActions.dataset.key = key;
        }
      } else stationActions.replaceChildren();
      $("detail-label").textContent = track.label;
      $("detail-badges").replaceChildren(node("span", enumText(domains, track.domain), "badge"), node("span", enumText(affiliations, track.affiliation), `badge ${affClass(track.affiliation)}`), node("span", classificationText(track.classification), "badge"));
      const detailEntries = [
        ["source", track.source], ["quality", number(track.quality, 2)],
        ["bearing", unit(track.bearing, "\u00b0", 0)], ["range", unit(track.range_nm, "NM")],
        ["depth", unit(track.depth_m, "m", 0)], ["course", unit(track.course, "\u00b0", 0)],
        ["speed", unit(track.speed_kn, "kn")], ["age", unit(track.age_s, "s", 0)],
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
      if (protocolMode === "v2" && session?.station === "sonar") {
        $("sonar-release-status").hidden = false;
        $("sonar-release-status").textContent = t(track.released_to_opz ? "sonar_released" : "sonar_withdrawn");
        $("sonar-release").hidden = false;
        $("sonar-release").textContent = t(track.released_to_opz ? "sonar_withdraw_opz" : "sonar_release_to_opz");
      } else { $("sonar-release-status").hidden = true; $("sonar-release").hidden = true; }
    }
    const proposal = snapshot.proposal;
    const statuses = { pending: "proposal_pending", accepted: "proposal_accepted", rejected: "proposal_rejected", expired: "proposal_expired" };
    $("proposal-status").textContent = proposal ? t(statuses[proposal.status] || "proposal_pending", { label: proposal.label }) : t("no_proposal");
    const navigation = snapshot.navigation_proposal;
    $("navigation-status").textContent = navigation ? t(statuses[navigation.status], {
      label: t("navigation_summary", {
        course: navigation.course === null ? t("navigation_unchanged") : unit(navigation.course, "\u00b0"),
        speed: navigation.speed_kn === null ? t("navigation_unchanged") : unit(navigation.speed_kn, "kn"),
      }),
    }) : t("navigation_none");
    renderActionState();
  }

  function renderActionState() {
    const enabled = canCommand();
    const track = selectedTrack();
    $("follow").disabled = !hasPosition(snapshot?.ownship);
    if ($("follow").disabled) view.follow = false;
    $("follow").setAttribute("aria-pressed", String(view.follow));
    const stationEnabled = protocolMode === "v2" && stationActionAvailable();
    const sonarAction = stationEnabled && session.station === "sonar" && track?.can_classify === true;
    const opzAction = stationEnabled && session.station === "opz";
    $("apply-classification").disabled = !(enabled && track?.can_classify === true) &&
      !(sonarAction || opzAction && track?.can_classify === true);
    $("classification").disabled = $("apply-classification").disabled;
    $("apply-classification").textContent = t("apply");
    $("sonar-release").disabled = !(sonarAction && track);
    $("apply-affiliation").disabled = !(enabled && track) && !(opzAction && track);
    $("affiliation").disabled = $("apply-affiliation").disabled;
    $("propose").disabled = !enabled || track?.can_propose !== true;
    $("clear-proposal").disabled = !enabled || !snapshot?.proposal;
    for (const id of ["navigation-course", "navigation-speed", "propose-navigation"]) $(id).disabled = !enabled || !navigationLive();
    const message = pending ? { key: pending.uncertain ? "command_uncertain" : "command_pending", status: "pending" } : commandMessage;
    const reason = Object.hasOwn(reasons, message?.reasoncode) ? t(reasons[message.reasoncode]) : message?.reasoncode || t("unavailable");
    $("command-status").textContent = message ? t(message.key, { reason }) : "";
    $("command-status").dataset.status = message?.status || "";
    $("station-command-status").textContent = message ? t(message.key, {reason}) : "";
    $("station-command-status").dataset.status = message?.status || "";
    $("command-reconcile").hidden = !pending?.uncertain;
    if (protocolMode === "v2") $("command-reconcile").hidden = true;
    $("retry-command").disabled = !pending?.uncertain || pending.inFlight || performance.now() < pending.retryAt ||
      !connected || (protocolMode === "v2" && session?.grants.command !== true) ||
      snapshot?.commands_allowed !== true || !chartMatches(snapshot) || !sameContext(snapshot, pending.body) ||
      (pending.body.action === "propose_navigation" && !navigationLive());
    renderBridgeOrders();
    renderOpzControls();
    renderStationControls();
    renderDirectFireControls();
  }

  function directFireSpec(action) {
    const role = session?.station;
    const payload = v2State?.[role];
    if (role === "weapons") {
      const ref = $("weapons-fire-target").value;
      const depth = $("weapons-fire-depth").valueAsNumber;
      const target = payload?.target_choices.some((row) => row.ref === ref);
      const common = Boolean(payload && !payload.readiness.station_down);
      if (action === "weapons_launch_torpedo") return {ref, params: {ref, depth_m: depth},
        ready: common && target && payload.inventory.torpedoes > 0 && payload.readiness.state === "available" &&
          payload.tubes.some((tube) => tube.state === "ready"), readiness: [payload?.inventory.torpedoes, payload?.readiness, payload?.tubes]};
      if (action === "helicopter_launch_torpedo") return {ref, params: {ref, depth_m: depth},
        ready: common && target, readiness: [payload?.readiness, payload?.target_choices.map((row) => row.ref)]};
      if (action === "weapons_deploy_nixie") return {ref: "", params: {},
        ready: common && payload.inventory.nixies > 0, readiness: [payload?.readiness.station_down, payload?.inventory.nixies]};
    }
    if (role === "helicopter" && action === "helicopter_launch_torpedo") {
      const ref = $("helicopter-fire-target").value;
      const depth = $("helicopter-fire-depth").valueAsNumber;
      return {ref, params: {ref, depth_m: depth}, ready: payload?.asset.airborne && payload.asset.torpedoes > 0 &&
        payload.target_choices.some((row) => row.ref === ref),
      readiness: [payload?.asset.state, payload?.asset.airborne, payload?.asset.torpedoes,
        payload?.readiness, payload?.target_choices.map((row) => row.ref)]};
    }
    if (role === "opz" && ["opz_launch_essm", "opz_launch_chaff"].includes(action)) {
      const ref = $("opz-fire-target").value;
      const target = payload?.asm_observations.some((row) => row.ref === ref);
      return {ref, params: {ref}, ready: payload?.radar.live && target && (action === "opz_launch_essm" ?
        payload.defense.vls > 0 && payload.defense.aa_ready : payload.defense.chaff_ready),
      readiness: [payload?.radar.live, payload?.defense, payload?.asm_observations.map((row) => row.ref)]};
    }
    return {ref: "", params: {}, ready: false, readiness: null};
  }

  function directFireAvailable() {
    return stationActionAvailable() && session?.grants.direct_fire === true;
  }

  function directFireFingerprint(action, spec) {
    return JSON.stringify([generation, session?.station, session?.station_generation, session?.grants.command,
      session?.grants.direct_fire, v2State?.session, v2State?.epoch, action, spec.ref,
      action.includes("torpedo") ? spec.params.depth_m : null, spec.ready, spec.readiness]);
  }

  function fireStatusKey() {
    if (!session?.grants.command || !session?.grants.direct_fire) return "fire_revoked";
    if (!connected || !chartMatches(snapshot)) return "fire_stale";
    if (v2State?.phase !== "live") return "fire_inactive";
    if (pending) return pending.uncertain ? "fire_uncertain" : "fire_pending";
    return "fire_ready";
  }

  function renderDirectFireControls() {
    const role = session?.station;
    const status = role === "weapons" ? $("weapons-fire-status") : role === "opz" ? $("opz-fire-status") :
      role === "helicopter" ? $("helicopter-fire-status") : null;
    if (!status) { clearFireConfirmation(); return; }
    let armed = false;
    let anyReady = false;
    for (const button of document.querySelectorAll("[data-fire-action]")) {
      const owned = button.closest("[data-station-role]")?.dataset.stationRole === role;
      const spec = directFireSpec(button.dataset.fireAction);
      const fingerprint = directFireFingerprint(button.dataset.fireAction, spec);
      const confirmed = owned && fireConfirmation?.action === button.dataset.fireAction &&
        fireConfirmation.fingerprint === fingerprint &&
        performance.now() < fireConfirmation.expiresAt;
      if (owned && fireConfirmation?.action === button.dataset.fireAction && !confirmed) clearFireConfirmation();
      button.disabled = !owned || !directFireAvailable() || !spec.ready ||
        actionIncludesInvalidDepth(button.dataset.fireAction, spec.params.depth_m);
      anyReady ||= owned && spec.ready && !actionIncludesInvalidDepth(button.dataset.fireAction, spec.params.depth_m);
      button.classList.toggle("armed", confirmed);
      button.textContent = t(confirmed ? "fire_confirm" : button.dataset.fireAction);
      armed ||= confirmed;
    }
    for (const control of document.querySelectorAll(".direct-fire-controls input, .direct-fire-controls select")) {
      const owned = control.closest("[data-station-role]")?.dataset.stationRole === role;
      control.disabled = !owned || !directFireAvailable();
    }
    const stateKey = fireStatusKey();
    const statusKey = stateKey === "fire_ready" && !anyReady ? "fire_not_ready" : stateKey;
    status.textContent = t(armed ? "fire_confirmation_active" : statusKey);
    status.dataset.state = armed ? "armed" : statusKey;
  }

  function actionIncludesInvalidDepth(action, depth) {
    return action.includes("torpedo") && (!finite(depth) || depth < 10 || depth > 300);
  }

  function activateDirectFire(button) {
    const action = button.dataset.fireAction;
    const spec = directFireSpec(action);
    if (!directFireAvailable() || !spec.ready || actionIncludesInvalidDepth(action, spec.params.depth_m)) return;
    const fingerprint = directFireFingerprint(action, spec);
    if (!fireConfirmation || fireConfirmation.fingerprint !== fingerprint || performance.now() >= fireConfirmation.expiresAt) {
      clearFireConfirmation();
      fireConfirmation = {action, fingerprint, expiresAt: performance.now() + 5000};
      fireConfirmationTimer = setTimeout(() => { clearFireConfirmation(); renderDirectFireControls(); }, 5000);
      renderDirectFireControls();
      return;
    }
    clearFireConfirmation();
    sendStationAction(action, spec.params);
  }

  function renderStationControls() {
    const available = stationActionAvailable();
    for (const control of document.querySelectorAll("[data-station-action], .station-controls input, .station-controls select, .station-controls button, #helicopter-waypoint-form input, #helicopter-waypoint-form button")) {
      const local = control.id === "sonar-control-page";
      const owned = control.closest("[data-station-role]")?.dataset.stationRole === session?.station;
      control.disabled = !owned || !local && (!available || control.dataset.ready === "false");
    }
    const sonar = v2State?.sonar?.settings;
    if (sonar) {
      const live = available && !sonar.station_down;
      for (const id of ["sonar-bearing", "sonar-bearing-submit", "sonar-clear-focus", "sonar-array-mode", "sonar-array-apply",
        "sonar-tma", "sonar-gain", "sonar-gain-submit", "sonar-band", "sonar-band-apply", "sonar-notch", "sonar-peak",
        "sonar-harmonic-input", "sonar-harmonic-submit", "sonar-harmonic-clear"]) $(id).disabled = !live;
      $("sonar-clear-focus").disabled = !live || sonar.focus_ref === null;
    }
    const engine = v2State?.engine;
    if (engine) {
      const live = available && engine.machinery.station_state !== "ZERSTOERT";
      for (const id of ["engine-telegraph", "engine-telegraph-submit", "engine-speed", "engine-speed-submit", "engine-quiet"]) $(id).disabled = !live;
    }
    $("damage-team").disabled = !(available && session?.station === "damage" && v2State?.damage?.teams.length);
    $("opz-designate").disabled = !(available && session?.station === "opz" && selectedTrack() && v2State?.opz?.radar.live);
  }

  function renderSonarControlPage() {
    const page = $("sonar-control-page").value;
    for (const panel of document.querySelectorAll("[data-sonar-page]")) panel.hidden = panel.dataset.sonarPage !== page;
  }

  function stationActionAvailable() {
    return connected && protocolMode === "v2" && session?.grants.command === true &&
      v2State?.phase === "live" && chartMatches(snapshot) && !pending;
  }

  function renderOpzControls() {
    const active = protocolMode === "v2" && session?.station === "opz";
    $("opz-controls").hidden = !active;
    $("opz-track-actions").hidden = !active;
    if (!active) return;
    const radar = v2State?.opz?.radar;
    const available = stationActionAvailable() && radar?.live === true;
    $("opz-radar-surface").checked = radar?.surface === true;
    $("opz-radar-air").checked = radar?.air === true;
    if (finite(radar?.range_nm)) $("opz-range").value = String(radar.range_nm);
    for (const id of ["opz-radar-surface", "opz-radar-air", "opz-range"]) $(id).disabled = !available;
    $("opz-create-fusion").disabled = !available || opzMarked.size < 2 || opzMarked.size > 8;
    const track = selectedTrack();
    $("opz-mark").disabled = !track || track.source === "FUSION";
    $("opz-mark").setAttribute("aria-pressed", String(Boolean(track && opzMarked.has(track.ref))));
    $("opz-dissolve").disabled = !available || track?.source !== "FUSION";
    $("opz-suppress").disabled = !track;
    $("opz-suppress").textContent = t(track && opzSuppressed.has(track.ref) ? "opz_restore" : "opz_suppress");
    $("opz-mark-status").textContent = t("opz_mark_count", {count: opzMarked.size});
  }

  function renderSnapshot(resetDraft = false) {
    $("mission-name").textContent = snapshot.mission.name;
    $("objective").textContent = snapshot.mission.objective;
    $("phase").textContent = enumText(phases, snapshot.phase);
    $("command-permission").textContent = t(snapshot.commands_allowed ? "commands_enabled" : "commands_disabled");
    metrics($("mission-metrics"), [
      ["remaining", unit(snapshot.mission.remaining_s, "s", 0)],
      ["mission_clock", unit(snapshot.clock.mission, "s", 0)],
      ["time_scale", unit(snapshot.clock.time_scale, "x")],
      ["world_clock", finite(snapshot.clock.world) ? `${String(Math.floor(snapshot.clock.world) % 24).padStart(2, "0")}:${String(Math.floor(snapshot.clock.world * 60) % 60).padStart(2, "0")}` : t("unavailable")],
    ]);
    const own = snapshot.ownship;
    renderStationView();
    renderBridgeOrders();
    metrics($("own-metrics"), [
      ["course", unit(own.course, "\u00b0", 0)], ["speed", unit(own.speed, "kn")],
      ["ordered_course", unit(own.target_course, "\u00b0", 0)], ["ordered_speed", unit(own.target_speed, "kn")],
      ["position", `${unit(own.x, "NM")} / ${unit(own.y, "NM")}`],
    ]);
    const inventory = own.inventory || {};
    metrics($("inventory"), [
      ["torpedoes", number(inventory.torpedoes, 0)], ["vls", number(inventory.vls, 0)],
      ["ciws", number(inventory.ciws, 0)], ["chaff", typeof inventory.chaff_ready === "boolean" ? t(inventory.chaff_ready ? "ready" : "not_ready") : number(inventory.chaff_ready, 0)],
    ]);
    const helo = own.helo || {};
    metrics($("helo-metrics"), [
      ["state", enumText(heloStates, helo.state)], ["fuel", unit(helo.fuel_s, "s", 0)],
      ["torpedoes", number(helo.torpedoes, 0)], ["buoys", number(helo.buoys, 0)],
      ["course", unit(helo.course, "\u00b0", 0)], ["position", `${unit(helo.x, "NM")} / ${unit(helo.y, "NM")}`],
    ]);
    const damage = Array.isArray(own.damage) ? own.damage : [];
    let alarms = 0;
    $("damage-list").replaceChildren(...damage.map((item) => {
      const alarm = item.flood > 0 || item.fire > 0 || ["FLUTEND", "BESCHAEDIGT", "ZERSTOERT"].includes(item.state);
      if (alarm) alarms += 1;
      const row = node("div", undefined, `damage-row${alarm ? " alarm" : ""}`);
      const heading = node("h3");
      heading.append(node("span", item.name), node("span", enumText(damageStates, item.state)));
      const values = node("dl", undefined, "metrics");
      metrics(values, [["flood", unit(item.flood, "%")], ["fire", unit(item.fire, "%")], ["teams", Array.isArray(item.teams) ? number(item.teams.length, 0) : t("unavailable")]]);
      row.append(heading, values);
      return row;
    }));
    if (!damage.length) $("damage-list").append(node("p", t("no_damage_data"), "empty"));
    $("alarm-count").textContent = t("alarm_count", { count: number(alarms, 0) });
    $("chart-disclaimer").textContent = chart.disclaimer;
    $("snapshot-meta").textContent = t("snapshot_meta", { version: snapshot.version, seq: snapshot.seq, revision: snapshot.revision, sim: number(snapshot.clock.sim, 1) });
    renderTracks();
    renderDetail(resetDraft);
    renderEvents();
    queueDraw();
    renderLookoutStatus();
    queueLookoutDraw();
  }

  function secureId() {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function bridgeOrderAvailable(kind) {
    const orders = v2State?.bridge?.orders;
    return protocolMode === "v2" && session?.station === "bridge" &&
      session.grants.command === true && connected && v2State?.phase === "live" &&
      chartMatches(snapshot) && !pending && orders && (kind !== "course" || !orders.station_down);
  }

  function renderBridgeOrders() {
    const panel = $("bridge-orders");
    panel.hidden = protocolMode !== "v2" || session?.station !== "bridge";
    if (panel.hidden) return;
    const navigation = v2State?.bridge?.navigation || {};
    metrics($("bridge-order-values"), [
      ["bridge_current_course", unit(navigation.course, "\u00b0", 0)],
      ["bridge_ordered_course", unit(navigation.target_course, "\u00b0", 0)],
      ["bridge_current_speed", unit(navigation.speed, "kn")],
      ["bridge_ordered_speed", unit(navigation.target_speed, "kn")],
    ]);
    $("bridge-course").disabled = $("bridge-course-submit").disabled = !bridgeOrderAvailable("course");
    $("bridge-speed").disabled = $("bridge-speed-submit").disabled = !bridgeOrderAvailable("speed");
    const message = pending ? {key: pending.uncertain ? "bridge_order_uncertain" : "bridge_order_pending", status: "pending"} : commandMessage;
    const reason = Object.hasOwn(reasons, message?.reasoncode) ? t(reasons[message.reasoncode]) : t("reason_action_rejected");
    $("bridge-order-status").textContent = message ? t(message.key, {reason}) :
      v2State?.bridge?.orders.station_down ? t("bridge_down") : "";
    $("bridge-order-status").dataset.status = message?.status || "";
  }

  async function sendBridgeOrder(kind) {
    if (!bridgeOrderAvailable(kind)) return;
    const form = $(`bridge-${kind}-form`);
    const input = $(`bridge-${kind}`);
    if (!form.reportValidity()) return;
    const value = input.valueAsNumber;
    const maximum = kind === "course" ? 360 : v2State.bridge.orders.speed_max_kn;
    if (!finite(value) || value < 0 || value > maximum || (kind === "course" && value === 360)) {
      commandMessage = {key: "bridge_order_invalid", status: "rejected"};
      renderBridgeOrders();
      return;
    }
    let id;
    try { id = secureId(); } catch (_) {
      commandMessage = {key: "command_no_crypto", status: "rejected"};
      renderBridgeOrders();
      return;
    }
    const body = Object.freeze({protocol: 2, id, seq: nextCommandSeq,
      station: "bridge", station_generation: session.station_generation,
      active_generation: session.active_generation,
      world_session: v2State.session, world_epoch: v2State.epoch,
      resource_revision: v2State.revision, action: `bridge_set_${kind}`,
      params: Object.freeze({[kind === "course" ? "course" : "speed_kn"]: value})});
    pending = {id, body, uncertain: false, inFlight: true};
    commandMessage = null;
    renderBridgeOrders();
    const context = generation;
    try {
      await request("/commands", {method: "POST", body, expected: 202, csrf: session.csrf,
        guard: () => context === generation && pending?.id === id});
      nextCommandSeq += 1;
    } catch (error) {
      if (context !== generation || pending?.id !== id || error.message === "cancelled") return;
      pending.uncertain = true;
      if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
      else if (!error.status || error.status >= 500) setConnection("stale");
      else { commandMessage = {key: "bridge_order_http_rejected", status: "rejected", reasoncode: "action_rejected"}; pending = null; }
    } finally {
      if (pending?.id === id) pending.inFlight = false;
      renderBridgeOrders();
    }
  }

  async function sendStationAction(action, params) {
    if (!stationActionAvailable()) return;
    let id;
    try { id = secureId(); } catch (_) {
      commandMessage = {key: "command_no_crypto", status: "rejected"};
      renderActionState();
      return;
    }
    const body = Object.freeze({protocol: 2, id, seq: nextCommandSeq,
      station: session.station, station_generation: session.station_generation,
      active_generation: session.active_generation,
      world_session: v2State.session, world_epoch: v2State.epoch,
      resource_revision: v2State.revision, action, params: Object.freeze(params)});
    pending = {id, body, uncertain: false, inFlight: true};
    commandMessage = null;
    renderActionState();
    const context = generation;
    try {
      await request("/commands", {method: "POST", body, expected: 202, csrf: session.csrf,
        guard: () => context === generation && pending?.id === id});
      nextCommandSeq += 1;
    } catch (error) {
      if (context !== generation || pending?.id !== id || error.message === "cancelled") return;
      pending.uncertain = true;
      if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
      else if (!error.status || error.status >= 500) setConnection("stale");
      else { commandMessage = {key: "command_rejected", status: "rejected", reasoncode: "action_rejected"}; pending = null; }
    } finally {
      if (pending?.id === id) pending.inFlight = false;
      renderActionState();
    }
  }

  async function pollV2Result(context) {
    const command = pending;
    const payload = await request("/results", {guard: () => context === generation && pending === command});
    if (context !== generation || pending !== command || !exactKeys(payload, ["protocol", "results"]) ||
        payload.protocol !== 2 || !boundedArray(payload.results, 64)) throw new Error("results");
    const result = payload.results.find((item) => exactKeys(item, ["id", "seq", "status", "reasoncode"]) &&
      item.id === command.id && item.seq === command.body.seq && ["applied", "rejected"].includes(item.status) &&
      typeof item.reasoncode === "string" && item.reasoncode.length <= 64);
    if (!result) return;
    const bridge = command.body.action.startsWith("bridge_");
    commandMessage = {key: result.status === "applied" ?
      (bridge ? "bridge_order_applied" : "command_applied") :
      (bridge ? "bridge_order_rejected" : "command_rejected"),
      status: result.status, reasoncode: result.reasoncode};
    pending = null;
    stationDrafts.clear();
    clearFireDrafts();
  }

  async function sendCommand(action, value) {
    if (!canCommand()) return;
    const track = selectedTrack();
    if (!["clear_proposal", "propose_navigation"].includes(action) && !track) return;
    let navigation;
    if (action === "propose_navigation") {
      if (!navigationLive() || !$("navigation-form").reportValidity()) return;
      navigation = {};
      for (const [id, field] of [["navigation-course", "course"], ["navigation-speed", "speed_kn"]]) {
        const input = $(id);
        if (input.value.trim()) navigation[field] = input.valueAsNumber;
      }
      if (!Object.keys(navigation).length || Object.values(navigation).some((n) => !finite(n)) ||
          (navigation.course !== undefined && (navigation.course < 0 || navigation.course >= 360)) ||
          (navigation.speed_kn !== undefined && (navigation.speed_kn < 0 || navigation.speed_kn > 25))) {
        commandMessage = { key: "navigation_invalid", status: "rejected" };
        renderActionState();
        return;
      }
    }
    if (action === "classify" && track.can_classify !== true) return;
    if (action === "propose" && track.can_propose !== true) return;
    let id;
    try { id = secureId(); } catch (_) {
      commandMessage = { key: "command_no_crypto", status: "rejected" };
      renderActionState();
      return;
    }
    const body = { id, session: snapshot.session, epoch: snapshot.epoch, revision: snapshot.revision, action };
    if (!["clear_proposal", "propose_navigation"].includes(action)) body.track = track.ref;
    if (navigation) Object.assign(body, navigation);
    if (action === "classify" || action === "affiliate") body.value = value;
    pending = { id, body: Object.freeze(body), uncertain: false, inFlight: false, retryAt: 0 };
    commandMessage = null;
    await transmitCommand(pending);
  }

  async function transmitCommand(command) {
    const current = () => pending === command && connected && snapshot?.commands_allowed === true &&
      (protocolMode !== "v2" || session?.grants.command === true) &&
      chartMatches(snapshot) && sameContext(snapshot, command.body) &&
      (command.body.action !== "propose_navigation" || navigationLive());
    if (!current() || command.inFlight) return;
    command.inFlight = true;
    renderActionState();
    try {
      await request("/commands", { method: "POST", body: command.body, expected: 202, guard: current });
      // HTTP 202 only acknowledges the queue. Only snapshot.results settles it.
    } catch (error) {
      if (pending !== command || error.message === "cancelled") return;
      if (error.status === 401 || error.status === 403) {
        forgetSession("connection_expired");
        return;
      }
      // Even a refused retry cannot prove that the original attempt did not apply.
      command.uncertain = true;
      if (!error.status || error.status >= 500) setConnection("stale");
    } finally {
      if (pending === command) {
        command.inFlight = false;
        command.retryAt = performance.now() + 5000;
        renderActionState();
      }
    }
  }

  function processEvents(events, quiet) {
    let alert = false;
    for (const event of [...events].sort((a, b) => a.seq - b.seq)) {
      if (!Number.isSafeInteger(event.seq) || seenEvents.has(event.seq) || event.seq <= eventHighWater) continue;
      seenEvents.add(event.seq);
      eventHighWater = event.seq;
      eventHistory.push(event);
      if (!quiet && ["warning", "critical", "alarm", "error"].includes(String(event.severity).toLowerCase())) alert = true;
    }
    while (seenEvents.size > 256) seenEvents.delete(seenEvents.values().next().value);
    eventHistory = eventHistory.slice(-80);
    if (alert) playAlert();
  }

  function renderEvents() {
    $("event-list").replaceChildren(...[...eventHistory].reverse().map((event) => {
      const severity = String(event.severity).toLowerCase();
      const style = ["critical", "alarm", "error"].includes(severity) ? "critical" : severity === "warning" ? "warning" : "";
      const item = node("li", undefined, style);
      item.append(node("span", `${event.seq} / ${event.kind}`, "event-meta"), node("span", event.message));
      return item;
    }));
    if (!eventHistory.length) $("event-list").append(node("li", t("no_events")));
  }

    // Hidden view (#simlog): complete bounded simulation log, read-only.
  // Event rows carry localized text; state rows carry a structured snapshot
  // of every unit, weapon and map item, rendered as readable tables.
  const simlogTags = { navigation: "NAV", funk: "FUNK", sonar: "SON", waffen: "WAF", schaden: "SCH", mission: "MIS", welt: "WET", state: "STATE" };
  const simlogStateSections = ["subs", "surfaces", "animals", "torpedoes", "enemy_torpedoes", "decoys", "asms", "essms", "asrocs", "nixies", "buoys", "flights", "raiders", "helo"];
  const simlogStateColumns = {
    subs: ["id", "x", "y", "depth", "course", "speed", "state", "torps", "sunk"],
    surfaces: ["id", "kind", "x", "y", "course", "speed", "damage", "sunk"],
    animals: ["id", "x", "y", "dead"],
    torpedoes: ["id", "x", "y", "depth", "course", "state", "target"],
    enemy_torpedoes: ["id", "x", "y", "depth", "course", "state"],
    decoys: ["id", "x", "y", "depth", "life", "dead"],
    asms: ["seq", "x", "y", "course", "state", "jammer"],
    essms: ["seq", "x", "y", "course", "state"],
    asrocs: ["seq", "x", "y", "course", "state"],
    nixies: ["seq", "x", "y", "depth", "dead"],
    buoys: ["seq", "x", "y", "battery_s", "active"],
    flights: ["seq", "kind", "x", "y", "course"],
    raiders: ["seq", "x", "y", "course", "phase", "hp", "pending_asm"],
    helo: ["state", "x", "y", "airborne"],
  };
  const simlogColumnKeys = {
    id: "simlog_col_id", seq: "simlog_col_id", kind: "simlog_col_kind",
    x: "simlog_col_x", y: "simlog_col_y", depth: "simlog_col_depth",
    course: "simlog_col_course", speed: "simlog_col_speed",
    state: "simlog_col_state", torps: "simlog_col_torps",
    damage: "simlog_col_damage", sunk: "simlog_col_sunk", dead: "simlog_col_dead",
    target: "simlog_col_target", life: "simlog_col_life",
    battery_s: "simlog_col_battery", active: "simlog_col_active",
    jammer: "simlog_col_jammer", phase: "simlog_col_phase", hp: "simlog_col_hp",
    pending_asm: "simlog_col_pending_asm", airborne: "simlog_col_active",
  };
  const simlogCategoryKeys = {
    subs: "simlog_cat_subs", surfaces: "simlog_cat_surfaces",
    animals: "simlog_cat_animals", torpedoes: "simlog_cat_torps",
    enemy_torpedoes: "simlog_cat_enemy_torps", decoys: "simlog_cat_decoys",
    asms: "simlog_cat_asms", essms: "simlog_cat_essms",
    asrocs: "simlog_cat_asrocs", nixies: "simlog_cat_nixies",
    buoys: "simlog_cat_buoys", flights: "simlog_cat_flights",
    raiders: "simlog_cat_raiders", helo: "simlog_cat_helo",
  };
  const simlogFlagFields = {
    subs: "sunk", surfaces: "sunk", animals: "dead",
    decoys: "dead", nixies: "dead",
  };
  const simlogMapStyles = {
    ship: ["SURFACE", "#a1e7cc"], subs: ["SUBSURFACE", "#ff9090"],
    surfaces: ["SURFACE", "#f3c577"], animals: ["UNKNOWN", "#8fdfab"],
    torpedoes: ["SUBSURFACE", "#81c5ff"], enemy_torpedoes: ["SUBSURFACE", "#ff6666"],
    decoys: ["UNKNOWN", "#c89cff"], asms: ["AIR", "#ff9f6e"],
    essms: ["AIR", "#8fcfff"], asrocs: ["AIR", "#f0dc85"],
    nixies: ["SUBSURFACE", "#c89cff"], buoys: ["UNKNOWN", "#76d5b0"],
    flights: ["AIR", "#d4c37b"], raiders: ["AIR", "#ff9090"], helo: ["AIR", "#a1e7cc"],
  };
  function simlogActive() { return location.hash === "#simlog" && authenticated() &&
    (protocolMode !== "v2" || session?.station !== null); }
  function applySimlogView() {
    const active = simlogActive();
    $("simlog-view").hidden = !active;
    $("operations").hidden = active;
    if (active) { releaseCanvas(canvas); releaseCanvas(lookoutCanvas); }
    else closeSimlogMap();
  }
  function validateSimlogData(data, depth = 0) {
    if (data === null || typeof data === "boolean" || typeof data === "string" ||
        (typeof data === "number" && Number.isFinite(data))) {
      return typeof data !== "string" || data.length <= 128;
    }
    if (depth >= 4) return false;
    if (Array.isArray(data)) return data.length <= 1024 && data.every((item) => validateSimlogData(item, depth + 1));
    if (typeof data !== "object") return false;
    const keys = Object.keys(data);
    return keys.length <= 64 && keys.every((key) => key.length <= 32 &&
      keys.length > 0 && validateSimlogData(data[key], depth + 1));
  }
  function validateSimlog(rows) {
    if (!Array.isArray(rows) || rows.length > 2048) throw new Error("simlog_schema");
    for (const row of rows) {
      if (!row || typeof row !== "object" || Array.isArray(row)) throw new Error("simlog_schema");
      const keys = Object.keys(row).sort().join(",");
      if (keys !== "cat,seq,stamp,t,text" && keys !== "cat,data,seq,stamp,t,text") throw new Error("simlog_schema");
      if (typeof row.seq !== "number" || !Number.isSafeInteger(row.seq) || row.seq < 1) throw new Error("simlog_schema");
      if (!finite(row.t) || row.t < 0 || row.t > 1e9) throw new Error("simlog_schema");
      if (typeof row.stamp !== "string" || row.stamp.length > 32) throw new Error("simlog_schema");
      if (typeof row.cat !== "string" || row.cat.length > 24) throw new Error("simlog_schema");
      if (typeof row.text !== "string" || row.text.length > 512) throw new Error("simlog_schema");
      if ("data" in row && !validateSimlogData(row.data)) throw new Error("simlog_schema");
    }
  }
  function simlogCell(field, value) {
    if (typeof value === "boolean") return t(value ? "simlog_yes" : "simlog_no");
    if (finite(value)) return number(value, 1);
    if (value === null || value === undefined) return t("unavailable");
    return String(value).slice(0, 40);
  }
  function simlogSectionRows(section, data) {
    if (Array.isArray(data[section])) return data[section];
    if (section === "helo" && data.helo && typeof data.helo === "object" && !Array.isArray(data.helo)) return [data.helo];
    return [];
  }
  function simlogUnitTable(section, data) {
    const columns = simlogStateColumns[section] || [];
    const rows = simlogSectionRows(section, data);
    const wrap = node("div", undefined, "simlog-table-wrap");
    wrap.append(node("h4", `${t(simlogCategoryKeys[section])} (${rows.length})`));
    if (!rows.length) return wrap;
    const table = node("table", undefined, "simlog-table");
    const head = node("thead");
    const headRow = node("tr");
    for (const field of columns) {
      headRow.append(node("th", t(simlogColumnKeys[field] || "unavailable")));
    }
    head.append(headRow);
    const body = node("tbody");
    const flagField = simlogFlagFields[section];
    for (const row of rows) {
      const tr = node("tr");
      if (flagField && row[flagField]) tr.className = "simlog-flag-row";
      for (const field of columns) {
        tr.append(node("td", simlogCell(field, row[field])));
      }
      body.append(tr);
    }
    table.append(head, body);
    wrap.append(table);
    return wrap;
  }
  function simlogMetricBlock(titleKey, entries) {
    const wrap = node("div", undefined, "simlog-metrics-wrap");
    wrap.append(node("h4", t(titleKey)));
    const dl = node("dl", undefined, "metrics");
    for (const [key, value] of entries) {
      const group = node("div");
      group.append(node("dt", t(key)), node("dd", value));
      dl.append(group);
    }
    wrap.append(dl);
    return wrap;
  }
  function simlogCurrentState(data) {
    const root = node("div", undefined, "simlog-current-body");
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      root.append(node("p", t("simlog_state_unavailable"), "empty"));
      return root;
    }
    const ship = data.ship && typeof data.ship === "object" ? data.ship : {};
    const world = data.world && typeof data.world === "object" ? data.world : {};
    const weapons = data.weapons && typeof data.weapons === "object" ? data.weapons : {};
    const downed = Object.keys(ship.stations || {}).filter((key) => ship.stations[key]);
    root.append(simlogMetricBlock("simlog_own", [
      ["position", `${unit(ship.x, "NM")} / ${unit(ship.y, "NM")}`],
      ["course", unit(ship.course, "\u00b0", 0)],
      ["speed", unit(ship.speed, "kn")],
      ["simlog_col_damage", unit(ship.damage, "%")],
      ["simlog_col_sunk", simlogCell("sunk", ship.sunk)],
    ]));
    if (downed.length) {
      root.append(node("p", `${t("simlog_stations_down")}: ${downed.join(", ")}`, "simlog-note-danger"));
    }
    root.append(simlogMetricBlock("simlog_world", [
      ["world_clock", number(world.hour, 1)],
      ["sea_state", String(world.sea_state ?? t("unavailable"))],
      ["night", simlogCell("night", world.night)],
      ["simlog_mission_time", `${Math.round(data.mission_t ?? 0)} s`],
      ["time_scale", `x${data.timescale ?? 1}`],
      ["simlog_result", data.result ? String(data.result) : "-"],
    ]));
    root.append(simlogMetricBlock("simlog_weapons", [
      ["torpedoes", number(weapons.torpedoes, 0)],
      ["vls", number(weapons.vls, 0)],
      ["ciws", number(weapons.ciws, 0)],
      ["aa", number(weapons.aa, 0)],
      ["chaff", unit(weapons.chaff_cd, "s", 1)],
    ]));
    for (const section of simlogStateSections) {
      root.append(simlogUnitTable(section, data));
    }
    return root;
  }
  function simlogMapItems(data) {
    const items = [];
    const add = (section, value, index, label) => {
      if (!hasPosition(value)) return;
      const [domain, color] = simlogMapStyles[section];
      const identity = value.id ?? value.seq ?? index + 1;
      items.push({ section, value, domain, color, x: value.x, y: value.y,
        label: label || `${t(simlogCategoryKeys[section])} ${identity}` });
    };
    if (data.ship && typeof data.ship === "object") add("ship", data.ship, 0, t("simlog_own"));
    for (const section of simlogStateSections) {
      simlogSectionRows(section, data).forEach((value, index) => add(section, value, index));
    }
    return items;
  }
  function simlogMapBounds(items) {
    if (simlogMapFit === "world" && finite(chart?.size_nm) && chart.size_nm > 0) {
      return { left: 0, right: chart.size_nm, top: 0, bottom: chart.size_nm };
    }
    if (!items.length) return { left: 0, right: 1, top: 0, bottom: 1 };
    const minX = Math.min(...items.map((item) => item.x));
    const maxX = Math.max(...items.map((item) => item.x));
    const minY = Math.min(...items.map((item) => item.y));
    const maxY = Math.max(...items.map((item) => item.y));
    const span = Math.max(10, maxX - minX, maxY - minY);
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const radius = span * .58;
    return { left: centerX - radius, right: centerX + radius,
      top: centerY - radius, bottom: centerY + radius };
  }
  function simlogMapLabel(item) {
    const parts = [item.label];
    if (finite(item.value.course)) parts.push(`${number(item.value.course, 0)}\u00b0`);
    const speed = finite(item.value.speed) ? item.value.speed : item.value.speed_kn;
    if (finite(speed)) parts.push(`${number(speed, 1)} kn`);
    return parts.join(" \u00b7 ");
  }
  function queueSimlogMapDraw() {
    if (simlogMapDrawQueued) return;
    simlogMapDrawQueued = true;
    requestAnimationFrame(() => { simlogMapDrawQueued = false; drawSimlogMap(); });
  }
  function drawSimlogMap() {
    if (!simlogMapData || !$("simlog-map-dialog").open) return;
    const width = simlogMapCanvas.clientWidth;
    const height = simlogMapCanvas.clientHeight;
    if (!width || !height) return;
    resizeCanvas(simlogMapCanvas, simlogMapCtx, width, height);
    const context = simlogMapCtx;
    context.fillStyle = "#071117";
    context.fillRect(0, 0, width, height);
    const items = simlogMapItems(simlogMapData);
    const bounds = simlogMapBounds(items);
    const pad = Math.max(24, Math.min(width, height) * .06);
    const scale = Math.max(.0001, Math.min((width - pad * 2) / Math.max(.001, bounds.right - bounds.left),
      (height - pad * 2) / Math.max(.001, bounds.bottom - bounds.top)));
    const contentWidth = (bounds.right - bounds.left) * scale;
    const contentHeight = (bounds.bottom - bounds.top) * scale;
    const offsetX = (width - contentWidth) / 2;
    const offsetY = (height - contentHeight) / 2;
    const point = (x, y) => [offsetX + (x - bounds.left) * scale, offsetY + (y - bounds.top) * scale];
    context.strokeStyle = "#233741";
    context.lineWidth = 1;
    context.beginPath();
    for (let index = 0; index <= 5; index += 1) {
      const x = offsetX + contentWidth * index / 5;
      const y = offsetY + contentHeight * index / 5;
      context.moveTo(x, offsetY); context.lineTo(x, offsetY + contentHeight);
      context.moveTo(offsetX, y); context.lineTo(offsetX + contentWidth, y);
    }
    context.stroke();
    if (chart && Array.isArray(chart.landmasses)) {
      context.fillStyle = "#283c40";
      context.strokeStyle = "#607e78";
      for (const land of chart.landmasses) {
        if (!land.points.length) continue;
        context.beginPath();
        land.points.forEach(([x, y], index) => {
          const [px, py] = point(x, y);
          if (!index) context.moveTo(px, py); else context.lineTo(px, py);
        });
        context.closePath(); context.fill(); context.stroke();
      }
    }
    context.strokeStyle = "#58707c";
    context.setLineDash([5, 5]);
    context.strokeRect(offsetX, offsetY, contentWidth, contentHeight);
    context.setLineDash([]);
    const fontSize = Math.max(11, parseFloat(getComputedStyle(document.documentElement).fontSize) * .68);
    context.font = `${fontSize}px ui-monospace, monospace`;
    const plotted = items.map((item) => {
      const [x, y] = point(item.x, item.y);
      const course = item.value.course;
      const angle = finite(course) ? course * Math.PI / 180 : null;
      const endX = angle === null ? x : x + Math.sin(angle) * 24;
      const endY = angle === null ? y : y - Math.cos(angle) * 24;
      return { item, x, y, endX, endY };
    });
    const occupied = plotted.map(({ x, y, endX, endY }, index) => ({
      x: Math.min(x, endX) - 9, y: Math.min(y, endY) - 9,
      right: Math.max(x, endX) + 9, bottom: Math.max(y, endY) + 9, index,
    }));
    occupied.push({ x: width - 70, y: 0, right: width, bottom: 48, index: -1 });
    for (const { item, x, y, endX, endY } of plotted) {
      if (finite(item.value.course)) {
        context.strokeStyle = item.color;
        context.lineWidth = 1.4;
        context.beginPath(); context.moveTo(x, y); context.lineTo(endX, endY); context.stroke();
      }
      if (item.section === "ship") {
        context.fillStyle = item.color;
        context.beginPath(); context.arc(x, y, 3.5, 0, Math.PI * 2); context.fill();
      } else {
        drawSymbolOn(context, x, y, item.domain, item.color, 6);
      }
      if (item.value.sunk === true || item.value.dead === true) {
        context.strokeStyle = item.color;
        context.beginPath(); context.moveTo(x - 8, y - 8); context.lineTo(x + 8, y + 8); context.stroke();
      }
    }
    plotted.forEach(({ item }, index) => {
      const label = simlogMapLabel(item);
      const textWidth = context.measureText(label).width;
      const footprint = occupied[index];
      const candidates = [[footprint.right + 4, footprint.y + fontSize],
        [footprint.right + 4, footprint.bottom + fontSize + 3],
        [footprint.x - textWidth - 4, footprint.y + fontSize],
        [x - textWidth / 2, footprint.bottom + fontSize + 4]];
      const candidate = candidates.map(([tx, ty]) => ({ x: tx, y: ty - fontSize, right: tx + textWidth, bottom: ty + 3, ty }))
        .find((box) => box.x >= 3 && box.y >= 3 && box.right <= width - 3 && box.bottom <= height - 3 &&
          occupied.every((other) => box.right < other.x || box.x > other.right ||
            box.bottom < other.y || box.y > other.bottom));
      if (candidate) {
        context.fillStyle = item.color;
        context.fillText(label, candidate.x, candidate.ty);
        occupied.push({ ...candidate, index: -1 });
      }
    });
    context.fillStyle = "#c6d6d9";
    context.fillText(t("north"), width - 28, 20);
    context.strokeStyle = "#c6d6d9";
    context.beginPath(); context.moveTo(width - 22, 42); context.lineTo(width - 22, 25); context.lineTo(width - 27, 32); context.moveTo(width - 22, 25); context.lineTo(width - 17, 32); context.stroke();
  }
  function closeSimlogMap() {
    const dialog = $("simlog-map-dialog");
    if (dialog.open) dialog.close();
    simlogMapData = null;
    simlogMapSeq = null;
    simlogMapLatest = false;
    $("simlog-map-units").replaceChildren();
    releaseCanvas(simlogMapCanvas);
  }
  function openSimlogMap(data, stamp, seq, latest = false) {
    if (!data || typeof data !== "object") return;
    const dialog = $("simlog-map-dialog");
    if (!dialog.open) simlogMapFit = "world";
    simlogMapData = data;
    simlogMapSeq = seq;
    simlogMapLatest = latest;
    const items = simlogMapItems(data);
    $("simlog-map-stamp").textContent = stamp;
    $("simlog-map-count").textContent = t("simlog_map_count", { count: number(items.length, 0) });
    $("simlog-map-units").replaceChildren(...items.map((item) => {
      const entry = node("li", `${simlogMapLabel(item)}: ${number(item.x, 1)} / ${number(item.y, 1)} NM`);
      entry.style.setProperty("--unit-color", item.color);
      return entry;
    }));
    if (!dialog.open) dialog.showModal();
    queueSimlogMapDraw();
  }
  function simlogSummary(data) {
    if (!data || typeof data !== "object") return "";
    const parts = [`mission ${Math.round(data.mission_t ?? 0)}s`];
    const ship = data.ship;
    if (ship && typeof ship === "object") parts.push(`ship ${ship.x ?? "?"} / ${ship.y ?? "?"} dmg ${ship.damage ?? "?"}`);
    for (const key of simlogStateSections) {
      if (Array.isArray(data[key]) && data[key].length) parts.push(`${data[key].length}x${key}`);
    }
    return parts.join("  ");
  }
  function renderSimlog(rows) {
    const status = $("simlog-status");
    const list = $("simlog-list");
    const current = $("simlog-current");
    $("simlog-count").textContent = String(rows.length);
    if (!rows.length) {
      latestSimlogState = null;
      $("simlog-current-map").disabled = true;
      closeSimlogMap();
      status.hidden = false;
      status.textContent = t("simlog_empty");
      current.replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
      list.replaceChildren();
      return;
    }
    status.hidden = true;
    const lastState = [...rows].reverse().find((row) => row.cat === "state");
    latestSimlogState = lastState || null;
    $("simlog-current-map").disabled = !lastState;
    current.replaceChildren(simlogCurrentState(lastState ? lastState.data : null));
    const openSnapshots = new Set([...list.querySelectorAll("details[open][data-seq]")]
      .map((detail) => detail.dataset.seq));
    const oldScroll = list.scrollTop;
    const followedBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 24;
    list.replaceChildren(...rows.map((row) => {
      const item = node("li", undefined, "simlog-entry");
      item.append(
        node("span", `${row.stamp}  T+${Math.floor(row.t)}s`, "simlog-stamp"),
        node("span", simlogTags[row.cat] || row.cat.toUpperCase().slice(0, 5), "simlog-cat"));
      if (row.cat === "state" && row.data) {
        const details = node("details", undefined, "simlog-snapshot");
        details.dataset.seq = String(row.seq);
        details.open = openSnapshots.has(String(row.seq));
        details.append(node("summary",
          `${t("simlog_snapshot")} \u2013 ${simlogSummary(row.data)}`));
        const mapButton = node("button", t("simlog_map_open"), "quiet simlog-snapshot-map");
        mapButton.type = "button";
        mapButton.addEventListener("click", () => openSimlogMap(
          row.data, `${row.stamp} / T+${Math.floor(row.t)}s`, row.seq));
        details.append(mapButton);
        details.append(simlogCurrentState(row.data));
        item.append(details);
      } else {
        item.append(node("span", row.text, "simlog-text"));
      }
      return item;
    }));
    list.scrollTop = followedBottom ? list.scrollHeight : Math.min(oldScroll,
      Math.max(0, list.scrollHeight - list.clientHeight));
    if ($("simlog-map-dialog").open) {
      const mapped = simlogMapLatest ? lastState : rows.find(
        (row) => row.seq === simlogMapSeq && row.cat === "state");
      if (mapped) openSimlogMap(mapped.data,
        `${mapped.stamp} / T+${Math.floor(mapped.t)}s`, mapped.seq, simlogMapLatest);
      else closeSimlogMap();
    }
  }
  async function loadSimlog() {
    if (!simlogActive()) return;
    if (protocolMode === "v2") {
      latestSimlogState = null;
      $("simlog-current-map").disabled = true;
      closeSimlogMap();
      $("simlog-status").hidden = false;
      $("simlog-status").textContent = t("simlog_unavailable");
      $("simlog-current").replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
      $("simlog-list").replaceChildren();
      $("simlog-count").textContent = "";
      return;
    }
    const now = performance.now();
    if (now - lastSimlogFetch < 2000) return;
    lastSimlogFetch = now;
    try {
      const rows = await request("/simlog");
      if (!simlogActive()) return;
      validateSimlog(rows);
      renderSimlog(rows);
    } catch (_) {
      latestSimlogState = null;
      $("simlog-current-map").disabled = true;
      closeSimlogMap();
      $("simlog-status").hidden = false;
      $("simlog-status").textContent = t("simlog_unavailable");
      $("simlog-list").replaceChildren();
    }
  }

  function renderSound() {
    $("sound").textContent = t(soundEnabled ? "sound_on" : "sound_off");
    $("sound").setAttribute("aria-pressed", String(soundEnabled));
  }

  function playAlert() {
    if (!soundEnabled || !audio || audio.state !== "running" || document.hidden) return;
    const volume = Number($("volume").value) / 100;
    if (!volume) return;
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    const now = audio.currentTime;
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(660, now);
    oscillator.frequency.setValueAtTime(880, now + .12);
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(volume * .12, now + .015);
    gain.gain.setValueAtTime(volume * .12, now + .18);
    gain.gain.linearRampToValueAtTime(0, now + .26);
    oscillator.connect(gain);
    gain.connect(audio.destination);
    oscillator.start(now);
    oscillator.stop(now + .28);
    oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
  }

  function chartGeometry() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const scale = Math.min(width, height) / chart.size_nm * .9 * view.zoom;
    return { width, height, scale, point: (x, y) => [width / 2 + (x - view.x) * scale, height / 2 + (y - view.y) * scale] };
  }

  function fitChart() {
    view.x = chart.size_nm / 2;
    view.y = chart.size_nm / 2;
    view.zoom = 1;
    view.follow = false;
    view.initialized = true;
    $("follow").setAttribute("aria-pressed", "false");
    queueDraw();
  }

  function queueDraw() {
    if (drawQueued) return;
    drawQueued = true;
    requestAnimationFrame(() => { drawQueued = false; drawChart(); });
  }

  function releaseCanvas(element) {
    if (element.width !== 1 || element.height !== 1) {
      element.width = 1;
      element.height = 1;
    }
  }

  function resizeCanvas(element, context, width, height) {
    const requested = Math.min(window.devicePixelRatio || 1, 3);
    const dpr = Math.min(requested, Math.sqrt(maxCanvasPixels / Math.max(1, width * height)));
    const pixelWidth = Math.max(1, Math.round(width * dpr));
    const pixelHeight = Math.max(1, Math.round(height * dpr));
    if (element.width !== pixelWidth || element.height !== pixelHeight) {
      element.width = pixelWidth;
      element.height = pixelHeight;
    }
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    return dpr;
  }

  function drawChart() {
    if (!snapshot || !chartMatches(snapshot) || $("panel-operations").hidden) return;
    const own = snapshot.ownship;
    const ownPosition = hasPosition(own);
    if (view.follow && ownPosition) { view.x = own.x; view.y = own.y; }
    const { width, height, scale, point } = chartGeometry();
    if (!width || !height) return;
    resizeCanvas(canvas, ctx, width, height);
    ctx.fillStyle = "#0c1c26";
    ctx.fillRect(0, 0, width, height);
    const fontSize = Math.max(12, parseFloat(getComputedStyle(document.documentElement).fontSize) * .74);
    ctx.font = `${fontSize}px ui-monospace, monospace`;
    const left = view.x - width / (2 * scale);
    const right = view.x + width / (2 * scale);
    const top = view.y - height / (2 * scale);
    const bottom = view.y + height / (2 * scale);
    const rough = 110 / scale;
    const power = 10 ** Math.floor(Math.log10(rough));
    const step = [1, 2, 5, 10].find((n) => n * power >= rough) * power;
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#233741";
    ctx.fillStyle = "#8ba4ad";
    ctx.beginPath();
    for (let x = Math.ceil(left / step) * step; x < right; x += step) {
      const px = point(x, 0)[0];
      ctx.moveTo(px, 0); ctx.lineTo(px, height);
      const label = number(x || 0, step < 1 ? 1 : 0);
      if (px + 4 + ctx.measureText(label).width <= width - 4) ctx.fillText(label, px + 4, height - 9);
    }
    for (let y = Math.ceil(top / step) * step; y < bottom; y += step) {
      const py = point(0, y)[1];
      ctx.moveTo(0, py); ctx.lineTo(width, py);
      if (py >= fontSize + 5 && py < height - fontSize - 12) ctx.fillText(number(y || 0, step < 1 ? 1 : 0), 6, py - 5);
    }
    ctx.stroke();
    ctx.fillStyle = "#283c40";
    ctx.strokeStyle = "#607e78";
    for (const land of chart.landmasses) {
      // Cull in world coordinates before allocating/translating polygon vertices.
      if (!land.points.length || land.points.every(([x]) => x < left) || land.points.every(([x]) => x > right) ||
          land.points.every(([, y]) => y < top) || land.points.every(([, y]) => y > bottom)) continue;
      ctx.beginPath();
      land.points.forEach(([x, y], index) => { const [px, py] = point(x, y); if (!index) ctx.moveTo(px, py); else ctx.lineTo(px, py); });
      ctx.closePath(); ctx.fill(); ctx.stroke();
    }
    const [zeroX, zeroY] = point(0, 0);
    ctx.strokeStyle = "#58707c";
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(zeroX, zeroY, chart.size_nm * scale, chart.size_nm * scale);
    ctx.setLineDash([]);
    chartHits = [];
    // Status-only snapshots intentionally omit ownship geometry. Null is not 0.
    const [ox, oy] = ownPosition ? point(own.x, own.y) : [null, null];
    const rayLength = ownPosition ? Math.hypot(width, height) + Math.hypot(ox - width / 2, oy - height / 2) : null;
    const radar = v2State?.role === "opz" ? v2State.opz.radar : null;
    if (ownPosition && radar?.live && (radar.surface || radar.air)) {
      ctx.strokeStyle = "#426b62";
      ctx.globalAlpha = .55;
      for (const fraction of [.25, .5, .75, 1]) {
        ctx.beginPath(); ctx.arc(ox, oy, radar.range_nm * fraction * scale, 0, Math.PI * 2); ctx.stroke();
      }
      const sweep = currentOpzSweepBearing() * Math.PI / 180;
      ctx.strokeStyle = "#8de6c4";
      ctx.beginPath(); ctx.moveTo(ox, oy);
      ctx.lineTo(ox + Math.sin(sweep) * radar.range_nm * scale,
        oy - Math.cos(sweep) * radar.range_nm * scale); ctx.stroke();
      ctx.globalAlpha = 1;
    }
    // No integration, dead reckoning or animation of tracks: only published fixes.
    for (const track of snapshot.tracks) {
      const color = colors[track.affiliation] || colors.UNKNOWN;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = track.ref === selected ? 2 : 1;
      if (!finite(track.x) || !finite(track.y)) {
        if (!ownPosition || !finite(track.bearing)) continue;
        const angle = track.bearing * Math.PI / 180 - Math.PI / 2;
        const uncertainty = finite(track.bearing_uncertainty_deg) ? Math.min(180, Math.max(0, track.bearing_uncertainty_deg)) * Math.PI / 180 : 0;
        if (uncertainty) {
          ctx.globalAlpha = track.ref === selected ? .13 : .055;
          ctx.beginPath(); ctx.moveTo(ox, oy); ctx.arc(ox, oy, rayLength, angle - uncertainty, angle + uncertainty); ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1;
        }
        ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox + Math.cos(angle) * rayLength, oy + Math.sin(angle) * rayLength);
        if (track.ref === selected) { ctx.strokeStyle = "#a1e7cc"; ctx.lineWidth = 4; ctx.stroke(); }
        if (track.ref === snapshot.crew_target) { ctx.strokeStyle = "#e9eee8"; ctx.lineWidth = 6; ctx.setLineDash([14, 14]); ctx.stroke(); }
        if (track.ref === snapshot.proposal?.ref) { ctx.strokeStyle = "#f3c577"; ctx.lineWidth = 7; ctx.setLineDash([2, 10]); ctx.stroke(); }
        ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([6, 6]); ctx.stroke(); ctx.setLineDash([]);
        // A ray is intentionally not pickable as a fictitious contact position.
        continue;
      }
      const [x, y] = point(track.x, track.y);
      const radius = finite(track.range_uncertainty_nm) ? Math.max(0, track.range_uncertainty_nm) * scale : 0;
      if (x + radius < -60 || y + radius < -60 || x - radius > width + 60 || y - radius > height + 60) continue;
      if (radius > 1) {
        ctx.globalAlpha = .16; ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.stroke(); ctx.globalAlpha = 1;
      }
      if (radar && track.source.startsWith("RADAR")) {
        ctx.strokeStyle = color; ctx.globalAlpha = .18;
        for (const glow of [8, 13, 19]) { ctx.beginPath(); ctx.arc(x, y, glow, 0, Math.PI * 2); ctx.stroke(); }
        ctx.globalAlpha = 1;
      }
      drawSymbol(x, y, track.domain, color, fontSize * .65);
      if (track.ref === snapshot.crew_target) {
        ctx.strokeStyle = "#e9eee8";
        for (const r of [18, 21]) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke(); }
      }
      if (track.ref === snapshot.proposal?.ref) {
        ctx.strokeStyle = "#f3c577"; ctx.setLineDash([4, 3]);
        ctx.beginPath(); ctx.moveTo(x, y - 28); ctx.lineTo(x + 28, y); ctx.lineTo(x, y + 28); ctx.lineTo(x - 28, y); ctx.closePath(); ctx.stroke(); ctx.setLineDash([]);
      }
      if (track.ref === selected) { ctx.strokeStyle = "#a1e7cc"; ctx.lineWidth = 2; ctx.strokeRect(x - 25, y - 25, 50, 50); }
      ctx.fillStyle = color;
      ctx.fillText(String(track.label ?? ""), x + 31, y - 9, Math.max(60, width - x - 37));
      chartHits.push({ ref: track.ref, x, y });
    }
    // Independent sonar fixes share their parent track identity and are rebuilt
    // from the current snapshot on every draw, so stale markers cannot be hit.
    for (const track of snapshot.tracks) {
      for (const fix of track.fixes) {
        const [x, y] = point(fix.x, fix.y);
        const radius = Math.max(2, fix.uncertainty_nm * scale);
        if (x + radius < -60 || y + radius < -60 || x - radius > width + 60 || y - radius > height + 60) continue;
        ctx.strokeStyle = fix.source === "PING" ? "#59d8dc" : fix.source === "TMA" ? "#f3c577" : "#83c99a";
        ctx.lineWidth = track.ref === selected ? 2 : 1;
        ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(x - 6, y); ctx.lineTo(x + 6, y); ctx.moveTo(x, y - 6); ctx.lineTo(x, y + 6); ctx.stroke();
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fillText(`${String(track.label ?? "")} ${fix.source}`, x + 9, y - 8, Math.max(50, width - x - 13));
        chartHits.push({ ref: track.ref, x, y });
      }
    }
    if (ownPosition) {
      ctx.save();
      ctx.translate(ox, oy);
      ctx.strokeStyle = "#a1e7cc"; ctx.fillStyle = "#183e3c"; ctx.lineWidth = 2;
      ctx.beginPath();
      if (finite(own.course)) {
        ctx.rotate(own.course * Math.PI / 180);
        ctx.moveTo(0, -13); ctx.lineTo(7, 9); ctx.lineTo(-7, 9); ctx.closePath(); ctx.fill(); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, -16); ctx.lineTo(0, -35); ctx.stroke();
      } else {
        ctx.arc(0, 0, 8, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();
      ctx.fillStyle = "#a1e7cc"; ctx.fillText(t("ownship"), ox + 15, oy + 18);
    }
    const helo = own.helo;
    if (hasPosition(helo) && ["AUF", "ZURUECK"].includes(helo.state)) {
      const [hx, hy] = point(helo.x, helo.y);
      if (hx > -30 && hy > -30 && hx < width + 30 && hy < height + 30) {
        drawSymbol(hx, hy, "AIR", "#a1e7cc", 8);
        ctx.fillStyle = "#a1e7cc"; ctx.fillText(t("helicopter"), hx + 15, hy + 5);
      }
    }
    ctx.fillStyle = "#c6d6d9"; ctx.fillText(t("north"), width - 27, 25);
    ctx.strokeStyle = "#c6d6d9"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(width - 23, 47); ctx.lineTo(width - 23, 31); ctx.lineTo(width - 27, 37); ctx.moveTo(width - 23, 31); ctx.lineTo(width - 19, 37); ctx.stroke();
    $("chart-scale").textContent = t("chart_scale", { distance: number(step, step < 1 ? 1 : 0) });
  }

  function drawSymbolOn(context, x, y, domain, color, size) {
    context.strokeStyle = color; context.lineWidth = 1.8; context.beginPath();
    if (domain === "SURFACE") context.rect(x - size, y - size * .65, size * 2, size * 1.3);
    else if (domain === "AIR") { context.arc(x, y + size / 2, size, Math.PI, Math.PI * 2); }
    else if (domain === "SUBSURFACE") { context.arc(x, y - size / 2, size, 0, Math.PI); }
    else { context.moveTo(x, y - size); context.lineTo(x + size, y); context.lineTo(x, y + size); context.lineTo(x - size, y); context.closePath(); }
    context.stroke();
  }
  function drawSymbol(x, y, domain, color, size) {
    drawSymbolOn(ctx, x, y, domain, color, size);
  }

  function renderLookoutStatus() {
    const environment = snapshot?.environment;
    $("lookout-sea").textContent = finite(environment?.sea_state) ? number(environment.sea_state, 0) : t("unavailable");
    $("lookout-light").textContent = typeof environment?.is_night === "boolean" ? t(environment.is_night ? "night" : "day") : t("unavailable");
    $("lookout-range").textContent = t("lookout_range", { distance: number(lookoutView.rangeNm, 0) });
    $("lookout-scope").dataset.light = environment?.is_night === true ? "night" : environment?.is_night === false ? "day" : "unknown";
    $("lookout-own").textContent = t("lookout_own_course", { course: unit(snapshot?.ownship?.course, "\u00b0", 0) });
    if (!$("panel-lookout").hidden) {
      $("lookout-observations").replaceChildren(...(snapshot?.tracks || []).map((track) => node(
        "li", `${String(track.label ?? "")}: ${t(hasPosition(track) ? "lookout_positioned" : "lookout_bearing_report")} / ${unit(track.bearing, "\u00b0", 0)} / ${unit(track.range_nm, "NM")}`)));
    }
  }

  function queueLookoutDraw() {
    if (lookoutDrawQueued) return;
    lookoutDrawQueued = true;
    requestAnimationFrame(() => { lookoutDrawQueued = false; drawLookout(); });
  }

  function drawLookout() {
    if (!snapshot || $("panel-lookout").hidden) return;
    const width = lookoutCanvas.clientWidth;
    const height = lookoutCanvas.clientHeight;
    if (!width || !height) return;
    resizeCanvas(lookoutCanvas, lookoutCtx, width, height);
    const environment = snapshot.environment;
    lookoutCtx.fillStyle = environment?.is_night === true ? "#071117" : environment?.is_night === false ? "#102833" : "#0b151c";
    lookoutCtx.fillRect(0, 0, width, height);
    const own = snapshot.ownship;
    if (!hasPosition(own)) return;
    const fontSize = Math.max(11, parseFloat(getComputedStyle(document.documentElement).fontSize) * .7);
    lookoutCtx.font = `${fontSize}px ui-monospace, monospace`;
    lookoutCtx.lineWidth = 1;
    const centerX = width / 2;
    const centerY = height / 2;
    const compact = height < 120;
    const radius = Math.max(8, Math.min(width, height) / 2 - (compact ? 3 : Math.max(24, fontSize * 2.4)));
    const scale = radius / lookoutView.rangeNm;
    lookoutCtx.strokeStyle = environment?.is_night === true ? "#294452" : "#496976";
    lookoutCtx.fillStyle = environment?.is_night === true ? "#7895a0" : "#adc3c9";
    for (const fraction of compact ? [.5, 1] : [.25, .5, .75, 1]) {
      const ringRadius = radius * fraction;
      lookoutCtx.beginPath();
      lookoutCtx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2);
      lookoutCtx.stroke();
      if (!compact) {
        const label = `${number(lookoutView.rangeNm * fraction, lookoutView.rangeNm < 10 ? 1 : 0)} NM`;
        const labelWidth = lookoutCtx.measureText(label).width;
        lookoutCtx.fillText(label, Math.max(2, centerX - labelWidth / 2), Math.max(fontSize, centerY - ringRadius + fontSize));
      }
    }
    // All geometry below is derived from the current detached snapshot only.
    for (const track of snapshot.tracks) {
      const color = colors[track.affiliation] || colors.UNKNOWN;
      lookoutCtx.strokeStyle = color;
      lookoutCtx.fillStyle = color;
      if (finite(track.x) && finite(track.y)) {
        const dx = track.x - own.x;
        const dy = track.y - own.y;
        if (Math.hypot(dx, dy) > lookoutView.rangeNm) continue;
        const x = centerX + dx * scale;
        const y = centerY + dy * scale;
        lookoutCtx.beginPath();
        lookoutCtx.arc(x, y, compact ? 2 : 4, 0, Math.PI * 2);
        lookoutCtx.fill();
        const label = String(track.label ?? "");
        if (!compact && label && x + 9 < width - 2) lookoutCtx.fillText(label, x + 8, Math.max(fontSize, Math.min(height - 3, y - 7)), Math.max(0, width - x - 11));
        continue;
      }
      if (!finite(track.bearing)) continue;
      const angle = track.bearing * Math.PI / 180 - Math.PI / 2;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;
      const uncertainty = finite(track.bearing_uncertainty_deg) ? Math.min(180, Math.max(0, track.bearing_uncertainty_deg)) * Math.PI / 180 : 0;
      if (uncertainty) {
        lookoutCtx.globalAlpha = .35;
        lookoutCtx.beginPath();
        lookoutCtx.arc(centerX, centerY, radius, angle - uncertainty, angle + uncertainty);
        lookoutCtx.stroke();
        lookoutCtx.globalAlpha = 1;
      }
      lookoutCtx.save();
      lookoutCtx.translate(x, y);
      lookoutCtx.rotate(angle + Math.PI / 2);
      lookoutCtx.beginPath();
      const marker = compact ? 4 : 9;
      lookoutCtx.moveTo(0, marker);
      lookoutCtx.lineTo(-marker * .67, -marker / 3);
      lookoutCtx.lineTo(marker * .67, -marker / 3);
      lookoutCtx.closePath();
      lookoutCtx.fill();
      lookoutCtx.restore();
    }
    lookoutCtx.save();
    lookoutCtx.translate(centerX, centerY);
    lookoutCtx.strokeStyle = "#a1e7cc";
    lookoutCtx.fillStyle = "#183e3c";
    lookoutCtx.lineWidth = 2;
    if (finite(own.course)) {
      lookoutCtx.rotate(own.course * Math.PI / 180);
      lookoutCtx.beginPath();
      const shipSize = compact ? 4 : 12;
      lookoutCtx.moveTo(0, -shipSize);
      lookoutCtx.lineTo(shipSize * .58, shipSize * .67);
      lookoutCtx.lineTo(-shipSize * .58, shipSize * .67);
      lookoutCtx.closePath();
      lookoutCtx.fill();
      lookoutCtx.stroke();
      lookoutCtx.beginPath();
      lookoutCtx.moveTo(0, -(compact ? 5 : 15));
      lookoutCtx.lineTo(0, -Math.min(compact ? 12 : 48, radius * .55));
      lookoutCtx.stroke();
    } else {
      lookoutCtx.beginPath();
      lookoutCtx.arc(0, 0, compact ? 3 : 8, 0, Math.PI * 2);
      lookoutCtx.stroke();
    }
    lookoutCtx.restore();
    if (!compact) {
      lookoutCtx.fillStyle = "#c6d6d9";
      lookoutCtx.fillText(t("north"), width - Math.max(18, lookoutCtx.measureText(t("north")).width + 6), fontSize + 5);
    }
  }

  function changeLookoutRange(direction) {
    const current = lookoutRanges.indexOf(lookoutView.rangeNm);
    const index = Math.max(0, Math.min(lookoutRanges.length - 1, current + direction));
    lookoutView.rangeNm = lookoutRanges[index];
    renderLookoutStatus();
    queueLookoutDraw();
  }

  function zoom(factor, px = canvas.clientWidth / 2, py = canvas.clientHeight / 2) {
    if (!chart || !snapshot) return;
    const before = chartGeometry();
    const newZoom = Math.max(.5, Math.min(256, view.zoom * factor));
    if (!view.follow) {
      view.x += (px - before.width / 2) / before.scale * (1 - view.zoom / newZoom);
      view.y += (py - before.height / 2) / before.scale * (1 - view.zoom / newZoom);
    }
    view.zoom = newZoom;
    queueDraw();
  }

  $("pair-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if ($("pair-submit").disabled || !$("pair-form").reportValidity()) return;
    $("pair-submit").disabled = true;
    $("pair-error").textContent = "";
    const code = $("code").value.toUpperCase();
    const name = $("name").value.trim();
    $("code").value = "";
    try {
      const body = protocolMode === "v2" ? { code, name } : { code };
      const result = await request("/pair", { method: "POST", body, auth: false,
        version: protocolMode === "v2" ? 2 : 1 });
      if (protocolMode === "v2") {
        acceptSession(result);
      } else {
        if (!result || typeof result.token !== "string" || !result.token) throw new Error("pair");
        token = result.token;
      }
      generation += 1;
      failures = 0;
      $("pairing").hidden = true;
      $("disconnect").hidden = false;
      setConnection(protocolMode === "v2" && session.station === null ? "lobby" : "syncing");
      clearTimeout(pollTimer);
      poll();
    } catch (_) {
      $("pair-error").textContent = t("pair_failed");
      $("code").focus();
    } finally { $("pair-submit").disabled = false; }
  });
  $("language").addEventListener("change", () => loadLanguage($("language").value === "de" ? "de" : "en"));
  $("volume").addEventListener("input", () => {
    if (sonarAudioGain) sonarAudioGain.gain.value = sonarGainValue();
  });
  $("analysis-filter").addEventListener("input", renderContactAnalysis);
  $("analysis-category").addEventListener("change", renderContactAnalysis);
  $("sonar-broadband").addEventListener("click", (event) => {
    if (session?.station !== "sonar" || !stationActionAvailable() || sonarVisualPage !== "broadband") return;
    const canvas = $("sonar-broadband");
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = (event.clientX - bounds.left) * canvas.clientWidth / bounds.width;
    const y = (event.clientY - bounds.top) * canvas.clientHeight / bounds.height;
    const area = plotArea(canvas.clientWidth, canvas.clientHeight);
    if (x < area.left || x >= area.left + area.width ||
        y < area.top || y >= area.top + area.height) return;
    sendStationAction("sonar_set_listen_bearing", {
      bearing: (x - area.left) / area.width * 360,
    });
  });
  $("disconnect").addEventListener("click", async () => {
    const csrf = session?.csrf;
    try {
      if (protocolMode === "v2" && csrf) await request("/logout", {
        method: "POST", auth: true, version: 2, csrf,
      });
    } catch (_) {
      // Local tactical data is cleared even when the host cannot confirm logout.
    } finally {
      forgetSession();
      $("code").focus();
    }
  });
  const releaseActiveStation = () => session?.station && mutateStation("/stations/release", {
    station: session.station, station_generation: session.station_generation,
    active_generation: session.active_generation,
  });
  $("release-station").addEventListener("click", releaseActiveStation);
  $("mobile-release-station").addEventListener("click", releaseActiveStation);
  const openStationPicker = () => {
    if (!session?.station || session.requested_station !== null || stationMutation) return;
    stationPickerOpen = true;
    renderLobby();
  };
  for (const id of ["add-station", "mobile-add-station", "workstation-add-station"]) {
    $(id).addEventListener("click", openStationPicker);
  }
  $("lobby-back").addEventListener("click", () => {
    stationPickerOpen = false;
    renderLobby();
  });
  for (const id of ["mobile-station", "workstation-station"]) {
    $(id).addEventListener("change", () => chooseStation($(id).value));
  }
  $("classification-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const classification = $("classification").value || null;
    if (protocolMode === "v2" && session?.station === "sonar") sendStationAction("sonar_classify", {ref: selected, classification});
    else if (protocolMode === "v2" && session?.station === "opz") sendStationAction("opz_classify", {ref: selected, classification});
    else sendCommand("classify", classification);
  });
  $("classification").addEventListener("change", renderActionState);
  $("sonar-release").addEventListener("click", () => {
    const track = selectedTrack();
    if (track) sendStationAction("sonar_set_release", {
      ref: track.ref, released: !track.released_to_opz,
    });
  });
  $("affiliation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (protocolMode === "v2" && session?.station === "opz") sendStationAction("opz_affiliate", {ref: selected, affiliation: $("affiliation").value});
    else sendCommand("affiliate", $("affiliation").value);
  });
  $("opz-radar-surface").addEventListener("change", () => sendStationAction("opz_set_radar", {domain: "surface", enabled: $("opz-radar-surface").checked}));
  $("opz-radar-air").addEventListener("change", () => sendStationAction("opz_set_radar", {domain: "air", enabled: $("opz-radar-air").checked}));
  $("opz-range").addEventListener("change", () => sendStationAction("opz_set_range", {range_nm: Number($("opz-range").value)}));
  $("opz-create-fusion").addEventListener("click", () => sendStationAction("opz_create_fusion", {refs: [...opzMarked]}));
  $("opz-mark").addEventListener("click", () => {
    const track = selectedTrack();
    if (!track || track.source === "FUSION") return;
    if (opzMarked.has(track.ref)) opzMarked.delete(track.ref); else if (opzMarked.size < 8) opzMarked.add(track.ref);
    renderActionState(); renderTracks(); queueDraw();
  });
  $("opz-dissolve").addEventListener("click", () => sendStationAction("opz_dissolve_fusion", {ref: selected}));
  $("opz-designate").addEventListener("click", () => {
    if (selected) sendStationAction("opz_designate_target", {ref: selected});
  });
  $("opz-suppress").addEventListener("click", () => {
    const track = selectedTrack();
    if (!track) return;
    if (opzSuppressed.has(track.ref)) opzSuppressed.delete(track.ref); else opzSuppressed.add(track.ref);
    const raw = v2State; if (raw) { snapshot = adaptV2State(raw); if (!selectedTrack()) selected = null; renderSnapshot(); }
  });
  $("opz-manage").addEventListener("change", () => {
    opzManage = $("opz-manage").checked;
    if (v2State) { snapshot = adaptV2State(v2State); renderSnapshot(); }
  });
  const numberAction = (formId, inputId, action, field, minimum, maximum) => {
    const form = $(formId);
    if (!form.reportValidity()) return;
    const value = $(inputId).valueAsNumber;
    if (!finite(value) || value < minimum || value > maximum) return;
    sendStationAction(action, {[field]: value});
  };
  for (const id of ["sonar-array-mode", "sonar-band", "sonar-bearing", "sonar-depth", "sonar-gain",
    "sonar-harmonic-input", "engine-telegraph", "engine-speed", "helicopter-x", "helicopter-y",
    "helicopter-dip-depth",
    "weapons-fire-target", "weapons-fire-depth", "helicopter-fire-target", "helicopter-fire-depth", "opz-fire-target"]) {
    $(id).addEventListener("input", () => stationDrafts.add(id));
    $(id).addEventListener("change", () => stationDrafts.add(id));
    if (id.includes("fire")) for (const eventName of ["input", "change"]) $(id).addEventListener(eventName, () => {
      clearFireConfirmation(); renderDirectFireControls();
    });
  }
  for (const button of document.querySelectorAll("[data-fire-action]")) button.addEventListener("click", () => activateDirectFire(button));
  $("sonar-control-page").addEventListener("change", renderSonarControlPage);
  for (const button of $("sonar-page-tabs").querySelectorAll("button")) {
    button.addEventListener("click", () => {
      sonarVisualPage = button.dataset.sonarVisual;
      $("sonar-control-page").value = ({environment: "array", active: "listen", broadband: "listen"}[sonarVisualPage] || "analysis");
      renderSonarControlPage();
      renderRoleVisuals(v2State?.role);
    });
    button.addEventListener("keydown", (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...$("sonar-page-tabs").querySelectorAll("button")];
      let index = buttons.indexOf(button);
      if (event.key === 'ArrowLeft') index = (index - 1 + buttons.length) % buttons.length;
      if (event.key === 'ArrowRight') index = (index + 1) % buttons.length;
      if (event.key === 'Home') index = 0;
      if (event.key === 'End') index = buttons.length - 1;
      buttons[index].click(); buttons[index].focus();
    });
  }
  $("sonar-bearing-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-bearing-form", "sonar-bearing", "sonar_set_listen_bearing", "bearing", 0, 359.99999999999994);
  });
  $("sonar-clear-focus").addEventListener("click", () => sendStationAction("sonar_clear_focus", {}));
  $("sonar-array-apply").addEventListener("click", () => sendStationAction("sonar_set_array_mode", {mode: $("sonar-array-mode").value}));
  $("sonar-tas").addEventListener("click", () => sendStationAction("sonar_set_tas", {deployed: $("sonar-tas").dataset.deployed !== "true"}));
  $("sonar-depth-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-depth-form", "sonar-depth", "sonar_set_tow_depth", "depth_m", 20, 260);
  });
  $("sonar-bt").addEventListener("click", () => sendStationAction("sonar_measure_bt", {}));
  $("sonar-ping").addEventListener("click", () => sendStationAction("sonar_active_ping", {}));
  $("sonar-tma").addEventListener("change", () => sendStationAction("sonar_set_tma_enabled", {enabled: $("sonar-tma").checked}));
  $("sonar-gain-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-gain-form", "sonar-gain", "sonar_set_gain", "gain_db", -12, 24);
  });
  $("sonar-band-apply").addEventListener("click", () => sendStationAction("sonar_set_band_preset", {preset: $("sonar-band").value}));
  $("sonar-notch").addEventListener("change", () => sendStationAction("sonar_set_notch", {enabled: $("sonar-notch").checked}));
  $("sonar-peak").addEventListener("change", () => sendStationAction("sonar_set_peak_hold", {enabled: $("sonar-peak").checked}));
  $("sonar-harmonic-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-harmonic-form", "sonar-harmonic-input", "sonar_set_harmonic", "frequency_hz", 0.000001, 300);
  });
  $("sonar-harmonic-clear").addEventListener("click", () => sendStationAction("sonar_set_harmonic", {frequency_hz: null}));
  $("engine-telegraph-submit").addEventListener("click", () => sendStationAction("engine_set_telegraph", {order: $("engine-telegraph").value}));
  $("engine-speed-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("engine-speed-form", "engine-speed", "engine_set_speed", "speed_kn", 0, 25);
  });
  $("engine-quiet").addEventListener("click", () => sendStationAction("engine_set_quiet_mode", {enabled: !v2State.engine.propulsion.quiet_mode}));
  $("helicopter-launch").addEventListener("click", () => sendStationAction("helicopter_launch", {}));
  $("helicopter-return").addEventListener("click", () => sendStationAction("helicopter_return", {}));
  $("helicopter-waypoint-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const x = $("helicopter-x").valueAsNumber, y = $("helicopter-y").valueAsNumber;
    if (finite(x) && finite(y) && x >= 0 && x <= 1000 && y >= 0 && y <= 1000) sendStationAction("helicopter_set_waypoint", {x, y});
  });
  $("helicopter-buoy").addEventListener("click", () => sendStationAction("helicopter_deploy_buoy", {}));
  $("helicopter-dip-toggle").addEventListener("click", () => sendStationAction("helicopter_set_dipping", {
    deployed: $("helicopter-dip-toggle").dataset.deployed !== "true",
  }));
  $("helicopter-dip-ping").addEventListener("click", () => sendStationAction("helicopter_dipping_ping", {}));
  $("helicopter-dip-depth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const depth_m = $("helicopter-dip-depth").valueAsNumber;
    if (finite(depth_m)) sendStationAction("helicopter_set_dip_depth", {depth_m});
  });
  $("propose").addEventListener("click", () => sendCommand("propose"));
  $("clear-proposal").addEventListener("click", () => sendCommand("clear_proposal"));
  $("navigation-form").addEventListener("submit", (event) => { event.preventDefault(); sendCommand("propose_navigation"); });
  $("bridge-course-form").addEventListener("submit", (event) => { event.preventDefault(); sendBridgeOrder("course"); });
  $("bridge-speed-form").addEventListener("submit", (event) => { event.preventDefault(); sendBridgeOrder("speed"); });
  $("retry-command").addEventListener("click", () => {
    if (!pending?.uncertain || pending.inFlight || performance.now() < pending.retryAt) return;
    // Reconciliation never reconstructs an envelope from the current selection.
    transmitCommand(pending);
  });
  for (const [id, name] of [["workstation-help", "guide"], ["workstation-library", "contacts"], ["workstation-lookout", "lookout"]]) {
    $(id).addEventListener("click", () => { $("workstation-tools").open = false; activateTab(name); });
  }
  $("workstation-release").addEventListener("click", releaseActiveStation);
  for (const name of tabNames) {
    const tab = $(`tab-${name}`);
    tab.addEventListener("click", () => activateTab(name));
    tab.addEventListener("keydown", (event) => {
      const visible = tabNames.filter((candidate) => !$(`tab-${candidate}`).hidden);
      let index = visible.indexOf(name);
      if (event.key === "ArrowRight") index = (index + 1) % visible.length;
      else if (event.key === "ArrowLeft") index = (index - 1 + visible.length) % visible.length;
      else if (event.key === "Home") index = 0;
      else if (event.key === "End") index = visible.length - 1;
      else return;
      event.preventDefault();
      activateTab(visible[index]);
    });
  }
  for (const link of document.querySelectorAll("#guide-nav a")) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = $(link.hash.slice(1));
      const panel = $("panel-guide");
      if (!target || panel.hidden) return;
      panel.scrollTop += target.getBoundingClientRect().top - panel.getBoundingClientRect().top - 12;
      target.focus({ preventScroll: true });
    });
  }
  $("track-list").addEventListener("keydown", (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = [...$("track-list").querySelectorAll("button")];
    const index = buttons.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
    buttons[next]?.focus();
  });
  $("sound").addEventListener("click", async () => {
    try {
      if (soundEnabled) {
        soundEnabled = false;
        if (!sonarAudioEnabled) await audio?.suspend();
      } else {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) throw new Error("audio");
        if (!audio) audio = new Audio();
        await audio.resume();
        soundEnabled = audio.state === "running";
      }
      renderSound();
    } catch (_) { soundEnabled = false; renderSound(); $("sound").textContent = t("sound_unavailable"); }
  });
  $("sonar-live-toggle").addEventListener("click", async () => {
    if (sonarAudioEnabled) { stopSonarAudio(); return; }
    if (!(session?.station === "sonar" && session.grants.sonar_audio === true)) return;
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw new Error("audio");
      if (!audio) audio = new Audio();
      await audio.resume();
      if (audio.state !== "running" || !sonarAudioAuthorized()) throw new Error("audio");
      sonarAudioGain = audio.createGain();
      sonarAudioGain.gain.value = sonarGainValue();
      sonarAudioGain.connect(audio.destination);
      sonarAudioEnabled = true;
      sonarAudioNextTime = audio.currentTime;
      renderSonarAudio("sonar_live_waiting");
      scheduleSonarAudioPoll();
    } catch (_) { stopSonarAudio("sonar_live_unavailable"); }
  });
  $("zoom-in").addEventListener("click", () => zoom(1.4));
  $("zoom-out").addEventListener("click", () => zoom(1 / 1.4));
  $("fit").addEventListener("click", fitChart);
  const changeRoleMapZoom = (factor) => {
    const role = v2State?.role;
    if (!mapRoles.has(role)) return;
    roleMapViews[role].zoom = Math.max(.5, Math.min(32, roleMapViews[role].zoom * factor));
    queueVisualDraw();
  };
  $("role-map-zoom-in").addEventListener("click", () => changeRoleMapZoom(1.4));
  $("role-map-zoom-out").addEventListener("click", () => changeRoleMapZoom(1 / 1.4));
  $("role-map-fit").addEventListener("click", () => {
    const role = v2State?.role;
    if (!mapRoles.has(role)) return;
    Object.assign(roleMapViews[role], {x: chart?.size_nm / 2 || 250, y: chart?.size_nm / 2 || 250, zoom: 1, follow: false});
    queueVisualDraw();
  });
  $("role-map-follow").addEventListener("click", () => {
    const state = roleMapViews[v2State?.role]; if (!state) return;
    state.follow = !state.follow; queueVisualDraw();
  });
  $("role-map").addEventListener("wheel", (event) => { event.preventDefault(); changeRoleMapZoom(event.deltaY < 0 ? 1.15 : 1 / 1.15); }, {passive: false});
  $("role-map").addEventListener("pointerdown", (event) => {
    const role = v2State?.role;
    if (!mapRoles.has(role) || !event.isPrimary || event.button !== 0) return;
    $("role-map").setPointerCapture(event.pointerId);
    roleMapDrag = {id: event.pointerId, x: event.clientX, y: event.clientY, role,
      worldX: roleMapViews[role].x, worldY: roleMapViews[role].y, moved: false};
  });
  $("role-map").addEventListener("pointermove", (event) => {
    if (!roleMapDrag || roleMapDrag.id !== event.pointerId || roleMapDrag.role !== v2State?.role) return;
    const dx = event.clientX - roleMapDrag.x, dy = event.clientY - roleMapDrag.y;
    if (Math.hypot(dx, dy) > 5) roleMapDrag.moved = true;
    if (!roleMapDrag.moved) return;
    const state = roleMapViews[roleMapDrag.role];
    state.follow = false;
    const scale = Math.min($("role-map").clientWidth, $("role-map").clientHeight) / chart.size_nm * state.zoom;
    state.x = roleMapDrag.worldX - dx / scale;
    state.y = roleMapDrag.worldY - dy / scale;
    queueVisualDraw();
  });
  $("role-map").addEventListener("pointerup", (event) => {
    if (!roleMapDrag || roleMapDrag.id !== event.pointerId) return;
    const gesture = roleMapDrag;
    roleMapDrag = null;
    if (!gesture.moved && gesture.role === v2State?.role) {
      const rect = $("role-map").getBoundingClientRect();
      const x = event.clientX - rect.left, y = event.clientY - rect.top;
      const hits = roleMapHits.filter((hit) => Math.hypot(hit.x - x, hit.y - y) < 26)
        .sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y));
      const contact = hits.find((hit) => hit.ref !== null);
      if (contact) {
        selectTrack(contact.ref);
      } else if (!hits.length && gesture.role === "helicopter" && stationActionAvailable() &&
                 v2State.helicopter.readiness.can_set_waypoint) {
        const geometry = roleMapGeometry(gesture.role);
        const state = roleMapViews[gesture.role];
        const worldX = state.x + (x - rect.width / 2) / geometry.scale;
        const worldY = state.y + (y - rect.height / 2) / geometry.scale;
        if (finite(worldX) && finite(worldY) && worldX >= 0 && worldX <= 1000 && worldY >= 0 && worldY <= 1000) {
          sendStationAction("helicopter_set_waypoint", {x: worldX, y: worldY});
        }
      }
    }
    $("role-map").releasePointerCapture(event.pointerId);
  });
  $("role-map").addEventListener("pointercancel", (event) => { if (roleMapDrag?.id === event.pointerId) roleMapDrag = null; });
  $("role-map").addEventListener("lostpointercapture", () => { roleMapDrag = null; });
  $("role-map").addEventListener("keydown", (event) => {
    const role = v2State?.role;
    if (!mapRoles.has(role) || !["+", "=", "-", "Home", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    if (["+", "="].includes(event.key)) changeRoleMapZoom(1.4);
    else if (event.key === "-") changeRoleMapZoom(1 / 1.4);
    else if (event.key === "Home") $("role-map-fit").click();
    else { const amount = chart.size_nm / roleMapViews[role].zoom / 10; if (event.key === "ArrowLeft") roleMapViews[role].x -= amount; if (event.key === "ArrowRight") roleMapViews[role].x += amount; if (event.key === "ArrowUp") roleMapViews[role].y -= amount; if (event.key === "ArrowDown") roleMapViews[role].y += amount; queueVisualDraw(); }
  });
  $("damage-team").addEventListener("change", queueVisualDraw);
  $("damage-schematic").addEventListener("click", (event) => {
    if (v2State?.role !== "damage" || !stationActionAvailable()) return;
    const rect = $("damage-schematic").getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const roomHit = damageHits.find((hit) => x >= hit.x && x <= hit.x + hit.width && y >= hit.y && y <= hit.y + hit.height);
    const teamNumber = Number($("damage-team").value);
    const team = v2State.damage.teams.find((row) => row.team === teamNumber);
    const room = v2State.damage.compartments.find((row) => row.key === roomHit?.key);
    if (!team || !room || team.compartment !== room.key && !room.repairable) return;
    const action = team.compartment === room.key ? "damage_unassign_team" : "damage_assign_team";
    sendStationAction(action, {team: team.team, compartment: room.key});
  });
  $("follow").addEventListener("click", () => {
    if (!hasPosition(snapshot?.ownship)) return;
    view.follow = !view.follow;
    $("follow").setAttribute("aria-pressed", String(view.follow));
    queueDraw();
  });
  $("lookout-zoom-in").addEventListener("click", () => changeLookoutRange(-1));
  $("lookout-zoom-out").addEventListener("click", () => changeLookoutRange(1));
  $("lookout-reset").addEventListener("click", () => {
    lookoutView.rangeNm = 100;
    renderLookoutStatus();
    queueLookoutDraw();
  });
  $("simlog-current-map").addEventListener("click", () => {
    if (latestSimlogState) openSimlogMap(latestSimlogState.data,
      `${latestSimlogState.stamp} / T+${Math.floor(latestSimlogState.t)}s`,
      latestSimlogState.seq, true);
  });
  $("simlog-map-close").addEventListener("click", closeSimlogMap);
  $("simlog-map-world").addEventListener("click", () => {
    simlogMapFit = "world";
    queueSimlogMapDraw();
  });
  $("simlog-map-units-fit").addEventListener("click", () => {
    simlogMapFit = "units";
    queueSimlogMapDraw();
  });
  $("simlog-map-dialog").addEventListener("close", () => {
    simlogMapData = null;
    simlogMapSeq = null;
    simlogMapLatest = false;
    releaseCanvas(simlogMapCanvas);
  });
  lookoutCanvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    changeLookoutRange(event.deltaY < 0 ? -1 : 1);
  }, { passive: false });
  lookoutCanvas.addEventListener("keydown", (event) => {
    if (!["+", "=", "-", "Home"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "+" || event.key === "=") changeLookoutRange(-1);
    else if (event.key === "-") changeLookoutRange(1);
    else {
      lookoutView.rangeNm = 100;
      renderLookoutStatus();
      queueLookoutDraw();
    }
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    zoom(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  canvas.addEventListener("pointerdown", (event) => {
    if (!snapshot || !chart || !event.isPrimary || event.button !== 0) return;
    canvas.focus();
    canvas.setPointerCapture(event.pointerId);
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, worldX: view.x, worldY: view.y, moved: false };
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (Math.hypot(dx, dy) > 5) drag.moved = true;
    if (!drag.moved) return;
    const { scale } = chartGeometry();
    view.follow = false;
    $("follow").setAttribute("aria-pressed", "false");
    view.x = drag.worldX - dx / scale;
    view.y = drag.worldY - dy / scale;
    queueDraw();
  });
  canvas.addEventListener("pointerup", (event) => {
    if (!drag || drag.id !== event.pointerId) return;
    if (!drag.moved) {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const hits = chartHits.filter((hit) => Math.hypot(hit.x - x, hit.y - y) < 26).sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y));
      if (hits.length) selectTrack(hits[0].ref);
    }
    drag = null;
    canvas.releasePointerCapture(event.pointerId);
  });
  canvas.addEventListener("lostpointercapture", () => { drag = null; });
  canvas.addEventListener("pointercancel", () => { drag = null; });
  canvas.addEventListener("keydown", (event) => {
    if (!snapshot || !chart) return;
    if (["+", "=", "-", "Home", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) event.preventDefault();
    if (event.key === "+" || event.key === "=") zoom(1.4);
    else if (event.key === "-") zoom(1 / 1.4);
    else if (event.key === "Home") fitChart();
    else if (event.key.startsWith("Arrow")) {
      const distance = 65 / chartGeometry().scale;
      view.follow = false;
      $("follow").setAttribute("aria-pressed", "false");
      if (event.key === "ArrowLeft") view.x -= distance;
      if (event.key === "ArrowRight") view.x += distance;
      if (event.key === "ArrowUp") view.y -= distance;
      if (event.key === "ArrowDown") view.y += distance;
      queueDraw();
    }
  });
  new ResizeObserver(queueDraw).observe(canvas);
  new ResizeObserver(queueLookoutDraw).observe(lookoutCanvas);
  new ResizeObserver(queueSimlogMapDraw).observe(simlogMapCanvas);
  for (const id of visualCanvasIds) new ResizeObserver(() => { queueVisualDraw(); syncOpzSweepAnimation(); }).observe($(id));
  window.addEventListener("resize", () => { queueDraw(); queueLookoutDraw(); queueSimlogMapDraw(); queueVisualDraw(); });
  window.addEventListener("hashchange", () => { applySimlogView(); loadSimlog(); });
  document.addEventListener("visibilitychange", () => {
    // A background tab's event batch is not a new audible alarm on return.
    suppressNextEvents = true;
    if (document.hidden) stopSonarAudio("sonar_live_unavailable");
    if (document.hidden && authenticated()) setConnection("stale");
    syncOpzSweepAnimation();
  });
  window.addEventListener("offline", () => { stopSonarAudio("sonar_live_unavailable"); stopOpzSweepAnimation(); if (authenticated()) setConnection("stale"); });
  window.addEventListener("online", () => { syncOpzSweepAnimation(); if (authenticated() && !polling) { clearTimeout(pollTimer); poll(); } });
  setInterval(() => {
    if (authenticated() && lastSuccess && performance.now() - lastSuccess > 4500) setConnection("stale");
    else if (linkState === "stale") renderConnection();
    if (pending) {
      if (!pending.inFlight && performance.now() >= pending.retryAt) pending.uncertain = true;
      renderActionState();
    }
  }, 1000);

  async function bootstrap() {
    const resumed = await detectSession();
    let delay = 1000;
    while (!await loadLanguage(language)) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      delay = Math.min(8000, delay * 2);
    }
    loadContactAnalysis();
    if (resumed) {
      $("pairing").hidden = true;
      $("disconnect").hidden = false;
      renderLobby();
      setConnection(session.station === null ? "lobby" : "syncing");
      poll();
    }
  }
  bootstrap();
})();
