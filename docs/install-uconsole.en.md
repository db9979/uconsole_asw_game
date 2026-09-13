# Installing on the ClockworkPi uConsole

[Deutsche Version](install-uconsole.md)

This guide describes installing, launching, and updating U-Jagd from the
repository <https://github.com/db9979/uconsole_asw_game>. The target system is a
uConsole with a Debian-based ClockworkPi distribution, particularly a CM5
system. Commands without `sudo` run as a regular user.

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

The interface renders natively on a 1280 x 720 pixel canvas. In fullscreen it is
scaled to the available display area; in windowed mode, 1280 x 720 is the native
size.

Optional Remote Crew is configured on the uConsole with `F9` or through **F10 >
Commander LAN**. The service starts off on every launch.

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
stations. Notices in the event feed are limited to the active station; the full
context-sensitive controls are available under `F1`.

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
