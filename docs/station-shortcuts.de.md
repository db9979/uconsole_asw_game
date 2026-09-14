# U-Jagd 0.2.1 - Stations- und Tastenkürzel

Druckfassung: [`station-shortcuts.de.pdf`](station-shortcuts.de.pdf).
Maßgeblich ist die implementierte lokale Bedienung. Stationsnummern und
Tasten sind kontextabhängig; normale Bereitschafts-, Schadens- und
Berechtigungsprüfungen bleiben wirksam.

## Global

| Taste / Eingabe | Funktion |
|---|---|
| `1 bis 9` | Station direkt wählen; aktive Stationsnummer erneut drücken, um verfügbare Seiten weiterzuschalten. |
| `Tab / Shift+Tab` | Nächste / vorherige Station. |
| `P` | Pause oder Fortsetzen. |
| `[ / Z` | Zeitraffer verringern. |
| `] / X` | Zeitraffer erhöhen. |
| `+ / -` | Maschinentelegraf vor / zurück; auch Num+ / Num-. |
| `F1` | Kontextsensitive Hilfe öffnen. |
| `F2` | Autocrew der aktuellen Station ein- oder ausschalten. |
| `F3` | Autocrew-Übersicht öffnen. |
| `F4` | SimLog öffnen, sofern die Option aktiviert ist. |
| `F8` | Taktischen Einheitenanalysator öffnen; bei Commander-Vorschlägen Vorschlagsart wechseln. |
| `F9` | Lokale Commander-/Remote-Crew-Verwaltung öffnen. |
| `F10` | Optionen öffnen; während Pause funktioniert zusätzlich O. |
| `N` | Nationen-/Einheitenansicht öffnen; nicht am Sonar. |
| `S / L` | Speichern / Laden; L ist in der OPZ stattdessen der Fusionsbefehl. |
| `Alt+Enter` | Vollbild umschalten. |
| `Esc` | Fixierten Tooltip lösen, Eingabe/Ansicht abbrechen oder Beenden-Dialog öffnen. |

## 1  Brücke

| Taste / Eingabe | Funktion |
|---|---|
| `← / → halten` | Sollkurs kontinuierlich nach Backbord / Steuerbord ändern. |
| `↑ / ↓` | Maschinentelegraf vor / zurück. |
| `U` | Sollkurs numerisch eingeben. |
| `V` | Sollfahrt numerisch eingeben. |
| `Q / E` | Karte heraus- / hineinzoomen. |
| `K` | Kartenverfolgung ein- oder ausschalten. |
| `Mausrad / Ziehen` | Karte um Mausposition zoomen / verschieben. |
| `Klick auf Objekt` | Tooltip fixieren; beobachtbaren Sonarkontakt gegebenenfalls wählen. |

## 2  Sonar

| Taste / Eingabe | Funktion |
|---|---|
| `Bild↑ / Bild↓` | Vorherige / nächste Sonarseite: Broadband, LOFAR, DEMON, TMA, Environment, ACTIVE. |
| `2` | Bei bereits aktivem Sonar zur nächsten Sonarseite. |
| `Shift+A` | Aktiven Schiffssonar-Ping senden. |
| `Shift+B` | Empfangsarray zwischen HMS/Bug und TAS/Schlepparray wechseln. |
| `Y` | TAS ausbringen oder einholen. |
| `E` | Bathythermografische Messung durchführen. |
| `U / V` | TAS-/VDS-Solltiefe um 10 m heben / senken. |
| `R` | Horchpeilung numerisch eingeben. |
| `← / →` | Horchpeilung um 0,5° ändern; Shift: 5°, Strg: 0,1°. |
| `↑ / ↓` | Vorherigen / nächsten Kontakt wählen. |
| `Enter` | Gewähltem Kontakt folgen; bei Fokus zur manuellen Peilung zurückkehren. |
| `J` | Sonar-Hörton ein- oder ausschalten. |
| `, / .` | Hörlautstärke um 10 % verringern / erhöhen. |
| `A / B / H` | Breitband-, gefilterten oder Heterodyn-Hörmodus wählen. |
| `D` | Zwischen Breitband und gefiltertem Hören wechseln. |
| `I / O` | Empfangsverstärkung um 3 dB verringern / erhöhen. |
| `F` | Frequenzband weit / tief / mittel wechseln. |
| `N` | Eigenantriebs-Notchfilter ein- oder ausschalten. |
| `K` | Erkannte Harmonik-Hypothese wählen oder löschen. |
| `Leertaste` | LOFAR-Peak-Hold ein- oder ausschalten. |
| `T / C / G / M` | TMA umschalten / klassifizieren / an OPZ freigeben / als Waffenziel setzen. |
| `Maus` | Seitentab oder Kontakt wählen; im Broadband-Wasserfall Horchpeilung setzen. |

## 3  Waffen

| Taste / Eingabe | Funktion |
|---|---|
| `↑ / ↓ halten` | Torpedo-Solltiefe zwischen 10 und 300 m ändern. |
| `← / →` | Vorherigen / nächsten Sonarkontakt wählen. |
| `M` | Gewählten Sonarkontakt als Ziel setzen. |
| `T / Strg+Enter` | Schiffstorpedo starten; Bereitschafts- und ROE-Prüfungen gelten. |
| `H` | Helikopter starten oder zurückrufen. |
| `B / D` | Sonarboje absetzen / Helikoptertorpedo abwerfen. |
| `V` | Nixie-Schleppköder ausbringen. |
| `Q / E / K` | Kartenzoom heraus / hinein / Verfolgung umschalten. |
| `Mausrad / Ziehen` | Karte zoomen / verschieben. |

## 4  Schadensabwehr

| Taste / Eingabe | Funktion |
|---|---|
| `← / →` | Vorherige / nächste Abteilung wählen. |
| `↑ / ↓` | Reparaturteam 1 bis 3 wählen. |
| `Enter` | Gewähltes Team der gewählten Abteilung zuweisen. |
| `Backspace` | Gewähltes Team zurückziehen. |
| `Klick auf Abteilung` | Abteilung wählen und Zuweisung des aktuell gewählten Teams versuchen. |
| `1 bis 9` | Wechselt immer die Station; wählt kein Reparaturteam. |

## 5  OPZ / CIC

| Taste / Eingabe | Funktion |
|---|---|
| `↑ / ↓` | Vorherigen / nächsten CIC-Track wählen. |
| `C / F` | Klassifikation / NATO-Zugehörigkeit des gewählten Tracks ändern. |
| `Leertaste` | Gewählten Rohbericht markieren oder Markierung entfernen. |
| `L / Shift+L` | Aus markierten Meldungen Fusion bilden / gewählte Fusion auflösen. |
| `Backspace` | Alle Markierungen leeren. |
| `Delete / H` | Bericht unterdrücken / Anzeige unterdrückter Meldungen umschalten. |
| `M` | CIC-Track an Sonar/Waffen übergeben. |
| `Bild↑ / Bild↓` | Radar-Anzeigebereich vergrößern / verkleinern. |
| `← / →` | Vorheriges / nächstes ASM-Ziel wählen. |
| `E / Strg+Enter` | ESSM starten; Bereitschafts- und ROE-Prüfungen gelten. |
| `G` | Chaff ausbringen. |
| `R / Shift+R` | Seezielradar / Luftraumradar ein- oder ausschalten. |
| `Mausrad / Klick` | PPI-Bereich ändern / dargestellten Bericht wählen. |

## 6  Funk

| Taste / Eingabe | Funktion |
|---|---|
| `↑ / ↓` | Vorheriges / nächstes HFDF-Signal wählen. |
| `Enter` | HFDF-Peilung zusammen mit der eigenen Position protokollieren. |

## 7  Maschinenraum

| Taste / Eingabe | Funktion |
|---|---|
| `↑ / ↓` | Maschinentelegraf vor / zurück. |
| `A` | Schleichfahrt / Normalbetrieb umschalten. |
| `U` | Sollkurs numerisch eingeben. |
| `V` | Sollfahrt numerisch eingeben. |
| `+ / -` | Globaler Maschinentelegraf vor / zurück. |

## 8  Helikopter

| Taste / Eingabe | Funktion |
|---|---|
| `H` | Helikopter starten oder zurückrufen; Wettergrenzen gelten für den Start. |
| `← / →` | Wegpunktpeilung um 15° ändern. |
| `↑ / ↓` | Wegpunktentfernung um 1 NM erhöhen / verringern. |
| `M` | Sonarkontakt als Lufttorpedoziel setzen. |
| `B` | Sonarboje an aktueller Position absetzen. |
| `Y` | Tauchsonar ausbringen oder einholen. |
| `U / V` | Tauchsonar-Solltiefe um 10 m heben / senken. |
| `A` | Aktiven Tauchsonar-Ping senden. |
| `D / Strg+Enter` | Leichttorpedo abwerfen. |
| `Q / E / K` | Kartenzoom heraus / hinein / Verfolgung umschalten. |
| `Klick in freie Karte` | Wegpunkt direkt setzen; Objektklick wählt stattdessen Objekt/Tooltip. |

## 9  EloKa / ESM

| Taste / Eingabe | Funktion |
|---|---|
| `↑ / ↓` | Vorherige / nächste passive ESM-Auffassung wählen. |
| `C` | Manuelle Radarart-Zuordnung wechseln. |
| `Klick auf Track` | Auffassung wählen und gegebenenfalls Tooltip fixieren. |

## Eingabe und Dialoge

| Taste / Eingabe | Funktion |
|---|---|
| `Numerische Eingabe` | Ziffern, Punkt oder Komma; Backspace; Enter bestätigt; Esc bricht ab. |
| `Hilfe` | ←/→/Tab Kategorie; ↑/↓ zeilenweise; Bild↑/Bild↓ seitenweise; F1/Esc schließen. |
| `Speichern/Laden` | 1 bis 5 wählt Slot; Enter bestätigt; Esc zurück. |
| `Commander-Vorschlag` | F6 annehmen; F7 ablehnen; F8 Vorschlagsart; Esc ausblenden. |
| `SimLog` | ↑/↓, Bild↑/Bild↓, Home/End oder Mausrad; F4/Esc schließen. |

## Hinweise

- `Num-Enter` entspricht in Spiel- und Eingabedialogen grundsätzlich `Enter`.
- Wiederholte Keydown-Ereignisse werden ignoriert; nur ausdrücklich als
  gehalten beschriebene Steuerungen arbeiten kontinuierlich.
- Remote Crew verwendet Browser-Bedienelemente. Dieses Blatt beschreibt die
  lokale Tastatur- und Mausbedienung auf der uConsole.
- U-Jagd ist ein Spiel und kein Ausbildungs- oder Navigationsprodukt.

Erzeugt mit `python tools/build_station_shortcuts_pdf.py`.
