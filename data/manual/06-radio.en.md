# 6 Radio {#station-radio}

## Purpose {#radio-purpose}

The radio room handles communications with HQ and HF direction finding (HFDF). HQ sends orders, weather bulletins and ROE changes by teletype. HFDF takes bearings on submarines that transmit on HF or run a snorkel mast, out to 120 NM, far beyond sonar range.

## Displays and instruments {#radio-displays}

Page 1 lists current HFDF signals and the bearing log; page 2 is the teletype with HQ traffic; page 3 lists HQ tasks.

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
- Each signal shows its frequency and propagation. A submarine calling a distant shore station picks a high frequency by day (ground wave heard to about 95 NM) and a lower one at night (about 150 NM). Beyond the skip distance, several hundred NM away, the sky wave arrives instead.
- Logged lines and cross-fixes appear on the charts of Bridge, Weapons and Helicopter.
- In the Remote Crew browser the radio room has no chart: an HF/DF bearing scope (one strobe per signal, fan width is the bearing error, logged bearings dashed), receiver channels with frequency, propagation, signal meter and a log button, and the teletype. Selecting a channel opens the contact detail for annotation; logged bearings and cross-fixes are listed in the station panel.
- A second bearing of the same signal gives a cross-fix if it is taken at least 1 NM away from the first and within 300 s.
- The teletype also carries the weather bulletin every 30 minutes and HQ messages (threat warnings, ROE FREE).
- At mission start HQ reports the threat. With **coarse** intelligence it gives only a rough bearing and range of one threat. With **exact** intelligence it also names every hostile unit type committed to the mission with its number (for example "1x Altmetall (Diesel, älter), 2x air raid wave with anti-ship missiles"), using the names in the unit analyser (`F8`); positions stay unconfirmed. Patrol always gets exact intelligence, Double hunt and Nuclear intercept coarse, and the free hunt lets you choose on its difficulty screen (last row, "HQ intelligence").

## HQ tasks {#radio-tasks}

Besides the hunt, HQ radios tasks to the ship: the first about 15 to 25 minutes into a built-in mission, then one every 25 to 45 minutes, at most six per mission and two open at a time. Custom missions get none. Each offer arrives on the teletype and on page 3 (Tasks). Answer it within 5 minutes with `A` (accept) or `D` (decline); no answer counts as declined. A destroyed radio room cannot answer.

- **Distress call (SAR):** a life raft with 2 to 6 people, reported by EPIRB with about 0.5 NM error and drifting with current and wind. The survivors last according to the sea temperature, from 40 minutes in water below 8 °C to 100 minutes above 20 °C. The raft is sighted within 2 NM by day (3 NM at night by its strobe); then the circle on the chart shrinks onto it. Take them aboard by lying within 0.25 NM at 3 kn or less for 4 minutes, or let the helicopter hover overhead (one minute per person, only when the weather allows dipping). +600 points, -400 if they are lost.
- **Identify merchant:** HQ names a merchant within 60 NM and gives its position with about 2 NM error. It counts as identified once the lookout has published its identification or the helicopter passes within 1 NM with at least 1 NM visibility. About a third are flagged as suspect: HQ then passes a submarine datum near the ship. 40 minutes.
- **Submarine datum:** a circle of 5 NM radius from a maritime patrol report; not every datum has a submarine behind it. Search 10 minutes inside the circle with the ship or the helicopter. 50 minutes.
- **Replenishment at sea:** offered when fuel is below 70 % or torpedoes, ASROC or depth charges have been used; `R` on the Tasks page (or the browser's *Request supply ship*) asks for one yourself when at least 5 % fuel or any store is missing, at most once every 20 minutes after the last one ended. A friendly supply ship appears 18 to 28 NM away at 12 kn; its course and a dead-reckoning line are plotted. Keep within 0.3 NM and within 3 kn of its speed: fuel flows the whole time (a full load in 15 minutes), and torpedoes, ASROC, depth charges, Nixie decoys and CIWS and gun rounds come over in five loads, one every 3 minutes, each a share of what is still missing. Breaking away keeps what came over. The Tasks page shows what is aboard. VLS cells are not reloaded at sea. Worth +100, no penalty.
- **Radar silence (EMCON):** both radars off within 90 s and silent for 20 to 30 minutes. +200, -250 if a radar radiates.

Accepted positions are plotted on every chart (also in the Remote Crew browser). Scores are listed at mission end. The radio operator in the browser answers with the same buttons.

## Keys {#radio-keys}

<!-- keys:radio -->

## Standard procedure {#radio-sop}

<!-- sop:radio -->

## Pro tips {#radio-tips}

- Take the two bearings from positions across the expected bearing line: the more they cross at right angles, the smaller the error ellipse.
- A submarine that transmits or snorkels is usually shallow and slow: a good moment to close in with the helicopter.
- Combine an HFDF bearing with a sonar bearing for a quick position estimate.

## Not modelled {#radio-limits}

- No free-text radio transmissions or reports to HQ beyond answering tasks; no communication plan or crypto.
- No frequency tuning: HFDF monitors the whole HF band and lists the detected signals with their frequency.
