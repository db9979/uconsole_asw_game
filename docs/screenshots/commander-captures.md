# Commander Browser Captures

These are seeded demonstration screenshots of the actual packaged browser assets,
served by the production `CommanderServer` and projected by `CommanderBridge` from
a real `Game`. They are not mocked API responses, station screenshots stretched
to browser dimensions, or evidence of two-computer LAN/hardware acceptance.

| Image | PNG Dimensions | Capture |
| --- | --- | --- |
| [Commander overview](commander-overview.png) | 1920 x 1080 | English, seed 1234, Patrol |
| [Commander wide](commander-wide.png) | 2560 x 1440 | English, seed 1234, Patrol |

## Reproduction

From the repository root, with the project dependencies and Chromium installed:

```sh
python tools/capture_commander.py
python tools/capture_commander.py --output /tmp/commander-review --seed 1234
```

The optional tool does not download a browser or require Node/Playwright. It warms
the game with 360 normal 1/60-second updates, then continues the simulation and
pumps the bridge on the main thread while Chromium runs. Consequently the seed
and setup are repeatable, but sensor ages, bearings, damage repair and elapsed
time can vary slightly with browser timing. These PNGs are not pixel-golden tests.
`--budget-ms` changes Chromium's virtual-time budget (default 3000); process and
server shutdown have separate bounded wall-time handling.

Only own-ship damage is authored for illustration: the sonar compartment starts
damaged with 12% flooding, and the engine compartment starts damaged with 7%
flooding and 9% fire. Team 1 is assigned to sonar; teams 2 and 3 to engineering.
Normal simulation continues repairing these demonstration conditions. Enemy
contacts, bearings, quality, positions and ranges come only from sensor outputs.
The two contacts in the reviewed captures are bearing-only observations; absent
range/depth/course remains unavailable, not an invented position.

The script binds only `127.0.0.1` on an ephemeral port. It appends automation only
to the server's in-memory cached JavaScript: enter the current pairing code,
submit the real pairing form, and select the first published contact locally.
No command is sent after pairing. The main thread explicitly grants permission
once the browser is paired. No HTTP thread accesses `Game`.

An isolated temporary HOME and incognito Chromium profile avoid real user data.
Credentials are neither printed nor placed in a URL or intentionally persisted;
the injected script is never written to source files. Browser DOM output is
examined only in memory. Both images are staged before publication. The service
is stopped, pairing revoked, injected cached assets cleared, and listener/worker
termination checked before the PNGs are copied to the output directory.

## Review And Limits

Image review on 2026-09-07 checked both final PNGs for readable mission/connection
status, contact selection/details, a correctly proportioned north-up chart,
bearing-only rays, chart disclaimer/legend, and visible ownship/alarm/log headings.
The initial 1080p image exposed a layout issue: long contact details stretched
the workspace and pushed all support panels below the first screen. The desktop
workspace is now bounded with internally scrolling contact assessments. Numeric
grid labels are also culled before they clip against the canvas edges.

The capture checks verified `phase=live`, `connected=true`,
`commands_allowed=true`, two published contacts, first-contact selection,
enabled affiliation Apply, English UI, a rendered canvas, no horizontal page
overflow and no captured JavaScript errors. The selected ESM contact cannot be
classified or proposed as a weapon target; those disabled buttons correctly
reflect observation eligibility, not a missing local grant. Sound remains muted.

Vertical scrolling is intentional: the complete compartment report and the
lower parts of a long assessment need not fit on the first screen. Chromium may
report a shorter CSS viewport during automation before its final screenshot
resize; the tool verifies the actual PNG dimensions separately.

This review does not establish real two-PC pairing, Wi-Fi reliability, physical
display readability, touch input, WebAudio playback, or uConsole performance.
Command execution/reconciliation is covered by separate contract tests, not by
this non-commanding screenshot automation. Mobile and German layout contract
tests remain distinct from this English desktop image review.
