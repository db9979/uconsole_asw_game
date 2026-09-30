#!/bin/sh
# One-command installer for U-Jagd on the ClockworkPi uConsole.
#
#   curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
#
# Clones (or adopts) the game in $U_JAGD_DIR (default ~/games/u-jagd), creates
# its .venv, brings it to the newest GitHub release and adds a menu/desktop
# entry and the `u-jagd` command.  Later releases are never installed on their
# own: the game shows a new release on its start screen and installs it when
# you press "Update now".  Run as the normal user, not with sudo.
#   sh install.sh --uninstall   removes the menu entry and command.
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

U_JAGD_UPDATE_NOW=1 python3 "$APP_DIR/packaging/uconsole/u_jagd_updater.py" update
python3 "$APP_DIR/packaging/uconsole/u_jagd_updater.py" setup
say "installed. Start it from the menu (Games > U-Jagd) or with: ~/.local/bin/u-jagd"
