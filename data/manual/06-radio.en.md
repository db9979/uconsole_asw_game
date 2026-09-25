# 6 Radio {#station-radio}

## Purpose {#radio-purpose}

The radio room handles communications with HQ and HF direction finding (HFDF). HQ sends orders, weather bulletins and ROE changes by teletype. HFDF takes bearings on submarines that transmit on HF or run a snorkel mast, out to 120 NM, far beyond sonar range.

## Displays and instruments {#radio-displays}

Page 1 lists current HFDF signals and the bearing log; page 2 is the teletype with HQ traffic.

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
- A second bearing of the same signal gives a cross-fix if it is taken at least 1 NM away from the first and within 300 s.
- The teletype also carries the weather bulletin every 30 minutes and HQ messages (threat warnings, ROE FREE).
- At mission start HQ reports the threat. With **coarse** intelligence it gives only a rough bearing and range of one threat. With **exact** intelligence it also names every hostile unit type committed to the mission with its number (for example "1x Altmetall (Diesel, älter), 2x air raid wave with anti-ship missiles"), using the names in the unit analyser (`F8`); positions stay unconfirmed. Patrol always gets exact intelligence, Double hunt and Nuclear intercept coarse, and the free hunt lets you choose on its difficulty screen (last row, "HQ intelligence").

## Keys {#radio-keys}

<!-- keys:radio -->

## Standard procedure {#radio-sop}

<!-- sop:radio -->

## Pro tips {#radio-tips}

- Take the two bearings from positions across the expected bearing line: the more they cross at right angles, the smaller the error ellipse.
- A submarine that transmits or snorkels is usually shallow and slow: a good moment to close in with the helicopter.
- Combine an HFDF bearing with a sonar bearing for a quick position estimate.

## Not modelled {#radio-limits}

- No own radio transmissions or reports to HQ; no communication plan or crypto.
- No frequency tuning: HFDF monitors the whole HF band and lists the detected signals with their frequency.
