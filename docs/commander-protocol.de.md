# Commander-Protokoll und -Sicherheit

[English](commander-protocol.md)

Anwendung 1.3.10, API-Protokoll 2, ausschließlich Spielstandsformat v39. Diese
Versionen sind voneinander unabhängig. Zugangsdaten, Netzwerksitzungen, Leases,
Befehlswarteschlangen oder Vorschläge werden nicht gespeichert. Gemeinsame
Anmerkungen und von der Besatzung angenommene Ziel-/Navigations-Sollwerte verwenden
die normale Spielpersistenz.

## Zuständigkeit

CommanderConsole steuert den Listener lokal. CommanderBridge.pump wird einmal pro
Wall-Frame der Hauptschleife vor Game.update ausgeführt, auch in Menü-Frames.
Es liest öffentliche Beobachtungen und eigene Einheiten, validiert Befehle und
veröffentlicht abgelöstes JSON. HTTP-Handler importieren niemals Game/Pygame,
greifen nicht auf Simulationsobjekte zu und lösen keine Sensor-/TMA-Arbeit aus.
Methoden zum Laden eines Kandidaten haben keine Netzwerknebenwirkungen.

## Endpunkte von Protokoll v2

| Methode / Route | Vertrag |
|---|---|
| GET /, /js/**, /css/**, /fonts/** | Feste paketierte Ressourcen (exakte Routentabelle aus `src/commander/assets.py`), beim Serverstart zwischengespeichert |
| GET /api/v2/ui?lang=en or de | Nur `commander.web.*`-Zeichenketten aus den Root-Katalogen |
| GET /api/v2/contacts | Öffentlicher paketierter Kontaktreferenzkatalog |
| POST /api/v2/pair | JSON-Kopplungscode; Erfolg erzeugt Cookie-Sitzung und CSRF-Zustand |
| GET /api/v2/session | Authentifizierter Client-, Lease-, Freigabe- und Sequenzzustand |
| GET /api/v2/state, /chart | Aktive Rollenprojektion und passende bekannte Karte |
| GET /api/v2/results, /proposals, /events | Rollen- und sitzungsbegrenzter Befehlszustand |
| GET /api/v2/simlog | Vom Host freigegebene Full-Truth-Diagnose-Snapshots, höchstens 64 Einträge |
| POST /api/v2/stations/request, /activate, /release | Strikte Lease-Operationen |
| POST /api/v2/commands | Strikter Aktionsumschlag; 202 bedeutet eingereiht, nicht angewendet |
| POST /api/v2/sonar/audio | Separat freigegebene Live-Sonaraudio-Abfrage |
| POST /api/v2/helicopter/audio | Separat freigegebene Live-Helikopteraudio-Abfrage |
| GET /ws/v2/sonar/audio, /ws/v2/helicopter/audio | Geleaster, nur lesender binaerer PCM-Strom (WebSocket-Upgrade) |
| GET /ws/v2/sonar | Binärer Anzeigestrom der aktiven Sonarrollen-Lease (WebSocket-Upgrade) |
| POST /api/v2/logout | Widerruft die aktuelle Sitzung und löscht ihr Cookie |

Alle Routen unter `/api/v1/*` sind entfernt und liefern 404 ohne Weiterleitung
oder Fallback. Geschützte Anfragen verwenden das HttpOnly-Sitzungscookie.
Änderungsanfragen erfordern `application/json`, exakt denselben `Origin` und nach
der Kopplung das exakte CSRF-Token. `Host` ist auf die gebundene IPv4-Adresse und den
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
Release, Widerruf, Übernahme, Ablauf und Weltersatz machen
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

Jede zugewiesene v2-Rolle erhält dieselbe abgelöste Umgebungszusammenfassung:
vorgegebenen ganzzahligen `sea_state`, überblendeten `effective_sea_state`, den
maßgeblichen Wert `is_night`, Wetterart, nautische Wind-Herkunftsrichtung,
Windgeschwindigkeit in Knoten, Regenstärke und Sicht in NM. Jede Rolle erhält
außerdem den gemeinsamen Block `weather_station` für den Analysedialog (Taste 0):
eigene `atmosphere` (Barometer und 3-Stunden-Tendenz, Luft-/Wassertemperatur,
Böen, Beaufort, Wolkenuntergrenze, Vereisung, Tageslicht, Mondphase),
qualitative `effects`, die abgeleitete Helikopter-Entscheidung `flight`
(CLEAR/LIMITED/NO-GO mit Werten und konfigurierten Grenzwerten) und `profile`.
`profile` ist null, bis das Sonar einen Bathythermographen genommen hat; danach
enthält es ausschließlich diese Messung (Alter, Versatz, Veraltet-Kennzeichen,
Schicht, Tiefen und Geschwindigkeiten, SOFAR-Achse oder null, KZ-Bänder) mit
höchstens neun Strahlen zu 64 Punkten und einem begrenzten, daraus berechneten
Schattenraster. Die Helikopterrolle erhält zusätzlich abgeleitete Freigaben für
Start und Tauchsonar sowie den Querwind; verborgener Luftfahrzeug- oder
Wetterzustand und das wahre Meeresprofil werden nicht übertragen.
Taktische Beobachtungszeilen tragen `visual_class` und `visual_type`: null
außer bei Meldungen des Brückenausgucks, dort die erkannte Klasse (feste
Codeliste) und nach der Identifizierung der Katalog-Typname eines Kriegsschiffs
oder Militärflugzeugs. Das sind Beobachtungen, nie die Klassifizierung oder
Zugehörigkeit des Bedieners. Die Brückenrolle erhält zusätzlich `sightings`, die
neuesten 24 Ausguck-Meldungen (Zeit, gesichtete Art oder Klassencode, Typ,
Peilung, Entfernung); Handelsschiffnamen und Identitäten des Live-Verkehrs sind
nie enthalten.
Die Autocrew-Projektion jeder Rolle enthält ausschließlich deren Aktivierung und
Status. Zugangsdaten, Leases und Autocrew-Befehle gehören nicht zur Projektion.

Befehle verwenden strikte Umschläge mit `protocol`, kryptografischer Anfrage-ID
(`id`), clientbezogener Sequenz (`seq`), `station_generation`,
`active_generation`, `world_session`/`world_epoch`, `resource_revision`, `action`
und exakt begrenzten Parametern (`params`).
HTTP-Threads reihen nur abgelöste Umschläge ein. Der Hauptthread validiert erneut
und wendet angenommene Befehle genau einmal in deterministischer Stationsreihenfolge
und je Client in FIFO-Reihenfolge an. Nur Bediener-Annotationen des gemeinsamen
Lagebilds (Klassifizierung, Zugehörigkeit, Track-ID, Freigabe, Fusion,
Qualifizierung, ESM-Annotation, Zielvorschlag) müssen noch zur vom Browser
gesehenen `resource_revision` passen (`revision_conflict`); alle übrigen Befehle
lösen ihre opaken Referenzen erst bei der Anwendung auf und werden nicht
abgelehnt, nur weil sich ein anderer Kontakt geändert hat. Direktfeueraktionen benötigen zusätzlich die
Direktfeuer-Freigabe der Station sowie die üblichen Prüfungen von Beobachtung,
Bereitschaft, Bestand, ROE und Einsatzbereich. Eine eingereihte Antwort wird vor
ihrem endgültigen Ergebnis niemals als erfolgreich gemeldet.

V2-Sitzungen, Clients, Leases, Historien, Warteschlangen, Abfragen und
Projektionsgrößen sind strikt begrenzt. Sonar-Audio ist ausschließlich live
verfügbar, wird separat freigegeben, ist an die aktive `station_generation` von
Sonar gebunden und
wird im Hauptthread anhand des projizierten Sonar-Abhörmodus sowie der Einstellungen
für Band, Notch und Gain gefiltert. Der Server hält die letzten 40 Blöcke (zehn
Sekunden), damit ein kurz stockender Client der Reihe nach aufholt; ältere Blöcke
werden verworfen und als Diskontinuität gemeldet. Der Browser startet die Wiedergabe
etwa zwei Sekunden (acht Blöcke) hinter dem neuesten Block. Das AudioWorklet regelt
diesen Vorlauf, indem es den Strom um höchstens 2 % schneller oder langsamer liest;
Uhrendrift und Jitter leeren oder überfüllen ihn so nicht; es hält höchstens sechs
Sekunden. Bei einem Unterlauf spielt es einen nicht periodischen, granular aus der
letzten halben Sekunde erzeugten Ersatz und puffert eine Sekunde (vier Blöcke) nach,
bevor frische Daten weiterlaufen; nach drei Sekunden ohne Daten spielt es leises
neutrales Rauschen und kennzeichnet den Strom als veraltet. Überblendet wird nur an
echten Brüchen. Der uConsole-Mixer-Worker nutzt dasselbe elastische Verfahren mit
1,5 s Vorlauf, fünf Sekunden Warteschlangengrenze und derselben Drei-Sekunden-Regel;
die Hauptschleife holt bis zu 2,5 s eines hängenden Frames nach, Audio dieser Länge
wird also verdeckt, nie abgeschnitten. Ein vorübergehender Fehler der
Zustandsabfrage oder HTTP 503 verwirft gepuffertes Audio nicht; der Audio-Endpunkt
prüft Sitzung und Stationsrecht weiterhin bei jeder Anfrage. Die Blocknummerierung
ist über die Lebensdauer des Host-Prozesses monoton: Ein geleerter Stream (ein
Epoch-Schritt nach lokaler Eingabe am Host, eine neue Freigabe) zählt oberhalb aller
bisher gesendeten Nummern weiter und überspringt eine, sodass der Neustart als Lücke
erscheint; ein umgestimmter Empfänger (Peilungsschwenk) überspringt ebenfalls eine
Nummer, damit Browser überblenden statt fremdes Audio zu verbinden. Nur eine Nummer
vor allem je Veröffentlichten (Neustart des Hosts) wird mit Diskontinuität
zurückgesetzt. Es gibt kein dauerhaftes Eigenschiff-Ambientgeräusch,
weder lokal noch im Browser; die Tonfreigabe aktiviert nur synthetisierte
Alarm-/Gefechtseffekt-Signale und diesen Live-Sonar-/Hubschrauber-Stream.

Der zusaetzliche Audio-WebSocket verwendet das Subprotokoll `u-jagd-audio-v2`,
das HttpOnly-Sitzungscookie, den genauen Origin sowie aktive Station und
Audiofreigabe. Jede binaere Nachricht mit 2060 Byte enthaelt `UJA2`, eine
Little-Endian-Sequenznummer mit 64 Bit und 1024 Mono-PCM-Samples mit 16 Bit
bei 4096 Hz. Sequenzluecken zeigen uebersprungene Bloecke, einen Epoch-Schritt
oder einen Peilungsschwenk an. Ein ohne Cursor geoeffneter Socket erhaelt hoechstens
die neuesten acht ausstehenden Bloecke; ein Reconnect uebergibt `?after=<Sequenz>`
(streng geprueft), sodass nichts erneut gesendet wird, was das Worklet schon haelt;
eine doppelte Nummer zaehlt das Worklet und verwirft sie. Der Audio-Socket
toleriert einen Sendestau von sechs Sekunden, bevor er schliesst.
Die HTTP-Abfrage bleibt der Fallback. Beide Transporte nehmen weder Browseraudio
noch Simulationsbefehle an.

Für die Diagnose auf dem Gerät schreibt `U_JAGD_AUDIO_DEBUG=1` begrenzte,
kontaktfreie Werte zu Receiver-Blockrate, Mixer-Unterläufen, verdeckten
Blöcken, Ratenkorrektur, Pufferstand, leer gelaufenem Mixerkanal, verspäteten
Worker-Durchläufen, Eingangslücken und Verlusten nach
`~/.u-jagd/audio_debug.log`; `U_JAGD_PERF_DEBUG=1` ergänzt in `perf_debug.log`
Frame-Spitzen, die Hauptthread-Zeiten je Phase (Simulation, Audio, Remote-Crew-
Veröffentlichung, Ereignisse, Live-Verkehr, Zeichnen) und das Nachholen der
Simulationszeit. Im Browser zeigen die Entwicklerwerkzeuge
`window.uJagdAudioDiagnostics` mit Puffersekunden, Sequenzlücken, verworfenen
Duplikaten, verdrängten und verdeckten Blöcken, Wiedergaberate, Veraltet-Zustand
und Transport. `tools/audio_soak.py` fährt die gesamte Kette headless mit
simulierten Browsern (oder als Client auf einem anderen Rechner) und meldet die
Kontinuität. Beide Protokolle bleiben außerhalb der Spielstände.

Die Sonarrollenprojektion erhält nur die
begrenzte Eigenschifffahrt und die TAS-Handhabungsgrenzen, die zur Erklärung eines
deaktivierten Array-Bedienelements nötig sind; Hovergründe prüfen niemals
verborgene Einheiten.

Der Sonar-Anzeigestrom ist ein zusätzlicher Transport von Protokoll v2 und keine
Simulationsschnittstelle. Das Upgrade gelingt nur mit exakt gleichem `Origin`,
authentifiziertem HttpOnly-Cookie, aktiver Sonar-Lease samt Generation und dem
Subprotokoll `u-jagd-sonar-v2`. Pro Sitzung wird höchstens ein Strom zugelassen.
Widerruf, Rollenaktivierung, Lease-Wechsel, Weltersatz oder Serverende machen ihn
sofort ungültig. Die normale Zustandsabfrage bleibt maßgeblich und dient als
automatischer Fallback. Während der Strom läuft, fragt der Client
`/api/v2/state?sonar=stream` ab; diese Sonarprojektion lässt die bereits binär
übertragenen Spektralfelder weg. Das Cookie gilt für `/`, damit der Browser es an
`/api/v2/*` und die feste WebSocket-Route senden kann; es bleibt HttpOnly,
SameSite=Strict und erscheint weder in JavaScript noch in URLs oder Nutzdaten.

Jede Servernachricht ist genau ein abschließender Binärframe mit höchstens 4096
Bytes. Sein 60 Byte großer Little-Endian-Header lautet
`<4sBBHQQdfHHHHHHfff>`: Magic `UJS2`, Stromversion, Flags, Headerlänge,
monotone Stromsequenz, Weltepoche, Simulationszeit, Hörpeilung, fünf Feldlängen,
eine reservierte Länge sowie das Alter von Broadband, LOFAR und DEMON. Danach
folgen fünf Bytefelder: neueste Broadband-, LOFAR- und DEMON-Zeile, aktuelles
LOFAR- und aktuelles DEMON-Spektrum. Die Werte stammen ausschließlich aus der
bereits abgelösten Freigabelistenprojektion und werden von [0,1] auf [0,255]
quantisiert. Der Server hält nur das neueste Paket; ein langsamer Client überspringt
Zwischenbilder und wird bei stockender Ausgabe getrennt. So entstehen weder eine
unbegrenzte Renderwarteschlange noch Einflüsse auf die deterministische Simulation.

## Kopplung und Grenzen von Protokoll v2

- Explizite RFC1918- oder Loopback-IPv4-Bindung; keine Wildcard/öffentliche IPv4.
- Kryptografischer Code: `[0-9]{3}[A-Z]{3}`, für weitere Besatzungsmitglieder bis
  zum ausdrücklichen Widerruf oder zur Erneuerung nach Fehlversuchen wiederverwendbar.
  Bei Erneuerung ist der Vorgänger ausgeschlossen. Der Serververgleich ist
  groß-/kleinschreibungssensitiv und erfolgt in konstanter Zeit.
- Fünf fehlgeschlagene Versuche innerhalb gleitender 60 Sekunden, global über alle
  IPs.
  Automatische Erneuerung löscht Fehlversuche nicht. Weitere Versuche liefern bei
  ausgeschöpftem Limit 429.
- Unabhängige kryptografische Cookie-Sitzung mit acht Stunden Idle-Limit. Die
  Anwesenheitsabfrage erneuert eine Stations-Lease von 15 Sekunden; Freigaben
  binden an deren Generation. Höchstens zwölf Clients können Sitzungen halten.
- Sechzehn zugelassene Worker-Verbindungen, 1,5 Sekunden Inaktivitäts-Timeout und
  drei Sekunden absolute Deadline für gewöhnliches HTTP. Ein erfolgreich
  authentifiziertes Sonar-Upgrade belegt einen begrenzten Worker-Platz, bis es
  ungültig wird oder schließt. Deadline-Timer sind durch die Worker begrenzt und
  werden bei der Bereinigung gejoint.
- JSON-Bodys mit höchstens 4096 Bytes; begrenzte Request-Line/Header, striktes
  Framing sowie Ablehnung doppelter Member, nicht endlicher Zahlen und unbekannter
  Felder.
- Globale Befehlswarteschlange mit höchstens 64 und je Client höchstens acht
  Einträgen. Nach zwei Sekunden veraltete Befehle ergeben eine endgültige
  Ablehnung und verschwinden nicht stillschweigend.
- Höchstens 256 projizierte Tracks, 128 Ereignisse und 64 SimLog-Einträge. Karte
  mit höchstens 20.000 Vertices und 1.024 Polygonen; zu
  große Karten werden ausdrücklich weggelassen, statt teilweise falsch dargestellt.

HTTP bleibt unverschlüsselt. Kopplung, Origin-Prüfungen und Limits bieten keine
Vertraulichkeit im Netzwerk. Nur für ein vertrauenswürdiges LAN; keine
Portweiterleitung und kein öffentliches Hosting.

## Projektionen und Befehle von Protokoll v2

Der Rollenzustand enthält Protokoll/Version, Weltsitzung/-epoche,
Ressourcenrevision, Phase und Befehlsverfügbarkeit, Uhren, bekannte
Missionsinformationen, eigene Bereitschaft, öffentliche Tracks und die
Umgebungszusammenfassung. Vorschläge, Ereignisse, Befehlsergebnisse und
SimLog-Historie verwenden getrennte authentifizierte Endpunkte, damit jeder seine
eigene Sitzungs-, Rollen-, Autoritäts- und Freigabegrenze erzwingt.
Menü/Editor/Splash verwenden dasselbe Schema mit eigener Geometrie und Umgebung
als `null` sowie leerer Mission, leeren Tracks, Ereignissen und leerer Karte.

Track-Referenzen und neutrale Bezeichnungen sind Identitäten für die Lebensdauer
einer Beobachtung, keine rohen Entity-IDs. Ersetzung/Wiedererfassung macht sie
ungültig. Nur modellierte AIS-Bezeichnungen werden weitergegeben; interne
Producer-Präfixe dürfen die Identität als Zivil-/Kriegsschiff nicht offenlegen.
Seed, RNG, versteckte Entity-/Profilinformationen oder Spielstand-Dumps werden
nicht exportiert.

Die ELOKA-Auffassungszeile von v2 enthält zusätzlich die abgeleiteten Felder
`signal_state` (`LIVE`, `RECENT`, `MEMORY` oder `UNCONFIRMED`) und `operational`.
Die Browserfilter für Status, Mindestbedrohung und Frequenzband bleiben
clientlokal und verwenden für Auffassungsliste, Kontakte, Scope und barrierefreie
Textalternative dieselbe Teilmenge. Aktive ECM-Ziele bleiben sichtbar. Die Zeilen
tragen außerdem den gemessenen Spitzenpegel `signal_db`, die gemessene
Antennenumlaufzeit `scan_period_s` (oder null) und eine `range_estimate_nm`, die
nur aus diesem Pegel und der Leistungsklasse der besten Katalog-Hypothese
abgeleitet ist (oder null); wahre Entfernung und verborgene Senderidentität werden
weder projiziert noch filterbar gemacht.

Befehle enthalten `protocol`, kryptografische Anfrage-ID, Clientsequenz, Station,
Stations- und Aktivgeneration, Weltsitzung/-epoche, Ressourcenrevision, Aktion und
exakte aktionsspezifische Parameter. Vorschlagsaktionen sind:

| Aktion | Zusätzliche Felder |
|---|---|
| propose_target | Beobachtungs-`ref` |
| clear_target_proposal | keine Parameter |
| propose_navigation | `course` und/oder `speed_kn`; `course` in [0,360), Geschwindigkeit im konfigurierten Ruderbereich |

Alle Aktionen erfordern Kopplung, eine aktive Rollen-Lease, die Befehlsfreigabe
der Rolle und aktive Befehlszuständigkeit; Direktfeueraktionen erfordern ihre
zusätzliche Freigabe. Explizite Revisionsprüfungen lösen gleichzeitige Änderungen
der Besatzung auf. Die Wiederholung einer identischen
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

Schadensereignisse sind für Brücke und Schadensabwehr sichtbar, Bedrohungen für
Brücke, OPZ und Waffen und Missionsereignisse für jede Rolle. Der Lebenszyklus
eines Vorschlags ist nur für Ursprungssitzung und -rolle sichtbar. SimLog hält
höchstens 64 frühere abgelöste Diagnose-Snapshots mit ihren
Simulationszeitstempeln. Eine ausdrückliche Host-Freigabe legt über diesen
schreibgeschützten Endpunkt die vollständige Simulationswahrheit offen;
deaktiviertes oder nicht freigegebenes SimLog liefert keine Historie.

Epochenwechsel lehnen eingereihte Aktionen über Übergänge bei
Verwaltung/Eingabe/Freigabe/Verbindung hinweg ab. Ein Weltersatz widerruft die
Kopplung und erzeugt beim nächsten Pump eine neue Sitzung. Der Browser benötigt
einen passenden Sitzungs-/Kartenkontext, bevor er das neue Bild offenlegt. Der alte
Ereignisrückstand löst Audio nach dem Neuverbinden nicht erneut aus.

Die Mission läuft immer in Echtzeit und kennt keine Pause. Die Protokollphase
bleibt hinter jedem lokalen Menü und Overlay (Hilfe, Optionen, Speichern/Laden,
Beenden-Abfrage, Nationen, F8-Analyzer, F9-Verwaltung) und über einen Fokusverlust
hinweg `live`; Öffnen oder Schließen macht eingereihte Befehle nicht ungültig.
Phasen sind `live`, `menu`, `blocked` (nur Splash) und `ended`; nur Änderungen am
Weltlebenszyklus verschieben die Epoche.

Der Lookout nutzt ausschließlich den aktuellen Zustands-Snapshot, niemals
Kartengeografie oder Simulationsobjekte. Er ist nordorientiert und schiffszentriert:
Positionierte Beobachtungen sind Punkte, Meldungen mit reiner Peilung dagegen
Randmarkierungen ohne erfundene Entfernung. Seine Reichweite ist browserlokal und
sendet keinen Befehl. Seegang und Tag/Nacht beeinflussen nur die Darstellung; sie
sind keine Sichtbarkeitsmodelle, und Symbole belegen keine Plattformidentität. Der
Lookout zeichnet nur bei Snapshots, Tab-Aktivierung, lokaler Reichweitenänderung
oder Größenänderung und verwendet gerätepixelgerechte Backing-Dimensionen.

## Ergänzungen für den Solo-Modus (Protokoll v2, additiv)

Der Session-Body enthält `host`: normal `null`, für eine Solo-Sitzung
`{"generation": n}`. `GET /api/v2/host` liefert die losgelöste Host-Sicht (`phase`,
`world_mode`, `scenario`, `level`, `scenarios`, `levels`, `slots`)
nur an eine Sitzung mit `host`; andere erhalten 403. Slot-Zeilen enthalten `saved` und
`modified` ausschließlich aus Dateimetadaten, nie Spielstandinhalte.

Host-Steuerungen nutzen das normale `POST /api/v2/commands` mit der Pseudo-Rolle
`"host"` (nie ein Station-Lease; `STATIONS` und jede Projektion bleiben bei neun).
`station_generation` ist `host.generation` der Sitzung, `active_generation` muss 0
sein und `world_session` muss passen; Epoche und Ressourcenrevision werden nicht
geprüft, weil diese Aktionen keine Ressource referenzieren und Laden/Neues Spiel die
Epoche selbst verschieben. Es gibt keine Pause- oder Zeitfaktor-Aktion. Aktionen:
`host_save {slot}`, `host_load {slot}`, `host_new_game {scenario, world_mode,
level?, seed?}` und `host_instructor_environment {sea_state, event}`. Die Ausbilderaktion
aendert das spielstandkompatible autoritative Weltfeld (0–6) und baut die daraus
abgeleiteten Wetterendpunkte neu auf. Ihre optionale geschlossene Ereignisauswahl
setzt alle feindlichen U-Boote auf Schleich-, Marsch- oder Hoechstfahrt oder spielt
einen Torpedostart als Uebungsreiz ein, ohne Zielidentitaet oder Simulationswahrheit
offenzulegen. Jede Aktion hat ein geschlossenes Schema und eigene erlaubte Phasen (ein
Menü oder Overlay am Host macht die Phase `blocked` und weist alle ab). Host-Befehle
laufen in einem Frame vor den Stationsbefehlen; ersetzt einer die Welt, werden alle
späteren Befehle dieses Frames mit `phase_blocked` abgewiesen. Im Solo-Modus behält
ein Weltwechsel Sitzung, Cookie und CSRF, verwirft wartende und gehaltene Befehle,
least alle Stationen unter neuen Generationen neu und rotiert den Beitrittscode nicht.

Der Crew-Modus bleibt unverändert: `station: "host"` wird mit 403 abgewiesen, die
Spielsteuerung bleibt Host-Sache. Der Solo-Modus ist eine ausdrückliche lokale
Host-Entscheidung (CLI-Flag oder F9-Zeile), wird nie gespeichert, und ein Wechsel
widerruft alle Sitzungen.

## U-Boot-Rollen, Seitenwahl und Admin-Ergänzungen (Protokoll v2, additiv)

Neben den neun Fregatten-`STATIONS` kennt Protokoll v2 die sieben Rollen des
besetzten feindlichen U-Boots (`OPFOR_ROLES`): `uboot` (Führung), `uboot_sonar`,
`uboot_weapons`, `uboot_engine`, `uboot_esm`, `uboot_nav` und `uboot_radio`. Sie
werden wie Fregattenstationen verliehen, eine Sitzung hält aber immer nur Rollen
einer Seite. `uboot_sonar` teilt die Befehle des Sonarraums (Horchpeilung, Fokus);
Direktfeuer gilt auch für `uboot_weapons`.

Im Solo-Modus wechselt ein `POST /api/v2/stations/request` für eine Rolle der
anderen Seite die Seite der Sitzung: alle gehaltenen Leases werden freigegeben
(`role_revoked`) und alle Rollen der angefragten Seite vergeben. Der Dialog
„Neues Spiel“ des Browsers sendet diese Anfrage vor `host_new_game`, sodass die neue
Welt mit der gewählten Seite beginnt; `solo_rebase` behält die Seite über den
Weltwechsel. Fregattenstationen, die niemand hält, fahren die KI-Jäger.

`sonar_set_array_mode` nimmt `BOW`, `TOWED` oder `VDS`; `sonar_set_vds {deployed}`
fiert oder hievt das Tiefensonar, und `sonar_set_vds_depth {depth_m}` stellt
seine Tiefe (`sonar_set_tow_depth` bleibt die der Schleppantenne).

Die Admin-Aktionen des Webspiels (`POST /api/v2/web/admin`) enthalten `shutdown`
(`client_id` und `station` leer, `value` genau `true`): der Hauptthread beendet den
Spielprozess nach einer kurzen Frist, damit ein Webspiel nicht im Hintergrund
weiterläuft.

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
