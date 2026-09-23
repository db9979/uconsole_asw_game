#!/usr/bin/env bash
# Desktop launcher: keep startup errors visible in the terminal.
set -u

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd) || exit 1
cd -- "$project_dir" || exit 1

if [[ ! -x .venv/bin/python ]]; then
    printf 'U-Jagd: Python-Umgebung fehlt: %s/.venv/bin/python\n' "$project_dir" >&2
    read -r -p 'Zum Schliessen Enter druecken ... ' _
    exit 1
fi

.venv/bin/python main.py --web-host "$@"
status=$?
if (( status != 0 )); then
    printf '\nU-Jagd-Webserver wurde mit Fehlercode %s beendet.\n' "$status" >&2
    read -r -p 'Zum Schliessen Enter druecken ... ' _
fi
exit "$status"
