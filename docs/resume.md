# Wiederaufnahme

## Aktueller Stand (2026-10-05)

U-Jagd steht bei der Version aus `src/core/version.py` (1.3.x). Geschrieben
werden Spielstände im Format aus `SAVE_VERSION` (v53); ältere ab
`save_migrate.MIGRATE_FROM` (v38) werden beim Laden angehoben. Remote Crew
spricht Protokoll v2. Jede Änderung erhöht die Patch-Version und bekommt einen
Eintrag oben in `CHANGELOG.md` und `CHANGELOG.de.md`; das README zeigt nur die
neueste Version. Die Arbeit läuft über Pull Requests auf GitHub; der Verlauf
steht in den Changelogs und in der Versionsgeschichte, nicht in diesem Dokument.

Prüfungen: `.github/workflows/tests.yml` führt bei jedem Pull Request die
Testsuite (mit Chromium für die Browser-Tests), die Katalog-, Handbuch-,
Schema- und Changelog-Prüfungen, die Kalibrierung und den Smoke-Test aus.
Hardware-Prüfpunkte der uConsole stehen in `docs/hardware-acceptance.md`.
Fairness (Gewinnraten KI gegen KI und gegen das besetzte U-Boot) wird vor und
nach spielwirksamen Änderungen gemessen; die Ergebnisse liegen außerhalb des
Repositorys je Paket mit einer kurzen README.

## Offene Arbeit

Grundlage ist der Verbesserungsplan nach der Gesamtprüfung vom 05.10.2026
(Kennungen wie dort):

- **Abnahme auf der echten uConsole (L6):** Die Tabellen in
  `docs/hardware-acceptance.md` sind seit 1.3.0 leer; der Faktor zwischen x86
  und Gerät ist nur geschätzt. Ein Kurzlauf je Release mit
  `U_JAGD_PERF_DEBUG=1`, Ergebnis in `docs/verification-log.md`.
- **Ruckler (L1 bis L5):** Schallstrahl-Tabellen und Sensor-Takt im
  Hauptthread, Speichern im Hauptthread, offene Zeichen-Bremsen, automatische
  niedrige Grafik.
- **Bedienregeln (B1 bis B6), Browser wie uConsole (W1 bis W5), Release (R1,
  R2):** siehe Plan.
- **Taktische Tiefe (T1 bis T5):** Die offenen Simulationslücken stehen oben in
  `docs/simulation-gaps.md`.
- **Wartung:** `_handle_owned_event` aufteilen; `src/enemies/sub.py` liegt nahe
  der Zeilengrenze aus `tests/test_module_size.py`.

Historie: Die Wiederaufnahme des Durchlaufs 0.1.7 bis 1.3.0 steht in
`docs/history/resume-0.1.7-1.3.0.md`.
