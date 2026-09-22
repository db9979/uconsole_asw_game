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

## Raum und Spiel

Die Spielleitung meldet sich unter `/admin` an. Dort stehen Raumcode,
Stationsanfragen, Zuteilung, Widerruf, Freigaben, Vorschläge und Serveroptionen bereit. Der Link „Spiel öffnen“ führt zur vorhandenen
Browserkonsole mit allen neun Stationen und Spielsteuerung. Anfangs hält die
Spielleitung alle Stationen; eine Zuteilung überträgt eine Station exklusiv an
ein Crew-Mitglied. Ein Mitglied kann mehrere Stationen erhalten und zwischen
ihnen wechseln. Freie Stationen fallen an die Spielleitung zurück.

Crew-Mitglieder öffnen die Basisadresse, geben Name und Raumcode ein und fordern
Stationen an. Der Host kann auch eine bereits gehaltene Station übernehmen.
Direktfeuer und Sonar-Audio werden je Station separat freigegeben. Wenn die
Spielleitung länger als 15 Sekunden nicht anwesend ist, pausiert das Spiel;
nach erneuter Anmeldung kann sie fortsetzen. Laden oder ein neues Spiel wirft
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
Alle `/api/v1/*`-Routen bleiben abgeschaltet. Spielstände bleiben exakt v10.
