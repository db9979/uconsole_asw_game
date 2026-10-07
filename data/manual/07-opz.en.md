# 5 Operations / CIC {#station-opz}

## Purpose {#opz-purpose}

Operations (OPZ / CIC) builds the tactical picture above the water: surface and air radar, AIS, released sonar and ESM bearings, manual fusion of reports, NATO affiliation and air defence. It hands designated tracks to Sonar and Weapons.

## Pages {#opz-pages}

| Page | Shows |
|---|---|
| 1 Picture | Full-height chart with every published track |
| 2 Track details | Target page of the selected track: assign, chaff, missile track, ESSM |
| 3 Patrol aircraft | Orders and state of the patrol aircraft |
| 4 Group | Orders of the consort destroyer in a group hunt |
| 5 Display | What the OPZ chart draws |

## Displays and instruments {#opz-displays}

Every page has three columns: track cards on the left (a click selects a track), the chart in the middle and the page's panel on the right. Page 1 is a full-height free chart with all published tracks; page 2 is the target page for the selected track (its key chips assign the target with `M`, launch chaff with `G` and step the missile track with `←`/`→`; ESSM stays on `Ctrl+Enter`); page 3 commands the patrol aircraft; page 4 commands the consort destroyer of a group hunt; page 5 sets the chart display. The ship-centred radar picture uses its own range scale (10/20/40/80/120 NM, `Q`/`E` as the zoom keys elsewhere; `PgUp`/`PgDn` page), independent of the chart zoom (wheel, down to 0.25 NM radius; drag pans; `K` follows). Own units come from the datalink, not from sensors: the ship, the airborne helicopter ("HSP-5 DL") and every own weapon under way, i.e. torpedoes from ship, helicopter or ASROC (`T<n>`), ASROC in flight and ESSM, each with a friendly symbol and a heading tick; the helicopter wears the NATO rotary-wing sign (a bow tie of two rotor blades) inside the friendly frame, on the uConsole and in the browser. On a real sea area the chart's grid is the graticule with meridians and parallels in degrees and minutes (numbers along the bottom and left edges) and own position stands in its top right corner (`54°21.4'N 010°08.2'E`); only the stylized fixed chart keeps the NM grid.

![OPZ on the uConsole](figure:station-opz-cic)

![OPZ in the Remote Crew browser](figure:web-opz-desktop)

```text
 NATO frame colours (operator annotation, not truth)
   yellow = UNKNOWN   blue = FRIEND   green = NEUTRAL   red = HOSTILE

 report sources:  radar  AIS  sonar(released)  ESM  HFDF  lookout
 track list:  ID  source  bearing  range  course/speed  age  class
```

- **Surface radar:** 30 NM, limited by the radar horizon (20 m mast) and target height; submerged submarines are invisible.
- **Mast and snorkel echoes:** a submarine at periscope depth with a raised mast or snorkel head (a crew's mast, a snorkelling submarine, one at radio depth, or an AI reconnaissance submarine's periscope during its look round) returns a tiny echo: in calm sea about half the sweeps find it at 7 NM, at sea state 3 at about 2.5 NM, at sea state 5 under 1 NM. It shows only as a bare dot that glows for about 6 s, with no symbol, no label and no track. Click the dot on the PPI or press `B` (newest dot) to mark it: a radar track `R-…` starts from that measurement and further echoes of the same mast update it; without new echoes it fades after 30 s. Blips and the mark are not saved.
- **Air radar:** 100 NM for aircraft and anti-ship missiles (ASM).
- The antenna turns once every 4 s: a contact is updated only when the beam sweeps past it, and each sweep detects it with a probability that falls with range (50 % at the nominal range for a broadside ship; bow-on targets are seen later, fluctuating echoes can miss a sweep). Sea clutter grows with sea state (about -5 % at sea state 4, -25 % at 6) and rain attenuates the echo (-10 % surface, -20 % air); from sea state 5 measurement errors increase. Inside 3 NM the CIWS search/track radar holds an inbound missile continuously while CIWS is released.
- **AIS:** civilian ships broadcast course and speed every 2-10 s (3 min at anchor) and their name about every 6 min. The VHF receiver hears them only within line of sight (about 20 NM). A radar track of a civilian shows name and course only after the matching AIS report has been received; radar alone gives position only. Optional live AIS/ADS-B traffic is indistinguishable from simulated traffic.
- **Fusion:** mark 2-8 raw reports (`Space`) and fuse them (`L`) into one operator track; `Shift+L` dissolves it. A fusion whose reports come from exactly one sonar contact can be designated to Weapons; its classification counts for fire control unless Sonar has classified the contact itself, and its affiliation applies to that contact. A fusion lasts only while all its reports are current.
- **Automatic fusion:** once a second the OPZ fuses reports of different sensors that lie on top of each other by itself, so one ship seen by radar, lookout and AIS is one contact. It uses the same gates as the correlation suggestions below, but only for a clear match: the score must be well inside the gates, at least one of the two reports needs a position (two bearing-only reports, such as sonar and ESM, are never fused automatically), and neither may have a second candidate from the same kind of sensor (two ships close together stay apart and appear as a suggestion). A further report joins an existing automatic fusion the same way, up to 8 reports. An automatic fusion keeps its ID while at least two of its reports are current and drops a report that has lapsed; with fewer than two it ends. It takes its name from an AIS report, if it has one, and then also the AIS course and speed over ground (the ship's satellite navigation), so a young radar or lookout estimate does not swing its vector around. `Shift+L` separates it, and those reports are not fused again automatically until one of them is new. With the OPZ down nothing is fused.
- **Sources:** reports inside a fusion are no longer listed or drawn on their own; the fusion stands for them (`H` shows them with the suppressed reports). Each track card ends with sensor tags: `R` radar, `V` lookout, `A` AIS, `E` ESM, `S` sonar, `H` helicopter, `B` buoy, `M` patrol aircraft, `F` HF/DF, `J` home-on-jam, `D` datalink. Page 2 shows the full names under *Sources* for a fusion (for example `Radar · Lookout · AIS`). The Remote Crew OPZ station lists the sources of each fusion and hides its reports unless *Manage suppressed reports* is on.
- **Correlation suggestions:** the OPZ compares its current reports (at most 30 s old) from different sensors: sonar (only the ship's own bearings and fixes, not buoys or the dipping sonar), radar, ESM, lookout and AIS. Received AIS reports are OPZ reports of their own: the ship's reported position dead-reckoned to now by its reported course and speed, and its name once the static message is in; they count while their data is fresh (up to 10 min at anchor). Two reports whose bearings from the ship agree within 1.5° plus both reports' bearing uncertainties (together at most 8°) and, if both have positions, lie within 1.5 NM plus a tenth of their range of each other are suggested as a pair, provided their motion and class agree too: when both give a course and one moves at 3 kn or more, the courses must agree within 35°; when both give a speed, within 4 kn plus a quarter of the faster; two operator classifications must be equal, and an AIS report never pairs with a report classified as submarine, biological or aircraft. Agreeing classes rank a pair higher. Sonar and AIS are never paired with an air track. The sidebar of page 1 lists the two best (for example `> K03 + R-2  Brg 087°`); `U` fuses the top one exactly like marking both and pressing `L`, `Shift+U` dismisses it. The Remote Crew OPZ station lists all of them, with the course and speed difference and whether the classes agree, and the buttons *Fuse suggestion* and *Dismiss*. At most 4 suggestions exist at a time, each report in only one; reports already fused are left out. Suggestions are hints, not identification, and like fusions and dismissals they are not saved.
- **Suppression:** `Delete` hides a report locally; `H` shows suppressed reports again.

## Patrol aircraft {#opz-mpa}

Page 3 commands a maritime patrol aircraft (MPA) on call from the nearest friendly airfield (without one it comes in from the nearest map edge). It flies at 300 kn in transit and orbits its search area at 200 kn in a 3 NM circle. Each sortie lasts up to 5 h including a 15 min reserve; at bingo fuel it turns home by itself. After landing it needs 30 min on the ground and then flies once more: 2 sorties per mission, each with 16 sonobuoys and 2 lightweight torpedoes.

- The aircraft uses the helicopter's keys. `H` requests the aircraft (it first heads for the ship's position) or sends it home.
- `W` sets the search area on the selected track's plotted position (without a selection on the ship); a click on the chart sets it on that point. A bearing-only track has no position to fly to.
- `X` plans a buoy pattern (field, barrier, circle) about the search area; the aircraft flies the points and drops a buoy at each; within 4 NM of the next point it slows to 200 kn so it can turn onto it. `Shift+X` cancels the pattern. `B` drops one buoy where the aircraft is, `Shift+B` switches its buoys between PASSIVE and ACTIVE.
- `Ctrl+R` switches the aircraft's surface-search radar (as the helicopter's). From 300 m it sees ships and surfaced or mast-raised submarines out to 60 NM (limited by the radar horizon); its contacts appear as `RADAR-MPA` tracks with the aircraft as observer. AI submarines with a raised mast hear it and go deep (see the helicopter chapter).
- Like the helicopter's, the aircraft's crew sees a raised mast's feather (see the helicopter chapter); while the datalink holds, these sightings appear as `MPA-EYE` tracks.
- `Shift+M` starts or ends **MAD passes** (browser: *Start MAD passes*/*End MAD passes*) while the aircraft is on its way or on station: once there it descends to 60 m and flies straight passes at 180 kn through the search area, turning back 2 NM past it (a cloverleaf). A submerged hull within about 400 m slant range is detected on a stateless draw each second (sure inside 250 m) and reaches the ship over the datalink as a MAD position fix without depth or course on that submarine's sonar contact. A buoy pattern flies first; `H` (home) ends the passes.
- `D` drops a torpedo on the designated sonar contact. The same checks as for the helicopter apply (current contact classified as a submarine, rules of engagement, a fresh fix under standard ROE), and the aircraft must be within 2 NM of the datum.

Everything the aircraft learns reaches the ship only by datalink, out to 250 NM. Its buoys report only while the aircraft is within 50 NM of them; once it leaves or lands they go silent for the ship. The sidebar shows its state, bearing and range, the time left on station, stores, sorties left and how many of its buoys are being relayed.

## Consort destroyer {#opz-consort}

Page 4 (Group) commands the consort of a group hunt: the destroyer LUETJENS (hull sonar, 8 ASROC, 2 in the Hunter group) that sails with the frigate in frigate scenario 11 (Search group) and submarine scenario 11 (Hunter group). Other missions have no consort and the page says so. The destroyer is an own unit on the datalink (out to 100 NM): its position, course, speed, orders and stores are shown as truth, drawn on the OPZ chart as a friendly symbol labelled with its call sign and `DL`; what its sonar hears reaches the frigate only as measurements.

- **Orders:** `Y` auto, `F` formation (each press moves it to the next station 5 NM off the frigate: starboard beam, ahead, port beam, astern), `H` hold (4 kn on its course), `X` search about a point (it closes at 18 kn and circles the point 4 NM out at 10 kn so its sonar hears), `W` prosecute the selected track's plotted position (26 kn, then a 2 NM circle with active sonar). A click on the chart sets the point and switches formation, hold or auto to search. Each order key in the panel's hints is clickable too; its ASROC stays on `Ctrl+Enter`.
- **Auto:** it keeps formation until the frigate's own picture holds a contact you classified as a submarine or designated with a position fix under 10 minutes old; then it prosecutes the freshest one with active sonar.
- **Sonar:** every 10 s its passive bearings appear on page 4 as lines from the destroyer. Its hull sonar hears a submarine within 8 NM, and nothing while it runs faster than 15 kn. Where one cuts the frigate's own passive bearing on the same contact at 15° or more and within 30 NM, the contact gets a `CONSORT` fix (uncertainty from both bearing errors and the cut). `Shift+A` switches its active sonar: every 20 s a ping fixes each submerged contact within 5 NM with position and depth (more likely the closer it is) as a `CONSORT` fix; every submarine within 25 NM hears the ping.
- **Weapons:** `Shift+W` switches weapons free or tight (tight at the start). Free, it fires one ASROC at most every 3 minutes on the auto contact's fix when that fix is under 2 minutes old and 1 to 12 NM from the destroyer. `Ctrl+Enter` orders one ASROC on the selected track's fix (under 2 minutes old); without a selection on the auto contact. Only one of its ASROC is in the air at a time. While nobody works the frigate's OPZ (the AI crews the frigate), the hunters may also send it a located datum for an ASROC.

If the destroyer is sunk the page and the event log say so; the mission goes on. The browser's OPZ has the same orders in the card *Consort destroyer*, and its chart shows the destroyer, its point and its bearing lines.

## Chart display {#opz-display}

Page 5 (Display) sets what the OPZ chart draws; it changes nothing in the simulation or the picture itself and is kept in the settings. `↑`/`↓` picks a row, `←`/`→` changes it (a click on a row moves it on), `Backspace` puts the selected row back to its default, `Shift+Backspace` every row.

- **Track trails:** off, 3, 6 or 12 minutes of earlier published positions behind each track (one point every 30 s, oldest faintest; they start anew after a load).
- **Vectors:** the motion vector shows the distance run in 3, 6, 12 or 30 minutes. Track names stand abeam of the course, clear of vectors and trails, and keep their place from frame to frame. `Alt+N` hides all contact names on every chart and overrides the label row below (see the Bridge chapter).
- **Labels:** full, short (six characters) or off.
- **Bearing scale:** ticks every 10° and numbers every 30° on the outer radar ring, with a mark for the own course. The numbers always stand at their bearing; when the chart is zoomed far out the rings carry their distance only every second ring, and a distance that would cover a bearing number is left out, as is a number under the position line.
- **Range rings**, **bearing lines** of bearing-only reports, **furthest-on** circles, **depths + grid** of the chart and the **radar afterglow** each switch on and off.
- **CPA of selected:** for the selected track with a position, course and speed, both run on to the closest point of approach; a line joins the two points with distance and time (red under 2 NM). It uses only the track's reported motion, so it is only as good as that report.

Two switches in the chart's top left turn the surface and air radar on and off on every page (the same as `R` and `Shift+R`, with the EMCON report to HQ); they glow while the radar transmits. The chips under the chart show which layers are on and switch them with a click on every page. The browser's OPZ has the radar switches and the same settings as buttons above its chart (kept for that browser tab only).

## Keys {#opz-keys}

<!-- keys:opz -->

## Mouse {#opz-mouse}

Every key in the key bar at the foot of the station can be clicked; holding the button holds the key. Lamps, page tabs and key hints in the text are clickable too (chapter Tools, Mouse). In addition:

- A click on a track card selects the track.
- The key chips on the target page assign the target (`M`), launch chaff (`G`) and step the missile track (`←`/`→`); the chips `J`, `H`, `Shift+L`, `Del` and `K` (follow) work by click too.
- **Fire buttons:** the ESSM button on the target page, the patrol aircraft's torpedo button on page 3 (shown once `D` has chosen the torpedo) and the consort's ASROC button on page 4 fire only on a second click: the first click arms the button (it reads "click again to fire"), a second click within 3 s fires like `Ctrl+Enter`; otherwise it disarms itself.
- Page 3: a click on the chart sets the patrol aircraft's search area; page 4: a click sets the consort's point and its order keys in the panel are clickable.
- Page 5: a click on a row moves it on; the layer chips under the chart and the two radar switches in its top left work on every page.
- On the chart the wheel zooms, dragging pans (it ends `K` follow) and a click pins a tooltip.

## Standard procedure {#opz-sop}

<!-- sop:opz -->

Air defence sequence (missile inbound):

```text
  40 NM  ASM detected (air radar / ESM seeker bearing)
  30 NM  ESSM envelope          -> Ctrl+Enter (2 fire channels)
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
- Automatic fusion only for a clear match of reports from different sensors with at least one position; bearing-only pairs and ambiguous matches wait for the operator. Signatures are compared only as the operator's classifications (no acoustic or emitter fingerprint matching), and AIS carries no ship type.
- No link-based air control of friendly aircraft.
- The consort destroyer cannot be crewed from a station of its own: it has no helicopter, towed array or torpedoes, takes orders only from the frigate's OPZ, and its bearings are not shared with the helicopter or the patrol aircraft. Own torpedoes never home on it (its datalink position is kept out of every search), while the submarines' torpedoes can sink it.
