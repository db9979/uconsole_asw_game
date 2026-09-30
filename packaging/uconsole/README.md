# U-Jagd auf der uConsole installieren

Im Terminal der uConsole als normaler Benutzer (nicht mit `sudo`):

```sh
curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
```

Danach startet das Spiel über **Spiele > U-Jagd**, die Desktop-Verknüpfung oder
`~/.local/bin/u-jagd`. Updates werden nie von selbst installiert: Gibt es ein
neues Release, zeigt der Startbildschirm (und das Hauptmenü) die Version, den
Eintrag aus dem Änderungsprotokoll, einen Hinweis, falls alte Spielstände damit
nicht mehr laden, und den Knopf **Jetzt updaten** (Taste U). Erst dann schließt
das Spiel, ein kleines Fenster zeigt Download und Prüfung, und die neue Version
startet. Ohne Netz erscheint einfach kein Hinweis. Ein zweiter Start öffnet das
Spiel nicht doppelt.

Entfernen (Spiel und Speicherstände bleiben):

```sh
sh ~/games/u-jagd/packaging/uconsole/install.sh --uninstall
```

Alle Details, Optionen und Fehlerbehebung:
[docs/install-uconsole.md](../../docs/install-uconsole.md)
([English](../../docs/install-uconsole.en.md)).
