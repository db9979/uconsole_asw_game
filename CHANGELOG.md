# Changelog

[Deutsches Änderungsprotokoll](CHANGELOG.de.md)

Every U-Jagd release, newest first. The [README](README.md) shows only the latest one.

## 1.3.53

Release 1.3.53 gives the OPZ correlation suggestions. When two of the ship's
own sensors (sonar, radar, ESM, lookout) report a contact on the same bearing
within their uncertainty (and, where both have positions, close together), the
OPZ offers the pair for fusion: on the uConsole up to two suggestions stand in
the page 1 sidebar, `U` fuses the top one and `Shift+U` dismisses it; the
Remote Crew OPZ lists up to four with Fuse and Dismiss buttons. Suggestions
only compare published reports no older than 30 s; nothing is fused without
the operator. Saves stay v28.

## 1.3.52

Release 1.3.52 gives the frigate an autopilot route. On the Bridge a right
click on the chart adds a waypoint (up to 8), `W` starts a search pattern from
the ship's position and course (a zigzag of 3 NM legs, then an expanding
square) and `Backspace` clears the route. The helm steers for each waypoint in
turn, counts it reached within 0.3 NM and holds its course after the last one;
speed stays with the telegraph, and any helm order takes over. The chart shows
the route with numbered waypoints, and the Remote Crew bridge has an
"Autopilot route" card with the same patterns and a chart mode for setting
waypoints. Saves are now v28 (they keep the route); v27 saves no longer load.

## 1.3.51

Release 1.3.51 lets the AI hunters use the frigate's ESM. When the frigate has
no position on the submarine, an ESM intercept of a mast radar now gives the
search line: the library must rank a submarine radar among its three best
matches and no ship the frigate tracks by radar or AIS may lie within 10° of
the bearing. It competes with the HF/DF bearings by age and stays a datum for
5 minutes, so a submarine that radiates at periscope depth draws the frigate,
its helicopter and the patrol aircraft down that bearing. Saves stay v27.

## 1.3.50

Release 1.3.50 adds a guard against frozen Remote Crew browsers. A new test
plays two busy missions (the frigate with the autocrew on every station
against the AI submarine, and a crewed submarine with its radio, threat
picture and HQ tasks filled), publishes every station's state and chart for
both units and runs the browser's own validators over all of them in Node. A
field the browser would refuse, as in 1.3.44, now fails the tests before a
release. Nothing changes in play. Saves stay v27.

## 1.3.49

Release 1.3.49 lets Remote Crew browsers follow a host update by themselves.
The host now names its version on every reply and in the page it serves; a
browser page that is still open from before an update reloads itself once and
so always runs the web client that matches the host, instead of freezing on
data it cannot read. Saves stay v27.

## 1.3.48

Release 1.3.48 adds an autosave. A running mission is saved every 5 minutes
and when you quit or leave it for the main menu, to `~/.u-jagd/autosave.json`
beside the five slots. The main menu then starts with "Continue mission",
which resumes it exactly; after a crash it holds the last 5-minute save. The
file is written in the background so the uConsole does not stutter. A mission
that ends and any new mission delete the autosave. Saves stay v27.

## 1.3.47

Release 1.3.47 puts a phone on watch. `F9` shows a second QR code, Phone
lookout: scan it, accept the game's own certificate once, type the pairing code,
and the phone becomes the frigate's bridge lookout or the crewed submarine's
periscope. Turn the phone like binoculars (gyroscope) or swipe, zoom, and report
what you see by voice ("Ship bearing 040, range 5 miles") or by tapping it. The
bridge only hears what the lookout really has there; a report of nothing is
refused. While a phone holds the watch the automatic lookout stays silent, and
the crew browsers speak every confirmed report. The phone on the periscope
trains it and takes stadimeter ranges. The listener serves this page over HTTPS
on the next port (self-signed, made by the game), because phones only give the
gyroscope and the microphone to a secure page; saves stay v27.

## 1.3.46

Release 1.3.46 redraws the bridge's small weather picture in the start screen's
look: it now looks into the wind with the sky of the hour (sun, moon and stars),
the clouds, rain, snow or fog and the sea running at the eye, and a turquoise
wind rose in its corner, framed by the corner brackets of the other views. Both
on the uConsole and in the Remote Crew browser; saves stay v27.

## 1.3.45

Release 1.3.45 keeps the sky still in the periscope and the lookout's
binoculars: clouds, stars, the sun and the moon stay in place while the sea and
the horizon roll with the swell. From dusk to dawn and in poor visibility
neutral ships run their navigation lights as the collision regulations lay
down: white masthead lights, the red or green side light for the side you see,
the white stern light from astern, each within its range, and the all-round
lights of vessels at work (trawler, pilot, survey ship and cable layer, mine
clearance), and civil aircraft their wingtip, tail and flashing anti-collision
lights; the ship's bow points the way its lights show, and a lit ship is sighted by its lights in the dark.
Warships and military aircraft run dark. The sea follows the wind: into it the
crests come at you, down-sea they run away, across it they run sideways, and
the ship pitches in head seas and rolls in beam seas. The binoculars and the
periscope now tilt up and down, zoom (binoculars 16°, 8°, 4°; periscope low and
high power) and have a horizon stabilizer. Both on the uConsole and in the
browser; saves stay v27.

## 1.3.44

Release 1.3.44 fixes Remote Crew browsers that froze with "Host sends data
this browser cannot read". Four lists named a row's type with a field the
browser refuses in every station state: the submarine's radio log, its threat
intercepts and evasion order, and the frigate radio room's HQ tasks. As soon as
the first broadcast was copied, a ping or torpedo was heard or HQ offered a
task, the station picture stopped and actions were locked. These rows now send
the field as `type`; a new test catches such a field without Chromium. After
updating the host, reload the browser page once so it loads the new web
client. Saves stay v27.

## 1.3.43

Release 1.3.43 keeps only the newest release on GitHub: after publishing a new
version the Windows workflow deletes every older release (their git tags stay).
The Windows starter and the uConsole updater read only the latest release.
Saves stay v27.

## 1.3.42

Release 1.3.42 keeps only the newest release on GitHub: after publishing a new
version the Windows workflow deletes every older release (their git tags stay).
The Windows starter and the uConsole updater read only the latest release.
Saves stay v27.

## 1.3.41

Release 1.3.41 brings back the full top bar on the uConsole: the frigate shows
the station, the mission, the clock, speed and course again, and the crewed
submarine shows the mission, the clock, speed, course and depth, now compactly
separated by "·". Saves stay v27.

## 1.3.40

Release 1.3.40 adds a bug report. "Report a bug" in the main menu writes
`~/.u-jagd/bug-report.txt` with version, platform and the newest lines of the
crash log (your user name removed from paths) and shows a QR code that opens a
prefilled GitHub issue on a phone; `Enter` opens it with the log in a browser
where the device has one. After a crashed start the main menu offers it. The
Windows starter and the browser settings menu link to the same issue form, and
the crash log now also records each mission start. Nothing is sent until you
submit the issue with your own GitHub account. Saves stay v27.

## 1.3.39

Release 1.3.39 gives the periscope, the lookout's binoculars and every station
the start screen's look. The eyepieces show day, dusk and night with stars, the
moon in its phase and its glitter on the water, clouds, rain, snow and fog from
the weather, and the ships in steel with a lit rim, lit windows at night, bow
wave and wake. The Remote Crew bridge gets the lookout's binoculars as a card
and the browser periscope the same picture and silhouettes. uConsole and
browser stations use the turquoise phosphor and night blue of the start screen
with corner brackets on the panels; the chart keeps its NATO symbols and the
high-contrast theme is unchanged. Saves stay v27.

## 1.3.38

Release 1.3.38 lets the uConsole charts zoom much further in. `Q`/`E` now
step through fixed chart heights of 500, 250, 100, 50, 25, 10, 5, 2, 1 and
0.5 NM on the bridge, weapons, helicopter and submarine charts, and the mouse
wheel zooms smoothly down to 0.5 NM; the operations centre chart goes down to
a 0.25 NM radius. The grid gets finer as you zoom (down to 0.1 NM, with
decimal labels), the scale line shows fractions, and coastlines and radar
rings are clipped so strong zoom stays fast. Saves stay v27.

## 1.3.37

Release 1.3.37 fixes a crash that closed the game as soon as a frigate or
AI torpedo was in the water while the simulation log (Options, Simulation log) was
recording: the log's state snapshot read a torpedo number the torpedo does
not have. The crash log added in 1.3.34 showed the cause. Saves stay v27.

## 1.3.36

Release 1.3.36 fixes sonar audio on the uConsole that could fall silent until
audio was switched off and on in the options. A rare race in the pygame mixer
could leave the sonar channel idle with its next block queued forever, and
the sonar playback waited for that queue slot for good. Playback now replays
such a stranded block and carries on, and a stopped sonar audio worker is
restarted with the next block. `audio_debug.log` counts both
(`queue_stranded`, `worker_restarts`). Saves stay v27.

## 1.3.35

Release 1.3.35 puts less text on the uConsole screens. The top bar names only
the station and the clock, the chart header only its scale. The sonar loses its
header status chips and legend lines and keeps one row of four main keys (the
rest is in F1); a towed or variable-depth array shows its state only while it
is moving or not ready. The submarine's threat box appears only while a threat
is fresh, then an amber triangle next to the clock marks standing warnings.
Courses read in whole degrees with °, and the turn radius shows only in a turn.
The TMA header no longer overlaps, and the submarine's Weapons tab, tube line
and alarm lines are no longer cut off. Saves stay v27.

## 1.3.34

Release 1.3.34 writes a crash log: every game start adds a start and an end
line to `~/.u-jagd/crash.log`, and a game that ends on an error leaves its
traceback there, or after a hard crash (a segmentation fault in SDL or audio,
`SIGTERM`) the stacks of all threads. A start line with no end line means the
game was killed from outside, usually by the kernel when memory ran out. The
file stays below 256 KiB. Saves stay v26.

## 1.3.33

Release 1.3.33 lets the crewed submarine's ESM measure each radar's scan
period, the time between its main-beam hits: a search radar reads rotating
with its period (about 2.5 s for navigation and surface search, 5 s for air
search), a tracking or fire-control radar reads steady. A steady beam on the
mast is always a mast warning and is reported in the log; the uConsole's Mast
& ESM page and the browser show the reading. Saves are now v27.

## 1.3.32

Release 1.3.32 adds directional hearing: with stereo sound, detonations,
returning echoes and another platform's active ping come from the bearing they
were heard on, left for port and right for starboard of the frigate's or the
crewed submarine's head, on the uConsole and in the Remote Crew browser. The
frigate now also plays a submarine's ping itself, and the crewed submarine
hears a hunter's ping ring on its hull.

## 1.3.31

Release 1.3.31 gives the crewed submarine real torpedo tubes: the torpedo gang
loads each empty tube from the racks (`M` at the Weapons station, or Load in
the browser), and a loaded tube must be flooded before it fires, which takes
20 s and can be heard (`Shift+M`, or Flood). Every submarine now carries as
many reloads again as it has tubes, reloaded in 2 to 4 minutes; the AI's
submarines keep loading and flooding by themselves. Saves are now v26.

## 1.3.30

Release 1.3.30 lets the **frigate play the submarine missions against the AI**:
an uncrewed mission submarine now pursues its objective instead of
patrolling. It runs below the layer for the breakthrough goal, follows HQ's
contact reports and comes to periscope depth to sight and report the
frigate, and in the convoy attack runs ahead of the convoy and torpedoes its
merchants one at a time. Saves stay v25.

## 1.3.29

Release 1.3.29 names the submarine consistently: every screen, the web
clients, help and manual now say **submarine** (German **U-Boot**) where they
used to say just "boat", for example the **Submarine campaign** and the
submarine missions. Saves stay v25.

## 1.3.28

Release 1.3.28 makes the **AI hunters smarter**: the OPZ marks the bare radar
blip of a raised mast or snorkel, and a mast track, an HF/DF cross-fix or an
HQ submarine datum report now becomes the hunt's datum. A fresh fix from the
ship's own sensors goes over the datalink to a friendly AI warship with
ASROC in range. Saves are now v25 (radar blips and marks).

## 1.3.27

Release 1.3.27 sorts the boat's **ESM library by fit**: the emitters whose
published ranges hold a measurement are listed best fit first (frequency and
PRF near the middle of their ranges, the same modulation), each with a grade
of good, fair or poor on the uConsole and in the browser, so a well-fitting
radar such as the helicopter's no longer drops off the list. Saves stay v24.

## 1.3.26

Release 1.3.26 skips the update check on the uConsole when there is no
internet: a connection test to GitHub decides within 2.5 seconds, and the game
then starts right away instead of waiting on timeouts. Stalled git downloads
give up after at most 60 seconds. Saves stay v23.

## 1.3.25

Release 1.3.25 tidies up the documentation. Gameplay is unchanged and saves stay
v24.

## 1.3.24

Release 1.3.24 brings **atmosphere to the crewed boat**: the pressure hull creaks
deep down and cracks when it fails, detonations in the water are heard close
aboard or far off and logged with a bearing, and **silent running** rigs the
boat's screens for dimmed red light on the uConsole and in the browser. The
boat's browsers now play its own sound cues, and a rescue task's alarm cue no
longer upsets the browser. Saves stay v24.

## 1.3.23

Release 1.3.23 gives every menu and dialog the start screen's look: help,
options, save/load, quit, nations, Remote Crew administration (`F9`) and the
mission end now show the night hunt behind a translucent console panel with
phosphor corner brackets and a glowing title, while the mission keeps running
behind them. In high contrast the panels stay opaque. Browser dialogs use the
same night sky and bracket frame. Saves stay v24.

## 1.3.22

Release 1.3.22 makes the Remote Crew streams steadier. A browser that
reconnects its sonar audio or sonar display stream now takes over its own
previous stream at once instead of being refused while the host had not yet
noticed that the old connection was gone. The web client no longer sends an
extra state request for every pushed state. The browser tests for live audio
and the state push now run in real time next to the host. Saves stay v23.

## 1.3.21

Release 1.3.21 lets the crewed boat go **below its test depth**, down to crush
depth (1.5 x test depth), at a growing risk: sheared bolts, failed shaft or
valve seals and, deeper, a cracked pressure hull flood compartments and add
damage, far more often the deeper the boat goes; at crush depth the hull
collapses. The depth columns mark the crush depth and a red alarm shows while
the boat is below test depth. Saves stay v24.

## 1.3.20

Release 1.3.20 adds the boat's **periscope attack computer**: every stadimeter
reading is a mark, and two or more marks a minute apart give the target's
course and speed, the lead angle and the torpedo's running time under the
periscope (browser: Solution column). `Ctrl+Enter` on the periscope page
(browser: Fire on solution) fires on the intercept course; a shot at a marked
sonar contact uses the solution too. Saves move to **v24** (the marks are
saved); v23 saves are no longer loaded.

## 1.3.19

Release 1.3.19 makes the uConsole start visible at once: a small start window
shows whether the launcher is checking for, downloading or installing an update
and closes when the game appears. A second start while U-Jagd is starting or
running no longer opens the game twice; it shows "U-Jagd is already running."
instead. Saves stay v23.

## 1.3.18

Release 1.3.18 adds an **A4 poster** in German and English (PNG at 300 dpi
and PDF) in `docs/poster/`: the start-screen scene, a short description of the
uConsole and Windows versions, four screenshots and QR codes for the download
and the support page. `tools/build_poster.py` renders it again from the
current scene and screenshots. The game itself is unchanged; saves stay v23.

## 1.3.17

Release 1.3.17 fixes the Windows program's self-update: after swapping in the
new `U-Jagd-Windows.exe` it failed to start ("Failed to load Python DLL")
because it inherited the old process's already deleted unpack directory. The
restart now unpacks afresh. The starter window also shows the "Buy me a
coffee" link. Saves stay v23.

## 1.3.16

Release 1.3.16 adds the **boat campaign**: five linked boat missions in one sea
area (reconnaissance, breakthrough, convoy attack, breakthrough, convoy
attack), chosen with `Tab` on the campaign screen. The boat carries its
torpedoes, hull damage and standing with U-boat command from mission to
mission; at its base it takes a full refit or a quick turnaround. Kept in
`~/.u-jagd/boat_campaign.json`; saves stay v23.

## 1.3.15

Release 1.3.15 adds boat mission 7, **Convoy attack**: the frigate escorts four
merchants and the submarine must sink two of them. Only the crewed boat's
torpedoes take a merchant; the AI frigate keeps station ahead of the convoy
and prosecutes contacts only near it. The boat's orders count the merchants
sunk. Saves stay v23.

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
