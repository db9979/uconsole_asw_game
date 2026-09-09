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
