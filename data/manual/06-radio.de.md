# 6 Funk {#station-radio}

## Zweck {#radio-purpose}

Der Funkraum wickelt die Verbindung zum Hauptquartier und die Kurzwellenpeilung (HFDF) ab. Das Hauptquartier sendet Befehle, Wetterberichte und ROE-Änderungen per Fernschreiber. HFDF peilt U-Boote, die auf Kurzwelle senden oder schnorcheln, bis 120 sm, weit jenseits der Sonarreichweite.

## Anzeigen und Instrumente {#radio-displays}

Seite 1 listet aktuelle HFDF-Signale und das Peilprotokoll; Seite 2 ist der Fernschreiber mit dem HQ-Verkehr; Seite 3 listet die HQ-Aufträge.

```text
 HFDF-SIGNALE               PEILPROTOKOLL
 > HF-03  247.0  Alter 12 s  HF-03 247.0 von Pos A  t=12:04
   HF-05  061.5  Alter 40 s  HF-03 239.5 von Pos B  t=12:08
                             -> KREUZPEILUNG + Fehlerellipse

   Pos A *----------__
                       --___  X  <- Fix
   Pos B *------------------/
```

- Der Peilfehler beträgt +/-8 Grad bei Bodenwelle und +/-16 Grad bei Raumwelle; Signale älter als 30 s lassen sich nicht mehr protokollieren.
- Jedes Signal zeigt Frequenz und Ausbreitung. Ein U-Boot, das eine ferne Landstation ruft, wählt tagsüber eine hohe Frequenz (Bodenwelle bis etwa 95 sm hörbar) und nachts eine niedrigere (etwa 150 sm). Jenseits der Sprungdistanz, einige hundert sm entfernt, kommt stattdessen die Raumwelle an.
- Protokollierte Linien und Kreuzpeilungen erscheinen auf den Karten von Brücke, Waffenzentrale und Helikopter.
- Im Remote-Crew-Browser hat der Funkraum keine Karte: ein HF/DF-Peilscope (ein Strahl je Signal, die Fächerbreite ist der Peilfehler, geloggte Peilungen gestrichelt), Empfängerkanäle mit Frequenz, Ausbreitung, Signalmesser und Log-Taste sowie der Fernschreiber. Ein gewählter Kanal öffnet das Kontaktdetail zum Bewerten; geloggte Peilungen und Kreuzpeilungen stehen im Stationsbereich.
- Eine zweite Peilung desselben Signals ergibt eine Kreuzpeilung, wenn sie mindestens 1 sm entfernt von der ersten und innerhalb von 300 s genommen wird.
- Der Fernschreiber bringt außerdem alle 30 Minuten den Wetterbericht und HQ-Meldungen (Bedrohungswarnungen, ROE FREI).
- Zum Missionsbeginn meldet das HQ die Bedrohung. Bei **grober** Aufklärung nur eine ungefähre Peilung und Entfernung einer Bedrohung, bei **genauer** Aufklärung zusätzlich jeden eingesetzten feindlichen Einheitentyp mit Anzahl (zum Beispiel "1x Altmetall (Diesel, älter), 2x Luftangriffswelle mit Seezielflugkörpern"), mit den Namen aus dem Einheitenanalysator (`F8`); Positionen bleiben unbestätigt. Patrouille hat immer genaue Aufklärung, Doppeljagd und Nuklearer Abfang grobe, bei der Freien Jagd wählen Sie im Schwierigkeits-Bildschirm (letzte Zeile, "HQ-Aufklärung").

## HQ-Aufträge {#radio-tasks}

Neben der Jagd funkt das HQ Aufträge an das Schiff: den ersten etwa 15 bis 25 Minuten nach Beginn einer eingebauten Mission, danach einen alle 25 bis 45 Minuten, höchstens sechs je Mission und zwei gleichzeitig offen. Eigene Missionen erhalten keine. Jedes Angebot kommt über den Fernschreiber und auf Seite 3 (Aufträge). Innerhalb von 5 Minuten mit `A` (annehmen) oder `D` (ablehnen) antworten; keine Antwort gilt als Ablehnung. Ein zerstörter Funkraum kann nicht antworten.

- **Seenotruf (SAR):** eine Rettungsinsel mit 2 bis 6 Personen, per EPIRB mit etwa 0,5 sm Fehler gemeldet, treibt mit Strom und Wind. Die Überlebenden halten je nach Wassertemperatur durch, von 40 Minuten in Wasser unter 8 °C bis 100 Minuten über 20 °C. Die Insel wird tagsüber auf 2 sm gesichtet (nachts 3 sm an ihrem Blitzlicht); dann schrumpft der Kreis in der Karte auf sie. Aufnehmen, indem das Schiff 4 Minuten lang innerhalb 0,25 sm mit höchstens 3 kn liegt, oder der Helikopter darüber schwebt (eine Minute je Person, nur wenn das Wetter Tauchsonar erlaubt). +600 Punkte, -400 bei Verlust.
- **Handelsschiff identifizieren:** Das HQ nennt ein Handelsschiff innerhalb 60 sm und gibt seine Position mit etwa 2 sm Fehler. Es gilt als identifiziert, sobald der Ausguck seine Identifizierung gemeldet hat oder der Helikopter bei mindestens 1 sm Sicht auf 1 sm heranfliegt. Etwa ein Drittel wird als verdächtig eingestuft: Das HQ gibt dann ein U-Boot-Datum nahe dem Schiff durch. 40 Minuten.
- **U-Boot-Datum:** ein Kreis mit 5 sm Radius aus einer Seefernaufklärer-Meldung; nicht hinter jedem Datum steckt ein U-Boot. 10 Minuten im Kreis mit Schiff oder Helikopter suchen. 50 Minuten.
- **Versorgung auf See:** angeboten bei weniger als 70 % Kraftstoff oder nach verschossenen Torpedos. Ein befreundeter Versorger erscheint 18 bis 28 sm entfernt mit 12 kn; sein Kurs und eine Koppellinie stehen in der Karte. 15 Minuten innerhalb 0,3 sm und höchstens 3 kn Fahrtunterschied halten füllt Kraftstoff und Torpedos auf. +100, keine Strafe.
- **Radarstille (EMCON):** beide Radare innerhalb 90 s aus und 20 bis 30 Minuten still. +200, -250 wenn ein Radar strahlt.

Angenommene Positionen stehen in jeder Karte (auch im Remote-Crew-Browser). Die Punkte stehen in der Missionsauswertung. Der Funker im Browser antwortet mit denselben Tasten.

## Tasten {#radio-keys}

<!-- keys:radio -->

## Standardablauf {#radio-sop}

<!-- sop:radio -->

## Tipps für Profis {#radio-tips}

- Die beiden Peilungen von Positionen quer zur erwarteten Peillinie nehmen: je rechtwinkliger sie sich schneiden, desto kleiner die Fehlerellipse.
- Ein sendendes oder schnorchelndes U-Boot ist meist flach und langsam: ein guter Moment, mit dem Helikopter heranzugehen.
- HFDF-Peilung mit einer Sonarpeilung kombinieren ergibt schnell eine Positionsschätzung.

## Nicht modelliert {#radio-limits}

- Keine freien Funksprüche oder Meldungen an das HQ außer der Antwort auf Aufträge; kein Fernmeldeplan und keine Kryptierung.
- Keine Frequenzabstimmung: HFDF überwacht das ganze KW-Band und listet die erfassten Signale mit ihrer Frequenz.
