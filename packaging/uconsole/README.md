# U-Jagd auf der uConsole installieren

Im Terminal der uConsole als normaler Benutzer (nicht mit `sudo`):

```sh
curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
```

Danach startet das Spiel über **Spiele > U-Jagd**, die Desktop-Verknüpfung oder
`~/.local/bin/u-jagd`. Jeder Start holt zuerst das neueste Release und startet
dann das Spiel; ohne Netz startet sofort die installierte Version. Zusätzlich
sucht ein Hintergrund-Timer alle sechs Stunden nach Updates.

Entfernen (Spiel und Speicherstände bleiben):

```sh
sh ~/games/u-jagd/packaging/uconsole/install.sh --uninstall
```

Alle Details, Optionen und Fehlerbehebung:
[docs/install-uconsole.md](../../docs/install-uconsole.md)
([English](../../docs/install-uconsole.en.md)).
