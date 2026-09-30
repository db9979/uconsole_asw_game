# Quickstart {#quickstart}

You command the ASW frigate F-217 and man nine stations. Your job: detect, track, classify and sink hostile submarines without losing the ship or harming neutral shipping.

> Everything in this manual describes what the simulation actually models. Features that are not modelled are listed at the end of every station chapter.

## Mission and win conditions {#qs-goal}

- **Win:** sink every assigned target submarine, or survive until the time limit (depends on the mission).
- **Lose:** own ship sinks, a civilian vessel is hit, the target escapes more than 150 NM from its start point, or time runs out on a sink mission.
- Time warnings arrive at 5, 2 and 1 minutes remaining: on a sink mission as a deadline, on a survive (convoy) mission as the time until the convoy is safe.
- When the mission ends, `R` restarts it with the same seed (an editor mission restarts itself) and `M` returns to the main menu. During a mission, `Esc` offers "Main menu (without saving)" next to save-and-exit.
- Score: 1000 per submarine sunk, 200 per unused torpedo, 500 for no civilian losses, up to 500 time bonus.

## Stations {#qs-stations}

The ship is split into nine stations. Keys `1`-`9` select a station; pressing the number of the current station again cycles its pages.

```text
 1 Bridge      2 Sonar       3 Weapons
 4 Damage      5 Operations  6 Radio
 7 Engine      8 Helicopter  9 Electronic warfare
```

Each station shows only what its sensors and operators know. Sonar contacts are noisy bearings until a ping, TMA, buoy or cross-fix supplies range. No station shows "the truth".

`F2` hands the current station to the autocrew; `F3` shows which stations run automatically. Use it when you want to concentrate on one or two stations. `Shift+F2` switches the crew assist: the AI mans every station of both units that nobody holds, and the station on screen stays yours. A mission started from the multiplayer lobby always has it on.

## Controls {#qs-controls}

The game runs at 1280x720 and is designed for the uConsole keyboard and trackball. The trackball acts as a joystick: horizontal steers on the Bridge, vertical steps the station's main selection elsewhere. A mouse works too: wheel zooms charts, drag pans, click pins a tooltip.

Global keys (all stations):

<!-- keys:global -->

In the Remote Crew browser (Commander, `F9`) stations are operated with buttons; the keyboard helps with navigation:

<!-- keys:web -->

The bottom status ticker shows the newest event and key telemetry; `F11` opens the full event log and telemetry over the station without stopping it or taking its keys. `F1` (or `?`) opens the help overlay at any time. It has four categories: global keys, the current station (keys and standard procedure), sensors and tactics, and this manual. Menus and dialogs over a running mission (help, options, save/load, quit, nations, `F9`, mission end) show the start screen's night scene behind a console panel instead of the station; the mission keeps running behind them.

## Underwater acoustics in five minutes {#qs-acoustics}

- **Passive sonar gives bearing only.** Every contact starts as a line of bearing. Range comes from active ping, TMA, sonobuoys or a cross-fix.
- **Detection is signal against noise.** The passive sonar equation SE = SL - TL - NL + DI - DT decides: the target's source level (louder = farther), transmission loss (spreading, absorption, layer and path losses), noise (own self noise plus wind, rain and nearby shipping), and the array gain. A contact is detected at SE >= 0 dB. Wind and rain matter most when you run slow and quiet; at high own speed your own noise dominates.
- **Own speed is own noise.** Self-noise rises from 4 kn to 31 kn, the frigate's top speed. Above 15 kn the propellers cavitate and passive range drops to about a third.
- **The layer (thermocline) bends sound.** Passive propagation is ray traced through the real sound-speed profile: above the layer a surface duct carries sound far, below it lies a shadow zone a few miles wide. In deep water the shadow is strong; in water of a few hundred metres, bottom bounce and multipath fill it beyond about 10 NM, so hiding below the layer mainly works close in. A ping into the shadow zone reaches only 35 % of its range.
- **Seabed and surface matter.** Rock and gravel reflect sound well, silt and mud absorb it; a rough sea scatters high frequencies. **Convergence zones** appear only where the water is deep enough for rays to turn back up.
- **Baffles:** own-ship noise is a soft 70 degree lobe astern of the hull array (and along the cable of the towed array). It masks, it does not blank.

```text
            surface
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    frigate  HMS )))            direct path
  ---------- layer / thermocline ----------  -6.5 dB across
       TAS below layer  )))    submarine
                                (shadow zone for a shallow sensor)
  ________________________________________ seabed
```

## Navigation conventions {#qs-navigation}

- Distances in nautical miles (NM), speed in knots (kn), depth in metres, frequency in Hz.
- Courses and bearings are true degrees: 000 north, clockwise. Charts are north-up.
- The game always runs in real time: one real second is one simulated second. There is no time acceleration and no pause; menus, help, options, save/load and losing window focus do not stop the simulation either.
- The ship turns at up to 0.8 degrees per second; speed changes take minutes. Plan manoeuvres early.

## Your first patrol {#qs-first-patrol}

1. Main menu: pick scenario 1 (Patrol) with `1` and start with `Enter`.
2. Bridge (`1`): press `1` again for the mission page, read objective and time limit.
3. Engine (`7`): select SLOW or 6-8 kn. Sonar (`2`): stream the towed array with `Y`.
4. Sonar BROADBAND page: look for a bright vertical trace; select it with the arrow keys and press `Enter` to follow it.
5. Classify with `C`, enable TMA with `T`, then turn the ship 30-60 degrees on the Bridge and hold the new leg for a few minutes.
6. When TMA or a ping gives range: release the contact to Operations (`G`), make it the target (`M`).
7. Weapons (`3`): set torpedo depth to the pinged target depth, fire with `T`.
8. Watch the sonar for an incoming torpedo; if one appears, go FLANK, turn away and stream the Nixie (`V` at Weapons).

## Main menu, saving and options {#qs-menu}

- **First launch:** when no `~/.u-jagd/settings.json` exists yet, a welcome page follows the start screen: "What do you want to play?" `1` Frigate (the Training menu with lesson 1 selected), `2` Submarine (the Training menu with lesson 5, the first submarine lesson, selected), `3` Remote Crew (opens the multiplayer lobby; `Esc` there leads to the main menu), `4` or `Esc` main menu. Arrow keys and `Enter` choose as well. Whatever you pick, the page is remembered in the settings and not shown again.
- Menu: `1`-`7` scenario (4 = random with custom difficulty, 5 to 7 = submarine missions, see the reference chapter), `W` world mode, `R` new seed, `F` fullscreen, `Enter` start.
- **Training** (main menu): six guided lessons, each a short mission with a hint banner that waits for you: 1 listen and take bearings, 2 target motion analysis, 3 torpedo attack, 4 helicopter and sonobuoys; on the submarine (the uConsole plays the submarine for these two): 5 listen and hide below the layer (hear the frigate, classify it as a warship, measure the layer with a BT and dive below it), 6 shake off a hunting frigate (read the Threat page, evade with `I`, go quiet and deeper than 100 m until no ping has come for two minutes; the frigate pings every 45 s until you evade, then only while its pings still find you, and never fires). In lessons 1, 2 and 4 the submarine is neutral and never attacks; lesson 3 is a real attack that ends when the submarine sinks. The other lessons end as won after their last step. `R` at the end runs the lesson again. A saved lesson restarts its hints at step 1 after loading and passes the steps that are already done. After a lesson the uConsole keeps the side it played.
- **Campaign** (main menu): six linked missions in the sea area chosen in the menu (world `W` and seed; every mission keeps the same sector). Carried over are the torpedoes left (at least 2, at most 10), compartments still damaged, a lost helicopter and your standing with HQ (0-100, start 50: +15 for a win, -20 for a loss, -10 for a civilian loss, +/-3 per task done or failed). After each mission the ship calls at port: `1` full refit (4 to 8 torpedoes by standing, all repairs, a new helicopter, standing -5) or `2` quick turnaround (half that restock, damage stays aboard, standing +3); `Enter` sails. The campaign ends when the ship is lost, standing falls below 10, or the sixth mission is done. It is kept in `~/.u-jagd/campaign.json`, apart from the save slots: a slot saved during a campaign mission loads as a plain mission; to count, the mission is sailed again from the campaign screen. `N` starts a new campaign (twice while one is running).
- **Submarine campaign** (main menu, Campaign, `Tab`): five linked submarine missions in the same sea area, played on the submarine side: reconnaissance, breakthrough, convoy attack, breakthrough, convoy attack. Carried over are the submarine's torpedoes, its hull damage (at most 60 %) and your standing with submarine command (0-100, start 50: +15 for a mission won, -20 for one lost). After each mission the submarine calls at its base: `1` full refit (full torpedo load, hull repaired, standing -5) or `2` quick turnaround (half of 4 to 8 torpedoes by standing added, the hull damage stays, standing +3); `Enter` puts to sea. It ends when the submarine is lost, standing falls below 10, or the fifth mission is done, and is kept in `~/.u-jagd/boat_campaign.json` beside the frigate's campaign.
- **Logbook** (main menu): every finished mission (never a lesson) for the side the uConsole played, with date, mission, realism level, result, score and minutes; the best score per mission and five awards per side: first victory, one shot one kill (the enemy sunk with a single weapon), unscathed (no damage), never fired at, and realist (a victory on the Realistic level). The frigate files its mission score; the submarine counts its outcome (sinking the frigate 1500, sinking the convoy 1200, breakthrough or report 1000, escape 800, surviving 600) plus up to 500 for an undamaged boat and 100 per torpedo left, times the level's factor. `Left`/`Right` switch frigate and submarine, `Esc` back. The end panel names the score, a new best and new awards. The logbook is `~/.u-jagd/logbook.json` (the newest 200 missions), never part of a save.
- **Report a bug** (main menu): writes `~/.u-jagd/bug-report.txt` (version, platform and the newest lines of `~/.u-jagd/crash.log`, with your user name removed from paths) and shows a QR code that opens a new GitHub issue on a phone with version and platform filled in; attach the file there. `Enter` opens the issue with the log in a browser if the device has one, `Esc` goes back. After a crashed start the main menu selects this entry and says so. Nothing is sent until you submit the issue with your own GitHub account. The Windows starter ("Report a bug") and the browser settings menu have the same link.
- **Update notice** (start screen and main menu): new releases are never installed on their own. At launch the game asks GitHub once whether a newer release exists; if so, the start screen (top right) and the main menu (left of the entries) show its version, its changelog entry in the game language and, when saved games of this version (the autosave too) will not load in the new release because the save format changed, a warning. `U` or a click on **Update now** installs it: on the uConsole the game closes, the launcher's small window shows the download and check and the new version starts; the Windows program downloads it in the background (progress on the button), checks its size and SHA-256 digest, closes, replaces itself and starts the new version; any other installation opens the release page. Offline, or with `U_JAGD_NO_UPDATE=1`, no notice appears.
- `S` / `L`: save / load (slots 1-5). Saves are exact and deterministic: a loaded game continues identically.
- **Autosave:** a running mission is saved every 5 minutes and when you quit or leave it for the main menu, to `~/.u-jagd/autosave.json` beside the five slots. The main menu then starts with **Continue mission**, which resumes it exactly; after a crash it holds the last 5-minute save. A mission that ends (won, lost or ship sunk) and any new mission delete the autosave. The web host (`--web-host`) does not autosave.
- `F10`: options - language, fullscreen, audio, large text, tooltips, frame rate (30 or 60 FPS; 30 saves CPU on the uConsole and is the default), event log / telemetry as status ticker (default, more room for the station) or docked band, and the **realism level** for the next mission: **Beginner** (operator assistance on: automatic line labels, blade-rate and catalogue/emitter candidates; the computer opponent attacks less eagerly, waits for a better firing solution and, as the frigate, classifies and launches its helicopter 1.5 times slower; score 75 %), **Standard** (default: raw data and manual analysis, the calibrated opponent; score 100 %) or **Realistic** (no assistance; the opponent attacks more eagerly, fires on a rougher solution and reacts 30 % faster as the frigate; score 125 %). The level only tunes the computer opponent, never a human on the other side, and a running mission keeps the level it started with (the row then says "from the next mission"). The end panel shows the level with its score factor; saves keep it. Page 2 (`PgDn`/`Tab`): which side the uConsole plays, frigate (default) or hostile submarine; only in the main menu, never saved. A new game asks for it first anyway. Page 2 also holds **anti-aliased chart lines** (off by default; smooths bearing lines, coast and plot at some CPU cost on the uConsole). And **spoken crew reports** (off by default): the crew says torpedo in the water, new contact with bearing, breaking-up noises, torpedo away, hit, action stations, patrol aircraft on station and the mission result aloud, bearings digit by digit. The uConsole speaks through an installed `espeak-ng` (`sudo apt install espeak-ng`) and stays silent without it; Remote Crew browsers have their own switch under Settings (the browser's speech synthesis, in the browser's language). With the uConsole on the submarine the submarine's crew reports instead (see the reference chapter).
- **Multiplayer** (main menu): the lobby where the crew meets before a mission. It starts Remote Crew in crew mode by itself and shows the QR code, address and join code. Browsers pair, choose their unit and stations and press **Ready**; they see the mission, what the uConsole plays and every crewmate with their stations and ready tick. On the uConsole, `Up`/`Down` choose a row and `Left`/`Right` change it: the mission, the unit the uConsole plays and the station it shows, or **none, host only**: then the uConsole plays no station, the browsers can take every one and the AI crews the rest. **Start the mission for everyone** starts a five-second countdown that every browser sees, then the mission begins for all at once and the uConsole opens on its chosen station. If a crewmate with a station is not ready yet, the first `Enter` asks again and a second one starts anyway. `Esc` cancels a countdown, otherwise it leads back to the main menu while Remote Crew keeps running. When a mission started from the lobby ends, everyone returns to the lobby with their stations; the ready ticks start again from zero. Every mission started from the lobby has the crew assist on (`Shift+F2`). `F9` opens the full Remote Crew settings from the lobby.
- `F9`: Commander / Remote Crew - lets browser clients on the LAN take stations. A free station is taken at once with all of its rights (including direct fire and live sonar audio where the station has them); a station a crewmate holds is requested, and the host can hand it over. The host can revoke a station or single rights at any time, and can make up to two browsers read-only observers (roster key `O`): they watch any station of either unit without holding it, cannot command, and get the SimLog with a debrief timeline and JSON export. On a Windows PC the program `U-Jagd-Windows.exe` starts the game with Remote Crew already on (crew or solo mode) and shows the browser address, join code and QR code; its Language box switches the starter, the game and the crew pages between English and Deutsch and is saved in the settings. `--remote-crew` does the same from the command line (see the README). The crew pages open in the host's saved language (`F10` options on the uConsole); the English/Deutsch button in the browser's status bar switches that browser alone. The crew page is built for Chrome or Chromium (also Edge) on a desktop PC; another browser shows a hint above the pairing code, and a page that cannot start there says so instead of loading forever. After a host update an open browser page reloads itself once, so it always runs the web client that matches the host.

## Phone lookout and periscope {#qs-phone}

A phone can stand the watch as the frigate's bridge lookout or on the crewed submarine's periscope. `F9` shows a second QR code, **Phone lookout**, for the address `https://<address>:<port+1>/lookout`. Scan it, accept the certificate warning once, choose the watch station, and type the pairing code shown next to it (the code is never in the QR code). Type it as shown, with or without the space and in any case; look-alikes such as O and 0, I, l and 1 or S and 5 are read by position. "Wrong pairing code" means exactly that and shows the code the game received; if the game refuses the address itself, the page says so.

- **Certificate:** the game makes its own certificate for its LAN address (kept in `~/.u-jagd/tls/`, renewed when the address changes). The phone warns once because no authority signed it: on iPhone tap *Show Details*, then *visit this website*; on Android Chrome tap *Advanced*, then *Proceed*. Phones only hand the gyroscope and the microphone to such a secure page.
- **Looking around:** tap *Gyro* and turn the phone like binoculars; tilt it to look up or down. Without the gyroscope, swipe. *Ahead* looks at the bow again, *Zoom* cycles the magnification. On the periscope the phone trains the periscope itself, and *Range* takes a stadimeter range on what is in the crosshair.
- **Reporting:** tap *Report by voice* and say what you see, for example "Ship bearing 040, range 5 miles", "aircraft starboard 30" or "torpedo" (the line of sight then counts as the bearing). Categories: contact, ship, warship, merchant ship, aircraft, submarine, torpedo. Or tap the target in the picture and pick the category.
- **Confirmation:** a report counts only when the lookout really has something of that kind within 10° of the bearing (and, with a range, within 40 % or 1 NM of his estimate). Then it appears on the bridge as a lookout track and in the event log, and the crew browsers speak it. A report of nothing is refused, and the phone vibrates twice.

While a phone holds the bridge lookout, the lookout no longer reports ships, aircraft or torpedoes by himself: only what the player calls reaches the bridge (land is still reported automatically). On the submarine the periscope picture stays with the attack computer, and the crew's own "in sight" notices give way to the phone's reports. Speech recognition uses the phone browser's speech service (Chrome on Android, Safari on the iPhone with Siri and Dictation switched on; Firefox and the other iPhone browsers have none, tap the target there). When it fails the page names the reason. Nothing of the phone lookout is saved.
