# Simulation Realism Gap Analysis — U-Jagd 0.2.2

> **Status (physics upgrade, save v12):** rows are marked *Closed (Phase N)* as the
> phased upgrade on branch `sim-gaps-v12` lands. Calibration against the 1.0.0
> behaviour is enforced by `tools/calibrate.py --check` (`tests/calibration/`).

Analysis date: 2026-07-15
Scope: Ship dynamics, weapons, enemy AI, air, sonar/sensors, world/environment.

---

## 1. Player Frigate — `src/ship/ship.py` + `src/world/grounding.py` + `src/core/config.py`

### 1.1 What is currently modeled

| Aspect | Implementation | Ref |
|--------|---------------|-----|
| Rudder dynamics | 1st-order lag on rudder angle (`SHIP_RUDDER_RATE_DEG_PER_S = 4°/s`, max ±30°) + 1st-order lag on yaw rate (`SHIP_YAW_RESPONSE_S = 10 s`) | `ship.py:126-139` |
| Speed response | Linear rate-limited approach to target speed (`SHIP_SPEED_RESP_KN_PER_S = 0.08 kn/s ≈ 2–4 min to full`) | `ship.py:141-153` |
| Telegraph orders | Discrete STOP/SLOW/HALF/FULL/FLANK (0/6/10/16/25 kn) + ASTERN (3 kn) | `config.py:194-203`, `ship.py:50-71` |
| Fuel | Hotel load 400 kg/h + cubic propulsion load up to 7 400 kg/h; 500 t capacity; astern penalty ×1.15 | `ship.py:88-112`, `config.py:205-208` |
| Cavitation | Binary flag at `CAVITATION_KN = 15`; boosts noise, degrades passive sonar by factor 0.35 | `ship.py:78-81`, `config.py:214-215` |
| Quiet mode | Speed capped to 12 kn, noise ×0.65 | `ship.py:25,142-143,210-211` |
| Roll/pitch | Sinusoidal cosmetic oscillation scaled by sea state + speed | `ship.py:195-201` |
| Grounding | Swept hull-footprint (9 points) against coastline + bathymetry; impact energy → compartment flooding | `grounding.py:343-557`, `game.py:4318-4334` |
| Hull spec | Mass 3600 t, length 118 m, beam 14 m, draft 7.5 m, keel reserve 1.5 m | `grounding.py:18-43` |
| Station damage | 9 compartments; flooding/fire state machines; 3 repair teams; speed cap on engine damage | `damage.py:33-266` |

### 1.2 Gaps and simplifications

| Gap | Current behaviour | Would need for realism |
|-----|-------------------|------------------------|
| ~~**Hydrodynamic resistance**~~ | **Closed (Phase 2).** `src/physics/ship_dynamics.py`: resistance R = k v^2 (k from installed power and propulsive efficiency) plus added resistance in waves (Hs^2 B^2/L); thrust from a linear K_T(J) propeller; exact Riccati integration so any step size gives the same speed. | — |
| ~~**Propeller/shaft physics**~~ | **Closed (Phase 2).** Shaft revolutions from the propeller (steady rpm proportional to speed), a propulsion control programme limiting load-up, reverse-pitch braking, and cavitation from the cavitation number sigma at the screw depth (calibrated to 15 kn in calm water; earlier when pitching lifts the stern). | — |
| ~~**Rudder effectiveness vs speed**~~ | **Fixed (2026-09).** `speed_factor = clamp((speed/10)^2, 0, 1.5)` — already quadratic (dynamic-pressure-like), not linear. `ship.py:139`. | — |
| ~~**Turn radius**~~ | **Closed (Phase 2).** First-order Nomoto steering r = K (V/L) delta with T proportional to L/V, calibrated to 1.2 deg/s at FULL; turning circle about 0.4 NM at all speeds. | — |
| ~~**Trim / sink at speed**~~ | **Closed (Phase 2).** Hydrostatic draft from displacement (fuel burnt, floodwater), Barrass squat in shallow water feeding swept grounding, dynamic trim by the stern ~ Fn^2. | — |
| ~~**Sea-state effect on motion**~~ | **Closed (Phase 2).** Added resistance in waves; 1-DOF roll and pitch oscillators driven by an 8-component Pierson-Moskowitz wave slope relative to the wave direction, turn heel, damage list and speed-dependent fin stabilizer damping. | — |
| ~~**Draft / under-keel clearance**~~ | **Closed (Phase 2).** Dynamic draft (displacement + squat) is passed to `swept_grounding`; the tide (Phase 1) changes the water depth. | — |
| ~~**Fuel → mass → performance**~~ | **Closed (Phase 2).** Displacement = design load - burnt fuel + floodwater drives surge inertia and draft; fuel burn follows delivered shaft power (steady values reproduce the 1.0.0 cubic law). | — |
| ~~**Damage → hydrodynamics**~~ | **Closed (Phase 2).** List yaw bias (existing), jammed rudder when the aft steering-gear compartment (flight deck) is destroyed, fin stabilizers lost with a destroyed hull compartment, floodwater mass. | — |
| ~~**Wake signature**~~ | **Closed (Phase 2 model).** Bounded, saved wake ring (48 points, one per 10 s) with sea-state-dependent bubble decay and `Ship.wake_strength_at()`; consumed by own-sonar and wake-homing weapons in later phases. | — |

### 1.3 Data structures / interfaces that would be touched

- `Ship.__init__`: add `trim_deg`, `draft_m`, `mass_t` (dynamic), `propeller_state`, `rudder_lift_coeff`
- `Ship.update()`: replace linear speed approach with thrust/drag equilibrium
- `Ship.steer_input()` / `Ship.update()`: speed-dependent rudder authority
- `config.py`: add `SHIP_DRAG_COEFF`, `SHIP_PROPELLER_KV`, `SHIP_SHARP_RATIO`, `SHIP_SQUAT_EXponent`, sea-state drag table
- `damage.py`: add list angle, asymmetric flooding, structural integrity
- `grounding.py`: `HullSpec` already has mass/length/beam/draft; extend with waterplane area, metacentric height

---

## 2. Enemy Submarines — `src/enemies/sub.py` + `src/enemies/endurance.py`

### 2.1 What is currently modeled

| Aspect | Implementation | Ref |
|--------|---------------|-----|
| State machine | PATROLLE ↔ EVADE ↔ LAUER ↔ SINKING | `sub.py:417-524` |
| Utility-based AI | Scores hide/lurk/attack/escape from distance, thermo position, frigate noise, damage | `sub.py:173-199` |
| Endurance (battery/AIP/snorkel/radio) | Full phase machine: SUBMERGED → AIP → ASCENDING → SNORKEL → RADIO → DESCENDING; battery kWh, AIP energy, generator charge | `endurance.py:26-282` |
| Speed support from power | `supported_speed()` computes max speed from available kW vs propulsion power curve `load_kw = hotel + max_kw * (v/v_max)^n` | `endurance.py:92-113` |
| Noise model | `quiet_factor()` from profile (0..1), modified by damage, EVADE, LAUER, transmitting; `noise_level() = 1 - quiet` | `sub.py:582-594` |
| LOFAR / acoustic signature | Fingerprinted tonal lines (blade rate, harmonics, secondary tonals) + broadband noise; catalog-driven | `sub.py:636-714`, `data/contacts/subs.json` machines |
| Motion limits | `motion_limits()`: turn rate, accel, depth rate from catalog (length-based if reference exists) | `platform.py:405-426` |
| Counter-attack | Interception course with lead, ±3° aim error, probability-based fire, weapon-arc check | `sub.py:215-303` |
| Decoy deployment | One-time on torpedo alert, catalog probability, cooldown | `sub.py:162-172, 348-355` |
| Torpedo alert | Triggers EVADE + decoy + faster evasive speed | `sub.py:162-171` |
| Ping reaction | `hear_ping()` → immediate EVADE | `sub.py:152-161` |
| Land avoidance | Sweep check + 90° turn on blocked path | `sub.py:501-507` |
| World-boundary reflection | Bounce off 0/size_nm edges | `sub.py:510-515` |

### 2.2 Gaps and simplifications

| Gap | Current behaviour | Would need for realism |
|-----|-------------------|------------------------|
| ~~**No depth dynamics**~~ | **Closed (Phases W2 + 6).** Inertial depth changes; hydroplane authority ~ v^2 (ballast-only rate below ~4 kn); one emergency blow from a bounded HP-air store at 4 m/s. | — |
| ~~**No cavitation model on subs**~~ | **Closed (Phase 6).** Onset speed from the catalog (or tendency) rising with depth as sqrt(1 + z/10.3); cavitation adds 8 dB source level. | — |
| ~~**No pressure / hull limits**~~ | **Closed (Phase 6).** Fatigue accumulates beyond 0.9 x test depth (saved) and converts to damage; 1.5 x test depth crushes the hull. | — |
| ~~**Speed vs noise coupling is indirect**~~ | **Closed (Phase 6).** Source level ~40 log v relative to the patrol reference (subs 6 kn, ships their cruise speed), plus cavitation and launch/blow transients, in all passive sonar paths (own, dipping, buoys, NPC). | — |
| ~~**No propeller-wake / bubble effects**~~ | **Closed (Phases 2/6/8).** Own wake ring masks the hull array astern; submarine screw transients and cavitation raise source level; torpedo bubble trails in Phase 8. | — |
| ~~**Evasive manoeuvre is kinematic**~~ | **Closed (Phase 6).** Evasion speeds are reached at the hull's acceleration limit, deep dives are limited by plane authority, and a hard sprint cavitates and becomes loud. | — |
| ~~**LAUER is a speed brake, not a tactic**~~ | **Closed (Phase 6).** The lurking boat heads into the current at bare steerage way and holds station. | — |
| ~~**No current / drift**~~ | **Fixed (2026-09).** `World.current_vec(x, y)` provides a deterministic current field, already applied to ship/sub/surface ships (`world.py:217-224`), and now also to torpedoes (both classes) and the free-drift enemy decoy. | — |
| ~~**Torpedo launch is instantaneous**~~ | **Closed (Phases W2 + 6).** Motor spool-up, launch depth, and a loud 8 s tube-discharge transient on the firing boat. | — |
| ~~**No active sonar use by subs**~~ | **Closed.** `Sub._maybe_active_ping` (aggressive boats, fresh contact, cooldown saved since Phase 0); the ping is heard by the frigate. | — |
| ~~**No ESM/ESB use by subs**~~ | **Closed (Phase 7).** All submarines use their `PlatformSensorSuite` (legacy snapshot gate removed); ESM works only with the mast up (<= 18 m); range from their own passive TMA with TMA legs (saved track). | — |
| ~~**No ASW coordination**~~ | **Closed (Phase 7).** Hostile red-group datalink shares tracks; a submerged boat only exchanges at mast depth or while snorkelling/transmitting, which makes the latency physical. | — |
| **Damage model is scalar** | `self.damage: float` 0-100; affects speed (`speed_for_state`), noise, and sinking | Compartment flooding on subs; loss of specific systems; trim change; rudder damage |

### 2.3 Data structures / interfaces that would be touched

- `Sub.__init__`: add `trim_deg`, `plane_angle`, `current_vec`, `pressure_depth_m`, `hull_stress`
- `Sub.update()`: replace `depth += clamp(...)` with physics-based depth dynamics
- `Sub.quiet_factor()`: derive from RPM, speed, cavitation state, hull damage
- `SubmarineEndurance`: add depth-dependent power draw, emergency blow energy
- `data/contacts/subs.json` machines: add `cavitation_onset_kn`, `pressure_hull_rating_m`
- `config.py`: add current fields, pressure constants

---

## 3. Enemy Surface Ships — `src/enemies/surface.py`

### 3.1 What is currently modeled

| Aspect | Implementation | Ref |
|--------|---------------|-----|
| Loiter / orbit | Waypoint orbit around anchor; 4-point loiter for military; civil: A→B via optional waypoint | `surface.py:126-197` |
| ASM salvo | When frigate within `WARSHIP_ASM_RANGE_NM` (35 NM) and LOS clear; salvo size from catalog | `surface.py:275-289`, `game.py:3796-3811` |
| ASROC response | Responds to positioned sonar fixes (ACTIVE/TMA/BUOY/FUSED) | `surface.py:199-232` |
| RCS aspect | `aspect_rcs_factor()` — broadside = 1.0, end-on = 0.55 | `config.py:444-449` |
| Radar emission | `esm_prob` from catalog; `emitter` flag | `surface.py:76` |
| AIS | Civilian ships transmit AIS; military do not | `surface.py:109-110` |
| Damage | Scalar 0-100; `speed_cap_kn` reduced by 25% at full damage; `hit()` adds 34 per torpedo | `surface.py:114-120` |
| Motion | Turn rate 1°/s, accel 0.03 kn/s (catalog-driven) | `surface.py:55-59` |

### 3.2 Gaps and simplifications

| Gap | Current behaviour | Would need |
|-----|-------------------|------------|
| ~~**No ship hydrodynamics**~~ | **Closed (Phase 6).** Speed lag from the catalog, Nomoto-linear turning, and added resistance in waves lowering attainable speed by hull length (small hulls lose more). | — |
| ~~**No radar horizon**~~ | **Fixed (2026-09).** Surface detection now uses `min(effective_range × aspect, radar_horizon_nm(RADAR_ANTENNA_HEIGHT_M, RADAR_SURFACE_TARGET_HEIGHT_M))` for both civilians and warships (`game.py`, `_update_air_picture`), the same formula already used for raiders. | — |
| **No countermeasures** | Warships do not deploy chaff/flare | ASM jamming, chaff, hard-kill CIWS on enemy ships |
| **No damage propagation** | Single scalar `damage`; one torpedo = 34 damage → 3 hits to sink | Compartment flooding, fire, loss of specific capabilities |
| **No evasive manoeuvres** | Loiter pattern only; no evasive when torpedo detected | Evasive turns, smoke, decoys |
| **No weapon systems modelling** | ASM/ASROC are simple projectiles; no fire-control solution error | Guidance accuracy, warhead proximity fuze, multi-target saturation |

### 3.3 Data structures touched

- `SurfaceShip`: add `draft_m`, `trim_deg`, `radar_height_m`, `damage_compartments`
- `data/contacts/warships.json`: add hull dimensions, radar antenna height, countermeasure profiles

---

## 4. Torpedoes — `src/weapons/torpedo.py`

### 4.1 What is currently modeled

| Aspect | Implementation | Ref |
|--------|---------------|-----|
| Speed | Fixed `speed_kn` from catalog (45/55/28 kn) | `torpedo.py:45`, JSON |
| Range | Fixed `range_nm` (12/30 NM); travel counter; SASE at range | `torpedo.py:46,251-253` |
| Wire guidance | Mid-course updates every `TORP_MIDCOURSE_UPDATE_S = 0.5 s`; stale at 3 s; broken at 12 s | `torpedo.py:51-53,115-137` |
| Serpentine search | Sine-wave offset (±15°) around mid-course heading | `torpedo.py:219-225` |
| Terminal homing | Within `TORP_HOME_RANGE_NM = 1.2` NM; seeker evaluates candidates; 15°/s turn | `torpedo.py:49,189,212-215` |
| Depth control | Proportional rate-limited: `DEPTH_RATE_M_PER_S = 10 m/s` | `torpedo.py:50,231-235` |
| Kill criteria | Swept distance ≤ `kill_dist_nm` AND depth within ±`kill_depth_m` | `torpedo.py:47-48,288-313` |
| Terrain avoidance | `underwater_path_blocked()` — 64-sample sweep against land/bathymetry | `torpedo.py:20-39` |
| Throttle on turn | Speed ×0.6 when |Δcourse| > 60°; gradual reduction 30-60° | `torpedo.py:243-248` |
| Decoy interaction | Decoys are seeker candidates; torpedo "hits" decoy → SASE | `torpedo.py:139-161` |
| Enemy torpedo | 6°/s turn, 3 NM seeker range, no wire | `torpedo.py:388-436` |
| ASROC delivery | Ballistic transit to datum, then torpedo spawns at water entry | `asw.py:521-583` |

### 4.2 Gaps and simplifications

| Gap | Current behaviour | Would need |
|-----|-------------------|------------|
| ~~**No launch dynamics**~~ | **Closed (Phases W2 + 6 + 8).** Spool-up, launch-depth offset and tube transient on the firing boat, speed-dependent turning and depth response right after launch. | — |
| ~~**No acceleration phase**~~ | **Closed.** Spool-up (W2) plus an energy store: power ~ v^3, range emerges from the battery and grows when running slower. | — |
| ~~**No depth inertia**~~ | **Closed (Phase 8).** Fin-limited vertical acceleration (~ dynamic pressure) with a proportional depth command (saved rate, small overshoot); hostile torpedoes now have depth control too (run depth, keel depth when homing). | — |
| ~~**No hydrodynamic turn limit**~~ | **Closed (Phase 8).** Constant turning radius: turn rate proportional to speed, for both torpedo classes. | — |
| ~~**No wire dynamics**~~ | **Closed (Phase 8).** Two finite spools (torpedo 1.25 x range, ship 5 NM of own track) and tension breaks from ship overspeed (> 20 kn) or hard turns (> 1.5 deg/s) held for 5 s; the old timers remain as datalink latency. | — |
| ~~**No propeller noise model**~~ | **Closed (Phase 8).** Speed-dependent propulsor lines (both classes) and a 60 log v source level; the target hears a running torpedo through the passive sonar equation (ray excess, ambient, own noise). | — |
| ~~**Kill is binary**~~ | **Closed (Phase 8).** Proximity fuze at closest approach; damage from the shock factor sqrt(W)/R (250 kg), so near misses damage without sinking. | — |
| ~~**No target reaction to torpedo**~~ | **Closed (Phases W2 + 7 + 8).** Launch-transient and homing alerts, crew recognition delay (per-boat lognormal 2-15 s, saved countdown), evasive dive across the layer; Phase 8 makes the running-torpedo notice a sonar-equation detection. | — |
| ~~**No self-destruction timing**~~ | **Closed (Phase 8).** Battery exhaustion stops the motor; the weapon coasts (dv/dt = -k v^2) and is lost below 30 % speed. | — |
| ~~**No wake / trail signature**~~ | **Closed (Phase 8).** Shallow hostile torpedoes leave a bubble track visible to the lookout by day up to 1.5 NM; hostile torpedoes can home on the own-ship wake. | — |
| ~~**ASROC payload depth**~~ | **Closed (Phase 8).** The payload flies a helix search at its splash point while its depth controller descends to the search depth. | — |

### 4.3 Data structures touched

- `Torpedo.__init__`: add `launch_delay_s`, `accel_time_s`, `cruise_speed_kn`, `max_turn_rate_by_speed`
- `Torpedo.update()`: replace fixed turn/depth rates with physics
- `config.py`: `TORP_HOME_RANGE_NM`, `TORP_MIDCOURSE_UPDATE_S` already exist; add `TORP_ACCEL_S`, `TORP_WIRE_MAX_NM`
- `data/contacts/torpedoes.json`: add `accel_time_s`, `wire_max_nm`, `cavitation_kn`

---

## 5. Decoys — `src/enemies/decoy.py` + `src/weapons/asw.py` (TowedAcousticDecoy)

### 5.1 What is currently modeled

| Aspect | Implementation |
|--------|---------------|
| Free-drift decoy (enemy sub) | Constant speed from catalog, random course, lifetime from catalog; LOFAR lines from profile; quiet factor 0.15 |
| Towed decoy (Nixie, own ship) | Tethered behind ship at fixed `tether_nm`; depth fixed; lifetime from loadout; `TowedAcousticDecoy.update()` just tracks position + life |
| Decoy as torpedo target | Decoys are in `seeker_candidates` list; torpedo "hits" decoy → SASE (no damage) |

### 5.2 Gaps and simplifications

- No self-noise model (decoys are "loud" with fixed quiet factor)
- No towed-decoy cable dynamics (drag, sway, depth variation)
- No frequency/content modulation of decoy signal
- No decoy effectiveness model (why does it fool the torpedo? just proximity + being a candidate)
- No multiple-decoy confusion logic

---

## 6. Air — `src/air/`

### 6.1 What is currently modeled

| Entity | Model | Ref |
|--------|-------|-----|
| **Flight** (civil/military) | Waypoint transit or loiter; 2°/s turn; ESM sensing; AIS (civil) | `flights.py:113-172` |
| **Raider** (attack plane) | 3-phase FSM: APPROACH → ATTACK (tangential stand-off) → RETREAT; fires ASM salvo; fixed altitude; 4°/s turn | `raid.py:75-117` |
| **ASM** (missile) | Sea-skimming; homing on frigate with 12°/s turn; optional jammer (burn-through at `jam_break_nm`); chaff vulnerability; terminal-active radar seeker (silent until `seeker_active_range_nm`, then feeds ESM independently of the HOJ path) | `asm.py:75-113` |
| **ESSM** (SAM) | Homing on observed ASM track; seeker activates within `seeker_range_nm`; 12°/s turn; no boost phase | `asm.py:138-182` |
| **Helicopter** | Fixed speed 120 kn; fuel timer; dipping sonar (deploy/retrieve, depth control); sonobuoy drop; torpedo release; weather-gated launch/dip | `helicopter.py:59-272` |
| **Sonobuoy** | Static position, battery life, passive sonar sensor | `sonobuoy.py:6-19` |

### 6.2 Gaps and simplifications

| Gap | Current behaviour | Would need |
|-----|-------------------|------------|
| **No flight dynamics** | Fixed altitude, constant speed, rate-limited turn | Climb/dive rate, speed- altitude coupling, turn rate vs speed, engine-out |
| ~~**No radar horizon**~~ | **Fixed (2026-09) for airframes.** Raiders already used `radar_horizon_nm()`; regular civil/military `flights` now use it too (flat `FLIGHT_RADAR_ALTITUDE_M`). **Still open for the ASM body itself** (see below): its own search-radar detection in `game.py._update_air_picture` uses flat `air_eff` with no altitude/horizon term, so a sea-skimmer is currently seen by search radar at the same range as a 60 m-altitude aircraft. | — |
| **No ASM boost phase** | ASM flies at constant speed from launch | Boost motor (first seconds), then cruise; speed affects intercept geometry |
| **No seeker physics** | ESSM/ASM homing itself is a range gate + turn-rate limit (unchanged) | Seeker FOV, lock-on delay, jamming resistance (burn-through is binary) |
| ~~**No ESM warning for inbound ASM**~~ | **Fixed (2026-09).** ASM `seeker_active()` stays silent mid-course (INS-only) and radiates once inside `seeker_active_range_nm` (18 NM); the seeker's own fingerprint (9.0-9.5 GHz, pulse-Doppler) feeds `_update_esm_picture` as a distinct RWR track, independent of the existing HOJ/jammer path (`asm.py`, `game.py._asm_seeker_emitter`). Not yet catalogued for classification in `data/contacts/*` emitters, so `rank_emitters()` won't positively ID it as "missile" — an intentional ambiguity, but worth revisiting. | — |
| **ASM body ignores radar horizon** | Regular (non-jamming) radar detection of the missile airframe uses flat `air_eff` range (`game.py:3141`), unlike raiders/warships/civilians/flights which all use `radar_horizon_nm()` | Give ASM a low `altitude_m` (~10-20 m) and route its radar branch through the same horizon formula, so search radar only picks it up very late, consistent with the new ESM early warning |
| **Raider has no attack-altitude profile** | `altitude_m` is a fixed profile constant across APPROACH/ATTACK/RETREAT | Brief pop-up (e.g. 60 m → few hundred m) during ATTACK for target acquisition before missile release, then back down; ties into `radar_horizon_nm()` (a visible radar "spike") and could feed a raider fire-control-radar ESM emission during the pop-up window |
| **No CIWS physics** | CIWS is a probability roll per cycle with range falloff | Gun barrel elevation/traverse rate; radar-illuminated tracking; round-in-air time |
| **No chaff physics** | Chaff is a timer (`chaff_left`); ASM goes straight or breaks | Chaff cloud drift, radar reflectivity, seeker discrimination |
| **No ECM on own ship** | Only chaff (soft-kill) and CIWS/ESSM (hard-kill) | Radar jamming, GPS spoofing (less relevant 1970s but modern) |
| **Helicopter: no hover dynamics** | Hovering = zero motion; no wind drift | Wind drift, rotor downwash, fuel consumption in hover |
| **Sonobuoy: no drift** | Fixed position after deployment | Current drift; battery decay already present |
| **No air-to-air threat** | Only ASM + raiders; no friendly CAP, no air-to-air | Out of scope for U-Jagd but noted |

### 6.3 Data structures touched

- `ASM.__init__`: seeker activation range done (`seeker_active_range_nm`); still add `altitude_m` for its own radar-horizon detection (distinct from the seeker's ESM range), `boost_phase_s`
- `Raider.__init__`: add `climb_rate_m_s`, `min_altitude_m`, `max_altitude_m` for an attack pop-up
- `Helicopter`: add `wind_drift`, `hover_fuel_rate`, `dip_sonar_dynamics`
- `config.py`: add `ASM_BOOST_S`, `CIWS_TURN_RATE`, `RAIDER_CLIMB_RATE`

---

## 7. Sonar & Propagation — `src/sonar/sonar.py` + `src/sonar/propagation.py` + `src/audio/receiver.py`

### 7.1 What is currently modeled

| Aspect | Implementation | Ref |
|--------|---------------|-----|
| **Passive detection** | `SNR = 20·log10(R_eff / d)`; detect if SNR ≥ 0 dB; quality = SNR / 14 dB | `sonar.py:30-33, 895-902` |
| **R_eff computation** | Base 20 NM × own-noise penalty × target-noise bonus × sea-state × array factor × towed bonus × propagation factor | `sonar.py:726-775` |
| **Own-ship noise** | `noise_level()` from speed + cavitation; isotropic + directional lobe (Gaussian, 70° FWHM) | `ship.py:205-212`, `sonar.py:748-754` |
| **Bearing error** | Base 6° (bow) / 2° (towed) × speed factor × quality factor; smooth correlated noise | `sonar.py:36-41, 1263-1270` |
| **Active ping** | Echo delay = 2d/c; range + depth with ±0.18 NM / ±12 m error; 30 s cooldown | `sonar.py:672-715, 1178-1261` |
| **TMA** | Grid search over (course: 0-360°/15°, speed: 0-18 kn/2 kn) + local refinement; IRLS 2-pass; observability gate | `tma.py:157-213` |
| **Towed array** | Deploy/retrieve cycles; speed window 3-12 kn; depth 20-260 m; heading lag; fault on overspeed | `sonar.py:450-504, 1107-1128` |
| **Bouys** | 5 buoys; 8 NM range; cross-bearing fix; battery 1 h; thermocline penalty | `sonar.py:988-1039`, `config.py:321-324` |
| **Dipping sonar** | Bearing-only from helo; 18 NM passive / 14 NM active; 30 s ping cooldown | `sonar.py:777-831`, `config.py:317-320` |
| **Propagation** | 4 paths (direct/refracted/surface/bottom); spherical spreading + absorption per band; layer-crossing penalty; CZ bonus; terrain block | `propagation.py:146-235` |
| **Sound speed profile** | Synthetic 21-point profile; `c(d) = 1504 - 0.018·min(d,thermo) + 0.012·max(0,d-thermo)` | `propagation.py:106-111` |
| **LOFAR / DEMON** | FFT-based waterfall; DEMON envelope analysis; blade-count hypotheses; signature ranking | `receiver.py:491-557`, `sonar.py:1140-1149` |
| **Array fusion** | Bow + towed: confirmed / uncertain / divergent; weighted bearing combine | `sonar.py:928-957` |
| **Contact decay** | Confidence decays at `SONAR_CONF_DECAY_PER_S = 0.003/s`; lost after 120 s + conf < 0.15 | `sonar.py:369-378` |

### 7.2 Gaps and simplifications

| Gap | Current behaviour | Would need |
|-----|-------------------|------------|
| ~~**No full sonar equation**~~ | **Closed (Phase 3).** `src/sonar/equation.py`: passive SE = SL - TL - NL + DI - DT per band; active SE = SL - 2TL + TS - max(NL - PG, RL - Doppler rejection). Calibrated so 1.0.0 detection ranges hold (`tools/calibrate.py`). Own sonar, dipping sonar and NPC platform sonars use it. | — |
| ~~**No source-level model**~~ | **Closed (Phase 3; speed/cavitation terms Phase 6).** Source level in dB from the catalog quietness; NPC passive sonars hear loud targets farther (up to +5 dB). | — |
| ~~**No receiver noise model**~~ | **Closed (Phase 3).** Wenz/Knudsen wind noise (flat below 500 Hz), distant shipping from nearby merchant count, heavy-rain noise, thermal floor, hull-array self-noise floor plus speed/cavitation self noise, own wake astern; NPC receiver sensitivity from the catalog. | — |
| ~~**No target strength (TS)**~~ | **Closed (Phase 3).** Aspect- and length-dependent target strength (beam highlight ~20 log(L/10)+8 dB, bow/stern 15 dB lower). | — |
| ~~**Propagation: fixed 4 paths**~~ | **Closed (Phase 4).** `src/sonar/raytrace.py`: 48-ray Snell fan through the Mackenzie profile (turning points, surface duct, shadow zone, convergence where deep enough), rough-surface and lossy Rayleigh bottom reflections, incoherent flux summation into TL(range, depth) tables per band; pure functions of a quantized environment key with a bounded LRU cache (purity keeps save/load deterministic). Own, dipping and NPC passive sonars use it via reciprocity (sensor = source). | — |
| ~~**Propagation: no frequency dependence in path loss**~~ | **Closed (Phases 3-4).** Francois-Garrison absorption per band; boundary losses (surface roughness k-dependence) per band in the ray tables. | — |
| ~~**No Doppler**~~ | **Closed (Phase 5).** Tonal lines in LOFAR/audio are Doppler shifted by the closing speed; the strongest tonal is measured per bearing point (SNR-dependent error) and saved; TMA estimates the unshifted f0 and uses Doppler for observability. | — |
| ~~**No interference / clutter**~~ | **Closed (Phase 3).** Boundary (Lambert bottom by sediment, wind-dependent surface) and volume reverberation with absorption; CW Doppler rejection grows with radial speed; charted wrecks return unassociated echoes (saved pending clutter). | — |
| ~~**Ping: no pulse parameters**~~ | **Closed (Phase 3).** Selectable CW (1 s) / LFM (1 s, 100 Hz) pulse (`W`, saved): resolution c*tau/2 or c/2B, Cramer-Rao range accuracy, LFM processing gain against noise, CW Doppler against reverberation. | — |
| ~~**TMA: fixed grid**~~ | **Closed (Phase 5).** Grid seed plus Levenberg-Marquardt refinement over position/velocity (+f0 with Doppler), accepted where observable; 1-sigma covariance ellipse published and saved; range sigma never more optimistic than the observability heuristic. | — |
| ~~**No multi-static sonar**~~ | **Closed (Phase 5).** Sonobuoy (sonar-equation) and dipping bearings enter the contact's bearing track with their own observer positions, so one estimator fuses own-ship, buoy and helicopter geometry. | — |
| ~~**No sonar array beamforming**~~ | **Closed (Phase 5).** Uniform-aperture sinc beam pattern with -13 dB side lobes in the receiver/broadband scan, towed-array endfire broadening (1/sqrt(sin)), and the towed line array's left/right ambiguity (mirror bearing, excluded from TMA until an own turn or the hull array resolves it). | — |

### 7.3 Data structures / interfaces touched

- `SonarSystem._passive_range_nm()`: replace scalar R_eff with frequency-dependent SL/TL/NL/DT
- `propagation.propagate()`: add frequency parameter (currently fixed 100 Hz for passive); add reverberation; add clutter
- `Contact`: add `ts_db` (target strength), `sl_db` (source level), `snr_db` (per frequency band)
- `config.py`: add `SOUND_SPEED_M_S` already exists; add `TL_SPHERICAL_REF`, `NL_SEA_STATE_TABLE`, `TS_DEFAULT`
- `data/contacts/acoustics.json`: extend `TargetSignature` with per-band source level, target strength
- `sensors/platform.py`: `SensorProfile.sensitivity_db` is currently unused in the passive path; wire it into the sonar equation

---

## 8. Radar / ESM / HFDF — `src/sensors/esm.py`, `src/sensors/tracks.py`, `src/core/game.py`

### 8.1 What is currently modeled

| Sensor | Model | Ref |
|--------|-------|-----|
| **Surface radar** | Range 30 NM (nominal) × weather × rain; bearing ±0.8°; range ±1.5%; RCS aspect factor; terrain occlusion; 0.5 s epoch | `game.py:2949-2981`, `config.py:133-134,254-269` |
| **Air radar** | Range 100 NM; same model; 0.5 s epoch | `game.py:3004-3040` |
| **ESM** | Range 150 NM; bearing ±3°; frequency/PRF/modulation fingerprint; emitter ranking; 300 s operator memory with quality decay and stable association across intermittent radar duty cycles; terrain occlusion | `esm.py`, `game.py` |
| **HFDF** | Range 120 NM; bearing ±8°; cross-bearing fix with covariance; 0.5 s cadence | `game.py:3678-3794` |
| **Lookout (visual)** | Surface 12 NM, sub 5 NM (only if <2 m depth), air 20 NM; night ×0.35; sea state loss; weather visibility cap | `game.py:2888-2947`, `config.py:160-170` |
| **Track fusion (OPZ)** | Bounded picture (512 air, 64 ESM); smoothing (exponential, per-source τ); correlation gating; manual fusion; classification/affiliation | `tracks.py`, `fusion.py`, `game.py:3086-3111` |
| **Weather effects** | Sea state 0-6; wind; rain; fog; visibility; all modulate radar/lookout/range | `world.py:44-142` |

### 8.2 Gaps and simplifications

| Gap | Current behaviour | Would need |
|-----|-------------------|------------|
| **No radar equation** | Detection = distance < range × aspect; no radar cross-section vs range, no pulse parameters, no clutter | Radar range equation: `R_max = (P_t·G²·λ²·σ)/(P_min·(4π)³·k·T·B)`; clutter rejection; sea-spike, ground-clutter |
| **No scan rate / PPI dynamics** | Tracks appear/disappear per 0.5 s epoch; no sweep angle | Radar sweep: contacts only visible when beam sweeps past; afterglow decay; PPI refresh |
| **No ECCM / jamming effect on radar** | Jamming only produces a HOJ bearing (bearing-only, no range) | Radar jamming: range-gate pull-off, angle deception, burn-through; radar self-protection |
| **ESM: no signal strength** | Detection is binary (in range or not); no amplitude | Signal level vs distance; frequency-agile waveform detection; dwell time |
| **HFDF: no frequency** | Only bearing; no frequency measurement | HF frequency → rough distance via ionospheric model; or at least frequency for emitter ID |
| ~~**No AIS decoding**~~ | **Closed (Phase 0).** `src/sensors/ais.py` is a simulated own-ship AIS receiver: ITU-R M.1371 class-A dynamic reports (COG/SOG every 2-10 s, 3 min at anchor) and static reports (name every 6 min), received only inside VHF line of sight and not through land. Radar observations of civilians no longer carry the true name/course (an observation-boundary leak); both come from the latest decoded report. MMSI is deliberately not shown to the player, so live and simulated traffic stay indistinguishable. Decoded reports are saved (save v12). | — |
| **Lookout: no silhouette / size** | Visual detection is a range gate; no target size effect | Target height, silhouette against sea/sky; searchlight; smoke |

### 8.3 Data structures touched

- `config.py`: add radar power, antenna gain, pulse width, PRF; ESM sensitivity; HFDF frequency bands
- `game._update_air_picture()`: integrate radar equation, clutter, scan dynamics
- `sensors/esm.py`: add signal-level gating
- `sensors/tracks.py`: add scan-phase to track age

---

## 9. Damage Model — `src/ship/damage.py`

### 9.1 What is currently modeled

- 9 compartments: bridge, sonar, weapons, OPZ, radio, engine, flightdeck, hull L/R
- Torpedo hit: 1–2 compartments randomly selected (weighted by hit zone); 10-30% initial flood; 35% chance of fire start
- Flooding: 0.10%/s (flooded) or 0.025%/s (damaged); repair 0.12%/s per team
- Fire: 0.08%/s growth; 0.14%/s per team extinguish; 0.02%/s spread to adjacent; 35% start chance on hit; kill at 100%
- Compartment destroyed at 70% flood or 100% fire
- Ship sinks at 540% total flood (60% avg over 9 compartments)
- Grounding: impact energy → localized flooding (deterministic, no RNG)
- 3 repair teams; cycle or assign

### 9.2 Gaps and simplifications

| Gap | Current behaviour | Would need |
|-----|-------------------|------------|
| **No hit-location physics** | Torpedo zone (bow/stern/port/starboard/center) from approach bearing; random within zone | Torpedo impact point on hull → specific compartment; warhead burst → localised damage |
| **No flooding dynamics** | Compartment flood % changes linearly; no free-flood, no list, no change in centre of gravity | Compartment interconnection; free-flood moment of inertia; list → affects sonar, radar, helicopter ops |
| **No fire propagation physics** | Fire spreads to adjacent with fixed probability per second | Compartment fire based on material, fuel type; water ingress suppresses fire; electrical fire |
| **No systems degradation** | Station is binary: OK → DEGRADED → DOWN | Gradual performance loss: sonar sensitivity ↓, radar range ↓, engine power ↓, comm range ↓ |
| **No damage repair realism** | Repair rate is constant; no consumables, no time-to-repair estimate | Repair teams need time to travel; materials limited; some damage irreparable |
| **No secondary damage** | Only flooding + fire | Structural failure, magazine detonation, electrical short-circuit cascade |
| **Torpedo damage to subs** | `Sub.hit()`: +60-100% damage; at 100% → SINKING (20 s) | Compartment damage on sub; loss of specific systems; emergency blow; controlled sink |

---

## 10. World / Environment — `src/world/`

### 10.1 What is currently modeled

| Aspect | Implementation |
|--------|---------------|
| Bathymetry | 12×12 grid (procedural) or real-sector (loaded from gz); bilinear interpolation |
| Thermocline | Per-cell depth (40-120 m procedural); affects sonar layer detection |
| Coastline | Polygon landmasses; `on_land()`, `land_blocks_line()`, `sonar_path_blocked()` (straight-ray terrain test) |
| Weather | Sea state 0-6 (±1 random walk every hour); wind (direction/speed); rain (0-1); fog; visibility; blended over 600 s transition |
| Day/night | 24-h cycle; `is_night()` at 19:30-05:30; affects lookout |
| Sound speed | Synthetic profile (1504 m/s base); echo delay = 2d/1500 |

### 10.2 Gaps and simplifications

| Gap | Current behaviour | Would need |
|-----|-------------------|------------|
| ~~**No ocean currents**~~ | **Closed.** Static seeded current field (`World.current_vec`) applied to ship, subs, surface ships, torpedoes and decoys; Phase 1 adds the wind-driven component. | — |
| ~~**No tides**~~ | **Closed (Phase 1).** `src/world/ocean.py`: M2 + S2 constituents, seeded amplitude/phase and a spatial phase gradient, Green's-law shoaling. `World.depth_m`/`physical_depth_m` = chart datum + tide, so grounding and sub safe depth follow the tide. | — |
| ~~**No thermocline dynamics**~~ | **Closed (Phase 1).** Mixed-layer depth = seasonal cell base + diurnal heating (-8 m at 15:00, zero 24-h mean) + wind-mixing deepening (saved first-order relaxation, fast deepening / slow restratification) + three internal-wave components. | — |
| ~~**No wind/current interaction**~~ | **Closed (Phase 1).** 3 % of wind speed, deflected 20 deg to the right of downwind, added to `current_vec`. | — |
| ~~**No seasonal / diurnal sound-speed variation**~~ | **Closed (Phase 1).** Seeded season, SST with seasonal and diurnal terms, exponential thermocline temperature profile and the Mackenzie (1981) equation. Used by the bathythermograph and ping echo latency; the ray tracer (Phase 4) samples the same profile. | — |
| ~~**Seabed composition**~~ | **Closed (Phase 1 model).** Seeded 12x12 sediment grid (rock/gravel/sand/silt/mud) from depth and slope with Hamilton-style geoacoustic parameters and a Rayleigh fluid-fluid bottom-loss function; consumed by the sonar equation (Phase 3) and ray tracer (Phase 4). | — |
| ~~**No underwater geography beyond depth**~~ | **Closed (Phase 1 model).** Up to 64 seeded wrecks and submerged rocks. Rocks shoal `depth_m` (tops at least 15 m, a hazard to submarines and weapons, never to surface keels); wrecks become active-sonar clutter in Phase 3. | — |

---

## 11. Summary of Key Abstractions to Extend

For a "reale Simulation" upgrade, the following core interfaces would need to grow:

1. **`Ship.update()`** — from kinematic to dynamic (force-based speed/turn)
2. **`Sub.update()`** — add depth dynamics, current drift, cavitation state
3. **`Torpedo.update()`** — add launch transient, depth control loop, wire length limit, speed-dependent turn
4. **`SonarSystem._passive_range_nm()`** — replace scalar R_eff with sonar equation (SL, TL, NL, DI, DT)
5. **`propagation.propagate()`** — extend from 4 fixed paths to N-ray; add frequency dependence
6. **`HydroacousticChannel`** — already has a basic TL model (spherical spreading + absorption + 25 dB layer cross); extend with bottom-loss, grazing-angle effects
7. **`DamageModel`** — from compartment-percentage to structural/stability model
8. **`World`** — add current field, time-varying thermocline, seabed type
9. **`config.py`** — many new physical constants (drag coefficients, radar parameters, sonar equation terms, current speeds)
10. **`data/contacts/*.json`** — extend `TargetSignature` with per-band SL/TS; extend `MachineProfile` with RPM curves, cavitation thresholds; extend `EnduranceProfile` with depth-dependent power

### Determinism invariants to preserve

All changes must maintain the rules in `AGENTS.md`:
- Same seed + world + input → same state (use local `random.Random`, stable hashes)
- No global `random`, no `time.time()`, no wall-clock in sim
- Save/load round-trip: all new state fields must be serialised, validated, and restored
- Observation boundary: AI/sensors must never read hidden ground-truth except through the sensor model
- `PHYS_SUBSTEP_S = 0.05 s` sub-stepping must remain the integrator cadence; any new ODE must be stable at 0.05 s
- Bounded work: all new loops/arrays must have hard caps (the codebase is meticulous about this)
