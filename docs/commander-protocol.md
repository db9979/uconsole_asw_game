# Commander Protocol and Security

Application 0.1.6, API protocol 1, save format v8. These versions are independent.
No credentials, network sessions, leases, command queues or target proposals are
saved. Shared annotations and a crew-accepted target use normal game persistence.

## Ownership

CommanderConsole controls the listener locally. CommanderBridge.pump executes
once per main-loop wall frame before Game.update, including paused frames. It
reads public observations and own assets, validates commands and publishes
detached JSON. HTTP handlers never import Game/Pygame, access simulation objects,
or trigger sensor/TMA work. Candidate-load methods have no network side effects.

## Endpoints

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

## Pairing and Bounds

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

## Snapshot and Commands

State includes protocol/version/session/epoch/revision/sequence, phase and command
availability, clocks, known mission information, own readiness, public tracks,
crew target, proposal, events and command results. Unknown values are null.
Menu/editor/splash use the same schema with null own geometry, empty mission,
tracks, events and chart. Paused live missions retain a frozen read-only picture.

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

All require pairing, lease-bound local grant and live command ownership. Explicit
revision checks resolve concurrent crew/Commander annotation changes. Repeating
an identical retained ID replays its result; changing its payload is rejected.
Results contain id, status (applied/rejected), and reasoncode. Browser recovery
reuses the exact envelope and never retries automatically under a new ID.

Proposal acceptance is local-only and revalidates the current contact. It sets
Game.target without changing crew selection/listening focus and without invoking
weapons. Air/missile sequence namespaces cannot alias sonar identity.

Epoch changes reject queued actions across administrative/input/grant/connection
transitions. World replacement revokes pairing and generates a new session at the
next pump. The browser requires matching session/chart context before revealing
the new picture. Old event backlog does not retrigger audio after reconnect.

## Test Scope

Transport tests cover live loopback framing, Host/Origin, pairing/TTL/rate limits,
lease changes, trickle deadlines, cleanup, queues and credential-free responses.
Bridge tests cover truth traps, namespaces, freshness, revisions, deduplication,
redaction, object-lifetime references, proposals and failed/successful loads.
Integration tests combine actual Game, HTTP and main-thread acceptance. Chromium
contracts exercise browser polling, commands, XSS-inert authored strings, resize,
redaction, audio baseline and uncertainty recovery. Real LAN/hardware acceptance
must be recorded separately rather than inferred from automated test success.
