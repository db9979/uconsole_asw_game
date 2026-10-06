# Main menu and game start {#menu}

After the start screen (a key or a click closes it) the main menu opens. `Up`/`Down` (or the mouse) choose an entry, `Enter` opens it, `Esc` asks whether to quit. Every page reached from it goes back with `Esc`.

![Main menu](figure:main-menu)

## Main menu entries {#menu-entries}

| Entry | What it does |
|---|---|
| Continue mission | Resumes the autosaved mission; only shown while an autosave exists |
| New mission | Side, scenario, briefing (below) |
| Training | Nine guided lessons (below) |
| Daily mission | One fixed short mission per side and day |
| Multiplayer | The lobby with Remote Crew (chapter Remote Crew) |
| Server (browsers only) | The uConsole only serves; everyone plays in the browser |
| Campaign | Theatre campaign for either side (chapter Scenarios and missions) |
| Logbook | Service record and awards (chapter After the mission) |
| Load mission | Loads slot 1-5 |
| Mission Editor | Own missions (chapter Mission and unit editor) |
| Unit Editor | Own unit profiles (chapter Mission and unit editor) |
| Tactical Unit Analyzer | Read-only catalogue of every unit (chapter Mission and unit editor) |
| Options | Settings (chapter Options) |
| Report a bug | Bug report with QR code (below) |
| Quit | Ends the game |

## First launch {#menu-welcome}

When no `~/.u-jagd/settings.json` exists yet, a welcome page follows the start screen: "What do you want to play?" `1` Frigate (the Training menu with lesson 1 selected), `2` Submarine (the Training menu with lesson 8, the first submarine lesson, selected), `3` Remote Crew (opens the multiplayer lobby; `Esc` there leads to the main menu), `4` or `Esc` main menu. Arrow keys and `Enter` choose as well. Whatever you pick, the page is remembered in the settings and not shown again.

## New mission: side and scenario {#menu-new}

A new game first asks for the side (`1` frigate, `2` submarine), then lists only that side's scenarios: each side counts from `1`: `1`-`9` and `0` (the tenth; the eleventh and twelfth with the arrow keys) on either side (frigate 4 = random with custom difficulty) (see chapter Scenarios and missions), `Esc` back to the side choice; `W` world mode, `R` new seed, `F` fullscreen (these three only on the main menu and the scenario pages: list, difficulty, briefing), `Enter` start.

The list shows nine rows at once and scrolls with the selection (`Up`/`Down`, mouse wheel, `PgUp`/`PgDn` one page, `Home`/`End` first and last row; with a fixed real sector `[`/`]` choose the sector); a bar at its right edge shows where you are, and below it the start of the selected scenario's briefing. The own missions and the free hunt's difficulty list scroll the same way.

**Own missions:** the start menu lists, after the scenarios of the chosen side, the row "Own missions" (`O`, or `Enter` on the row). It opens the Mission Editor's missions of that side; `Enter` starts one. The multiplayer lobby offers them in its mission row after the scenarios, and the solo browser in the "New game" dialog and under "Own missions" in the host bar (see chapter Mission and unit editor).

## Briefing: weather, time of day and length {#menu-briefing}

![Mission briefing before the start: task, area, forces and win conditions](figure:mission-briefing)

**Weather and time of day:** every scenario's briefing (for 4 after the difficulty), a campaign hotspot's briefing, the multiplayer lobby and the browser's "New game" dialog choose the weather (random, fair, rain, storm, fog) and the time of day (random, dawn 06:00, day 12:00, dusk 19:00, night 01:00): `Up`/`Down` picks the row, `Left`/`Right` changes it. Random keeps what the seed gives.

A chosen weather holds for the whole mission (sea state fair and fog 1, rain 3, storm 5; the sea changes only within 0-2, 2-4 and 5-6; a storm brings thunderstorms with lightning, thunder and sferics), and no weather fronts pass then; the clock runs on from the chosen time. The choice holds for every new mission until the game quits, also for `R` at mission end; it is saved with the mission, not in the settings.

**Short mission:** the same places offer a third row, the length: the full mission or a short one (not for scenario 4, whose time limit is its own setting). The length last chosen there (start menu, lobby or browser) is kept in the settings for the next launch; a new player without settings starts on the short missions.

A short mission keeps its goal but has a shorter time limit and starts closer to the action: Patrol 30 min, Double hunt 60 min, Nuclear intercept 45 min, Breakthrough 60 min, Hunter group 60 min, Reconnaissance 45 min, Convoy attack 35 min, Strait blockade 45 min, Combat swimmers 45 min, Supply ship escort 45 min, Convoy escort 35 min, Damaged homecoming 60 min, every other new scenario 45 min. The first hostile submarine starts 5-8 NM from the frigate (Breakthrough and Hunter group 4-6 NM, Reconnaissance 10-16 NM) and every further one 8-14 NM; in a submarine mission the goal beyond the frigate, the strait's entry and exit, the swimmers' approach and the place on the convoy's or supply ship's bow come closer as well.

Each short variant was tuned with AI-against-AI games so that both sides win about equally often. Its name carries "(short)" and it is saved like any mission.

## Training {#menu-training}

**Training** offers nine guided lessons. Each is a short mission with a hint banner that waits for you; `Up`/`Down` or `1`-`9` choose, `Enter` starts. A lesson finished once carries a tick (✓), the first one not yet finished is marked "next" and is selected when the page opens; a line below the list counts the lessons done. The ticks are kept in the settings, not in a save.

| Lesson | Side | What you practise |
|---|---|---|
| 1 Listen and take bearings | Frigate | Find a submarine on the sonar, follow it and classify it |
| 2 Target motion analysis | Frigate | Switch TMA on, run a second leg and get a range |
| 3 Torpedo attack | Frigate | Locate, classify, designate and sink a hostile submarine |
| 4 Helicopter and sonobuoys | Frigate | Launch the helicopter, lay a buoy and hear the submarine on it |
| 5 Air defence: missile inbound | Frigate | Find the sea-skimmer from the north-east on the OPZ and shoot it down with an ESSM; a missed or leaking missile is followed by another 30 s later |
| 6 ESM: hear a radar | Frigate | Hear a merchant's radar on the ELOKA, name its radar type with `C` and see the released bearing on the OPZ |
| 7 Torpedo defence with the Nixie | Frigate | A torpedo runs at the ship from 3.6 NM: stream the Nixie (`V`), run at HALF or FULL and hold the course until it has run out or hit the decoy |
| 8 Listen and hide below the layer | Submarine | Hear the frigate, classify it as a warship, measure the layer with a BT and dive below it |
| 9 Shake off a hunting frigate | Submarine | Read the Threat page, evade with `I`, go quiet and deeper than 100 m until no ping has come for two minutes |

For lessons 8 and 9 the uConsole plays the submarine. In lesson 9 the frigate pings every 45 s until you evade, then only while its pings still find you, and it never fires.

In lessons 1, 2 and 4 the submarine is neutral and never attacks; lesson 3 is a real attack that ends when the submarine sinks; lessons 5 to 7 have no submarine. In lesson 7 the torpedo is real: at SLOW or FLANK, or without the Nixie, it still finds the ship, and a hit ends the lesson as lost. The other lessons end as won after their last step. `R` at the end runs the lesson again, `N` after a finished lesson starts the next one. A saved lesson restarts its hints at step 1 after loading and passes the steps that are already done. After a lesson the uConsole keeps the side it played.

## Daily mission {#ref-daily}

- The main menu's *Daily mission* offers one fixed mission per side and day, the same for every player: the date picks the scenario and the seed, and with it the real sea area, weather and time. It is always the short variant of a scenario that has one (the page names its minutes), so it fits a break.
- The page shows today's best score of each side; a finished daily mission (also after midnight, for yesterday's) keeps the best win in the logbook for 30 days; only the short daily mission counts. The realism level is the player's own setting.

## Saving, loading and autosave {#menu-save}

`S` saves, `L` loads (slots 1-5). Saves are exact and deterministic: a loaded game continues identically. The file is written in the background while the mission runs on; the save menu closes (or the game quits after **Save and exit**) only once it is safely on disk. A save of an older release (save format v38, release 1.3.98, or newer) still loads: it is brought up to the current format on loading, slots and autosave alike.

**Autosave:** a running mission is saved every 5 minutes and when you quit or leave it for the main menu, to `~/.u-jagd/autosave.json` beside the five slots. The main menu then starts with **Continue mission**, which resumes it exactly; after a crash it holds the last recovery point, at most one minute old. A mission that ends (won, lost or ship sunk) and any new mission delete the autosave. The web host (`--web-host`) does not autosave.

**Fault protection:** a station view that fails to draw shows "Display fault" while the mission keeps running; a fault in the simulation puts the mission back to its recovery point of up to one minute earlier (an in-memory copy, never written on its own) and says so in the feed. Remote Crew browsers are handed their stations again as after a load. After repeated faults the mission is saved and the main menu opens with **Continue mission**. Every caught fault goes to `~/.u-jagd/crash.log` for a bug report.

## Update notice {#menu-update}

New releases are never installed on their own. At launch the game asks GitHub once whether a newer release exists; if so, the start screen (top right) and the main menu (left of the entries) show its version, its changelog entry in the game language and, only when saved games of this version (the autosave too) are too old for the new release to bring up to date, a warning. The cross at its top right hides the notice until the next launch.

`U` or a click on **Update now** installs it: on the uConsole the game closes, the launcher's small window shows the download and check and the new version starts; the Windows program downloads it in the background (progress on the button), checks its size and SHA-256 digest, closes, replaces itself and starts the new version; the macOS app does the same with its zip (Apple silicon only; an Intel Mac opens the release page): it unpacks the new `U-Jagd.app` beside itself, closes, swaps the bundle (the old one is deleted only once the new one is in place) and opens the new version, provided it may write to its folder (otherwise it opens the release page); any other installation opens the release page.

If the check fails, the same place says so and why (no connection to GitHub, the connection could not be verified by certificate, or an error from GitHub) and `U` or a click checks again; with `U_JAGD_NO_UPDATE=1` nothing is checked.

## Report a bug {#menu-bug}

**Report a bug** in the main menu writes `~/.u-jagd/bug-report.txt` (version, platform and the newest lines of `~/.u-jagd/crash.log`, with your user name removed from paths) and shows a QR code that opens a new GitHub issue on a phone with version and platform filled in; attach the file there. `Enter` opens the issue with the log in a browser if the device has one, `Esc` goes back. After a crashed start the main menu selects this entry and says so. Nothing is sent until you submit the issue with your own GitHub account. The browser settings menu has the same link.

## Starting the game {#menu-launch}

On a Windows PC the program `U-Jagd-Windows.exe` starts straight into the game with the same command-line options; there is no separate starter window (on a Mac the app `U-Jagd.app` works the same way), and **Multiplayer** in the main menu (or `--multiplayer`, below) opens the lobby with Remote Crew on.

Command-line options at launch (the same for the Windows program and the macOS app):

- `--windowed` and `--no-audio` override the saved fullscreen and audio setting for one launch.
- `--multiplayer` opens the multiplayer lobby straight after the start screen.
- `--server` starts the browsers-only server mode (chapter Remote Crew).
- `--solo-crew` starts Remote Crew in solo mode: one browser runs every station (chapter Remote Crew).
- A number as the only argument sets the seed of the world.

## Menu keys {#menu-keys}

Menu keys (main menu and its pages; `F1` in a menu shows them):

<!-- keys:menu -->
