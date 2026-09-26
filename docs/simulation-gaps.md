# Simulation Realism Gaps — Closure Record (U-Jagd 1.1.0, save v12)

This document began as the realism gap analysis for U-Jagd 0.2.2 (2026-07-15)
and was carried forward to 1.0.0. The 1.1.0 physics upgrade closed every gap
in phases 0-12 on branch `sim-gaps-v12` (save format v12; v11 saves are
rejected without migration). Each row below states the model that now closes
the gap, the phase and its commit. The few items that stay out of scope are
listed with their reason at the end.

## How the upgrade is held to gameplay

- **Calibration:** `tools/calibrate.py --check` re-measures 77 gameplay metrics
  (ship speed/turn/acceleration, sonar and radar ranges, lookout, torpedo,
  submarine, damage and air-defence behaviour) through the public runtime and
  compares them with `tests/calibration/golden.json`, recorded on the 1.0.0
  tree (3b3753c). Intentional deviations are listed with their physical reason
  in `tests/calibration/deviations.json` (rpm display, turn rate at HALF,
  cavitating sea state 4, ray-traced sonar ranges).
- **Anchoring:** every new physical model is anchored so that the 1.0.0
  equilibrium value appears at its reference point (for example the radar's
  nominal range is its Pd = 0.5 range, the sonar figure of merit puts SE = 0
  at the former effective range, the CIWS lethal area reproduces the 1.0.0 leak
  rate).
- **Determinism and saves:** new random draws use the stateless counter-based
  `src/core/detrand.py`; every new state variable is in the exact save-v12
  schema (`src/core/save_schema.py`), validated strictly and covered by
  round-trip and continuation tests.
- **Observation boundary:** new measurements (sonar TMA ellipse, towed-array
  ambiguity, ESM level/range estimate, HF frequency, lookout contrast) are
  published as observations; nothing exposes hidden truth to stations or the
  Remote Crew projection.
- **Performance:** a 0.1 s simulation substep costs the same as in 1.0.0 on the
  development ARM host (6.7 ms mean over three seeds); ray-trace tables,
  radar range fractions and ESM emitter rankings use bounded pure caches.

## Phases

| Phase | Scope | Commit |
|---|---|---|
| 0 | Save v12, persisted AI timers, strict damage block, simulated AIS, calibration harness | bd9260b |
| 1 | Ocean environment: tides, mixed layer, SST/Mackenzie sound speed, wind drift, sediments, wrecks/rocks | d666b1b |
| 2 | Own-ship hydrodynamics: surge, Nomoto steering, cavitation number, seakeeping, squat, mass/fuel | 236d23b |
| 3 | Passive and active sonar equations, ambient noise, reverberation, pulse types | 4cd903a |
| 4 | Ray-traced propagation with bottom/surface loss and convergence zones | 5c9199e |
| 5 | Array gain, towed-array ambiguity, Doppler, Levenberg-Marquardt TMA, multistatic buoys | 7abc45f |
| 6 | Submarine and surface-ship physics | 8f79700 |
| 7 | Hostile sensing, own TMA, crew reaction, mast-limited ESM/datalink | 8e6b1d3 |
| 8 | Torpedo energy, fins, wire, proximity fuze, wake homing, ASROC | ae3991b |
| 9 | Decoys, seeker discrimination, Nixie cable, warship decoys | f75d177 |
| 10 | Damage, stability, fire, repair logistics | 9d8e15c |
| 11 | Radar equation, antenna scan, ESM amplitude, HFDF, lookout | 2f3b0f2 |
| 12 | Missile flight physics, chaff clouds, CIWS, raiders, helicopter, buoys | 97319f3 |
| 13 | Performance pass, closure record, release 1.1.0 | this change |

## 1. Player Frigate — `src/ship/ship.py` + `src/world/grounding.py` + `src/core/config.py`

| Gap | Model now | Closed in |
|---|---|---|
| Hydrodynamic resistance | `src/physics/ship_dynamics.py`: resistance R = k v^2 (k from installed power and propulsive efficiency) plus added resistance in waves (Hs^2 B^2/L); thrust from a linear K_T(J) propeller; exact Riccati integration so any step size gives the same speed. | 2 (236d23b) |
| Propeller/shaft physics | Shaft revolutions from the propeller (steady rpm proportional to speed), a propulsion control programme limiting load-up, reverse-pitch braking, and cavitation from the cavitation number sigma at the screw depth (calibrated to 15 kn in calm water; earlier when pitching lifts the stern). | 2 (236d23b) |
| Rudder effectiveness vs speed | `speed_factor = clamp((speed/10)^2, 0, 1.5)` — already quadratic (dynamic-pressure-like), not linear. `ship.py:139`. | pre-1.1 (2026-09) |
| Turn radius | First-order Nomoto steering r = K (V/L) delta with T proportional to L/V, calibrated to 1.2 deg/s at FULL; turning circle about 0.4 NM at all speeds. | 2 (236d23b) |
| Trim / sink at speed | Hydrostatic draft from displacement (fuel burnt, floodwater), Barrass squat in shallow water feeding swept grounding, dynamic trim by the stern ~ Fn^2. | 2 (236d23b) |
| Sea-state effect on motion | Added resistance in waves; 1-DOF roll and pitch oscillators driven by an 8-component Pierson-Moskowitz wave slope relative to the wave direction, turn heel, damage list and speed-dependent fin stabilizer damping. | 2 (236d23b) |
| Draft / under-keel clearance | Dynamic draft (displacement + squat) is passed to `swept_grounding`; the tide (Phase 1) changes the water depth. | 2 (236d23b) |
| Fuel → mass → performance | Displacement = design load - burnt fuel + floodwater drives surge inertia and draft; fuel burn follows delivered shaft power (steady values reproduce the 1.0.0 cubic law). | 2 (236d23b) |
| Damage → hydrodynamics | List yaw bias (existing), jammed rudder when the aft steering-gear compartment (flight deck) is destroyed, fin stabilizers lost with a destroyed hull compartment, floodwater mass. | 2 (236d23b) |
| Wake signature | Bounded, saved wake ring (48 points, one per 10 s) with sea-state-dependent bubble decay and `Ship.wake_strength_at()`; consumed by own-sonar and wake-homing weapons in later phases. | 2 (236d23b) |

## 2. Enemy Submarines — `src/enemies/sub.py` + `src/enemies/endurance.py`

| Gap | Model now | Closed in |
|---|---|---|
| No depth dynamics | Inertial depth changes; hydroplane authority ~ v^2 (ballast-only rate below ~4 kn); one emergency blow from a bounded HP-air store at 4 m/s. | W2 (1.0.0), 6 (8f79700) |
| No cavitation model on subs | Onset speed from the catalog (or tendency) rising with depth as sqrt(1 + z/10.3); cavitation adds 8 dB source level. | 6 (8f79700) |
| No pressure / hull limits | Fatigue accumulates beyond 0.9 x test depth (saved) and converts to damage; 1.5 x test depth crushes the hull. | 6 (8f79700) |
| Speed vs noise coupling is indirect | Source level ~40 log v relative to the patrol reference (subs 6 kn, ships their cruise speed), plus cavitation and launch/blow transients, in all passive sonar paths (own, dipping, buoys, NPC). | 6 (8f79700) |
| No propeller-wake / bubble effects | Own wake ring masks the hull array astern; submarine screw transients and cavitation raise source level; torpedo bubble trails in Phase 8. | 2 (236d23b), 6 (8f79700), 8 (ae3991b) |
| Evasive manoeuvre is kinematic | Evasion speeds are reached at the hull's acceleration limit, deep dives are limited by plane authority, and a hard sprint cavitates and becomes loud. | 6 (8f79700) |
| LAUER is a speed brake, not a tactic | The lurking boat heads into the current at bare steerage way and holds station. | 6 (8f79700) |
| No current / drift | `World.current_vec(x, y)` provides a deterministic current field, already applied to ship/sub/surface ships (`world.py:217-224`), and now also to torpedoes (both classes) and the free-drift enemy decoy. | pre-1.1 (2026-09) |
| Torpedo launch is instantaneous | Motor spool-up, launch depth, and a loud 8 s tube-discharge transient on the firing boat. | W2 (1.0.0), 6 (8f79700) |
| No active sonar use by subs | `Sub._maybe_active_ping` (aggressive boats, fresh contact, cooldown saved since Phase 0); the ping is heard by the frigate. | pre-1.1 (1.0.0) |
| No ESM/ESB use by subs | All submarines use their `PlatformSensorSuite` (legacy snapshot gate removed); ESM works only with the mast up (<= 18 m); range from their own passive TMA with TMA legs (saved track). | 7 (8e6b1d3) |
| No ASW coordination | Hostile red-group datalink shares tracks; a submerged boat only exchanges at mast depth or while snorkelling/transmitting, which makes the latency physical. | 7 (8e6b1d3) |
| Damage model is scalar | Shock-factor hits, progressive flooding while holed, emergency blow, fatigue; damage throttles speed and raises noise. Subs keep a lumped damage value by design (no player-visible compartments). | 6 (8f79700), 10 (9d8e15c) |

## 3. Enemy Surface Ships — `src/enemies/surface.py`

| Gap | Model now | Closed in |
|---|---|---|
| No ship hydrodynamics | Speed lag from the catalog, Nomoto-linear turning, and added resistance in waves lowering attainable speed by hull length (small hulls lose more). | 6 (8f79700) |
| No radar horizon | The ASM body has its own altitude (20 m cruise, 5 m terminal); radar detection and the HOJ bearing both require line of sight over the horizon. | 12 (97319f3) |
| No countermeasures | Hostile combatants stream acoustic decoys (saved store of 2) when they hear a torpedo launch; missile defence (ship chaff/CIWS) is modelled on the own ship in Phase 12. | 9 (f75d177), 12 (97319f3) |
| No damage propagation | Shock-factor damage (near misses no longer sink), progressive flooding above 30 %, radar lost above 60 % and missile launch above 75 % damage. | 8 (ae3991b), 10 (9d8e15c) |
| No evasive manoeuvres | Combatants turn away at flank speed on a heard launch (W2, state saved in Phase 0) and stream decoys (Phase 9). | pre-1.1 (1.0.0) |
| No weapon systems modelling | Warship ASMs fly to the datum of the launcher's own (noisy) sensor contact, so fire-control error carries into the shot; 3-DOF missile with seeker FOV, lock delay and PN; torpedo and ASROC proximity fuze with shock-factor damage; salvos saturate the two ESSM fire channels and the CIWS mount. | 8 (ae3991b), 12 (97319f3) |

## 4. Torpedoes — `src/weapons/torpedo.py`

| Gap | Model now | Closed in |
|---|---|---|
| No launch dynamics | Spool-up, launch-depth offset and tube transient on the firing boat, speed-dependent turning and depth response right after launch. | W2 (1.0.0), 6 (8f79700), 8 (ae3991b) |
| No acceleration phase | Spool-up (W2) plus an energy store: power ~ v^3, range emerges from the battery and grows when running slower. | pre-1.1 (1.0.0) |
| No depth inertia | Fin-limited vertical acceleration (~ dynamic pressure) with a proportional depth command (saved rate, small overshoot); hostile torpedoes now have depth control too (run depth, keel depth when homing). | 8 (ae3991b) |
| No hydrodynamic turn limit | Constant turning radius: turn rate proportional to speed, for both torpedo classes. | 8 (ae3991b) |
| No wire dynamics | Two finite spools (torpedo 1.25 x range, ship 5 NM of own track) and tension breaks from ship overspeed (> 20 kn) or hard turns (> 1.5 deg/s) held for 5 s; the old timers remain as datalink latency. | 8 (ae3991b) |
| No propeller noise model | Speed-dependent propulsor lines (both classes) and a 60 log v source level; the target hears a running torpedo through the passive sonar equation (ray excess, ambient, own noise). | 8 (ae3991b) |
| Kill is binary | Proximity fuze at closest approach; damage from the shock factor sqrt(W)/R (250 kg), so near misses damage without sinking. | 8 (ae3991b) |
| No target reaction to torpedo | Launch-transient and homing alerts, crew recognition delay (per-boat lognormal 2-15 s, saved countdown), evasive dive across the layer; Phase 8 makes the running-torpedo notice a sonar-equation detection. | W2 (1.0.0), 7 (8e6b1d3), 8 (ae3991b) |
| No self-destruction timing | Battery exhaustion stops the motor; the weapon coasts (dv/dt = -k v^2) and is lost below 30 % speed. | 8 (ae3991b) |
| No wake / trail signature | Shallow hostile torpedoes leave a bubble track visible to the lookout by day up to 1.5 NM; hostile torpedoes can home on the own-ship wake. | 8 (ae3991b) |
| ASROC payload depth | The payload flies a helix search at its splash point while its depth controller descends to the search depth. | 8 (ae3991b) |

## 6. Air — `src/air/`

| Gap | Model now | Closed in |
|---|---|---|
| No flight dynamics | Raiders fly coordinated turns at a 56 deg bank limit (rate = g tan(bank)/v) and climb/descend at a limited vertical speed; missiles are 3-DOF point masses (boost, sustainer, altitude control, g-limited turns). Civil/military transit flights keep standard-rate turns at constant altitude (their cruise profile); engine failures are out of scope. | 12 (97319f3) |
| No radar horizon | Raiders already used `radar_horizon_nm()`; regular civil/military `flights` now use it too (flat `FLIGHT_RADAR_ALTITUDE_M`). **Still open for the ASM body itself** (see below): its own search-radar detection in `game.py._update_air_picture` uses flat `air_eff` with no altitude/horizon term, so a sea-skimmer is currently seen by search radar at the same range as a 60 m-altitude aircraft. | pre-1.1 (2026-09) |
| No ASM boost phase | Launched rounds boost from the launcher's speed at 60 m/s^2, then the sustainer holds cruise; the saved age is bounded by the powered flight time (range at cruise plus boost). | 12 (97319f3) |
| No seeker physics | ASM: inertial mid-course to the launch datum, active seeker with a +/-30 deg field of view and 1.5 s lock, then proportional navigation (N = 4) limited to 15 g. ESSM: PN on the seeker LOS rate within its airframe turn limit. | 12 (97319f3) |
| No ESM warning for inbound ASM | ASM `seeker_active()` stays silent mid-course (INS-only) and radiates once inside `seeker_active_range_nm` (18 NM); the seeker's own fingerprint (9.0-9.5 GHz, pulse-Doppler) feeds `_update_esm_picture` as a distinct RWR track, independent of the existing HOJ/jammer path (`asm.py`, `game.py._asm_seeker_emitter`). Not yet catalogued for classification in `data/contacts/*` emitters, so `rank_emitters()` won't positively ID it as "missile" — an intentional ambiguity, but worth revisiting. | pre-1.1 (2026-09) |
| ASM body ignores radar horizon | See radar horizon above: a sea-skimmer appears at about 20 NM (15 NM in the terminal phase). | 12 (97319f3) |
| Raider has no attack-altitude profile | Each salvo needs a pop-up to 300 m and a 4 s fire-control lock; the fire-control radar is an ESM emission only during the pop-up, and the higher raider crosses the radar horizon earlier. | 12 (97319f3) |
| No CIWS physics | Mount slews at 115 deg/s and fires only on target; the fire control uses its own latest measurement; the CIWS radar holds missiles inside 3 NM; burst kill from dispersion (2 mrad) and prediction error over the rounds' time of flight; bursts that would arrive after impact cannot kill. Calibrated to the 1.0.0 leak rate. | 12 (97319f3) |
| No chaff physics | Up to 8 saved chaff clouds laid off the threat axis, blooming over 3 s, drifting with the wind and falling out after 90 s; seduction is the Swerling-1 contest between cloud and ship echo, reduced when the cloud has not bloomed by the missile's arrival; a seduced missile steers to the cloud. | 12 (97319f3) |
| No ECM on own ship | The ELOKA station's ECM jammer (noise, RGPO/VGPO, false targets) acts on missile seekers; GPS spoofing is out of scope for this setting. | pre-1.1 (1.0.0) |
| Helicopter: no hover dynamics | Hover burns fuel 1.3x faster; wind pushes the aircraft off its (saved) hover point against the pilot's position hold; launch and recovery wait for a deck-motion window (roll 8 deg, pitch 3.5 deg). | 12 (97319f3) |
| Sonobuoy: no drift | Buoys drift with the surface current (which carries the wind drift) plus 2 % windage. | 12 (97319f3) |

## 7. Sonar & Propagation — `src/sonar/sonar.py` + `src/sonar/propagation.py` + `src/audio/receiver.py`

| Gap | Model now | Closed in |
|---|---|---|
| No full sonar equation | `src/sonar/equation.py`: passive SE = SL - TL - NL + DI - DT per band; active SE = SL - 2TL + TS - max(NL - PG, RL - Doppler rejection). Calibrated so 1.0.0 detection ranges hold (`tools/calibrate.py`). Own sonar, dipping sonar and NPC platform sonars use it. | 3 (4cd903a) |
| No source-level model | Source level in dB from the catalog quietness; NPC passive sonars hear loud targets farther (up to +5 dB). | 3 (4cd903a), 6 (8f79700) |
| No receiver noise model | Wenz/Knudsen wind noise (flat below 500 Hz), distant shipping from nearby merchant count, heavy-rain noise, thermal floor, hull-array self-noise floor plus speed/cavitation self noise, own wake astern; NPC receiver sensitivity from the catalog. | 3 (4cd903a) |
| No target strength (TS) | Aspect- and length-dependent target strength (beam highlight ~20 log(L/10)+8 dB, bow/stern 15 dB lower). | 3 (4cd903a) |
| Propagation: fixed 4 paths | `src/sonar/raytrace.py`: 48-ray Snell fan through the Mackenzie profile (turning points, surface duct, shadow zone, convergence where deep enough), rough-surface and lossy Rayleigh bottom reflections, incoherent flux summation into TL(range, depth) tables per band; pure functions of a quantized environment key with a bounded LRU cache (purity keeps save/load deterministic). Own, dipping and NPC passive sonars use it via reciprocity (sensor = source). | 4 (5c9199e) |
| Propagation: no frequency dependence in path loss | Francois-Garrison absorption per band; boundary losses (surface roughness k-dependence) per band in the ray tables. | 3 (4cd903a), 4 (5c9199e) |
| No Doppler | Tonal lines in LOFAR/audio are Doppler shifted by the closing speed; the strongest tonal is measured per bearing point (SNR-dependent error) and saved; TMA estimates the unshifted f0 and uses Doppler for observability. | 5 (7abc45f) |
| No interference / clutter | Boundary (Lambert bottom by sediment, wind-dependent surface) and volume reverberation with absorption; CW Doppler rejection grows with radial speed; charted wrecks return unassociated echoes (saved pending clutter). | 3 (4cd903a) |
| Ping: no pulse parameters | Selectable CW (1 s) / LFM (1 s, 100 Hz) pulse (`W`, saved): resolution c*tau/2 or c/2B, Cramer-Rao range accuracy, LFM processing gain against noise, CW Doppler against reverberation. | 3 (4cd903a) |
| TMA: fixed grid | Grid seed plus Levenberg-Marquardt refinement over position/velocity (+f0 with Doppler), accepted where observable; 1-sigma covariance ellipse published and saved; range sigma never more optimistic than the observability heuristic. | 5 (7abc45f) |
| No multi-static sonar | Sonobuoy (sonar-equation) and dipping bearings enter the contact's bearing track with their own observer positions, so one estimator fuses own-ship, buoy and helicopter geometry. | 5 (7abc45f) |
| No sonar array beamforming | Uniform-aperture sinc beam pattern with -13 dB side lobes in the receiver/broadband scan, towed-array endfire broadening (1/sqrt(sin)), and the towed line array's left/right ambiguity (mirror bearing, excluded from TMA until an own turn or the hull array resolves it). | 5 (7abc45f) |

## 8. Radar / ESM / HFDF — `src/sensors/esm.py`, `src/sensors/tracks.py`, `src/core/game.py`

| Gap | Model now | Closed in |
|---|---|---|
| No radar equation | `src/sensors/radar.py`: SNR ~ sigma/R^4 anchored so the nominal range is the Pd = 0.5 point for a broadside target; Swerling-1 target behind a 16-cell CA-CFAR (exact closed form, Pfa 1e-6); GIT-type sea clutter (+3 dB per sea state, CNR ~ R^-3; air search with MTI); two-way rain attenuation; aspect enters as RCS (aspect^4). Hostile platform radars use the same Pd = 0.5 range. Anchors reproduce the 1.0.0 weather/rain losses (calibration harness). | 11 (2f3b0f2) |
| No scan rate / PPI dynamics | The antenna turns in simulation time (90 deg/s, phase and pending sweep saved); a contact gets one look only when the beam passed its bearing since the previous publication; one deterministic (`detrand`) detection draw per look; the PPI sweep line is the saved antenna phase. | 11 (2f3b0f2) |
| No ECCM / jamming effect on radar | Self-screening noise jammer as JNR ~ R^-2 solved from the profiled burn-through range; skin detection uses SINR = S/(N + C + J), so the echo emerges inside burn-through (HOJ bearing outside). Deception jamming (RGPO/angle) is out of scope: missiles carry noise jammers only. | 11 (2f3b0f2) |
| ESM: no signal strength | One-way level 20 log10(R_class/R); rotating search radars reach the mast with the main beam once per revolution (2-5 s by role, 0.5 s dwell), side lobes at -25 dB; peak-hold level, measured scan period (LIVE window follows it) and a range estimate from the best candidate's power class, shown at ELOKA and in Remote Crew. | 11 (2f3b0f2) |
| HFDF: no frequency | `src/sensors/hfdf.py`: the boat picks OWF = 0.85 MUF for its shore path (foF2 day/night, F2 height 300 km); ground-wave range falls with frequency (anchored 120 NM at 15 MHz); sky wave only beyond the skip distance with doubled bearing error; frequency and mode are published on the observation. | 11 (2f3b0f2) |
| No AIS decoding | `src/sensors/ais.py` is a simulated own-ship AIS receiver: ITU-R M.1371 class-A dynamic reports (COG/SOG every 2-10 s, 3 min at anchor) and static reports (name every 6 min), received only inside VHF line of sight and not through land. Radar observations of civilians no longer carry the true name/course (an observation-boundary leak); both come from the latest decoded report. MMSI is deliberately not shown to the player, so live and simulated traffic stay indistinguishable. Decoded reports are saved (save v12). | 0 (bd9260b) |
| Lookout: no silhouette / size | `src/sensors/visual.py`: Koschmieder contrast decay with meteorological visibility, Blackwell-type threshold vs angular size (target height), optical horizon (eye 18 m), whitecap clutter for sea-level targets, night threshold interpolated by lunar illumination (seeded lunar age advancing with sim time). C0 anchored to the 1.0.0 day ranges; searchlight and smoke are out of scope. | 11 (2f3b0f2) |

## 9. Damage Model — `src/ship/damage.py`

| Gap | Model now | Closed in |
|---|---|---|
| No hit-location physics | The torpedo's impact point on the hull (`_hull_impact`) selects the compartment; hole area scales with the warhead stand-off (20 m / distance, 0.5-3x); ASM hits above the waterline and mainly starts fires. | 10 (9d8e15c) |
| No flooding dynamics | Orifice inflow Q = Cd A sqrt(2 g h) against the outside waterline (dynamic draft + heel), so flooding slows as levels equalize and high rooms stay dry; floodwater mass, free-surface GM loss and transverse moment give draft and list; the ship sinks beyond reserve buoyancy and capsizes at lost GM or 35 deg heel. | 10 (9d8e15c) |
| No fire propagation physics | Growth from compartment fuel load x oxygen, smothered by flooding and cooled by water; deterministic spread after a bulkhead has stayed hot (heat timer, saved); flooded switchboards short and start electrical fires. | 10 (9d8e15c) |
| No systems degradation | Continuous `capability()` per compartment from flooding and fire scales sonar and radar range; destroyed rooms still disable their station. | 10 (9d8e15c) |
| No damage repair realism | Teams walk the compartment graph (20 s per hop, ETA saved) and act only on arrival; holes must be patched first with one of 8 patch kits, leaving a small leak. | 10 (9d8e15c) |
| No secondary damage | Magazine cook-off above 90 % fire destroys the weapons room and holes its neighbours; electrical short-circuit fires; capsize as structural stability failure. | 10 (9d8e15c) |
| Torpedo damage to subs | Shock-factor damage, one emergency blow, hull fatigue, and progressive flooding of a holed boat (30-100 % damage) that ends in sinking unless it surfaces. | 6 (8f79700), 8 (ae3991b), 10 (9d8e15c) |

## 10. World / Environment — `src/world/`

| Gap | Model now | Closed in |
|---|---|---|
| No ocean currents | Static seeded current field (`World.current_vec`) applied to ship, subs, surface ships, torpedoes and decoys; Phase 1 adds the wind-driven component. | pre-1.1 (1.0.0) |
| No tides | `src/world/ocean.py`: M2 + S2 constituents, seeded amplitude/phase and a spatial phase gradient, Green's-law shoaling. `World.depth_m`/`physical_depth_m` = chart datum + tide, so grounding and sub safe depth follow the tide. | 1 (d666b1b) |
| No thermocline dynamics | Mixed-layer depth = seasonal cell base + diurnal heating (-8 m at 15:00, zero 24-h mean) + wind-mixing deepening (saved first-order relaxation, fast deepening / slow restratification) + three internal-wave components. | 1 (d666b1b) |
| No wind/current interaction | 3 % of wind speed, deflected 20 deg to the right of downwind, added to `current_vec`. | 1 (d666b1b) |
| No seasonal / diurnal sound-speed variation | Seeded season, SST with seasonal and diurnal terms, exponential thermocline temperature profile and the Mackenzie (1981) equation. Used by the bathythermograph and ping echo latency; the ray tracer (Phase 4) samples the same profile. | 1 (d666b1b) |
| Seabed composition | Seeded 12x12 sediment grid (rock/gravel/sand/silt/mud) from depth and slope with Hamilton-style geoacoustic parameters and a Rayleigh fluid-fluid bottom-loss function; consumed by the sonar equation (Phase 3) and ray tracer (Phase 4). | 1 (d666b1b) |
| No underwater geography beyond depth | Up to 64 seeded wrecks and submerged rocks. Rocks shoal `depth_m` (tops at least 15 m, a hazard to submarines and weapons, never to surface keels); wrecks become active-sonar clutter in Phase 3. | 1 (d666b1b) |

## Atmosphere and weather station (after 1.1.0)

| Gap | Model now | Closed in |
|---|---|---|
| No barometer, air temperature, gusts, cloud ceiling, snow/icing or twilight | `src/world/atmosphere.py`: derived (no saved state) from the weather epoch, season, clock and sea temperature - barometer leading the sea with WMO tendency classes and storm warning, air temperature with cold northerly outbreaks, snow below 0.5 deg C, gusts, ceiling, spray/precipitation icing, sun elevation with twilight, moon phases. Helicopter launch/dipping honour gusts, ceiling and icing. | weather station |
| Constant salinity | Rain-fed fresh surface lens mixed away by wind in the Mackenzie sound speed. | weather station |
| No deep sound channel | Temperature profile continues to the seabed in the ray profiles and the bathythermograph (to 1500 m); a SOFAR axis appears where an interior sound-speed minimum exists. | weather station |

## Charted hazards

| Gap | Model now | Closed in |
|---|---|---|
| Wrecks only as sonar clutter | Wrecks and rocks are drawn on every chart (native and web) with depth and tooltip; wrecks raise the seabed within half their length (obstacle for grounding, submarines, weapons); evading submarines near the frigate may lie on the bottom beside a charted wreck, where a zero-Doppler echo inside the same range cell and beam merges with the wreck echo (CW 750 m cell, LFM about 8 m). | charted hazards |

## Out of scope (with reason)

| Item | Reason |
|---|---|
| Air-to-air combat, CAP, fighters | U-Jagd is an ASW frigate simulation; hostile aircraft are engaged only by own-ship air defence. |
| Deception jamming by missiles (RGPO/angle gates) | Hostile missiles carry self-screening noise jammers (modelled with burn-through); own-ship ECM does model RGPO/VGPO/false targets against seekers. |
| GPS spoofing | Not relevant to the modelled sensors and weapons (inertial/radar guidance). |
| Lookout searchlight and smoke | No player control for them; visibility, contrast, size, horizon and moonlight are modelled. |
| Aircraft engine failure | Aircraft are threats/traffic, not player-flown airframes. |
| Compartments inside hostile submarines | Hostile boats keep a lumped damage value with progressive flooding, emergency blow and hull fatigue; their internal layout is never observable. |
| Counter-flooding orders | Heel is corrected by repair and rudder; the stability model is complete without a manual ballast order. |

Real-world geography, seabed and weather used by the world are synthetic or
generalised (see `THIRD_PARTY_NOTICES.md` and the manual's disclaimers); the
physics models are plausible engineering approximations anchored to the
1.0.0 gameplay, not validated naval data.
