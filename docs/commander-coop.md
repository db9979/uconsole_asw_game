# Commander LAN Co-op (0.1.7)

Two-player role split: the uConsole crew operates the ship and simulation; one
Commander uses a browser on another PC. The service is optional, dependency-free
beyond the game's existing runtime, and intended only for a trusted local IPv4
network. HTTP does not protect traffic from someone who can observe the LAN.

## Setup

1. Launch the game. Networking is off, regardless of settings or saved game.
2. Open F10 Options and choose Commander LAN, or press F9 directly.
3. While off, choose the local private IPv4 address with Left/Right. Loopback
   127.0.0.1 is offered for same-machine testing only. If no LAN address appears,
   check the device's network connection; discovery does not perform DNS or
   Internet probes.
4. Choose a port if the default 8765 is occupied. Enable the service with Enter.
5. Open the actual displayed URL in the other PC's browser. Permit incoming
   connections on the host firewall only from the trusted LAN if needed.
6. Type the local pairing code: three digits plus three uppercase letters.
   Browser lowercase input is normalized. Codes are one-use and expire after
   five minutes. Five wrong guesses per rolling minute block further attempts
   temporarily; the fifth failure rotates the code. Explicit local revocation
   creates a new code and clears the lockout.
7. Once paired, the crew enables the separate changes grant. Close the panel
   with Esc to resume simulation and enable browser mutations.

The secret long bearer token is kept only in browser memory. Refreshing or
closing the browser loses it. Use local Revoke to reconnect immediately; otherwise
the old connection lease expires after 30 seconds without authenticated polling.
Never publish real pairing codes or tokens in screenshots, logs or issue reports.

## Role Controls

- Browser contact/list selection, Operations pan/zoom/follow and Lookout range
  are browser-local and independent.
- Classification and affiliation use explicit Apply buttons and require the crew
  grant. They are operator judgments, not discovered platform identity.
- Neutral C-number labels identify observation lifetimes. A reacquired contact
  may receive a new label. Only explicitly modeled AIS reports preserve names.
- Propose target sends a request, not a weapon command. The crew opens F9 and
  explicitly accepts or rejects. Accepted targets still need ordinary weapon
  readiness and local firing controls.
- Propose navigation sends an ordered course, speed, or both for local review.
  Only crew acceptance in F9 changes helm setpoints. The browser cannot steer the
  ship directly. Course acceptance requires an operational bridge; speed-only
  acceptance remains possible and cannot override propulsion or quiet-mode limits.
- An unresolved proposal cannot be silently replaced by another proposal of the
  same kind. A target proposal and a navigation proposal may wait together.
- The local panel supports row selection by mouse and activation by a second
  click on the selected row or Enter. Clicking does not bypass readiness checks.
- Voice coordination uses your existing external voice connection or conversation.
  There is no built-in chat, microphone capture or general command execution.
- Pause, focus loss, editors and administration lock remote changes. Unknown or
  stale observations never gain information merely because the Commander selects
  them. Menu/editor/splash pages disclose no pregenerated tactical world.

## Display and Alarms

After pairing, the fixed shell offers Operations, Lookout, Guide and Contacts
tabs. Operations contains the current mission picture and controls. Lookout is a
north-up, ship-centered view of the same published snapshot: it shows own course,
range rings, sea state and day/night, plots positioned observations as points and
shows bearing-only reports as edge marks. Its display range is neither visual nor
sensor range, and a plotted symbol does not establish identity. It uses no chart
geography and sends no command. Guide and Contacts remain reserved placeholders.
Tab switching preserves contact selection, draft assessments, navigation drafts
and both local view states. The authenticated shell fits the viewport; long
Operations content scrolls only inside its tab or nested panels.

The chart adapts to browser size and device pixel ratio, preserving equal map
scales. Contact details show observation/fix age and nullable range/depth/motion.
Peilung-only observations appear as rays, not invented range fixes. Local selection,
Commander proposal and crew target have distinct outlines.

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

One Commander is supported. Snapshots normally publish twice per real second,
with immediate important transitions. Four HTTP workers, absolute request
deadlines and bounded queues protect the game from slow or excessive clients.
This is not an Internet-facing service, VPN product, remote desktop or sonar
audio stream. See commander-protocol.md for the exact boundary.

## Abnahme / Pause

Automated coverage uses real loopback HTTP and headless Chromium contracts at
desktop and narrow viewport sizes. This does not establish two-physical-device
network, firewall, headphone, uConsole thermal or readability acceptance.
Follow `docs/plan-0.1.7.md` and `docs/resume.md` after this milestone. The
authorized sonar/filter/readability and physical-fidelity packages B-F follow
that plan's dependency order and end at its mandatory documented pause.
