# Verification Log

This append-only ledger records historical verification against an exact commit
or working-tree description. `docs/resume.md` remains the current handoff; an old
green entry here is never evidence that a later dirty tree is green.

## 2026-09-07 Commander Baseline

- Revision: working tree later committed as `1a8e278`.
- Automated suite: 1648 passed in 278.28 seconds.
- Catalog: 106 acoustic profiles valid.
- Smoke: `SMOKE-OK` with SDL dummy drivers.
- Packaging: sdist and wheel 0.1.6 built; wheel installed outside the source tree.
- Integration: real loopback pairing, observation API and packaged web resources.
- Browser: headless Chromium desktop and narrow contracts.
- Not covered: physical two-device LAN, firewall, uConsole audio, thermal load and
  hardware readability.

## 2026-09-07 Audio Follow-up

- Revision: `1aae70d` plus its predecessor `fb7a6ce`.
- Automated suite: 1757 passed, 3 Commander desktop-layout assertions failed.
- Interpretation: not a green release result. The layout assertions were assigned
  to the subsequent 0.1.6 stabilization.
- Not covered: physical uConsole crackle/endurance acceptance.

## 2026-09-08 Stabilization, Focused Runs

- Revision: dirty working tree based on `1aae70d`; see `docs/resume.md`.
- Audio/receiver/sonar expanded subset: 393 passed.
- Audio core regression subset: 240 passed.
- Commander non-browser subset: 416 passed with 6 temporarily deselected during
  parallel audio repair.
- Commander layout: 20 passed.
- Commander browser assets: 6 passed.
- Navigation Chromium: 2 passed.
- `py_compile` and `git diff --check`: passed in focused work.
- Status: provisional until the combined and full verification commands complete.

## 2026-09-08 Stabilization, Full Software Acceptance

- Revision: dirty working tree based on `1aae70d`.
- Code/data/test patch SHA-256:
  `4f52d9dea37b97a3208ec729f9edbe6492f6f213286c9c000020e51bb11d64aa`.
- Combined subsystem run: 705 passed.
- Review follow-up subset: 512 passed.
- Full command: `.venv/bin/python -m pytest -q -p no:cacheprovider`.
- Full result: 1779 passed in 564.48 seconds.
- Catalog: 106 acoustic profiles valid.
- Smoke: `SMOKE-OK`.
- Packaging: sdist and wheel 0.1.6 built successfully.
- Isolated install: version, Commander resources and real loopback pairing passed
  as `WHEEL-LOOPBACK-OK`.
- Commander captures regenerated at 1920x1080 and 2560x1440.
- `git diff --check`: passed.

## 2026-09-08 0.1.7 R0-R2 Integration

- Revision: dirty working tree based on `ed4dcc7`.
- R1 input/Commander focused run: 80 passed.
- Save/runtime/Commander regression run: 297 passed.
- Commander assets and complete Chromium layout matrix: 38 passed.
- Full suite: 1817 passed in 421.37 seconds.
- Catalog: 106 acoustic profiles valid.
- Smoke: `SMOKE-OK`.
- `git diff --check`: passed.
- Commander screenshots regenerated at 1920x1080 and 2560x1440.

## 2026-09-08 0.1.7 R3 Catalog Foundation

- Revision: dirty working tree based on `ed4dcc7`.
- Catalog-v1/v2, provenance and packaging focus: 164 passed.
- Full suite: 1862 passed in 442.36 seconds.
- Catalog: 106 acoustic profiles valid; all packaged profile documents remain v1.
- Smoke: `SMOKE-OK`.
- `git diff --check`: passed.
- Not covered: physical uConsole audio/thermal/readability and physical two-device
  LAN/firewall acceptance.

## 2026-09-08 0.1.7 R4 Nine-Platform Pilot

- Revision: dirty working tree based on `ed4dcc7`; includes R0-R4 and the earlier
  uncommitted 0.1.6 stabilization.
- Catalog/provenance/tool focus: 167 passed.
- Save snapshot, historical migration and continuation focus: 220 passed.
- Full suite: 1878 passed in 505.26 seconds.
- Catalog: 115 runtime profiles and 109 acoustic profiles valid; complete
  provenance coverage enforced by the CLI checker.
- Save v9: bounded, strict runtime catalog snapshot; snapshotless v1-v9 migration
  retained; changed-package split-run passed.
- Smoke: `SMOKE-OK`.
- `git diff --check`: passed.
- Not covered: physical uConsole audio/thermal/readability and physical two-device
  LAN/firewall acceptance.

## 2026-09-08 0.1.7 R5 Platform And Sensor Foundation

- Revision: dirty working tree based on `ed4dcc7`; includes R0-R5 and the earlier
  uncommitted 0.1.6 stabilization.
- Platform/save/determinism/observation focus: 364 passed.
- Full suite: 1907 passed in 449.97 seconds.
- Catalog: 115 runtime profiles and 109 acoustic profiles valid.
- Save v9: catalog snapshot v2 plus platform-state v1; snapshot-v1 and
  snapshotless historical migration retained; malformed state rejected before
  candidate commit.
- Runtime: mission-owned side/doctrine, nine pilot machine/acoustic profiles,
  independent bounded Radar/ESM/Sonar/AIS controllers, observation-only friendly
  datalink, damage/EMCON gating, and observation-based legacy AI release.
- Smoke: `SMOKE-OK`.
- `git diff --check`: passed.
- Not covered: physical uConsole audio/thermal/readability and physical two-device
  LAN/firewall acceptance.

## 2026-09-08 0.1.7 R6 Bridge Lookout

- Revision: dirty working tree based on `ed4dcc7`; includes R0-R6 and the earlier
  uncommitted 0.1.6 stabilization.
- Commander/i18n focus including Chromium and layout: 510 passed.
- Browser contract: 6 passed, including four primary Chromium widths.
- Dense EN/DE desktop/mobile/200-percent matrix: 20 passed.
- Short landscape and 400-percent reflow matrix: 6 passed.
- Full suite: 1917 passed in 480.64 seconds.
- Snapshot: additive protocol-1 environment with sea state and authoritative
  day/night; status-only phases publish null environment values.
- Lookout: snapshot-only north-up geometry, independent local range, positioned
  points, bearing edge marks, accessible text equivalent, bounded/released canvas
  backing stores, active resize and direct-disconnect clearing.
- Catalog: 115 runtime profiles and 109 acoustic profiles valid.
- Smoke: `SMOKE-OK`.
- `git diff --check`: passed; final independent review reported no findings.
- Not covered: physical uConsole audio/thermal/readability, physical browser and
  two-device LAN/firewall acceptance.

## 2026-09-09 0.1.7 R7 ELOKA / ESM

- Revision: dirty working tree based on `ed4dcc7`; includes R0-R7 and the earlier
  uncommitted 0.1.6 stabilization.
- Focused sensor/save/Commander/UI matrix: 785 passed.
- Full suite: 1945 passed in 529.51 seconds.
- Runtime: separate 64-track passive ESM picture, opaque monotonic intercept keys,
  observed bearing/error/frequency/PRF/modulation/quality/age, deterministic
  measurement-only association and catalog candidate ranking.
- Observation boundary: parallel radar/ESM evidence; radar/sonar correlation uses
  only time, bearing and observed position, with no entity ID, object reference or
  true emitter key in the ESM picture.
- Station: ninth canonical `ELOKA` enum member, key 9 and Tab traversal, EN/DE
  workstation/help/tooltips, manual radar-type annotation, and OPZ-damage gating
  without another compartment.
- Save v9: internally versioned ESM picture/selection/annotation/scheduler state;
  v1-v8 and pre-R7 v9 default empty; malformed state is transactionally rejected.
- Bounds: 64 ESM tracks, 256 annotations, 512 common correlation tracks, and
  `FlightManager.MAX_FLIGHTS` enforced during save validation.
- Catalog: 115 runtime profiles and 109 acoustic profiles valid.
- Smoke: `SMOKE-OK`, including draw over all nine stations and overlays.
- Build: 0.1.7 sdist and wheel succeeded; the new ESM sensor module is packaged.
- `git diff --check`: passed; final independent review reported no findings.
- New deterministic ELOKA workstation and overview screenshots inspected at
  1280x720.
- Not covered: physical uConsole audio/thermal/readability and physical two-device
  LAN/firewall acceptance.

## 2026-09-09 0.1.7 R8 ASW And Save-v10 Acceptance

- Revision: dirty working tree based on `ed4dcc7`; includes R0-R8 and the earlier
  uncommitted 0.1.6 stabilization.
- Full suite: 1927 passed in 528.76 seconds.
- Runtime: typed finite magazines, tubes and reload, ASROC, helicopter and
  submarine torpedoes, Nixie and reactive submarine decoys, bounded launch
  queues, and a dedicated persisted ASW RNG stream.
- Observation boundary: datum guidance uses detached observations until terminal
  seeker acquisition; platform and weapon provenance survive pending and live
  weapon phases without public entity references.
- Save v10: exact root and nested schemas, mandatory current catalog/platform/
  ESM/ASW/RNG state, canonical restore-to-serialize equality, and transactional
  rejection of v1-v9, future, incomplete and malformed documents.
- Regression: sonar contact ID high-water marks, store/provenance accounting,
  helicopter launch origin, OPZ affiliation vocabulary, and canonical expired
  ping timers are covered.
- Catalog: 115 runtime profiles and 109 acoustic profiles valid.
- Smoke: `SMOKE-OK`, including v10 slot save/load and all nine stations.
- Build: 0.1.7 sdist and wheel succeeded.
- `git diff --check`: passed.
- Not covered: physical uConsole audio/performance/thermal/readability and
  physical two-device LAN/firewall acceptance.

## 2026-09-10 0.1.7 R12 Guide And R13 Integration Checkpoint

- Revision: uncommitted R9-R13 working tree on `7d52faf`; no push performed.
- Guide: eight semantic sections and 42 exact-parity EN/DE strings cover the
  implemented Commander workflow and explicit remote-authority exclusions.
- Security/layout: `textContent`/`data-i18n` only, no command coupling, panel-local
  guide navigation, and responsive EN/DE browser acceptance.
- Focused Commander matrix: 521 passed; final guide/layout/i18n run: 64 passed.
- Full suite: 2111 passed in 640.94 seconds.
- Catalog checks: 109 acoustic profiles and 232 deterministic PNG assets valid.
- Smoke: `SMOKE-OK`.
- Build/install: 0.1.7 sdist and wheel succeeded; tests verify exact resources,
  hashes, notices, isolated wheel import, static analyzer loading and loopback
  Commander startup.
- Save v10, browser, loopback, source/provenance and license contracts passed as
  part of the full and focused matrices. No third-party image was introduced.
- `git diff --check`: passed.
- Not covered: physical uConsole audio/frame-time/thermal/readability and
  physical two-device LAN/firewall acceptance.

## 2026-09-10 0.1.7 R14 Sonar Audition And Fix Publication

- Revision: uncommitted R9-R14 working tree on `7d52faf`; no push performed.
- Focused audio/fix/save/Commander matrix: 635 passed; map/performance regression
  run: 41 passed.
- Full suite: 2124 passed in 628.08 seconds.
- Audio: broadband, filtered and whole-beam heterodyne modes; durable availability,
  gain, band, notch, volume and accelerated-mute status; sequence-idempotent
  block-continuous transitions without simulation or RNG coupling.
- Fixes: independent PING/TMA/SONOBUOY records with measurement/publication ages,
  uncertainty and bounded simulation-time expiry independent of rendering.
- Bridge/Commander: all valid detached fixes, shared visible draw/hit geometry,
  parent opaque Commander identity and no stale clickable markers.
- Persistence: strict v10 audition/fix state and narrowly recognized exact R13-v10
  file shape; malformed current documents remain transactionally rejected.
- Review fixes: removed half-block OLA dropout, retained delayed TMA publication
  time and aligned hit targets with uncertainty rings.
- Catalog/image checks, `SMOKE-OK`, sdist/wheel build and `git diff --check` passed.
- Not covered: physical 1x headphone/speaker quality and uConsole acceptance.

## 2026-09-10 0.1.7 R15 Sonar Layout And Input Acceptance

- Revision: uncommitted R9-R15 working tree on `7d52faf`; no push performed.
- R15 visual/state matrix: 72 passed; focused review-fix matrix: 146 passed;
  broad sonar/input/layout matrix: 446 passed.
- Full suite: 2199 passed in 605.26 seconds.
- Layout: six distinct pages, 862x386 main panel, at least three contact rows,
  compact LOFAR spectrum/waterfall and large DEMON evidence plot.
- Semantics: measured lines remain evidence; harmonics require explicit transient
  operator selection; DEMON RPM/blade and max-three catalog candidates expose no
  entity or fingerprint truth.
- Input: shared painted draw/hit rectangles, inert margins/gaps, safe footer
  actions only, keyboard parity and 1280x800 letterbox rejection.
- Localization: permanent page-specific source/evidence age/state and structured
  two-line footer pass EN/DE, large text and pseudolocale containment.
- Catalog/image checks, `SMOKE-OK`, build and `git diff --check` passed.
- Not covered: physical 1280x720 contrast/readability and trackball acceptance.

## 2026-09-10 Analyzer Spectrum Review Follow-up

- Revision: uncommitted 0.1.7 working tree; no push performed.
- Focused analyzer/UI/Commander/assets/browser/layout/i18n/packaging matrix:
  293 passed in 212.29 seconds, including Chromium reflow and isolated
  wheel/sdist resource checks.
- Images: exactly 226 deterministic font-free 320x180 PNGs. The fixed
  logarithmic axis is 5 Hz-10 kHz; catalog tonals use separate bounded,
  max-composed peaks and broadband uses only its supplied plateau interval.
- Hypotheses: the 0-80 Hz shaft-rate/optional-BPF strip is explicitly synthetic,
  profile-wide and not a recording or measurement. It is populated only on the
  Cruise reference image and no missing value is inferred.
- Both generator checks passed: 109 acoustic profiles and 226 analyzer PNGs.
  Manifest hashes/routes, EN/DE parity and `git diff --check` passed.
- The historical R11 ledger below is retained unchanged. Its silhouette result
  is superseded by the active 226-asset no-silhouette contract.
- Not covered: physical uConsole readability/performance and physical
  two-device LAN/firewall acceptance; zlib reproducibility across runtimes.

## 2026-09-10 0.1.7 R11 Contact Database And Tactical Unit Analyzer

- Revision: uncommitted R9-R11 working tree on `7d52faf`; no push performed.
- Focused R11/Commander/browser/layout acceptance: 341 passed; all 38 dedicated
  EN/DE, zoom and viewport layout cases passed after review fixes.
- Full suite: 2109 passed in 690.89 seconds.
- Projection: 115 detached bounded profiles shared by game and Commander, with
  no live entities, observation coupling, source URLs or request-derived paths.
- Images: 232 deterministic font-free PNGs; six dimension-based silhouettes and
  cruise/high plots only for 113 profiles with applicable machine acoustic data.
- Serving: 233 prebuilt exact routes, nested browser schema validation,
  textContent-only rendering and independent analyzer selection.
- Game UI: read-only analyzer under the existing administrative owner, bounded
  list/detail scrolling and a four-surface decoded-image cache.
- Security: traversal and symlink/non-regular-entry negatives passed; manifest,
  hashes, dimensions, counts and aggregate bytes are bounded and validated.
- Catalog/image checks, `SMOKE-OK`, sdist and wheel build all passed. Artifact
  tests verified exact assets in source, wheel, sdist and isolated install.

Superseding asset contract (2026-09-10): the R11 result above remains a
historical ledger entry. Hydroacoustic DSP follow-up removes all six silhouette
assets/routes and replaces the acoustic plots with 226 deterministic 320x180
composite spectral/DEMON diagrams (113 cruise and 113 high).
- `git diff --check`: passed; independent re-review found no production issue.
- Not covered: physical uConsole readability/performance and physical two-device
  LAN/firewall acceptance; zlib reproducibility across different runtimes.

## 2026-09-09 0.1.7 R9 Missile Defense Acceptance

- Revision: uncommitted R9 working tree on `7d52faf`; no push performed.
- Focused air-defense/save/continuation run: 200 passed.
- Full suite: 1953 passed in 464.25 seconds.
- Runtime: profile-driven ASM, SAM/ESSM, VLS, CIWS and finite chaff stores with
  separate loadout, capacity and fire-channel limits.
- Observation boundary: SAM, chaff and CIWS require fresh position timestamps;
  only the own `blue` friendly datalink group contributes detached fire-control
  tracks, and equal-time own radar takes precedence.
- Persistence: strict versioned air-defense state, launch/store reconciliation,
  canonical projectile headings and integrated deterministic continuation.
- Compatibility: file loading recognizes only the exact pre-R9 v10 root and
  projectile shapes; current in-memory documents still require every field.
- Catalog: 115 runtime profiles and 109 acoustic profiles valid.
- Smoke: `SMOKE-OK`.
- Build: 0.1.7 sdist and wheel succeeded with the new loadout and module.
- `git diff --check`: passed; final independent review found no functional issue.
- Residual risk: pre-R9 v10 coverage is structurally generated rather than stored
  as a large frozen fixture.
- Not covered: physical uConsole and two-device LAN acceptance.

## 2026-09-10 0.1.7 R10 Full Catalog Migration Acceptance

- Revision: uncommitted R9-R10 working tree on `7d52faf`; no push performed.
- Focused catalog/runtime/save/determinism matrix: 288 passed.
- Full suite: 2083 passed in 530.86 seconds.
- Catalog: all 115 profiles across eight resources use v2 component documents;
  all 109 acoustic profiles remain valid.
- Provenance: 350 field-level claims cover every attached component coordinate;
  the shared loader rejects missing and entirely empty manifests. Only strict
  runtime snapshots may omit source prose and URLs.
- Runtime: keys, ordering, spawn pools and adapters remain stable. Catalog-driven
  finite submarine decoys are the documented gameplay difference and use the
  persisted ASW RNG stream.
- Persistence: v10 snapshots reconstruct all migrated components canonically and
  remain runtime-only; package provenance is not copied into saves.
- Smoke: `SMOKE-OK`.
- Build: 0.1.7 sdist and wheel succeeded with all v2 contact resources and
  `sources.json` packaged.
- `git diff --check`: passed. Independent review found one empty-provenance bypass;
  it was fixed and covered by a regression test.
- Not covered: physical uConsole audio/performance/thermal/readability and
  physical two-device LAN/firewall acceptance.

## 2026-09-10 0.1.7 R16 Battery And AIP Endurance

- Revision: uncommitted R9-R16 working tree on `7d52faf`; no push performed.
- Final endurance/save/catalog/determinism/integration matrix: 326 passed.
- Full suite: 2260 passed in 712.16 seconds.
- Catalog: strict fictional `game_assumption` endurance components for all 12
  relevant non-nuclear submarine profiles; 109 acoustic profiles valid.
- Runtime: closed battery/AIP/generator/load accounting, reserve hysteresis,
  exact snorkel-depth gating, separate radio and descent phases, state-specific
  motion resumption, partition-stable threshold handling and a strict 1024-step
  bound.
- Persistence: mandatory canonical endurance state in save v10, recursively
  type-exact recognition of only the canonical pre-R16 v10 file shape, and
  legacy `SNOCKEL` continuation without an extra patrol RNG draw.
- Review: malformed numeric near-matches, legacy phase/RNG continuation,
  subsecond thresholds, residual descent time and loop bounds were reproduced,
  fixed and regression-tested; final independent reproduction found no issue.
- Smoke: `SMOKE-OK`.
- Build: 0.1.7 sdist and wheel succeeded.
- `git diff --check`: passed.
- Not covered: physical uConsole endurance/audio/performance/thermal/readability
  and physical two-device LAN/firewall acceptance.

## 2026-09-10 0.1.7 R17 Synthetic Acoustic Propagation

- Revision: uncommitted R9-R17 working tree on `7d52faf`; no push performed.
- Final propagation/save/sonar/platform matrix: 425 passed; ASW stub follow-up:
  203 passed.
- Full suite: 2293 passed in 624.76 seconds.
- Model: immutable shared 21-point synthetic sound-speed profile, four canonical
  bands, at most four stable paths and three segments per path, bounded 500 NM
  range, frequency loss, profile travel time, terrain clearance, synthetic CZ
  focusing and bounded reverberation.
- Integration: BT preserves its draw order and save shape; own and catalog
  passive sonar evaluate propagation only on existing sensor scan cadence.
- Boundaries: no active propagation call, extra echo, receive-time geometry read,
  physical terrain/collision reuse, renderer/audio call or serialized derived
  cache state was introduced.
- Save hardening: cooldown and canonical noisy BT structure are finite, bounded
  and transactionally validated; runtime CZ bands must match operator evidence.
- Catalog: 109 acoustic profiles valid. Smoke: `SMOKE-OK`.
- Build: 0.1.7 sdist and wheel succeeded; `src/sonar/propagation.py` is packaged.
- `git diff --check`: passed.
- Not covered: physical uConsole sensor-cadence/propagation-cost acceptance and
  the existing physical audio/readability/LAN checks.

## 2026-09-11 0.1.7 R18 Grounding And Localized Damage

- Revision: uncommitted R9-R18 working tree on `7d52faf`; no push performed.
- Final blocker matrix: 459 passed; grounding/save/determinism follow-up after
  persisted-normal hardening: 259 passed.
- Integrated full suite with the hydroacoustic follow-up: 2321 passed in 675.87
  seconds before the final focused normal hardening.
- World: generated-only deterministic synthetic shallows and hull-safe starts;
  restored old bathymetry remains value-identical and fully detached.
- Physics: separate bounded swept hull query for translating/turning footprints,
  exact thin-land handling, world boundaries and bilinear footprint minimum
  depth; no sonar propagation or acoustic-occlusion reuse.
- Runtime: canonical fictional hull assumptions, one-impact latch, deliberate
  swept ASTERN recovery and deterministic energy/location damage across only the
  existing nine compartments without damage RNG consumption.
- Persistence: strict current grounding/hull/world snapshots, exact pre-R18 v10
  shape upgrade, physical contact/normal consistency and transactional near-miss
  rejection.
- Catalog: 109 acoustic profiles valid. Smoke: `SMOKE-OK`.
- `git diff --check`: passed; final normal-specific independent review found no
  issue.
- Not covered: physical uConsole grounding cost, trackball ASTERN feel,
  readability and the existing physical audio/LAN checks.

## 2026-09-11 0.1.7 R19 Final Software Acceptance And Hold

- Revision: uncommitted R9-R19 candidate plus hydroacoustic/analyzer follow-up
  on `7d52faf`; no commit or push performed.
- Full suite: 2363 passed in 1107.32 seconds.
- Focused acceptance: save/version/transaction/continuation 299; real loopback
  and Chromium 506; stations/layout/i18n 384; audio/DSP 331; milestones and
  performance 202; catalog/provenance/assets/packaging/security 347. No skips in
  the browser/loopback matrix.
- Catalog: 109 acoustic profiles valid. Analyzer: 226 deterministic PNGs valid,
  exactly 113 Cruise and 113 High, no silhouette assets or routes.
- Smoke: `SMOKE-OK` including save/load and all nine stations.
- Packaging: 0.1.7 sdist and wheel built; clean separate installations passed
  version, schema, module and exact-resource checks.
- Security/provenance: no private PDFs, external audio/fonts/images, credentials,
  local saves or debug logs in artifacts; dependency consistency, credential,
  DOM-sink and Commander security tests passed. Dedicated CVE/SAST tools were
  unavailable.
- `git diff --check`: passed.
- Release status: HOLD. The accepted candidate remains a dirty worktree and is
  not reproducible from `HEAD` until an explicitly authorized complete commit is
  prepared.
- Physical gaps: uConsole nine-station/input/readability, headphone/speaker audio,
  sustained frame/thermal/endurance/propagation/grounding load, and two-device
  LAN/private-bind/firewall behavior.
- Mandatory post-R19 pause reached.
