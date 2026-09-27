# 7 Engine room {#station-engine}

## Purpose {#engine-purpose}

The engine room sets the propulsion order and manages the ship's acoustic signature. Speed is the most important trade-off in ASW: fast to reach a datum, slow and quiet to hear anything.

## Displays and instruments {#engine-displays}

Page 1 is the engine telegraph with order, speed, shaft RPM and own noise; page 2 shows machinery systems, fuel and damage state.

```text
 TELEGRAPH      kn     own noise
   FLANK        25     |##########|  cavitating
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
             4           15        25
```

- Own noise rises linearly from 4 kn to 25 kn. The propellers cavitate when the blade-tip speed is too high for the water pressure at the screws: in calm water from 15 kn, in heavy seas earlier when pitching lifts the stern. Cavitation raises noise to at least 0.85 and cuts passive sonar range to 35 %.
- QUIET mode reduces own noise to 65 % and limits speed to 12 kn.
- Plant selection (`G`): AUTO runs the plant as before. DIESEL is the quiet plant (own noise about -4 dB, fuel -10 %) but caps speed at 18 kn; TURBINE gives full speed at about +3 dB and +25 % fuel. The choice is shown on page 2 and in the browser's engine room.
- Shaft RPM follows the fixed-pitch propeller: about 5.8 rpm per knot at steady speed (146 rpm at 25 kn). While accelerating the control programme keeps the shaft at most about 11 rpm ahead of the present speed; when slowing down the pitch reverses and the shaft idles at 20 rpm. The own shaft line on LOFAR moves with speed.
- Machinery damage caps speed at 15 kn (damaged) or 8 kn (destroyed).
- Fuel burn follows the power the propellers deliver: at steady speed it grows with the cube of speed, accelerating and braking cost extra. A lighter ship (burnt fuel) accelerates slightly faster; floodwater makes it slower and deeper. Heavy seas add resistance and cost up to about 1 kn at FULL. With empty tanks the shaft stops and no engine order is accepted.

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
- No refuelling at sea.
