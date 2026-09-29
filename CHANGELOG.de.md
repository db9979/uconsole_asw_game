# Änderungsprotokoll

[English changelog](CHANGELOG.md)

Alle Versionen von U-Jagd, die neueste zuerst. Die [README](README.de.md) zeigt nur die neueste.

## 1.3.71

Version 1.3.71 macht das computergesteuerte U-Boot in den Missionen
Durchbruch, Aufklärung und Geleitzug klüger und gibt der Fregatte mehr
Torpedos. Das U-Boot schleicht jetzt mit 3 kn, solange es Pings hört oder die
Fregatte in der Nähe weiß, umfährt eine geortete Fregatte weiträumig, lauert
dem Geleitzug 2 sm voraus auf, statt ihm nachzulaufen, weicht Pings leise mit
5 kn aus und schießt deutlich eher auf eine geortete Fregatte zurück. Die
Fregatte hat in der Doppeljagd 8 und im Abfang 6 Torpedos. Spielstände bleiben
v31.

## 1.3.70

Version 1.3.70 zeichnet die See im Fernglas des Ausgucks, im Ausguckstreifen, im
Sehrohr und im Handy-Ausguck neu. Statt einer großen Welle an der Kimm füllen die
Wellen jetzt die ganze See in Perspektive: klein und dicht bis zur klaren Kimm,
zum Auge hin länger und höher, jede Reihe bewegt sich mit dem Seegang, läuft je
nach Wind auf einen zu, davon oder seitlich durchs Bild, bei grober See mit
Schaumkronen. Auf der uConsole und im Remote-Crew-Browser; Spielstände bleiben
v31.

## 1.3.69

Version 1.3.69 macht die Versorgung auf See planbar. Der Funkraum kann jetzt
selbst bei der HQ einen Versorger anfordern (R auf der Seite Aufträge, im
Browser Versorger anfordern), sobald Kraftstoff oder ein Vorrat knapp wird,
höchstens alle 20 Minuten nach der letzten Versorgung. Längsseits fließt der
Kraftstoff jetzt die ganze Zeit, und die Vorräte kommen in fünf Ladungen:
Torpedos, ASROC, Wasserbomben, Nixie-Täuschkörper sowie CIWS- und
Geschützmunition, jede Ladung ein Anteil dessen, was noch fehlt, sodass
früheres Abdrehen behält, was schon übergeben ist. Die Seite Aufträge zeigt
Kraftstoff, Torpedos, ASROC und Wasserbomben an Bord. Die HQ bietet einen
Versorger jetzt auch an, wenn ASROC oder Wasserbomben verbraucht sind. VLS-
Zellen werden auf See nicht nachgeladen. Spielstände bleiben v31.

## 1.3.68

Version 1.3.68 macht die Zuordnungsvorschläge der OPZ klüger. Neben Peilung
und Position vergleichen sie jetzt Kurs, Fahrt und die Klassifizierung des
Bedieners: zwei Meldungen mit deutlich verschiedenem Kurs oder verschiedener
Fahrt oder unpassender Klasse werden nicht mehr vorgeschlagen, und gleiche
Klassen setzen ein Paar weiter nach oben. Empfangene AIS-Meldungen erscheinen
jetzt als eigene Meldungen in der OPZ (gemeldete Position, Kurs, Fahrt und
Name) und werden mit Radar- und Ausguckmeldungen desselben Schiffs
vorgeschlagen. Eine Fusion übernimmt jetzt Kurs und Fahrt ihrer Mitglieder.
Spielstände sind jetzt v31 (AIS-Meldungen behalten ihre gemeldete Position);
v30-Stände laden nicht mehr.

## 1.3.67

Version 1.3.67 lässt die Führung dem besetzten U-Boot während der Mission
Befehle geben. Unter dem Mast nimmt die VLF-Rahmenantenne den Rundspruch jetzt
bis 25 m Tiefe auf (langsamer als mit Mast und nur Empfang). Ab dem zweiten
Rundspruch kann ein Rundspruch einen Befehl enthalten: ein Seegebiet in tiefem
Wasser anlaufen, eine Lagemeldung absetzen oder Funkstille halten, jeweils mit
Frist. Funkraumseite, Karte und die Browserkarte Funkraum zeigen den offenen
Befehl und wie viele ausgeführt wurden; ein verpasster Rundspruch ist ein
verpasster Befehl. Spielstände sind jetzt v30 (sie behalten die Befehle);
v29-Stände laden nicht mehr.

## 1.3.66

Version 1.3.66 gibt dem Helikopter ein Seeraumradar. Solange er mit
eingeholtem Tauchsonar fliegt, sucht es aus 150 m: Schiffe bis 40 sm,
aufgetauchte U-Boote sowie ausgefahrene Schnorchel oder Sehrohre innerhalb
seines Radarhorizonts, einen Mast bei ruhiger See auf etwa 10 sm und bei
rauerer See nur auf wenige Meilen. Jeder Kontakt erreicht die OPZ als RADAR-
HELO-Track; die Helikopterseite und die Remote-Crew-Ansicht zeigen, ob das
Radar sucht. Spielstände bleiben v29.

## 1.3.65

Version 1.3.65 gibt der Fregatte zwei weitere U-Jagd-Waffen in der
Waffenzentrale. `A` startet eines von vier ASROC: Die Rakete fliegt zur
beobachteten Position des zugewiesenen U-Boots (1 bis 10 sm, aktuelle
Entfernung nötig) und setzt dort einen Leichttorpedo ab. `Z` wirft ein Muster
aus fünf Wasserbomben über das Heck (20 an Bord, 45 s Nachladen, mindestens 10
kn); sie sinken auf die voreingestellte Tiefe und sind bis etwa 25 m tödlich.
Beide nutzen die Zielprüfungen des Torpedos und stehen auch auf der
Waffenseite der Remote Crew. Spielstände sind jetzt v29 (sie behalten sinkende
Wasserbomben und die Bestände); v28-Stände laden nicht mehr.
## 1.3.64

Version 1.3.64 räumt die uConsole-Bildschirme auf. Alle Texte nutzen jetzt
die mitgelieferte Schrift JetBrains Mono, damit auf keinem System mehr Zeilen
abgeschnitten werden, und der Zeilenabstand folgt der Schrift. Alle
Zustandsbalken haben einen gemeinsamen Stil mit Viertelmarken und
Beschriftung, der Maschinentelegraph hebt die nächste Stufe hervor und warnt,
wenn eine Direktfahrt zwischen zwei Stufen liegt, und die Brücke bekommt Kurs-,
Ruder- und Fahrtanzeige. U-Boot-Reiter, Kartenskala, Wassersäule, ESM-Rose und
Laufband überlappen nicht mehr; OPZ, ELOKA und Helikopter bekommen die Rahmen
des Startbilds und eine Tastenzeile, und die letzten englischen Reste in
deutschen Menüs sind übersetzt. Spielstände bleiben v28.

## 1.3.63

Version 1.3.63 macht den Kopplungscode leichter einzugeben, auf der
Crew-Seite und am Handy-Ausguck. Der Code darf so getippt werden, wie `F9` ihn
zeigt, mit Leerzeichen, in Kleinbuchstaben oder mit verwechselbaren Zeichen
wie O statt 0, l statt 1 oder S statt 5, und wird trotzdem richtig gelesen.
„Falscher Kopplungscode“ erscheint nur noch, wenn der Code wirklich falsch ist,
und nennt den Code, den das Spiel bekommen hat; lehnt das Spiel die Adresse selbst ab (ein
Lesezeichen oder ein anderer Name für den Host), sagt die Seite, dass sie über
den QR-Code oder die Adresse aus `F9` zu öffnen ist. Die Kopplungshilfe
behauptet nicht mehr, der Code laufe nach fünf Minuten ab: er bleibt, solange
das Spiel läuft, und wechselt nach fünf Fehlversuchen. Spielstände bleiben v28.

## 1.3.62

Version 1.3.62 bringt dem Autopiloten die Seekarte bei. Führt die Strecke
eines Wegpunkts oder Suchmusters durch Flachwasser oder Land, fügt er Umweg-
Punkte ein oder meldet im Verlauf, welche Strecke von Hand zu steuern ist.
Während der Fahrt schaut er einmal pro Sekunde zwei Minuten voraus;
Flachwasser dort bekommt einen Umweg zum aktuellen Wegpunkt, sonst schaltet
sich die Route ab und das Schiff dreht auf den Gegenkurs. Er plant mit
Kartentiefe, Felsen und Wracks gegen Tiefgang plus Kielreserve und 2 m
Sicherheit. Spielstände bleiben v28; eine Route kann mit Umwegen jetzt bis zu
16 Punkte haben.

## 1.3.61

Version 1.3.61 macht den Einheiteneditor wirksam. Dort gespeicherte Profile
lassen sich jetzt wie eingebaute Einheiten in eigenen Missionen platzieren und
wirken dort: Name, Fahrtbereich, Tiefe, Torpedozahl, Verhalten, Akustik und
Häufigkeit. Ein eigenes U-Boot übernimmt Sensoren, Rohre, Täuschkörper und
seine Batterie-, Diesel- oder AIP-Anlage vom eingebauten Boot seines Antriebs.
Eine Mission kann außerdem einen feindlichen Torpedo platzieren, der beim
Start schon auf seinem Kurs läuft, zum Üben des Ausweichens. Solche Missionen
lassen sich normal speichern und laden (der Katalog-Schnappschuss des
Spielstands enthält die eigenen Profile); eingebaute Szenarien verwenden sie
nie. Spielstände bleiben v28.

## 1.3.60

Version 1.3.60 macht beide Seiten gewinnbar. Der Annäherungszünder eines
Torpedos zündet jetzt bei der größten Annäherung, die seine Bahn voraussagt,
statt schon beim Eintritt in seinen Radius; ein zielsuchender Torpedo trifft
dadurch schwer. Vorher zündete er 250 bis 370 m zu früh und richtete nur 12 bis
18 % Schaden an. Feindtorpedos laufen 40 kn über 20 sm und sind schneller als
die Fregatte, und ein KI-U-Boot greift eine geortete Fregatte innerhalb 10 sm
auch bei leiser Fahrt an. Die U-Boot-Missionen passen in ihre Zeit: das Ziel des
Durchbruchs liegt 5 sm hinter der Fregatte, die Aufklärung hat 3 Stunden, und
der Geleitzug läuft 8 kn, das U-Boot startet an seinem Bug etwa 10 sm voraus. Spielstände
bleiben v28.

## 1.3.59

Version 1.3.59 räumt auf, ohne das Spiel zu ändern. Die beiden größten Module
sind entlang ihrer Nähte geteilt: Radar-, Luft-, ECM-, ESM- und Funklage mit
Flugkörpern und Angreifern ziehen aus dem Simulationsschritt in ein eigenes
Modul, und die Aktionen der Remote-Crew-Stationen ziehen aus der Brücke in ein
eigenes Modul; der Code wird unverändert verschoben, und die
Aktualisierungsreihenfolge bleibt eingefroren. Der Changelog-Eintrag zu 1.3.43
beschreibt jetzt, was diese Version tatsächlich behoben hat. Spielstände
bleiben v28.

## 1.3.58

Version 1.3.58 begrüßt den ersten Start mit einer Auswahl. Gibt es noch keine
Einstellungsdatei, folgt auf das Startbild eine Seite mit der Frage, was du
spielen möchtest: Fregatte öffnet das Training mit der ersten Fregatten-
Lektion, U-Boot öffnet die erste U-Boot-Lektion und stellt die uConsole auf
die U-Boot-Seite, Remote Crew öffnet die F9-Seite für Browser-Crews, und
Hauptmenü (oder `Esc`) führt direkt ins Menü. Die Wahl wird gemerkt, die Seite
erscheint also nur einmal. Spielstände bleiben v28.

## 1.3.57

Version 1.3.57 lässt die U-Boot-Besatzung mehr Meldungen sprechen. Neben
Kontakten, Ortungsimpulsen und Torpedowarnungen meldet das Boot jetzt den
eigenen Torpedo los, Detonationen nah oder fern mit Peilung, Sinkgeräusche,
die sein Sonar hören kann, einen aufgenommenen Rundspruch der Führung (und ob
er eine Feindlagemeldung zur Fregatte enthält), jede Klasse, die das Sehrohr
sichtet, mit Peilung, das Annähern an die und Unterschreiten der Testtiefe
beim Tauchen, einen Treffer, Schäden am Druckkörper und das Missionsergebnis,
auf Deutsch oder Englisch. Jede gesprochene Meldung stammt aus einer Zeile im
eigenen Bordbuch, die Besatzung hört also nie mehr, als ihr gemeldet wurde.
Spielstände bleiben v28.

## 1.3.56

Version 1.3.56 gibt der OPZ Zuordnungsvorschläge. Melden zwei eigene Sensoren
des Schiffs (Sonar, Radar, ESM, Ausguck) einen Kontakt in derselben Peilung
innerhalb ihrer Unsicherheit (und, wo beide eine Position haben, nah
beieinander), bietet die OPZ das Paar zur Fusion an: auf der uConsole stehen
bis zu zwei Vorschläge in der Seitenleiste von Seite 1, `U` fusioniert den
obersten und `Umschalt+U` verwirft ihn; die Remote-Crew-OPZ listet bis zu vier
mit Knöpfen zum Fusionieren und Verwerfen. Verglichen werden nur
veröffentlichte Meldungen, die höchstens 30 s alt sind; ohne den Bediener wird
nichts fusioniert. Spielstände bleiben v28.

## 1.3.55

Version 1.3.55 gibt der Fregatte eine Autopilot-Route. Auf der Brücke setzt
ein Rechtsklick in die Karte einen Wegpunkt (bis zu 8), `W` startet ein
Suchmuster ab Position und Kurs des Schiffs (Zickzack mit 3 sm langen
Schlägen, dann wachsendes Quadrat), und `Rücktaste` löscht die Route. Das
Ruder steuert die Wegpunkte nacheinander an, zählt einen innerhalb von 0,3 sm
als erreicht und hält nach dem letzten den Kurs; die Fahrt bleibt beim
Maschinentelegrafen, und jeder Ruderbefehl übernimmt. Die Karte zeigt die
Route mit nummerierten Wegpunkten, und die Remote-Crew-Brücke hat eine Karte
„Autopilot-Route“ mit denselben Mustern und einem Kartenmodus zum Setzen von
Wegpunkten. Spielstände sind jetzt v28 (sie behalten die Route); v27-Stände
laden nicht mehr.

## 1.3.54

Version 1.3.54 lässt die KI-Jäger das ESM der Fregatte nutzen. Hat die
Fregatte keinen Standort des U-Boots, gibt jetzt ein ESM-Intercept eines
Mastradars die Suchlinie: Die Bibliothek muss unter ihren drei besten Treffern
ein U-Boot-Radar führen, und kein Schiff, das die Fregatte per Radar oder AIS
verfolgt, darf innerhalb 10° der Peilung stehen. Die Peilung konkurriert nach
Alter mit den HF/DF-Peilungen und bleibt 5 Minuten ein Datum; ein U-Boot, das
auf Sehrohrtiefe sein Radar benutzt, zieht so Fregatte, Hubschrauber und
Seefernaufklärer auf diese Peilung. Spielstände bleiben v27.

## 1.3.53

Version 1.3.53 bringt eine Absicherung gegen eingefrorene Remote-Crew-Browser.
Ein neuer Test spielt zwei belebte Missionen (die Fregatte mit Autocrew auf
allen Stationen gegen das KI-U-Boot und ein besetztes U-Boot mit gefülltem
Funkraum, Bedrohungsbild und HQ-Aufträgen), veröffentlicht Zustand und Karte
jeder Station beider Einheiten und prüft sie alle in Node mit den Prüfroutinen
des Browsers selbst. Ein Feld, das der Browser ablehnen würde, wie in 1.3.44,
lässt jetzt die Tests vor einem Release scheitern. Am Spiel ändert sich
nichts. Spielstände bleiben v27.

## 1.3.52

Version 1.3.52 lässt Remote-Crew-Browser einem Update des Hosts selbst folgen.
Der Host nennt seine Version jetzt in jeder Antwort und in der Seite, die er
ausliefert; eine Browserseite, die noch von vor dem Update offen ist, lädt
sich einmal selbst neu und läuft so immer mit dem Web-Client, der zum Host
passt, statt an Daten hängen zu bleiben, die sie nicht lesen kann. Spielstände
bleiben v27.

## 1.3.51

Version 1.3.51 bringt einen Autosave. Eine laufende Mission wird alle 5
Minuten und beim Beenden oder Verlassen ins Hauptmenü nach
`~/.u-jagd/autosave.json` gespeichert, neben den fünf Plätzen. Das Hauptmenü
beginnt dann mit „Einsatz fortsetzen“, das sie exakt weiterführt; nach einem
Absturz ist es der letzte 5-Minuten-Stand. Die Datei wird im Hintergrund
geschrieben, damit die uConsole nicht ruckelt. Eine beendete und jede neue
Mission löschen den Autosave. Spielstände bleiben v27.

## 1.3.50

Version 1.3.50 repariert die Remote-Crew-Kopplung im LAN. Ein frisch
gekoppelter Browser begrüßt nicht mehr mit „Deine Station wurde widerrufen oder
freigegeben“, als wäre die Kopplung gescheitert, sondern mit der Aufforderung,
eine freie Station zu nehmen. Die Crew-Seite sagt jetzt, wenn sie in einem
Browser läuft, der nicht Chrome oder Chromium (auch Edge) ist: Firefox und
Safari zeigen über dem Kopplungscode einen Hinweis, und eine Seite, die dort
nicht starten kann, sagt das, statt endlos zu laden. Der Navigationsvorschlag
der Brücke nimmt die vollen 31 kn der Fregatte an; Spielstände bleiben v27.

## 1.3.49

Version 1.3.49 zeigt Flugzeuge im Fernglas des Ausgucks, im Ausguckstreifen, im
Sehrohr und im Handy-Ausguck in ihrer wahren Höhe: Jedes steht in seinem
Höhenwinkel über der Kimm, berechnet aus Flughöhe und Entfernung abzüglich der
Erdkrümmung, sodass man ein hohes, nahes Flugzeug erst mit nach oben geneigter
Optik sieht. Flugzeuge hängen jetzt hinter den Wolken im ruhigen Himmel, statt
mit den Schiffen im Seegang zu schwanken. Auf der uConsole und im
Remote-Crew-Browser; Spielstände bleiben v27.

## 1.3.48

Version 1.3.48 erneuert die Bilder auf der Projektseite. Sie stehen jetzt in
einer Galerie und zeigen neu das Fernglas des Ausgucks auf der Fregatte und das
Sehrohr des U-Boots bei Tag und bei Nacht, auf der uConsole und im Browser, mit
einem Kriegsschiff und Frachtern im Okular und den Positionslichtern der
Frachter im Dunkeln; alle Stationsbilder zeigen den neuen türkisen Look. Die
Screenshot-Werkzeuge erzeugen diese Okularbilder selbst
(`tools/sight_capture.py`). Spielstände bleiben v27.

## 1.3.47

Version 1.3.47 schickt ein Handy auf Wache. `F9` zeigt einen zweiten QR-Code,
Handy-Ausguck: scannen, das eigene Zertifikat des Spiels einmal bestätigen, den
Kopplungscode eintippen, und das Handy wird zum Ausguck auf der Brücke der
Fregatte oder zum Sehrohr des besetzten U-Boots. Das Handy wie ein Fernglas
drehen (Gyroskop) oder wischen, zoomen und melden, was zu sehen ist, per
Sprache („Schiff Peilung 040, Entfernung 5 Meilen“) oder durch Antippen. Die
Brücke hört nur, was der Ausguck dort wirklich hat; eine Meldung von nichts wird
abgelehnt. Solange ein Handy Wache hält, schweigt der automatische Ausguck, und
die Crew-Browser sprechen jede bestätigte Meldung. Am Sehrohr dreht das Handy
das Sehrohr und nimmt Stadimeter-Entfernungen. Der Listener liefert die Seite
über HTTPS auf dem nächsten Port (selbst erzeugtes Zertifikat), weil Handys
Gyroskop und Mikrofon nur einer sicheren Seite freigeben; Spielstände bleiben
v27.

## 1.3.46

Version 1.3.46 zeichnet das kleine Wetterbild der Brücke im Stil des Startbilds:
Es blickt jetzt in den Wind, mit dem Himmel der Stunde (Sonne, Mond und Sterne),
den Wolken, Regen, Schnee oder Nebel und der auf das Auge zulaufenden See, dazu
eine türkise Windrose in der Ecke und die Eckwinkel der anderen Sichten. Auf der
uConsole und im Remote-Crew-Browser; Spielstände bleiben v27.

## 1.3.45

Version 1.3.45 hält den Himmel im Sehrohr und im Fernglas des Ausgucks ruhig:
Wolken, Sterne, Sonne und Mond bleiben stehen, während See und Horizont mit dem
Seegang schwanken. Von der Dämmerung bis zum Morgen und bei schlechter Sicht
führen neutrale Schiffe ihre Positionslichter nach den
Kollisionsverhütungsregeln: weiße Topplichter, das rote oder grüne Seitenlicht
der Seite, die man sieht, von achtern das weiße Hecklicht, jedes in seiner
Tragweite, und die Rundumlichter von Fahrzeugen bei der Arbeit (Trawler, Lotse,
Vermesser und Kabelleger, Minenräumer), zivile Flugzeuge ihre Flügelspitzen-,
Heck- und blitzenden Kollisionswarnlichter; der Bug zeigt dorthin, wohin die Lichter weisen, und ein
beleuchtetes Schiff wird im Dunkeln an seinen Lichtern gesichtet.
Kriegsschiffe und Militärflugzeuge bleiben dunkel. Die See folgt dem Wind:
gegen die See laufen die Kämme auf einen zu, mit der See davon, quer dazu
seitlich, und das Schiff stampft in Gegensee und rollt in Dwarssee. Fernglas und
Sehrohr lassen sich jetzt nach oben und unten neigen, zoomen (Fernglas 16°, 8°,
4°; Sehrohr kleine und große Vergrößerung) und haben eine
Horizontstabilisierung. Auf der uConsole und im Browser; Spielstände bleiben v27.

## 1.3.44

Version 1.3.44 behebt Remote-Crew-Browser, die mit „Host sendet Daten, die
dieser Browser nicht lesen kann“ einfroren. Vier Listen nannten die Art einer
Zeile mit einem Feld, das der Browser in jedem Stationszustand ablehnt: das
Funklog des U-Boots, seine Bedrohungs-Peilungen und sein Ausweichbefehl sowie
die HQ-Aufträge im Funkraum der Fregatte. Sobald die erste Sendung mitgeschrieben,
ein Ping oder Torpedo gehört oder ein Auftrag angeboten war, stand das
Lagebild still und Aktionen waren gesperrt. Diese Zeilen senden das Feld jetzt
als `type`; ein neuer Test findet solche Felder auch ohne Chromium. Nach dem
Update des Hosts die Browserseite einmal neu laden, damit sie den neuen
Web-Client lädt. Spielstände bleiben v27.

## 1.3.43

Version 1.3.43 lässt auf GitHub nur noch das neueste Release stehen: Nach dem
Veröffentlichen einer neuen Version löscht der Windows-Workflow alle älteren
Releases (ihre Git-Tags bleiben). Windows-Starter und uConsole-Updater lesen
nur das neueste Release. Spielstände bleiben v27.

## 1.3.42

Version 1.3.42 lässt auf GitHub nur noch das neueste Release stehen: Nach dem
Veröffentlichen einer neuen Version löscht der Windows-Workflow alle älteren
Releases (ihre Git-Tags bleiben). Windows-Starter und uConsole-Updater lesen
nur das neueste Release. Spielstände bleiben v27.

## 1.3.41

Version 1.3.41 bringt die volle obere Leiste auf der uConsole zurück: Die
Fregatte zeigt wieder Station, Mission, Uhrzeit, Fahrt und Kurs, das besetzte
U-Boot Mission, Uhrzeit, Fahrt, Kurs und Tiefe, jetzt kompakt durch „·“
getrennt. Spielstände bleiben v27.

## 1.3.40

Version 1.3.40 bringt eine Fehlermeldung. „Fehler melden“ im Hauptmenü
schreibt `~/.u-jagd/bug-report.txt` mit Version, Plattform und den neuesten
Zeilen des Absturz-Logs (Benutzername aus Pfaden entfernt) und zeigt einen
QR-Code, der am Handy ein vorausgefülltes GitHub-Issue öffnet; `Enter` öffnet
es mit Log im Browser, wo das Gerät einen hat. Nach einem abgestürzten Start
bietet das Hauptmenü den Punkt an. Der Windows-Starter und das
Einstellungsmenü im Browser verlinken dasselbe Formular, und das Absturz-Log
hält jetzt auch jeden Missionsstart fest. Gesendet wird erst, wenn Sie das
Issue mit Ihrem eigenen GitHub-Konto abschicken. Spielstände bleiben v27.

## 1.3.39

Version 1.3.39 gibt dem Sehrohr, dem Fernglas des Ausgucks und allen Stationen
den Stil des Startbilds. Die Okulare zeigen Tag, Dämmerung und Nacht mit
Sternen, dem Mond in seiner Phase und seinem Glitzern auf dem Wasser, Wolken,
Regen, Schnee und Nebel nach dem Wetter, und die Schiffe in Stahl mit heller
Kante, nachts mit beleuchteten Fenstern, Bugwelle und Kielwasser. Die
Remote-Crew-Brücke bekommt das Fernglas des Ausgucks als Karte und das
Browser-Sehrohr dasselbe Bild und dieselben Schiffsformen. Die Stationen auf
der uConsole und im Browser tragen das Türkis und Nachtblau des Startbilds mit
Eckwinkeln an den Feldern; die Karte behält ihre NATO-Symbole, der
Kontrastmodus bleibt unverändert. Spielstände bleiben v27.

## 1.3.38

Version 1.3.38 lässt die Karten auf der uConsole viel weiter hineinzoomen.
`Q`/`E` springen jetzt auf Brücke, Waffen, Helikopter und der U-Boot-Karte in
festen Stufen durch die Kartenhöhen 500, 250, 100, 50, 25, 10, 5, 2, 1 und
0,5 sm, das Mausrad zoomt stufenlos bis 0,5 sm; die OPZ-Karte geht bis 0,25 sm
Radius. Das Gitter wird beim Hineinzoomen feiner (bis 0,1 sm, mit
Dezimalbeschriftung), der Maßstab zeigt Bruchteile, und Küsten und Radarringe
werden beschnitten, damit starker Zoom schnell bleibt. Spielstände bleiben v27.

## 1.3.37

Version 1.3.37 behebt einen Absturz, der das Spiel schloss, sobald ein
Torpedo der Fregatte oder der KI im Wasser war, während das
Simulationsprotokoll (Optionen, Simulationsprotokoll) aufzeichnete: Der Zustandsschnappschuss
des Protokolls las eine Torpedonummer, die der Torpedo nicht hat. Das in 1.3.34
eingebaute Absturzprotokoll zeigte die Ursache. Spielstände bleiben v27.

## 1.3.36

Version 1.3.36 behebt Sonar-Ton auf der uConsole, der verstummen konnte, bis
man den Ton in den Optionen aus- und wieder einschaltete. Ein seltenes
Wettrennen im pygame-Mixer konnte den Sonarkanal still stehen lassen, während
sein nächster Block für immer in der Warteschlange hing, und die
Sonar-Wiedergabe wartete dauerhaft auf diesen Platz. Die Wiedergabe spielt
einen solchen hängenden Block jetzt selbst ab und macht weiter, und ein
beendeter Sonar-Audio-Thread startet mit dem nächsten Block neu.
`audio_debug.log` zählt beides (`queue_stranded`, `worker_restarts`).
Spielstände bleiben v27.

## 1.3.35

Version 1.3.35 bringt weniger Text auf die uConsole-Bildschirme. Die obere
Leiste nennt nur Station und Uhrzeit, der Kartenkopf nur den Maßstab. Das Sonar
verliert die Statusfelder im Kopf und die Legendenzeilen und behält eine Zeile
mit vier Haupttasten (der Rest steht in F1); ein Schlepp- oder Tiefensonar
zeigt seinen Zustand nur, solange es fährt oder nicht bereit ist. Die
Bedrohungsbox des U-Boots erscheint nur bei frischer Bedrohung, danach markiert
ein gelbes Dreieck neben der Uhrzeit anstehende Warnungen. Kurse stehen in
ganzen Grad mit °, der Drehkreis nur während einer Drehung. Der TMA-Kopf
überlappt nicht mehr, und Waffen-Reiter, Rohrzeile und Alarmzeilen des U-Boots
werden nicht mehr abgeschnitten. Spielstände bleiben v27.

## 1.3.34

Version 1.3.34 schreibt ein Absturzprotokoll: Jeder Spielstart hängt an
`~/.u-jagd/crash.log` eine Start- und eine Endzeile an, und endet das Spiel
durch einen Fehler, steht dort der Traceback, nach einem harten Absturz
(Speicherzugriffsfehler in SDL oder Audio, `SIGTERM`) die Stapel aller Threads.
Eine Startzeile ohne Endzeile heißt, das Spiel wurde von außen beendet, meist
vom Kernel bei Speichermangel. Die Datei bleibt unter 256 KiB. Spielstände
bleiben v26.

## 1.3.33

Version 1.3.33 lässt das ESM des besetzten U-Boots die Umlaufzeit jedes Radars
messen, die Zeit zwischen den Treffern seiner Hauptkeule: ein Suchradar zeigt
„dreht“ mit seiner Umlaufzeit (etwa 2,5 s für Navigations- und Seeraumradar, 5
s für Luftraumradar), ein Verfolgungs- oder Feuerleitradar „dauernd“. Eine
Dauerbeleuchtung des Mastes ist immer eine Mastwarnung und steht im Log; die
Seite Mast & ESM am uConsole und der Browser zeigen die Messung. Spielstände
sind jetzt v27.

## 1.3.32

Version 1.3.32 bringt Richtungshören: Mit Stereoton kommen Detonationen,
zurückkehrende Echos und das aktive Ping einer anderen Plattform aus der
Peilung, aus der sie gehört wurden, links für Backbord und rechts für
Steuerbord vom Bug der Fregatte oder des besetzten U-Boots aus, am uConsole
und im Remote-Crew-Browser. Die Fregatte spielt jetzt auch das Ping eines
U-Boots selbst, und das besetzte U-Boot hört das Ping eines Jägers am Rumpf.

## 1.3.31

Version 1.3.31 gibt dem besetzten U-Boot echte Torpedorohre: Die Torpedogasten
laden jedes leere Rohr aus den Reserven (`M` an der Station Waffen oder Laden
im Browser), und ein geladenes Rohr muss vor dem Schuss geflutet werden, was
20 s dauert und hörbar ist (`Shift+M` oder Fluten). Jedes U-Boot führt jetzt
noch einmal so viele Reservetorpedos wie Rohre, nachgeladen in 2 bis 4
Minuten; die U-Boote der KI laden und fluten weiter selbst. Spielstände sind
jetzt v26.

## 1.3.30

Version 1.3.30 lässt die **Fregatte die U-Boot-Missionen gegen die KI
spielen**: Ein unbesetztes Missions-U-Boot verfolgt jetzt seinen Auftrag,
statt zu patrouillieren. Es läuft unter der Sprungschicht zum
Durchbruchsziel, folgt den Feindmeldungen der Führung und geht zum Sichten
und Melden der Fregatte auf Sehrohrtiefe, und beim Geleitzugangriff läuft es
dem Geleitzug voraus und torpediert seine Handelsschiffe einzeln.
Spielstände bleiben v25.

## 1.3.29

Version 1.3.29 benennt das U-Boot einheitlich: Alle Anzeigen, die
Web-Clients, Hilfe und Handbuch sagen jetzt **U-Boot** (englisch
**submarine**), wo bisher nur „Boot“ stand, etwa **U-Boot-Kampagne** und
U-Boot-Missionen. Spielstände bleiben v25.

## 1.3.28

Version 1.3.28 macht die **KI-Jäger klüger**: Die OPZ markiert den bloßen
Radarpunkt eines ausgefahrenen Masts oder Schnorchels, und eine Mastspur,
eine HF/DF-Kreuzpeilung oder eine U-Boot-Datummeldung der Führung wird jetzt
zum Datum der Jagd. Ein frischer Fix der eigenen Sensoren geht per Datenlink
an ein befreundetes KI-Kriegsschiff mit ASROC in Reichweite. Spielstände sind
jetzt v25 (Radarpunkte und Markierungen).

## 1.3.27

Version 1.3.27 sortiert die **ESM-Bibliothek des Boots nach Passung**: die
Emitter, deren veröffentlichte Bereiche eine Messung enthalten, stehen mit der
besten Passung zuerst (Frequenz und PRF nahe der Bereichsmitte, dieselbe
Modulation), jeder mit der Stufe gut, mittel oder schwach am uConsole und im
Browser, sodass ein gut passendes Radar wie das des Hubschraubers nicht mehr
aus der Liste fällt. Spielstände bleiben v24.

## 1.3.26

Version 1.3.26 überspringt auf der uConsole die Update-Suche, wenn kein
Internet da ist: Ein Verbindungstest zu GitHub entscheidet in höchstens 2,5
Sekunden, danach startet das Spiel sofort, statt auf Zeitüberschreitungen zu
warten. Hängende Git-Abrufe brechen nach spätestens 60 Sekunden ab. Spielstände
bleiben v23.

## 1.3.25

Version 1.3.25 räumt die Dokumentation auf. Das Spiel bleibt unverändert, Spielstände
bleiben v24.

## 1.3.24

Version 1.3.24 bringt **Atmosphäre ins besetzte Boot**: der Druckkörper knarzt in
der Tiefe und kracht, wenn er versagt, Detonationen im Wasser sind dicht beim
Boot oder in der Ferne zu hören und stehen mit Peilung im Log, und bei
**Schleichfahrt** schalten die Boot-Bildschirme am uConsole und im Browser auf
gedimmtes Rotlicht. Die Browser des Boots spielen jetzt dessen eigene Töne, und
der Alarmton einer Rettungsaufgabe stört den Browser nicht mehr. Spielstände
bleiben v24.

## 1.3.23

Version 1.3.23 gibt allen Menüs und Dialogen das Aussehen des Startbildschirms:
Hilfe, Optionen, Speichern/Laden, Beenden, Nationen, Remote-Crew-Verwaltung
(`F9`) und das Missionsende zeigen jetzt die nächtliche Jagd hinter einem
durchscheinenden Konsolen-Panel mit Phosphor-Eckwinkeln und leuchtendem Titel;
die Mission läuft dahinter weiter. Bei hohem Kontrast bleiben die Panels
deckend. Die Browser-Dialoge nutzen denselben Nachthimmel und Winkelrahmen.
Spielstände bleiben v24.

## 1.3.22

Version 1.3.22 macht die Remote-Crew-Datenströme stabiler. Ein Browser, der
seinen Sonar-Audio- oder Sonar-Anzeigestrom neu verbindet, übernimmt jetzt
sofort seinen eigenen bisherigen Strom, statt abgewiesen zu werden, solange der
Host die alte Verbindung noch nicht als beendet erkannt hat. Der Web-Client
fragt bei eingeschaltetem Push nicht mehr zu jedem gepushten Zustand
zusätzlich den Zustand ab. Die Browsertests für Live-Audio und den
Zustands-Push laufen jetzt in Echtzeit neben dem Host. Spielstände bleiben
v23.

## 1.3.21

Version 1.3.21 lässt das besetzte Boot **unter seine Testtiefe** tauchen, bis zur
Zerstörungstiefe (1,5-fache Testtiefe), mit wachsendem Risiko: gebrochene
Bolzen, versagende Wellen- oder Ventildichtungen und, tiefer, ein Riss im
Druckkörper fluten Abteilungen und erhöhen den Schaden, je tiefer, desto
häufiger; in Zerstörungstiefe bricht der Druckkörper zusammen. Die
Tiefenleitern markieren die Zerstörungstiefe, und ein roter Alarm zeigt die
Fahrt unter der Testtiefe. Spielstände bleiben v24.

## 1.3.20

Version 1.3.20 bringt den **Angriffsrechner am Sehrohr** des Boots: Jede
Stadimeter-Messung ist eine Marke, und zwei oder mehr Marken im Abstand von
einer Minute ergeben Kurs und Fahrt des Ziels, den Vorhaltewinkel und die
Laufzeit des Torpedos unter dem Sehrohr (Browser: Spalte Lösung).
`Strg+Enter` auf der Sehrohrseite (Browser: Schuss nach Lösung) schießt auf
den Abfangkurs; ein Schuss auf einen markierten Sonarkontakt nutzt die Lösung
ebenfalls. Spielstände wechseln auf **v24** (die Marken werden gespeichert);
v23-Spielstände werden nicht mehr geladen.

## 1.3.19

Version 1.3.19 macht den Start auf der uConsole sofort sichtbar: Ein kleines
Startfenster zeigt, ob der Starter nach einem Update sucht, es lädt oder
installiert, und schließt sich, sobald das Spiel erscheint. Ein zweiter Start,
während U-Jagd startet oder läuft, öffnet das Spiel nicht mehr doppelt, sondern
meldet „U-Jagd läuft bereits.“. Spielstände bleiben v23.

## 1.3.18

Version 1.3.18 bringt ein **A4-Werbeplakat** auf Deutsch und Englisch (PNG mit
300 dpi und PDF) in `docs/poster/`: die Szene des Startbildschirms, eine kurze
Beschreibung der uConsole- und Windows-Version, vier Screenshots und QR-Codes
zum Download und zur Unterstützerseite. `tools/build_poster.py` rendert es aus
der aktuellen Szene und den Screenshots neu. Das Spiel selbst ist unverändert;
Spielstände bleiben v23.

## 1.3.17

Version 1.3.17 behebt das Selbst-Update des Windows-Programms: Nach dem
Austausch startete die neue `U-Jagd-Windows.exe` nicht ("Failed to load
Python DLL"), weil sie das bereits gelöschte Entpackverzeichnis des alten
Prozesses erbte. Der Neustart entpackt jetzt frisch. Das Starterfenster zeigt
außerdem den Link "Spendier mir einen Kaffee". Spielstände bleiben v23.

## 1.3.16

Version 1.3.16 bringt die **Bootskampagne**: fünf verkettete Bootsmissionen in
einem Seegebiet (Aufklärung, Durchbruch, Geleitzugangriff, Durchbruch,
Geleitzugangriff), gewählt mit `Tab` im Kampagnenbildschirm. Das Boot nimmt
Torpedos, Rumpfschaden und Ansehen bei der U-Boot-Führung von Mission zu
Mission mit; im Stützpunkt gibt es volle Überholung oder schnelles Auslaufen.
Gespeichert in `~/.u-jagd/boat_campaign.json`; Spielstände bleiben v23.

## 1.3.15

Version 1.3.15 bringt Bootsmission 7, **Geleitzugangriff**: Die Fregatte
geleitet vier Handelsschiffe, und das U-Boot muss zwei davon versenken. Nur
die Torpedos des besetzten Boots treffen ein Handelsschiff; die KI-Fregatte
hält ihre Position vor dem Geleitzug und verfolgt Kontakte nur in seiner Nähe.
Der Auftrag des Boots zählt die versenkten Handelsschiffe. Spielstände bleiben v23.

## 1.3.14

Version 1.3.14 bringt **Bootsmissionen**: Szenario 5 *Durchbruch* (das U-Boot
muss ein Zielgebiet hinter der Patrouillenposition der Fregatte erreichen)
und Szenario 6 *Aufklärung* (es muss die Fregatte durch das Sehrohr sichten
und eine Lagemeldung funken, während sie in Sicht ist). Die Fregatte muss das
verhindern. Der Auftrag des Boots steht über seiner Karte und in den
Bootsstationen im Browser; das Ziel ist auf der Bootskarte markiert.
Spielstände bleiben v23.

## 1.3.13

Version 1.3.13 rendert die uConsole-Screenshots nach drei simulierten
Minuten statt nach sechs Sekunden, damit Wasserfälle, Plots und Kontaktlisten
gefüllt sind, und zeigt den Missionseditor mit der mitgelieferten
Beispielmission (Bibliothek und Seed-Vorschau des Sektors) statt einer leeren
Bibliothek. Die README verlinkt jetzt auch Menü- und Editoransichten.
Spielstände bleiben v23.

## 1.3.12

Version 1.3.12 erneuert die Screenshots in der README aus dem aktuellen
Spiel (uConsole mit 1280 x 720, einschließlich der Stationen des besetzten
U-Boots, und der Remote-Crew-Browser in Chromium) und verschiebt die
Versionsgeschichte nach [CHANGELOG.de.md](CHANGELOG.de.md), damit die README nur noch
die neueste Version steht. `tools/capture_screenshots.py` und
`tools/capture_commander.py` erzeugen alle Bilder neu. Spielstände bleiben v23.

## 1.3.11

Version 1.3.11 bringt ein **Windows-Programm**: `U-Jagd-Windows.exe` startet
das Spiel als Remote-Crew-Server (Besatzungs- oder Solomodus, wahlweise als
U-Boot), zeigt Browser-Adresse, Beitrittscode und QR-Code und bietet jede
neuere Version selbst zum Update an. GitHub Actions baut es bei jedem Push auf
`main` und veröffentlicht es als Release `v<Version>`. Das Spiel kennt dazu
`--remote-crew` (Remote Crew im Besatzungsmodus auf der ersten privaten
LAN-Adresse beim Start) und `--status-file`. Siehe
[Windows-Programm](README.de.md#windows-programm). Spielstände bleiben v23.

## 1.3.10

Version 1.3.10 behebt den uConsole-Installer bei einem Checkout, der älter als
der Installer ist: Er zieht diesen Checkout jetzt zuerst per Fast-Forward auf
`main`, statt mit fehlender `u_jagd_updater.py` abzubrechen.

## 1.3.9

Version 1.3.9 bringt einen Ein-Befehl-Installer für die uConsole mit
automatischem Update: Jeder Start holt das neueste GitHub-Release (ein
Hintergrund-Timer prüft zusätzlich alle sechs Stunden), ohne Netz startet die
installierte Version, und eine Version, die nicht startet, wird zurückgerollt.
Er legt Menüeintrag, Desktop-Verknüpfung und den Befehl `u-jagd` an.
Spielstände bleiben v23.

## 1.3.8

Version 1.3.8 bringt einen Unterstützungslink: einen QR-Code im Hauptmenü des
uConsole und einen kleinen Link auf den Remote-Crew-Seiten Kopplung, Lobby und
Einstellungen sowie auf der Admin-Seite des Webspiels, nie über einer
laufenden Station. Außerdem sind die Anleitungen aktualisiert: Referenz und
README nennen das VDS und 31 kn, die Grenzen des Missionseditors in der README
entsprechen der Laufzeit, und die Koop- und Protokollanleitungen beschreiben
Seitenwahl im Solo-Modus, U-Boot-Rollen und das Beenden über die Admin-Seite.
Spielstände bleiben v23.

## 1.3.7

Version 1.3.7 gibt der Fregatte F-217 ihre echte Höchstfahrt von 31 kn
(AK). Die Antriebsleistung ist so skaliert, dass Widerstand, Beschleunigung
und Drehverhalten bis 25 kn unverändert bleiben; der Eigenlärm steigt jetzt
bis 31 kn, und das Kabel der Nixie reißt weiterhin über 25 kn. Die
Admin-Seite des Webspiels bekommt **Spiel jetzt beenden**, das den
Serverprozess nach Rückfrage stoppt, damit er nicht im Hintergrund
weiterläuft. Spielstände bleiben v23.

## 1.3.6

Version 1.3.6 zeichnet den Startbildschirm als animierte Nachtjagd: die
Fregatte F-217 mit drehendem Radar, Schornsteinrauch, Bugwelle und
Schleppantenne, der Hubschrauber mit Tauchsonar und ein U-Boot unter der
Sprungschicht, das aufleuchtet, wenn der Puls des Rumpfsonars es trifft; im
Titel stehen Autor und Version. Dieselbe Szene liegt abgedunkelt hinter dem
Hauptmenü. Die Silhouetten in Sehrohr und Brückenfernglas zeigen jetzt
detaillierte Klassenprofile (Fregatte, Containerschiff, Kleinfahrzeug,
Hubschrauber), die mit der See stampfen, Radar und Rotoren drehen und Bugwelle
und Kielwasser ziehen. Im Remote-Crew-Solomodus wählt der Dialog „Neues
Spiel“ die Seite: Fregatte oder U-Boot, das dann die KI-Jäger jagen.
Spielstände bleiben v23.

## 1.3.5

Version 1.3.5 bringt KI-Jäger: Wenn niemand die Fregatte fährt (die uConsole
spielt das Boot oder ein Solo-Browser das U-Boot), jagen Fregatte,
Hubschrauber und Seefernaufklärer das Boot mit den eigenen Sensoren der
Fregatte, auf jeder Fregattenstation, die kein Browser hält. Spielstände
bleiben v23.

## 1.3.4

Version 1.3.4 gibt der Fregatte ein Tiefensonar mit variabler Tiefe (VDS)
als dritte Anlage neben Rumpfsonar und Schleppantenne: `Shift+Y` fiert den
Schleppkörper aus oder holt ihn ein (3-15 kn, Seegang bis 5, Verlust über
24 kn), `U`/`V` stellen seine Tiefe (20-300 m), solange er die gewählte
Anlage ist, und er horcht und pingt aus seiner eigenen Tiefe, also unter der
Sprungschicht, wenn er dort hängt. Er löst die Links/Rechts-Mehrdeutigkeit
der Schleppantenne wie das Rumpfsonar auf. Das Remote-Crew-Sonar bekommt
dieselben Bedienelemente. Spielstände wechseln auf Format v23 (VDS-Zustand).

## 1.3.3

Version 1.3.3 zeichnet die Wasserfälle (LOFAR, DEMON, Breitband) im
Remote-Crew-Browser über `OffscreenCanvas` in einem Hintergrund-Worker, wo der
Browser das anbietet; der Hauptthread der Seite und das Live-Sonaraudio darauf
laufen die Rasterschleife nicht mehr. Andere Browser behalten den bisherigen
Weg. Spielstände bleiben v22.

## 1.3.2

Version 1.3.2 lässt im Missionseditor die Referenzwelt einer Mission aus einer
Liste der 128 mitgelieferten Sektoren (mit ihren Ländern) wählen, statt
`sector:<n>` einzutippen; die Vorschau zeichnet die Küste des gewählten
Sektors. Spielstände bleiben v22.

## 1.3.1

Version 1.3.1 gibt dem besetzten U-Boot einen Funkraum (eine siebte
Bootsstation: der Rundspruch des Hauptquartiers mit einer Kontaktmeldung zur
Fregatte und Lagemeldungen, die der KW-Peiler der Fregatte peilen kann) und
lässt die ESM des Boots den Hubschrauber der Fregatte und den
Seefernaufklärer an ihren eigenen katalogisierten Suchradaren hören.
Spielstände wechseln auf Format v22 (Zustand des Funkraums).

## 1.3.0

Version 1.3.0 erweitert Simulation und Werkzeuge der Besatzung, ohne die
Balance von 1.0.0 zu verschieben (77 Kalibrierungsmetriken unverändert): ein
zweiter Leichtgewichtstorpedo mit Suchmustern, Einschaltpunkt und
Salvenstreuung; feindliche U-Boote, die erst nach konvergierter eigener
Zielanalyse schießen; Gegenfluten, Längstrimm und Anlagenwahl an Bord;
Sonobojen-Muster und MAD-Lauf des Hubschraubers; Konvergenzzonen aus dem
gemessenen Schallprofil mit Ekelund- und Punktstapel-TMA; ein Sehrohr mit
Sichtungen, Stadimeter und Dieselgeräusch beim Schnorcheln für das besetzte
U-Boot; geglättete Kartenlinien, das Licht der Stunde auf der Karte, ein
Wetterband und ein gemeinsamer Horizont-Renderer; ein WebSocket-Zustandspush
für die Remote Crew mit generierter Schema-Allowlist; eine reine
Beobachterrolle, ein Zeitstrahl zur Nachbesprechung mit JSON-Export und
Sprachfunk ab Start; und eine Missionslaufzeit im Umfang des Editors
(Referenzsektoren, Schützen- und Erreichen-Ziele, Zufallsgruppen,
zeitgesteuerte Ereignisse, eingestelltes Wetter, platzierte Luftfahrzeuge,
Tiere und Täuschkörper). Der Kern ist in Mixins zerlegt, die Testsuite läuft
parallel. **Spielstände haben das Format v23 (Tiefensonar der Fregatte, Funkraum des besetzten Boots, Funkaufträge der Führung, Wachplan, Ermüdung und Moral der Crew, der Seefernaufklärer auf Abruf, Abteilungen und Leckabwehr, Tauchzellen, Trimm und Pressluft sowie ESM-Bild des besetzten Boots,
Diesel, Laderate und Luftvorräte der U-Boote, Crew-Zustand des Bootes,
Sehrohr-Sichtungen, Waffeneinstellungen, Missionsereignisse, fremde Pings auf
dem Weg zur Fregatte); ältere Stände werden abgewiesen.**

## 1.2.0

Version 1.2.0 verbessert den Spielfluss und die Übergabe zwischen den
Stationen: Der `Esc`-Dialog und das Missionsende führen zurück ins Hauptmenü
(`M`), `R` startet eine Editor-Mission als sie selbst neu, Konvoimissionen
melden die Restzeit als Fortschritt, und eine OPZ-Fusion aus einem
Sonarkontakt lässt sich der Waffenzentrale zuweisen; ihre Klassifizierung und
Zugehörigkeit gelten für die Feuerleitung (FREUND/NEUTRAL auf einer Fusion
sperrt jeden Torpedoschuss). Spielstände bleiben v14.

## 1.1.0

Version 1.1.0 ersetzt die verbliebenen kinematischen Vereinfachungen durch
physikalische Modelle und hält dabei die Spielbalance von 1.0.0 (geprüft durch
einen Kalibrierungs-Harness): kraftbasierte Schiffshydrodynamik und
Seegangsbewegungen; ein zeitlich veränderlicher Ozean mit Gezeiten,
Deckschicht, Sedimenten und Wracks; passive/aktive Sonargleichungen mit
Strahlverfolgung; Seiten-Mehrdeutigkeit der Schleppantenne, Doppler und TMA mit
Kovarianz; U-Boot- und Torpedophysik (Energie, Flossen, Draht,
Annäherungszünder); Täuschkörper-Diskriminierung; Abteilungsflutung,
Stabilität, Brand und Reparaturlogistik; die Radargleichung mit drehender
Antenne, ESM-Pegel, KW-Ausbreitung und ein Ausguck mit Mondlicht; sowie
Flugkörper-Flugphysik mit Düppelwolken, CIWS-Ballistik, Pop-up-Angriffen,
Helikopter-Schwebeflug/Decklimits und treibenden Bojen. Feindliche U-Boote
brauchen jetzt eine eigene TMA, bevor sie Ihre Entfernung kennen.
**Spielstände haben jetzt das Format v14 (Katalogzuordnung, gemeinsamer Kartenplot);
ältere Spielstände werden abgelehnt.** Das Remote-Crew-v2-Protokoll bleibt bis auf neue ELOKA-Felder
unverändert. Die vollständige Übersicht steht in
[docs/simulation-gaps.md](docs/simulation-gaps.md).

## 1.0.0

Version 1.0.0 teilt jede Arbeitsstation in zwei per Tab wählbare Unterseiten,
ergänzt manuelle Freigabeschalter für CIWS und FLAK neben den bestehenden
automatischen Feuerfreigaben und gibt der Autocrew-Brücke ein Ausweich- und
Grundberührungs-Vermeidungsverhalten gegen ASM-/Torpedo-Bedrohungen. TMA-
Neulösungen nutzen jetzt eine Hysterese gegen fast gleichwertige
Peilungslösungen, und feindliche Seezielflugkörper tragen einen aktiven
Radar-Suchkopf in der Terminalphase, der eine ESM/RWR-Warnung liefert, bevor
das Suchradar sie erfasst. Ein konsolidiertes Theme-System ergänzt eine
optionale High-Contrast-Palette für Farbfehlsichtigkeit. Speicherformat v11
und das Remote-Crew-v2-Protokoll bleiben unverändert.
