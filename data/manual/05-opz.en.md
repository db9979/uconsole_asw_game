# 5 Operations / CIC {#station-opz}

## Purpose {#opz-purpose}

Operations (OPZ / CIC) builds the tactical picture above the water: surface and air radar, AIS, released sonar and ESM bearings, manual fusion of reports, NATO affiliation and air defence. It hands designated tracks to Sonar and Weapons.

## Displays and instruments {#opz-displays}

Page 1 is a full-height free chart with all published tracks; page 2 is the target page for the selected track; page 3 commands the patrol aircraft. The ship-centred radar picture uses its own range scale (10/20/40/80/120 NM, `PgUp`/`PgDn`), independent of the chart zoom (wheel, down to 0.25 NM radius; drag pans; `K` follows). Own units come from the datalink, not from sensors: the ship, the airborne helicopter ("HSP-5 DL") and every own weapon under way, i.e. torpedoes from ship, helicopter or ASROC (`T<n>`), ASROC in flight and ESSM, each with a friendly symbol and a heading tick.

```text
 NATO frame colours (operator annotation, not truth)
   yellow = UNKNOWN   blue = FRIEND   green = NEUTRAL   red = HOSTILE

 report sources:  radar  AIS  sonar(released)  ESM  HFDF  lookout
 track list:  ID  source  bearing  range  course/speed  age  class
```

- **Surface radar:** 30 NM, limited by the radar horizon (20 m mast) and target height; submerged submarines are invisible.
- **Mast and snorkel echoes:** a submarine at periscope depth with a raised mast or snorkel head (a crew's mast, a snorkelling submarine or one at radio depth) returns a tiny echo: in calm sea about half the sweeps find it at 7 NM, at sea state 3 at about 2.5 NM, at sea state 5 under 1 NM. It shows only as a bare dot that glows for about 6 s, with no symbol, no label and no track. Click the dot on the PPI or press `B` (newest dot) to mark it: a radar track `R-…` starts from that measurement and further echoes of the same mast update it; without new echoes it fades after 30 s. Blips and the mark are not saved.
- **Air radar:** 100 NM for aircraft and anti-ship missiles (ASM).
- The antenna turns once every 4 s: a contact is updated only when the beam sweeps past it, and each sweep detects it with a probability that falls with range (50 % at the nominal range for a broadside ship; bow-on targets are seen later, fluctuating echoes can miss a sweep). Sea clutter grows with sea state (about -5 % at sea state 4, -25 % at 6) and rain attenuates the echo (-10 % surface, -20 % air); from sea state 5 measurement errors increase. Inside 3 NM the CIWS search/track radar holds an inbound missile continuously while CIWS is released.
- **AIS:** civilian ships broadcast course and speed every 2-10 s (3 min at anchor) and their name about every 6 min. The VHF receiver hears them only within line of sight (about 20 NM). A radar track of a civilian shows name and course only after the matching AIS report has been received; radar alone gives position only. Optional live AIS/ADS-B traffic is indistinguishable from simulated traffic.
- **Fusion:** mark 2-8 raw reports (`Space`) and fuse them (`L`) into one operator track; `Shift+L` dissolves it. A fusion whose reports come from exactly one sonar contact can be designated to Weapons; its classification counts for fire control unless Sonar has classified the contact itself, and its affiliation applies to that contact. A fusion lasts only while all its reports are current.
- **Automatic fusion:** once a second the OPZ fuses reports of different sensors that lie on top of each other by itself, so one ship seen by radar, lookout and AIS is one contact. It uses the same gates as the correlation suggestions below, but only for a clear match: the score must be well inside the gates, at least one of the two reports needs a position (two bearing-only reports, such as sonar and ESM, are never fused automatically), and neither may have a second candidate from the same kind of sensor (two ships close together stay apart and appear as a suggestion). A further report joins an existing automatic fusion the same way, up to 8 reports. An automatic fusion keeps its ID while at least two of its reports are current and drops a report that has lapsed; with fewer than two it ends. It takes its name from an AIS report, if it has one. `Shift+L` separates it, and those reports are not fused again automatically until one of them is new. With the OPZ down nothing is fused.
- **Sources:** reports inside a fusion are no longer listed or drawn on their own; the fusion stands for them (`H` shows them with the suppressed reports). Each row of the page 1 track list ends with sensor tags: `R` radar, `V` lookout, `A` AIS, `E` ESM, `S` sonar, `H` helicopter, `B` buoy, `M` patrol aircraft, `F` HF/DF, `J` home-on-jam, `D` datalink. Page 2 shows the full names under *Sources* for a fusion (for example `Radar · Lookout · AIS`). The Remote Crew OPZ station lists the sources of each fusion and hides its reports unless *Manage suppressed reports* is on.
- **Correlation suggestions:** the OPZ compares its current reports (at most 30 s old) from different sensors: sonar (only the ship's own bearings and fixes, not buoys or the dipping sonar), radar, ESM, lookout and AIS. Received AIS reports are OPZ reports of their own: the ship's reported position dead-reckoned to now by its reported course and speed, and its name once the static message is in; they count while their data is fresh (up to 10 min at anchor). Two reports whose bearings from the ship agree within 1.5° plus both reports' bearing uncertainties (together at most 8°) and, if both have positions, lie within 1.5 NM plus a tenth of their range of each other are suggested as a pair, provided their motion and class agree too: when both give a course and one moves at 3 kn or more, the courses must agree within 35°; when both give a speed, within 4 kn plus a quarter of the faster; two operator classifications must be equal, and an AIS report never pairs with a report classified as submarine, biological or aircraft. Agreeing classes rank a pair higher. Sonar and AIS are never paired with an air track. The sidebar of page 1 lists the two best (for example `> K03 + R-2  Brg 087°`); `U` fuses the top one exactly like marking both and pressing `L`, `Shift+U` dismisses it. The Remote Crew OPZ station lists all of them, with the course and speed difference and whether the classes agree, and the buttons *Fuse suggestion* and *Dismiss*. At most 4 suggestions exist at a time, each report in only one; reports already fused are left out. Suggestions are hints, not identification, and like fusions and dismissals they are not saved.
- **Suppression:** `Delete` hides a report locally; `H` shows suppressed reports again.

## Patrol aircraft {#opz-mpa}

Page 3 commands a maritime patrol aircraft (MPA) on call from the nearest friendly airfield (without one it comes in from the nearest map edge). It flies at 300 kn in transit and orbits its search area at 200 kn in a 3 NM circle. Each sortie lasts up to 5 h including a 15 min reserve; at bingo fuel it turns home by itself. After landing it needs 30 min on the ground and then flies once more: 2 sorties per mission, each with 16 sonobuoys and 2 lightweight torpedoes.

- `A` requests the aircraft (it first heads for the ship's position) or sends it home.
- `W` sets the search area on the selected track's plotted position (without a selection on the ship); a click on the chart sets it on that point. A bearing-only track has no position to fly to.
- `Z` plans a buoy pattern (field, barrier, circle) about the search area; the aircraft flies the points and drops a buoy at each. `Shift+Z` cancels the pattern. `X` drops one buoy where the aircraft is, `Y` switches its buoys between PASSIVE and ACTIVE.
- `T` switches the aircraft's surface-search radar. From 300 m it sees ships and surfaced or mast-raised submarines out to 60 NM (limited by the radar horizon); its contacts appear as `RADAR-MPA` tracks with the aircraft as observer. AI submarines with a raised mast hear it and go deep (see the helicopter chapter).
- `V` starts or ends **MAD passes** (browser: *Start MAD passes*/*End MAD passes*) while the aircraft is on its way or on station: once there it descends to 60 m and flies straight passes at 180 kn through the search area, turning back 2 NM past it (a cloverleaf). A submerged hull within about 400 m slant range is detected on a stateless draw each second (sure inside 250 m) and reaches the ship over the datalink as a MAD position fix without depth or course on that submarine's sonar contact. A buoy pattern flies first; `A` (home) ends the passes.
- `D` drops a torpedo on the designated sonar contact. The same checks as for the helicopter apply (current contact classified as a submarine, rules of engagement, a fresh fix under standard ROE), and the aircraft must be within 2 NM of the datum.

Everything the aircraft learns reaches the ship only by datalink, out to 250 NM. Its buoys report only while the aircraft is within 50 NM of them; once it leaves or lands they go silent for the ship. The sidebar shows its state, bearing and range, the time left on station, stores, sorties left and how many of its buoys are being relayed.

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
- Affiliation is your annotation. Marking a contact, or a fusion containing it, FRIEND or NEUTRAL blocks every torpedo shot on it.
- Chart symbols follow NATO style on the uConsole and on every Remote Crew map: the frame shows your affiliation (hostile diamond, neutral square, friend wide rectangle, unknown without frame), the inner glyph the observed domain.
- `J` gives a track a shared ID that the whole crew (and Remote Crew browsers) sees.
- `Enter` confirms an engagement against a live (real-world traffic) contact after you classified it hostile; nothing fires automatically on unclassified contacts.

## Not modelled {#opz-limits}

- The helicopter's buoys belong to the helicopter station; OPZ handles only the patrol aircraft's buoys.
- The patrol aircraft has no dipping sonar and no own ESM; it cannot be shot down. MAD passes fly over the search area only, not along a track.
- No automatic fusion: every fusion needs the operator's confirmation. Signatures are compared only as the operator's classifications (no acoustic or emitter fingerprint matching), and AIS carries no ship type.
- No link-based air control of friendly aircraft.
