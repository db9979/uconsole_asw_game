#!/bin/sh
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' "Run this installer with sudo." >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
helper=/usr/libexec/u-jagd-hotspot-helper
policy=/usr/share/polkit-1/actions/io.github.db9979.u-jagd.hotspot.policy

if [ "${1-}" = "--uninstall" ]; then
    rm -f -- "$helper" "$policy"
    printf '%s\n' "U-Jagd hotspot helper removed."
    exit 0
fi
if [ "$#" -ne 0 ]; then
    printf '%s\n' "Usage: sudo $0 [--uninstall]" >&2
    exit 2
fi
if ! /usr/bin/python3 -I -c 'import dbus' >/dev/null 2>&1; then
    printf '%s\n' "Missing python3-dbus. Install it with: sudo apt install python3-dbus" >&2
    exit 1
fi
if [ ! -x /usr/bin/pkexec ]; then
    printf '%s\n' "Missing pkexec. Install the polkit package first." >&2
    exit 1
fi

install -d -o root -g root -m 0755 /usr/libexec
install -o root -g root -m 0755 "$script_dir/u-jagd-hotspot-helper" "$helper"
install -o root -g root -m 0644 \
    "$script_dir/io.github.db9979.u-jagd.hotspot.policy" "$policy"
printf '%s\n' "U-Jagd hotspot helper installed. Restart U-Jagd if it is running."
