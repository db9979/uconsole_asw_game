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

- Steady vertical lines are **tonals** (narrowband): generators, pumps, shaft lines. Several lines at integer multiples of one frequency are a harmonic family: put the white cursor on a line with `Z`/`X` (`Shift`: 10 Hz steps) and press `K` to mark it as fundamental; amber guides then show 2f, 3f and so on. `K` on the same frequency clears it.
- Own ship produces a shaft line at about 10 + 1.9 x own speed Hz. `N` notches it out.
- `Space` holds peaks so faint tonals stand out.
- The spectrum strip above the waterfall prints the frequency over every prominent line (interpolated between bins; with `Space` the held envelope). Where values would overlap, the stronger line keeps its label. The Remote Crew browser labels its spectra the same way.
- `F` selects the analysed band: FULL 0-300, LOW 4-80, SHAFT 8-55, MID 20-120 Hz. `Ctrl+Z` / `Ctrl+X` set the low / high band edge at the cursor for any band-, low- or high-pass; `Shift+N` puts an extra notch on the cursor frequency.
- `Q` selects the integration time: 2 s (the receiver's own FFT), 8, 16 or 64 s. Longer integration averages successive spectra so a weak steady tonal rises out of the noise, but a moving line smears. `Shift+Q` opens the vernier: 20 Hz around the cursor at the native 0.5 Hz resolution.
- The detail rail reads the level at the cursor. The strip labels lines automatically only with operator assistance set to training (`F10`).

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

The display shows measured modulation, not identity. After changing the bearing listen for at least a few seconds before judging. Count blades yourself: move the cursor (`Z`/`X`, 0.5 Hz) onto the shaft line and press `K`, then onto the blade line and press `K` again; the rail shows blades = blade rate / shaft rate (with the deviation from a whole number) and the shaft RPM. A third `K` clears both marks. Compare the result with the references in the contact analyser (`F8`). With operator assistance set to training (`F10`) the sonar also labels modulation lines, proposes RPM for 3-7 blades and ranks catalogue candidates.

### TMA, environment and active {#sonar-tma-env}

- **TMA** solves range, course and speed from a bearing series of the focused contact. It needs at least 4 bearings over 180 s and an own course change of at least 6 degrees; range is trusted from quality 0.35. It does not estimate depth. A grid search finds the basin and a Levenberg-Marquardt fit refines it; the detail line shows the 1-sigma uncertainty ellipse. The strongest tonal is measured with its Doppler shift ("Tonal (Doppler)"): a target crossing close by sweeps its frequency, which fixes range even without an own turn. Sonobuoy bearings enter the same estimate with the buoy as observer, so a buoy field gives range quickly.
- **UMWELT / FUSION** shows the bathythermograph (`E`, 60 s cooldown): measured layer depth, sound-speed profile and convergence-zone bands, plus the HMS/TAS comparison. Bearings within 5 degrees confirm each other; 9 degrees or more apart are flagged as a possible ghost contact. The layer is not fixed: afternoon sun makes it shallower (about 8 m), strong wind mixes it deeper over hours, and internal waves move it a few metres. Repeat the BT after a few hours or a weather change. The measured profile is the real temperature-driven sound speed (Mackenzie equation), so it drops below the layer.
- **ACTIVE** lists echoes of the last 120 s: bearing, range and depth (+/-12 m). A ping fix ages out after 120 s. `W` selects the pulse: **CW** (1 s tone) gives coarse range (about 0.1-0.3 NM) but its Doppler separates a moving target from seabed reverberation; **LFM** (100 Hz sweep) measures range to a few metres and gains 20 dB against noise, but a slow or stationary target stays inside the reverberation. The echo strength depends on the target's aspect (broadside about 15 dB stronger than bow-on) and size. Rocky ground reverberates far more than mud; charted wrecks return real echoes that no contact owns ("unassociated echo").

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

1. A launch transient, high-frequency sonar pulses, or a new loud broadband contact without tonals and with fast bearing drift may be a torpedo. Classify it as Torpedo (`C`) and report the bearing to the Bridge immediately.
2. Keep focus on the hostile submarine so the torpedo wire datum stays fresh.
3. Ping only when you need depth for the shot or the contact is about to be lost: the submarine hears a ping out to 60 NM and starts evading.

## Pro tips {#sonar-tips}

- Gain (`I`/`O`) changes display and audio only, not detection. Black level (`Ctrl+I`/`Ctrl+O`) and contrast (`Shift+I`/`Shift+O`) help faint traces stand out; `Shift+C` changes the phosphor colour.
- `D` or `A`/`B`/`H` choose broadband, filtered or heterodyne audition. Heterodyne shifts the low band up to about 700 Hz so low tonals become audible.
- The listening audio runs about one second behind the display so a busy moment never interrupts it. After steering the listening bearing the old beam fades into the new one after about a second; the stream is not cut.
- Put the TAS below the measured layer to hear deep targets; keep the HMS for shallow ones. Both arrays run in parallel.
- The TMA page shows the closing rate derived from the solution: positive means the target is closing.
- If the TAS and HMS disagree by 9 degrees or more, treat the contact as a possible ghost (the display flags it) and turn to resolve it.
- The towed array is a line: it cannot tell a bearing from its mirror about the cable. A contact heard only on the TAS is marked "TAS left/right ambiguous" with its mirror bearing and does not feed TMA; the shown side is right only half the time. Turn 20 degrees (or get the contact on the HMS) and the wrong side drops out. Bearings toward the cable ends (endfire) are also less accurate than broadside.
- A contact is lost 120 s after its last detection. Keep tracking weak contacts, or reacquire with a ping.
- Wrecks return real echoes without Doppler. A submarine lying still beside a charted wreck hides in that echo from a CW ping (750 m range cell); an LFM ping resolves about 8 m and can separate the boat from the wreck. Suspect every wreck the enemy could have reached.
- The bathythermograph (`E`) measures to the seabed, at most 1500 m. Only after a measurement does the weather & sonar analysis (`0`) show the layer, the shadow zone below it and a SOFAR channel.
- The sonar never names a torpedo or a submarine. It reports what it hears: a mechanical launch transient (heard out to 35 NM) or high-frequency seeker pulses (about 6 NM) as a bearing, held on the Bridge alarm for 60 s, and breaking-up noises when a hull sinks. The OPZ symbol of a sonar contact follows your classification only; an unclassified contact stays unknown.

## Not modelled {#sonar-limits}

- No manual TMA (dot stack, manual solution entry); only the automatic solver, switched with `T`.
- No selectable split-window normalisation (TPSW); use gain, black level and contrast instead.
- No hard blind baffle sector; own noise is a soft lobe.
- No variable-depth sonar separate from the TAS.
