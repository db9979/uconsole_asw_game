# U-Jagd als Webspiel im LAN

Der optionale Webmodus betreibt einen Raum ohne sichtbares Spielfenster. Ein
Python-Prozess führt die Simulation aus; Browser bedienen Stationen und die
Spielleitung. Ein gestarteter Prozess stellt genau einen Raum bereit. Die
bisherige lokale Spielweise und Commander LAN bleiben separat verfügbar.

## Start

Ein eigener HTTPS-Reverse-Proxy muss vorhanden sein. Er leitet normale HTTP- und
WebSocket-Anfragen weiter und reicht den öffentlichen `Host`-Header durch. Die
öffentliche Adresse muss im LAN per HTTPS erreichbar sein. Läuft der Proxy auf
demselben Gerät, starte mit:

```sh
.venv/bin/python main.py --web-host --public-origin https://spiel.example.lan
```

Läuft der Proxy auf einem anderen Gerät im vertrauenswürdigen LAN, gib die
private IPv4-Adresse des Spielgeräts ausdrücklich an. Beispiel:

```sh
.venv/bin/python main.py --web-host --web-bind 192.168.178.36 --public-origin https://spiel.example.lan
```

Der Proxy verwendet dann `http://192.168.178.36:8765` als Upstream. Ohne
`--web-bind` bleibt der Server auf `127.0.0.1`; `--web-port 9000` ändert den
Upstream-Port. `0.0.0.0` und öffentliche Adressen sind als Bind-Adresse gesperrt.
Das Programm prüft bei jeder Browseranfrage die exakte öffentliche Origin; ein
Proxy mit abweichender Adresse oder HTTP statt HTTPS funktioniert nicht. Der
Proxy muss auch `/ws/v2/sonar` und `/ws/v2/voice` als WebSocket durchreichen
und dabei `Sec-WebSocket-Protocol` unverändert weitergeben. Öffne die angezeigte
Adresse mit `/admin` für die Spielleitung.

Beim ersten Start erscheint im **lokalen Terminal** ein 15 Minuten gültiger
Einrichtungscode. Gib ihn auf der Einrichtungsseite ein und setze ein Host-Passwort
mit mindestens zwölf Zeichen. Das Passwort wird als gesalzener scrypt-Hash in
`~/.u-jagd/web-host.json` gespeichert. Für einen lokalen Reset starte mit
`--reset-web-host-password` zusätzlich zu den Webmodus-Argumenten; der alte
Hash wird entfernt und ein neuer Einrichtungscode angezeigt.

## Lokales Spiel (F9, Crew oder Solo) hinter einem Proxy

Auch das normale Spiel auf der uConsole kann Remote Crew zusätzlich über einen
HTTPS-Reverse-Proxy anbieten. Die direkte LAN-Adresse bleibt dabei nutzbar:

```sh
.venv/bin/python main.py --public-origin https://asw.example.net
.venv/bin/python main.py --public-origin https://asw.example.net --solo-crew
```

Der Proxy zeigt auf die im F9-Fenster angezeigte Adresse, z. B.
`http://192.168.178.36:8765`. Er darf den öffentlichen `Host`-Header
durchreichen oder durch die Upstream-Adresse ersetzen; ein explizites `:443`
ist ebenfalls erlaubt. Das F9-Fenster und die Solo-Anzeige nennen beide
Adressen. Über den Proxy gilt nur die exakte Origin `https://asw.example.net`,
über das LAN nur `http://<IP>:<Port>`; Kopplungscode, CSRF-Token und
HttpOnly-Cookies bleiben unverändert, das Cookie ist auf dem HTTPS-Weg
zusätzlich `Secure`. Ohne `--public-origin` antwortet der Server wie bisher
nur auf seiner LAN-Adresse; ein Proxy mit eigenem Hostnamen erhält dann
`403 Forbidden`.

Ist die Adresse aus dem Internet erreichbar, schützt allein der sechsstellige
Kopplungscode den Zugang (nach fünf Fehlversuchen je Minute wird er neu
erzeugt). Im Solo-Modus darf der gekoppelte Browser zusätzlich speichern,
laden und ein neues Spiel starten; im Dialog „Neues Spiel“ wählt er dabei die
Seite (Fregatte oder U-Boot, das dann die KI-Jäger jagen). Beschränke den Zugriff deshalb möglichst am
Proxy (z. B. Zugriffsliste, VPN oder Proxy-Anmeldung).

## Raum und Spiel

Die Spielleitung meldet sich unter `/admin` an. Dort stehen Raumcode,
Stationsanfragen, Zuteilung, Widerruf, Freigaben, Vorschläge und Serveroptionen bereit. **Spiel jetzt beenden** (Karte „Spiel beenden“, mit Rückfrage) stoppt den Spielprozess auf dem Server nach etwa zwei Sekunden, damit er nicht im Hintergrund weiterläuft; alle Verbindungen werden getrennt, nicht gespeicherter Fortschritt geht verloren. Der Link „Spiel öffnen“ führt zur vorhandenen
Browserkonsole mit allen neun Stationen und Spielsteuerung. Anfangs hält die
Spielleitung alle Stationen; eine Zuteilung überträgt eine Station exklusiv an
ein Crew-Mitglied. Ein Mitglied kann mehrere Stationen erhalten und zwischen
ihnen wechseln. Freie Stationen fallen an die Spielleitung zurück.

Crew-Mitglieder öffnen die Basisadresse, geben Name und Raumcode ein und fordern
Stationen an. Der Host kann auch eine bereits gehaltene Station übernehmen.
Direktfeuer und Sonar-Audio werden je Station separat freigegeben. Das Spiel
läuft immer in Echtzeit weiter, auch wenn die Spielleitung nicht angemeldet ist;
es gibt keine Pause. Laden oder ein neues Spiel wirft
vorbereitete Befehle weg und setzt Crew-Zuteilungen zurück.

Die Weboptionen verwalten Serversprache, SimLog, Besatzungsfunk und Live-AIS/ADS-B samt
Zugangsdaten. Sprache und Ton der Station stellt jeder Browser selbst ein;
Browser-Zoom steuert die Textgröße. Fenster- und Vollbildoptionen des lokalen
Spiels haben im fensterlosen Webmodus keine Wirkung.

Der Besatzungsfunk wird im Adminportal unter **Serveroptionen** für den
laufenden Start aktiviert und mit „Optionen speichern“ übernommen. An einer
zugeteilten Station wählt jedes Crew-Mitglied dann „Funk aktivieren“ und gibt
das Mikrofon frei. Zum Senden muss „Zum Sprechen halten“ oder **F** gedrückt
bleiben. Beim Loslassen, Fokusverlust, Stationswechsel oder Entzug der Station
endet die Übertragung. Es kann jeweils nur eine Station senden. Kopfhörer
verhindern Rückkopplungen. Sprachdaten und Funkfreigabe gelangen weder in
Spielstände noch in die Spielsimulation.

Live-AIS und Live-ADS-B benötigen die **prozedurale Karte** mit echten
Geokoordinaten. Auf der festen, stilisierten Karte bleiben beide Datenquellen
inaktiv. Das Adminportal zeigt den Verbindungsstatus beider Anbieter an.
OpenSky begrenzt die Zahl der Abrufe; bei HTTP 429 wartet der Server auf die
vom Anbieter genannte Freigabezeit. Auch bei bestehender Verbindung erscheinen
nur Kontakte innerhalb der modellierten Sensorreichweite.
Die OpenSky-Abfrage deckt deshalb nur die Sensorumgebung des eigenen Schiffs
ab und wandert bei größerer Bewegung mit. Mit Zugangsdaten wird ungefähr alle
drei Minuten abgefragt; ohne Zugangsdaten seltener. Die reduzierte Abfrage
schont das tägliche OpenSky-Kontingent, verzögert aber neue Flugkontakte.

## Sicherheit und Betrieb

Der Browser verbindet sich per HTTPS. Zwischen einem entfernten Proxy und dem
Spielgerät läuft HTTP samt Zugangsdaten und Sitzungs-Cookies über das LAN; nutze
dafür nur ein vertrauenswürdiges Netz oder einen verschlüsselten Tunnel und
begrenze den Zugriff auf den Upstream-Port möglichst auf den Proxy. Der
Spielserver akzeptiert Änderungen
nur mit exakter Origin und CSRF-Token. Pro Host-Konto gilt eine aktive Sitzung;
eine neue Host-Anmeldung beendet die alte. Veröffentliche den lokalen Port nicht
im Internet. Die Proxy-Einrichtung und sein Zertifikat werden außerhalb des
Spiels verwaltet.

Die Webverwaltung liegt unter `/api/v2/web/*` und nutzt die vorhandene v2-Sitzung.
Alle `/api/v1/*`-Routen bleiben abgeschaltet. Spielstände bleiben exakt v28.
