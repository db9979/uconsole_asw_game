# Commander Browser Captures

These seeded demonstration screenshots use the packaged browser assets, the
production `CommanderServer`, `CommanderBridge`, and a real `Game`. They do not
use mocked API responses or stretched native-station images, and they are not
evidence of two-computer LAN or hardware acceptance.

## Desktop Workstations

All desktop captures are 1920 x 1080, use seed 1234, complete a real protocol-v2
pairing, receive their station lease from the host, and display that station's
allowlisted projection.

| Workstation | English | German |
| --- | --- | --- |
| Bridge | [PNG](commander-v2-en-bridge-desktop.png) | [PNG](commander-v2-de-bridge-desktop.png) |
| Sonar | [PNG](commander-v2-en-sonar-desktop.png) | [PNG](commander-v2-de-sonar-desktop.png) |
| Weapons | [PNG](commander-v2-en-weapons-desktop.png) | [PNG](commander-v2-de-weapons-desktop.png) |
| Damage Control | [PNG](commander-v2-en-damage-desktop.png) | [PNG](commander-v2-de-damage-desktop.png) |
| OPZ/CIC | [PNG](commander-v2-en-opz-desktop.png) | [PNG](commander-v2-de-opz-desktop.png) |
| Radio | [PNG](commander-v2-en-radio-desktop.png) | [PNG](commander-v2-de-radio-desktop.png) |
| Engineering | [PNG](commander-v2-en-engine-desktop.png) | [PNG](commander-v2-de-engine-desktop.png) |
| Helicopter | [PNG](commander-v2-en-helicopter-desktop.png) | [PNG](commander-v2-de-helicopter-desktop.png) |
| Electronic Warfare/ESM | [PNG](commander-v2-en-eloka-desktop.png) | [PNG](commander-v2-de-eloka-desktop.png) |

`commander-overview.png` is an alias of the English OPZ/CIC capture for existing
README links. `commander-wide.png` is a separate 2560 x 1440 English Sonar
capture.

## Mobile Views

The 500 x 844 captures exercise the responsive single-column layout. Chromium's
headless mode enforces a 500-CSS-pixel minimum viewport; narrower physical
devices use the same mobile breakpoint.

| Scene | Image |
| --- | --- |
| English station-request lobby | [PNG](commander-v2-en-lobby-mobile.png) |
| English Sonar filters | [PNG](commander-v2-en-sonar-mobile.png) |
| German Radio messages | [PNG](commander-v2-de-radio-mobile.png) |
| German multi-station selector | [PNG](commander-v2-de-multi-station-mobile.png) |

## Reproduction

From the repository root, with the project dependencies and Chromium installed:

```sh
python tools/capture_commander.py
python tools/capture_commander.py --output /tmp/commander-review --seed 1234
```

The optional tool does not download a browser and does not require Node or
Playwright. It advances the game through 360 normal 1/60-second updates, freezes
the simulation, and then pumps only the main-thread projection on a deterministic
capture clock. The Sonar examples use the real filtered audition state. Authored
own-ship damage demonstrates the Damage Control interface; contacts and mission
intelligence still come only from game observations.

The script binds only `127.0.0.1` on an ephemeral port. Its in-memory-only browser
automation performs real v2 pairing and cookie recovery. The host grants and
activates the requested station after pairing; the multi-station scene receives
three independent leases. It sends no simulation command. No HTTP thread accesses
`Game`.

An isolated temporary HOME and incognito Chromium profile avoid real user data.
Credentials are not printed, placed in a URL, written into a source file, left in
the DOM, or intentionally persisted. All images are staged before publication.
The service is stopped, pairing is revoked, injected cached assets are cleared,
and listener and worker termination are checked before the PNGs are copied.

## Review And Limits

The 2026-09-13 regeneration verified, for every image, the expected language and
role, healthy connection state, rendered workstation instrument, required Sonar,
Radio, or multi-station content, hidden credential, inaccessible HttpOnly session
cookie, exact PNG dimensions, no horizontal overflow, no captured JavaScript
error, and clean server shutdown. The complete desktop and mobile contact sheets
were also inspected for readable, unclipped content.

The captures preserve the observation boundary: unknown hostile range, depth,
course, identity, and position are not invented for display. They do not establish
real two-PC pairing, Wi-Fi reliability, physical touch ergonomics, WebAudio output,
or uConsole performance. Command execution, authorization, responsive layouts,
and browser interactions have separate automated contract tests.
