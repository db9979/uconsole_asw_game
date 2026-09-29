# U-Jagd 1.3.69 - Stations- und Tastenkürzel

Druckfassung: [`station-shortcuts.de.pdf`](station-shortcuts.de.pdf).
Maßgeblich ist die implementierte lokale Bedienung. Stationsnummern und
Tasten sind kontextabhängig; normale Bereitschafts-, Schadens- und
Berechtigungsprüfungen bleiben wirksam.

## Global

| Taste / Eingabe | Funktion |
|---|---|
| `Tab / Shift+Tab` | Nächste / vorherige Station |
| `1 / 2 / 3 / 4` | Brücke / Sonar / Waffen / Schaden |
| `5 / 6 / 7 / 8` | OPZ / Funk / Maschine / Helikopter |
| `9` | Elektronische Kampfführung / ESM |
| `Nummer der aktiven Station` | Erneut drücken, um die Seite dieser Station weiterzuschalten |
| `Pfeiltasten` | Stationsbezogene Auswahl oder Einstellung |
| `+ / -` | Telegraph (an jeder Station verfügbar) |
| `F1 / ?` | Hilfe (diese Anzeige) |
| `F2` | Autocrew der aktuellen Station umschalten |
| `F3` | Autocrew-Übersicht öffnen |
| `0` | Wetter- & Sonar-Analyse |
| `F8` | Taktischer Einheitenanalysator (Katalog, nur lesend) |
| `F4` | Simulationsprotokoll-Ansicht (live; benötigt simlog-Option; M: Karte aller Kontakte) |
| `F9` | Lokale Commander-LAN-Verwaltung öffnen |
| `F10` | Optionen: Sprache, Vollbild, Audio, großer Text, Tooltips, Bildrate |
| `F11` | Ereignislog und volle Telemetrie einblenden (Station bleibt bedienbar) |
| `N` | Nationen & Einheiten; im Sonar: Notchfilter |
| `S / L` | Speichern / Laden (Slots 1-5) |
| `Alt+Enter` | Vollbild (alle Stationen) |
| `Q / E oder Mausrad` | Kartenzoom nur auf Brücke, Waffen und Helikopter |
| `Drag` | Karte verschieben (Brücke, Waffen und Helikopter) |
| `K` | Kamera-Follow nur auf sichtbaren Karten (Drag schaltet es aus) |
| `P` | Plotmodus auf Brücken-/Waffen-/Helo-Karte und OPZ-Karte: Marken, Lineal, Peillinien, Kreise, Koppellinien (für alle Stationen, wird gespeichert) |
| `M R B C D · Enter · Rück` | Im Plotmodus: Werkzeug wählen, Punkt mit Enter oder Klick setzen (Pfeile bewegen den Cursor, Shift schneller), nächstes Objekt löschen (Shift: alle) |
| `Esc` | Eingabe abbrechen oder Beenden-Dialog öffnen |
| `R / M` | Nach Missionsende: Neustart mit gleichem Seed / Hauptmenü |
| `D` | Nach Missionsende: Nachbesprechung mit der Wahrheit neben dem Wissen der Crew |

## 1 Brücke

| Taste / Eingabe | Funktion |
|---|---|
| `<- / ->` | Ruder: Zielkurs ändern |
| `Auf / Ab` | Telegraph hoch / runter |
| `U` | Direkten Zielkurs eingeben (000-359) |
| `V` | Direkte Zielgeschwindigkeit eingeben (0-31 kn) |
| `+ / -` | Telegraph: Motorenbefehl (ASTERN-STOP-SLOW-HALF-FULL-FLANK) |
| `Karte` | Mausrad: Zoom, Maus-Drag: Pan |
| `Q / E` | Karte in Stufen zoomen, 500 bis 0,5 sm |
| `K` | Kamera-Follow an/aus |
| `, / .` | Ausguck-Seite: Radius kleiner / größer |
| `B` | Ausguck-Seite: Fernglas über der Karte ein/aus (, / . schwenken) |
| `↑/↓ · Q/E · Space` | Fernglas oben: ↑/↓ neigen 2° (Umschalt: 10°) statt Maschinentelegraf, Q/E Zoom (16°, 8°, 4° Feld), Leertaste Stabilisierung |
| `G` | Gefechtsstationen an/aus |
| `W` | Autopilot: Zickzack-Suche, wachsendes Quadrat, aus |
| `Rechtsklick` | Autopilot-Wegpunkt auf der Karte setzen |
| `Backspace` | Autopilot-Route löschen |

## 2 Sonar

| Taste / Eingabe | Funktion |
|---|---|
| `Shift+A` | Aktiv-Ping abfeuern (Kühlzeit, verrät Position!) |
| `Umschalt+B` | Empfangsarray wechseln: HMS, TAS, VDS |
| `Y` | TAS ausbringen / einholen (nur bei 3-12 kn) |
| `Shift+Y` | VDS fieren / hieven (3-15 kn, Seegang bis 5) |
| `Bild Auf / Ab` | Broadband / LOFAR / DEMON / TMA / Umwelt / ACTIVE |
| `2` | 2 erneut drücken, um die Sonarseite weiterzuschalten |
| `E` | Bathythermograph: lokales Schallprofil messen |
| `W` | Aktivpuls CW / LFM |
| `U / V` | Solltiefe des gewählten Arrays (TAS oder VDS) um 10 m heben / senken |
| `R` | Hörpeilung direkt: 000 bis 359.9 Grad rechtweisend |
| `<- / ->` | Peilung +/-0.5 Grad; Shift: 5, Ctrl: 0.1 |
| `Auf / Ab` | Kontakt für TMA und Klassifikation wählen |
| `Eingabe` | Gemessener Kontaktpeilung folgen / manuell halten |
| `J \| , / .` | Empfangston an/aus \| Lautstärke senken/erhöhen |
| `A / B / H` | Direkt Breitband / gefiltert / Heterodyn abhören |
| `D` | Breitband/gefiltertes Abhören umschalten |
| `I / O` | Gain senken / erhöhen (3 dB) |
| `Shift+I / Shift+O` | Sonar-Anzeigekontrast senken / erhöhen |
| `Ctrl+I / Ctrl+O` | Sonar-Schwarzpunkt senken / erhöhen |
| `Shift+C` | Phosphorpalette Grün / Amber / Cyan wechseln |
| `Shift+H` | Angezeigte Historientiefe 25 / 50 / 100 Prozent wechseln |
| `F` | Frequenzband wählen: breit / tief / mittel |
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
| `Shift+T (TMA)` | TMA-Methode: Hypothese/Residuen, Ekelund-Entfernung, Dot-Stack (Umschalt+K bei Ekelund: Entfernung übernehmen) |
| `SPACE` | LOFAR Peak-Hold ein/aus |
| `T` | TMA für ausgewählten Kontakt ein/aus |
| `C` | Kontakt klassifizieren (U-Boot / Kampfschiff / Biologisch / Fahrzeug / Flugzeug / Torpedo) |
| `G` | Gewählt Kontakt unabhängig von der Klassifikation an OPZ freigeben / zurückziehen |
| `M` | Ausgewählten Kontakt als Ziel setzen |

## 3 Waffenzentrale

| Taste / Eingabe | Funktion |
|---|---|
| `M` | Ziel setzen (aus Sonarkontakten) |
| `Auf / Ab halten` | Torpedotiefe (10-300 m) |
| `<- / ->` | Sonarkontakt für Zielwahl wählen |
| `T / Ctrl+Enter` | Torpedo abfeuern (ROE-Prüfung) |
| `W` | Torpedotyp (Rohre laden um; W wechselt Mk1/Mk2) |
| `X` | Suchmuster im Endanlauf: Schlange, Kreis, Helix |
| `, / .` | Sucheraktivierung -/+ (0,6 bis 3,0 sm, Schritte 0,2 sm) |
| `Y` | Salve: ein Torpedo oder zwei im Fächer +/-8° |
| `H` | HSP-5 starten / zurückrufen |
| `B` | Sonarbojen aussetzen (HSP-5 in Luft) |
| `D` | Leichttorpedo vom HSP-5 |
| `V` | Einen begrenzten geschleppten Akustik-Täuschkörper ausbringen |
| `A` | ASROC auf den zugewiesenen Kontakt (1-10 sm) |
| `Z` | Wasserbombenmuster über das Heck |
| `Q / E` | Karte in Stufen zoomen, 500 bis 0,5 sm |
| `K` | Kamera-Follow an/aus |
| `F` | Flak-Feuerfreigabe umschalten (gesperrt = feuert nie auf Angreifer) |

## 4 Schadensabwehr

| Taste / Eingabe | Funktion |
|---|---|
| `<- / ->` | Kompartiment wählen |
| `Auf / Ab` | Team 1-3 auswählen (ohne Zuweisung) |
| `Eingabe` | Gewähltes Team dem gewählten Kompartiment zuweisen |
| `Backspace` | Gewähltes Team zurückziehen |
| `C` | Hohe Rumpfseite gegen Krängung gegenfluten (erneut: Ventil schließen) |
| `W` | Wache jetzt ablösen (Seite Besatzung) |
| `G` | Gefechtsstationen an/aus |
| `1-9` | Immer Station wechseln, keine Teamzuweisung |
| `Klick` | Raum oder Beschriftung wählen; Enter weist das gewählte Team zu |

## 5 OPZ / CIC

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | CIC-Track wählen |
| `C` | OPZ-eigene Radar-/HOJ-Meldungen oder manuelle Fusion klassifizieren |
| `F` | NATO-Zugehörigkeit setzen |
| `Shift+F` | OPZ-Kontaktdomainfilter wechseln |
| `J` | Gemeinsame bedienersichtbare Track-ID eingeben |
| `Space / L / Shift+L` | Rohmeldungen markieren und manuelle Fusion bilden/auflösen (Shift+L) |
| `U / Shift+U` | Obersten Zuordnungsvorschlag fusionieren (Shift+U verwirft ihn) |
| `Delete / H` | Lokal unterdrücken/wiederherstellen; H verwaltet Unterdrückte |
| `M` | CIC-Track an Sonar/Waffen übergeben |
| `Bild Auf / Ab` | Radarbereich 10/20/40/80/120 NM |
| `<- / ->` | ASM-Track wählen |
| `E / Ctrl+Enter` | ESSM abfeuern (VLS-Cell) |
| `G` | Chaff abwerfen (8 NM-Kegel, Kühlzeit) |
| `R` | Seeraumradar an/aus (EMCON) |
| `Shift+R` | Luftraumradar an/aus (EMCON) |
| `I` | CIWS-Feuerfreigabe umschalten (gesperrt = feuert nie auf anfliegende ASM) |
| `Backspace` | Alle markierten Meldungen abwählen |
| `B` | Neuestes bloßes Radarecho als Track markieren (oder das Echo anklicken) |
| `Eingabe` | Angriff nach Feind-Einstufung eines realen Kontakts bestätigen |
| `K` | Kamera-Follow an/aus |
| `A` | OPZ Seite 3: Seefernaufklärer anfordern / heimschicken |
| `W` | Suchgebiet auf die gewählte Spur (sonst eigenes Schiff); Klick in die Karte für einen Punkt |
| `Z / Shift+Z` | Bojenmuster um das Suchgebiet wechseln / Shift bricht ab |
| `X` | Eine Boje am Flugzeug werfen |
| `Y` | Bojenmodus des Flugzeugs PASSIV / AKTIV |
| `T` | Seeraumradar des Flugzeugs ein/aus |
| `D` | Torpedo auf den zugewiesenen Kontakt (Flugzeug höchstens 2 sm vom Datum) |

## 6 Funk

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | HFDF-Signal auswählen |
| `Eingabe` | Peilung mit eigener Position protokollieren |
| `Auf / Ab` | HQ-Auftrag wählen (Seite Aufträge) |
| `A` | Gewählten Auftrag annehmen |
| `D` | Gewählten Auftrag ablehnen |
| `R` | Versorger bei der HQ anfordern |

## 7 Maschinenraum

| Taste / Eingabe | Funktion |
|---|---|
| `+ / -` | Motorenbefehl (Telegraph) |
| `Auf / Ab` | Telegraph hoch / runter |
| `A` | Akustikmodus LEISE/NORMAL |
| `G` | Antriebsanlage: AUTO, DIESEL (18 kn, -4 dB) oder TURBINE (+3 dB, +25 % Brennstoff) |
| `U` | Direkten Zielkurs eingeben (000-359) |
| `V` | Direkte Zielgeschwindigkeit eingeben (0-31 kn) |

## 8 Helikopterdeck

| Taste / Eingabe | Funktion |
|---|---|
| `H` | HSP-5 starten / zurückrufen |
| `Pfeiltasten` | Wegpunktpeilung und -entfernung einstellen |
| `M` | Sonarkontakt als Ziel für Lufttorpedo setzen |
| `B` | Eine Sonarboje an aktueller Position aussetzen |
| `Umschalt+B` | Modus der nächsten Boje PASSIV / AKTIV |
| `X` | Bojenmuster: einzeln, 2x2-Feld, Sperre quer zur Wegpunktpeilung, Kreis (X erneut: nächstes; einzeln löscht) |
| `Shift+M` | MAD-Anflug ein/aus: tief und langsam, Tauchsonar eingeholt |
| `T` | Sensorquelle: Tauchsonar / Sonarbojen |
| `F` | Gewählten Hubschrauberkontakt bestätigen / aufheben |
| `C` | Kontakt klassifizieren (U-Boot / Kampfschiff / Biologisch / Fahrzeug / Flugzeug / Torpedo) |
| `G / Shift+G` | Tauchsonarkontakt wählen / an OPZ freigeben oder zurückziehen |
| `Y` | Hubschrauber-Tauchsonar absenken / einholen |
| `U / V` | Solltiefe des Tauchsonars heben / senken |
| `A` | Aktiven Ping vom abgesenkten Tauchsonar senden |
| `D / Ctrl+Enter` | Leichttorpedo abwerfen |
| `Q / E` | Karte in Stufen zoomen, 500 bis 0,5 sm |
| `K` | Kamera-Follow an/aus |
| `Akustik: Bild Auf / Ab` | Akustikseite: Breitband / LOFAR / DEMON |
| `Akustik: ← / →` | Hubschrauber-Horchpeilung -/+ 5 Grad |
| `Akustik: R` | Horchpeilung auf automatisch zurücksetzen |
| `Akustik: T` | Horchquelle: Tauchsonar / passive Bojen |
| `Akustik: J \| , / .` | Empfangston an/aus \| Lautstärke senken/erhöhen |
| `Akustik: I / O` | Gain senken / erhöhen (3 dB) |
| `Akustik: N` | Notchfilter gegen Eigenantrieb |
| `Akustik: Shift+D` | Abhörmodus Breitband / gefiltert / Überlagerung |
| `Akustik: Shift+F` | Abhör-Frequenzband wechseln |

## 9 EloKa

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | Sichtbare passive ESM-Auffassung wählen |
| `F / Shift+F / B` | Status-, Mindestbedrohungs- und Frequenzbandfilter wechseln |
| `C` | Radarart zuordnen und aktuelle Peilungen an OPZ freigeben; Zuordnung löschen zieht die Freigabe zurück |
| `J` | Gerichteten ECM-Kanal für die gewählte Auffassung aktivieren / freigeben |
| `Shift+J` | ECM-Verfahren Noise, RGPO, VGPO oder Falschziele wechseln |
| `A` | Automatische ECM-Priorisierung und Softkill-Kopplung umschalten |
| `M` | Lokalen ELOKA-Auffassungston umschalten |

## Tasten im Remote-Crew-Browser:

| Taste / Eingabe | Funktion |
|---|---|
| `1-9` | Eine eigene Station öffnen (U-Boot-Crew: 1-7) |
| `[ / ]` | Vorherige / nächste eigene Station |
| `?` | Leitfaden und Stationshilfe öffnen |
| `Pfeiltasten` | In fokussierter Registerleiste, Trackliste oder Karte bewegen |
| `Home / End` | Erster / letzter Eintrag der fokussierten Liste |
| `+ / -` | Fokussierte Karte zoomen; Pos1 passt die Ansicht ein |
| `Pfeiltasten (Karte)` | Fokussierte Karte verschieben |
| `Maus über Karte` | Details zu Track, eigenem Schiff, Asset, Wrack oder Kartenposition unter dem Mauszeiger |
| `0` | Wetter- & Sonar-Analyse öffnen oder schließen |
| `Plotwerkzeug + Klick` | Auf den gemeinsamen Plot zeichnen: Werkzeug über der Karte wählen, einmal (Marke, Peillinie) oder zweimal (Lineal, Kreis, Koppellinie) klicken |
| `, / .` | Kontaktliste (,) oder Stationsbereich (.) ein- oder ausklappen |
| `L` | Einsatzprotokoll öffnen oder schließen |
| `Esc` | Leitfaden, Ausguck oder Kontaktbibliothek schließen und zur Station zurück |

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
