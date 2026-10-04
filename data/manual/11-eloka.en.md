# 9 Electronic warfare {#station-eloka}

## Purpose {#eloka-purpose}

Electronic warfare (EloKa) listens passively for radar emitters (ESM) and, when ordered, jams them (ECM). ESM detects radars out to about 150 NM, far beyond own radar, without transmitting. It gives bearings and emitter parameters that point to a platform type - and warns when a missile seeker locks on.

## Pages {#eloka-pages}

| Page | Shows |
|---|---|
| 1 Intercepts | Intercept cards, threat rose with list switches, the selected intercept, ESM, jammer, automatic ECM and tone lamps |
| 2 Evidence | Full evidence of the selected intercept: frequency, PRF, modulation, candidates, correlation |

## Displays and instruments {#eloka-displays}

Both pages show the intercepts as cards on the left (key with group size, classification or modulation, bearing, frequency and band, quality and age; the stripe is the threat colour; a click selects one as `↑`/`↓` would). Page 1 has the threat rose with the four list switches in the middle and the selected intercept on the right (signal fingerprint, bearing, radar type, threat, ECM, assignment, best library candidates) above the ESM, jammer, automatic ECM and tone lamps; page 2 shows the full evidence for the selected intercept (frequency, PRF, modulation, candidates, correlation).

![Electronic warfare on the uConsole](figure:station-eloka)

![Electronic warfare in the Remote Crew browser](figure:web-eloka-desktop)

```text
 INTERCEPTS                       status  threat  band
 > E-07  brg 312  9.3 GHz  PRF 2.4k  NEW     HIGH    X
   E-04  brg 045  3.0 GHz  PRF 1.0k  TRACK   LOW     S

 EVIDENCE E-07
   frequency 9.3 GHz   PRF 2400 Hz   modulation pulse-doppler
   candidates (ranked, not identified):
     1. missile seeker     2. fire-control radar
   correlation: compatible with CIC track T-12 (time/bearing)
```

- Bearing accuracy is about +/-3 degrees. Intercepts are bearings, not positions.
- A rotating search radar reaches the ESM antenna with its main beam once per revolution; its side lobes are heard only close in. The evidence page shows the peak signal level, a range estimate that assumes the power class of the best candidate (a wrong candidate gives a wrong range) and the measured antenna scan period.
- By default (realism level Standard or Realistic, `F10`) the evidence page shows only the measured parameters and a library lookup: every emitter whose published frequency (and PRF) range contains the measurement, in name order, without score. Radar type, threat and range estimate are then yours to judge; `C` cycles the library in name order. At the Beginner level, candidates are ranked by frequency, PRF and modulation with a score, and radar type, threat and range estimate are filled in. A tie is not an identification.
- Correlation with radar or sonar tracks uses compatible time, bearing and observed position, never hidden identity.
- The emitter library includes the anti-ship missile seeker (9.0-9.5 GHz, PRF 1.8-3.2 kHz, pulse-Doppler). It radiates only in the last 18 NM and only once the sea-skimmer is above the radar horizon, and it matches an attack aircraft's fire-control radar just as well: the bearing trend and the air picture decide.
- ESM runs from the operations compartment: a destroyed operations room disables it.

Beside the intercept list a bearing rose shows every listed emitter as a strobe in its threat colour (older ones shorter and fainter), and lamps show ESM, jammer, automatic ECM and audio.

### Sorting the list {#eloka-list}

Many merchants and aircraft transmit with navigation radars, so four switches above the rose order the list (clickable; the browser has the same bar):

| Switch | Key | Values |
|---|---|---|
| Status | `F` | operational (live, recent, classified or high threat), open (operational but not yet classified), live, memory, all |
| Threat | `Shift+F` | all, low and above up to critical (assessed on the Beginner level only) |
| Band | `Ctrl+F` | all, A/C, D, E/F, G/H, I/J, K |
| Group | `Z` | on: intercepts of one kind (same band and modulation, frequency and PRF within the association gates, bearing within 6 degrees) appear as one entry "E27 ×3"; off: every intercept on its own |

A group is a display aid, not an identification: it can merge several ships in one direction. `←`/`→` steps through its intercepts, the Group row on the right shows where you are ("2 of 4"). Classified and jammed intercepts always stand alone. Each card names the key (running number), the classification or else the modulation, then frequency, band, quality and age. Workflow: with status open, classify the not yet classified emitters one by one with `C`; classified ones leave that view.

## ECM techniques {#eloka-ecm}

| Technique | Effect |
|---|---|
| Noise | Masks the victim radar with broadband noise |
| RGPO | Range-gate pull-off: drags the seeker's range gate away |
| VGPO | Velocity-gate pull-off: drags the Doppler gate away |
| False targets | Injects false returns |

Automatic mode (`A`) picks targets and techniques and couples jamming with soft-kill (chaff) during a missile attack.

## Keys {#eloka-keys}

<!-- keys:eloka -->

## Mouse {#eloka-mouse}

Every key in the key bar at the foot of the station can be clicked; holding the button holds the key. Lamps, page tabs and key hints in the text are clickable too (chapter Tools, Mouse). In addition:

- A click on an intercept card selects it as `↑`/`↓` would.
- The four switches above the rose act like `F`, `Shift+F`, `Ctrl+F` and `Z`.

## Standard procedure {#eloka-sop}

<!-- sop:eloka -->

## Pro tips {#eloka-tips}

- Keep ESM running even under EMCON: it is completely passive.
- An intercept that changes from search to a high PRF pulse-doppler seeker at a steady bearing is a missile about to attack: warn Operations immediately.
- Assigning a radar type (`C`) releases the bearing to CIC; clearing the assignment withdraws it again.
- Jamming is a transmission. Use it deliberately, not continuously.
- Your own radar is heard too: a submarine at periscope depth (mast up, about 18 m) intercepts it on its ESM and can pass the bearing to other hostile units over its datalink. Deep submarines neither hear radar nor receive the datalink.

## Not modelled {#eloka-limits}

- No communications intelligence (COMINT) or radio intercept; HF signals are handled by the radio room (HFDF).
- No decoy launchers other than chaff and no towed radar decoys.
