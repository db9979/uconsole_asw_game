# 3 Weapons {#station-weapons}

## Purpose {#weapons-purpose}

Weapons control turns a sonar contact into a firing solution. It launches the frigate's wire-guided torpedoes and its own ASROC, drops depth charges, manages the helicopter's stores (buoys, lightweight torpedoes), streams the Nixie towed decoy and releases the AA gun.

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
- ASROC (`A`): 4 rounds per mission. The rocket flies at 500 kn to the target's observed position (1 to 10 NM, current range needed) and drops the helicopter's lightweight torpedo there, set to the preset depth. It needs the same target checks as the torpedo and counts against the doctrine limit.
- Depth charges (`Z`): 20 per mission, dropped as a pattern of 5 (three along the wake 20, 80 and 140 m astern, two thrown 70 m abeam), then 45 s to reload the rack. The ship must make at least 10 kn. The charges sink at 3.5 m/s to the preset depth (15-300 m) or the seabed; each 90 kg charge is lethal within about 25 m and still damages out to about 100 m. Submarines within 5 NM hear the detonation and evade.
- ASW rocket launcher (`R`, RBU/Bofors type): 36 rockets per mission, fired in salvoes of 6, then 60 s to reload. An attack salvo goes to the designated target's observed position 0.4 to 3 NM away (current range needed, same target checks as the torpedo): one round on the aim point, five on a ring of 80 m around it. The rockets fly at 400 kn (about 9 s per NM), and each round sinks at 11 m/s to the preset depth (10-300 m) or the seabed; the 23 kg charges are lethal only within about 14 m and harm out to 60 m, so a rough or stale fix wastes the salvo. **Defence salvo** (`Shift+R`): six rounds in a line 0.3 to 0.8 NM out along the bearing of a torpedo warning at most 5 s old, set to 15 m; a round that goes off within 35 m of a running torpedo destroys it, and the log reports that the torpedo noise ended. Every submarine within 3 NM hears the rockets splash into the water: an AI boat evades at once, the crewed submarine's sonar room reports the splashes with their bearing.

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

- Depth charges only from the stern rack and throwers; the rocket launcher has no contact fuze (every round goes off at its set depth) and no anti-torpedo projectile of its own.
- One torpedo type for the helicopter; the doctrine limit of two own torpedoes running is fixed.
- No depth ceiling difference between Mk1 and Mk2; both run at the set depth.
