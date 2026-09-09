# Abschlussplan 0.1.6

## Umfang

0.1.6 ist der Commander-LAN-Meilenstein und schreibt weiterhin Save v8. Neue
Commander-Ansichten, Eloka, Kontakt-Schema v2, Save v9 und der erweiterte
Plattform-/Waffenbaukasten gehoeren zu 0.1.7 und stehen in
`docs/plan-0.1.7.md`.

Der aktuelle Abschluss umfasst ausschliesslich:

- Audio-Kontinuitaet auf der uConsole ohne Simulations-, RNG- oder Save-Aenderung,
- Korrekturen der Commander-Beobachtungs-, Vorschlags- und Transportgrenzen,
- den bestehenden responsiven Browservertrag mit bewusst erlaubtem
  Dokument-Scrollen,
- aktuelle EN/DE-Anleitungen, reproduzierbare Verifikation und Releasevorbereitung.

Private WaveOps-Unterlagen bleiben ausgeschlossen. Es werden weder Daten noch
Text, Bilder, Layouts oder abgeleitete Diagramme daraus uebernommen.

## Repository-Stand

Ausgang fuer diese Abschlussarbeit ist `main` bei `1aae70d`, drei lokale Commits
vor `origin/main`. Die vor Beginn vorhandene uncommittete Audio-OLA-Arbeit wird
fertiggestellt und nicht verworfen. Der jeweils aktuelle Arbeitsbaum, Teststand
und naechste Schritt stehen ausschliesslich in `docs/resume.md`.

## Abgeschlossene Commander-Basis

Die Commits `1a8e278`, `fb7a6ce` und `1aae70d` liefern beziehungsweise erweitern:

- einen standardmaessig ausgeschalteten, begrenzten LAN-HTTP-Dienst,
- kurzlebige Kopplung, lease-gebundene lokale Freigabe und Widerruf,
- eine vom Spielthread erzeugte, abgeloeste Beobachtungsprojektion,
- Browserannotation, Ziel- und Navigationsvorschlaege mit lokaler Annahme,
- Session-/Epoch-Wechsel, Statusredaktion und paketierte EN/DE-Webressourcen,
- mono Audio, Wall-Time-Auslieferung, Diagnosezaehler und einen begrenzten Hold.

Diese Liste beschreibt Implementierung, nicht automatisch aktuelle Abnahme.
Automatisierte, Browser-, LAN- und Hardwareabnahmen werden getrennt ausgewiesen.

## Arbeitspakete

### S1 Audio-Kontinuitaet

- Breitband-, Kavitation- und Hoerfilter verwenden begrenzten Streamingzustand
  mit 50 Prozent Ueberlappung; Erstaufruf und Freigabe sind definiert.
- Ein Receiversequenz-Retry liefert bitgleich denselben gefilterten Block und
  schreibt den Filterzustand nicht doppelt fort.
- Bei 1x kann die Audioausgabe einen bereits synthetisierten letzten Block
  begrenzt halten, wenn noch kein neuer Block verfuegbar ist.
- Oberhalb 1x ist Sonar stumm. Erzeugte Bloecke werden verworfen und nach der
  Rueckkehr zu 1x nicht nachgespielt.
- Der Pygame-Parameter heisst `AUDIO_MIXER_BUFFER_SAMPLES`; 512 bezeichnet
  Samples, nicht Millisekunden.
- `U_JAGD_AUDIO_DEBUG=1` protokolliert nach Wall-Time-Takt in einem sicheren,
  testspezifisch ersetzbaren Saveverzeichnis. Ohne Opt-in erfolgt kein I/O.

Abnahme: fokussierte Audio-/Receiver-/Sonartests, Backpressure, Wechsel 1x/5x/1x,
vollstaendige Suite und ein dokumentierter uConsole-Dauerlauf mit Motor, Sonar
und Alarmen. Headless-Erfolg ersetzt die Hardwareabnahme nicht.

### S2 Commander-Korrektheit

- Ein Bedrohungsalarm darf nur aus publizierter Beobachtung oder manueller
  Zugehoerigkeit entstehen, nie allein aus verborgenem `ASM`-/`TORP`-Typ.
- Ein neuer Vorschlag darf einen ausstehenden Vorschlag desselben Typs nicht
  ersetzen und erhaelt `proposal_pending`. Je ein Ziel- und Navigationsvorschlag
  duerfen gleichzeitig bestehen; identische Request-IDs bleiben idempotent.
- Navigation ist nur ein Vorschlag. Erst lokale Annahme prueft Lease, Session,
  Phase und Grenzwerte. Ein Kursanteil erfordert eine betriebsbereite Bruecke;
  reine Fahrtvorgaben bleiben moeglich und unterliegen den Antriebsgrenzen.
- Der Browser besitzt keinen direkten Steuer-, Waffen-, Sensor-, ROE-, Zeit-,
  Save- oder Editorbefehl.
- Listenerports sind `0` fuer isolierte Tests oder 1024 bis 65535 fuer den
  lokalen Betrieb. Bind bleibt auf explizite private/Loopback-IPv4 begrenzt.

Abnahme: Server-, Bridge-, Local-, Startup-, Navigation- und echte
Loopback-Integrationstests sowie getrennte Zwei-Geraete-LAN-Pruefung.

### S3 Browservertrag 0.1.6

0.1.6 behaelt Operations als lange responsive Seite. Vertikales
Dokument-Scrollen ist erlaubt; der tabbasierte Ein-Bildschirm-Vertrag folgt in
0.1.7.

- Keine horizontale Dokumentueberbreite bei 390 bis 3840 CSS-Pixeln.
- Karte, Kontaktliste, Details, Navigation, Schiff, Schaden, Ereignisse und
  Footer ueberlappen nicht und bleiben per Tastatur/Scrollen erreichbar.
- Dichte Listen scrollen innerhalb ihrer Panels; Karte bleibt enthalten und
  mindestens 200 x 200 CSS-Pixel gross, wo der Desktopvertrag das fordert.
- EN/DE, lange Daten, 120 Kontakte, neun Schadenszeilen, 80 Ereignisse und
  200-Prozent-Reflow sind Bestandteil der Chromium-Abnahme.

### S4 Dokumentation und Releaseabnahme

- `README.md`, `docs/commander-coop.md` und `docs/commander-protocol.md`
  beschreiben Ziel- und Navigationsvorschlaege sowie 1x-Audio korrekt.
- `docs/resume.md` ist der einzige volatile Handoff; historische Ergebnisse
  werden nicht als aktueller Gruenstatus ausgegeben.
- Commander-Screenshots werden nach finalem Layout neu erzeugt, ohne Codes oder
  Tokens.
- Keine Zugangsdaten, lokalen Saves, Caches, Buildbaeume oder unlizenzierte
  Medien gelangen in Commit oder Paket.

## Gesamtverifikation

Vor Abschluss aus dem Repository-Root:

```sh
pytest
python tools/gen_contacts.py --check
python tools/smoke_full.py
python -m build
```

Danach Wheel und sdist ausserhalb des Quellbaums installieren und Paketressourcen,
Version, Save v1-v8, echte Loopback-Kopplung und Browsermatrix pruefen. Physische
uConsole- und Zwei-PC-Ergebnisse separat in `docs/resume.md` dokumentieren.

0.1.6 gilt erst als abgeschlossen, wenn keine bekannte automatisierte Regression
offen ist. Ein fehlender Hardwaretest wird ausdruecklich als offen bezeichnet und
nicht als bestanden umgedeutet.

## Uebergang

Nach dem 0.1.6-Abschluss beginnt 0.1.7 bei Paket R0 in
`docs/plan-0.1.7.md`. Die Sonar-/Fidelity-Pakete B-F sind inzwischen
ausdruecklich freigegeben und folgen dort nach ihren technischen Voraussetzungen.
