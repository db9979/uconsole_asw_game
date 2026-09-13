# Commander LAN Co-op (0.2.0)

Remote Crew keeps the uConsole process authoritative while authenticated crew
members operate exclusive station roles from browsers. A client may retain
multiple leases but displays only one active station at a time. The optional
service has no extra runtime dependency and is intended only for a trusted local
IPv4 network. HTTP does not protect traffic from someone who can observe the LAN.

## Setup

1. Launch the game. Networking is off, regardless of settings or saved game.
2. Open F10 Options and choose Commander LAN, or press F9 directly.
3. While off, choose the local private IPv4 address with Left/Right. Loopback
   127.0.0.1 is offered for same-machine testing only. If no LAN address appears,
   check the device's network connection; discovery does not perform DNS or
   Internet probes.
4. Choose a port if the default 8765 is occupied. Enable the service with Enter.
5. Open the actual displayed URL in each crew browser. Permit incoming
   connections on the host firewall only from the trusted LAN if needed.
6. Type the local pairing code: three digits plus three uppercase letters.
   Browser lowercase input is normalized. Codes are one-use and expire after
   five minutes. Five wrong guesses per rolling minute block further attempts
   temporarily; the fifth failure rotates the code. Explicit local revocation
   creates a new code and clears the lockout.
7. Once paired, request a station in the browser. The host grants or rejects the
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
- Browser contact selection, map pan/zoom/follow, workstation pages, drafts, and
  analyzer selection remain local to that browser.
- Each station exposes only its allowlisted observation-led projection and
  controls. Classification and affiliation remain operator judgments.
- Visible labels match the corresponding uConsole station: Sonar/OPZ use K labels,
  HFDF uses public H labels, and ELOKA uses its public track key. Transport refs
  remain opaque and are not displayed. Only modeled AIS reports preserve names.
- A command grant permits direct operation of that station. Weapons additionally
  require the host's direct-fire grant. Every action is revalidated immediately
  before application against lease generation, world context, freshness,
  readiness, damage, inventory, ROE, and engagement envelope.
- Sonar contacts are released to OPZ explicitly; classification alone does not
  publish them. Sonar audio needs its own host grant and remains live-only at 1x.
- The local panel supports independent per-station request decisions, grants,
  revocation, takeover, and host control. Clicking never bypasses readiness.
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

On Sonar, clicking or tapping inside the Broadband waterfall sets the manual
listening bearing and clears contact-follow focus. The yellow line marks that
bearing. LOFAR and the other analysis plots do not steer the listening beam.

Damage status and team count, available own weapons and airborne helicopter
position are displayed. A hangared or lost helicopter is not plotted as a current
aircraft. Mission/threat/damage alerts are observation-led. Select the sound button
to enable browser tones; volume and mute are independent of uConsole audio.
Autoplay may be blocked by the browser until this gesture. Visual alarms always
remain available. Reconnection establishes a new sound baseline, not alarm replay.

A queued response is not an accepted action. If delivery is uncertain, the browser
keeps the action pending. Its explicit reconciliation control retries the same
request ID/envelope, with a five-second cooldown; it never silently sends a new
action or invents success. Stale context or revision conflicts require reviewing
the current picture. The server reports expired queued actions as rejections.

## Lifecycle and Limits

Local disable or process shutdown stops the listener and revokes credentials.
Successful load/reset replaces the network session at the next main-thread pump;
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
