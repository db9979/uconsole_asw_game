# Installing on the ClockworkPi uConsole

[Deutsche Version](install-uconsole.md)

This guide describes installing, launching, and updating U-Jagd from the
repository <https://github.com/db9979/uconsole_asw_game>. The target system is a
uConsole with a Debian-based ClockworkPi distribution, particularly a CM5
system. Commands without `sudo` run as a regular user.

## 0. One-command install with update notice (recommended)

Run a single command in the uConsole terminal as your normal user (not with
`sudo`):

```sh
curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
```

The installer

- installs missing system packages (`git`, `python3-venv`), asking once for the
  `sudo` password,
- downloads the game to `~/games/u-jagd` (an existing checkout there is adopted;
  choose another place with `U_JAGD_DIR=/path` before `sh`),
- creates the `.venv` virtual environment,
- adds the menu entry **Games > U-Jagd**, a desktop shortcut and the command
  `~/.local/bin/u-jagd`,
- brings the checkout to the newest GitHub release and switches off the
  background timer of older versions (up to 1.3.109).

**Updates only on request:** since 1.3.110 nothing is installed on its own.
At start the game asks GitHub once in the background for the newest release
(tag `vX.Y.Z`, the same source as the Windows starter). When it is newer, the
start screen (top right) and the main menu (left of the entries) show the new version,
its changelog entry in the game language, a warning when saved games of this
version (the autosave too) will not load in the new update (a different save
format), and the button **Update now** (key U or a click). Without internet no
notice appears. Only the button closes the game and runs
`u_jagd_updater.py install`: it waits until the game has closed, fetches the
release, runs `pip install -e .` when dependencies changed and starts the new
version. A new version that does not even start (`main.py --version` fails) is
rolled back, and only the next version is tried again. Local changes in the
checkout or a branch other than `main` leave everything untouched. A stalled
git download gives up after 60 s at most. Log: `~/.u-jagd/updater.log`. Saves
under `~/.u-jagd/` are not touched.

**Crash log:** every game start writes a start and an end line to
`~/.u-jagd/crash.log`. If the game ends on an error, the traceback is there;
after a hard crash (a segmentation fault in SDL or audio, `SIGTERM`) the
stacks of all threads. A start line followed by neither an end line nor an
error means the game was killed from outside, usually by the kernel when
memory ran out (`dmesg | grep -i -e oom -e killed`). The file stays below
256 KiB. Mission starts are logged there too (scenario, world, seed, side).

**Report a bug:** the main menu entry "Report a bug" writes
`~/.u-jagd/bug-report.txt` (version, platform, newest log lines without your
user name) and shows a QR code that opens a prefilled GitHub issue on a
phone; attach the file there. After a crash the main menu offers the entry at
the next start.

**Start window:** right after the click a small "U-Jagd" window shows the
current step (starting U-Jagd; after **Update now** also waiting for U-Jagd to
close, downloading the update, installing dependencies, checking the new
version). It closes as soon as the game shows its first frame. A second start
while U-Jagd is already starting or running opens no second game; it shows
"U-Jagd is already running." for three seconds instead (and brings the game
window to the front when `wmctrl` is installed). `U_JAGD_NO_SPLASH=1` turns
the window off.

Game arguments are passed through, for example `u-jagd --windowed`. Start once
without looking for updates: `U_JAGD_NO_UPDATE=1 u-jagd`. Take the newest
`main` instead of releases when updating: `U_JAGD_UPDATE_CHANNEL=main`. To
remove the menu entry and command (game and saves stay):

```sh
sh ~/games/u-jagd/packaging/uconsole/install.sh --uninstall
```

The following sections describe the manual installation.

## 1. Prepare the system

Open a terminal and update the package lists and installed packages:

```sh
sudo apt update
sudo apt upgrade
sudo apt install git python3 python3-venv python3-pip
```

The game requires Python 3.11 or newer, Pygame 2.6 or newer, and NumPy 2.0 or
newer. Check the version:

```sh
python3 --version
```

## 2. Get the repository

```sh
git clone https://github.com/db9979/uconsole_asw_game.git
cd uconsole_asw_game
```

If the repository is already present, do not clone it again. Continue in the
existing directory with the "Update" section instead.

## 3. Create a virtual environment

A virtual environment prevents conflicts with Python packages managed by the
system:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

After a restart or in a new terminal, activate the environment again:

```sh
cd uconsole_asw_game
. .venv/bin/activate
```

## 4. Launch

Normal fullscreen launch:

```sh
python main.py
```

Launch in a window, for example for troubleshooting:

```sh
python main.py --windowed
```

Reproducible launch with a numeric seed:

```sh
python main.py 12345 --windowed
```

Launch without audio or display the version:

```sh
python main.py --no-audio
python main.py --version
```

These are the currently supported launch arguments. In the start menu, select
the scenario with the arrow keys or number keys and confirm with `Enter` or the
space bar. `W` selects one of the 128 seed-determined real 500 NM sectors or the
fixed legacy reference map; `R` generates a new seed. The same seed and world
mode reproducibly generate the same world. The real names and coastlines are not
a navigational product; depths are synthetic, and military gameplay roles are
fictional training roles. `F` toggles fullscreen there. In the game, `F1` opens
context-sensitive help; `Alt+Enter` switches between fullscreen and windowed
mode at any time.

A complete printable German reference for all local station shortcuts is
available at [`station-shortcuts.de.pdf`](station-shortcuts.de.pdf).

The interface renders natively on a 1280 x 720 pixel canvas. In fullscreen it is
scaled to the available display area; in windowed mode, 1280 x 720 is the native
size.

Optional Remote Crew is configured on the uConsole with `F9` or through **F10 >
Commander LAN**. The service starts off on every launch.

To let Remote Crew create its own temporary Wi-Fi hotspot when no network is
available, install the narrowly scoped system helper once from the checkout:

```sh
sudo ./packaging/uconsole/install-hotspot-helper.sh
```

Continue to launch the game itself without `sudo`. The helper can only create
and remove the transient U-Jagd hotspot. Remove the system integration with
`sudo ./packaging/uconsole/install-hotspot-helper.sh --uninstall`.

**Wi-Fi power saving:** the Compute Module's Wi-Fi driver (brcmfmac) switches the
radio off between packets in power-save mode, which causes latency spikes of a
few hundred milliseconds that browsers may hear as sonar dropouts. Turn power
saving off on the uConsole for Remote Crew (`iw dev wlan0 get power_save` shows
the state):

```sh
sudo iw dev wlan0 set power_save off
```

Permanently through NetworkManager: create
`/etc/NetworkManager/conf.d/wifi-powersave.conf` containing `[connection]` and
`wifi.powersave = 2`, then restart the service. The same applies to browser PCs
on that Wi-Fi.

**Security:** HTTP is unencrypted. Use only a trusted LAN. No Internet hosting,
wildcard binding, CDN, remote ROE/time/save controls, or hidden entity data are
exposed. See [Remote Crew setup](commander-coop.md) and
[protocol/security](commander-protocol.md).

## 5. Optionally install as a package

For a system-independent command entry point within the virtual environment:

```sh
python -m pip install -e .
u-jagd --windowed
```

Launching directly with `python main.py` remains the simplest approach for a Git
checkout. Contact and coastline data are included in the package configuration.

In the game, `Esc` opens the quit dialog or closes the current input or
administrative view. `Q`/`E` zoom only on the Bridge, Weapons, and Helicopter
stations. At OPZ, the wheel zooms its independent chart down to a 5 NM radius,
dragging pans, and `K` toggles follow; Page Up/Down changes only the ship-centred
radar range. The event feed is shared across stations and retains operational
reports, completed orders, and alerts; transient input and selection hints stay
in the status banner. Feed and telemetry remain active but are hidden at OPZ.
The full context-sensitive key map is available under
`F1`.

## 6. Update

Quit the game before updating. In the repository, with the virtual environment
activated:

```sh
git pull --ff-only
. .venv/bin/activate
python -m pip install -r requirements.txt
```

For an editable package installation, also run:

```sh
python -m pip install -e .
```

Local saved games under `~/.u-jagd/` are not changed by `git pull`. Your own
changes in the repository can block a fast-forward update; in that case, first
check with `git status` and deliberately preserve or commit the changes.

## 7. Uninstall

If you launch exclusively from the checkout, removing the repository and its
virtual environment is sufficient. Remove a package installation from the
activated environment as follows:

```sh
python -m pip uninstall u-jagd
```

Saved games remain under `~/.u-jagd/` and must be deleted separately if desired.

## Troubleshooting

### `externally-managed-environment`

The installation was attempted outside the virtual environment. Do not bypass
the system protection with `--break-system-packages`; instead run:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

### Pygame cannot be installed

First update `pip` in the virtual environment. If no suitable wheel is available
for the ARM/Python combination in use and Pygame must be built locally, install
the usual build tools and SDL2 headers:

```sh
sudo apt install build-essential python3-dev pkg-config \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
python -m pip install -r requirements.txt
```

### Black window or `No available video device`

- Launch the game from a running graphical desktop session, not from a plain SSH
  session.
- Test `python main.py --windowed` first.
- Check whether `DISPLAY` is set: `printenv DISPLAY`.
- Do not permanently set `SDL_VIDEODRIVER=dummy`; the dummy driver is suitable
  only for automated, invisible tests.

### No sound or ALSA warnings

Check the output device and volume in the desktop environment or with
`alsamixer`. Pygame can use a specific ALSA device through the `AUDIODEV`
environment variable. The game catches errors when opening the audio device and
then intentionally continues silently; missing sound does not prevent startup.

### Poor performance or high CPU load

- Close other graphics- or CPU-intensive programs.
- Test windowed mode and do not scale the window unnecessarily large.
- Ensure that no debugging or remote desktop session is forcing software
  rendering.
- Use `python -m pip show pygame numpy` to check that both packages are installed
  in the active virtual environment.

### Contact database does not load

At startup, the message `[contact-db] ... using built-in default catalog` may
appear. In a Git checkout, check:

```sh
test -f data/contacts/subs.json
test -f data/coastlines/region.json
test -f data/coastlines/real_sectors.json.gz
```

Investigate missing or locally changed files with `git status`. The contact
database has a built-in fallback. The fixed legacy map may be empty if its file
is missing; however, a missing or damaged real-sector catalog prevents that
world mode from starting. For a package installation, reinstall the package
from the current checkout.

### Saving or loading fails

Saved games are stored in `~/.u-jagd/`. Check permissions and free space:

```sh
ls -ld "$HOME" "$HOME/.u-jagd"
df -h "$HOME"
```

Never launch the game with `sudo`, because this can create save files owned by
root. If this has already happened, correct the directory owner specifically.

### Collect diagnostic information

At least the following information is useful for a bug report:

```sh
python3 --version
python -m pip show pygame numpy
uname -a
git rev-parse --short HEAD
```

Also record the exact launch command, the complete terminal output, and whether
fullscreen, windowed mode, video, or audio is affected.
