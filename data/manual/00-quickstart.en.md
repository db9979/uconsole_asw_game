# Quickstart {#quickstart}

You command the ASW frigate F-217 and man nine stations. Your job: detect, track, classify and sink hostile submarines without losing the ship or harming neutral shipping.

> Everything in this manual describes what the simulation actually models. Features that are not modelled are listed at the end of every station chapter.

## Mission and win conditions {#qs-goal}

- **Win:** sink every assigned target submarine, or survive until the time limit (depends on the mission).
- **Lose:** own ship sinks, a civilian vessel is hit, the target escapes more than 150 NM from its start point, or time runs out on a sink mission.
- Deadline warnings arrive at 5, 2 and 1 minutes remaining.
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

`F1` (or `?`) opens the help overlay at any time. It has four categories: global keys, the current station (keys and standard procedure), sensors and tactics, and this manual.

## Underwater acoustics in five minutes {#qs-acoustics}

- **Passive sonar gives bearing only.** Every contact starts as a line of bearing. Range comes from active ping, TMA, sonobuoys or a cross-fix.
- **Detection is signal against noise.** SNR = 20 log10(effective range / distance). A contact is detected at SNR >= 0 dB. Quiet targets and high sea state shrink the effective range.
- **Own speed is own noise.** Self-noise rises from 4 kn to 25 kn. Above 15 kn the propellers cavitate and passive range drops to about a third.
- **The layer (thermocline) splits the water.** Sensor and target on different sides of the layer lose about 6.5 dB. A ping into the shadow zone below the layer reaches only 35 % of its range.
- **Convergence zones** at roughly 40-70 NM and 90-130 NM return sound from far away (+8 dB).
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
- At 1x one real second is one simulated second. There is no time acceleration; `P` pauses.
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
- `S` / `L`: save / load (slots 1-5). Saves are exact and deterministic: a loaded game continues identically.
- `F10` (or `O` while paused): options - language, fullscreen, audio, large text, tooltips.
- `F9`: Commander / Remote Crew - lets browser clients on the LAN take stations.
