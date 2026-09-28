# Coding Agent Guide

## Authority and scope

- This is U-Jagd 1.3.39 (`src/core/version.py`); current saves are v27-only. Treat these as compatibility contracts, not changelog entries.
- Resolve conflicts in this order: executable code and focused tests; packaged JSON/runtime resources; `pyproject.toml` and provenance/license notices; `README.md`; design/history documents under `docs/`. A plan or old comment is not an implementation contract.
- Preserve explicit compatibility tests and user data unless a task intentionally changes the contract. Add a regression test for behavior changes.
- Older phase/milestone labels under `docs/GDD.md`, `docs/implementation-plan.md`, `docs/plan-0.1.6.md`, and `docs/plan-0.1.7.md` are historical. Current resumable work is tracked in `docs/plan-1.3.md` and `docs/resume.md`.

## Architecture

- `main.py`: CLI and saved-preference/CLI override wiring.
- `src/core/game.py`: composition root only; `Game` is assembled from mixins with one responsibility each: `game_events.py` (event precedence and input ownership), `game_sim.py` (`update`/`_update_sim` and the frozen `SIM_ORDER`), `game_operator.py` (station commands shared by keys and Remote Crew), `game_pictures.py` (OPZ/ELOKA pictures, plot layer, weather, SimLog), `game_draw.py` (frame, overlays, main loop), `mission_bridge.py` (scenario start and the custom-mission runtime bridge), `game_tasking.py` (HQ radio tasks, model in `tasking.py`), `game_crew.py` (watches, fatigue, morale; model in `crew.py`), `game_mpa.py` (the on-call patrol aircraft, flight model in `src/air/mpa.py`), `game_save.py` (save/load, slots) with `save_validate.py` (pure document validator) and `limits.py` (shared bounds); `game_shared.py` holds help/display constants. Move code between them verbatim; `Game` re-exports the names tests import from `src.core.game`.
- `src/core/config.py`: gameplay constants, units/conversions, scenarios, layout, and timing.
- `src/core/mission*.py`, `commands.py`, `station.py`, `preferences.py`, `i18n.py`: mission models, shared commands, UI state, settings, and localization.
- `src/world/`: coastline/bathymetry, real-sector loading, projection, terrain queries, weather/time.
- `src/sonar/` and `src/sensors/`: measurements, receiver/TMA, and persistent observation tracks.
- `src/ship/`, `src/enemies/`, `src/air/`, `src/weapons/`: simulation entities and mechanics.
- Crewed submarine: `src/core/opfor.py` (crew orders, sightings, periscope, stadimeter, wires), `src/core/boat_radio.py` (radio room), `src/core/uboot_local.py` (uConsole keys of the boat side), `src/ui/uboot_view.py` and `src/ui/uboot_scope.py` (boat stations and the periscope page).
- `src/ui/`: rendering, hit testing, viewport, tooltips, and editors. Station views live in `src/ui/stations/` (one module per station, `common.py` shared); `src/ui/stations_view.py` is the facade with the station-wide hit test and re-exports. Views should consume game-facing observations, not discover hidden entity state.
- `src/audio/`: bounded NumPy synthesis/analysis and non-blocking Pygame playback.
- `src/data/`: packaged catalog loading, validation, fingerprints, and secure user-content persistence. `data/` contains package resources; `tests/` is the behavioral contract; `tools/` contains validators/reproducible generators.

## Simulation invariants

- World position/range is nautical miles, speed is knots, simulation duration is seconds, depth is metres, frequency is Hz, and headings/bearings are nautical degrees: 0 north, clockwise; movement uses `x += sin(course)`, `y -= cos(course)`.
- At 1x, one real second is one simulation second. Convert knots with `kn / 3600`; do not add hidden tactical compression. `GAME_TIME_PER_SEC` advances the 24-hour clock separately.
- The game always runs in real time: there is no time acceleration and no pause. Menus and overlays opened over a mission (help/manual, options, save/load, quit confirmation, nations, F8 analyzer, F9 administration, live traffic) and focus loss own input only and never stop the simulation. `Game.update()` subdivides each frame to at most `PHYS_SUBSTEP_S` subject to `PHYS_SUBSTEP_MAX`; the main loop (`Game._frame_dt`) never advances a frame by more than `SIM_FRAME_DT_MAX` (0.1 s) but catches up slow frames from a bounded debt (`SIM_CATCHUP_MAX_S`, 2.5 s), and never after the main menu, load or reset, so sim time (and the sonar audio produced in it) keeps pace with wall-clock playback. Preserve swept collision behavior and the update ordering in `_update_sim()` (`SIM_ORDER` in `src/core/game_sim.py`, frozen by `tests/test_sim_order.py`). `tests/test_module_size.py` keeps every source module under 2500 lines.
- Only states without a running mission (splash, main menu and its editors, game over) do not advance simulation. Cosmetic/UI timers and audio cadence use wall time where the code says so.
- Same seed, world mode, and input/update sequence must produce the same state. Use explicit local `random.Random` streams, stable hashes, stable iteration/order, and saved RNG states. Never introduce simulation dependence on global randomness, hash randomization, rendering frequency, audio availability, or wall clock.
- Save/load must preserve deterministic continuation, entity ID progression, generated coastline/bathymetry snapshots, pending sensor/projectile state, and operator focus. When adding random draws, consider stream/order compatibility and update determinism and round-trip tests.
- New random draws should use the stateless counter-based `src/core/detrand.py` (`u01`/`normal` keyed by seed, tag, entity and tick) so they need no saved stream and never shift existing `random.Random` sequences.
- Physics lives in pure modules (`src/physics/`, `src/sonar/equation.py`/`raytrace.py`, `src/sensors/radar.py`/`visual.py`/`hfdf.py`, `src/weapons/ciws.py`) anchored so the 1.0.0 behaviour appears at its reference point. `python tools/calibrate.py --check` compares 77 gameplay metrics with `tests/calibration/golden.json` (recorded on 1.0.0); intentional deviations go in `tests/calibration/deviations.json` with a reason. Caches in these paths must be pure and bounded (results may never depend on call order).

## Input ownership and precedence

- Keep `Game.handle_event()` single-owner semantics: splash, editor, pinned-tooltip escape, administrative overlay, menu, numeric entry, then live global/station controls. `Alt+Enter` is intercepted before contextual confirmation; key-repeat `KEYDOWN` is ignored.
- Only one administrative overlay owns input, clears held/joystick/drag/audio state, and blocks background devices; the simulation keeps running behind it. Focus loss clears controls only.
- `Esc` first clears a pinned tooltip, then cancels the active owner, then opens quit confirmation. Numeric entry is intentionally live while simulation runs, but held controls are cleared and invalid input remains editable.
- Station keys are contextual and must not leak across stations. Clear held controls on station/administration transitions. Trackball axes are station-specific; steering is Bridge-only. Map zoom/pan/follow only operate where a map is visible.
- Transform display coordinates through `_window_to_canvas()` and reject letterbox space before hit testing. Keep draw and hit-test geometry aligned.

## Observation boundary

- The player has no general ground-truth access. Sonar exposes noisy bearing-only contacts unless a current ping/TMA/fused observation supplies range/depth/course; stale fixes decay or disappear. Radar, AIS, ESM, HFDF, and radio publish `SensorTrack` observations with age/quality.
- Workstations, targeting, weapon guidance, tooltips, and logs must use contacts/tracks/datalink data, not live enemy `x`, `y`, `depth`, class, hostility, or object references. Do not put simulation objects into serialized/public tracks.
- Legitimate truth is limited to own ship and commanded own assets, known geography/synthetic chart depth, authored/static preview data, and explicitly modeled friendly datalink truth. Physics, AI, collision, sensor generation, and terminal weapon seekers may use underlying entities internally.
- Manual classification and NATO affiliation are operator annotations, not inferred truth. A sensor domain comes from the observation. Weapons require the modeled track/fix freshness and engagement envelope; pre-terminal torpedo guidance uses the commanded datum, not a hidden target.

## Data and localization

- `data/contacts/*.json` is the single source of truth for built-in platform/acoustic/torpedo/decoy profile values. Load through `src/data/catalog.py`; do not duplicate JSON-owned values in Python. `tools/gen_contacts.py` is a strict validator despite its historical name; it never generates files.
- `data/editor_templates/*.json` supplies editor templates, while Python validators define acceptance and runtime code defines effectiveness. Validation success does not imply runtime support.
- All new user-visible prose needs matching keys in `data/i18n/en.json` and `de.json`. English is the reference/fallback; catalogs require exact key parity and identical named placeholders. Use named placeholders only.
- Route rendering through `Translator`, `localize`, `translation_scope`, and bounded layout helpers. Do not add direct `Font.render` prose; the test allowlist is technical labels only. Verify English, German, large text where relevant, and the pseudolocale/layout tests.

## Player documentation

- `src/core/help.py` is the single source for key bindings (`STATION_HELP`, `_GLOBAL_HELP`, `_WEB_HELP`) and per-station standard procedures (`STATION_SOP`, `help.sop.*` keys). The F1 overlay, the in-game manual reader (F1 category 4), the Remote Crew `/manual-en|de` pages, and `docs/manual/` all render from it.
- Manual prose lives in `data/manual/<nn>-<chapter>.{en,de}.md` (small Markdown subset parsed by `src/core/manual.py`; every heading needs an explicit `{#anchor}`; key tables and procedures only via `<!-- keys:… -->` / `<!-- sop:… -->` markers). EN and DE must keep identical block structure, anchors, and markers.
- Every change to controls, stations, mechanics, or documented numbers updates `help.py`, both manual languages, and the catalogs in the same change, then runs `python tools/build_manual.py` (CI: `--check`) and `pytest tests/test_manual.py`. Document only implemented behavior; list gaps under "Not modelled".

## Persistence and user content

- Runtime root is `~/.u-jagd/`: `settings.json`; `slot1.json` through `slot5.json`; editor files in `missions/` and `units/`. Tests replace save paths with temporary directories; never write real user paths from tests. `.u-jagd/`, build products, caches, and egg metadata stay untracked.
- Preferences persist language/fullscreen/audio/large text/tooltips in `settings.json`; v27 saves also retain the mission's tooltip state and the uConsole's local side. CLI `--windowed` and `--no-audio` override saved values for one launch; no inverse fullscreen or CLI-language switch exists.
- Write and load save v27 only. Require the exact `u-jagd-save-v27` schema (exact key sets live in `src/core/save_schema.py`) and the complete current catalog, platform, ESM, ASW, AIS, RNG and crewed-boat crew state (`crew` block: orders with the attack computer's stadimeter marks `tdc` and each tube's flooding state `tubes`, wires, plot, ESM picture with each emitter's last main-beam hit `last_peak`, radio room, feed, sonar station; a loaded boat keeps its binding for `UBOOT_RESTORE_HOLD_S` until its crew returns), plus foreign active pings still travelling to the frigate (`ping_intercepts`) and each conventional boat's diesel, charge rate and air stores (endurance state version 2) and every submarine's ballast, trim and high-pressure air (`ballast`) and its compartments, leaks, fires, gas and damage-control teams (`damage_control`), plus the HQ task board (`tasking`), the frigate's watch bill (`watch`; the boat's is `crew.watch`), the patrol aircraft (`mpa`) and each buoy's `owner`, plus the frigate's variable-depth sonar (`vds_state`, payout, depth and target), plus the frigate's radar mast blips and the OPZ's marks the AI hunters act on (`radar_marks`). Reject malformed, non-integer, older, newer, incomplete, or unknown schemas without migration.
- Writes must stage beside the destination, flush and `fsync`, then atomically `os.replace`; failure leaves the prior file intact and save-and-quit quits only after success. Load into a candidate state and commit only after complete validation/restoration; failure must leave the live game and global ID counters unchanged.
- Treat imported/editor JSON as hostile. Require finite typed/bounded values, strict schemas, `user.<lowercase/digit/_/->` keys, confined destinations, and no symlinked root/file. Never interpret a logical reference as a filesystem path.
- Bundle import validates every item and collision before the first visible write, stages all files, rechecks confinement/symlinks, and rolls back the whole commit on failure. Preserve backups if rollback itself fails. JSON output must reject NaN/Infinity.

## Remote Crew multiplayer

- Remote Crew is authoritative-host multiplayer for multiple authenticated browser clients. The uConsole process remains the sole simulation authority. Browsers never run simulation, advance time, resolve physics, read live entities, or mutate game state from transport threads.
- Multiplayer protocol versions are independent of application and save versions. Remote Crew is protocol v2-only; every `/api/v1/*` route is retired and returns 404. Saves remain exact v27; credentials, clients, station leases, network queues, drafts, and unaccepted commands are transient and never enter saves or settings.
- Support a hard-bounded client count. Each client has an independent cryptographic session, expiry, request namespace, and revocation state. The host explicitly grants one exclusive station role per client and can revoke or take over any role. Reconnect never inherits another client's authority.
- Role capabilities are allowlisted. A granted browser may directly operate its station, including weapons when the host separately enables direct fire, but every action must pass the same observation freshness, damage, inventory, ROE, envelope, and readiness checks as local input. Save/load, reset, editors, options, quit, network administration, and credentials remain host-only, with one explicit exception: solo mode (below).
- The transport is `src/commander/server.py` (`CommanderServer`: sessions, leases, publications) with `src/commander/v2/` (`wire.py` constants and framing, `commands.py` the closed action registry and validators, `routes.py` HTTP and WebSocket handlers); `server.py` re-exports the v2 names. `/ws/v2/state` pushes the active role's projection (the same bytes as `GET /api/v2/state`, at most 4 Hz, heartbeat 2 s, latest state only) and the browser falls back to polling; both paths share one allowlist: `src/commander/v2/schema.py` is rendered into the generated block of `data/commander/js/state/schema.js` by `tools/gen_web_schema.py` (`--check` in CI). Transport handlers accept only strict, finite, size-bounded, versioned messages and enqueue detached envelopes. The main thread revalidates client, role, lease generation, world epoch, resource revision, freshness, and readiness immediately before applying each command. Never synthesize Pygame events or dispatch arbitrary method names from network data.
- Apply accepted remote commands exactly once in deterministic station order and per-client FIFO order before `Game.update()`. Wall clock, packet scheduling, polling frequency, browser rendering, and hash iteration must not affect simulation results. Role loss, disconnect, load/new game, and world replacement reject unsafe queued commands and clear held remote controls; local overlays and focus loss do not.
- Each normal role view receives only an allowlisted detached projection of own ship and commanded assets, published observations, annotations, and known geography. Never export simulation objects, hidden IDs, undiscovered positions, true hostile identity, RNG state, or save dumps through station state. The explicit host-granted SimLog capability is the sole diagnostic exception: its read-only history may include detached full-truth snapshots, but never simulation objects, RNG state, credentials, settings, or save dumps.
- Observers are a host-granted, never-persisted read-only pseudo-role (at most `OBSERVER_MAX` = 2): no lease, any station viewable through `stations/activate` with generation 0, every command rejected, SimLog included; occupancy and `station_leased()` ignore observers. Voice starts enabled in the web-host room and the host switches it off.
- Solo mode is a per-launch, never-persisted host decision (`--solo-crew` or the F9 "Crew mode" row; changing it revokes every session and rotates the code). One paired session then holds all nine stations and may use the closed host command surface: save/load slots 1-5, new game and the instructor environment, sent as pseudo-role `host` over the normal command pipeline (same CSRF/Origin, exactly-once, phase and world-session checks; rejected in crew mode). There is no pause or time-scale command. Editors, options, quit, network administration and credentials stay host-only, saves stay exact v27, and a world replacement keeps the solo session but re-leases every station and drops queued commands. The browser runs on a desktop PC, so the web UI targets large screens; `data/commander/` keeps the accessible single-column fallback for narrow windows only.
- Browser sessions may use host-only HttpOnly SameSite cookies for reload recovery. Credentials never enter JavaScript, URLs, DOM, logs, settings, or saves. State-changing requests also require exact Origin and a separate CSRF token. Plain HTTP remains trusted-LAN-only; Internet-capable deployment requires a separately reviewed encrypted endpoint or reverse proxy. The local F9 listener accepts only its exact LAN `Host`/`http://` origin unless launched with `--public-origin https://…`; then it also accepts exactly that proxy host (plus explicit `:443`) and origin, and marks cookies `Secure` only on the HTTPS path. The `--web-host` room accepts its public origin only.
- Keep clients, histories, queues, projections, polling, and render work bounded for the uConsole. Cache immutable projections shared by clients with identical visibility, apply backpressure, and verify maximum-client CPU, memory, bandwidth, frame time, reconnect, and thermal behavior on real hardware.
- New multiplayer prose uses exact EN/DE catalog parity and safe DOM insertion. Browser controls require keyboard and touch access, bounded responsive layouts, explicit stale/revoked states, and tests at desktop, mobile, large zoom, and pseudolocale where applicable.

## Coastline provenance

- `data/coastlines/region.json` is the hand-maintained stylized legacy map. `data/coastlines/real_sectors.json.gz` is a generated runtime artifact: exactly 128 distinct, validated 500 NM sectors selected by `seed % 128`.
- Never hand-edit, casually recompress, or replace the generated catalog. `tools/build_coastline_sectors.py` is offline and deterministic (sorted JSON, gzip `mtime=0`) and accepts only the pinned Natural Earth and Wikidata snapshots with exact SHA-256 values embedded in the tool.
- The source snapshots are not runtime assets. Regenerate only from rights-cleared pinned inputs, then verify embedded provenance, `THIRD_PARTY_NOTICES.md`, loader/integrity tests, package inclusion, deterministic seed mapping, and geographic disclaimers together. Gameplay roles and synthetic bathymetry are not claims about real states or real seabed.
- New third-party assets require source, author, license, modification terms, attribution, and redistribution rights documented before release.

## Current intentional limits

- Editor authoring/validation is broader than runtime. Unit-editor profiles currently have no simulation effect.
- A user mission starts only via `F5` from the Mission Editor browser and only with a 500 NM world: `fixed` (the game's current world mode) or `reference` naming a packaged real sector as `sector:<0..127>` (`Coastline.generate(sector_index=...)`). For `sink`, targets must exactly equal all placed hostile submarines; `protect` targets are placed friendly/neutral units; `reach` needs `objective.reach` (x, y, radius_nm).
- Runtime-effective mission fields are seed/name/description, player pose/speed, sea state/start time/thermocline/weather (an authored weather kind is held as `world.weather_override`, saved), exact units of every built-in kind except torpedoes (submarines, surface ships, aircraft at profile speed from the nearest charted airbase, animals, static decoys) with placement/course/speed/depth, seeded random groups (`MISSION_GROUP_SPEED_KN`/`_DEPTH_M`, a spawn event defers its group), events in time order (message verbatim, spawn, weather, objective; pending ids are the save root field `mission_events`), and objective/time limit. Placed units are remembered as `mission_runtime.units` (mission id → entity id). Other world sizes, torpedoes and user unit profiles are rejected, never silently ignored. Mission world definitions do not replace the packaged coastline dataset.
- Audio is optional and synthesized at runtime; no device, disabled audio, or an incompatible shared mixer must degrade to silence without changing simulation. There are currently no external image/font/audio assets.

## uConsole and performance

- The canonical virtual canvas is 1280x720. The frame-rate cap is the `frame_rate` preference (30 or 60 FPS, default 30 to save uConsole CPU); `config.FPS` = 60 stays the reference maximum. Preserve semantic station layout and bounded text/tooltips at that size. Other windows use aspect-correct letterboxing (`FILL_SCREEN=False`); do not distort tactical geometry.
- The uConsole is a low-power target. Keep render paths free of disk I/O and hidden simulation mutation; cache metadata/surfaces, cull by bounds before point transforms, bound histories/queues/caches, and use NumPy/vectorized processing for signal/waterfall work. Avoid per-frame synthesis and expensive full-world scans.
- Audio updates at 0.25 s cadence. Engine and sonar streams generate short continuous blocks and retain at most the current plus one queued block. Buffered sonar playback (local mixer worker and browser AudioWorklet) is elastic: it steers its queue by resampling at most 2 % faster/slower, conceals underruns with non-periodic granular audio and refills before resuming; never reintroduce plain block repetition. Retuning the listening bearing continues the stream (sequence gap), it does not hard-stop it. Preserve their phase/filter state, independent reserved channels, bounded queues, and an already initialized compatible shared mixer.
- Headless CI is not hardware acceptance. Changes affecting frame time, display scaling, controls, mixer behavior, or readability still need testing on the real 1280x720 uConsole target when available.

## Build and verification

Use Python 3.11+ from the repository root:

```sh
python -m pip install -e '.[dev]'
pytest
python tools/gen_contacts.py --check
python tools/build_manual.py --check
python tools/gen_web_schema.py --check
python tools/calibrate.py --check
python tools/smoke_full.py
python -m build
```

- `pytest` configures SDL dummy video/audio and isolates saves. Run focused tests while iterating, then the full suite for cross-system changes.
- `python -m build` requires the `build` extra/package and produces both sdist and wheel. Packaging tests build/install artifacts and verify package resources.
- Release notes: `README.md`/`README.de.md` describe only the current release (one paragraph each); every release adds its entry at the top of `CHANGELOG.md` and `CHANGELOG.de.md` (`## x.y.z`), which also becomes the GitHub release text (`tools/changelog_notes.py`, `--check` in `tests/test_changelog.py`). After visible changes regenerate the README screenshots with `python tools/capture_screenshots.py` and `python tools/capture_commander.py` (Chromium on `PATH`).
- For releases, verify `src/core/version.py`, save compatibility, README release statement, changelog entries, package metadata, wheel/sdist resources, notices/licenses, full tests, catalog check, smoke test, and a clean install. Do not include caches, local saves/settings, build trees, source snapshots, private references, or unlicensed assets.
- Keep commits narrowly scoped; inspect status/diff before staging, never overwrite unrelated work, never commit secrets or local user data, and do not rewrite history or force-push without explicit approval. Generated artifacts must be reproducible and accompanied by their provenance updates.
