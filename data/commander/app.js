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
  const reasons = {
    invalid_schema: "reason_invalid_schema", unauthorized: "reason_unauthorized",
    stale_session: "reason_stale_session", stale_epoch: "reason_stale_epoch",
    commands_blocked: "reason_commands_blocked", duplicate_id: "reason_duplicate_id",
    revision_conflict: "reason_revision_conflict", unknown_track: "reason_unknown_track",
    ineligible_track: "reason_ineligible_track", proposal_pending: "reason_proposal_pending",
    ok: "reason_ok",
  };
  const colors = { UNKNOWN: "#f3cf79", FRIEND: "#81c5ff", NEUTRAL: "#8fdfab", HOSTILE: "#ff9090" };
  let language = (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
  let catalog = {};
  // Credentials are deliberately closure-local: no URL, DOM, persistence or logging.
  let token = null;
  let generation = 0;
  let snapshot = null;
  let chart = null;
  let chartSession = null;
  let chartEpoch = null;
  let selected = null;
  let connected = false;
  let linkState = "unpaired";
  let lastSuccess = 0;
  let failures = 0;
  let pollTimer = null;
  let polling = false;
  let pending = null;
  let commandMessage = null;
  let requestQueue = Promise.resolve();
  let activeRequest = null;
  let languageRequest = 0;
  let audio = null;
  let soundEnabled = false;
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
  let analysisError = false;

  const t = (key, values = {}) => (catalog[prefix + key] || "").replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_, name) => String(values[name] ?? ""));
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const hasPosition = (entity) => finite(entity?.x) && finite(entity?.y);
  const number = (value, digits = 1) => finite(value) ? value.toLocaleString(language, { minimumFractionDigits: digits, maximumFractionDigits: digits }) : t("unavailable");
  const unit = (value, symbol, digits = 1) => finite(value) ? `${number(value, digits)} ${symbol}` : t("unavailable");
  const enumText = (map, value) => t(map[value] || "unknown");
  const affClass = (value) => `aff-${Object.hasOwn(affiliations, value) ? value.toLowerCase() : "unknown"}`;
  const domainClass = (value) => `domain-${Object.hasOwn(domains, value) ? value.toLowerCase() : "unknown"}`;
  const selectedTrack = () => snapshot?.tracks.find((track) => track.ref === selected);
  const sameContext = (a, b) => a && b && a.session === b.session && a.epoch === b.epoch;
  const chartMatches = (state) => chart && chartSession === state.session && chartEpoch === state.epoch && chart.revision === state.chart_revision;
  const canCommand = () => connected && snapshot?.commands_allowed === true && chartMatches(snapshot) && !pending;
  const navigationLive = () => snapshot?.phase === "live" && hasPosition(snapshot?.ownship);

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = String(text ?? "");
    if (className) element.className = className;
    return element;
  }

  function metrics(element, entries) {
    element.replaceChildren(...entries.map(([key, value]) => {
      const group = node("div");
      group.append(node("dt", t(key)), node("dd", value));
      return group;
    }));
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
    if (focus) $(`tab-${name}`).focus();
    if (name === "operations") queueDraw();
    if (name === "lookout") { renderLookoutStatus(); queueLookoutDraw(); }
    if (name === "contacts") renderContactAnalysis();
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
  function request(path, { method = "GET", body, auth = true, expected = 200, guard } = {}) {
    const credential = auth ? token : null;
    const requestGeneration = generation;
    const run = async () => {
      if (auth && (!credential || requestGeneration !== generation)) throw new Error("cancelled");
      if (guard && !guard()) throw new Error("cancelled");
      const controller = new AbortController();
      activeRequest = controller;
      const timeout = setTimeout(() => controller.abort(), 4000);
      try {
        const headers = { Accept: "application/json" };
        if (credential) headers.Authorization = `Bearer ${credential}`;
        if (body !== undefined) headers["Content-Type"] = "application/json";
        const response = await fetch(`/api/v1${path}`, {
          method, headers, body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal, cache: "no-store", credentials: "omit", redirect: "error", mode: "same-origin",
        });
        if (response.status !== expected) {
          const error = new Error("http");
          error.status = response.status;
          throw error;
        }
        // A queued command acknowledgement need not contain a JSON body.
        if (expected === 202) { await response.text(); return null; }
        return await response.json();
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
      $("bootstrap").hidden = true;
      $("shell").hidden = false;
      renderConnection();
      renderSound();
      if (snapshot && chartMatches(snapshot)) renderSnapshot();
      renderContactAnalysis();
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
  }

  function forgetSession(message = "connection_unpaired") {
    generation += 1;
    token = null;
    activeRequest?.abort();
    clearTimeout(pollTimer);
    snapshot = null;
    chart = null;
    chartSession = null;
    chartEpoch = null;
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
    $("pairing").hidden = false;
    $("disconnect").hidden = true;
    $("pair-error").textContent = "";
    $("code").value = "";
    $("navigation-form").reset();
    $("navigation-status").textContent = "";
    activateTab("operations", false);
    for (const id of ["track-list", "detail-label", "detail-badges", "detail-metrics", "mission-name", "objective", "mission-metrics", "own-metrics", "inventory", "helo-metrics", "damage-list", "event-list", "chart-disclaimer", "proposal-status", "command-status", "snapshot-meta", "lookout-sea", "lookout-light", "lookout-own", "lookout-observations"]) $(id).replaceChildren();
    $("lookout-scope").dataset.light = "unknown";
    releaseCanvas(canvas);
    releaseCanvas(lookoutCanvas);
    setConnection("unpaired");
    $("connection").textContent = t(message);
  }

  function validateState(state) {
    if (!state || state.protocol !== 1 || typeof state.session !== "string" || !state.session ||
        !Number.isSafeInteger(state.epoch) || !Number.isSafeInteger(state.revision) || !Number.isSafeInteger(state.seq) ||
        state.chart_revision == null || typeof state.commands_allowed !== "boolean" ||
        !state.ownship || ["x", "y"].some((key) => state.ownship[key] !== null && !finite(state.ownship[key])) ||
        !state.clock || !state.mission || !Array.isArray(state.tracks) || !Array.isArray(state.events) || !Array.isArray(state.results) ||
        state.tracks.some((track) => !track || typeof track.ref !== "string" || !track.ref ||
          !Array.isArray(track.fixes) || track.fixes.length > 3 || track.fixes.some((fix) => !fix ||
            !["PING", "TMA", "SONOBUOY"].includes(fix.source) ||
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
    if (!data || data.revision !== state.chart_revision || !finite(data.size_nm) || data.size_nm <= 0 ||
        !Array.isArray(data.landmasses) || data.landmasses.some((land) => !Array.isArray(land.points) ||
          land.points.some((point) => !Array.isArray(point) || point.length !== 2 || !point.every(finite)))) throw new Error("chart");
  }

  async function poll() {
    if (!token || polling) return;
    polling = true;
    const context = generation;
    const started = performance.now();
    let delay = 500;
    try {
      let next = await request("/state");
      if (context !== generation) return;
      validateState(next);
      if (!chartMatches(next)) {
        // Chart has no session field. Sandwich it between matching snapshots;
        // never display a previous session with a new session's geography.
        $("operations").hidden = true;
        setConnection("syncing");
        const candidate = await request("/chart");
        if (context !== generation) return;
        validateChart(candidate, next);
        const confirmed = await request("/state");
        if (context !== generation) return;
        validateState(confirmed);
        if (!sameContext(next, confirmed) || confirmed.chart_revision !== candidate.revision || confirmed.seq < next.seq) throw new Error("chart");
        chart = candidate;
        chartSession = confirmed.session;
        chartEpoch = confirmed.epoch;
        next = confirmed;
      }
      if (sameContext(snapshot, next) && next.seq < snapshot.seq) throw new Error("sequence");
      const changed = !sameContext(snapshot, next);
      const quiet = !connected || changed || suppressNextEvents;
      const advanced = changed || !snapshot || next.seq > snapshot.seq;
      if (changed) {
        selected = null;
        if (pending) commandMessage = { key: "command_context_changed", status: "rejected" };
        pending = null;
        eventHistory = [];
        seenEvents.clear();
        eventHighWater = -1;
        view.initialized = false;
        lookoutView.rangeNm = 100;
      }
      snapshot = next;
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
      $("operations").hidden = false;
      renderSnapshot();
    } catch (error) {
      if (context !== generation) return;
      if (error.status === 401 || error.status === 403) {
        forgetSession("connection_expired");
      } else {
        failures += 1;
        delay = Math.min(8000, 500 * (2 ** Math.min(failures, 4)));
        setConnection("stale");
      }
    } finally {
      polling = false;
      if (token) pollTimer = setTimeout(poll, context !== generation ? 0 : failures ? delay : Math.max(0, delay - (performance.now() - started)));
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
      $("detail-label").textContent = track.label;
      $("detail-badges").replaceChildren(node("span", enumText(domains, track.domain), "badge"), node("span", enumText(affiliations, track.affiliation), `badge ${affClass(track.affiliation)}`), node("span", enumText(classes, track.classification), "badge"));
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
    $("apply-classification").disabled = !enabled || track?.can_classify !== true;
    $("classification").disabled = !enabled || track?.can_classify !== true;
    $("apply-affiliation").disabled = !enabled || !track;
    $("affiliation").disabled = !enabled || !track;
    $("propose").disabled = !enabled || track?.can_propose !== true;
    $("clear-proposal").disabled = !enabled || !snapshot?.proposal;
    for (const id of ["navigation-course", "navigation-speed", "propose-navigation"]) $(id).disabled = !enabled || !navigationLive();
    const message = pending ? { key: pending.uncertain ? "command_uncertain" : "command_pending", status: "pending" } : commandMessage;
    const reason = Object.hasOwn(reasons, message?.reasoncode) ? t(reasons[message.reasoncode]) : message?.reasoncode || t("unavailable");
    $("command-status").textContent = message ? t(message.key, { reason }) : "";
    $("command-status").dataset.status = message?.status || "";
    $("command-reconcile").hidden = !pending?.uncertain;
    $("retry-command").disabled = !pending?.uncertain || pending.inFlight || performance.now() < pending.retryAt ||
      !connected || snapshot?.commands_allowed !== true || !chartMatches(snapshot) || !sameContext(snapshot, pending.body) ||
      (pending.body.action === "propose_navigation" && !navigationLive());
  }

  function renderSnapshot() {
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
    renderDetail();
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

  function drawSymbol(x, y, domain, color, size) {
    ctx.strokeStyle = color; ctx.lineWidth = 1.8; ctx.beginPath();
    if (domain === "SURFACE") ctx.rect(x - size, y - size * .65, size * 2, size * 1.3);
    else if (domain === "AIR") { ctx.arc(x, y + size / 2, size, Math.PI, Math.PI * 2); }
    else if (domain === "SUBSURFACE") { ctx.arc(x, y - size / 2, size, 0, Math.PI); }
    else { ctx.moveTo(x, y - size); ctx.lineTo(x + size, y); ctx.lineTo(x, y + size); ctx.lineTo(x - size, y); ctx.closePath(); }
    ctx.stroke();
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
    $("code").value = "";
    try {
      const result = await request("/pair", { method: "POST", body: { code }, auth: false });
      if (!result || typeof result.token !== "string" || !result.token) throw new Error("pair");
      token = result.token;
      generation += 1;
      failures = 0;
      $("pairing").hidden = true;
      $("disconnect").hidden = false;
      setConnection("syncing");
      clearTimeout(pollTimer);
      poll();
    } catch (_) {
      $("pair-error").textContent = t("pair_failed");
      $("code").focus();
    } finally { $("pair-submit").disabled = false; }
  });
  $("language").addEventListener("change", () => loadLanguage($("language").value === "de" ? "de" : "en"));
  $("analysis-filter").addEventListener("input", renderContactAnalysis);
  $("analysis-category").addEventListener("change", renderContactAnalysis);
  $("disconnect").addEventListener("click", () => { forgetSession(); $("code").focus(); });
  $("classification-form").addEventListener("submit", (event) => { event.preventDefault(); sendCommand("classify", $("classification").value || null); });
  $("affiliation-form").addEventListener("submit", (event) => { event.preventDefault(); sendCommand("affiliate", $("affiliation").value); });
  $("propose").addEventListener("click", () => sendCommand("propose"));
  $("clear-proposal").addEventListener("click", () => sendCommand("clear_proposal"));
  $("navigation-form").addEventListener("submit", (event) => { event.preventDefault(); sendCommand("propose_navigation"); });
  $("retry-command").addEventListener("click", () => {
    if (!pending?.uncertain || pending.inFlight || performance.now() < pending.retryAt) return;
    // Reconciliation never reconstructs an envelope from the current selection.
    transmitCommand(pending);
  });
  for (const name of tabNames) {
    const tab = $(`tab-${name}`);
    tab.addEventListener("click", () => activateTab(name));
    tab.addEventListener("keydown", (event) => {
      let index = tabNames.indexOf(name);
      if (event.key === "ArrowRight") index = (index + 1) % tabNames.length;
      else if (event.key === "ArrowLeft") index = (index - 1 + tabNames.length) % tabNames.length;
      else if (event.key === "Home") index = 0;
      else if (event.key === "End") index = tabNames.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabNames[index]);
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
        await audio?.suspend();
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
  $("zoom-in").addEventListener("click", () => zoom(1.4));
  $("zoom-out").addEventListener("click", () => zoom(1 / 1.4));
  $("fit").addEventListener("click", fitChart);
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
  window.addEventListener("resize", () => { queueDraw(); queueLookoutDraw(); });
  document.addEventListener("visibilitychange", () => {
    // A background tab's event batch is not a new audible alarm on return.
    suppressNextEvents = true;
    if (document.hidden && token) setConnection("stale");
  });
  window.addEventListener("pagehide", () => forgetSession());
  window.addEventListener("offline", () => { if (token) setConnection("stale"); });
  window.addEventListener("online", () => { if (token && !polling) { clearTimeout(pollTimer); poll(); } });
  setInterval(() => {
    if (token && lastSuccess && performance.now() - lastSuccess > 4500) setConnection("stale");
    else if (linkState === "stale") renderConnection();
    if (pending) {
      if (!pending.inFlight && performance.now() >= pending.retryAt) pending.uncertain = true;
      renderActionState();
    }
  }, 1000);

  async function bootstrap() {
    let delay = 1000;
    while (!await loadLanguage(language)) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      delay = Math.min(8000, delay * 2);
    }
    loadContactAnalysis();
  }
  bootstrap();
})();
