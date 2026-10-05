# 6 Radio {#station-radio}

## Purpose {#radio-purpose}

The radio room handles communications with HQ and HF direction finding (HFDF). HQ sends orders, weather bulletins and ROE changes by teletype. HFDF takes bearings on submarines that transmit on HF or run a snorkel mast, out to 120 NM, far beyond sonar range.

## Pages {#radio-pages}

| Page | Shows |
|---|---|
| 1 HF direction finding | HFDF signal cards, cross-fix chart, DF rose with bearing log and fixes |
| 2 Messages | Teletype with HQ traffic |
| 3 Tasks | HQ tasks and the own calls to HQ |

## Displays and instruments {#radio-displays}

Page 1 has three columns: the current HFDF signals as cards on the left (a click selects one as `↑`/`↓` would), the cross-fix chart in the middle and the DF rose with the bearing log and the fixes on the right; page 2 is the teletype with HQ traffic; page 3 lists HQ tasks.

![Radio room on the uConsole](figure:station-radio)

![Radio room in the Remote Crew browser](figure:web-radio-desktop)

```text
 HFDF SIGNALS               BEARING LOG
 > HF-03  247.0  age 12 s    HF-03 247.0 from pos A  t=12:04
   HF-05  061.5  age 40 s    HF-03 239.5 from pos B  t=12:08
                             -> CROSS-FIX + error ellipse on chart

   pos A *----------__
                       --___  X  <- fix
   pos B *------------------/
```

- Bearing error is +/-8 degrees for a ground wave and +/-16 degrees for a sky wave; signals older than 30 s can no longer be logged.
- Each signal shows its frequency and propagation. A submarine calling a distant shore station picks a high frequency by day (ground wave heard to about 95 NM) and a lower one at night (about 150 NM). Beyond the skip distance, several hundred NM away, the sky wave arrives instead. An AI submarine at periscope depth that has held the ship within the last 4 minutes reports it to its headquarters once every 30 minutes, at an unpredictable moment, with a 20 s call that HF/DF hears like any other.
- Logged lines and cross-fixes appear on the charts of Bridge, Weapons and Helicopter.
- In the Remote Crew browser the radio room has no chart: an HF/DF bearing scope (one strobe per signal, fan width is the bearing error, logged bearings dashed), receiver channels with frequency, propagation, signal meter and a log button, and the teletype. Selecting a channel opens the contact detail for annotation; logged bearings and cross-fixes are listed in the station panel.
- A second bearing of the same signal gives a cross-fix if it is taken at least 1 NM away from the first and within 300 s.
- The teletype also carries the weather bulletin every 30 minutes and HQ messages (threat warnings, ROE FREE).
- At mission start HQ reports the threat. With **coarse** intelligence it gives only a rough bearing and range of one threat. With **exact** intelligence it also names every hostile unit type committed to the mission with its number (for example "1x Altmetall (Diesel, älter), 2x air raid wave with anti-ship missiles"), using the names in the unit analyser (`F8`); positions stay unconfirmed. Patrol always gets exact intelligence, Double hunt and Nuclear intercept coarse, and the free hunt lets you choose on its difficulty screen (last row, "HQ intelligence").

Page 1 also shows an HF/DF bearing rose: each current signal is a strobe, fanned as wide as its bearing error.

The **cross-fix chart** beside it is the radio room's plotting sheet, north up, with grid and coastline: every logged bearing of the last 5 minutes is a line drawn from where the ship took it (the origin as a small circle), the current intercepts are thin lines from the ship with their error fan (the selected one amber), two logged bearings of the same signal that cross mark their crossing with a diamond, and each cross-fix shows its error ellipse with its label and 1-sigma error. Older lines fade. The chart frames the ship, every origin and fix and shows its half width (at least ±20 NM); below it are the newest logged bearings and fixes. It draws only what the radio room measured and computed, never the emitter itself.

## HQ tasks {#radio-tasks}

Besides the hunt, HQ radios tasks to the ship: the first about 15 to 25 minutes into a built-in mission, then one every 25 to 45 minutes, at most six per mission and two open at a time (on a free patrol every 10 to 20 minutes without a cap, with the sector patrol as a sixth kind; see the reference chapter). Custom missions get none. Each offer arrives on the teletype and on page 3 (Tasks). Answer it within 5 minutes with `A` or `Enter` (accept) or `D` (decline); no answer counts as declined. A destroyed radio room cannot answer. On a real sea area HQ, incident reports, the task page, logged bearings and the submarine's ESM fix give positions in degrees and minutes (`54°21.4'N 010°08.2'E`), always with bearing and range from the ship where HQ gives them; on the stylized fixed chart they stay in NM.

- **Distress call (SAR):** a life raft with 2 to 6 people, reported by EPIRB with about 0.5 NM error and drifting with current and wind. The survivors last according to the sea temperature, from 40 minutes in water below 8 °C to 100 minutes above 20 °C. The raft is sighted within 2 NM by day (3 NM at night by its strobe), and it is a small radar echo for the ship's and the helicopter's radar (a few miles in a calm sea, far less in a rough one); then the circle on the chart shrinks onto it. Take them aboard by lying within 0.25 NM at 3 kn or less for 4 minutes, or with the helicopter's rescue hoist (`Z` within 0.1 NM: one minute per person, 6 in the cabin, only when the weather allows dipping); the helicopter's survivors count once it is back on deck (chapter Helicopter deck). +600 points, -400 if they are lost.
- **Identify merchant:** HQ names a merchant within 60 NM and gives its position with about 2 NM error. It counts as identified once the lookout has published its identification or the helicopter passes within 1 NM with at least 1 NM visibility. About a third are flagged as suspect: HQ then passes a submarine datum near the ship. 40 minutes.
- **Submarine datum:** a circle of 5 NM radius from a maritime patrol report; not every datum has a submarine behind it. Search 10 minutes inside the circle with the ship or the helicopter. 50 minutes. Not offered in the submarine missions 8 and 9: HQ has no intelligence on that submarine.
- **Replenishment at sea:** offered when fuel is below 70 % or torpedoes, ASROC or depth charges have been used; `R` on the Tasks page (or the browser's *Request supply ship*) asks for one yourself when at least 5 % fuel or any store is missing, at most once every 20 minutes after the last one ended. A friendly supply ship appears 18 to 28 NM away at 12 kn; its course and a dead-reckoning line are plotted. Keep within 0.3 NM and within 3 kn of its speed: fuel flows the whole time (a full load in 15 minutes), and torpedoes, ASROC, depth charges, Nixie decoys and CIWS and gun rounds come over in five loads, one every 3 minutes, each a share of what is still missing. Breaking away keeps what came over. The Tasks page shows what is aboard. VLS cells are not reloaded at sea. Worth +100, no penalty.
- **Radar silence (EMCON):** both radars off within 90 s and silent for 20 to 30 minutes. +200, -250 if a radar radiates.

Accepted positions are plotted on every chart (also in the Remote Crew browser). Scores are listed at mission end. The radio operator in the browser answers with the same buttons.

## Incidents at sea {#radio-incidents}

The sea brings surprises of its own: the first 20 to 40 minutes into a built-in mission, then one every 30 to 50 minutes, at most six per mission (on a free patrol every 20 to 40 minutes without a cap; none in custom missions and lessons). Each is reported on the teletype.

- **Drift net:** a fishing boat reports a net 2 NM long across the ship's track, 3 to 7 NM ahead, hanging from the surface down to 20 m; the radio operator plots it on every chart as a ruler `NET n`, and it is hauled in after an hour. Running over it tears it: the fishermen claim damages (-100 points), and a streamed towed array or variable-depth sonar fouls in it and is hauled in at once. A submarine that crosses it shallower than 20 m fouls it too and is loud for 20 s while it tears free; deeper it passes under.
- **Weather front:** HQ warns 10 minutes ahead; then rain, a storm or fog holds for 30 to 60 minutes (visibility, wind and rain noise for every sensor, on both sides), and HQ reports when it has passed.
- **Merchant without AIS:** a freighter running without AIS appears 8 to 15 NM away; HQ reports it with about 2 NM error and offers it as an identify task when fewer than two tasks are open.
- **Whales:** a fishing boat reports a pod of two to four whales 3 to 6 NM ahead; they are real biological contacts for every sonar. Merchants without AIS and whales from incidents stay at sea; once 56 ships or 40 animals are about, no more of them come.
- **Man overboard:** a sailor goes over the side next to the ship; the general alarm sounds and the chart carries the mark `OVERBOARD n`, which drifts with the surface current. The Bridge turns back with a Williamson turn and recovers him when the ship passes within 0.1 NM at 5 kn or less; the helicopter recovers him when it hovers right over him (waypoint on the mark, or dipping sonar lowered). A rescue is worth +100 points; after 20 minutes in the water he is lost (-300 points). When the AI runs the Bridge it steers onto the mark itself and comes back up to 12 kn afterwards.
- **Steering failure:** the steering gear fails: the rudder is jammed for 60 s, then the engine room steers from the emergency position at half rudder rate until the steering gear is repaired after 10 minutes.
- **Snorkel valve and battery gas (submarine):** on a diesel-electric submarine the snorkel head valve jams for 15 minutes (no charging; the AI submarine goes deep and stays down), or battery gas has to be vented (half charging rate). The crewed submarine's crew reports both; the frigate learns nothing of them.

HQ passes the net, the front and the whales (not the emergencies aboard) on to the submarine's broadcast; a crewed submarine hears of them when it copies the next broadcast, and its crew plots the net on its own chart.

## Own calls to HQ {#radio-reports}

On the Tasks page the radio room can call HQ itself, at most once every 10 minutes; the line at the foot of the task list says whether a call is on the air, how long until the next one, or that both are ready.

- `K` **Contact report:** sends the position of the freshest located contact (ping, TMA, buoy or fused fix, else an HF/DF cross-fix up to 15 minutes old). HQ acknowledges it on the teletype and vectors the patrol aircraft to it when the aircraft is airborne. HQ never says whether a submarine was really there: each report that put a hostile submarine within 3 NM of the fix earns 150 points at the mission's end (at most three; later calls never push them out). A report broken off because the radio room fails during the 20 s never reaches HQ and earns nothing.
- `H` **Request support:** HQ sends the on-call patrol aircraft toward the ship when it is available (even with the OPZ down), otherwise it says that no support is available.
- Each call is 20 s of HF transmission. While it is on the air, a submarine with its antenna up (the crewed submarine's raised mast, an AI submarine at periscope depth) takes an HF/DF bearing on the frigate (+/-8 degrees for a ground wave, +/-16 degrees for a sky wave): the crewed submarine gets a report and a bearing line on its chart, an AI submarine keeps the direction like a sonar bearing of its own (up to 4 minutes) and acts on it. Talking to HQ costs silence.

## Keys {#radio-keys}

<!-- keys:radio -->

## Mouse {#radio-mouse}

Every key in the key bar at the foot of the station can be clicked; holding the button holds the key. Lamps, page tabs and key hints in the text are clickable too (chapter Tools, Mouse). In addition:

- A click on a signal card selects that signal as `↑`/`↓` would.
- On the Tasks page a click on a task row selects the task; the key hints `K` (contact report), `H` (support) and those of a replenishment task press their keys.

## Standard procedure {#radio-sop}

<!-- sop:radio -->

## Pro tips {#radio-tips}

- Take the two bearings from positions across the expected bearing line: the more they cross at right angles, the smaller the error ellipse.
- A submarine that transmits or snorkels is usually shallow and slow: a good moment to close in with the helicopter.
- Combine an HFDF bearing with a sonar bearing for a quick position estimate.

## Not modelled {#radio-limits}

- No free-text radio transmissions: the only own calls to HQ are the contact report and the support request, besides answering tasks; no communication plan or crypto.
- No frequency tuning: HFDF monitors the whole HF band and lists the detected signals with their frequency.
