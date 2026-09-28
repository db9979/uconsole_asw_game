# 1 Bridge {#station-bridge}

## Purpose {#bridge-purpose}

The Bridge conns the frigate: course, speed and position relative to coast, contacts and threats. Every sensor depends on how the ship is driven. Fast and straight is loud and blind; slow, steady legs with deliberate turns make sonar and TMA work.

## Displays and instruments {#bridge-displays}

The top bar shows the station, the mission, the clock, speed and course; the chart header shows only its scale (plus "follow" while `K` follows own ship). Page 1 (navigation) shows the chart and four panels; page 2 (press `1` again) shows the mission briefing; page 3 is the lookout scope. The chart water darkens with the clock in three steps (day, dusk within an hour of 05:30 and 19:30, night), and rain or a storm hatches the chart with dashed diagonals (a storm adds an amber border); both are display only, as on the browser chart. Options page 2 can anti-alias the chart and plot lines.

```text
+---------------------------+----------------------+
|                           | COURSE / RUDDER      |
|   CHART (north up)        |  course 045 > 080    |
|   own ship + wake         |  rudder 15 R         |
|   published tracks        +----------------------+
|   bearing lines / fixes   | SPEED / ACOUSTICS    |
|   helicopter, buoys       |  HALF 10.0 kn        |
|                           |  38% own noise       |
|                           +----------------------+
|                           | TACTICAL PICTURE     |
|                           |  threats, sensors,   |
|                           |  assets, weather     |
+---------------------------+----------------------+
 footer: <- -> course | Up/Down telegraph | U/V direct
```

- **Course / rudder:** current course, ordered course (`→`), rudder angle in whole degrees and, only while turning, the turn radius.
- **Speed / acoustics:** telegraph order, speed, own noise in percent and a CAVITATION warning above 15 kn.
- **Tactical picture:** observed threats (a heard torpedo launch transient or HF seeker pulses, a contact sonar classified as torpedo, or an air track flagged as a possible missile), sensor state (radar, TAS), assets (helicopter, buoys) and weather/day-night. Beside the weather lines a small picture in the start screen's look looks into the wind: the sky of the hour with sun, moon or stars, the clouds, rain, snow or fog and the sea running at the eye, with a wind rose (north up, the arrow blowing downwind) in its corner; the Remote Crew bridge shows the same picture.
- **Chart:** synthetic chart depth and coastline, own ship, tracks published by the other stations. `Q`/`E` zoom in fixed steps (chart height 500, 250, 100, 50, 25, 10, 5, 2, 1 and 0.5 NM), the wheel zooms smoothly down to 0.5 NM; the grid gets finer as you zoom in (down to 0.1 NM). Drag pans, `K` follows own ship.

## Bridge lookout reports {#bridge-lookout}

The bridge lookout (eye height 18 m, 7x50 binoculars) reports sightings in the event feed as `AUSG` lines, for example `Bridge lookout: frigate (Admiral-Gorshkov-Fregatte) bearing 040°, 3.8 NM`. The Remote Crew bridge lists the same reports under "Lookout reports". Bridge page 3 (the lookout scope) shows the sightings north up around the own ship at the range and bearing the lookout measured, coloured by kind (surface, submarine, aircraft, torpedo) and labelled with what he made out, next to visibility, sea state, day/night and the latest reports; `,` and `.` change the scope radius (2 to 30 NM). Above the reports a horizon strip shows the binoculars toward the bow (90° field, true-bearing scale, the horizon moving with the sea, the light of the hour) with the outlines of the lookout's sightings at their measured bearing and range; it is the same renderer as the submarine's periscope. The picture has the start screen's look: by day a blue sky, at dusk a warm horizon, at night stars and the moon in its phase at its bearing with its glitter on the water; clouds, rain, snow and fog follow the weather station, and the silhouettes are drawn in steel with a lit rim, with lit windows at night. From dusk to dawn and in visibility under 2 NM neutral merchant ships and fishing vessels run their navigation lights (warships run darkened): white masthead lights over the forward 225° (two from 50 m length, the aft one higher, 6 NM), the green starboard or red port side light (3 NM), both when she heads straight at you, and the white stern light over the 135° astern (3 NM; under 50 m length one masthead light at 5 NM and the others at 2 NM), never beyond the visibility. Vessels at work add their all-round lights: a trawler green over white (a masthead light only from 50 m), a pilot vessel white over red instead of masthead lights, a survey ship, cable layer or research ship restricted in her ability to manoeuvre red, white, red, and a mine clearance vessel three green; a tug without a tow shows ordinary lights. Civil aircraft show the red left and green right wingtip light and the white tail light (3 NM) and their flashing red anti-collision beacons and white strobes (10 NM); military aircraft fly dark; the silhouette then points its bow the way the lights show, and a lit ship is sighted by its lights even where the dark hull is not (its class still needs the silhouette). The Remote Crew bridge shows the same binoculars as a card ("Lookout binoculars"), trained in that browser only with the arrow buttons (2°, 10°) and "Bow". `B` raises the binoculars large over the chart: a 16° field the operator trains with `,` and `.` (`Shift`: 20° steps) or by clicking the all-round panorama below it, which marks every sighting at its measured bearing with the bow in the middle; the sightings are listed underneath, nearest the line of sight first. The charted coast stands on the horizon of the strip and the binoculars as far as the lookout can see land (at most 20 NM, fading into the haze), and the panorama marks it along its foot; the chart has no elevation, so the hills are an assumed 25 to 70 m. While the binoculars are up, `↑`/`↓` tilt them 2° (`Shift`: 10°, from 20° down to 45° up) instead of working the telegraph, `Q`/`E` zoom them (16°, 8° or 4° field) and `Space` switches the stabilizer, which takes out all but an eighth of the ship's motion; the line under the picture shows tilt and field, and the Remote Crew card has the same buttons for its own browser. The sea follows the wind: looking into it the crests come at you in long rows, looking down-sea their backs run away, across it short crests run sideways, and the ship pitches in a head or following sea and rolls in a beam sea. `B` again returns to the chart; the binoculars are display only and are not saved. A contact is reported in up to three steps as it closes, each step once:

- **Sighted:** only the kind of object is clear (vessel, aircraft, small object on the surface).
- **Class:** the silhouette shows the class, for example merchant ship, warship, aircraft carrier, fishing vessel, speedboat, surfaced submarine, airliner or military aircraft.
- **Type:** close in the lookout names the type: cargo ship, tanker, passenger ship, tug, frigate, destroyer, corvette or combat aircraft; warships and military aircraft also with their class name. Merchant ships and airliners are identified by name, AIS or transponder, not by eye, so the lookout never reports their name or airliner type.

Class and type need a finer resolved silhouette than the sighting (Johnson criteria): by clear day a tanker is classed at about 7 NM and a frigate identified at about 4 NM, a speedboat is classed only inside 3 NM, and at night the type is made out only within a few cables. Fog, rain and sea state shorten every step. The lookout also calls "land in sight" with the bearing of the nearest coast, and a torpedo wake with a banner. The class is held while the lookout keeps the contact. It appears in the chart and OPZ tooltips as "Lookout: ..." and is an observation only: it never sets the OPZ classification or the affiliation.

## Autopilot route {#bridge-route}

The helm can follow a route of up to 8 waypoints. On the navigation page a right click on the chart adds a waypoint; `W` starts a search pattern from the ship's position and course (first a zigzag of 3 NM legs 45° either side of the course, pressed again an expanding square of 1, 1, 2, 2, 3, 3, 4, 4 NM legs turning right, a third time the route is cleared), and `Backspace` clears it. The chart draws the route as an amber line with numbered waypoints and the Course panel shows the next one with its distance. The autopilot sets only the ordered course; speed stays with the telegraph. A waypoint counts as reached within 0.3 NM, then the helm steers for the next one; after the last one the ship holds its course. Any helm order (`←`/`→`, `U`, the trackball or a course from Remote Crew) takes over and switches the route off; with the Bridge out of action no route can be set and an active one is not steered. The route is saved. The Remote Crew bridge has an "Autopilot route" card: "Set waypoints on chart" makes a click on open chart add a waypoint, and buttons start the zigzag or the expanding square or clear the route.

## Keys {#bridge-keys}

<!-- keys:bridge -->

The trackball steers the rudder while the Bridge is selected. `U` and `V` open direct numeric entry; the simulation keeps running while you type. `Enter` confirms, `Esc` cancels.

## Standard procedure {#bridge-sop}

<!-- sop:bridge -->

Combat situation:

1. Torpedo reported: FLANK immediately, turn to put the torpedo bearing astern or on the beam.
2. Order the Nixie at Weapons (`V`); keep turning so the torpedo sees the decoy first.
3. Once clear, reduce speed below 15 kn so sonar can reacquire; never above 20 kn with the towed array out.

## Pro tips {#bridge-tips}

- TMA needs a real change of own velocity. A 30-60 degree turn followed by a steady leg of several minutes gives the best range estimate. Turning on the spot does not help.
- The turn rate grows with speed (about 0.75 deg/s at 10 kn, 1.2 at 16 kn, 1.9 at 25 kn, 2.3 at 31 kn), so the turning circle stays near 0.4 NM. A stopped ship cannot turn. Speed changes take minutes: about 90 s to 90 % of FULL, and a stop from FULL uses reverse propeller pitch and takes about 90 s. Start evasive turns early.
- In a hard turn at speed the ship heels outward a few degrees; in heavy seas the fin stabilizers damp the roll, but only with steerage way.
- In shallow water the hull squats: at 25 kn the draft grows by up to 3 m, at 31 kn by up to 4.6 m, when the water is less than about five draughts deep. Slow down in shoal water.
- Sprint-and-drift: sprint at FULL to a new position, then slow to 4-6 kn and listen.
- Heavy flooding on one side gives a list and a steady yaw pull; correct with rudder.
- The ship cannot run aground onto land; it is pushed back, but shallow water limits the helicopter dipping depth (10 m bottom clearance).
- Water depth follows the tide (semi-diurnal, about 12.4 h, up to a few metres in shallow water). A passage that is safe at high water can ground the hull at low water; the HQ weather bulletin reports the current tide at the ship.
- Wind pushes the surface water: about 3 % of the wind speed, 20 degrees to the right of downwind, on top of the steady ocean current.

## Not modelled {#bridge-limits}

- No time acceleration and no pause. The autopilot steers only course, never speed, and does not avoid land or shallow water.
- No automatic torpedo identification: the alarm rests only on heard intercepts or the sonar operator's classification; a torpedo running silent outside seeker range can arrive unannounced. The lookout calls out only a visible wake.
- The lookout never reads a ship's name or flag and does not report navigation lights or day shapes; the lights are only drawn. No ship in the game anchors, tows, trawls at trawling speed or is not under command, so anchor lights, towing lights and the not-under-command lights never show.
