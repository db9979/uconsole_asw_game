# 9 Electronic warfare {#station-eloka}

## Purpose {#eloka-purpose}

Electronic warfare (EloKa) listens passively for radar emitters (ESM) and, when ordered, jams them (ECM). ESM detects radars out to about 150 NM, far beyond own radar, without transmitting. It gives bearings and emitter parameters that point to a platform type - and warns when a missile seeker locks on.

## Displays and instruments {#eloka-displays}

Page 1 lists intercepts; page 2 shows the evidence for the selected intercept (frequency, PRF, modulation, candidates, correlation).

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
- Candidates are ranked only from observed frequency, PRF and modulation. A tie is not an identification.
- Correlation with radar or sonar tracks uses compatible time, bearing and observed position, never hidden identity.
- ESM runs from the operations compartment: a destroyed operations room disables it.

## Keys {#eloka-keys}

<!-- keys:eloka -->

## Standard procedure {#eloka-sop}

<!-- sop:eloka -->

## ECM techniques {#eloka-ecm}

| Technique | Effect |
|---|---|
| Noise | Masks the victim radar with broadband noise |
| RGPO | Range-gate pull-off: drags the seeker's range gate away |
| VGPO | Velocity-gate pull-off: drags the Doppler gate away |
| False targets | Injects false returns |

Automatic mode (`A`) picks targets and techniques and couples jamming with soft-kill (chaff) during a missile attack.

## Pro tips {#eloka-tips}

- Keep ESM running even under EMCON: it is completely passive.
- An intercept that changes from search to a high PRF pulse-doppler seeker at a steady bearing is a missile about to attack: warn Operations immediately.
- Assigning a radar type (`C`) releases the bearing to CIC; clearing the assignment withdraws it again.
- Jamming is a transmission. Use it deliberately, not continuously.
- Your own radar is heard too: a submarine at periscope depth (mast up, about 18 m) intercepts it on its ESM and can pass the bearing to other hostile units over its datalink. Deep boats neither hear radar nor receive the datalink.

## Not modelled {#eloka-limits}

- No communications intelligence (COMINT) or radio intercept; HF signals are handled by the radio room (HFDF).
- No decoy launchers other than chaff and no towed radar decoys.
