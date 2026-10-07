# Mission and unit editor {#editors}

The Mission Editor and the Unit Editor (both in the main menu) build your own missions and unit profiles. They run outside a mission; the simulation is not running while you edit.

## Mission Editor {#ed-mission}

![Mission editor](figure:mission-editor)

![Mission editor, unit details](figure:mission-editor-detail)

User missions start from the Mission Editor (`F5` in its browser). The runtime takes the editor's scope: a 500 NM fixed world or a packaged reference sector (`sector:0` to `sector:127`), the authored weather, placed submarines, surface ships, aircraft (patrolling a 10 NM box at profile speed), animals, static decoys and hostile torpedoes already running on their course, seeded random groups, timed events (message, spawn, weather, objective) and the objectives sink, survive, protect (keep the named units alive until the time limit) and reach (enter the objective point's radius).

Profiles saved in the Unit Editor can be placed like built-in ones and take effect in that mission (speeds, depth, torpedo load, behaviour, acoustics); a user submarine takes sensors, tubes, decoys and its battery, diesel or AIP plant from the built-in submarine of its propulsion. Frigate and helicopter torpedoes, missing user profiles and other world sizes are refused at start.

A field opens with `Enter` or a second click on its row (the first click picks it). In the editor's World tab, `Enter` on Kind or Reference opens a pick list (`Up`/`Down`, `PgUp`/`PgDn`, `Enter` takes, `Esc` cancels); Reference lists the 128 sectors with their countries, and picking one makes the world a 500 NM reference world. The Preview tab then draws that sector's coast.

Both editors work fully by mouse. The key bar at the foot of the page shows the keys of the current mode as chips, and a click presses that key: `F5` starts the selected mission, `N` makes a new one, `←`/`→` changes the section (left half back, right half on). The cross at the top right goes back to the list, or out of the editor from the list. The path dialog has **OK** and **Cancel** buttons. The exchange folder list has buttons for import (overwrite, when asked), path and folder, and a cross. A delete question shows **yes, delete** and **no** in the key bar; `Esc` on a question or dialog closes only that, never the editor.

## Own missions and sharing {#ed-share}

Own missions and sharing: in the Mission Editor's overview the player side is frigate or submarine. For the submarine, "Player's submarine" names one placed hostile submarine, which the player commands while the AI crews the frigate; its objectives are sink (only merchant ships can be targets, because the submarine's torpedoes hit civilian shipping), survive (hold out until the time limit) or reach, never protect. The submarine wins by sinking all targets, reaching the point or holding out, and loses when it is sunk or, on sink and reach, when time runs out. The editor's browser marks submarine missions with `[U]`, and its brief and preview give fairness hints: a submarine starting within 3 NM of the frigate, no hostile unit at all, or a reach point or nearest target that the side can hardly get to in the time limit (frigate 20 kn, submarine 8 kn).

`Ctrl+E` shares the selected mission as a file into the exchange folder `~/.u-jagd/share` (Windows: `%USERPROFILE%\.u-jagd\share`), with every user unit it references packed in; `Ctrl+Shift+E` still exports to a typed path. `Ctrl+I` lists the files in that folder with their missions (`Up`/`Down`, `Enter` imports, a second `Enter` overwrites existing items, `Tab` types a path instead, `O` opens the folder, `Esc` closes); items that are already identical are skipped. `O` in the editor's browser opens the folder in the file manager (Explorer on Windows). Copy a file into a friend's folder and they import it with `Ctrl+I`.

In the Remote Crew solo mode, "Own missions" in the browser's host bar lists the same missions with side, objective, hints or problems: Start (switches to the mission's side first), Edit, Download (the same share file) and Delete; "Upload file" takes a share file or a single mission (at most 1 MB). "New mission" or Edit opens the Mission Planner: tabs Overview, World, Units, Objective and Events and a map of the world or reference sector where a click places the frigate, the selected unit or the reach point. Save stores the mission on the uConsole after the same validation as the editor (problems are listed, an existing key asks before it is overwritten), Save and start starts it at once. Crew sessions have no access to the library.

## Unit analyser and Unit Editor {#ed-unit}

![Unit editor](figure:unit-editor)

![Contact analyser (F8)](figure:contact-analyzer)

Unit analyser (`F8`, main menu) and Unit Editor: the first page of every catalog profile in the analyser is a schematic 3D model of its type (tab `3D`, then the sound and radar images with `Left`/`Right`); it turns slowly, and in the Remote Crew browser it can also be turned by dragging. The Unit Editor shows the same model under the selected profile and beside the fields of an opened one.

Every ship, submarine and aircraft type of the catalog has its own model, built from the public main dimensions and general arrangement of the real class (Wikipedia; generic types such as a VLCC or a harbour tug use typical values): length, beam and draught, where bridge, masts, funnels, guns, missile cells, flight deck, cranes and cargo stand, the submarine's sail, planes, rudders and missile deck, the aircraft's wings, tail and engines. The same type always looks the same; unit-editor profiles and anything without a type of its own keep the model of their class (warship, merchant, small craft, submarine, the lookout's helicopter). Torpedoes, decoys, whales, fish schools and jellyfish have their own models.

The models are schematic and every one is drawn at the same length, so they are not to scale with each other. The same models stand in the eyepieces, turned by the judged angle on the bow (lookout, binoculars, periscope); the browser loads them in three groups on first use.
