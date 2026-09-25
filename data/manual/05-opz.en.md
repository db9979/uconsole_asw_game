# 5 Operations / CIC {#station-opz}

## Purpose {#opz-purpose}

Operations (OPZ / CIC) builds the tactical picture above the water: surface and air radar, AIS, released sonar and ESM bearings, manual fusion of reports, NATO affiliation and air defence. It hands designated tracks to Sonar and Weapons.

## Displays and instruments {#opz-displays}

Page 1 is a full-height free chart with all published tracks; page 2 is the target page for the selected track. The ship-centred radar picture uses its own range scale (10/20/40/80/120 NM, `PgUp`/`PgDn`), independent of the chart zoom (wheel, down to 5 NM radius; drag pans; `K` follows).

```text
 NATO frame colours (operator annotation, not truth)
   yellow = UNKNOWN   blue = FRIEND   green = NEUTRAL   red = HOSTILE

 report sources:  radar  AIS  sonar(released)  ESM  HFDF  lookout
 track list:  ID  source  bearing  range  course/speed  age  class
```

- **Surface radar:** 30 NM, limited by the radar horizon (20 m mast) and target height; submerged submarines are invisible.
- **Air radar:** 100 NM for aircraft and anti-ship missiles (ASM).
- The antenna turns once every 4 s: a contact is updated only when the beam sweeps past it, and each sweep detects it with a probability that falls with range (50 % at the nominal range for a broadside ship; bow-on targets are seen later, fluctuating echoes can miss a sweep). Sea clutter grows with sea state (about -5 % at sea state 4, -25 % at 6) and rain attenuates the echo (-10 % surface, -20 % air); from sea state 5 measurement errors increase. Inside 3 NM the CIWS search/track radar holds an inbound missile continuously while CIWS is released.
- **AIS:** civilian ships broadcast course and speed every 2-10 s (3 min at anchor) and their name about every 6 min. The VHF receiver hears them only within line of sight (about 20 NM). A radar track of a civilian shows name and course only after the matching AIS report has been received; radar alone gives position only. Optional live AIS/ADS-B traffic is indistinguishable from simulated traffic.
- **Fusion:** mark 2-8 raw reports (`Space`) and fuse them (`L`) into one operator track; `Shift+L` dissolves it.
- **Suppression:** `Delete` hides a report locally; `H` shows suppressed reports again.

## Keys {#opz-keys}

<!-- keys:opz -->

## Standard procedure {#opz-sop}

<!-- sop:opz -->

Air defence sequence (missile inbound):

```text
  40 NM  ASM detected (air radar / ESM seeker bearing)
  30 NM  ESSM envelope          -> E / Ctrl+Enter (2 fire channels)
   8 NM  chaff cone             -> G (40 % break-lock, short blindness)
 1.5 NM  CIWS                   -> must be released with I
```

1. Air radar on (`Shift+R`), select the ASM track (`Left`/`Right`).
2. Chaff and manoeuvre first, then ESSM. Only 6 ESSM are loaded.
3. Keep CIWS released while missiles are inbound; withheld CIWS never fires.

## Pro tips {#opz-tips}

- Radar is a transmission that hostile ESM can intercept. Switch radars off (EMCON) when stealth matters more than the air picture.
- The radar does not know what an air contact is. Threat evaluation flags an air track as a possible missile (ASM) only from its own measurements: faster than 300 kn at or below 150 m, or a jamming strobe; a low, fast attack aircraft can raise the same flag. The flag needs about a second of plots, CIWS and ESSM engage only flagged tracks, and HFDF fixes and unclassified sonar contacts carry no domain until you classify them.
- Anti-ship missiles skim at about 20 m (5 m in the last 5 NM): radar sees them only inside about 20 NM, and a jamming missile gives only a home-on-jam (HOJ) bearing until it burns through. Missiles fly inertially to their launch datum, then their seeker needs the ship inside its cone for 1.5 s before homing; attack aircraft pop up to about 300 m for a few seconds to lock their fire-control radar before each salvo (an ESM warning and an early radar contact).
- Chaff lays a cloud beside the ship that blooms in about 3 s and drifts with the wind; fire it early enough for the cloud to bloom. CIWS must first slew onto the missile and kills mostly in the last few hundred metres.
- Affiliation is your annotation. Marking a contact FRIEND or NEUTRAL blocks every torpedo shot on it.
- Chart symbols follow NATO style on the uConsole and on every Remote Crew map: the frame shows your affiliation (hostile diamond, neutral square, friend wide rectangle, unknown quatrefoil), the inner glyph the observed domain.
- `J` gives a track a shared ID that the whole crew (and Remote Crew browsers) sees.
- `Enter` confirms an engagement against a live (real-world traffic) contact after you classified it hostile; nothing fires automatically on unclassified contacts.

## Not modelled {#opz-limits}

- No sonobuoy management here: buoys belong to the helicopter station.
- No automatic track correlation across sensors; fusion is manual.
- No link-based air control of friendly aircraft.
