# Tools {#tools}

These aids work at every station of both units. None of them stops the simulation.

## Mouse and the game menu {#tools-mouse}

The game runs at 1280x720 and is designed for the uConsole keyboard and trackball. Much of the uConsole can also be played with the mouse (or the trackball's buttons): a click on a key in a station's key bar presses that key (holding the button holds the key, for example for steering or the telegraph), the numbered tabs in the top bar switch stations, a click on the course, speed or depth dial orders that value, and a numeric entry shows a keypad. Status lamps, key hints in a station's text (for example "`Y` lower/retrieve" or the radar state), page tabs, list rows and the readings in the bottom status line are clickable too: a lamp or hint presses its key, a reading such as flooding or torpedoes opens the station that handles it. The element under the mouse gets a thin frame. A click does exactly what its key does, with the same checks.

The fire key `Ctrl+Enter` is clickable only at the weapons station (station 3) on both sides. Station orders that are not in the key bar have key chips of their own: classify, TMA, release to the CIC, target and the towed arrays under the sonar's contact cards, assign target, chaff and the missile track on the CIC's target page, the consort's orders on its group page, and flooding a tube and the decoy in the submarine's fire control (a dry tube's lamp floods it, an empty one's loads it). Missiles stay on their key: ESSM and the consort's ASROC are fired only with `Ctrl+Enter`.

Menu rows, dialog rows, save slots and the hints under them are clickable too; the wheel moves through menus and scrolls the help, and a right click cancels like `Esc` in menus, dialogs, entries and at the mission end. On charts the wheel zooms, dragging pans and a click pins a tooltip.

The menu icon in the top bar, left of the dark/light switch, opens the game menu on both sides: help, options, save and load, the weather panel, the plot, the autocrew and crew assist, the simulation log, the executive officer, the unit analyzer, Remote Crew, nations and quit, each marked with its key; a click beside the menu or any key closes it. Every overlay (help, options, save/load, quit, nations, live traffic, the weather panel, the autocrew overview and the simulation log) has a close box in its top right corner that acts like `Esc`. `F1` lists every key of the station.

## Help (F1) and event log (F11) {#tools-help}

`F1` (or `?`) opens the help overlay at any time. It has four categories: global keys, the current station (keys and standard procedure), sensors and tactics, and this manual. Menus and dialogs over a running mission (help, options, save/load, quit, nations, `F9`, mission end) show the start screen's night scene behind a console panel instead of the station; the mission keeps running behind them.

The bottom status ticker shows the newest event and key telemetry; `F11` opens the full event log and telemetry over the station without stopping it or taking its keys (on the submarine side the submarine log). The Remote Crew browsers show the same log, newest first, in their operational log (`L`): the frigate's stations the frigate's log, the submarine's stations the submarine log.

## Autocrew and crew assist (F2, F3, Shift+F2) {#tools-autocrew}

`F2` hands the current station to the autocrew; `F3` shows which stations run automatically. Use it when you want to concentrate on one or two stations. `Shift+F2` switches the crew assist: the AI mans every station of both units that nobody holds, and the station on screen stays yours. A mission started from the multiplayer lobby has it on when a browser takes part or the uConsole is host only; started there alone it is a solo game with the assist off.

### Crew assist {#ref-crew-assist}

`Shift+F2` (on in a mission started from the multiplayer lobby with a browser taking part or with the uConsole host only) lets the AI man every station nobody holds, on the frigate and on a crewed submarine, so each player can stay on one station. A station a browser holds, and the one the uConsole shows, stay with their player; a station released in the browser ("Hand over to AI") goes back to the AI at once. The assist is saved with the mission (save v41).

- **Frigate:** the AI hunters above work the Bridge, Sonar, Weapons and the helicopter, the autocrew the other stations, also against an AI submarine.
- **Submarine command:** evades a torpedo or a ping it has heard, otherwise follows the submarine mission's leg or, in a frigate mission, closes a frigate the submarine's own sonar has fixed within 12 NM and else patrols at 4 kn below the layer around its start point. It comes to snorkel depth when the battery falls below 35 % and nothing hunts the submarine.
- **Submarine weapons:** keeps the tubes loaded, floods quietly once a heard target has a fix within 8 NM and fires one torpedo at a time down a fix within 4 NM. A target is a contact whose signature the library knows only from warships (in the convoy attack, from merchants).
- **Engine room:** snorkels to charge up to 95 % while unhunted, keeps the trim automatic, answers foul air with absorbers and oxygen candles and sends the two damage-control teams where fire, leaks or water are worst.
- **Sonar and mast:** the sonar keeps the focus on the loudest fresh contact; the mast comes down on such an alarm. Navigation and the radio room only keep watch.
- **A player's order wins:** a station the AI mans never overrides what a player at another station commands. With a player at Navigation the AI command leaves course, depth and evasion alone; with one in the engine room it leaves speed and silent running; with one at command the AI engine room leaves the trim and the damage-control teams, and the AI mast station leaves a mast raised at command or in the radio room up even on an alarm. While a player at the mast or in the radio room holds the mast up, the AI command keeps the submarine at periscope depth; it dives again once the mast is down. On the frigate the AI Bridge does not steer while a player is in the engine room, and the AI weapons and patrol aircraft do not re-designate a current target a player chose at Sonar, OPZ or Weapons. A contact picked on the uConsole with `Up`/`Down` stays picked.

## Weather & sonar analysis (key 0) {#ref-weather-station}

Key `0` opens a full-screen analysis panel over any station (`0` or `Esc` closes it; the simulation keeps running). In the web client every station opens it with `0` or from the workstation menu. Over the ocean profile the mouse reads depth and sound speed; over the sound-path section it reads range, depth and sound speed and says whether that point lies in a shadow zone or a convergence zone.

- **Environment:** time, daylight (day, civil or nautical twilight, night), moon phase, weather and precipitation, visibility, wind with gusts and Beaufort force, sea state, barometer with its 3-hour tendency (rising, steady, falling, falling rapidly), air and sea temperature, cloud ceiling and icing. A rapidly falling glass below about 1004 hPa gives a storm warning. The weather system changes by at most one sea state per hour, so the barometer moves faster than a real one.
- **Weather effects:** sun (strong layer), wind (deeper mixed layer) and rain or snow (fresher surface water, rain noise) light up while they act.
- **Helicopter flight weather:** CLEAR, LIMITED (within 80 % of a limit, or light icing) or NO-GO, with wind, gusts, crosswind, visibility, ceiling, sea state, deck roll and pitch, icing and whether dipping is possible.
- **Submarine (crewed submarine stations, key 0 on the uConsole and the web client):** instead of the helicopter flight weather, cloud ceiling and icing, the submarine's stations show what the weather does to the submarine. *Mast on radar:* the range at which a surface-search radar like the frigate's detects a raised mast or snorkel head (half of all sweeps) in the current sea and rain, beside the calm-sea value; sea clutter hides the small echo, and the radar horizon caps it. *By eye:* how far a ship's lookout sights the submarine surfaced in the current light, moon, visibility and sea (5 NM on a clear, calm day); a raised mast at periscope depth is never sighted by eye. *Ambient noise:* wind and rain noise above a calm sea (sea state 1) in the four sonar bands (100, 400, 1600, 6400 Hz); it masks the submarine from passive sonar and dampens its own listening alike. *Snorkel:* at most 6 kn, +12 dB radiated level and diesel lines at 50 and 100 Hz that a sonar can hear.
- **Ocean profile:** appears only after the sonar has taken a bathythermograph (Sonar `E`): measured sound speed over depth, the layer, a SOFAR axis if present, nine sound rays from the hull sonar to 20 NM and the shadow zone below the layer (red) where the hull sonar hears little. The measurement is marked stale after 30 min or 10 NM.

## Chart plot tools (key P) {#ref-plot}

The crew keeps one shared grease-pencil plot. Every station and every Remote Crew browser sees the same drawing, and it is saved with the game. It is the crew's own drawing: nothing in it comes from a sensor, and it never changes the simulation.

- **Opening it:** press `P` on the Bridge, Weapons or Helicopter map or on the OPZ chart. A cursor appears on own ship. Arrow keys move it (Shift: faster), or click on the chart. `Enter` sets a point, `Esc` cancels a started object and then ends plot mode, and `P` also ends it. A hint bar at the top of the chart shows the active tool and keys on the left and the cursor's bearing and distance from own ship on the right.
- **Tools:** `M` mark (one point); `R` ruler (two points, shows bearing and distance); `B` bearing line from own ship through the cursor (own position and time are stored, so the line stays where it was laid); `C` circle (centre, then a point on the radius, at most 200 NM); `D` dead-reckoning line (start point, then a point in the direction of travel, then type the speed 0-60 kn). The DR line moves on with time and shows its CPA to own ship's present course and speed.
- **Erasing:** `Backspace` deletes the object nearest the cursor. `Shift+Backspace` clears the whole plot.
- **Labels:** objects are numbered M1, R2, B3 and so on. In the web client you can type a label before drawing or rename an object in the list under the map.
- **Web client:** choose a tool above the map, then click once (mark, bearing line) or twice (ruler, circle, DR line). "Plot track bearing" lays the selected track's measured bearing from its observer position.
- **Limits:** at most 64 objects and 24 characters per label.

On the submarine side `P` works the mast; the submarine's plot is drawn in the browser (chapter Submarine, Navigation).

## Chart history and labels {#ref-chart-history}

Every tactical chart (Bridge, Weapons, Helicopter, OPZ, the submarine's chart and plot, and the Remote Crew charts) shows where things were, not only where they are:

- **Own track:** a faint dotted line behind the own ship or submarine, one point every 30 s of simulation time, the last 2 hours.
- **Contact history:** earlier positions of a track as small dots that fade with age, one every minute, the last 12 per track.
- **Bearing history:** for a bearing-only contact the chart keeps its last 6 bearings; the selected contact's earlier bearings are drawn dashed from where each was taken, so their crossing shows where it may be.
- **Labels:** chart labels move aside instead of covering each other, the own ship or a symbol: first to the right, then down, up and to the left; bearing-line labels slide along their line.

The history is display only: it is built from what the sensors reported, is never saved and forgets a track 15 minutes after its last report.

## Simulation log (F4) {#tools-simlog}

`F4` opens the simulation log over the station: a live list of the true state of the world (own ship, submarines, surface vessels, torpedoes, decoys, missiles, aircraft and buoys). It works only when **Simulation log** is switched on in the options, because it shows what no station knows: use it to study or debug the simulation, not to play. `M` shows a map of all contacts, and `F` on the map fits it to the units or the whole world. In the browser the host can grant the SimLog to a crew member.

## Analyser, executive officer and nations {#tools-more}

- `F8` opens the Tactical Unit Analyzer, a read-only catalogue of every unit with its 3D model, sound and radar images (chapter Mission and unit editor). With a sonar contact selected, `Enter` assigns the browsed profile to it as your annotation (chapter 2 Sonar, Pro tips).
- `F7` opens the executive officer when the optional language model is switched on (chapter Language model).
- `N` opens the overview of nations and units (at the sonar and on the helicopter's acoustic page `N` is the notch filter instead).
