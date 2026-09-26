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

- **TMA** is yours. The page plots the bearings of the selected contact over time. Build a hypothesis: `Z`/`X` course (`Shift`: 1 degree), `Ctrl+Z`/`Ctrl+X` speed, `Q`/`Shift+Q` range on the newest bearing (`Ctrl`: 0.2 NM). The amber curve shows the bearings that hypothesis predicts, the dots at the foot the residuals (measured minus predicted). Good hypotheses leave residuals scattered around zero; a wrong course, speed or range leaves a trend. The rail shows the residual RMS, the systematic trend after averaging, the fit and the observability. Range is only observable after an own course change (at least 6 degrees, better 30-60): without one, `K` refuses. `K` accepts the hypothesis as the contact's TMA fix; it is dead-reckoned on its course and speed and ages out after 120 s, so refine and re-accept as bearings come in. Noisy bearings give a large range uncertainty even when the fit is good. TMA does not estimate depth. With operator assistance set to training (`F10`) an automatic solver proposal (it needs at least 4 bearings over 180 s) is drawn as a thin line and `Shift+K` copies it into the hypothesis. Sonobuoy bearings enter the track with the buoy as observer.
- **UMWELT / FUSION** shows the bathythermograph (`E`, 60 s cooldown): measured layer depth, sound-speed profile and convergence-zone bands, plus the HMS/TAS comparison. Bearings within 5 degrees confirm each other; 9 degrees or more apart are flagged as a possible ghost contact. The layer is not fixed: afternoon sun makes it shallower (about 8 m), strong wind mixes it deeper over hours, and internal waves move it a few metres. Repeat the BT after a few hours or a weather change. The measured profile is the real temperature-driven sound speed (Mackenzie equation), so it drops below the layer. Point the mouse at the profile to read the exact depth, the sound speed there and whether that depth lies above or below the layer (uConsole and web). In the web client the plot also labels the layer, the seabed and the sound-speed minimum.
- **ACTIVE** lists echoes of the last 120 s: bearing, range and depth (+/-12 m). A ping fix ages out after 120 s. `W` selects the pulse: **CW** (1 s tone) gives coarse range (about 0.1-0.3 NM) but its Doppler separates a moving target from seabed reverberation; **LFM** (100 Hz sweep) measures range to a few metres and gains 20 dB against noise, but a slow or stationary target stays inside the reverberation. The echo strength depends on the target's aspect (broadside about 15 dB stronger than bow-on) and size. Rocky ground reverberates far more than mud; charted wrecks return real echoes that no contact owns ("unassociated echo").
- **Hearing the echo:** every return is audible when it arrives, after its real two-way travel time (about 2.5 s per nautical mile of range), for the ship's sonar and the helicopter's dipping sonar alike. A CW echo is a soft tone on the carrier, an LFM echo a short sweep; the pulse is the one the ping was sent with. A strong echo stands out clearly, a faint one barely rises out of the reverberation hiss. In the Remote Crew browser the echo plays with the general sound (loud or faint).

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
- The listening audio runs about one and a half seconds behind the display (Remote Crew browsers about two seconds) so a busy moment never interrupts it. After steering the listening bearing the old beam fades into the new one after that delay; the stream is not cut.
- Put the TAS below the measured layer to hear deep targets; keep the HMS for shallow ones. Both arrays run in parallel.
- The TMA page shows the closing rate derived from the accepted solution: positive means the target is closing.
- If the TAS and HMS disagree by 9 degrees or more, treat the contact as a possible ghost (the display flags it) and turn to resolve it.
- The towed array is a line: it cannot tell a bearing from its mirror about the cable. A contact heard only on the TAS is marked "TAS left/right ambiguous" with its mirror bearing and does not feed TMA; the display shows the side you choose (starboard by default). Turn 20 degrees and watch both traces: the true one stays continuous, the ghost jumps (the status then reads "turn made - compare traces"). On the broadband or fusion page `X` shows the other side and `Shift+X` confirms the shown side; nothing is resolved for you. A wrongly confirmed side stays mirrored (the TMA residuals will show it; `X` reopens the choice). A hull-sonar bearing resolves the side by measurement. Bearings toward the cable ends (endfire) are also less accurate than broadside.
- `Shift+F` selects the DEMON carrier band (200-800, 400-1400 or 1000-2000 Hz): search the band where the cavitation noise is strongest. `Ctrl+F` sets the heterodyne shift (400/700/1000/1200 Hz) for listening to low tonals.
- In the contact analyser (`F8`) with a contact selected, `Enter` assigns the browsed catalog profile to that contact and `Shift+Enter` clears it. The assignment is your annotation: it is shown in the contact list and saved, and it never changes the contact's classification or weapon interlocks.
- A contact is lost 120 s after its last detection. Keep tracking weak contacts, or reacquire with a ping.
- Wrecks return real echoes without Doppler. A submarine lying still beside a charted wreck hides in that echo from a CW ping (750 m range cell); an LFM ping resolves about 8 m and can separate the boat from the wreck. Suspect every wreck the enemy could have reached.
- The bathythermograph (`E`) measures to the seabed, at most 1500 m. Only after a measurement does the weather & sonar analysis (`0`) show the layer, the shadow zone below it and a SOFAR channel.
- The sonar never names a torpedo or a submarine. It reports what it hears: a mechanical launch transient (heard out to 35 NM) or high-frequency seeker pulses (about 6 NM) as a bearing, held on the Bridge alarm for 60 s, and breaking-up noises when a hull sinks. The OPZ symbol of a sonar contact follows your classification only; an unclassified contact stays unknown.

## Not modelled {#sonar-limits}

- No dot stack or Ekelund range; TMA is the hypothesis/residual method above. `T` switches the solver behind the training aid.
- No selectable split-window normalisation (TPSW); use gain, black level and contrast instead.
- No hard blind baffle sector; own noise is a soft lobe.
- No variable-depth sonar separate from the TAS.
