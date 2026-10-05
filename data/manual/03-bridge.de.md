# 1 Brücke {#station-bridge}

## Zweck {#bridge-purpose}

Die Brücke führt die Fregatte: Kurs, Fahrt und Position zu Küste, Kontakten und Bedrohungen. Jeder Sensor hängt davon ab, wie das Schiff gefahren wird. Schnell und geradeaus ist laut und blind; langsame, ruhige Schläge mit bewussten Wenden lassen Sonar und TMA arbeiten.

## Seiten {#bridge-pages}

Die Karte füllt auf jeder Seite die linke Hälfte der Station; nochmals `1` oder `Bild Auf`/`Bild Ab` blättern das Feld daneben:

| Seite | Feld neben der Karte |
|---|---|
| 1 Navigation | Bedrohungszeile, Kurs- und Ruderfeld mit Kursscheibe, Fahrt- und Akustikfeld mit Fahrtscheibe |
| 2 Mission & Systeme | Missionsname, Auftrag und Restzeit; Sensoren, Waffenbestände, Hubschrauberzustand und Wetter |
| 3 Ausguck | Ausguck-Sichtfeld mit den Sichtungen, Horizontstreifen und Ausguck-Meldungen |

## Anzeigen und Instrumente {#bridge-displays}

Die obere Leiste zeigt Station, Mission, Uhrzeit, Fahrt und Kurs; der Kartenkopf zeigt nur den Maßstab (dazu „folgen“, solange `K` dem eigenen Schiff folgt). Das Kartenwasser dunkelt mit der Uhr in drei Stufen ab (Tag, Dämmerung innerhalb einer Stunde um 05:30 und 19:30, Nacht), und Regen oder Sturm schraffiert die Karte mit gestrichelten Diagonalen (ein Sturm zusätzlich mit gelbem Rand); beides ist nur Anzeige, ebenso auf der Browserkarte. Optionen Seite 2 kann Karten- und Plotlinien glätten.

![Brücke, Seite 1 (Navigation) auf der uConsole](figure:station-bridge)

![Brücke im Remote-Crew-Browser](figure:web-bridge-desktop)

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
- **Taktische Lage:** beobachtete Bedrohungen (gehörter Torpedo-Starttransient, HF-Ortungsimpulse oder ein U-Boot, das ein Torpedorohr flutet, ein vom Sonar als Torpedo klassifizierter Kontakt oder ein als möglicher Flugkörper markierter Luftkontakt), Sensorzustand (Radar, TAS), Mittel (Helikopter, Bojen) und Wetter/Tag-Nacht. Neben den Wetterzeilen blickt ein kleines Bild im Stil des Startbilds in den Wind: der Himmel der Stunde mit Sonne, Mond oder Sternen, die Wolken, Regen, Schnee oder Nebel und die auf das Auge zulaufende See, mit einer Windrose (Norden oben, der Pfeil weht mit dem Wind) in der Ecke; die Remote-Crew-Brücke zeigt dasselbe Bild.
- **Karte:** synthetische Kartentiefe und Küste, eigenes Schiff, von anderen Stationen veröffentlichte Tracks. `Q`/`E` zoomen in festen Stufen (Kartenhöhe 500, 250, 100, 50, 25, 10, 5, 2, 1 und 0,5 sm), das Mausrad stufenlos bis 0,5 sm; das Gitter wird beim Hineinzoomen feiner (bis 0,1 sm). Ziehen verschiebt, `K` folgt dem eigenen Schiff.

## Ausguck-Meldungen {#bridge-lookout}

Der Brückenausguck (Augenhöhe 18 m, Fernglas 7x50) meldet seine Sichtungen im Ereignis-Feed als `AUSG`-Zeilen, zum Beispiel `Brücke/Ausguck: Fregatte (Admiral-Gorshkov-Fregatte) in 040°, 3.8 sm`. Die Remote-Crew-Brücke zeigt dieselben Meldungen unter „Ausguck-Meldungen“. Brückenseite 3 (Ausguck-Sichtfeld) zeigt die Sichtungen nordorientiert um das eigene Schiff mit der vom Ausguck gemessenen Peilung und Entfernung, nach Art eingefärbt (Oberwasser, U-Boot, Luftfahrzeug, Torpedo) und mit dem Erkannten beschriftet, daneben Sicht, Seegang, Tag/Nacht und die letzten Meldungen; `,` und `.` ändern den Radius (2 bis 30 sm).

Über den Meldungen zeigt ein Horizontstreifen das Fernglas voraus (90° Sichtfeld, Skala rechtweisender Peilungen, mit der See bewegter Horizont, Licht der Stunde) mit den Umrissen der Ausguck-Sichtungen in gemessener Peilung und Entfernung; es ist derselbe Renderer wie das Sehrohr des U-Boots. Das Bild hat den Stil des Startbilds: tagsüber blauer Himmel, in der Dämmerung ein warmer Horizont, nachts Sterne und der Mond in seiner Phase in seiner Peilung mit seinem Glitzern auf dem Wasser; Wolken, Regen, Schnee und Nebel folgen der Wetterstation, und die Umrisse erscheinen in Stahl mit heller Kante, nachts mit beleuchteten Fenstern. Hat der Ausguck die Klasse eines Schiffs, U-Boots oder Luftfahrzeugs ausgemacht, erscheint es als sein 3D-Modell (das des Analysators), gedreht um den Lagewinkel, den er in 10°-Schritten schätzt, sobald es mindestens 16 Pixel lang ist; vorher, veraltet oder kleiner bleibt es eine flache Silhouette. Das Modell ist der echte Typ, den das Auge sieht (jeder Schiffs-, U-Boot- und Flugzeugtyp hat sein eigenes Modell, siehe Kapitel Missions- und Einheiteneditor), sodass sich der Typ auf Sicht bestimmen lässt; die Meldung des Ausgucks nennt nur, was er ausgemacht hat, und nur die Meldung geht an die OPZ. Jeder Umriss steht in der Peilung, die der Ausguck gemessen hat, und ein Schiff schwimmt mit seiner Wasserlinie so weit unter der Kimm, wie sein Auge in 18 m Höhe das Wasser in der gemessenen Entfernung sieht: etwa 1° darunter auf 0,5 sm, 0,4° auf 1 sm, ab etwa 9 sm auf der Kimm (Erdkrümmung); ein näheres Schiff steht vor einem ferneren. Der Lagewinkel zeigt, wie es liegt: Steuerbordseite mit dem Bug nach rechts, Backbordseite mit dem Bug nach links, Bug voraus, wenn es auf einen zuläuft.

Von der Dämmerung bis zum Morgen und bei Sicht unter 2 sm führen neutrale Handels- und Fischereifahrzeuge ihre Positionslichter (Kriegsschiffe fahren abgeblendet): weiße Topplichter über die vorderen 225° (ab 50 m Länge zwei, das hintere höher, 6 sm), das grüne Steuerbord- oder rote Backbord-Seitenlicht (3 sm), beide, wenn das Schiff genau auf einen zuhält, und das weiße Hecklicht über die 135° achteraus (3 sm; unter 50 m Länge ein Topplicht mit 5 sm und die übrigen mit 2 sm), nie weiter als die Sicht. Fahrzeuge bei der Arbeit führen dazu ihre Rundumlichter: ein Trawler Grün über Weiß (ein Topplicht erst ab 50 m), ein Lotsenfahrzeug Weiß über Rot statt der Topplichter, ein Vermessungsschiff, Kabelleger oder Forschungsschiff als manövrierbehindertes Fahrzeug Rot, Weiß, Rot und ein Minenräumer drei grüne; ein Schlepper ohne Schleppzug zeigt gewöhnliche Lichter. Zivile Flugzeuge zeigen das rote linke und grüne rechte Flügelspitzenlicht und das weiße Hecklicht (3 sm) sowie ihre blitzenden roten Kollisionswarnlichter und weißen Blitzlichter (10 sm); Militärflugzeuge fliegen abgeblendet; die Silhouette zeigt dann mit dem Bug dorthin, wohin die Lichter weisen, und ein beleuchtetes Schiff wird an seinen Lichtern gesichtet, auch wo der dunkle Rumpf es nicht wird (die Klasse braucht weiter die Silhouette). Der Ausguck meldet die Lichter, die er sieht, mit seiner Deutung, zum Beispiel `Brücke/Ausguck: Lichter in 040°, 2.8 sm: zwei Topplichter, rotes Seitenlicht; zeigt Backbordseite`: beide Seitenlichter heißen, es hält auf uns zu (laut gemeldet), Grün allein seine Steuerbordseite, Rot allein seine Backbordseite, das Hecklicht allein, es läuft ab, und die Rundumlichter seine Arbeit (Fischer, Lotse im Dienst, manövrierbehindert, Minenräumer; Blitzlichter ein Luftfahrzeug). Die Lichter eines Kontakts meldet er erst wieder, wenn sich ihre Aussage ändert, höchstens alle 2 Minuten; die Remote-Crew-Brücke führt diese Meldungen mit den übrigen.

Flugzeuge stehen in ihrem wahren Höhenwinkel über der Kimm, berechnet aus Flughöhe und Entfernung abzüglich der Erdkrümmung, und hängen hinter den Wolken im ruhigen Himmel, statt mit dem Seegang zu schwanken; ein hohes, nahes Flugzeug liegt über dem Bildfeld, bis man das Fernglas nach oben neigt. Ein Luftfahrzeug weniger als 1° über der Kimm (tief im Schwebeflug, nah am Schiff) steht dagegen auf der bewegten Kimm vor der See.

Der eigene Hubschrauber ist in all diesen Bildern (Streifen, Fernglas, Remote-Crew-Karte, Handy-Ausguck und Trefferbild), sobald die Brücke ihn sehen kann: das Hubschraubermodell an seiner wahren Position, mit eigenem Kurs und eigener Länge (15,2 m), im Transit etwa 60 m hoch, beim MAD-Lauf 30 m und über dem Tauchsonar 15 m; beim Start hebt er vom Flugdeck achteraus ab und steigt innerhalb von 0,3 sm weg, nachts zeigt er seine Positionslichter. Er braucht dieselbe Sicht wie jedes Luftfahrzeug, wird nie gemeldet oder an die OPZ gegeben und ist im Hangar nicht zu sehen. Das Ausguck-Sichtgerät markiert ihn als „eigener Hubschrauber“ an seiner Position, das Panorama mit einem kurzen grünen Strich oben, und die Liste unter dem Fernglas nennt ihn zuerst. Die Remote-Crew-Brücke zeigt dasselbe Fernglas als Karte („Fernglas des Ausgucks“), geschwenkt nur in diesem Browser mit den Pfeiltasten (2°, 10°) und „Bug“.

`B` nimmt das Fernglas groß über die Karte: ein 16°-Sichtfeld, das wie das Sehrohr des U-Boots mit `←` und `→` statt des Ruders (`Umschalt`: 20°-Schritte) oder per Klick in das Rundumbild darunter geschwenkt wird; das Rundumbild markiert jede Sichtung in ihrer gemessenen Peilung, der Bug liegt in der Mitte. Darunter stehen die Sichtungen, die der Sichtlinie nächste zuerst. Die kartierte Küste steht im Horizontstreifen und im Fernglas auf dem Horizont, so weit der Ausguck Land sieht (höchstens 20 sm, im Dunst verblassend), und das Rundumbild markiert sie an seinem Fuß; die Karte kennt keine Höhen, die Hügel sind mit 25 bis 70 m angenommen. Solange das Fernglas oben ist, neigen `↑`/`↓` es um 2° (`Umschalt`: 10°, von 20° nach unten bis 45° nach oben) statt den Maschinentelegrafen zu bedienen, `Q`/`E` zoomen (16°, 8° oder 4° Feld) und die `Leertaste` schaltet die Stabilisierung, die alle bis auf ein Achtel der Schiffsbewegung herausnimmt; die Zeile unter dem Bild zeigt Neigung und Feld, und die Remote-Crew-Karte hat dieselben Knöpfe für ihren eigenen Browser. Die See folgt dem Wind: gegen die See laufen die Kämme in langen Reihen auf einen zu, mit der See laufen ihre Rücken davon, quer dazu ziehen kurze Kämme seitlich durchs Bild, und das Schiff stampft in Gegen- oder Mitlaufsee und rollt in Dwarssee. Die Wellen füllen die ganze See in Perspektive, klein und dicht bis zur klaren Kimm, zum Auge hin länger und höher, und jede Reihe bewegt sich mit dem Seegang. Die eigene Fahrt zeigt sich im Wasser: in Fahrt strömen die Reihen voraus auf das Auge zu, achteraus von ihm fort und querab vom Bug zum Heck, schneller mit mehr Fahrt; achteraus läuft das Kielwasser als Band aus glatterem, hellerem Wasser mit Schaum zwischen den beiden Armen der Kelvin-Welle bis zum Horizont, und voraus wirft die Bugwelle ihre Gischt in den unteren Bildrand (das Fernglas nach unten neigen, um das weiße Wasser vom Steven abrollen zu sehen). `B` erneut führt zur Karte zurück; das Fernglas ist reine Anzeige und wird nicht gespeichert.

![Fernglas (B) bei Tag](figure:frigate-binoculars-day)

![Fernglas bei Nacht mit Positionslichtern](figure:frigate-binoculars-night)

![Ausguck-Fernglas im Remote-Crew-Browser](figure:web-binoculars-day)

Ein Kontakt wird beim Näherkommen in bis zu drei Stufen gemeldet, jede Stufe einmal:

- **Gesichtet:** nur die Art des Objekts ist klar (Fahrzeug, Luftfahrzeug, kleines Objekt an der Wasseroberfläche).
- **Klasse:** die Silhouette zeigt die Klasse, zum Beispiel Handelsschiff, Kriegsschiff, Flugzeugträger, Fischereifahrzeug, Speedboot, aufgetauchtes U-Boot, Verkehrsflugzeug oder Militärflugzeug.
- **Typ:** auf kurze Entfernung nennt der Ausguck den Typ: Frachter, Tanker, Passagierschiff, Schlepper, Fregatte, Zerstörer, Korvette oder Kampfflugzeug; Kriegsschiffe und Militärflugzeuge zusätzlich mit ihrem Klassennamen. Handelsschiffe und Verkehrsflugzeuge werden über Namen, AIS oder Transponder identifiziert, nicht mit dem Auge; der Ausguck meldet deshalb nie ihren Namen oder den Flugzeugtyp.

Klasse und Typ brauchen eine feiner aufgelöste Silhouette als die Sichtung (Johnson-Kriterien): an einem klaren Tag wird ein Tanker auf etwa 7 sm klassifiziert und eine Fregatte auf etwa 4 sm identifiziert, ein Speedboot erst innerhalb von 3 sm klassifiziert, und nachts ist der Typ nur auf wenige Kabellängen erkennbar. Nebel, Regen und Seegang verkürzen jede Stufe. Der Ausguck meldet außerdem „Land in Sicht“ mit der Peilung der nächsten Küste und eine Torpedolaufbahn mit Banner.

Ein ausgefahrenes Sehrohr oder ein Schnorchelkopf eines getauchten U-Boots zieht eine Schaumfahne, die mit der Fahrt wächst: an einem klaren, ruhigen Tag sieht er die volle Fahne ab 8 kn auf knapp 3 sm, bei 3 kn auf etwa 1,7 sm und einen stehenden Kopf erst auf etwa 1 sm; Seegang und Dunst verkürzen das, nachts sieht er kaum etwas. Gesichtet meldet er einen „Schaumstreifen auf dem Wasser“, auf etwa die halbe Entfernung erkennt er das Sehrohr (mit Banner, als U-Boot in die OPZ). Dasselbe Auge haben die Besatzungen des Helikopters und des Seefernaufklärers (siehe dort).

Die Klasse bleibt erhalten, solange er den Kontakt hält. Sie erscheint in den Tooltips von Karte und OPZ als „Ausguck: …“ und ist nur eine Beobachtung: Sie setzt weder die OPZ-Klassifizierung noch die Zugehörigkeit.

## Autopilot-Route {#bridge-route}

Das Ruder kann einer Route aus bis zu 8 Wegpunkten folgen. Auf der Navigationsseite setzt ein Rechtsklick in die Karte einen Wegpunkt; `W` startet ein Suchmuster ab Position und Kurs des Schiffs (zuerst ein Zickzack mit 3 sm langen Schlägen 45° beiderseits des Kurses, erneut gedrückt ein wachsendes Quadrat mit Schlägen von 1, 1, 2, 2, 3, 3, 4, 4 sm nach rechts drehend, beim dritten Mal wird die Route gelöscht), und `Rücktaste` löscht sie.

Die Karte zeichnet die Route als bernsteinfarbene Linie mit nummerierten Wegpunkten, das Kursfeld zeigt den nächsten mit seinem Abstand. Der Autopilot setzt nur den befohlenen Kurs; die Fahrt bleibt beim Maschinentelegrafen. Ein Wegpunkt gilt innerhalb von 0,3 sm als erreicht, dann steuert das Ruder den nächsten an; nach dem letzten hält das Schiff seinen Kurs. Jeder Ruderbefehl (`←`/`→`, `C`, der Trackball oder ein Kurs aus der Remote Crew) übernimmt und schaltet die Route ab; bei ausgefallener Brücke lässt sich keine Route setzen, und eine laufende wird nicht gesteuert.

Der Autopilot plant nach der Karte: Kartentiefe sowie eingezeichnete Felsen und Wracks gegen die Mindesttiefe des Rumpfs (Tiefgang plus Kielreserve) und weitere 2 m Sicherheit, geprüft alle 0,1 sm entlang jeder Strecke und 0,1 sm zu beiden Seiten. Führt die Strecke eines neuen Wegpunkts oder eines Suchmusters durch Flachwasser oder Land, fügt er Umweg-Punkte ein: zuerst einen Ausweichpunkt quer zur Strecke neben der ersten flachen Stelle (der nächste zuerst, Backbord vor Steuerbord); reicht das nicht, findet eine Wegsuche auf der Karte (ein Raster von höchstens 96 Zellen je Seite über einem Gebiet 4, dann 30, dann 80 sm um die Strecke, begradigt zu so wenigen Wendepunkten, wie freie Strecken es erlauben) den Weg durch ein Fahrwasser oder um eine Bucht oder eine lange Küste. Die Route kann dann bis zu 16 Punkte haben; findet er keinen Weg, meldet der Verlauf, welche Strecke von Hand zu steuern ist.

Während der Fahrt schaut der Autopilot einmal pro Sekunde auf der Strecke voraus (zwei Minuten bei der jetzigen Fahrt, mindestens 0,5 sm): Flachwasser dort bekommt einen Umweg zum aktuellen Wegpunkt, sonst schaltet sich die Route ab und das Schiff dreht auf den Gegenkurs. Er plant nach der Karte, nicht nach dem aktuellen Gezeitenstand. Die Route wird gespeichert.

Die Remote-Crew-Brücke hat eine Karte „Autopilot-Route“: „Wegpunkte auf der Karte setzen“ lässt einen Klick in freie Karte einen Wegpunkt setzen, Knöpfe starten Zickzack oder Quadratsuche oder löschen die Route.

## Tasten {#bridge-keys}

<!-- keys:bridge -->

Auf der Brücke steuert der Trackball das Ruder. `C` (Kurs) und `V` (Fahrt) öffnen die direkte Zahleneingabe, wie `C`/`V`/`D` auf dem U-Boot; die Simulation läuft währenddessen weiter. `Enter` bestätigt, `Esc` bricht ab.

## Maus {#bridge-mouse}

Jede Taste in der Tastenleiste am Fuß der Station lässt sich anklicken; gedrückt halten hält die Taste. Lampen, Seitenreiter und Tastenhinweise im Text sind ebenfalls anklickbar (Kapitel Werkzeuge, Maus). Außerdem:

- Ein Klick auf die Kursscheibe befiehlt diesen Kurs, ein Klick auf die Fahrtscheibe diese Fahrt (Seite 1).
- Eine Ruder- oder Telegrafentaste in der Tastenleiste gedrückt halten hält das Ruder oder schaltet den Telegrafen.
- Ein Rechtsklick auf die Karte setzt einen Wegpunkt des Autopiloten (Seite 1).
- Auf der Ausguckseite richtet ein Klick auf das Rundum-Panorama das Fernglas auf diese Peilung.
- Auf der Karte zoomt das Mausrad, Ziehen verschiebt (und beendet das Folgen mit `K`) und ein Klick heftet eine Kurzinfo an.

## Standardablauf {#bridge-sop}

<!-- sop:bridge -->

Gefechtslage:

1. Torpedo gemeldet: sofort auf 24 kn gehen (nicht FLANK: das Schleppkabel des Nixie reißt über 25 kn), so drehen, dass die Torpedopeilung achteraus oder querab liegt.
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

- Keine Zeitraffung und keine Pause. Der Autopilot steuert nur den Kurs, nie die Fahrt; seine Umwege nutzen nur die Karte (keine aktuelle Gezeit, keine anderen Schiffe); seine Wegsuche sieht die Karte in Zellen von mindestens 0,2 sm, ein Fahrwasser schmaler als etwa eine halbe Meile oder ein Weg weiter als 80 sm neben der Strecke wird daher nicht gefunden.
- Keine automatische Torpedoerkennung: der Alarm beruht nur auf gehörten Intercepts oder der Klassifizierung des Sonarbedieners; ein außerhalb der Suchkopfreichweite leise laufender Torpedo kann unangekündigt eintreffen. Der Ausguck meldet nur eine sichtbare Laufbahn.
- Der Ausguck liest weder Schiffsnamen noch Flagge und meldet keine Signalkörper; Lichter deutet er nur wie oben beschrieben, nie Kurs oder Fahrt daraus. Kein Schiff im Spiel ankert, schleppt, fischt mit Schleppfahrt oder ist manövrierunfähig, daher erscheinen Ankerlicht, Schlepplichter und die Lichter eines manövrierunfähigen Fahrzeugs nie.
