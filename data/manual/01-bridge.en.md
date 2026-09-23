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
- The ship turns at no more than 0.8 degrees per second and needs minutes to change speed. Start evasive turns early.
- Sprint-and-drift: sprint at FULL to a new position, then slow to 4-6 kn and listen.
- Heavy flooding on one side gives a list and a steady yaw pull; correct with rudder.
- The ship cannot run aground onto land; it is pushed back, but shallow water limits the helicopter dipping depth (10 m bottom clearance).

## Not modelled {#bridge-limits}

- No time acceleration and no autopilot waypoints for the frigate.
- No separate torpedo alarm procedure: incoming torpedoes appear as sonar contacts and in the tactical picture only when observed.
