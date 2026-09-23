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
| HFDF | about 95-150 NM ground wave | +/-8 deg bearing (sky wave +/-16) |
| Lookout | 12 NM surface, 5 NM surfaced sub, 20 NM air | x0.25 (new moon) to x0.45 (full moon) at night; fog and sea state reduce |

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
| Hazards | up to 64 charted wrecks and submerged rocks (tops at least 15 m deep) |

## Opposing submarines {#ref-subs}

| Class | Quietness | Max depth | Torpedoes |
|---|---|---|---|
| Diesel (older) | 0.75 | 200 m | 4 |
| AIP (modern) | 0.85 | 250 m | 5 |
| Nuclear attack | 0.92 | 400 m | 8 |

Submarines evade for 240 s after hearing a ping or a torpedo, may launch a decoy, lie in wait, snorkel (detectable by HFDF and ESM) and sometimes ping from 15 NM or less.

Submarine physics: the hull accelerates toward an ordered speed (no instant sprints); hydroplanes need speed (below about 4 kn depth changes are slow); radiated noise rises about 12 dB per doubling of speed and jumps when the screw cavitates, and the cavitation speed rises with depth; a torpedo launch makes an 8 s transient; a badly flooded boat blows ballast once and rises fast and loud; operating below test depth fatigues the hull, and 1.5 x test depth crushes it; a lurking boat holds its position against the current. Submarines sense like you do: passive bearings from their own sonar, a range only after their own TMA legs (a few minutes), ESM only with the mast up, the datalink only at mast depth or snorkelling, and a torpedo alarm takes the crew a few seconds (2-15 s) before the boat evades. Surface ships lose top speed in heavy seas (small ships more).

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
