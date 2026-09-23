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

- **FLOODING:** water rises (0.10 % per second) until a team pumps it down. At 70 % the compartment is DESTROYED.
- **DAMAGED:** stabilised residual leak (0.025 % per second); still needs a team to reach OK.
- **Fire:** a hit starts a fire with 35 % chance. Fire grows by itself and can spread to neighbouring rooms; at 100 % the compartment is destroyed.
- **Total flooding:** the ship sinks at 540 points, which is 60 % average flooding over all nine compartments.
- **Heel:** uneven flooding between port and starboard hull lists the ship (up to 15 degrees) and pulls it to one side.
- **Steering gear and stabilizers:** the steering gear sits aft under the flight deck. If that compartment is destroyed, the rudder jams at its last angle until the room is repaired. A destroyed hull compartment on either side knocks out the fin stabilizers, so the ship rolls more in a seaway. Floodwater adds weight: the ship sits deeper and accelerates more slowly.

Station effects: a damaged sonar room halves sonar range; a damaged engine room caps speed at 15 kn, a destroyed one at 8 kn; a damaged or destroyed weapons room blocks torpedo launches; a destroyed flight deck prevents helicopter launch and recovery; a destroyed operations room also disables ESM.

## Keys {#damage-keys}

<!-- keys:damage -->

On the uConsole the joystick buttons 1-3 assign team 1-3 directly to the selected compartment.

## Standard procedure {#damage-sop}

<!-- sop:damage -->

## Pro tips {#damage-tips}

- One team pumps 0.12 % per second, more than a flooding room gains. Two teams on one room halve the time.
- A room below 35 % flooding changes from FLOODING to DAMAGED; that is the moment to move a team to the next emergency.
- Teams cannot be assigned to a destroyed compartment. Do not waste them there.
- Fire in a room next to the engine or the weapons room is the most dangerous: it spreads into mission-critical spaces.

## Not modelled {#damage-limits}

- No individual crew members, casualties or ammunition cook-off.
- No counter-flooding order; correct heel with repairs and rudder.
