# Commander LAN Co-op

For a browser-only room with a web host account, see the
[web-host guide](web-host.de.md).

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

**Windows PC as server.** `U-Jagd-Windows.exe` (see the README section
"Windows program") runs the same game on a Windows PC. Its starter window
launches the game with `--remote-crew` or `--solo-crew`, so the listener is
already up on the PC's private LAN address (steps 1-5 are done), and it shows
the URL, the pairing code and a QR code. Steps 6-8 stay the same: the host
approves station requests in the game window (F9). The hotspot mode is
Linux-only. Allow U-Jagd on private networks when the Windows firewall asks.
`python main.py --remote-crew` does the same on Linux.

## Role Controls

- The host grants one exclusive owner per station. One client may retain several
  station leases and switch between them without releasing the inactive leases.
  Use Add station for another request; an approved station opens automatically.
  Afterwards, choose any retained lease from the stable station selector.
- A leased station is read-only on the uConsole until the host revokes its lease.
  F9 administration and switching the local display to another station
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
- Voice in the `--web-host` room starts enabled; the host's option row switches it
  off, which also drops the current talker. The LAN listener (`F9`) has no voice;
  use your existing external voice connection there. There is no general chat or
  command execution over voice.
- The mission always runs in real time and cannot be paused. Local menus and
  overlays (F1 help, options, save/load, quit confirmation, nations, the in-game F8
  analyzer, F9 administration) and focus loss leave simulation and remote stations
  live. Only the main menu and the splash lock remote changes.
  Unknown or stale observations never gain information merely because the
  Commander selects them. Menu/editor/splash pages disclose no pregenerated
  tactical world.
- Phone lookouts: the roles `lookout` (the frigate's bridge lookout) and
  `uboot_lookout` (the crewed submarine's periscope) belong to phones paired
  through `/lookout`. A phone pairs straight onto its role (pair body `role`),
  never takes another station, and in solo mode may join beside the solo
  session (one phone per role). The F9 listener also serves HTTPS on the next
  port with a self-signed certificate for its LAN address (`~/.u-jagd/tls/`),
  because phones only give the gyroscope and the microphone to a secure page;
  F9 shows a second QR code for it. The phone calls sightings (`lookout_call`:
  category, bearing, optional range); the host confirms a call only when its
  lookout or periscope has a matching sighting there. While a phone holds the
  lookout, the automatic lookout stops reporting ships, aircraft and torpedoes.

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
animation follows projected simulation time. Helicopter
readiness separately shows weather-safe launch/dipping decisions and crosswind.
Autocrew status is read-only in every browser role; the host controls it locally.

On Sonar, clicking or tapping inside the Broadband waterfall sets the manual
listening bearing and clears contact-follow focus. The yellow line marks that
bearing. LOFAR and the other analysis plots do not steer the listening beam.

Damage status and team count, available own weapons and airborne helicopter
position are displayed. A hangared or lost helicopter is not plotted as a current
aircraft. Mission/threat/damage alerts are observation-led. Select the sound button
to enable browser tones (synthesized alert and combat-effect cues) and, where
separately host-granted, the live Sonar/Helicopter audio stream; volume and mute
are independent of uConsole audio. There is no continuous own-ship ambience
sound, locally or in the browser.
Autoplay may be blocked by the browser until this gesture. Visual alarms always
remain available. Reconnection establishes a new sound baseline, not alarm replay.

Events are role-scoped: damage reports reach Bridge and Damage Control, threats
reach Bridge, OPZ and Weapons, and mission events reach every role. Proposal
lifecycle events are visible only to their originating session and role. With a
local SimLog grant, a browser receives at most 64 detached diagnostic snapshots.
This explicit read-only capability includes full simulation truth and hidden
entity identifiers; ordinary station state remains observation-bounded.

**Observers.** The host may make at most two paired browsers observers (`F9`
roster key `O`, or the web-host admin page). An observer holds no station
lease and never blocks a crew: it views any station of either unit read-only
(the lobby offers every station with "View"; every control stays disabled and
every command is rejected), receives the SimLog, and reads the ordinary
observation-bounded projection of the station it watches. The grant is
transient (never saved), drops any lease the session held, and the SimLog page
shows observers and the solo host a debrief timeline (recorded snapshots with
marks for own and hostile torpedo launches, own damage, new contacts and
losses; a click scrubs the shown snapshot) plus a JSON export of the recorded
entries that strips RNG, credential, token and settings keys.

A queued response is not an accepted action. If delivery is uncertain, the browser
keeps the action pending. Its explicit reconciliation control retries the same
request ID/envelope, with a five-second cooldown; it never silently sends a new
action or invents success. Stale context or revision conflicts require reviewing
the current picture. The server reports expired queued actions as rejections.

## Web Console and Solo Mode

The browser console is built for a desktop PC with a large monitor, not the
uConsole. It is a dark combat-information-centre layout in one viewport without
page scroll:

- a slim status bar with the station tabs (1-9 select a station, `[`/`]` step
  through the held ones), mission name and phase, mission/world clock, UTC, the
  link state and the settings and help menus;
- an alert band that pulses under the status bar while a new warning from the
  operational log is fresh;
- the instrument (chart, sonar plots, damage schematic, ...) as the centrepiece,
  with docks around it: contacts on the left, the station panel on the right,
  the contact detail below it and the operational log as a drawer under the
  instrument. `,` and `.` collapse or expand the contact and station docks,
  `L` the log; every dock also has its own button.

From 1600 px wide all three columns are open; from 2400 px (2560 px and 4K
monitors) the contact detail gets a fourth column, the station cards flow into
two columns and the helicopter shows its acoustic console beside the map. The
type scales with the screen. The sonar overview shows all six plots from 1800 px.
The guide, lookout and contact library open as overlays above the running
station (`Esc` closes them). Returning to a station already visited repaints
from a cache (map zoom, selection and typed values stay); the first visit to a
station takes one round trip. Narrow windows fall back to a single scrolling
column.

**Solo mode** lets one person run the whole game from one browser while the uConsole
stays the simulation server. Start it with `python main.py --solo-crew` (this launch
only, first private LAN address, never saved) or switch the "Crew mode" row in the
F9 overlay; either way pairing still uses the join code. A solo session holds all
nine frigate stations (or, playing the submarine, the submarine's seven) with command, direct fire, sonar audio and SimLog, only one browser
may pair (a second gets `session_limit` until you remove the first in the roster),
and leases do not lapse. Changing the mode revokes every session and rotates the code.

The solo browser also gets a **game control bar**:
save and load (slots 1-5) and new game (scenario, world, side, difficulty,
optional seed). With side *Submarine* the browser plays the hostile submarine and the
AI hunters sail the frigate, its helicopter and the patrol aircraft. Loading or starting a game replaces the world but keeps the browser
paired; anything it had prepared for the old world fails closed. At the uConsole main
menu the browser shows a start screen. Editors, options, network administration,
quit and credentials stay host-only. With every station leased Autocrew is
suspended for all of them.

## Lifecycle and Limits

Local disable or process shutdown first stops the listener and revokes credentials.
A game-owned hotspot is then removed and the previous Wi-Fi connection is
reactivated. A normal application failure also closes the helper control channel
and triggers that cleanup. Successful load/reset replaces the network session at the next main-thread pump;
pair and grant again. Failed candidate restoration leaves the live network session
unchanged. A new connection never inherits the previous connection's grant.

Clients, workers, histories, projections, and command queues are hard-bounded.
Snapshots normally publish twice per real second, with immediate important
transitions. A browser with an active station also opens the state push
(`/ws/v2/state`, subprotocol `u-jagd-state-v2`, same cookie and Origin rules
as the sonar stream): the host sends that station's projection, byte-identical
to `GET /api/v2/state`, whenever it changes, at most four times per second,
with a heartbeat every 2 s while nothing changes, and only the latest state is
ever queued for a slow client. The browser keeps polling session metadata,
chart and feeds on a slower cadence while the push is healthy; after two missed
heartbeats it is back on its normal polling and retries the push every 10 s.
The push closes on role loss, world replacement and the host's push switch
(`CommanderServer.set_state_push`, never persisted). This is not an
Internet-facing service, VPN product, or remote desktop. See
commander-protocol.md for the exact boundary.

## Abnahme / Pause

Automated coverage uses real loopback HTTP and headless Chromium contracts at
desktop and narrow viewport sizes. This does not establish two-physical-device
network, firewall, headphone, uConsole thermal or readability acceptance.
Follow `docs/plan-0.1.8.md` and `docs/resume.md` for current resumable work.
