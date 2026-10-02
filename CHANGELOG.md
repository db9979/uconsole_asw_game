# Changelog

[Deutsches Änderungsprotokoll](CHANGELOG.de.md)

Every U-Jagd release, newest first. The [README](README.md) shows only the latest one.

## 1.3.145

Release 1.3.145 puts the echo sounder into the browser's Navigation station
of the submarine: the seabed sounded over the last ten minutes beside the
boat's own depth, thin water under the keel in amber and red, and the charted
profile ahead on the ordered course with the obstacle the chart check found.
Save format v48 unchanged.

## 1.3.144

Release 1.3.144 makes the uConsole draw faster on both sides. Text widths,
wrapped lines and rendered text are now remembered and reused, and the red
light of silent running no longer blends the whole screen twice per frame.
In a headless benchmark a submarine frame takes about a quarter of the time,
with silent running about a sixth, and a frigate frame less than half.
`tools/bench_draw.py` measures every station of both sides. Save format v48
unchanged.

## 1.3.143

Release 1.3.143 gives the submarine's navigation dead reckoning and a route.
Dived, the navigated position slowly drifts from the true one (less on a
nuclear boat); a GPS fix with the mast up at periscope depth for 20 s puts it
back. The crew's chart lies where the navigator believes it lies, the chart
check ahead and the route steer from that position, and the pilot chart shows
the error estimate and the age of the fix. A right click on the chart adds a
waypoint, `W` lays a zigzag or expanding-square search and `Backspace` clears
the route; the browser has the same buttons and a click mode. Saves move to
format v48; v38 to v47 saves still load.

## 1.3.142

Release 1.3.142 lets the submarine's Weapons station set the seeker of the
next shots like the frigate: search pattern straight, snake, circle or helix
(`X`) and the enable point 0.6 to 3.0 NM before the datum (`,` and `.`), in
the browser on the Weapons card. The defaults keep the earlier shot. Save
format v48.

## 1.3.141

Release 1.3.141 adds the manual chapter "Submarine" with each boat station's
job and a five-step standard procedure for all seven stations. F1 on the
submarine side shows the procedure of the station in use, and the manual
reader opens on the submarine chapter. Save format v47 unchanged.

## 1.3.140

Release 1.3.140 adds three uConsole pages. The submarine's Navigation station
opens on a pilot chart with an echo sounder: charted depths around the boat,
water too deep for it in red, the ordered course ahead, the seabed of the last
ten minutes and the depth ahead; a click on the chart orders the course. The
helicopter's status page is a console with lamps, a fuel tank, a return rose
and its stores. The radio room's first page shows the HF/DF bearings and fixes
on a chart beside the intercept list. Save format v47 unchanged.

## 1.3.139

Release 1.3.139 balances scenarios 11 to 20 at full length, measured with
AI-against-AI games on six seeds each. Trail now asks the frigate to hold
contact for 80 % of the time, and a lost contact counts sooner. In the duel the
submarine starts 8 to 12 NM out, the damaged homecoming's goal lies nearer, and
in Rescue under threat the frigate starts farther from the rafts. Search group
now lasts 4 hours with the first submarine 8 to 14 NM out, and Hunter group
starts the boat 4 to 6 NM out with its goal just beyond the frigate and a
90-minute limit. The short variants are unchanged. Save format v47 unchanged.

## 1.3.138

Release 1.3.138 turns the campaign into a theatre campaign for both sides. A
sector chart shows three open hotspots, each one of the side's scenarios with a
role (patrol, strike, defence), plus the decisive battle once the front
situation reaches 75. Wins and losses move the situation and the enemy
strength, ignored defence hotspots count as losses, and new hotspots open by
the situation, so the campaign branches. It ends in victory, defeat or a draw
after twelve missions. Older campaigns carry on with their results. Save
format v47 unchanged.

## 1.3.137

Release 1.3.137 brings the group hunt. In the new scenarios Search group
(frigate 11) and Hunter group (submarine 11) the destroyer LUETJENS sails with
the frigate. OPZ page 4 and the browser's OPZ command it: formation, search or
prosecute a point, hold or auto, active sonar, weapons release and ASROC on
order. Its passive bearings cross with the frigate's into fixes, and its pings
fix nearby submarines. Saves move to format v47; v38 to v46 saves still load.

## 1.3.136

Release 1.3.136 lets two crews play each other. The lobby's new row Opponent
switches between the AI and a second crew: browsers join the frigate (blue) or
the submarine (red), whichever has fewer people, the teams are fixed for the
round, each unit has its own voice channel, and each team gets its own result.
With the lobby station "none, host only" the uConsole shows an umpire screen
without either side's picture. Save format v46 unchanged.

## 1.3.135

Release 1.3.135 adds Free patrol as the last entry of both sides: no time
limit, just sail. HQ keeps sending radio tasks (the frigate also gets sector
patrols; the submarine gets attack, landing, supply and recon orders), and
random encounters and events keep coming: submarines, merchant groups, air
raids, AI hunters, incidents at sea. Points add up for as long as the ship or
boat stays afloat; weather and time are chosen at the start as usual. Saves
move to format v46; v38 to v45 saves still load.

## 1.3.134

Release 1.3.134 brings ten new scenarios, so each side now has ten. The
frigate gets 5 Convoy escort, 6 Flaming datum, 7 Trail (peacetime, weapons
tight, hold sonar contact), 8 Replenishment at sea, 9 Rescue under threat and
10 Harbour defence; the submarine gets 7 Duel, 8 Damaged homecoming, 9 Agent
pick-up and 10 Listening post. Key `0` picks the tenth row. An AI plays the
other side in each, every one has a short variant, and both sides win them in
AI-against-AI games. Saves move to format v45; v38 to v44 saves still load.

## 1.3.133

Release 1.3.133 lets you build your own missions for both sides and share them.
In the Mission Editor's overview the player side can now be the frigate or a
submarine you place yourself (the AI then crews the frigate), and the editor
gives fairness hints. Own missions appear in the start menu (`O`), in the
multiplayer lobby and in the browser's "New game" dialog. `Ctrl+E` shares a
mission with its own units into the exchange folder `~/.u-jagd/share`, `Ctrl+I`
lists and imports the files there and `O` opens the folder. In solo mode the
browser has an "Own missions" page to list, download, upload, edit, delete and
start missions, with a Mission Planner on a sector map. Save format v44
unchanged.

## 1.3.132

Release 1.3.132 numbers each side's scenarios from 1. The frigate list reads
1 Patrol, 2 Double hunt, 3 Nuclear intercept, 4 Free hunt; the submarine list
1 Breakthrough, 2 Reconnaissance, 3 Convoy attack, 4 Strait blockade, 5 Combat
swimmers, 6 Supply ship escort, and the number keys follow the list on the
screen. The manual counts the submarine scenarios the same way. Save format v44
unchanged.

## 1.3.131

Release 1.3.131 adds short missions. The briefing, the campaign screen, the
multiplayer lobby and the browser's "New game" dialog now have a length row:
every fixed scenario except the free hunt can be played as a short mission of
30 to 60 minutes with the same goal, a shorter time limit and a start closer
to the action, so a mission fits into an evening or a break. Each short
variant was tuned with AI-against-AI games so that frigate and submarine win
about equally often. Saves stay format v44.

## 1.3.130

Release 1.3.130 adds a graphics level under Options: "Economy" saves the
uConsole's processor (no radar afterglow, a calmer menu background), "Normal"
shows every effect and "Full" also smooths chart lines; the uConsole starts at
Normal, Windows at Full. In a window or full screen larger than 1280 x 720 the
picture is now scaled sharply: whole factors repeat pixels exactly and other
sizes no longer show uneven text rows or blur. The level never changes what a
station shows as information. Saves stay format v44.

## 1.3.129

Release 1.3.129 makes the game more robust. A nightly soak test now plays
every mission on both sides for an hour each with random input at every
station, saving and reloading along the way, and opens a bug report when
anything breaks. Its first run found that a submarine mission saved while a
sonar contact was selected could not be loaded again; that is fixed. Saves
stay format v44.

## 1.3.128

Release 1.3.128 keeps your saved games across updates. A save slot or autosave
written by an older release, back to release 1.3.98 (save format v38), now
loads: it is brought up to the current format step by step and then checked as
strictly as before, so an update no longer throws away a mission you
interrupted. The update notice warns about saves only when they are too old
for the new release. Saves are written as format v44.

## 1.3.127

Release 1.3.127 keeps a mission alive when something goes wrong. A station
view that fails to draw now shows "Display fault" while the mission and every
other station keep running. A fault in the simulation puts the mission back to
its recovery point, an in-memory copy at most one minute old, and says so in
the feed; Remote Crew browsers get their stations back as after a load. After
repeated faults, or an error that still ends the game, the recovery point
becomes the autosave, so "Continue mission" resumes it. Every caught fault is
written to crash.log for a bug report. Saves stay format v44.
## 1.3.126

Release 1.3.126 lists the scenarios by side. After "New game" you first pick
the frigate or the submarine, and the list then shows only that side's
missions: Patrol, Double hunt, Nuclear intercept and Free hunt on the frigate;
Breakthrough, Reconnaissance, Convoy attack, Strait blockade, Combat swimmers
and Supply ship escort on the submarine. The titles therefore lose their
"(submarine)" suffix, which read as if the frigate were meant to play them.
The multiplayer lobby and the browser's New game dialog filter the same way,
and Esc in the scenario list returns to the side choice. Save format v44
unchanged.

## 1.3.125

Release 1.3.125 adds three new missions that both sides can play, each with the
AI on the other side. In "Strait blockade" (8) the submarine must slip through
the nearest narrow passage while the frigate guards the gate; merchant traffic
runs through it and an AI boat hides in their noise. In "Combat swimmers" (9)
the submarine must lie still near a coast for ten minutes at periscope depth
and dead slow to lock out its swimmers, and the frigate patrols the coast
section. In "Supply ship escort" (10) the frigate escorts a zigzagging supply
ship and one torpedo hit decides the mission. The places come from the real or
generated coastline of each world. The scenario menu takes keys 1 to 9 and 0.
In AI-against-AI test runs (six seeds each) every new mission went three times
each way: the AI submarine sneaks at 4 kn, ignores pings from farther than 5 NM,
fires back down a closer one and, in the strait and off the coast, snaps a shot
at a loud frigate; the strait stays busy with six merchants shuttling through
it, and HQ passes the frigate no submarine datum in scenarios 8 and 9. Save
format v44; older saves do not load.

## 1.3.124

Release 1.3.124 evens out the AI frigate and the AI submarine. In the
frigate scenarios the AI hunters now run down HQ's start report of the threat
and a lost submarine bearing, ping a bare bearing only every 10 minutes so a
ping that finds nothing no longer sends the submarine running, and no longer
take a long-radiating ship radar for a submarine mast. In the submarine
scenarios a mission submarine keeps its course through a ping and gives way
only to a torpedo, and the frigate guards its post: against a breakthrough it
stays by its patrol position with no patrol aircraft, and against a
breakthrough or reconnaissance it fires its own torpedo from 3 NM and keeps its
helicopter within 8 NM. The breakthrough submarine skirts the frigate's patrol
position, the reconnaissance report counts within 5 NM and the convoy
submarine fires from 3 NM. Saves move to format v43 (the hunters' leads).

## 1.3.123

The submarine gets a towed buoy antenna. In the radio room (B, or the browser's
Radio room card) the crew streams it about 280 m astern; it copies HQ's
broadcast down to 60 m at 6 kn or less, receiving only. Above 10 kn the cable
parts and the buoy is lost for the mission. Close in, the frigate's lookout and
surface radar can find the small buoy on the water. Saves are now format v42;
older saves do not load.

## 1.3.122

Release 1.3.122 makes the browser stations steadier to operate. A drop-down
list that is open or in use, such as the ESM classification on the submarine,
the fire-control target or the wire, torpedo type and damage-team choices, no
longer closes or loses its choice when the station updates; it catches up once
it is left. Buttons in updating lists (ESM emitters, tubes, bulkheads, radio
channels and tasks, crew and patrol-aircraft orders) stay in place, so a click
is no longer lost when an update lands mid-click. Saves stay format v41.


## 1.3.121

Emergencies aboard join the incidents at sea. A man can go overboard from the
frigate: the general alarm sounds, a drifting mark goes on the chart, and the
Bridge recovers him within 0.1 NM at 5 kn or less, or the helicopter hovering
over him (+100 points; lost after 20 minutes, -300). The steering gear can
fail: the rudder jams for 60 s, then turns at half rate from the emergency
position for 10 minutes. On a diesel submarine the snorkel head valve can jam
(no charging for 15 minutes; the AI boat stays deep) or battery gas has to be
vented (half charging rate). The Bridge crew assist steers onto a man overboard
itself. Up to six incidents per mission.

## 1.3.120

Release 1.3.119 adds shipboard atmosphere to the sound. Action stations on the
frigate ring the general alarm bell through the ship, and in a heavy head sea
at speed the bow is heard slamming each time it pitches down hard. The
submarine rings only a quiet alarm bell, and its ventilation fans are heard
running down when silent running starts and up again when it ends. The uConsole
and the Remote Crew browsers play the same cues, all synthesized at runtime.

## 1.3.119

Release 1.3.118 lets you choose the weather and the time of day. Every
scenario's briefing, the campaign screen before sailing, the multiplayer lobby
and the browser's "New game" dialog now offer weather (random, fair, rain,
storm, fog) and time of day (random, dawn, day, dusk, night); random keeps what
the seed gives. A chosen weather holds for the whole mission with its sea state
in a matching band, and the clock runs on from the chosen time.

## 1.3.118

Release 1.3.117 lets the eye find a raised periscope. A periscope or snorkel
head of a dived submarine now pulls a feather that grows with speed: the bridge
lookout, the phone lookout and the crews of the helicopter and the patrol
aircraft see the full plume from 8 kn at almost 3 NM on a clear, calm day, a
slow head only at about 1 NM, and hardly anything at night or in a heavy sea.
Close in the lookout recognizes the periscope and calls it with a banner;
aircrew sightings reach Operations as HELO-EYE and MPA-EYE tracks. This works
the same for AI boats and the crewed submarine, whose crew warns "feather
visible, reduce speed" when it runs faster than 5 kn with a mast up.

## 1.3.117

Release 1.3.117 brings the sea to life. The eyepieces show water columns, fire,
smoke and sinkings; charts move smoothly and pings and detonations ring out;
needles and the telegraph move with mass and the telegraph bell rings; the
periscope comes up out of the water with water on the glass. A red light comes
on at night and on an alarm (switchable), and the station tabs carry alarm lamps
on both sides, on the uConsole and in the browser. After a mission the debrief
plays back at 10x or 60x, in the browser too. At night warm water glows where it
is stirred, so wakes and torpedo tracks are seen farther on both sides. A hard
turn at speed leaves a knuckle, a bubble slick that masks sonar, gives a false
echo and can lure a wake-homing torpedo. Wrecks and rocks return echoes and
wrecks give MAD anomalies. Storms bring lightning in the eyepieces, thunder,
heavier rain and sferics that crackle on ESM and spread HF/DF bearings. In a
heavy sea the helicopter launches and lands only in a quiet period; a deck-
motion gauge shows it, and slowing down helps. Saves are now format v41; older
saves do not load.


## 1.3.116

Release 1.3.116 gives the same function the same key at every station, on the
frigate and on the submarine. Ctrl+Enter is the only fire key (T and E no
longer fire), Q/E zoom everywhere including the CIC radar range, the
binoculars and the periscope, and Page Up/Down turn the pages of every
station. Course, speed and depth are entered with C/V/D on both sides and the
torpedo run depth with T. The submarine now uses the frigate's G for action
stations, A for silent running, V for the decoy and W/M/U on its crew page;
the patrol aircraft takes the helicopter's keys, both aircraft radars sit on
Ctrl+R, and the helicopter and ELOKA follow the sonar (Shift+A ping, G release
to CIC, J audio). A click on the crew message box is no longer taken by a
station key underneath it.

## 1.3.115

Release 1.3.115 seats new players in a sensible order. A browser that pairs
while the multiplayer lobby is open now takes the first free station of the
uConsole's unit, the stations that need judgement first: on the frigate Bridge,
Sonar, Weapons, Helicopter, OPZ, ELOKA, Radio, Engine and Damage control, on the
submarine Command, Sonar, Weapons, Mast and ESM, Navigation, Engine room and
Radio room. The AI crew keeps the routine stations well. Every player can still
change unit and station at any time.

## 1.3.114

Release 1.3.114 makes a player's order win over the AI crew. In multiplayer
with the crew assist, the AI command dived the submarine every few seconds and
so pulled down the periscope a player had raised at the mast or in the radio
room; it now keeps the boat at periscope depth while a player holds the mast
up. A station the AI mans no longer overrides what a player at another station
commands: course, depth and evasion stay with a player at Navigation, speed and
silent running with one in the engine room, trim and damage control with one
at command, and a raised mast stays up on an alarm while a player at command or
in the radio room holds it. On the frigate the AI Bridge no longer steers over
a player in the engine room, the AI weapons and patrol aircraft keep a target a
player designated, and a contact picked on the uConsole stays picked. A lobby round started
without any browser is now a solo game with the crew assist off.

## 1.3.113

Release 1.3.113 lets you play the uConsole entirely with the mouse and makes
the charts and the sea traffic easier to read. A click on a key in a
station's key bar presses it (held like the key), numbered tabs in the top bar
switch stations, a click on the course, speed or depth dial orders that value,
numeric entries show a keypad, menu and dialog rows are clickable, the wheel
moves through menus and a right click cancels. Every chart now draws the own
track, the earlier positions of each contact and the earlier bearings of the
selected contact, and chart labels move aside instead of covering each other.
Cargo ships, tankers and passenger ships steam on steady courses between ports
and the edge of the sea area, give way to each other under the collision
regulations and run from nearby detonations.

## 1.3.112

Release 1.3.112 makes multiplayer simpler to host. F9 is now one switch,
Multiplayer on or off: it uses the first local network address, or opens the
uConsole's own hotspot when there is no network; network mode, address and
port sit under the advanced settings. The hotspot keeps its name and password,
the uConsole installer sets it up, and the lobby and F9 show two steps: the
Wi-Fi QR code, then the crew page QR code. A browser that asks for a station
another player holds now asks that player, who can hand it over in the
browser; every station always carries its full rights. The command line has
one flag, --multiplayer, which opens the lobby, and the Windows program starts
straight into the game without a starter window.

## 1.3.111

Release 1.3.111 adds an engagement sketch to fire control on both sides. The
frigate's Weapons station and the submarine's Weapons page now draw, north up
around the own ship, the torpedo's reach, the bearing to the target and, once
a range is known, the estimated position, the intercept point from the TMA
course and speed and the torpedo run to it, taken only from the contact's
observation. The submarine's Command and Navigation pages get labelled round dials for
course, depth (test and crush depth marked) and speed like the frigate's
bridge, and the submarine's radio room boxes are sized to their text again,
so the HQ order no longer runs through the frame.

## 1.3.110

Release 1.3.110 no longer installs updates on its own. When a newer release
is published, the start screen and the main menu show its version, its
changelog entry in the game language and a warning when saved games of this
version (the autosave too) will not load in it, plus the button **Update now**
(key U or a click). Only that button installs it: on the uConsole the game
closes, updates to the release and starts again (the old background update
timer switches itself off); the Windows program downloads the new file in the
background, checks it, swaps itself and restarts. Offline no notice appears.

## 1.3.109

Release 1.3.109 lets the AI man every free station. The new crew assist
(Shift+F2, always on in a mission started from the multiplayer lobby) crews
each station of the frigate and of a crewed submarine that nobody holds, so
every player can stay on one station: the station on the uConsole's screen and
every station a browser holds stay with their player, and a station released
in the browser ("Hand over to AI") goes straight back to the AI. On the
submarine the AI commands evasion, patrols or closes a known frigate, keeps
the tubes loaded and fires at a close fix, snorkels to charge, keeps the trim
and sends the damage-control teams. In the lobby the uConsole can also be
host only (station "none, host only"): it plays no station, and the browsers
and the AI crew every one. Saves are now v40.

## 1.3.108

Release 1.3.108 gives the AI reconnaissance submarine a real periscope
search. In the reconnaissance mission played from the frigate, the AI boat at
periscope depth no longer sights the frigate just by range and visibility: it
raises its periscope for a 24 s look every 90 s, sweeps round from the bow
and makes the frigate out only where the lookout's contrast model at 2.5 m eye
height allows (light, moon, visibility, sea state, land in the way). While the
periscope is up it counts as a raised mast, so the frigate's surface radar and
the patrol aircraft can catch it. Night, fog and heavy seas now shield the
frigate, and every look is a risk for the boat.

## 1.3.107

Release 1.3.107 makes the AI hunters and the AI submarines use the radio
spectrum more like real crews (save format v39). When nobody sails the
frigate, its ELOKA plots an ESM bearing on a submarine's mast radar as a line
from the ship's position, one per nautical mile run, and crosses the newest
line with an earlier one into a position datum for ship, helicopter and patrol
aircraft (not for a friendly escort's ASROC). An AI submarine at periscope
depth that holds the frigate now reports it to its headquarters once every
30 minutes with a 20 s HF call, which the frigate's HF/DF hears and can take
bearings on, whoever crews it. The ESM lines are saved, so a loaded game
continues the hunt unchanged.

## 1.3.106

Release 1.3.106 adds a multiplayer lobby. The new main-menu entry Multiplayer
starts Remote Crew in crew mode and shows the QR code and join code; browsers
pair, pick their unit and stations and press Ready, and everyone sees the
mission, the uConsole's unit and station and each crewmate's stations and
ready tick. The host chooses the mission, which unit the uConsole plays and
its own station, then starts a five-second countdown that every browser sees,
and the mission begins for all at once. A mission started from the lobby
returns everyone to the lobby when it ends.

## 1.3.103

Release 1.3.103 turns the submarine's Damage control card in the browser
into a damage-control console like the frigate's: an annunciator panel with
the master lamp (power, water, leaks, fire, gas, lost compartments, shut
bulkheads, teams, bilge pumps, wounded, trim, high-pressure air and over
depth) above a side view of the pressure hull with water rising from the
keel, fire glow, gas haze, leaks, shut bulkheads, a state lamp per
compartment and the team badges, and gauges for trim, floodwater and
high-pressure air; the table and the team orders stay below.

## 1.3.102

Release 1.3.102 lets the bridge lookout call out the navigation lights he
sees at night and in poor visibility, with his reading of them: both side
lights mean a vessel is heading for the ship and are called aloud, green or
red alone show her starboard or port side, the stern light alone that she is
going away, and all-round lights her work (fishing, pilot, restricted in
ability to manoeuvre, clearing mines) or, flashing, an aircraft. He calls a
contact's lights again only when what they tell changes, at most every two
minutes, and the Remote Crew bridge lists the calls with the other reports.

## 1.3.101

Release 1.3.101 brings the manual's "Not modelled" lists up to date: the
Operations room does fuse clearly matching reports of different sensors by
itself, and the radio room does call HQ with contact reports and support
requests; both lists now say only what is really missing.

## 1.3.100

Release 1.3.100 brings the sonar, electronic warfare, radio and weapons
stations up to the console style of the engine and damage screens. The
frigate's and the submarine's sonar get darker phosphor panels, a listening
console with lamps for ping, audio and peak hold and a north-up bearing rose
with listening beam, baffles, own course and contact bearings; each contact
row carries a lamp and a signal-to-noise bar. The helicopter's dipping sonar
shows lamps for dome, ping and water entry, a water-column gauge and bearing
wedges as wide as their error, and its waterfalls use the ship's phosphor
colours. ESM and HF/DF get bearing roses, the weapons pages tube and interlock
lamps and magazine tanks. In the browser the sonar and helicopter get the
same rose and lamps, the weapons card lamps and tube columns and the ESM scope
a graduated rose.

## 1.3.99

Release 1.3.99 turns the damage screens into damage-control consoles on the
uConsole and in the browser. On the frigate's uConsole ship plan, water rises
in each compartment from the keel, a fire glows red and a lost compartment is
hatched; each compartment card carries a state LED, flood and fire values with
LEDs and bars and numbered team badges. The submarine's Damage page is a
compartment mimic from stern to bow with water level, fire glow, gas haze,
leak/fire/gas/bulkhead LEDs and team badges, and lamps for the selected
compartment and the power. The browser's Damage card opens with an
annunciator panel above a side view of the ship and gauges for list, trim and
total damage; a click on a compartment still sends the selected team.

## 1.3.98

Release 1.3.98 wounds people. Hits, fire, flooding and gas hurt the crews of
the frigate and of every submarine at their sonar, weapons and damage-control
stations; every empty post slows that station (recognition, reloading and
flooding tubes, repairs), and every third wounded man is out for the mission.
The damage-control officer sends the medical team (frigate Damage page 3 `M`,
submarine `Shift+M`, browser button) and re-mans the worst station with up to
two men from the resting watches (`U`, submarine `Ctrl+M`), who then lack their
rest; AI ships re-man on their own. Saves are now v38. This completes nine
improvements from 1.3.90 on, each with a counterpart for the submarine side.

## 1.3.97

Release 1.3.97 adds an ASW rocket launcher to the frigate (Weapons `R`,
browser button): six-round salvoes 0.4 to 3 NM onto a fresh range fix, 36
rockets, one minute to reload. `Shift+R` fires a shallow defence line along a
torpedo warning's bearing that destroys a torpedo it goes off next to. The
splashes warn every submarine within 3 NM: AI boats evade and the crewed
boat's sonar room reports their bearing. The AI frigate uses both. Saves are
now v37.

## 1.3.96

Release 1.3.96 adds a sonar class library: the DEMON page lists the three
catalogue classes that best fit the operator's shaft, blade and LOFAR marks,
with a fit in percent, and the F8 analyzer sorts the whole catalogue by fit.
The submarine's sonar room and the web sonar station have the same library.

## 1.3.95

Release 1.3.95 lets both sides call HQ freely: the radio room sends a
contact report with its freshest fix (`K`) or asks for support (`H`). Each
call is on the air for 20 s and can be DF'd by a hostile submarine with its
antenna up, so the radio becomes a sensor for both sides; accurate reports
score at the mission's end. Saves are now v36.

## 1.3.94

Release 1.3.94 models baffles: the frigate's hull array and every
submarine's hull sonar no longer hear within 30 degrees of their own stern,
the towed array and the VDS still do. Bridge and crewed boat clear their
baffles with `Ctrl+B` (browser button): 60 degrees to starboard for two
minutes, then back. An AI submarine close in the frigate's baffles after a
ping trails her instead of running. Saves are now v35.

## 1.3.93

Release 1.3.93 adds a logbook to the main menu: every finished mission of
the side the uConsole played is filed in `~/.u-jagd/logbook.json` with the
best score per mission and five awards per side. The submarine now gets a
score from its outcome, so both sides can earn the same.

## 1.3.92

Release 1.3.92 adds realism levels Beginner, Standard and Realistic
(options, kept per mission). They tune only the computer opponent (AI
submarine attack eagerness and firing threshold, AI frigate classification
and helicopter delays) and the operator assistance; the mission score is
scaled by 75, 100 or 125 %.

## 1.3.91

Release 1.3.91 brings incidents at sea. From 20 to 40 minutes into a
built-in mission up to four come over the teletype: a drift net across the
track (running over it costs points and fouls a streamed towed array or VDS, a
shallow submarine fouls it loudly), a weather front with HQ's warning, a
freighter without AIS to identify, and a pod of whales. HQ passes net, front
and whales on to the submarine; the AI frigate steers round reported nets.
Saves are now v34.

## 1.3.90

Release 1.3.90 makes flooding torpedo tubes audible. A submarine flooding a
tube and opening its outer door makes a transient that the frigate's sonar
reports as a warning on a measured bearing: loud flooding out to 8 NM, slow
quiet flooding within 1.5 NM. The crewed boat can flood quietly (`Ctrl+M`,
browser button); AI boats flood quietly and early on a fix, loudly just
before a shot on dry tubes. Saves are now v33.

## 1.3.89

Release 1.3.89 turns the uConsole engine rooms into machinery control
consoles in the splash style. On the frigate the telegraph becomes a column of
lit steps beside a large speed gauge, shaft RPM and own-noise gauges and plant
lamps; the Systems page has an annunciator panel with a master lamp, the fuel
bunker as a tank column, roll, pitch and list gauges and a mimic of the ship's
sections from bow to stern with water level, LEDs and numbered repair teams.
On the submarine the Plant page shows gauges for speed, battery (depth on a
nuclear boat) and own noise with mode lamps, and Stores shows tank columns
for battery, AIP, diesel and absorber and a bar per telegraph step.

## 1.3.88

Release 1.3.88 makes the OPZ fuse reports that lie on top of each other by
itself: a ship seen by radar, lookout and AIS is now one contact instead of
three. Only clear matches are fused (at least one position fix, no second
candidate from the same kind of sensor); ships close together stay apart and
appear as suggestions, and `Shift+L` still separates a fusion. The fused
reports disappear from the track list and the chart, each row ends with
sensor tags (`R` radar, `V` lookout, `A` AIS, `E` ESM, `S` sonar ...), and the
track details and the Remote Crew OPZ list a fusion's sources by name. Saves
stay v32.

## 1.3.87

Release 1.3.87 gives the frigate's engine room in the browser the same
machinery control console as the submarine's: an annunciator panel of status
lamps for shafts, plant, cavitation, fuel, speed limit, machinery damage,
fires and flooding aboard, round gauges for speed, shaft RPM, own noise, fuel,
roll and pitch, the fuel bunker with endurance and range, and a mimic of the
ship's sections from bow to stern with water level, fire lamps and repair
teams. The console only shows; the orders stay in the station panel.

## 1.3.86

Release 1.3.86 makes the 3D models solid. Until now their faces were drawn
in the order of their centres, so from many angles a far face was painted over
a near one: decks showed through superstructures, the far side of a hull
through the near side, and ships looked hollow. Every model is now split once
into a binary space partition that gives, from any side, an exact order from
back to front, on the uConsole and in the browser alike; hull plating is
closed and faces outward, and hulls, submarines and fuselages are drawn with
a finer grid. Deckhouses are no longer single blocks: they rise in deck tiers,
warships drawn in and raked, passenger ships stepping back in terraces,
merchant ships with a short wheelhouse and bridge wings on top; submarine
sails are streamlined. Saves stay v32.

## 1.3.85

Release 1.3.85 lets the helicopter switch its search radar off and on
(`Shift+R`, browser button): a radiating helicopter or patrol aircraft now
drives an AI submarine with a raised mast or snorkel deep for 15 minutes, a
silent one may catch it at the surface. The patrol aircraft flies MAD passes
over its search area (`V` at Operations page 3, browser button) and reports a
submerged hull it crosses as a MAD fix over the datalink. In the frigate
scenarios an AI patrol submarine far from the frigate and not being hunted
now and then torpedoes a merchant that passes close, and each merchant lost
costs 300 points. Measured AI against AI, mission outcomes stayed the same in
all 30 before/after pairs of scenarios 1 to 3 and 5 to 7; the double hunt lost a merchant
in 2 of 6 runs. Saves are now v32; older saves are not loaded.

## 1.3.84

Release 1.3.84 lets the Bridge autopilot find its way through channels, into
bays and round long coasts: when a stand-off detour does not clear a leg, a
path search on the chart plans the turning points (planning is also faster
than before). GitHub now runs the whole test suite with the browser tests,
the generated-file checks, the calibration and the smoke test on every change,
and two flaky browser checks are fixed: the phone lookout no longer falls back to the pairing screen when the host answers slowly right after pairing, and the status bar check measures with the bundled fonts. The manual no
longer says the frigate has no ASROC, and `tools/hw_report.py` turns a debug
run on the uConsole into the hardware checklist's table. Saves stay v31.

## 1.3.83

Release 1.3.83 turns the submarine's engine room in the Remote Crew browser
into a machinery control console. The large picture area, empty until now, shows
an annunciator panel of status lamps (dark when off, turquoise while running,
amber for a caution, flashing red for an alarm, each with its value) for motor,
snorkel, generator, battery, charging, fuel, air, main ballast, high-pressure
air, pumps, trim, power, flooding, leak, fire and gas, with a master lamp that
counts the alarms. Below it are round gauges for speed, battery, energy
balance, depth, high-pressure air and trim angle, tank columns for the stores
and tanks, and a mimic of the six compartments from bow to stern with the
water level, the lamps of each room, the bulkheads and the teams at work. The
orders stay in the station panel. Saves stay v31.

## 1.3.82

Release 1.3.82 makes the phone lookout's voice reports say why they failed.
Instead of a bare "Speech recognition failed" the page now names the cause:
Siri and Dictation switched off on the iPhone (with where to turn them on),
microphone not allowed, microphone busy, nothing heard, or the phone's speech
service unreachable; any other failure shows its error code. Chrome, Firefox
and Edge on an iPhone use Safari's engine without its speech service, so the
page there advises Safari for voice reports; tapping the target works
everywhere. A short report that Safari ends without marking it final is now
still read. Saves stay v31.

## 1.3.81

Release 1.3.81 shows the own ship's way in the lookout's pictures. Underway
the waves stream toward the eye looking ahead, away looking astern and from
bow to stern looking abeam, faster with more speed and without a jump when
speed or course change. Astern the wake runs as a band of smoother, lighter
water with foam between the two arms of the Kelvin wave out to the horizon,
and ahead the bow wave throws its spray into the lower edge of the picture.
This holds on the uConsole and in the browser for the bridge binoculars, the
lookout strip and the phone lookout; in the submarine's periscope the water
streams past with the boat's own speed. Saves stay v31.

## 1.3.80

Release 1.3.80 gives every ship, submarine and aircraft type its own 3D
model. Each of the 111 catalog types is built from the public main dimensions
and general arrangement of the real class (Wikipedia; generic types such as a
VLCC or a harbour tug use typical values): length, beam and draught, where
bridge, masts, funnels, guns, missile cells, flight deck, cranes and cargo
stand, a submarine's sail, planes, rudders and missile deck, an aircraft's
wings, tail and engines. The same type always looks the same, so a Type 23
no longer looks like an Arleigh Burke. The analyser, the Unit Editor and the
eyepieces (binoculars, periscope, phone lookout) show the real type the eye
sees, so it can be told by sight; the lookout report still names only what
was made out, and only the report reaches the OPZ. Saves stay v31.

## 1.3.79

Release 1.3.79 fixes pairing in Safari and Firefox, and with it the phone
lookout on an iPhone. The game's pages told the browser to send no referrer at
all; under the web standard Safari and Firefox then mark the pages' own
requests as coming from nowhere ("Origin: null"), and the game refused them as
a foreign address, so pairing failed with "The game refused this address".
The pages now keep the referrer to the game itself and still send none to any
other site; Chrome was never affected. Saves stay v28.

## 1.3.78

Release 1.3.78 shows the units as 3D models. In the unit analyser (`F8`) the
first page of every catalog profile is now a slowly turning 3D model of its
class, ahead of the sound and radar images; in the Remote Crew browser it can
also be turned by dragging. The Unit Editor shows the same model under the
selected profile and beside the fields of an opened one. Ships, submarines
and aircraft are the lookout's own silhouettes built out in 3D, so a unit
looks in the analyser as it does in the binoculars and the periscope
(warship, merchant, small craft, submarine, the lookout's helicopter for
every aircraft); torpedoes, decoys and animals, which no lookout sees, have
models of their own. The same models now stand in the lookout's binoculars
and the periscope on the uConsole, in the browser and on the phone, turned by
the angle on the bow the observer judges once he has made out the class.
Saves stay v31.

## 1.3.75

Release 1.3.75 also tidies the git tags on GitHub: when a new version is
published, the Windows build now deletes every older `vX.Y.Z` tag together
with its release, so only the newest release and its tag stay. The uConsole
updater only needs that newest tag. Saves stay v31.

## 1.3.74

Release 1.3.74 gives the submarine a fair chance against the computer-run
frigate. When you play the submarine, the frigate's crew now needs about 3
minutes to recognise a submarine by its sound and about 10 minutes to ready the
helicopter. On a bare bearing the helicopter only listens with its dipping
sonar, the patrol aircraft comes only for a position, and aircraft attack only
from a fix at most 2 minutes old. Breakthrough now runs 5 hours instead of 4
and Reconnaissance 2 hours instead of 3. Saves stay v31.

## 1.3.73

Release 1.3.73 fixes the Windows self-update: after **Install update** the
new U-Jagd-Windows.exe now replaces the running one and starts. Before, the
download stayed next to it as `U-Jagd-Windows.exe.new` and the old version
started again. The starter also deletes such a leftover `.new` file, and the
Windows build now tests the swap on every change. Saves stay v31.

## 1.3.72

Release 1.3.72 makes the computer-driven submarine in the breakthrough,
reconnaissance and convoy missions cleverer and gives the frigate more
torpedoes. The submarine now creeps at 3 kn while it hears pings or knows the
frigate is near, passes wide of a frigate it has located, lies in wait 2 NM
ahead of the convoy instead of chasing it, dodges pings quietly at 5 kn and
fires back at a located frigate far more readily. The frigate carries 8
torpedoes in Double Hunt and 6 in Intercept. Saves stay v31.

## 1.3.71

Release 1.3.71 lets you switch the Remote Crew server between English and
German. The Windows starter has a Language box at the top: the choice applies
to the starter at once and is saved in the settings, so the game window and
every crew browser start in it too. The browser pages now open in the host's
saved language instead of the browser's, and the crew page has a visible
English/Deutsch button next to Sound to switch for that browser alone; the web
host's admin page switches its own page with the saved server language. Saves
stay v31.

## 1.3.70

Release 1.3.70 redraws the sea in the lookout's binoculars, the lookout strip,
the periscope and the phone lookout. Instead of one big wave along the horizon
the waves now fill the whole sea in perspective: small and close together out
to a clean horizon, longer and higher toward the eye, every row moving with the
swell and coming at you, running away or sliding sideways with the wind, with
white caps in a rough sea. Both on the uConsole and in the Remote Crew browser;
saves stay v31.

## 1.3.69

Release 1.3.69 makes replenishment at sea something you can plan. The radio
room can now ask HQ for a supply ship itself (R on the Tasks page, or Request
supply ship in the browser) whenever fuel or any store runs short, at most
once every 20 minutes after the last one. Alongside, fuel now flows the whole
time and the stores come over in five loads: torpedoes, ASROC, depth charges,
Nixie decoys and CIWS and gun rounds, each load a share of what is still
missing, so breaking away early keeps what already came over. The Tasks page
shows fuel, torpedoes, ASROC and depth charges aboard. HQ also offers a supply
ship when ASROC or depth charges have been used. VLS cells are not reloaded at
sea. Saves stay v31.

## 1.3.68

Release 1.3.68 makes the OPZ's correlation suggestions smarter. Besides
bearing and position they now compare course, speed and the operator's
classification: two reports whose courses or speeds clearly differ, or whose
classes do not match, are no longer suggested, and agreeing classes rank a
pair higher. Received AIS reports now appear in the OPZ as reports of their
own (reported position, course, speed and name) and are suggested with the
radar and lookout reports of the same ship. A fusion now carries its members'
course and speed. Saves are now v31 (AIS reports keep their reported
position); v30 saves no longer load.

## 1.3.67

Release 1.3.67 lets HQ give the crewed submarine orders during the mission.
Below the mast the VLF loop antenna now copies the broadcast down to 25 m
(slower than with the mast up, and receive only). From the second broadcast
on, a broadcast may carry an HQ order: proceed to an area in deep water, send
a situation report, or keep radio silence, each with a deadline. The radio
room page, the chart and the browser's Radio room card show the open order and
how many were carried out; a missed broadcast is a missed order. Saves are now
v30 (they keep the orders); v29 saves no longer load.

## 1.3.66

Release 1.3.66 gives the helicopter a surface-search radar. Whenever it flies
with the dipping sonar stowed it searches from 150 m: ships out to 40 NM,
surfaced submarines and raised snorkels or periscopes inside its radar
horizon, a mast at about 10 NM in calm water and only a few miles in a rougher
sea. Every contact reaches the OPZ as a RADAR-HELO track; the helicopter page
and the Remote Crew helicopter view show whether the radar is searching. Saves
stay v29.

## 1.3.65

Release 1.3.65 gives the frigate two more anti-submarine weapons at the
Weapons station. `A` fires one of four ASROC: the rocket flies to the
designated submarine's observed position (1 to 10 NM, current range needed)
and drops a lightweight torpedo there. `Z` drops a pattern of five depth
charges over the stern (20 in the rack, 45 s reload, at least 10 kn); they
sink to the preset depth and are lethal within about 25 m. Both use the
torpedo's target checks and are also on the Remote Crew weapons page. Saves
are now v29 (they keep the charges in the water and the stores); v28 saves no
longer load.
## 1.3.64

Release 1.3.64 tidies the uConsole screens. Every text now uses the bundled
JetBrains Mono face, so lines no longer clip on any system, and line spacing
follows the font. All status bars share one style with quarter marks and
labels, the engine telegraph highlights the nearest step and warns when a
direct speed lies between steps, and the bridge gains heading, rudder and
speed dials. The submarine tab bar, map scale numbers, water column labels, ESM
compass and the bottom ticker no longer overlap; OPZ, ELOKA and helicopter
pages get the start screen's frames and a key footer, and the last English
leftovers in German menus are translated. Saves stay v28.

## 1.3.63

Release 1.3.63 makes the pairing code easier to enter, on the crew page and
on the phone lookout. The code can be typed the way `F9` shows it, with the
space, in lower case, or with look-alikes such as O for 0, l for 1 or S for 5,
and it is still read correctly. "Wrong pairing code" now appears only when the
code really is wrong, and it names the code the game received;
when the game refuses the address itself (a bookmark or another name for the
host), the page says to open it from the QR code or the address in `F9`. The
pairing help no longer claims the code expires after five minutes: it stays
while the game runs and changes after five wrong tries. Saves stay v28.

## 1.3.62

Release 1.3.62 teaches the autopilot the chart. A waypoint or search pattern
whose leg crosses shoal water or land now gets detour points around it, or a
warning in the feed which leg to steer by hand. While the route runs, the
autopilot looks two minutes ahead once a second; shoal water there gets a
detour to the current waypoint, or the route switches off and the ship turns
back on the reciprocal course. It plans on charted depth, rocks and wrecks
against the hull's draft plus keel reserve and a 2 m margin. Saves stay v28; a
route may now hold up to 16 points with detours.

## 1.3.61

Release 1.3.61 makes the Unit Editor count. Profiles saved there can now be
placed in your own missions like built-in units, and they take effect there:
name, speeds, depth, torpedo load, behaviour, acoustics and spawn weight. A
user submarine takes its sensors, tubes, decoys and battery, diesel or AIP
plant from the built-in boat of its propulsion. A mission can also place a
hostile torpedo that is already running on its course at the start, for
torpedo-evasion drills. Such missions save and load normally (the save's
catalog snapshot carries the user profiles); built-in scenarios never use
them. Saves stay v28.

## 1.3.60

Release 1.3.60 makes both sides able to win. A torpedo's proximity fuze now
fires at the closest approach its track predicts instead of on entering its
radius, so a torpedo that homes in hits hard; before, it went off 250 to 370 m
short and did only 12 to 18 % damage. Hostile torpedoes run 40 kn for 20 NM
and outpace the frigate, and an AI submarine attacks a located frigate within
10 NM even when she runs quiet. The submarine missions fit their clocks: the
breakthrough goal lies 5 NM beyond the frigate, reconnaissance has 3 hours,
and the convoy sails at 8 kn with the submarine starting on its bow, about
10 NM ahead. Saves stay v28.

## 1.3.59

Release 1.3.59 is a clean-up with no change in play. The two largest modules
are split along their seams: the radar, air, ECM, ESM and radio pictures with
missiles and raiders move from the simulation step into their own module, and
the Remote Crew station action handlers move out of the bridge into their own
module; the code moves verbatim and the update order stays frozen. The
changelog entry of 1.3.43 now says what that release actually fixed. Saves
stay v28.

## 1.3.58

Release 1.3.58 greets a first launch with a choice. When no settings file
exists yet, the splash is followed by one page asking what you want to play:
Frigate opens the training with the first frigate lesson selected, Submarine
opens the first submarine lesson and sets the uConsole to the submarine side,
Remote Crew opens the F9 page for browser crews, and Main menu (or `Esc`) goes
straight to the menu. Any choice is remembered, so the page appears only once.
Saves stay v28.

## 1.3.57

Release 1.3.57 lets the submarine's crew speak more of its reports. Besides
contacts, pings and torpedo warnings the boat now calls out its own torpedo
leaving the tube, detonations close aboard or at a distance with their
bearing, breaking-up noises its sonar can hear, a copied HQ broadcast (and
whether it carries a contact report on the frigate), each class the periscope
sights with its bearing, approaching and passing test depth on the way down, a
hit, hull damage and the mission result, in English or German. Every spoken
report comes from a line in the boat's own log, so the crew never hears more
than it has been told. Saves stay v28.

## 1.3.56

Release 1.3.56 gives the OPZ correlation suggestions. When two of the ship's
own sensors (sonar, radar, ESM, lookout) report a contact on the same bearing
within their uncertainty (and, where both have positions, close together), the
OPZ offers the pair for fusion: on the uConsole up to two suggestions stand in
the page 1 sidebar, `U` fuses the top one and `Shift+U` dismisses it; the
Remote Crew OPZ lists up to four with Fuse and Dismiss buttons. Suggestions
only compare published reports no older than 30 s; nothing is fused without
the operator. Saves stay v28.

## 1.3.55

Release 1.3.55 gives the frigate an autopilot route. On the Bridge a right
click on the chart adds a waypoint (up to 8), `W` starts a search pattern from
the ship's position and course (a zigzag of 3 NM legs, then an expanding
square) and `Backspace` clears the route. The helm steers for each waypoint in
turn, counts it reached within 0.3 NM and holds its course after the last one;
speed stays with the telegraph, and any helm order takes over. The chart shows
the route with numbered waypoints, and the Remote Crew bridge has an
"Autopilot route" card with the same patterns and a chart mode for setting
waypoints. Saves are now v28 (they keep the route); v27 saves no longer load.

## 1.3.54

Release 1.3.54 lets the AI hunters use the frigate's ESM. When the frigate has
no position on the submarine, an ESM intercept of a mast radar now gives the
search line: the library must rank a submarine radar among its three best
matches and no ship the frigate tracks by radar or AIS may lie within 10° of
the bearing. It competes with the HF/DF bearings by age and stays a datum for
5 minutes, so a submarine that radiates at periscope depth draws the frigate,
its helicopter and the patrol aircraft down that bearing. Saves stay v27.

## 1.3.53

Release 1.3.53 adds a guard against frozen Remote Crew browsers. A new test
plays two busy missions (the frigate with the autocrew on every station
against the AI submarine, and a crewed submarine with its radio, threat
picture and HQ tasks filled), publishes every station's state and chart for
both units and runs the browser's own validators over all of them in Node. A
field the browser would refuse, as in 1.3.44, now fails the tests before a
release. Nothing changes in play. Saves stay v27.

## 1.3.52

Release 1.3.52 lets Remote Crew browsers follow a host update by themselves.
The host now names its version on every reply and in the page it serves; a
browser page that is still open from before an update reloads itself once and
so always runs the web client that matches the host, instead of freezing on
data it cannot read. Saves stay v27.

## 1.3.51

Release 1.3.51 adds an autosave. A running mission is saved every 5 minutes
and when you quit or leave it for the main menu, to `~/.u-jagd/autosave.json`
beside the five slots. The main menu then starts with "Continue mission",
which resumes it exactly; after a crash it holds the last 5-minute save. The
file is written in the background so the uConsole does not stutter. A mission
that ends and any new mission delete the autosave. Saves stay v27.

## 1.3.50

Release 1.3.50 fixes Remote Crew pairing on the LAN. A freshly paired
browser no longer greets you with "Your station was revoked or released" as if
pairing had failed; it now says "Authenticated. Take a free station." The crew
page now tells you when it runs in a browser that is not Chrome or Chromium (also
Edge): Firefox and Safari show a hint above the pairing code, and a page that
cannot start there says so instead of loading forever. The bridge's navigation
proposal accepts the frigate's full 31 kn; saves stay v27.

## 1.3.49

Release 1.3.49 puts aircraft at their true height in the lookout's binoculars,
the lookout strip, the periscope and the phone lookout: each stands at its
elevation above the horizon, worked out from its altitude and range less the
curve of the Earth, so a high aircraft close by needs the optics tilted up.
Aircraft now hang in the still sky behind the clouds instead of riding the
swell with the ships. Both on the uConsole and in the Remote Crew browser;
saves stay v27.

## 1.3.48

Release 1.3.48 renews the pictures on the project page. They are now a
gallery and show, new, the lookout's binoculars on the frigate and the
submarine's periscope by day and by night, on the uConsole and in the browser,
with a warship and merchants in the eyepiece and the merchants' navigation
lights in the dark; every station picture is in the new turquoise look. The
screenshot tools make these eyepiece pictures on their own
(`tools/sight_capture.py`). Saves stay v27.

## 1.3.47

Release 1.3.47 puts a phone on watch. `F9` shows a second QR code, Phone
lookout: scan it, accept the game's own certificate once, type the pairing code,
and the phone becomes the frigate's bridge lookout or the crewed submarine's
periscope. Turn the phone like binoculars (gyroscope) or swipe, zoom, and report
what you see by voice ("Ship bearing 040, range 5 miles") or by tapping it. The
bridge only hears what the lookout really has there; a report of nothing is
refused. While a phone holds the watch the automatic lookout stays silent, and
the crew browsers speak every confirmed report. The phone on the periscope
trains it and takes stadimeter ranges. The listener serves this page over HTTPS
on the next port (self-signed, made by the game), because phones only give the
gyroscope and the microphone to a secure page; saves stay v27.

## 1.3.46

Release 1.3.46 redraws the bridge's small weather picture in the start screen's
look: it now looks into the wind with the sky of the hour (sun, moon and stars),
the clouds, rain, snow or fog and the sea running at the eye, and a turquoise
wind rose in its corner, framed by the corner brackets of the other views. Both
on the uConsole and in the Remote Crew browser; saves stay v27.

## 1.3.45

Release 1.3.45 keeps the sky still in the periscope and the lookout's
binoculars: clouds, stars, the sun and the moon stay in place while the sea and
the horizon roll with the swell. From dusk to dawn and in poor visibility
neutral ships run their navigation lights as the collision regulations lay
down: white masthead lights, the red or green side light for the side you see,
the white stern light from astern, each within its range, and the all-round
lights of vessels at work (trawler, pilot, survey ship and cable layer, mine
clearance), and civil aircraft their wingtip, tail and flashing anti-collision
lights; the ship's bow points the way its lights show, and a lit ship is sighted by its lights in the dark.
Warships and military aircraft run dark. The sea follows the wind: into it the
crests come at you, down-sea they run away, across it they run sideways, and
the ship pitches in head seas and rolls in beam seas. The binoculars and the
periscope now tilt up and down, zoom (binoculars 16°, 8°, 4°; periscope low and
high power) and have a horizon stabilizer. Both on the uConsole and in the
browser; saves stay v27.

## 1.3.44

Release 1.3.44 fixes Remote Crew browsers that froze with "Host sends data
this browser cannot read". Four lists named a row's type with a field the
browser refuses in every station state: the submarine's radio log, its threat
intercepts and evasion order, and the frigate radio room's HQ tasks. As soon as
the first broadcast was copied, a ping or torpedo was heard or HQ offered a
task, the station picture stopped and actions were locked. These rows now send
the field as `type`; a new test catches such a field without Chromium. After
updating the host, reload the browser page once so it loads the new web
client. Saves stay v27.

## 1.3.43

Release 1.3.43 keeps only the newest release on GitHub: after publishing a new
version the Windows workflow deletes every older release (their git tags stay).
The Windows starter and the uConsole updater read only the latest release.
Saves stay v27.

## 1.3.42

Release 1.3.42 keeps only the newest release on GitHub: after publishing a new
version the Windows workflow deletes every older release (their git tags stay).
The Windows starter and the uConsole updater read only the latest release.
Saves stay v27.

## 1.3.41

Release 1.3.41 brings back the full top bar on the uConsole: the frigate shows
the station, the mission, the clock, speed and course again, and the crewed
submarine shows the mission, the clock, speed, course and depth, now compactly
separated by "·". Saves stay v27.

## 1.3.40

Release 1.3.40 adds a bug report. "Report a bug" in the main menu writes
`~/.u-jagd/bug-report.txt` with version, platform and the newest lines of the
crash log (your user name removed from paths) and shows a QR code that opens a
prefilled GitHub issue on a phone; `Enter` opens it with the log in a browser
where the device has one. After a crashed start the main menu offers it. The
Windows starter and the browser settings menu link to the same issue form, and
the crash log now also records each mission start. Nothing is sent until you
submit the issue with your own GitHub account. Saves stay v27.

## 1.3.39

Release 1.3.39 gives the periscope, the lookout's binoculars and every station
the start screen's look. The eyepieces show day, dusk and night with stars, the
moon in its phase and its glitter on the water, clouds, rain, snow and fog from
the weather, and the ships in steel with a lit rim, lit windows at night, bow
wave and wake. The Remote Crew bridge gets the lookout's binoculars as a card
and the browser periscope the same picture and silhouettes. uConsole and
browser stations use the turquoise phosphor and night blue of the start screen
with corner brackets on the panels; the chart keeps its NATO symbols and the
high-contrast theme is unchanged. Saves stay v27.

## 1.3.38

Release 1.3.38 lets the uConsole charts zoom much further in. `Q`/`E` now
step through fixed chart heights of 500, 250, 100, 50, 25, 10, 5, 2, 1 and
0.5 NM on the bridge, weapons, helicopter and submarine charts, and the mouse
wheel zooms smoothly down to 0.5 NM; the operations centre chart goes down to
a 0.25 NM radius. The grid gets finer as you zoom (down to 0.1 NM, with
decimal labels), the scale line shows fractions, and coastlines and radar
rings are clipped so strong zoom stays fast. Saves stay v27.

## 1.3.37

Release 1.3.37 fixes a crash that closed the game as soon as a frigate or
AI torpedo was in the water while the simulation log (Options, Simulation log) was
recording: the log's state snapshot read a torpedo number the torpedo does
not have. The crash log added in 1.3.34 showed the cause. Saves stay v27.

## 1.3.36

Release 1.3.36 fixes sonar audio on the uConsole that could fall silent until
audio was switched off and on in the options. A rare race in the pygame mixer
could leave the sonar channel idle with its next block queued forever, and
the sonar playback waited for that queue slot for good. Playback now replays
such a stranded block and carries on, and a stopped sonar audio worker is
restarted with the next block. `audio_debug.log` counts both
(`queue_stranded`, `worker_restarts`). Saves stay v27.

## 1.3.35

Release 1.3.35 puts less text on the uConsole screens. The top bar names only
the station and the clock, the chart header only its scale. The sonar loses its
header status chips and legend lines and keeps one row of four main keys (the
rest is in F1); a towed or variable-depth array shows its state only while it
is moving or not ready. The submarine's threat box appears only while a threat
is fresh, then an amber triangle next to the clock marks standing warnings.
Courses read in whole degrees with °, and the turn radius shows only in a turn.
The TMA header no longer overlaps, and the submarine's Weapons tab, tube line
and alarm lines are no longer cut off. Saves stay v27.

## 1.3.34

Release 1.3.34 writes a crash log: every game start adds a start and an end
line to `~/.u-jagd/crash.log`, and a game that ends on an error leaves its
traceback there, or after a hard crash (a segmentation fault in SDL or audio,
`SIGTERM`) the stacks of all threads. A start line with no end line means the
game was killed from outside, usually by the kernel when memory ran out. The
file stays below 256 KiB. Saves stay v26.

## 1.3.33

Release 1.3.33 lets the crewed submarine's ESM measure each radar's scan
period, the time between its main-beam hits: a search radar reads rotating
with its period (about 2.5 s for navigation and surface search, 5 s for air
search), a tracking or fire-control radar reads steady. A steady beam on the
mast is always a mast warning and is reported in the log; the uConsole's Mast
& ESM page and the browser show the reading. Saves are now v27.

## 1.3.32

Release 1.3.32 adds directional hearing: with stereo sound, detonations,
returning echoes and another platform's active ping come from the bearing they
were heard on, left for port and right for starboard of the frigate's or the
crewed submarine's head, on the uConsole and in the Remote Crew browser. The
frigate now also plays a submarine's ping itself, and the crewed submarine
hears a hunter's ping ring on its hull.

## 1.3.31

Release 1.3.31 gives the crewed submarine real torpedo tubes: the torpedo gang
loads each empty tube from the racks (`M` at the Weapons station, or Load in
the browser), and a loaded tube must be flooded before it fires, which takes
20 s and can be heard (`Shift+M`, or Flood). Every submarine now carries as
many reloads again as it has tubes, reloaded in 2 to 4 minutes; the AI's
submarines keep loading and flooding by themselves. Saves are now v26.

## 1.3.30

Release 1.3.30 lets the **frigate play the submarine missions against the AI**:
an uncrewed mission submarine now pursues its objective instead of
patrolling. It runs below the layer for the breakthrough goal, follows HQ's
contact reports and comes to periscope depth to sight and report the
frigate, and in the convoy attack runs ahead of the convoy and torpedoes its
merchants one at a time. Saves stay v25.

## 1.3.29

Release 1.3.29 names the submarine consistently: every screen, the web
clients, help and manual now say **submarine** (German **U-Boot**) where they
used to say just "boat", for example the **Submarine campaign** and the
submarine missions. Saves stay v25.

## 1.3.28

Release 1.3.28 makes the **AI hunters smarter**: the OPZ marks the bare radar
blip of a raised mast or snorkel, and a mast track, an HF/DF cross-fix or an
HQ submarine datum report now becomes the hunt's datum. A fresh fix from the
ship's own sensors goes over the datalink to a friendly AI warship with
ASROC in range. Saves are now v25 (radar blips and marks).

## 1.3.27

Release 1.3.27 sorts the boat's **ESM library by fit**: the emitters whose
published ranges hold a measurement are listed best fit first (frequency and
PRF near the middle of their ranges, the same modulation), each with a grade
of good, fair or poor on the uConsole and in the browser, so a well-fitting
radar such as the helicopter's no longer drops off the list. Saves stay v24.

## 1.3.26

Release 1.3.26 skips the update check on the uConsole when there is no
internet: a connection test to GitHub decides within 2.5 seconds, and the game
then starts right away instead of waiting on timeouts. Stalled git downloads
give up after at most 60 seconds. Saves stay v23.

## 1.3.25

Release 1.3.25 tidies up the documentation. Gameplay is unchanged and saves stay
v24.

## 1.3.24

Release 1.3.24 brings **atmosphere to the crewed boat**: the pressure hull creaks
deep down and cracks when it fails, detonations in the water are heard close
aboard or far off and logged with a bearing, and **silent running** rigs the
boat's screens for dimmed red light on the uConsole and in the browser. The
boat's browsers now play its own sound cues, and a rescue task's alarm cue no
longer upsets the browser. Saves stay v24.

## 1.3.23

Release 1.3.23 gives every menu and dialog the start screen's look: help,
options, save/load, quit, nations, Remote Crew administration (`F9`) and the
mission end now show the night hunt behind a translucent console panel with
phosphor corner brackets and a glowing title, while the mission keeps running
behind them. In high contrast the panels stay opaque. Browser dialogs use the
same night sky and bracket frame. Saves stay v24.

## 1.3.22

Release 1.3.22 makes the Remote Crew streams steadier. A browser that
reconnects its sonar audio or sonar display stream now takes over its own
previous stream at once instead of being refused while the host had not yet
noticed that the old connection was gone. The web client no longer sends an
extra state request for every pushed state. The browser tests for live audio
and the state push now run in real time next to the host. Saves stay v23.

## 1.3.21

Release 1.3.21 lets the crewed boat go **below its test depth**, down to crush
depth (1.5 x test depth), at a growing risk: sheared bolts, failed shaft or
valve seals and, deeper, a cracked pressure hull flood compartments and add
damage, far more often the deeper the boat goes; at crush depth the hull
collapses. The depth columns mark the crush depth and a red alarm shows while
the boat is below test depth. Saves stay v24.

## 1.3.20

Release 1.3.20 adds the boat's **periscope attack computer**: every stadimeter
reading is a mark, and two or more marks a minute apart give the target's
course and speed, the lead angle and the torpedo's running time under the
periscope (browser: Solution column). `Ctrl+Enter` on the periscope page
(browser: Fire on solution) fires on the intercept course; a shot at a marked
sonar contact uses the solution too. Saves move to **v24** (the marks are
saved); v23 saves are no longer loaded.

## 1.3.19

Release 1.3.19 makes the uConsole start visible at once: a small start window
shows whether the launcher is checking for, downloading or installing an update
and closes when the game appears. A second start while U-Jagd is starting or
running no longer opens the game twice; it shows "U-Jagd is already running."
instead. Saves stay v23.

## 1.3.18

Release 1.3.18 adds an **A4 poster** in German and English (PNG at 300 dpi
and PDF) in `docs/poster/`: the start-screen scene, a short description of the
uConsole and Windows versions, four screenshots and QR codes for the download
and the support page. `tools/build_poster.py` renders it again from the
current scene and screenshots. The game itself is unchanged; saves stay v23.

## 1.3.17

Release 1.3.17 fixes the Windows program's self-update: after swapping in the
new `U-Jagd-Windows.exe` it failed to start ("Failed to load Python DLL")
because it inherited the old process's already deleted unpack directory. The
restart now unpacks afresh. The starter window also shows the "Buy me a
coffee" link. Saves stay v23.

## 1.3.16

Release 1.3.16 adds the **boat campaign**: five linked boat missions in one sea
area (reconnaissance, breakthrough, convoy attack, breakthrough, convoy
attack), chosen with `Tab` on the campaign screen. The boat carries its
torpedoes, hull damage and standing with U-boat command from mission to
mission; at its base it takes a full refit or a quick turnaround. Kept in
`~/.u-jagd/boat_campaign.json`; saves stay v23.

## 1.3.15

Release 1.3.15 adds boat mission 7, **Convoy attack**: the frigate escorts four
merchants and the submarine must sink two of them. Only the crewed boat's
torpedoes take a merchant; the AI frigate keeps station ahead of the convoy
and prosecutes contacts only near it. The boat's orders count the merchants
sunk. Saves stay v23.

## 1.3.14

Release 1.3.14 adds **boat missions**: scenario 5 *Breakthrough* (the submarine
must reach a goal area beyond the frigate's patrol position) and scenario 6
*Reconnaissance* (it must sight the frigate through the periscope and radio a
situation report while it is in sight). The frigate's task is to stop it. The
boat's orders stand over its chart and in the browser's boat stations; the
goal is marked on the boat's chart. Saves stay v23.

## 1.3.13

Release 1.3.13 renders the uConsole screenshots after three simulated
minutes instead of six seconds, so waterfalls, plots and contact lists are
filled, and shows the Mission Editor with the packaged example mission (library
and seeded sector preview) instead of an empty library. The README now links
the menu and editor views too. Saves stay v23.

## 1.3.12

Release 1.3.12 refreshes the screenshots in the README from the current game
(the uConsole at 1280 x 720, including the crewed submarine's stations, and the
Remote Crew browser in Chromium) and moves the release history into
[CHANGELOG.md](CHANGELOG.md), so the README shows only the latest release.
`tools/capture_screenshots.py` and `tools/capture_commander.py` regenerate
every image. Saves stay v23.

## 1.3.11

Release 1.3.11 adds a **Windows program**: `U-Jagd-Windows.exe` starts the game
as Remote Crew server (crew or solo mode, optionally as the submarine), shows
the browser address, join code and QR code, and offers each newer release
itself. GitHub Actions builds it on every push to `main` and publishes it as
release `v<version>`. The game also gains `--remote-crew` (crew-mode Remote
Crew on the first private LAN address at launch) and `--status-file`. See
[Windows program](README.md#windows-program). Saves stay v23.

## 1.3.10

Release 1.3.10 fixes the uConsole installer on a checkout that is older than
the installer itself: it now fast-forwards that checkout to `main` first
instead of stopping with a missing `u_jagd_updater.py`.

## 1.3.9

Release 1.3.9 adds a one-command installer for the uConsole with automatic
updates: every start fetches the newest GitHub release (a background timer also
checks every six hours), offline the installed version starts, and a version
that does not start is rolled back. It creates a menu entry, a desktop shortcut
and the `u-jagd` command. Saves stay v23.

## 1.3.8

Release 1.3.8 adds a support link: a QR code in the uConsole main menu and a
small link on the Remote Crew pairing, lobby and settings screens and the
web-host admin page, never over a running station. It also brings the guides
up to date: the reference and README list the VDS and 31 kn, the README's
mission-editor limits match the runtime, and the co-op and protocol guides
cover the solo side choice, the submarine roles and the admin shutdown.
Saves stay v23.

## 1.3.7

Release 1.3.7 gives the frigate F-217 its real 31 kn top speed (FLANK). The
brake power is scaled so drag, acceleration and turning up to 25 kn stay as
before; self-noise now rises up to 31 kn and the Nixie's cable still parts
above 25 kn. The web-host admin page gets **End game now**, which stops the
server process after a confirmation so it does not keep running in the
background. Saves stay v23.

## 1.3.6

Release 1.3.6 redraws the start screen as an animated night hunt: the
frigate F-217 with turning radar, funnel smoke, bow wave and towed array,
the helicopter with its dipping sonar, and a submarine below the layer that
lights up when the hull sonar's pulse reaches it, with the author and the
version on the title. The same scene, dimmed, lies behind the main menu.
The silhouettes in the periscope and the bridge binoculars now show
detailed class profiles (frigate, container ship, small craft, helicopter)
that pitch with the sea, turn their radar and rotors and trail a bow wave
and wake. In Remote Crew solo mode the New Game dialog picks the side:
the frigate or the submarine, which the AI hunters then chase. Saves stay
v23.

## 1.3.5

Release 1.3.5 adds AI hunters: when nobody sails the frigate (the uConsole
plays the boat, or a solo browser plays the submarine), the frigate, its
helicopter and the patrol aircraft hunt the boat from the frigate's own
sensors, on every frigate station no browser holds. Saves stay v23.

## 1.3.4

Release 1.3.4 gives the frigate a variable-depth sonar (VDS) as a third
array beside the hull sonar and the towed array: `Shift+Y` lowers or
recovers the towed body (3-15 kn, sea state up to 5, lost above 24 kn),
`U`/`V` set its depth (20-300 m) while it is the selected array, and it
listens and pings from its own depth, below the layer when lowered there.
It resolves the towed array's left/right ambiguity like the hull sonar.
Remote Crew sonar gets the same controls. Saves move to format v23 (the
VDS state).

## 1.3.3

Release 1.3.3 paints the Remote Crew browser waterfalls (LOFAR, DEMON,
broadband) in a background worker through `OffscreenCanvas` where the browser
offers it, so the page's main thread and the live sonar audio on it no longer
run the per-cell raster loop; other browsers keep the previous path. Saves
stay v22.

## 1.3.2

Release 1.3.2 lets the Mission Editor pick a mission's reference world from a
list of the 128 packaged sectors (with their countries) instead of typing
`sector:<n>`, and its preview draws the chosen sector's coast. Saves stay v22.

## 1.3.1

Release 1.3.1 gives the crewed submarine a radio room (a seventh boat
station: HQ's broadcast with a contact report on the frigate, and situation
reports the frigate's HF direction finder can bear) and lets the boat's ESM
hear the frigate's helicopter and the patrol aircraft by their own catalogued
search radars. Saves move to format v22 (the radio room's state).

## 1.3.0

Release 1.3.0 widens the simulation and the crew's tools without moving the
1.0.0 balance (77 calibration metrics still match): a second lightweight
torpedo type with search patterns, enable point and salvo spread; hostile
submarines that fire only once their own target-motion analysis has
converged; counter-flooding, longitudinal trim and plant selection aboard;
helicopter sonobuoy patterns and a MAD run; convergence zones from the
measured sound-speed profile with Ekelund and dot-stack TMA; a periscope
with visual sightings, a stadimeter and diesel noise while snorkelling for
the crewed submarine; anti-aliased chart lines, the chart's light of the
hour, a weather hatch and a shared horizon renderer; a WebSocket state push
for Remote Crew with a generated schema allowlist; a read-only observer
role, a debrief timeline with JSON export and voice on by default; and a
mission runtime that takes the editor's scope (reference sectors, protect
and reach objectives, random groups, timed events, authored weather, placed
aircraft, animals and decoys). The core is split into mixins and the test
suite runs in parallel. **Saves are format v23 (the variable-depth sonar, the crewed boat's radio room, HQ radio tasks, the crew's watch bill, fatigue and morale, the on-call patrol aircraft, the crewed boat's compartments and damage control, its tanks, trim and high-pressure air, its ESM picture,
submarine diesel, charge rate and air stores, crewed-boat crew state, periscope
sightings, weapon settings, mission events, foreign pings still travelling to
the frigate); older saves are rejected.**

## 1.2.0

Release 1.2.0 tightens the game flow and the hand-over between stations: the
`Esc` dialog and the mission-end screen return to the main menu (`M`), `R`
restarts an editor mission as itself, convoy missions announce the remaining
time as progress, and an Operations fusion built from one sonar contact can be
designated to Weapons, with its classification and affiliation applying to fire
control (FRIEND/NEUTRAL on a fusion blocks every torpedo shot). Saves stay v14.

## 1.1.0

Release 1.1.0 replaces the remaining kinematic shortcuts with physical models
while keeping the 1.0.0 gameplay balance (checked by a calibration harness):
force-based own-ship hydrodynamics and seakeeping; a time-varying ocean with
tides, mixed layer, sediments and wrecks; passive/active sonar equations with
ray-traced propagation; towed-array left/right ambiguity, Doppler and a
covariance TMA; submarine and torpedo physics (energy, fins, wire, proximity
fuze); decoy discrimination; compartment flooding, stability, fire and repair
logistics; the radar equation with a rotating antenna, ESM amplitude, HF
propagation and a moonlit lookout; and missile flight physics with chaff
clouds, CIWS ballistics, pop-up raiders, helicopter hover/deck limits and
drifting buoys. Hostile submarines now need their own TMA before they know
your range. The Remote Crew v2 protocol is unchanged apart from new ELOKA
intercept fields.
See [docs/simulation-gaps.md](docs/simulation-gaps.md) for the full record.

## 1.0.0

Release 1.0.0 splits every workstation into two tabbed sub-pages, adds manual
CIWS and FLAK release authorization alongside the existing automatic gates,
and gives the autocrew bridge ASM/torpedo evasion and grounding-avoidance
behavior. TMA re-solves now use hysteresis against near-tied bearing
solutions, and inbound anti-ship missiles carry a terminal-active radar
seeker that gives an ESM/RWR warning before search radar acquires them. A
consolidated theme system adds an optional high-contrast, colorblind-safe
palette. Save format v11 and the Remote Crew v2 protocol are unchanged.
