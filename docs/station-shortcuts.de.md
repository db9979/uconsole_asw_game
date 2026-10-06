# U-Jagd 1.3.243 - Stations- und Tastenkürzel

Druckfassung: [`station-shortcuts.de.pdf`](station-shortcuts.de.pdf).
Maßgeblich ist die implementierte lokale Bedienung. Stationsnummern und
Tasten sind kontextabhängig; normale Bereitschafts-, Schadens- und
Berechtigungsprüfungen bleiben wirksam.

## Global

| Taste / Eingabe | Funktion |
|---|---|
| `Tab / Umschalt+Tab` | Nächste / vorherige Station |
| `1 / 2 / 3 / 4` | Brücke / Sonar / Waffen / Schaden |
| `5 / 6 / 7 / 8` | OPZ / Funk / Maschine / Helikopter |
| `9` | Elektronische Kampfführung / ESM |
| `Nummer der aktiven Station` | Erneut drücken, um die Seite dieser Station weiterzuschalten |
| `Bild Auf / Ab` | Vorige / nächste Seite der Station (jede Station mit mehreren Seiten) |
| `Strg+Eingabe` | Gewählte Waffe abfeuern: die einzige Feuertaste (Eingabe allein feuert nie; an der Waffenstation wählen D, A, Z, R und Umschalt+R nur Lufttorpedo, ASROC, Wasserbomben und Raketen) |
| `Pfeiltasten` | Stationsbezogene Auswahl oder Einstellung |
| `+ / -` | Telegraph (an jeder Station verfügbar) |
| `F1 / ?` | Hilfe (diese Anzeige) |
| `F2` | Autocrew der aktuellen Station umschalten |
| `Umschalt+F2` | Crew-Hilfe: Die KI besetzt jede freie Station beider Einheiten |
| `F3` | Autocrew-Übersicht öffnen |
| `0` | Wetter- & Sonar-Analyse |
| `F7` | Erster Offizier (optionales Sprachmodell) |
| `F8` | Taktischer Einheitenanalysator (Katalog, nur lesend) |
| `F4` | Simulationsprotokoll-Ansicht (live; benötigt simlog-Option; M: Karte aller Kontakte, F auf der Karte: Einheiten oder ganze Welt einpassen) |
| `F9` | Lokale Commander-LAN-Verwaltung öffnen |
| `F10` | Optionen: Sprache, Vollbild, Audio, großer Text, Tooltips, Bildrate |
| `F11` | Ereignislog und volle Telemetrie einblenden (Station bleibt bedienbar) |
| `N` | Nationen & Einheiten (Sonar und Akustikseite des Helikopters: Notchfilter) |
| `S / L (OPZ: L = Fusion)` | Speichern / Laden (Slots 1-5) |
| `Alt+Eingabe` | Vollbild (alle Stationen) |
| `Q / E oder Mausrad` | Kartenzoom auf Brücke, Waffen, Helikopter und OPZ-Karte (dort stellen Q/E den Radarbereich) |
| `Drag` | Karte verschieben (Brücke, Waffen, Helikopter und OPZ) |
| `K` | Karte folgt nur auf sichtbaren Karten (Ziehen schaltet es aus) |
| `Linksklick` | Angeklickte Taste, Lampe, Hinweis, Reiter, Scheibe oder Zeile |
| `Rechtsklick` | Abbrechen wie Esc in Menüs und Eingaben |
| `Menü-Symbol (Kopfzeile)` | Spielmenü per Maus: Hilfe, Optionen, Speichern/Laden, Wetter, Plot, Autocrew, Beenden und mehr; jedes Overlay schließt mit seinem Schließfeld (wie Esc) |
| `P` | Plotmodus auf Brücken-/Waffen-/Helo-Karte und OPZ-Karte: Marken, Lineal, Peillinien, Kreise, Koppellinien (für alle Stationen, wird gespeichert) |
| `M R B C D · Eingabe · Rück` | Im Plotmodus: Werkzeug wählen, Punkt mit Eingabe oder Klick setzen (Pfeile bewegen den Cursor, Umschalt schneller), nächstes Objekt löschen (Umschalt: alle) |
| `Esc` | Eingabe abbrechen oder Beenden-Dialog öffnen |
| `R / M` | Nach Missionsende: Neustart mit gleichem Seed / Hauptmenü |
| `D` | Nach Missionsende: Nachbesprechung mit der Wahrheit neben dem Wissen der Crew (Leertaste spielt ab, Tab 10×/60×, Pos1/Ende Anfang/Ende, B Bericht des Sprachmodells, wenn eingeschaltet) |

## 1 Brücke

| Taste / Eingabe | Funktion |
|---|---|
| `<- / ->` | Ruder: Zielkurs ändern |
| `Auf / Ab` | Telegraph hoch / runter |
| `C` | Direkten Zielkurs eingeben (000-359) |
| `V` | Direkte Zielgeschwindigkeit eingeben (0-31 kn) |
| `+ / -` | Telegraph: Motorenbefehl (ASTERN-STOP-SLOW-HALF-FULL-FLANK) |
| `Karte` | Mausrad: Zoom, Ziehen mit der Maus: verschieben |
| `Q / E` | Karte in Stufen zoomen, 500 bis 0,5 sm |
| `K` | Karte folgt dem eigenen Schiff an/aus |
| `, / .` | Ausguck-Seite: Radius kleiner / größer |
| `B` | Ausguck-Seite: Fernglas über der Karte ein/aus |
| `↑/↓ · ←/→ · Q/E · Leertaste` | Fernglas oben (wie das Sehrohr): ↑/↓ neigen 2° (Umschalt: 10°) statt Maschinentelegraf, ←/→ schwenken 5° (Umschalt: 20°) statt Ruder, Q/E Zoom (16°, 8°, 4° Feld), Leertaste Stabilisierung |
| `G` | Gefechtsstationen an/aus |
| `W` | Autopilot: Zickzack-Suche, wachsendes Quadrat, aus |
| `Rechtsklick` | Autopilot-Wegpunkt auf der Karte setzen |
| `Rücktaste` | Autopilot-Route löschen |
| `Strg+B` | Toten Winkel klären: zwei Minuten 60° nach Steuerbord, dann zurück (das Rumpfsonar ist 30° beiderseits des Hecks taub) |

## 2 Sonar

| Taste / Eingabe | Funktion |
|---|---|
| `Umschalt+A` | Aktiv-Ping abfeuern (Kühlzeit, verrät Position!) |
| `Umschalt+B` | Empfangsarray wechseln: HMS, TAS, VDS |
| `Y` | TAS ausbringen / einholen (nur bei 3-12 kn) |
| `Umschalt+Y` | VDS fieren / hieven (3-15 kn, Seegang bis 5) |
| `Bild Auf / Ab` | Broadband / LOFAR / DEMON / TMA / Umwelt / ACTIVE |
| `2` | 2 erneut drücken, um die Sonarseite weiterzuschalten |
| `E` | Bathythermograph: lokales Schallprofil messen |
| `W` | Aktivpuls CW / LFM |
| `U / V` | Solltiefe des gewählten Arrays (TAS oder VDS) um 10 m heben / senken |
| `R` | Hörpeilung direkt: 000 bis 359.9 Grad rechtweisend |
| `<- / ->` | Peilung +/-0.5 Grad; Umschalt: 5, Strg: 0.1 |
| `Auf / Ab` | Kontakt für TMA und Klassifikation wählen |
| `Eingabe` | Gemessener Kontaktpeilung folgen / manuell halten |
| `J \| , / .` | Empfangston an/aus \| Lautstärke senken/erhöhen |
| `A / B / H` | Direkt Breitband / gefiltert / Heterodyn abhören |
| `D` | Breitband/gefiltertes Abhören umschalten |
| `I / O` | Gain senken / erhöhen (3 dB) |
| `Umschalt+I / Umschalt+O` | Sonar-Anzeigekontrast senken / erhöhen |
| `Strg+I / Strg+O` | Sonar-Schwarzpunkt senken / erhöhen |
| `Umschalt+C` | Phosphorpalette Grün / Amber / Cyan wechseln |
| `Umschalt+H` | Angezeigte Historientiefe 25 / 50 / 100 Prozent wechseln |
| `F` | Frequenzband wählen: breit / tief / mittel |
| `N` | Notchfilter gegen Eigenantrieb |
| `K` | Linie am Cursor markieren (LOFAR-Grundton, DEMON Welle/Blatt) |
| `Z / X` | LOFAR/DEMON-Frequenzcursor (Umschalt: 10 Hz) |
| `Strg+Z / Strg+X` | Bandpass untere / obere Kante am Cursor |
| `Q` | Integrationszeit 2 (FFT)/8/16/64 s |
| `Umschalt+Q` | LOFAR-Nonius: 20 Hz in nativen 0,5 Hz |
| `Umschalt+N` | Notch auf der Cursorfrequenz |
| `Umschalt+F` | DEMON-Trägerband 200-800 / 400-1400 / 1000-2000 Hz |
| `Strg+F` | Überlagerungsversatz 400/700/1000/1200 Hz |
| `X / Umschalt+X (BB)` | Breitband/Fusion: TAS-Seite des gewählten Kontakts wechseln / Umschalt: bestätigen |
| `Z / X (TMA)` | TMA-Seite: Hypothesenkurs -/+ 5 Grad (Umschalt 1 Grad) |
| `Strg+Z / Strg+X (TMA)` | TMA-Seite: Hypothesenfahrt -/+ 1 kn |
| `Q / Umschalt+Q (TMA)` | TMA-Seite: Hypothesenentfernung -/+ 1 sm (Strg 0,2 sm) |
| `K / Umschalt+K (TMA)` | TMA-Seite: Hypothese als Fix übernehmen / Umschalt: Solver-Vorschlag kopieren (Training) |
| `Umschalt+T (TMA)` | TMA-Methode: Hypothese/Residuen, Ekelund-Entfernung, Dot-Stack (Umschalt+K bei Ekelund: Entfernung übernehmen) |
| `LEER` | LOFAR Peak-Hold ein/aus |
| `T` | TMA für ausgewählten Kontakt ein/aus |
| `C` | Kontakt klassifizieren (U-Boot / Kampfschiff / Biologisch / Fahrzeug / Flugzeug / Torpedo) |
| `G` | Gewählten Kontakt unabhängig von der Klassifikation an OPZ freigeben / zurückziehen |
| `M` | Ausgewählten Kontakt als Ziel setzen |

## 3 Waffenzentrale

| Taste / Eingabe | Funktion |
|---|---|
| `M` | Ziel setzen (aus Sonarkontakten) |
| `Auf / Ab halten` | Torpedotiefe (10-300 m) |
| `T` | Torpedo-Lauftiefe eingeben (10-300 m), wie auf dem U-Boot |
| `<- / ->` | Sonarkontakt für Zielwahl wählen |
| `Strg+Eingabe` | Gewählte Waffe abfeuern (Torpedo, solange D/A/Z/R nichts anderes gewählt haben; ROE-Prüfung) |
| `W` | Torpedotyp (Rohre laden um; W wechselt Mk1/Mk2) |
| `X` | Suchmuster im Endanlauf: Schlange, Kreis, Helix |
| `, / .` | Sucheraktivierung -/+ (0,6 bis 3,0 sm, Schritte 0,2 sm) |
| `Y` | Salve: ein Torpedo oder zwei im Fächer +/-8° |
| `H` | HSP-5 starten (5 min Vorbereitung, tankt an Deck) / abbrechen / zurückrufen |
| `B` | Sonarbojen aussetzen (HSP-5 in Luft) |
| `D` | Leichttorpedo vom HSP-5 wählen (nochmals: Schiffstorpedo) |
| `V` | Einen begrenzten geschleppten Akustik-Täuschkörper ausbringen |
| `A` | ASROC auf den zugewiesenen Kontakt wählen (1-10 sm) |
| `Z` | Wasserbombenmuster über das Heck wählen |
| `R` | U-Jagd-Raketensalve auf das Ziel wählen (frische Entfernung, 0,4-3 sm) |
| `Umschalt+R` | Raketen-Abwehrsalve in Richtung der Torpedowarnung wählen |
| `Q / E` | Karte in Stufen zoomen, 500 bis 0,5 sm |
| `K` | Karte folgt dem eigenen Schiff an/aus |
| `F` | Flak-Feuerfreigabe umschalten (gesperrt = feuert nie auf Angreifer) |

## 4 Schadensabwehr

| Taste / Eingabe | Funktion |
|---|---|
| `<- / ->` | Kompartiment wählen |
| `Auf / Ab` | Team 1-3 auswählen (ohne Zuweisung) |
| `Eingabe` | Gewähltes Team dem gewählten Kompartiment zuweisen |
| `Rücktaste` | Gewähltes Team zurückziehen |
| `C` | Hohe Rumpfseite gegen Krängung gegenfluten (erneut: Ventil schließen) |
| `W` | Wache jetzt ablösen (Seite Besatzung) |
| `G` | Gefechtsstationen an/aus (Seite Besatzung) |
| `M` | Sanitätstrupp zur nächsten Station mit Verwundeten (Seite Besatzung) |
| `U` | Leute aus den Freiwachen zur am schwersten getroffenen Station (Seite Besatzung) |
| `1-9` | Immer Station wechseln, keine Teamzuweisung |
| `Klick` | Raum oder Beschriftung wählen; Eingabe weist das gewählte Team zu |

## 5 OPZ / CIC

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | CIC-Track wählen |
| `C` | OPZ-eigene Radar-/HOJ-Meldungen oder manuelle Fusion klassifizieren |
| `F` | NATO-Zugehörigkeit setzen |
| `Umschalt+F` | OPZ-Kontaktdomainfilter wechseln |
| `J` | Gemeinsame bedienersichtbare Track-ID eingeben |
| `Leertaste / L / Umschalt+L` | Rohmeldungen markieren und Fusion bilden/auflösen (Umschalt+L); Treffer fusionieren automatisch |
| `U / Umschalt+U` | Obersten Zuordnungsvorschlag fusionieren (Umschalt+U verwirft ihn) |
| `Entf / H` | Lokal unterdrücken/wiederherstellen; H verwaltet Unterdrückte |
| `M` | CIC-Track an Sonar/Waffen übergeben |
| `Q / E` | Radarbereich 10/20/40/80/120 sm (Q weiter, E näher) |
| `<- / ->` | ASM-Track wählen |
| `Strg+Eingabe` | Seiten 1-2: ESSM starten (VLS-Zelle); Seite 3: die gewählte Waffe feuern |
| `G` | Chaff abwerfen (8 sm-Kegel, Kühlzeit) |
| `R` | Seeraumradar an/aus (EMCON) |
| `Umschalt+R` | Luftraumradar an/aus (EMCON) |
| `I` | CIWS-Feuerfreigabe umschalten (gesperrt = feuert nie auf anfliegende ASM) |
| `Rücktaste` | Seiten 1-2: alle markierten Meldungen verwerfen |
| `B` | Seiten 1-2: den neuesten rohen Radarblip als Track markieren (oder den Blip anklicken) |
| `Eingabe` | Angriff nach Feind-Einstufung eines realen Kontakts bestätigen |
| `K` | Karte folgt dem eigenen Schiff an/aus |
| `H` | OPZ Seite 3: Seefernaufklärer anfordern / heimschicken (Tasten wie beim Helikopter) |
| `W` | Seite 3: Suchgebiet auf die gewählte Spur (sonst eigenes Schiff); Klick in die Karte für einen Punkt |
| `X / Umschalt+X` | Seite 3: Bojenmuster um das Suchgebiet wechseln / Umschalt bricht ab |
| `B` | Seite 3: eine Boje am Flugzeug werfen |
| `Umschalt+B` | Seite 3: Bojenmodus des Flugzeugs PASSIV / AKTIV |
| `Strg+R` | Seite 3: Seeraumradar des Flugzeugs ein/aus |
| `Umschalt+M` | Seite 3: MAD-Anflüge des Flugzeugs über seinen Wegpunkt ein/aus (tief und langsamer, der Radarhorizont schrumpft) |
| `D` | Seite 3: Torpedo des Flugzeugs auf den zugewiesenen Kontakt wählen, Strg+Eingabe wirft (Flugzeug höchstens 2 sm vom Datum; nochmals: ESSM) |
| `Y / F / H` | OPZ-Seite 4 (Gruppenjagd): Begleiter selbständig / nächster Formationsplatz / halten |
| `X / W` | OPZ-Seite 4: Begleiter sucht hier / verfolgt den gewählten Track (oder Klick in die Karte) |
| `Umschalt+A` | OPZ-Seite 4: Aktivsonar des Begleiters an/aus |
| `Umschalt+W` | OPZ-Seite 4: Waffen des Begleiters frei / gesperrt |
| `Strg+Eingabe` | OPZ-Seite 4: ein ASROC des Begleiters auf den gewählten Track (Standort unter 2 min) |
| `↑/↓ ←/→` | Seite 5 Anzeige: Karteneinstellung wählen, ändern |
| `Rücktaste` | Seite 5: gewählte Karteneinstellung auf Standard |
| `Umschalt+Rücktaste` | Seite 5: alle Karteneinstellungen auf Standard |

## 6 Funk

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | Seiten 1-2: HFDF-Signal wählen |
| `Eingabe` | Peilung mit eigener Position protokollieren (auf der Seite Aufträge nimmt Eingabe den Auftrag an) |
| `Auf / Ab` | HQ-Auftrag wählen (Seite Aufträge) |
| `A / Eingabe` | Seite Aufträge: gewählten Auftrag annehmen |
| `D` | Seite Aufträge: gewählten Auftrag ablehnen |
| `R` | Seite Aufträge: Versorger beim HQ anfordern |
| `K` | Seite Aufträge: Kontaktmeldung an HQ (der frischeste Fix; KW-Ruf, anpeilbar) |
| `H` | Seite Aufträge: Unterstützung beim HQ anfordern (der Seefernaufklärer; KW-Ruf, anpeilbar) |

## 7 Maschinenraum

| Taste / Eingabe | Funktion |
|---|---|
| `+ / -` | Motorenbefehl (Telegraph) |
| `Auf / Ab` | Telegraph hoch / runter |
| `A` | Akustikmodus LEISE/NORMAL |
| `G` | Antriebsanlage: AUTO, DIESEL (18 kn, -4 dB) oder TURBINE (+3 dB, +25 % Brennstoff) |
| `C` | Direkten Zielkurs eingeben (000-359) |
| `V` | Direkte Zielgeschwindigkeit eingeben (0-31 kn) |

## 8 Helikopterdeck

| Taste / Eingabe | Funktion |
|---|---|
| `H` | HSP-5 starten (5 min Vorbereitung, tankt an Deck) / abbrechen / zurückrufen |
| `Pfeiltasten` | Wegpunktpeilung und -entfernung einstellen |
| `W` | Wegpunkt auf die Position des gewählten Kontakts (wie W beim Seefernaufklärer) |
| `M` | Sonarkontakt als Ziel für Lufttorpedo setzen |
| `B` | Eine Sonarboje an aktueller Position aussetzen |
| `Umschalt+B` | Modus der nächsten Boje PASSIV / AKTIV |
| `X` | Bojenmuster: einzeln, 2x2-Feld, Sperre quer zur Wegpunktpeilung, Kreis (X erneut: nächstes; einzeln löscht) |
| `Umschalt+M` | MAD-Anflug ein/aus: tief und langsam, Tauchsonar eingeholt |
| `Strg+R` | Suchradar ein/aus (aus: das ESM eines U-Boots hört es nicht, es findet aber auch keine Masten) |
| `Z` | Rettungswinde über einer Insel (bis 0,1 sm) an/aus |
| `T` | Sensorquelle: Tauchsonar / Sonarbojen |
| `F` | Gewählten Hubschrauberkontakt bestätigen / aufheben |
| `C` | Kontakt klassifizieren (U-Boot / Kampfschiff / Biologisch / Fahrzeug / Flugzeug / Torpedo) |
| `G` | Gewählten Kontakt an die OPZ freigeben oder zurückziehen (wie am Sonar) |
| `Umschalt+↑ / ↓` | Nächsten Tauchsonarkontakt wählen (Pfeile allein steuern den Wegpunkt) |
| `Y` | Hubschrauber-Tauchsonar absenken / einholen |
| `U / V` | Solltiefe des Tauchsonars heben / senken |
| `Umschalt+A` | Aktiven Ping vom abgesenkten Tauchsonar senden |
| `Strg+Eingabe` | Leichttorpedo abwerfen |
| `Q / E` | Karte in Stufen zoomen, 500 bis 0,5 sm |
| `K` | Karte folgt dem eigenen Schiff an/aus |
| `Akustik: Bild Auf / Ab` | Akustikseite: Breitband / LOFAR / DEMON |
| `Akustik: ← / →` | Hubschrauber-Horchpeilung -/+ 5 Grad |
| `Akustik: R` | Horchpeilung auf automatisch zurücksetzen |
| `Akustik: T` | Horchquelle: Tauchsonar / passive Bojen |
| `Akustik: J \| , / .` | Empfangston an/aus \| Lautstärke senken/erhöhen |
| `Akustik: I / O` | Gain senken / erhöhen (3 dB) |
| `Akustik: N` | Notchfilter gegen Eigenantrieb |
| `Akustik: Umschalt+D` | Abhörmodus Breitband / gefiltert / Überlagerung |
| `Akustik: Umschalt+F` | Abhör-Frequenzband wechseln |

## 9 EloKa

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | Nächsten gelisteten Sender wählen (eine Gruppe zählt einmal) |
| `← / →` | Durch die Auffassungen der gewählten Sendergruppe blättern |
| `F / Umschalt+F / Strg+F` | Status (operativ, offen = noch nicht eingestuft, live, Speicher, alle) / Mindestbedrohung / Frequenzband wechseln |
| `Z` | Gleichartige Auffassungen einer Richtung zu einem Eintrag bündeln an/aus |
| `C` | Radarart zuordnen und aktuelle Peilungen an OPZ freigeben; Zuordnung löschen zieht die Freigabe zurück |
| `E` | Gerichteten ECM-Kanal für die gewählte Auffassung aktivieren / freigeben |
| `Umschalt+E` | ECM-Verfahren Noise, RGPO, VGPO oder Falschziele wechseln |
| `A` | Automatische ECM-Priorisierung und Softkill-Kopplung umschalten |
| `J` | Lokalen ELOKA-Auffassungston umschalten |

## Steuerung (alle U-Boot-Stationen)

| Taste / Eingabe | Funktion |
|---|---|
| `Tab / Umschalt+Tab` | Nächste / vorherige Station |
| `1 … 7` | Stationen: 1 Führung, 2 Sonar, 3 Waffen, 4 Maschine, 5 Mast & ESM, 6 Navigation, 7 Funkraum |
| `Nummer der aktiven Station` | Erneut drücken, um die Seite dieser Station weiterzuschalten |
| `Bild Auf / Ab` | Vorige / nächste Seite der Station (jede Station mit mehreren Seiten) |
| `Strg+Eingabe` | Torpedo abfeuern (Waffen; Sehrohrseite: auf die Lösung des Angriffsrechners; F: nach Peilung und Entfernung). Eingabe allein feuert nie |
| `Umschalt+A` | Aktiver Ping mit dem eigenen Sonar (Führung und Sonarraum) |
| `F1 / ?` | Hilfe (diese Anzeige) |
| `Umschalt+F2` | Crew-Hilfe: Die KI besetzt jede freie Station beider Einheiten |
| `0` | Wetterseite des U-Boots (0 oder Esc schließt) |
| `F7` | Erster Offizier (optionales Sprachmodell) |
| `F9` | Lokale Commander-LAN-Verwaltung öffnen |
| `F10` | Optionen: Sprache, Vollbild, Audio, großer Text, Tooltips, Bildrate |
| `F11` | Ereignislog und volle Telemetrie einblenden (Station bleibt bedienbar) |
| `S / L` | Speichern / Laden (Slots 1-5; nicht im Sonarraum) |
| `Alt+Eingabe` | Vollbild (alle Stationen) |
| `Esc` | Eingabe abbrechen oder Beenden-Dialog öffnen |
| `R / M` | Nach Missionsende: Neustart mit gleichem Seed / Hauptmenü |
| `D` | Nach Missionsende: Nachbesprechung mit der Wahrheit neben dem Wissen der Crew (Leertaste spielt ab, Tab 10×/60×, Pos1/Ende Anfang/Ende, B Bericht des Sprachmodells, wenn eingeschaltet) |

## U-Boot spielen (uConsole)

| Taste / Eingabe | Funktion |
|---|---|
| `1 … 7 / Tab` | Stationen: 1 Führung, 2 Sonar, 3 Waffen, 4 Maschine, 5 Mast & ESM, 6 Navigation, 7 Funkraum; Tab weiter (oder Reiter anklicken) |
| `C / V / D` | Kurs / Fahrt / Tiefe befehlen (Führung; Kurs und Tiefe auch Navigation, Fahrt auch Maschine) |
| `U / J / H` | Tiefenstufen: Sehrohr- / Schnorcheltiefe (Umschalt), unter / über dem gemessenen Layer (Umschalt), tief (Führung, Navigation) |
| `Bild auf/ab` | Führungsseiten: Navigation / Waffen & Kontakte / Sehrohr / Bedrohung (oder erneut 1); Seiten Navigation: Karte & Echolot / Navigation / Bedrohung (oder erneut 6); Seiten Mast & ESM: ESM / Sehrohr (oder erneut 5) |
| `Q / E` | Karte in Stufen zoomen, 500 bis 0,5 sm (Sehrohrseite: das Mausrad zoomt die Karte) |
| `K` | Karte folgt dem U-Boot an/aus |
| `Mausrad / Ziehen` | Karte zoomen / verschieben (Maus auf der Karte) |
| `Linksklick` | Kurs zu einem Punkt der Lotsenkarte befehlen (Navigation, Karte & Echolot) |
| `Pfeiltasten` | Eigenen Sonarkontakt wählen |
| `Strg+Eingabe` | Torpedo auf den gewählten Kontakt schießen (Waffen) |
| `F` | Auf eine eingegebene Peilung schießen: Peilung, Eingabe, Entfernung zum Datum (leer: keine), dann schießt Strg+Eingabe (Waffen) |
| `V` | Täuschkörper ausstoßen (Waffen) |
| `M` | Nächstes leeres Torpedorohr laden (Waffen) |
| `Umschalt+M` | Nächstes geladenes Rohr fluten (20 s) und Mündungsklappe öffnen; laut, die Fregatte kann es hören; nur ein geflutetes Rohr schießt (Waffen) |
| `Strg+M` | Nächstes geladenes Rohr langsam fluten (60 s); die Fregatte hört es nur ganz nah (Waffen) |
| `Umschalt+B` | Notanblasen, einmal (Führung, Maschine) |
| `T` | Torpedo-Lauftiefe 5-300 m (Waffen) |
| `Y` | Ein Torpedo oder Zweierfächer (Waffen) |
| `X` | Suchmuster des Suchers: gerade, Schlange, Kreis, Helix (Waffen) |
| `, / .` | Sucheraktivierung -/+ (0,6 bis 3,0 sm vor dem Datum, Schritte 0,2 sm; Waffen) |
| `W` | Neuesten Drahttorpedo lenken: Peilung, dann Entfernung (Waffen) |
| `Umschalt+W` | Draht des neuesten Torpedos kappen (Waffen) |
| `A` | Schleichfahrt ein/aus, höchstens 5 kn (Führung, Maschine) |
| `Umschalt+A` | Aktiver Ping mit dem eigenen Sonar (Führung und Sonarraum) |
| `Umschalt+G` | Auf Grund legen / abheben (Führung, Navigation) |
| `Umschalt+H` | Auftauchen: an die Oberfläche, Brückenwache, Diesel an der Luft (Führung, Navigation) |
| `H` | Von der Oberfläche: Alarmtauchen, Flutventile auf, äußerste Kraft (Führung, Navigation) |
| `N` | Schnorchel aus-/einfahren, Diesel laden auf Schnorcheltiefe (Maschine) |
| `P` | Mast aus-/einfahren auf Sehrohrtiefe: ESM hört Radare, das Sehrohr sieht, die Funkantenne ist klar (Führung, Mast & ESM, Funkraum) |
| `Pfeiltasten` | Seite Mast & ESM: Emitter wählen |
| `C / ← / →` | Seite Mast & ESM: Emitter aus der Bibliothek einstufen (C oder →: weiter, Umschalt+C oder ←: zurück; Annotation, keine Wahrheit) |
| `Eingabe` | Seite Mast & ESM: Kreuzpeilung (oder Peillinie) in den Plot des U-Boots |
| `← / →` | Sehrohrseite: Rohr 2° schwenken (Umschalt: 10°) (Führung, Mast & ESM) |
| `↑/↓ · Q/E · Leertaste` | Sehrohrseite (wie das Fernglas): ↑/↓ Kopf 2° neigen (Umschalt: 10°), Q/E kleine/große Vergrößerung (32°, 8° Feld), Leertaste Stabilisierung |
| `Eingabe` | Sehrohrseite: Stadimeter-Entfernung der Sichtung unter dem Fadenkreuz (Führung, Mast & ESM) |
| `Strg+Eingabe` | Sehrohrseite: Schuss nach der Lösung des Angriffsrechners für die Sichtung unter dem Fadenkreuz (Führung) |
| `+ / -` | Fahrtstufe schneller / langsamer (Führung, Maschine) |
| `Sonartasten` | Wie am Fregattensonar, ohne Schleppantenne, OPZ-Freigabe, Plot und Telegraph |
| `R` | Maschine, Seite Vorräte: Laderate beim Schnorcheln wechseln (voll, halb, nur lüften) |
| `Umschalt+O` | Maschine, Seite Vorräte: neuen CO2-Absorbersatz einsetzen |
| `O` | Maschine, Seite Vorräte: O2-Kerze zünden |
| `Pfeiltasten` | Maschine, Seite Zellen: Regelzelle fluten (ab) oder lenzen (auf) |
| `← / →` | Maschine, Seite Zellen: Trimmwasser nach vorn (rechts) oder achtern (links) |
| `Z` | Maschine: Trimmautomatik an/aus |
| `Pfeiltasten` | Maschine, Seite Leckwehr: Abteilung wählen (auf/ab) und Aufgabe (links/rechts) |
| `Eingabe` | Maschine, Seite Leckwehr: Trupp 1 (Umschalt: Trupp 2) mit der Aufgabe schicken |
| `I` | Maschine, Seite Leckwehr: Schotten der Abteilung schließen oder öffnen |
| `I` | Führung, Navigation: dem frischesten Ping- oder Torpedoalarm ausweichen (Kurs, Fahrt, Schicht, Schleichfahrt oder Täuschkörper) |
| `Eingabe` | Funkraum: Lagemeldung an die Führung senden (Mast auf Sehrohrtiefe ausgefahren; die Fregatte kann die KW-Sendung peilen) |
| `B` | Funkraum: Bojenantenne ausbringen oder einholen (Rundspruch bis 60 m bei höchstens 6 kn; reißt über 10 kn ab) |
| `W` | Maschine, Seite Leckwehr: Wache jetzt ablösen |
| `M` | Maschine, Seite Leckwehr: Sanitätstrupp zur nächsten Station mit Verwundeten |
| `U` | Maschine, Seite Leckwehr: Leute aus den Freiwachen zur am schwersten getroffenen Station |
| `G` | Gefechtsstationen an/aus (alle Wachen im Dienst, aufmerksam, aber ermüdend) |
| `Strg+B` | Toten Winkel klären: zwei Minuten 60° nach Steuerbord, dann zurück (das Rumpfsonar ist achtern taub) |
| `Rechtsklick` | Routen-Wegpunkt auf der Karte setzen (Navigation) |
| `W` | Route: Zickzack-Suche, wachsendes Quadrat, aus (Navigation) |
| `Rücktaste` | Route löschen (Navigation) |
| `0` | Wetterseite des U-Boots (0 oder Esc schließt) |
| `S / L / F9` | Speichern / Laden / Remote Crew (die Fregatten-Crew) |
| `Menü-Symbol (Kopfzeile)` | Spielmenü per Maus: Hilfe, Optionen, Speichern/Laden, Wetter, Plot, Autocrew, Beenden und mehr; jedes Overlay schließt mit seinem Schließfeld (wie Esc) |

## Menütasten (Hauptmenü und seine Seiten)

| Taste / Eingabe | Funktion |
|---|---|
| `Auf / Ab` | Zeile wählen |
| `Eingabe` | Gewählte Zeile öffnen oder starten |
| `Esc / Q` | Zurück (Hauptmenü: Beenden-Dialog) |
| `Bild Auf / Ab` | Listen: eine Seite auf / ab |
| `Pos1 / Ende` | Listen: erste / letzte Zeile |
| `W` | Hauptmenü und Szenarioseiten: Weltmodus (erzeugt / feste Karte / fester realer Sektor) |
| `R` | Hauptmenü und Szenarioseiten: neuer Seed |
| `[ / ]` | Hauptmenü und Szenarioseiten, fester realer Sektor: voriger / nächster Sektor |
| `F` | Hauptmenü und Szenarioseiten: Vollbild / Fenster |
| `← / → / Tab` | Einsatzbuch: Fregatte / U-Boot |
| `A` | Einsatzbuch: Auswertung des Sprachmodells (wenn eingeschaltet) |
| `B` | Einsatzbuch: der neueste Einsatzbericht |
| `L` | Einsatzbuch: Gegner lernt deine Gewohnheiten an/aus |
| `Eingabe / Esc` | Einsatzbuch: zurück ins Hauptmenü (Esc schließt erst eine offene Auswertung oder einen Bericht) |
| `F1 / F9` | Hilfe / Remote-Crew-Verwaltung |

## Tasten im Remote-Crew-Browser

| Taste / Eingabe | Funktion |
|---|---|
| `1-9` | Eine eigene Station öffnen (U-Boot-Crew: 1-7); dieselbe Nummer nochmals blättert die Seite um |
| `?` | Leitfaden und Stationshilfe öffnen |
| `Pfeiltasten` | In fokussierter Registerleiste, Trackliste oder Karte bewegen |
| `Pos1 / Ende` | Erster / letzter Eintrag der fokussierten Liste |
| `Q / E` | Karte oder Ausguck zoomen (wie auf der uConsole); Pos1 passt die Ansicht ein |
| `K` | Karte folgt dem eigenen Schiff an oder aus |
| `+ / -` | Maschinentelegraph eine Stufe höher / tiefer (Brücke, Maschine, U-Boot-Führung und -Maschine) |
| `C / V / D · T` | Kurs, Fahrt, Tiefe, Torpedo-Lauftiefe: der Cursor springt ins Feld, Eingabe sendet (Brücke, Maschine, U-Boot) |
| `Umschalt+A · J` | Aktiver Ping · Live-Sonarton an oder aus (Sonar, U-Boot-Führung, Tauchsonar des Helikopters) |
| `W · Umschalt+T` | Sonar: Aktivpuls CW / LFM · TMA-Methode (Hypothese, Ekelund, Dot-Stack) |
| `Strg+Eingabe` | Schuss scharf machen (Waffen, OPZ, Helikopter, U-Boot-Waffen); der Feuerdialog fragt noch einmal |
| `R / Umschalt+R` | OPZ: Seeziel- / Luftraumradar an oder aus; Q / E ändern den Radar-Anzeigebereich |
| `H · B · Strg+R · Umschalt+M` | Helikopter: starten oder zurückrufen, Boje werfen, Flugzeugradar, MAD |
| `A · V · Strg+B` | Schleichfahrt (Maschine) · Täuschkörper (U-Boot-Waffen) · toten Winkel klären (Brücke, U-Boot-Führung) |
| `Stationsbuchstaben` | Jede weitere Stationstaste ist die der uConsole (Funk K / H / R / A / D, Leckwehr C / G / W / M / U, ELOKA E / Umschalt+E / A / C, Waffen W / X / Y / D / A / Z / R, ...); jede steht als blaue Tastenkappe auf ihrem Bedienelement |
| `Pfeiltasten (Karte)` | Fokussierte Karte verschieben |
| `Maus über Karte` | Details zu Track, eigenem Schiff, Asset, Wrack oder Kartenposition unter dem Mauszeiger |
| `0` | Wetter- & Sonar-Analyse öffnen oder schließen |
| `Bild auf/ab` | Seiten durchblättern: Helikopter Akustikanalyse, Tauchsonar und Taktische Karte (auch nochmals 8), Sonarseiten |
| `Plotwerkzeug + Klick` | Auf den gemeinsamen Plot zeichnen: Werkzeug über der Karte wählen, einmal (Marke, Peillinie) oder zweimal (Lineal, Kreis, Koppellinie) klicken |
| `Alt+, / Alt+.` | Kontaktliste (Alt+,) oder Stationsbereich (Alt+.) ein- oder ausklappen |
| `Alt+L` | Einsatzprotokoll öffnen oder schließen |
| `Esc` | Leitfaden, Ausguck oder Kontaktbibliothek schließen und zur Station zurück |

## Eingabe und Dialoge

| Taste / Eingabe | Funktion |
|---|---|
| `Numerische Eingabe` | Ziffern, Punkt oder Komma; Backspace; Enter bestätigt; Esc bricht ab. Mit der Maus über das eingeblendete Tastenfeld. |
| `Maus` | Klick auf eine Taste der Tastenleiste drückt sie (gehalten wie die Taste); Reiter oben wechseln die Station; Klick auf Kurs-, Fahrt- oder Tiefenscheibe befiehlt den Wert; Statuslampen, Tastenhinweise, Seitenreiter, Listenzeilen und Werte der Statuszeile anklickbar (Rahmen unter der Maus; Strg+Enter nur an Station 3); Menü- und Dialogzeilen anklickbar; Mausrad blättert; Rechtsklick bricht ab wie Esc. Menü-Symbol in der Kopfzeile: Spielmenü (Hilfe, Optionen, Speichern/Laden, Wetter, Plot, Autocrew, Beenden u. a.); Schließfeld oben rechts in jedem Overlay wirkt wie Esc; Tastenchips für Sonar-Kontaktbefehle (C, T, G, M, Y), OPZ-Zielseite (M, G, ←/→), Begleiter-Befehle und U-Boot-Rohre/Täuschkörper (Shift+M, Strg+M, V). ESSM und ASROC des Begleiters nur per Strg+Enter. |
| `Hilfe` | ←/→/Tab Kategorie; ↑/↓ zeilenweise; Bild↑/Bild↓ seitenweise; im Handbuch [ ] oder , . bzw. 0-9 Kapitel; F1/Esc schließen. |
| `Speichern/Laden` | 1 bis 5 wählt Slot; Enter bestätigt; Esc zurück. |
| `Beenden-Dialog` | ↑/↓ wählen, Enter bestätigen: zurück zum Spiel, speichern und beenden, zum Hauptmenü (ohne Speichern), ohne Speichern beenden; Esc/N schließt. |
| `Missionsende` | R Neustart mit gleichem Seed (Editor-Mission startet sich selbst neu); M zum Hauptmenü; Esc Beenden-Dialog. |
| `Commander-Vorschlag` | F6 annehmen; F7 ablehnen; F8 Vorschlagsart; Esc ausblenden. |
| `SimLog` | ↑/↓, Bild↑/Bild↓, Home/End oder Mausrad; M Karte, F Karte einpassen; F4/Esc oder Schließfeld schließen. |
| `Wetter/Analyse` | 0, Esc oder das Schließfeld schließt das Analysefeld. |
| `Autocrew-Übersicht` | F3, Esc oder das Schließfeld schließt. |

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
