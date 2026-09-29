# 1 Brücke {#station-bridge}

## Zweck {#bridge-purpose}

Die Brücke führt die Fregatte: Kurs, Fahrt und Position zu Küste, Kontakten und Bedrohungen. Jeder Sensor hängt davon ab, wie das Schiff gefahren wird. Schnell und geradeaus ist laut und blind; langsame, ruhige Schläge mit bewussten Wenden lassen Sonar und TMA arbeiten.

## Anzeigen und Instrumente {#bridge-displays}

Die obere Leiste zeigt Station, Mission, Uhrzeit, Fahrt und Kurs; der Kartenkopf zeigt nur den Maßstab (dazu „folgen“, solange `K` dem eigenen Schiff folgt). Seite 1 (Navigation) zeigt Karte und vier Felder; Seite 2 (nochmals `1`) zeigt das Missionsbriefing; Seite 3 ist das Ausguck-Sichtfeld. Das Kartenwasser dunkelt mit der Uhr in drei Stufen ab (Tag, Dämmerung innerhalb einer Stunde um 05:30 und 19:30, Nacht), und Regen oder Sturm schraffiert die Karte mit gestrichelten Diagonalen (ein Sturm zusätzlich mit gelbem Rand); beides ist nur Anzeige, ebenso auf der Browserkarte. Optionen Seite 2 kann Karten- und Plotlinien glätten.

```text
+---------------------------+----------------------+
|                           | KURS / RUDER         |
|   KARTE (genordet)        |  Kurs 045 > 080      |
|   eigenes Schiff + Kielw. |  Ruder 15 stb        |
|   veröffentlichte Tracks  +----------------------+
|   Peillinien / Fixe       | FAHRT / AKUSTIK      |
|   Helikopter, Bojen       |  HALF 10,0 kn        |
|                           |  38% Eigenlärm       |
|                           +----------------------+
|                           | TAKTISCHE LAGE       |
|                           |  Bedrohungen, Senso- |
|                           |  ren, Mittel, Wetter |
+---------------------------+----------------------+
 Fußzeile: <- -> Kurs | Auf/Ab Telegraph | U/V direkt
```

- **Kurs / Ruder:** aktueller Kurs, befohlener Kurs (`→`), Ruderlage in ganzen Grad und, nur während einer Drehung, der Drehkreis. Unter den Zahlen zeigt eine Ruderskala die Lage von Backbord (links) nach Steuerbord (rechts), und eine Kompassrose zeigt die Kursnadel mit dem befohlenen Kurs als hohle gelbe Marke.
- **Fahrt / Akustik:** Telegraphenstufe, Fahrt, Eigenlärm in Prozent und Warnung KAVITATION über 15 kn. Eine Fahrtskala von 0 bis 31 kn zeigt die aktuelle Fahrt als Nadel und die befohlene Fahrt als hohle gelbe Marke.
- **Taktische Lage:** beobachtete Bedrohungen (gehörter Torpedo-Starttransient oder HF-Ortungsimpulse, ein vom Sonar als Torpedo klassifizierter Kontakt oder ein als möglicher Flugkörper markierter Luftkontakt), Sensorzustand (Radar, TAS), Mittel (Helikopter, Bojen) und Wetter/Tag-Nacht. Neben den Wetterzeilen blickt ein kleines Bild im Stil des Startbilds in den Wind: der Himmel der Stunde mit Sonne, Mond oder Sternen, die Wolken, Regen, Schnee oder Nebel und die auf das Auge zulaufende See, mit einer Windrose (Norden oben, der Pfeil weht mit dem Wind) in der Ecke; die Remote-Crew-Brücke zeigt dasselbe Bild.
- **Karte:** synthetische Kartentiefe und Küste, eigenes Schiff, von anderen Stationen veröffentlichte Tracks. `Q`/`E` zoomen in festen Stufen (Kartenhöhe 500, 250, 100, 50, 25, 10, 5, 2, 1 und 0,5 sm), das Mausrad stufenlos bis 0,5 sm; das Gitter wird beim Hineinzoomen feiner (bis 0,1 sm). Ziehen verschiebt, `K` folgt dem eigenen Schiff.

## Ausguck-Meldungen {#bridge-lookout}

Der Brückenausguck (Augenhöhe 18 m, Fernglas 7x50) meldet seine Sichtungen im Ereignis-Feed als `AUSG`-Zeilen, zum Beispiel `Brücke/Ausguck: Fregatte (Admiral-Gorshkov-Fregatte) in 040°, 3.8 sm`. Die Remote-Crew-Brücke zeigt dieselben Meldungen unter „Ausguck-Meldungen“. Brückenseite 3 (Ausguck-Sichtfeld) zeigt die Sichtungen nordorientiert um das eigene Schiff mit der vom Ausguck gemessenen Peilung und Entfernung, nach Art eingefärbt (Oberwasser, U-Boot, Luftfahrzeug, Torpedo) und mit dem Erkannten beschriftet, daneben Sicht, Seegang, Tag/Nacht und die letzten Meldungen; `,` und `.` ändern den Radius (2 bis 30 sm). Über den Meldungen zeigt ein Horizontstreifen das Fernglas voraus (90° Sichtfeld, Skala rechtweisender Peilungen, mit der See bewegter Horizont, Licht der Stunde) mit den Umrissen der Ausguck-Sichtungen in gemessener Peilung und Entfernung; es ist derselbe Renderer wie das Sehrohr des U-Boots. Das Bild hat den Stil des Startbilds: tagsüber blauer Himmel, in der Dämmerung ein warmer Horizont, nachts Sterne und der Mond in seiner Phase in seiner Peilung mit seinem Glitzern auf dem Wasser; Wolken, Regen, Schnee und Nebel folgen der Wetterstation, und die Umrisse erscheinen in Stahl mit heller Kante, nachts mit beleuchteten Fenstern. Von der Dämmerung bis zum Morgen und bei Sicht unter 2 sm führen neutrale Handels- und Fischereifahrzeuge ihre Positionslichter (Kriegsschiffe fahren abgeblendet): weiße Topplichter über die vorderen 225° (ab 50 m Länge zwei, das hintere höher, 6 sm), das grüne Steuerbord- oder rote Backbord-Seitenlicht (3 sm), beide, wenn das Schiff genau auf einen zuhält, und das weiße Hecklicht über die 135° achteraus (3 sm; unter 50 m Länge ein Topplicht mit 5 sm und die übrigen mit 2 sm), nie weiter als die Sicht. Fahrzeuge bei der Arbeit führen dazu ihre Rundumlichter: ein Trawler Grün über Weiß (ein Topplicht erst ab 50 m), ein Lotsenfahrzeug Weiß über Rot statt der Topplichter, ein Vermessungsschiff, Kabelleger oder Forschungsschiff als manövrierbehindertes Fahrzeug Rot, Weiß, Rot und ein Minenräumer drei grüne; ein Schlepper ohne Schleppzug zeigt gewöhnliche Lichter. Zivile Flugzeuge zeigen das rote linke und grüne rechte Flügelspitzenlicht und das weiße Hecklicht (3 sm) sowie ihre blitzenden roten Kollisionswarnlichter und weißen Blitzlichter (10 sm); Militärflugzeuge fliegen abgeblendet; die Silhouette zeigt dann mit dem Bug dorthin, wohin die Lichter weisen, und ein beleuchtetes Schiff wird an seinen Lichtern gesichtet, auch wo der dunkle Rumpf es nicht wird (die Klasse braucht weiter die Silhouette). Flugzeuge stehen in ihrem wahren Höhenwinkel über der Kimm, berechnet aus Flughöhe und Entfernung abzüglich der Erdkrümmung, und hängen hinter den Wolken im ruhigen Himmel, statt mit dem Seegang zu schwanken; ein hohes, nahes Flugzeug liegt über dem Bildfeld, bis man das Fernglas nach oben neigt. Die Remote-Crew-Brücke zeigt dasselbe Fernglas als Karte („Fernglas des Ausgucks“), geschwenkt nur in diesem Browser mit den Pfeiltasten (2°, 10°) und „Bug“. `B` nimmt das Fernglas groß über die Karte: ein 16°-Sichtfeld, das mit `,` und `.` (`Umschalt`: 20°-Schritte) oder per Klick in das Rundumbild darunter geschwenkt wird; das Rundumbild markiert jede Sichtung in ihrer gemessenen Peilung, der Bug liegt in der Mitte. Darunter stehen die Sichtungen, die der Sichtlinie nächste zuerst. Die kartierte Küste steht im Horizontstreifen und im Fernglas auf dem Horizont, so weit der Ausguck Land sieht (höchstens 20 sm, im Dunst verblassend), und das Rundumbild markiert sie an seinem Fuß; die Karte kennt keine Höhen, die Hügel sind mit 25 bis 70 m angenommen. Solange das Fernglas oben ist, neigen `↑`/`↓` es um 2° (`Umschalt`: 10°, von 20° nach unten bis 45° nach oben) statt den Maschinentelegrafen zu bedienen, `Q`/`E` zoomen (16°, 8° oder 4° Feld) und die `Leertaste` schaltet die Stabilisierung, die alle bis auf ein Achtel der Schiffsbewegung herausnimmt; die Zeile unter dem Bild zeigt Neigung und Feld, und die Remote-Crew-Karte hat dieselben Knöpfe für ihren eigenen Browser. Die See folgt dem Wind: gegen die See laufen die Kämme in langen Reihen auf einen zu, mit der See laufen ihre Rücken davon, quer dazu ziehen kurze Kämme seitlich durchs Bild, und das Schiff stampft in Gegen- oder Mitlaufsee und rollt in Dwarssee. `B` erneut führt zur Karte zurück; das Fernglas ist reine Anzeige und wird nicht gespeichert. Ein Kontakt wird beim Näherkommen in bis zu drei Stufen gemeldet, jede Stufe einmal:

- **Gesichtet:** nur die Art des Objekts ist klar (Fahrzeug, Luftfahrzeug, kleines Objekt an der Wasseroberfläche).
- **Klasse:** die Silhouette zeigt die Klasse, zum Beispiel Handelsschiff, Kriegsschiff, Flugzeugträger, Fischereifahrzeug, Speedboot, aufgetauchtes U-Boot, Verkehrsflugzeug oder Militärflugzeug.
- **Typ:** auf kurze Entfernung nennt der Ausguck den Typ: Frachter, Tanker, Passagierschiff, Schlepper, Fregatte, Zerstörer, Korvette oder Kampfflugzeug; Kriegsschiffe und Militärflugzeuge zusätzlich mit ihrem Klassennamen. Handelsschiffe und Verkehrsflugzeuge werden über Namen, AIS oder Transponder identifiziert, nicht mit dem Auge; der Ausguck meldet deshalb nie ihren Namen oder den Flugzeugtyp.

Klasse und Typ brauchen eine feiner aufgelöste Silhouette als die Sichtung (Johnson-Kriterien): an einem klaren Tag wird ein Tanker auf etwa 7 sm klassifiziert und eine Fregatte auf etwa 4 sm identifiziert, ein Speedboot erst innerhalb von 3 sm klassifiziert, und nachts ist der Typ nur auf wenige Kabellängen erkennbar. Nebel, Regen und Seegang verkürzen jede Stufe. Der Ausguck meldet außerdem „Land in Sicht“ mit der Peilung der nächsten Küste und eine Torpedolaufbahn mit Banner. Die Klasse bleibt erhalten, solange er den Kontakt hält. Sie erscheint in den Tooltips von Karte und OPZ als „Ausguck: …“ und ist nur eine Beobachtung: Sie setzt weder die OPZ-Klassifizierung noch die Zugehörigkeit.

## Autopilot-Route {#bridge-route}

Das Ruder kann einer Route aus bis zu 8 Wegpunkten folgen. Auf der Navigationsseite setzt ein Rechtsklick in die Karte einen Wegpunkt; `W` startet ein Suchmuster ab Position und Kurs des Schiffs (zuerst ein Zickzack mit 3 sm langen Schlägen 45° beiderseits des Kurses, erneut gedrückt ein wachsendes Quadrat mit Schlägen von 1, 1, 2, 2, 3, 3, 4, 4 sm nach rechts drehend, beim dritten Mal wird die Route gelöscht), und `Rücktaste` löscht sie. Die Karte zeichnet die Route als bernsteinfarbene Linie mit nummerierten Wegpunkten, das Kursfeld zeigt den nächsten mit seinem Abstand. Der Autopilot setzt nur den befohlenen Kurs; die Fahrt bleibt beim Maschinentelegrafen. Ein Wegpunkt gilt innerhalb von 0,3 sm als erreicht, dann steuert das Ruder den nächsten an; nach dem letzten hält das Schiff seinen Kurs. Jeder Ruderbefehl (`←`/`→`, `U`, der Trackball oder ein Kurs aus der Remote Crew) übernimmt und schaltet die Route ab; bei ausgefallener Brücke lässt sich keine Route setzen, und eine laufende wird nicht gesteuert. Die Route wird gespeichert. Die Remote-Crew-Brücke hat eine Karte „Autopilot-Route“: „Wegpunkte auf der Karte setzen“ lässt einen Klick in freie Karte einen Wegpunkt setzen, Knöpfe starten Zickzack oder Quadratsuche oder löschen die Route.

## Tasten {#bridge-keys}

<!-- keys:bridge -->

Auf der Brücke steuert der Trackball das Ruder. `U` und `V` öffnen die direkte Zahleneingabe; die Simulation läuft währenddessen weiter. `Enter` bestätigt, `Esc` bricht ab.

## Standardablauf {#bridge-sop}

<!-- sop:bridge -->

Gefechtslage:

1. Torpedo gemeldet: sofort FLANK, so drehen, dass die Torpedopeilung achteraus oder querab liegt.
2. Nixie in der Waffenzentrale befehlen (`V`); weiter drehen, damit der Torpedo zuerst den Täuschkörper sieht.
3. Nach der Abwehr unter 15 kn gehen, damit das Sonar wieder erfasst; mit ausgebrachtem Schleppsonar nie über 20 kn.

## Tipps für Profis {#bridge-tips}

- TMA braucht eine echte Änderung der eigenen Geschwindigkeit. Eine Wende um 30-60 Grad mit anschließend mehreren Minuten ruhigem Schlag liefert die beste Entfernungsschätzung. Drehen auf der Stelle hilft nicht.
- Die Drehrate wächst mit der Fahrt (etwa 0,75 Grad/s bei 10 kn, 1,2 bei 16 kn, 1,9 bei 25 kn, 2,3 bei 31 kn), der Drehkreis bleibt deshalb bei etwa 0,4 NM. Ein gestopptes Schiff kann nicht drehen. Fahrtänderungen brauchen Minuten: etwa 90 s bis 90 % von FULL; ein Stopp aus FULL nutzt Umsteuerung der Propellersteigung und dauert etwa 90 s. Ausweichmanöver früh beginnen.
- In einer harten Wende mit Fahrt krängt das Schiff einige Grad nach außen; bei schwerer See dämpfen die Flossenstabilisatoren das Rollen, aber nur mit Fahrt durchs Wasser.
- Im Flachwasser sackt der Rumpf ab (Squat): bei 25 kn wächst der Tiefgang um bis zu 3 m, bei 31 kn um bis zu 4,6 m, wenn das Wasser weniger als etwa fünf Tiefgänge tief ist. Im Flachwasser Fahrt reduzieren.
- Sprint und Drift: mit FULL an eine neue Position, dann auf 4-6 kn gehen und horchen.
- Starke einseitige Flutung bewirkt Krängung und einen stetigen Drehzug; mit Ruder ausgleichen.
- Das Schiff kann nicht auf Land fahren (es wird zurückgeschoben), aber Flachwasser begrenzt die Tauchtiefe des Helikoptersonars (10 m Bodenabstand).
- Die Wassertiefe folgt der Gezeit (halbtägig, etwa 12,4 h, im Flachwasser bis zu einigen Metern). Eine Passage, die bei Hochwasser sicher ist, kann bei Niedrigwasser zur Grundberührung führen; das HQ-Wetterbulletin meldet die aktuelle Gezeit am Schiff.
- Wind treibt das Oberflächenwasser: etwa 3 % der Windgeschwindigkeit, 20 Grad rechts von der Windrichtung, zusätzlich zur ständigen Meeresströmung.

## Nicht modelliert {#bridge-limits}

- Keine Zeitraffung und keine Pause. Der Autopilot steuert nur den Kurs, nie die Fahrt, und weicht weder Land noch Flachwasser aus.
- Keine automatische Torpedoerkennung: der Alarm beruht nur auf gehörten Intercepts oder der Klassifizierung des Sonarbedieners; ein außerhalb der Suchkopfreichweite leise laufender Torpedo kann unangekündigt eintreffen. Der Ausguck meldet nur eine sichtbare Laufbahn.
- Der Ausguck liest weder Schiffsnamen noch Flagge und meldet keine Lichter oder Signalkörper; die Lichter werden nur gezeichnet. Kein Schiff im Spiel ankert, schleppt, fischt mit Schleppfahrt oder ist manövrierunfähig, daher erscheinen Ankerlicht, Schlepplichter und die Lichter eines manövrierunfähigen Fahrzeugs nie.
