# 1 Bridge {#station-bridge}

## Purpose {#bridge-purpose}

The Bridge conns the frigate: course, speed and position relative to coast, contacts and threats. Every sensor depends on how the ship is driven. Fast and straight is loud and blind; slow, steady legs with deliberate turns make sonar and TMA work.

## Displays and instruments {#bridge-displays}

Page 1 (navigation) shows the chart and four panels; page 2 (press `1` again) shows the mission briefing.

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

- **Course / rudder:** current course, ordered course, rudder angle and turn radius.
- **Speed / acoustics:** telegraph order, speed, own noise in percent and a CAVITATION warning above 15 kn.
- **Tactical picture:** observed threats (for example a torpedo bearing or missile threat), sensor state (radar, TAS), assets (helicopter, buoys) and weather/day-night.
- **Chart:** synthetic chart depth and coastline, own ship, tracks published by the other stations. Wheel or `Q`/`E` zoom, drag pans, `K` follows own ship.

## Bridge lookout reports {#bridge-lookout}

The bridge lookout (eye height 18 m, 7x50 binoculars) reports sightings in the event feed as `AUSG` lines, for example `Bridge lookout: frigate (Admiral-Gorshkov-Fregatte) bearing 040°, 3.8 NM`. The Remote Crew bridge lists the same reports under "Lookout reports". A contact is reported in up to three steps as it closes, each step once:

- **Sighted:** only the kind of object is clear (vessel, aircraft, small object on the surface).
- **Class:** the silhouette shows the class, for example merchant ship, warship, aircraft carrier, fishing vessel, speedboat, surfaced submarine, airliner or military aircraft.
- **Type:** close in the lookout names the type: cargo ship, tanker, passenger ship, tug, frigate, destroyer, corvette or combat aircraft; warships and military aircraft also with their class name. Merchant ships and airliners are identified by name, AIS or transponder, not by eye, so the lookout never reports their name or airliner type.

Class and type need a finer resolved silhouette than the sighting (Johnson criteria): by clear day a tanker is classed at about 7 NM and a frigate identified at about 4 NM, a speedboat is classed only inside 3 NM, and at night the type is made out only within a few cables. Fog, rain and sea state shorten every step. The lookout also calls "land in sight" with the bearing of the nearest coast, and a torpedo wake with a banner. The class is held while the lookout keeps the contact. It appears in the chart and OPZ tooltips as "Lookout: ..." and is an observation only: it never sets the OPZ classification or the affiliation.

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
- The turn rate grows with speed (about 0.75 deg/s at 10 kn, 1.2 at 16 kn, 1.9 at 25 kn), so the turning circle stays near 0.4 NM. A stopped ship cannot turn. Speed changes take minutes: about 90 s to 90 % of FULL, and a stop from FULL uses reverse propeller pitch and takes about 90 s. Start evasive turns early.
- In a hard turn at speed the ship heels outward a few degrees; in heavy seas the fin stabilizers damp the roll, but only with steerage way.
- In shallow water the hull squats: at 25 kn the draft grows by up to 3 m when the water is less than about five draughts deep. Slow down in shoal water.
- Sprint-and-drift: sprint at FULL to a new position, then slow to 4-6 kn and listen.
- Heavy flooding on one side gives a list and a steady yaw pull; correct with rudder.
- The ship cannot run aground onto land; it is pushed back, but shallow water limits the helicopter dipping depth (10 m bottom clearance).
- Water depth follows the tide (semi-diurnal, about 12.4 h, up to a few metres in shallow water). A passage that is safe at high water can ground the hull at low water; the HQ weather bulletin reports the current tide at the ship.
- Wind pushes the surface water: about 3 % of the wind speed, 20 degrees to the right of downwind, on top of the steady ocean current.

## Not modelled {#bridge-limits}

- No time acceleration and no autopilot waypoints for the frigate.
- No separate torpedo alarm procedure: incoming torpedoes appear as sonar contacts and in the tactical picture only when observed; the lookout calls out only a visible wake.
- The lookout never reads a ship's name or flag and does not report navigation lights or day shapes.
