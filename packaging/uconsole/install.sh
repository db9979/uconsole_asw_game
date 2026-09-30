#!/bin/sh
# One-command installer for U-Jagd on the ClockworkPi uConsole.
#
#   curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
#
# Clones (or adopts) the game in $U_JAGD_DIR (default ~/games/u-jagd), creates
# its .venv, adds a menu/desktop entry, the `u-jagd` command and a background
# update timer.  Every start then updates to the newest GitHub release first;
# offline the installed version starts.  Run as the normal user, not with sudo.
# On a machine with NetworkManager and a wlan0 Wi-Fi device it also installs
# the small hotspot helper (asks for the sudo password once); without it, or
# with U_JAGD_NO_HOTSPOT=1, it prints a note and the game installs anyway.
#   sh install.sh --uninstall   removes the menu entry, command and timer.
set -eu

REPO_URL=https://github.com/db9979/uconsole_asw_game.git
APP_DIR=${U_JAGD_DIR:-"$HOME/games/u-jagd"}

say() { printf '%s\n' "U-Jagd: $*"; }
die() { printf '%s\n' "U-Jagd: $*" >&2; exit 1; }
note() { printf '%s\n' "U-Jagd: note: $*" >&2; }

# The multiplayer hotspot needs a root-owned helper; it is optional, so every
# failure here is a note and the game itself is installed regardless.
setup_hotspot() {
    kit="$APP_DIR/packaging/uconsole"
    manual="sudo sh $kit/install-hotspot-helper.sh"
    if [ "${U_JAGD_NO_HOTSPOT-}" = 1 ]; then
        say "skipping the hotspot helper (U_JAGD_NO_HOTSPOT=1)."
        return 0
    fi
    if [ ! -f "$kit/install-hotspot-helper.sh" ] || [ ! -f "$kit/u-jagd-hotspot-helper" ] \
            || [ ! -f "$kit/io.github.db9979.u-jagd.hotspot.policy" ]; then
        note "hotspot helper files are missing; multiplayer runs on an existing network only."
        return 0
    fi
    if ! command -v nmcli >/dev/null 2>&1; then
        note "NetworkManager not found, so no own hotspot; multiplayer runs on an existing network only."
        return 0
    fi
    if ! nmcli -t -f DEVICE,TYPE device status 2>/dev/null | grep -qx 'wlan0:wifi'; then
        note "no Wi-Fi device wlan0, so no own hotspot; multiplayer runs on an existing network only."
        return 0
    fi
    if cmp -s "$kit/u-jagd-hotspot-helper" /usr/libexec/u-jagd-hotspot-helper \
            && cmp -s "$kit/io.github.db9979.u-jagd.hotspot.policy" \
                /usr/share/polkit-1/actions/io.github.db9979.u-jagd.hotspot.policy; then
        say "hotspot helper already installed."
        return 0
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        note "sudo not found; install the hotspot helper later with: $manual (as root)"
        return 0
    fi
    say "installing the hotspot helper for multiplayer (needs your sudo password)"
    if ! /usr/bin/python3 -I -c 'import dbus' >/dev/null 2>&1 \
            && command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y python3-dbus || true
    fi
    if sudo sh "$kit/install-hotspot-helper.sh"; then
        say "hotspot helper installed: without a network, multiplayer opens its own Wi-Fi."
    else
        note "the hotspot helper was not installed; the game works without it. Try later with: $manual"
    fi
    return 0
}

[ "$(id -u)" -ne 0 ] || die "please run as your normal user, not with sudo."

if [ "${1-}" = "--uninstall" ]; then
    [ -f "$APP_DIR/packaging/uconsole/u_jagd_updater.py" ] || die "no installation in $APP_DIR"
    exec python3 "$APP_DIR/packaging/uconsole/u_jagd_updater.py" uninstall
fi
[ "$#" -eq 0 ] || die "usage: install.sh [--uninstall]"

missing=
command -v git >/dev/null 2>&1 || missing="$missing git"
command -v python3 >/dev/null 2>&1 || missing="$missing python3"
if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import venv, ensurepip' >/dev/null 2>&1 || missing="$missing python3-venv"
fi
if [ -n "$missing" ]; then
    say "installing system packages:$missing (needs your sudo password)"
    # shellcheck disable=SC2086
    sudo apt-get update && sudo apt-get install -y $missing python3-pip
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || die "Python 3.11 or newer is required ($(python3 --version 2>&1))."

if [ -d "$APP_DIR/.git" ]; then
    say "using existing checkout $APP_DIR"
    if [ ! -f "$APP_DIR/packaging/uconsole/u_jagd_updater.py" ]; then
        # A checkout from before the installer existed: bring it to main first.
        say "checkout predates the installer; updating it to main"
        [ "$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)" = main ] \
            || die "$APP_DIR is not on branch main; switch with 'git -C $APP_DIR checkout main' and try again."
        git -C "$APP_DIR" fetch origin main \
            && git -C "$APP_DIR" merge --ff-only FETCH_HEAD \
            || die "could not update $APP_DIR (local changes or another branch?). Run 'git -C $APP_DIR status', then 'git -C $APP_DIR pull --ff-only' and try again."
    fi
elif [ -e "$APP_DIR" ]; then
    die "$APP_DIR exists but is not a git checkout; set U_JAGD_DIR to another folder."
else
    say "downloading into $APP_DIR"
    mkdir -p "$(dirname -- "$APP_DIR")"
    git clone --branch main "$REPO_URL" "$APP_DIR"
fi

python3 "$APP_DIR/packaging/uconsole/u_jagd_updater.py" update
python3 "$APP_DIR/packaging/uconsole/u_jagd_updater.py" setup
setup_hotspot || note "hotspot helper setup skipped."
say "installed. Start it from the menu (Games > U-Jagd) or with: ~/.local/bin/u-jagd"
