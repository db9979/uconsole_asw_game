# Commander Protocol and Security

[Deutsch](commander-protocol.de.md)

Application 1.0.0, API protocol 2, save format v12-only. These versions are independent.
No credentials, network sessions, leases, command queues or proposals are saved.
Shared annotations and crew-accepted target/navigation setpoints use normal game
persistence.

## Ownership

CommanderConsole controls the listener locally. CommanderBridge.pump executes
once per main-loop wall frame before Game.update, including paused frames. It
reads public observations and own assets, validates commands and publishes
detached JSON. HTTP handlers never import Game/Pygame, access simulation objects,
or trigger sensor/TMA work. Candidate-load methods have no network side effects.

## Protocol v2 Endpoints

| Method / route | Contract |
|---|---|
| GET /, /app.js, /style.css | Fixed packaged resources, cached at server start |
| GET /api/v2/ui?lang=en or de | Only `commander.web.*` strings from root catalogs |
| GET /api/v2/contacts | Public packaged contact-reference catalog |
| POST /api/v2/pair | JSON pairing code; success creates a cookie session and returns CSRF state |
| GET /api/v2/session | Authenticated client, lease, grant and sequence state |
| GET /api/v2/state, /chart | Active role projection and matching known chart |
| GET /api/v2/results, /proposals, /events | Role- and session-scoped command state |
| GET /api/v2/simlog | Host-granted full-truth diagnostic snapshots, at most 64 entries |
| POST /api/v2/stations/request, /activate, /release | Strict lease operations |
| POST /api/v2/commands | Strict action envelope; 202 means queued, not applied |
| POST /api/v2/sonar/audio | Separately granted live Sonar audio polling |
| POST /api/v2/helicopter/audio | Separately granted live helicopter audio polling |
| GET /ws/v2/sonar/audio, /ws/v2/helicopter/audio | Leased, read-only binary PCM stream (WebSocket upgrade) |
| GET /ws/v2/sonar | Active-Sonar-role binary display stream (WebSocket upgrade) |
| POST /api/v2/logout | Revokes the current session and clears its cookie |

Every `/api/v1/*` route is retired and returns 404 without redirect or fallback.
Protected requests use the HttpOnly session cookie. Mutation requests require
`application/json`, exact same Origin and, after pairing, the exact CSRF token.
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
Sonar audition mode, band, notch, and gain. The server keeps the last 40 blocks
(ten seconds) so a briefly stalled client catches up in order; older blocks are dropped
and reported as a discontinuity. The browser starts playback about one second behind the newest
block. Its AudioWorklet repeats the last block for at most two seconds after fresh data ends,
then plays quiet neutral noise and marks the stream stale. The uConsole mixer worker uses the
same one-second lead and two-second continuation. A transient
state-poll failure or HTTP 503 does not discard queued audio; the audio endpoint
still checks session and station authority on each request. A restarted stream
rebases a browser cursor that is ahead of its new sequence. There is no continuous
own-ship ambience sound, locally or in the browser; sound opt-in only enables
synthesized alert/combat-effect cues and this live sonar/helicopter stream.
The optional audio WebSocket uses subprotocol `u-jagd-audio-v2`, the HttpOnly session
cookie, exact Origin, active station and audio grant. Each 2060-byte binary message is
`UJA2`, a little-endian unsigned 64-bit sequence, and 1024 mono signed 16-bit
samples at 4096 Hz. Sequence gaps signal dropped blocks; the server sends at most
the newest four pending blocks after a slow client. HTTP audio polling remains the
fallback. Neither transport accepts browser audio or simulation commands.
For on-device diagnosis, `U_JAGD_AUDIO_DEBUG=1` writes bounded, contact-free
receiver block rate, mixer underruns, queue fill and loss counters to
`~/.u-jagd/audio_debug.log`. Browser developer tools can read the bounded
`window.uJagdAudioDiagnostics` snapshot (buffer seconds, sequence gaps,
dropped blocks, repeats, stale state and transport). Neither is persisted in
game saves.
The Sonar role receives only bounded own-ship speed and TAS handling limits needed
to explain a disabled array control; hover reasons never inspect hidden entities.

The Sonar display stream is an additive protocol-v2 transport, not a simulation
interface. It upgrades only with the exact same Origin, authenticated HttpOnly
cookie, active Sonar lease/generation and subprotocol `u-jagd-sonar-v2`. Only one
stream per session is admitted. Revocation, role activation, lease replacement,
world replacement or shutdown invalidates it immediately. The ordinary state
poll remains authoritative and is the automatic fallback; while streaming, the
client requests `/api/v2/state?sonar=stream`, whose Sonar projection omits the
duplicated spectral arrays. The cookie is scoped to `/` so the browser can present
it to both `/api/v2/*` and the fixed WebSocket route; it remains HttpOnly,
SameSite=Strict and absent from JavaScript, URLs and protocol payloads.

Each server-to-client WebSocket message is one final binary frame, at most 4096
bytes. Its 60-byte little-endian header is
`<4sBBHQQdfHHHHHHfff>`: magic `UJS2`, stream version, flags, header bytes,
monotonic stream sequence, world epoch, simulation time, listening bearing, five
array lengths, one reserved length, then Broadband/LOFAR/DEMON ages. Five packed
unsigned-byte arrays follow in that order: newest Broadband row, newest LOFAR row,
newest DEMON row, current LOFAR spectrum, current DEMON spectrum. Values are the
already detached, allowlisted projection quantized from [0,1] to [0,255]. The
server caches only the newest packet; a slow client skips intermediate display
samples and is disconnected if writing stalls, so render traffic cannot build an
unbounded queue or alter deterministic simulation order.

## Protocol v2 Pairing and Bounds

- Explicit RFC1918 or loopback IPv4 bind; no wildcard/public IPv4.
- Cryptographic code: `[0-9]{3}[A-Z]{3}`, reusable for additional crew until
  explicit revocation or rate-limit rotation. Rotation excludes its predecessor.
  Server comparison is case-sensitive and constant-time.
- Five failed guesses per rolling 60 seconds, globally across IPs. Automatic
  rotation does not erase failures. Further attempts return 429 while exhausted.
- Independent cryptographic cookie session with an eight-hour idle limit. Presence
  polling renews a 15-second station lease; grants bind to its generation. At most
  12 clients can hold sessions.
- Sixteen admitted worker connections, 1.5-second inactivity timeout and
  three-second absolute deadline for ordinary HTTP. A successfully authenticated
  Sonar upgrade retains one bounded worker slot until it is invalidated or closes.
  Deadline timers are bounded by workers and joined on cleanup.
- JSON bodies at most 4096 bytes; bounded request line/headers, strict framing,
  duplicate-member/nonfinite-number/unknown-field rejection.
- Global command queue at most 64 and per-client queue at most eight. Commands
  older than two seconds yield terminal rejection, not silent disappearance.
- At most 256 projected tracks, 128 events and 64 SimLog entries. Chart at most
  20,000 vertices and 1,024 polygons; oversized charts are
  explicitly omitted rather than partially misrepresented.

HTTP remains plaintext. Pairing, Origin checks and limits do not provide network
confidentiality. Trusted LAN only; no port forwarding or public hosting.

## Protocol v2 Projections and Commands

Role state includes protocol/version/world session/epoch/resource revision,
phase and command availability, clocks, known mission information, own readiness,
public tracks and the environment summary. Proposals, events, command results and
SimLog history use separate authenticated endpoints so each can enforce its own
session, role, authority and grant boundary.
Menu/editor/splash use the same schema with null own geometry and environment,
plus empty mission, tracks, events and chart. Paused live missions retain a
frozen read-only picture.

Track references and neutral labels are observation-lifetime identities, not raw
entity IDs. Replacement/reacquisition invalidates them. Only modeled AIS labels
are forwarded; internal producer prefixes cannot reveal civilian/warship identity.
No seed, RNG, hidden entity/profile information or save dumps are exported.

The ELOKA v2 intercept row additionally carries derived `signal_state`
(`LIVE`, `RECENT`, `MEMORY`, or `UNCONFIRMED`) and boolean `operational` fields.
Browser status, minimum-threat, and frequency-band filters are client-local and
apply one identical subset to the intercept list, contacts, scope, and accessible
text alternative. Active ECM targets remain visible. No range or hidden emitter
identity is projected or filterable.

Commands carry protocol, cryptographic request ID, client sequence, station,
station and active generations, world session/epoch, resource revision, action,
and exact action-specific parameters. Proposal actions are:

| Action | Additional fields |
|---|---|
| propose_target | observation `ref` |
| clear_target_proposal | no parameters |
| propose_navigation | `course` and/or `speed_kn`; course in [0,360), speed in the configured helm range |

All actions require pairing, an active role lease, the role's command grant and
live command ownership; direct-fire actions require their additional grant.
Explicit revision checks resolve concurrent crew changes. Repeating
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

Damage events are visible to Bridge and Damage Control, threats to Bridge, OPZ
and Weapons, and mission events to every role. Proposal lifecycle events are
visible only to the originating session and role. SimLog stores at most 64 prior
detached diagnostic snapshots with their simulation timestamps. An explicit
host grant exposes full simulation truth through this read-only endpoint;
disabled or ungranted SimLog returns no history.

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

## Solo Mode Additions (protocol v2, additive)

The session body carries `host`: `null` normally, `{"generation": n}` for a solo
session. `GET /api/v2/host` returns the detached host view (`phase`, `paused`,
`time_scale`, `world_mode`, `scenario`, `level`, `scenarios`, `levels`, `slots`) only to a
session with `host`; other sessions get 403. Slot rows carry `saved` and `modified`
from file metadata only, never save contents.

Host controls use the ordinary `POST /api/v2/commands` with the pseudo-role
`"host"` (never a station lease; `STATIONS` and every projection stay nine).
`station_generation` is the session's `host.generation`, `active_generation` must be
0, and `world_session` must match; the epoch and resource revision are not checked
because these actions reference no resource and pause/resume move the epoch
themselves. Actions: `host_pause`, `host_resume`, `host_time_scale {index}`,
`host_save {slot}`, `host_load {slot}`, `host_new_game {scenario, world_mode,
level?, seed?}`, and `host_instructor_environment {sea_state, event}`. The instructor
action changes the save-compatible authoritative world field (0–6) and refreshes
the derived weather endpoints. Its optional closed event enum changes all hostile
submarines to quiet/cruise/flank speed or injects a torpedo-launch exercise cue,
without exposing target identity or simulation truth to a station.
Each action has a closed schema and its own allowed phases (a host menu
or overlay makes the phase `blocked` and rejects all of them). Host commands run
before station commands in a frame; once one replaces the world, every later command
of that frame is rejected as `phase_blocked`. In solo mode a world replacement keeps
session, cookie and CSRF, drops queued and held commands, re-leases every station
under fresh generations and does not rotate the join code.

Crew mode is unchanged: `station: "host"` is rejected with 403 and the game controls
remain host-only. Solo mode is an explicit local host decision (CLI flag or F9 row),
never persisted, and changing it revokes all sessions.

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
