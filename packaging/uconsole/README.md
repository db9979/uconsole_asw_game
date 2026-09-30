# U-Jagd auf der uConsole installieren

Im Terminal der uConsole als normaler Benutzer (nicht mit `sudo`):

```sh
curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
```

Danach startet das Spiel über **Spiele > U-Jagd**, die Desktop-Verknüpfung oder
`~/.local/bin/u-jagd`. Jeder Start holt zuerst das neueste Release und startet
dann das Spiel; ohne Netz startet sofort die installierte Version. Zusätzlich
sucht ein Hintergrund-Timer alle sechs Stunden nach Updates. Beim Start zeigt
ein kleines Fenster sofort, was gerade passiert (Update-Suche, Download,
Start); ein zweiter Start öffnet das Spiel nicht doppelt.

Hat die uConsole NetworkManager und das WLAN-Gerät `wlan0`, richtet der
Installer auch den kleinen Hotspot-Helfer für den Mehrspieler ein (fragt einmal
nach dem `sudo`-Passwort). Ohne `sudo`, ohne NetworkManager oder auf einem
anderen Rechner gibt er nur einen Hinweis aus und installiert das Spiel trotzdem;
`U_JAGD_NO_HOTSPOT=1` überspringt den Schritt. Später nachholen oder nach einem
Update auffrischen: den Installer erneut ausführen oder
`sudo sh ~/games/u-jagd/packaging/uconsole/install-hotspot-helper.sh`.
Der Hotspot behält WLAN-Name und Passwort (gespeichert in
`/var/lib/u-jagd/hotspot.json`, nur für root lesbar), damit Handys, die einmal
beigetreten sind, sich von selbst wieder verbinden; `F9` > Erweiterte
Netzwerkeinstellungen > **Neues Hotspot-Passwort** erzeugt bei ausgeschaltetem
Mehrspieler ein neues Passwort.

Entfernen (Spiel und Speicherstände bleiben):

```sh
sh ~/games/u-jagd/packaging/uconsole/install.sh --uninstall
```

Alle Details, Optionen und Fehlerbehebung:
[docs/install-uconsole.md](../../docs/install-uconsole.md)
([English](../../docs/install-uconsole.en.md)).
