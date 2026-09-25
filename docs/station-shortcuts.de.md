# U-Jagd 1.2.0 - Stations- und Tastenkürzel

Druckfassung: [`station-shortcuts.de.pdf`](station-shortcuts.de.pdf).
Maßgeblich ist die implementierte lokale Bedienung. Stationsnummern und
Tasten sind kontextabhängig; normale Bereitschafts-, Schadens- und
Berechtigungsprüfungen bleiben wirksam.

## Global

| Taste / Eingabe | Funktion |
|---|---|
| `Tab / Shift+Tab` | Naechste / vorherige Station |
| `1 / 2 / 3 / 4` | Bruecke / Sonar / Waffen / Schaden |
| `5 / 6 / 7 / 8` | OPZ / Funk / Maschine / Helikopter |
| `9` | Elektronische Kampffuehrung / ESM |
| `Nummer der aktiven Station` | Erneut druecken, um die Seite dieser Station weiterzuschalten |
| `Pfeiltasten` | Stationsbezogene Auswahl oder Einstellung |
| `+ / -` | Telegraph (an jeder Station verfuegbar) |
| `F1 / ?` | Hilfe (diese Anzeige) |
| `F2` | Autocrew der aktuellen Station umschalten |
| `F3` | Autocrew-Uebersicht oeffnen |
| `0` | Wetter- & Sonar-Analyse |
| `F8` | Taktischer Einheitenanalysator (Katalog, nur lesend) |
| `F4` | Simulationsprotokoll-Ansicht (live; benötigt simlog-Option; M: Karte aller Kontakte) |
| `F9` | Lokale Commander-LAN-Verwaltung oeffnen |
| `F10` | Optionen: Sprache, Vollbild, Audio, grosser Text, Tooltips, Bildrate |
| `F11` | Ereignislog und volle Telemetrie einblenden (Station bleibt bedienbar) |
| `N` | Nationen & Einheiten; im Sonar: Notchfilter |
| `S / L` | Speichern / Laden (Slots 1-5) |
| `Alt+Enter` | Vollbild (alle Stationen) |
| `Q / E oder Mausrad` | Kartenzoom nur auf Bruecke, Waffen und Helikopter |
| `Drag` | Karte verschieben (Bruecke, Waffen und Helikopter) |
| `K` | Kamera-Follow nur auf sichtbaren Karten (Drag schaltet es aus) |
| `P` | Plotmodus auf Brücken-/Waffen-/Helo-Karte und OPZ-Karte: Marken, Lineal, Peillinien, Kreise, Koppellinien (für alle Stationen, wird gespeichert) |
| `M R B C D · Enter · Rück` | Im Plotmodus: Werkzeug wählen, Punkt mit Enter oder Klick setzen (Pfeile bewegen den Cursor, Shift schneller), nächstes Objekt löschen (Shift: alle) |
| `Esc` | Eingabe abbrechen oder Beenden-Dialog oeffnen |
| `R / M` | Nach Missionsende: Neustart mit gleichem Seed / Hauptmenue |

## 1 Brücke

| Taste / Eingabe | Funktion |
|---|---|
| `<- / ->` | Ruder: Zielkurs aendern |
| `Auf / Ab` | Telegraph hoch / runter |
| `U` | Direkten Zielkurs eingeben (000-359) |
| `V` | Direkte Zielgeschwindigkeit eingeben (0-25 kn) |
| `+ / -` | Telegraph: Motorenbefehl (ASTERN-STOP-SLOW-HALF-FULL-FLANK) |
| `Karte` | Mausrad: Zoom, Maus-Drag: Pan |
| `Q / E` | Karte heraus-/hineinzoomen |
| `K` | Kamera-Follow an/aus |

## 2 Sonar

| Taste / Eingabe | Funktion |
|---|---|
| `Shift+A` | Aktiv-Ping abfeuern (Kuehlzeit, verraet Position!) |
| `Shift+B` | Empfangsarray zwischen HMS und TAS wechseln |
| `Y` | TAS ausbringen / einholen (nur bei 3-12 kn) |
| `Bild Auf / Ab` | Broadband / LOFAR / DEMON / TMA / Umwelt / ACTIVE |
| `2` | 2 erneut druecken, um die Sonarseite weiterzuschalten |
| `E` | Bathythermograph: lokales Schallprofil messen |
| `W` | Aktivpuls CW / LFM |
| `U / V` | TAS/VDS-Solltiefe um 10 m heben / senken |
| `R` | Hoerpeilung direkt: 000 bis 359.9 Grad rechtweisend |
| `<- / ->` | Peilung +/-0.5 Grad; Shift: 5, Ctrl: 0.1 |
| `Auf / Ab` | Kontakt fuer TMA und Klassifikation waehlen |
| `Enter` | Gemessener Kontaktpeilung folgen / manuell halten |
| `J \| , / .` | Empfangston an/aus \| Lautstaerke senken/erhoehen |
| `A / B / H` | Direkt Breitband / gefiltert / Heterodyn abhoeren |
| `D` | Breitband/gefiltertes Abhoeren umschalten |
| `I / O` | Gain senken / erhoehen (3 dB) |
| `Shift+I / Shift+O` | Sonar-Anzeigekontrast senken / erhoehen |
| `Ctrl+I / Ctrl+O` | Sonar-Schwarzpunkt senken / erhoehen |
| `Shift+C` | Phosphorpalette Gruen / Amber / Cyan wechseln |
| `Shift+H` | Angezeigte Historientiefe 25 / 50 / 100 Prozent wechseln |
| `F` | Frequenzband waehlen: breit / tief / mittel |
| `N` | Notchfilter gegen Eigenantrieb |
| `K` | Linie am Cursor markieren (LOFAR-Grundton, DEMON Welle/Blatt) |
| `Z / X` | LOFAR/DEMON-Frequenzcursor (Umschalt: 10 Hz) |
| `Ctrl+Z / Ctrl+X` | Bandpass untere / obere Kante am Cursor |
| `Q` | Integrationszeit 2 (FFT)/8/16/64 s |
| `Shift+Q` | LOFAR-Nonius: 20 Hz in nativen 0,5 Hz |
| `Shift+N` | Notch auf der Cursorfrequenz |
| `Shift+F` | DEMON-Trägerband 200-800 / 400-1400 / 1000-2000 Hz |
| `Ctrl+F` | Überlagerungsversatz 400/700/1000/1200 Hz |
| `X / Shift+X (BB)` | Breitband/Fusion: TAS-Seite des gewählten Kontakts wechseln / Umschalt: bestätigen |
| `Z / X (TMA)` | TMA-Seite: Hypothesenkurs -/+ 5 Grad (Umschalt 1 Grad) |
| `Ctrl+Z / Ctrl+X (TMA)` | TMA-Seite: Hypothesenfahrt -/+ 1 kn |
| `Q / Shift+Q (TMA)` | TMA-Seite: Hypothesenentfernung -/+ 1 sm (Strg 0,2 sm) |
| `K / Shift+K (TMA)` | TMA-Seite: Hypothese als Fix übernehmen / Umschalt: Solver-Vorschlag kopieren (Training) |
| `SPACE` | LOFAR Peak-Hold ein/aus |
| `T` | TMA fuer ausgewaehlten Kontakt ein/aus |
| `C` | Kontakt klassifizieren (U-Boot / Kampfschiff / Biologisch / Fahrzeug / Flugzeug / Torpedo) |
| `G` | Gewaehlt Kontakt unabhaengig von der Klassifikation an OPZ freigeben / zurueckziehen |
| `M` | Ausgewaehlten Kontakt als Ziel setzen |

## 3 Waffenzentrale

| Taste / Eingabe | Funktion |
|---|---|
| `M` | Ziel setzen (aus Sonarkontakten) |
| `Auf / Ab halten` | Torpedotiefe (10-300 m) |
| `<- / ->` | Sonarkontakt fuer Zielwahl waehlen |
| `T / Ctrl+Enter` | Torpedo abfeuern (ROE-Pruefung) |
| `H` | HSP-5 starten / zurueckrufen |
| `B` | Sonarbojen aussetzen (HSP-5 in Luft) |
| `D` | Leichttorpedo vom HSP-5 |
| `V` | Einen begrenzten geschleppten Akustik-Taeuschkoerper ausbringen |
| `Q / E` | Karte heraus-/hineinzoomen |
| `K` | Kamera-Follow an/aus |
| `F` | Flak-Feuerfreigabe umschalten (gesperrt = feuert nie auf Angreifer) |

## 4 Schadensabwehr

| Taste / Eingabe | Funktion |
|---|---|
| `<- / ->` | Kompartiment waehlen |
| `Auf / Ab` | Team 1-3 auswaehlen (ohne Zuweisung) |
| `Enter` | Gewaehltes Team dem gewaehlten Kompartiment zuweisen |
| `Backspace` | Gewaehltes Team zurueckziehen |
| `1-9` | Immer Station wechseln, keine Teamzuweisung |
| `Klick` | Raum oder Beschriftung waehlen; Enter weist das gewaehlte Team zu |

## 5 OPZ / CIC

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | CIC-Track waehlen |
| `C` | OPZ-eigene Radar-/HOJ-Meldungen oder manuelle Fusion klassifizieren |
| `F` | NATO-Zugehoerigkeit setzen |
| `Shift+F` | OPZ-Kontaktdomainfilter wechseln |
| `J` | Gemeinsame bedienersichtbare Track-ID eingeben |
| `Space / L / Shift+L` | Rohmeldungen markieren und manuelle Fusion bilden/aufloesen (Shift+L) |
| `Delete / H` | Lokal unterdruecken/wiederherstellen; H verwaltet Unterdrueckte |
| `M` | CIC-Track an Sonar/Waffen uebergeben |
| `Bild Auf / Ab` | Radarbereich 10/20/40/80/120 NM |
| `<- / ->` | ASM-Track waehlen |
| `E / Ctrl+Enter` | ESSM abfeuern (VLS-Cell) |
| `G` | Chaff abwerfen (8 NM-Kegel, Kuehlzeit) |
| `R` | Seeraumradar an/aus (EMCON) |
| `Shift+R` | Luftraumradar an/aus (EMCON) |
| `I` | CIWS-Feuerfreigabe umschalten (gesperrt = feuert nie auf anfliegende ASM) |
| `Backspace` | Alle markierten Meldungen abwaehlen |
| `Enter` | Angriff nach Feind-Einstufung eines realen Kontakts bestaetigen |
| `K` | Kamera-Follow an/aus |

## 6 Funk

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | HFDF-Signal auswaehlen |
| `Enter` | Peilung mit eigener Position protokollieren |

## 7 Maschinenraum

| Taste / Eingabe | Funktion |
|---|---|
| `+ / -` | Motorenbefehl (Telegraph) |
| `Auf / Ab` | Telegraph hoch / runter |
| `A` | Akustikmodus LEISE/NORMAL |
| `U` | Direkten Zielkurs eingeben (000-359) |
| `V` | Direkte Zielgeschwindigkeit eingeben (0-25 kn) |

## 8 Helikopterdeck

| Taste / Eingabe | Funktion |
|---|---|
| `H` | HSP-5 starten / zurueckrufen |
| `Pfeiltasten` | Wegpunktpeilung und -entfernung einstellen |
| `M` | Sonarkontakt als Ziel fuer Lufttorpedo setzen |
| `B` | Eine Sonarboje an aktueller Position aussetzen |
| `Shift+B` | Modus der nächsten Boje PASSIV / AKTIV |
| `T` | Sensorquelle: Tauchsonar / Sonarbojen |
| `F` | Gewählten Hubschrauberkontakt bestätigen / aufheben |
| `C` | Kontakt klassifizieren (U-Boot / Kampfschiff / Biologisch / Fahrzeug / Flugzeug / Torpedo) |
| `G / Shift+G` | Tauchsonarkontakt waehlen / an OPZ freigeben oder zurueckziehen |
| `Y` | Hubschrauber-Tauchsonar absenken / einholen |
| `U / V` | Solltiefe des Tauchsonars heben / senken |
| `A` | Aktiven Ping vom abgesenkten Tauchsonar senden |
| `D / Ctrl+Enter` | Leichttorpedo abwerfen |
| `Q / E` | Karte heraus-/hineinzoomen |
| `K` | Kamera-Follow an/aus |
| `Akustik: Bild Auf / Ab` | Akustikseite: Breitband / LOFAR / DEMON |
| `Akustik: <- / ->` | Hubschrauber-Horchpeilung -/+ 5 Grad |
| `Akustik: R` | Horchpeilung auf automatisch zurücksetzen |
| `Akustik: T` | Horchquelle: Tauchsonar / passive Bojen |
| `Akustik: J \| , / .` | Empfangston an/aus \| Lautstaerke senken/erhoehen |
| `Akustik: I / O` | Gain senken / erhoehen (3 dB) |
| `Akustik: N` | Notchfilter gegen Eigenantrieb |
| `Akustik: Shift+D` | Abhörmodus Breitband / gefiltert / Überlagerung |
| `Akustik: Shift+F` | Abhör-Frequenzband wechseln |

## 9 EloKa

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | Sichtbare passive ESM-Auffassung waehlen |
| `F / Shift+F / B` | Status-, Mindestbedrohungs- und Frequenzbandfilter wechseln |
| `C` | Radarart zuordnen und aktuelle Peilungen an OPZ freigeben; Zuordnung loeschen zieht die Freigabe zurueck |
| `J` | Gerichteten ECM-Kanal fuer die gewaehlte Auffassung aktivieren / freigeben |
| `Shift+J` | ECM-Verfahren Noise, RGPO, VGPO oder Falschziele wechseln |
| `A` | Automatische ECM-Priorisierung und Softkill-Kopplung umschalten |
| `M` | Lokalen ELOKA-Auffassungston umschalten |

## Tasten im Remote-Crew-Browser:

| Taste / Eingabe | Funktion |
|---|---|
| `1-9` | Eine eigene Station öffnen |
| `[ / ]` | Vorherige / nächste eigene Station |
| `?` | Leitfaden und Stationshilfe öffnen |
| `Pfeiltasten` | In fokussierter Registerleiste, Trackliste oder Karte bewegen |
| `Home / End` | Erster / letzter Eintrag der fokussierten Liste |
| `+ / -` | Fokussierte Karte zoomen; Pos1 passt die Ansicht ein |
| `Pfeiltasten (Karte)` | Fokussierte Karte verschieben |
| `Maus über Karte` | Details zu Track, eigenem Schiff, Asset, Wrack oder Kartenposition unter dem Mauszeiger |
| `0` | Wetter- & Sonar-Analyse öffnen oder schließen |
| `Plotwerkzeug + Klick` | Auf den gemeinsamen Plot zeichnen: Werkzeug über der Karte wählen, einmal (Marke, Peillinie) oder zweimal (Lineal, Kreis, Koppellinie) klicken |

## Eingabe und Dialoge

| Taste / Eingabe | Funktion |
|---|---|
| `Numerische Eingabe` | Ziffern, Punkt oder Komma; Backspace; Enter bestätigt; Esc bricht ab. |
| `Hilfe` | ←/→/Tab Kategorie; ↑/↓ zeilenweise; Bild↑/Bild↓ seitenweise; im Handbuch [ ] oder , . bzw. 0-9 Kapitel; F1/Esc schließen. |
| `Speichern/Laden` | 1 bis 5 wählt Slot; Enter bestätigt; Esc zurück. |
| `Beenden-Dialog` | ↑/↓ wählen, Enter bestätigen: zurück zum Spiel, speichern und beenden, zum Hauptmenü (ohne Speichern), ohne Speichern beenden; Esc/N schließt. |
| `Missionsende` | R Neustart mit gleichem Seed (Editor-Mission startet sich selbst neu); M zum Hauptmenü; Esc Beenden-Dialog. |
| `Hauptmenü` | ↑/↓ und Enter; W Weltmodus, R neuer Seed, Bild↑/Bild↓ Sektor (feste reale Welt), F Vollbild; Esc in der Szenarioauswahl zurück zum Hauptmenü. |
| `Commander-Vorschlag` | F6 annehmen; F7 ablehnen; F8 Vorschlagsart; Esc ausblenden. |
| `SimLog` | ↑/↓, Bild↑/Bild↓, Home/End oder Mausrad; M Karte, F Karte einpassen; F4/Esc schließen. |
| `Wetter/Analyse` | 0 oder Esc schließt das Analysefeld. |
| `Autocrew-Übersicht` | F3 oder Esc schließt. |

## Hinweise

- `Num-Enter` entspricht in Spiel- und Eingabedialogen grundsätzlich `Enter`.
- Wiederholte Keydown-Ereignisse werden ignoriert; nur ausdrücklich als
  gehalten beschriebene Steuerungen arbeiten kontinuierlich.
- Remote Crew verwendet Browser-Bedienelemente; der Abschnitt zum Browser
  nennt nur dessen Tastaturhilfen.
- In der nativen OPZ sind Ereignis-Feed und Telemetrie ausgeblendet; ihre
  Daten laufen weiter, `F11` blendet sie auch dort als Overlay ein.
- Tasten und Beschreibungen der Stationen stammen aus `src/core/help.py`
  (dieselbe Quelle wie die F1-Hilfe und das Handbuch).
- U-Jagd ist ein Spiel und kein Ausbildungs- oder Navigationsprodukt.

Erzeugt mit `python tools/build_station_shortcuts_pdf.py`.
