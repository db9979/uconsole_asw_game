# Remote Crew and multiplayer {#multiplayer}

Remote Crew lets browsers on the local network take stations. The uConsole stays the only simulation: the browsers send orders and show their station's own picture, they never run the game themselves. A browser holds stations of one unit only, frigate or submarine.

## Multiplayer lobby {#mp-lobby}

**Multiplayer** (main menu): the lobby where the crew meets before a mission. It starts Remote Crew in crew mode by itself and shows the QR code, address and join code. On the uConsole's own hotspot it shows two numbered steps side by side: **1** the Wi-Fi QR code with the Wi-Fi name and password (join the hotspot), **2** the page QR code with the address and join code (open the crew page).

A browser that pairs while the lobby is open is seated on the first free station of the uConsole's unit, in this order: frigate Bridge, Sonar, Weapons, Helicopter, OPZ, ELOKA, Radio, Engine, Damage control; submarine Command, Sonar, Weapons, Mast & ESM, Navigation, Engine room, Radio room (the stations that need judgement first; the AI crew keeps the routine ones well). Browsers can change their unit and stations at any time and press **Ready**; they see the mission, what the uConsole plays and every crewmate with their stations and ready tick.

On the uConsole, `Up`/`Down` choose a row and `Left`/`Right` change it: the mission, the unit the uConsole plays and the station it shows, or **none, host only**: then the uConsole plays no station, the browsers can take every one and the AI crews the rest. **Start the mission for everyone** starts a five-second countdown that every browser sees, then the mission begins for all at once and the uConsole opens on its chosen station. If a crewmate with a station is not ready yet, the first `Enter` asks again and a second one starts anyway. `Esc` cancels a countdown, otherwise it leads back to the main menu while Remote Crew keeps running.

When a mission started from the lobby ends, everyone returns to the lobby with their stations; the ready ticks start again from zero. Every mission started from the lobby with a browser taking part (or host only) has the crew assist on (`Shift+F2`); alone it starts as a solo game with the assist off. `F9` opens the full Remote Crew settings from the lobby. Started with `--multiplayer`, the game opens the lobby straight after the start screen.

## Crew versus crew {#mp-versus}

**Crew versus crew** (lobby row **Opponent**): *AI* (the default) puts every browser on the uConsole's unit as above; *second crew* lets two teams play each other, the frigate's crew against the submarine's.

A browser that pairs then joins the team with fewer people (on a tie the frigate, which has more stations), the uConsole counting for its own unit unless it only hosts; the browser lobby shows both teams with a blue (frigate) or red (submarine) stripe. If a team has nobody, the first `Enter` asks again and a second one starts anyway with the AI crewing that unit.

From the start every browser stays with its team for the whole round: it can swap stations within its unit but never take one of the other unit. Each team sees only its own unit's picture (as always), and in the web-host room each unit has its own push-to-talk channel, so a crew never hears the other one. When the round ends, the end panel names each unit's own result ("Frigate: victory, submarine: defeat") and each browser gets its own unit's result in its event feed.

A uConsole that only hosts a crew-versus-crew round shows the **umpire screen** instead of a station: the mission, the time left and who crews which station of both units (a name or AI), never a tactical picture, and it plays no sonar or effect sounds; only `F1`, `F9` and `Esc` work there. The scenarios are the same as against the AI, so their balance (both sides win, see chapter Main menu, Briefing) holds for two crews as well.

## Server mode (browsers only) {#mp-server}

**Server (browsers only)** (main menu, or `--server` at launch): the uConsole only serves and everyone plays in the browser, on both units, alone or together. It opens the lobby with Remote Crew on, the uConsole plays no station (the station row is fixed to host only) and shows only the QR code, address, join code and the crew.

The first crew browser that joins is the **game leader** (marked in every browser's lobby): it chooses in the lobby the unit, the mission (a scenario, the daily mission, a campaign hotspot of the chosen unit with the campaign's port choices, or an own mission), the opponent (AI or second crew), weather, time of day and mission length, and starts the countdown with **Start for everyone** (a second click when a crewmate is not ready). Against the AI, a change of unit moves every browser to the first free stations of the new unit. Alone, the leader plays solo: the AI crews every station it does not hold.

During a mission the uConsole shows the umpire screen with the join line and the leader's name, the leader's host bar keeps Save and Load and adds **Back to the lobby**, which ends the mission for everyone; the crew keeps its stations across every mission start, load and return. The leader hands the lead over with **Hand over the lead** beside a crewmate's name; a leader that stays away for a while passes it on to the next crewmate by itself. Phone lookouts and observers never lead.

`Esc` on the uConsole leaves server mode for the main menu. Nothing of it is saved.

## Remote Crew page (F9) {#mp-f9}

`F9`: Commander / Remote Crew - lets browser clients on the LAN take stations. The page has one switch, **Multiplayer**: `Enter` turns it on on the first local network address, or, when the uConsole has no network, on its own hotspot (if the hotspot helper is installed; the uConsole installer `install.sh` sets it up when it can and otherwise prints a note). The hotspot keeps its Wi-Fi name and password from one start to the next, so a phone or PC that joined once reconnects by itself. On the hotspot the page shows the two steps together: **1** the Wi-Fi QR code with name and password, **2** the page QR code with the join code.

![Remote Crew administration (F9) on the uConsole](figure:commander-options)

**Crew** lists the players and their stations. **Advanced network settings** shows the network mode (LAN or hotspot), the address and the port for a manual choice; they change only while multiplayer is off. There, while multiplayer is off, **New hotspot password** makes a new hotspot password and keeps the name; every device then has to join again with the new Wi-Fi QR code.

A free station is taken at once with all of its rights (including direct fire and live sonar audio where the station has them); a station a crewmate holds is requested, and the holder (who sees the request with Hand over / Keep station buttons) or the host can hand it over. A station always carries its full rights; the host can revoke a station, grant or withdraw the SimLog (roster key `L`) at any time, and can make up to two browsers read-only observers (roster key `O`): they watch any station of either unit without holding it, cannot command, and get the SimLog with a debrief timeline and JSON export.

The crew pages open in the host's saved language (`F10` options on the uConsole); the English/Deutsch button in the browser's status bar switches that browser alone. The crew page is built for Chrome or Chromium (also Edge) on a desktop PC; another browser shows a hint above the pairing code, and a page that cannot start there says so instead of loading forever. After a host update an open browser page reloads itself once, so it always runs the web client that matches the host.

A browser station has three columns: the contact list on the left, the display in the middle, the station panel on the right with the contact detail below it. To give the controls room without scrolling, an empty contact list folds to a narrow rail and the contact detail to its title bar while no contact is chosen; both open again as soon as there is something to show, and keep any state you set by hand. The mission overview is one **Orders** line at the top of the station panel and opens with a click. A value with nothing reported yet shows as a grey dash; hovering it gives the reason. On a phone, language, sound, microphone, settings and tools sit behind the ☰ button.

## Crew mode, solo mode and the web host {#mp-modes}

Remote Crew normally runs in **crew mode**: each browser holds the stations the host grants it, and the AI or the uConsole crews the rest. Started with `--solo-crew`, it runs in **solo mode** for that launch only: one paired browser holds every station of its unit and may also use the host commands save, load and new game and the own-mission library (chapter Mission and unit editor). Editors, options, quit and the network settings stay on the uConsole, and there is no pause in either mode.

In solo mode the one browser holds all nine frigate stations, or with **Play the submarine** in the host bar all seven submarine stations (and back with **Play the frigate**). The host's **New game** dialog picks the **Side** too (*Frigate F-217* or *Submarine*); as the submarine the frigate, its helicopter and the patrol aircraft are run by the **AI hunters**. A solo browser (Remote Crew solo mode) chooses the side in the same way: its **New game** dialog has a *Side* field, and with *Submarine* the session takes the submarine's seven stations while the AI hunters crew the frigate.

`--web-host` runs one browser-only room behind a separate HTTPS reverse proxy (`--public-origin` names its address); it does not autosave. The setup is described in the web-host guide of the project documentation.

## Phone lookout and periscope {#qs-phone}

A phone can stand the watch as the frigate's bridge lookout or on the crewed submarine's periscope. `F9` shows a second QR code, **Phone lookout**, for the address `https://<address>:<port+1>/lookout`. Scan it, accept the certificate warning once, choose the watch station, and type the pairing code shown next to it (the code is never in the QR code). Type it as shown, with or without the space and in any case; look-alikes such as O and 0, I, l and 1 or S and 5 are read by position. "Wrong pairing code" means exactly that and shows the code the game received; if the game refuses the address itself, the page says so.

![Binoculars and periscope by day and at night (frigate left, submarine right)](figure:sight-overview)

- **Certificate:** the game makes its own certificate for its LAN address (kept in `~/.u-jagd/tls/`, renewed when the address changes). The phone warns once because no authority signed it: on iPhone tap *Show Details*, then *visit this website*; on Android Chrome tap *Advanced*, then *Proceed*. Phones only hand the gyroscope and the microphone to such a secure page.
- **Looking around:** tap *Gyro* and turn the phone like binoculars; tilt it to look up or down. Without the gyroscope, swipe. *Ahead* looks at the bow again, *Zoom* cycles the magnification. On the periscope the phone trains the periscope itself, and *Range* takes a stadimeter range on what is in the crosshair.
- **Reporting:** tap *Report by voice* and say what you see, for example "Ship bearing 040, range 5 miles", "aircraft starboard 30" or "torpedo" (the line of sight then counts as the bearing). Categories: contact, ship, warship, merchant ship, aircraft, submarine, torpedo. Or tap the target in the picture and pick the category.
- **Confirmation:** a report counts only when the lookout really has something of that kind within 10° of the bearing (and, with a range, within 40 % or 1 NM of his estimate). Then it appears on the bridge as a lookout track and in the event log, and the crew browsers speak it. A report of nothing is refused, and the phone vibrates twice.

While a phone holds the bridge lookout, the lookout no longer reports ships, aircraft or torpedoes by himself: only what the player calls reaches the bridge (land is still reported automatically). On the submarine the periscope picture stays with the attack computer, and the crew's own "in sight" notices give way to the phone's reports. Speech recognition uses the phone browser's speech service (Chrome on Android, Safari on the iPhone with Siri and Dictation switched on; Firefox and the other iPhone browsers have none, tap the target there). When it fails the page names the reason. Nothing of the phone lookout is saved.

## Browser keys {#mp-keys}

In the Remote Crew browser (Commander, `F9`) stations are operated with buttons or with the same keys as on the uConsole; every control with a key shows it as a blue key cap after its label, and a key never acts while the cursor is in a field. Keys that send an order or fire only press the matching control, so they pass the same checks as a click:

<!-- keys:web -->

## Not in the browser {#mp-gaps}

The browser follows the uConsole station by station. The solo browser also has the main menu's **Logbook** (service record, best scores, awards and what the enemy has learnt, for the frigate and the submarine) and **Training** (the six lessons; a submarine lesson first switches the browser to the submarine). What the browser does not have yet:

- **Training in server mode:** the server-mode lobby starts missions only; lessons start from a solo browser or on the uConsole.
- **Logbook page extras:** switching "enemy learns" on or off (`L`), the language model's review of the service record and the after-action report stay on the uConsole's logbook page; the browser shows the record read-only.
- **Damage control:** choosing a compartment with `←`/`→` has no key; pick it in the compartment list.
- **Helicopter:** the keys of the acoustic pages that only exist on the uConsole's helicopter display have no browser counterpart.
- **Station stepping:** `Tab` does not step through the stations; use the station's number (`1`-`9`), and the same number again turns its page.
- **Host-only functions:** options, editors on the uConsole, quitting, network administration and credentials stay on the uConsole by design.
