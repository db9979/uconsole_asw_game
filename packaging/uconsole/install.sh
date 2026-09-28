#!/bin/sh
# One-command installer for U-Jagd on the ClockworkPi uConsole.
#
#   curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
#
# Clones (or adopts) the game in $U_JAGD_DIR (default ~/games/u-jagd), creates
# its .venv, adds a menu/desktop entry, the `u-jagd` command and a background
# update timer.  Every start then updates to the newest GitHub release first;
# offline the installed version starts.  Run as the normal user, not with sudo.
#   sh install.sh --uninstall   removes the menu entry, command and timer.
set -eu

REPO_URL=https://github.com/db9979/uconsole_asw_game.git
APP_DIR=${U_JAGD_DIR:-"$HOME/games/u-jagd"}

say() { printf '%s\n' "U-Jagd: $*"; }
die() { printf '%s\n' "U-Jagd: $*" >&2; exit 1; }

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
elif [ -e "$APP_DIR" ]; then
    die "$APP_DIR exists but is not a git checkout; set U_JAGD_DIR to another folder."
else
    say "downloading into $APP_DIR"
    mkdir -p "$(dirname -- "$APP_DIR")"
    git clone --branch main "$REPO_URL" "$APP_DIR"
fi

python3 "$APP_DIR/packaging/uconsole/u_jagd_updater.py" update
python3 "$APP_DIR/packaging/uconsole/u_jagd_updater.py" setup
say "installed. Start it from the menu (Games > U-Jagd) or with: ~/.local/bin/u-jagd"
