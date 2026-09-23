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

- Own noise rises linearly from 4 kn to 25 kn. From 15 kn the propellers cavitate: noise is at least 0.85 and passive sonar range is cut to 35 %.
- QUIET mode reduces own noise to 65 % and limits speed to 12 kn.
- Shaft RPM is about 20 + 2.4 x speed. The own shaft line on LOFAR moves with speed.
- Machinery damage caps speed at 15 kn (damaged) or 8 kn (destroyed).
- Fuel burn grows with speed. With empty tanks the shaft stops and no engine order is accepted.

## Keys {#engine-keys}

<!-- keys:engine -->

## Standard procedure {#engine-sop}

<!-- sop:engine -->

## Pro tips {#engine-tips}

- Speed changes take minutes; order slow-down early before a listening leg.
- The towed array can only be streamed or recovered between 3 and 12 kn; at more than 20 kn with cable out it is lost.
- A hostile submarine hears you better than you hear it when you cavitate. Sprint only when you are far from the expected contact.

## Not modelled {#engine-limits}

- No separate gas turbine / diesel plant selection and no individual shaft control.
- No refuelling at sea.
