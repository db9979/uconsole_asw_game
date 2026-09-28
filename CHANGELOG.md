# Changelog

[Deutsches Änderungsprotokoll](CHANGELOG.de.md)

Every U-Jagd release, newest first. The [README](README.md) shows only the latest one.

## 1.3.14

Release 1.3.14 adds **boat missions**: scenario 5 *Breakthrough* (the submarine
must reach a goal area beyond the frigate's patrol position) and scenario 6
*Reconnaissance* (it must sight the frigate through the periscope and radio a
situation report while it is in sight). The frigate's task is to stop it. The
boat's orders stand over its chart and in the browser's boat stations; the
goal is marked on the boat's chart. Saves stay v23.

## 1.3.13

Release 1.3.13 renders the uConsole screenshots after three simulated
minutes instead of six seconds, so waterfalls, plots and contact lists are
filled, and shows the Mission Editor with the packaged example mission (library
and seeded sector preview) instead of an empty library. The README now links
the menu and editor views too. Saves stay v23.

## 1.3.12

Release 1.3.12 refreshes the screenshots in the README from the current game
(the uConsole at 1280 x 720, including the crewed submarine's stations, and the
Remote Crew browser in Chromium) and moves the release history into
[CHANGELOG.md](CHANGELOG.md), so the README shows only the latest release.
`tools/capture_screenshots.py` and `tools/capture_commander.py` regenerate
every image. Saves stay v23.

## 1.3.11

Release 1.3.11 adds a **Windows program**: `U-Jagd-Windows.exe` starts the game
as Remote Crew server (crew or solo mode, optionally as the submarine), shows
the browser address, join code and QR code, and offers each newer release
itself. GitHub Actions builds it on every push to `main` and publishes it as
release `v<version>`. The game also gains `--remote-crew` (crew-mode Remote
Crew on the first private LAN address at launch) and `--status-file`. See
[Windows program](README.md#windows-program). Saves stay v23.

## 1.3.10

Release 1.3.10 fixes the uConsole installer on a checkout that is older than
the installer itself: it now fast-forwards that checkout to `main` first
instead of stopping with a missing `u_jagd_updater.py`.

## 1.3.9

Release 1.3.9 adds a one-command installer for the uConsole with automatic
updates: every start fetches the newest GitHub release (a background timer also
checks every six hours), offline the installed version starts, and a version
that does not start is rolled back. It creates a menu entry, a desktop shortcut
and the `u-jagd` command. Saves stay v23.

## 1.3.8

Release 1.3.8 adds a support link: a QR code in the uConsole main menu and a
small link on the Remote Crew pairing, lobby and settings screens and the
web-host admin page, never over a running station. It also brings the guides
up to date: the reference and README list the VDS and 31 kn, the README's
mission-editor limits match the runtime, and the co-op and protocol guides
cover the solo side choice, the submarine roles and the admin shutdown.
Saves stay v23.

## 1.3.7

Release 1.3.7 gives the frigate F-217 its real 31 kn top speed (FLANK). The
brake power is scaled so drag, acceleration and turning up to 25 kn stay as
before; self-noise now rises up to 31 kn and the Nixie's cable still parts
above 25 kn. The web-host admin page gets **End game now**, which stops the
server process after a confirmation so it does not keep running in the
background. Saves stay v23.

## 1.3.6

Release 1.3.6 redraws the start screen as an animated night hunt: the
frigate F-217 with turning radar, funnel smoke, bow wave and towed array,
the helicopter with its dipping sonar, and a submarine below the layer that
lights up when the hull sonar's pulse reaches it, with the author and the
version on the title. The same scene, dimmed, lies behind the main menu.
The silhouettes in the periscope and the bridge binoculars now show
detailed class profiles (frigate, container ship, small craft, helicopter)
that pitch with the sea, turn their radar and rotors and trail a bow wave
and wake. In Remote Crew solo mode the New Game dialog picks the side:
the frigate or the submarine, which the AI hunters then chase. Saves stay
v23.

## 1.3.5

Release 1.3.5 adds AI hunters: when nobody sails the frigate (the uConsole
plays the boat, or a solo browser plays the submarine), the frigate, its
helicopter and the patrol aircraft hunt the boat from the frigate's own
sensors, on every frigate station no browser holds. Saves stay v23.

## 1.3.4

Release 1.3.4 gives the frigate a variable-depth sonar (VDS) as a third
array beside the hull sonar and the towed array: `Shift+Y` lowers or
recovers the towed body (3-15 kn, sea state up to 5, lost above 24 kn),
`U`/`V` set its depth (20-300 m) while it is the selected array, and it
listens and pings from its own depth, below the layer when lowered there.
It resolves the towed array's left/right ambiguity like the hull sonar.
Remote Crew sonar gets the same controls. Saves move to format v23 (the
VDS state).

## 1.3.3

Release 1.3.3 paints the Remote Crew browser waterfalls (LOFAR, DEMON,
broadband) in a background worker through `OffscreenCanvas` where the browser
offers it, so the page's main thread and the live sonar audio on it no longer
run the per-cell raster loop; other browsers keep the previous path. Saves
stay v22.

## 1.3.2

Release 1.3.2 lets the Mission Editor pick a mission's reference world from a
list of the 128 packaged sectors (with their countries) instead of typing
`sector:<n>`, and its preview draws the chosen sector's coast. Saves stay v22.

## 1.3.1

Release 1.3.1 gives the crewed submarine a radio room (a seventh boat
station: HQ's broadcast with a contact report on the frigate, and situation
reports the frigate's HF direction finder can bear) and lets the boat's ESM
hear the frigate's helicopter and the patrol aircraft by their own catalogued
search radars. Saves move to format v22 (the radio room's state).

## 1.3.0

Release 1.3.0 widens the simulation and the crew's tools without moving the
1.0.0 balance (77 calibration metrics still match): a second lightweight
torpedo type with search patterns, enable point and salvo spread; hostile
submarines that fire only once their own target-motion analysis has
converged; counter-flooding, longitudinal trim and plant selection aboard;
helicopter sonobuoy patterns and a MAD run; convergence zones from the
measured sound-speed profile with Ekelund and dot-stack TMA; a periscope
with visual sightings, a stadimeter and diesel noise while snorkelling for
the crewed submarine; anti-aliased chart lines, the chart's light of the
hour, a weather hatch and a shared horizon renderer; a WebSocket state push
for Remote Crew with a generated schema allowlist; a read-only observer
role, a debrief timeline with JSON export and voice on by default; and a
mission runtime that takes the editor's scope (reference sectors, protect
and reach objectives, random groups, timed events, authored weather, placed
aircraft, animals and decoys). The core is split into mixins and the test
suite runs in parallel. **Saves are format v23 (the variable-depth sonar, the crewed boat's radio room, HQ radio tasks, the crew's watch bill, fatigue and morale, the on-call patrol aircraft, the crewed boat's compartments and damage control, its tanks, trim and high-pressure air, its ESM picture,
submarine diesel, charge rate and air stores, crewed-boat crew state, periscope
sightings, weapon settings, mission events, foreign pings still travelling to
the frigate); older saves are rejected.**

## 1.2.0

Release 1.2.0 tightens the game flow and the hand-over between stations: the
`Esc` dialog and the mission-end screen return to the main menu (`M`), `R`
restarts an editor mission as itself, convoy missions announce the remaining
time as progress, and an Operations fusion built from one sonar contact can be
designated to Weapons, with its classification and affiliation applying to fire
control (FRIEND/NEUTRAL on a fusion blocks every torpedo shot). Saves stay v14.

## 1.1.0

Release 1.1.0 replaces the remaining kinematic shortcuts with physical models
while keeping the 1.0.0 gameplay balance (checked by a calibration harness):
force-based own-ship hydrodynamics and seakeeping; a time-varying ocean with
tides, mixed layer, sediments and wrecks; passive/active sonar equations with
ray-traced propagation; towed-array left/right ambiguity, Doppler and a
covariance TMA; submarine and torpedo physics (energy, fins, wire, proximity
fuze); decoy discrimination; compartment flooding, stability, fire and repair
logistics; the radar equation with a rotating antenna, ESM amplitude, HF
propagation and a moonlit lookout; and missile flight physics with chaff
clouds, CIWS ballistics, pop-up raiders, helicopter hover/deck limits and
drifting buoys. Hostile submarines now need their own TMA before they know
your range. The Remote Crew v2 protocol is unchanged apart from new ELOKA
intercept fields.
See [docs/simulation-gaps.md](docs/simulation-gaps.md) for the full record.

## 1.0.0

Release 1.0.0 splits every workstation into two tabbed sub-pages, adds manual
CIWS and FLAK release authorization alongside the existing automatic gates,
and gives the autocrew bridge ASM/torpedo evasion and grounding-avoidance
behavior. TMA re-solves now use hysteresis against near-tied bearing
solutions, and inbound anti-ship missiles carry a terminal-active radar
seeker that gives an ESM/RWR warning before search radar acquires them. A
consolidated theme system adds an optional high-contrast, colorblind-safe
palette. Save format v11 and the Remote Crew v2 protocol are unchanged.
