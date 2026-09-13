# Implementation Plan 0.1.8 - Remote Crew Multiplayer

## Status and authority

This is the resumable plan after 0.1.7. The 0.1.6 and 0.1.7 plans remain
historical acceptance records. Current state and the next small step belong in
`docs/resume.md`.

Application, multiplayer protocol, and save versions are independent. This
plan preserves exact save v10 and introduces Remote Crew protocol v2 without
silently broadening Commander protocol v1.

Product decisions are fixed as follows:

- The uConsole is the authoritative host and may play alongside multiple
  browser clients.
- At most 12 authenticated browser sessions exist at once.
- Each browser may hold one exclusive station role; the host may revoke or
  take over every role.
- Direct station operation is role-gated. Direct weapon release additionally
  requires an explicit host direct-fire grant.
- Reload recovery uses an opaque host-only HttpOnly SameSite session cookie
  and a separate CSRF token.
- Save/load, reset, editors, options, quit, credentials, listener setup, and
  multiplayer administration remain host-only.
- [x] Keep the F9 host screen focused on service, bind address, port, a large
  grouped join code, and the crew roster. Proposal decisions remain in the
  local confirmation overlay rather than duplicate menu rows.
- [x] Keep one transient join code for the lifetime of a Commander server/game
  object. Pairing, reads, client logout/revoke, role changes, and service
  stop/start preserve it; the fifth failed attempt and the existing deliberate
  world-replacement/new-session revoke rotate it. The code is never saved.

## Non-negotiable contracts

- Simulation and physics run only in the uConsole process and main thread.
- Network input is never converted to Pygame events or arbitrary method calls.
- Strict action schemas, finite bounds, short freshness limits, and exact
  role/capability allowlists apply at transport and main-thread execution.
- Same accepted command order and update sequence must produce the same state.
- Browser projections obey the observation boundary for the assigned role.
- Credentials, clients, leases, queues, drafts, and unaccepted commands are
  never persisted in settings or save v10.
- All clients, queues, histories, messages, assets, and projection work are
  hard-bounded for the uConsole.
- Plain HTTP is trusted-LAN-only. Internet deployment requires a separately
  reviewed encrypted endpoint or reverse proxy.

## M0 - Baseline and boundary closure

- Freeze Commander protocol v1 behavior as compatibility coverage during the
  v2 rollout.
- Add save-v10 continuation fixtures with networking disabled.
- Make network SimLog role-safe. Full-truth diagnostics remain host-local;
  remote views receive only own assets and published observations.
- Record current frame-time, memory, publication, and bandwidth baselines.

Acceptance: save-v10 round-trip and continuation, protocol-v1 baseline,
negative hidden-truth tests, catalog validation, smoke test, and full suite.

## M1 - Protocol-v2 sessions

- Add up to 12 independent cryptographic sessions.
- Add `/api/v2/pair`, `/api/v2/session`, `/api/v2/logout`, `/api/v2/state`,
  `/api/v2/chart`, and a role-safe `/api/v2/simlog`.
- Store only a SHA-256 digest of each cookie token server-side.
- Use a host-only `HttpOnly; SameSite=Strict; Path=/api/v2` session cookie.
- Require exact Origin and a separate per-session CSRF token for mutations.
- Use an eight-hour session idle limit and clear expired/revoked cookies.
- Keep protocol v1 and v2 command authority mutually exclusive during rollout.

Acceptance: multiple pairings, reload recovery, independent logout/revoke,
cookie ambiguity rejection, CSRF/origin tests, client limit, expiry, and no
credential exposure in JavaScript, URLs, DOM, logs, settings, or saves.

## M2 - Lobby and station leases

- Add the canonical roles Bridge, Sonar, Weapons, Damage, OPZ, Radio, Engine,
  Helicopter, and ELOKA.
- Let clients request one role; only the local host may grant it.
- Enforce one browser holder per station with monotonic lease generations.
- New assignments start with command, direct-fire, and SimLog grants disabled.
- [x] Add local roster, approve/reject, capability toggles, station/client revoke,
  takeover, and revoke-all controls.
- Release a silent client's station after 15 seconds while retaining its
  authenticated session for reconnect.

Acceptance: contention, deterministic roster order, atomic takeover, lease
expiry, grant reset, reconnect, world replacement, and host override tests.

Status: the local host administration item is implemented and covered by its
focused input, persistence, localization, and layout tests. Full M2 acceptance
has not yet been verified as a combined milestone run.

## M3 - Role-scoped projections

- [x] Build detached projection functions independent of transport and rendering.
- [x] Publish own ship and commanded assets, known geography, and only the sensor
  observations permitted for the assigned role.
- [x] Keep opaque observation references and separate measurement/fix age,
  uncertainty, quality, and operator annotations.
- [x] Cache immutable projections shared by clients with identical visibility.
- [x] Keep menu, editor, splash, and world replacement safely redacted.

Acceptance: exact projection tests and hidden-truth traps for every role,
object detachment, bounded payloads, stable ordering, and polling-independent
simulation state.

Status: M3 software acceptance is implemented and covered by exact per-role,
hidden-truth, freshness, detachment, ordering, payload-bound, deterministic
polling, browser-validation, and lease-selection tests. Real uConsole frame
time, memory, bandwidth, readability, and sustained multi-client thermal tests
remain physical acceptance work; headless CI does not close those risks.

Observation follow-up: OPZ now receives explicitly released, classified ELOKA
bearing reports and independent Bridge LOOKOUT fixes. ESM release is the valid
operator emitter annotation itself; visual detection uses bounded day/night,
sea-state, range, surfaced-depth and land-occlusion gates. Both use detached,
separately opaque observation identities and remain exact save-v10 state.

## M4 - Deterministic command gateway

- [x] Use per-client FIFO queues with a global bound of 64 and a per-client bound
  of eight commands.
- [x] Drain in canonical station order, then immutable client ordinal order, before
  `Game.update()`.
- [x] Require per-client sequence numbers and bounded request-ID deduplication.
- [x] Revalidate session, station lease, grants, world epoch, resource revision,
  observation freshness, damage, inventory, ROE, and readiness on the main
  thread immediately before mutation. The M4 `acknowledge` action has no
  gameplay preconditions or mutation; action-specific checks remain mandatory
  when M6/M7 register gameplay actions.
- [x] Return terminal command results only to the originating client.
- [x] Invalidate unsafe queued and held controls on administration, pause, focus
  loss, disconnect, role loss, save/load, and world replacement.

Acceptance: duplicate, reordered, delayed, saturated, revoked, and stale
command tests plus deterministic replay and continuation tests.

Status: M4 software acceptance is implemented. Protocol v2 has an exact generic
envelope, closed schema/action registries, cookie/Origin/CSRF authorization,
detached bounded queues, deterministic main-thread draining, atomic revalidation,
per-session terminal results, bounded deduplication, and lifecycle invalidation.
At M4 acceptance only mutation-free `acknowledge` was registered; the first M6
slice below now adds Bridge orders. Save v10 and protocol v1 are unchanged.

## M5 - Browser lobby and shell

- [x] Replace the single Commander entry flow with an authenticated lobby and nine
  station cards.
- [x] Use a persistent desktop role rail and a native mobile station chooser.
- [x] Preserve Operations, Lookout, Guide, Contact Analyzer, and role-safe SimLog
  as shared utilities.
- [x] Keep transport/session state, authoritative station state, and per-role local
  presentation state separate.
- [x] Preserve selections and harmless view state across polling; clear command
  drafts on epoch or lease changes.

Acceptance: EN/DE parity, inert authored text, CSP, keyboard/touch operation,
desktop/mobile/large-zoom layout, stale/revoked states, and bounded canvases.

## M6 - Non-lethal station operation

Implement and accept one station at a time:

1. [x] Bridge course and propulsion orders with disconnect-safe controls.
2. [x] Engine telegraph, speed, and quiet mode.
3. [x] Damage team assignment and withdrawal.
4. [x] Radio HFDF selection and capture.
5. [x] ELOKA selection and operator annotation.
6. [x] Sonar pages, receiver controls, focus, classification, TAS, environment
   measurement, active ping, and role-private live audio.
7. [x] OPZ track selection, affiliation, radar scope, and EMCON controls.
8. [x] Helicopter launch/return, waypoint, and sonobuoy operation.

Each action receives an exact schema and local/remote parity tests. Browser
selection, maps, filters, and scroll state remain client-local unless the
simulation explicitly models shared operator state.

Status: action coverage implemented; practical workstation acceptance remains
open. All nine roles have station-specific responsive browser views, bounded
detached diagrams and role-appropriate maps. Sonar carries
the six native analysis views and an explicitly granted bounded PCM stream.
Non-lethal actions use exact schemas and shared local/remote main-thread helpers;
browser selection, marks, suppression and viewport remain client-local. Protocol
v1 and save v10 remain unchanged.

Operator-feedback follow-up: instrument-first layouts, a compact secondary menu,
native-aligned map coordinates, complete 80-row waterfall history, LOFAR spectrum,
and audio recovery across session refresh/timeouts are implemented. A host-local
station-request popup applies station and capabilities atomically without role
takeover. Software regression: 2665 tests passed; real-device usability and audio
continuity are separate acceptance items, not implied by test counts.

Native OPZ fusion slice: implemented on the authoritative main thread. Sonar
release now requires a valid Sonar operator classification; manual OPZ fusions,
marks, and suppression are bounded, transient, detached, and display-only. The
v2 OPZ projection and browser carry observations, fusions, radar state, detached
source classifications and own assets. Browser marks and suppression are local;
fusion and annotations are authoritative transient OPZ state.

## M7 - Targeting and direct fire

- [x] Refactor local launch paths into target-specific, result-returning main-thread
  helpers without changing local controls.
- [x] Resolve only current opaque observation references; never accept entity IDs,
  hidden coordinates, or profile keys from a browser.
- [x] Add role-authorized torpedo, helicopter torpedo, ESSM, chaff, Nixie, and
  other finite-store commands.
- [x] Require both command and direct-fire grants, a heartbeat no older than two
  seconds, a direct-fire command age below one second, and all existing local
  engagement checks.
- [x] Never change local selection or focus as an implementation shortcut.

Status: complete in software. Direct fire is restricted to five explicit actions:
ship torpedo, helicopter torpedo, Nixie, ESSM, and chaff. ASROC, CIWS, and AA stay
outside browser control. Hardware and multi-device acceptance remains under M9.

Acceptance: no cross-role firing, no hidden-target guidance, stale-fix and
role-loss rejection, exactly-once launch, unchanged inventory on failure, and
deterministic save continuation after accepted launches.

## M8 - Reconnect and failure handling

- Reload obtains a fresh CSRF token through the surviving HttpOnly session.
- Reconnect restores a role only while its exact lease remains valid.
- Reconnection never restores held controls or silently retries uncertain
  consequential commands.
- Slow or abusive clients cannot block the main loop or other stations.
- Role loss returns the browser to the lobby and clears private role state.

Acceptance: reload, transient loss, lease expiry, host revoke, server restart,
queue pressure, stale imagery, and multi-hour LAN stability tests.

## M9 - Documentation, packaging, and release pause

- Update README, setup/security guidance, GDD, and resume state.
- Preserve protocol-v1 documentation as historical compatibility material.
- Verify packaged browser assets and clean wheel/sdist installation.
- Measure maximum-client CPU, memory, bandwidth, latency, frame time, and
  thermals on real uConsole hardware and multiple browser devices.

Required software verification:

```sh
pytest
python tools/gen_contacts.py --check
python tools/smoke_full.py
python -m build
```

Release remains paused until save-v10 compatibility, security review,
multi-device browser testing, and real uConsole performance acceptance are
recorded in `docs/resume.md`.
