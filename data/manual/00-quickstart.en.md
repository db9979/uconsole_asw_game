# Quickstart {#quickstart}

U-Jagd is a real-time simulation of anti-submarine warfare. You play one of two sides: the ASW frigate F-217 with nine stations, whose job is to detect, track, classify and sink hostile submarines without losing the ship or harming neutral shipping, or the hostile submarine with seven stations, which slips past, attacks or survives the hunt.

The game always runs in real time: one real second is one simulated second. There is no time acceleration and no pause; menus, help and options open over the running mission.

> Everything in this manual describes what the simulation actually models. Features that are not modelled are listed at the end of every station chapter.

## Mission and win conditions {#qs-goal}

- **Win:** sink every assigned target submarine, or survive until the time limit (depends on the mission).
- **Lose:** own ship sinks, a civilian vessel is hit, the target escapes more than 150 NM from its start point, or time runs out on a sink mission.
- Time warnings arrive at 5, 2 and 1 minutes remaining: on a sink mission as a deadline, on a survive (convoy) mission as the time until the convoy is safe.
- When the mission ends, `R` restarts it with the same seed (an editor mission restarts itself) and `M` returns to the main menu. During a mission, `Esc` offers "Main menu (without saving)" next to save-and-exit.
- Score: 1000 per submarine sunk, 200 per unused torpedo, 500 for no civilian losses, up to 500 time bonus.

## Stations {#qs-stations}

The ship is split into nine stations. Keys `1`-`9` select a station; pressing the number of the current station again cycles its pages.

![Frigate stations on the uConsole: Bridge, Sonar, Weapons and Damage control](figure:stations-overview-1)

![Frigate stations on the uConsole: OPZ, Radio, Engine room and Helicopter](figure:stations-overview-2)

![Frigate station ELOKA on the uConsole](figure:stations-overview-3)

```text
 1 Bridge      2 Sonar       3 Weapons
 4 Damage      5 Operations  6 Radio
 7 Engine      8 Helicopter  9 Electronic warfare
```

Each station shows only what its sensors and operators know. Sonar contacts are noisy bearings until a ping, TMA, buoy or cross-fix supplies range. No station shows "the truth".

The submarine has seven stations on the keys `1`-`7` (see chapter Submarine). `F2` hands the current station to the autocrew, `F3` shows which stations run automatically (see chapter Tools).

## Controls in 60 seconds {#qs-controls}

- **Stations:** `1`-`9` (submarine `1`-`7`), `Tab`/`Shift+Tab` or a click on a tab in the top bar.
- **Pages:** press the station's number again, `PgUp`/`PgDn`, or click a page tab.
- **Fire:** `Ctrl+Enter` fires torpedoes and missiles. `Enter` alone never fires.
- **Help:** `F1` (or `?`) lists every key of the current station, its standard procedure and this manual. `Esc` cancels an entry or opens the quit dialog.
- **Trackball:** horizontal steers on the Bridge, vertical steps the station's main selection elsewhere.
- **Mouse:** a click on a key in the station's key bar, a lamp, a hint, a tab, a dial or a list row does exactly what its key does, with the same checks. The menu icon in the top bar opens the game menu (help, options, save, load, quit). On charts the wheel zooms and dragging pans (details in chapter Tools).

Global keys (all stations):

<!-- keys:global -->

## Your first patrol (frigate) {#qs-first-patrol}

![Scenario selection, sorted by side](figure:mission-scenario-selection)

1. Main menu: choose **New mission** with the arrow keys and `Enter`, the frigate with `1` and `Enter`, then scenario 1 (Patrol) with `1` and `Enter`; the briefing shows weather and time of day, `Enter` starts.
2. Bridge (`1`): press `1` again for the mission page, read objective and time limit.
3. Engine (`7`): select SLOW or 6-8 kn. Sonar (`2`): stream the towed array with `Y`.
4. Sonar BROADBAND page: look for a bright vertical trace; select it with the arrow keys and press `Enter` to follow it.
5. Classify with `C`, enable TMA with `T`, then turn the ship 30-60 degrees on the Bridge and hold the new leg for a few minutes.
6. When TMA or a ping gives range: release the contact to Operations (`G`), make it the target (`M`).
7. Weapons (`3`): set torpedo depth to the pinged target depth, fire with `Ctrl+Enter`.
8. Watch the sonar for an incoming torpedo; if one appears, run at 24 kn (not FLANK: the Nixie's tow cable parts above 25 kn), turn away and stream the Nixie (`V` at Weapons).

## Your first dive (submarine) {#qs-first-dive}

The quickest way into the submarine is lesson 8 of the training: main menu **Training**, lesson 8 (Listen and hide below the layer) with `8` or the arrow keys, `Enter`. The uConsole plays the submarine for this lesson, and a banner waits for each step:

1. Sonar room (`2`): wait for the frigate in the contact list.
2. Select the contact with `Up`/`Down` and press `C` until it reads warship.
3. Measure the layer with the bathythermograph (`E`).
4. Command (`1`), then `J`: the submarine dives below the measured layer, where the frigate's hull sonar hears it badly.

Lesson 9 continues with evading a pinging frigate (`I` on the Threat page). After the lessons, start **New mission**, the submarine with `2` and `Enter`, then scenario 1 (Breakthrough) with `1` and `Enter`: reach the goal area marked GOAL on the chart. Go slow (`-` on the telegraph or `A` for silent running), stay below the layer, keep the mast down near the frigate and evade with `I` when a ping or torpedo alarm comes in.

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
- The ship turns faster the faster it runs (about 0.75 degrees per second at 10 kn, 1.2 at 16 kn) and cannot turn when stopped; speed changes take minutes. Plan manoeuvres early.
