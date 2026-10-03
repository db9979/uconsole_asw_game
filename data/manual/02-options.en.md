# Options {#options}

`F10` (or **Options** in the main menu or the game menu) opens the options. `Up`/`Down` pick a row, `Enter`/`Left`/`Right` change it, `PgUp`/`PgDn` or `Tab` switch between the two pages and `Esc` goes back. The settings are kept in `~/.u-jagd/settings.json`; a running mission keeps running behind the options.

![Options (F10)](figure:options)

## Page 1: screen, sound and realism {#options-page1}

| Row | Choices |
|---|---|
| Language | English, German |
| Fullscreen | on, off (also `Alt+Enter`) |
| Audio | on, off |
| Large text | on, off |
| Tooltips | on, off: explanations under the mouse; a click pins one |
| Simulation log | on, off: enables the `F4` view (chapter Tools) |
| Red light | Automatic (night, alarm), Always on, Off |
| Colour theme | Tactical Night, Tactical Day, High contrast / colour-blind |
| Frame rate | 30 FPS (default, saves CPU on the uConsole) or 60 FPS |
| Event log / telemetry | status ticker (default, more room for the station; `F11` opens the log) or docked band |
| Realism | Beginner, Standard, Realistic (below) |
| Real-world traffic | opens the AIS / ADS-B page (below) |
| Commander / local network (F9) | opens the Remote Crew page (chapter Remote Crew) |

- **Red light:** **Automatic** (default) turns the screens to dimmed red at night and on a torpedo, missile or fire alarm, **Always on** or **Off**. The browser has the same switch in its settings. The station tabs show an alarm lamp: amber steady for a warning (flooding, a ping, a degraded engine), red blinking for danger (torpedo, missile, fire).
- **Colour theme:** **Tactical Night** (default: dark surfaces, phosphor green, amber and red), **Tactical Day** (light glare-free greys with navy and dark text for daylight; waterfall, LOFAR and DEMON then draw dark traces on a light ground like a chart recorder) or **High contrast** (colour-blind friendly). The switch at the right of the top bar flips between dark and light with a click, on both sides. While the red light is on, the uConsole draws dark. The choice lives in `settings.json`, never in a save, and only changes the picture. The browser has its own switch.

### Realism level {#options-realism}

The realism level applies to the next mission:

- **Beginner:** operator assistance on (automatic line labels, blade-rate and catalogue or emitter candidates); the computer opponent attacks less eagerly, waits for a better firing solution and, as the frigate, classifies and launches its helicopter 1.5 times slower. Score 75 %.
- **Standard** (default): raw data and manual analysis, the calibrated opponent. Score 100 %.
- **Realistic:** no assistance; the opponent attacks more eagerly, fires on a rougher solution and reacts 30 % faster as the frigate. Score 125 %.

The level only tunes the computer opponent, never a human on the other side, and a running mission keeps the level it started with (the row then says "from the next mission"). The end panel shows the level with its score factor; saves keep it.

### Real-world traffic {#options-traffic}

The page **Real-world traffic** brings real ships (AIS Stream, needs your own API key) and real aircraft (OpenSky ADS-B, optionally with your OpenSky client ID) into a mission whose world is a real sea area. It needs an internet connection; without one the rows are greyed out. **API test** checks both services. Only traffic within about 150 NM of the frigate is placed (at most 60 ships and 40 aircraft), and ship positions are updated every 2 to 5 minutes. Changes apply at once and are saved.

## Page 2: game setup {#options-page2}

**uConsole plays:** which side the uConsole plays, frigate (default) or hostile submarine; only in the main menu, never saved. A new game asks for it first anyway. See chapter Submarine.

**Graphics level** (`Enter`/`Right` next, `Left` back): **Economy** uses plain pixel scaling, drops the radar afterglow and calms the menu backdrop to save CPU on the uConsole; **Normal** (the uConsole default) shows every effect; **Full** (the Windows default) also smooths bearing lines, coast and plot. In a window or full screen larger than 1280 x 720, Normal and Full scale the picture sharply: whole factors repeat pixels exactly, and other sizes (such as 1920 x 1080) first repeat pixels to the next whole factor and then smooth down, so text and thin lines stay even. The level changes only the picture, never the simulation or what a station shows.

**Spoken crew reports** (off by default): the crew says torpedo in the water, new contact with bearing, breaking-up noises, torpedo away, hit, action stations, patrol aircraft on station and the mission result aloud, bearings digit by digit. The uConsole speaks through an installed `espeak-ng` (`sudo apt install espeak-ng`) and stays silent without it; Remote Crew browsers have their own switch under Settings (the browser's speech synthesis, in the browser's language). With the uConsole on the submarine the submarine's crew reports instead (see chapter Submarine).

**Microphone** (off by default) lets the players' voices count for noise discipline (below). **Language model** opens the settings of the optional language model (chapter Language model).

## Noise discipline and microphone {#ref-noise}

- Now and then a crew drops a tool, slams a hatch, knocks a pot or rattles a chain: a short metallic bang for 3 s that raises the own noise. A fresh crew fumbles about twice an hour, a tired or demoralised one up to five times as often. Silent running (the frigate's quiet mode, the submarine's silent running or lying on the bottom) cuts it to 30 %, but repairs and reloading then go at 75 % speed.
- Within 4 NM the enemy hears such a bang on its bearing (less through its own machinery noise): the frigate's sonar reports a metallic transient, the submarine's sonar room a transient. The own crew reports its fumble under silent running.

**Microphone:** the players' voices count too. On the uConsole it is the option *Microphone* (off by default); in the browser the button *Microphone on* next to the sound button (asks for the microphone). Browsers hand the microphone only to a secure page: on the plain LAN page (`http://`) a box says so, and *Open HTTPS page* frees your stations and opens the host's HTTPS address (port + 1), where you accept the certificate warning once and pair again with the same code.

When the microphone does not work, the game says why: a status message in the mission and the cause on Options page 2 (no microphone, cannot be opened, or no sound because Windows or macOS blocks the access; there allow microphone access for desktop apps or for U-Jagd). The browser names a refused, missing or busy microphone in the same box.

A meter of 20 cells shows the own level against the thresholds: up to 5 quiet (green, unheard), 6 to 11 heard close by (yellow), from 12 heard far off (red, up to 2.5 NM at full volume). The outlined cell is the crew's loudest voice. A voice above the threshold raises the own noise by up to 20 %; the enemy hears voices, and the own crew is told to keep it down when it is far too loud. Only the level number leaves the browser, never sound; it counts for 1.5 s and is never saved.
