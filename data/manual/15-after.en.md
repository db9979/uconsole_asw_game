# After the mission {#after-mission}

## End panel {#after-end}

When a mission ends, the end panel names the result, the score with the realism level's factor, a new best score and new awards. `R` restarts the mission with the same seed, `M` returns to the main menu and `D` opens the debrief. A mission started from the multiplayer lobby returns everyone to the lobby.

## Debrief {#after-debrief}

Debrief: after the mission ends, `D` on the end panel opens the debrief. It replays the mission with the truth beside what the crew knew: the true tracks of the ship and the hostile submarines, the crew's contacts where it had placed them (bearing-only contacts as bearing lines), weapons, buoys and aircraft.

Beside the chart it lists the time of the first contact, first fix and classification, weapons fired and submarines sunk, the mean error of the crew's fixes, and every event; a "missed chance" is a hostile submarine within 4 NM for at least 5 min without any contact, marked above or below the layer.

`Left`/`Right` step (Shift: 1 min), `Up`/`Down` or `PgUp`/`PgDn` jump between events, a click on the timeline jumps there, `Space` plays it back (`Tab`: 10x or 60x), `D` or `Esc` returns. The debrief is recorded every 10 s (coarser on long missions), is never shown during a mission and is not saved: after a load it covers the mission from the load onwards.

- **Debrief replay:** after the mission `Space` plays the debrief back and `Tab` switches between 10x and 60x; the tracks grow and shots, pings, hits and sinkings flash where they happened. The browser's **Play debrief** button (next to the mission state, only after the end) shows the same replay for its own side.

## Logbook and awards {#after-logbook}

**Logbook** (main menu): every finished mission (never a lesson) for the side the uConsole played, with date, mission, realism level, result, score and minutes; the best score per mission and five awards per side: first victory, one shot one kill (the enemy sunk with a single weapon), unscathed (no damage), never fired at, and realist (a victory on the Realistic level).

The frigate files its mission score; the submarine counts its outcome (sinking the frigate 1500, sinking the convoy 1200, breakthrough or report 1000, escape 800, surviving 600) plus up to 500 for an undamaged submarine and 100 per torpedo left, times the level's factor.

`Left`/`Right` or `Tab` switch frigate and submarine, `A` the language model's review, `B` the newest report, `L` the enemy's learning, `Enter` or `Esc` back; the footer names these keys and a click on one presses it. The end panel names the score, a new best and new awards. The logbook is `~/.u-jagd/logbook.json` (the newest 200 missions), never part of a save.

## The enemy learns {#ref-habits}

- After every mission of 5 min or more the logbook notes coarse habits of the side played. Frigate: **early pings** (first ping before or up to 2 min after the first contact), **fast search** (a mean of 18 kn or more without a position), **long shots** (torpedoes at a mean of 5 NM or more). Submarine: **periscope depth** (a quarter of the time), **above the layer** (half of the time), **high speed** (a mean of 10 kn or more).
- When more than half of the last five missions of a side (at least three) showed a habit, the enemy knows it in the next mission and adapts a little: against early pings the submarines go under the layer as soon as they hear the frigate, and all go deep after a ping; against a fast search they lie in wait instead of closing; against long shots they creep deep instead of closing. Against a submarine often at periscope depth the hunter frigate searches in sprints, against one above the layer too, against high speed it searches quietly.
- What the enemy knows is fixed at the start of the mission and saved. The debrief names it, the logbook page shows it per side. `L` on the logbook page switches the learning off and on. In the daily mission, lessons and two-crew play the enemy never learns.
