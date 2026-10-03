# 10 Submarine {#submarine}

## Overview {#sub-overview}

A second crew can play the submarine on the uConsole or in browsers (the lobby, `F9` or a new game as the submarine). The submarine has seven stations; each order is accepted only from the station that owns it, and an AI fills every free station when the crew assist is on. This chapter gives each station's job and standard procedure; the key table and the submarine's missions are in the reference chapter (*Crewed opposing submarine*).

On the uConsole `1` to `7` switch the stations and pressing the same number again (or `Page Up`/`Page Down`) turns the station's pages. Every station has a key bar at the bottom; a click on a key there, on a lamp or on a dial does the same as the key. The full key table is in the reference chapter (*Playing the submarine on the uConsole*); the browser stations have the same orders as buttons.

| Station | Pages |
|---|---|
| 1 Command | Navigation, Weapons & contacts, Periscope, Threat |
| 2 Sonar | Broadband, LOFAR, DEMON, TMA, Environment, Active (as the frigate's sonar) |
| 3 Weapons | Tubes and fire control |
| 4 Engine room | Plant, Stores, Tanks, Damage |
| 5 Mast & ESM | ESM, Periscope |
| 6 Navigation | Chart & sounder, Navigation, Threat |
| 7 Radio room | Radio |

## Command {#sub-command}

Command sees the whole submarine: chart, navigation, weapons and contacts, the periscope and the threat page. It orders course, speed and depth, lies on the bottom, pings, takes a BT and evades on the freshest alarm.

- **Navigation (page 1):** the chart with the submarine's own contacts and bearing lines, the course, speed and depth dials and the depth bar. `C`, `V` and `D` order course, speed and depth; `U`, `J` and `H` step to periscope, below-layer or deep depth (with `Shift` snorkel and above-layer depth); a click on a dial orders that value.
- **Weapons & contacts (page 2):** the tubes and the contact list as the Weapons station sees them, to follow the attack.
- **Periscope (page 3):** the view through the head at periscope depth with the mast up. `←`/`→` train it, `↑`/`↓` tilt it, `Q`/`E` switch low and high power, `Space` the stabilizer; `Enter` takes a stadimeter range of the sighting under the crosshair and `Ctrl+Enter` fires on the attack computer's solution.
- **Threat (page 4):** the freshest pings, torpedo noises and radar intercepts with their bearings. `I` evades the freshest alarm, `Ctrl+B` clears the baffles, `G` calls action stations.
- In the browser Command also pings and takes a BT; on the uConsole the sonar room does that (`2`, `Shift+A`).

![Submarine command on the uConsole](figure:uboot-command)

![Submarine command in the Remote Crew browser](figure:web-uboot-desktop)

<!-- sop:uboot_command -->

## Sonar {#sub-sonar}

The submarine's sonar room works like the frigate's, without towed array, OPZ release, plot and telegraph. The hull sonar is deaf in the baffles astern.

- The six pages and their keys are those of the frigate's sonar (chapter 2): broadband waterfall, LOFAR lines, DEMON shaft rate, TMA, environment with BT, active pings with `Shift+A`.
- The hull sonar listens at the submarine's own depth: above the layer it hears surface ships well, below it it is shielded from them. Astern lies the deaf baffle sector, so ask Command for a baffle clearing now and then.

![Submarine sonar](figure:uboot-sonar)

![Submarine sonar in the Remote Crew browser](figure:web-uboot-sonar-desktop)

<!-- sop:uboot_sonar -->

## Weapons {#sub-weapons}

Weapons loads and floods the tubes, sets run depth and salvo, fires at a selected contact or down an entered bearing, steers the wired torpedoes and launches decoys. The fire-control box shows the seeker setting of the next shots.

- **Tubes:** each tube is empty, loaded (dry) or flooded; only a flooded tube fires. `M` loads the next empty tube, `Ctrl+M` floods the next loaded one slowly (60 s, hardly audible), `Shift+M` fast (20 s, loud).
- **Fire control:** `↑`/`↓` pick a contact with a fresh range, `T` sets the run depth, `Y` single shot or two-torpedo spread, `X` the seeker pattern and `,`/`.` the enable point; `Ctrl+Enter` fires. `F` fires down an entered bearing and distance without a contact.
- **Wire and decoy:** `W` steers the newest wired torpedo onto a new bearing, `Shift+W` cuts its wire; `V` launches a decoy.

![Submarine weapons](figure:uboot-weapons)

![Submarine weapons in the Remote Crew browser](figure:web-uboot-weapons-desktop)

<!-- sop:uboot_weapons -->

## Engine room {#sub-engine}

The engine room runs the telegraph, snorkel and charge rate, silent running, the trim tanks and the emergency blow, keeps the air breathable and leads the damage-control teams.

- **Plant (page 1):** telegraph (`+`/`-`), silent running (`A`, at most 5 kn), snorkel (`N`) and the battery, diesel and motor readings.
- **Stores (page 2):** battery, fuel, carbon dioxide and oxygen. `R` cycles the snorkel charge rate (full, half, air only), `Shift+O` fits a fresh absorber set, `O` lights an oxygen candle.
- **Tanks (page 3):** regulating and trim tanks. `↑`/`↓` pump out or flood the regulating tank, `←`/`→` move trim water, `Z` switches the automatic trim; `Shift+B` is the one emergency blow.
- **Damage (page 4):** the compartments with water, leaks, fire and gas. `↑`/`↓` pick a compartment, `←`/`→` a task, `Enter` sends team 1 (`Shift+Enter` team 2), `I` shuts or opens its bulkheads; `W`, `M` and `U` relieve the watch, send the medical team and re-man the worst-hit station.

![Submarine engine room](figure:uboot-engine)

![Submarine damage control (engine room, page 4)](figure:uboot-damage-control)

![Submarine engine room in the Remote Crew browser](figure:web-uboot-engine-desktop)

<!-- sop:uboot_engine -->

## Mast & ESM {#sub-esm}

Mast & ESM raises the mast at periscope depth, listens for radars on the ESM rose, classifies the emitters, plots cross-fixes and looks through the periscope.

- **ESM (page 1):** with the mast up (`P`, only at periscope depth) the rose shows every radar heard with its bearing and level. `↑`/`↓` pick an emitter, `←`/`→` classify it from the library (an annotation, never the truth), `Enter` puts its cross-fix or bearing line into the submarine's plot. A main-beam hit means the radar may already see the mast.
- **Periscope (page 2):** the same periscope as Command's page 3, without the shot.

![Mast & ESM](figure:uboot-mast-esm)

![Mast & ESM in the Remote Crew browser](figure:web-uboot-esm-desktop)

![Periscope by day](figure:uboot-periscope-day)

![Periscope at night](figure:uboot-periscope-night)

![Periscope in the Remote Crew browser](figure:web-periscope-day)

<!-- sop:uboot_esm -->

## Navigation {#sub-nav}

Navigation orders course and depth, watches keel and shoals on the pilot chart and the echo sounder, keeps the dead reckoning and steers the route.

- **Chart & sounder (page 1):** the pilot chart around the submarine with soundings, shoals and land, the echo sounder with water under the keel and the DR position lamp. A left click orders the course to that point.
- **Navigation (page 2):** the tactical chart as on Command's page 1; a right click adds a route waypoint, `W` lays a zigzag or expanding-square search, `Backspace` clears the route.
- **Threat (page 3):** as Command's threat page; `I` evades, `Shift+G` lies on the bottom in shallow water.

![Submarine navigation](figure:uboot-navigation)

![Submarine navigation in the Remote Crew browser](figure:web-uboot-nav-desktop)

<!-- sop:uboot_nav -->

## Radio room {#sub-radio}

The radio room copies HQ's broadcasts, reads HQ's orders and contact reports and sends situation reports.

- The page shows when HQ's next broadcast comes, whether the antenna is up (mast `P` at periscope depth, or the towed buoy antenna `B` down to 60 m at 6 kn or less), HQ's orders and contact reports and the log.
- `Enter` sends a situation report; it needs the mast up, and the frigate can take an HF bearing on it.

![Submarine radio room](figure:uboot-radio)

![Submarine radio room in the Remote Crew browser](figure:web-uboot-radio-desktop)

<!-- sop:uboot_radio -->

## Dead reckoning and route {#sub-dead-reckoning}

- Dived, the submarine knows its position only by dead reckoning. The navigated position drifts from the true one by a steady set of up to 0.4 kn that log and gyro cannot see (a nuclear submarine's inertial navigation drifts 0.3 times as much), plus a small random walk once a minute; the error stays below 8 NM.
- The crew's chart (coast, soundings, hazards, mission goal, HQ's reports and the route) is drawn where the navigator believes it lies against the submarine. The submarine itself, its own sonar contacts and own torpedoes stay where the submarine measures them.
- A GPS fix: mast up at periscope depth for 20 s puts the navigated position back on the true one. The **DR position** lamp on the Chart & sounder page shows the navigator's own error estimate and the minutes since the fix, or the fix being taken.
- The chart check ahead and the route steer from the navigated position, so an old fix can lead the submarine into water the chart calls clear.
- The route: a right click on the chart adds a waypoint (at most 8), `W` lays a zigzag or expanding-square search from the submarine and steps to off, `Backspace` clears it. Any course order from the helm or an evasion ends the route; a baffle clearing has the helm while it runs. In the browser **Set waypoints on chart** turns clicks on the chart into waypoints.

## Torpedo seeker {#sub-seeker}

- `X` steps the search pattern of the next shots: straight (as before), snake, circle or helix. The torpedo runs straight to the datum; once its seeker is on and it has found nothing, it searches in that pattern.
- `,` and `.` move the enable point between 0.6 and 3.0 NM before the datum in 0.2 NM steps (default 3.0 NM). A late enable point keeps the seeker blind longer, so decoys and other ships on the way are not taken.
- A torpedo in the water keeps the settings it was fired with; the browser's Weapons card sets both with **Apply**.

## Surfacing and crash dive {#sub-surface}

- `Shift+H` (browser: **Surface**, Command or Navigation) orders the submarine up to the surface. At 2 m or less it is surfaced: the low-pressure blower empties the main ballast within 2 minutes (no bottle air), the hatch is open and the submarine airs itself.
- Surfaced, the diesels (`N`) run in the open air: up to 12 kn (or the submarine's top speed) instead of 6 kn on the snorkel, and the generator gives 1.3 times its snorkel power, so the battery charges faster.
- The bridge watch looks out from 6 m instead of the periscope's 2.5 m and sees farther; its reports read **Bridge:** and an aircraft is called as an alarm. The scope page shows the bridge watch's view.
- The enemy sees a surfaced submarine too: the frigate's surface radar and the radars of helicopter and patrol aircraft see hull and conning tower (ten times a mast's echo), and lookouts see it by eye.
- `H` from the surface or with blown tanks (browser: **Crash dive**) is the crash dive: alarm, masts and snorkel down, vents open, full ahead, ordered depth 40 m. Blown tanks hold the submarine above 10 m until the vents have flooded them (up to 40 s), and the flooding vents are a transient the enemy may hear. From deeper than 12 m a crash dive is refused.

## Not modelled {#sub-limits}

- No position fixes from landmarks, soundings or stars; only GPS clears the dead-reckoning error.
- The plot keeps its marks where they were drawn against the submarine; it does not move with a fix.
- No separate control room or diving officer station; trim and ballast stay with the engine room.
