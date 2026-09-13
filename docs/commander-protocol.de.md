# Commander-Protokoll und -Sicherheit

[English](commander-protocol.md)

Anwendung 0.2.0, API-Protokolle 1 und 2, ausschließlich Spielstandsformat v10. Diese
Versionen sind voneinander unabhängig. Zugangsdaten, Netzwerksitzungen, Leases,
Befehlswarteschlangen oder Vorschläge werden nicht gespeichert. Gemeinsame
Anmerkungen und von der Besatzung angenommene Ziel-/Navigations-Sollwerte verwenden
die normale Spielpersistenz.

## Zuständigkeit

CommanderConsole steuert den Listener lokal. CommanderBridge.pump wird einmal pro
Wall-Frame der Hauptschleife vor Game.update ausgeführt, auch in pausierten Frames.
Es liest öffentliche Beobachtungen und eigene Einheiten, validiert Befehle und
veröffentlicht abgelöstes JSON. HTTP-Handler importieren niemals Game/Pygame,
greifen nicht auf Simulationsobjekte zu und lösen keine Sensor-/TMA-Arbeit aus.
Methoden zum Laden eines Kandidaten haben keine Netzwerknebenwirkungen.

## Endpunkte des Legacy-Protokolls v1

| Methode / Route | Vertrag |
|---|---|
| GET /, /app.js, /style.css | Feste paketierte Ressourcen, beim Serverstart zwischengespeichert |
| GET /api/v1/ui?lang=en or de | Nur `commander.web.*`-Zeichenketten aus den Root-Katalogen |
| POST /api/v1/pair | JSON-Code; Erfolg liefert ein ausschließlich im Speicher gehaltenes Bearer-Token |
| GET /api/v1/state | Authentifizierter zwischengespeicherter Beobachtungs-Snapshot |
| GET /api/v1/chart | Authentifizierte zwischengespeicherte aktuelle Karte oder redigierte leere Karte |
| POST /api/v1/commands | Strikter Aktionsumschlag; 202 bedeutet eingereiht, nicht angewendet |

Geschützte Anfragen verwenden `Authorization: Bearer`. Token sind niemals
Query-Parameter oder Cookies. Änderungsanfragen erfordern `application/json` und
exakt denselben `Origin`. `Host` ist auf die gebundene IPv4-Adresse und den
tatsächlichen Port beschränkt (localhost ist für Loopback ebenfalls erlaubt). Es
gibt weder Wildcard-CORS, beliebige Routen/Dateien, Weiterleitungen, externe
Ressourcen noch HTML-Interpolation von erstelltem Text. Antworten verwenden
`no-store`, CSP, `nosniff` und Anti-Framing-Header. Zugriffsprotokolle enthalten
keine Zugangsdaten, weil sie deaktiviert sind.

## Remote-Crew-Protokoll v2

Protokoll v2 ist die aktuelle rollenorientierte Schnittstelle. Die Kopplung
erstellt eine unabhängige kryptografische Sitzung in einem HttpOnly-SameSite-Cookie
und liefert ein separates CSRF-Token in der exakten Sitzungsantwort. Zustandsändernde
Anfragen erfordern sowohl das Cookie als auch den exakten `Origin` und das
CSRF-Token.

Die Sitzung weist alle neun Stationen als verschachtelte Datensätze aus. Ein Client
kann mehrere Leases behalten, jede mit einer eigenen monotonen
`station_generation`. Die Zuweisung aktiviert die gewöhnliche `command`-Freigabe
der Lease sofort; `direct_fire`- und `sonar_audio`-Freigaben bleiben separat. Genau
eine behaltene Lease ist aktiv und wird durch eine separate monotone
`active_generation` identifiziert.
Stationsanfragen sind additiv; die Aktivierung gibt keine andere Lease frei.
Release, Widerruf, Übernahme, Ablauf, Pause, Fokusverlust und Weltersatz machen
die Berechtigung in ihrem jeweils definierten Geltungsbereich ungültig.

Die Aktivierung validiert die Ziel-Lease und ihre Stationsgeneration, vergleicht
aber keine ältere aktive Generation; dadurch kann ein Client nach einer
gleichzeitigen Host-Aktivierung jede noch behaltene Lease auswählen. Release- und
Simulationsbefehle behalten ihre Prüfungen von `active_generation` bei. Eine
v2-Lease sperrt die Eingabe an der entsprechenden lokalen uConsole-Station, ohne
die Host-Verwaltung oder den Remote-Befehlspfad im Hauptthread zu sperren.

Der Rollenzustand ist eine exakte Projektion gemäß Freigabeliste unter
`/api/v2/state`. Die aktive Rolle erhält ausschließlich Wahrheitsdaten eigener
Einheiten, bekannte Geografie und veröffentlichte Beobachtungen. Sie erhält niemals
Simulationsobjekte, versteckte IDs, unentdeckte Positionen, RNG-Zustand,
Zugangsdaten oder Spielstanddaten. OPZ erhält nur ausdrücklich freigegebene
Sonarbeobachtungen; die Klassifizierung ist davon unabhängig. Browser-Bezeichnungen
sind undurchsichtige Referenzen für die Lebensdauer einer Beobachtung.

Befehle verwenden strikte Umschläge mit `protocol`, kryptografischer Anfrage-ID
(`id`), clientbezogener Sequenz (`seq`), `station_generation`,
`active_generation`, `world_session`/`world_epoch`, `resource_revision`, `action`
und exakt begrenzten Parametern (`params`).
HTTP-Threads reihen nur abgelöste Umschläge ein. Der Hauptthread validiert erneut
und wendet angenommene Befehle genau einmal in deterministischer Stationsreihenfolge
und je Client in FIFO-Reihenfolge an. Direktfeueraktionen benötigen zusätzlich die
Direktfeuer-Freigabe der Station sowie die üblichen Prüfungen von Beobachtung,
Bereitschaft, Bestand, ROE und Einsatzbereich. Eine eingereihte Antwort wird vor
ihrem endgültigen Ergebnis niemals als erfolgreich gemeldet.

V2-Sitzungen, Clients, Leases, Historien, Warteschlangen, Abfragen und
Projektionsgrößen sind strikt begrenzt. Sonar-Audio ist ausschließlich live
verfügbar, wird separat freigegeben, ist an die aktive `station_generation` von
Sonar gebunden und
wird im Hauptthread anhand des projizierten Sonar-Abhörmodus sowie der Einstellungen
für Band, Notch und Gain gefiltert. Das Kavitationsgeräusch der Brücke wird nach
lokaler Tonfreigabe im Browser ausschließlich aus dem bereits freigegebenen
Eigenschiff-Kavitations-Boolean synthetisiert. Es ergänzt weder Endpunkt, Freigabe,
Befehl noch uConsole-Audiosteuerung. Die Sonarrollenprojektion erhält nur die
begrenzte Eigenschifffahrt und die TAS-Handhabungsgrenzen, die zur Erklärung eines
deaktivierten Array-Bedienelements nötig sind; Hovergründe prüfen niemals
verborgene Einheiten. Protokoll v1 bleibt aus Kompatibilitätsgründen exakt
unverändert und wird nicht stillschweigend um v2-Felder erweitert.

## Kopplung und Grenzen von Protokoll v1

- Explizite RFC1918- oder Loopback-IPv4-Bindung; keine Wildcard/öffentliche IPv4.
- Kryptografischer Code: `[0-9]{3}[A-Z]{3}`, fünf Minuten gültig, einmal verwendbar.
  Bei Erneuerung ist der Vorgänger ausgeschlossen. Der Serververgleich ist
  groß-/kleinschreibungssensitiv und erfolgt in konstanter Zeit.
- Fünf fehlgeschlagene Versuche innerhalb gleitender 60 Sekunden, global über alle
  IPs.
  Automatische Erneuerung löscht Fehlversuche nicht. Weitere Versuche liefern bei
  ausgeschöpftem Limit 429.
- Unabhängiges Bearer-Token aus 32 zufälligen Bytes und eine Idle-Lease von 30
  Sekunden, die durch authentifizierte State-/Chart-Abfragen erneuert wird. Eine
  Freigabe ist an diese Lease-Generation gebunden.
- Vier zugelassene Worker-Verbindungen, 1,5 Sekunden Inaktivitäts-Timeout und drei
  Sekunden absolute Deadline. Deadline-Timer sind durch die Worker begrenzt und
  werden bei der Bereinigung gejoint.
- JSON-Bodys mit höchstens 4096 Bytes; begrenzte Request-Line/Header, striktes
  Framing sowie Ablehnung doppelter Member, nicht endlicher Zahlen und unbekannter
  Felder.
- Warteschlange mit höchstens 32 Einträgen; die Bridge wendet höchstens vier
  Anfragen pro Wall-Frame an. Nach fünf Sekunden abgelaufene Anfragen ergeben eine
  endgültige Ablehnung und verschwinden nicht stillschweigend.
- Höchstens 256 projizierte Tracks, 128 Ereignisse, 32 aktuelle Ergebnisse und 128
  deduplizierte IDs. Karte mit höchstens 20.000 Vertices und 1.024 Polygonen; zu
  große Karten werden ausdrücklich weggelassen, statt teilweise falsch dargestellt.

HTTP bleibt unverschlüsselt. Kopplung, Origin-Prüfungen und Limits bieten keine
Vertraulichkeit im Netzwerk. Nur für ein vertrauenswürdiges LAN; keine
Portweiterleitung und kein öffentliches Hosting.

## Snapshot und Befehle von Protokoll v1

Der Zustand enthält `protocol`/`version`/`session`/`epoch`/`revision`/`seq`, Phase
und Befehlsverfügbarkeit, Uhren, bekannte Missionsinformationen, eigene Bereitschaft,
öffentliche Tracks, Besatzungsziel, Zielvorschlag, Navigationsvorschlag, Ereignisse
und Befehlsergebnisse. Das additive Protokoll-1-Objekt `environment` enthält den
ganzzahligen `sea_state` im Bereich 0-9 und den maßgeblichen booleschen Wert
`is_night`; unbekannte Werte sind `null`.
Menü/Editor/Splash verwenden dasselbe Schema mit eigener Geometrie und Umgebung
als `null` sowie leerer Mission, leeren Tracks, Ereignissen und leerer Karte.
Pausierte laufende Missionen behalten ein eingefrorenes schreibgeschütztes Bild.

Track-Referenzen und neutrale Bezeichnungen sind Identitäten für die Lebensdauer
einer Beobachtung, keine rohen Entity-IDs. Ersetzung/Wiedererfassung macht sie
ungültig. Nur modellierte AIS-Bezeichnungen werden weitergegeben; interne
Producer-Präfixe dürfen die Identität als Zivil-/Kriegsschiff nicht offenlegen.
Seed, RNG, versteckte Entity-/Profilinformationen oder Spielstand-Dumps werden
nicht exportiert.

Befehle enthalten `id`, `session`, `epoch`, `revision`, `action` und
aktionsspezifische Felder:

| Aktion | Zusätzliche Felder |
|---|---|
| classify | `track`, `value` (zulässige Bedienerklasse oder `null`) |
| affiliate | `track`, `value` (zulässige NATO-Zuordnung) |
| propose | `track` |
| clear_proposal | optional passender `track` |
| propose_navigation | `course` und/oder `speed_kn`; `course` in [0,360), Geschwindigkeit im konfigurierten Ruderbereich |

Alle erfordern Kopplung, eine an die Lease gebundene lokale Freigabe und aktive
Befehlszuständigkeit. Explizite Revisionsprüfungen lösen gleichzeitige Änderungen
von Besatzungs-/Commander-Anmerkungen auf. Die Wiederholung einer identischen
behaltenen ID spielt ihr Ergebnis erneut ab; eine Änderung ihrer Payload wird
abgelehnt. Eine separate Anfrage kann einen noch nicht abgeschlossenen Vorschlag
derselben Art nicht ersetzen und erhält `proposal_pending`; je ein Ziel- und ein
Navigationsvorschlag können gleichzeitig bestehen. Ergebnisse enthalten `id`,
`status` (`applied`/`rejected`) und `reasoncode`. Die Browser-Wiederherstellung
verwendet exakt denselben Umschlag erneut und wiederholt niemals automatisch mit
einer neuen ID.

Vorschläge können nur lokal angenommen werden. Die Annahme eines Zielvorschlags
validiert den aktuellen Kontakt erneut und setzt `Game.target`, ohne Auswahl/Hörfokus
der Besatzung zu ändern oder Waffen aufzurufen. Die Annahme eines
Navigationsvorschlags validiert Sitzung, Lease, Live-Phase, Brückenbereitschaft und
vollständige numerische Grenzen erneut, bevor Sollkurs/-geschwindigkeit atomar
geändert werden. Die Kursannahme erfordert eine funktionsfähige Brücke; ein gültiger
Vorschlag ausschließlich für die Geschwindigkeit kann dennoch angenommen werden.
Die physische Bewegung unterliegt weiterhin der normalen Schiffsphysik, dem Antrieb
und den Grenzen des Schleichmodus. Keine Remote-Aktion kann direkt steuern.
Air-/Missile-Sequenznamensräume können die Sonaridentität nicht als Alias verwenden.

Epochenwechsel lehnen eingereihte Aktionen über Übergänge bei
Verwaltung/Eingabe/Freigabe/Verbindung hinweg ab. Ein Weltersatz widerruft die
Kopplung und erzeugt beim nächsten Pump eine neue Sitzung. Der Browser benötigt
einen passenden Sitzungs-/Kartenkontext, bevor er das neue Bild offenlegt. Der alte
Ereignisrückstand löst Audio nach dem Neuverbinden nicht erneut aus.

Eine aktive Besatzungsstation hält die Protokollphase hinter der lokalen F1-Hilfe,
dem spielinternen F8-Kontakt-Analyzer, der F9-Besatzungsverwaltung und den
F10-Optionen auf `live`. Das Öffnen oder Schließen eines dieser Eingabebesitzer
macht über den Übergang hinweg eingereihte Befehle dennoch ungültig. Manuelle
Pause, Fokusverlust, Speichern/Laden, Beenden, Nationen, echte Editoren, Menüs und
Splash bleiben gesperrt.

Der Lookout nutzt ausschließlich den aktuellen Zustands-Snapshot, niemals
Kartengeografie oder Simulationsobjekte. Er ist nordorientiert und schiffszentriert:
Positionierte Beobachtungen sind Punkte, Meldungen mit reiner Peilung dagegen
Randmarkierungen ohne erfundene Entfernung. Seine Reichweite ist browserlokal und
sendet keinen Befehl. Seegang und Tag/Nacht beeinflussen nur die Darstellung; sie
sind keine Sichtbarkeitsmodelle, und Symbole belegen keine Plattformidentität. Der
Lookout zeichnet nur bei Snapshots, Tab-Aktivierung, lokaler Reichweitenänderung
oder Größenänderung und verwendet gerätepixelgerechte Backing-Dimensionen.

## Testumfang

Transporttests decken echtes Loopback-Framing, Host/Origin, Kopplung/TTL/Rate-Limits,
Lease-Änderungen, Trickle-Deadlines, Bereinigung, Warteschlangen und Antworten ohne
Zugangsdaten ab. Bridge-Tests decken Truth Traps, Namensräume, Aktualität,
Revisionen, Deduplizierung, Redigierung, Referenzen für die Objektlebensdauer,
Vorschläge sowie fehlgeschlagene/erfolgreiche Ladevorgänge ab. Integrationstests
kombinieren tatsächliches Game, HTTP und Annahme im Hauptthread. Chromium-Verträge
prüfen Browser-Abfragen, Befehle, XSS-inerte erstellte Zeichenketten,
Größenänderung, Redigierung, Audio-Ausgangsbasis, Wiederherstellung bei Unsicherheit
und reine Snapshot-Geometrie des Lookout. Die EN/DE-Matrix für
Desktop/Mobil/200 Prozent verifiziert das Ein-Bildschirm-Layout. Eine echte
LAN-/Hardware-Abnahme muss separat dokumentiert werden und darf nicht aus dem
Erfolg automatisierter Tests abgeleitet werden.
