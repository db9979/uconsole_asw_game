# 8 Helicopter deck {#station-helicopter}

## Purpose {#helicopter-purpose}

The HSP-5 "Sea Lynx" extends the frigate's reach: it flies to a datum at 120 kn, drops sonobuoys, dips its own sonar and attacks with lightweight torpedoes, while the frigate stays quiet and out of torpedo range.

## Pages {#helicopter-pages}

The station has four pages (`8` again cycles them); it opens on page 3.

| Page | Content |
|---|---|
| 1 Status | Status console: state lamps, fuel, home bearing, stores, flight weather, deck motion |
| 2 Mission rules | Waypoint bearing and range, fuel margin for the return, launch, dip and weapon keys, buoy pattern, MAD, radar, ROE |
| 3 Sonar | Dipping sonar and buoy contacts, depth, source |
| 4 Acoustic | Listening: BROADBAND / LOFAR / DEMON of the dipping sonar or a passive buoy |

## Displays and instruments {#helicopter-displays}

![Helicopter deck on the uConsole](figure:station-helicopter)

![Helicopter deck in the Remote Crew browser](figure:web-helicopter-desktop)

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
- **Start preparation:** the helicopter is never ready at once. `H` (browser: *Launch helicopter*) starts 5 minutes of preparation in the hangar (checks, fuel, weapons, crew brief); the state reads START PREP with the time left and the HANGAR lamp turns amber. Then it lifts off at the next launch window; until one comes the state reads READY, WAITING. `H` again (browser: *Stop start preparation*) stops the preparation. After every landing the next launch needs the full preparation again, so order it early. The AI frigate waits for it too.
- **Refuelling:** the tank is full at the start of a mission. After a landing the helicopter keeps the fuel it came back with and is refuelled on deck: 15 minutes from empty to full (8 minutes of flight per minute on deck). The state reads REFUEL with the time to a full tank and the HANGAR lamp turns amber. A launch order does not wait for a full tank: the helicopter lifts off after its preparation with the fuel aboard by then, but never with less than 30 minutes (the reserve plus 10 minutes); short of that it reads REFUEL with the time to that minimum. Torpedoes and buoys are not reloaded: the stores aboard are the whole mission's load. The AI frigate refuels the same way.
- **Launch limits:** wind up to 32 kn, crosswind up to 22 kn, visibility at least 2 NM, sea state 5 or less, working flight deck, gusts up to 40 kn, cloud ceiling at least 300 ft, no severe icing, and a deck-motion window: roll within 8 degrees and pitch within 3.5 degrees for a quiet period of at least 6 s. Light icing costs 20 % more fuel; the weather & sonar analysis (`0`) shows CLEAR, LIMITED or NO-GO. Landing also waits for such a window. Page 1 shows the **deck motion** beside the stores: the stern seen from aft rolling against the horizon, a pitch bar with its limits and a bar that fills during the quiet period (green: window open, amber: inside the limits but not yet quiet long enough, red: outside). Running into the sea at speed pitches harder (the ship meets the waves faster), with the sea abeam it rolls; slowing down and taking the sea a little off the bow gives the most windows, at the cost of time on the hunt.
- **Dipping sonar:** depth 15-300 m (default 75 m, at least 10 m above the seabed), passive 18 NM with +/-2 degrees, active ping 14 NM with 30 s cooldown. Dipping needs wind up to 30 kn, visibility of 1 NM and no icing.
- **Sonobuoys:** 5 per sortie, 8 NM range, 60 min battery; they drift with the current and a little with the wind. PASSIVE buoys give bearings (like DIFAR); ACTIVE buoys give range and bearing every 30 s (like DICASS).
- **Buoy patterns:** with `X` a pattern is planned: a queue of drop points about the waypoint: a 2x2 field (1.5 NM spacing), a barrier across the bearing from the ship to the waypoint (3 NM spacing) or a circle of 1.5 NM radius, each with up to 4 buoys of the remaining stock. The helicopter flies the points one after the other and drops the ordinary single buoy (in the selected mode) at each; SINGLE clears the queue, returning home drops it.
- **MAD run:** with `Shift+M` and the dipping sonar stowed the helicopter descends to 30 m and slows to 90 kn. A submerged hull within about 400 m slant range is detected on a stateless draw per sensor tick (sure inside 250 m) and reported as a MAD position fix without depth or course; it feeds the weapons' range check and, once the helicopter releases its contact, Operations.
- **Surface-search radar:** searches whenever the helicopter is airborne with the dipping sonar stowed (status line on page 2). From 150 m it sees ships out to 40 NM, surfaced submarines and raised snorkels or periscopes inside its radar horizon (about 30 NM). A mast is small: in calm water it shows at about 10 NM, in sea state 3 at 3-5 NM, and in sea state 5 the clutter hides it. Every contact goes to Operations as a `RADAR-HELO` track with the helicopter as observer, one look every 2 s. A crewed submarine's ESM hears the radar and can warn its crew. `Ctrl+R` (as the patrol aircraft's; browser: *Switch radar off*/*on*) switches the radar off and on again; switched off it neither sees nor radiates, and it stays off (saved) until switched on. An AI submarine with its mast or snorkel raised hears an aircraft radar within 40 NM (inside the radar horizon to its mast) on four of five 5-s looks, goes 40 m below snorkel depth and puts off snorkeling for 15 minutes while its battery holds more than 5 %; so a radiating helicopter drives snorkelers down, a silent one may catch them at the surface.
- **Crew's eyes:** while the helicopter flies its crew keeps a lookout too, with the bridge lookout's contrast model from its altitude (150 m, 20 m while dipping): it sees a raised periscope's or snorkel's feather at the same range as the lookout, independent of the radar and without radiating. The sighting goes to Operations every 2 s as a `HELO-EYE` track, at half the range as a submarine.
- **Lightweight torpedo:** 2 per sortie, 45 kn, 6 NM, dropped from the helicopter's position towards the datum, no wire. The target must be classified as submarine.

Page 1 is the helicopter's status console. A strip of state lamps lights where the aircraft is: HANGAR (amber during the start preparation and while refuelling), DECK (green when it may launch now, amber while weather or deck motion hold it, red with the flight deck out of action), AIRBORNE (red when the aircraft is lost), DIPPING (amber while the dome goes down or comes up) and RETURN.

Below it a fuel tank with the 20-minute reserve as an amber mark (in the hangar it fills while refuelling; hovering the pointer over the status explains what the helicopter is waiting for), a rose with the bearing back to the ship and the aircraft's course needle, and readouts: state, endurance (and in the hover, which burns 1.3 times as fast), bingo (fuel left after the flight home and the reserve), bearing, distance and flight time back to the ship, flight course and the dipping sonar's state and depth. The resources show torpedoes and buoys aboard as pips, the buoys in the water and the datalink, then lamps for the flight weather (CLEAR, LIMITED or NO-GO), the deck window, the dipping weather, dome, ping, water entry and radar. The deck-motion gauge is at the foot; in a small window or with large text the lower lamp row and then the gauge give way.

Page 3 shows the dipping sonar like a console: lamps for dome (green in the water, amber while lowering or raising), ping ready and water entry clear, a side view of the dip (grey air with the helicopter on top, a bold blue waterline, then the water darker with depth, the layer as an amber line and the dome on its cable; the browser draws it beside the dip scope), and a scope with the dipping and buoy bearings as wedges as wide as their error. Page 4 draws its waterfalls in the same phosphor colours as the ship's sonar.

## Keys {#helicopter-keys}

<!-- keys:helicopter -->

Keys marked "Acoustic" apply only on the acoustic page (page 4).

## Mouse {#helicopter-mouse}

Every key in the key bar at the foot of the station can be clicked; holding the button holds the key. Lamps, page tabs and key hints in the text are clickable too (chapter Tools, Mouse). In addition:

- On page 2 the keys named in the rules (`H`, `Y`, `U`/`V`, `Shift+A`, `B`, `D`, `Shift+B`, `Shift+M`, `Ctrl+R`) are switches: a click presses them.
- On the acoustic page a click on the source label switches the listening source.
- On the chart the wheel zooms, dragging pans (it ends `K` follow) and a click pins a tooltip.

## Standard procedure {#helicopter-sop}

<!-- sop:helicopter -->

Attack sequence:

1. Localise with two passive buoys or an active buoy/dip ping until the contact has a fresh position.
2. Classify it as submarine (`C`) and set it as target (`M`).
3. Fly to the datum; drop the torpedo (`Ctrl+Enter` or `D`). Keep contact for a second drop if needed.

## Pro tips {#helicopter-tips}

- Put the dipping sonar below the layer to hear deep submarines. The dip gauge shows the layer at the helicopter only once the lowered dome has passed through it; before that it shows only the charted water depth.
- Lay buoys ahead of the target's estimated track, not on top of the last datum.
- `F` confirms a helicopter contact; `G` releases it to Operations as at the sonar; `Shift+↑`/`Shift+↓` select the next dipping-sonar contact; `W` puts the waypoint on the selected contact's position (as the patrol aircraft's `W`; a bearing-only contact has none). A click on the chart (uConsole and browser, also on a symbol or label, only a sonar contact selects that contact) puts the waypoint exactly on that point; the chart marks it as HSP-5 WP with a dashed track from the helicopter. The helicopter slows down on the approach and stops on the point (within about 20 m); the arrow keys still move the waypoint in 15-degree and 1 NM steps from the ship.
- On the acoustic page, `T` switches the listening source between the dip and each passive buoy.
- Recall the helicopter in time (`H`): landing needs a working flight deck, and stores are not replenished between sorties.

## Not modelled {#helicopter-limits}

- No frequency channel management for buoys.
- The helicopter radar has no power or sector settings, only on and off; an AI submarine hears it only with its mast or snorkel up.
- Only one helicopter.
