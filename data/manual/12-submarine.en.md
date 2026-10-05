# Submarine {#submarine}

## Overview {#sub-overview}

A second crew can play the submarine on the uConsole or in browsers (the lobby, `F9` or a new game as the submarine). The submarine has seven stations; each order is accepted only from the station that owns it, and an AI fills every free station when the crew assist is on. This chapter describes each station, its pages and standard procedure; the submarine's missions are in chapter Scenarios and missions.

As long as one of them is held, the living hostile submarine with the lowest number follows only that crew's orders; when the roles are released or the host revokes them, the AI takes the submarine back from where it is. A browser holds roles of one side only (frigate or submarine), never both; the lobby first asks which unit it plays.

![Submarine stations on the uConsole at a glance](figure:uboot-overview)

| Station | Pages |
|---|---|
| 1 Command | Navigation, Weapons & contacts, Periscope, Threat |
| 2 Sonar | Broadband, LOFAR, DEMON, TMA, Environment, Active (as the frigate's sonar) |
| 3 Weapons | Tubes and fire control |
| 4 Engine room | Plant, Stores, Tanks, Damage |
| 5 Mast & ESM | ESM, Periscope |
| 6 Navigation | Chart & sounder, Navigation, Threat |
| 7 Radio room | Radio |

**Stations:** *Command* orders course, speed and depth, lies on the bottom, pings (`Shift+A`) and takes a BT (the BT in the browser; on the uConsole the sonar room takes it), and sees the whole submarine. *Navigation* orders course and depth, keeps the submarine's plot and watches keel and obstacles. *Engine room* runs the telegraph, snorkel, silent running, the trim and the emergency blow and watches battery and noise. *Mast & ESM* raises the mast and watches ESM and alarms; Command may raise it too, to look through the periscope. *Weapons* fires, guides the wires and launches decoys. *Sonar* is the submarine's sonar room. The *Radio room* copies HQ's broadcast and sends situation reports; it may raise the mast for its antenna. Each order is accepted only from the station that owns it.

**What the submarine crew sees:** its own submarine, the known chart, its own sonar measurements and its own torpedoes in the water. It never sees the frigate's position, its plot, its events or its mission messages; the frigate crew cannot tell a crewed submarine from the AI.

A save keeps the crew's orders, modes, mast, wires, plot, alarm bearings, ESM picture and radio log; after a load the submarine runs its last orders and waits up to ten minutes for its crew to take the stations again (every submarine station is re-leased) before the AI takes it back.

### Playing the submarine on the uConsole {#ref-opfor-local}

Every new game first asks **Which unit do you play?**: *Frigate F-217* or *Hostile submarine* (`Up`/`Down` or `1`/`2`, `Enter`; the last choice is preselected). Outside a mission, Options (`F10`) page 2 **uConsole plays** changes it as well, for example before loading a game. With the submarine the uConsole commands the hostile submarine instead of the frigate. The frigate is then crewed from the browsers through Remote Crew (`F9`); every frigate station no browser holds is crewed by the **AI hunters** (below).

The uConsole shows only the submarine's own picture; the frigate's banners, event log, sound cues, plot and tooltips never appear (the submarine's own lamp notes do), and its trackball and telegraph controls are disabled. The side can only be changed outside a mission; it lasts for this launch and is never saved, so every launch starts with the frigate.

On the uConsole `1` to `7` switch the stations and pressing the same number again (or `Page Up`/`Page Down`) turns the station's pages. Every station has a key bar at the bottom; a click on a key there, on a lamp or on a dial does the same as the key. The full key table is at the end of this chapter; the browser stations have the same orders as buttons.

The top bar shows the submarine's seven stations as tabs: `1` Command, `2` Sonar, `3` Weapons, `4` Engine room, `5` Mast & ESM, `6` Navigation, `7` Radio room (`Tab` or a click on a tab switches), and on the right the mission, the clock, speed, course and depth. Each order key works only at the station that owns it, as in the browser; elsewhere a banner names the right station. Browsers can crew the submarine's other stations at the same time; a station a browser holds is marked in the top bar and is not operated from the uConsole.

Every station but the sonar room is laid out like the Bridge: the chart on the left (known geography, the submarine's own plot, the ESM bearing lines and cross-fixes, the submarine with its ordered course and motion vector, the bearing lines of its own sonar contacts or their symbol while a ping or TMA fix is current, its own torpedoes `T1`…, a limited tube firing arc), the station on the right with a threat bar (torpedo alarm and active sonar heard with measured bearing, hull damage, cavitation, low battery, ESM radar intercept) and the station's page. The threat bar appears only while a threat is current: a heard ping or an ESM intercept fills it for 30 s; after that an amber triangle with the number of standing warnings sits in the top bar and the details stay on the Threat page.

Below are the submarine log and the submarine's telemetry, as a band or a status ticker as set in the options; orders, shots and decoys are logged there.

Keys that work at every station of the submarine (`F1` on the uConsole shows them first):

<!-- keys:uboot_global -->

## Command {#sub-command}

Command sees the whole submarine: chart, navigation, weapons and contacts, the periscope and the threat page. It orders course, speed and depth, lies on the bottom, pings, takes a BT and evades on the freshest alarm.

- **Navigation (page 1):** the chart with the submarine's own contacts and bearing lines, the course, speed and depth dials and the depth bar. `C`, `V` and `D` order course, speed and depth; `U`, `J` and `H` step to periscope, below-layer or deep depth (with `Shift` snorkel and above-layer depth); a click on a dial orders that value.
- **Weapons & contacts (page 2):** the tubes and the contact list as the Weapons station sees them, to follow the attack.
- **Periscope (page 3):** the view through the head at periscope depth with the mast up. `←`/`→` train it, `↑`/`↓` tilt it, `Q`/`E` switch low and high power, `Space` the stabilizer; `Enter` takes a stadimeter range of the sighting under the crosshair and `Ctrl+Enter` fires on the attack computer's solution.
- **Threat (page 4):** the freshest pings, torpedo noises and radar intercepts with their bearings. `I` evades the freshest alarm, `Ctrl+B` clears the baffles, `G` calls action stations.
- Command pings with `Shift+A` on the uConsole and in the browser. The BT is taken by the sonar room on the uConsole (`2`, `E`); in the browser Command can take it too.

**Depth steps and displays:** Command and Navigation order depth in one step: periscope depth (15 m, keeps the mast usable), snorkel depth (submarines with a snorkel), above or below the layer (15 m above / 30 m below; only after the submarine's own BT measurement, since the crew knows the layer only from it) and deep (the safe depth over the charted bottom). On the uConsole these are `U`, `Shift+U`, `Shift+J`, `J` and `H`.

The browser shows the water column (surface, periscope depth, measured layer, ordered, safe and crush depth, seabed, the submarine and its dive direction), large readouts for course, speed, depth and battery with coloured mode and alarm chips, and an ESM rose with each emitter's strobe and the ping and torpedo alarm bearings; the uConsole's Mast & ESM page has the same rose. Mast, snorkel, silent running and lying on the bottom have separate on and off buttons.

**Navigation** (Command page 1 and Navigation page 2) shows course and depth, water under the keel and any charted obstacle ahead, speed, own noise, battery and the active modes, below them a row of round dials for course (the ordered course as an amber mark), depth (amber beyond test depth, red beyond crush depth) and speed as on the frigate's bridge, and the water column under the submarine: submarine depth, ordered depth, safe depth and seabed; the layer appears there only after the submarine's own BT measurement (`E` at the submarine sonar).

![Submarine command on the uConsole](figure:uboot-command)

![Submarine command in the Remote Crew browser](figure:web-uboot-desktop)

### Periscope, stadimeter and attack computer {#sub-periscope}

With the mast up the **periscope** page (Command page 3, Mast & ESM page 2; `P` raises the mast at both) shows the eyepiece in the start screen's look: sky and sea in the light of the hour (day, dusk, night with stars and the moon), clouds, rain, snow and fog from the weather, the horizon moving with the sea, a true-bearing scale and a crosshair; the scope trains in 2° steps (`←`/`→`, `Shift`: 10°). Everything the optics make out within the frigate lookout's contrast model at 2.5 m eye height (day/night, moon, visibility, sea state, land in the way) appears as a silhouette and as a bearing-only **sighting** with a coarse class (warship, merchant ship, vessel, aircraft, torpedo wake) and its apparent length; the log reports each new sighting. Neutral ships show their navigation lights here as on the bridge's binoculars. Made-out ships, submarines and aircraft appear as turned 3D models as in the binoculars, at the full length their apparent length and the judged angle on the bow give, each as the model of its real type; the crew's sighting still names only the coarse class.

`↑`/`↓` tilt the head 2° (`Shift`: 10°, from 10° down to 60° up, for aircraft), `Q`/`E` switch between low power (32° field) and high power (8°) as on the frigate's binoculars, and `Space` switches the stabilizer; tilt and field stand in the corner of the picture. These settings belong to the eyepiece of the uConsole or of each browser, change only the picture (not what the optics detect) and are not saved. A helicopter in sight hangs at its true elevation above the horizon in the still sky, behind the clouds. Underway the water streams past just below the eyepiece with the submarine's own speed (toward the eye looking ahead, from bow to stern looking abeam). A ship with a stadimeter range stands that far below the horizon as the low eye sees her waterline (hardly a tenth of a degree at 0.5 NM), a nearer ship in front of a farther one.

`Enter` reads the **stadimeter** on the sighting under the crosshair: the range follows from its apparent length and the assumed hull length of the class (130 m for a warship or an unrecognized vessel, 150 m for a merchant), so an unrecognized or bow-on target reads long; the reading is ±25 % and becomes a VISUAL fix on the submarine's sonar contact of that target for 120 s, usable for a shot like a ping fix. Aircraft and wakes cannot be ranged.

Each reading is also a **mark** for the **attack computer**: from two or more marks at least a minute apart (the last six within 15 minutes) it fits the target's course and speed in a straight line and, with the torpedo's speed, shows the lead angle (left or right of the bearing) and the running time under the periscope (browser: the Solution column); the quality grows with the time between the first and last mark (full at 5 minutes) and the number of marks. `Ctrl+Enter` on the periscope page (browser: Fire on solution, Command only) fires on the solution of the sighting under the crosshair: the torpedo runs on the intercept course to the point where target and torpedo meet. A shot at the sonar contact of a marked target uses the solution as well. A target turning after the last mark leaves the solution behind; a faster fit than 40 kn is rejected as a bad mark. The marks are part of the saved game.

The charted coast stands on the periscope's horizon as far as its low optics see land (hills assumed 25 to 70 m). Command can also ping and take a BT without a sonar operator. The chart shows the tube firing arc where the tubes cannot fire all round, and the sonar room's assigned target is preselected for the shot.

![Periscope by day](figure:uboot-periscope-day)

![Periscope at night](figure:uboot-periscope-night)

![Periscope in the Remote Crew browser](figure:web-periscope-day)

### Threat page and evasion {#sub-threat}

**Situation picture:** an intercepted active ping or torpedo is logged with the bearing the submarine's own ears measured (a few degrees off) and shown with its age in the alarms. At periscope depth the **mast** can be raised; its ESM then reports the radars sweeping the submarine with bearing (log and ESM list), and the mast lowers by itself when the submarine goes deeper.

The submarine's sonar room tells an intercepted active ping by its frequency as the frigate's hull sonar, a helicopter's dipping sonar or a sonobuoy, and logs it with the measured bearing and the received level (dB re 1 µPa, from source level, spreading and absorption); a buoy pinging within 12 NM is heard only by a crewed submarine. A buoy splashing into the water within 4 NM is heard with a rough bearing (±6°); a salvo from the frigate's ASW rocket launcher splashing in within 3 NM is reported with its bearing while its charges sink (about 11 m/s), time to change depth or get out from under them; and a torpedo alarm is kept with its bearing.

The **Threat** page (Command page 4 and Navigation page 3; the browser's Threat card at Command and Navigation) counts the pings of the last 5 minutes by source, gives the loudest level with its assessment (from 150 dB the pinger probably holds an echo) and the trend of the last two pings (rising: closing in), splashes, torpedo alarms and ESM emitters, the submarine's own signature (depth against the measured layer, own noise: cavitating, snorkelling, loud, moderate or quiet, the mast) and the crew's recommendations. The chart draws each intercept of the last 2 minutes as a dashed bearing ray.

**Evade** (`I` at Command or Navigation, the browser's **Evade** button) gives the crew's evasion order for the freshest alarm (under 2 minutes): against a torpedo, the smaller turn that puts it 150° on the quarter, full speed and a decoy; against active sonar, the stern to the pinger, silent running at 3 kn. Both cross the measured layer (down when above or in it, up when below it), or go deep without a BT; the submarine lifts off the bottom first. The order goes through the same checks as the single keys, and the page shows it before it is given. The picture is display only and not saved.

<!-- sop:uboot_command -->

## Sonar {#sub-sonar}

The submarine's sonar room works like the frigate's, without towed array, OPZ release, plot and telegraph. The hull sonar is deaf in the baffles astern.

- The six pages and their keys are those of the frigate's sonar (chapter 2 Sonar): broadband waterfall, LOFAR lines, DEMON shaft rate, TMA, environment with BT, active pings with `Shift+A`.
- The hull sonar listens at the submarine's own depth: above the layer it hears surface ships well, below it it is shielded from them. Astern lies the deaf baffle sector, so ask Command for a baffle clearing now and then.

![Submarine sonar](figure:uboot-sonar)

![Submarine sonar in the Remote Crew browser](figure:web-uboot-sonar-desktop)

<!-- sop:uboot_sonar -->

## Weapons {#sub-weapons}

Weapons loads and floods the tubes, sets run depth and salvo, fires at a selected contact or down an entered bearing, steers the wired torpedoes and launches decoys. The page has two columns beside the chart: contact cards (a click selects one) above the engagement plot, and fire control above the tube lamps. The fire-control box shows the seeker setting of the next shots; at the Weapons station a click on its red fire plate fires like `Ctrl+Enter`. Below the presets its key chips flood the next dry tube (`Shift+M`, quietly `Ctrl+M`) and launch a decoy (`V`), and a click on a tube lamp loads an empty tube (`M`) or floods a dry one (`Shift+M`).

- **Tubes:** each tube is empty, loaded (dry) or flooded; only a flooded tube fires. `M` loads the next empty tube, `Ctrl+M` floods the next loaded one slowly (60 s, hardly audible), `Shift+M` fast (20 s, loud).
- **Fire control:** `↑`/`↓` pick a contact with a fresh range, `T` sets the run depth, `Y` single shot or two-torpedo spread, `X` the seeker pattern and `,`/`.` the enable point; `Ctrl+Enter` fires. `F` fires without a contact: type the bearing and `Enter`, then the distance to the datum (blank: 10 NM down the bearing) and `Enter`, and `Ctrl+Enter` fires; `Enter` alone never fires.
- **Wire and decoy:** `W` steers the newest wired torpedo onto a new bearing, `Shift+W` cuts its wire; `V` launches a decoy.

**Weapons** (page and Weapons station) shows fire readiness, torpedoes, tubes ready (flooded), reload, decoys, emergency blow, a line with the tubes that are not ready (`M` loads the next empty tube, `Shift+M` floods the next dry one, `Ctrl+M` floods it slowly and quietly) and the submarine's own sonar contacts (bearing, range where known, and quality in percent: the better of the signal quality and the track confidence, 100 % being a firm contact), below them the engagement plot of the selected contact, drawn like the frigate's engagement sketch (torpedo reach, bearing, estimated position, intercept point and torpedo run, from the submarine's own observation only).

**Orders and weapons:** the submarine follows course, speed and depth orders within its turn, depth and acceleration limits; telegraph steps (stop, 3, 6, 10, 15 kn, maximum) set the speed quickly. Fires a torpedo down a sonar contact's measured bearing, with its ping fix or TMA solution while current, or down a free bearing with an optional range; firing needs a flooded, loaded tube and the target inside the tube arc.

**Tubes:** the crew takes over with the loaded tubes flooded. A fired tube stays empty until the torpedo gang loads it from the racks, if any torpedo is left there (`M` at the Weapons station, browser: Load; every submarine carries at least as many reloads again as it has tubes, and loading takes 2 min on a nuclear submarine, 3 min on a conventional one and 4 min on the older diesel classes, slower in stale air); a loaded tube is dry and must be flooded before it fires, which opens its outer door, takes 20 s and is audible for 4 s like a short transient that the frigate's sonar hears out to 8 NM (`Shift+M`, browser: Flood); slow flooding takes 60 s and is heard only within 1.5 NM (`Ctrl+M`, browser: Flood quietly). The Weapons station and the browser list each tube as empty, loading, dry, flooding or ready, and the log reports every tube loaded and flooded. The AI's submarines load and flood by themselves: quietly and early once they hold a fix on the frigate within 15 NM, loudly and just before the shot when they must fire on dry tubes.

The crew sets the run depth (5-300 m, otherwise a shallow default) and fires one torpedo or two in a ±4° spread, each with its own datum. Every crew torpedo runs on a wire: the crew can move its datum (bearing and distance from the submarine) and the wire turns it onto the new datum until its seeker acquires; faster than 10 kn or turning harder than 1.5°/s for 5 s breaks the wire, as does running out of either spool, and the crew can cut it. Launches a decoy and blows main ballast in an emergency (three times on a full air store).

![Submarine weapons](figure:uboot-weapons)

![Submarine weapons in the Remote Crew browser](figure:web-uboot-weapons-desktop)

### Torpedo seeker {#sub-seeker}

- `X` steps the search pattern of the next shots: straight (as before), snake, circle or helix. The torpedo runs straight to the datum; once its seeker is on and it has found nothing, it searches in that pattern.
- `,` and `.` move the enable point between 0.6 and 3.0 NM before the datum in 0.2 NM steps (default 3.0 NM). A late enable point keeps the seeker blind longer, so decoys and other ships on the way are not taken.
- A torpedo in the water keeps the settings it was fired with; the browser's Weapons card sets both with **Apply**.

<!-- sop:uboot_weapons -->

## Engine room {#sub-engine}

The engine room runs the telegraph, snorkel and charge rate, silent running, the trim tanks and the emergency blow, keeps the air breathable and leads the damage-control teams.

- **Plant (page 1):** telegraph (`+`/`-`), silent running (`A`, at most 5 kn), snorkel (`N`) and the battery, diesel and motor readings.
- **Stores (page 2):** battery, fuel, carbon dioxide and oxygen. `R` cycles the snorkel charge rate (full, half, air only), `Shift+O` fits a fresh absorber set, `O` lights an oxygen candle.
- **Tanks (page 3):** regulating and trim tanks. `↑`/`↓` pump out or flood the regulating tank, `←`/`→` move trim water, `Z` switches the automatic trim; `Shift+B` is the one emergency blow.
- **Damage (page 4):** the compartments with water, leaks, fire and gas. `↑`/`↓` pick a compartment, `←`/`→` a task, `Enter` sends team 1 (`Shift+Enter` team 2), `I` shuts or opens its bulkheads; `W`, `M` and `U` relieve the watch, send the medical team and re-man the worst-hit station.

The **Engine room** is a control console: round gauges for speed (the ordered speed as an amber mark), battery (depth on a nuclear submarine) and own noise, lamps for silent running, snorkel, on the bottom, cavitation, emergency blow and the plant state, and the telegraph steps.

![Submarine engine room](figure:uboot-engine)

![Submarine damage control (engine room, page 4)](figure:uboot-damage-control)

![Submarine engine room in the Remote Crew browser](figure:web-uboot-engine-desktop)

### Plant and stores {#sub-plant}

**Plant and submarine modes:** a crewed submarine never goes up, snorkels or calls home by itself. The battery drains with speed and hotel load; below 20 % the log warns, and an empty battery limits the speed to what the plant can serve (an AIP plant still takes over the load by itself).

**Snorkel** runs the diesels at snorkel depth and charges the battery, at most 6 kn; diving deeper shuts the head valve. The running diesels are loud: +12 dB radiated level, a lower quiet factor and two firing lines at 50 and 100 Hz in the submarine's LOFAR signature (AI submarines too). **Silent running** limits the submarine to 5 kn and makes it as quiet as a lurking AI submarine. **Lie on bottom** stops the submarine 3 m above the seabed where the water is no deeper than test depth: silent and no drift; any speed or depth order lifts off. The submarine stops short of land or a seamount instead of turning away, and the log warns in shallow water.

**Energy and stores:** the engine room's **Energy & stores** (browser card, uConsole Engine room page 2 **Stores**) shows the energy balance at the present speed (load, supply and net kW, the time until the battery is empty or full), the battery and AIP oxygen, the diesel bunkers and a table of how long the battery lasts dived at each telegraph step and how far that carries the submarine (on the uConsole tank columns for battery, AIP oxygen, diesel and absorber and a bar per telegraph step).

**Diesel:** the bunkers hold 300 hours of the generators' full output and a patrol starts with 65 %; only the running diesels burn it (0.27 l per kWh), the log warns at 10 %, and with dry bunkers snorkelling no longer charges. The **charge rate** sets what snorkelling does: *full* (the whole generator output, +12 dB and both diesel lines), *half* (half the output, +9 dB, weaker lines) or *air only* (the fans without diesels, +4 dB, no lines).

**Air:** dived, the crew uses oxygen and breathes out carbon dioxide (about 0.45 % per hour each); a CO2 absorber set takes CO2 out until it is spent (8 spare sets), an oxygen candle adds 1 % O2 over 15 minutes (12 aboard, one at a time), and snorkelling flushes the submarine toward fresh air within minutes. From 3 % CO2 or below 18 % O2 the air is stale, from 5 % CO2 or below 16 % O2 it is foul; the log warns at each step. Stale air slows the crew (down to 30 % performance), and the torpedo gang reloads accordingly slower. AI submarines manage their air by themselves and come up to air the submarine when it turns foul. A nuclear submarine has none of these stores.

The Engine room's second page **Stores** shows energy, endurance and air; `R` cycles the charge rate, `Shift+O` fits an absorber set and `O` lights an oxygen candle.

### Tanks, trim and air {#sub-tanks}

The engine room's **Tanks & trim** (browser card with a cross-section of the submarine, uConsole Engine room page 3 **Tanks**) shows the main ballast, the regulating tank, the trim tanks, the high-pressure air and the trim the submarine is in.

Every weight change moves the submarine off neutral: a torpedo leaving a bow tube makes it 1.5 t lighter and bow light, water in flooded compartments (see damage control) makes it heavier and trims it toward the flooded end; the automatic trim takes up what its tanks can of that weight and moment. With the **automatic trim** on, the engineer pumps the regulating tank (±8 t, 25 kg/s) and the trim tanks (±3 t fore and aft, 15 kg/s) back to neutral; by hand, each order moves the regulating tank 0.5 t or the trim water 0.25 t (and switches the automatic off). Running trim pumps are audible (+3 dB and a 120 Hz line). Whatever the tanks cannot take up sinks or lifts the submarine by 0.03 m/s per tonne, and a trim angle (1° per tonne of moment, + bow down) drives it down or up with speed; the hydroplanes hold that only with way on, so a heavy submarine hovering at low speed sinks below its ordered depth; the log warns from 2 t and from 3°.

The **high-pressure air** (200 bar) holds three emergency blows of 60 bar each; a blow empties the main ballast in 20 s and the submarine rises to 10 m and stays there, the ordered depth reset to 10 m. The next order below 12 m opens the vents: the main ballast floods in 40 s before the submarine can dive. Snorkelling on the diesels runs the compressor (0.05 bar/s); with the air only on the fans it does not. Without power neither the trim pumps nor the compressor run. The AI's submarines keep themselves trimmed and keep their one legacy blow.

Its third page **Tanks** shows the cross-section, main ballast and air, the tanks with their orders, weight, trim angle, drift without planes, flooding and pumps; `↑`/`↓` pump out or flood the regulating tank, `←`/`→` move trim water aft or forward and `Z` switches the automatic trim.

### Damage control {#sub-damage}

Its fourth page **Damage** is a cutaway of the submarine from stern to bow (sail, casing and the pressure hull with its fittings; water tilted by the trim, fire and smoke, chlorine haze, a leak with water rushing in, round bulkhead doors with a cross when shut, team badges; each compartment's name and water in tonnes below), lamps with the selected compartment's water, leak, fire, gas, bulkheads and the power, and both teams; `↑`/`↓` pick a compartment, `←`/`→` a task, `Enter` sends team 1 and `Shift+Enter` team 2 there with that task, and `I` shuts or opens the compartment's bulkheads.

The engine room's **Damage control** (browser card with a damage-control lamp panel, a side view of the pressure hull with water, fire glow, gas haze, leaks, shut bulkheads, a state lamp per compartment and the team badges, gauges for trim, floodwater and high-pressure air, then the table; uConsole Engine room page 4 **Damage**) divides the pressure hull into six compartments: bow room, control room, quarters, battery room, engine room and stern room.

A hit on the crewed submarine holes the compartment it strikes (a leak of 1.5 % per % of hit damage, up to a full hole; from 50 % damage the neighbour too, with half the leak) and may start a fire there (chance = damage / 150); a hull failure below test depth holes it as well (see Below test depth). Water comes in at 40 kg/s through a full hole at 100 m, growing with the square root of depth; above half a compartment it spills into open neighbours (20 kg/s) and smothers a fire. A fire grows to full in 2 min and then spreads through open bulkheads; seawater in the battery room (from 2 t) gives off chlorine gas that drifts through open bulkheads and clears slowly once the battery is dry. Water in the battery room (from 5 t) or a fire there cuts the **power**: the motor stops (no way on, so the hydroplanes do not hold a heavy submarine), and the trim pumps, compressor and electric bilge pumps stand still.

**Shutting the bulkheads** of a compartment keeps water, fire and gas in it and starves a fire there in 3 min. Two **damage-control teams** walk the submarine (8 s per compartment) and **seal a leak** (a full hole in 60 s), **pump out** (30 kg/s, a quarter by hand without power) or **fight a fire** (a full fire in 60 s); in gas they work at half rate, and in a compartment 90 % full they can only pump. A compartment half full of water, half on fire or half gassed takes its station out: the bow room the torpedo tubes, the control room the mast and periscope, the engine room the diesels, the stern room half the top speed. The floodwater is weight and moment for the trim (see above); a submarine that sinks below 1.5 x test depth is crushed. The log reports leaks, fires, sealed leaks, fires out, flooded compartments, chlorine and power.

### Below test depth {#sub-depth}

The crew may order the crewed submarine below its test depth, down to crush depth (1.5 x test depth); the "deep" step and lying on the bottom stay at the safe depth. The uConsole's and the browser's depth columns mark the crush depth, and while the submarine is below test depth Command on the uConsole shows a red **BELOW TEST DEPTH** alarm and the browser a red alarm chip, both with the test and crush depths. From 90 % of test depth the hull fatigues as before (one failure in about 30 min at test depth); below test depth failures come far faster, growing with the square of the excess: about one every 6 min at 110 %, one a minute at 125 % and one every 20 s at 140 %.

Each failure is one of three: **sheared bolts** of a fitting (a quarter leak in a random compartment, 6 % damage), a **failed seal** of a shaft or valve (half a leak in the engine or stern room, 12 % damage) or a **cracked pressure hull** (a full leak and a 60 % leak in the neighbour, 30 % damage). Just past test depth a crack does not happen; its chance grows by 15 % per 10 % of excess, up to 60 %, and a seal fails in 30 % of the rest. The log reports every failure with its compartment, and at crush depth the hull collapses and the submarine is lost. The AI's submarines keep to their test depth.

### Engine-room console in the browser {#sub-console}

In the browser the Engine room's picture area is a machinery control console instead of a chart. An **annunciator panel** of status lamps shows every plant state at a glance: dark when off, turquoise while running, amber for a caution and flashing red for an alarm, each with its value (motor, silent running, cavitation, snorkel, generator, battery, charging, fuel, oxygen, carbon dioxide, absorber, oxygen candle, main ballast, blowing, vents, high-pressure air, compressor, trim pumps, automatic trim, trim angle, power, flooding, leak, fire, gas, over depth, emergency ascent, on the bottom); the master lamp in its plate counts the alarms and cautions.

Below it are round **gauges** for speed, battery, energy balance, depth (test to crush depth in amber), high-pressure air and trim angle with the ordered value as an amber mark, **tank columns** for battery, fuel, AIP oxygen, absorber, high-pressure air, main ballast and the regulating and trim tanks (these from their middle: up heavy, down light), and the **compartment cutaway**: the submarine drawn in section from stern to bow (casing, sail with masts, the pressure hull with its fittings) with the water in each compartment tilted by the trim, fire and smoke, chlorine haze, a leak with water rushing in, the round bulkhead doors (a cross when shut) and the teams at work, with each compartment's name, water and teams below it. A nuclear submarine shows no battery, diesel or air stores. The console only shows; the orders stay in the station panel on the right.

<!-- sop:uboot_engine -->

## Mast & ESM {#sub-esm}

Mast & ESM raises the mast at periscope depth, listens for radars on the ESM rose, classifies the emitters, plots cross-fixes and looks through the periscope. A click on a row of the emitter list selects that emitter, like ↑/↓.

- **ESM (page 1):** with the mast up (`P`, only at periscope depth) the rose shows every radar heard with its bearing and level. `↑`/`↓` pick an emitter, `C` (or `→`; `Shift+C` or `←` back) classifies it from the library (an annotation, never the truth), `Enter` puts its cross-fix or bearing line into the submarine's plot. A main-beam hit means the radar may already see the mast.
- **Periscope (page 2):** the same periscope as Command's page 3, without the shot.

**Mast & ESM** shows the mast time, the rose, the emitter list and the selected emitter (signal, level and trend, cross-fix, classification); its second page and Command's third are the **Periscope** (eyepiece, line of sight, light and the sightings list; `←`/`→` train, `Enter` stadimeter).

With the mast up at periscope depth the submarine's own ESM antenna (3 m above the water) hears the radars around it once a second: the frigate's, other ships' and aircraft radars inside the radar horizon, over land only where the coast does not block the line. The frigate's helicopter radiates its X-band search radar while it flies and is not dipping (antenna at 150 m), the patrol aircraft its frequency-agile search radar while the OPZ has it switched on. Each intercept carries the measured bearing (±4°), band, carrier frequency, PRF, modulation and received level, never the emitter's identity or position.

The crew keeps an **emitter list** (`E1`, `E2` …) across mast periods: an intercept joins an emitter when bearing, band and waveform agree (a frequency-agile radar by bearing and band only), and the list forgets an emitter 30 minutes after its last intercept. **Classification** is the crew's annotation from the library: the emitters whose published frequency and PRF ranges hold the measurement, up to 16, best fit first: each entry shows its fit (**good**, **fair** or **poor**: frequency and PRF near the middle of its ranges and the same modulation fit best), entries of one grade stand by catalogue key, and the list only reorders when a grade changes; the choice sets the power class for the **range estimate** from the level (unclassified: the shortest range the library allows). Every 30 s each emitter keeps a **bearing** from the submarine's own position (20 minutes); the chart shows the latest bearing lines, and once the submarine's own motion has swung the bearing by at least 8°, the **cross-fix** is their best crossing with a 95 % error ellipse that allows for an emitter drifting up to 8 kn since each line (a fast frigate usually gives none; a fix whose lines disagree is marked). The **level trend** reads rising, steady or falling over five minutes.

The **scan period** is the time between an emitter's main-beam hits (the level peaks; close in, the weaker side lobes are heard in between and do not count), measured only on the emitter's own waveform, over gaps up to 12 s with no washed scan between them, and read after 8 s: **rotating** with its period (about 2.5 s for a navigation or surface-search radar, 5 s for an air-search radar, 2 s for a multi-function radar) is a search radar sweeping past; **steady** (the beam on the mast at every scan) is a tracking or fire-control radar. A steady, live emitter is always a mast warning, and the log reports once when an emitter turns steady.

The **mast warning** ("radar can see the mast") comes when a live search radar's estimated range is inside the range at which a surface radar sees a raised mast in this sea and rain (the weather page's value); the **recommended mast time** is 60 s in a calm sea, up to 300 s when sea clutter hides the mast and 20 s under that warning, and the log reports when it is exceeded. From sea state 3 waves wash over the antenna and some scans hear nothing.

The browser's Mast & ESM card has the rose, the emitter table and the selected emitter's evaluation; **Transfer to plot** puts the cross-fix (mark and error circle) or else the latest bearing line into the submarine's plot. On the uConsole's Mast & ESM page `↑`/`↓` select an emitter, `C` or `←`/`→` (`Shift+C` back) step through its library classification and `Enter` transfers it to the plot. A raised mast pulls a feather that the lookout, the helicopter and the patrol aircraft see by eye (see the bridge chapter): going slow keeps it small, and when the submarine runs faster than 5 kn with a mast up, the crew warns "feather visible, reduce speed".

![Mast & ESM](figure:uboot-mast-esm)

![Mast & ESM in the Remote Crew browser](figure:web-uboot-esm-desktop)

<!-- sop:uboot_esm -->

## Navigation {#sub-nav}

Navigation orders course and depth, watches keel and shoals on the pilot chart and the echo sounder, keeps the dead reckoning and steers the route.

- **Chart & sounder (page 1):** the pilot chart around the submarine with soundings, shoals and land, the echo sounder with water under the keel and the DR position lamp. A left click orders the course to that point.
- **Navigation (page 2):** the tactical chart as on Command's page 1; a right click adds a route waypoint, `W` lays a zigzag or expanding-square search, `Backspace` clears the route.
- **Threat (page 3):** as Command's threat page; `I` evades, `Shift+G` lies on the bottom in shallow water.

The Navigation station opens on its own page **Chart & sounder**: four readouts (depth, sounding under the keel, keel clearance, the chart check ahead), a pilot chart of ±6 NM centred on the submarine, north up (the charted depth in shades with contour lines at 20, 50, 100, 200, 500, 1000 and 2000 m, water shallower than the keel limit red and within 30 m of it amber, land, charted hazards, range rings every 2 NM, the submarine's wake over the last 10 minutes, the ordered course out to the 5 NM check with a tick every 5 minutes at the present speed and a red cross on an obstacle ahead; a click on the chart orders the course to that point, as typed with `C`) and an **echo sounder** strip: the seabed and the submarine's own depth over the last 10 minutes (one sounding every 5 s), the keel clearance drawn amber under 30 m and red under 15 m, and on the right the charted profile along the ordered course out to 5 NM with the ordered depth; the header names the least clearance of the 10 minutes.

The trace is display only, is not saved and starts empty after a load.

**Plot:** in the browser Command and Navigation keep the submarine's own grease-pencil plot (marks, rulers, bearing lines, circles, DR lines). On the uConsole the submarine side has no drawing tools (`P` works the mast there), but `Enter` on the Mast & ESM page puts a cross-fix or bearing line into the plot, and every station's chart shows the plot. The frigate never sees it; the plot is saved with the game.

The navigation display shows the water under the keel and checks the chart along the ordered course up to 5 NM: land or a seabed shallower than the submarine is reported as an obstacle ahead, in the log and as a warning. Only charted geography counts; other vessels are not in the check.

![Submarine navigation](figure:uboot-navigation)

![Submarine navigation in the Remote Crew browser](figure:web-uboot-nav-desktop)

### Dead reckoning and route {#sub-dead-reckoning}

- Dived, the submarine knows its position only by dead reckoning. The navigated position drifts from the true one by a steady set of up to 0.4 kn that log and gyro cannot see (a nuclear submarine's inertial navigation drifts 0.3 times as much), plus a small random walk once a minute; the error stays below 8 NM.
- The crew's chart (coast, soundings, hazards, mission goal, HQ's reports and the route) is drawn where the navigator believes it lies against the submarine. The submarine itself, its own sonar contacts and own torpedoes stay where the submarine measures them. The position in degrees and minutes at the chart's top left is the navigated position, not the true one.
- A GPS fix: mast up at periscope depth for 20 s puts the navigated position back on the true one. The **DR position** lamp on the Chart & sounder page shows the navigator's own error estimate and the minutes since the fix, or the fix being taken.
- The chart check ahead and the route steer from the navigated position, so an old fix can lead the submarine into water the chart calls clear.
- The route: a right click on the chart adds a waypoint (at most 8), `W` lays a zigzag or expanding-square search from the submarine and steps to off, `Backspace` clears it. Any course order from the helm or an evasion ends the route; a baffle clearing has the helm while it runs. In the browser **Set waypoints on chart** turns clicks on the chart into waypoints.

<!-- sop:uboot_nav -->

## Radio room {#sub-radio}

The radio room copies HQ's broadcasts, reads HQ's orders and contact reports and sends situation reports.

- The page shows when HQ's next broadcast comes, whether the antenna is up (mast `P` at periscope depth, or the towed buoy antenna `B` down to 60 m at 6 kn or less), HQ's orders and contact reports and the log.
- `Enter` sends a situation report; it needs the mast up, and the frigate can take an HF bearing on it.

The **Radio room** has one page: antenna, broadcast schedule, copy and transmit progress, HQ's latest contact report and the radio log; `Enter` sends a situation report and `P` raises or lowers the mast.

Fleet headquarters sends a submarine broadcast every 10 minutes (broadcast 0 at mission start, then 1, 2 …) and repeats it until the next one. The submarine copies it only with its antenna up, which is the raised mast at periscope depth, and only after 20 s of unbroken reception inside that broadcast's time on the air; a submarine that stays deep misses broadcasts and only ever gets the latest. A broadcast carries HQ's **contact report** on the frigate in 60 % of cases: a position 5 to 15 minutes old with an error circle of 4 NM, and its course and speed rounded. On the chart it is drawn as an amber circle with its age, and the radio page gives bearing and range from the submarine.

A **situation report** (`Enter` at the radio room, or the browser's button) is 20 s of HF transmission with the antenna up. During it the frigate's HF direction finder can take a bearing on the submarine (radio room HF/DF), and lowering the mast aborts it. HQ acknowledges a report in its next broadcast and then always adds a sharper contact report (2 NM). The radio page and the browser's Radio room card show the antenna, the broadcast number and time to the next one, copy and transmit progress, the reports sent, the latest contact report and the radio log (12 entries, saved).

Below the mast the **VLF loop antenna** still copies the broadcast down to 25 m, but the slow VLF signal needs 60 s of unbroken reception instead of 20 s; it only receives, a situation report still needs the mast. Deeper still, the **towed buoy antenna** (`B` on the radio page, or the buttons on the browser's Radio room card) streams about 280 m astern in 60 s and copies the broadcast down to 60 m in 30 s, but only at 6 kn or less (faster it is pulled under); it only receives as well. Above 10 kn the cable parts and the buoy is lost for the mission. The small buoy on the water can be found by the frigate's lookout close in (an unknown small object, never recognised as a submarine) and by its surface radar at short range; aircraft crews do not look for it. Recovering it takes another 60 s.

From broadcast 2 on, a broadcast may carry an **HQ order** (half of them, while no order is open, at most 4 per mission; a missed broadcast is a missed order): proceed to an area 8 to 15 NM away in deep water and reach it within 3 NM inside 40 minutes (a green circle on the chart), send a situation report within 30 minutes, or keep radio silence (no transmission) for 20 minutes. The radio page and the browser's Radio room card show the open order with bearing, range and time left, and how many were carried out; the log marks the order a broadcast brought. Orders do not decide the mission.

A broadcast also passes on the incidents at sea HQ knows of (drift net, weather front, whales; see the Radio chapter); the crew plots a net on the submarine's chart. With the antenna up the radio room also hears the frigate calling HQ (a contact report or a request for support, 20 s each): it reports the HF/DF bearing (+/-8 degrees ground wave, +/-16 degrees sky wave) and draws a 30 NM bearing line labelled HF on the chart.

![Submarine radio room](figure:uboot-radio)

![Submarine radio room in the Remote Crew browser](figure:web-uboot-radio-desktop)

<!-- sop:uboot_radio -->

## Surfacing and crash dive {#sub-surface}

- `Shift+H` (browser: **Surface**, Command or Navigation) orders the submarine up to the surface. At 2 m or less it is surfaced: the low-pressure blower empties the main ballast within 2 minutes (no bottle air), the hatch is open and the submarine airs itself.
- Surfaced, the diesels (`N`) run in the open air: up to 12 kn (or the submarine's top speed) instead of 6 kn on the snorkel, and the generator gives 1.3 times its snorkel power, so the battery charges faster.
- The bridge watch looks out from 6 m instead of the periscope's 2.5 m and sees farther; its reports read **Bridge:** and an aircraft is called as an alarm. The scope page shows the bridge watch's view.
- The enemy sees a surfaced submarine too: the frigate's surface radar and the radars of helicopter and patrol aircraft see hull and conning tower (ten times a mast's echo), and lookouts see it by eye.
- `H` from the surface or with blown tanks (browser: **Crash dive**) is the crash dive: alarm, masts and snorkel down, vents open, full ahead, ordered depth 40 m. Blown tanks hold the submarine above 10 m until the vents have flooded them (up to 40 s), and the flooding vents are a transient the enemy may hear. From deeper than 12 m a crash dive is refused.

## Crew, sounds and red light {#sub-crew}

**Crew:** the submarine has its own watch bill with the frigate's rules (see Damage control, Crew and watches): three watches, fatigue, action stations and morale. The Engine room and Command order action stations (`G` on the uConsole as on the frigate, a button in the browser's Damage control card) and relieve the watch (`W` on the Damage page, or the button). Morale rises when a ship sinks and falls with every 10 % of hull damage. A tired crew hears later on sonar, sights later through the periscope and its damage-control teams seal and fight fire more slowly (the pumps are machinery and keep their rate).

**Wounded** follow the frigate's rules too: hull damage (one wounded per 15 % in a hit) and a minute in a fully flooded, burning or gassed compartment wound people in the control room (sonar, 4 posts), the bow room (torpedo gang, 4 posts) or the rest of the submarine (damage control, 8 posts); empty posts slow sonar recognition, tube loading and flooding, and the repair teams. The log reports the wounded; the Damage page shows them with the empty posts and the spare hands. `M` sends the medical team to the next station, `U` re-mans the worst-hit station from the resting watches (the browser's Damage control card has both buttons).

**Atmosphere:** the submarine has its own sounds, on the uConsole when it plays the submarine and in the submarine's browsers with sound on (never on the frigate's). From 60 % of test depth the hull creaks, now and then at first and every 12 to 28 s at test depth and below; a hull failure cracks. Every detonation in the water within 30 NM (a torpedo or missile hit, a merchant torpedoed) is heard: within 2 NM as a heavy blast close aboard, farther off as a dull distant rumble, and the log reports it with the bearing the crew's ears give (a few degrees off). A hunter's ping (hull sonar, dipping sonar or active buoy) rings on the hull. With stereo sound both come from that bearing, left for port and right for starboard of the submarine's head.

In **silent running** the submarine rigs for red: the uConsole's submarine screens and the browser's submarine command stations turn to dimmed red light until silent running ends. The submarine's action stations signal is only a quiet alarm bell, and when silent running starts the fans are heard running down, and up again when it ends.

## Mission end, debrief and spoken reports {#sub-mission}

**Mission:** From the submarine's side a mission is won when the frigate sinks, when the submarine escapes (it leaves 150 NM from its start) or when it holds out to the time limit of a hunt; if the submarine sinks, its crew sees "Submarine lost".

`D` on the submarine's end panel opens the submarine's own **debrief**: its track, what its sonar held on the frigate, the true positions of frigate, helicopter, patrol aircraft and buoys, torpedoes both ways, the pings it took and the spans (at least 1 min) in which the frigate's sonar really held it, marked below or above the layer.

Spoken crew reports (Options page 2) speak the submarine's log when the uConsole plays the submarine: torpedo and pings heard, buoy splash, new contact, evasion, mast warning, leak, fire, action stations, each own torpedo away (the log names its tube), detonations close aboard or distant and breaking-up noises with their measured bearing, a copied HQ broadcast (with or without a contact report on the frigate), a new periscope sighting with its class and bearing, passing 90 % of test depth and going below it on the way down, a hit, every hull failure, and the mission won or lost; browsers at submarine stations get the same reports.

## AI hunters {#ref-opfor-hunters}

When nobody sails the frigate (the uConsole plays the submarine, or a solo browser plays the submarine), AI hunters crew every frigate station no browser holds; a station a browser takes is left to it at once. They read only what the frigate's own sensors report, never the submarine's position or identity:

- **Classification:** a contact whose heard signature the library knows only from submarines is classified submarine, as an operator comparing it with the library would; recognising it takes the operator 3 minutes on average. Other contacts stay unclassified.
- **Datum:** the freshest located submarine contact (ping, TMA or buoy fix); else the youngest of a radar mast track up to 10 minutes old, an HF/DF or ESM cross-fix up to 15 minutes old and an HQ submarine datum report up to 30 minutes old; else the bearing of a submarine contact; else the fresher of an HF/DF bearing and an ESM bearing on a mast radar up to 5 minutes old (an intercept the library matches to a submarine radar among its three best fits, with no radar or AIS ship within 10° of its bearing, heard for no more than 10 minutes: a radar radiating longer is a ship); else a lead. A lost submarine bearing stays a lead for 20 minutes: the frigate runs down the line from where it was heard, 8 NM ahead of its own position on it, at most 60 NM out. In the frigate scenarios HQ's start report of the threat (bearing and range from the ship) is a lead for an hour, until the ship is within 3 NM of the reported position. In submarine scenarios 4 and 5 HQ reports no threat position at the start and passes no submarine datum: the frigate knows only what it guards. The leads are saved (save v43). The OPZ marks every bare radar blip of a raised mast or snorkel as a track, like an operator, and a mast track within 10° of a submarine contact's bearing counts as that contact. The radio room takes HF/DF bearings and cross-fixes like the autocrew. ELOKA plots an ESM bearing on a mast radar at most 30 s old as a line from the ship's position, a new line only after the ship has run 1 NM from the last one (at most 8, each for 15 minutes), and crosses the newest line with the latest earlier one it meets at 15° or more, no farther than 60 NM out: that ESM cross-fix is a position datum like an HF/DF fix.
- **Bridge:** in the convoy attack the frigate keeps station 3 NM ahead of the convoy, weaving 45° either side every 5 minutes (it closes at 18 kn when more than 2.5 NM off station), and prosecutes a datum only within 8 NM of the convoy; in the supply ship escort the supply ship is its convoy. Without a datum in the strait blockade it sweeps across the gate at 10 kn, turning 1.5 NM off either shore, and in the combat swimmers mission along the coast section (70 % of its radius either side of the centre), closing the section at 18 kn when outside it. Otherwise, without a datum the frigate searches at 10 kn on a zigzag (legs of 10 minutes) whose base course turns 90° every 30 minutes. It runs at 18 kn to a position datum farther than 6 NM and works a closer one at 8 kn on a crossing course (60° off, switching sides every 5 minutes) so the towed array and TMA get bearing motion; on a bearing alone it steers 30° off it at 14 kn and runs down a lead at 14 kn. Against a breakthrough (5) it guards its patrol position: it prosecutes a datum only within 6 NM of it and returns there without one when more than 3 NM off. In the strait blockade it prosecutes a datum only within 6 NM beyond either end of the gate, in the combat swimmers mission only inside the coast section. It turns away from torpedoes and missiles like the autocrew and never steers into shoal water.
- **Sonar and weapons:** the ship pings every 10 minutes on a submarine contact that has no fresh range (a ping that finds nothing only sends the submarine running), and fires one torpedo (or the set salvo) at a located submarine within 6 NM (within 3 NM in submarine scenarios 1, 2, 4 and 5, where it guards its post), again only when it has stopped running. Nixies go out against a heard torpedo.
- **Helicopter:** launched for a datum within 30 NM (8 NM in submarine scenarios 1, 2, 4 and 5; weather and deck permitting), after the deck has readied it (10 minutes on average); it flies to the datum, or 8 NM down a bearing, and dips. On a position it pings every 30 s; on a bare bearing it only listens. It drops a torpedo on a located submarine within 1.5 NM from a fix at most 2 minutes old, one at a time. Without a datum it recovers.
- **Patrol aircraft:** requested once a position datum exists (never for a bare bearing, and never in submarine scenario 1, where the frigate guards the passage alone); it flies to the datum with its radar on, lays a circle of buoys where none listen within 4 NM, and attacks a located submarine within its drop range over the datalink from a fix at most 2 minutes old.
- **ASROC:** a position datum at most 2 minutes old from the ship's own sensors (not an HQ report or an ESM cross-fix) is passed over the datalink to the nearest friendly AI warship that carries ASROC and has it in range, at most every 2 minutes and never while an ASROC is in flight or its torpedo is running. The AI hunters do not fire the frigate's own ASROC or depth charges (those stay with a player at the Weapons station), and the submarine scenarios add no escort for it.
- The other stations (damage control, engine room, OPZ air defence, ELOKA) run the autocrew's policies. The hunt keeps no state of its own; the radar blips and the OPZ's marks it acts on (save v25), ELOKA's ESM lines (save v39) and its leads (save v43) are saved, so a loaded game continues it unchanged.

## Keys {#sub-keys}

Every key of the submarine on the uConsole (`F1` at a submarine station shows the same table):

<!-- keys:uboot -->

## Mouse {#sub-mouse}

- Every key in a station's key bar can be clicked; lamps, page tabs and key hints in the text press their keys, and the station tabs in the top bar switch stations.
- A click on the course, speed or depth dial orders that value.
- In the fire control a dry tube's lamp floods it and an empty tube's lamp loads it; the decoy has a key chip. The fire key `Ctrl+Enter` can be clicked only at the Weapons station.
- Navigation, Chart & sounder: a left click on the pilot chart orders the course to that point; on the Navigation page a right click adds a route waypoint.
- A click on a row of the emitter list selects that emitter. On the chart the wheel zooms and dragging pans.

## Not modelled {#sub-limits}

- No position fixes from landmarks, soundings or stars; only GPS clears the dead-reckoning error.
- The plot keeps its marks where they were drawn against the submarine; it does not move with a fix.
- No separate control room or diving officer station; trim and ballast stay with the engine room.
- The radio room knows HQ's broadcast schedule, three kinds of order (seven on a free patrol) and situation reports: no free-text messages from HQ, no reception below 25 m without the buoy antenna and none below 60 m (no ELF, no trailing wire), no burst transmission and no other units on the net; HQ's contact report is modelled intelligence, not a sensor of its own.
- Damage control is six compartments and two teams: no separate pressure-hull and outer-hull damage, no smoke or heat spreading, no fire in the air stores and no fire consuming oxygen; the submarine's overall damage (noise, top speed, sinking at 100 %) still adds up from hits, and the AI's submarines keep only that value.
- Below test depth the hull has no individual fittings, no gradual shrinking of the hull and no stronger welds from a refit; a failure picks its kind and compartment at random, and a crushed submarine is lost at once.
- The submarine's sounds are simple cues: stereo only tells port from starboard (ahead and astern sound the same), a detonation gives no range estimate and no creak comes from a particular compartment; the submarine's sonar room has no red light.
- The trim model is one weight and one moment: no free-surface effect, no compressibility of the hull with depth and no separate negative tank; the submarine does not surface fully. Food and fresh water do not run out.
- A raised mast or snorkel head is seen by the frigate's radar only as a bare blip (see the OPZ chapter). A raised mast's feather depends only on speed (not on how far the mast is out of the water or on the course to the sea), and the crew warns only once when the submarine runs faster than 5 kn with a mast up.
- The submarine's ESM hears no other submarine's radar and no missile seeker; it has no scored likelihood analysis and no target motion analysis of an emitter (the cross-fix assumes a slow emitter).
- The fit grade is the crew's reading of the published ranges, not a likelihood: a wide-band radar measured near the middle of its range can fit better than the true emitter measured near its edge, and the browser shows the first 8 entries.
- The AI hunters' ASROC comes only from friendly warships already in the scenario, never from the frigate's own launcher.
- The periscope has no camera; sightings carry no identification beyond the coarse class, and the stadimeter assumes a class length rather than a masthead height.
