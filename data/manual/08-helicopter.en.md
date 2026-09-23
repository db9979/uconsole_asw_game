# 8 Helicopter deck {#station-helicopter}

## Purpose {#helicopter-purpose}

The HSP-5 "Sea Lynx" extends the frigate's reach: it flies to a datum at 120 kn, drops sonobuoys, dips its own sonar and attacks with lightweight torpedoes, while the frigate stays quiet and out of torpedo range.

## Displays and instruments {#helicopter-displays}

The station has four pages (`8` again cycles them); it opens on page 3.

| Page | Content |
|---|---|
| 1 Status | Fuel, stores, weather limits, deck state |
| 2 Mission | Chart with waypoint, buoys, contacts |
| 3 Sonar | Dipping sonar and buoy contacts, depth, source |
| 4 Acoustic | Listening: BROADBAND / LOFAR / DEMON of the dipping sonar or a passive buoy |

```text
          frigate                           waypoint (1-30 NM)
            *----------- 120 kn -------------->  H  hover + dip
                                                 |
   buoy line (B):  o ---- o ---- o               |  cable 15-300 m
   PASSIVE: bearings;                            )))  dipping sonar
   two crossing bearings (>= 10 deg) = fix          passive 18 NM
   ACTIVE: range + bearing every 30 s               active  14 NM
```

- **Fuel:** 2 hours in forward flight; hovering (dipping) burns 1.3 times as fast. The helicopter returns automatically when only the 20-minute reserve remains. Running dry before landing loses the aircraft. In the hover the wind pushes it slightly downwind of its hover point.
- **Launch limits:** wind up to 32 kn, crosswind up to 22 kn, visibility at least 2 NM, sea state 5 or less, working flight deck, and a deck-motion window (roll within 8 degrees, pitch within 3.5 degrees). Landing also waits for such a window; turning into the sea reduces pitching.
- **Dipping sonar:** depth 15-300 m (default 75 m, at least 10 m above the seabed), passive 18 NM with +/-2 degrees, active ping 14 NM with 30 s cooldown. Dipping needs wind up to 30 kn and visibility of 1 NM.
- **Sonobuoys:** 5 per sortie, 8 NM range, 60 min battery; they drift with the current and a little with the wind. PASSIVE buoys give bearings (like DIFAR); ACTIVE buoys give range and bearing every 30 s (like DICASS).
- **Lightweight torpedo:** 2 per sortie, 55 kn, 12 NM, dropped from the helicopter's position towards the datum, no wire. The target must be classified as submarine.

## Keys {#helicopter-keys}

<!-- keys:helicopter -->

Keys marked "Acoustic" apply only on the acoustic page (page 4).

## Standard procedure {#helicopter-sop}

<!-- sop:helicopter -->

Attack sequence:

1. Localise with two passive buoys or an active buoy/dip ping until the contact has a fresh position.
2. Classify it as submarine (`C`) and set it as target (`M`).
3. Fly to the datum; drop the torpedo (`D` or `Ctrl+Enter`). Keep contact for a second drop if needed.

## Pro tips {#helicopter-tips}

- Put the dipping sonar below the layer (measure it with the bathythermograph at Sonar) to hear deep submarines.
- Lay buoys ahead of the target's estimated track, not on top of the last datum.
- `F` confirms a helicopter contact; `Shift+G` releases it to Operations like a sonar contact.
- On the acoustic page, `T` switches the listening source between the dip and each passive buoy.
- Recall the helicopter in time (`H`): landing needs a working flight deck, and stores are not replenished between sorties.

## Not modelled {#helicopter-limits}

- No buoy patterns (field, barrier) and no frequency channel management; buoys are dropped one at a time.
- No MAD (magnetic anomaly detector) and no radar on the helicopter.
- Only one helicopter.
