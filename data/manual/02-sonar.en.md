# 2 Sonar {#station-sonar}

## Purpose {#sonar-purpose}

The sonar room is the main ASW sensor. It listens passively on the hull-mounted sonar (HMS) and the towed array (TAS), analyses signatures on LOFAR and DEMON, estimates target motion with TMA, measures the sound profile and, when ordered, transmits an active ping. It classifies contacts and releases them to Operations and Weapons.

## Displays and instruments {#sonar-displays}

The station has six pages. `PgUp`/`PgDn` (or `2` again) cycles them.

| Page | Shows | Use it for |
|---|---|---|
| BROADBAND | Bearing-time waterfall | Detecting contacts and following their bearing |
| LOFAR | Frequency-time waterfall, 0-300 Hz | Tonal lines: machinery, shaft, blade signatures |
| DEMON | Modulation spectrum of the listening beam | Blade rate and shaft-rate hypotheses |
| TMA | Solution for the focused contact | Range, course and speed estimates |
| UMWELT / FUSION | Sound profile, layer, CZ, array comparison | Choosing TAS depth, spotting ghost contacts |
| ACTIVE | Stored echoes with age and error | Range and depth from pings |

### BROADBAND waterfall {#sonar-broadband}

```text
 bearing  000      090      180      270      359
 now    |   .   #     .        :          .    |
        |   .   #    .         :         .     |
        |   .    #   .          :        .     |
 older  |   .    #  .           :       .      |
        +--------------------------------------+
            ^    ^              ^
            |    moving contact own baffle noise (soft lobe astern)
            steady weak contact
```

Newest data is at the top. A straight vertical trace is a contact on a steady bearing; a slanting trace shows bearing rate. The history covers 20 s of fine data plus 4 minutes of long history (`Shift+H` selects 25/50/100 %). Brightness is relative received level, not range.

### LOFAR {#sonar-lofar}

The x axis is frequency (0-300 Hz), time runs downwards. Bins are 1 Hz below 40 Hz, 2 Hz up to 100 Hz and 5 Hz above. A new line is added every 0.25 s; 80 lines are kept.

- Steady vertical lines are **tonals** (narrowband): generators, pumps, shaft lines. Several lines at integer multiples of one frequency are a harmonic family; `K` cycles the detected harmonic hypothesis.
- Own ship produces a shaft line at about 10 + 1.9 x own speed Hz. `N` notches it out.
- `Space` holds peaks so faint tonals stand out.
- `F` selects the analysed band: FULL 0-300, LOW 4-80, SHAFT 8-55, MID 20-120 Hz.

### DEMON {#sonar-demon}

DEMON demodulates the broadband noise envelope of the listening beam. Propeller cavitation is modulated at the **blade rate** = shaft rate x number of blades.

```text
 level
   |      |              blade rate 12.5 Hz
   |  |   |              -> 5 blades => shaft 2.5 Hz = 150 RPM
   |  |   |   |
   +--+---+---+------ Hz
     2.5 12.5 25
    shaft blade 2nd harmonic
```

The display shows measured modulation, not certain identity. The analysis windows are up to 2 s long: after changing the bearing listen for at least one second before judging. Ranked candidates from the acoustic catalogue appear as hints; the classification is still yours.

### TMA, environment and active {#sonar-tma-env}

- **TMA** solves range, course and speed from a bearing series of the focused contact. It needs at least 4 bearings over 180 s and an own course change of at least 6 degrees; range is trusted from quality 0.35. It does not estimate depth.
- **UMWELT / FUSION** shows the bathythermograph (`E`, 60 s cooldown): measured layer depth, sound-speed profile and convergence-zone bands, plus the HMS/TAS comparison. Bearings within 5 degrees confirm each other; 9 degrees or more apart are flagged as a possible ghost contact.
- **ACTIVE** lists echoes of the last 120 s: bearing, range (+/-0.18 NM) and depth (+/-12 m). A ping fix ages out after 120 s.

## Hull sonar versus towed array {#sonar-arrays}

| | HMS (hull) | TAS (towed) |
|---|---|---|
| Passive range | 1.0 x base | 1.4 x base, minus 3 % per knot |
| Beam width | 12 degrees | 6 degrees |
| Bearing error | +/-6 degrees | +/-2 degrees |
| Self-noise | full | 35 % of hull |
| Ping range | 1.0 x | 0.8 x |
| Handling | always ready | stream 360 s, recover 480 s, only at 3-12 kn, 30 s settle |

- TAS depth 20-260 m (`U`/`V` in 10 m steps), limited to 260 m minus 4 m per knot of own speed. At 30 m or deeper and in the same layer as the target it gains another 25 %.
- Above 20 kn with any cable out the array suffers a permanent FAULT.
- The array heading lags the ship by about 45 s after a turn; its bearings are less reliable while it swings.

```text
          HMS                          TAS
     noise lobe astern          noise lobe along cable
            ^                           ^
      \  ship  /                   ship ====== cable === array
       \  ||  /                             (lobe points to ship)
      ~~~~||~~~~  70 deg soft lobe
```

## Keys {#sonar-keys}

<!-- keys:sonar -->

## Standard procedure {#sonar-sop}

<!-- sop:sonar -->

Combat situation:

1. A new high-pitched, fast-moving contact with rapidly changing bearing may be a torpedo. Report the bearing to the Bridge immediately.
2. Keep focus on the hostile submarine so the torpedo wire datum stays fresh.
3. Ping only when you need depth for the shot or the contact is about to be lost: the submarine hears a ping out to 60 NM and starts evading.

## Pro tips {#sonar-tips}

- Gain (`I`/`O`) changes display and audio only, not detection. Black level (`Ctrl+I`/`Ctrl+O`) and contrast (`Shift+I`/`Shift+O`) help faint traces stand out; `Shift+C` changes the phosphor colour.
- `D` or `A`/`B`/`H` choose broadband, filtered or heterodyne audition. Heterodyne shifts the low band up to about 700 Hz so low tonals become audible.
- Put the TAS below the measured layer to hear deep targets; keep the HMS for shallow ones. Both arrays run in parallel.
- The TMA page shows the closing rate derived from the solution: positive means the target is closing.
- If the TAS and HMS disagree by 9 degrees or more, treat the contact as a possible ghost (the display flags it) and turn to resolve it.
- A contact is lost 120 s after its last detection. Keep tracking weak contacts, or reacquire with a ping.

## Not modelled {#sonar-limits}

- No manual TMA (dot stack, manual solution entry); only the automatic solver, switched with `T`.
- No selectable split-window normalisation (TPSW); use gain, black level and contrast instead.
- No hard blind baffle sector; own noise is a soft lobe.
- No acoustic Doppler shift of tonal lines; closing rate comes from the TMA solution only.
- No variable-depth sonar separate from the TAS.
