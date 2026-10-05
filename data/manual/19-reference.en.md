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
| Passive sonar (base) | 20 NM | bearing only; HMS +/-6 deg, TAS +/-2 deg, VDS +/-4 deg |
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
| Helicopter torpedo | 45 kn, 6 NM, 2 per sortie, no wire |
| Hostile torpedo | 40 kn, 20 NM, homes from 3 NM, explodes within about 90 m (at keel depth under a ship), damage falls with distance; faster than the frigate, so outrunning it alone rarely works; an AI submarine attacks a located frigate within 10 NM even when she runs quiet |
| Nixie towed decoy | 2 per mission, 600 s, 0.2 NM cable (10 m at 15 kn, deeper when slower, parts above 25 kn), 60 s reload |
| ESSM | 6 missiles, 30 NM, 2 fire channels |
| CIWS | 1.5 NM, 180 rounds, needs release; 115 deg/s slew, own track radar inside 3 NM |
| AA gun | 240 rounds, needs release |
| Chaff | 6 rounds, 8 NM, 40 % break-lock when bloomed; cloud drifts with the wind for 90 s |

## Own ship {#ref-ship}

| Item | Value |
|---|---|
| Speed | 4-31 kn; telegraph STOP 0, SLOW 6, HALF 10, FULL 16, FLANK 31 kn |
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
| Shipping | cargo ships, tankers and passenger ships steam from destination to destination (the charted ports and exits at the edge of the sea area) on steady courses; they give way under the collision regulations (head-on, crossing from starboard or overtaking: alter 35 deg to starboard when the pass would be closer than 0.5 NM; any ship alters under 0.25 NM) and run from a detonation within 8 NM at full speed for 10 min; work boats and fishing vessels keep wandering, convoys and HQ task ships hold their course |
| Atmosphere | barometer 975-1025 hPa that falls ahead of rising seas; air temperature from the sea, season, day and cold northerly winds (below 0 deg C in winter storms: snow, icing); gusts; cloud ceiling; sun elevation with civil/nautical twilight; moon phase |
| Rain lens | rain freshens the top few metres (up to -1 PSU, mixed away by wind) and lowers the surface sound speed |
| SOFAR channel | an interior sound-speed minimum (about 400-500 m below the surface layer) exists only in deep enough water |

## Sea, weather and effects {#ref-sea-effects}

What the sea and the weather do, and what the screens show of it:

- **Eyepieces:** the bridge binoculars, the periscope and the phone lookout show what happens at sea: water columns of torpedo and depth-charge hits, fire and smoke of a burning ship and a ship going down. Raising the periscope brings it up out of the water with the water running off the glass; in a sea of 3.5 or more waves wash over the head now and then and leave drops.
- **Charts:** marks move smoothly between sensor updates, a fresh ping or detonation rings out from where it happened.
- **Instruments:** needles and telegraph handles move with mass and settle; a new engine order rings the telegraph bell.
- **Bioluminescence:** at night in warm water (from 11 °C surface temperature, full from 16 °C) plankton lights up where water is stirred. Wakes, a periscope's feather and torpedo tracks glow blue-green and are seen farther: a fully glowing wake takes back 40 % of the night's penalty for lookouts on both sides. How strongly a sea area blooms is fixed by its seed.
- **Knuckles:** a hard turn (from 0.9 deg/s) at speed (from 12 kn) leaves a bubble slick of about 150 m where the stern swept round, at most one every 15 s per platform, fading over about 100 s and gone after 5 min. Sound through it loses up to 12 dB (passive and active, at most 20 dB for several), an active ping gets a false echo from it without Doppler, and a wake-homing torpedo close to a strong one may be drawn in and circle there. Frigate and submarines make and suffer them alike; the Bridge log notes the first knuckle of a turn.
- **Wrecks and rocks:** charted wrecks and rocks return active echoes like a stationary target. A helicopter or patrol aircraft passing over a wreck with MAD gets an anomaly without a contact (log: "wreck or submarine?").
- **Thunderstorms:** under a storm (rain 55 % or more) lightning strikes around the ship at random, about one every 12 s in the heaviest rain. A strike lights up the eyepieces and forks down at its bearing, the rain pours harder, and a strike within 10 NM is followed by thunder after the sound's run time (3 s per km). The sferics of the discharges crackle on the ESM roses (ELOKA and the submarine's ESM), on the HF/DF rose and in the browser (badge **Sferics**), and spread every HF/DF bearing, the frigate's on a submarine's call and a submarine's on the frigate's, by up to 75 %. The strikes follow the seed and sim time, so they need no save.
- **Deck motion:** see Helicopter deck, launch limits: launch and recovery need a quiet period of at least 6 s inside the roll and pitch limits.

## Opposing submarines {#ref-subs}

| Class | Quietness | Max depth | Torpedoes |
|---|---|---|---|
| Diesel (older) | 0.75 | 200 m | 4 |
| AIP (modern) | 0.85 | 250 m | 5 |
| Nuclear attack | 0.92 | 400 m | 8 |

Submarines evade for 240 s after hearing a ping or a torpedo (away from the bearing of the torpedo, rocket or charge they heard, else away from the frigate), may launch a decoy, lie in wait, snorkel (detectable by HFDF and ESM) and sometimes ping from 15 NM or less. Near the frigate a submarine may instead creep to a charted wreck within 8 NM and lie still on the bottom beside it for 15-30 minutes.

A submarine with its mast or snorkel raised that hears an aircraft radar (helicopter or patrol aircraft) goes deep and holds off snorkeling for 15 minutes. In the frigate scenarios (1 to 4) a patrol submarine that has heard no ping or torpedo for 10 minutes, keeps more than 2 torpedoes and is more than 10 NM from the frigate torpedoes a merchant passing within 4 NM on about one in seven of its once-a-minute fire windows; each merchant lost costs 300 points.

Submarine physics: the hull accelerates toward an ordered speed (no instant sprints); hydroplanes need speed (below about 4 kn depth changes are slow); radiated noise rises about 12 dB per doubling of speed and jumps when the screw cavitates, and the cavitation speed rises with depth; a torpedo launch makes an 8 s transient; a badly flooded submarine blows ballast once and rises fast and loud; operating below test depth fatigues the hull, and 1.5 x test depth crushes it; a lurking submarine holds its position against the current.

Submarines sense like you do: passive bearings from their own sonar, a range only after their own TMA legs (a few minutes), and a shot on that TMA only once its range error has converged (the difficulty field "enemy fire-control convergence": sigma over range at or below 0.25 in the patrol scenarios, 0.15 for the SSN; a solution older than 90 s or re-opened by your course change is not fired on), ESM only with the mast up, the datalink only at mast depth or snorkelling, and a torpedo alarm takes the crew a few seconds (2-15 s) before the submarine evades.

Surface ships lose top speed in heavy seas (small ships more).

## Enemy commanders {#ref-commanders}

- Every computer submarine commander and the AI hunter frigate's captain has one of four characters, fixed by the seed: **daring** (attacks early, gives way briefly, rarely lies in wait), **fox** (lies in wait long and far, pings little), **cautious** (gives way long, holds fire, keeps its distance) and **hunter** (stubborn, runs a lost bearing down for long).
- Each character changes existing tactics only by factors (attack rate, evasion time, lurking distance; the hunter's closing speed, ping interval, firing range and lead time); across the four they average out.
- In about six of ten missions HQ hints at the character after 90 s (*Intelligence rates the enemy's commander ...*); the debrief names it.
- **Own plans:** every free AI submarine and the AI hunter frigate pick a plan of their own, without any language model. A submarine that hears the frigate closes in (daring, hunter), lies in wait under the layer (fox) or keeps its patrol (cautious); after a ping it goes deep and creeps or hovers listening under the layer; damaged or out of torpedoes it slips away. Without a datum the hunter frigate searches fast, quietly, in sprints with listening pauses or at normal speed, by its captain. Evasion, lying in wait and attacks keep priority.

## Shock, hit picture and seekers {#ref-shock}

- A detonation within 0.6 NM of the own ship shakes the picture and dims the light; within 0.15 NM the instrument glass cracks for a moment. Both are display only.
- When the own side sees a hit happen (a fireball, a torpedo's water column, a ship going down), a small window trained on its bearing opens for 8 s at every station; a hit only heard opens it with the bearing and the noise.
- Through the binoculars and the periscope a made-out ship shows its bow wave and wake: high and white when she is fast, hardly any when slow.
- A homing torpedo's seeker pings slowly while it searches and fast once it has locked on. Frigate and submarine hear it: *torpedo locked on*, *bearing steady* (collision course) and on the submarine's threat page a rough torpedo clock, the time to impact guessed by ear.

## Scoring {#ref-scoring}

| Item | Points |
|---|---|
| Frigate: submarine sunk | 1000 each |
| Frigate: unused torpedo | 200 each |
| Frigate: no civilian losses | 500 |
| Frigate: time bonus | up to 500 |
| Submarine: frigate sunk | 1500 |
| Submarine: convoy sunk | 1200 |
| Submarine: breakthrough or report | 1000 |
| Submarine: escape | 800 |
| Submarine: survived | 600 |
| Submarine: undamaged | up to 500 |
| Submarine: torpedo left | 100 each |
| Realism factor | Beginner 75 %, Standard 100 %, Realistic 125 % |
