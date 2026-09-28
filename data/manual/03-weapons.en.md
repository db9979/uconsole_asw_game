# 3 Weapons {#station-weapons}

## Purpose {#weapons-purpose}

Weapons control turns a sonar contact into a firing solution. It launches the frigate's wire-guided torpedoes, manages the helicopter's stores (buoys, lightweight torpedoes), streams the Nixie towed decoy and releases the AA gun.

## Displays and instruments {#weapons-displays}

Page 1 (target) shows the chart with the selected contact, the torpedo depth and the fire-control readiness line. Page 2 (stores) lists tubes, reload timers, torpedo stock, Nixie state, helicopter stores and the torpedo setup line: selected type with its remaining stock, search pattern, seeker enable point and salvo size.

The readiness line is checked top to bottom; the first failed check is shown:

```text
 BLOCKED: NO TARGET            select or take a contact (M)
 BLOCKED: AFFILIATION ...      operator marked it FRIEND/NEUTRAL
 BLOCKED: NO RANGE             ROE STD needs ping/TMA/buoy range
 BLOCKED: NOT CLASSIFIED       classify as submarine or warship (Sonar C)
 BLOCKED: NO TORPEDOES / NO TUBE READY / SALVO LIMIT
 BLOCKED: WEAPONS ROOM DAMAGED
 WEAPONS FREE                  -> T or Ctrl+Enter
```

Torpedo run, seen from above:

```text
 frigate ==wire==> . . . . . /\/\/\/\  ( datum )
                    mid-course      snake search   seeker on
                    to datum        +/-15 deg      inside 1.2 NM
                    (wire update                   -> homes on nearest
                     every 0.5 s)                     candidate
```

- Two torpedo types share the two tubes (60 s reload). Mk1: 45 kn, 12 NM, wire-guided. Mk2: 55 kn but only 8 NM. The scenario stock (default 6) is split 2:1 between Mk1 and Mk2; `W` selects the type, and if no tube holds it a tube unloads and reloads with it (60 s).
- Search pattern (`X`): the snake (+/-15 deg about the datum course, default), a circle of 0.4 NM about the enable point, or a helix that opens from 0.15 NM by 0.15 NM per turn to 1 NM. The pattern runs only once the seeker is enabled and has not acquired.
- Seeker enable point (`,` / `.`): 0.6 to 3.0 NM from the datum in 0.2 NM steps (default 1.2 NM). Earlier enable finds a target that has moved off the datum; later enable keeps the weapon quiet longer.
- Salvo (`Y`): one torpedo, or two in a +/-8 deg spread with their own datums turned about the ship; a spread needs two loaded tubes of the selected type and counts against the doctrine limit.
- Preset depth 10-300 m (default 60 m). A wrong depth is a miss: take depth from a ping, not from TMA.
- The wire updates the datum from the contact's observed position. Without updates it becomes STALE after 3 s and BROKEN after 12 s; the torpedo then continues to the last datum.
- The seeker homes on the nearest candidate: that can be a decoy, a whale or a merchant ship. A civilian hit ends the mission.
- Salvo doctrine SHOOT-LOOK-SHOOT: at most 2 own torpedoes running.

## Keys {#weapons-keys}

<!-- keys:weapons -->

## Standard procedure {#weapons-sop}

<!-- sop:weapons -->

Combat situation:

1. Enemy torpedo reported: stream the Nixie at once (`V`). It lasts 600 s on a 0.2 NM cable; one ready, a second after 60 s. It runs at 10 m at 15 kn, deeper and closer astern when you slow down, and its cable parts above 25 kn. In a turn the cable lags behind.
2. Keep the counter-attack going: a fresh contact keeps the wire datum on the submarine.
3. With the helicopter airborne, a lightweight torpedo (`D`) can reach a distant contact faster than the ship's torpedo.

## Rules of engagement {#weapons-roe}

| ROE | Requirement |
|---|---|
| STD (start) | Current range (ping, TMA or buoy) and classification submarine or warship |
| FREE | Classification only; without range the torpedo is aimed 10 NM down the bearing |

HQ switches to FREE by radio after the first hostile submarine is sunk; the player cannot change ROE. A contact marked FRIEND or NEUTRAL in Operations, directly or through a fusion, can never be engaged.

## Pro tips {#weapons-tips}

- Fire from inside about 6-8 NM: at 45 kn the torpedo needs 8 minutes for 6 NM, and the submarine hears the launch out to 35 NM and starts evading.
- Aim the datum ahead of a moving target by keeping TMA running; the wire follows the observation, not the truth.
- Keep own speed below cavitation while guiding; losing the contact means losing the wire datum.
- The wire is a physical cable: it snaps if the ship runs faster than 20 kn or turns faster than 1.5 deg/s for about 5 s, when the ship-side spool (5 NM of own track) runs out, or when the torpedo has run 1.25 x its range.
- Torpedo range comes from its battery: at full speed it runs the catalogue range, hard manoeuvring throttles it and saves energy; when the battery is empty it coasts for a few seconds and is lost. Turning is slower right after launch (constant turning circle), and depth changes need a moment to build up.
- The warhead has a proximity fuze: it fires at the closest approach inside its radius, and the damage falls with distance (shock factor). A near miss can leave a submarine damaged but able to escape.
- A running torpedo is heard by the target through the sonar equation: quiet submarines in calm water hear it from a few miles, rain and their own speed mask it.
- Only two Nixies per mission: stream the first when a torpedo is likely, keep the second for the next attack.
- Homing seekers lock on the loudest candidate and only switch when another is clearly (6 dB) louder. They ignore echoes without Doppler, so a hovering target is hard to find; a torpedo that overruns a decoy without a hull hit remembers it and re-attacks. Hostile submarine decoys fade as their battery drains; hostile warships stream their own decoys when they hear your torpedo launch.

## Not modelled {#weapons-limits}

- No depth charges, ASW rockets or ship-launched ASROC (ASROC is used only by friendly AI warships).
- One torpedo type for the helicopter; the doctrine limit of two own torpedoes running is fixed.
- No depth ceiling difference between Mk1 and Mk2; both run at the set depth.
