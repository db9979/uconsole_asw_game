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
