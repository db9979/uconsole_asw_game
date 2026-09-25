"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const prefix = "commander.web.";
  const domains = { UNKNOWN: "domain_unknown", SURFACE: "domain_surface", SUBSURFACE: "domain_subsurface", AIR: "domain_air" };
  const affiliations = { UNKNOWN: "aff_unknown", FRIEND: "aff_friend", NEUTRAL: "aff_neutral", HOSTILE: "aff_hostile" };
  const classes = { U_BOOT: "class_submarine", KAMPFSCHIFF: "class_warship", BIOLOGISCH: "class_biological", FAHRZEUG: "class_vehicle", FLUGZEUG: "class_aircraft", TORPEDO: "class_torpedo" };
  const phases = { live: "phase_live", menu: "phase_menu", blocked: "phase_blocked", ended: "phase_ended" };
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
  // Affiliation colours come from the stylesheet tokens (one palette for
  // lists, badges and map symbols); literals are only the fallback.
  const cssToken = (name, fallback) => {
    try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; } catch { return fallback; }
  };
  const colors = { UNKNOWN: cssToken("--aff-unknown", "#f3c577"), FRIEND: cssToken("--aff-friend", "#81c5ff"),
    NEUTRAL: cssToken("--aff-neutral", "#8fdfab"), HOSTILE: cssToken("--aff-hostile", "#ff9090") };
  // Canvas drawing cannot use CSS custom properties directly, so it used to
  // duplicate the palette as hand-copied hex literals - a real drift risk if
  // style.css's :root palette is ever retuned. Read it once instead; these
  // are static custom properties (no @media override anywhere in style.css),
  // so there is nothing to invalidate the cache for.
  let paletteCache = null;
  function palette() {
    if (!paletteCache) {
      const style = getComputedStyle(document.documentElement);
      const read = (name) => style.getPropertyValue(name).trim();
      paletteCache = {
        bg: read("--bg"), panel: read("--panel"), line: read("--line"),
        text: read("--text"), muted: read("--muted"), accent: read("--accent"),
        amber: read("--amber"), red: read("--red"), blue: read("--blue"),
        scopeBg: read("--scope-bg"), plot: read("--plot"),
      };
    }
    return paletteCache;
  }
  let language = (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
  let catalog = {};
  // Session metadata stays closure-local: no URL, DOM or persistence.
  let session = null;
  let pairingAvailable = false;
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
  // Distinguishes "server sent something this client cannot parse" (a real
  // bug, not a network blip) from ordinary transient failures, and gives
  // the operator an honest signal once a transient failure has been
  // retrying for a while instead of "retrying automatically" forever with
  // no escalation.
  const PROTOCOL_ERROR_MESSAGES = new Set(["protocol", "session", "chart", "events",
    "proposals", "results", "simlog_schema", "catalog"]);
  const ESCALATE_AFTER_FAILURES = 10;
  // Below this, a stale poll is shown as a low-alarm "reconnecting" notice
  // rather than the full amber "stale" treatment - most blips clear before
  // this many consecutive failures. Purely cosmetic: linkState/connected and
  // the action-locking gate they drive are untouched.
  const NOTICE_AFTER_FAILURES = 2;
  let pollTimer = null;
  let polling = false;
  let pending = null;
  let v2State = null;
  // Purely client-local presentation state; never sent to the host or saved.
  const elokaFilters = {status: "OPERATIONAL", threat: "ALL", band: "ALL"};
  const elokaThreatRank = {unknown: 0, low: 1, medium: 2, high: 3, critical: 4};
  const elokaSignalRank = {LIVE: 0, RECENT: 1, MEMORY: 2, UNCONFIRMED: 3};
  function filteredEloka(intercepts) {
    const minimum = elokaFilters.threat === "ALL" ? -1 : elokaThreatRank[elokaFilters.threat.toLowerCase()];
    return intercepts.filter((row) => {
      if (row.jamming) return true;
      if (elokaFilters.status === "OPERATIONAL" && !row.operational) return false;
      if (["LIVE", "MEMORY"].includes(elokaFilters.status) && row.signal_state !== elokaFilters.status) return false;
      if ((elokaThreatRank[row.threat] ?? 0) < minimum) return false;
      return elokaFilters.band === "ALL" || row.frequency_band === elokaFilters.band;
    }).sort((a, b) => Number(b.jamming) - Number(a.jamming) ||
      (elokaThreatRank[b.threat] ?? 0) - (elokaThreatRank[a.threat] ?? 0) ||
      (elokaSignalRank[a.signal_state] ?? 9) - (elokaSignalRank[b.signal_state] ?? 9) ||
      b.quality - a.quality || a.age_s - b.age_s || a.label.localeCompare(b.label));
  }
  // Last accepted state per station. A station switch inside one world shows
  // the target's cached picture at once (marked stale, commands disabled) until
  // its fresh state arrives; a world/lease change clears every entry.
  const roleCache = new Map();
  let roleStale = false;
  // Solo host surface: the published host view and the one host command in flight.
  let hostView = null;
  let hostPending = null;
  let hostMessage = null;
  let hostMessageTimer = null;
  let stationRenderSignature = null;
  let nextCommandSeq = 0;
  let stationMutation = false;
  let activatingStation = null;
  let queuedSonarFocus = null;
  let stationPickerOpen = false;
  let lobbyMessage = null;
  let commandMessage = null;
  let lastToastedMessage = null;
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
  let helicopterAudioSource = null;
  let sonarAudioSources = [];
  let sonarAudioGain = null;
  let sonarAudioHighpass = null;
  let sonarAudioLowpass = null;
  let sonarAudioWorklet = null;
  let sonarAudioSocket = null;
  let sonarAudioReconnect = null;
  let sonarAudioMetrics = {buffered: 0, gaps: 0, concealed: 0, rate: 1, stale: false};
  let gameSoundContext = null;
  let gameSoundHighWater = 0;
  const gameEffectKinds = new Set(["sonar_ping", "esm_contact", "torpedo_launch", "missile_launch", "gunfire", "explosion", "water_entry",
    "sonar_echo_cw", "sonar_echo_cw_faint", "sonar_echo_lfm", "sonar_echo_lfm_faint"]);
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
  let proposals = null;
  let eventContext = null;
  let eventBaselinePending = false;
  let eventHighWater = 0;
  let eventHistory = [];
  let analysisError = false;
  let latestSimlogState = null;
  const simlogMapCanvas = $("simlog-map");
  const simlogMapCtx = simlogMapCanvas.getContext("2d");
  const roleMapSweepCanvas = $("role-map-sweep");
  const roleMapSweepCtx = roleMapSweepCanvas.getContext("2d");
  let simlogMapData = null;
  let simlogMapSeq = null;
  let simlogMapLatest = false;
  let simlogMapFit = "world";
  let simlogMapDrawQueued = false;
  const visualCanvasIds = ["role-map", "role-map-sweep", "sonar-broadband", "sonar-lofar", "sonar-spectrum",
    "sonar-band-low", "sonar-band-mid", "sonar-band-high", "sonar-demon", "sonar-demon-spectrum",
    "sonar-tma-plot", "sonar-environment", "sonar-active", "sonar-a-scan", "damage-schematic",
    "engine-instruments", "eloka-scope", "weapons-system", "helicopter-broadband-canvas",
    "helicopter-lofar-canvas", "helicopter-demon-canvas"];
  const mapRoles = new Set(["bridge", "weapons", "opz", "radio", "helicopter"]);
  const trackRoles = new Set(["bridge", "sonar", "weapons", "opz", "radio", "helicopter", "eloka"]);
  const roleMapViews = Object.fromEntries([...mapRoles].map((role) => [role, {x: 250, y: 250, zoom: 1}]));
  const maxRoleMapHits = 512;
  let roleMapHits = [];
  // Hover information for the maps (tracks, own ship, assets, chart items);
  // separate from the click hit lists so selection semantics are unchanged.
  let roleMapInfo = [];
  let chartInfo = [];
  let damageHits = [];
  const defaultSonarPage = () => matchMedia("(min-width: 851px)").matches ? "overview" : "broadband";
  let sonarVisualPage = defaultSonarPage();
  let helicopterVisualPage = "acoustic";
  let helicopterPlot = "lofar";
  // The browser runs on a desktop PC: on a wide screen the overview shows all six
  // plots at once, otherwise the four that matter most.
  const wideScreen = matchMedia("(min-width: 1800px) and (min-height: 850px)");
  const overviewPlotList = () => wideScreen.matches ? ["broadband", "lofar", "demon", "tma", "environment", "active"] :
    ["broadband", "lofar", "demon", "tma"];
  let visualDrawQueued = false;
  let weatherFrame = null;
  let weatherTimer = null;
  let weatherLastDraw = 0;
  let roleMapDrag = null;
  let plotAnchor = null;
  let plotListKey = "";
  let sonarBroadbandDrag = null;
  let opzSweepFrame = null;
  let opzSweepSample = null;
  let fireConfirmation = null;
  let fireConfirmationTimer = null;
  let sonarAudioGeneration = 0;
  const detachedSonarScope = new URLSearchParams(location.search).get("scope");
  const sonarScopeNames = new Set(["broadband", "lofar", "demon", "tma", "environment", "active"]);
  const sonarDisplay = {black: 0, contrast: 2.5, history: 300, palette: "green", demonCursor: null, btCursorDepth: null};
  const sonarHistory = {context: null, broadband: new Map(), lofar: new Map(), demon: new Map()};
  const sonarStream = {socket: null, connected: false, retry: null, generation: 0,
    sequence: -1, lofarSpectrum: [], demonSpectrum: []};
  if (sonarScopeNames.has(detachedSonarScope)) {
    document.body.dataset.sonarScope = detachedSonarScope;
    sonarVisualPage = detachedSonarScope;
  }

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
  // Every assigned station receives the identical known chart, so a station
  // switch keeps it; only the redacted (role-less) chart is a different picture.
  const chartMatches = (state) => Boolean(state && chart) && chartSession === state.session && chartEpoch === state.epoch &&
    (chartRole === state.role || (chartRole !== null && state.role !== null)) &&
    chart.revision === state.chart_revision;
  const authenticated = () => session !== null;

  // State polling and browser network hints can fail while the dedicated audio
  // request still works. The audio endpoint rechecks the session on every block.
  const sonarAudioAuthorized = () => !document.hidden &&
    ["sonar", "helicopter"].includes(session?.station) && session.grants.sonar_audio === true &&
    v2State?.role === session.station && v2State.phase === "live" &&
    v2State.sonar?.settings?.station_down !== true &&
    (session.station !== "helicopter" || v2State.helicopter?.acoustic?.ready === true);
  // Blocks arrive at real-time rate, so the standing buffer is the start lead. It
  // must outlast a browser main-thread stall or a Wi-Fi hiccup, otherwise every
  // such hiccup is an audible gap; live listening tolerates the extra latency.
  const sonarAudioStartLead = 1.0;
  const sonarAudioTargetAhead = 1.5;
  const sonarAudioMaxSources = 12;
  const sonarGainValue = () => {
    const value = Number($("volume").value) / 200;
    const helicopterLevel = session?.station === "helicopter"
      ? Number($("helicopter-audio-volume").value) / 100 : 1;
    return finite(value) && finite(helicopterLevel)
      ? Math.max(0, Math.min(.5, value * helicopterLevel)) : 0;
  };
  const sonarFilterValues = () => {
    const prefix = session?.station === "helicopter" ? "helicopter" : "sonar";
    return [Number($(`${prefix}-audio-highpass`).value),
      Number($(`${prefix}-audio-lowpass`).value)];
  };

  function playGameEffect(kind) {
    if (!soundEnabled || !audio || audio.state !== "running" || document.hidden || !gameEffectKinds.has(kind)) return;
    const volume = Math.max(0, Math.min(1, Number($("volume").value) / 100));
    if (!volume) return;
    const profile = {
      sonar_ping: [720, 980, .62, .10, "sine"], esm_contact: [1040, 1320, .16, .10, "sine"],
      torpedo_launch: [95, 38, .72, .16, "sawtooth"],
      missile_launch: [150, 1250, .9, .13, "sawtooth"], gunfire: [115, 52, .42, .16, "square"],
      explosion: [68, 25, 1.1, .20, "sawtooth"], water_entry: [260, 90, .58, .11, "triangle"],
      // Returned echoes: CW a steady carrier tone, LFM a short 100 Hz sweep.
      sonar_echo_cw: [900, 900, .55, .07, "sine"], sonar_echo_cw_faint: [900, 900, .55, .025, "sine"],
      sonar_echo_lfm: [850, 950, .32, .08, "sine"], sonar_echo_lfm_faint: [850, 950, .32, .03, "sine"],
    }[kind];
    const [startHz, endHz, duration, gainLevel, type] = profile;
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    const now = audio.currentTime;
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(startHz, now);
    if (kind.startsWith("sonar_echo_lfm")) oscillator.frequency.linearRampToValueAtTime(endHz, now + duration);
    else oscillator.frequency.setValueAtTime(endHz, now + duration);
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(volume * gainLevel, now + .012);
    gain.gain.linearRampToValueAtTime(0, now + duration);
    oscillator.connect(gain);
    gain.connect(audio.destination);
    oscillator.start(now);
    oscillator.stop(now + duration + .02);
    oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
  }

  function syncGameAudio() {
    // The general sound control plays bounded one-shot events only. Live sonar
    // remains an explicit, separately authorized station function.
    const stateAudio = v2State?.audio;
    const context = v2State ? `${v2State.session}:${v2State.epoch}` : null;
    const events = Array.isArray(stateAudio?.events) ? stateAudio.events : [];
    const latest = events.length ? events.at(-1).seq : 0;
    if (context !== gameSoundContext) {
      gameSoundContext = context;
      gameSoundHighWater = latest;
    } else {
      for (const event of events) if (event.seq > gameSoundHighWater) playGameEffect(event.cue);
      gameSoundHighWater = Math.max(gameSoundHighWater, latest);
    }
  }

  function renderSonarAudio(key) {
    const button = $("sonar-live-toggle");
    button.textContent = t(sonarAudioEnabled ? "sonar_live_stop" : "sonar_live_start");
    button.setAttribute("aria-pressed", String(sonarAudioEnabled));
    button.disabled = !sonarAudioEnabled && !(["sonar", "helicopter"].includes(session?.station) && session?.grants.sonar_audio === true &&
      (session.station !== "helicopter" || v2State?.helicopter?.acoustic?.ready === true));
    const receiverRequired = session?.station === "helicopter" && v2State?.helicopter?.acoustic?.ready !== true;
    $("sonar-live-status").textContent = t(receiverRequired ? "sonar_live_receiver_required" :
      sonarAudioEnabled && sonarAudioMetrics.stale ? "sonar_live_stale" :
      key || (sonarAudioEnabled ? "sonar_live_waiting" : "sonar_live_off"));
  }

  function stopSonarAudio(key = "sonar_live_off") {
    sonarAudioGeneration += 1;
    sonarAudioEnabled = false;
    sonarAudioMetrics = {buffered: 0, gaps: 0, concealed: 0, rate: 1, stale: false};
    window.uJagdAudioDiagnostics = Object.freeze({bufferedSeconds: 0,
      sequenceGaps: 0, droppedBlocks: 0, concealedBlocks: 0, playbackRate: 1,
      stale: false, transport: "off"});
    clearTimeout(sonarAudioTimer);
    sonarAudioTimer = null;
    sonarAudioController?.abort();
    sonarAudioController = null;
    clearTimeout(sonarAudioReconnect);
    sonarAudioReconnect = null;
    sonarAudioSocket?.close();
    sonarAudioSocket = null;
    sonarAudioWorklet?.port.postMessage({type: "reset"});
    sonarAudioWorklet?.disconnect();
    sonarAudioWorklet = null;
    for (const source of sonarAudioSources) { try { source.stop(); } catch (_) {} source.disconnect(); }
    sonarAudioSources = [];
    sonarAudioSequence = null;
    sonarAudioNextTime = 0;
    sonarAudioGain?.disconnect();
    sonarAudioGain = null;
    if (typeof sonarAudioHighpass !== "undefined") {
      sonarAudioHighpass?.disconnect();
      sonarAudioHighpass = null;
    }
    if (typeof sonarAudioLowpass !== "undefined") {
      sonarAudioLowpass?.disconnect();
      sonarAudioLowpass = null;
    }
    renderSonarAudio(key);
  }

  function scheduleSonarAudioPoll(delay = 0) {
    clearTimeout(sonarAudioTimer);
    if (sonarAudioEnabled && !sonarAudioSocket) sonarAudioTimer = setTimeout(pollSonarAudio, delay);
  }

  function openSonarAudioSocket() {
    if (!sonarAudioEnabled || !sonarAudioWorklet || sonarAudioSocket || !sonarAudioAuthorized()) return;
    const role = session.station;
    const client = session.client_id;
    const lease = session.station_generation;
    const active = session.active_generation;
    const world = v2State.session;
    const epoch = v2State.epoch;
    const streamGeneration = sonarAudioGeneration;
    const current = () => sonarAudioEnabled && streamGeneration === sonarAudioGeneration &&
      session?.client_id === client && session?.station === role &&
      session?.station_generation === lease && session?.active_generation === active &&
      v2State?.session === world && v2State?.epoch === epoch;
    let socket;
    try {
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${scheme}//${location.host}/ws/v2/${role}/audio`, "u-jagd-audio-v2");
    } catch (_) { scheduleSonarAudioPoll(0); return; }
    socket.binaryType = "arraybuffer";
    sonarAudioSocket = socket;
    socket.onopen = () => { if (!current()) socket.close(); else clearTimeout(sonarAudioTimer); };
    socket.onmessage = ({data}) => {
      if (!current() || !(data instanceof ArrayBuffer) || data.byteLength !== 2060) { socket.close(); return; }
      const view = new DataView(data);
      if (view.getUint32(0, false) !== 0x554a4132) { socket.close(); return; }
      const sequence = Number(view.getBigUint64(4, true));
      if (!Number.isSafeInteger(sequence) || sequence < 1) { socket.close(); return; }
      sonarAudioSequence = sequence;
      const bytes = data.slice(12);
      sonarAudioWorklet.port.postMessage({type: "pcm", sequence,
        bytes}, [bytes]);
      if (!sonarAudioMetrics.stale) renderSonarAudio("sonar_live_playing");
    };
    socket.onclose = () => {
      if (sonarAudioSocket === socket) sonarAudioSocket = null;
      if (current()) {
        scheduleSonarAudioPoll(0);
        sonarAudioReconnect = setTimeout(openSonarAudioSocket, 2000);
      }
    };
    socket.onerror = () => socket.close();
  }

  async function readSonarPcm(response) {
    const reader = response.body?.getReader?.();
    if (!reader) throw new Error("audio_protocol");
    const output = new Uint8Array(2048);
    let offset = 0;
    let complete = false;
    try {
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        if (!(value instanceof Uint8Array) || offset + value.byteLength > output.byteLength)
          throw new Error("audio_protocol");
        output.set(value, offset);
        offset += value.byteLength;
      }
      if (offset !== output.byteLength) throw new Error("audio_protocol");
      complete = true;
      return output.buffer;
    } finally {
      if (!complete) await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  async function pollSonarAudio() {
    if (!sonarAudioEnabled || sonarAudioController || sonarAudioSocket?.readyState === WebSocket.OPEN) return;
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
      response = await fetch(session?.station === "helicopter" ? "/api/v2/helicopter/audio" : "/api/v2/sonar/audio", {
        method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", mode: "same-origin",
        signal: controller.signal,
        headers: {Accept: "audio/pcm", "Content-Type": "application/json", "X-U-Jagd-CSRF": expectedSession.csrf},
        body: JSON.stringify({protocol: 2, after: sonarAudioSequence, world_session: expectedSession.world,
          world_epoch: expectedSession.epoch, station_generation: expectedSession.station_generation,
          active_generation: expectedSession.active_generation}),
      });
      if (!currentStream()) return;
      if (response.status === 204) {
        if (![null, "0"].includes(response.headers.get("content-length"))) throw new Error("audio_protocol");
        renderSonarAudio("sonar_live_waiting");
        scheduleSonarAudioPoll(60);
        return;
      }
      if ([401, 403, 409].includes(response.status)) { stopSonarAudio("sonar_live_unavailable"); return; }
      if (response.status >= 500 || response.status === 429) {
        renderSonarAudio("sonar_live_waiting");
        return;
      }
      const sequence = Number(response.headers.get("x-u-jagd-audio-sequence"));
      const discontinuity = response.headers.get("x-u-jagd-audio-discontinuity");
      const contentType = (response.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
      if (response.status !== 200 || contentType !== "audio/pcm" ||
          response.headers.get("x-u-jagd-pcm") !== "s16le" || response.headers.get("x-u-jagd-sample-rate") !== "4096" ||
          response.headers.get("x-u-jagd-audio-frames") !== "1024" ||
          !Number.isSafeInteger(sequence) || sequence < 1 || !["0", "1"].includes(discontinuity)) throw new Error("audio_protocol");
      const bytes = await readSonarPcm(response);
      if (!currentStream()) return;
      if (bytes.byteLength !== 2048) throw new Error("audio_protocol");
      const gap = discontinuity === "1" || sonarAudioSequence !== null && sequence !== sonarAudioSequence + 1;
      sonarAudioSequence = sequence;
      if (sonarAudioWorklet) {
        sonarAudioWorklet.port.postMessage({type: "pcm", sequence, bytes}, [bytes]);
        if (!sonarAudioMetrics.stale) renderSonarAudio("sonar_live_playing");
        return;
      }
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
      // An overrun skips old data, but audio already queued is still valid.
      // Keep its timeline and soften the first samples of the new block.
      if (gap) for (let index = 0; index < Math.min(channel.length, Math.round(audio.sampleRate * .01)); index++)
        channel[index] *= index / Math.max(1, Math.round(audio.sampleRate * .01));
      sonarAudioSources = sonarAudioSources.filter((source) => !source.__ended);
      if (sonarAudioSources.length >= sonarAudioMaxSources) throw new Error("audio_protocol");
      sonarAudioGain.gain.value = sonarGainValue();
      const start = sonarAudioNextTime > audio.currentTime + .03
        ? sonarAudioNextTime : audio.currentTime + sonarAudioStartLead;
      if (start > audio.currentTime + 7.0) throw new Error("audio_protocol");
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

  // Visual add-on for high-importance command/fire results, alongside (not
  // instead of) the role=status/aria-live text that already carries this to
  // screen readers - a busy operator screen can otherwise bury that text.
  function showToast(key, values, variant) {
    const region = $("toast-region");
    if (!region) return;
    const toast = node("p", t(key, values), `toast toast-${variant}`);
    region.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
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
    const dialog = $("fire-confirm-dialog");
    if (dialog?.open) dialog.close();
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
      const entries = entryBuilder(row, index);
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
    animatedPlots.clear();
    spectrumStates.clear();
    syncPlotAnimation();
    stopOpzSweepAnimation();
    roleMapHits = [];
    roleMapInfo = [];
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
      ...(row.domain === "AIR" ? [["altitude", unit(row.altitude_m, "m", 0)]] : []),
      ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
      ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
      ["range_uncertainty", unit(row.range_uncertainty_nm, "NM")],
      ...(row.visual_class ? [["sighting", sightingText(row.visual_class, row.visual_type)]] : [])];
  }

  function sonarEntries(row) {
    return [["reference", row.label], ["source", row.source],
      ["classification", classificationText(row.classification)], ["catalog_profile", row.profile || t("station_none")],
      ["bearing", unit(row.bearing, "\u00b0", 0)],
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
      ["yaw_rate", unit(navigation.yaw_rate, "\u00b0/s")], ["turn_radius", unit(navigation.turn_radius_nm, "NM", 2)]]);
    metrics($("bridge-orders-summary"), [["station_down", yesNo(payload.orders.station_down)],
      ["speed_max", unit(payload.orders.speed_max_kn, "kn")], ["telegraph", payload.orders.telegraph],
      ["noise", number(payload.orders.noise, 2)], ["cavitating", yesNo(payload.orders.cavitating)],
      ["threat_count", number(payload.threat.count, 0)], ["flood", unit(payload.threat.average_flood, "%")],
      ["systems_down", payload.systems.filter((item) => item.down).map((item) => item.key).join(", ") || t("station_none")],
      ["threat_tracks", payload.threat.observations.map((row) => row.label).join(", ") || t("station_none")],
      ["torpedo_warning", payload.threat.torpedoes.length ? t(`torpedo_warning_${payload.threat.torpedoes[0].source}`, {
        bearing: number(payload.threat.torpedoes[0].bearing, 1), age: number(payload.threat.torpedoes[0].age_s, 0)}) : t("torpedo_warning_none")]]);
    stationRows($("bridge-tactical"), payload.tactical_summary, tacticalEntries);
    renderSightings(payload.sightings);
    drawBridgeWeather(performance.now());
    syncWeatherAnimation();
    const weather = v2State.environment;
    $("bridge-weather-text").textContent = t("weather_equivalent", {
      kind: t(`weather_${weather.weather}`), light: t(weather.is_night ? "weather_night" : "weather_day"),
      sea: number(weather.effective_sea_state, 1), direction: number(weather.wind_from_deg, 0),
      speed: number(weather.wind_speed_kn, 0), rain: number(weather.rain_intensity * 100, 0),
      visibility: number(weather.visibility_nm, 1),
    });
  }

  function renderSightings(rows) {
    const list = $("bridge-sightings");
    const lines = rows.map((row) => t("sighting_report", {
      time: row.time, what: row.code === null ? t(`sighting_detect_${row.sighted.toLowerCase()}`) : sightingText(row.code, row.type),
      bearing: number(row.bearing, 0).padStart(3, "0"), range: number(row.range_nm, 1)}));
    if (!lines.length) lines.push(t("sightings_none"));
    [...list.children].slice(lines.length).forEach((item) => item.remove());
    lines.forEach((text, index) => {
      const item = list.children[index] || list.appendChild(node("li"));
      if (item.textContent !== text) item.textContent = text;
    });
  }

  function drawBridgeWeather(now) {
    const weather = v2State?.environment;
    if (!weather || session?.station !== "bridge") return;
    const canvas = $("bridge-weather-canvas"), context = canvas.getContext("2d");
    const width = canvas.width, height = canvas.height, horizon = Math.floor(height / 2);
    const phase = displaySimNow(now) + DISPLAY_CLOCK_LAG_S;
    const gradient = context.createLinearGradient(0, 0, 0, horizon);
    gradient.addColorStop(0, weather.is_night ? "#050e1b" : "#19465c");
    gradient.addColorStop(1, weather.is_night ? "#26353e" : "#789ba0");
    context.fillStyle = gradient; context.fillRect(0, 0, width, horizon);
    context.fillStyle = weather.is_night ? "#08232f" : "#0c3641";
    context.fillRect(0, horizon, width, height - horizon);
    context.fillStyle = weather.is_night ? "#bed2cd" : "#f4cc5c";
    const dayStart = 5.5, dayEnd = 19.5;
    const progress = weather.is_night ? ((v2State.clock.world - dayEnd + 24) % 24) / (24 - dayEnd + dayStart) : Math.max(0, Math.min(1, (v2State.clock.world - dayStart) / (dayEnd - dayStart)));
    const lightX = 24 + progress * (width - 48), lightY = horizon - 12 - Math.sin(progress * Math.PI) * 32;
    context.beginPath(); context.arc(lightX, lightY, 12, 0, Math.PI * 2); context.fill();
    const sea = weather.effective_sea_state;
    context.strokeStyle = sea >= 5 ? "#f3cf79" : "#63b5b5";
    context.lineWidth = 2;
    for (let band = 0; band < 3; band += 1) {
      context.beginPath();
      const amplitude = 3 + sea * (.8 + band * .16), wavelength = Math.max(28, 62 - sea * 4 + band * 10);
      for (let x = 0; x <= width + 4; x += 4) {
        const y = horizon + 15 + band * 20 + Math.sin(x / wavelength * Math.PI * 2 + phase * (.7 + weather.wind_speed_kn / 35 + band * .18) + weather.wind_from_deg * Math.PI / 180) * amplitude;
        if (x === 0) context.moveTo(x, y); else context.lineTo(x, y);
      }
      context.stroke();
    }
    context.strokeStyle = "#80aeb8"; context.lineWidth = 1;
    for (let i = 0; i < Math.floor(weather.rain_intensity * 44); i += 1) {
      const x = (i * 47 + phase * 31) % (width + 20) - 10, y = (i * 23 + phase * 53) % height;
      context.beginPath(); context.moveTo(x, y); context.lineTo(x - 5, y + 13); context.stroke();
    }
    const haze = 1 - Math.max(0, Math.min(1, weather.visibility_nm / 30));
    context.fillStyle = `rgba(180, 194, 190, ${haze * .55})`; context.fillRect(0, 0, width, height);
    const windAngle = weather.wind_from_deg * Math.PI / 180, cx = 28, cy = 28;
    context.fillStyle = "rgba(4, 18, 24, .75)"; context.beginPath(); context.arc(cx, cy, 20, 0, Math.PI * 2); context.fill();
    context.strokeStyle = "#f3cf79"; context.lineWidth = 3; context.beginPath();
    context.moveTo(cx + Math.sin(windAngle) * 17, cy - Math.cos(windAngle) * 17); context.lineTo(cx, cy); context.stroke();
  }

  function weatherAnimation(now) {
    weatherFrame = null;
    if (now - weatherLastDraw >= 66) { weatherLastDraw = now; drawBridgeWeather(now); }
    syncWeatherAnimation();
  }

  function syncWeatherAnimation() {
    const active = !document.hidden && connected && session?.station === "bridge" && v2State?.role === "bridge";
    if (active && weatherFrame === null && weatherTimer === null) weatherTimer = setTimeout(() => {
      weatherTimer = null; weatherFrame = requestAnimationFrame(weatherAnimation);
    }, 66);
    if (!active) {
      if (weatherFrame !== null) cancelAnimationFrame(weatherFrame);
      if (weatherTimer !== null) clearTimeout(weatherTimer);
      weatherFrame = null; weatherTimer = null;
    }
  }

  function renderSonarStation(payload) {
    const settings = payload.settings;
    const auditionMode = payload.visualization.receiver.listen_mode;
    metrics($("sonar-settings"), [["sonar_mode", settings.mode], ["sonar_page", number(settings.page, 0)],
      ["sonar_listen_bearing", unit(settings.listen_bearing, "\u00b0", 0)], ["sonar_focus", settings.focus_ref || t("station_none")],
      ["sonar_target", settings.target_ref || t("station_none")], ["station_down", yesNo(settings.station_down)],
      ["sonar_tow_state", settings.tow.state], ["sonar_tow_payout", unit(settings.tow.payout * 100, "%", 0)],
      ["sonar_tow_speed_window", `${unit(settings.tow.speed_min_kn, "kn", 0)} - ${unit(settings.tow.speed_max_kn, "kn", 0)}`],
      ["sonar_tow_depth", unit(settings.tow.depth_m, "m", 0)],
      ["sonar_bt_ready", yesNo(settings.bt.ready)], ["sonar_ping_ready", yesNo(settings.ping.ready)],
      ["sonar_tma", yesNo(settings.tma_enabled)], ["sonar_audition_mode", enumText({BROADBAND: "sonar_audition_broadband", FILTERED: "sonar_audition_filtered", HETERODYNE: "sonar_audition_heterodyne"}, auditionMode)], ["sonar_gain", unit(settings.gain_db, "dB")],
      ["sonar_band", settings.band_preset || settings.band_hz.map((value) => number(value, 0)).join("-")],
      ["sonar_notch", yesNo(settings.notch)], ["sonar_peak_hold", yesNo(settings.peak_hold)],
      ["sonar_harmonic", unit(settings.harmonic_hz, "Hz")], ["sonar_audio", yesNo(settings.audio_enabled)],
      ["sonar_volume", number(settings.volume, 2)], ["quiet_mode", yesNo(settings.quiet_mode)],
      ["sonar_integration", `${settings.tools.integration_s} s`], ["sonar_vernier", yesNo(settings.tools.vernier)],
      ["sonar_operator_notch", unit(settings.tools.operator_notch_hz, "Hz")],
      ["sonar_demon_marks", t("sonar_demon_marks_value", {shaft: finite(settings.tools.shaft_hz) ? number(settings.tools.shaft_hz, 1) : "--",
        blade: finite(settings.tools.blade_hz) ? number(settings.tools.blade_hz, 1) : "--",
        blades: finite(settings.tools.shaft_hz) && finite(settings.tools.blade_hz) && settings.tools.shaft_hz > 0
          ? number(Math.round(settings.tools.blade_hz / settings.tools.shaft_hz), 0) : "--",
        rpm: finite(settings.tools.shaft_hz) ? number(settings.tools.shaft_hz * 60, 0) : "--"})],
      ["sonar_assist", yesNo(settings.tools.assist)]]);
    if (!stationDrafts.has("sonar-integration")) $("sonar-integration").value = String(settings.tools.integration_s);
    if (!stationDrafts.has("sonar-demon-band")) $("sonar-demon-band").value = settings.tools.demon_band_hz.map((value) => number(value, 0).replace(/\D/g, "")).join("-");
    if (!stationDrafts.has("sonar-heterodyne")) $("sonar-heterodyne").value = String(Math.round(settings.tools.heterodyne_hz));
    $("sonar-vernier").checked = settings.tools.vernier;
    const live = !settings.station_down;
    if (!stationDrafts.has("sonar-array-mode")) $("sonar-array-mode").value = settings.mode;
    const tasDeployed = ["DEPLOYING", "STREAMED"].includes(settings.tow.state);
    $("sonar-tas").textContent = t(tasDeployed ? "sonar_tas_retrieve" : "sonar_tas_deploy");
    $("sonar-tas").dataset.deployed = String(tasDeployed);
    $("sonar-tma").checked = settings.tma_enabled;
    $("sonar-notch").checked = settings.notch;
    $("sonar-listen-notch").checked = settings.notch;
    $("sonar-peak").checked = settings.peak_hold;
    if (!stationDrafts.has("sonar-audition-mode")) $("sonar-audition-mode").value = auditionMode;
    if (settings.band_preset && !stationDrafts.has("sonar-band")) $("sonar-band").value = settings.band_preset;
    if (settings.band_preset && !stationDrafts.has("sonar-listen-band")) $("sonar-listen-band").value = settings.band_preset;
    $("sonar-harmonic-candidates").replaceChildren(...settings.harmonic_candidates_hz.map((value) => {
      const option = node("option"); option.value = String(value); return option;
    }));
    $("sonar-ping").dataset.ready = String(live && settings.ping.ready &&
      (settings.mode !== "TOWED" || settings.tow.available));
    $("sonar-bt").dataset.ready = String(live && settings.bt.ready);
    $("sonar-tas").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state !== "FAULT");
    $("sonar-depth-submit").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state === "STREAMED");
    $("sonar-depth").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state === "STREAMED");
    stationRows($("sonar-observations"), payload.observations, (row) => [...sonarEntries(row),
      ["opz_release_status", t(row.released_to_opz ? "opz_release_active" : "opz_release_private")]]);
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
      ["ciws_ready", yesNo(payload.defense.ciws_ready)], ["aa_ready", yesNo(payload.defense.aa_ready)],
      ["opz_ciws_release", yesNo(payload.defense.ciws_released)]]);
    $("opz-ciws").checked = payload.defense.ciws_released;
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
    metrics($("engine-propulsion"), [["course", unit(propulsion.course, "\u00b0", 0)], ["ordered_course", unit(propulsion.target_course, "\u00b0", 0)],
      ["speed", unit(propulsion.speed, "kn")], ["ordered_speed", unit(propulsion.target_speed, "kn")],
      ["telegraph", propulsion.telegraph], ["rpm", unit(propulsion.rpm, "RPM", 0)], ["quiet_mode", yesNo(propulsion.quiet_mode)],
      ["cavitating", yesNo(propulsion.cavitating)], ["engine_fuel", unit(propulsion.fuel_kg / 1000, "t")],
      ["engine_fuel_capacity", unit(propulsion.fuel_capacity_kg / 1000, "t")], ["engine_fuel_burn", unit(propulsion.fuel_burn_kg_h, "kg/h", 0)],
      ["engine_endurance", unit(propulsion.fuel_endurance_h, "h", 0)], ["engine_range", unit(propulsion.fuel_range_nm, "NM", 0)]]);
    const machinery = payload.machinery;
    metrics($("engine-machinery"), [["station_state", machinery.station_state], ["speed_cap", unit(machinery.speed_cap, "kn")],
      ["effective_speed_cap", unit(machinery.effective_speed_cap, "kn")], ["flood", unit(machinery.flood, "%")],
      ["fire", unit(machinery.fire, "%")], ["engine_repair_teams", machinery.repair_teams.join(", ") || t("station_none")],
      ["engine_flood_trend", unit(machinery.repair_trend.flood_rate, "%/s")],
      ["engine_fire_trend", unit(machinery.repair_trend.fire_rate, "%/s")],
      ["noise", number(machinery.noise, 2)], ["grounded", yesNo(machinery.grounded)]]);
    const effects = payload.environment_effects;
    metrics($("engine-environment"), [["sea_state", number(effects.sea_state, 0)], ["roll", unit(effects.roll, "\u00b0")],
      ["pitch", unit(effects.pitch, "\u00b0")], ["tas_available", yesNo(effects.tas_available)],
      ["tas_performance", number(effects.tas_performance, 2)]]);
    const controls = payload.controls;
    if (!$("engine-telegraph").options.length) $("engine-telegraph").replaceChildren(...controls.orders.map((order) => {
      const option = node("option", order); option.value = order; return option;
    }));
    if (!stationDrafts.has("engine-telegraph")) $("engine-telegraph").value = propulsion.telegraph;
    if (!stationDrafts.has("engine-course")) $("engine-course").value = String(propulsion.target_course);
    $("engine-speed").max = String(Math.min(controls.speed_max_kn, machinery.speed_cap));
    $("engine-quiet").textContent = t(propulsion.quiet_mode ? "engine_quiet_disable" : "engine_quiet_enable");
    $("engine-quiet").setAttribute("aria-pressed", String(propulsion.quiet_mode));
  }

  function renderHelicopterStation(payload) {
    const asset = payload.asset;
    if (helicopterAudioSource !== null && helicopterAudioSource !== payload.acoustic.source && sonarAudioEnabled)
      stopSonarAudio("sonar_live_waiting");
    helicopterAudioSource = payload.acoustic.source;
    if (!stationDrafts.has("helicopter-buoy-mode")) $("helicopter-buoy-mode").value = asset.buoy_mode;
    const listen = $("helicopter-listen-source");
    if (listen.options.length !== payload.acoustic.sources.length ||
        payload.acoustic.sources.some((source, index) => listen.options[index]?.value !== source)) {
      listen.replaceChildren(...payload.acoustic.sources.map((source) => {
        const option = node("option", source === "DIP" ? t("helicopter_dip_picture") : source);
        option.value = source;
        return option;
      }));
    }
    listen.value = payload.acoustic.source;
    if (document.activeElement !== $("helicopter-listen-bearing"))
      $("helicopter-listen-bearing").value = payload.acoustic.listen_bearing ?? "";
    $("helicopter-audition-mode").value = payload.acoustic.audition_mode;
    $("helicopter-audio-band").value = payload.acoustic.band_preset;
    $("helicopter-audio-notch").checked = payload.acoustic.notch;
    if (document.activeElement !== $("helicopter-audio-gain"))
      $("helicopter-audio-gain").value = payload.acoustic.gain_db;
    $("helicopter-audio-gain-value").value = `${number(payload.acoustic.gain_db, 0)} dB`;
    $("helicopter-acoustic-text").textContent = t("helicopter_acoustic_equivalent", {
      rows: payload.acoustic.history.length, bearings: payload.acoustic.broadband.length,
      bins: payload.acoustic.demon.length});
    metrics($("helicopter-asset"), [["state", enumText(heloStates, asset.state)], ["airborne", yesNo(asset.airborne)],
      ["position", position(asset)], ["course", unit(asset.course, "\u00b0", 0)], ["fuel", unit(asset.fuel_s, "s", 0)],
      ["torpedoes", number(asset.torpedoes, 0)], ["buoys", number(asset.buoys, 0)],
      ["helicopter_hovering", yesNo(asset.hovering)], ["helicopter_dip_state", asset.dip_state],
      ["helicopter_dip_depth", unit(asset.dip_depth_m, "m", 0)],
      ["helicopter_dip_water", unit(asset.dip_water_depth_m, "m", 0)],
      ["helicopter_dip_cooldown", unit(asset.dip_ping_cooldown_s, "s", 0)]]);
    metrics($("helicopter-waypoint"), [["position", payload.waypoint ? position(payload.waypoint) : t("station_none")]]);
    const environment = payload.dip_environment;
    metrics($("helicopter-dip-environment"), [
      ["helicopter_dip_water", unit(environment.water_depth_m, "m", 0)],
      ["helicopter_dip_thermocline", unit(environment.thermocline_m, "m", 0)],
      ["helicopter_dip_limit", unit(environment.depth_limit_m, "m", 0)],
      ["helicopter_dip_clearance", unit(environment.bottom_clearance_m, "m", 0)],
      ["helicopter_dip_winch_rate", unit(environment.winch_rate_m_s, "m/s", 1)],
      ["helicopter_dip_below_layer", environment.below_thermocline === null ? t("station_none") : yesNo(environment.below_thermocline)]]);
    const ready = payload.readiness;
    metrics($("helicopter-readiness"), [["flightdeck_down", yesNo(ready.flightdeck_down)],
      ["helicopter_can_launch", yesNo(ready.can_launch)], ["helicopter_can_return", yesNo(ready.can_return)],
      ["deck_state", ready.deck_state], ["helicopter_can_waypoint", yesNo(ready.can_set_waypoint)],
      ["helicopter_can_buoy", yesNo(ready.can_deploy_buoy)],
      ["helicopter_can_dipping", yesNo(ready.can_set_dipping)],
      ["helicopter_can_dip_ping", yesNo(ready.can_dipping_ping)],
      ["helicopter_weather_launch", yesNo(ready.weather_launch_safe)],
      ["helicopter_weather_dipping", yesNo(ready.weather_dipping_safe)],
      ["helicopter_crosswind", unit(ready.crosswind_kn, "kn")],
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
    stationRows($("helicopter-buoys"), payload.buoys, (row) => [["reference", row.label], ["position", position(row)],
      ["battery", unit(row.battery_s, "s", 0)], ["active", yesNo(row.active)],
      ["helicopter_buoy_mode", t(row.mode === "ACTIVE" ? "helicopter_buoy_active" : "helicopter_buoy_passive")]]);
    stationRows($("helicopter-buoy-observations"), payload.buoy_observations, (row) => [
      ["reference", `${row.buoy_label} / ${row.label}`],
      ["helicopter_buoy_mode", t(row.mode === "ACTIVE" ? "helicopter_buoy_active" : "helicopter_buoy_passive")],
      ["bearing", unit(row.bearing, "°", 1)],
      ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "°", 1)],
      ["range", unit(row.range_nm, "NM", 1)], ["age", unit(row.age_s, "s", 0)],
      ["helicopter_qualified", yesNo(row.qualified)],
      ["opz_release_status", t(row.released_to_opz ? "opz_release_active" : "opz_release_private")]],
      "helicopter_dip_empty");
    stationRows($("helicopter-dip-observations"), payload.dip_observations, (row) => [
      ["reference", row.label], ["helicopter_dip_passive_bearing", unit(row.bearing, "°", 1)],
      ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "°", 1)],
      ["age", unit(row.age_s, "s", 0)],
      ["helicopter_dip_active_range", unit(row.range_nm, "NM", 1)],
      ["range_uncertainty", unit(row.range_uncertainty_nm, "NM", 2)],
      ["depth", unit(row.depth_m, "m", 0)],
      ["helicopter_dip_depth_uncertainty", unit(row.depth_uncertainty_m, "m", 0)],
      ["fix_age", unit(row.fix_age_s, "s", 0)],
      ["opz_release_status", t(row.released_to_opz ? "opz_release_active" : "opz_release_private")]],
      "helicopter_dip_empty");
    drawHelicopterDip(payload.dip_observations);
  }

  function drawHelicopterDip(rows) {
    const canvas = $("helicopter-dip-canvas"), ctx = canvas.getContext("2d");
    if (!ctx) return;
    const {width: w, height: h} = canvas;
    ctx.fillStyle = "#091b1a"; ctx.fillRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, radius = Math.min(w, h) * .43;
    ctx.strokeStyle = "#42645e"; ctx.lineWidth = 1;
    for (const scale of [.5, 1]) { ctx.beginPath(); ctx.arc(cx, cy, radius * scale, 0, Math.PI * 2); ctx.stroke(); }
    for (const angle of [0, 90, 180, 270]) {
      const a = angle * Math.PI / 180;
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.sin(a) * radius, cy - Math.cos(a) * radius); ctx.stroke();
    }
    for (const row of rows) {
      if (finite(row.bearing)) {
        const a = row.bearing * Math.PI / 180;
        if (finite(row.bearing_uncertainty_deg)) {
          ctx.strokeStyle = "#4e8f7d"; ctx.lineWidth = 1;
          for (const edge of [-1, 1]) {
            const b = (row.bearing + edge * row.bearing_uncertainty_deg) * Math.PI / 180;
            ctx.beginPath(); ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.sin(b) * radius, cy - Math.cos(b) * radius); ctx.stroke();
          }
        }
        ctx.strokeStyle = "#79d8a7"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.sin(a) * radius, cy - Math.cos(a) * radius); ctx.stroke();
      }
      if (finite(row.active_bearing) && finite(row.range_nm)) {
        const a = row.active_bearing * Math.PI / 180;
        const dx = Math.sin(a), dy = -Math.cos(a);
        const r = Math.min(radius, radius * row.range_nm / 20);
        if (finite(row.range_uncertainty_nm)) {
          ctx.strokeStyle = "#ffcc70"; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.arc(cx + dx * r, cy + dy * r,
            Math.max(3, Math.min(radius, radius * row.range_uncertainty_nm / 20)), 0, Math.PI * 2); ctx.stroke();
        }
        ctx.fillStyle = "#ffcc70"; ctx.beginPath(); ctx.arc(cx + dx * r, cy + dy * r, 5, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.fillStyle = "#a8c3bc"; ctx.font = "14px sans-serif";
    ctx.fillText(t("helicopter_dip_scale"), 12, h - 12);
  }

  function renderElokaStation(payload) {
    const intercepts = filteredEloka(payload.intercepts);
    metrics($("eloka-hardware"), [["df_sensors", number(payload.hardware.df_sensors, 0)],
      ["broadband_sensors", number(payload.hardware.broadband_sensors, 0)],
      ["ecm_channels", number(payload.hardware.ecm_channels, 0)],
      ["frequency", `${unit(payload.hardware.frequency_min_hz, "Hz", 0)} - ${unit(payload.hardware.frequency_max_hz, "Hz", 0)}`],
      ["reaction_time", unit(payload.hardware.reaction_s * 1000000, "\u00b5s", 1)]]);
    $("eloka-filter-count").textContent = t("eloka_filter_count", {visible: intercepts.length, total: payload.intercepts.length});
    stationRows($("eloka-intercepts"), intercepts, (row) => [["reference", row.label],
      ["bearing", unit(row.bearing, "\u00b0", 0)], ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
      ["frequency", unit(row.frequency_hz, "Hz", 0)], ["frequency_band", row.frequency_band.toUpperCase().replace("_", "/")], ["prf", unit(row.prf_hz, "Hz", 0)],
      ["modulation", row.modulation], ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
      ["signal_level", unit(row.signal_db, "dB", 0)], ["range_estimate", row.range_estimate_nm === null ? t("station_none") : unit(row.range_estimate_nm, "NM", 0)],
      ["scan_period", row.scan_period_s === null ? t("station_none") : unit(row.scan_period_s, "s", 1)],
      ["radar_type", row.radar_type || t("station_none")], ["threat", row.threat],
      ["ambiguous", yesNo(row.ambiguous)],
      ["synthetic_assumption", yesNo(row.synthetic_assumption)],
      ["jamming_effectiveness", row.jamming_effectiveness === null ? t("station_none") : number(row.jamming_effectiveness, 2)],
      ["jamming_technique", row.jamming_technique === null ? t("station_none") : t(`ecm_${row.jamming_technique}`)],
      ["ecm_power_draw", row.ecm_power_draw === null ? t("station_none") : number(row.ecm_power_draw, 2)],
      ["ecm_lock", yesNo(row.is_locked_on)], ["hoj_risk", yesNo(row.hoj_risk)],
      ["annotation", row.annotation || t("station_none")],
      ["opz_release_status", t(row.annotation ? "opz_release_annotated" : "opz_release_unannotated")],
      ["candidates", row.candidates.map((item) => item.score === null ? item.name : `${item.name}: ${number(item.score, 2)}`).join(" / ") || t("station_none")],
      ["correlations", row.correlations.map((item) => `${item.ref} / ${item.source}: ${number(item.score, 2)} (${t(item.ambiguous ? "ambiguous" : "unambiguous")}); ${unit(item.evidence.bearing, "\u00b0", 0)} / ${unit(item.evidence.age_s, "s", 0)}`).join(" / ") || t("station_none")]],
      "station_none", (row) => [...row.candidates.map((candidate) => actionButton("eloka_annotate_candidate",
        "eloka_annotate", {ref: row.ref, candidate_ref: candidate.ref}, !payload.station_down, {candidate: candidate.name})),
      actionButton(row.jamming ? "eloka_stop_jam" : "eloka_jam", "eloka_set_jamming",
        {ref: row.ref, enabled: !row.jamming}, !payload.station_down),
      ...["noise", "rgpo", "vgpo", "false_targets"].filter((technique) => technique !== row.jamming_technique)
        .map((technique) => actionButton(`ecm_${technique}`, "eloka_set_technique",
          {ref: row.ref, technique}, !payload.station_down)),
      actionButton(row.auto_jamming ? "eloka_auto_off" : "eloka_auto_on", "eloka_set_auto",
        {enabled: !row.auto_jamming}, !payload.station_down),
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
    plot.context.fillStyle = palette().muted;
    plot.context.textAlign = "center";
    plot.context.fillText(t(key), plot.width / 2, plot.height / 2);
  }

  // --- Weather & sonar analysis dialog (key 0, every station) -------------
  function toggleWeatherStation(force) {
    const dialog = $("weather-dialog");
    const open = force === undefined ? !dialog.open : force;
    if (open && !dialog.open) { dialog.hidden = false; dialog.showModal(); renderWeatherStation(); }
    else if (!open && dialog.open) dialog.close();
  }

  function renderWeatherStation() {
    const dialog = $("weather-dialog");
    const ws = v2State?.weather_station;
    if (!dialog.open || !ws) return;
    const a = ws.atmosphere, f = ws.flight, p = ws.profile;
    const limit = (value, max, digits = 0) => t("weather_limit_value", {value: number(value, digits), limit: number(max, digits)});
    metrics($("weather-environment"), [
      ["weather_time", `${a.time} · ${t(`weather_daylight_${a.daylight}`)}`],
      ["weather_moon", `${t(`weather_moon_${a.moon_phase}`)} · ${number(a.moon_illumination * 100, 0)} %`],
      ["weather_kind", `${t(`weather_kind_${a.weather}`)} · ${t(`weather_precip_${a.precipitation}`)}`],
      ["weather_visibility", unit(a.visibility_nm, "NM", 1)],
      ["weather_wind", `${number(a.wind_from_deg, 0)}° · ${unit(a.wind_kn, "kn", 0)} · ${t("weather_gust_value", {gust: number(a.gust_kn, 0)})}`],
      ["weather_beaufort", `${a.beaufort} · ${t("weather_sea_state_value", {sea: a.sea_state})}`],
      ["weather_pressure", `${unit(a.pressure_hpa, "hPa", 0)} · ${number(a.pressure_tendency_hpa_3h, 0)} hPa/3h · ${t(`weather_trend_${a.pressure_trend}`)}`],
      ["weather_temperature", `${unit(a.air_temp_c, "°C", 1)} / ${unit(a.sea_temp_c, "°C", 1)}`],
      ["weather_ceiling", a.ceiling_ft === null ? t("weather_ceiling_none") : unit(a.ceiling_ft, "ft", 0)],
      ["weather_icing", t(`weather_icing_${a.icing}`)],
    ]);
    $("weather-storm").hidden = !a.storm_warning;
    $("weather-effects").replaceChildren(...[["solar_heating", "solar"], ["wind_mixing", "wind"], ["freshwater", "rain"]].map(([key, label]) => {
      const item = node("li", t(`weather_effect_${label}`));
      item.dataset.active = String(ws.effects[key]);
      return item;
    }));
    const status = $("weather-flight-status");
    status.textContent = t(`weather_flight_${f.status}`);
    status.dataset.status = f.status;
    metrics($("weather-flight"), [
      ["weather_wind", limit(f.wind_kn, f.limits.wind_kn)],
      ["weather_gust", limit(f.gust_kn, f.limits.gust_kn)],
      ["weather_crosswind", limit(f.crosswind_kn, f.limits.crosswind_kn)],
      ["weather_visibility", limit(f.visibility_nm, f.limits.visibility_nm, 1)],
      ["weather_ceiling", f.ceiling_ft === null ? t("weather_ceiling_none") : limit(f.ceiling_ft, f.limits.ceiling_ft)],
      ["weather_sea_state", limit(f.sea_state, f.limits.sea_state)],
      ["weather_deck_roll", limit(Math.abs(f.roll_deg), f.limits.roll_deg, 1)],
      ["weather_deck_pitch", limit(Math.abs(f.pitch_deg), f.limits.pitch_deg, 1)],
      ["weather_icing", t(`weather_icing_${f.icing}`)],
      ["weather_dipping", t(f.dipping_safe ? "weather_dip_ok" : "weather_dip_blocked")],
    ]);
    const text = $("weather-profile-text");
    if (p === null) {
      text.textContent = t("weather_profile_none");
    } else {
      const shadowCells = p.shadow.reduce((sum, row) => sum + row.filter(Boolean).length, 0);
      text.textContent = [t("weather_profile_text", {
        age: number(p.age_s / 60, 0), offset: number(p.offset_nm, 1), layer: number(p.thermocline_m, 0),
        depth: number(p.water_depth_m, 0),
        sofar: p.sofar_axis_m === null ? t("weather_sofar_none") : t("weather_sofar_depth", {depth: number(p.sofar_axis_m, 0)}),
        shadow: shadowCells, cz: p.cz_bands_nm.map(([low, high]) => `${number(low, 0)}-${number(high, 0)}`).join(" / "),
      }), p.stale ? t("weather_profile_stale") : "",
        p.dip_relative_to_layer ? t(`weather_dip_${p.dip_relative_to_layer}`) : t("weather_shadow_hint")].filter(Boolean).join(" ");
    }
    drawWeatherProfile(p);
  }

  // Sound speed at a depth, linearly interpolated from a measured profile.
  function profileSpeedAt(depths, speeds, depth) {
    if (!depths.length) return null;
    if (depth <= depths[0]) return speeds[0];
    for (let index = 1; index < depths.length; index++) {
      if (depth <= depths[index]) {
        const upper = depths[index - 1], lower = depths[index];
        const share = lower > upper ? (depth - upper) / (lower - upper) : 0;
        return speeds[index - 1] + share * (speeds[index] - speeds[index - 1]);
      }
    }
    return speeds[speeds.length - 1];
  }

  // Pointer position over the weather profile (CSS px), or null.
  let weatherCursor = null;

  function weatherProfileGeometry(p, width, height) {
    const depthMax = Math.max(1, p.depths_m[p.depths_m.length - 1]);
    const top = 18, bottom = height - 18, leftW = Math.max(90, width * .26);
    const sx = leftW + 6, sw = width - sx - 4;
    return {depthMax, top, bottom, leftW, sx, sw};
  }

  function weatherCursorReading(p, width, height) {
    if (!weatherCursor || !p) return null;
    const {depthMax, top, bottom, leftW, sx, sw} = weatherProfileGeometry(p, width, height);
    const {x, y} = weatherCursor;
    if (y < top || y > bottom || x < 4 || x > width - 4) return null;
    const depth = (y - top) / (bottom - top) * depthMax;
    const speed = profileSpeedAt(p.depths_m, p.speeds_m_s, depth);
    if (x <= leftW) {
      return {x: null, y, text: t("weather_cursor_depth", {depth: number(depth, 0), speed: number(speed, 1)})};
    }
    if (x < sx) return null;
    const range = (x - sx) / sw * p.range_nm;
    const parts = [t("weather_cursor_section", {range: number(range, 1), depth: number(depth, 0), speed: number(speed, 1)})];
    const column = Math.min(p.shadow.length - 1, Math.floor(range / p.range_nm * p.shadow.length));
    let row = -1;
    for (let index = 0; index + 1 < p.depth_edges_m.length; index++)
      if (depth >= p.depth_edges_m[index] && depth < p.depth_edges_m[index + 1]) row = index;
    if (column >= 0 && row >= 0 && p.shadow[column]?.[row]) parts.push(t("weather_cursor_shadow"));
    if (p.cz_bands_nm.some(([low, high]) => range >= low && range <= high)) parts.push(t("weather_cursor_cz"));
    return {x, y, text: parts.join(" · ")};
  }

  function drawWeatherProfile(p) {
    const plot = visualContext("weather-profile");
    if (!plot) return;
    if (p === null) { drawEmpty(plot, "weather_profile_none"); return; }
    const {context, width, height} = plot;
    const colors = palette();
    const {depthMax, top, bottom, leftW} = weatherProfileGeometry(p, width, height);
    const y = (depth) => top + Math.min(1, Math.max(0, depth / depthMax)) * (bottom - top);
    const low = Math.min(...p.speeds_m_s), high = Math.max(...p.speeds_m_s, low + 1);
    context.strokeStyle = colors.line;
    context.strokeRect(4, top, leftW - 8, bottom - top);
    context.strokeStyle = colors.accent;
    context.beginPath();
    p.depths_m.forEach((depth, index) => {
      const x = 10 + (p.speeds_m_s[index] - low) / (high - low) * (leftW - 20);
      if (index) context.lineTo(x, y(depth)); else context.moveTo(x, y(depth));
    });
    context.stroke();
    const sx = leftW + 6, sw = width - sx - 4;
    context.strokeStyle = colors.line;
    context.strokeRect(sx, top, sw, bottom - top);
    context.fillStyle = "rgb(150 50 50 / .45)";
    p.shadow.forEach((row, column) => row.forEach((cell, index) => {
      if (!cell || p.depth_edges_m[index] > depthMax) return;
      const y0 = y(p.depth_edges_m[index]), y1 = y(Math.min(p.depth_edges_m[index + 1], depthMax));
      context.fillRect(sx + column * sw / p.shadow.length, y0, sw / p.shadow.length, Math.max(1, y1 - y0));
    }));
    context.strokeStyle = "#5adc96";
    for (const ray of p.rays) {
      context.beginPath();
      ray.forEach(([range, depth], index) => {
        const x = sx + range / p.range_nm * sw;
        if (index) context.lineTo(x, y(depth)); else context.moveTo(x, y(depth));
      });
      context.stroke();
    }
    context.textAlign = "left";
    for (const [depth, color, key] of [[p.thermocline_m, colors.amber, "weather_layer_label"], [p.sofar_axis_m, colors.blue, "weather_sofar_label"]]) {
      if (depth === null || depth > depthMax) continue;
      context.strokeStyle = color; context.fillStyle = color; context.setLineDash([5, 5]);
      context.beginPath(); context.moveTo(4, y(depth)); context.lineTo(width - 4, y(depth)); context.stroke();
      context.setLineDash([]);
      context.fillText(t(key, {depth: number(depth, 0)}), sx + 8, y(depth) - 4);
    }
    context.fillStyle = colors.muted;
    context.fillText(`${number(depthMax, 0)} m · ${number(low, 0)}-${number(high, 0)} m/s`, 8, height - 4);
    context.textAlign = "right";
    context.fillText(`${number(p.range_nm, 0)} NM`, width - 6, height - 4);
    const reading = weatherCursorReading(p, width, height);
    if (reading) {
      context.strokeStyle = colors.accent; context.setLineDash([2, 3]);
      context.beginPath(); context.moveTo(4, reading.y); context.lineTo(width - 4, reading.y); context.stroke();
      if (reading.x !== null) { context.beginPath(); context.moveTo(reading.x, top); context.lineTo(reading.x, bottom); context.stroke(); }
      context.setLineDash([]);
      const label = reading.text, labelWidth = context.measureText(label).width + 10;
      const lx = Math.min(width - labelWidth - 4, Math.max(4, (reading.x ?? leftW / 2) + 8));
      const ly = reading.y > top + 22 ? reading.y - 18 : reading.y + 6;
      context.fillStyle = colors.panel || "#07151c"; context.fillRect(lx, ly, labelWidth, 16);
      context.fillStyle = colors.accent; context.textAlign = "left";
      context.fillText(label, lx + 5, ly + 12);
    }
  }

  function plotAxes(plot, xmax, ymax, xunit, yunit, xorigin = 0, reverseY = false) {
    const context = plot.context;
    const {left, top, width, height} = plotArea(plot.width, plot.height);
    context.fillStyle = palette().muted; context.strokeStyle = palette().line; context.textAlign = "center";
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

  // One packed 0xAABBGGRR colour per quantised level, in the byte order the
  // Uint32 view of ImageData uses on this platform.
  const heatmapPalettes = new Map();
  function heatmapPalette() {
    if (heatmapPalettes.has(sonarDisplay.palette)) return heatmapPalettes.get(sonarDisplay.palette);
    const little = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
    const channels = {green: [68, 255, 154], amber: [255, 184, 62], cyan: [65, 225, 255]}[sonarDisplay.palette] || [68, 255, 154];
    const lut = Uint32Array.from({length: 256}, (_, index) => {
      const level = (index / 255) ** .72;
      const r = Math.round(3 + level * channels[0]), g = Math.round(8 + level * channels[1]), b = Math.round(6 + level * channels[2]);
      return little ? ((255 << 24) | (b << 16) | (g << 8) | r) >>> 0 : ((r << 24) | (g << 16) | (b << 8) | 255) >>> 0;
    });
    heatmapPalettes.set(sonarDisplay.palette, lut);
    return lut;
  }
  const heatmapRasters = new Map();

  // The host publishes at most every 0.5 s, so drawing the acoustic plots only
  // when data arrived made the waterfalls jump in steps. They are instead drawn
  // against a smoothed display clock. The game always runs in real time and
  // never pauses, so the clock simply advances 1:1 with wall time from the last
  // publication while the world is live, runs a fixed jitter delay behind it
  // (rows scroll in over the top edge instead of popping in) and only slews
  // gently. Purely presentational: nothing here is sent to the host.
  const DISPLAY_CLOCK_LAG_S = .75;
  const displayClock = {context: null, sim: 0, wall: 0, live: false, shown: null, shownWall: 0};

  function sampleDisplayClock(state, sim = state?.clock?.sim) {
    if (!state || !finite(sim)) return;
    const context = `${state.session}:${state.epoch}`;
    const live = state.phase === "live";
    const reset = displayClock.context !== context;
    if (reset) { displayClock.context = context; displayClock.shown = null; }
    // One publication reaches the page twice (stream frame and state poll);
    // its earliest arrival is the better anchor for extrapolation.
    if (reset || sim > displayClock.sim || live !== displayClock.live)
      Object.assign(displayClock, {sim, wall: performance.now(), live});
  }

  function displaySimNow(wallNow = performance.now()) {
    if (displayClock.context === null) return v2State?.clock?.sim ?? 0;
    const rate = displayClock.live ? 1 : 0;
    const elapsed = Math.min(1.5, Math.max(0, (wallNow - displayClock.wall) / 1000));
    const target = displayClock.sim + elapsed * rate - DISPLAY_CLOCK_LAG_S;
    if (displayClock.shown === null || Math.abs(target - displayClock.shown) > 3) {
      displayClock.shown = target;
    } else {
      const dt = Math.min(.25, Math.max(0, (wallNow - displayClock.shownWall) / 1000));
      displayClock.shown += Math.max(0, dt * (rate + Math.max(-.1, Math.min(.1, target - displayClock.shown))));
    }
    displayClock.shownWall = wallNow;
    return displayClock.shown;
  }

  // Plots redrawn on every animation frame between publications, by canvas id.
  // A frame only blits cached rasters and strokes a few hundred points.
  const animatedPlots = new Map();
  let plotFrame = null;
  let plotLastDraw = 0;

  function registerAnimatedPlot(id, draw) {
    animatedPlots.set(id, {role: v2State?.role, draw});
  }

  function plotAnimation(now) {
    plotFrame = null;
    if (now - plotLastDraw >= 30) {
      plotLastDraw = now;
      for (const [id, plot] of animatedPlots) {
        const element = $(id);
        if (plot.role !== v2State?.role || !element || element.closest("[hidden]")) continue;
        plot.draw(now);
      }
    }
    syncPlotAnimation();
  }

  function syncPlotAnimation() {
    const role = v2State?.role;
    const active = !document.hidden && connected && v2State?.phase === "live" && (role === "sonar" || role === "helicopter") &&
      !$("role-visuals").hidden && [...animatedPlots.values()].some((plot) => plot.role === role);
    if (active && plotFrame === null) plotFrame = requestAnimationFrame(plotAnimation);
    if (!active && plotFrame !== null) { cancelAnimationFrame(plotFrame); plotFrame = null; }
  }

  // A waterfall has tens of thousands of cells. Painting each with fillRect blocked
  // the browser's main thread long enough to starve the live-sonar audio scheduler,
  // so the cells are written into one pixel buffer. The buffer is positioned by
  // row time stamps and rebuilt only when rows or display settings change; each
  // animation frame merely blits it at the display clock's offset.
  function heatmap(id, rows, frequencies = null, axisMaximum = null, overlay = null, historyS = sonarDisplay.history) {
    const now = v2State?.clock?.sim ?? 0;
    rows = rows.map((row) => finite(row.stamp) ? row : {...row, stamp: now - row.age_s})
      .filter((row) => row.stamp >= now - historyS - 5 && row.bins.length);
    const spec = {rows, frequencies, axisMaximum, overlay, historyS};
    const draw = (wallNow) => drawHeatmap(id, spec, wallNow);
    registerAnimatedPlot(id, draw);
    return draw(performance.now());
  }

  function heatmapRaster(id, spec, width, height, pixelsPerSecond, headroom) {
    const {rows, frequencies, historyS} = spec;
    let raster = heatmapRasters.get(id);
    const settings = [width, height, headroom, historyS, sonarDisplay.palette, sonarDisplay.black, sonarDisplay.contrast].join(":");
    if (raster?.rows === rows && raster.settings === settings) return raster;
    const rasterHeight = height + headroom;
    if (!raster || raster.canvas.width !== width || raster.canvas.height !== rasterHeight) {
      const off = document.createElement("canvas");
      off.width = width; off.height = rasterHeight;
      const context = off.getContext("2d");
      const image = context.createImageData(width, rasterHeight);
      raster = {canvas: off, context, image, pixels: new Uint32Array(image.data.buffer)};
      heatmapRasters.set(id, raster);
    }
    const anchor = Math.max(...rows.map((row) => row.stamp));
    Object.assign(raster, {rows, settings, anchor});
    const pixels = raster.pixels;
    const colors = heatmapPalette();
    pixels.fill(colors[0]);
    const xmax = spec.axisMaximum ?? (frequencies ? 300 : 360);
    const count = Math.max(...rows.map((row) => row.bins.length));
    const stamps = rows.map((row) => row.stamp).sort((a, b) => a - b);
    const gaps = stamps.slice(1).map((stamp, index) => stamp - stamps[index]).filter((gap) => gap > 0);
    const samplePeriod = gaps.length ? gaps.sort((a, b) => a - b)[Math.floor(gaps.length / 2)] : .25;
    const cellHeight = Math.max(1, Math.round(samplePeriod * pixelsPerSecond));
    for (const row of rows) {
      const age = anchor - row.stamp;
      const y0 = Math.floor(headroom + age * pixelsPerSecond);
      if (y0 < 0 || y0 >= rasterHeight) continue;
      const y1 = Math.min(rasterHeight, y0 + cellHeight);
      const persistence = Math.exp(-age / Math.max(8, historyS * .8));
      for (let x = 0; x < row.bins.length; x++) {
        const raw = Math.max(0, Math.min(1, row.bins[x]));
        const level = Math.max(0, Math.min(1, (raw - sonarDisplay.black) / Math.max(.01, 1 - sonarDisplay.black) * sonarDisplay.contrast * persistence));
        const start = frequencies ? frequencies[x] / xmax : x / count;
        const end = frequencies ? (frequencies[x + 1] ?? xmax) / xmax : (x + 1) / count;
        const x0 = Math.min(width - 1, Math.max(0, Math.floor(start * width)));
        const x1 = Math.min(width, Math.max(x0 + 1, Math.floor(end * width)));
        const color = colors[Math.round(level * 255)];
        for (let y = y0; y < y1; y++) pixels.fill(color, y * width + x0, y * width + x1);
      }
    }
    raster.context.putImageData(raster.image, 0, 0);
    return raster;
  }

  function drawHeatmap(id, spec, wallNow) {
    const plot = visualContext(id);
    if (!plot) return null;
    if (!spec.rows.length) { drawEmpty(plot); return null; }
    const xmax = spec.axisMaximum ?? (spec.frequencies ? 300 : 360);
    // A fixed time axis: rows scroll down through it rather than the axis
    // rescaling while the history fills.
    const area = plotAxes(plot, xmax, spec.historyS, spec.frequencies ? " Hz" : "°", "s");
    const width = Math.max(1, Math.round(area.width)), height = Math.max(1, Math.round(area.height));
    const pixelsPerSecond = height / spec.historyS;
    const headroom = Math.min(height, Math.ceil((DISPLAY_CLOCK_LAG_S + 1.5) * pixelsPerSecond) + 2);
    const raster = heatmapRaster(id, spec, width, height, pixelsPerSecond, headroom);
    const dpr = area.context.getTransform().a || 1;
    const scaleY = area.height / height;
    const offset = Math.round(((displaySimNow(wallNow) - raster.anchor) * pixelsPerSecond - headroom) * scaleY * dpr) / dpr;
    const context = area.context;
    context.save();
    context.beginPath(); context.rect(0, 0, area.width, area.height); context.clip();
    context.fillStyle = "#030806"; context.fillRect(0, 0, area.width, area.height);
    context.imageSmoothingEnabled = false;
    context.drawImage(raster.canvas, 0, offset, area.width, (height + headroom) * scaleY);
    context.restore();
    spec.overlay?.(area);
    return area;
  }

  // Spectra ease towards each publication instead of jumping to it.
  const SPECTRUM_SMOOTHING_S = .15;
  const spectrumStates = new Map();

  function spectrum(id, values, markers = [], frequencies = null, xmax = 80, xmin = 0, overlay = null) {
    const spec = {values, markers, frequencies, xmax, xmin, overlay};
    const draw = (wallNow) => drawSpectrum(id, spec, wallNow);
    registerAnimatedPlot(id, draw);
    return draw(performance.now());
  }

  function easedSpectrum(id, values, wallNow) {
    const maximum = Math.max(1e-6, ...values.map((value) => Math.abs(value)));
    let state = spectrumStates.get(id);
    if (!state || state.values.length !== values.length) {
      state = {values: Float64Array.from(values), maximum, wall: wallNow};
      spectrumStates.set(id, state);
      return state;
    }
    const alpha = 1 - Math.exp(-Math.max(0, wallNow - state.wall) / 1000 / SPECTRUM_SMOOTHING_S);
    for (let index = 0; index < values.length; index++) state.values[index] += (values[index] - state.values[index]) * alpha;
    state.maximum += (maximum - state.maximum) * alpha;
    state.wall = wallNow;
    return state;
  }

  function drawSpectrum(id, spec, wallNow) {
    const {markers, frequencies, xmax, xmin} = spec;
    let plot = visualContext(id);
    if (!plot) return;
    if (!spec.values.length) { spectrumStates.delete(id); drawEmpty(plot); return; }
    const eased = easedSpectrum(id, spec.values, wallNow);
    const values = eased.values;
    let maximum = eased.maximum;
    for (const value of values) maximum = Math.max(maximum, Math.abs(value));
    plot = plotAxes(plot, xmax - xmin, maximum, " Hz", "rel.", xmin, true);
    plot.context.strokeStyle = palette().accent;
    plot.context.beginPath();
    values.forEach((value, index) => {
      const x = frequencies ? (frequencies[index] - xmin) / (xmax - xmin) * plot.width : values.length === 1 ? 0 : index / (values.length - 1) * plot.width;
      const y = plot.height - Math.max(0, value) / maximum * (plot.height - 12);
      index ? plot.context.lineTo(x, y) : plot.context.moveTo(x, y);
    });
    plot.context.stroke();
    drawPeakLabels(plot, values, frequencies, xmin, xmax, maximum, markers);
    plot.context.fillStyle = palette().amber;
    for (const marker of markers.slice(0, 20)) plot.context.fillText(marker.text, Math.max(2, Math.min(plot.width - 50, marker.x * plot.width)), 14);
    spec.overlay?.(plot);
    return plot;
  }

  // Same rule as sonar_view.spectrum_peaks: prominent local maxima above the
  // median floor, parabola-refined, strongest first and thinned so labels
  // never overlap.
  const PEAK_LABEL_W = 30;
  function spectrumPeaks(values, frequencies, limit, minSeparation) {
    const count = values.length;
    if (count < 3 || frequencies.length !== count || limit <= 0) return [];
    const v = Array.from(values, (value) => Number.isFinite(value) ? value : 0);
    const top = Math.max(...v);
    const sorted = [...v].sort((a, b) => a - b);
    const floor = count % 2 ? sorted[(count - 1) / 2] : (sorted[count / 2 - 1] + sorted[count / 2]) / 2;
    const span = top - floor;
    if (top < .03 || span <= 1e-6) return [];
    const threshold = Math.max(floor + .25 * span, floor * 1.6, .03);
    const candidates = [];
    for (let i = 1; i < count - 1; i++) {
      if (!(v[i] > v[i - 1] && v[i] >= v[i + 1] && v[i] >= threshold)) continue;
      const left = Math.min(...v.slice(Math.max(0, i - 4), i));
      const right = Math.min(...v.slice(i + 1, i + 5));
      if (v[i] - Math.max(left, right) < .1 * span) continue;
      const [x0, x1, x2] = [frequencies[i - 1], frequencies[i], frequencies[i + 1]];
      const [y0, y1, y2] = [v[i - 1], v[i], v[i + 1]];
      const denominator = (x0 - x1) * (x0 - x2) * (x1 - x2);
      let hz = x1;
      if (Math.abs(denominator) > 1e-12) {
        const a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / denominator;
        const b = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / denominator;
        if (a < 0) hz = Math.max(x0, Math.min(x2, -b / (2 * a)));
      }
      candidates.push({hz, level: v[i], index: i});
    }
    candidates.sort((a, b) => b.level - a.level || a.index - b.index);
    const chosen = [];
    for (const peak of candidates) {
      if (chosen.every((other) => Math.abs(peak.hz - other.hz) >= minSeparation)) chosen.push(peak);
      if (chosen.length >= limit) break;
    }
    return chosen.sort((a, b) => a.hz - b.hz);
  }

  // Same rule as sonar_view.place_peak_labels: strongest first, above the
  // apex or beside it, and a value with no free place is dropped.
  function placePeakLabels(apexes, width, height, obstacles) {
    const taken = [...obstacles], placed = [];
    const collides = (box) => taken.some((other) => box.x - 2 < other.x + other.w && other.x < box.x + box.w + 2 && box.y < other.y + other.h && other.y < box.y + box.h);
    for (const apex of [...apexes].sort((a, b) => b.level - a.level || a.x - b.x)) {
      const sideTop = Math.max(1, apex.y - 6);
      const options = [[{x: apex.x - apex.w / 2, y: apex.y - 15, w: apex.w, h: 12}, true]];
      for (const top of [sideTop, sideTop + 12]) for (const x of [apex.x + 4, apex.x - 4 - apex.w]) options.push([{x, y: top, w: apex.w, h: 12}, false]);
      for (const [box, above] of options) {
        if (box.x < 0 || box.y < 0 || box.x + box.w > width || box.y + box.h > height || collides(box)) continue;
        taken.push(box); placed.push({...apex, box, above});
        break;
      }
    }
    return placed;
  }

  function drawPeakLabels(plot, values, frequencies, xmin, xmax, maximum, markers) {
    // Automatic peak labels are a training aid; off, the operator reads lines
    // with the cursor (same rule as the uConsole).
    if (v2State?.sonar?.settings?.tools && !v2State.sonar.settings.tools.assist) return;
    if (plot.width < PEAK_LABEL_W || xmax <= xmin) return;
    const hz = frequencies ?? Array.from(values, (_, index) => values.length === 1 ? xmin : xmin + index / (values.length - 1) * (xmax - xmin));
    const scale = plot.width / (xmax - xmin);
    const normalised = Array.from(values, (value) => Math.max(0, value) / maximum);
    const context = plot.context;
    context.save();
    context.font = "10px ui-monospace, monospace";
    const markerBoxes = markers.slice(0, 20).map((marker) => ({x: Math.max(2, Math.min(plot.width - 50, marker.x * plot.width)), y: 3, w: context.measureText(marker.text).width, h: 13}));
    const apexes = [];
    for (const peak of spectrumPeaks(normalised, hz, 12, 0)) {
      const x = (peak.hz - xmin) * scale;
      if (x < 0 || x > plot.width || markers.some((marker) => Math.abs(marker.x * plot.width - x) < 4)) continue;
      const text = peak.hz < 100 ? number(peak.hz, 1) : number(peak.hz, 0);
      apexes.push({x, y: plot.height - peak.level * (plot.height - 12), w: context.measureText(text).width, text, level: peak.level});
    }
    context.fillStyle = palette().text;
    context.strokeStyle = palette().text;
    context.textBaseline = "top";
    for (const label of placePeakLabels(apexes, plot.width, plot.height, markerBoxes)) {
      if (label.above) { context.beginPath(); context.moveTo(label.x, label.y - 1); context.lineTo(label.x, label.y - 4); context.stroke(); }
      context.fillText(label.text, label.box.x, label.box.y);
    }
    context.restore();
  }

  function drawBandLimits(plot, band, maximum = 300) {
    if (!plot || !Array.isArray(band) || band.length !== 2) return;
    plot.context.strokeStyle = palette().amber;
    for (const frequency of band) {
      const x = Math.max(0, Math.min(plot.width, frequency / maximum * plot.width));
      plot.context.beginPath(); plot.context.moveTo(x, 0);
      plot.context.lineTo(x, plot.height); plot.context.stroke();
    }
  }

  function drawHarmonicGuides(plot, fundamental, maximum) {
    if (!plot || !finite(fundamental) || fundamental <= 0) return;
    plot.context.save();
    plot.context.strokeStyle = palette().amber;
    plot.context.fillStyle = palette().amber;
    plot.context.setLineDash([3, 3]);
    plot.context.font = "10px ui-monospace, monospace";
    for (let order = 1; order <= 12 && fundamental * order <= maximum; order++) {
      const hz = fundamental * order;
      const x = hz / maximum * plot.width;
      plot.context.beginPath(); plot.context.moveTo(x, 0); plot.context.lineTo(x, plot.height); plot.context.stroke();
      plot.context.fillText(`${order}f`, Math.min(plot.width - 18, x + 2), 11);
    }
    plot.context.restore();
  }

  function bandSpectrum(id, visual, low, high) {
    const pairs = visual.bin_frequencies_hz.map((frequency, index) =>
      [frequency, visual.spectrum[index]]).filter(([frequency]) => frequency >= low && frequency <= high);
    spectrum(id, pairs.map((pair) => pair[1]), [], pairs.map((pair) => pair[0]), high, low);
  }

  const broadbandVisible = () => sonarVisualPage === "broadband" || sonarVisualPage === "overview";

  function drawSonarVisuals() {
    const visual = v2State.sonar.visualization;
    const historyRows = (name, fallback) => {
      const rows = [...sonarHistory[name].values()].filter((row) => row.stamp >= v2State.clock.sim - 600);
      return rows.length ? rows.sort((a, b) => b.stamp - a.stamp) : fallback;
    };
    const broadbandHistory = historyRows("broadband", visual.broadband.history);
    const lofarHistory = historyRows("lofar", visual.lofar.history);
    const demonHistory = historyRows("demon", visual.demon.history);
    heatmap("sonar-broadband", broadbandHistory, null, null, (broadband) => {
      const focusedTrack = selectedTrack();
      const bearing = visual.receiver.listen_bearing % 360;
      const half = visual.receiver.beam_width_deg / 2;
      broadband.context.strokeStyle = palette().muted;
      for (const value of [(bearing - half + 360) % 360, (bearing + half) % 360]) {
        const x = value / 360 * broadband.width;
        broadband.context.beginPath(); broadband.context.moveTo(x, 0);
        broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
      }
      broadband.context.strokeStyle = palette().amber;
      const x = bearing / 360 * broadband.width;
      broadband.context.beginPath(); broadband.context.moveTo(x, 0);
      broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
      if (finite(focusedTrack?.bearing)) {
        const selectedX = focusedTrack.bearing % 360 / 360 * broadband.width;
        broadband.context.strokeStyle = palette().accent;
        broadband.context.lineWidth = 3;
        broadband.context.beginPath(); broadband.context.moveTo(selectedX, 0);
        broadband.context.lineTo(selectedX, broadband.height); broadband.context.stroke();
        broadband.context.lineWidth = 1;
      }
    });
    const lofarGuides = (plot) => {
      drawBandLimits(plot, v2State.sonar.settings.band_hz);
      drawHarmonicGuides(plot, v2State.sonar.settings.harmonic_hz, 300);
    };
    heatmap("sonar-lofar", lofarHistory, visual.lofar.bin_frequencies_hz, null, lofarGuides);
    const vernier = visual.lofar.vernier;
    if (vernier) {
      // Vernier: the operator's 20 Hz window at native 0.5 Hz resolution.
      spectrum("sonar-spectrum", vernier.bins, [], vernier.bins.map((_, index) => vernier.low_hz + index * vernier.step_hz),
        vernier.high_hz, vernier.low_hz, null);
    } else spectrum("sonar-spectrum", visual.lofar.spectrum, [], visual.lofar.bin_frequencies_hz, 300, 0, lofarGuides);
    bandSpectrum("sonar-band-low", visual.lofar, 0, 40);
    bandSpectrum("sonar-band-mid", visual.lofar, 40, 100);
    bandSpectrum("sonar-band-high", visual.lofar, 100, 300);
    const peak = visual.demon.analysis?.modulation_peak_hz;
    const demonFrequencies = visual.demon.spectrum.map((_, index) => index + 1);
    const demonGuides = (plot) => {
      drawHarmonicGuides(plot, sonarDisplay.demonCursor, 50);
      const tools = v2State.sonar.settings.tools;
      plot.context.save(); plot.context.font = "11px ui-monospace, monospace";
      for (const [value, label, color] of [[tools.shaft_hz, "S", palette().accent], [tools.blade_hz, "B", palette().amber]]) {
        if (!finite(value) || value > 50) continue;
        const x = value / 50 * plot.width;
        plot.context.strokeStyle = color; plot.context.fillStyle = color;
        plot.context.beginPath(); plot.context.moveTo(x, 0); plot.context.lineTo(x, plot.height); plot.context.stroke();
        plot.context.fillText(`${label} ${number(value, 1)}`, Math.min(plot.width - 60, x + 3), 26);
      }
      plot.context.restore();
    };
    heatmap("sonar-demon", demonHistory.map((row) => ({...row, bins: row.bins.slice(0, 50)})), demonFrequencies.slice(0, 50), 50, demonGuides);
    spectrum("sonar-demon-spectrum", visual.demon.spectrum.slice(0, 50),
      finite(peak) && peak <= 50 ? [{x: peak / 50, text: `${number(peak, 1)} Hz`}] : [], demonFrequencies.slice(0, 50), 50, 0, demonGuides);
    const tmaSim = v2State.clock.sim;
    const drawTma = (wallNow) => {
      let tma = visualContext("sonar-tma-plot");
      if (!tma) return;
      const contacts = visual.tma.filter((row) => row.bearings.length);
      if (!contacts.length) drawEmpty(tma);
      // Bearings age smoothly between publications, in step with the waterfalls.
      const shift = Math.max(0, Math.min(1.5, displaySimNow(wallNow) + DISPLAY_CLOCK_LAG_S - tmaSim));
      const maxAge = Math.max(1, ...contacts.flatMap((track) => track.bearings.map((point) => point.age_s + shift)));
      tma = plotAxes(tma, maxAge, 360, " s", "°");
      contacts.forEach((track, index) => {
        const isSelected = track.ref === selected;
        tma.context.strokeStyle = isSelected ? palette().accent : ["#7fb8a5", palette().amber, palette().blue, palette().red][index % 4];
        tma.context.lineWidth = isSelected ? 3 : 1;
        tma.context.beginPath();
        track.bearings.forEach((point, pointIndex) => {
          const x = (point.age_s + shift) / maxAge * tma.width;
          const y = point.bearing / 360 * tma.height;
          pointIndex && Math.abs(point.bearing - track.bearings[pointIndex - 1].bearing) < 180 ? tma.context.lineTo(x, y) : tma.context.moveTo(x, y);
        });
        tma.context.stroke();
        // Operator hypothesis: predicted bearings (measured minus residual).
        if (isSelected && track.residuals_deg.length === track.bearings.length) {
          tma.context.save(); tma.context.setLineDash([5, 4]); tma.context.strokeStyle = palette().amber; tma.context.lineWidth = 2;
          tma.context.beginPath();
          track.bearings.forEach((point, pointIndex) => {
            const predicted = ((point.bearing - track.residuals_deg[pointIndex]) % 360 + 360) % 360;
            const x = (point.age_s + shift) / maxAge * tma.width, y = predicted / 360 * tma.height;
            pointIndex ? tma.context.lineTo(x, y) : tma.context.moveTo(x, y);
          });
          tma.context.stroke(); tma.context.restore();
        }
      });
      tma.context.lineWidth = 1;
      const chosen = visual.tma.find((row) => row.ref === selected);
      if (chosen) $("sonar-tma-readout").value = t("sonar_tma_summary", {rate: finite(chosen.summary.rate_deg_min) ? number(chosen.summary.rate_deg_min, 2) : "--", legs: chosen.summary.legs}) + " | " + (chosen.evaluation ? t("sonar_tma_evaluation", {
        rms: number(chosen.evaluation.rms_deg, 1), trend: number(chosen.evaluation.systematic_deg, 1),
        fit: number(chosen.evaluation.fit * 100, 0), observable: number(chosen.evaluation.observability * 100, 0)}) : t("sonar_tma_pending"));
    };
    registerAnimatedPlot("sonar-tma-plot", drawTma);
    drawTma(performance.now());
    let bt = visualContext("sonar-environment");
    if (bt) {
      if (!visual.bt || !visual.bt.depths_m.length) drawEmpty(bt);
      else {
        const min = Math.min(...visual.bt.speeds_m_s), max = Math.max(...visual.bt.speeds_m_s, min + 1);
        const depth = Math.max(1, ...visual.bt.depths_m);
        bt = plotAxes(bt, max - min, depth, " m/s", "m", min);
        bt.context.fillStyle = palette().muted;
        bt.context.fillText(`${number(min, 0)}–${number(max, 0)} m/s`, bt.width / 2, -7);
        if (finite(visual.bt.thermocline_m)) { const y = visual.bt.thermocline_m / depth * bt.height; bt.context.strokeStyle = palette().amber; bt.context.setLineDash([4, 4]); bt.context.beginPath(); bt.context.moveTo(0, y); bt.context.lineTo(bt.width, y); bt.context.stroke(); bt.context.setLineDash([]); }
        bt.context.strokeStyle = palette().blue; bt.context.beginPath();
        const speedX = (speed) => 12 + (speed - min) / (max - min) * (bt.width - 24);
        visual.bt.depths_m.forEach((value, index) => {
          const x = speedX(visual.bt.speeds_m_s[index]);
          const y = value / depth * bt.height;
          index ? bt.context.lineTo(x, y) : bt.context.moveTo(x, y);
        });
        bt.context.stroke();
        // Labelled reference depths: layer, seabed and the sound-speed minimum.
        bt.context.textAlign = "right";
        if (finite(visual.bt.thermocline_m)) {
          bt.context.fillStyle = palette().amber;
          bt.context.fillText(t("sonar_bt_layer", {depth: number(visual.bt.thermocline_m, 0)}),
            bt.width - 4, Math.max(12, visual.bt.thermocline_m / depth * bt.height - 4));
        }
        if (finite(visual.bt.water_depth_m) && visual.bt.water_depth_m <= depth) {
          const y = visual.bt.water_depth_m / depth * bt.height;
          bt.context.strokeStyle = palette().muted; bt.context.beginPath(); bt.context.moveTo(0, y); bt.context.lineTo(bt.width, y); bt.context.stroke();
          bt.context.fillStyle = palette().muted;
          bt.context.fillText(t("sonar_bt_bottom", {depth: number(visual.bt.water_depth_m, 0)}), bt.width - 4, Math.max(12, y - 4));
        }
        const slowest = visual.bt.speeds_m_s.indexOf(min);
        if (slowest >= 0) {
          const x = speedX(min), y = visual.bt.depths_m[slowest] / depth * bt.height;
          bt.context.fillStyle = palette().blue; bt.context.beginPath(); bt.context.arc(x, y, 3.5, 0, Math.PI * 2); bt.context.fill();
          bt.context.textAlign = x < bt.width / 2 ? "left" : "right";
          bt.context.fillText(t("sonar_bt_minimum", {speed: number(min, 0), depth: number(visual.bt.depths_m[slowest], 0)}),
            x + (x < bt.width / 2 ? 8 : -8), Math.min(bt.height - 4, Math.max(12, y + 4)));
        }
        if (finite(sonarDisplay.btCursorDepth) && sonarDisplay.btCursorDepth <= depth) {
          const y = sonarDisplay.btCursorDepth / depth * bt.height;
          bt.context.strokeStyle = palette().accent; bt.context.setLineDash([2, 3]);
          bt.context.beginPath(); bt.context.moveTo(0, y); bt.context.lineTo(bt.width, y); bt.context.stroke();
          bt.context.setLineDash([]);
          if (sonarDisplay.btCursorText) {
            bt.context.fillStyle = palette().accent; bt.context.textAlign = "left";
            bt.context.fillText(sonarDisplay.btCursorText, 4, y > 16 ? y - 4 : y + 13);
          }
        }
        bt.context.textAlign = "center";
      }
    }
    const active = visualContext("sonar-active");
    if (active) {
      const radius = Math.min(active.width, active.height) * .44, cx = active.width / 2, cy = active.height / 2;
      active.context.strokeStyle = palette().line;
      for (const scale of [.25, .5, .75, 1]) { active.context.beginPath(); active.context.arc(cx, cy, radius * scale, 0, Math.PI * 2); active.context.stroke(); }
      const maxRange = Math.max(5, Math.ceil(Math.max(0, ...visual.active_echoes.map((echo) => echo.range_nm)) / 5) * 5);
      active.context.fillStyle = palette().muted; active.context.fillText(`N · ${number(maxRange, 0)} NM`, cx, 18);
      if (visual.bt && finite(visual.bt.thermocline_m) && finite(visual.bt.water_depth_m)) {
        const duct = Math.max(.15, Math.min(.9, visual.bt.thermocline_m / Math.max(1, visual.bt.water_depth_m)));
        active.context.strokeStyle = `${palette().blue}88`;
        active.context.setLineDash([5, 5]); active.context.beginPath(); active.context.arc(cx, cy, radius * duct, 0, Math.PI * 2); active.context.stroke(); active.context.setLineDash([]);
      }
      for (const echo of visual.active_echoes) {
        const angle = echo.bearing * Math.PI / 180;
        const r = echo.range_nm / maxRange * radius;
        const strength = Math.max(.12, Math.min(1, Math.exp(-echo.age_s / 12) * (.35 + Math.max(0, echo.snr_db) / 30)));
        active.context.globalAlpha = strength; active.context.fillStyle = palette().amber; active.context.beginPath();
        active.context.arc(cx + Math.sin(angle) * r, cy - Math.cos(angle) * r, 2 + strength * 3, 0, Math.PI * 2); active.context.fill();
      }
      active.context.globalAlpha = 1;
      if (!visual.active_echoes.length) drawEmpty(active);
    }
    let aScan = visualContext("sonar-a-scan");
    if (aScan) {
      const maxRange = Math.max(5, Math.ceil(Math.max(0, ...visual.active_echoes.map((echo) => echo.range_nm)) / 5) * 5);
      aScan = plotAxes(aScan, maxRange, 1, " NM", "AMP", 0, true);
      const samples = 256;
      const trace = Array.from({length: samples}, (_, index) => .035 + .025 * (1 + Math.sin(index * 12.9898 + visual.active_echoes.length)));
      for (const echo of visual.active_echoes) {
        const center = echo.range_nm / maxRange * (samples - 1);
        const width = Math.max(1, echo.range_uncertainty_nm / maxRange * samples);
        const amplitude = Math.max(.08, Math.min(.95, .18 + echo.snr_db / 35)) * Math.exp(-echo.age_s / 12);
        for (let index = 0; index < samples; index++) trace[index] += amplitude * Math.exp(-.5 * ((index - center) / width) ** 2);
      }
      aScan.context.strokeStyle = palette().accent; aScan.context.beginPath();
      trace.forEach((value, index) => { const x = index / (samples - 1) * aScan.width; const y = aScan.height - Math.min(1, value) * (aScan.height - 8); index ? aScan.context.lineTo(x, y) : aScan.context.moveTo(x, y); });
      aScan.context.stroke();
    }
    $("sonar-broadband-text").textContent = t("sonar_broadband_equivalent", {rows: broadbandHistory.length, bins: broadbandHistory.at(-1)?.bins.length || 0});
    $("sonar-lofar-text").textContent = t("sonar_lofar_equivalent", {rows: lofarHistory.length, bins: visual.lofar.spectrum.length, held: yesNo(visual.lofar.held)});
    $("sonar-demon-text").textContent = t("sonar_demon_equivalent", {rows: demonHistory.length, bins: visual.demon.spectrum.length, hypotheses: visual.demon.analysis?.hypotheses.length || 0});
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
    if (role === "opz") return {own: payload.own_assets.ship, observations: [...payload.observations, ...payload.fusions], assets: [...(payload.own_assets.helicopter.airborne ? [payload.own_assets.helicopter] : []), ...payload.own_assets.weapons], bearingLogs: [], fixes: []};
    if (role === "radio") return {own: payload.navigation, observations: payload.tactical, assets: [], bearingLogs: payload.logged_bearings, fixes: payload.logged_fixes};
    return {own: payload.navigation, observations: payload.tactical,
      assets: [payload.asset, ...payload.buoys.map((buoy) => ({...buoy, display: buoy.label})),
        ...(payload.waypoint ? [{...payload.waypoint, waypoint: true}] : [])], bearingLogs: [], fixes: []};
  }

  // The host sweep turns at a constant rate in sim time, so every sample fixes
  // one phase offset (bearing - rate * sim). The strobe is drawn against the
  // shared smoothed display clock, which only ever advances (with at most
  // +/-10 % rate correction), so the beam turns steadily and never steps back
  // when a delayed or duplicate publication arrives.
  const wrap360 = (value) => ((value % 360) + 360) % 360;

  function currentOpzSweepBearing() {
    const model = opzSweepSample;
    if (!model) return null;
    return wrap360(model.offset + (displaySimNow() + DISPLAY_CLOCK_LAG_S) * model.rate);
  }

  function updateOpzSweepSample(state) {
    const radar = state?.role === "opz" ? state.opz.radar : null;
    if (!radar || !finite(radar.sweep_bearing) || !finite(state.clock?.sim)) {
      opzSweepSample = null; stopOpzSweepAnimation(); return;
    }
    const rate = finite(radar.sweep_rate_deg_s) ? radar.sweep_rate_deg_s : 90;
    opzSweepSample = {offset: wrap360(radar.sweep_bearing - state.clock.sim * rate), rate};
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
    if (!opzSweepActive()) { stopOpzSweepAnimation(); drawOpzSweepOverlay(); return; }
    if (opzSweepFrame !== null) return;
    const animate = () => {
      opzSweepFrame = null;
      if (!opzSweepActive()) return;
      drawOpzSweepOverlay();
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

  function drawChartHazards(context, hazards, point, width, height, pxPerNm, info) {
    for (const hazard of hazards) {
      const [x, y] = point(hazard.x, hazard.y);
      if (x < -8 || x > width + 8 || y < -8 || y > height + 8) continue;
      addMapInfo(info, x, y, "hazard", hazard);
      context.save();
      context.lineWidth = 1.5;
      context.strokeStyle = hazard.kind === "wreck" ? "#96b4c8" : "#dcbe78";
      context.beginPath();
      if (hazard.kind === "wreck") {
        context.moveTo(x - 8, y); context.lineTo(x + 8, y);
        for (const dx of [-4, 0, 4]) { context.moveTo(x + dx, y - 5); context.lineTo(x + dx, y + 5); }
      } else {
        context.moveTo(x - 5, y); context.lineTo(x + 5, y); context.moveTo(x, y - 5); context.lineTo(x, y + 5);
        context.moveTo(x - 4, y - 4); context.lineTo(x + 4, y + 4); context.moveTo(x - 4, y + 4); context.lineTo(x + 4, y - 4);
      }
      context.stroke();
      if (pxPerNm >= 12) {
        context.fillStyle = context.strokeStyle;
        context.textAlign = "left";
        context.fillText(t("chart_hazard_depth", {depth: number(hazard.top_depth_m, 0)}), x + 12, y + 4);
      }
      context.restore();
    }
  }

  function addMapInfo(list, x, y, kind, item) {
    if (list.length < 512) list.push({x, y, kind, item});
  }

  function chartDepthAt(x, y) {
    const grid = chart?.geography?.depths;
    if (!Array.isArray(grid) || !grid.length || !finite(chart.size_nm)) return null;
    const n = grid.length;
    const row = grid[Math.min(n - 1, Math.max(0, Math.floor(y / chart.size_nm * n)))];
    if (!Array.isArray(row) || !row.length) return null;
    const value = row[Math.min(row.length - 1, Math.max(0, Math.floor(x / chart.size_nm * row.length)))];
    return finite(value) ? value : null;
  }

  function mapTooltipLines(hit, worldX, worldY, own) {
    const lines = [];
    if (hit?.kind === "track") {
      const row = hit.item;
      lines.push(String(row.label || row.ref || ""));
      if (row.source) lines.push(t("map_tip_source", {source: row.source}));
      if (row.classification !== undefined || row.affiliation !== undefined)
        lines.push(t("map_tip_class", {classification: classificationText(row.classification),
          affiliation: enumText(affiliations, row.affiliation)}));
      if (finite(row.bearing)) lines.push(finite(row.range_nm) ?
        t("map_tip_bearing_range", {bearing: number(row.bearing, 0), range: number(row.range_nm, 1)}) :
        t("map_tip_bearing", {bearing: number(row.bearing, 0)}));
      if (finite(row.course)) lines.push(t("map_tip_course", {course: number(row.course, 0),
        speed: finite(row.speed_kn) ? number(row.speed_kn, 0) : "--"}));
      if (finite(row.altitude_m)) lines.push(t("map_tip_altitude", {altitude: number(row.altitude_m, 0)}));
      if (finite(row.age_s)) lines.push(t("map_tip_age", {age: number(row.age_s, 0),
        quality: finite(row.quality) ? number(row.quality * 100, 0) : "--"}));
      return lines;
    }
    if (hit?.kind === "fix") {
      lines.push(t("map_tip_fix", {label: String(hit.item.label || ""), source: String(hit.item.source || "")}));
      if (finite(hit.item.uncertainty_nm)) lines.push(t("map_tip_uncertainty", {value: number(hit.item.uncertainty_nm, 1)}));
      if (finite(hit.item.depth_m)) lines.push(t("map_tip_depth_estimate", {depth: number(hit.item.depth_m, 0)}));
      return lines;
    }
    if (hit?.kind === "own") {
      lines.push(t("map_tip_own"));
      lines.push(t("map_tip_course", {course: number(hit.item.course, 0), speed: number(hit.item.speed, 1)}));
      return lines;
    }
    if (hit?.kind === "asset") {
      lines.push(hit.item.waypoint ? t("station_waypoint") : String(hit.item.display || hit.item.ref || t("helicopter")));
      if (finite(hit.item.depth_m)) lines.push(t("map_tip_depth_estimate", {depth: number(hit.item.depth_m, 0)}));
      if (finite(hit.item.course)) lines.push(t("map_tip_course", {course: number(hit.item.course, 0), speed: "--"}));
      return lines;
    }
    if (hit?.kind === "hazard") {
      const hazard = hit.item;
      lines.push(t(hazard.kind === "wreck" ? "map_tip_wreck" : "map_tip_rock"));
      lines.push(t("map_tip_hazard_top", {depth: number(hazard.top_depth_m, 0)}));
      if (hazard.kind === "wreck") lines.push(t("map_tip_wreck_length", {length: number(hazard.length_m, 0)}));
      lines.push(t("map_tip_hazard_note"));
      return lines;
    }
    if (hit?.kind === "base") {
      lines.push(String(hit.item.name || ""));
      lines.push(t("map_tip_airbase"));
      return lines;
    }
    if (!finite(worldX) || !finite(worldY) || !chart || worldX < 0 || worldY < 0 ||
        worldX > chart.size_nm || worldY > chart.size_nm) return lines;
    lines.push(t("map_tip_position", {x: number(worldX, 1), y: number(worldY, 1)}));
    const depth = chartDepthAt(worldX, worldY);
    if (depth !== null) lines.push(depth <= 0 ? t("map_tip_land") : t("map_tip_chart_depth", {depth: number(depth, 0)}));
    if (own && finite(own.x) && finite(own.y)) {
      const dx = worldX - own.x, dy = worldY - own.y;
      lines.push(t("map_tip_from_own", {bearing: number(((Math.atan2(dx, -dy) * 180 / Math.PI) + 360) % 360, 0),
        range: number(Math.hypot(dx, dy), 1)}));
    }
    return lines;
  }

  function showMapTooltip(event, lines) {
    const element = $("map-tooltip");
    if (!lines.length) { element.hidden = true; return; }
    element.replaceChildren(...lines.map((line, index) => node(index ? "span" : "strong", line)));
    element.hidden = false;
    const margin = 14, box = element.getBoundingClientRect();
    const left = Math.min(event.clientX + margin, window.innerWidth - box.width - 4);
    const top = Math.min(event.clientY + margin, window.innerHeight - box.height - 4);
    element.style.left = `${Math.max(4, left)}px`;
    element.style.top = `${Math.max(4, top)}px`;
  }

  function hideMapTooltip() {
    $("map-tooltip").hidden = true;
  }

  function nearestMapInfo(list, x, y, radius = 14) {
    let best = null;
    for (const hit of list) {
      const distance = Math.hypot(hit.x - x, hit.y - y);
      if (distance <= radius && (best === null || distance < best.distance)) best = {hit, distance};
    }
    return best?.hit || null;
  }

  function rayLengthToCanvasEdge(x, y, dx, dy, width, height) {
    const candidates = [];
    if (dx > 0) candidates.push((width - x) / dx);
    else if (dx < 0) candidates.push(-x / dx);
    if (dy > 0) candidates.push((height - y) / dy);
    else if (dy < 0) candidates.push(-y / dy);
    return Math.max(0, Math.min(...candidates.filter((value) => finite(value) && value >= 0)));
  }

  function drawOpzSweepOverlay() {
    const width = roleMapSweepCanvas.clientWidth;
    const height = roleMapSweepCanvas.clientHeight;
    if (!width || !height || !chart || $("role-map-sweep").closest("[hidden]")) {
      releaseCanvas(roleMapSweepCanvas);
      return;
    }
    resizeCanvas(roleMapSweepCanvas, roleMapSweepCtx, width, height);
    roleMapSweepCtx.clearRect(0, 0, width, height);
    const radar = v2State?.role === "opz" ? v2State.opz.radar : null;
    const own = v2State?.role === "opz" ? v2State.opz.own_assets.ship : null;
    if (!radar?.live || !(radar.surface || radar.air) || !hasPosition(own)) return;
    const geometry = roleMapGeometry("opz", width, height);
    if (!geometry) return;
    const [ox, oy] = geometry.point(own.x, own.y);
    const bearing = v2State.phase === "live" && connected ?
      currentOpzSweepBearing() ?? radar.sweep_bearing : radar.sweep_bearing;
    if (!finite(bearing)) return;
    const angle = bearing * Math.PI / 180;
    const dx = Math.sin(angle), dy = -Math.cos(angle);
    // The beam reaches as far as the own radar does: the effective range of
    // the longest-reaching active radar, not the display scale or canvas edge.
    const reach = Math.max(radar.surface ? radar.surface_effective_range_nm : 0,
      radar.air ? radar.air_effective_range_nm : 0);
    const length = reach * geometry.scale;
    roleMapSweepCtx.strokeStyle = palette().accent;
    roleMapSweepCtx.lineWidth = 1.5;
    roleMapSweepCtx.beginPath();
    roleMapSweepCtx.moveTo(ox, oy);
    roleMapSweepCtx.lineTo(ox + dx * length, oy + dy * length);
    roleMapSweepCtx.stroke();
  }

  function drawRoleMap(role) {
    const plot = visualContext("role-map");
    roleMapHits = [];
    roleMapInfo = [];
    if (!plot || !chart) return;
    const payload = v2State[role], data = mapPayload(role), viewState = roleMapViews[role];
    plot.context.textAlign = "left";
    plot.context.textBaseline = "alphabetic";
    if (!viewState.initialized) { viewState.initialized = true; viewState.follow = true; viewState.zoom = role === "opz" ? chart.size_nm / (2 * payload.radar.range_nm) : 2; }
    const followTarget = role === "helicopter" && payload.asset.airborne && hasPosition(payload.asset) ?
      payload.asset : data.own;
    if (viewState.follow && hasPosition(followTarget)) { viewState.x = followTarget.x; viewState.y = followTarget.y; }
    $("role-map-follow").setAttribute("aria-pressed", String(Boolean(viewState.follow)));
    $("role-map-follow").textContent = t(role === "helicopter" ? "follow_helicopter" : "follow");
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
      if (x >= 0 && x <= plot.width) { plot.context.beginPath(); plot.context.moveTo(x, 0); plot.context.lineTo(x, plot.height); plot.context.stroke(); }
      if (y >= 0 && y <= plot.height) { plot.context.beginPath(); plot.context.moveTo(0, y); plot.context.lineTo(plot.width, y); plot.context.stroke(); }
    }
    plot.context.strokeStyle = palette().line; plot.context.fillStyle = "#233d38";
    for (const land of chart.landmasses) {
      plot.context.beginPath(); land.points.forEach(([x, y], index) => { const p = point(x, y); index ? plot.context.lineTo(...p) : plot.context.moveTo(...p); });
      plot.context.closePath(); plot.context.fill(); plot.context.stroke();
    }
    plot.context.font = "12px sans-serif";
    plot.context.lineWidth = 3;
    plot.context.strokeStyle = "#07151c";
    plot.context.fillStyle = "#b5c8cf";
    for (let value = 0; value <= chart.size_nm; value += step) {
      const [x, y] = point(value, value), text = String(value);
      if (x >= 0 && x + plot.context.measureText(text).width + 2 <= plot.width) {
        plot.context.strokeText(text, x + 2, plot.height - 5);
        plot.context.fillText(text, x + 2, plot.height - 5);
      }
      if (y >= 10 && y <= plot.height - 20) {
        const baseline = y + 4;
        plot.context.strokeText(text, 4, baseline);
        plot.context.fillText(text, 4, baseline);
      }
    }
    plot.context.lineWidth = 1;
    plot.context.fillStyle = palette().muted;
    for (const label of [...(geo?.labels || []), ...(geo?.airbases || [])]) {
      const [x, y] = point(label.x, label.y);
      if (x >= 0 && x <= plot.width && y >= 0 && y <= plot.height) plot.context.fillText(label.name, x + 5, y - 5);
    }
    for (const base of geo?.airbases || []) { const [x, y] = point(base.x, base.y); plot.context.strokeRect(x - 3, y - 3, 6, 6); addMapInfo(roleMapInfo, x, y, "base", base); }
    // Charted wrecks (hull line with masts) and underwater rocks (asterisk).
    drawChartHazards(plot.context, geo?.hazards || [], point, plot.width, plot.height,
      Math.abs(point(1, 0)[0] - point(0, 0)[0]), roleMapInfo);
    const [ox, oy] = hasPosition(data.own) ? point(data.own.x, data.own.y) : [plot.width / 2, plot.height / 2];
    if (hasPosition(data.own)) {
      addRoleMapHit(null, ox, oy);
      addMapInfo(roleMapInfo, ox, oy, "own", data.own);
      plot.context.save(); plot.context.translate(ox, oy); plot.context.rotate(data.own.course * Math.PI / 180);
      plot.context.strokeStyle = palette().accent; plot.context.fillStyle = palette().accent; plot.context.beginPath();
      plot.context.moveTo(0, -9); plot.context.lineTo(-5, 6); plot.context.lineTo(5, 6); plot.context.closePath(); plot.context.fill();
      plot.context.beginPath(); plot.context.moveTo(0, -9); plot.context.lineTo(0, -35); plot.context.stroke(); plot.context.restore();
    }
    for (const row of data.observations) {
      const isSelected = row.ref === selected;
      plot.context.strokeStyle = isSelected ? palette().accent : colors[row.affiliation] || colors.UNKNOWN;
      plot.context.lineWidth = isSelected ? 3 : 1;
      if (hasPosition(row)) {
        const [x, y] = point(row.x, row.y);
        addRoleMapHit(row.ref, x, y);
        addMapInfo(roleMapInfo, x, y, "track", row);
        if (finite(row.range_uncertainty_nm)) { plot.context.beginPath(); plot.context.arc(x, y, row.range_uncertainty_nm * scale, 0, Math.PI * 2); plot.context.stroke(); }
        // Same NATO symbol as the chart and the uConsole: affiliation frame + domain glyph.
        const symbolColor = colors[row.affiliation] || colors.UNKNOWN;
        drawNatoSymbol(plot.context, x, y, row.affiliation, row.domain, symbolColor, 7);
        plot.context.strokeStyle = isSelected ? palette().accent : symbolColor;
        plot.context.lineWidth = isSelected ? 3 : 1;
        if (isSelected) { plot.context.beginPath(); plot.context.arc(x, y, 14, 0, Math.PI * 2); plot.context.stroke(); }
        plot.context.fillStyle = symbolColor;
        plot.context.fillText(row.label || row.ref, x + 12, y - 10);
        if (finite(row.course)) {
          const angle = row.course * Math.PI / 180, tipX = x + Math.sin(angle) * 22, tipY = y - Math.cos(angle) * 22;
          plot.context.beginPath(); plot.context.moveTo(x, y); plot.context.lineTo(tipX, tipY); plot.context.stroke();
          if (finite(row.speed_kn)) plot.context.fillText(unit(row.speed_kn, "kn", 0), tipX + 4, tipY + 4);
        }
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
    plot.context.lineWidth = 1;
    for (const log of data.bearingLogs) {
      const [x, y] = point(log.observer_x, log.observer_y), angle = log.bearing * Math.PI / 180;
      plot.context.strokeStyle = palette().amber; plot.context.setLineDash([3, 4]); plot.context.beginPath(); plot.context.moveTo(x, y); plot.context.lineTo(x + Math.sin(angle) * plot.width, y - Math.cos(angle) * plot.width); plot.context.stroke(); plot.context.setLineDash([]);
    }
    for (const item of [...data.fixes, ...data.assets]) if (hasPosition(item)) {
      const [x, y] = point(item.x, item.y);
      addRoleMapHit(null, x, y);
      addMapInfo(roleMapInfo, x, y, "asset", item);
      plot.context.strokeStyle = item.waypoint ? palette().amber : palette().blue;
      if (finite(item.uncertainty_nm)) { plot.context.beginPath(); plot.context.arc(x, y, item.uncertainty_nm * scale, 0, Math.PI * 2); plot.context.stroke(); }
      plot.context.strokeRect(x - 4, y - 4, 8, 8);
      plot.context.fillStyle = plot.context.strokeStyle; plot.context.fillText(item.waypoint ? t("station_waypoint") : item.display || item.ref || t("helicopter"), x + 6, y + 12);
    }
    if (role === "opz" && hasPosition(data.own)) {
      if (payload.radar.live && (payload.radar.surface || payload.radar.air)) {
        for (const range of [payload.radar.surface_effective_range_nm, payload.radar.air_effective_range_nm]) if (finite(range)) { plot.context.strokeStyle = "#365d69"; plot.context.beginPath(); plot.context.arc(ox, oy, range * scale, 0, Math.PI * 2); plot.context.stroke(); }
      }
      const byRef = new Map(data.observations.map((row) => [row.ref, row]));
      for (const fusion of payload.fusions) if (hasPosition(fusion)) for (const ref of fusion.members) { const member = byRef.get(ref); if (hasPosition(member)) { plot.context.strokeStyle = "#697f88"; plot.context.beginPath(); plot.context.moveTo(...point(fusion.x, fusion.y)); plot.context.lineTo(...point(member.x, member.y)); plot.context.stroke(); } }
    }
    drawPlotLayer(plot.context, point, scale, plot.width, plot.height, null);
    renderPlotList();
    $("role-map-scale").textContent = t("role_map_scale", {distance: number(chart.size_nm / viewState.zoom, 0)});
    plot.context.save(); plot.context.textAlign = "right"; plot.context.fillStyle = palette().text; plot.context.fillText("N ↑", plot.width - 10, 18); plot.context.restore();
    const equivalent = [t("role_map_own", {position: hasPosition(data.own) ? position(data.own) : t("unavailable")})];
    equivalent.push(...data.observations.map((row) => t("role_map_observation", {ref: row.ref, bearing: number(row.bearing, 0), position: hasPosition(row) ? position(row) : t("bearing_only")})));
    equivalent.push(...data.fixes.map((row) => t("role_map_fix", {ref: row.ref, position: position(row), uncertainty: number(row.uncertainty_nm, 1)})));
    $("role-map-text").replaceChildren(...equivalent.slice(0, 256).map((text) => node("li", text)));
    if (role === "opz") drawOpzSweepOverlay();
  }

  function gauge(context, x, y, radius, value, maximum, label) {
    context.strokeStyle = palette().line; context.lineWidth = 6; context.beginPath(); context.arc(x, y, radius, Math.PI, Math.PI * 2); context.stroke();
    context.strokeStyle = palette().accent; context.beginPath(); context.arc(x, y, radius, Math.PI, Math.PI + Math.PI * Math.max(0, Math.min(1, value / Math.max(1e-6, maximum)))); context.stroke();
    context.fillStyle = palette().text; context.textAlign = "center"; context.fillText(label, x, y + 18);
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
      plot.context.strokeStyle = assigned ? palette().accent : room.state === "ZERSTOERT" ? palette().red : "#536873";
      plot.context.lineWidth = assigned ? 3 : 1.5; plot.context.strokeRect(x, y, width, height);
      plot.context.fillStyle = palette().text; plot.context.textAlign = "left"; plot.context.fillText(room.name, x + 6, y + 20, roomW - 18);
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
    plot.context.fillStyle = p.cavitating ? palette().red : palette().accent; plot.context.textAlign = "center"; plot.context.fillText(`${p.telegraph} / ${t(p.cavitating ? "cavitating" : "not_cavitating")}`, plot.width / 2, 22);
    $("engine-instruments-text").textContent = t("engine_equivalent", {telegraph: p.telegraph, rpm: number(p.rpm, 0), speed: number(p.speed, 1), target: number(p.target_speed, 1), cap: number(m.effective_speed_cap, 1), noise: number(m.noise, 2), roll: number(e.roll, 1), pitch: number(e.pitch, 1)});
  }

  function drawElokaVisual() {
    const plot = visualContext("eloka-scope"), payload = v2State.eloka;
    if (!plot) return;
    const intercepts = filteredEloka(payload.intercepts);
    const simNow = finite(v2State.clock?.sim) ? v2State.clock.sim : 0;
    const scopeWidth = plot.width * .43;
    const radius = Math.min(scopeWidth, plot.height) * .38, cx = scopeWidth / 2, cy = plot.height / 2;
    plot.context.strokeStyle = palette().line; plot.context.beginPath(); plot.context.arc(cx, cy, radius, 0, Math.PI * 2); plot.context.stroke();
    for (const row of intercepts) { const angle = row.bearing * Math.PI / 180; plot.context.save(); plot.context.globalAlpha = .2 + .8 * row.quality; plot.context.strokeStyle = palette().amber; plot.context.lineWidth = 2 + row.quality * 3; if (row.signal_state !== "LIVE") plot.context.setLineDash([5, 5]); plot.context.beginPath(); plot.context.moveTo(cx, cy); plot.context.lineTo(cx + Math.sin(angle) * radius, cy - Math.cos(angle) * radius); plot.context.stroke(); plot.context.restore(); }
    const focused = intercepts[0];
    const gx = scopeWidth + 12, gy = 16, gw = plot.width - gx - 12, gh = plot.height - 32;
    plot.context.strokeStyle = palette().line; plot.context.lineWidth = 1; plot.context.strokeRect(gx, gy, gw, gh);
    plot.context.beginPath(); plot.context.moveTo(gx, gy + gh * .52); plot.context.lineTo(gx + gw, gy + gh * .52); plot.context.stroke();
    if (focused && gw > 40 && gh > 60) {
      const motionNow = Math.min(simNow, simNow - focused.age_s + 2);
      const rate = .35 + Math.min(2.4, Math.log10(Math.max(1, focused.prf_hz || 500)) * .38);
      const techniqueRate = focused.jamming_technique === "vgpo" ? 1 + (focused.jamming_effectiveness || 0) * 1.8 : 1;
      const phase = (((Math.round(focused.frequency_hz / 1e6) + Math.round(focused.prf_hz || 500)) % 360) * Math.PI / 180) + motionNow * rate * techniqueRate;
      const pulses = Math.max(3, Math.min(12, Math.round(2 + Math.log10(Math.max(1, focused.prf_hz || 500)) * 2)));
      const hop = focused.modulation === "frequency_agile" ? ((Math.floor(motionNow * 2) % 7) - 3) * .025 : 0;
      const centers = (focused.modulation === "frequency_agile" ? [.28, .5, .72] : [.5]).map((value) => value + hop);
      const width = focused.modulation === "continuous_wave" ? .035 : ["pulse_doppler", "frequency_agile"].includes(focused.modulation) ? .09 : .14;
      plot.context.strokeStyle = palette().amber; plot.context.lineWidth = 2; plot.context.beginPath();
      for (let i = 0; i < 40; i++) { const x = i / 39; let value = Math.max(...centers.map((center) => Math.exp(-Math.pow((x - center) / width, 2)))); if (focused.jamming_technique === "noise") value = Math.max(value, (.28 + .08 * Math.sin(i * .71 + motionNow * 5)) * (focused.jamming_effectiveness || 0)); if (focused.jamming_technique === "false_targets") value = Math.max(value, ...centers.map((center) => .55 * (focused.jamming_effectiveness || 0) * Math.exp(-Math.pow((x - center - .14) / width, 2)))); const px = gx + 6 + x * (gw - 12), py = gy + gh * .47 - value * focused.quality * gh * .34; if (i) plot.context.lineTo(px, py); else plot.context.moveTo(px, py); }
      plot.context.stroke(); plot.context.strokeStyle = palette().accent; plot.context.beginPath();
      for (let i = 0; i < 48; i++) { const x = i / 47; const movingX = (x + motionNow * rate * .08 + (focused.jamming_technique === "rgpo" ? motionNow * (focused.jamming_effectiveness || 0) * .03 : 0)) % 1; let value;
        if (focused.modulation === "continuous_wave") value = Math.sin(Math.PI * 10 * x + phase);
        else if (focused.modulation === "frequency_agile") { const steps = [-.75, .15, .7, -.25, .45, -.55, .85, 0]; value = steps[(Math.min(7, Math.floor(movingX * 8)) + Math.floor(motionNow * 2)) % 8]; }
        else if (["pulse", "pulse_doppler"].includes(focused.modulation)) { const envelope = Math.max(0, 1 - ((movingX * pulses) % 1) / .16); value = envelope * 2 - .85; if (focused.modulation === "pulse_doppler") value *= .65 + .35 * Math.sin(Math.PI * 3 * pulses * movingX + phase); }
        else value = .55 * Math.sin(Math.PI * 6 * x + phase) + .25 * Math.sin(Math.PI * 22 * x + phase * .37);
        if (focused.jamming_technique === "noise") value = value * (1 - .45 * (focused.jamming_effectiveness || 0)) + Math.sin(i * 2.17 + motionNow * 11) * .55 * (focused.jamming_effectiveness || 0);
        if (focused.jamming_technique === "false_targets") value += Math.sin(Math.PI * 6 * ((movingX + .14) % 1) + phase) * .35 * (focused.jamming_effectiveness || 0);
        value *= focused.quality;
        const px = gx + 6 + x * (gw - 12), py = gy + gh * .76 - value * gh * .17; if (i) plot.context.lineTo(px, py); else plot.context.moveTo(px, py); }
      plot.context.stroke(); plot.context.fillStyle = palette().text; plot.context.textAlign = "left";
      plot.context.fillText(`${focused.label} / ${focused.modulation}`, gx + 8, gy + 17, gw - 16);
      plot.context.fillStyle = focused.signal_state === "LIVE" ? palette().accent : palette().amber; plot.context.textAlign = "right";
      const signalLabel = focused.signal_state === "MEMORY" ? t("eloka_signal_memory", {age: number(focused.age_s, 0)}) : t(`eloka_signal_${focused.signal_state.toLowerCase()}`);
      plot.context.fillText(signalLabel, gx + gw - 8, gy + 17, gw / 2);
      plot.context.fillStyle = palette().text; plot.context.textAlign = "left";
      plot.context.fillText(`${number(focused.frequency_hz / 1e9, 3)} GHz / ${number(focused.prf_hz, 0)} Hz`, gx + 8, gy + gh - 7, gw - 16);
    }
    if (!intercepts.length) drawEmpty(plot);
    const equivalents = intercepts.map((row) => node("p", t("eloka_equivalent", {ref: row.label, bearing: number(row.bearing, 0), frequency: number(row.frequency_hz, 0), prf: number(row.prf_hz, 0), modulation: row.modulation, candidates: row.candidates.map((item) => item.name).join(", ") || t("station_none"), correlations: row.correlations.map((item) => item.ref).join(", ") || t("station_none")})));
    if (focused) equivalents.push(node("p", t("eloka_signal_equivalent", {ref: focused.label, modulation: focused.modulation, frequency: number(focused.frequency_hz / 1e9, 3), prf: number(focused.prf_hz, 0)})));
    $("eloka-scope-text").replaceChildren(...equivalents);
    if (!intercepts.length) $("eloka-scope-text").textContent = t("visual_empty");
  }

  function drawWeaponsVisual() {
    const plot = visualContext("weapons-system"), payload = v2State.weapons;
    if (!plot) return;
    const stages = [payload.readiness.station_down ? t("station_down_state") : t("station_live_state"), payload.readiness.roe, payload.readiness.interlock];
    stages.forEach((text, index) => { const x = 10 + index * plot.width / 3; plot.context.fillStyle = index === 2 && payload.readiness.interlock ? "#53421f" : "#24493f"; plot.context.fillRect(x, 20, plot.width / 3 - 20, 45); plot.context.fillStyle = palette().text; plot.context.textAlign = "center"; plot.context.fillText(text, x + plot.width / 6 - 10, 48, plot.width / 3 - 28); });
    payload.tubes.forEach((tube, index) => { const x = 10 + index * Math.max(36, (plot.width - 20) / Math.max(1, payload.tubes.length)); plot.context.strokeStyle = tube.state === "ready" ? palette().accent : palette().amber; plot.context.strokeRect(x, 90, 28, 55); plot.context.fillStyle = palette().text; plot.context.fillText(String(tube.tube), x + 14, 122); });
    $("weapons-system-text").textContent = t("weapons_equivalent", {state: payload.readiness.state, interlock: payload.readiness.interlock, tubes: payload.tubes.map((tube) => `${tube.tube}:${tube.state}/${number(tube.reload_s, 0)}s`).join(", ") || t("station_none"), nixies: number(payload.inventory.nixies, 0), active: payload.active_assets.length});
  }

  function visualStationDown(role) {
    const payload = v2State?.[role];
    return role === "sonar" ? payload.settings.station_down : role === "weapons" ? payload.readiness.station_down :
      role === "opz" ? !payload.radar.live : role === "radio" ? payload.station_down :
      role === "engine" ? payload.machinery.station_state === "ZERSTOERT" : role === "eloka" ? payload.station_down : false;
  }

  function drawHelicopterAcoustic() {
    const acoustic = v2State?.helicopter?.acoustic;
    if (!acoustic || $("helicopter-buoy-console").hidden) return;
    const aged = (rows) => rows.map((bins, index) => ({bins, age_s: (rows.length - 1 - index) * .25}));
    // The buoy relay keeps a fixed number of 0.25 s rows; that span is its time axis.
    const span = (rows) => Math.max(20, rows.length * .25);
    heatmap("helicopter-broadband-canvas", aged(acoustic.broadband_history), null, null, (broadband) => {
      if (!finite(acoustic.listen_bearing)) return;
      broadband.context.strokeStyle = palette().amber;
      const x = acoustic.listen_bearing / 360 * broadband.width;
      broadband.context.beginPath(); broadband.context.moveTo(x, 0);
      broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
    }, span(acoustic.broadband_history));
    spectrum("helicopter-spectrum-canvas", acoustic.spectrum,
      [], acoustic.bin_frequencies_hz, 300);
    heatmap("helicopter-lofar-canvas", aged(acoustic.history), acoustic.bin_frequencies_hz, null, null, span(acoustic.history));
    spectrum("helicopter-demon-canvas", acoustic.demon,
      [], acoustic.demon.map((_, index) => index + 1), 80);
  }

  function drawRoleVisuals() {
    const role = v2State?.role;
    if (!role || $("role-visuals").hidden) return;
    if (mapRoles.has(role) && $("map-visual").hidden === false) drawRoleMap(role);
    if (role === "helicopter") drawHelicopterAcoustic();
    if (role === "sonar") drawSonarVisuals();
    if (role === "damage") drawDamageVisual();
    if (role === "engine") drawEngineVisual();
    if (role === "eloka") drawElokaVisual();
    if (role === "weapons") drawWeaponsVisual();
  }

  function queueVisualDraw() {
    if (visualDrawQueued) return;
    visualDrawQueued = true;
    requestAnimationFrame(() => { visualDrawQueued = false; drawRoleVisuals(); syncPlotAnimation(); });
  }

  function renderRoleVisuals(role) {
    $("role-visuals").hidden = !role;
    $("helicopter-visual-tabs").hidden = role !== "helicopter";
    $("helicopter-buoy-console").hidden = role !== "helicopter" || helicopterVisualPage !== "acoustic";
    $("helicopter-dip-display").hidden = role !== "helicopter" || helicopterVisualPage !== "map";
    for (const mode of ["acoustic", "map"])
      $(`helicopter-visual-${mode}`).setAttribute("aria-selected", String(helicopterVisualPage === mode));
    for (const plot of ["broadband", "lofar", "demon"]) {
      $(`helicopter-plot-${plot}`).hidden = helicopterPlot !== plot;
      $(`helicopter-acoustic-plot-tabs`).querySelector(`[data-helicopter-plot-tab="${plot}"]`)
        .setAttribute("aria-selected", String(helicopterPlot === plot));
    }
    for (const [id, active] of [["map-visual", mapRoles.has(role) && (role !== "helicopter" || helicopterVisualPage === "map")], ["sonar-visual", role === "sonar"],
      ["damage-visual", role === "damage"], ["engine-visual", role === "engine"],
      ["eloka-visual", role === "eloka"], ["weapons-visual", role === "weapons"]]) $(id).hidden = !active;
    if (!role) { clearVisuals(); return; }
    const stateKey = !connected ? "visual_stale" : v2State.phase !== "live" ? "visual_inactive" : visualStationDown(role) ? "visual_station_down" : "visual_live";
    $("role-visual-state").textContent = t(stateKey);
    for (const button of $("sonar-page-tabs").querySelectorAll("button")) {
      const selectedPage = button.dataset.sonarVisual === sonarVisualPage;
      button.setAttribute("aria-selected", String(selectedPage)); button.tabIndex = selectedPage ? 0 : -1;
    }
    const shownPlots = sonarVisualPage === "overview" ? overviewPlotList() : [sonarVisualPage];
    $("sonar-plots").dataset.layout = sonarVisualPage !== "overview" ? "single" :
      wideScreen.matches ? "overview-wide" : "overview";
    for (const panel of document.querySelectorAll("[data-sonar-plot]")) panel.hidden = !shownPlots.includes(panel.dataset.sonarPlot);
    queueVisualDraw();
    syncOpzSweepAnimation();
  }

  function renderStationView() {
    const active = v2State?.role;
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
      $("workstation-manual-link").href = `/manual-${language}#station-${active}`;
    }
    if (active) {
      const section = $(`station-${active}`), grid = section.querySelector(".station-grid");
      section.classList.toggle("track-workstation", trackRoles.has(active));
      if ($("role-visuals").parentElement !== section) section.insertBefore($("role-visuals"), grid);
      if (active === "bridge" && $("bridge-orders").parentElement !== grid) grid.prepend($("bridge-orders"));
      if (active === "opz" && $("opz-controls").parentElement !== grid) grid.prepend($("opz-controls"));
      if (active === "helicopter" && $("helicopter-dipping-controls").parentElement !== grid) {
        grid.prepend($("helicopter-dipping-controls"));
        $("helicopter-dipping-controls").hidden = false;
      }
      if (active === "helicopter" && $("helicopter-dip-display").parentElement !== $("role-visuals"))
        $("role-visuals").insertBefore($("helicopter-dip-display"), $("map-visual"));
      if (active === "helicopter" && $("helicopter-buoy-console").parentElement !== $("role-visuals"))
        $("role-visuals").insertBefore($("helicopter-buoy-console"), $("map-visual"));
      if (active === "helicopter" && $("sonar-live-toggle").parentElement?.parentElement !== $("helicopter-buoy-console"))
        $("helicopter-buoy-console").prepend($("sonar-live-toggle").parentElement);
      if (active === "sonar" && $("sonar-live-toggle").parentElement?.parentElement !== $("sonar-visual"))
        $("sonar-visual").prepend($("sonar-live-toggle").parentElement);
      if (trackRoles.has(active) && $("operations-workspace").parentElement !== section)
        section.insertBefore($("operations-workspace"), grid);
      const controls = grid.querySelector(":scope > .station-controls");
      if (controls && grid.firstElementChild !== controls) grid.prepend(controls);
      const fire = grid.querySelector(":scope > .direct-fire-controls");
      if (active === "weapons" && fire && grid.firstElementChild !== fire) grid.prepend(fire);
    } else {
      // Return shared nodes to their neutral homes before hiding role panels.
      if ($("role-visuals").parentElement !== $("station-view")) $("station-view").append($("role-visuals"));
      if ($("operations-workspace").parentElement !== $("panel-operations"))
        $("station-view").after($("bridge-orders"), $("opz-controls"), $("operations-workspace"));
      $("helicopter-dipping-controls").hidden = true;
    }
    $("station-view").hidden = !active;
    for (const section of document.querySelectorAll("[data-station-role]")) {
      section.hidden = section.dataset.stationRole !== active;
      if (section.hidden) for (const container of section.querySelectorAll("dl, .station-list")) container.replaceChildren();
    }
    $("operations-workspace").hidden = Boolean(active) && !trackRoles.has(active);
    renderRoleVisuals(active);
    if (!active) return;
    const signature = `${language}:${active}:${JSON.stringify(v2State[active])}:${JSON.stringify(v2State.environment)}`;
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
    stopSonarStream();
    roleCache.clear();
    roleStale = false;
    document.body.removeAttribute("data-role-stale");
    document.body.classList.remove("workstation-mode");
    $("station-view").append($("role-visuals"));
    $("station-view").after($("bridge-orders"), $("opz-controls"), $("operations-workspace"));
    $("workstation-tools").hidden = true;
    $("workstation-station-label").hidden = true;
    for (const name of tabNames) $(`tab-${name}`).hidden = false;
    snapshot = null;
    chart = null;
    chartSession = null;
    chartEpoch = null;
    chartRole = null;
    selected = null;
    queuedSonarFocus = null;
    pending = null;
    v2State = null;
    sonarHistory.context = null;
    for (const name of ["broadband", "lofar", "demon"]) sonarHistory[name].clear();
    stationDrafts.clear();
    clearFireDrafts();
    stationRenderSignature = null;
    sonarVisualPage = defaultSonarPage();
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
    proposals = null;
    eventContext = null;
    eventHighWater = 0;
    eventHistory = [];
    view.initialized = false;
    view.follow = false;
    lookoutView.rangeNm = 100;
    activeTab = "operations";
    $("navigation-form").reset();
    $("bridge-course-form").reset();
    $("bridge-speed-form").reset();
    for (const id of ["sonar-bearing-form", "sonar-depth-form", "sonar-gain-form", "sonar-harmonic-form",
      "engine-course-form", "engine-speed-form", "helicopter-waypoint-form", "helicopter-dip-depth-form"]) $(id).reset();
    $("sonar-control-page").value = "listen";
    renderSonarControlPage();
    $("navigation-status").textContent = "";
    $("track-list").replaceChildren();
    $("station-view").hidden = true;
    $("operations-workspace").hidden = false;
    for (const section of document.querySelectorAll("[data-station-role]")) {
      section.hidden = true;
      for (const container of section.querySelectorAll("dl, .station-list")) container.replaceChildren();
    }
    $("track-detail").hidden = true;
    for (const id of ["detail-label", "detail-badges", "detail-metrics", "mission-name", "objective",
      "mission-metrics", "chart-disclaimer", "proposal-status", "command-status", "snapshot-meta", "lookout-sea",
      "lookout-light", "lookout-own", "lookout-observations", "bridge-order-values",
      "bridge-order-status", "opz-mark-status", "opz-release-status", "station-command-status",
      "autocrew-status", "bridge-weather-text"]) $(id).replaceChildren();
    $("simlog-list").replaceChildren();
    $("simlog-current").replaceChildren();
    releaseCanvas(canvas);
    releaseCanvas(lookoutCanvas);
    activateTab("operations", false);
  }

  function renderLobby() {
    if (!session) return;
    const assigned = session.station !== null;
    const simlog = simlogActive();
    $("pairing").hidden = true;
    $("lobby").hidden = simlog || assigned && !stationPickerOpen || session.host !== null && hostView?.phase === "menu";
    $("lobby-back").hidden = !assigned;
    // A solo session holds every station, so there is nothing to add or release.
    const solo = session.host !== null;
    $("role-rail").hidden = !assigned || stationPickerOpen || solo;
    $("mobile-role").hidden = !assigned || stationPickerOpen;
    for (const id of ["mobile-add-station", "mobile-release-station"]) $(id).hidden = solo;
    const rolePublished = v2State?.role === session.station;
    const hostMenu = session.host !== null && hostView?.phase === "menu";
    $("operations").hidden = simlog || !assigned || stationPickerOpen || !rolePublished || hostMenu;
    $("simlog-view").hidden = !simlog;
    if (simlog) loadSimlog();
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
      // The web host initially holds every station and may transfer any of them.
      button.disabled = stationMutation || requested !== null ||
        (state !== "available" && !webHostAvailable);
    });
    if (!assigned) { renderDisabledReasons(); return; }
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
    const displayedStation = activatingStation && session.stations[activatingStation]?.status === "mine" ?
      activatingStation : session.station;
    const leasedStations = stationNames.filter((station) => session.stations[station].status === "mine");
    for (const id of ["mobile-station"]) {
      const select = $(id);
      const signature = leasedStations.map((station) => `${station}:${t(`station_${station}`)}`).join("|");
      if (select.dataset.options !== signature) {
        select.replaceChildren(...leasedStations.map((station) => {
        const option = node("option", t(`station_${station}`));
        option.value = station;
        return option;
        }));
        select.dataset.options = signature;
      }
      if (document.activeElement !== select || stationMutation) select.value = displayedStation;
      select.disabled = stationMutation;
    }
    renderStationTabs(leasedStations, displayedStation);
    $("workstation-add-station").hidden = leasedStations.length === stationNames.length;
    $("workstation-release").hidden = solo;
    renderHost();
    renderDisabledReasons();
  }

  function switchRole(from, to) {
    if (v2State?.role === from) roleCache.set(from, v2State);
    stopSonarAudio();
    stopSonarStream();
    // Everything bound to the old station's authority is dropped: the pending
    // command, armed fire, queued focus and the per-station feeds. Map views,
    // selection, form contents and the sonar page belong to the operator and stay.
    pending = null;
    commandMessage = null;
    queuedSonarFocus = null;
    clearFireDrafts();
    stationRenderSignature = null;
    proposals = null;
    eventContext = null;
    eventHighWater = 0;
    eventHistory = [];
    renderEvents();
    clearVisuals();
    const cached = roleCache.get(to) ?? null;
    v2State = cached;
    snapshot = cached ? buildDisplayModel(cached) : null;
    roleStale = true;
    document.body.dataset.roleStale = "true";
    if (snapshot && chart) {
      // Paint immediately from the cache; the fresh state replaces it next poll.
      renderSnapshot();
    }
  }

  function acceptSession(next) {
    validateSession(next);
    const previous = session;
    const changed = previous && (previous.station !== next.station ||
      previous.station_generation !== next.station_generation ||
      previous.active_generation !== next.active_generation);
    const lostRole = previous?.station !== null && next.station === null;
    // A plain activation moves between leases this client already held under the
    // same generations; any lease, grant or world change is a full reset.
    const activation = changed && previous.station !== null && next.station !== null &&
      previous.station !== next.station &&
      stationNames.every((name) => previous.stations[name].status === next.stations[name].status &&
        previous.stations[name].station_generation === next.stations[name].station_generation);
    if (!activation && changed) clearRoleState();
    if (previous?.requested_station &&
        next.stations[previous.requested_station]?.status === "mine") stationPickerOpen = false;
    session = next;
    if (activation) switchRole(previous.station, next.station);
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
    if (!session || stationMutation) return;
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
        if (path === "/stations/activate") {
          activatingStation = null;
          // Do not wait for the next 500 ms tick: fetch the new station now.
          if (authenticated() && !polling) { clearTimeout(pollTimer); poll(); }
        }
        renderLobby();
      }
    }
  }

  function requestStation(station) {
    if (!stationNames.includes(station) ||
        (session?.stations[station]?.status !== "available" && !webHostAvailable) ||
        session.requested_station !== null) return;
    mutateStation("/stations/request", { station });
  }

  function chooseStation(station) {
    const record = session?.stations?.[station];
    if (!record || stationMutation || station === session.station) return;
    if (record.status === "mine") {
      if (activeTab !== "operations") activateTab("operations", false);
      activatingStation = station;
      mutateStation("/stations/activate", {
        station, station_generation: record.station_generation,
        active_generation: session.active_generation,
      });
    }
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
    if (focus) (name !== "operations" ? $(`panel-${name}`) : $(`tab-${name}`)).focus();
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
      const referenceFields = ["hull_type", "length_m"];
      const machineFields = ["cruise_speed_kn", "maximum_speed_kn", "quiet_speed_kn", "propulsion_codes", "motor_rpm", "shaft_rpm", "propulsor_type", "blade_count", "cruise_lines", "high_speed_lines", "cruise_broadband", "high_speed_broadband"];
      if (!profile || typeof profile !== "object" || Array.isArray(profile) ||
          Object.keys(profile).sort().join(",") !== "assets,components,key,machine,name,reference,resource" ||
          typeof profile.key !== "string" || !/^[a-z0-9][a-z0-9_.-]{0,95}$/.test(profile.key) || keys.has(profile.key) ||
          typeof profile.name !== "string" || !profile.name || profile.name.length > 256 ||
          typeof profile.resource !== "string" || !["subs.json", "warships.json", "civilians.json", "aircraft.json", "animals.json", "torpedoes.json", "decoys.json"].includes(profile.resource) ||
          !profile.assets || typeof profile.assets !== "object" || Array.isArray(profile.assets) ||
          Object.keys(profile.assets).some((kind) => !["acoustic_cruise", "acoustic_high", "radar"].includes(kind)) ||
          Object.entries(profile.assets).some(([kind, route]) => {
            const suffix = { acoustic_cruise: "cruise", acoustic_high: "high", radar: "radar" }[kind];
            return typeof route !== "string" || route !== `/contact-analysis/${profile.key}-${suffix}.png`;
          }) ||
          !profile.components || typeof profile.components !== "object" || Array.isArray(profile.components) ||
          Object.keys(profile.components).sort().join(",") !== "countermeasures,emitters,launchers,magazines,sensors,weapons" ||
          Object.values(profile.components).some((items) => !Array.isArray(items) || items.length > 128 || items.some((item) => !boundedObject(item))) ||
          !record(profile.reference, referenceFields) || !record(profile.machine, machineFields) ||
          !referenceFields.every((field) => scalar(profile.reference[field])) ||
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
      (!term || `${profile.name} ${profile.key}`.toLocaleLowerCase(language).includes(term)));
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
    // Sonar operators assign the compared profile to their selected contact.
    const canAssign = session?.station === "sonar" && Boolean(selected) && stationActionAvailable();
    $("analysis-assign").hidden = $("analysis-assign-clear").hidden = !canAssign;
    $("analysis-assign-status").value = canAssign ? t("analyzer_assign_target", {contact: selectedTrack()?.label || selected}) : "";
    const reference = profile.reference;
    const machine = profile.machine;
    const joined = (items) => Array.isArray(items) && items.length ? items.join(", ") : t("unavailable");
    metrics($("analysis-metrics"), [
      ["analyzer_hull", reference.hull_type || t("unavailable")],
      ["analyzer_length", unit(reference.length_m, "m")],
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
    const imageLabels = { acoustic_cruise: "analyzer_acoustic_cruise", acoustic_high: "analyzer_acoustic_high",
      radar: "analyzer_radar" };
    const imageKey = `${language}:${profile.key}`;
    if (analysisImageKey !== imageKey) {
      $("analysis-images").replaceChildren(...Object.entries(profile.assets).map(([kind, route]) => {
        const figure = node("figure", undefined, "analysis-image");
        const image = node("img");
        const descriptions = [];
        if (kind === "radar") {
          descriptions.push(t("analyzer_image_alt_radar_base", { speed: t(imageLabels[kind]) }));
          descriptions.push(t(profile.components.emitters.some((emitter) => Array.isArray(emitter.prf_band_hz))
            ? "analyzer_image_alt_radar_prf" : "analyzer_image_alt_radar_no_prf"));
        } else {
          const cruise = kind === "acoustic_cruise";
          const lines = cruise ? machine.cruise_lines : machine.high_speed_lines;
          const broadband = cruise ? machine.cruise_broadband : machine.high_speed_broadband;
          descriptions.push(t("analyzer_image_alt_base", { speed: t(imageLabels[kind]) }));
          if (Array.isArray(lines) && lines.length) descriptions.push(t("analyzer_image_alt_tonals"));
          if (Array.isArray(broadband)) descriptions.push(t("analyzer_image_alt_broadband"));
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
  function request(path, { method = "GET", body, auth = true, expected = 200, guard, csrf } = {}) {
    const cookieSession = auth ? session : null;
    const requestGeneration = generation;
    const run = async () => {
      if (auth && (!cookieSession || requestGeneration !== generation)) throw new Error("cancelled");
      if (guard && !guard()) throw new Error("cancelled");
      const controller = new AbortController();
      activeRequest = controller;
      const timeout = setTimeout(() => controller.abort(), 4000);
      let response;
      try {
        const headers = { Accept: "application/json" };
        if (csrf) headers["X-U-Jagd-CSRF"] = csrf;
        if (body !== undefined) headers["Content-Type"] = "application/json";
        response = await fetch(`/api/v2${path}`, {
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
      $("guide-manual-link").href = `/manual-${language}`;
      window.dispatchEvent(new CustomEvent("u-jagd-language", {
        detail: {language, translations}
      }));
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
    const displayState = linkState === "stale" && failures < NOTICE_AFTER_FAILURES
      ? "reconnecting" : linkState;
    $("connection").dataset.state = displayState;
    const age = lastSuccess ? Math.max(0, Math.floor((performance.now() - lastSuccess) / 1000)) : 0;
    const key = displayState === "stale" ? "connection_stale"
      : displayState === "protocol_error" ? "connection_protocol_error"
      : `connection_${displayState}`;
    let text = t(key, { age });
    if ((linkState === "stale" || linkState === "protocol_error") && failures >= ESCALATE_AFTER_FAILURES) {
      text += " " + t("connection_escalated_hint", { minutes: Math.max(1, Math.floor(age / 60)) });
    }
    $("connection").textContent = text;
  }

  function setConnection(state) {
    linkState = state;
    connected = state === "connected";
    renderConnection();
    renderActionState();
    renderHost();
    if (v2State?.role) renderRoleVisuals(v2State.role);
    if (sonarAudioEnabled && !sonarAudioAuthorized()) stopSonarAudio("sonar_live_unavailable");
    syncGameAudio();
    syncPlotAnimation();
  }

  function forgetSession(message = "connection_unpaired") {
    stopSonarAudio();
    generation += 1;
    session = null;
    activatingStation = null;
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
    proposals = null;
    eventContext = null;
    eventHighWater = 0;
    eventHistory = [];
    renderEvents();
    $("pairing").hidden = false;
    $("disconnect").hidden = true;
    $("pair-error").textContent = "";
    $("code").value = "";
    $("navigation-form").reset();
    $("navigation-status").textContent = "";
    document.body.dataset.remoteRole = "";
    lobbyMessage = null;
    stationMutation = false;
    hostView = null;
    hostPending = null;
    hostMessage = null;
    $("host-screen").hidden = true;
    $("host-bar").hidden = true;
    activateTab("operations", false);
    for (const id of ["track-list", "detail-label", "detail-badges", "detail-metrics", "mission-name", "objective", "mission-metrics", "proposal-status", "command-status", "snapshot-meta", "lookout-sea", "lookout-light", "lookout-own", "lookout-observations"]) $(id).replaceChildren();
    $("lookout-scope").dataset.light = "unknown";
    releaseCanvas(canvas);
    releaseCanvas(lookoutCanvas);
    setConnection("unpaired");
    $("connection").textContent = t(message);
  }

  function validateSession(value) {
    const fields = ["active_generation", "active_station", "client_id", "csrf", "grants", "name", "host", "next_command_seq", "ordinal", "presence", "protocol", "requested_station", "simlog", "station", "station_generation", "stations"];
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
        (value.grants.sonar_audio && !["sonar", "helicopter"].includes(value.station)) ||
        typeof value.simlog !== "boolean" || value.grants.simlog !== value.simlog ||
        (value.host !== null && (!exactKeys(value.host, ["generation"]) ||
          !Number.isSafeInteger(value.host.generation) || value.host.generation < 0)) ||
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
          record.grants.sonar_audio && !["sonar", "helicopter"].includes(station)) throw new Error("session");
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

  async function resumeSession() {
    try {
      const resumed = await request("/session", { auth: false });
      validateSession(resumed);
      pairingAvailable = true;
      acceptSession(resumed);
      return true;
    } catch (error) {
      pairingAvailable = error.status === 401;
      if (!pairingAvailable) setConnection("stale");
      return false;
    }
  }

  const exactKeys = (value, keys) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).sort().join(",") === [...keys].sort().join(",");
  const boundedArray = (value, maximum) => Array.isArray(value) && value.length <= maximum;
  // Bridge-lookout classes (src/sensors/lookout_id.py): an observation, not
  // an operator classification.
  const sightingClasses = ["MERCHANT", "TANKER", "CARGO", "PASSENGER", "WARSHIP", "CARRIER", "CRUISER", "DESTROYER",
    "FRIGATE", "CORVETTE", "MINE_WARFARE", "NAVAL_AUXILIARY", "SERVICE", "TUG", "RESEARCH", "OFFSHORE", "FISHING",
    "SMALL_CRAFT", "RESCUE", "SUBMARINE", "AIRLINER", "MILITARY_AIRCRAFT", "COMBAT_AIRCRAFT", "TORPEDO_WAKE", "SHIP", "LAND"];
  const sightingKinds = ["SURFACE", "SUB", "FLG", "TORP"];
  function validSightingClass(code, type) {
    if (code === null) return type === null;
    return sightingClasses.includes(code) && (type === null || (typeof type === "string" && type.length > 0 && type.length <= 80));
  }
  function sightingText(code, type) {
    const what = t(`sighting_class_${code.toLowerCase()}`);
    return type === null ? what : t("sighting_with_type", { what, type });
  }
  function v2Observation(row, fields) {
    if (!exactKeys(row, fields) || typeof row.ref !== "string" || !row.ref || row.ref.length > 64) throw new Error("protocol");
  }
  // Weather & sonar analysis block, common to every role.  The ocean profile
  // is null until the sonar has taken a bathythermograph measurement.
  const PLOT_FIELDS = {
    mark: ["id", "shape", "label", "t", "x", "y"],
    ruler: ["id", "shape", "label", "t", "x", "y", "x2", "y2"],
    bearing: ["id", "shape", "label", "t", "x", "y", "bearing"],
    circle: ["id", "shape", "label", "t", "x", "y", "radius_nm"],
    dr: ["id", "shape", "label", "t", "x", "y", "course", "speed_kn", "now_x", "now_y", "cpa_nm", "cpa_s"],
  };

  function validPlot(plot) {
    if (!exactKeys(plot, ["objects", "max_objects", "max_label"]) || !Number.isInteger(plot.max_objects) ||
        !Number.isInteger(plot.max_label) || !boundedArray(plot.objects, plot.max_objects)) return false;
    const ids = new Set();
    return plot.objects.every((item) => {
      const fields = item && PLOT_FIELDS[item.shape];
      if (!fields || !exactKeys(item, fields) || !Number.isSafeInteger(item.id) || item.id < 1 || ids.has(item.id) ||
          typeof item.label !== "string" || item.label.length > plot.max_label) return false;
      ids.add(item.id);
      return fields.filter((key) => !["id", "shape", "label"].includes(key)).every((key) => finite(item[key]));
    });
  }

  function validWeatherStation(ws) {
    const nullableFinite = (value) => value === null || finite(value);
    const atmosphereKeys = ["weather", "precipitation", "rain_intensity", "visibility_nm", "sea_state", "wind_from_deg", "wind_kn", "gust_kn", "beaufort", "pressure_hpa", "pressure_tendency_hpa_3h", "pressure_trend", "storm_warning", "air_temp_c", "sea_temp_c", "cloud_cover", "ceiling_ft", "icing", "sun_elevation_deg", "daylight", "moon_phase", "moon_illumination", "time"];
    const flightKeys = ["status", "launch_safe", "dipping_safe", "deck_safe", "wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "ceiling_ft", "icing", "sea_state", "roll_deg", "pitch_deg", "limits"];
    const limitKeys = ["wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "ceiling_ft", "sea_state", "roll_deg", "pitch_deg"];
    const profileKeys = ["age_s", "offset_nm", "stale", "thermocline_m", "water_depth_m", "depths_m", "speeds_m_s", "sofar_axis_m", "cz_bands_nm", "range_nm", "rays", "depth_edges_m", "shadow", "dip_relative_to_layer"];
    if (!exactKeys(ws, ["atmosphere", "effects", "flight", "profile"])) return false;
    const a = ws.atmosphere, f = ws.flight, p = ws.profile;
    if (!exactKeys(a, atmosphereKeys) || !["clear", "rain", "storm", "fog", "snow"].includes(a.weather) ||
        !["none", "rain", "snow"].includes(a.precipitation) || !["rising", "steady", "falling", "falling_rapidly"].includes(a.pressure_trend) ||
        !["none", "light", "severe"].includes(a.icing) || !["day", "civil_twilight", "nautical_twilight", "night"].includes(a.daylight) ||
        !["new", "waxing_crescent", "first_quarter", "waxing_gibbous", "full", "waning_gibbous", "last_quarter", "waning_crescent"].includes(a.moon_phase) ||
        typeof a.storm_warning !== "boolean" || typeof a.time !== "string" || !/^\d\d:\d\d$/.test(a.time) ||
        !Number.isInteger(a.beaufort) || a.beaufort < 0 || a.beaufort > 12 || !Number.isInteger(a.sea_state) || a.sea_state < 0 || a.sea_state > 6 ||
        !["rain_intensity", "visibility_nm", "wind_from_deg", "wind_kn", "gust_kn", "pressure_hpa", "pressure_tendency_hpa_3h", "air_temp_c", "sea_temp_c", "cloud_cover", "sun_elevation_deg", "moon_illumination"].every((key) => finite(a[key])) ||
        !nullableFinite(a.ceiling_ft)) return false;
    if (!exactKeys(ws.effects, ["solar_heating", "wind_mixing", "freshwater"]) || Object.values(ws.effects).some((value) => typeof value !== "boolean")) return false;
    if (!exactKeys(f, flightKeys) || !["clear", "limited", "no_go"].includes(f.status) || !["none", "light", "severe"].includes(f.icing) ||
        ["launch_safe", "dipping_safe", "deck_safe"].some((key) => typeof f[key] !== "boolean") ||
        !["wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "roll_deg", "pitch_deg"].every((key) => finite(f[key])) || !nullableFinite(f.ceiling_ft) ||
        !Number.isInteger(f.sea_state) || !exactKeys(f.limits, limitKeys) || !Object.values(f.limits).every((value) => finite(value))) return false;
    if (p === null) return true;
    const pairs = (rows, maximum) => boundedArray(rows, maximum) && rows.every((row) => Array.isArray(row) && row.length === 2 && row.every((value) => finite(value)));
    return exactKeys(p, profileKeys) && typeof p.stale === "boolean" &&
      ["age_s", "offset_nm", "thermocline_m", "water_depth_m", "range_nm"].every((key) => finite(p[key]) && p[key] >= 0) && nullableFinite(p.sofar_axis_m) &&
      boundedArray(p.depths_m, 64) && boundedArray(p.speeds_m_s, 64) && p.depths_m.length === p.speeds_m_s.length && p.depths_m.length >= 2 &&
      [...p.depths_m, ...p.speeds_m_s].every((value) => finite(value)) && pairs(p.cz_bands_nm, 8) &&
      boundedArray(p.rays, 9) && p.rays.every((ray) => pairs(ray, 64)) &&
      boundedArray(p.depth_edges_m, 32) && p.depth_edges_m.length >= 2 && p.depth_edges_m.every((value) => finite(value)) &&
      boundedArray(p.shadow, 32) && p.shadow.every((row) => boundedArray(row, 32) && row.length === p.depth_edges_m.length - 1 && row.every((cell) => typeof cell === "boolean")) &&
      (p.dip_relative_to_layer === null || ["above", "below"].includes(p.dip_relative_to_layer));
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
    const common = [...status, "clock", "environment", "mission", "autocrew", "autocrew_overview", "audio", "weather_station", "plot"];
    if (!stationNames.includes(state.role) || state.role !== session?.station ||
        !exactKeys(state, [...common, state.role]) || !exactKeys(state.clock, ["sim", "mission", "world"]) ||
        !exactKeys(state.environment, ["sea_state", "effective_sea_state", "is_night", "weather", "wind_from_deg", "wind_speed_kn", "rain_intensity", "visibility_nm"]) ||
        !Number.isInteger(state.environment.sea_state) || state.environment.sea_state < 0 || state.environment.sea_state > 6 ||
        !finite(state.environment.effective_sea_state) || state.environment.effective_sea_state < 0 || state.environment.effective_sea_state > 6 ||
        typeof state.environment.is_night !== "boolean" || !["clear", "rain", "storm", "fog"].includes(state.environment.weather) ||
        !finite(state.environment.wind_from_deg) || state.environment.wind_from_deg < 0 || state.environment.wind_from_deg >= 360 ||
        !finite(state.environment.wind_speed_kn) || state.environment.wind_speed_kn < 0 || state.environment.wind_speed_kn > 80 ||
        !finite(state.environment.rain_intensity) || state.environment.rain_intensity < 0 || state.environment.rain_intensity > 1 ||
        !finite(state.environment.visibility_nm) || state.environment.visibility_nm < .1 || state.environment.visibility_nm > 30 ||
        !exactKeys(state.autocrew, ["enabled", "status"]) || typeof state.autocrew.enabled !== "boolean" ||
        !["off", "active", "suspended_remote", "blocked_damage"].includes(state.autocrew.status) ||
        !boundedArray(state.autocrew_overview, 9) || state.autocrew_overview.some((row) => !exactKeys(row, ["station", "enabled", "status"]) ||
          !stationNames.includes(row.station) || typeof row.enabled !== "boolean" ||
          !["off", "active", "suspended_remote", "blocked_damage"].includes(row.status)) ||
        !exactKeys(state.mission, ["name", "objective", "remaining_s"]) ||
        !exactKeys(state.audio, ["events"]) ||
        !boundedArray(state.audio.events, 16) ||
        state.audio.events.some((event, index, events) => !exactKeys(event, ["seq", "cue"]) ||
          !Number.isSafeInteger(event.seq) || event.seq < 1 || !gameEffectKinds.has(event.cue) ||
          index > 0 && event.seq <= events[index - 1].seq)) throw new Error("protocol");
    if (!validWeatherStation(state.weather_station) || !validPlot(state.plot)) throw new Error("protocol");
    const payload = state[state.role];
    const shapes = {
      bridge: ["navigation", "orders", "threat", "systems", "tactical_summary", "sightings"], sonar: ["observations", "settings", "visualization"],
      weapons: ["inventory", "readiness", "designated_target", "navigation", "tactical", "target_choices", "depth_m", "tubes", "own_weapons", "active_assets"],
      damage: ["compartments", "teams", "total", "sunk"],
      opz: ["observations", "fusions", "radar", "defense", "asm_observations", "source_classifications", "designated_target_ref", "own_assets"],
      radio: ["observations", "logged_fixes", "logged_bearings", "messages", "station_down", "navigation", "tactical"],
      engine: ["propulsion", "machinery", "controls", "environment_effects"],
      helicopter: ["asset", "waypoint", "buoys", "buoy_observations", "acoustic", "navigation", "tactical", "target_choices", "readiness", "dip_observations", "dip_environment"], eloka: ["intercepts", "station_down", "status", "hardware"],
    };
    if (!exactKeys(payload, shapes[state.role])) throw new Error("protocol");
    const rowsExact = (rows, maximum, fields) => {
      if (!boundedArray(rows, maximum)) throw new Error("protocol");
      rows.forEach((row) => v2Observation(row, fields));
    };
    const tacticalFields = ["ref", "label", "domain", "source", "affiliation", "bearing", "range_nm", "x", "y", "course", "speed_kn", "altitude_m", "observer_x", "observer_y", "quality", "age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "visual_class", "visual_type"];
    const tacticalRows = (rows, maximum, extraFields = []) => {
      if (!boundedArray(rows, maximum)) throw new Error("protocol");
      rows.forEach((row) => {
        v2Observation(row, [...tacticalFields, ...extraFields]);
        if (!validSightingClass(row.visual_class, row.visual_type)) throw new Error("protocol");
        if (row.speed_kn !== null && !finite(row.speed_kn)) throw new Error("protocol");
        if (row.altitude_m !== null && (!finite(row.altitude_m) || row.altitude_m < 0 || row.altitude_m > 30000)) throw new Error("protocol");
      });
    };
    const sonarFields = ["ref", "label", "source", "classification", "profile", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "observer_x", "observer_y", "released_to_opz", "fixes"];
    if (state.role === "bridge") {
      if (!exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"])) throw new Error("protocol");
      if (!exactKeys(payload.orders, ["station_down", "speed_max_kn", "telegraph", "noise", "cavitating"]) ||
          typeof payload.orders.station_down !== "boolean" || !finite(payload.orders.speed_max_kn) ||
          typeof payload.orders.cavitating !== "boolean" || payload.orders.speed_max_kn < 0 || payload.orders.speed_max_kn > 100 ||
          !exactKeys(payload.threat, ["observations", "count", "average_flood", "torpedoes"]) ||
          !boundedArray(payload.threat.torpedoes, 8) || payload.threat.torpedoes.some((row) =>
            !exactKeys(row, ["source", "bearing", "age_s"]) || !["transient", "seeker", "classified"].includes(row.source) ||
            !finite(row.bearing) || row.bearing < 0 || row.bearing >= 360 || !finite(row.age_s) || row.age_s < 0) ||
          !boundedArray(payload.systems, 32) || payload.systems.some((row) => !exactKeys(row, ["key", "state", "down"]) || typeof row.down !== "boolean")) throw new Error("protocol");
      tacticalRows(payload.threat.observations, 128);
      tacticalRows(payload.tactical_summary, 256);
      if (!boundedArray(payload.sightings, 24) || payload.sightings.some((row) =>
          !exactKeys(row, ["time", "sighted", "code", "type", "bearing", "range_nm"]) || typeof row.time !== "string" || row.time.length > 8 ||
          (row.code === null ? !sightingKinds.includes(row.sighted) || row.type !== null : row.sighted !== null || !validSightingClass(row.code, row.type)) ||
          !finite(row.bearing) || row.bearing < 0 || row.bearing >= 360 || !finite(row.range_nm) || row.range_nm < 0 || row.range_nm > 1000)) throw new Error("protocol");
    } else if (state.role === "sonar") {
      rowsExact(payload.observations, 256, sonarFields);
      const settings = payload.settings;
      if (!exactKeys(settings, ["mode", "page", "listen_bearing", "focus_ref", "target_ref", "station_down", "tow", "bt", "ping", "tma_enabled", "gain_db", "band_preset", "band_hz", "notch", "peak_hold", "harmonic_hz", "harmonic_candidates_hz", "audio_enabled", "volume", "quiet_mode", "tools"]) ||
          !["BOW", "TOWED"].includes(settings.mode) || typeof settings.station_down !== "boolean" ||
          !exactKeys(settings.tools, ["assist", "lofar_cursor_hz", "demon_cursor_hz", "integration_s", "vernier", "shaft_hz", "blade_hz", "operator_notch_hz", "demon_band_hz", "heterodyne_hz"]) ||
          !boundedArray(settings.tools.demon_band_hz, 2) || settings.tools.demon_band_hz.some((value) => !finite(value)) || !finite(settings.tools.heterodyne_hz) ||
          typeof settings.tools.assist !== "boolean" || typeof settings.tools.vernier !== "boolean" ||
          ![2, 8, 16, 64].includes(settings.tools.integration_s) ||
          [settings.tools.lofar_cursor_hz, settings.tools.demon_cursor_hz].some((value) => !finite(value) || value < 0 || value > 300) ||
          [settings.tools.shaft_hz, settings.tools.blade_hz, settings.tools.operator_notch_hz].some((value) => value !== null && (!finite(value) || value < 0 || value > 300)) ||
          !exactKeys(settings.tow, ["state", "payout", "available", "handling_ok", "speed_kn", "speed_min_kn", "speed_max_kn", "depth_m", "depth_target_m"]) ||
          !finite(settings.tow.speed_kn) || !finite(settings.tow.speed_min_kn) || !finite(settings.tow.speed_max_kn) ||
          !exactKeys(settings.bt, ["ready", "cooldown_s", "thermocline_m"]) ||
          !exactKeys(settings.ping, ["ready", "cooldown_s"]) ||
          settings.tow.speed_kn < 0 || settings.tow.speed_kn > 100 || settings.tow.speed_min_kn < 0 ||
          settings.tow.speed_max_kn > 100 || settings.tow.speed_min_kn > settings.tow.speed_max_kn ||
          !boundedArray(settings.band_hz, 2) || settings.band_hz.length !== 2 ||
          !boundedArray(settings.harmonic_candidates_hz, 64) ||
          [settings.tow.available, settings.tow.handling_ok, settings.bt.ready, settings.ping.ready,
            settings.tma_enabled, settings.notch, settings.peak_hold, settings.audio_enabled,
            settings.quiet_mode].some((value) => typeof value !== "boolean")) throw new Error("protocol");
      const visual = payload.visualization;
      if (!exactKeys(visual, ["broadband", "lofar", "demon", "tma", "bt", "active_echoes", "receiver"]) ||
          !exactKeys(visual.broadband, ["bearing_start_deg", "bearing_step_deg", "history"]) ||
          !boundedArray(visual.broadband.history, 120) || visual.broadband.history.some((row) => !exactKeys(row, ["age_s", "bins"]) || !boundedArray(row.bins, 180)) ||
          !exactKeys(visual.lofar, ["frequency_min_hz", "frequency_max_hz", "bin_frequencies_hz", "history", "spectrum", "held", "vernier"]) ||
          (visual.lofar.vernier !== null && (!exactKeys(visual.lofar.vernier, ["low_hz", "high_hz", "step_hz", "bins"]) || !boundedArray(visual.lofar.vernier.bins, 64) || !finite(visual.lofar.vernier.low_hz) || !finite(visual.lofar.vernier.high_hz))) ||
          !boundedArray(visual.lofar.bin_frequencies_hz, 256) || !boundedArray(visual.lofar.spectrum, 256) ||
          !boundedArray(visual.lofar.history, 80) || visual.lofar.history.some((row) => !exactKeys(row, ["age_s", "bearing", "bins"]) || !boundedArray(row.bins, 110)) || typeof visual.lofar.held !== "boolean" ||
          !exactKeys(visual.demon, ["frequency_min_hz", "frequency_max_hz", "bin_step_hz", "spectrum", "history", "analysis"]) || !boundedArray(visual.demon.spectrum, 80) ||
          !boundedArray(visual.demon.history, 120) || visual.demon.history.some((row) => !exactKeys(row, ["age_s", "bins"]) || !boundedArray(row.bins, 80)) ||
          (visual.demon.analysis !== null && (!exactKeys(visual.demon.analysis, ["modulation_peak_hz", "detection_confidence", "cavitation", "tonal_hz", "hypotheses"]) || !boundedArray(visual.demon.analysis.hypotheses, 20) || visual.demon.analysis.hypotheses.some((row) => !exactKeys(row, ["blades", "order", "rpm"])))) ||
          !boundedArray(visual.tma, 32) || visual.tma.some((row) => !exactKeys(row, ["ref", "bearings", "solution", "summary", "hypothesis", "evaluation", "residuals_deg", "proposal"]) ||
            !exactKeys(row.summary, ["rate_deg_min", "legs"]) || !Number.isInteger(row.summary.legs) ||
            !exactKeys(row.hypothesis, ["course", "speed_kn", "range_nm"]) || !finite(row.hypothesis.course) || !finite(row.hypothesis.speed_kn) || !finite(row.hypothesis.range_nm) ||
            (row.evaluation !== null && !exactKeys(row.evaluation, ["rms_deg", "systematic_deg", "fit", "observability"])) ||
            !boundedArray(row.residuals_deg, 24) || row.residuals_deg.some((value) => !finite(value)) ||
            (row.proposal !== null && !exactKeys(row.proposal, ["course", "speed_kn", "range_nm"])) || !boundedArray(row.bearings, 24) || row.bearings.some((point) => !exactKeys(point, ["age_s", "bearing", "uncertainty_deg", "own_x", "own_y", "own_course"])) || row.solution !== null && !exactKeys(row.solution, ["x", "y", "course", "speed_kn", "quality", "age_s", "uncertainty_nm"])) ||
          (visual.bt !== null && (!exactKeys(visual.bt, ["age_s", "thermocline_m", "water_depth_m", "sea_state", "depths_m", "speeds_m_s", "cz_bands_nm"]) || !boundedArray(visual.bt.depths_m, 64) || !boundedArray(visual.bt.speeds_m_s, 64) || visual.bt.depths_m.length !== visual.bt.speeds_m_s.length || !boundedArray(visual.bt.cz_bands_nm, 8) || visual.bt.cz_bands_nm.some((band) => !boundedArray(band, 2) || band.length !== 2))) ||
          !boundedArray(visual.active_echoes, 40) || visual.active_echoes.some((row) => !exactKeys(row, ["age_s", "bearing", "range_nm", "depth_m", "range_uncertainty_nm", "depth_uncertainty_m", "snr_db", "array"])) ||
          !exactKeys(visual.receiver, ["array", "listen_bearing", "beam_width_deg", "listen_mode", "focus_locked", "audio_enabled"]) || !["BROADBAND", "FILTERED", "HETERODYNE"].includes(visual.receiver.listen_mode) || typeof visual.receiver.focus_locked !== "boolean" || typeof visual.receiver.audio_enabled !== "boolean") throw new Error("protocol");
    } else if (state.role === "weapons") {
      if (!exactKeys(payload.inventory, ["torpedoes", "vls", "ciws", "aa", "chaff_ready", "nixies"]) ||
          !exactKeys(payload.readiness, ["station_down", "roe", "ciws_ready", "aa_ready", "state", "interlock", "reload_s"]) ||
          (payload.designated_target !== null && !exactKeys(payload.designated_target, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"])) ||
          !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
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
           !exactKeys(payload.defense, ["vls", "ciws", "aa", "chaff_ready", "ciws_ready", "aa_ready", "ciws_released"]) || typeof payload.defense.ciws_released !== "boolean") throw new Error("protocol");
      tacticalRows(payload.asm_observations, 128);
      if (payload.designated_target_ref !== null && (typeof payload.designated_target_ref !== "string" || !pictureRefs.has(payload.designated_target_ref))) throw new Error("protocol");
      if (!exactKeys(payload.own_assets, ["ship", "helicopter", "weapons"]) ||
          !boundedArray(payload.own_assets.weapons, 104) || payload.own_assets.weapons.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"])) ||
          !exactKeys(payload.own_assets.ship, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
          !exactKeys(payload.own_assets.helicopter, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s"])) throw new Error("protocol");
    } else if (state.role === "radio") {
      rowsExact(payload.observations, 256, ["ref", "label", "bearing", "quality", "age_s", "bearing_uncertainty_deg", "can_capture"]);
      if (!boundedArray(payload.logged_fixes, 256) || payload.logged_fixes.some((row) => !exactKeys(row, ["ref", "x", "y", "uncertainty_nm", "age_s", "covariance_nm2"]) || row.covariance_nm2 !== null && (!boundedArray(row.covariance_nm2, 3) || row.covariance_nm2.length !== 3)) ||
          !boundedArray(payload.logged_bearings, 256) || payload.logged_bearings.some((row) => !exactKeys(row, ["ref", "bearing", "observer_x", "observer_y", "age_s"])) ||
          !boundedArray(payload.messages, 40) || payload.messages.some((row) => !exactKeys(row, ["stamp", "text"])) ||
          typeof payload.station_down !== "boolean" || payload.observations.some((row) => typeof row.can_capture !== "boolean") ||
          !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"])) throw new Error("protocol");
      tacticalRows(payload.tactical, 128);
    } else if (state.role === "engine") {
      if (!exactKeys(payload.propulsion, ["course", "target_course", "speed", "target_speed", "telegraph", "rpm", "quiet_mode", "cavitating", "fuel_kg", "fuel_capacity_kg", "fuel_burn_kg_h", "fuel_endurance_h", "fuel_range_nm"]) ||
          !exactKeys(payload.machinery, ["station_state", "speed_cap", "effective_speed_cap", "flood", "fire", "repair_teams", "repair_trend", "noise", "grounded"]) ||
          !boundedArray(payload.machinery.repair_teams, 16) || !exactKeys(payload.machinery.repair_trend, ["flood_rate", "fire_rate", "repairable"]) ||
          !exactKeys(payload.controls, ["orders", "speed_max_kn"]) || !boundedArray(payload.controls.orders, 6) ||
          payload.controls.orders.join(",") !== "ASTERN,STOP,SLOW,HALF,FULL,FLANK" ||
          !exactKeys(payload.environment_effects, ["sea_state", "roll", "pitch", "tas_available", "tas_performance"])) throw new Error("protocol");
    } else if (state.role === "helicopter") {
      if (!exactKeys(payload.asset, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s", "buoy_mode"]) ||
          (payload.waypoint !== null && !exactKeys(payload.waypoint, ["x", "y"])) ||
          !boundedArray(payload.buoys, 64) || payload.buoys.some((row) => !exactKeys(row, ["ref", "label", "x", "y", "battery_s", "active", "mode"]) || typeof row.label !== "string" || !/^SB[0-9]{2,}$/.test(row.label) || !["ACTIVE", "PASSIVE"].includes(row.mode)) ||
          !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
          !exactKeys(payload.readiness, ["flightdeck_down", "deck_state", "can_launch", "can_return", "can_set_waypoint", "can_deploy_buoy", "can_set_dipping", "can_set_dip_depth", "can_dipping_ping", "weather_launch_safe", "weather_dipping_safe", "crosswind_kn", "rtb_margin_s"]) ||
          [payload.readiness.flightdeck_down, payload.readiness.can_launch, payload.readiness.can_return, payload.readiness.can_set_waypoint, payload.readiness.can_deploy_buoy, payload.readiness.can_set_dipping, payload.readiness.can_set_dip_depth, payload.readiness.can_dipping_ping, payload.readiness.weather_launch_safe, payload.readiness.weather_dipping_safe].some((value) => typeof value !== "boolean") ||
          !finite(payload.readiness.crosswind_kn) || payload.readiness.crosswind_kn < 0 || payload.readiness.crosswind_kn > 80) throw new Error("protocol");
      tacticalRows(payload.tactical, 128, ["classification", "released_to_opz"]);
      rowsExact(payload.dip_observations, 128, ["ref", "label", "bearing", "bearing_uncertainty_deg", "age_s", "range_nm", "active_bearing", "range_uncertainty_nm", "depth_m", "depth_uncertainty_m", "fix_age_s", "classification", "qualified", "released_to_opz"]);
      rowsExact(payload.buoy_observations, 128, ["ref", "label", "buoy_label", "mode", "bearing", "bearing_uncertainty_deg", "range_nm", "x", "y", "observer_x", "observer_y", "age_s", "quality", "qualified", "released_to_opz"]);
      if (!exactKeys(payload.acoustic, ["source", "sources", "spectrum", "history", "ready",
          "bin_frequencies_hz", "broadband", "broadband_history", "demon", "demon_history",
          "listen_bearing", "audition_mode", "band_preset", "gain_db", "notch"]) ||
          typeof payload.acoustic.ready !== "boolean" ||
          !(payload.acoustic.listen_bearing === null || finite(payload.acoustic.listen_bearing) &&
            payload.acoustic.listen_bearing >= 0 && payload.acoustic.listen_bearing < 360) ||
          !["BROADBAND", "FILTERED", "HETERODYNE"].includes(payload.acoustic.audition_mode) ||
          !["FULL", "LOW", "SHAFT", "MID"].includes(payload.acoustic.band_preset) ||
          !finite(payload.acoustic.gain_db) || payload.acoustic.gain_db < -12 || payload.acoustic.gain_db > 24 ||
          typeof payload.acoustic.notch !== "boolean" ||
          !boundedArray(payload.acoustic.sources, 6) || !payload.acoustic.sources.includes(payload.acoustic.source) ||
          !boundedArray(payload.acoustic.spectrum, 256) || !boundedArray(payload.acoustic.bin_frequencies_hz, 256) ||
          payload.acoustic.spectrum.length !== payload.acoustic.bin_frequencies_hz.length ||
          !boundedArray(payload.acoustic.broadband, 180) || !boundedArray(payload.acoustic.demon, 80) ||
          !["spectrum", "bin_frequencies_hz", "broadband", "demon"].every((key) =>
            payload.acoustic[key].every((value) => finite(value))) ||
          !["history", "broadband_history", "demon_history"].every((key) =>
            boundedArray(payload.acoustic[key], 64) && payload.acoustic[key].every((row) =>
              boundedArray(row, 256) && row.every((value) => finite(value))))) throw new Error("protocol");
      if (!exactKeys(payload.dip_environment, ["water_depth_m", "thermocline_m", "depth_limit_m", "bottom_clearance_m", "winch_rate_m_s", "below_thermocline"]) ||
          Object.entries(payload.dip_environment).some(([key, value]) => value !== null &&
            (key === "below_thermocline" ? typeof value !== "boolean" : !finite(value))) ||
          payload.dip_environment.winch_rate_m_s <= 0) throw new Error("protocol");
      rowsExact(payload.target_choices, 128, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"]);
    } else if (state.role === "eloka") {
      if (!boundedArray(payload.intercepts, 64) || payload.intercepts.some((row) => !exactKeys(row, ["ref", "label", "bearing", "bearing_uncertainty_deg", "frequency_hz", "frequency_band", "prf_hz", "modulation", "quality", "age_s", "radar_type", "threat", "signal_state", "operational", "ambiguous", "synthetic_assumption", "auto_jamming", "jamming", "jamming_effectiveness", "jamming_technique", "ecm_power_draw", "is_locked_on", "hoj_risk", "annotation", "candidates", "correlations", "signal_db", "range_estimate_nm", "scan_period_s"]) ||
          typeof row.synthetic_assumption !== "boolean" || typeof row.auto_jamming !== "boolean" || typeof row.jamming !== "boolean" ||
          !finite(row.signal_db) || [row.range_estimate_nm, row.scan_period_s].some((value) => value !== null && (!finite(value) || value < 0)) ||
          typeof row.is_locked_on !== "boolean" || typeof row.hoj_risk !== "boolean" || !["a_c", "d", "e_f", "g_h", "i_j", "k"].includes(row.frequency_band) ||
          (row.jamming_technique !== null && !["noise", "rgpo", "vgpo", "false_targets"].includes(row.jamming_technique)) ||
          typeof row.ambiguous !== "boolean" || typeof row.operational !== "boolean" || !["LIVE", "RECENT", "MEMORY", "UNCONFIRMED"].includes(row.signal_state) || !["low", "medium", "high", "critical", "unknown"].includes(row.threat) ||
          !boundedArray(row.candidates, 32) || row.candidates.some((item) => !exactKeys(item, ["ref", "name", "score"]) || (item.score !== null && !finite(item.score))) ||
          !boundedArray(row.correlations, 8) || row.correlations.some((item) => !exactKeys(item, ["ref", "source", "score", "ambiguous", "evidence"]) || !exactKeys(item.evidence, ["bearing", "bearing_uncertainty_deg", "age_s", "position_available"])))) throw new Error("protocol");
      if (typeof payload.station_down !== "boolean" || !["down", "live"].includes(payload.status)) throw new Error("protocol");
      if (!exactKeys(payload.hardware, ["df_sensors", "broadband_sensors", "ecm_channels", "frequency_min_hz", "frequency_max_hz", "reaction_s"]) ||
          payload.hardware.df_sensors !== 4 || payload.hardware.broadband_sensors !== 1 || payload.hardware.ecm_channels !== 4 ||
          !finite(payload.hardware.frequency_min_hz) || !finite(payload.hardware.frequency_max_hz) || !finite(payload.hardware.reaction_s)) throw new Error("protocol");
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

  function accumulateSonarHistory(state) {
    if (state.role !== "sonar" || !finite(state.clock?.sim)) return;
    const context = `${state.session}:${state.epoch}`;
    if (sonarHistory.context !== context) {
      sonarHistory.context = context;
      for (const name of ["broadband", "lofar", "demon"]) sonarHistory[name].clear();
    }
    const visual = state.sonar.visualization;
    for (const [name, rows] of [["broadband", visual.broadband.history], ["lofar", visual.lofar.history], ["demon", visual.demon.history]]) {
      const history = sonarHistory[name];
      for (const row of rows) {
        const stamp = state.clock.sim - row.age_s;
        if (!finite(stamp)) continue;
        history.set(Math.round(stamp * 1000), {...row, stamp});
      }
      for (const [key, row] of history) if (row.stamp < state.clock.sim - 605 || row.stamp > state.clock.sim + .001) history.delete(key);
      while (history.size > 3000) history.delete(history.keys().next().value);
    }
  }

  function stopSonarStream() {
    sonarStream.generation += 1;
    clearTimeout(sonarStream.retry);
    sonarStream.retry = null;
    const socket = sonarStream.socket;
    sonarStream.socket = null;
    sonarStream.connected = false;
    sonarStream.sequence = -1;
    if (socket) socket.close(1000, "station context changed");
  }

  function storeSonarStreamRow(name, stamp, bins, bearing = null) {
    if (!finite(stamp) || !Array.isArray(bins) || !bins.length) return;
    const row = {stamp, age_s: 0, bins};
    if (bearing !== null) row.bearing = bearing;
    const history = sonarHistory[name];
    history.set(Math.round(stamp * 1000), row);
    while (history.size > 3000) history.delete(history.keys().next().value);
  }

  function acceptSonarStreamFrame(buffer) {
    if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 60 || !v2State || v2State.role !== "sonar") throw new Error("sonar_stream_protocol");
    const view = new DataView(buffer);
    if (view.getUint8(0) !== 85 || view.getUint8(1) !== 74 || view.getUint8(2) !== 83 || view.getUint8(3) !== 50 ||
        view.getUint8(4) !== 1 || view.getUint8(5) !== 0 || view.getUint16(6, true) !== 60) throw new Error("sonar_stream_protocol");
    const sequence = Number(view.getBigUint64(8, true));
    const epoch = Number(view.getBigUint64(16, true));
    const simTime = view.getFloat64(24, true);
    const bearing = view.getFloat32(32, true);
    const counts = [36, 38, 40, 42, 44].map((offset) => view.getUint16(offset, true));
    const ages = [48, 52, 56].map((offset) => view.getFloat32(offset, true));
    if (!Number.isSafeInteger(sequence) || sequence <= sonarStream.sequence || !Number.isSafeInteger(epoch) ||
        epoch !== v2State.epoch || !finite(simTime) || !finite(bearing) || ages.some((age) => !finite(age) || age < 0) ||
        counts[0] > 180 || counts[1] > 256 || counts[2] > 80 || counts[3] > 256 || counts[4] > 80 ||
        60 + counts.reduce((sum, count) => sum + count, 0) !== buffer.byteLength) throw new Error("sonar_stream_protocol");
    let offset = 60;
    const take = (count) => { const values = Array.from(new Uint8Array(buffer, offset, count), (value) => value / 255); offset += count; return values; };
    const broadband = take(counts[0]), lofar = take(counts[1]), demon = take(counts[2]);
    sonarStream.lofarSpectrum = take(counts[3]);
    sonarStream.demonSpectrum = take(counts[4]);
    sonarStream.sequence = sequence;
    storeSonarStreamRow("broadband", simTime - ages[0], broadband);
    storeSonarStreamRow("lofar", simTime - ages[1], lofar, bearing);
    storeSonarStreamRow("demon", simTime - ages[2], demon);
    sampleDisplayClock(v2State, simTime);
    const visual = v2State.sonar.visualization;
    visual.lofar.spectrum = sonarStream.lofarSpectrum;
    visual.demon.spectrum = sonarStream.demonSpectrum;
    queueVisualDraw();
  }

  function syncSonarStream() {
    const allowed = authenticated() && connected && !document.hidden && session?.station === "sonar" &&
      v2State?.role === "sonar" && v2State.phase === "live";
    if (!allowed) { if (sonarStream.socket) stopSonarStream(); return; }
    if (sonarStream.socket) return;
    const streamGeneration = ++sonarStream.generation;
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new window.WebSocket(`${scheme}//${location.host}/ws/v2/sonar`, "u-jagd-sonar-v2");
    socket.binaryType = "arraybuffer";
    sonarStream.socket = socket;
    socket.addEventListener("open", () => {
      if (streamGeneration !== sonarStream.generation || sonarStream.socket !== socket) { socket.close(); return; }
      sonarStream.connected = true;
    });
    socket.addEventListener("message", (event) => {
      if (streamGeneration !== sonarStream.generation || sonarStream.socket !== socket) return;
      try { acceptSonarStreamFrame(event.data); }
      catch (_) { socket.close(4002, "invalid sonar frame"); }
    });
    socket.addEventListener("close", () => {
      if (sonarStream.socket === socket) sonarStream.socket = null;
      sonarStream.connected = false;
      if (streamGeneration === sonarStream.generation && authenticated()) {
        sonarStream.retry = setTimeout(syncSonarStream, 1000);
      }
    });
    socket.addEventListener("error", () => socket.close());
  }

  function useV2State(state) {
    accumulateSonarHistory(state);
    sampleDisplayClock(state);
    v2State = state;
    if (state.role === "sonar" && sonarStream.connected) {
      state.sonar.visualization.lofar.spectrum = sonarStream.lofarSpectrum;
      state.sonar.visualization.demon.spectrum = sonarStream.demonSpectrum;
    }
    updateOpzSweepSample(state);
    syncGameAudio();
    syncSonarStream();
    syncPlotAnimation();
  }

  function buildDisplayModel(state) {
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
    if (state.role === "eloka") observations = filteredEloka(payload.intercepts);
    const tracks = observations.map((row) => ({ref: row.ref, label: row.label || row.ref,
      domain: row.domain || "UNKNOWN", source: row.source || (state.role === "eloka" ? "ESM" : "HFDF"),
      affiliation: row.affiliation || "UNKNOWN", classification: row.classification ?? null,
      bearing: row.bearing ?? null, range_nm: row.range_nm ?? null, x: row.x ?? null, y: row.y ?? null,
      depth_m: row.depth_m ?? null, altitude_m: row.altitude_m ?? null, course: row.course ?? null, speed_kn: row.speed_kn ?? null,
      observer_x: row.observer_x ?? null, observer_y: row.observer_y ?? null,
      released_to_opz: row.released_to_opz === true,
      eloka_annotated: state.role === "eloka" && Boolean(row.annotation),
      quality: row.quality ?? null, age_s: row.age_s ?? null, fix_age_s: row.fix_age_s ?? null,
      bearing_uncertainty_deg: row.bearing_uncertainty_deg ?? null,
      range_uncertainty_nm: row.range_uncertainty_nm ?? null, fixes: row.fixes || [],
      members: row.members || [],
      can_classify: state.role === "sonar" || state.role === "helicopter" || (state.role === "opz" &&
        (row.source.startsWith("RADAR") || row.source.startsWith("SONAR") ||
         ["HOJ", "FUSION"].includes(row.source))),
      can_propose: state.role === "sonar"})).filter((row) => state.role !== "opz" || opzManage || !opzSuppressed.has(row.ref));
    return {version: state.version, session: state.session, epoch: state.epoch,
      revision: state.revision, seq: state.seq, phase: state.phase,
      chart_revision: state.chart_revision, clock: state.clock,
      environment: state.environment, mission: state.mission, ownship, tracks};
  }

  function validateState(state) {
    validateV2State(state);
    if (state.role === null) return;
    const display = buildDisplayModel(state);
    if (typeof display.session !== "string" || !display.session ||
        !Number.isSafeInteger(display.epoch) || !Number.isSafeInteger(display.revision) || !Number.isSafeInteger(display.seq) ||
        display.chart_revision == null ||
        !display.ownship || ["x", "y"].some((key) => display.ownship[key] !== null && !finite(display.ownship[key])) ||
        !display.clock || !display.mission || !Array.isArray(display.tracks) ||
        display.tracks.some((track) => !track || typeof track.ref !== "string" || !track.ref ||
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
    if (new Set(display.tracks.map((track) => track.ref)).size !== display.tracks.length) throw new Error("protocol");
    if (display.tracks.some((track) => new Set(track.fixes.map((fix) => fix.source)).size !== track.fixes.length)) throw new Error("protocol");
    const environment = display.environment;
    if (environment != null && (typeof environment !== "object" || Array.isArray(environment) ||
        Object.keys(environment).sort().join(",") !== "effective_sea_state,is_night,rain_intensity,sea_state,visibility_nm,weather,wind_from_deg,wind_speed_kn" ||
        (environment.sea_state !== null && (!Number.isInteger(environment.sea_state) || environment.sea_state < 0 || environment.sea_state > 9)) ||
        (environment.is_night !== null && typeof environment.is_night !== "boolean"))) throw new Error("protocol");
  }

  function validateChart(data, state) {
    if (!data || data.protocol !== 2 ||
        data.revision !== state.chart_revision || !finite(data.size_nm) || data.size_nm <= 0 ||
        !Array.isArray(data.landmasses) || data.landmasses.some((land) => !Array.isArray(land.points) ||
          land.points.some((point) => !Array.isArray(point) || point.length !== 2 || !point.every(finite)))) throw new Error("chart");
    if (data.geography !== undefined) {
      const geo = data.geography;
      if (!exactKeys(geo, ["labels", "airbases", "depths", "hazards"]) ||
          !Array.isArray(geo.hazards) || geo.hazards.length > 64 || geo.hazards.some((row) =>
            !exactKeys(row, ["kind", "x", "y", "top_depth_m", "length_m"]) || !["wreck", "rock"].includes(row.kind) ||
            ![row.x, row.y, row.top_depth_m, row.length_m].every(finite)) ||
          ![geo.labels, geo.airbases].every((rows) => Array.isArray(rows) && rows.length <= 128 && rows.every((row) =>
            exactKeys(row, ["name", "x", "y"]) && typeof row.name === "string" && row.name.length <= 96 && finite(row.x) && finite(row.y))) ||
          !Array.isArray(geo.depths) || geo.depths.length > 64 || geo.depths.some((row) =>
            !Array.isArray(row) || row.length > 64 || !row.every(finite))) throw new Error("chart");
    }
  }

  function contextKey(value) {
    return value ? `${value.session}\n${value.epoch}\n${value.role}` : null;
  }

  function validateProposals(value) {
    if (!exactKeys(value, ["protocol", "session", "epoch", "role", "target", "navigation"]) ||
        value.protocol !== 2 || typeof value.session !== "string" || !value.session || value.session.length > 64 ||
        !Number.isSafeInteger(value.epoch) || value.epoch < 0 || !stationNames.includes(value.role)) throw new Error("proposals");
    const validStatus = (status) => ["pending", "accepted", "rejected", "expired"].includes(status);
    if (value.target !== null && (!exactKeys(value.target, ["ref", "label", "status"]) ||
        value.role !== "sonar" || typeof value.target.ref !== "string" || !value.target.ref || value.target.ref.length > 64 ||
        typeof value.target.label !== "string" || !value.target.label || value.target.label.length > 64 ||
        !validStatus(value.target.status))) throw new Error("proposals");
    if (value.navigation !== null && (!exactKeys(value.navigation, ["course", "speed_kn", "status"]) ||
        value.role !== "bridge" || !validStatus(value.navigation.status) ||
        (value.navigation.course !== null && (!finite(value.navigation.course) || value.navigation.course < 0 || value.navigation.course >= 360)) ||
        (value.navigation.speed_kn !== null && (!finite(value.navigation.speed_kn) || value.navigation.speed_kn < 0 || value.navigation.speed_kn > 25)) ||
        value.navigation.course === null && value.navigation.speed_kn === null)) throw new Error("proposals");
  }

  function renderProposals() {
    const sonar = session?.station === "sonar";
    const bridge = session?.station === "bridge";
    $("target-proposal-controls").hidden = !sonar;
    $("target-proposal").hidden = !sonar;
    $("navigation-proposal").hidden = !bridge;
    const target = sonar ? proposals?.target : null;
    $("proposal-status").textContent = target ? t(`proposal_${target.status}`, {label: target.label}) : "";
    const navigation = bridge ? proposals?.navigation : null;
    if (navigation) {
      const summary = t("navigation_summary", {
        course: navigation.course === null ? t("navigation_unchanged") : unit(navigation.course, "\u00b0", 0),
        speed: navigation.speed_kn === null ? t("navigation_unchanged") : unit(navigation.speed_kn, "kn"),
      });
      $("navigation-status").textContent = t(`proposal_${navigation.status}`, {label: summary});
    } else $("navigation-status").textContent = t("navigation_none");
  }

  function validateEvents(value) {
    if (!exactKeys(value, ["protocol", "session", "epoch", "role", "latest_seq", "events"]) ||
        value.protocol !== 2 || typeof value.session !== "string" || !value.session || value.session.length > 64 ||
        !Number.isSafeInteger(value.epoch) || value.epoch < 0 || !stationNames.includes(value.role) ||
        !Number.isSafeInteger(value.latest_seq) || value.latest_seq < 0 ||
        !boundedArray(value.events, 128)) throw new Error("events");
    let previous = 0;
    for (const event of value.events) {
      if (!exactKeys(event, ["seq", "kind", "severity", "message"]) ||
          !Number.isSafeInteger(event.seq) || event.seq <= previous || event.seq < 1 || event.seq > value.latest_seq ||
          typeof event.kind !== "string" || !event.kind || event.kind.length > 32 ||
          !["info", "warning"].includes(event.severity) ||
          typeof event.message !== "string" || !event.message || event.message.length > 512) throw new Error("events");
      previous = event.seq;
    }
  }

  function useEvents(value, state) {
    const key = contextKey(state);
    if (eventContext !== key || eventBaselinePending || document.hidden || !navigator.onLine) {
      eventContext = key;
      eventHighWater = value.latest_seq;
      eventHistory = value.events.slice(-80);
      if (!document.hidden && navigator.onLine) eventBaselinePending = false;
    } else {
      const fresh = value.events.filter((event) => event.seq > eventHighWater);
      if (fresh.some((event) => event.severity === "warning")) playAlert();
      eventHistory = [...eventHistory, ...fresh].slice(-80);
      eventHighWater = Math.max(eventHighWater, value.latest_seq);
    }
    renderEvents();
  }

  function renderEvents() {
    $("event-list").replaceChildren(...[...eventHistory].reverse().map((event) => {
      const item = node("li", undefined, event.severity === "warning" ? "warning" : "");
      item.append(node("span", `${event.seq} / ${event.kind}`, "event-meta"), node("span", event.message));
      return item;
    }));
    if (!eventHistory.length) $("event-list").append(node("li", t("no_events")));
  }

  async function pollRoleFeeds(state, context) {
    const nextProposals = await request("/proposals", {guard: () => context === generation});
    validateProposals(nextProposals);
    if (contextKey(nextProposals) !== contextKey(state)) return;
    const nextEvents = await request("/events", {guard: () => context === generation});
    validateEvents(nextEvents);
    if (context !== generation || contextKey(nextEvents) !== contextKey(state) ||
        contextKey(state) !== contextKey(v2State)) return;
    proposals = nextProposals;
    renderProposals();
    useEvents(nextEvents, state);
  }

  async function poll() {
    if (!authenticated() || polling) return;
    polling = true;
    const context = generation;
    const started = performance.now();
    let delay = 500;
    try {
      if (started - lastSessionFetch >= 1000) {
        const metadata = await request("/session");
        if (context !== generation) return;
        acceptSession(metadata);
      }
      if (session.station === null) {
        failures = 0;
        lastSuccess = performance.now();
        setConnection("lobby");
        renderLobby();
        return;
      }
      if (session.host !== null) await pollHost(context);
      if (context !== generation) return;
      const stateRoute = sonarStream.connected && session.station === "sonar" ? "/state?sonar=stream" : "/state";
      let next = await request(stateRoute);
      if (context !== generation) return;
      if (next?.role !== null && next?.role !== session.station) {
        const metadata = await request("/session");
        if (context !== generation) return;
        acceptSession(metadata);
      }
      validateState(next);
      if (next.role !== null) { useV2State(next); next = buildDisplayModel(next); }
      if (!chartMatches(next)) {
        // Chart has no session field. Sandwich it between matching snapshots;
        // never display a previous session with a new session's geography.
        // Only a first load or a new world blanks the console; a re-fetch after
        // a pause or station switch repaints in place.
        if (!chart || chartSession !== next.session) $("operations").hidden = true;
        setConnection("syncing");
        const candidate = await request("/chart");
        if (context !== generation) return;
        validateChart(candidate, next);
        let confirmed = await request(stateRoute);
        if (context !== generation) return;
        validateState(confirmed);
        if (confirmed.role !== null) { useV2State(confirmed); confirmed = buildDisplayModel(confirmed); }
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
      if (next.role === null) {
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
        // A solo host in the menu is not "syncing": the host screen is the view.
        setConnection(session.host !== null && hostView?.phase === "menu" ? "connected" : "syncing");
        renderLobby();
        return;
      }
      if (sameContext(snapshot, next) && next.seq < snapshot.seq) throw new Error("sequence");
      const hadSnapshot = Boolean(snapshot);
      const sessionChanged = hadSnapshot && snapshot.session !== next.session;
      const epochChanged = hadSnapshot && !sessionChanged && snapshot.epoch !== next.epoch;
      const changed = !sameContext(snapshot, next);
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
            "engine-course-form", "engine-speed-form", "helicopter-waypoint-form"]) $(id).reset();
          $("sonar-control-page").value = "listen";
          renderSonarControlPage();
        }
        if (sessionChanged || epochChanged) {
          selected = null;
          eventContext = null;
          eventHighWater = 0;
          eventHistory = [];
          view.initialized = false;
          lookoutView.rangeNm = 100;
        }
      }
      snapshot = next;
      roleStale = false;
      document.body.removeAttribute("data-role-stale");
      await pollRoleFeeds(v2State, context);
      if (sonarAudioEnabled && !sonarAudioAuthorized()) stopSonarAudio("sonar_live_unavailable");
      if (pending) await pollV2Result(context);
      // A station switch that landed while this poll awaited its feeds replaced
      // the snapshot; this result belongs to the old station, drop it.
      if (context !== generation || snapshot !== next) return;
      if (!view.initialized) fitChart();
      if (selected && !selectedTrack()) selected = null;
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
        // Still retried automatically either way (no forced reload) - only
        // the message differs, so the operator can tell "network is rough"
        // from "the host is sending something broken".
        setConnection(PROTOCOL_ERROR_MESSAGES.has(error.message) ? "protocol_error" : "stale");
      }
    } finally {
      polling = false;
      if (authenticated()) {
        const cadence = session?.station === null ? 1000 : delay;
        pollTimer = setTimeout(poll, context !== generation ? 0 : failures ? delay : Math.max(0, cadence - (performance.now() - started)));
      }
    }
  }

  function flushSonarFocus() {
    if (!queuedSonarFocus) return;
    if (!(connected && session?.station === "sonar" &&
          session.grants.command === true && v2State?.role === "sonar" && v2State.phase === "live" &&
          chartMatches(snapshot) && snapshot.tracks.some((track) => track.ref === queuedSonarFocus))) {
      queuedSonarFocus = null;
      return;
    }
    if (v2State.sonar.settings.focus_ref === queuedSonarFocus) {
      queuedSonarFocus = null;
      return;
    }
    if (!stationActionAvailable()) return;
    const ref = queuedSonarFocus;
    queuedSonarFocus = null;
    sendStationAction("sonar_set_focus", {ref});
  }

  function selectTrack(ref) {
    const changed = selected !== ref;
    selected = ref;
    const track = selectedTrack();
    const role = v2State?.role;
    if (mapRoles.has(role) && hasPosition(track)) {
      Object.assign(roleMapViews[role], {x: track.x, y: track.y, follow: false});
    }
    renderTracks();
    renderDetail(true);
    queueDraw();
    queueVisualDraw();
    if (changed && role === "sonar" && track && v2State.sonar.settings.focus_ref !== ref &&
        connected && session?.grants.command === true && v2State.phase === "live" && chartMatches(snapshot))
      queuedSonarFocus = ref;
    flushSonarFocus();
  }

  function renderTracks() {
    const list = $("track-list");
    const term = $("contact-filter").value.trim().toLocaleLowerCase(language).slice(0, 48);
    const visibleTracks = snapshot.tracks.filter((track) => !term ||
      (`${track.label} ${track.source} ${track.domain} ${enumText(domains, track.domain)} ` +
       `${track.affiliation} ${enumText(affiliations, track.affiliation)} ${classificationText(track.classification)}`)
        .toLocaleLowerCase(language).includes(term));
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
      button.setAttribute("aria-pressed", String(track.ref === selected));
      const symbol = node("span", undefined, `domain-symbol ${domainClass(track.domain)}`);
      symbol.setAttribute("aria-hidden", "true");
      const body = node("span");
      body.append(node("span", track.label, "track-name"), node("span", `${enumText(domains, track.domain)} / ${enumText(affiliations, track.affiliation)}`, "track-info"));
      body.append(node("span", `${unit(track.bearing, "\u00b0", 0)} / ${unit(track.range_nm, "NM")} / ${unit(track.age_s, "s", 0)}`, "track-info"));
      const flags = [];
      if (track.ref === selected) flags.push(t("selected"));
      if (["sonar", "helicopter"].includes(session?.station))
        flags.push(t(track.released_to_opz ? "opz_release_active" : "opz_release_private"));
      if (session?.station === "eloka")
        flags.push(t(track.eloka_annotated ? "opz_release_active" : "opz_release_private"));
      if (opzMarked.has(track.ref)) flags.push(t("opz_marked"));
      if (opzSuppressed.has(track.ref)) flags.push(t("opz_suppressed"));
      if (flags.length) body.append(node("span", flags.join(" / "), "track-flags"));
      button.replaceChildren(symbol, body);
      // Preserve focused buttons across the two-Hz refresh, including reordering.
      if (list.children[index] !== button) list.insertBefore(button, list.children[index] || null);
    });
    if (!visibleTracks.length) list.replaceChildren(node("p", t(snapshot.tracks.length ? "contact_filter_empty" : "no_contacts"), "empty"));
    $("track-count").textContent = term ? `${number(visibleTracks.length, 0)} / ${number(snapshot.tracks.length, 0)}` : number(snapshot.tracks.length, 0);
  }

  function renderDetail(resetDraft = false) {
    const track = selectedTrack();
    $("classification-form").hidden = !["sonar", "helicopter", "opz"].includes(session?.station);
    $("affiliation-form").hidden = session?.station !== "opz";
    $("no-selection").hidden = Boolean(track);
    $("track-detail").hidden = !track;
    if (track) {
      let stationActions = document.getElementById("selection-station-actions");
      if (!stationActions) { stationActions = node("div", undefined, "station-row-actions"); stationActions.id = "selection-station-actions"; $("track-detail").append(stationActions); }
      if (session?.station === "sonar") {
        const key = `${track.ref}:${stationActionAvailable()}:${language}`;
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
      if (session?.station === "sonar" || session?.station === "helicopter") {
        const buoyContact = session.station === "helicopter" &&
          v2State?.helicopter?.buoy_observations.some((row) => row.ref === track.ref);
        const dipContact = session.station === "helicopter" &&
          v2State?.helicopter?.dip_observations.some((row) => row.ref === track.ref);
        const heliContact = buoyContact || dipContact;
        const qualified = Boolean(v2State?.helicopter?.buoy_observations.find((row) => row.ref === track.ref)?.qualified ||
          v2State?.helicopter?.dip_observations.find((row) => row.ref === track.ref)?.qualified);
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
        $("sonar-release").hidden = session.station === "helicopter" && !dipContact;
        $("sonar-release").textContent = t(track.released_to_opz ? "sonar_withdraw_opz" : "sonar_release_to_opz");
      } else if (session?.station === "eloka") {
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

  function renderActionState() {
    const track = selectedTrack();
    $("follow").disabled = !hasPosition(snapshot?.ownship);
    if ($("follow").disabled) view.follow = false;
    $("follow").setAttribute("aria-pressed", String(view.follow));
    const stationEnabled = stationActionAvailable();
    const sonarAction = stationEnabled &&
      (session.station === "sonar" || session.station === "helicopter") &&
      track?.can_classify === true;
    const opzAction = stationEnabled && session.station === "opz";
    $("apply-classification").disabled = !(sonarAction || opzAction && track?.can_classify === true);
    $("classification").disabled = $("apply-classification").disabled;
    $("apply-classification").textContent = t("apply");
    const dipReport = v2State?.helicopter?.dip_observations.find((row) => row.ref === track?.ref);
    const buoyReport = v2State?.helicopter?.buoy_observations.find((row) => row.ref === track?.ref);
    $("sonar-release").disabled = !(sonarAction && track &&
      (session.station !== "helicopter" || dipReport && (dipReport.qualified || dipReport.released_to_opz)));
    $("helicopter-qualify").disabled = !(stationEnabled && session.station === "helicopter" && track);
    $("helicopter-buoy-release").disabled = !(stationEnabled && session.station === "helicopter" &&
      buoyReport && (buoyReport.qualified || buoyReport.released_to_opz));
    $("apply-affiliation").disabled = !(opzAction && track);
    $("affiliation").disabled = $("apply-affiliation").disabled;
    const proposalAvailable = stationEnabled && proposals && contextKey(proposals) === contextKey(v2State);
    $("propose").disabled = !(proposalAvailable && session.station === "sonar" && track?.can_propose === true);
    $("clear-proposal").disabled = !(proposalAvailable && session.station === "sonar" && proposals.target !== null);
    const navigationAvailable = proposalAvailable && session.station === "bridge";
    for (const id of ["navigation-course", "navigation-speed", "propose-navigation"]) $(id).disabled = !navigationAvailable;
    const message = pending ? { key: pending.uncertain ? "command_uncertain" : "command_pending", status: "pending" } : commandMessage;
    const reason = Object.hasOwn(reasons, message?.reasoncode) ? t(reasons[message.reasoncode]) : message?.reasoncode || t("unavailable");
    $("command-status").textContent = message ? t(message.key, { reason }) : "";
    $("command-status").dataset.status = message?.status || "";
    $("station-command-status").textContent = message ? t(message.key, {reason}) : "";
    $("station-command-status").dataset.status = message?.status || "";
    if (message && message !== lastToastedMessage && message.status !== "pending") {
      lastToastedMessage = message;
      showToast(message.key, { reason }, message.status === "rejected" ? "danger" : "ok");
    }
    $("command-reconcile").hidden = !pending?.uncertain;
    $("retry-command").disabled = !pending?.uncertain || pending.inFlight || performance.now() < pending.retryAt ||
      !connected || session?.grants.command !== true || !sameContext(v2State, {
        session: pending?.body.world_session, epoch: pending?.body.world_epoch,
      });
    renderProposals();
    renderBridgeOrders();
    renderOpzControls();
    renderStationControls();
    renderDirectFireControls();
    renderDisabledReasons();
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
    let pendingConfirm = false;
    let anyReady = false;
    for (const button of document.querySelectorAll("[data-fire-action]")) {
      const owned = button.closest("[data-station-role]")?.dataset.stationRole === role;
      const spec = directFireSpec(button.dataset.fireAction);
      const fingerprint = directFireFingerprint(button.dataset.fireAction, spec);
      const isTarget = fireConfirmation?.action === button.dataset.fireAction;
      // The dialog holds its own fingerprint snapshot; if the underlying
      // spec changed while it was open (target dropped, readiness lost),
      // cancel rather than let a stale confirm silently go through.
      if (isTarget && (fireConfirmation.fingerprint !== fingerprint || performance.now() >= fireConfirmation.expiresAt)) {
        clearFireConfirmation();
      }
      const stillPending = fireConfirmation?.action === button.dataset.fireAction;
      button.disabled = !owned || !directFireAvailable() || !spec.ready ||
        actionIncludesInvalidDepth(button.dataset.fireAction, spec.params.depth_m);
      anyReady ||= owned && spec.ready && !actionIncludesInvalidDepth(button.dataset.fireAction, spec.params.depth_m);
      button.classList.toggle("armed", stillPending);
      button.textContent = t(button.dataset.fireAction);
      pendingConfirm ||= stillPending;
    }
    for (const control of document.querySelectorAll(".direct-fire-controls input, .direct-fire-controls select")) {
      const owned = control.closest("[data-station-role]")?.dataset.stationRole === role;
      control.disabled = !owned || !directFireAvailable();
    }
    const stateKey = fireStatusKey();
    const statusKey = stateKey === "fire_ready" && !anyReady ? "fire_not_ready" : stateKey;
    status.textContent = t(pendingConfirm ? "fire_confirmation_active" : statusKey);
    status.dataset.state = pendingConfirm ? "armed" : statusKey;
  }

  function actionIncludesInvalidDepth(action, depth) {
    return action.includes("torpedo") && (!finite(depth) || depth < 10 || depth > 300);
  }

  function fireConfirmSummary(action, spec) {
    const parts = [t(action)];
    if (spec.ref) parts.push(t("fire_confirm_dialog_target", { ref: spec.ref }));
    if (action.includes("torpedo") && finite(spec.params.depth_m)) {
      parts.push(t("fire_confirm_dialog_depth", { depth: spec.params.depth_m }));
    }
    return parts.join(" — ");
  }

  function activateDirectFire(button) {
    const action = button.dataset.fireAction;
    const spec = directFireSpec(action);
    if (!directFireAvailable() || !spec.ready || actionIncludesInvalidDepth(action, spec.params.depth_m)) return;
    clearFireConfirmation();
    fireConfirmation = {action, fingerprint: directFireFingerprint(action, spec),
      expiresAt: performance.now() + 5000};
    fireConfirmationTimer = setTimeout(() => { clearFireConfirmation(); renderDirectFireControls(); }, 5000);
    $("fire-confirm-summary").textContent = fireConfirmSummary(action, spec);
    renderDirectFireControls();
    const dialog = $("fire-confirm-dialog");
    if (!dialog.open) dialog.showModal();
  }

  function confirmFireDialog() {
    const state = fireConfirmation;
    clearFireConfirmation();
    if (!state) return;
    const spec = directFireSpec(state.action);
    const fingerprint = directFireFingerprint(state.action, spec);
    // Re-validate against the current state rather than trusting what was
    // true when the dialog opened - readiness or the target list can move
    // underneath a modal the operator took a few seconds to act on.
    if (!directFireAvailable() || !spec.ready || fingerprint !== state.fingerprint ||
        actionIncludesInvalidDepth(state.action, spec.params.depth_m)) {
      renderDirectFireControls();
      return;
    }
    sendStationAction(state.action, spec.params);
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
        "sonar-tma", "sonar-audition-mode", "sonar-listen-band", "sonar-listen-notch", "sonar-gain", "sonar-gain-submit", "sonar-band", "sonar-band-apply", "sonar-notch", "sonar-peak",
        "sonar-harmonic-input", "sonar-harmonic-submit", "sonar-harmonic-clear"]) $(id).disabled = !live;
      $("sonar-clear-focus").disabled = !live || sonar.focus_ref === null;
    }
    const engine = v2State?.engine;
    if (engine) {
      const live = available && engine.machinery.station_state !== "ZERSTOERT";
      for (const id of ["engine-telegraph", "engine-telegraph-submit", "engine-course", "engine-course-submit", "engine-speed", "engine-speed-submit", "engine-quiet"]) $(id).disabled = !live;
    }
    $("damage-team").disabled = !(available && session?.station === "damage" && v2State?.damage?.teams.length);
    $("opz-designate").disabled = !(available && session?.station === "opz" && selectedTrack() && v2State?.opz?.radar.live);
  }

  function renderSonarControlPage() {
    const page = $("sonar-control-page").value;
    for (const panel of document.querySelectorAll("[data-sonar-page]")) panel.hidden = panel.dataset.sonarPage !== page;
  }

  function stationActionAvailable() {
    return connected && !roleStale && session?.grants.command === true &&
      v2State?.phase === "live" && chartMatches(snapshot) && !pending;
  }

  const unavailable = (key, values = {}) => ({key, values});

  function stationUnavailableReason() {
    if (!session?.station) return unavailable("reason_role_revoked");
    if (!connected) return unavailable(linkState === "syncing" ? "connection_syncing" : "connection_stale", {age: 0});
    if (!v2State || roleStale || !chartMatches(snapshot)) return unavailable("connection_syncing");
    if (session.grants.command !== true) return unavailable("reason_grant_revoked");
    if (v2State.phase !== "live") return unavailable("reason_phase_blocked");
    if (pending) return unavailable(pending.uncertain ? "command_uncertain" : "command_pending");
    return null;
  }

  function directFireUnavailableReason(control) {
    const shared = stationUnavailableReason();
    if (shared) return shared;
    if (session?.grants.direct_fire !== true) return unavailable("reason_direct_fire_grant");
    const action = control.dataset.fireAction;
    const spec = directFireSpec(action);
    if (actionIncludesInvalidDepth(action, spec.params.depth_m)) return unavailable("reason_invalid_depth");
    const payload = v2State?.[session.station];
    if (!spec.ref && action !== "weapons_deploy_nixie") return unavailable("reason_no_target");
    if (session.station === "weapons") {
      if ((action === "weapons_launch_torpedo" && payload.inventory.torpedoes <= 0) ||
          (action === "weapons_deploy_nixie" && payload.inventory.nixies <= 0)) return unavailable("reason_no_inventory");
      if (action === "weapons_launch_torpedo" && !payload.tubes.some((tube) => tube.state === "ready")) return unavailable("reason_no_ready_tube");
    }
    if (session.station === "helicopter") {
      if (!payload.asset.airborne) return unavailable("reason_not_airborne");
      if (payload.asset.torpedoes <= 0) return unavailable("reason_no_inventory");
    }
    return unavailable("reason_not_ready");
  }

  function disabledReason(control) {
    if (!control.disabled) return null;
    if (control.dataset.fireAction) return directFireUnavailableReason(control);
    if (control.closest("#station-cards")) {
      const record = session?.stations[control.dataset.station];
      if (session?.requested_station) return unavailable("reason_station_request_pending");
      if (record?.status === "occupied") return unavailable("reason_station_occupied");
      if (record?.status === "mine") return unavailable("reason_station_already_leased");
      return unavailable("reason_station_change_pending");
    }
    if (["add-station", "mobile-add-station", "workstation-add-station"].includes(control.id)) {
      return unavailable(session?.requested_station ? "reason_station_request_pending" : "reason_station_change_pending");
    }
    if (["release-station", "mobile-release-station", "mobile-station"].includes(control.id)) {
      return unavailable("reason_station_change_pending");
    }
    if (control.closest("#host-bar, #host-screen, #host-slot-dialog, #host-new-dialog")) return hostUnavailableReason(control);
    if (control.id === "follow") return unavailable("reason_position_unavailable");
    if (control.id === "sonar-live-toggle") return unavailable("reason_sonar_audio_grant");
    const shared = stationUnavailableReason();
    if (shared) return shared;
    const sonar = v2State?.sonar?.settings;
    if (control.closest('[data-station-role="sonar"]') && sonar) {
      if (sonar.station_down) return unavailable("reason_sonar_down");
      if (control.id === "sonar-clear-focus" && sonar.focus_ref === null) return unavailable("reason_no_focus");
      if (["sonar-tas", "sonar-depth", "sonar-depth-submit"].includes(control.id)) {
        if (sonar.tow.state === "FAULT") return unavailable("reason_tas_fault");
        if (sonar.tow.speed_kn > sonar.tow.speed_max_kn) return unavailable("reason_tas_too_fast", {speed: number(sonar.tow.speed_kn), limit: number(sonar.tow.speed_max_kn)});
        if (sonar.tow.speed_kn < sonar.tow.speed_min_kn) return unavailable("reason_tas_too_slow", {speed: number(sonar.tow.speed_kn), limit: number(sonar.tow.speed_min_kn)});
        if (["sonar-depth", "sonar-depth-submit"].includes(control.id) && sonar.tow.state !== "STREAMED") return unavailable("reason_tas_not_streamed");
      }
      if (control.id === "sonar-ping" && !sonar.ping.ready) return unavailable("reason_cooldown", {seconds: number(sonar.ping.cooldown_s, 0)});
      if (control.id === "sonar-bt" && !sonar.bt.ready) return unavailable("reason_cooldown", {seconds: number(sonar.bt.cooldown_s, 0)});
    }
    if (control.closest('[data-station-role="engine"]') && v2State?.engine?.machinery.station_state === "ZERSTOERT") return unavailable("reason_engine_down");
    if (control.closest('[data-station-role="opz"]') && v2State?.opz?.radar.live === false) return unavailable("reason_opz_down");
    if (control.closest('[data-station-role="radio"]') && v2State?.radio?.station_down) return unavailable("reason_radio_down");
    if (control.closest('[data-station-role="bridge"]') && v2State?.bridge?.orders.station_down) return unavailable("reason_bridge_down");
    const helicopter = v2State?.helicopter;
    if (control.closest('[data-station-role="helicopter"]') && helicopter) {
      if (helicopter.readiness.flightdeck_down) return unavailable("reason_flightdeck_down");
      if (["helicopter-return", "helicopter-buoy", "helicopter-dip-toggle", "helicopter-dip-depth", "helicopter-dip-depth-submit", "helicopter-dip-ping"].includes(control.id) && !helicopter.asset.airborne) return unavailable("reason_not_airborne");
      if (control.id === "helicopter-buoy" && helicopter.asset.buoys <= 0) return unavailable("reason_no_buoys");
      if (control.id === "helicopter-dip-ping" && helicopter.asset.dip_ping_cooldown_s > 0) return unavailable("reason_cooldown", {seconds: number(helicopter.asset.dip_ping_cooldown_s, 0)});
    }
    return unavailable("reason_not_ready");
  }

  function renderDisabledReasons() {
    const visibleReasons = [];
    for (const control of document.querySelectorAll("button, input, select")) {
      const reason = disabledReason(control);
      if (reason) {
        const text = t(reason.key, reason.values);
        control.title = text;
        control.dataset.disabledReason = text;
        control.setAttribute("aria-disabled", "true");
        const stationPanel = control.closest("[data-station-role]");
        const relevant = stationPanel ? stationPanel.dataset.stationRole === session?.station
          : !control.closest("[hidden]");
        if (relevant && !visibleReasons.includes(text)) {
          visibleReasons.push(text);
        }
      } else {
        control.removeAttribute("title");
        delete control.dataset.disabledReason;
        control.removeAttribute("aria-disabled");
      }
    }
    $("disabled-control-explain").hidden = visibleReasons.length === 0;
    $("disabled-control-explain").dataset.reasons = JSON.stringify(visibleReasons.slice(0, 24));
    if (!visibleReasons.length) {
      $("disabled-control-help").hidden = true;
      $("disabled-control-explain").setAttribute("aria-expanded", "false");
    }
    else if (!$("disabled-control-help").hidden) {
      $("disabled-control-help").textContent = visibleReasons.slice(0, 24).join(" ");
    }
  }

  function renderOpzControls() {
    const active = session?.station === "opz";
    $("opz-controls").hidden = !active;
    $("opz-track-actions").hidden = !active;
    $("track-id-form").hidden = !active;
    if (!active) return;
    const radar = v2State?.opz?.radar;
    const available = stationActionAvailable() && radar?.live === true;
    $("opz-radar-surface").checked = radar?.surface === true;
    $("opz-radar-air").checked = radar?.air === true;
    if (finite(radar?.range_nm)) $("opz-range").value = String(radar.range_nm);
    for (const id of ["opz-radar-surface", "opz-radar-air", "opz-range"]) $(id).disabled = !available;
    $("opz-create-fusion").disabled = !available || opzMarked.size < 2 || opzMarked.size > 8;
    const track = selectedTrack();
    if (track && document.activeElement !== $("track-id")) $("track-id").value = track.label;
    $("track-id").disabled = !available || !track;
    $("apply-track-id").disabled = !available || !track;
    $("opz-mark").disabled = !track || track.source === "FUSION";
    $("opz-mark").setAttribute("aria-pressed", String(Boolean(track && opzMarked.has(track.ref))));
    $("opz-dissolve").disabled = !available || track?.source !== "FUSION";
    $("opz-suppress").disabled = !track;
    $("opz-suppress").textContent = t(track && opzSuppressed.has(track.ref) ? "opz_restore" : "opz_suppress");
    $("opz-mark-status").textContent = t("opz_mark_count", {count: opzMarked.size});
  }

  function renderSnapshot(resetDraft = false) {
    renderWeatherStation();
    $("mission-name").textContent = snapshot.mission.name;
    $("objective").textContent = snapshot.mission.objective;
    $("phase").textContent = enumText(phases, snapshot.phase);
    $("command-permission").textContent = t(session?.grants.command ? "commands_enabled" : "commands_disabled");
    $("autocrew-status").textContent = v2State?.autocrew ? t("autocrew_status", {
      status: t(`autocrew_${v2State.autocrew.status}`),
    }) : "";
    $("autocrew-overview").textContent = v2State?.autocrew_overview?.some((row) => row.enabled)
      ? t("autocrew_overview", {stations: v2State.autocrew_overview.filter((row) => row.enabled)
        .map((row) => `${t(`station_${row.station}`)}: ${t(`autocrew_${row.status}`)}`).join(", ")})
      : t("autocrew_overview_none");
    metrics($("mission-metrics"), [
      ["remaining", unit(snapshot.mission.remaining_s, "s", 0)],
      ["mission_clock", unit(snapshot.clock.mission, "s", 0)],
      ["world_clock", finite(snapshot.clock.world) ? `${String(Math.floor(snapshot.clock.world) % 24).padStart(2, "0")}:${String(Math.floor(snapshot.clock.world * 60) % 60).padStart(2, "0")}` : t("unavailable")],
    ]);
    renderStationView();
    renderBridgeOrders();
    $("chart-disclaimer").textContent = chart.disclaimer;
    $("snapshot-meta").textContent = t("snapshot_meta", { version: snapshot.version, seq: snapshot.seq, revision: snapshot.revision, sim: number(snapshot.clock.sim, 1) });
    renderTracks();
    renderDetail(resetDraft);
    queueDraw();
    renderLookoutStatus();
    queueLookoutDraw();
    flushSonarFocus();
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
    return session?.station === "bridge" &&
      session.grants.command === true && connected && !roleStale && v2State?.phase === "live" &&
      chartMatches(snapshot) && !pending && orders && (kind !== "course" || !orders.station_down);
  }

  function renderBridgeOrders() {
    const panel = $("bridge-orders");
    panel.hidden = session?.station !== "bridge";
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
    renderDisabledReasons();
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
    pending = {id, body, uncertain: false, inFlight: true, retryAt: 0};
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
      if (pending?.id === id) {
        pending.inFlight = false;
        pending.retryAt = performance.now() + 5000;
      }
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
    pending = {id, body, uncertain: false, inFlight: true, retryAt: 0};
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
      if (pending?.id === id) {
        pending.inFlight = false;
        pending.retryAt = performance.now() + 5000;
      }
      renderActionState();
    }
  }

  async function retryPendingCommand() {
    const command = pending;
    if (!command?.uncertain || command.inFlight || performance.now() < command.retryAt ||
        !connected || session?.grants.command !== true ||
        command.body.station !== session.station || command.body.station_generation !== session.station_generation ||
        command.body.active_generation !== session.active_generation ||
        command.body.world_session !== v2State?.session || command.body.world_epoch !== v2State?.epoch) return;
    command.inFlight = true;
    renderActionState();
    const context = generation;
    try {
      await request("/commands", {method: "POST", body: command.body, expected: 202, csrf: session.csrf,
        guard: () => context === generation && pending === command});
      nextCommandSeq = Math.max(nextCommandSeq, command.body.seq + 1);
    } catch (error) {
      if (context !== generation || pending !== command || error.message === "cancelled") return;
      if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
      else if (!error.status || error.status >= 500) setConnection("stale");
    } finally {
      if (pending === command) {
        command.inFlight = false;
        command.retryAt = performance.now() + 5000;
        renderActionState();
      }
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

    // Hidden view (#simlog): complete bounded simulation log, read-only.
  // Every entry carries its normal role context plus a detached full-truth
  // diagnostic snapshot, fully tabulated and plottable on the snapshot map.
  const simlogAffiliationColors = { FRIEND: "#81c5ff", NEUTRAL: "#8fdfab", HOSTILE: "#ff8080", UNKNOWN: "#f3cf79" };
  function simlogActive() { return location.hash === "#simlog" && authenticated(); }
  function applySimlogView() {
    const active = simlogActive();
    $("simlog-view").hidden = !active;
    $("operations").hidden = active;
    if (session) renderLobby();
    if (active) { releaseCanvas(canvas); releaseCanvas(lookoutCanvas); }
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
  // Map items are supplied by the selected full-truth diagnostic snapshot.
  function simlogMapItems(display) {
    const items = [];
    if (hasPosition(display.ownship)) {
      items.push({ section: "ship", value: display.ownship, domain: "SURFACE", color: "#a1e7cc",
        x: display.ownship.x, y: display.ownship.y, label: t("simlog_own") });
    }
    for (const track of display.tracks) {
      if (!hasPosition(track)) continue;
      items.push({ section: "track", value: track, domain: track.domain,
        color: simlogAffiliationColors[track.affiliation] || simlogAffiliationColors.UNKNOWN,
        x: track.x, y: track.y, label: track.label });
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
    context.fillStyle = palette().scopeBg;
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
        drawSymbolOn(context, x, y, item.domain, item.color, 6, item.value?.affiliation);
      }
      if (item.value.sunk === true || item.value.dead === true) {
        context.strokeStyle = item.color;
        context.beginPath(); context.moveTo(x - 8, y - 8); context.lineTo(x + 8, y + 8); context.stroke();
      }
    }
    plotted.forEach(({ item, x }, index) => {
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
    // Cleanup lives on the native "close" event (below) so every dismissal
    // path - this helper, the dialog's own close button, or the browser's
    // built-in Escape handling - converges on the same state reset.
  }
  function openSimlogMap(data, stamp, seq, latest = false) {
    if (!data || typeof data !== "object") return;
    const dialog = $("simlog-map-dialog");
    if (!dialog.open) {
      simlogMapFit = "world";
      $("simlog-map-world").setAttribute("aria-pressed", "true");
      $("simlog-map-units-fit").setAttribute("aria-pressed", "false");
    }
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
    if (!dialog.open) { dialog.hidden = false; dialog.showModal(); }
    queueSimlogMapDraw();
  }
  async function loadSimlog() {
    if (!simlogActive()) return;
    const status = $("simlog-status");
    if (session?.station === null || session?.simlog !== true) {
      latestSimlogState = null;
      status.hidden = false;
      status.textContent = t(session?.station === null ? "simlog_station_required" : "simlog_grant_required");
      $("simlog-current").replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
      $("simlog-list").replaceChildren();
      $("simlog-count").textContent = "";
      return;
    }
    const now = performance.now();
    if (now - lastSimlogFetch < 2000) return;
    lastSimlogFetch = now;
    const expected = v2State;
    if (!expected || expected.role !== session.station) return;
    try {
      const value = await request("/simlog");
      validateRoleSimlog(value, expected);
      if (!simlogActive() || contextKey(value) !== contextKey(v2State)) return;
      renderRoleSimlog(value.entries);
    } catch (error) {
      latestSimlogState = null;
      status.hidden = false;
      status.textContent = t(error.status === 403 ? "simlog_grant_required" : "simlog_unavailable");
      $("simlog-current").replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
      $("simlog-list").replaceChildren();
      $("simlog-count").textContent = "";
    }
  }

  function validateRoleSimlog(value, expected) {
    if (!exactKeys(value, ["protocol", "session", "epoch", "role", "entries"]) ||
        value.protocol !== 2 || value.session !== expected.session || value.epoch !== expected.epoch ||
        value.role !== expected.role || !boundedArray(value.entries, 64)) throw new Error("simlog_schema");
    let previous = 0;
    for (const entry of value.entries) {
      if (!exactKeys(entry, ["seq", "t", "stamp", "state", "truth"]) ||
          !Number.isSafeInteger(entry.seq) || entry.seq <= previous || entry.seq < 1 ||
          !finite(entry.t) || entry.t < 0 || entry.t > 1e12 ||
          typeof entry.stamp !== "string" || !entry.stamp || entry.stamp.length > 32) throw new Error("simlog_schema");
      validateV2State(entry.state);
      if (entry.state.session !== value.session || entry.state.epoch !== value.epoch || entry.state.role !== value.role)
        throw new Error("simlog_schema");
      validateSimlogTruth(entry.truth);
      previous = entry.seq;
    }
  }

  function validateSimlogTruth(value) {
    const arrays = ["subs", "surfaces", "animals", "torpedoes", "enemy_torpedoes", "decoys",
      "asms", "essms", "asrocs", "nixies", "buoys", "flights", "raiders"];
    if (!exactKeys(value, ["mission_t", "result", "world", "ship", "weapons", ...arrays,
      "helo", "radars"]) || arrays.some((key) => !boundedArray(value[key], 1024)) ||
      !value.ship || typeof value.ship !== "object" || !finite(value.ship.x) || !finite(value.ship.y))
      throw new Error("simlog_schema");
    const inspect = (item, depth = 0) => {
      if (depth > 4) throw new Error("simlog_schema");
      if (item === null || typeof item === "string" || typeof item === "boolean") return;
      if (typeof item === "number") { if (!finite(item)) throw new Error("simlog_schema"); return; }
      if (Array.isArray(item)) { item.forEach((child) => inspect(child, depth + 1)); return; }
      if (!item || typeof item !== "object") throw new Error("simlog_schema");
      Object.entries(item).forEach(([key, child]) => {
        if (!key || key.length > 64) throw new Error("simlog_schema");
        inspect(child, depth + 1);
      });
    };
    inspect(value);
  }

  function simlogTruthDisplay(truth) {
    const tracks = [];
    const add = (rows, domain, affiliation, prefix) => rows.forEach((row) => {
      tracks.push({...row, label: `${prefix}${row.id ?? row.seq ?? ""}`, domain, affiliation,
        speed_kn: row.speed ?? null});
    });
    add(truth.subs, "SUBSURFACE", "HOSTILE", "S-");
    add(truth.surfaces, "SURFACE", "UNKNOWN", "V-");
    add(truth.animals, "SUBSURFACE", "NEUTRAL", "B-");
    add(truth.torpedoes, "SUBSURFACE", "FRIEND", "T-");
    add(truth.enemy_torpedoes, "SUBSURFACE", "HOSTILE", "T-");
    add(truth.decoys, "SUBSURFACE", "UNKNOWN", "D-");
    add(truth.asms, "AIR", "HOSTILE", "M-");
    add(truth.essms, "AIR", "FRIEND", "M-");
    add(truth.asrocs, "AIR", "FRIEND", "M-");
    add(truth.nixies, "SUBSURFACE", "FRIEND", "N-");
    add(truth.buoys, "SUBSURFACE", "FRIEND", "B-");
    add(truth.flights, "AIR", "UNKNOWN", "A-");
    add(truth.raiders, "AIR", "HOSTILE", "R-");
    if (truth.helo.airborne) add([truth.helo], "AIR", "FRIEND", "H-");
    return {ownship: truth.ship, tracks};
  }

  function simlogTruthTable(titleKey, rows, ownship) {
    const wrap = node("div", undefined, "simlog-table-wrap");
    wrap.tabIndex = 0;
    wrap.append(node("h4", t(titleKey)));
    const table = node("table", undefined, "simlog-table");
    const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    if (rows.some((row) => finite(row.x) && finite(row.y))) keys.splice(Math.min(3, keys.length), 0, "distance_own");
    const head = node("tr");
    keys.forEach((key) => head.append(node("th", key === "distance_own" ? t(key) : key)));
    table.append(head);
    for (const value of rows) {
      const row = node("tr");
      keys.forEach((key) => {
        let cell = value[key];
        if (key === "distance_own") cell = finite(value.x) && finite(value.y)
          ? `${number(Math.hypot(value.x - ownship.x, value.y - ownship.y), 1)} NM` : t("unavailable");
        else if (cell && typeof cell === "object") cell = JSON.stringify(cell);
        else if (cell === null || cell === undefined) cell = t("unavailable");
        row.append(node("td", String(cell)));
      });
      table.append(row);
    }
    wrap.append(table);
    return wrap;
  }

  function simlogTruthSummary(entry) {
    const truth = entry.truth;
    const root = node("div", undefined, "simlog-current-body");
    root.append(simlogMetricBlock("simlog_own", Object.entries(truth.ship).map(([key, value]) =>
      [key, value && typeof value === "object" ? JSON.stringify(value) : String(value)])));
    root.append(simlogMetricBlock("simlog_world", [...Object.entries(truth.world),
      ["mission_t", truth.mission_t], ["result", truth.result ?? "-"]]));
    root.append(simlogMetricBlock("simlog_weapons", Object.entries(truth.weapons)));
    const display = simlogTruthDisplay(truth);
    const mapButton = node("button", t("simlog_map_open"));
    mapButton.type = "button";
    mapButton.addEventListener("click", () => openSimlogMap(display, entry.stamp, entry.seq,
      entry === latestSimlogState));
    root.append(mapButton);
    const sections = [["simlog_cat_subs", truth.subs], ["simlog_cat_surfaces", truth.surfaces],
      ["simlog_cat_animals", truth.animals], ["simlog_cat_torps", truth.torpedoes],
      ["simlog_cat_enemy_torps", truth.enemy_torpedoes], ["simlog_cat_decoys", truth.decoys],
      ["simlog_cat_asms", truth.asms], ["simlog_cat_essms", truth.essms],
      ["simlog_cat_asrocs", truth.asrocs], ["simlog_cat_nixies", truth.nixies],
      ["simlog_cat_buoys", truth.buoys], ["simlog_cat_flights", truth.flights],
      ["simlog_cat_raiders", truth.raiders], ["simlog_cat_helo", [truth.helo]]];
    sections.filter(([, rows]) => rows.length).forEach(([title, rows]) =>
      root.append(simlogTruthTable(title, rows, truth.ship)));
    root.append(simlogTruthTable("simlog_world", [truth.radars], truth.ship));
    return root;
  }

  function roleHistorySummary(entry, expanded = false) {
    const state = entry.state;
    const display = buildDisplayModel(state);
    if (expanded) return simlogTruthSummary(entry);
    const root = node("div", undefined, "simlog-current-body");
    root.append(simlogMetricBlock("mission", [
      ["mission", state.mission.name],
      ["phase", enumText(phases, state.phase)],
      ["remaining", unit(state.mission.remaining_s, "s", 0)],
      ["mission_clock", unit(state.clock.mission, "s", 0)],
    ]));
    root.append(simlogMetricBlock("station_dashboard", [
      ["role_assigned", t(`station_${state.role}`)],
      ["contacts", number(display.tracks.length, 0)],
      ["world_clock", finite(state.clock.world) ? `${String(Math.floor(state.clock.world) % 24).padStart(2, "0")}:${String(Math.floor(state.clock.world * 60) % 60).padStart(2, "0")}` : t("unavailable")],
    ]));
    return root;
  }

  function renderRoleSimlog(entries) {
    const status = $("simlog-status");
    $("simlog-count").textContent = number(entries.length, 0);
    if (!entries.length) {
      latestSimlogState = null;
      status.hidden = false;
      status.textContent = t("simlog_empty");
      $("simlog-current").replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
      $("simlog-list").replaceChildren();
      return;
    }
    status.hidden = true;
    latestSimlogState = entries.at(-1);
    $("simlog-current").replaceChildren(roleHistorySummary(latestSimlogState, true));
    $("simlog-list").replaceChildren(...[...entries].reverse().map((entry) => {
      const item = node("li", undefined, "simlog-entry");
      item.append(node("span", `${entry.stamp}  T+${Math.floor(entry.t)}s`, "simlog-stamp"),
        node("span", t(`station_${entry.state.role}`), "simlog-cat"));
      const details = node("details", undefined, "simlog-snapshot");
      details.append(node("summary", `${entry.state.mission.name} / ${enumText(phases, entry.state.phase)}`),
        roleHistorySummary(entry));
      details.addEventListener("toggle", () => {
        // Full values (own ship, world, every observation) are built only when opened.
        if (details.open) details.lastChild.replaceWith(roleHistorySummary(entry, true));
      });
      item.append(details);
      return item;
    }));
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
    chartInfo = [];
    drawChartHazards(ctx, chart.geography?.hazards || [], point, width, height, scale, chartInfo);
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
      // Range labels at the top of each ring, beside the north axis.
      ctx.save();
      ctx.globalAlpha = .9; ctx.fillStyle = "#8fbfb0"; ctx.textAlign = "left"; ctx.textBaseline = "top";
      for (const fraction of [.25, .5, .75, 1]) {
        const ringRange = radar.range_nm * fraction;
        ctx.fillText(t("radar_ring", {range: number(ringRange, Number.isInteger(ringRange) ? 0 : 1)}),
          ox + 4, oy - ringRange * scale + 2);
      }
      ctx.restore();
      const displayedSweep = v2State?.phase === "live" ?
        currentOpzSweepBearing() : radar.sweep_bearing;
      const sweep = displayedSweep * Math.PI / 180;
      const sweepDx = Math.sin(sweep), sweepDy = -Math.cos(sweep);
      const sweepLength = rayLengthToCanvasEdge(ox, oy, sweepDx, sweepDy, width, height);
      ctx.strokeStyle = "#8de6c4";
      ctx.beginPath(); ctx.moveTo(ox, oy);
      ctx.lineTo(ox + sweepDx * sweepLength, oy + sweepDy * sweepLength); ctx.stroke();
      ctx.globalAlpha = 1;
    }
    // No integration, dead reckoning or animation of tracks: only published fixes.
    for (const track of snapshot.tracks) {
      const color = colors[track.affiliation] || colors.UNKNOWN;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = track.ref === selected ? 2 : 1;
      if (!finite(track.x) || !finite(track.y)) {
        // A bearing starts at the platform that measured it (buoy, dip,
        // logged HFDF position), as on the role map; else at own ship.
        const observed = finite(track.observer_x) && finite(track.observer_y);
        if (!finite(track.bearing) || (!ownPosition && !observed)) continue;
        const [bx, by] = observed ? point(track.observer_x, track.observer_y) : [ox, oy];
        const reach = Math.hypot(width, height) + Math.hypot(bx - width / 2, by - height / 2);
        const angle = track.bearing * Math.PI / 180 - Math.PI / 2;
        const uncertainty = finite(track.bearing_uncertainty_deg) ? Math.min(180, Math.max(0, track.bearing_uncertainty_deg)) * Math.PI / 180 : 0;
        if (uncertainty) {
          ctx.globalAlpha = track.ref === selected ? .13 : .055;
          ctx.beginPath(); ctx.moveTo(bx, by); ctx.arc(bx, by, reach, angle - uncertainty, angle + uncertainty); ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1;
        }
        ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + Math.cos(angle) * reach, by + Math.sin(angle) * reach);
        if (track.ref === selected) { ctx.strokeStyle = palette().accent; ctx.lineWidth = 4; ctx.stroke(); }
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
      drawSymbol(x, y, track.domain, color, fontSize * .65, track.affiliation);
      if (track.ref === selected) { ctx.strokeStyle = palette().accent; ctx.lineWidth = 2; ctx.strokeRect(x - 25, y - 25, 50, 50); }
      ctx.fillStyle = color;
      ctx.fillText(String(track.label ?? ""), x + 31, y - 9, Math.max(60, width - x - 37));
      chartHits.push({ ref: track.ref, x, y });
      addMapInfo(chartInfo, x, y, "track", track);
    }
    // Independent sonar fixes share their parent track identity and are rebuilt
    // from the current snapshot on every draw, so stale markers cannot be hit.
    for (const track of snapshot.tracks) {
      for (const fix of track.fixes) {
        const [x, y] = point(fix.x, fix.y);
        const radius = Math.max(2, fix.uncertainty_nm * scale);
        if (x + radius < -60 || y + radius < -60 || x - radius > width + 60 || y - radius > height + 60) continue;
        ctx.strokeStyle = fix.source === "PING" ? "#59d8dc" : fix.source === "TMA" ? palette().amber : "#83c99a";
        ctx.lineWidth = track.ref === selected ? 2 : 1;
        ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(x - 6, y); ctx.lineTo(x + 6, y); ctx.moveTo(x, y - 6); ctx.lineTo(x, y + 6); ctx.stroke();
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fillText(`${String(track.label ?? "")} ${fix.source}`, x + 9, y - 8, Math.max(50, width - x - 13));
        chartHits.push({ ref: track.ref, x, y });
        addMapInfo(chartInfo, x, y, "fix", {...fix, label: track.label});
      }
    }
    if (ownPosition) {
      addMapInfo(chartInfo, ox, oy, "own", own);
      ctx.save();
      ctx.translate(ox, oy);
      ctx.strokeStyle = palette().accent; ctx.fillStyle = "#183e3c"; ctx.lineWidth = 2;
      ctx.beginPath();
      if (finite(own.course)) {
        ctx.rotate(own.course * Math.PI / 180);
        ctx.moveTo(0, -13); ctx.lineTo(7, 9); ctx.lineTo(-7, 9); ctx.closePath(); ctx.fill(); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, -16); ctx.lineTo(0, -35); ctx.stroke();
      } else {
        ctx.arc(0, 0, 8, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();
      ctx.fillStyle = palette().accent; ctx.fillText(t("ownship"), ox + 15, oy + 18);
    }
    const helo = own.helo;
    if (hasPosition(helo) && ["AUF", "ZURUECK"].includes(helo.state)) {
      const [hx, hy] = point(helo.x, helo.y);
      if (hx > -30 && hy > -30 && hx < width + 30 && hy < height + 30) {
        drawSymbol(hx, hy, "AIR", palette().accent, 8);
        ctx.fillStyle = palette().accent; ctx.fillText(t("helicopter"), hx + 15, hy + 5);
      }
    }
    if (v2State?.plot) drawPlotLayer(ctx, point, scale, width, height, null);
    ctx.fillStyle = "#c6d6d9"; ctx.fillText(t("north"), width - 27, 25);
    ctx.strokeStyle = "#c6d6d9"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(width - 23, 47); ctx.lineTo(width - 23, 31); ctx.lineTo(width - 27, 37); ctx.moveTo(width - 23, 31); ctx.lineTo(width - 19, 37); ctx.stroke();
    $("chart-scale").textContent = t("chart_scale", { distance: number(step, step < 1 ? 1 : 0) });
  }

  // Shared crew plot (marks, rulers, bearing lines, circles, DR lines): the
  // same objects the uConsole draws, from the common "plot" projection.
  function plotBearingDistance(x1, y1, x2, y2) {
    const dx = x2 - x1, dy = y2 - y1;
    return [((Math.atan2(dx, -dy) * 180 / Math.PI) % 360 + 360) % 360, Math.hypot(dx, dy)];
  }

  function plotText(item) {
    if (item.shape === "ruler") {
      const [bearing, distance] = plotBearingDistance(item.x, item.y, item.x2, item.y2);
      return t("plot_ruler", {label: item.label, bearing: number(bearing, 0).padStart(3, "0"), range: number(distance, 1)});
    }
    if (item.shape === "bearing") return t("plot_bearing", {label: item.label, bearing: number(item.bearing, 0).padStart(3, "0")});
    if (item.shape === "circle") return t("plot_circle", {label: item.label, range: number(item.radius_nm, 1)});
    if (item.shape === "dr") return t("plot_dr", {label: item.label, range: number(item.cpa_nm, 1), minutes: number(item.cpa_s / 60, 0)});
    return item.label;
  }

  function plotLabel() {
    return $("plot-label-input").value.trim().slice(0, v2State?.plot?.max_label || 24);
  }

  function plotClick(role, worldX, worldY) {
    const tool = $("plot-tool").value, label = plotLabel(), own = mapPayload(role).own;
    if (!stationActionAvailable() || !finite(worldX) || !finite(worldY) ||
        Math.abs(worldX) > 1000 || Math.abs(worldY) > 1000) return;
    const tenth = (value) => (Math.round(value * 10) / 10) % 360;
    if (tool === "mark") { sendStationAction("plot_add", {shape: "mark", x: worldX, y: worldY, label}); return; }
    if (tool === "bearing") {
      if (!hasPosition(own)) return;
      const [bearing, distance] = plotBearingDistance(own.x, own.y, worldX, worldY);
      if (distance > 0) sendStationAction("plot_add", {shape: "bearing", x: own.x, y: own.y, bearing: tenth(bearing), label});
      return;
    }
    if (!plotAnchor || plotAnchor.role !== role || plotAnchor.tool !== tool) {
      plotAnchor = {role, tool, x: worldX, y: worldY};
      queueVisualDraw();
      return;
    }
    const anchor = plotAnchor;
    plotAnchor = null;
    const [bearing, distance] = plotBearingDistance(anchor.x, anchor.y, worldX, worldY);
    if (tool === "ruler") {
      sendStationAction("plot_add", {shape: "ruler", x: anchor.x, y: anchor.y, x2: worldX, y2: worldY, label});
    } else if (tool === "circle" && distance > 0 && distance <= 200) {
      sendStationAction("plot_add", {shape: "circle", x: anchor.x, y: anchor.y, radius_nm: Math.round(distance * 100) / 100, label});
    } else if (tool === "dr" && distance > 0) {
      const speed = Number($("plot-speed").value);
      if (finite(speed) && speed >= 0 && speed <= 60) {
        sendStationAction("plot_add", {shape: "dr", x: anchor.x, y: anchor.y, course: tenth(bearing), speed_kn: speed, label});
      }
    }
    queueVisualDraw();
  }

  // Plot the selected track's measured bearing from its observer position.
  function plotTrackBearing() {
    const role = v2State?.role;
    if (!mapRoles.has(role)) return;
    const data = mapPayload(role), row = data.observations.find((item) => item.ref === selected);
    if (!row || !finite(row.bearing)) return;
    const origin = finite(row.observer_x) && finite(row.observer_y) ? {x: row.observer_x, y: row.observer_y} : data.own;
    if (!hasPosition(origin)) return;
    sendStationAction("plot_add", {shape: "bearing", x: origin.x, y: origin.y,
      bearing: (Math.round(row.bearing * 10) / 10) % 360, label: (plotLabel() || String(row.label || row.ref)).slice(0, 24)});
  }

  function renderPlotList() {
    const objects = v2State?.plot?.objects || [];
    const key = JSON.stringify(objects.map((item) => [item.id, plotText(item)]));
    if (key === plotListKey) return;
    plotListKey = key;
    $("plot-list").replaceChildren(...objects.map((item) => {
      const row = node("li", plotText(item));
      const rename = node("button", t("plot_rename"));
      rename.type = "button";
      rename.addEventListener("click", () => sendStationAction("plot_relabel", {id: item.id, label: plotLabel()}));
      const remove = node("button", t("plot_delete"));
      remove.type = "button";
      remove.addEventListener("click", () => sendStationAction("plot_remove", {id: item.id}));
      row.append(" ", rename, " ", remove);
      return row;
    }));
  }

  function drawPlotLayer(context, point, scale, width, height, info) {
    const objects = v2State?.plot?.objects || [];
    const far = 2 * Math.hypot(width, height) / Math.max(scale, 1e-6);
    context.save();
    context.strokeStyle = palette().plot; context.fillStyle = palette().plot; context.lineWidth = 1.5;
    for (const item of objects) {
      const [x, y] = point(item.x, item.y);
      let [lx, ly] = [x, y];
      context.beginPath();
      if (item.shape === "mark") {
        context.moveTo(x - 6, y - 6); context.lineTo(x + 6, y + 6); context.moveTo(x - 6, y + 6); context.lineTo(x + 6, y - 6);
      } else if (item.shape === "ruler") {
        const [x2, y2] = point(item.x2, item.y2);
        context.moveTo(x, y); context.lineTo(x2, y2);
        context.moveTo(x + 3, y); context.arc(x, y, 3, 0, Math.PI * 2); context.moveTo(x2 + 3, y2); context.arc(x2, y2, 3, 0, Math.PI * 2);
        [lx, ly] = [(x + x2) / 2, (y + y2) / 2];
      } else if (item.shape === "bearing") {
        const angle = item.bearing * Math.PI / 180, [ex, ey] = point(item.x + Math.sin(angle) * far, item.y - Math.cos(angle) * far);
        context.setLineDash([8, 8]); context.moveTo(x, y); context.lineTo(ex, ey); context.stroke(); context.setLineDash([]);
        context.beginPath(); context.arc(x, y, 3, 0, Math.PI * 2);
      } else if (item.shape === "circle") {
        context.arc(x, y, Math.max(2, item.radius_nm * scale), 0, Math.PI * 2);
      } else if (item.shape === "dr") {
        const [nx, ny] = point(item.now_x, item.now_y), angle = item.course * Math.PI / 180;
        const ahead = item.speed_kn / 3600 * 1800;
        const [ax, ay] = point(item.now_x + Math.sin(angle) * ahead, item.now_y - Math.cos(angle) * ahead);
        context.moveTo(x, y); context.lineTo(nx, ny); context.stroke();
        context.setLineDash([8, 8]); context.beginPath(); context.moveTo(nx, ny); context.lineTo(ax, ay); context.stroke(); context.setLineDash([]);
        context.beginPath(); context.rect(nx - 4, ny - 4, 8, 8);
        [lx, ly] = [nx, ny];
      }
      context.stroke();
      context.fillText(plotText(item), lx + 8, ly - 6);
      if (info) addMapInfo(info, lx, ly, "plot", item);
    }
    const anchor = plotAnchor && plotAnchor.role === v2State?.role ? plotAnchor : null;
    if (anchor) {
      const [x, y] = point(anchor.x, anchor.y);
      context.beginPath(); context.arc(x, y, 5, 0, Math.PI * 2); context.stroke();
    }
    context.restore();
  }

  // NATO-style symbol, same geometry as the uConsole (src/ui/nato_symbols.py):
  // the frame shows the operator's affiliation (hostile diamond, neutral
  // square, friend wide rectangle, unknown: no frame), the glyph the domain.
  function drawNatoSymbol(context, x, y, affiliation, domain, color, size) {
    const half = Math.max(5, size), height = Math.max(6, size * 1.3), glyph = Math.max(3, size * .5);
    context.strokeStyle = color; context.lineWidth = 2; context.beginPath();
    if (affiliation === "HOSTILE") {
      context.moveTo(x, y - height); context.lineTo(x + half, y); context.lineTo(x, y + height); context.lineTo(x - half, y); context.closePath();
    } else if (affiliation === "NEUTRAL") {
      context.rect(x - half, y - height, half * 2, height * 2);
    } else if (affiliation === "FRIEND") {
      context.rect(x - half - 2, y - height, half * 2 + 4, height * 2);
    }
    // Unknown affiliation: no frame, only the domain glyph (colour marks it).
    context.stroke();
    context.lineWidth = 1.6; context.beginPath();
    if (domain === "AIR") {
      context.moveTo(x - glyph, y + glyph * .7); context.lineTo(x, y - glyph * .7); context.lineTo(x + glyph, y + glyph * .7);
    } else if (domain === "MISSILE") {
      context.moveTo(x, y + glyph); context.lineTo(x, y - glyph); context.moveTo(x - glyph * .7, y - glyph * .2);
      context.lineTo(x, y - glyph); context.lineTo(x + glyph * .7, y - glyph * .2);
    } else if (domain === "SUBSURFACE") {
      context.arc(x, y + glyph * .3, glyph * 1.2, Math.PI, Math.PI * 2);
      context.moveTo(x - glyph * .4, y + glyph * .3); context.lineTo(x - glyph * .4, y - glyph * .4); context.lineTo(x + glyph * .4, y - glyph * .4);
    } else if (domain === "UNDERWATER_WEAPON") {
      context.moveTo(x - glyph, y); context.lineTo(x + glyph, y); context.moveTo(x + glyph * .4, y - glyph * .4);
      context.lineTo(x + glyph, y); context.lineTo(x + glyph * .4, y + glyph * .4);
    } else if (domain === "SURFACE") {
      context.moveTo(x - glyph * 1.2, y + glyph * .4); context.lineTo(x + glyph * 1.2, y + glyph * .4);
      context.moveTo(x + glyph * 1.2, y + glyph * .4); context.arc(x, y + glyph * .4, glyph * 1.2, 0, Math.PI, true);
    } else {
      context.arc(x, y, Math.max(1.5, glyph * .4), 0, Math.PI * 2);
    }
    context.stroke();
  }
  function drawSymbolOn(context, x, y, domain, color, size, affiliation = "UNKNOWN") {
    drawNatoSymbol(context, x, y, affiliation, domain, color, size);
  }
  function drawSymbol(x, y, domain, color, size, affiliation = "UNKNOWN") {
    drawNatoSymbol(ctx, x, y, affiliation, domain, color, size);
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
    lookoutCtx.fillStyle = environment?.is_night === true ? palette().scopeBg : environment?.is_night === false ? "#102833" : palette().bg;
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
    lookoutCtx.strokeStyle = palette().accent;
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
    if (!pairingAvailable) {
      $("pair-error").textContent = t("pair_failed");
      return;
    }
    $("pair-submit").disabled = true;
    $("pair-error").textContent = "";
    const code = $("code").value.toUpperCase();
    const name = $("name").value.trim();
    $("code").value = "";
    try {
      const result = await request("/pair", { method: "POST", body: {code, name}, auth: false });
      acceptSession(result);
      generation += 1;
      failures = 0;
      $("pairing").hidden = true;
      $("disconnect").hidden = false;
      setConnection(session.station === null ? "lobby" : "syncing");
      clearTimeout(pollTimer);
      poll();
    } catch (_) {
      $("pair-error").textContent = t("pair_failed");
      $("code").focus();
    } finally { $("pair-submit").disabled = false; }
  });
  $("language").addEventListener("change", () => loadLanguage($("language").value === "de" ? "de" : "en"));
  for (const [id, key] of [["eloka-status-filter", "status"], ["eloka-threat-filter", "threat"], ["eloka-band-filter", "band"]]) {
    $(id).addEventListener("change", () => {
      elokaFilters[key] = $(id).value;
      if (v2State?.role === "eloka") {
        snapshot = buildDisplayModel(v2State);
        if (!selectedTrack()) selected = null;
        renderSnapshot();
      }
    });
  }
  $("volume").addEventListener("input", () => {
    if (sonarAudioGain) sonarAudioGain.gain.value = sonarGainValue();
    syncGameAudio();
  });
  $("analysis-filter").addEventListener("input", renderContactAnalysis);
  $("contact-filter").addEventListener("input", renderTracks);
  $("analysis-category").addEventListener("change", renderContactAnalysis);
  // Pointer Events (not "click") so this canvas matches #chart/#role-map's
  // tap-vs-drag disambiguation: a touch that starts a scroll/pan gesture
  // must not also silently set the listen bearing.
  $("sonar-broadband").addEventListener("pointerdown", (event) => {
    if (session?.station !== "sonar" || !stationActionAvailable() || !broadbandVisible()
        || !event.isPrimary || event.button !== 0) return;
    const canvas = $("sonar-broadband");
    canvas.setPointerCapture(event.pointerId);
    sonarBroadbandDrag = {id: event.pointerId, x: event.clientX, y: event.clientY, moved: false};
  });
  $("sonar-broadband").addEventListener("pointermove", (event) => {
    const canvas = $("sonar-broadband");
    const bounds = canvas.getBoundingClientRect();
    const area = plotArea(canvas.clientWidth, canvas.clientHeight);
    const x = (event.clientX - bounds.left) * canvas.clientWidth / Math.max(1, bounds.width);
    if (x >= area.left && x <= area.left + area.width) {
      const bearing = (x - area.left) / area.width * 360;
      $("sonar-cursor-readout").value = t("sonar_cursor_bearing", {bearing: number(bearing, 1)});
    }
    if (!sonarBroadbandDrag || sonarBroadbandDrag.id !== event.pointerId) return;
    const dx = event.clientX - sonarBroadbandDrag.x;
    const dy = event.clientY - sonarBroadbandDrag.y;
    if (Math.hypot(dx, dy) > 5) sonarBroadbandDrag.moved = true;
  });
  $("sonar-broadband").addEventListener("pointerup", (event) => {
    if (!sonarBroadbandDrag || sonarBroadbandDrag.id !== event.pointerId) return;
    const gesture = sonarBroadbandDrag;
    sonarBroadbandDrag = null;
    $("sonar-broadband").releasePointerCapture(event.pointerId);
    if (gesture.moved || session?.station !== "sonar" || !stationActionAvailable()
        || !broadbandVisible()) return;
    const canvas = $("sonar-broadband");
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = (event.clientX - bounds.left) * canvas.clientWidth / bounds.width;
    const y = (event.clientY - bounds.top) * canvas.clientHeight / bounds.height;
    const area = plotArea(canvas.clientWidth, canvas.clientHeight);
    if (x < area.left || x >= area.left + area.width ||
        y < area.top || y >= area.top + area.height) return;
    const bearing = (x - area.left) / area.width * 360;
    const observations = v2State?.sonar?.observations ?? [];
    const nearest = observations.map((row) => ({row, delta: Math.abs(((row.bearing - bearing + 540) % 360) - 180)}))
      .sort((a, b) => a.delta - b.delta)[0];
    // Selecting an observed bearing locks its passive S-track and routes that
    // beam to live audio. Empty-water clicks remain free beam steering.
    if (nearest && nearest.delta <= Math.max(3, v2State.sonar.visualization.receiver.beam_width_deg / 2)) {
      selected = nearest.row.ref;
      sendStationAction("sonar_set_focus", {ref: nearest.row.ref});
    } else sendStationAction("sonar_set_listen_bearing", {bearing});
  });
  $("sonar-broadband").addEventListener("pointercancel", (event) => {
    if (sonarBroadbandDrag?.id === event.pointerId) sonarBroadbandDrag = null;
  });
  $("sonar-broadband").addEventListener("lostpointercapture", () => { sonarBroadbandDrag = null; });
  const sonarFrequencyAt = (canvas, event, maximum) => {
    const bounds = canvas.getBoundingClientRect();
    const area = plotArea(canvas.clientWidth, canvas.clientHeight);
    const x = (event.clientX - bounds.left) * canvas.clientWidth / Math.max(1, bounds.width);
    return x < area.left || x > area.left + area.width ? null : (x - area.left) / area.width * maximum;
  };
  // Environment (BT): the cursor depth reads the measured profile.
  const btReadout = (event) => {
    const canvas = $("sonar-environment"), bt = v2State?.sonar?.visualization?.bt;
    if (!bt || !bt.depths_m.length) return null;
    const bounds = canvas.getBoundingClientRect();
    const area = plotArea(canvas.clientWidth, canvas.clientHeight);
    const y = (event.clientY - bounds.top) * canvas.clientHeight / Math.max(1, bounds.height);
    if (y < area.top || y > area.top + area.height) return null;
    const maximum = Math.max(1, ...bt.depths_m);
    const depth = (y - area.top) / area.height * maximum;
    const speed = profileSpeedAt(bt.depths_m, bt.speeds_m_s, depth);
    const key = !finite(bt.thermocline_m) ? "sonar_cursor_depth"
      : depth < bt.thermocline_m ? "sonar_cursor_depth_above" : "sonar_cursor_depth_below";
    return {depth, text: t(key, {depth: number(depth, 0), speed: number(speed, 1)})};
  };
  let btRedrawQueued = false;
  const redrawBt = () => {
    if (btRedrawQueued) return;
    btRedrawQueued = true;
    requestAnimationFrame(() => { btRedrawQueued = false; if (v2State?.sonar) drawSonarVisuals(); });
  };
  $("sonar-environment").addEventListener("pointermove", (event) => {
    const reading = btReadout(event);
    sonarDisplay.btCursorDepth = reading ? reading.depth : null;
    sonarDisplay.btCursorText = reading ? reading.text : "";
    if (reading) $("sonar-cursor-readout").value = reading.text;
    redrawBt();
  });
  $("sonar-environment").addEventListener("pointerleave", () => {
    sonarDisplay.btCursorDepth = null;
    redrawBt();
  });
  let weatherRedrawQueued = false;
  const redrawWeatherProfile = () => {
    if (weatherRedrawQueued) return;
    weatherRedrawQueued = true;
    requestAnimationFrame(() => {
      weatherRedrawQueued = false;
      const profile = v2State?.weather_station?.profile;
      if ($("weather-dialog").open && profile !== undefined) drawWeatherProfile(profile);
    });
  };
  $("weather-profile").addEventListener("pointermove", (event) => {
    const canvas = $("weather-profile"), bounds = canvas.getBoundingClientRect();
    weatherCursor = {x: (event.clientX - bounds.left) * canvas.clientWidth / Math.max(1, bounds.width),
                     y: (event.clientY - bounds.top) * canvas.clientHeight / Math.max(1, bounds.height)};
    redrawWeatherProfile();
  });
  $("weather-profile").addEventListener("pointerleave", () => { weatherCursor = null; redrawWeatherProfile(); });
  $("sonar-lofar").addEventListener("pointermove", (event) => {
    const hz = sonarFrequencyAt($("sonar-lofar"), event, 300);
    const visual = v2State?.sonar?.visualization?.lofar;
    if (hz === null || !visual?.spectrum?.length) return;
    let bin = 0;
    for (let index = 1; index < visual.bin_frequencies_hz.length; index++)
      if (Math.abs(visual.bin_frequencies_hz[index] - hz) < Math.abs(visual.bin_frequencies_hz[bin] - hz)) bin = index;
    const level = visual.spectrum[bin] || 0;
    const db = 20 * Math.log10(Math.max(1e-6, level));
    const fundamental = v2State.sonar.settings.harmonic_hz;
    const order = finite(fundamental) && fundamental > 0 ? Math.max(1, Math.round(hz / fundamental)) : 1;
    $("sonar-cursor-readout").value = t("sonar_cursor_frequency", {frequency: number(hz, 1), strength: number(db, 1), harmonic: order});
  });
  $("sonar-lofar").addEventListener("click", (event) => {
    const hz = sonarFrequencyAt($("sonar-lofar"), event, 300);
    if (hz !== null && session?.station === "sonar" && stationActionAvailable()) sendStationAction("sonar_set_harmonic", {frequency_hz: hz});
  });
  $("sonar-demon-spectrum").addEventListener("click", (event) => {
    const hz = sonarFrequencyAt($("sonar-demon-spectrum"), event, 50);
    if (hz === null) return;
    if (session?.station === "sonar" && stationActionAvailable())
      sendStationAction("sonar_set_cursor", {page: "demon", frequency_hz: Math.round(hz * 2) / 2});
    if (sonarDisplay.demonCursor === null) {
      sonarDisplay.demonCursor = hz;
      $("sonar-cursor-readout").value = t("sonar_demon_cursor_first", {frequency: number(hz, 1)});
    } else {
      const spacing = Math.abs(hz - sonarDisplay.demonCursor);
      sonarDisplay.demonCursor = spacing > .05 ? spacing : hz;
      $("sonar-cursor-readout").value = t("sonar_demon_spacing", {spacing: number(spacing, 2), rpm: number(spacing * 60, 1)});
    }
    queueVisualDraw();
  });
  for (const id of ["sonar-palette", "sonar-black-level", "sonar-contrast", "sonar-history"]) {
    $(id).addEventListener("input", () => {
      sonarDisplay.palette = $("sonar-palette").value;
      sonarDisplay.black = Number($("sonar-black-level").value);
      sonarDisplay.contrast = Number($("sonar-contrast").value);
      sonarDisplay.history = Number($("sonar-history").value);
      queueVisualDraw();
    });
  }
  $("sonar-detach").addEventListener("click", () => {
    const scope = sonarVisualPage === "overview" ? "broadband" : sonarVisualPage;
    if (!sonarScopeNames.has(scope)) return;
    window.open(`${location.pathname}?scope=${encodeURIComponent(scope)}`, `ujagd-sonar-${scope}`, "popup,width=1280,height=800,noopener");
  });
  // The dialog's own toolbar (close/fit-to-world/fit-to-units) was never
  // wired to the click handlers and view-fit modes it was built to control.
  $("simlog-map-close").addEventListener("click", closeSimlogMap);
  // Fires for every dismissal path (this button, Escape, a future .close()
  // call) - the single place that resets the dialog's transient state.
  $("simlog-map-dialog").addEventListener("close", () => {
    simlogMapData = null;
    simlogMapSeq = null;
    simlogMapLatest = false;
    $("simlog-map-dialog").hidden = true;
    $("simlog-map-units").replaceChildren();
    releaseCanvas(simlogMapCanvas);
  });
  $("simlog-map-world").addEventListener("click", () => {
    simlogMapFit = "world";
    $("simlog-map-world").setAttribute("aria-pressed", "true");
    $("simlog-map-units-fit").setAttribute("aria-pressed", "false");
    queueSimlogMapDraw();
  });
  $("simlog-map-units-fit").addEventListener("click", () => {
    simlogMapFit = "units";
    $("simlog-map-world").setAttribute("aria-pressed", "false");
    $("simlog-map-units-fit").setAttribute("aria-pressed", "true");
    queueSimlogMapDraw();
  });
  $("disconnect").addEventListener("click", async () => {
    const csrf = session?.csrf;
    try {
      if (csrf) await request("/logout", {method: "POST", csrf});
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
  wideScreen.addEventListener("change", () => { if (v2State?.role) renderRoleVisuals(v2State.role); });
  $("mobile-station").addEventListener("change", () => chooseStation($("mobile-station").value));
  $("classification-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const classification = $("classification").value || null;
    if (session?.station === "sonar" || session?.station === "helicopter")
      sendStationAction("sonar_classify", {ref: selected, classification});
    else if (session?.station === "opz") sendStationAction("opz_classify", {ref: selected, classification});
  });
  $("classification").addEventListener("change", renderActionState);
  $("sonar-release").addEventListener("click", () => {
    const track = selectedTrack();
    if (track) sendStationAction("sonar_set_release", {
      ref: track.ref, released: !track.released_to_opz,
    });
  });
  $("helicopter-qualify").addEventListener("click", () => {
    const rows = [...(v2State?.helicopter?.buoy_observations || []),
      ...(v2State?.helicopter?.dip_observations || [])];
    const row = rows.find((item) => item.ref === selected);
    if (row) sendStationAction("helicopter_qualify", {ref: selected, enabled: !row.qualified});
  });
  $("helicopter-buoy-release").addEventListener("click", () => {
    const row = v2State?.helicopter?.buoy_observations.find((item) => item.ref === selected);
    if (row) sendStationAction("helicopter_buoy_release", {ref: selected,
      released: !row.released_to_opz});
  });
  $("affiliation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (session?.station === "opz") sendStationAction("opz_affiliate", {ref: selected, affiliation: $("affiliation").value});
  });
  $("track-id-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!selected || !$("track-id-form").reportValidity()) return;
    sendStationAction("opz_set_track_id", {
      ref: selected, label: $("track-id").value.toUpperCase(),
    });
  });
  $("opz-radar-surface").addEventListener("change", () => sendStationAction("opz_set_radar", {domain: "surface", enabled: $("opz-radar-surface").checked}));
  $("opz-ciws").addEventListener("change", () => sendStationAction("opz_set_ciws", {enabled: $("opz-ciws").checked}));
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
    const raw = v2State; if (raw) { snapshot = buildDisplayModel(raw); if (!selectedTrack()) selected = null; renderSnapshot(); }
  });
  $("opz-manage").addEventListener("change", () => {
    opzManage = $("opz-manage").checked;
    if (v2State) { snapshot = buildDisplayModel(v2State); renderSnapshot(); }
  });
  const numberAction = (formId, inputId, action, field, minimum, maximum) => {
    const form = $(formId);
    if (!form.reportValidity()) return;
    const value = $(inputId).valueAsNumber;
    if (!finite(value) || value < minimum || value > maximum) return;
    sendStationAction(action, {[field]: value});
  };
  for (const id of ["sonar-array-mode", "sonar-audition-mode", "sonar-band", "sonar-listen-band", "sonar-bearing", "sonar-depth", "sonar-gain",
    "sonar-harmonic-input", "engine-telegraph", "engine-course", "engine-speed", "helicopter-x", "helicopter-y",
    "helicopter-dip-depth",
    "weapons-fire-target", "weapons-fire-depth", "helicopter-fire-target", "helicopter-fire-depth", "opz-fire-target"]) {
    $(id).addEventListener("input", () => stationDrafts.add(id));
    $(id).addEventListener("change", () => stationDrafts.add(id));
    if (id.includes("fire")) for (const eventName of ["input", "change"]) $(id).addEventListener(eventName, () => {
      clearFireConfirmation(); renderDirectFireControls();
    });
  }
  for (const button of document.querySelectorAll("[data-fire-action]")) button.addEventListener("click", () => activateDirectFire(button));
  $("fire-confirm-cancel").addEventListener("click", clearFireConfirmation);
  $("fire-confirm-confirm").addEventListener("click", confirmFireDialog);
  // Converges every dismissal path (Cancel, the 5s timeout, and the
  // browser's own Escape handling) on the same state reset, mirroring
  // closeSimlogMap()'s use of the dialog's native close event.
  $("fire-confirm-dialog").addEventListener("close", () => {
    clearFireConfirmation();
    renderDirectFireControls();
  });
  $("sonar-control-page").addEventListener("change", renderSonarControlPage);
  for (const button of $("sonar-page-tabs").querySelectorAll("button")) {
    button.addEventListener("click", () => {
      sonarVisualPage = button.dataset.sonarVisual;
      $("sonar-control-page").value = ({environment: "array", active: "listen", broadband: "listen", overview: "listen"}[sonarVisualPage] || "analysis");
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
  $("sonar-audition-mode").addEventListener("change", () => sendStationAction("sonar_set_audition_mode", {mode: $("sonar-audition-mode").value}));
  $("sonar-gain-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-gain-form", "sonar-gain", "sonar_set_gain", "gain_db", -12, 24);
  });
  $("sonar-band-apply").addEventListener("click", () => sendStationAction("sonar_set_band_preset", {preset: $("sonar-band").value}));
  $("sonar-notch").addEventListener("change", () => sendStationAction("sonar_set_notch", {enabled: $("sonar-notch").checked}));
  $("sonar-listen-band").addEventListener("change", () => sendStationAction("sonar_set_band_preset", {preset: $("sonar-listen-band").value}));
  $("sonar-listen-notch").addEventListener("change", () => sendStationAction("sonar_set_notch", {enabled: $("sonar-listen-notch").checked}));
  $("sonar-peak").addEventListener("change", () => sendStationAction("sonar_set_peak_hold", {enabled: $("sonar-peak").checked}));
  $("sonar-tma-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const course = Number($("sonar-tma-course").value), speed = Number($("sonar-tma-speed").value), range = Number($("sonar-tma-range").value);
    if (selected && [course, speed, range].every(finite) && course >= 0 && course < 360 && speed >= 0 && speed <= 45 && range >= .2 && range <= 60)
      sendStationAction("sonar_tma_set", {ref: selected, course, speed_kn: speed, range_nm: range});
  });
  $("analysis-assign").addEventListener("click", () => {
    const profile = analysisProfile();
    if (profile && selected) sendStationAction("sonar_assign_profile", {ref: selected, profile_key: profile.key});
  });
  $("analysis-assign-clear").addEventListener("click", () => { if (selected) sendStationAction("sonar_assign_profile", {ref: selected, profile_key: null}); });
  $("sonar-tma-accept").addEventListener("click", () => { if (selected) sendStationAction("sonar_tma_accept", {ref: selected}); });
  $("sonar-tma-copy").addEventListener("click", () => { if (selected) sendStationAction("sonar_tma_copy_proposal", {ref: selected}); });
  $("sonar-demon-band").addEventListener("change", () => {
    const [low, high] = $("sonar-demon-band").value.split("-").map(Number);
    sendStationAction("sonar_set_demon_band", {low_hz: low, high_hz: high});
  });
  $("sonar-heterodyne").addEventListener("change", () => sendStationAction("sonar_set_heterodyne", {frequency_hz: Number($("sonar-heterodyne").value)}));
  $("sonar-integration").addEventListener("change", () => sendStationAction("sonar_set_integration", {seconds: Number($("sonar-integration").value)}));
  $("sonar-vernier").addEventListener("change", () => sendStationAction("sonar_set_vernier", {enabled: $("sonar-vernier").checked}));
  $("sonar-tas-flip").addEventListener("click", () => { if (selected) sendStationAction("sonar_tas_side", {ref: selected, action: "flip"}); });
  $("sonar-tas-confirm").addEventListener("click", () => { if (selected) sendStationAction("sonar_tas_side", {ref: selected, action: "confirm"}); });
  $("sonar-demon-mark").addEventListener("click", () => sendStationAction("sonar_mark_line", {page: "demon"}));
  $("sonar-band-edges-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const low = Number($("sonar-band-low-hz").value), high = Number($("sonar-band-high-hz").value);
    if (finite(low) && finite(high) && low >= 0 && low < high && high <= 300) sendStationAction("sonar_set_band", {low_hz: low, high_hz: high});
  });
  $("sonar-operator-notch-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-operator-notch-form", "sonar-operator-notch", "sonar_set_operator_notch", "frequency_hz", 0.000001, 300);
  });
  $("sonar-operator-notch-clear").addEventListener("click", () => sendStationAction("sonar_set_operator_notch", {frequency_hz: null}));
  $("sonar-harmonic-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-harmonic-form", "sonar-harmonic-input", "sonar_set_harmonic", "frequency_hz", 0.000001, 300);
  });
  $("sonar-harmonic-clear").addEventListener("click", () => sendStationAction("sonar_set_harmonic", {frequency_hz: null}));
  $("engine-telegraph-submit").addEventListener("click", () => sendStationAction("engine_set_telegraph", {order: $("engine-telegraph").value}));
  $("engine-course-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("engine-course-form", "engine-course", "engine_set_course", "course", 0, 359.99999999999994);
  });
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
  for (const mode of ["acoustic", "map"]) $(
    `helicopter-visual-${mode}`).addEventListener("click", () => {
      helicopterVisualPage = mode;
      renderRoleVisuals("helicopter");
    });
  for (const button of $("helicopter-acoustic-plot-tabs").querySelectorAll("button"))
    button.addEventListener("click", () => {
      helicopterPlot = button.dataset.helicopterPlotTab;
      renderRoleVisuals("helicopter");
    });
  $("helicopter-broadband-canvas").addEventListener("click", (event) => {
    if (session?.station !== "helicopter" || !stationActionAvailable()) return;
    const canvas = event.currentTarget, area = plotArea(canvas.clientWidth, canvas.clientHeight);
    const x = event.clientX - canvas.getBoundingClientRect().left - area.left;
    if (x >= 0 && x < area.width) sendStationAction("helicopter_set_listen_bearing",
      {bearing: Math.max(0, Math.min(359.9, x / area.width * 360))});
  });
  $("helicopter-buoy-mode").addEventListener("change", () => sendStationAction(
    "helicopter_set_buoy_mode", {mode: $("helicopter-buoy-mode").value}));
  $("helicopter-listen-source").addEventListener("change", () => sendStationAction(
    "helicopter_set_listen_source", {source: $("helicopter-listen-source").value}));
  $("helicopter-listen-bearing-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const bearing = $("helicopter-listen-bearing").valueAsNumber;
    if (finite(bearing) && bearing >= 0 && bearing < 360)
      sendStationAction("helicopter_set_listen_bearing", {bearing});
  });
  $("helicopter-listen-auto").addEventListener("click", () => sendStationAction(
    "helicopter_clear_listen_bearing", {}));
  $("helicopter-audition-mode").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_mode", {mode: $("helicopter-audition-mode").value}));
  $("helicopter-audio-band").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_band", {preset: $("helicopter-audio-band").value}));
  $("helicopter-audio-notch").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_notch", {enabled: $("helicopter-audio-notch").checked}));
  $("helicopter-audio-gain").addEventListener("input", () => {
    $("helicopter-audio-gain-value").value = `${$("helicopter-audio-gain").value} dB`;
  });
  $("helicopter-audio-gain").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_gain", {gain_db: Number($("helicopter-audio-gain").value)}));
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
  $("propose").addEventListener("click", () => {
    const track = selectedTrack();
    if (track?.can_propose) sendStationAction("propose_target", {ref: track.ref});
  });
  $("clear-proposal").addEventListener("click", () => sendStationAction("clear_target_proposal", {}));
  $("navigation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const params = {};
    const course = $("navigation-course").value.trim() ? $("navigation-course").valueAsNumber : null;
    const speed = $("navigation-speed").value.trim() ? $("navigation-speed").valueAsNumber : null;
    if (course !== null) params.course = course;
    if (speed !== null) params.speed_kn = speed;
    if (!Object.keys(params).length || (course !== null && (!finite(course) || course < 0 || course >= 360)) ||
        (speed !== null && (!finite(speed) || speed < 0 || speed > 25))) {
      commandMessage = {key: "navigation_invalid", status: "rejected"};
      renderActionState();
      return;
    }
    sendStationAction("propose_navigation", params);
  });
  $("bridge-course-form").addEventListener("submit", (event) => { event.preventDefault(); sendBridgeOrder("course"); });
  $("bridge-speed-form").addEventListener("submit", (event) => { event.preventDefault(); sendBridgeOrder("speed"); });
  $("retry-command").addEventListener("click", retryPendingCommand);
  for (const [id, name] of [["workstation-help", "guide"], ["workstation-library", "contacts"], ["workstation-lookout", "lookout"]]) {
    $(id).addEventListener("click", () => { $("workstation-tools").open = false; activateTab(name); });
  }
  $("workstation-release").addEventListener("click", releaseActiveStation);
  $("workstation-weather").addEventListener("click", () => { $("workstation-tools").open = false; toggleWeatherStation(true); });
  $("weather-close").addEventListener("click", () => toggleWeatherStation(false));
  $("weather-dialog").addEventListener("close", (event) => {
    // Only the dialog's own dismissal hides it (not a close from inside).
    if (event.target !== $("weather-dialog") || $("weather-dialog").open) return;
    $("weather-dialog").hidden = true;
    releaseCanvas($("weather-profile"));
  });
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
      syncGameAudio();
    } catch (_) { soundEnabled = false; renderSound(); $("sound").textContent = t("sound_unavailable"); }
  });
  $("sonar-live-toggle").addEventListener("click", async () => {
    if (sonarAudioEnabled) { stopSonarAudio(); return; }
    if (!(["sonar", "helicopter"].includes(session?.station) && session.grants.sonar_audio === true)) return;
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw new Error("audio");
      if (!audio) audio = new Audio();
      await audio.resume();
      if (audio.state !== "running" || !sonarAudioAuthorized()) throw new Error("audio");
      sonarAudioGain = audio.createGain();
      sonarAudioGain.gain.value = sonarGainValue();
      sonarAudioHighpass = audio.createBiquadFilter();
      sonarAudioHighpass.type = "highpass";
      sonarAudioHighpass.frequency.value = sonarFilterValues()[0];
      sonarAudioLowpass = audio.createBiquadFilter();
      sonarAudioLowpass.type = "lowpass";
      sonarAudioLowpass.frequency.value = sonarFilterValues()[1];
      sonarAudioGain.connect(sonarAudioHighpass);
      sonarAudioHighpass.connect(sonarAudioLowpass);
      sonarAudioLowpass.connect(audio.destination);
      if (audio.audioWorklet && window.AudioWorkletNode) {
        try {
          await audio.audioWorklet.addModule("/sonar-audio-worklet.js");
          sonarAudioWorklet = new AudioWorkletNode(audio, "sonar-audio-v2", {outputChannelCount: [1]});
          sonarAudioWorklet.connect(sonarAudioGain);
          sonarAudioWorklet.port.onmessage = ({data}) => {
            if (!sonarAudioEnabled) return;
            if (data?.type === "metrics") {
              sonarAudioMetrics = data;
              window.uJagdAudioDiagnostics = Object.freeze({
                bufferedSeconds: Math.max(0, Math.min(6, data.buffered * .25)),
                sequenceGaps: data.gaps, droppedBlocks: data.evictions,
                concealedBlocks: data.concealed, playbackRate: data.rate,
                stale: data.stale, transport: sonarAudioSocket ? "websocket" : "http"});
            }
            if (data?.type === "stale") {
              sonarAudioMetrics.stale = data.value;
              renderSonarAudio(data.value ? "sonar_live_stale" : "sonar_live_playing");
            }
          };
        } catch (_) { sonarAudioWorklet?.disconnect(); sonarAudioWorklet = null; }
      }
      sonarAudioEnabled = true;
      sonarAudioNextTime = audio.currentTime;
      renderSonarAudio("sonar_live_waiting");
      if (sonarAudioWorklet) openSonarAudioSocket();
      else scheduleSonarAudioPoll();
    } catch (_) { stopSonarAudio("sonar_live_unavailable"); }
  });
  const updateSonarAudioFilters = () => {
    for (const prefix of ["sonar", "helicopter"]) {
      $(`${prefix}-audio-highpass-value`).value = `${number(Number($(`${prefix}-audio-highpass`).value), 0)} Hz`;
      $(`${prefix}-audio-lowpass-value`).value = `${number(Number($(`${prefix}-audio-lowpass`).value), 0)} Hz`;
    }
    const [high, low] = sonarFilterValues();
    if (sonarAudioHighpass && audio) sonarAudioHighpass.frequency.setTargetAtTime(high, audio.currentTime, .02);
    if (sonarAudioLowpass && audio) sonarAudioLowpass.frequency.setTargetAtTime(low, audio.currentTime, .02);
  };
  $("sonar-audio-highpass").addEventListener("input", updateSonarAudioFilters);
  $("sonar-audio-lowpass").addEventListener("input", updateSonarAudioFilters);
  $("helicopter-audio-highpass").addEventListener("input", updateSonarAudioFilters);
  $("helicopter-audio-lowpass").addEventListener("input", updateSonarAudioFilters);
  $("helicopter-audio-volume").addEventListener("input", () => {
    $("helicopter-audio-volume-value").value = `${$("helicopter-audio-volume").value} %`;
    if (sonarAudioGain) sonarAudioGain.gain.value = sonarGainValue();
  });
  updateSonarAudioFilters();
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
  $("plot-tool").addEventListener("change", () => { plotAnchor = null; queueVisualDraw(); });
  $("plot-clear").addEventListener("click", () => sendStationAction("plot_clear", {}));
  $("plot-track-bearing").addEventListener("click", plotTrackBearing);
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
      if ($("plot-tools").open && $("plot-tool").value !== "off") {
        const geometry = roleMapGeometry(gesture.role), state = roleMapViews[gesture.role];
        if (geometry) plotClick(gesture.role, state.x + (x - rect.width / 2) / geometry.scale,
          state.y + (y - rect.height / 2) / geometry.scale);
      } else if (contact) {
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
  // Mouse-over: describe the nearest map item, or the chart position.
  $("role-map").addEventListener("pointermove", (event) => {
    const role = v2State?.role;
    if (roleMapDrag?.moved || event.pointerType === "touch" || !mapRoles.has(role)) { hideMapTooltip(); return; }
    const rect = $("role-map").getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const geometry = roleMapGeometry(role);
    const view = roleMapViews[role];
    const worldX = geometry ? view.x + (x - rect.width / 2) / geometry.scale : null;
    const worldY = geometry ? view.y + (y - rect.height / 2) / geometry.scale : null;
    const own = roleMapInfo.find((hit) => hit.kind === "own")?.item || null;
    showMapTooltip(event, mapTooltipLines(nearestMapInfo(roleMapInfo, x, y), worldX, worldY, own));
  });
  $("role-map").addEventListener("pointerleave", hideMapTooltip);
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
  $("disabled-control-explain").addEventListener("click", () => {
    const reasons = JSON.parse($("disabled-control-explain").dataset.reasons || "[]");
    $("disabled-control-help").textContent = reasons.join(" ");
    $("disabled-control-help").hidden = !$("disabled-control-help").hidden || reasons.length === 0;
    $("disabled-control-explain").setAttribute("aria-expanded", String(!$("disabled-control-help").hidden));
  });
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
  canvas.addEventListener("pointermove", (event) => {
    if (drag?.moved || event.pointerType === "touch" || !chart) { hideMapTooltip(); return; }
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const { width, height, scale } = chartGeometry();
    const worldX = view.x + (x - width / 2) / scale, worldY = view.y + (y - height / 2) / scale;
    const own = chartInfo.find((hit) => hit.kind === "own")?.item || null;
    showMapTooltip(event, mapTooltipLines(nearestMapInfo(chartInfo, x, y), worldX, worldY, own));
  });
  canvas.addEventListener("pointerleave", hideMapTooltip);
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
  for (const id of visualCanvasIds) new ResizeObserver(() => { queueVisualDraw(); syncOpzSweepAnimation(); }).observe($(id));
  window.addEventListener("resize", () => { queueDraw(); queueLookoutDraw(); queueVisualDraw(); });
  window.addEventListener("hashchange", () => { applySimlogView(); loadSimlog(); });
  document.addEventListener("visibilitychange", () => {
    // A background tab's event batch is not a new audible alarm on return.
    if (document.hidden) eventBaselinePending = true;
    if (document.hidden) stopSonarAudio("sonar_live_unavailable");
    if (document.hidden) stopSonarStream(); else syncSonarStream();
    if (document.hidden && authenticated()) setConnection("stale");
    syncOpzSweepAnimation();
    syncWeatherAnimation();
    syncPlotAnimation();
  });
  window.addEventListener("offline", () => { eventBaselinePending = true; stopSonarStream(); stopOpzSweepAnimation(); if (authenticated()) setConnection("stale"); });
  window.addEventListener("online", () => { syncOpzSweepAnimation(); syncSonarStream(); if (authenticated() && !polling) { clearTimeout(pollTimer); poll(); } });
  setInterval(() => {
    if (authenticated() && lastSuccess && performance.now() - lastSuccess > 4500) setConnection("stale");
    else if (linkState === "stale") renderConnection();
    if (pending) {
      if (!pending.inFlight && performance.now() >= pending.retryAt) pending.uncertain = true;
      renderActionState();
    }
  }, 1000);

  // ---- Station tabs -----------------------------------------------------
  // One tab per station this client holds, in fixed station order. The digit on
  // a tab is its station number (1-9), also usable as a hotkey.
  const stationTabText = {bridge: "tab_bridge", sonar: "tab_sonar", weapons: "tab_weapons", damage: "tab_damage",
    opz: "tab_opz", radio: "tab_radio", engine: "tab_engine", helicopter: "tab_helicopter", eloka: "tab_eloka"};
  function renderStationTabs(leased, shown) {
    const bar = $("station-tabs");
    const signature = leased.map((station) => `${station}:${t(stationTabText[station])}`).join("|");
    if (bar.dataset.signature !== signature) {
      bar.replaceChildren(...leased.map((station) => {
        const tab = node("button", undefined, "station-tab");
        tab.type = "button";
        tab.id = `station-tab-${station}`;
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-controls", "panel-operations");
        tab.dataset.station = station;
        tab.setAttribute("aria-label", t(`station_${station}`));
        tab.append(node("span", String(stationNames.indexOf(station) + 1), "station-key"),
          node("span", t(stationTabText[station]), "station-name"));
        tab.addEventListener("click", () => chooseStation(station));
        tab.addEventListener("keydown", (event) => {
          const tabs = [...bar.children];
          let index = tabs.indexOf(tab);
          if (event.key === "ArrowRight") index = (index + 1) % tabs.length;
          else if (event.key === "ArrowLeft") index = (index - 1 + tabs.length) % tabs.length;
          else if (event.key === "Home") index = 0;
          else if (event.key === "End") index = tabs.length - 1;
          else return;
          event.preventDefault();
          tabs[index].focus();
          chooseStation(tabs[index].dataset.station);
        });
        return tab;
      }));
      bar.dataset.signature = signature;
    }
    for (const tab of bar.children) {
      const on = tab.dataset.station === shown;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
      tab.title = `${t(`station_${tab.dataset.station}`)} \u00b7 ${t("station_tab_hint", {key: stationNames.indexOf(tab.dataset.station) + 1})}`;
    }
  }

  function stepStation(delta) {
    const held = stationNames.filter((station) => session?.stations[station].status === "mine");
    if (held.length < 2) return;
    const index = held.indexOf(activatingStation ?? session.station);
    chooseStation(held[(index + delta + held.length) % held.length]);
  }

  document.addEventListener("keydown", (event) => {
    if (!session?.station || event.ctrlKey || event.altKey || event.metaKey || event.isComposing ||
        event.repeat || $("operations").hidden) return;
    const target = event.target;
    if (event.key === "0" && !(target instanceof Element && (target.closest("input, select, textarea") || target.isContentEditable)) &&
        !document.querySelector("dialog[open]:not(#weather-dialog)")) {
      event.preventDefault();
      toggleWeatherStation();
      return;
    }
    if (target instanceof Element && (target.closest("input, select, textarea, dialog[open]") ||
        target.isContentEditable)) return;
    if (/^[1-9]$/.test(event.key)) {
      const station = stationNames[Number(event.key) - 1];
      if (session.stations[station].status === "mine") { event.preventDefault(); chooseStation(station); }
    } else if (event.key === "[" || event.key === "]") {
      event.preventDefault();
      stepStation(event.key === "]" ? 1 : -1);
    } else if (event.key === "?") {
      event.preventDefault();
      activateTab("guide");
    }
  });

  // ---- Solo host surface --------------------------------------------------
  const scenarioText = {s1_patrouille: "scenario_s1_patrouille", s2_doppeljagd: "scenario_s2_doppeljagd",
    s3_abfang: "scenario_s3_abfang", s4_zufall: "scenario_s4_zufall"};
  const hostResultText = {ok: "host_result_ok", phase_blocked: "host_result_phase_blocked",
    no_save: "host_result_no_save", save_failed: "host_result_save_failed",
    session_revoked: "host_result_session_revoked", stale_world_session: "host_result_stale",
    stale_world_epoch: "host_result_stale", stale_generation: "host_result_stale",
    role_revoked: "host_result_revoked", expired: "host_result_stale",
    context_invalidated: "host_result_stale"};

  function validateHost(value) {
    const fields = ["epoch", "difficulty", "difficulty_fields", "phase", "protocol", "scenario", "scenarios", "session", "slots", "world_mode"];
    if (!exactKeys(value, fields) || value.protocol !== 2 || typeof value.session !== "string" ||
        !Number.isSafeInteger(value.epoch) || value.epoch < 0 ||
        !Object.hasOwn(phases, value.phase) ||
        !["fixed", "procedural", "real_fixed"].includes(value.world_mode) || typeof value.scenario !== "string" ||
        !boundedArray(value.difficulty_fields, 32) || !value.difficulty_fields.every((row) =>
          exactKeys(row, ["name", "kind", "min", "max", "step", "default"]) &&
          typeof row.name === "string" && ["int", "float"].includes(row.kind) &&
          Number.isFinite(row.min) && Number.isFinite(row.max) && row.min <= row.max &&
          Number.isFinite(row.step) && row.step > 0 &&
          Number.isFinite(row.default) && row.min <= row.default && row.default <= row.max) ||
        !exactKeys(value.difficulty, value.difficulty_fields.map((row) => row.name)) ||
        !value.difficulty_fields.every((row) => {
          const amount = value.difficulty[row.name];
          return row.kind === "int" ? Number.isInteger(amount) && amount >= row.min && amount <= row.max :
            Number.isFinite(amount) && amount >= row.min && amount <= row.max;
        }) ||
        !boundedArray(value.scenarios, 8) || !value.scenarios.every((row) => exactKeys(row, ["key", "fixed"]) &&
          typeof row.key === "string" && typeof row.fixed === "boolean") ||
        !boundedArray(value.slots, 8) || !value.slots.every((row) => exactKeys(row, ["slot", "saved", "modified"]) &&
          Number.isSafeInteger(row.slot) && row.slot >= 1 && typeof row.saved === "boolean" &&
          (row.modified === null || Number.isSafeInteger(row.modified)))) throw new Error("protocol");
  }

  async function pollHost(context) {
    try {
      const next = await request("/host", {guard: () => context === generation});
      if (context !== generation) return;
      validateHost(next);
      hostView = next;
    } catch (error) {
      // The host surface can be withdrawn while the session lives: 403 only
      // means "refresh the session", it is not an expired login.
      if (error.status !== 403) throw error;
      hostView = null;
      lastSessionFetch = 0;
    }
    if (hostPending) await pollHostResult(context);
  }

  const hostPhaseAllows = (kind) => {
    const phase = hostView?.phase;
    return kind === "any" ? phase === "live" :
      phase === "live" || phase === "menu" || phase === "ended";
  };

  function hostUnavailableReason(control) {
    if (!hostView) return unavailable("connection_syncing");
    if (hostPending) return unavailable("host_pending");
    if (!connected) return unavailable("connection_stale", {age: 0});
    if (hostView.phase === "blocked") return unavailable("host_blocked");
    if (control.dataset.slot && !hostView.slots.find((row) => String(row.slot) === control.dataset.slot)?.saved) {
      return unavailable("host_slot_empty");
    }
    return unavailable("host_phase");
  }

  let webHostAvailable = false;
  function renderHost() {
    const active = session?.host !== null && session !== null;
    $("host-bar").hidden = !active;
    $("web-admin-link").hidden = !active || !webHostAvailable;
    const menu = active && hostView?.phase === "menu";
    $("host-screen").hidden = !menu || simlogActive();
    if (!active) {
      for (const id of ["host-save", "host-load", "host-new",
                        "host-instructor", "host-screen-new", "host-screen-load",
                        "host-new-start"]) $(id).disabled = true;
      for (const button of $("host-slot-list").querySelectorAll("button"))
        button.disabled = true;
      return;
    }
    const ready = Boolean(hostView) && !hostPending && connected;
    const any = ready && hostPhaseAllows("any");
    const replacing = ready && hostPhaseAllows("replacing");
    $("host-save").disabled = !any;
    $("host-load").disabled = !replacing;
    $("host-new").disabled = !replacing;
    $("host-instructor").disabled = !any;
    $("host-screen-new").disabled = !replacing;
    $("host-screen-load").disabled = !replacing;
    $("host-new-start").disabled = !replacing;
    for (const button of $("host-slot-list").querySelectorAll("button")) {
      button.disabled = !replacing || (button.dataset.mode === "load" &&
        !hostView.slots.find((row) => String(row.slot) === button.dataset.slot)?.saved);
    }
    const text = hostMessage ? t(hostMessage.key, hostMessage.values ?? {}) : "";
    for (const id of ["host-status", "host-screen-status"]) {
      $(id).textContent = text;
      $(id).dataset.status = hostMessage?.status ?? "";
    }
  }

  function setHostMessage(message) {
    hostMessage = message;
    clearTimeout(hostMessageTimer);
    if (message && message.status !== "pending") {
      hostMessageTimer = setTimeout(() => { hostMessage = null; renderHost(); }, 6000);
    }
    renderHost();
  }

  async function sendHostAction(action, params) {
    if (!session?.host || !hostView || hostPending || !connected) return;
    let id;
    try { id = secureId(); } catch (_) {
      setHostMessage({key: "command_no_crypto", status: "rejected"});
      return;
    }
    const body = Object.freeze({protocol: 2, id, seq: nextCommandSeq, station: "host",
      station_generation: session.host.generation, active_generation: 0,
      world_session: hostView.session, world_epoch: hostView.epoch, resource_revision: 0,
      action, params: Object.freeze(params)});
    hostPending = {id, seq: body.seq, action};
    setHostMessage({key: "host_result_pending", status: "pending"});
    const context = generation;
    try {
      await request("/commands", {method: "POST", body, expected: 202, csrf: session.csrf,
        guard: () => context === generation && hostPending?.id === id});
      nextCommandSeq += 1;
      clearTimeout(pollTimer);
      if (!polling) poll();
    } catch (error) {
      if (context !== generation || hostPending?.id !== id || error.message === "cancelled") return;
      hostPending = null;
      if (error.status === 401) forgetSession("connection_expired");
      else if (error.status === 409 || error.status === 403) {
        lastSessionFetch = 0;
        setHostMessage({key: "host_result_stale", status: "rejected"});
      } else setHostMessage({key: "host_result_rejected", status: "rejected"});
    }
  }

  async function pollHostResult(context) {
    const command = hostPending;
    const payload = await request("/results", {guard: () => context === generation && hostPending === command});
    if (context !== generation || hostPending !== command || !exactKeys(payload, ["protocol", "results"]) ||
        payload.protocol !== 2 || !boundedArray(payload.results, 64)) throw new Error("results");
    const result = payload.results.find((item) => exactKeys(item, ["id", "seq", "status", "reasoncode"]) &&
      item.id === command.id && item.seq === command.seq && ["applied", "rejected"].includes(item.status) &&
      typeof item.reasoncode === "string" && item.reasoncode.length <= 64);
    if (!result) return;
    hostPending = null;
    setHostMessage({key: hostResultText[result.reasoncode] ?? "host_result_rejected",
      status: result.status});
  }

  function closeHostDialog(dialog) { if (dialog.open) dialog.close(); }
  for (const id of ["host-slot-dialog", "host-new-dialog", "instructor-dialog"]) {
    $(id).addEventListener("close", () => { $(id).hidden = true; });
  }
  $("host-slot-cancel").addEventListener("click", () => closeHostDialog($("host-slot-dialog")));
  $("host-new-cancel").addEventListener("click", () => closeHostDialog($("host-new-dialog")));
  $("instructor-cancel").addEventListener("click", () => closeHostDialog($("instructor-dialog")));

  function openSlotDialog(mode) {
    if (!hostView) return;
    const dialog = $("host-slot-dialog");
    $("host-slot-title").textContent = t(mode === "save" ? "host_save_title" : "host_load_title");
    $("host-slot-note").textContent = t(mode === "save" ? "host_save_note" : "host_load_note");
    $("host-slot-list").replaceChildren(...hostView.slots.map((row) => {
      const item = node("li");
      const button = node("button", t(row.saved ? "host_slot_saved" : "host_slot_empty_label", {
        slot: row.slot, time: row.modified === null ? "" : new Date(row.modified * 1000).toLocaleString(language)}));
      button.type = "button";
      button.dataset.slot = String(row.slot);
      button.dataset.mode = mode;
      button.disabled = mode === "load" && !row.saved;
      button.addEventListener("click", () => {
        closeHostDialog(dialog);
        sendHostAction(mode === "save" ? "host_save" : "host_load", {slot: row.slot});
      });
      item.append(button);
      return item;
    }));
    renderDisabledReasons();
    dialog.hidden = false;
    if (!dialog.open) dialog.showModal();
    dialog.querySelector("button:not(:disabled)")?.focus();
  }

  function syncNewGameDifficulty() {
    const scenario = hostView?.scenarios.find((row) => row.key === $("host-new-scenario").value);
    const free = Boolean(scenario) && !scenario.fixed;
    for (const input of $("host-new-difficulty").querySelectorAll("input")) input.disabled = !free;
    $("host-new-difficulty-note").textContent = scenario
      ? t(free ? "host_new_difficulty_free" : "host_new_difficulty_fixed") : "";
  }

  function openNewGameDialog() {
    if (!hostView) return;
    const dialog = $("host-new-dialog");
    $("host-new-scenario").replaceChildren(...hostView.scenarios.map((row) => {
      const option = node("option", t(scenarioText[row.key] ?? "unknown"));
      option.value = row.key;
      return option;
    }));
    $("host-new-difficulty").replaceChildren(...hostView.difficulty_fields.map((field) => {
      const wrapper = node("div", undefined, "field");
      const inputId = `host-new-difficulty-${field.name}`;
      const label = node("label", t(`difficulty_${field.name}`));
      label.htmlFor = inputId;
      const input = node("input");
      input.type = "number";
      input.id = inputId;
      input.dataset.field = field.name;
      input.min = String(field.min);
      input.max = String(field.max);
      input.step = String(field.step);
      input.value = String(hostView.difficulty[field.name]);
      wrapper.append(label, input);
      return wrapper;
    }));
    $("host-new-scenario").value = hostView.scenario;
    $("host-new-world").value = hostView.world_mode;
    $("host-new-seed").value = "";
    syncNewGameDifficulty();
    renderDisabledReasons();
    dialog.hidden = false;
    if (!dialog.open) dialog.showModal();
    $("host-new-scenario").focus();
  }

  $("host-new-scenario").addEventListener("change", syncNewGameDifficulty);
  $("host-new-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!$("host-new-form").reportValidity()) return;
    const params = {scenario: $("host-new-scenario").value, world_mode: $("host-new-world").value};
    const difficultyInputs = $("host-new-difficulty").querySelectorAll("input");
    if (difficultyInputs.length && !difficultyInputs[0].disabled) {
      const difficulty = {};
      for (const input of difficultyInputs) {
        const field = hostView.difficulty_fields.find((row) => row.name === input.dataset.field);
        difficulty[input.dataset.field] = field.kind === "int"
          ? parseInt(input.value, 10) : Number(input.value);
      }
      params.difficulty = difficulty;
    }
    if ($("host-new-seed").value.trim()) params.seed = $("host-new-seed").valueAsNumber;
    closeHostDialog($("host-new-dialog"));
    sendHostAction("host_new_game", params);
  });
  for (const id of ["host-save"]) $(id).addEventListener("click", () => openSlotDialog("save"));
  for (const id of ["host-load", "host-screen-load"]) $(id).addEventListener("click", () => openSlotDialog("load"));
  for (const id of ["host-new", "host-screen-new"]) $(id).addEventListener("click", openNewGameDialog);
  $("host-instructor").addEventListener("click", () => {
    if (!hostView) return;
    const dialog = $("instructor-dialog");
    const sea = v2State?.environment?.sea_state;
    $("instructor-sea-state").value = String(Number.isSafeInteger(sea) ? sea : 3);
    $("instructor-event").value = "";
    dialog.hidden = false;
    if (!dialog.open) dialog.showModal();
    $("instructor-sea-state").focus();
  });
  $("instructor-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const seaState = Number($("instructor-sea-state").value);
    if (!Number.isSafeInteger(seaState) || seaState < 0 || seaState > 6) return;
    closeHostDialog($("instructor-dialog"));
    sendHostAction("host_instructor_environment", {sea_state: seaState,
      event: $("instructor-event").value || null});
  });

  async function bootstrap() {
    if (location.protocol === "https:") {
      fetch("/api/v2/web/status", {cache: "no-store"})
        .then((response) => {
          webHostAvailable = response.ok;
          renderHost();
          if (session) renderLobby();
        })
        .catch(() => {});
    }
    const resumed = await resumeSession();
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
