# 4 Damage control {#station-damage}

## Purpose {#damage-purpose}

Damage control keeps the ship afloat and the stations working after a hit. Three repair teams fight flooding and fire in nine compartments. Every compartment houses a station; a damaged compartment degrades it, a destroyed one disables it for the rest of the mission.

## Displays and instruments {#damage-displays}

Page 1 is the ship schematic; page 2 lists details per compartment (flooding, fire, trend, teams on scene, heel); page 3 is the crew's watch bill.

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
- **Counter-flooding:** with `C` and a list of 5 degrees or more, damage control opens the flooding valve of the high hull side; water enters at 0.5 % of the room per second until the list is cancelled, never past 60 % of that side, and the valve closes by itself below 1 degree (or with `C` again). The water is real floodwater: it adds weight and draught and a team has to pump it out later.
- **Trim:** floodwater forward or aft trims the ship (bow down counts positive). Every degree costs 0.5 kn of top speed and, bow down, adds own noise at the bow sonar. The stability line on page 2 shows list, trim and the open valve.
- **Steering gear and stabilizers:** the steering gear sits aft under the flight deck. If that compartment is destroyed, the rudder jams at its last angle until the room is repaired. A destroyed hull compartment on either side knocks out the fin stabilizers, so the ship rolls more in a seaway. Floodwater adds weight: the ship sits deeper and accelerates more slowly.

Station effects: a station loses capability continuously with flooding and fire in its room (sonar and radar range shrink gradually); a destroyed room disables it. A damaged engine room caps speed at 15 kn, a destroyed one at 8 kn; a damaged or destroyed weapons room blocks torpedo launches; a destroyed flight deck prevents helicopter launch and recovery; a destroyed operations room also disables ESM.

## Crew and watches {#damage-crew}

Page 3 (Crew) shows the watch bill. The ship's company stands in three watches: one is on duty and tires, the other two rest and recover. The duty watch is relieved automatically every hour of game time (a real watch is four hours; the game compresses it so a session sees the rotation), or earlier with `W` on this page. For the first minute after a relief the new watch settles in and works at 85 %.

- **Fatigue** (0 to 100 % per watch) rises by about 25 % in a normal hour on duty and falls again at rest. Up to 25 % it costs nothing, so normal rotation keeps the crew at full performance. Above it, every 10 % costs 6 % performance.
- **Action stations** (`G` here or on the Bridge) put every watch on duty: the crew is 10 % more alert, but nobody rests and everybody tires in 90 minutes from fresh to exhausted, faster while fighting fire or flooding. There is no relief at action stations; standing down hands the watch to the freshest section. Stand to for an attack and stand down afterwards: after about half an hour at action stations the bonus is used up.
- **Morale** starts at 70 %. A sunk submarine (+15), a rescue (+12) or another task done (+6) raise it; a compartment damaged (-6), a task failed (-8) or declined (-2) lower it; a repaired compartment gives +2. Low morale tires the crew faster; each 10 % of morale changes performance by 2 %.
- **Performance** is what the crew delivers: the sonar operator needs a stronger signal (every 10 % lost raises the recognition threshold by 1 dB, so the passive ranges shrink), the lookout needs more contrast to sight, recognize and identify, and the repair teams patch, pump and fight fire at that pace. Page 3 lists the current values; the status ticker shows `CREW` with the performance, or `GQ` at action stations.
- The crewed opposing submarine has its own watch bill with the same rules (see the reference chapter).

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

- No individual crew members, casualties or sleep by the clock; watches are relieved every hour of game time.
- Counter-flooding only between the two hull sides; no selective flooding of other rooms.
