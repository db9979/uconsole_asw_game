# Workstation and Model Review

This implementation follows a source review of the eight workstations, six
sonar pages, input ownership, persistence, catalogs, AI, weapons and synthesized
audio. Specialist review roles were analytical perspectives, not naval
certification. No real classified performance or authentic F123 room layout is
claimed. Review baseline was 0.1.5; saves remain v8 with v1-v8 loading.
The subsequent Commander milestone is tracked in plan-0.1.6.md.

## Delivered Corrections

- Damage Control has an original procedural F-217 system diagram, nine existing
  compartment IDs, shared polygon/callout hit geometry, optional pinned details,
  redundant flood/fire/destroyed/team markers and model-backed net hazard rates.
- Weapons shows range, source, uncertainty, evidence age and readiness in bounded
  fields. Helo hangar/lost states, Bridge bearing-only alerts, OPZ selection and
  unknown sensor domains no longer imply information that is unavailable.
- Sonar panels reserve space for populated details. Historical tooltip selection
  follows rendered rows/points, including empty waterfall history. Selected-array
  audition is separate from the fused tactical contact.
- Universal repeat, focus and fullscreen protections precede editor input.
  Editor pointers respect letterboxing. Map click/drag and OPZ wheel geometry
  agree with the display. Station transitions clear input and pinned context.
- Help scrolls within its three categories. Ctrl+Enter supplies a common primary
  weapon action while existing shortcuts remain. Joystick device opening and
  hotplug cleanup are supported; device-specific sensitivity still needs testing.
- Operator course/depth adjustments use wall time. Track queries and chart
  rendering do not delete observations or change the saved camera state.
- TMA and buoy fixes age separately from passive bearings. Buoy pairs require
  valid geometry and use bounded presentation filtering. TMA considers
  intermediate turns and reuses precomputed geometry without changing grid order.
- Delayed active returns contain immutable numeric transmit-time measurements.
  Save restoration validates them, preserves new snapshots, and conservatively
  reconstructs old records when the target still exists.
- Helo releases use the observed datum and check water entry. Air torpedoes do
  not acquire a fictional ship wire. Torpedoes have terminal depth tracking,
  loss/reacquisition and terrain-aware swept collision. ESSM uses an observed
  midcourse datum before bounded terminal acquisition.
- Chaff does not remove physical collision. CIWS bursts consume ammunition even
  when unsuccessful. Missiles have bounded lifecycle and monotonic identities.
  Sinking cannot be cancelled by new sensor warnings, and delayed sink scoring
  is processed on the terminal transition.
- Launch authorization uses public annotations/evidence rather than hidden
  entity category. Protected affiliations survive picture expiry. Civilian
  incidents require depth-consistent swept overlap, not planar proximity alone.
- Submarine/surface/aircraft decisions use bounded local observation memory.
  Aircraft ESM reception requires player emissions; radar transmission is a
  separate explicit game rule. Hidden salvo/decoy spawns no longer announce
  platform identity. Depth commands and coast avoidance respect terrain.
- Catalog loader and validator share strict finite typed schemas and duplicate
  checks. Editor schemas reject unknown fields. Authored built-in submarine
  placement speed and difficulty settings reach the runtime bridge.
- Receiver oscillator phases survive frequency changes; scan energy comes from
  the same source components and does not depend on the selected listening beam.
  Audio handoff, phase state, band masks and playback queues are bounded. Volume
  has a useful full range and the reserved audio buses have tested headroom.
- Save/load retains new weapon/filter/timing states, operator team, civilian
  avoidance and allocator high-water marks. Known historical infinite memory
  sentinels migrate to null in strict JSON output. Invalid references, expanded
  salvos and malformed observation snapshots fail before candidate commit.

## Deliberate Model Limits

- Geographic bathymetry is synthetic. Sonar uses straight-path obstruction and
  heuristic environment effects, not ocean-acoustic ray tracing or calibrated
  covariance. A visually stable bearing does not prove precise localization.
- Active scattering is approximated at transmit pose. Warnings remain immediate,
  and destruction of the scatterer cancels a queued return for compatibility.
- HFDF covariance assumes a stationary emitter over a bounded measurement span;
  it is not a motion solution. Fix age and this assumption are displayed.
- Enemy sensing uses inexpensive local gates and aged estimates, not complete
  enemy-side radar/TMA processors. There is no battery/AIP/oxygen endurance model.
- Platform names and acoustic signatures remain illustrative. Difficulty hit
  envelopes remain an explicit gameplay contract, not claimed lethal radii.
  Enemy torpedoes, aviation and missile altitude/energy remain simplified.
- User-unit profiles remain authoring-only. Strict validation does not make every
  descriptive/library field effective. See contacts-db.md for field ownership.
- DSP restarts after loading; exact uninterrupted PCM continuation is not claimed.
  At accelerated time, audition is sampled preview rather than continuous replay.
- Initial code-review suggestions such as physical grounding damage, detailed
  biological call/silence cycles and a mechanically complete propulsion-noise
  model remain separate fidelity extensions, not fabricated real data.

## Measured Optimization

Short headless CPU measurements on the development aarch64 host (Python 3.13.5,
Pygame 2.6.1), not complete-game or physical readability acceptance:

| Workload | Before | After |
|---|---:|---:|
| TMA, 20 measured bearings | 25.02 ms | 16.91 ms |
| TMA, 80 measured bearings | 109.36 ms | 66.99 ms |
| Warm map draw, scale 1 | 22.91 ms | 10.24 ms |
| Warm map draw, scale 4 | 14.65 ms | 7.82 ms |

TMA measurements are medians of five batches of three solves. Map measurements
are medians of five batches of 30 draws with sector seed 42 and empty tracks.
The bounded chart cache retains one snapshot and at most 4096 cells; mutation,
snapshot/world replacement and palette changes invalidate it. Tests compare
arithmetic and pixels, rather than enforcing environment-dependent time limits.

120x is not guaranteed to sustain real time on low-power hardware: a full TMA
solve can become due 30 times per real second, in addition to sensor DSP and
physics. The implementation does not silently drop authoritative evidence or
change simulation timing to conceal overload.

## Acceptance

Automated regressions cover state transitions, displayed/commanded datums,
observation boundaries, malformed/legacy saves, phase continuity, audio power,
queue backpressure, historical tooltips, drawing purity, all nine schematic
hotspots, English/German/pseudolocale and large text. The screenshot tool includes
a separately authored own-ship damage example; it is not an observed battle.

Physical uConsole acceptance still requires headphones/speaker listening,
steady joystick and trackball handling, focus/hotplug tests, crowded stations,
long German labels, large text and sustained frame-time/thermal measurements
under time acceleration. Headless tests do not establish those outcomes.
