# Commander Protocol and Security

[Deutsch](commander-protocol.de.md)

Application 0.2.1, API protocols 1 and 2, save format v10-only. These versions are independent.
No credentials, network sessions, leases, command queues or proposals are saved.
Shared annotations and crew-accepted target/navigation setpoints use normal game
persistence.

## Ownership

CommanderConsole controls the listener locally. CommanderBridge.pump executes
once per main-loop wall frame before Game.update, including paused frames. It
reads public observations and own assets, validates commands and publishes
detached JSON. HTTP handlers never import Game/Pygame, access simulation objects,
or trigger sensor/TMA work. Candidate-load methods have no network side effects.

## Legacy Protocol v1 Endpoints

| Method / route | Contract |
|---|---|
| GET /, /app.js, /style.css | Fixed packaged resources, cached at server start |
| GET /api/v1/ui?lang=en or de | Only commander.web.* strings from root catalogs |
| POST /api/v1/pair | JSON code; success returns memory-only bearer token |
| GET /api/v1/state | Authenticated cached observation snapshot |
| GET /api/v1/chart | Authenticated cached current chart or redacted empty chart |
| POST /api/v1/commands | Strict action envelope; 202 means queued, not applied |

Protected requests use Authorization: Bearer. Tokens are never query parameters
or cookies. Mutation requests require application/json and exact same Origin.
Host is restricted to the bound IPv4 and actual port (localhost also allowed for
loopback). No wildcard CORS, arbitrary routes/files, redirects, external assets,
or HTML interpolation of authored text. Responses use no-store, CSP, nosniff and
anti-framing headers. Access logs contain no credentials because they are disabled.

## Remote Crew Protocol v2

Protocol v2 is the current role-oriented interface. Pairing creates an
independent cryptographic session in an HttpOnly SameSite cookie and returns a
separate CSRF token in the exact session response. State-changing requests
require both the cookie, exact Origin, and CSRF token.

The session advertises all nine stations as nested records. A client may retain
multiple leases, each with its own monotonic station generation. Assignment
enables the lease's ordinary command grant immediately; direct-fire and
sonar-audio grants remain separate. Exactly one retained lease is active and
identified by a separate monotonic active generation. Station requests are
additive; activation does not release another lease. Release, revocation,
takeover, expiry, pause, focus loss, and world replacement invalidate authority
at their defined scope.

Activation validates the target lease and its station generation but does not
compare an older active generation; this lets a client select any still-retained
lease after a concurrent host activation. Release and simulation commands retain
their active-generation checks. A v2 lease blocks matching local uConsole station
input without blocking host administration or the remote main-thread command path.

Role state is an exact allowlisted projection under `/api/v2/state`. The active
role receives own-asset truth, known geography, and published observations only.
It never receives simulation objects, hidden IDs, undiscovered positions, RNG
state, credentials, or save data. OPZ receives only explicitly released sonar
observations; classification is independent. Browser labels are opaque
observation-lifetime references.

Every assigned v2 role receives the same detached environment summary: authored
integer `sea_state`, transitioning `effective_sea_state`, authoritative
`is_night`, weather class, nautical wind-from direction, wind speed in knots,
rain intensity and visibility in NM. The Helicopter role additionally receives
only derived launch/dipping safety booleans and crosswind; it receives no hidden
aircraft or weather state. Each role's Autocrew projection contains only that
role's enabled flag and status. Credentials, leases and Autocrew commands are
not part of this projection.

Commands use strict envelopes containing protocol, cryptographic request ID,
per-client sequence, station generation, active generation, world
session/epoch, resource revision, action, and exact bounded parameters. HTTP
threads only enqueue detached envelopes. The main thread revalidates and applies
accepted commands once in deterministic station and per-client FIFO order.
Direct-fire actions additionally require the station's direct-fire grant and
ordinary observation, readiness, inventory, ROE, and envelope checks. A queued
response is never reported as successful before its terminal result.

V2 sessions, clients, leases, histories, queues, polling, and projection sizes
are hard-bounded. Sonar audio is live-only, separately granted, bound to the
active sonar generation, and filtered on the main thread using the projected
Sonar audition mode, band, notch, and gain. Bridge cavitation noise is synthesized
locally in the browser after sound opt-in from the already allowlisted own-ship
cavitation boolean; it adds no endpoint, grant, command, or host-audio control.
The Sonar role receives only bounded own-ship speed and TAS handling limits needed
to explain a disabled array control; hover reasons never inspect hidden entities.
Protocol v1 remains exact for compatibility and is not silently broadened by v2
fields.

## Protocol v1 Pairing and Bounds

- Explicit RFC1918 or loopback IPv4 bind; no wildcard/public IPv4.
- Cryptographic code: [0-9]{3}[A-Z]{3}, five-minute validity, one use. Rotation
  excludes its predecessor. Server comparison is case-sensitive and constant-time.
- Five failed guesses per rolling 60 seconds, globally across IPs. Automatic
  rotation does not erase failures. Further attempts return 429 while exhausted.
- Independent 32-random-byte bearer token and 30-second idle lease, renewed by
  authenticated state/chart polling. A grant binds to this lease generation.
- Four admitted worker connections, 1.5-second inactivity timeout and three-second
  absolute deadline. Deadline timers are bounded by workers and joined on cleanup.
- JSON bodies at most 4096 bytes; bounded request line/headers, strict framing,
  duplicate-member/nonfinite-number/unknown-field rejection.
- Queue at most 32; bridge applies at most four requests per wall frame. Expired
  five-second requests yield terminal rejection, not silent disappearance.
- At most 256 projected tracks, 128 events, 32 recent results and 128 deduplicated
  IDs. Chart at most 20,000 vertices and 1,024 polygons; oversized charts are
  explicitly omitted rather than partially misrepresented.

HTTP remains plaintext. Pairing, Origin checks and limits do not provide network
confidentiality. Trusted LAN only; no port forwarding or public hosting.

## Protocol v1 Snapshot and Commands

State includes protocol/version/session/epoch/revision/sequence, phase and command
availability, clocks, known mission information, own readiness, public tracks,
crew target, target proposal, navigation proposal, events and command results.
The additive protocol-1 `environment` object contains integer `sea_state` in
0-9 and authoritative boolean `is_night`; unknown values are null.
Menu/editor/splash use the same schema with null own geometry and environment,
plus empty mission, tracks, events and chart. Paused live missions retain a
frozen read-only picture.

Track references and neutral labels are observation-lifetime identities, not raw
entity IDs. Replacement/reacquisition invalidates them. Only modeled AIS labels
are forwarded; internal producer prefixes cannot reveal civilian/warship identity.
No seed, RNG, hidden entity/profile information or save dumps are exported.

Commands carry id, session, epoch, revision, action, and action-specific fields:

| Action | Additional fields |
|---|---|
| classify | track, value (allowed operator class or null) |
| affiliate | track, value (allowed NATO affiliation) |
| propose | track |
| clear_proposal | optional matching track |
| propose_navigation | course and/or speed_kn; course in [0,360), speed in the configured helm range |

All require pairing, lease-bound local grant and live command ownership. Explicit
revision checks resolve concurrent crew/Commander annotation changes. Repeating
an identical retained ID replays its result; changing its payload is rejected. A
distinct request cannot replace an unresolved proposal of the same kind and
receives `proposal_pending`; one target and one navigation proposal may coexist.
Results contain id, status (applied/rejected), and reasoncode. Browser recovery
reuses the exact envelope and never retries automatically under a new ID.

Proposal acceptance is local-only. Target acceptance revalidates the current
contact and sets Game.target without changing crew selection/listening focus or
invoking weapons. Navigation acceptance revalidates the session, lease, live
phase, bridge readiness and complete numeric bounds before atomically changing
ordered course/speed. Course acceptance requires an operational bridge; a valid
speed-only proposal may still be accepted. Physical movement remains governed by
normal ship physics, propulsion and quiet-mode limits. No remote action can
directly steer. Air/missile
sequence namespaces cannot alias sonar identity.

Epoch changes reject queued actions across administrative/input/grant/connection
transitions. World replacement revokes pairing and generates a new session at the
next pump. The browser requires matching session/chart context before revealing
the new picture. Old event backlog does not retrigger audio after reconnect.

An active crew station keeps protocol phase `live` behind local F1 help, the
in-game F8 contact analyzer, F9 crew administration, and F10 options. Opening or
closing one of these owners still invalidates commands queued across the
transition. Manual pause, focus loss, save/load, quit, nations, real editors,
menus, and splash remain blocked.

The Lookout consumes only the current state snapshot, never chart geography or
simulation objects. It is north-up and ship-centered: positioned observations
are points, while bearing-only reports are edge marks without invented range.
Its range is browser-local and sends no command. Sea state and day/night affect
presentation only; they are not visibility models, and symbols do not establish
platform identity. Lookout draws only on snapshots, tab activation, local range
changes or resize, with device-pixel-aware backing dimensions.

## Test Scope

Transport tests cover live loopback framing, Host/Origin, pairing/TTL/rate limits,
lease changes, trickle deadlines, cleanup, queues and credential-free responses.
Bridge tests cover truth traps, namespaces, freshness, revisions, deduplication,
redaction, object-lifetime references, proposals and failed/successful loads.
Integration tests combine actual Game, HTTP and main-thread acceptance. Chromium
contracts exercise browser polling, commands, XSS-inert authored strings, resize,
redaction, audio baseline, uncertainty recovery and snapshot-only Lookout geometry.
The EN/DE desktop/mobile/200-percent matrix verifies its one-screen layout. Real
LAN/hardware acceptance must be recorded separately rather than inferred from
automated test success.
