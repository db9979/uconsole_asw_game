# Reference data {#reference}

All values are the defaults of the current game version. Custom difficulty and missions can change stocks and time limits.

## Units {#ref-units}

| Quantity | Unit |
|---|---|
| Distance, range | nautical miles (NM) |
| Speed | knots (kn) |
| Depth | metres (m) |
| Frequency | hertz (Hz) |
| Course, bearing | degrees true, 000 = north, clockwise |
| Time | simulation seconds; 1x only |

## Sensors {#ref-sensors}

| Sensor | Range | Accuracy / note |
|---|---|---|
| Passive sonar (base) | 20 NM | bearing only; HMS +/-6 deg, TAS +/-2 deg |
| Active ping | 18 NM (reference target, broadside-quarter aspect) | CW or LFM (`W`); range accuracy from pulse and SNR, depth +/-12 m; 30 s cooldown; heard to 60 NM |
| Dipping sonar | 18 NM passive / 14 NM active | +/-2 deg |
| Sonobuoy | 8 NM | 60 min battery |
| Surface radar | 30 NM (50 % per sweep) | 4 s antenna revolution; radar horizon; no submerged contacts |
| Air radar | 100 NM (50 % per sweep) | aircraft and missiles; jammers burn through close in |
| ESM | 150 NM (main beam) | +/-3 deg bearing; level and range estimate |
| HFDF | 120 NM ground wave at 15 MHz (about 95-150 NM by frequency) | +/-8 deg bearing (sky wave +/-16) |
| Lookout | 12 NM surface, 5 NM surfaced sub, 20 NM air, 20 NM land | x0.25 (new moon) to x0.45 (full moon) at night; fog and sea state reduce; class at 2, type at 3.2 resolved cycles over relative size (tanker about 7/5 NM, frigate 5/4 NM, speedboat 3/2 NM by clear day) |

## Weapons and countermeasures {#ref-weapons}

| System | Data |
|---|---|
| Frigate torpedo | 45 kn, 12 NM (battery), wire-guided (ship <= 20 kn, <= 1.5 deg/s, 5 NM spool), 2 tubes, 60 s reload, depth 10-300 m, proximity fuze |
| Helicopter torpedo | 55 kn, 12 NM, 2 per sortie, no wire |
| Hostile torpedo | 28 kn, 30 NM, homes from 3 NM |
| Nixie towed decoy | 2 per mission, 600 s, 0.2 NM cable (10 m at 15 kn, deeper when slower, parts above 25 kn), 60 s reload |
| ESSM | 6 missiles, 30 NM, 2 fire channels |
| CIWS | 1.5 NM, 180 rounds, needs release; 115 deg/s slew, own track radar inside 3 NM |
| AA gun | 240 rounds, needs release |
| Chaff | 6 rounds, 8 NM, 40 % break-lock when bloomed; cloud drifts with the wind for 90 s |

## Own ship {#ref-ship}

| Item | Value |
|---|---|
| Speed | 4-25 kn; telegraph STOP 0, SLOW 6, HALF 10, FULL 16, FLANK 25 kn |
| Turn rate | about 0.075 deg/s per knot (1.2 deg/s at 16 kn); turning circle about 0.4 NM |
| Cavitation | from 15 kn in calm water, earlier in heavy seas; passive range x0.35 |
| QUIET mode | noise x0.65, max 12 kn |
| TAS handling | 3-12 kn, stream 360 s, recover 480 s, fault above 20 kn |
| TAS depth | 20-260 m, minus 4 m per knot |
| Damage | 9 compartments, 3 teams (about 20 s walk per compartment), 8 patch kits; sinks beyond reserve buoyancy, capsizes at 35 degrees heel or lost GM |

## Environment {#ref-environment}

| Process | Model |
|---|---|
| Tide | M2 (12.42 h) + S2 (12 h), 0.4-1.4 m amplitude, larger in shallow water |
| Surface layer | seasonal base depth; about 8 m shallower in the afternoon; deepens in wind above 12 kn; internal waves +/-6 m |
| Sound speed | Mackenzie equation from the temperature profile (sea surface 8-18 deg C by season) |
| Current | steady field up to 1 kn plus 3 % of the wind, 20 deg right of downwind |
| Seabed | rock, gravel, sand, silt or mud; affects bottom reflection |
| Hazards | up to 64 charted wrecks and submerged rocks (tops at least 15 m deep), shown on every chart (wreck: hull line with masts, rock: asterisk; depth of the top when zoomed in, details in the tooltip); both raise the seabed within their footprint and are obstacles for the ship, submarines and weapons |
| Atmosphere | barometer 975-1025 hPa that falls ahead of rising seas; air temperature from the sea, season, day and cold northerly winds (below 0 deg C in winter storms: snow, icing); gusts; cloud ceiling; sun elevation with civil/nautical twilight; moon phase |
| Rain lens | rain freshens the top few metres (up to -1 PSU, mixed away by wind) and lowers the surface sound speed |
| SOFAR channel | an interior sound-speed minimum (about 400-500 m below the surface layer) exists only in deep enough water |

## Weather & sonar analysis (key 0) {#ref-weather-station}

Key `0` opens a full-screen analysis panel over any station (`0` or `Esc` closes it; the simulation keeps running). In the web client every station opens it with `0` or from the workstation menu. Over the ocean profile the mouse reads depth and sound speed; over the sound-path section it reads range, depth and sound speed and says whether that point lies in a shadow zone or a convergence zone.

- **Environment:** time, daylight (day, civil or nautical twilight, night), moon phase, weather and precipitation, visibility, wind with gusts and Beaufort force, sea state, barometer with its 3-hour tendency (rising, steady, falling, falling rapidly), air and sea temperature, cloud ceiling and icing. A rapidly falling glass below about 1004 hPa gives a storm warning. The weather system changes by at most one sea state per hour, so the barometer moves faster than a real one.
- **Weather effects:** sun (strong layer), wind (deeper mixed layer) and rain or snow (fresher surface water, rain noise) light up while they act.
- **Helicopter flight weather:** CLEAR, LIMITED (within 80 % of a limit, or light icing) or NO-GO, with wind, gusts, crosswind, visibility, ceiling, sea state, deck roll and pitch, icing and whether dipping is possible.
- **Ocean profile:** appears only after the sonar has taken a bathythermograph (Sonar `E`): measured sound speed over depth, the layer, a SOFAR axis if present, nine sound rays from the hull sonar to 20 NM and the shadow zone below the layer (red) where the hull sonar hears little. The measurement is marked stale after 30 min or 10 NM.

## Chart plot tools (key P) {#ref-plot}

The crew keeps one shared grease-pencil plot. Every station and every Remote Crew browser sees the same drawing, and it is saved with the game. It is the crew's own drawing: nothing in it comes from a sensor, and it never changes the simulation.

- **Opening it:** press `P` on the Bridge, Weapons or Helicopter map or on the OPZ chart. A cursor appears on own ship. Arrow keys move it (Shift: faster), or click on the chart. `Enter` sets a point, `Esc` cancels a started object and then ends plot mode, and `P` also ends it. A hint bar at the top of the chart shows the active tool and keys on the left and the cursor's bearing and distance from own ship on the right.
- **Tools:** `M` mark (one point); `R` ruler (two points, shows bearing and distance); `B` bearing line from own ship through the cursor (own position and time are stored, so the line stays where it was laid); `C` circle (centre, then a point on the radius, at most 200 NM); `D` dead-reckoning line (start point, then a point in the direction of travel, then type the speed 0-60 kn). The DR line moves on with time and shows its CPA to own ship's present course and speed.
- **Erasing:** `Backspace` deletes the object nearest the cursor. `Shift+Backspace` clears the whole plot.
- **Labels:** objects are numbered M1, R2, B3 and so on. In the web client you can type a label before drawing or rename an object in the list under the map.
- **Web client:** choose a tool above the map, then click once (mark, bearing line) or twice (ruler, circle, DR line). "Plot track bearing" lays the selected track's measured bearing from its observer position.
- **Limits:** at most 64 objects and 24 characters per label.

## Opposing submarines {#ref-subs}

| Class | Quietness | Max depth | Torpedoes |
|---|---|---|---|
| Diesel (older) | 0.75 | 200 m | 4 |
| AIP (modern) | 0.85 | 250 m | 5 |
| Nuclear attack | 0.92 | 400 m | 8 |

Submarines evade for 240 s after hearing a ping or a torpedo, may launch a decoy, lie in wait, snorkel (detectable by HFDF and ESM) and sometimes ping from 15 NM or less. Near the frigate a boat may instead creep to a charted wreck within 8 NM and lie still on the bottom beside it for 15-30 minutes.

Submarine physics: the hull accelerates toward an ordered speed (no instant sprints); hydroplanes need speed (below about 4 kn depth changes are slow); radiated noise rises about 12 dB per doubling of speed and jumps when the screw cavitates, and the cavitation speed rises with depth; a torpedo launch makes an 8 s transient; a badly flooded boat blows ballast once and rises fast and loud; operating below test depth fatigues the hull, and 1.5 x test depth crushes it; a lurking boat holds its position against the current. Submarines sense like you do: passive bearings from their own sonar, a range only after their own TMA legs (a few minutes), ESM only with the mast up, the datalink only at mast depth or snorkelling, and a torpedo alarm takes the crew a few seconds (2-15 s) before the boat evades. Surface ships lose top speed in heavy seas (small ships more).

## Crewed opposing submarine (Remote Crew) {#ref-opfor}

A second crew can play the enemy. The boat has six stations: Command, Sonar, Weapons, Engine room, Mast & ESM and Navigation; a browser takes them like the frigate's (`F9`). As long as one of them is held, the living hostile submarine with the lowest number follows only that crew's orders; when the roles are released, the host revokes them or a game is loaded, the AI takes the boat back from where it is. A browser holds roles of one side only (frigate or submarine), never both; the lobby first asks which unit it plays. In solo mode the one browser holds all nine frigate stations, or with **Play the submarine** in the host bar all six boat stations (and back with **Play the frigate**).

- **Stations:** *Command* orders course, speed and depth, lies on the bottom, pings and takes a BT, and sees the whole boat. *Navigation* orders course and depth, keeps the boat's plot and watches keel and obstacles. *Engine room* runs the telegraph, snorkel, silent running and the emergency blow and watches battery and noise. *Mast & ESM* raises the mast and watches ESM and alarms. *Weapons* fires, guides the wires and launches decoys. *Sonar* is the boat's sonar room. Each order is accepted only from the station that owns it.
- **Orders and weapons:** the boat follows course, speed and depth orders within its turn, depth and acceleration limits; telegraph steps (stop, 3, 6, 10, 15 kn, maximum) set the speed quickly. Fires a torpedo down a sonar contact's measured bearing, with its ping fix or TMA solution while current, or down a free bearing with an optional range; firing needs a ready tube and the target inside the tube arc. The crew sets the run depth (5-300 m, otherwise a shallow default) and fires one torpedo or two in a ±4° spread, each with its own datum. Every crew torpedo runs on a wire: the crew can move its datum (bearing and distance from the boat) and the wire turns it onto the new datum until its seeker acquires; faster than 10 kn or turning harder than 1.5°/s for 5 s breaks the wire, as does running out of either spool, and the crew can cut it. Launches a decoy and makes the one emergency blow.
- **Plant and boat modes:** a crewed boat never goes up, snorkels or calls home by itself. The battery drains with speed and hotel load; below 20 % the log warns, and an empty battery limits the speed to what the plant can serve (an AIP plant still takes over the load by itself). **Snorkel** runs the diesels at snorkel depth and charges the battery, at most 6 kn; diving deeper shuts the head valve. **Silent running** limits the boat to 5 kn and makes it as quiet as a lurking AI boat. **Lie on bottom** stops the boat 3 m above the seabed where the water is no deeper than test depth: silent and no drift; any speed or depth order lifts off. The boat stops short of land or a seamount instead of turning away, and the log warns in shallow water.
- **Situation picture:** an intercepted active ping or torpedo is logged with the bearing the boat's own ears measured (a few degrees off) and shown with its age in the alarms. At periscope depth the **mast** can be raised; its ESM then reports the radars sweeping the boat with bearing (log and ESM list), and the mast lowers by itself when the boat goes deeper. Command can also ping and take a BT without a sonar operator. The chart shows the tube firing arc where the tubes cannot fire all round, and the sonar room's assigned target is preselected for the shot.
- **Navigation and plot:** the engine room has telegraph buttons, and Command and Navigation share the boat's own grease-pencil plot (marks, rulers, bearing lines, circles, DR lines); the frigate never sees it, and the boat's plot is not saved. The navigation display shows the water under the keel and checks the chart along the ordered course up to 5 NM: land or a seabed shallower than the boat is reported as an obstacle ahead, in the log and as a warning. Only charted geography counts; other vessels are not in the check.
- **Submarine sonar:** the same sonar workstation as on the frigate (broadband, LOFAR, DEMON, TMA, active echoes, classification, listening audio), but the hull array listens at the boat's own depth, so the layer works for and against the crew. There is no towed array and no release to an OPZ. An active ping gives echoes and is heard by the frigate.
- **What the submarine crew sees:** its own boat, the known chart, its own sonar measurements and its own torpedoes in the water. It never sees the frigate's position, its plot, its events or its mission messages; the frigate crew cannot tell a crewed boat from the AI.
- **Mission:** unchanged. If the frigate sinks, the submarine has won; if the boat sinks, its crew sees "Boat lost".
- **Saving:** the crew binding is not saved. After a load the AI commands the boat until a crew takes its roles again, and the boat's sonar picture starts empty.

### Playing the submarine on the uConsole {#ref-opfor-local}

Every new game first asks **Which unit do you play?**: *Frigate F-217* or *Hostile submarine* (`Up`/`Down` or `1`/`2`, `Enter`; the last choice is preselected, `--play-sub` preselects the submarine). Outside a mission, Options (`F10`) page 2 **uConsole plays** changes it as well, for example before loading a game. With the submarine the uConsole commands the hostile boat instead of the frigate. The frigate is then crewed from the browsers through Remote Crew (`F9`) or runs on autocrew. The uConsole shows only the boat's own picture; the frigate's banners, event log, sound cues, plot and tooltips never appear, and its trackball and telegraph controls are disabled. The side can only be changed outside a mission; it lasts for this launch and is never saved, so every launch starts with the frigate.

The **submarine command** station is laid out like the Bridge: the chart on the left (known geography, the boat with its ordered course and motion vector, the bearing lines of its own sonar contacts or their symbol while a ping or TMA fix is current, its own torpedoes `T1`…, a limited tube firing arc), the station on the right with a threat bar (torpedo alarm and active sonar heard with measured bearing, hull damage, cavitation, low battery, ESM radar intercept) and two pages. **Navigation** shows course and depth, water under the keel and any charted obstacle ahead, speed, own noise, battery and the active modes, and the water column under the boat: boat depth, ordered depth, safe depth and seabed; the layer appears there only after the boat's own BT measurement (`E` at the submarine sonar). **Weapons & contacts** shows fire readiness, torpedoes, tubes ready, reload, decoys, emergency blow and the boat's own sonar contacts. Below are the boat log and the boat's telemetry, as a band or a status ticker as set in the options; orders, shots and decoys are logged there.

<!-- keys:uboot -->

### Not modelled {#ref-opfor-limits}

- Crew state (modes, mast, wires, plot, alarm bearings) is not saved: after a load the AI commands the boat and every crew torpedo has lost its wire.
- The crewed boat sends no radio traffic and receives none; there is no contact report from home.
- No damage-control teams aboard the boat; damage only accumulates.
- A raised mast is not detected by the frigate's radar (the frigate radar does not detect submarines), and snorkelling adds no diesel noise: it only ends silent running.
- No periscope view and no visual sightings from the boat.

## Mission and scoring {#ref-mission}

- Scenarios: 1 Patrol, 2 Double hunt, 3 Nuclear intercept, 4 Random (custom difficulty). User missions start from the Mission Editor (`F5` in its browser).
- Win: all targets sunk, or survive the time limit. Lose: own ship sunk, civilian hit, target 150 NM from its start, or time out.
- Score: 1000 per sunk submarine, 200 per unused torpedo, 500 without civilian losses, up to 500 time bonus.

## Glossary {#ref-glossary}

| Term | Meaning |
|---|---|
| ASW | Anti-submarine warfare |
| HMS / TAS | Hull-mounted sonar / towed array sonar |
| LOFAR | Low-frequency analysis and recording: frequency-time waterfall |
| DEMON | Demodulated noise: reveals blade and shaft rate |
| TMA | Target motion analysis from bearings |
| BT | Bathythermograph: measures the sound-speed profile and layer |
| CZ | Convergence zone |
| Datum | Last estimated target position used for weapons and search |
| CIC / OPZ | Combat information centre / Operationszentrale |
| ESM / ECM | Electronic support (passive intercept) / countermeasures (jamming) |
| HFDF | High-frequency direction finding |
| EMCON | Emission control: radars off |
| ROE | Rules of engagement |

## Screen abbreviations {#ref-abbreviations}

When a full label does not fit the 1280x720 screen, the station shows its catalogue abbreviation instead of cutting the text off. The F11 log and tooltips always show the full wording.

| Short | Meaning |
|---|---|
| CRS/SPD | Course / speed |
| NOISE, CAV | Own radiated noise in %, cavitating |
| SS/LAYER | Sea state / measured layer depth (BT) |
| FLOOD | Mean flooding |
| TORP, VLS/CHAFF | Torpedoes left, VLS cells / chaff reload |
| HELO/ROE, HGR | Helicopter state / rules of engagement, hangar |
| BRG, G, N | Bearing, gain, notch |
| BB, FILT, HET | Broadband, filtered, heterodyne audition |
| STOW, DEPLOY, RECOV, OUT, STAB | Towed array stowed, deploying, recovering, streamed, stability |
| RDY, N/RDY | Ready, not ready |
| UNK, FRD, NEU, HOS | Affiliation: unknown, friend, neutral, hostile |
| SFC, SUB, AIR, MSL, TRP | Domain: surface, subsurface, air, missile, torpedo |
| RDR S/A | Radar surface / air |
| D, W, CD | Dipping sonar depth, water depth, ping cooldown |
| B-rate, Tgt | Bearing rate, target |
