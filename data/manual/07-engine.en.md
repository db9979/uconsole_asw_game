# 7 Engine room {#station-engine}

## Purpose {#engine-purpose}

The engine room sets the propulsion order and manages the ship's acoustic signature. Speed is the most important trade-off in ASW: fast to reach a datum, slow and quiet to hear anything.

## Displays and instruments {#engine-displays}

The engine room is a machinery control console. Page 1 shows the engine telegraph as a column of lit steps, a large speed gauge (ordered speed as an amber mark, the damage speed limit in red), gauges for shaft RPM and own noise (cavitation zone in red) and lamps for shaft, plant, course, acoustic mode, cavitation and speed limit. Page 2 **Systems** has an annunciator panel of status lamps (dark when off, green while running, amber for a caution, red for an alarm) with a master lamp counting alarms and cautions, the fuel bunker as a tank column with stock, burn, endurance and range, gauges for roll, pitch and hull list, and a mimic of the ship's sections from bow to stern between the starboard and port hull, each with its water level, state, flooding and fire LEDs and the numbered repair teams at work.

```text
 TELEGRAPH      kn     own noise
   FLANK        31     |##########|  cavitating
   FULL         16     |#######   |  cavitating above 15 kn
 > HALF         10     |####      |
   SLOW          6     |##        |
   STOP          0     |          |
   (ASTERN       3 kn, separate state)

 noise  ^                    ____ cavitation (>= 0.85)
        |                ___/
        |           ____/
        |      ____/
        |_____/
        +----+------------+--------+---> kn
             4           15        31
```

- Own noise rises linearly from 4 kn to 31 kn. The propellers cavitate when the blade-tip speed is too high for the water pressure at the screws: in calm water from 15 kn, in heavy seas earlier when pitching lifts the stern. Cavitation raises noise to at least 0.85 and cuts passive sonar range to 35 %.
- The lamp of the ordered step is lit (ASTERN in amber). When a direct speed (`V` on the bridge) lies between two steps, a warning line names the ordered speed, so HALF 10 kn with 12 kn ordered is never mistaken for HALF.
- QUIET mode reduces own noise to 65 % and limits speed to 12 kn.
- Plant selection (`G`): AUTO runs the plant as before. DIESEL is the quiet plant (own noise about -4 dB, fuel -10 %) but caps speed at 18 kn; TURBINE gives full speed at about +3 dB and +25 % fuel. The choice is shown on page 2 and in the browser's engine room.
- Shaft RPM follows the fixed-pitch propeller: about 5.8 rpm per knot at steady speed (146 rpm at 25 kn, 181 rpm at the 31 kn flank speed). While accelerating the control programme keeps the shaft at most about 11 rpm ahead of the present speed; when slowing down the pitch reverses and the shaft idles at 20 rpm. The own shaft line on LOFAR moves with speed.
- Machinery damage caps speed at 15 kn (damaged) or 8 kn (destroyed).
- Fuel burn follows the power the propellers deliver: at steady speed it grows with the cube of speed, accelerating and braking cost extra. A lighter ship (burnt fuel) accelerates slightly faster; floodwater makes it slower and deeper. Heavy seas add resistance and cost up to about 1 kn at FULL. With empty tanks the shaft stops and no engine order is accepted.
- **Engine-room console (browser):** in the browser the Engine room's picture area is a machinery control console. An **annunciator panel** of status lamps (dark when off, turquoise while running, amber for a caution, flashing red for an alarm, each with its value) shows shafts, plant auto, diesel, gas turbine, silent running, cavitation, fuel, speed limit, machinery state, flooding and fire in the engine room, repair teams, fires and flooded sections aboard, grounding, towed array, sea state and roll; the master lamp in its plate counts the alarms and cautions. Below it are round **gauges** for speed (with the ordered speed as an amber mark and the damage speed limit in red), shaft RPM, own noise (cavitation zone in red), fuel, roll and pitch, the **fuel bunker** with stock, capacity, consumption, endurance and range, and the **ship sections** from bow to stern between the starboard and port hull strips, each with its water level, state, flooding and fire lamps and the repair teams at work. The console only shows; the orders stay in the station panel on the right.

## Keys {#engine-keys}

<!-- keys:engine -->

## Standard procedure {#engine-sop}

<!-- sop:engine -->

## Pro tips {#engine-tips}

- Speed changes take minutes; order slow-down early before a listening leg.
- The towed array can only be streamed or recovered between 3 and 12 kn; at more than 20 kn with cable out it is lost.
- A hostile submarine hears you better than you hear it when you cavitate. Sprint only when you are far from the expected contact.

## Not modelled {#engine-limits}

- No individual shaft control; the plant choice applies to both shafts.
