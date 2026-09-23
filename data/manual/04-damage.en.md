# 4 Damage control {#station-damage}

## Purpose {#damage-purpose}

Damage control keeps the ship afloat and the stations working after a hit. Three repair teams fight flooding and fire in nine compartments. Every compartment houses a station; a damaged compartment degrades it, a destroyed one disables it for the rest of the mission.

## Displays and instruments {#damage-displays}

Page 1 is the ship schematic; page 2 lists details per compartment (flooding, fire, trend, teams on scene, heel).

```text
  bow                                                   stern
 +--------+--------+---------+-----+-------+--------+-----------+
 | BRIDGE | SONAR  | WEAPONS | OPZ | RADIO | ENGINE | FLIGHTDECK|
 +--------+--------+---------+-----+-------+--------+-----------+
 |            HULL PORT          |          HULL STARBOARD       |
 +-------------------------------+-------------------------------+
  state: OK -> DAMAGED / FLOODING -> DESTROYED     teams: 1 2 3
```

- **FLOODING:** a hole below the waterline lets water in. The inflow follows the water pressure: fast at first, slower as the water inside rises towards the outside waterline. Rooms high in the ship (bridge) do not flood through a hole. At 70 % the compartment is DESTROYED.
- **DAMAGED:** the hole is patched; a small residual leak remains until a team pumps the room dry.
- **Patch kits:** plugging a hole uses one of 8 patch kits. Without kits a team can only pump against the open hole.
- **Hit location:** the torpedo's impact point decides the compartment; a close burst tears a bigger hole than a distant one. Missiles hit above the waterline and mostly start fires.
- **Fire:** grows with the room's fuel load (engine, flight deck and magazine burn fiercest) and is smothered by rising water. A room that stays hot for about 30 s ignites its neighbours. A flooded switchboard (sonar, operations, radio, engine) shorts and starts an electrical fire. A fire above 90 % in the weapons room cooks off the magazine: the room is destroyed and the neighbouring rooms are holed.
- **Stability:** floodwater adds weight, and loose water surfaces reduce the metacentric height (GM). The ship sinks when the floodwater exceeds its reserve buoyancy, and capsizes when GM is lost or the heel passes 35 degrees.
- **Heel:** off-centre floodwater lists the ship to that side and pulls it off course.
- **Steering gear and stabilizers:** the steering gear sits aft under the flight deck. If that compartment is destroyed, the rudder jams at its last angle until the room is repaired. A destroyed hull compartment on either side knocks out the fin stabilizers, so the ship rolls more in a seaway. Floodwater adds weight: the ship sits deeper and accelerates more slowly.

Station effects: a station loses capability continuously with flooding and fire in its room (sonar and radar range shrink gradually); a destroyed room disables it. A damaged engine room caps speed at 15 kn, a destroyed one at 8 kn; a damaged or destroyed weapons room blocks torpedo launches; a destroyed flight deck prevents helicopter launch and recovery; a destroyed operations room also disables ESM.

## Keys {#damage-keys}

<!-- keys:damage -->

On the uConsole the joystick buttons 1-3 assign team 1-3 directly to the selected compartment.

## Standard procedure {#damage-sop}

<!-- sop:damage -->

## Pro tips {#damage-tips}

- Teams start in the operations room and need about 20 s per compartment to walk to their job; a team is only effective once it has arrived. Keep a team near the engine and weapons rooms.
- A team first patches the hole, then pumps. Patch kits are limited: spend them on rooms below the waterline, not on rooms that already stopped flooding.
- Two teams on one room halve the time. Teams cannot be assigned to a destroyed compartment.
- Fire in a room next to the engine or the weapons room is the most dangerous: it spreads into mission-critical spaces.

## Not modelled {#damage-limits}

- No individual crew members or casualties; no longitudinal trim from flooding.
- No counter-flooding order; correct heel with repairs and rudder.
