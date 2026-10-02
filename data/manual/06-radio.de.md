# 6 Funk {#station-radio}

## Zweck {#radio-purpose}

Der Funkraum wickelt die Verbindung zum Hauptquartier und die Kurzwellenpeilung (HFDF) ab. Das Hauptquartier sendet Befehle, Wetterberichte und ROE-Änderungen per Fernschreiber. HFDF peilt U-Boote, die auf Kurzwelle senden oder schnorcheln, bis 120 sm, weit jenseits der Sonarreichweite.

## Anzeigen und Instrumente {#radio-displays}

Seite 1 listet aktuelle HFDF-Signale mit der Peilrose links und die Kreuzpeilkarte mit dem Peilprotokoll rechts; Seite 2 ist der Fernschreiber mit dem HQ-Verkehr; Seite 3 listet die HQ-Aufträge.

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
- Jedes Signal zeigt Frequenz und Ausbreitung. Ein U-Boot, das eine ferne Landstation ruft, wählt tagsüber eine hohe Frequenz (Bodenwelle bis etwa 95 sm hörbar) und nachts eine niedrigere (etwa 150 sm). Jenseits der Sprungdistanz, einige hundert sm entfernt, kommt stattdessen die Raumwelle an. Ein KI-U-Boot auf Sehrohrtiefe, das das Schiff in den letzten 10 Minuten gehalten hat, meldet es alle 30 Minuten zu einem unvorhersehbaren Zeitpunkt mit einem 20-s-Ruf an seine Führung, den das HF/DF wie jeden anderen hört.
- Protokollierte Linien und Kreuzpeilungen erscheinen auf den Karten von Brücke, Waffenzentrale und Helikopter.
- Im Remote-Crew-Browser hat der Funkraum keine Karte: ein HF/DF-Peilscope (ein Strahl je Signal, die Fächerbreite ist der Peilfehler, geloggte Peilungen gestrichelt), Empfängerkanäle mit Frequenz, Ausbreitung, Signalmesser und Log-Taste sowie der Fernschreiber. Ein gewählter Kanal öffnet das Kontaktdetail zum Bewerten; geloggte Peilungen und Kreuzpeilungen stehen im Stationsbereich.
- Eine zweite Peilung desselben Signals ergibt eine Kreuzpeilung, wenn sie mindestens 1 sm entfernt von der ersten und innerhalb von 300 s genommen wird.
- Der Fernschreiber bringt außerdem alle 30 Minuten den Wetterbericht und HQ-Meldungen (Bedrohungswarnungen, ROE FREI).
- Zum Missionsbeginn meldet das HQ die Bedrohung. Bei **grober** Aufklärung nur eine ungefähre Peilung und Entfernung einer Bedrohung, bei **genauer** Aufklärung zusätzlich jeden eingesetzten feindlichen Einheitentyp mit Anzahl (zum Beispiel "1x Altmetall (Diesel, älter), 2x Luftangriffswelle mit Seezielflugkörpern"), mit den Namen aus dem Einheitenanalysator (`F8`); Positionen bleiben unbestätigt. Patrouille hat immer genaue Aufklärung, Doppeljagd und Nuklearer Abfang grobe, bei der Freien Jagd wählen Sie im Schwierigkeits-Bildschirm (letzte Zeile, "HQ-Aufklärung").

Seite 1 zeigt außerdem eine KW-Peilrose: Jedes aktuelle Signal ist ein Strahl, aufgefächert so breit wie sein Peilfehler.

Die **Kreuzpeilkarte** daneben ist das Koppelblatt des Funkraums, Norden oben, mit Gitter und Küste: Jede protokollierte Peilung der letzten 5 Minuten ist eine Linie vom Ort, an dem das Schiff sie nahm (der Ursprung als kleiner Kreis), die aktuellen Auffassungen sind dünne Linien vom Schiff mit ihrem Fehlerfächer (die gewählte gelb), zwei protokollierte Peilungen desselben Signals, die sich schneiden, markieren den Schnittpunkt mit einer Raute, und jede Kreuzpeilung zeigt ihre Fehlerellipse mit Kennung und 1-Sigma-Fehler. Ältere Linien verblassen. Die Karte rahmt Schiff, alle Ursprünge und Fixe ein und zeigt ihre halbe Breite (mindestens ±20 sm); darunter stehen die neuesten Peilungen und Fixe. Sie zeigt nur, was der Funkraum gemessen und berechnet hat, nie den Sender selbst.

## HQ-Aufträge {#radio-tasks}

Neben der Jagd funkt das HQ Aufträge an das Schiff: den ersten etwa 15 bis 25 Minuten nach Beginn einer eingebauten Mission, danach einen alle 25 bis 45 Minuten, höchstens sechs je Mission und zwei gleichzeitig offen (auf freier Fahrt alle 10 bis 20 Minuten ohne Obergrenze, mit dem Überwachen eines Seegebiets als sechster Art; siehe Kapitel Referenz). Eigene Missionen erhalten keine. Jedes Angebot kommt über den Fernschreiber und auf Seite 3 (Aufträge). Innerhalb von 5 Minuten mit `A` (annehmen) oder `D` (ablehnen) antworten; keine Antwort gilt als Ablehnung. Ein zerstörter Funkraum kann nicht antworten.

- **Seenotruf (SAR):** eine Rettungsinsel mit 2 bis 6 Personen, per EPIRB mit etwa 0,5 sm Fehler gemeldet, treibt mit Strom und Wind. Die Überlebenden halten je nach Wassertemperatur durch, von 40 Minuten in Wasser unter 8 °C bis 100 Minuten über 20 °C. Die Insel wird tagsüber auf 2 sm gesichtet (nachts 3 sm an ihrem Blitzlicht); dann schrumpft der Kreis in der Karte auf sie. Aufnehmen, indem das Schiff 4 Minuten lang innerhalb 0,25 sm mit höchstens 3 kn liegt, oder der Helikopter darüber schwebt (eine Minute je Person, nur wenn das Wetter Tauchsonar erlaubt). +600 Punkte, -400 bei Verlust.
- **Handelsschiff identifizieren:** Das HQ nennt ein Handelsschiff innerhalb 60 sm und gibt seine Position mit etwa 2 sm Fehler. Es gilt als identifiziert, sobald der Ausguck seine Identifizierung gemeldet hat oder der Helikopter bei mindestens 1 sm Sicht auf 1 sm heranfliegt. Etwa ein Drittel wird als verdächtig eingestuft: Das HQ gibt dann ein U-Boot-Datum nahe dem Schiff durch. 40 Minuten.
- **U-Boot-Datum:** ein Kreis mit 5 sm Radius aus einer Seefernaufklärer-Meldung; nicht hinter jedem Datum steckt ein U-Boot. 10 Minuten im Kreis mit Schiff oder Helikopter suchen. 50 Minuten. In den U-Boot-Missionen 8 und 9 gibt es diesen Auftrag nicht: Das HQ hat über dieses Boot keine Erkenntnisse.
- **Versorgung auf See:** angeboten bei weniger als 70 % Kraftstoff oder nach verbrauchten Torpedos, ASROC oder Wasserbomben; `R` auf der Seite Aufträge (im Browser *Versorger anfordern*) fordert selbst einen an, wenn mindestens 5 % Kraftstoff oder irgendein Vorrat fehlt, höchstens alle 20 Minuten nach dem Ende der letzten Versorgung. Ein befreundeter Versorger erscheint 18 bis 28 sm entfernt mit 12 kn; sein Kurs und eine Koppellinie stehen in der Karte. Innerhalb 0,3 sm und höchstens 3 kn Fahrtunterschied halten: Kraftstoff fließt die ganze Zeit (eine volle Ladung in 15 Minuten), Torpedos, ASROC, Wasserbomben, Nixie-Täuschkörper sowie CIWS- und Geschützmunition kommen in fünf Ladungen, alle 3 Minuten eine, jede ein Anteil dessen, was noch fehlt. Wer vorher abdreht, behält, was schon übergeben ist. Die Seite Aufträge zeigt, was an Bord ist. VLS-Zellen werden auf See nicht nachgeladen. +100, keine Strafe.
- **Radarstille (EMCON):** beide Radare innerhalb 90 s aus und 20 bis 30 Minuten still. +200, -250 wenn ein Radar strahlt.

Angenommene Positionen stehen in jeder Karte (auch im Remote-Crew-Browser). Die Punkte stehen in der Missionsauswertung. Der Funker im Browser antwortet mit denselben Tasten.

## Ereignisse auf See {#radio-incidents}

Die See bringt eigene Überraschungen: das erste 20 bis 40 Minuten nach dem Start einer eingebauten Mission, dann alle 30 bis 50 Minuten eines, höchstens sechs je Mission (auf freier Fahrt alle 20 bis 40 Minuten ohne Obergrenze; keine in eigenen Missionen und Lektionen). Jedes kommt über den Fernschreiber.

- **Treibnetz:** Ein Fischer meldet ein 2 sm langes Netz quer zum Kurs, 3 bis 7 sm voraus, von der Oberfläche bis 20 m tief; der Funker trägt es in jede Karte als Lineal `NET n` ein, und nach einer Stunde wird es eingeholt. Wer darüber fährt, zerreißt es: Die Fischer verlangen Schadenersatz (-100 Punkte), und ein ausgebrachtes Schleppsonar oder VDS verfängt sich und wird sofort eingeholt. Ein U-Boot, das flacher als 20 m kreuzt, verfängt sich ebenfalls und ist 20 s laut, bis es sich losreißt; tiefer taucht es darunter durch.
- **Wetterfront:** HQ warnt 10 Minuten vorher; dann halten Regen, Sturm oder Nebel 30 bis 60 Minuten an (Sicht, Wind und Regengeräusch für jeden Sensor, auf beiden Seiten), und HQ meldet, wenn sie durchgezogen ist.
- **Handelsschiff ohne AIS:** Ein Frachter ohne AIS taucht 8 bis 15 sm entfernt auf; HQ meldet ihn mit etwa 2 sm Fehler und bietet ihn als Identifizierungsauftrag an, wenn weniger als zwei Aufträge offen sind.
- **Wale:** Ein Fischer meldet eine Gruppe von zwei bis vier Walen 3 bis 6 sm voraus; sie sind echte biologische Kontakte für jedes Sonar.
- **Mann über Bord:** Ein Matrose geht neben dem Schiff über Bord; die Generalalarmglocke schlägt an, und die Karte trägt die Marke `OVERBOARD n`, die mit der Oberflächenströmung treibt. Die Brücke fährt eine Williamson-Kurve zurück und nimmt ihn auf, wenn das Schiff höchstens 0,1 sm entfernt mit höchstens 5 kn läuft; der Hubschrauber nimmt ihn auf, wenn er genau über ihm schwebt (Wegpunkt auf die Marke oder Tauchsonar ausgebracht). Gerettet gibt +100 Punkte, nach 20 Minuten im Wasser ist er verloren (-300 Punkte). Führt die KI die Brücke, steuert sie selbst auf die Marke und geht danach wieder auf 12 kn.
- **Ruderversager:** Die Rudermaschine fällt aus: 60 s klemmt das Ruder, dann steuert die Maschine vom Notruder mit halber Drehrate, bis die Rudermaschine nach 10 Minuten repariert ist.
- **Schnorchelventil und Batteriegas (U-Boot):** Auf einem dieselelektrischen U-Boot klemmt für 15 Minuten das Schnorchelkopfventil (kein Laden; das KI-U-Boot geht auf Tiefe und bleibt unten) oder es muss Batteriegas abgelüftet werden (halbe Laderate). Die Crew des besetzten U-Boots meldet beides; die Fregatte erfährt nichts davon.

Treibnetz, Front und Wale (nicht die Notfälle an Bord) gibt HQ auch in den Rundspruch an das U-Boot; ein besetztes U-Boot erfährt davon, wenn es den nächsten Rundspruch aufnimmt, und seine Crew trägt das Netz in die eigene Karte ein.

## Eigene Rufe an HQ {#radio-reports}

Auf der Aufträge-Seite kann der Funkraum HQ selbst rufen, höchstens alle 10 Minuten; die Zeile am Fuß der Auftragsliste sagt, ob ein Ruf auf Sendung ist, wie lange es bis zum nächsten dauert oder dass beide bereit sind.

- `K` **Kontaktmeldung:** sendet die Position des frischesten georteten Kontakts (Ping-, TMA-, Bojen- oder fusionierter Fix, sonst ein KW-Peilfix bis 15 Minuten alt). HQ bestätigt sie im Fernschreiber und setzt den Seefernaufklärer darauf an, wenn er in der Luft ist. HQ sagt nie, ob dort wirklich ein U-Boot war: Jede Meldung, bei der ein feindliches U-Boot innerhalb 3 sm um den Fix stand, bringt am Missionsende 150 Punkte (höchstens drei).
- `H` **Unterstützung anfordern:** HQ schickt den bereitstehenden Seefernaufklärer zum Schiff, wenn er verfügbar ist (auch bei ausgefallener OPZ), sonst meldet es, dass keine Unterstützung verfügbar ist.
- Jeder Ruf sind 20 s KW-Sendung. Solange er auf Sendung ist, nimmt ein U-Boot mit ausgefahrener Antenne (der Mast des besetzten Boots, ein KI-Boot auf Sehrohrtiefe) eine KW-Peilung auf die Fregatte (+/-8 Grad bei Bodenwelle, +/-16 Grad bei Raumwelle): Das besetzte Boot erhält eine Meldung und einen Peilstrahl auf seiner Karte, ein KI-Boot merkt sich die Richtung. Reden mit HQ kostet Funkstille.

## Tasten {#radio-keys}

<!-- keys:radio -->

## Standardablauf {#radio-sop}

<!-- sop:radio -->

## Tipps für Profis {#radio-tips}

- Die beiden Peilungen von Positionen quer zur erwarteten Peillinie nehmen: je rechtwinkliger sie sich schneiden, desto kleiner die Fehlerellipse.
- Ein sendendes oder schnorchelndes U-Boot ist meist flach und langsam: ein guter Moment, mit dem Helikopter heranzugehen.
- HFDF-Peilung mit einer Sonarpeilung kombinieren ergibt schnell eine Positionsschätzung.

## Nicht modelliert {#radio-limits}

- Keine freien Funksprüche: eigene Rufe an das HQ sind nur die Kontaktmeldung und die Unterstützungsanforderung, dazu die Antworten auf Aufträge; kein Fernmeldeplan und keine Kryptierung.
- Keine Frequenzabstimmung: HFDF überwacht das ganze KW-Band und listet die erfassten Signale mit ihrer Frequenz.
