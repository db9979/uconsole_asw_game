# 10 Submarine {#submarine}

## Overview {#sub-overview}

A second crew can play the submarine on the uConsole or in browsers (the lobby, `F9` or a new game as the submarine). The boat has seven stations; each order is accepted only from the station that owns it, and an AI fills every free station when the crew assist is on. This chapter gives each station's job and standard procedure; the key table and the boat's missions are in the reference chapter (*Crewed opposing submarine*).

## Command {#sub-command}

Command sees the whole boat: chart, navigation, weapons and contacts, the periscope and the threat page. It orders course, speed and depth, lies on the bottom, pings, takes a BT and evades on the freshest alarm.

<!-- sop:uboot_command -->

## Sonar {#sub-sonar}

The submarine's sonar room works like the frigate's, without towed array, OPZ release, plot and telegraph. The hull sonar is deaf in the baffles astern.

<!-- sop:uboot_sonar -->

## Weapons {#sub-weapons}

Weapons loads and floods the tubes, sets run depth and salvo, fires at a selected contact or down an entered bearing, steers the wired torpedoes and launches decoys. The fire-control box shows the seeker setting of the next shots.

<!-- sop:uboot_weapons -->

## Engine room {#sub-engine}

The engine room runs the telegraph, snorkel and charge rate, silent running, the trim tanks and the emergency blow, keeps the air breathable and leads the damage-control teams.

<!-- sop:uboot_engine -->

## Mast & ESM {#sub-esm}

Mast & ESM raises the mast at periscope depth, listens for radars on the ESM rose, classifies the emitters, plots cross-fixes and looks through the periscope.

<!-- sop:uboot_esm -->

## Navigation {#sub-nav}

Navigation orders course and depth, watches keel and shoals on the pilot chart and the echo sounder, keeps the dead reckoning and steers the route.

<!-- sop:uboot_nav -->

## Radio room {#sub-radio}

The radio room copies HQ's broadcasts, reads HQ's orders and contact reports and sends situation reports.

<!-- sop:uboot_radio -->

## Dead reckoning and route {#sub-dead-reckoning}

- Dived, the boat knows its position only by dead reckoning. The navigated position drifts from the true one by a steady set of up to 0.4 kn that log and gyro cannot see (a nuclear boat's inertial navigation drifts 0.3 times as much), plus a small random walk once a minute; the error stays below 8 NM.
- The crew's chart (coast, soundings, hazards, mission goal, HQ's reports and the route) is drawn where the navigator believes it lies against the boat. The boat itself, its own sonar contacts and own torpedoes stay where the boat measures them.
- A GPS fix: mast up at periscope depth for 20 s puts the navigated position back on the true one. The **DR position** lamp on the Chart & sounder page shows the navigator's own error estimate and the minutes since the fix, or the fix being taken.
- The chart check ahead and the route steer from the navigated position, so an old fix can lead the boat into water the chart calls clear.
- The route: a right click on the chart adds a waypoint (at most 8), `W` lays a zigzag or expanding-square search from the boat and steps to off, `Backspace` clears it. Any course order from the helm or an evasion ends the route; a baffle clearing has the helm while it runs. In the browser **Set waypoints on chart** turns clicks on the chart into waypoints.

## Torpedo seeker {#sub-seeker}

- `X` steps the search pattern of the next shots: straight (as before), snake, circle or helix. The torpedo runs straight to the datum; once its seeker is on and it has found nothing, it searches in that pattern.
- `,` and `.` move the enable point between 0.6 and 3.0 NM before the datum in 0.2 NM steps (default 3.0 NM). A late enable point keeps the seeker blind longer, so decoys and other ships on the way are not taken.
- A torpedo in the water keeps the settings it was fired with; the browser's Weapons card sets both with **Apply**.

## Surfacing and crash dive {#sub-surface}

- `Shift+H` (browser: **Surface**, Command or Navigation) orders the boat up to the surface. At 2 m or less it is surfaced: the low-pressure blower empties the main ballast within 2 minutes (no bottle air), the hatch is open and the boat airs itself.
- Surfaced, the diesels (`N`) run in the open air: up to 12 kn (or the boat's top speed) instead of 6 kn on the snorkel, and the generator gives 1.3 times its snorkel power, so the battery charges faster.
- The bridge watch looks out from 6 m instead of the periscope's 2.5 m and sees farther; its reports read **Bridge:** and an aircraft is called as an alarm. The scope page shows the bridge watch's view.
- The enemy sees a surfaced boat too: the frigate's surface radar and the radars of helicopter and patrol aircraft see hull and conning tower (ten times a mast's echo), and lookouts see it by eye.
- `H` from the surface or with blown tanks (browser: **Crash dive**) is the crash dive: alarm, masts and snorkel down, vents open, full ahead, ordered depth 40 m. Blown tanks hold the boat above 10 m until the vents have flooded them (up to 40 s), and the flooding vents are a transient the enemy may hear. From deeper than 12 m a crash dive is refused.

## Not modelled {#sub-limits}

- No position fixes from landmarks, soundings or stars; only GPS clears the dead-reckoning error.
- The plot keeps its marks where they were drawn against the boat; it does not move with a fix.
- No separate control room or diving officer station; trim and ballast stay with the engine room.
