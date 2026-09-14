# Commander LAN Co-op (0.2.2)

[Deutsch](commander-coop.de.md)

Remote Crew keeps the uConsole process authoritative while authenticated crew
members operate exclusive station roles from browsers. A client may retain
multiple leases but displays only one active station at a time. The optional
service has no extra runtime dependency and is intended only for a trusted local
IPv4 network. HTTP does not protect traffic from someone who can observe the LAN.

## Setup

1. Launch the game. Networking is off, regardless of settings or saved game.
2. Open F10 Options and choose Commander LAN, or press F9 directly.
3. Choose **existing LAN** or **temporary U-Jagd hotspot** while the service is
   off. In LAN mode, then select the local private IPv4 address. Loopback
   127.0.0.1 is for same-machine tests only.
4. Hotspot mode requires the one-time system-helper installation described in
   the uConsole installation guide. Activation temporarily disconnects the
   current Wi-Fi and displays a random SSID and a new Wi-Fi password. Neither is
   saved nor sent to browsers.
5. Choose a port if the default 8765 is occupied and enable the service with
   Enter. The Commander listener starts on the hotspot's exact private IPv4 only
   after NetworkManager has assigned it.
6. Open the actual displayed URL in each crew browser. Permit incoming
   connections on the host firewall only from the trusted LAN if needed.
7. Type the local pairing code: three digits plus three uppercase letters.
   Browser lowercase input is normalized. The displayed code remains valid for
   additional crew. Five wrong guesses per rolling minute block further attempts
   temporarily and rotate the code; explicit local revocation also creates a new
   code and clears the lockout.
8. Once paired, request a station in the browser. The host grants or rejects the
   exact request. Approval enables normal station operation; sonar audio and
   direct fire remain separate grants. When a crew station is active, the
   simulation continues behind F9 and F9 may remain open for crew administration.

The secret session credential is held in an HttpOnly SameSite cookie scoped to
the v2 API. JavaScript, URLs, the DOM, settings, saves, and logs never receive it.
A reload may recover the same session, but station authority expires quickly if
presence polling stops. Never publish real pairing codes, cookies, or CSRF tokens
in screenshots, logs, or issue reports.

## Role Controls

- The host grants one exclusive owner per station. One client may retain several
  station leases and switch between them without releasing the inactive leases.
  Use Add station for another request; an approved station opens automatically.
  Afterwards, choose any retained lease from the stable station selector.
- A leased station is read-only on the uConsole until the host revokes its lease.
  F9 administration, pause, and switching the local display to another station
  remain available, and retained inactive browser leases stay exclusive.
- Browser contact selection, map pan/zoom/follow, workstation pages, drafts, and
  analyzer selection remain local to that browser.
- Hover over a disabled control to read the current localized reason. Reasons are
  derived only from published state and include grants, phase, damage, cooldown,
  inventory, selection, and handling limits. For TAS, the browser reports whether
  own-ship speed is below 3 kn or above 12 kn.
- Each station exposes only its allowlisted observation-led projection and
  controls. Classification and affiliation remain operator judgments.
- Visible labels match the corresponding uConsole station: Sonar/OPZ use K labels,
  HFDF uses public H labels, and ELOKA uses its public track key. Transport refs
  remain opaque and are not displayed. Only modeled AIS reports preserve names.
- Assignment immediately enables normal operation of that station. Weapons
  additionally require the host's direct-fire grant. Every action is revalidated
  immediately before application against lease generation, world context, freshness,
  readiness, damage, inventory, ROE, and engagement envelope.
- Sonar contacts are released to OPZ explicitly; classification alone does not
  publish them. Sonar audio needs its own host grant and remains live-only at 1x.
  Its Broadband, Filtered, and Heterodyne modes share the authoritative band,
  notch, and gain settings with the Sonar workstation.
- Sonar crew can stage a target proposal and Bridge crew can stage course and/or
  speed orders. Proposals are bound to the originating v2 session, active role,
  station generation, world context and observation reference. They affect no
  target or navigation setpoint until the host accepts them locally.
- The local panel supports independent per-station request decisions, additional
  grants, revocation, takeover, and host control. Clicking never bypasses readiness.
- Voice coordination uses your existing external voice connection or conversation.
  There is no built-in chat, microphone capture or general command execution.
- Manual pause, focus loss, save/load, quit, nations, true editors, menus and the
  splash lock remote changes. With an active crew station, F1 help, the in-game F8
  analyzer, F9 crew administration and F10 options leave simulation and remote
  stations live; without active crew they retain the normal pause behavior.
  Unknown or stale observations never gain information merely because the
  Commander selects them. Menu/editor/splash pages disclose no pregenerated
  tactical world.

## Display and Alarms

After pairing, the shell becomes a role-specific workstation. Bridge, Sonar,
Weapons, Damage Control, OPZ, Radio, Engineering, Helicopter, and ELOKA each have
a dedicated instrument and bounded controls. OPZ overlays radar range and sweep
on known chart geography; bearing-only reports remain rays rather than invented
positions. Switching a retained station clears unsafe role-local state while
keeping the other lease. The guide and contact-reference library remain available
without exposing another station's tactical picture.

The chart adapts to browser size and device pixel ratio, preserving equal map
scales. Contact details show observation/fix age and nullable range/depth/motion.
Peilung-only observations appear as rays, not invented range fixes. Local selection,
Commander proposal and crew target have distinct outlines.
The Helicopter chart follows the airborne helicopter rather than the ship and
labels its projected Sonobuoys `SB01`, `SB02`, and so on.

The Bridge weather instrument shows the authoritative day/night state, effective
sea state, weather class, wind, rain and visibility. Its subdued wave and rain
animation follows projected simulation time and freezes while paused. Helicopter
readiness separately shows weather-safe launch/dipping decisions and crosswind.
Autocrew status is read-only in every browser role; the host controls it locally.

On Sonar, clicking or tapping inside the Broadband waterfall sets the manual
listening bearing and clears contact-follow focus. The yellow line marks that
bearing. LOFAR and the other analysis plots do not steer the listening beam.

Damage status and team count, available own weapons and airborne helicopter
position are displayed. A hangared or lost helicopter is not plotted as a current
aircraft. Mission/threat/damage alerts are observation-led. Select the sound button
to enable browser tones and the Bridge's synthesized own-ship cavitation noise;
volume and mute are independent of uConsole audio. Cavitation sound uses only the
Bridge projection and stops on quiet propulsion, stale connection, role change,
pause, hidden page, or mute.
Autoplay may be blocked by the browser until this gesture. Visual alarms always
remain available. Reconnection establishes a new sound baseline, not alarm replay.

Events are role-scoped: damage reports reach Bridge and Damage Control, threats
reach Bridge, OPZ and Weapons, and mission events reach every role. Proposal
lifecycle events are visible only to their originating session and role. With a
local SimLog grant, a browser receives at most 64 prior role projections; it
never receives the host's full-truth SimLog or hidden entity identifiers.

A queued response is not an accepted action. If delivery is uncertain, the browser
keeps the action pending. Its explicit reconciliation control retries the same
request ID/envelope, with a five-second cooldown; it never silently sends a new
action or invents success. Stale context or revision conflicts require reviewing
the current picture. The server reports expired queued actions as rejections.

## Lifecycle and Limits

Local disable or process shutdown first stops the listener and revokes credentials.
A game-owned hotspot is then removed and the previous Wi-Fi connection is
reactivated. A normal application failure also closes the helper control channel
and triggers that cleanup. Successful load/reset replaces the network session at the next main-thread pump;
pair and grant again. Failed candidate restoration leaves the live network session
unchanged. A new connection never inherits the previous connection's grant.

Clients, workers, histories, projections, and command queues are hard-bounded.
Snapshots normally publish twice per real second, with immediate important
transitions. This is not an Internet-facing service, VPN product, or remote
desktop. See commander-protocol.md for the exact boundary.

## Abnahme / Pause

Automated coverage uses real loopback HTTP and headless Chromium contracts at
desktop and narrow viewport sizes. This does not establish two-physical-device
network, firewall, headphone, uConsole thermal or readability acceptance.
Follow `docs/plan-0.1.8.md` and `docs/resume.md` for current resumable work.
