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

`F2` hands the current station to the autocrew; `F3` shows which stations run automatically. Use it when you want to concentrate on one or two stations.

## Controls {#qs-controls}

The game runs at 1280x720 and is designed for the uConsole keyboard and trackball. The trackball acts as a joystick: horizontal steers on the Bridge, vertical steps the station's main selection elsewhere. A mouse works too: wheel zooms charts, drag pans, click pins a tooltip.

Global keys (all stations):

<!-- keys:global -->

In the Remote Crew browser (Commander, `F9`) stations are operated with buttons; the keyboard helps with navigation:

<!-- keys:web -->

The bottom status ticker shows the newest event and key telemetry; `F11` opens the full event log and telemetry over the station without stopping it or taking its keys. `F1` (or `?`) opens the help overlay at any time. It has four categories: global keys, the current station (keys and standard procedure), sensors and tactics, and this manual.

## Underwater acoustics in five minutes {#qs-acoustics}

- **Passive sonar gives bearing only.** Every contact starts as a line of bearing. Range comes from active ping, TMA, sonobuoys or a cross-fix.
- **Detection is signal against noise.** The passive sonar equation SE = SL - TL - NL + DI - DT decides: the target's source level (louder = farther), transmission loss (spreading, absorption, layer and path losses), noise (own self noise plus wind, rain and nearby shipping), and the array gain. A contact is detected at SE >= 0 dB. Wind and rain matter most when you run slow and quiet; at high own speed your own noise dominates.
- **Own speed is own noise.** Self-noise rises from 4 kn to 25 kn. Above 15 kn the propellers cavitate and passive range drops to about a third.
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

- Menu: `1`-`4` scenario (4 = random with custom difficulty), `W` world mode, `R` new seed, `F` fullscreen, `Enter` start.
- **Training** (main menu): four guided lessons, each a short mission with a hint banner that waits for you: 1 listen and take bearings, 2 target motion analysis, 3 torpedo attack, 4 helicopter and sonobuoys. In lessons 1, 2 and 4 the boat is neutral and never attacks; lesson 3 is a real attack that ends when the boat sinks. The other lessons end as won after their last step. `R` at the end runs the lesson again. A saved lesson restarts its hints at step 1 after loading and passes the steps that are already done.
- **Campaign** (main menu): six linked missions in the sea area chosen in the menu (world `W` and seed; every mission keeps the same sector). Carried over are the torpedoes left (at least 2, at most 10), compartments still damaged, a lost helicopter and your standing with HQ (0-100, start 50: +15 for a win, -20 for a loss, -10 for a civilian loss, +/-3 per task done or failed). After each mission the ship calls at port: `1` full refit (4 to 8 torpedoes by standing, all repairs, a new helicopter, standing -5) or `2` quick turnaround (half that restock, damage stays aboard, standing +3); `Enter` sails. The campaign ends when the ship is lost, standing falls below 10, or the sixth mission is done. It is kept in `~/.u-jagd/campaign.json`, apart from the save slots: a slot saved during a campaign mission loads as a plain mission; to count, the mission is sailed again from the campaign screen. `N` starts a new campaign (twice while one is running).
- `S` / `L`: save / load (slots 1-5). Saves are exact and deterministic: a loaded game continues identically.
- `F10`: options - language, fullscreen, audio, large text, tooltips, frame rate (30 or 60 FPS; 30 saves CPU on the uConsole and is the default), event log / telemetry as status ticker (default, more room for the station) or docked band, operator assistance off (default: raw data and manual analysis) or training (automatic line labels, blade-rate and catalogue/emitter candidates). Page 2 (`PgDn`/`Tab`): which side the uConsole plays, frigate (default) or hostile submarine; only in the main menu, never saved. A new game asks for it first anyway. Page 2 also holds **anti-aliased chart lines** (off by default; smooths bearing lines, coast and plot at some CPU cost on the uConsole). And **spoken crew reports** (off by default): the crew says torpedo in the water, new contact with bearing, breaking-up noises, torpedo away, hit, action stations, patrol aircraft on station and the mission result aloud, bearings digit by digit. The uConsole speaks through an installed `espeak-ng` (`sudo apt install espeak-ng`) and stays silent without it; Remote Crew browsers have their own switch under Settings (the browser's speech synthesis, in the browser's language). Frigate side only.
- `F9`: Commander / Remote Crew - lets browser clients on the LAN take stations. A free station is taken at once with all of its rights (including direct fire and live sonar audio where the station has them); a station a crewmate holds is requested, and the host can hand it over. The host can revoke a station or single rights at any time, and can make up to two browsers read-only observers (roster key `O`): they watch any station of either unit without holding it, cannot command, and get the SimLog with a debrief timeline and JSON export.
