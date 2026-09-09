# Coding Agent Guide

## Authority and scope

- This is U-Jagd 0.1.7 (`src/core/version.py`); current saves are v10-only. Treat these as compatibility contracts, not changelog entries.
- Resolve conflicts in this order: executable code and focused tests; packaged JSON/runtime resources; `pyproject.toml` and provenance/license notices; `README.md`; design/history documents under `docs/`. A plan or old comment is not an implementation contract.
- Preserve explicit compatibility tests and user data unless a task intentionally changes the contract. Add a regression test for behavior changes.
- Older phase/milestone labels under `docs/GDD.md` and `docs/implementation-plan.md` are historical. Current resumable work is tracked in `docs/plan-0.1.6.md`, `docs/plan-0.1.7.md`, and `docs/resume.md`.

## Architecture

- `main.py`: CLI and saved-preference/CLI override wiring.
- `src/core/game.py`: composition root, event precedence, main loop, simulation orchestration, custom-mission runtime bridge, and save/load.
- `src/core/config.py`: gameplay constants, units/conversions, scenarios, layout, and timing.
- `src/core/mission*.py`, `commands.py`, `station.py`, `preferences.py`, `i18n.py`: mission models, shared commands, UI state, settings, and localization.
- `src/world/`: coastline/bathymetry, real-sector loading, projection, terrain queries, weather/time.
- `src/sonar/` and `src/sensors/`: measurements, receiver/TMA, and persistent observation tracks.
- `src/ship/`, `src/enemies/`, `src/air/`, `src/weapons/`: simulation entities and mechanics.
- `src/ui/`: rendering, hit testing, viewport, tooltips, and editors. Views should consume game-facing observations, not discover hidden entity state.
- `src/audio/`: bounded NumPy synthesis/analysis and non-blocking Pygame playback.
- `src/data/`: packaged catalog loading, validation, fingerprints, and secure user-content persistence. `data/` contains package resources; `tests/` is the behavioral contract; `tools/` contains validators/reproducible generators.

## Simulation invariants

- World position/range is nautical miles, speed is knots, simulation duration is seconds, depth is metres, frequency is Hz, and headings/bearings are nautical degrees: 0 north, clockwise; movement uses `x += sin(course)`, `y -= cos(course)`.
- At 1x, one real second is one simulation second. Convert knots with `kn / 3600`; do not add hidden tactical compression. `GAME_TIME_PER_SEC` advances the 24-hour clock separately.
- Time acceleration multiplies simulation time exactly once. `Game.update()` subdivides accelerated time to at most `PHYS_SUBSTEP_S` subject to `PHYS_SUBSTEP_MAX`; the main loop clamps wall-frame `dt` to 0.1 s. Preserve swept collision behavior and the update ordering in `_update_sim()`.
- Paused, menu, game-over, splash, editor, and administrative states must not accidentally advance simulation. Cosmetic/UI timers and audio cadence use wall time where the code says so.
- Same seed, world mode, and input/update sequence must produce the same state. Use explicit local `random.Random` streams, stable hashes, stable iteration/order, and saved RNG states. Never introduce simulation dependence on global randomness, hash randomization, rendering frequency, audio availability, or wall clock.
- Save/load must preserve deterministic continuation, entity ID progression, generated coastline/bathymetry snapshots, pending sensor/projectile state, and operator focus. When adding random draws, consider stream/order compatibility and update determinism and round-trip tests.

## Input ownership and precedence

- Keep `Game.handle_event()` single-owner semantics: splash, editor, pinned-tooltip escape, administrative overlay, menu, numeric entry, then live global/station controls. `Alt+Enter` is intercepted before contextual confirmation; key-repeat `KEYDOWN` is ignored.
- Only one administrative overlay owns input, clears held/joystick/drag/audio state, and blocks background devices and simulation. Focus loss clears controls and pauses; focus gain never auto-resumes.
- `Esc` first clears a pinned tooltip, then cancels the active owner, then opens quit confirmation. Numeric entry is intentionally live while simulation runs, but held controls are cleared and invalid input remains editable.
- Station keys are contextual and must not leak across stations. Clear held controls on station/pause/administration transitions. Trackball axes are station-specific; steering is Bridge-only. Map zoom/pan/follow only operate where a map is visible.
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

## Persistence and user content

- Runtime root is `~/.u-jagd/`: `settings.json`; `slot1.json` through `slot5.json`; editor files in `missions/` and `units/`. Tests replace save paths with temporary directories; never write real user paths from tests. `.u-jagd/`, build products, caches, and egg metadata stay untracked.
- Preferences persist language/fullscreen/audio/large text/tooltips in `settings.json`; v10 saves also retain the mission's tooltip state. CLI `--windowed` and `--no-audio` override saved values for one launch; no inverse fullscreen or CLI-language switch exists.
- Write and load save v10 only. Require the exact `u-jagd-save-v10` schema and the complete current catalog, platform, ESM, ASW, and RNG state. Reject malformed, non-integer, older, newer, incomplete, or unknown schemas without migration.
- Writes must stage beside the destination, flush and `fsync`, then atomically `os.replace`; failure leaves the prior file intact and save-and-quit quits only after success. Load into a candidate state and commit only after complete validation/restoration; failure must leave the live game and global ID counters unchanged.
- Treat imported/editor JSON as hostile. Require finite typed/bounded values, strict schemas, `user.<lowercase/digit/_/->` keys, confined destinations, and no symlinked root/file. Never interpret a logical reference as a filesystem path.
- Bundle import validates every item and collision before the first visible write, stages all files, rechecks confinement/symlinks, and rolls back the whole commit on failure. Preserve backups if rollback itself fails. JSON output must reject NaN/Infinity.

## Commander LAN

- Commander service is opt-in, off on every launch. `F10` Options or `F9` opens local administration. Bind only an explicitly selected loopback/private IPv4; HTTP is trusted-LAN-only, not Internet hosting.
- `src/commander/server.py` must never reference Game/Pygame. It serves cached bytes and bounded request queues. `CommanderBridge.pump()` executes once per main-loop wall frame, not on HTTP threads or physics substeps.
- Export only allowlisted observations and own-ship information, never a save/entity dump, seed, RNG, hidden platform identity or raw internal ID. Menu/editor/splash publish status-only data. Browser inspection never changes crew selection or sonar focus.
- Classification/affiliation require pairing AND local grant. Target and navigation proposals require explicit crew acceptance and fresh main-thread revalidation. An accepted navigation proposal changes local helm setpoints; direct remote steering, firing, sensor operation, ROE, time, saves and editor controls are forbidden.
- Pairing codes are three digits followed by three uppercase letters, valid five minutes, five failed attempts per rolling minute globally. Long bearer tokens remain independent. Never store or log codes/tokens; credentials, connections and pending proposals are not save fields.
- Successful world replacement revokes pairing/grant on the next main-thread pump; failed candidate restoration must have no server/bridge side effects. Queue epochs invalidate stale actions across input-owner changes.
- Bound connections, bodies, queues, chart geometry, events and retries. Exact Host/Origin validation and fixed static routes are required. Browser strings use root EN/DE catalogs and textContent, with no CDN or arbitrary HTML.
- Authorized post-Commander work, including sonar/fidelity packages B-F, is tracked in `docs/plan-0.1.7.md`. Execute its dependency order, stop after its final acceptance milestone, and record the pause in `docs/resume.md`.

## Coastline provenance

- `data/coastlines/region.json` is the hand-maintained stylized legacy map. `data/coastlines/real_sectors.json.gz` is a generated runtime artifact: exactly 128 distinct, validated 500 NM sectors selected by `seed % 128`.
- Never hand-edit, casually recompress, or replace the generated catalog. `tools/build_coastline_sectors.py` is offline and deterministic (sorted JSON, gzip `mtime=0`) and accepts only the pinned Natural Earth and Wikidata snapshots with exact SHA-256 values embedded in the tool.
- The source snapshots are not runtime assets. Regenerate only from rights-cleared pinned inputs, then verify embedded provenance, `THIRD_PARTY_NOTICES.md`, loader/integrity tests, package inclusion, deterministic seed mapping, and geographic disclaimers together. Gameplay roles and synthetic bathymetry are not claims about real states or real seabed.
- Private WaveOps PDFs are non-distributable inspiration only. Do not add, quote, transcribe, imitate, or derive text, images, layouts, or data from them. New third-party assets require source, author, license, modification terms, attribution, and redistribution rights documented before release.

## Current intentional limits

- Editor authoring/validation is broader than runtime. Unit-editor profiles currently have no simulation effect.
- A user mission starts only via `F5` from the Mission Editor browser and only if it uses a 500 NM `fixed` world, clear weather, no events or random groups, exact built-in submarine/surface profiles, hostile submarines, and a `sink` or `survive` objective. For `sink`, targets must exactly equal all placed submarines.
- Runtime-effective mission fields are seed/name, player pose/speed, sea state/start time/thermocline, exact-unit placement (fixed coordinates or authored sectors)/course/speed/sub depth, and objective/time limit. Reference worlds, alternate sizes, protect/reach, aircraft, animals, torpedoes, decoys, random groups, events, and user unit profiles are rejected, never silently ignored. Mission world definitions do not replace the packaged coastline dataset.
- Audio is optional and synthesized at runtime; no device, disabled audio, or an incompatible shared mixer must degrade to silence without changing simulation. There are currently no external image/font/audio assets.

## uConsole and performance

- The canonical virtual canvas is 1280x720 at 60 FPS. Preserve semantic station layout and bounded text/tooltips at that size. Other windows use aspect-correct letterboxing (`FILL_SCREEN=False`); do not distort tactical geometry.
- The uConsole is a low-power target. Keep render paths free of disk I/O and hidden simulation mutation; cache metadata/surfaces, cull by bounds before point transforms, bound histories/queues/caches, and use NumPy/vectorized processing for signal/waterfall work. Avoid per-frame synthesis and expensive full-world scans.
- Audio updates at 0.25 s cadence. Engine and sonar streams generate short continuous blocks and retain at most the current plus one queued block. Preserve their phase/filter state, independent reserved channels, bounded queues, and an already initialized compatible shared mixer.
- Headless CI is not hardware acceptance. Changes affecting frame time, display scaling, controls, mixer behavior, or readability still need testing on the real 1280x720 uConsole target when available.

## Build and verification

Use Python 3.11+ from the repository root:

```sh
python -m pip install -e '.[dev]'
pytest
python tools/gen_contacts.py --check
python tools/smoke_full.py
python -m build
```

- `pytest` configures SDL dummy video/audio and isolates saves. Run focused tests while iterating, then the full suite for cross-system changes.
- `python -m build` requires the `build` extra/package and produces both sdist and wheel. Packaging tests build/install artifacts and verify package resources.
- For releases, verify `src/core/version.py`, save compatibility, README release statements, package metadata, wheel/sdist resources, notices/licenses, full tests, catalog check, smoke test, and a clean install. Do not include caches, local saves/settings, build trees, source snapshots, private references, or unlicensed assets.
- Keep commits narrowly scoped; inspect status/diff before staging, never overwrite unrelated work, never commit secrets or local user data, and do not rewrite history or force-push without explicit approval. Generated artifacts must be reproducible and accompanied by their provenance updates.
