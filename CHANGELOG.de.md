# Änderungsprotokoll

[English changelog](CHANGELOG.md)

Alle Versionen von U-Jagd, die neueste zuerst. Die [README](README.de.md) zeigt nur die neueste.

## 1.3.253

Version 1.3.253 räumt die Kartenbeschriftung auf. Der Name eines Schiffs
liegt nicht mehr unter seiner eigenen Kurslinie: Er steht querab vom Kurs,
zusammen mit der Fahrt (MV KURELA 8kn), frei von Bewegungsvektoren, Spuren
und anderen Namen, und behält seinen Platz, statt von Bild zu Bild zu
springen. Ein Schiff, das Radar und Ausguck sehen, erscheint auf Brücken-
und Waffenkarte einmal, auch bevor die OPZ beide Meldungen fusioniert hat,
und ein fusioniertes Schiff mit AIS nimmt Kurs und Fahrt aus dem AIS, sodass
sein Vektor nicht mehr hin und her schwenkt. Das gilt auf der uConsole und
im Browser. Spielstände sind v53; Spielstände v38 bis v52 laden weiterhin.

## 1.3.251

Version 1.3.251 bringt neue Inhalte und mehr Komfort. Der Tageseinsatz ist
jetzt ein Kurzeinsatz, je Seite nach dem Datum gewählt, und das Spiel
merkt sich die gewählte Einsatzlänge; neue Spieler beginnen mit
Kurzeinsätzen. Die Ausbildung steht an zweiter Stelle im Hauptmenü, hakt
abgeschlossene Lektionen ab, wählt die nächste vor, und N auf der Endtafel
startet sie. Drei neue Fregatten-Lektionen üben die Luftabwehr gegen einen
anfliegenden Flugkörper, ESM an einem Frachterradar und die Torpedoabwehr
mit dem Nixie. Führt die Crew-Unterstützung das U-Boot, übernimmt sie
jetzt eine gute TMA-Lösung als Ortung und greift damit an. Beide
Endtafeln nennen in einer Zeile, was den Einsatz entschieden hat, und das
Einsatzbuch zeigt ein Band je gewonnenem Szenario, auch im Browser.
Spielstände sind v53; Spielstände v38 bis v52 laden weiterhin.

## 1.3.250

Version 1.3.250 lässt die Stimme sauberer sprechen. Temperaturen werden
ausgesprochen (-2 °C als „minus zwo Grad Celsius“), ebenso Vorzeichen,
Bereiche und Zeichen (± als „plus minus“, 0–360 als „null bis drei sechs
null“, & als „und“); kurze Kürzel in Großbuchstaben wie HQ werden
buchstabiert, Wörter in Großschrift normal gesprochen, und Zeichen wie |,
· oder Pfeile werden zu einer kurzen Pause, statt vorgelesen zu werden.
Die Stimme ist fest auf die Spielsprache eingestellt, Deutsch oder
Englisch: Die Sprechanweisung sagt das deutlicher, und Sprachdienste mit
einem Feld für die Sprache (etwa Qwen-TTS) bekommen sie mitgeschickt,
damit kein Satz mehr in einer anderen Sprache oder mit fremdem Akzent
beginnt. Tasten und Spielstände bleiben gleich (v53; Spielstände v38 bis
v52 laden weiter).

## 1.3.247

Version 1.3.247 zeigt jeden Kontakt auf der Brückenkarte nur noch einmal.
Ein Schiff, das Radar und Ausguck sahen, erschien bisher doppelt, jede
Meldung mit eigenem Symbol, eigener Beschriftung und eigenem
Fahrtvektor, weil die Brücke die rohen Sensormeldungen zeichnete und nur
die OPZ sie fusioniert zeigte. Brückenkarte, ihre Spuren und Tooltips
sowie Karte und Liste der Remote-Crew-Brücke zeigen jetzt den
fusionierten Track der OPZ, mit dem AIS-Namen des Schiffs, sobald er
bekannt ist. Tasten und Spielstände bleiben gleich (v53; Spielstände v38
bis v52 laden weiter).

## 1.3.246

Version 1.3.246 lässt die Stimme des Sprachmodells ruhig und gleichmäßig
klingen. Erster Offizier, Crew und Log sprechen jetzt in einem festen Ton,
der den Sprachdienst bittet, nicht zu lachen, zu seufzen oder die
Stimmung zu wechseln; Stimme und Ton springen nicht mehr von Satz zu
Satz. Ein Logeintrag wird am Stück gesprochen statt Satz für Satz,
Einheiten und Abkürzungen werden ausgesprochen (12 kn als „zwölf
Knoten“, sm als „Seemeilen“, ° als „Grad“, Rtg als „Richtung“,
Positionen in Grad und Minuten Nord und Ost), und Seed -1 zieht jetzt
einen Seed pro Start statt für jeden Satz einen neuen. Tasten und
Spielstände bleiben gleich (v53; Spielstände v38 bis v52 laden weiter).

## 1.3.243

Version 1.3.243 lässt die Stimme des Sprachmodells das Log vorlesen.
Ist ein Sprachdienst eingerichtet, werden die Einträge im Log der
eigenen Seite (`F11`) gesprochen, sobald sie kommen, nach den Antworten
des Ersten Offiziers und den Crew-Rufen; ein Eintrag, der länger als 15
Sekunden wartet, fällt weg, statt verspätet zu kommen, und was die Crew
schon ausruft, wird nicht doppelt vorgelesen. Jede Station des Logs lässt
sich einzeln stummschalten: auf der neuen Seite 4 „Meldungen“ der
Sprachmodell-Einstellungen (Optionen, Seite 2), die auch die Meldungen
jeder Station der letzten 5 Minuten zählt, oder mit den Knöpfen je
Station unten im `F11`-Log. Tasten und Spielstände bleiben gleich (v53;
Spielstände v38 bis v52 laden weiter).

## 1.3.242

Version 1.3.242 macht den Ersten Offizier (`F7`) und die Einstellungen
des Sprachmodells auf dem uConsole und in den Desktop-Apps vollständig mit
der Maus bedienbar. Ein Klick auf einen Reiter wählt die Art der Anfrage;
blaue Tastenknöpfe unter dem Protokoll senden, geben oder verwerfen einen
getippten Befehl, blättern älter und neuer und schließen die Seite; das
Mausrad blättert; oben rechts sitzt ein Schließkreuz, und kein Klick
erreicht die Station dahinter. Solange das Modell aus ist, öffnet ein
Knopf seine Einstellungen, in denen Tastenknöpfe unter den Zeilen jetzt
jede Taste abdecken (wählen, ändern, Seite, Feld speichern oder abbrechen,
zurück). Auf/Ab blättern
das Protokoll jetzt ab dem ersten Schritt und auch, während ein Befehl auf
Bestätigung wartet. Der Erste Offizier im Browser war schon mit der Maus
bedienbar. Das Spiel bleibt unverändert. Spielstände sind v53; v38 bis v52
laden weiter.

## 1.3.241

Version 1.3.241 ändert die Lizenz. U-Jagd steht nicht mehr unter der
MIT-Lizenz, sondern unter der PolyForm Strict License 1.0.0: Sie dürfen das
Spiel unverändert und nicht kommerziell spielen und nutzen, es aber nicht
verkaufen, weitergeben oder verändern. Das gilt für den Code, die
Browser-Clients, die Windows-EXE und die macOS-App; Pygame, NumPy,
Kartendaten und Schriften behalten ihre eigenen Lizenzen. Das Spielgeschehen
bleibt gleich. Spielstände sind v53; Spielstände v38 bis v52 laden weiterhin.

## 1.3.238

Version 1.3.238 zeigt Breite und Länge auf jeder Karte jeder Station.
Bisher hatten nur die Brückenkarte und die Karten neben den Stationen des
U-Boots das Gradnetz; auf der uConsole zeigten das Lagebild der OPZ, die
Kreuzpeilkarte des Funkraums und die Lotsenkarte des U-Boots noch ihr
einfaches sm-Gitter. In einem echten Seegebiet zeichnen sie jetzt
Meridiane und Breitenkreise in Grad und Minuten mit ihren Zahlen am Rand
und nennen die eigene Position wie 54°21,4'N 010°08,2'E (die Lotsenkarte
des U-Boots den gekoppelten Ort); die Zahlen halten sich von
Entfernungsringen, Peilskala und anderen Beschriftungen frei. Die Karten
im Browser hatten das Gradnetz schon. Die stilisierte feste Karte behält
ihr sm-Gitter. Spielablauf, Tasten und Spielstände bleiben gleich (v53;
v38 bis v52 laden weiter).

## 1.3.237

Version 1.3.237 lässt die optionale Stimme Zahlen sprechen wie auf Wache:
Ziffer für Ziffer. Erster Offizier, Coach, Crew-Meldungen und der
Stimmtest sagen 431 jetzt als „vier drei eins“ und 0,9 als „null Komma
neun“ (auf Englisch „four three one“, „zero point niner“), ob der Text vor
dem Sprechen bereinigt wird oder nicht. Die Stimme setzt auch früher
ein: Eine lange Antwort geht Satz für Satz hinaus, der erste Satz spielt
schon, während der Rest noch erzeugt wird, und Ton, den ein Dienst streamt
(OpenAI tut das), spielt schon während der Übertragung. Die Tasten bleiben
gleich.
Spielstände sind v53; v38 bis v52 werden weiter geladen.

## 1.3.235

Version 1.3.235 behebt einen Hänger beim Stoppen des eigenen Mikrofons.
Das Abschalten des Mikrofons für die Geräuschdisziplin, das Ende eines
Einsatzes oder das Beenden konnte das Spiel einfrieren, während gerade ein
Aufnahmeblock gelesen wurde; der Selbsttest des macOS-Builds blieb dort
hängen. Das Gerät schließt jetzt, ohne auf das Spiel zu warten, auf der
uConsole, unter Windows und unter macOS. Spielstände sind v53;
Spielstände v38 bis v52 laden weiterhin.

## 1.3.234

Version 1.3.234 bringt den Browser auf den Stand der uConsole. Die
Sonarseite wählt den aktiven Impuls (CW oder LFM, W) und das TMA-Verfahren
(Umschalt+T). Die Browser-Tasten folgen jetzt an jeder Station beider
Seiten der uConsole: + und - stellen den Maschinentelegrafen (jetzt auch
auf der Brücke), Funkraum, Leckwehr und ELOKA haben ihre Tasten, und jedes
belegte Bedienelement zeigt seine Taste als blauen Chip. Seitenleisten und
Protokoll liegen jetzt auf Alt+, Alt+. und Alt+L, und [ ] schalten keine
Stationen mehr um. Der Funkraum zeigt, ob ein eigener Ruf an die Führung
auf Sendung ist, wartet oder bereit ist, und eine neue KW-Peilkarte
zeichnet Peilungen, Kreuzpeilungen und Fehlerellipsen. Die Stationsleisten
stellen die Bedienelemente vor die Lesetabellen, die sich einklappen
lassen, und nutzen auf breiten Bildschirmen zwei Spalten. Der Solo-Browser
öffnet das Einsatzbuch und die Ausbildung. Spielstände sind v53;
Spielstände v38 bis v52 laden weiterhin.

## 1.3.233

Version 1.3.233 bringt die Bedienung unter einheitliche Regeln.
Strg+Eingabe ist jetzt die einzige Taste, die eine Waffe auslöst: An der
Waffenstation wählen D, A, Z, R und Umschalt+R nur die Waffe, die dann
leuchtet und in der Feuerzeile steht. Jede Taste einer Stationsseite steht
als blauer Chip in ihrer Tastenleiste und wird per Klick gedrückt; ein
+-Chip blättert durch den Rest (auch durch alle Sonartasten beider
Seiten). Lange Listen blättern mit dem Mausrad, Overlays schließen über
ein Schließkreuz, und Hinweise erklären weitere Lampen. Eigene Einheiten
tragen auf jeder Karte den passenden NATO-Rahmen, hoher Kontrast erreicht
jede Zeichnung, und deutsche Texte nutzen deutsche Tastennamen und „sm“.
Spielstände sind v53; v38- bis v52-Stände laden weiterhin.

## 1.3.231

Version 1.3.231 gibt dem optionalen Sprachmodell eine Stimme. Unter
Optionen, Seite 2, Sprachmodell nimmt eine zweite Seite „Stimme“ einen
OpenAI-kompatiblen Sprachdienst auf (Adresse, Sprechmodell, Stimme und
API-Schlüssel; voreingestellt OpenAI gpt-4o-mini-tts), und eine dritte Seite
„Klang“ stellt Temperature, top_p und Seed für Dienste ein, die sie annehmen
(Qwen-TTS), und bereinigt den Text vor dem Sprechen. Damit spricht der Erste
Offizier seine Antworten und die Tipps des Coachs, und die gesprochenen
Crew-Meldungen kommen mit derselben natürlichen Stimme statt über espeak-ng,
beides einzeln schaltbar. Die Stimme spielt auf einem eigenen Tonkanal neben
dem Sonarton, und ihr Schlüssel liegt in ~/.u-jagd/tts_key (oder es gilt der
des Sprachmodells beim selben Server), nie in Einstellungen oder Spielständen.
Ohne den Dienst läuft das Spiel genau wie bisher; Browser behalten ihre eigene
Stimme für Crew-Meldungen. Die Einstellungsseiten lassen sich jetzt mit der
Maus bedienen. Spielstände sind v53; v38 bis v52 werden weiter geladen.

## 1.3.229

Version 1.3.229 macht das Ereignislog (F11) in jedem Farbschema lesbar und
lässt es mit der Maus schließen. Im hellen Schema „Taktik Tag“ behielt das
Log die Farben der Nacht, viele Zeilen waren blassgrau oder hellblau auf
Weiß, und die Station schien durch. Jetzt nimmt das Log die Farben des
gewählten Schemas, deckt die Station ganz ab und hat oben rechts ein
Schließen-Kreuz. Ein Klick auf das Log erreicht die Station dahinter nicht
mehr. Im Browser nimmt die abgedunkelte Fläche um ein offenes Blatt
(Anleitung, Kontakte, Ausguck) den Klick und schließt das Blatt, statt ein
Bedienelement dahinter auszulösen. Dieselbe Korrektur gilt für die
Zeitleiste der Nachbesprechung, die Feldzugskarte, die Bedrohungs- und
Funkseite des U-Boots, die Ausguckseite, die Wetterstation und das
Simulationsprotokoll. Tasten bleiben gleich. Spielstände sind v53; v38 bis
v52 laden weiter.

## 1.3.223

Version 1.3.223 macht das Spiel auf dem uConsole ruhiger. Sonar-
Schalltabellen werden im Hintergrund vorbereitet, Missionsstart und neue
Seegebiete ruckeln nicht mehr, und Sonar, Wasserfall, ELOKA-Liste und
Ereignisanzeige zeichnen sparsamer. Speichern auf einen Platz läuft im
Hintergrund und hält das Bild nicht mehr an; das Speichermenü schließt
sich erst, wenn die Datei sicher auf dem Datenträger liegt. Neu ist
„automatisch sparsam“: Bleibt das Bild 5 Sekunden unter 14 Bildern pro
Sekunde, schaltet das Spiel selbst auf die Grafikstufe Sparsam und zeigt
oben eine gelbe ECO-Lampe (Optionen, Seite 2, Grafik schaltet es ab). Die
Simulation selbst bleibt unverändert. Die Tasten bleiben gleich.
Spielstände sind v53; v38- bis v52-Stände laden weiterhin.

## 1.3.222

Version 1.3.222 korrigiert, wie Einsätze enden und gewertet werden.
U-Boot-Siege in „Angeschlagen heim“, „Agenten abholen“, „Lauschposten“
und eine abgeschüttelte Fühlung zählen jetzt als Sieg mit ihren Punkten,
und die Endanzeige des U-Boots nennt den Grund des Einsatzendes und zeigt
die Punkte wie die der Fregatte. „Patrouille“ bringt immer das alte
Diesel-U-Boot aus der Einweisung. Ein torpediertes Handelsschiff funkt
einen Notruf, und die 300 Punkte Abzug gibt es nur, wenn dein Sonar den
Angreifer kurz davor gehört hat. Die Brücke ruft neue HQ-Aufträge aus,
und die KI-Funkcrew beantwortet liegen gelassene Aufträge. Dazu kleinere
Text- und Browseranzeige-Korrekturen. Die Tasten bleiben gleich.
Spielstände sind v53; v38- bis v52-Stände laden weiterhin.

## 1.3.221

Version 1.3.221 macht das Veröffentlichen sicherer. Eine neue Version
erscheint erst, wenn alle Tests auf ihr bestanden sind, so kommt ein
fehlerhafter Stand nie ins Update-Angebot. Scheitert der Windows-Bau,
bekommen uConsole und Mac das Update trotzdem, und für Windows bleibt die
ältere Version stehen. Updates für Windows und macOS werden nur noch mit
SHA-256-Prüfsumme angeboten. Die Tests laufen jetzt auch unter Windows und
mit Python 3.13. Spiel und Tasten bleiben gleich. Spielstände sind v53;
v38 bis v52 laden weiter.

## 1.3.218

Version 1.3.218 lässt einen Klick auf eine Sonar-Kontaktkarte diesen
Kontakt sofort abhören. Der Klick wählt den Kontakt und richtet die
Hörpeilung auf ihn, wie Auf/Ab und danach Enter, so dass Wasserfall,
Analyseseiten und Ton sofort zu ihm wechseln; ein Kontakt, der länger als
2 s nicht gehört wurde, wird nur gewählt. Das gilt an der Sonarstation der
Fregatte und im Sonarraum des U-Boots auf der uConsole und in den Desktop-Apps
; im Browser tat ein Klick auf einen Sonarkontakt das schon. Tasten
und Spielablauf bleiben gleich. Spielstände sind v53; v38 bis v52 werden
weiter geladen.

## 1.3.214

Version 1.3.214 zeichnet feinere Küsten und nennt Positionen auch im
Funkverkehr in Grad und Minuten. Die 128 echten Seegebiete kommen jetzt aus
Natural Earth im Maßstab 1:10m statt 1:50m: Buchten, Fjorde, Inseln und
Landzungen sind bis auf etwa 0,05 sm genau, die Küste in der Karte gleicht
damit viel mehr einer echten Seekarte (das Kartenpaket wächst auf etwa
3 MB). In einem echten Seegebiet nennen HQ-Aufträge und -Meldungen,
Vorfallwarnungen, die Auftragsseite, protokollierte KW-Peilungen und der
ESM-Fix des U-Boots Positionen wie 54°21,4'N 010°08,2'E, weiter mit Peilung
und Abstand, wo das HQ sie angibt, auf der uConsole wie im Browser. Ein
Patrouillenstart, den die feinere Küste in eine enge Bucht legen würde,
rückt ins offene Wasser, und ein U-Boot bleibt bei Hochwasser nicht mehr am
Grund hängen. Die gemessene Fairness bleibt gleich (KI gegen KI 14 bzw. 15
von 36 Siegen der Fregatte, besetztes U-Boot 16 von 24). Tasten bleiben
gleich. Spielstände sind v53; v38 bis v52 laden weiter, und eine
gespeicherte Mission behält die Küste, mit der sie begann.

## 1.3.213

Version 1.3.213 lässt ein feindliches U-Boot vor der Waffe ausweichen, die
es hört. Bisher drehte es von der Peilung der Fregatte weg, auch wenn
Torpedo, Wasserbombe oder Rakete von anderswo kamen, etwa vom Hubschrauber.
Jetzt dreht es von der Peilung der Waffe selbst weg und nur dann von der
Fregatte, wenn es keine gehört hat. Tasten bleiben gleich.
Spielstände sind v53; v38 bis v52 laden weiter.

## 1.3.212

Version 1.3.212 behebt Fehler in der Sonar-Akustik, die die Code-Prüfung
gefunden hat. Die Strahlverfolgung hält Schallstrahlen nicht mehr in ihrer
Umkehrtiefe fest; Schattenzonen und Konvergenzzonen entstehen also dort, wo
die Schallgeschwindigkeit sie hinlegt, und im Flachwasser endet ein Strahl
nicht mehr nach 12 Reflexionen. Der Nachhall des Aktivsonars auf kurze
Entfernung in tiefem Wasser folgt jetzt dem echten Streifwinkel und zählt
den Meeresboden erst, wenn das Echo ihn erreichen kann. Die eigene Linie der
Fregatte im LOFAR ist jetzt die Blattfrequenz aus der Wellendrehzahl (etwa
9,7 Hz bei 20 kn), und DEMON zeigt neben einer Blattlinie die Wellenlinie
und die doppelte Linie, sodass sich die Blätter eines Kontakts zählen
lassen. Tasten bleiben gleich. Spielstände sind v52; v38 bis v51 laden
weiter.

## 1.3.211

Version 1.3.211 behebt Fehler in Physik und Waffen, die die Code-Prüfung
gefunden hat. Ab Seegang 5 kommt die Fregatte aus dem Stand wieder in Fahrt
(sie blieb bei 0 kn stehen). Ein U-Boot, das seinen Tiefenbefehl mitten im
Tauchen ändert, springt nicht mehr auf die neue Tiefe. Das MAD des
Hubschraubers misst einmal pro Sekunde, die Kontaktchance hängt also nicht
mehr von der Bildrate ab. Die Crew-Hilfe flieht vor einem Torpedo mit 24 kn
statt AK, solange ein Nixie ausgesetzt oder an Bord ist, weil dessen
Schleppkabel über 25 kn reißt, und setzt darüber keinen mehr aus. Ein
feindlicher Torpedo verliert seine Erfassung, wenn das Ziel außer
Reichweite seines Suchkopfs ist, hört die Fregatte lauter, je schneller sie
fährt, und behält sein Suchmuster, solange der Draht hält. Tasten bleiben
gleich. Spielstände sind v52; v38 bis v51 laden weiter.

## 1.3.210

Version 1.3.210 zeigt die Karten in echten geografischen Koordinaten. In
einem echten Seegebiet zeigt das Kartengitter jetzt Längen- und Breitengrade
in Grad und Minuten, beim Hineinzoomen feiner (5 Grad bis 0,1 Minute), oben
links steht die eigene Position wie 53°19,9'N 007°00,9'E (auf dem U-Boot der
gekoppelte Ort), und der Tooltip des Mauszeigers nennt die Position darunter,
auf der uConsole wie im Browser. Die Gitterzahlen bleiben jetzt auch über
Land lesbar. Entfernungen, Ringe und Maßstab bleiben in sm, das Spiel spielt
sich wie bisher; die stilisierte feste Karte behält ihr sm-Gitter. Tasten
bleiben gleich. Spielstände sind v52; v38 bis v51 laden weiter.

## 1.3.209

Version 1.3.209 lässt die Browser-Stationen mehr ohne Scrollen zeigen. Im
Browser haben die Stationen dieselben Tasten wie auf dem uConsole (zum
Beispiel C/V/D für Kurs, Fahrt und Tiefe, Umschalt+A für den Ping,
Strg+Enter zum Feuern), und jede Taste steht als blaue Tastenkappe auf ihrer
Schaltfläche. Die leere Kontaktdetail-Spalte und eine leere Kontaktliste
klappen weg, die Missionsübersicht ist eine Zeile "Auftrag", und leere Werte
zeigen einen grauen Strich. Auf dem U-Boot sind Funklog und Rohre wieder
lesbar, die Rohre erscheinen als Karten. Die Waffenstation der Fregatte zählt
ihre Rohre ab 1 und zeigt die Feuerkette Schritt für Schritt. Ländernamen auf
der Karte stehen einmal je Land, auf Deutsch oder Englisch, auch auf dem
uConsole. Auf dem Handy klappt die obere Leiste in ein ☰-Menü. Die Tasten auf
dem uConsole sind unverändert. Spielstände sind v52; Spielstände v38 bis v51

## 1.3.208

Version 1.3.208 hält die uConsole bei Live-Verkehr flüssig. Eine Mission
mit echten Flugzeugen (OpenSky ADS-B) fliegt jetzt höchstens 5 davon statt
40, eine mit echten Schiffen (AIS) höchstens 15 statt 60, zufällig gewählt
und behalten, bis jeder Kontakt das Gebiet verlässt, damit Kontakte nicht
auftauchen und wieder verschwinden. Bei Dutzenden Live-Kontakten lief der
eine Spiel-Thread voll, und das Spiel ruckelte, obwohl der Prozessor nur
etwa ein Drittel Last zeigte. Das OPZ-Lagebild wird außerdem nur noch
einmal pro Bild statt mehrmals berechnet, und ein Schwall Live-AIS-Meldungen
wird auf mehrere Bilder verteilt. Remote-Crew-Browser sehen dieselben
Kontakte. Die Tasten bleiben gleich. Spielstände sind v52; v38- bis
v51-Stände werden weiter geladen.

## 1.3.207

Version 1.3.207 lässt die Beschriftungen der OPZ-Karte an ihrem Platz, wenn
weit herausgezoomt ist. Die Zahlen der Peilskala um die Radarringe stehen
jetzt immer bei ihrer Peilung, statt den Entfernungsangaben auszuweichen;
000 steht wieder oben und 180 unten. Liegen die Ringe eng beieinander, ist
nur jeder zweite Ring beschriftet, die Entfernung des äußeren Rings steht
neben der 000, und eine Entfernungsangabe, die eine Peilzahl verdecken
würde, entfällt. Die OPZ-Karte der Remote Crew im Browser macht es genauso.
Die Tasten sind unverändert. Spielstände sind v52; Spielstände v38 bis v51
laden weiterhin.

## 1.3.206

Version 1.3.206 schreibt die README neu: sie ist viel kürzer, lässt
veraltete Einzelheiten weg und verweist für alles Weitere auf das Handbuch
und das Änderungsprotokoll. Das Spiel selbst ist unverändert. Die Tasten
sind unverändert. Spielstände sind v52; Spielstände v38 bis v51 laden
weiterhin.

## 1.3.205

Version 1.3.205 behebt, was eine vollständige Code-Prüfung gefunden hat,
ohne das Spiel zu verändern. Ein beschädigter oder von Hand bearbeiteter
Spielstand wird jetzt abgewiesen, statt das Spiel zu beenden, und ein
fehlgeschlagenes Laden verändert die laufende Mission nicht mehr. Auf der
uConsole ruckelt es weniger: das Schallbild wird schneller berechnet, Regen
auf der Karte wird einmal statt in jedem Bild gezeichnet und ist im hellen
Farbschema jetzt sichtbar, Statuszeilen und Tooltips verwenden ihren
gezeichneten Text wieder, und ein Geräusch aus einer neuen Richtung wird
nicht neu erzeugt. Im Browser gehen Spielgeräusche und Durchsagen nicht mehr
verloren, wenn der Host ein Menü öffnet. Tooltip und Zeitangabe des
Sonar-Wasserfalls passen jetzt zum verkürzten Verlauf (Shift+H). Ein
abgebrochener Update-Download lässt sich erneut starten, und das
Windows-Programm schreibt sein Absturzprotokoll wieder. Tasten bleiben
gleich. Spielstände sind v52; v38 bis v51 laden weiter.

## 1.3.204

Version 1.3.204 lässt die Lampen des Hubschraubers die Startvorbereitung
nennen. Ruht die Maus auf der Lampe HANGAR, DECK oder START, steht dort, wie
lange die Startvorbereitung noch läuft, wie lange der Start noch auf Sprit
wartet oder dass der Hubschrauber startbereit auf ein Deckfenster wartet, aus
dem laufenden Spiel, und dass ein zweites H die Vorbereitung abbricht. Die
macOS-App gibt es nur noch für Apple Silicon; ein Intel-Mac öffnet die
Release-Seite, statt sich zu aktualisieren. Tasten bleiben gleich. Spielstände
sind v52; v38 bis v51 laden weiter.

## 1.3.203

Version 1.3.203 macht die Rettung von Schiffbrüchigen mit dem Hubschrauber
zu einer klaren Bedienhandlung. Rettungsinseln im Wasser sind jetzt kleine
Radarechos für das Schiffsradar, das Hubschrauberradar und den
Seefernaufklärer (bei hohem Seegang schwerer zu sehen) und verbessern die
gemeldete Position; die OPZ erfährt vom ersten Fix. Die
Hubschrauberstation zeigt ein Rettungsfeld mit dem Zustand der Winde, den
Personen an Bord (höchstens 6), der Insel mit Peilung und Abstand und einem
kurzen Hinweis, was als Nächstes zu tun ist. Im Schwebeflug höchstens
0,1 sm von einer Insel entfernt `Z` drücken (oder die Windenlampe bzw.
*Rettungswinde* im Browser anklicken): Der Hubschrauber stellt sich über
die Insel, holt bei zulässigem Wind eine Person pro Minute herauf und meldet
jede Person, eine leere Insel und eine volle Kabine. Gerettet sind die
Schiffbrüchigen erst, wenn der Hubschrauber auf dem Schiff landet; geht er
verloren, sind sie es auch. Der Hubschrauber der KI-Fregatte nutzt dieselbe
Winde. Spielstände sind v52; v38 bis v51 laden weiter.

## 1.3.202

Version 1.3.202 lässt den Bordhubschrauber der Fregatte Zeit an Deck brauchen.
Der Startbefehl (`H` oder *Helikopter starten* im Browser) beginnt 5 Minuten
Vorbereitung im Hangar, danach hebt er im nächsten Startfenster ab; ein
zweites `H` bricht sie ab. Nach einer Landung behält er den Kraftstoff, mit
dem er zurückkam, und wird an Deck betankt, 15 Minuten von leer bis voll; ein
Start hebt mit dem bis dahin getankten Kraftstoff ab, nie mit weniger als 30
Minuten. Die Hubschrauberstation zeigt STARTVORBEREITUNG oder TANKEN mit der
Restzeit (uConsole und Browser), und der Tooltip über dem Status nennt, worauf
er wartet. Die KI-Fregatte wartet genauso; ihre eigene Wartezeit vor dem
Befehl ist halbiert, damit beide Seiten ihre Chancen behalten. Die Peilrosen halten
„090“ und „270“ vom Text daneben frei, und die Tiefenleiste des Tauchsonars
trennt die Luft durch eine kräftige Wasserlinie vom Wasser. Der Fahrtstrich
des Hubschraubers zeigt seine echte Geschwindigkeit über Grund, und ein Klick
in die Karte legt seinen Wegpunkt genau dorthin; der Hubschrauber bleibt auf
dem Punkt stehen statt 0,3 sm davor. Plot-Objekte außerhalb der Karte bekommen
einen Pfeil am Kartenrand, und ihre Beschriftungen stehen dort nebeneinander
statt übereinander. Der eigene Hubschrauber trägt auf allen Karten das NATO-Zeichen für Drehflügler. Spielstände sind v51; v38 bis v50 lassen sich weiter laden.

## 1.3.201

Version 1.3.201 macht die ELOKA übersichtlicher. Gleichartige Auffassungen
aus einer Richtung (gleiches Band und gleiche Modulation, Peilung innerhalb
6 Grad), etwa die Navigationsradare mehrerer Handelsschiffe, stehen als ein
Sender „E27 ×3“ in der Liste; die Pfeiltasten links und rechts blättern durch
die Gruppe, Z listet wieder jede Auffassung einzeln. Auffassungen heißen nach
ihrer laufenden Nummer (E27 statt E000000000000001b) und zeigen die Einstufung
oder sonst Modulation, Band und Frequenz statt „Unbekannte Domäne“. Vier
Schalter über der Peilrose ordnen die Liste: Status F (neu: offen, die noch
nicht eingestuften Sender), Bedrohung Shift+F, Band Strg+F und Bündeln Z, als
blaue Tastenchips auf der uConsole und als Leiste im Remote-Crew-Browser. Die
Rose im Browser zeichnet je Sender einen Strahl, ältere kürzer und blasser,
und beschriftet den gewählten. Nur die Darstellung ändert sich, das ESM-Bild
bleibt gleich. Spielstände sind v50; v38 bis v49 laden weiter.

## 1.3.200

Version 1.3.200 gibt dem Tauchsonar und der Karte des Hubschraubers im
Remote-Crew-Browser Platz. Beide teilten sich bisher einen Reiter, sodass die
Karte nur ein Streifen und das Sonarbild klein war. Jetzt hat der Hubschrauber
auf der Bühne drei Seiten: Akustikanalyse, Tauchsonar (das Bild über die ganze
Bühne, Ringe mit 5, 10 und 15 sm beschriftet, die Werte daneben) und Taktische
Karte (die Karte über die ganze Bühne). Bild auf/ab, nochmals die
Stationsnummer 8 oder der blaue Tastenchip neben den Reitern blättern zwischen
ihnen, wie die Seiten der uConsole. Die uConsole bleibt gleich. Spielstände
sind v50; v38 bis v49 laden weiter.

## 1.3.199

Version 1.3.199 erklärt jede Statuslampe. Ruht die Maus auf einer Lampe oder
Anzeige, etwa START NO-GO und DECK WARTEN des Hubschraubers, einem
Torpedorohr, der Anlage, dem ESM-Empfänger oder dem Wasser unter dem Kiel des
U-Boots, öffnet sich ein Hinweis, warum sie so steht, aus dem laufenden Spiel
(Deckbewegung und Ruhezeit, Wettergrenzen, Nachladezeit, Kartentiefe), und was
zu tun ist. Jede Taste, die eine Station nutzen kann, ist jetzt ein blauer
Tastenchip zum Anklicken, auch in diesen Hinweisen. Beides gilt auf beiden
Seiten, auf der uConsole und im Remote-Crew-Browser. Die vier Kontaktknöpfe
der OPZ sagen, was sie tun (Klassifizieren, Zugehörigkeit wechseln, Für Fusion
markieren, Fusionieren / auflösen), mittig neben ihrem Tastenchip. Tasten
bleiben gleich. Spielstände sind v50; v38 bis v49 laden weiter.

## 1.3.198

Version 1.3.198 behebt die Meldung „Anzeige gestört“ beim starken
Hineinzoomen in eine Karte. Mit der Grafikstufe „Voll“ konnte das geglättete
Linienzeichnen keine Linien verarbeiten, die weit außerhalb der Karte enden,
etwa einen Autopilot-Schlag zu einem fernen Wegpunkt bei stärkstem Zoom; die
Karte zeigte dann die Fehlerbox statt des Lagebilds. Linien und Flächen werden
jetzt vor dem Zeichnen auf den sichtbaren Kartenteil zugeschnitten, sodass
jede Karte beider Seiten im nächsten und im weitesten Maßstab zeichnet.

## 1.3.197

Version 1.3.197 lässt die Hinweisfenster beim Überfahren mit der Maus dem
Farbschema folgen. Im hellen Schema „Taktik Tag“ ist ein Hinweis jetzt eine
helle Karte mit dunkler Schrift statt eines dunklen Kastens mit kaum lesbarer
Schrift; „Taktik Nacht“ und hoher Kontrast behalten den dunklen Kasten, bei
Rotlicht wird er grau. Die Bilder der Leckwehr (Seitenriss
und Querschnitt der Fregatte, Schnitt des U-Boots) werden bei Tag zu einer
hellen Zeichnung, Wasser, Feuer und Trupps bleiben gut erkennbar, auf der
uConsole und im Browser. Auch der Update-Hinweis im Hauptmenü und der Hinweis
für eine nicht gezeichnete Ansicht folgen dem Schema. Tasten bleiben gleich.
Spielstände sind v50; v38 bis v49 laden weiter.

## 1.3.196

Version 1.3.196 schließt die letzten Punkte der Codeprüfung. Der LFM-Ping
gewinnt nicht mehr 20 dB gegen Rauschen, was ein Puls mit derselben Energie
wie CW nicht kann; stattdessen senkt seine feine Entfernungszelle den Nachhall
des Meeresbodens um 20 dB, sodass er ein langsames oder stehendes U-Boot im
Flachwasser findet, während beide Pulse im tiefen Wasser gleich weit reichen.
Ein U-Boot hört einen laufenden Torpedo jetzt auf seiner vollen
Bezugsentfernung. Auf freier Fahrt kostet ein versenktes neutrales U-Boot die
Fregatte nur, wenn ihre eigenen Torpedos, Wasserbomben oder Raketen es
versenkt haben, und ein U-Boot, das als neue Begegnung zurückkehrt, ist ein
neuer Kontakt. Ein hängender Selbsttest beim Bau hält neue Versionen nicht mehr
stundenlang auf. Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.195

Version 1.3.195 hält die Mikrofonanzeige von der Statuszeile der Kopfleiste
fern. Auf der uConsole steht die Anzeige jetzt zwischen Statuszeile und
Menüknopf, und die Statuszeile weicht ihr aus: Ein langer Einsatzname wird
gekürzt, Uhrzeit, Fahrt, Kurs und Tiefe bleiben ganz. Die Anzeige ist als
LED-Leiste hinter einem Mikrofonzeichen gezeichnet; unbeleuchtete Felder sind
abgedunkelt statt leerer Kästchen, die wie fehlende Buchstaben aussahen, und
eine kleine Marke unter einem Feld zeigt die lauteste Stimme der Besatzung.
Die Anzeige im Browser sieht genauso aus.

## 1.3.194

Version 1.3.194 berichtigt Daten und den Zünder des Feindtorpedos aus der
Codeprüfung. Trafalgar und Rubis sind jetzt Atom-U-Boote und Collins ein
diesel-elektrisches; Improved-Kilo, Lada und Taigei haben keinen AIP mehr
(Taigei dafür eine größere Lithium-Batterie); Virginia und Yasen sind nicht
mehr schneller als ihre Klasse. Der Feindtorpedo detoniert erst innerhalb
etwa 90 m und nahe Kieltiefe statt schon 460 m querab, und sein Schaden sinkt
weiter mit dem Abstand. Der Leichttorpedo von Hubschrauber und
Seefernaufklärer läuft 45 kn über 6 sm, der Mk2 der Fregatte 50 kn über 6 sm.
Jedes Schiff hat jetzt seine echte Länge, die sein Echo und seine Wendigkeit
bestimmt; die Triple-E gilt als Containerschiff, und das Flusskreuzfahrtschiff
fährt nicht mehr auf offener See. Spielstände sind v50; v38 bis v49 lassen
sich weiter laden.

## 1.3.193

Version 1.3.193 benennt die Anzeige des Ersten Offiziers um: Der Titel heißt
jetzt nur „Erster Offizier“, und solange das optionale Sprachmodell an einer
Antwort arbeitet, steht auf der uConsole und im Browser „Der Erste Offizier
wertet die Lage aus ...“ statt „Das Sprachmodell schreibt ...“. Am Spiel
ändert sich nichts. Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.192

Version 1.3.192 behebt fünf Spielfehler aus der Codeprüfung. Der
Seefernaufklärer kreist nicht mehr endlos um einen Bojenpunkt: Ab 4 sm vor dem
nächsten Punkt eines auf dem Hinflug befohlenen Musters fliegt er mit
Stationsfahrt, damit er auf ihn eindrehen kann. Mehr Fahrt hebt das
Schleppsonar nur an; die befohlene Tiefe bleibt und wird wieder erreicht, wenn
das Schiff langsamer wird. Eine Kontaktmeldung, die abbricht, weil der
Funkraum ausfällt, bringt keine Punkte, und spätere Rufe verdrängen treffende
Meldungen nicht mehr aus der Wertung. KI-U-Boote behalten die Peilung der
KW-Rufe der Fregatte wie eine eigene Sonarpeilung und handeln danach. In der
Freien Fahrt bringen Vorfälle keine weiteren Schiffe und Wale mehr, wenn die
See voll ist, ein zurückkehrendes U-Boot vergisst seinen alten Kontakt und
Angriff, und nur die Fregattenseite zahlt für ein versenktes neutrales U-Boot.
Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.191

Version 1.3.191 ordnet das Handbuch in 21 kurze Kapitel: ein Schnellstart
unter 1.500 Wörtern für beide Seiten, dann Hauptmenü, Optionen, jede
Fregattenstation mit denselben Teilen (Zweck, Seiten, Anzeigen, Tasten, Maus,
Standardablauf, Tipps, nicht modelliert), das U-Boot mit einem Abschnitt je
Station, Szenarien mit Tabellen für beide Seiten, Mehrspieler und
Server-Modus, nach dem Einsatz, Werkzeuge, Editoren, Sprachmodell,
Referenzdaten und ein Glossar; veraltete Aussagen sind am Spiel berichtigt. Im
Handbuch-Leser öffnet 0 den Schnellstart und 1 bis 9 die Stationen. Die README
beschreibt nicht mehr das entfallene Windows-Starterfenster. Im Inneren ist
langer Speicher- und Rücksetzcode in kleinere Teile zerlegt, doppelte
Peilungs- und Abstandshelfer sind zusammengeführt, und Torpedos ohne Zielpunkt
lesen nie ein verborgenes Ziel. Am Spiel ändert sich nichts. Spielstände sind
v50; v38 bis v49 lassen sich weiter laden.

## 1.3.190

Version 1.3.190 behebt zwei Fehler im Server-Modus des Browsers. Schaltet der
Spielleiter in der Lobby die Einheit um, wechselt jetzt jeder Browser auf die
Stationen dieser Einheit (gegen die KI); bisher blieb die Besatzung auf den
Stationen der alten Einheit. Eine volle Kopfleiste quetscht „Station
hinzufügen“ nicht mehr zu einer Spalte einzelner Buchstaben: Der Knopf bleibt
einzeilig, und die Leiste bricht in eine zweite Zeile um, statt rechts
abgeschnitten zu werden. Tasten bleiben gleich. Spielstände sind v50; v38 bis
v49 lassen sich weiter laden.

## 1.3.189

Version 1.3.189 verhindert, dass der Sonar-Ton auf der uConsole verstummt,
während alle anderen Geräusche weiterlaufen. Die Sonar-Wiedergabe überwacht
jetzt ihren eigenen Kanal: Ein Block, der die Warteschlange nicht mehr
verlässt, eine nach dem Einblenden auf null stehende Kanallautstärke, ein
Fehler im Wiedergabe-Thread, ein hinter voller Warteschlange angehaltener
Thread oder eine Hörposition vor dem Empfänger starten den Sonar-Ton nach
spätestens etwa einer Sekunde neu, ohne Audio aus- und einzuschalten. Im
U-Boot liegt der Sonar-Ton jetzt links oder rechts relativ zum eigenen Kurs
des U-Boots statt zu dem der Fregatte. Mit `U_JAGD_AUDIO_DEBUG=1` zählt
`audio_debug.log` jede solche Erholung (`wedged`, `volume_restored`,
`pump_errors`, `full_resets`). Tasten bleiben gleich. Spielstände sind v50;
v38 bis v49 lassen sich weiter laden.

## 1.3.188

Version 1.3.188 macht Abläufe und Speichern verlässlicher. Zwei Spiele mit
gleichem Seed laufen jetzt gleich ab, auch nacheinander ohne Neustart des
Programms (Radar und MAD des Seefernaufklärers, Kontaktmeldungen und
U-Boot-Sichtungen hängen nicht mehr an der internen Nummerierung). Jeder
Spielstand wird vor dem Schreiben geprüft, ein kaputter Stand kann also den
letzten guten Platz oder die Autosicherung nicht mehr überschreiben; die
regelmäßige Autosicherung prüft im Hintergrund, damit das Spiel flüssig
weiterläuft. Die Zielzeile des U-Boots nutzt jetzt den Koppelort statt der
wahren Position. Ungenutzte Schwellen sind entfernt, und das Handbuch sagt
jetzt, dass KI-U-Boote Kontakte der letzten 4 Minuten melden. Die Tasten
folgen dem gemeinsamen Schema genauer: Der F-Schuss des U-Boots feuert nur mit
Strg+Enter (Enter bestätigt die Entfernung), C klassifiziert auf der ESM-Seite
des U-Boots, W legt den Wegpunkt des Hubschraubers auf den gewählten Kontakt,
Enter nimmt auf der Funkseite Aufträge den gewählten Auftrag an, Rück auf
OPZ-Seite 5 setzt nur die gewählte Zeile zurück (Umschalt+Rück alles),
Umschalt+A pingt an der Führung des U-Boots jetzt auch auf der uConsole, und
die Wahl des echten Seegebiets wandert von Bild↑/↓ auf [ und ]. W, R und F
wirken nicht mehr unsichtbar in Lobby, Einsatzbuch und anderen Menüseiten. F1
zeigt an Bord des U-Boots dessen eigene Globaltasten, und das Einsatzbuch
nennt seine Tasten unten. Funktionen, die bisher eine Taste brauchten, gehen
jetzt auch per Klick: Ein Menüsymbol in der Kopfleiste öffnet Hilfe, Optionen,
Speichern, Laden, Wetter, Plot, die Crew-Automatik, SimLog, den Ersten
Offizier, den Analysator, Remote Crew, Nationen und Beenden, und jedes Fenster
hat ein Schließen-Kreuz; Sonar, OPZ (Ziel- und Begleiterseite) sowie Sonar und
Waffen des U-Boots bekommen anklickbare Tastenchips (Klassifizieren, TMA,
Freigabe, Schleppsonar, Düppel, Ziel zuweisen, Rohr fluten, Täuschkörper).
Feuern per Klick bleibt auf die Waffenstation beschränkt. Spielstände sind
v50; v38 bis v49 lassen sich weiter laden.

## 1.3.187

Version 1.3.187 bringt einen Server-Modus: Die uConsole dient nur als
Server, alle spielen im Browser, auf beiden Einheiten, allein oder gemeinsam.
Dazu im Hauptmenü „Server (nur Browser)“ wählen oder mit `--server` starten.
Die uConsole zeigt dann nur QR-Code, Beitrittscode und Besatzung, im Einsatz
einen Schiedsrichter-Bildschirm. Der erste Browser, der beitritt, leitet das
Spiel: In seiner Lobby wählt er Einheit, Einsatz (Szenario, Tagesmission,
Brennpunkt der Kampagne oder eigene Mission), Gegner, Wetter, Tageszeit und
Länge, startet den Einsatz für alle, speichert und lädt und holt alle zurück
in die Lobby. Die Besatzung behält ihre Stationen von Einsatz zu Einsatz, die
Leitung lässt sich abgeben. Tasten bleiben gleich. Spielstände sind v50; v38
bis v49 lassen sich weiter laden.

## 1.3.186

Version 1.3.186 behebt das helle Schema hinter den Menüs. Das Hauptmenü und
jedes Fenster über einem laufenden Einsatz (Hilfe, Optionen, Speichern und
Laden, Beenden) liegen jetzt auf einer hellen Tagesszene mit Sonne und hellem
Meer statt auf dem dunklen Nachtbild, so bleibt die dunkle Schrift gut
lesbar. Das Nachtschema sieht aus wie bisher. Tasten bleiben gleich.
Spielstände sind v50; v38 bis v49 laden weiter.

## 1.3.185

Version 1.3.185 hält den Remote-Crew-Gastgeber reaktionsfähig. Laden, neues
Spiel, Einsatzstart und Speichern aus dem Browser sowie die Passwortprüfung
des Web-Gastgebers halten die anderen Browser nicht mehr auf, Abfragen,
Sonar-Audio und Sprechfunk laufen weiter. Abfragen lesen nicht mehr jedes Mal
das ganze Lagebild einer Station neu. Fehlgeschlagene Anmeldungen und
Kopplungsversuche zählen jetzt je Adresse, ein Fremder kann den Gastgeber im
Web-Gastgeber-Raum also nicht mehr aussperren, und der Raum wechselt nach
seinen Versuchen nicht mehr den Code. Ein Beobachter, der die Ansicht
wechselt, unterbricht nicht mehr das Live-Audio des Sonarbedieners. Tasten
bleiben gleich. Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.184

Version 1.3.184 bringt die neuen Karten zur Schadensabwehr im Browser. Jede
Karte eines Leckwehrtrupps nennt seine Abteilung in der Spielsprache (vorher
standen dort interne Schlüssel) und zeigt, ob der Trupp bereitsteht, mit den
restlichen Sekunden unterwegs ist oder vor Ort arbeitet, mit passendem
Farbstreifen. Der Trupp für die nächste Zuweisung ist umrahmt, ein Klick auf
eine Karte wählt ihn. Die Handbuchbilder sind im hellen Schema neu
aufgenommen. Tasten bleiben gleich. Spielstände sind v50; v38 bis v49 laden
weiter.

## 1.3.183

Version 1.3.183 bringt Bilder ins Handbuch. Jede Station der Fregatte und
des U-Boots ist jetzt auf der uConsole und im Remote-Crew-Browser zu sehen,
dazu alle sechs Sonarseiten, Fernglas und Sehrohr bei Tag und Nacht,
Hauptmenü, Szenarioauswahl, Einweisung, Optionen, die Editoren und die
Kontaktanalyse, alles im hellen Schema Taktik Tag, damit ein Ausdruck wenig
Tinte braucht; Markdown- und PDF-Handbuch zeigen sie, der Leser im Spiel
lässt sie weg. Das U-Boot-Kapitel nennt jetzt jede Stationsseite mit ihren
Tasten. Die Schritte der ersten Patrouille passen wieder zum Hauptmenü, der
Schnellstart sagt, welche Funktionen noch eine Taste brauchen, und „U-Boot“
ersetzt „Boot“. Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.182

Version 1.3.182 bringt die drei Spalten zur Seite Auswahl & Teams der
Schadensabwehr. Links stehen die Abteilungen als Karten mit Zustandsstreifen,
Lampen für Wasser und Brand und den Trupps vor Ort, in der Mitte die Details
der gewählten Abteilung und rechts die drei Leckwehrtrupps mit ihrem Ziel und
ob sie unterwegs sind, vor Ort arbeiten oder bereitstehen. Ein Klick wählt eine
Abteilung oder einen Trupp; Enter schickt den Trupp wie bisher los. Auf der
Seite Mast & ESM des U-Boots wählt ein Klick auf eine Zeile der Senderliste
diesen Sender. Tasten bleiben gleich. Spielstände sind v50; v38 bis v49 laden
weiter.

## 1.3.180

Version 1.3.180 bringt die drei Spalten zu ELOKA, Funkraum und der
Waffenseite der Fregatte. ELOKA zeigt die Auffassungen links als Karten (ein
Klick wählt), in der Mitte die Bedrohungsrose und rechts die gewählte
Auffassung mit Signal und den Lampen für ESM und Störer. Der Funkraum hat links
die HF-Peilsignale als Karten, in der Mitte die Kreuzpeilkarte und rechts die
Peilrose mit dem Peilprotokoll. Die Waffenseite der Fregatte zeigt ihre
Sonarkontakte als Karten über den Einsatzstufen (ein Klick wählt, M weist zu).
Tasten bleiben gleich. Spielstände sind v50; v38 bis v49 laden weiter.

## 1.3.179

Version 1.3.179 behebt zwei Klicks, die einen Programmfehler auslösten:
den Dunkel/Hell-Schalter in der oberen Leiste (im Hauptmenü beendete er das
Spiel, im Einsatz sprang das Spiel auf den letzten Sicherungspunkt zurück)
und die Kontaktkarten auf der Waffenseite des U-Boots. Beide funktionieren
jetzt (das Farbschema wechselt, die Karte wählt ihren Kontakt). Tasten bleiben gleich. Spielstände sind v50;
v38 bis v49 laden weiter.

## 1.3.177

Version 1.3.177 bringt die neue Aufteilung in drei Spalten zu Sonar, OPZ und
der Waffenseite des U-Boots. Das Sonar zeigt seine Kontakte links als Karten
(Peilung, Klassifizierung, Balken für den Störabstand; ein Klick wählt einen
Kontakt), in der Mitte die Anzeige der Seite und rechts den Hörposten mit
seiner Rose. Die OPZ hat auf jeder Seite links Trackkarten, in der Mitte die
Karte und rechts das Statusfeld. Die Waffenseite des U-Boots zeigt
Kontaktkarten über der Schusslage und die Feuerleitung über den Rohrlampen;
an der Waffenstation feuert ein Klick auf das rote Feuerfeld wie Strg+Enter.
Die Tasten bleiben gleich; Spielstände sind v50, v38 bis v49 lassen sich
weiter laden.

## 1.3.176

Version 1.3.176 beginnt das neue Aussehen. Alle Bildschirme nehmen ihre
Farben jetzt aus einem gemeinsamen Satz Farbbausteine, den uConsole und
Remote-Crew-Browser teilen, und es gibt zwei Schemata: Taktik Nacht (dunkel,
Standard) und Taktik Tag (hell, der Sonar-Wasserfall als LOFAR-Papierschrieb
mit dunkler Tinte). Umschalten mit dem kleinen Schalter Dunkel/Hell rechts in
der oberen Leiste (anklicken) oder in den Optionen (F10) unter „Farbschema“,
wo auch hoher Kontrast zur Wahl steht; die Wahl steht in den Einstellungen,
nicht im Spielstand. Rotlicht erzwingt weiter das dunkle Schema und macht die Farben vorher grau, damit grüne Werte unter dem Rot lesbar bleiben. Felder sind
jetzt abgerundet mit leichtem Schatten und farbiger Titelmarke, Seitenreiter
sind Pillen und Tastenhinweise Chips. Tasten, Aufteilung und Spielstände
bleiben gleich; Spielstände sind v50, v38 bis v49 lassen sich weiter laden.

## 1.3.175

Version 1.3.175 folgt aus einer Prüfung des ganzen Codes. Waffentasten mit
Umschalt oder Strg feuern nicht mehr versehentlich: Umschalt+A (Ping) startet
an der Waffenstation keinen ASROC mehr und Strg+R (Luftfahrzeug-Radar) feuert
keinen Raketenwerfer mehr, und Umschalt+A schaltet auf dem U-Boot nicht mehr
die Schleichfahrt. Ein lauerndes U-Boot hält jetzt auch gegen einen Nord- oder
Südstrom, statt mit ihm zu treiben, und der Doppler eines Täuschkörpers rechnet
seine Fahrt in Knoten. Die Host-Seite im Browser kann die Beobachterrolle
vergeben und der Waffenstation des U-Boots das Direktfeuer entziehen, die
Browser-Stationen des U-Boots haben eigene Kurzhilfen und Handbuch-Links, und
vier Auswahllisten an Sonar und Heli springen beim Bedienen nicht mehr zurück.
Ein Spielstand, gespeichert während die Fregatte auf einer Untiefe
saß, lädt wieder, auch wenn die Flut inzwischen gestiegen ist.
Hilfetexte wurden berichtigt (Seite Aufträge, OPZ-Zoom, Tasten der
Nachbesprechung, deutsche Begriffe, „U-Boot“ statt „Boot“), und ungenutzter
Code ist entfernt. Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.174

Version 1.3.174 füllt das Einsatzprotokoll der Remote Crew. Es zeigte bisher
nur wenige Browser-Alarme und wirkte deshalb leer; jetzt listet jede Station
dieselben Einträge wie F11 auf der uConsole, das Neueste oben, mit Uhrzeit
und Kategoriekürzel: die Stationen der Fregatte das Log der Fregatte, die
Stationen des U-Boots das Bootslog. Ein langes Protokoll scrollt in seiner
Leiste und lässt der Karte ihren Platz. Auf der uConsole öffnet F11 jetzt
auch auf der U-Boot-Seite das Bootslog. Spielstände sind v50; v38 bis v49
lassen sich weiter laden.

## 1.3.173

Version 1.3.173 repariert die Update-Prüfung der macOS-App. Ihr
eingebautes Python suchte die Stammzertifikate in einem Ordner, den es nur auf
dem Baurechner gibt, deshalb scheiterte jede HTTPS-Anfrage an der Prüfung und
der Startbildschirm bot nie eine neuere Version an. Das Windows-Programm und
die macOS-App bringen jetzt eigene Stammzertifikate (certifi) zusätzlich zu
denen des Systems mit, was auch dem optionalen Sprachmodell und dem
Live-Flugverkehr über HTTPS hilft. Schlägt die Update-Prüfung fehl, sagen
Startbildschirm und Hauptmenü jetzt, dass und warum (keine Verbindung,
Zertifikat oder ein Fehler von GitHub), und U prüft erneut. Spielstände sind
v50; v38 bis v49 lassen sich weiter laden.

## 1.3.172

Version 1.3.172 bringt das Mikrofon der Geräuschdisziplin zum Laufen. Auf der
uConsole, unter Windows und auf dem Mac öffnete das Spiel das Gerät nie (die
Tonbibliothek verlangt den Namen des Geräts), die Anzeige blieb dunkel. Jetzt
öffnet es das Standardmikrofon des Systems, und wenn das nicht geht, sagt das
Spiel warum: eine Meldung im Einsatz und Ursache mit Abhilfe auf Seite 2 der
Optionen (kein Mikrofon, lässt sich nicht öffnen oder kein Ton, weil Windows
oder macOS den Zugriff sperrt). Die Mac-App fragt nach dem Mikrofonzugriff,
und die Windows- und Mac-Builds prüfen die Aufnahme vor der Veröffentlichung.
Browser erlauben das Mikrofon nur auf einer sicheren Seite: Auf der normalen
LAN-Seite sagt das jetzt ein Hinweis, und „HTTPS-Seite öffnen“ wechselt zur
HTTPS-Adresse des Hosts, wo Sie sich mit demselben Code neu koppeln.
Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.171

Version 1.3.171 gibt der OPZ eine reichere Karte und eine Anzeigeseite voller
Einstellungen. Seite 5 (Anzeige) stellt den Spurverlauf (aus, 3, 6 oder 12
Minuten), die Vektorlänge (3 bis 30 Minuten), volle, kurze oder keine
Beschriftung, eine Peilskala mit eigenem Kurs am äußeren Radarring,
Entfernungsringe, Peilstrahlen, Unsicherheitskreise, Tiefen und Gitter, das
Radar-Nachleuchten und den Punkt der nächsten Annäherung (CPA) des gewählten
Tracks mit Abstand und Zeit ein. Auf/Ab wählt eine Zeile, Links/Rechts ändert
sie, Backspace stellt den Standard wieder her, und jede Zeile ist anklickbar.
Schalter unter der Karte schalten die Ebenen auf jeder Seite, zwei Schalter
auf der Karte See- und Luftradar ein und aus. Die
Einstellungen bleiben in settings.json. Die OPZ im Browser hat dieselben
Knöpfe über ihrer Karte und zeichnet dieselben Ringe, Peilskala, Spuren und
den CPA. Nur Anzeige: die Simulation bleibt unverändert. Spielstände sind

## 1.3.170

Version 1.3.170 beruhigt zwei Geräusche, die an jeder Station alle paar
Sekunden wiederkamen. Der Bug der Fregatte schlägt bei schwerer See von vorn
nicht mehr hörbar ein (bisher bei fast jeder Welle, alle 5 bis 18 s). Tief
unten knarzte der Rumpf des U-Boots an der Testtiefe alle 4 s; jetzt ruht er
nach jedem Knarzen 12 bis 28 s. Beides ändert nichts an der Simulation. Spielstände sind
v50; v38 bis v49 lassen sich weiter laden.

## 1.3.169

Version 1.3.169 zeigt andere Schiffe im Fernglas des Ausgucks, im
Horizontstreifen, im Sehrohr, im Trefferbild, in den Remote-Crew-Karten und
im Handy-Ausguck so, wie das Auge sie sieht. Ein Schiff in der Nähe schwimmt
jetzt mit seiner Wasserlinie unter der Kimm, so weit, wie das Auge in der
gemessenen Entfernung auf das Wasser hinabsieht (etwa 1° auf 0,5 sm aus den
18 m der Brücke), statt wie ein fernes Schiff auf der Kimm zu sitzen, und
ein näheres Schiff steht vor einem ferneren statt in Listenreihenfolge.
Peilung und Lagewinkel wurden geprüft und stimmten schon: die
Steuerbordseite zeigt den Bug rechts, die Backbordseite den Bug links.
Spielstände sind v50; v38 bis v49 lassen sich weiter laden.

## 1.3.168

Version 1.3.168 bringt U-Jagd auf den Mac. Jede Version enthält jetzt auch
eine macOS-App, `U-Jagd-macOS-arm64.zip` für Apple-Silicon und
`U-Jagd-macOS-x86_64.zip` für Intel-Macs, gebaut und geprüft wie das
Windows-Programm. „Jetzt updaten“ im Startbild und Hauptmenü lädt das Zip
für den Prozessor des Macs, prüft Größe und Prüfsumme und tauscht die App
nach dem Beenden aus; die alte App bleibt erhalten, bis die neue an ihrem
Platz ist. Auch die Remote Crew findet die Netzwerkadresse des Macs. Die
README erklärt den ersten Start. Spielstände sind v50; v38 bis v49 lassen
sich weiter laden.

## 1.3.167

Version 1.3.167 lässt den Gegner Ihre Gewohnheiten lernen. Das Logbuch
merkt sich zu jedem beendeten Einsatz ein paar grobe Gewohnheiten: auf der
Fregatte einen frühen ersten Ping, eine schnelle Suche oder weite
Torpedoschüsse, auf dem U-Boot viel Zeit auf Sehrohrtiefe, Fahrt über der
Sprungschicht oder hohe Fahrt. Eine Gewohnheit, die in mehr als der Hälfte
Ihrer letzten fünf Einsätze einer Seite (mindestens drei) auftrat, kennt der
Gegner, und die KI stellt sich ein wenig darauf ein: U-Boote gehen früher
unter die Schicht oder halten Abstand, die Jagdfregatte sucht langsam, sprintet
und treibt. Die Nachbesprechung nennt, womit der Gegner
gerechnet hat. Die Logbuchseite zeigt, was er kennt, und `L` schaltet das
Lernen dort aus. In der Tagesmission, in Lektionen und im Spiel zweier
Besatzungen ist es immer aus. Spielstände sind v50 (sie behalten die für den
Einsatz festgelegten Gewohnheiten); v38 bis v49 lassen sich weiter laden.

## 1.3.166

Version 1.3.166 gibt dem eingebauten Gegner eigene Taktiken, ganz ohne
Sprachmodell. Jedes freie KI-U-Boot wählt einen Plan aus dem, was es selbst
gehört hat, und dem Charakter seines Kommandanten: heranschließen, unter der
Schicht lauern, nach einem Ping tief verstecken oder beschädigt abtauchen
und weglaufen. Die KI-Jagdfregatte wählt ihre Suche genauso, von der
schnellen Suche über Sprint und Treiben bis zur langsamen, leisen Suche. Es
sind die Planlisten des experimentellen Gegners, der weiterhin Vorrang hat,
wenn er eingeschaltet ist. Spielstände bleiben kompatibel.

## 1.3.165

Version 1.3.165 macht die Tests verlässlicher und den Code leichter zu
pflegen. Die Browser-Tests, die ab und zu fehlschlugen, warten jetzt, bis
die Seite wirklich bereit ist, ein Befehl des Spielleiters nach einem
Seitenwechsel geht nicht mehr verloren, und der Zwischenspeicher der
Schallstrahlen hängt nicht mehr von der Reihenfolge der Aufrufe ab. Große
Quellmodule (Sonar, Katalog, Szenariotabelle, Ereignis- und Bedienercode des
Spiels, Spielstandprüfung) sind ohne Verhaltensänderung in kleinere
aufgeteilt.

## 1.3.164

Version 1.3.164 behebt Spielstände, die das Spiel nicht laden wollte. Ein
KI-U-Boot, das sich an einen sehr lauten Kontakt erinnerte, schrieb einen
Wert, den die Spielstandprüfung nicht erlaubte, sodass sich manche
Spielstände langer Einsätze nicht wieder laden ließen; sie laden jetzt. Der
nächtliche Dauertest fährt alle Szenarien beider Seiten, nennt die genaue
Prüfung, die einen Spielstand abgelehnt hat, und hebt den abgelehnten
Spielstand zur Untersuchung auf.

## 1.3.163

Version 1.3.163 macht die Stationen per Mausklick bedienbar.
Statuslampen, Tastenhinweise im Text einer Station, Seitenreiter,
Listenzeilen und die Werte in der unteren Statuszeile reagieren jetzt auf
beiden Seiten auf einen Klick: Eine Lampe oder ein Hinweis drückt seine
Taste (etwa den ELOKA-Ton, das Spitzenhalten des Sonars, das Tauchsonar des
Hubschraubers, die Zeilen des Maschinentelegrafen oder die Schleichfahrt des
U-Boots), und ein Wert wie Flutung oder Torpedos öffnet die Station, die ihn
bearbeitet. Das Sonar des U-Boots nimmt erstmals Klicks an, und das Element
unter der Maus bekommt einen dünnen Rahmen. Ein Klick tut genau das, was
seine Taste tut, mit denselben Prüfungen; die Feuertaste bleibt nur an der
Waffenstation anklickbar. In der Remote Crew drückt ein Klick auf eine
Sonar-, Hubschrauber- oder Maschinenlampe ihren Knopf. Spielstände bleiben
v49; v38 bis v48 lassen sich weiter laden.

## 1.3.162

Version 1.3.162 zeigt der Brücke den eigenen Hubschrauber der Fregatte.
Sobald die Brücke ihn sehen kann, fliegt das Hubschraubermodell im Fernglas
des Ausgucks, im Horizontstreifen, in der Fernglas-Karte der Remote Crew, im
Handy-Ausguck und im Trefferbild an seiner wahren Position und mit seinem
Kurs: Er hebt vom Flugdeck achteraus ab, steigt weg, schwebt tief über
seinem Tauchsonar und zeigt nachts seine Positionslichter. Das Ausguck-
Sichtgerät markiert ihn als „eigener Hubschrauber“, das Panorama mit einem
grünen Strich, und die Liste unter dem Fernglas nennt ihn zuerst. Tief
fliegende Luftfahrzeuge stehen jetzt vor der See statt hinter den Wellen.
An den Meldungen des Ausgucks ändert sich nichts. Spielstände bleiben v49;
v38 bis v48 lassen sich weiter laden.

## 1.3.161

Version 1.3.161 hält die Beschriftungen der Seekarte auseinander. An der
Waffenstation trägt das zugewiesene Ziel ein einziges Label mit dem
Ping-Hinweis statt zwei übereinander, der Maßstab in der Kartenecke liegt
nicht mehr auf der ersten Gitterzahl, Fahrtangaben von Flugzeugen und
Kontakten bleiben im Kartenbild und weichen anderen Labels aus, und die
Auftragszeile des U-Boots steht unter dem Maßstab. Das OPZ-Lagebild und die
Kreuzpeilungskarte im Funkraum setzen ihre Labels genauso, und die
Browserkarten halten ihre Labels von den Achsenzahlen fern. Spielstände
bleiben v49; v38 bis v48 lassen sich weiter laden.

## 1.3.160

Version 1.3.160 zeichnet die Leckwehr wie eine echte Leckwehrtafel. Die
Fregatte ist ein Seitenriss mit Decks, Aufbauten und Masten, jede Abteilung
auf ihrer wirklichen Höhe, außen See und Wasserlinie mit Tiefgangsmarken,
Leckwasser, das sich mit dem Trimm neigt, offene Lecks mit einströmendem
Wasser, gesetzte Leckpflaster und Pumpen, die über Bord lenzen, und ein
Querschnitt, der mit dem Schiff krängt. Das U-Boot ist ein Schnittbild des
Druckkörpers mit Turm, Einbauten, Wasser, Brand, Chlorgas, Lecks und runden
Schotttüren, auf der uConsole und im Browser. Übernehmen-Knöpfe im Browser
(Suchkopf, Torpedoeinstellung, Antrieb, Hubschraubermuster) springen nicht
mehr kurz zurück, und das aktive Sonar des Begleitzerstörers pingt in jedem
Spiel mit gleichem Startwert gleich. Spielstände bleiben v49; v38 bis v48
lassen sich weiter laden.

## 1.3.159

Version 1.3.159 ersetzt die feste Missionsliste im Startmenü durch eine rollende.
Mit zwölf Szenarien je Seite und der Zeile für eigene Missionen lagen die
letzten Zeilen über den Welt- und Seed-Zeilen am unteren Bildrand.

- Die Szenarioliste zeigt neun Zeilen auf einmal in einem Feld mit Rollbalken
  und Pfeilmarken; der Ausschnitt folgt der Auswahl. `Auf`/`Ab` und das Mausrad
  gehen einen Schritt, `Bild auf`/`Bild ab` eine Seite (bei festem realem
  Sektor wählen sie weiter den Sektor), `Pos1`/`Ende` springen zur ersten und
  letzten Zeile.
- Unter der Liste steht der Anfang der Einsatzbesprechung des gewählten
  Szenarios (bei der Zeile für eigene Missionen, was sie öffnet).
- Eigene Missionen, die Schwierigkeitsliste der freien Jagd und die Lektionen
  rollen genauso; die Beschreibung einer eigenen Mission berührt die
  Tastenzeile nicht mehr.
- Zentrierte Menüzeilen, die breiter als der Bildschirm sind (große Schrift,
  lange Sektornamen), werden verkleinert, statt über beide Ränder zu laufen,
  und die Tastenzeile des Einsatzbuchs bleibt frei von der Sektorzeile.
- Die Liste „Neues Spiel“ im Browser nannte die Freie Fahrt „Unbekannt“; jetzt
  steht ihr Name dort, und der Browser nimmt bis zu 128 Szenarien an.
- Ein neuer Layouttest zeichnet jede Seite des Startmenüs auf Englisch und
  Deutsch, mit normaler und großer Schrift und mit festem realem Sektor, auch
  mit weit mehr Missionen als heute, und schlägt bei jeder überlappenden oder
  aus dem Bild laufenden Zeile fehl.

Spielstände bleiben v49; Spielstände v38 bis v48 lassen sich weiter laden.

## 1.3.158

- Im Browser sitzt der Knopf des Ersten Offiziers jetzt in der Werkzeugleiste
  neben dem Tonschalter; neben dem Missionsnamen hatte die volle Kopfzeile ihn
  zu einer Säule aus einzelnen Buchstaben gequetscht.

## 1.3.155

Version 1.3.155 macht das optionale Sprachmodell mit Denkmodellen wie Qwen3
nutzbar.

- Das Spiel bittet den Server um Antworten ohne Denkphase (`enable_thinking`
  aus, das verstehen vLLM und SGLang); ein Server, der den Schalter ablehnt,
  wird ohne ihn erneut gefragt, und danach immer ohne.
- Antworten, die als Liste von Teilen kommen, werden gelesen.
- Kommen nur Denkschritte zurück, melden Verbindungstest und Erster Offizier
  „nur Denkschritte, keine Antwort“ statt „Antwort nicht verwendbar“. Der Test
  darf bis zu 32 Token antworten.
- Der API-Schlüssel erscheint beim Tippen als Sternchen, und die Optionsseite
  nutzt den eingestellten Schlüssel, statt die Schlüsseldatei bei jedem Bild zu
  lesen.

Spielstände bleiben v49; Spielstände v38 bis v48 lassen sich weiter laden.

## 1.3.154

Version 1.3.154 bringt ein optionales Sprachmodell über eine
OpenAI-kompatible Schnittstelle (ein Server im LAN wie Ollama oder LM Studio
oder ein Cloud-Dienst). Es ist ab Werk aus, und das Spiel läuft genau wie
ohne; jede Aufgabe fällt auf die eigenen Texte des Spiels zurück, wenn der
Server aus oder langsam ist. Optionen Seite 2, Sprachmodell, stellt Adresse,
Modell, API-Schlüssel (in einer eigenen Datei oder der Umgebung, nie in
Einstellungen, Spielständen oder einem Browser), den Coach und den
experimentellen Gegner ein, mit einem Verbindungstest.

- Funkverkehr erscheint zusätzlich wie echter Funk formuliert neben dem
  Original, auf der Funkseite der Fregatte, im Funkraum des U-Boots und im
  Browser.
- Nach der Mission schreibt das Modell für jede Seite einen Einsatzbericht:
  `B` in der Nachbesprechung, in der Wiedergabe im Browser und im Dienstbuch.
- Der Erste Offizier (`F7`, im Browser eine Schaltfläche): Lagemeldung,
  Fragen aus dem eigenen Lagebild und dem Handbuch, getippte Befehle (Kurs,
  Fahrt, Tiefe, Schleichfahrt, Gefechtsstationen, nie Waffen), die erst nach
  Bestätigung gegeben werden, Klassifizierungshilfe und eine Einweisung für
  die Station. Ein Coach gibt ab und zu einen kurzen Tipp.
- Das Dienstbuch lässt die Dienstzeit vom Modell bewerten (`A`) und behält die
  Berichte (`B`). Missionen mit Hilfe des Beraters sind markiert und bekommen
  keine Bestwertung und keine Auszeichnung.
- Der Missionseditor (`G`, `Umschalt+G`) und der Missionsplaner im Browser
  schreiben eine Mission aus wenigen Worten; sie durchläuft dieselbe Prüfung
  wie jede eigene Mission und öffnet sich zum Prüfen.
- Ein experimenteller Gegner lässt das Modell alle 3 Minuten den Plan der
  KI-Seite aus einer festen Liste wählen; solche Missionen sind markiert und
  nie gewertet, und in Kampagne, Lektionen, Tageseinsatz und Spiel mit zwei
  Crews läuft er nie.
- Im Browser springen die Suchkopf-Einstellungen des U-Boots nach Übernehmen
  nicht mehr kurz auf die alten Werte zurück.

Spielstände sind jetzt v49 (die Berater-Markierung und der Plan des
experimentellen Gegners); Spielstände v38 bis v48 lassen sich weiter laden.

## 1.3.153

Version 1.3.153 lässt das U-Boot auftauchen. `Shift+H` (Browser: Auftauchen)
bringt das U-Boot nach oben; das Niederdruckgebläse bläst die Hauptzellen aus,
die Diesel laufen an der freien Luft mit bis zu 12 kn und laden schneller, und
eine Brückenwache sieht aus 6 m Höhe und meldet Flugzeuge als Alarm. Ein
aufgetauchtes U-Boot sehen das Radar der Fregatte, die Radare der
Luftfahrzeuge und die Ausgucks. `H` von der Oberfläche ist das Alarmtauchen:
Alarm, Masten ein, Flutventile auf, äußerste Kraft; ausgeblasene Zellen
halten das U-Boot oben, bis die Flutventile sie geflutet haben.
Speicherformat v48 unverändert.

## 1.3.152

Version 1.3.152 bringt den Tageseinsatz ins Hauptmenü: je Seite und Tag ein
fester Einsatz, für alle Spieler gleich, im echten Seegebiet des Tages und in
normaler Länge. Die Seite zeigt den heutigen Bestwert jeder Seite, und das
Einsatzbuch hält den besten Sieg jedes Tages 30 Tage. Speicherformat v48
unverändert.

## 1.3.151

Version 1.3.151 gibt jedem Computer-U-Boot-Kommandanten und dem Kapitän der
KI-Jagdfregatte einen Charakter: Draufgänger, Fuchs, Vorsichtiger oder Jäger.
Jeder ändert Angriffsrate, Ausweichen, Lauern oder bei der Jagdfregatte
Annäherung, Pings, Schussweite und Vorhaltezeit um einen Faktor. Die Führung
deutet ihn manchmal früh an, die Nachbesprechung nennt ihn. Speicherformat
v48 unverändert.

## 1.3.150

Version 1.3.150 bringt Geräuschdisziplin. Ab und zu lässt eine Besatzung ein
Werkzeug fallen oder schlägt ein Schott zu: ein kurzer Schlag, den der Gegner
bis 4 sm hören kann, häufiger bei einer müden Besatzung, seltener unter
Schleichfahrt, die dafür Reparaturen und Nachladen bremst. Auch die Stimmen
der Spieler zählen: die uConsole-Option Mikrofon und der Mikrofon-Knopf im
Browser zeigen den Pegel gegen die Schwellen (leise, in der Nähe hörbar, weit
hörbar), und eine zu laute Besatzung macht ihr Schiff oder U-Boot lauter. Es
wird nur die Pegelzahl gesendet, nie Ton. Speicherformat v48 unverändert.

## 1.3.149

Version 1.3.149 macht die Endphase eines zielsuchenden Torpedos hörbar: Sein
Suchkopf pingt langsam, solange er sucht, und schnell, sobald er aufgeschaltet
hat. Fregatte und U-Boot melden „Torpedo hat aufgeschaltet“ und „Peilung
steht“, und die Bedrohungsseite des U-Boots zeigt eine grobe Torpedouhr.
Speicherformat v48 unverändert.

## 1.3.148

Version 1.3.148 zeigt Treffer in einem kleinen Bild: Sieht die eigene Seite
einen Feuerball, die Wassersäule eines Torpedos oder ein sinkendes Schiff,
öffnet sich an jeder Station für 8 s ein Fenster in seine Peilung; ein nur
gehörter Treffer zeigt Peilung und Geräusch. Auf der uConsole und im Browser.
Speicherformat v48 unverändert.

## 1.3.147

Version 1.3.147 zeichnet Bugwellen und Kielwasser erkannter Schiffe in
Fernglas und Sehrohr, hoch und weiß bei schneller Fahrt, und gibt beiden
Optiken einen runden Rand. Speicherformat v48 unverändert.

## 1.3.146

Version 1.3.146 lässt nach einer nahen Detonation die Bildschirme des eigenen
Schiffs wackeln: innerhalb 0,6 sm wackelt das Bild und das Licht flackert,
innerhalb 0,15 sm springt kurz das Instrumentenglas. Nur Anzeige, auf der
uConsole und im Browser. Speicherformat v48 unverändert.

## 1.3.145

Version 1.3.145 bringt das Echolot in die Navigation des U-Boots im Browser:
der gelotete Meeresgrund der letzten zehn Minuten neben der eigenen Tiefe,
wenig Wasser unter dem Kiel gelb und rot, und das Kartenprofil voraus auf dem
befohlenen Kurs mit dem Hindernis, das der Kartencheck gefunden hat.
Spielstandformat v48 unverändert.

## 1.3.144

Version 1.3.144 lässt die uConsole auf beiden Seiten schneller zeichnen.
Textbreiten, umbrochene Zeilen und gezeichnete Texte werden gemerkt und
wiederverwendet, und das Rotlicht der Schleichfahrt mischt nicht mehr zweimal
pro Bild den ganzen Schirm. In einem Messlauf ohne Bildschirm braucht ein
U-Boot-Bild etwa ein Viertel der Zeit, mit Schleichfahrt etwa ein Sechstel,
ein Fregatten-Bild weniger als die Hälfte. `tools/bench_draw.py` misst jede
Station beider Seiten. Spielstandformat v48 unverändert.

## 1.3.143

Version 1.3.143 gibt der Navigation des U-Boots Koppelnavigation und eine
Route. Getaucht wandert der gekoppelte Ort langsam vom wahren weg (bei einem
Atomboot weniger); ein GPS-Fix mit 20 s Mast oben an Sehrohrtiefe setzt ihn
zurück. Die Karte der Crew liegt dort, wo der Navigator sie vermutet,
Kartencheck voraus und Route rechnen von diesem Ort, und die Lotsenkarte zeigt
die Fehlerschätzung und das Alter des Fixes. Ein Rechtsklick in die Karte setzt
einen Wegpunkt, `W` legt eine Zickzack- oder Quadratsuche und `Rücktaste`
löscht die Route; der Browser hat dieselben Knöpfe und einen Klickmodus.
Spielstände wechseln auf Format v48; v38 bis v47 lassen sich weiter laden.

## 1.3.142

Version 1.3.142 lässt die Waffenstation des U-Boots den Suchkopf der nächsten
Schüsse wie auf der Fregatte einstellen: Suchmuster gerade, Schlange, Kreis
oder Helix (`X`) und den Einschaltpunkt 0,6 bis 3,0 sm vor dem Datum (`,` und
`.`), im Browser auf der Waffen-Karte. Die Vorgaben behalten den bisherigen
Schuss. Spielstandformat v48.

## 1.3.141

Version 1.3.141 ergänzt das Handbuchkapitel „U-Boot" mit der Aufgabe jeder
Bootsstation und einem Standardablauf in fünf Schritten für alle sieben
Stationen. F1 zeigt auf der U-Boot-Seite den Ablauf der besetzten Station, und
der Handbuchleser öffnet beim U-Boot-Kapitel. Spielstandformat v47 unverändert.

## 1.3.140

Version 1.3.140 bringt drei neue uConsole-Seiten. Die Navigation des U-Boots
öffnet mit einer Lotsenkarte samt Echolot: Kartentiefen um das Boot, zu tiefes
Wasser rot, der befohlene Kurs voraus, der Meeresgrund der letzten zehn Minuten
und die Tiefe voraus; ein Klick in die Karte befiehlt den Kurs. Die Statusseite
des Hubschraubers ist eine Konsole mit Lampen, Tank, Rückkehrrose und
Beladung. Die erste Seite des Funkraums zeigt die Funkpeilungen und Standorte
auf einer Karte neben der Empfangsliste. Spielstandformat v47 unverändert.

## 1.3.139

Version 1.3.139 gleicht die Szenarien 11 bis 20 in voller Länge aus, gemessen
mit KI-gegen-KI-Partien über je sechs Seeds. Bei Fühlung halten muss die
Fregatte jetzt 80 % der Zeit Kontakt halten, und ein verlorener Kontakt zählt
früher. Im Duell beginnt das U-Boot 8 bis 12 sm entfernt, das Ziel von
Angeschlagen heim liegt näher, und bei Seenot unter Bedrohung beginnt die
Fregatte weiter von den Rettungsinseln entfernt. Die Suchgruppe dauert jetzt
4 Stunden, das erste U-Boot beginnt 8 bis 14 sm entfernt, und in der
Jagdgruppe beginnt das U-Boot 4 bis 6 sm entfernt, mit dem Ziel knapp hinter
der Fregatte und 90 Minuten Zeitlimit. Die Kurzeinsätze bleiben unverändert. Spielstandformat v47 unverändert.

## 1.3.138

Version 1.3.138 macht aus der Kampagne einen Feldzug für beide Seiten. Eine
Karte des Sektors zeigt drei offene Brennpunkte, jeder eines der Szenarien der
Seite mit einer Rolle (Patrouille, Angriff, Verteidigung), dazu die
Entscheidung, sobald die Lage 75 erreicht. Siege und Niederlagen verschieben
Lage und Feindstärke, liegen gelassene Verteidigungen zählen als Verlust, und
neue Brennpunkte öffnen nach der Lage, so verzweigt sich der Feldzug. Er endet
mit Sieg, Niederlage oder nach zwölf Einsätzen unentschieden. Ältere Kampagnen
laufen mit ihren Ergebnissen weiter. Spielstandformat v47 unverändert.

## 1.3.137

Version 1.3.137 bringt die Gruppenjagd. In den neuen Szenarien Suchgruppe
(Fregatte 11) und Jagdgruppe (U-Boot 11) fährt der Zerstörer LUETJENS mit der
Fregatte. OPZ-Seite 4 und die OPZ im Browser führen ihn: Formation, einen
Punkt absuchen oder verfolgen, halten oder selbständig, Aktivsonar,
Waffenfreigabe und ASROC auf Befehl. Seine Passivpeilungen kreuzen sich mit
denen der Fregatte zu Standorten, und seine Pings orten nahe U-Boote.
Spielstände wechseln auf Format v47; Spielstände v38 bis v46 lassen sich weiter
laden.

## 1.3.136

Version 1.3.136 lässt zwei Crews gegeneinander spielen. Die neue Lobby-Zeile
Gegner schaltet zwischen KI und zweiter Crew: Browser kommen zur Fregatte
(blau) oder zum U-Boot (rot), je nachdem, wo weniger Leute sind, die Teams
bleiben für die Runde fest, jede Einheit hat ihren eigenen Sprechfunk, und
jedes Team erhält sein eigenes Ergebnis. Mit der Lobby-Station „keine, nur
Gastgeber“ zeigt die uConsole einen Schiedsrichter-Bildschirm ohne das
Lagebild einer Seite. Spielstandformat v46 unverändert.

## 1.3.135

Version 1.3.135 bringt Freie Fahrt als letzten Eintrag beider Seiten: kein
Zeitlimit, einfach fahren. Das Hauptquartier schickt laufend Funkaufträge (die
Fregatte bekommt zusätzlich Sektorpatrouillen, das U-Boot Angriffs-, Landungs-,
Versorgungs- und Aufklärungsbefehle), dazu kommen zufällige Begegnungen und
Ereignisse: U-Boote, Handelsgruppen, Luftangriffe, KI-Jäger, Zwischenfälle auf
See. Punkte sammeln sich, solange Schiff oder Boot schwimmt; Wetter und
Uhrzeit wählt man wie gewohnt beim Start. Spielstände wechseln auf Format v46;
Spielstände v38 bis v45 lassen sich weiter laden.

## 1.3.134

Version 1.3.134 bringt zehn neue Szenarien, damit hat jede Seite zehn. Die
Fregatte bekommt 5 Geleitschutz, 6 Brennendes Datum, 7 Fühlung halten (Frieden,
Waffen gesperrt, Sonarkontakt halten), 8 Versorgung auf See, 9 Seenot unter
Bedrohung und 10 Hafenschutz; das U-Boot bekommt 7 Duell, 8 Angeschlagen heim,
9 Agenten abholen und 10 Lauschposten. Taste `0` wählt die zehnte Zeile. In
jedem spielt eine KI die Gegenseite, jedes hat einen Kurzeinsatz, und in
KI-gegen-KI-Partien gewinnen beide Seiten. Spielstände wechseln auf Format
v45; Spielstände v38 bis v44 lassen sich weiter laden.

## 1.3.133

Version 1.3.133 lässt eigene Missionen für beide Seiten bauen und teilen. In der
Übersicht des Missionseditors kann die Spielerseite jetzt die Fregatte oder ein
selbst platziertes U-Boot sein (die KI besetzt dann die Fregatte), und der
Editor gibt Fairness-Hinweise. Eigene Missionen stehen im Startmenü (`O`), in
der Mehrspieler-Lobby und im Dialog „Neues Spiel“ des Browsers. `Strg+E` teilt
eine Mission mit ihren eigenen Einheiten in den Austauschordner
`~/.u-jagd/share`, `Strg+I` listet und importiert die Dateien dort, und `O`
öffnet den Ordner. Im Solo-Modus hat der Browser eine Seite „Eigene Missionen“
zum Auflisten, Herunterladen, Hochladen, Bearbeiten, Löschen und Starten, mit
einem Missionsplaner auf einer Sektorkarte. Speicherformat v44 unverändert.

## 1.3.132

Version 1.3.132 zählt die Szenarien jeder Seite ab 1. Die Fregatte zeigt
1 Patrouille, 2 Doppeljagd, 3 Nuklearer Abfang, 4 Freie Jagd; das U-Boot
1 Durchbruch, 2 Aufklärung, 3 Geleitzug, 4 Meerengen-Sperre, 5 Kampfschwimmer,
6 Versorgerschutz, und die Zifferntasten folgen der Liste auf dem Bildschirm.
Das Handbuch zählt die U-Boot-Szenarien genauso. Speicherformat v44
unverändert.

## 1.3.131

Version 1.3.131 bringt Kurzeinsätze. Briefing, Kampagnenbildschirm,
Mehrspieler-Lobby und der Dialog „Neues Spiel“ im Browser haben jetzt eine
Zeile Länge: Jedes feste Szenario außer der freien Jagd lässt sich als
Kurzeinsatz von 30 bis 60 Minuten spielen, mit demselben Ziel, kürzerem
Zeitlimit und einem Start näher am Geschehen, sodass eine Mission in einen
Abend oder eine Pause passt. Jeder Kurzeinsatz wurde mit KI-gegen-KI-Partien
so eingestellt, dass Fregatte und U-Boot etwa gleich oft gewinnen. Spielstände
bleiben im Format v44.

## 1.3.130

Version 1.3.130 bringt unter Optionen eine Grafikstufe: „Sparsam“ schont den
Prozessor der uConsole (kein Radar-Nachleuchten, ruhigerer Menühintergrund),
„Normal“ zeigt alle Effekte und „Voll“ glättet zusätzlich die Kartenlinien;
die uConsole startet mit Normal, Windows mit Voll. In einem Fenster oder
Vollbild größer als 1280 x 720 wird das Bild jetzt scharf skaliert: ganze
Faktoren wiederholen Pixel exakt, andere Größen zeigen keine ungleichmäßigen
Textzeilen und keine Unschärfe mehr. Die Stufe ändert nie, welche
Informationen eine Station zeigt. Spielstände bleiben im Format v44.

## 1.3.129

Version 1.3.129 macht das Spiel robuster. Ein nächtlicher Dauertest spielt
jetzt jede Mission auf beiden Seiten je eine Stunde lang mit zufälligen
Eingaben an allen Stationen, speichert und lädt dabei, und legt bei jedem
Fehler eine Fehlermeldung an. Sein erster Lauf fand, dass eine U-Boot-Mission,
die mit ausgewähltem Sonarkontakt gespeichert wurde, nicht mehr geladen werden
konnte; das ist behoben. Spielstände bleiben im Format v44.

## 1.3.128

Version 1.3.128 rettet Spielstände über Updates. Ein Speicherplatz oder
Autosave einer älteren Version, zurück bis Version 1.3.98 (Spielstandformat
v38), lädt jetzt: Er wird Schritt für Schritt auf das aktuelle Format gebracht
und danach so streng geprüft wie bisher, sodass ein Update keine unterbrochene
Mission mehr verwirft. Der Update-Hinweis warnt nur noch, wenn Spielstände zu
alt für das neue Release sind. Gespeichert wird im Format v44.

## 1.3.127

Version 1.3.127 hält eine Mission am Leben, wenn etwas schiefgeht. Eine
Stationsanzeige, die sich nicht zeichnen lässt, zeigt jetzt „Anzeige gestört“,
während die Mission und alle anderen Stationen weiterlaufen. Ein Fehler in der
Simulation setzt die Mission auf ihren Wiederherstellungspunkt zurück, eine
Kopie im Speicher von höchstens einer Minute, und meldet das im
Ereignisprotokoll; Browser der Remote Crew bekommen ihre Stationen wie nach
dem Laden zurück. Nach wiederholten Fehlern oder einem Fehler, der das Spiel
doch beendet, wird der Wiederherstellungspunkt zum Autosave, sodass „Einsatz
fortsetzen“ die Mission weiterführt. Jeder abgefangene Fehler landet für einen
Fehlerbericht in crash.log. Spielstände bleiben im Format v44.
## 1.3.126

Version 1.3.126 ordnet die Szenarien nach Seiten. Nach „Neues Spiel“ wählst
du zuerst Fregatte oder U-Boot, und die Liste zeigt danach nur die Einsätze
dieser Seite: Patrouille, Doppeljagd, Nuklearer Abfang und Freie Jagd auf der
Fregatte; Durchbruch, Aufklärung, Geleitzug, Meerengen-Sperre, Kampfschwimmer
und Versorgerschutz auf dem U-Boot. Die Titel verlieren deshalb den Zusatz
„(U-Boot)“, der so wirkte, als solle die Fregatte sie spielen. Die
Mehrspieler-Lobby und der Dialog „Neues Spiel“ im Browser filtern genauso, und
Esc in der Szenarienliste führt zurück zur Seitenwahl. Speicherformat v44
unverändert.

## 1.3.125

Version 1.3.125 bringt drei neue Einsätze, die beide Seiten spielen können,
jeweils mit der KI auf der Gegenseite. In „Meerengen-Sperre“ (8) muss das
U-Boot durch die nächste Meerenge schlüpfen, während die Fregatte die
Sperrlinie bewacht; Handelsverkehr fährt hindurch, und ein KI-Boot versteckt
sich in seinem Lärm. Bei „Kampfschwimmer“ (9) muss das U-Boot zehn Minuten auf
Sehrohrtiefe und in langsamster Fahrt vor einer Küste liegen, um seine
Schwimmer auszuschleusen, und die Fregatte bestreift den Küstenabschnitt. Beim
„Versorgerschutz“ (10) sichert die Fregatte einen zackenden Versorger, und ein
einziger Torpedotreffer entscheidet. Die Orte ergeben sich aus der echten oder
erzeugten Küste jeder Welt. Das Szenariomenü nimmt die Tasten 1 bis 9 und 0. In
Testläufen KI gegen KI (je sechs Seeds) ging jeder neue Einsatz dreimal für
jede Seite aus: Das KI-U-Boot schleicht mit 4 kn, überhört Pings aus mehr als
5 sm, schießt auf einen näheren zurück und gibt in der Meerenge und vor der
Küste einen Schnellschuss auf eine laute Fregatte ab; sechs Handelsschiffe
pendeln durch die Meerenge, und das HQ meldet der Fregatte in den Szenarien 8
und 9 kein U-Boot-Datum. Speicherformat v44; ältere Spielstände laden nicht.

## 1.3.124

Version 1.3.124 gleicht KI-Fregatte und KI-U-Boot an. In den
Fregatten-Szenarien folgen die KI-Jäger jetzt der Startmeldung der Führung
über die Bedrohung und einer verlorenen U-Boot-Peilung, pingen auf eine bloße
Peilung nur alle 10 Minuten, damit ein Ping ohne Treffer das U-Boot nicht mehr
davonjagt, und halten ein lange strahlendes Schiffsradar nicht mehr für einen
U-Boot-Mast. In den U-Boot-Szenarien hält ein Missions-U-Boot bei einem Ping
seinen Kurs und weicht nur einem Torpedo aus, und die Fregatte bewacht ihren
Posten: Gegen einen Durchbruch bleibt sie ohne Seefernaufklärer bei ihrer
Patrouillenposition, gegen Durchbruch und Aufklärung schießt sie ihren eigenen
Torpedo erst ab 3 sm und hält ihren Hubschrauber innerhalb 8 sm. Das
Durchbruch-U-Boot umgeht die Patrouillenposition der Fregatte, die
Aufklärungsmeldung zählt innerhalb 5 sm, und das Geleitzug-U-Boot schießt ab
3 sm. Spielstände wechseln auf Format v43 (die Spuren der Jäger).

## 1.3.123

Das U-Boot bekommt eine Bojenantenne. Im Funkraum (B oder die Funkraum-Karte im
Browser) bringt die Crew sie etwa 280 m achteraus aus; sie nimmt den Rundspruch
der Führung bis 60 m Tiefe bei höchstens 6 kn auf, nur Empfang. Über 10 kn
reißt das Kabel, und die Boje ist für die Mission verloren. Aus der Nähe können
Ausguck und Überwasserradar der Fregatte die kleine Boje auf dem Wasser finden.
Spielstände haben jetzt Format v42; ältere laden nicht.

## 1.3.122

Version 1.3.122 macht die Browser-Stationen ruhiger in der Bedienung. Eine
Auswahlliste, die offen ist oder gerade bedient wird, etwa die ESM-
Klassifizierung auf dem U-Boot, das Ziel der Feuerleitung oder die Auswahl von
Draht, Torpedotyp und Leckwehrtrupp, klappt bei einer Aktualisierung der Station
nicht mehr zu und verliert ihre Auswahl nicht; sie zieht nach, sobald man sie
verlässt. Schaltflächen in sich aktualisierenden Listen (ESM-Emitter, Rohre,
Schotten, Funkkanäle und Aufträge, Befehle an Besatzung und Seefernaufklärer)
bleiben stehen, sodass ein Klick nicht mehr verloren geht, wenn mitten im Klick
eine Aktualisierung eintrifft. Spielstände bleiben im Format v41.


## 1.3.121

Notfälle an Bord ergänzen die Ereignisse auf See. Auf der Fregatte kann ein
Mann über Bord gehen: Die Generalalarmglocke schlägt an, eine treibende Marke
kommt in die Karte, und die Brücke nimmt ihn bis 0,1 sm mit höchstens 5 kn auf,
oder der Hubschrauber schwebend über ihm (+100 Punkte; nach 20 Minuten
verloren, -300). Die Rudermaschine kann ausfallen: 60 s klemmt das Ruder, dann
10 Minuten halbe Drehrate vom Notruder. Auf einem Diesel-U-Boot kann das
Schnorchelkopfventil klemmen (15 Minuten kein Laden; das KI-U-Boot bleibt tief)
oder Batteriegas muss abgelüftet werden (halbe Laderate). Die KI-Hilfe der
Brücke steuert selbst auf einen Mann über Bord. Bis zu sechs Ereignisse je
Mission.

## 1.3.120

Version 1.3.119 bringt Bordatmosphäre in den Ton. Gefechtsstationen auf der
Fregatte lassen die Alarmglocke durch das Schiff läuten, und in schwerer See
von vorn schlägt der Bug bei Fahrt hörbar ein, sobald er tief eintaucht. Das
U-Boot läutet nur eine leise Alarmklingel, und seine Lüfter laufen beim
Einschalten der Schleichfahrt hörbar aus und beim Aufheben wieder an. uConsole
und Remote-Crew-Browser spielen dieselben Geräusche, alle zur Laufzeit erzeugt.

## 1.3.119

Version 1.3.118 lässt Wetter und Uhrzeit wählen. Das Briefing jedes Szenarios,
der Kampagnenbildschirm vor dem Auslaufen, die Mehrspieler-Lobby und der Dialog
„Neues Spiel“ im Browser bieten jetzt Wetter (Zufall, schön, Regen, Sturm,
Nebel) und Uhrzeit (Zufall, Morgengrauen, Tag, Abenddämmerung, Nacht); Zufall
behält, was der Seed ergibt. Ein gewähltes Wetter hält die ganze Mission mit
einem passenden Seegang, und die Uhr läuft von der gewählten Zeit weiter.

## 1.3.118

Version 1.3.117 lässt das Auge ein ausgefahrenes Sehrohr finden. Sehrohr oder
Schnorchelkopf eines getauchten U-Boots ziehen jetzt eine Schaumfahne, die mit
der Fahrt wächst: Brückenausguck, Handy-Ausguck und die Besatzungen von
Helikopter und Seefernaufklärer sehen die volle Fahne ab 8 kn an einem klaren,
ruhigen Tag auf knapp 3 sm, einen langsamen Kopf erst auf etwa 1 sm und nachts
oder bei schwerer See kaum etwas. Aus der Nähe erkennt der Ausguck das Sehrohr
und meldet es mit Banner; Sichtungen der Flugzeugbesatzungen erreichen die OPZ
als HELO-EYE- und MPA-EYE-Tracks. Das gilt für KI-U-Boote und das besetzte
U-Boot gleich, dessen Crew „Schaumfahne sichtbar, Fahrt verringern“ warnt, wenn
es mit oben stehendem Mast schneller als 5 kn läuft.

## 1.3.117

Version 1.3.117 erweckt die See zum Leben. Die Optiken zeigen Wassersäulen,
Feuer, Rauch und sinkende Schiffe; Karten bewegen sich weich, Pings und
Detonationen breiten sich als Ringe aus; Zeiger und Telegraf bewegen sich mit
Masse und die Telegrafenglocke läutet; das Sehrohr kommt aus dem Wasser, mit
Wasser auf dem Glas. Nachts und bei Alarm geht Rotlicht an (abschaltbar), und
die Stationsreiter tragen Alarmlampen auf beiden Seiten, auf der uConsole und im
Browser. Nach einer Mission läuft die Nachbesprechung als Zeitraffer mit 10×
oder 60×, auch im Browser. Nachts leuchtet warmes Wasser, wo es aufgewühlt wird,
sodass Kielwasser und Torpedobahnen auf beiden Seiten weiter zu sehen sind. Eine
harte Drehung mit Fahrt hinterlässt ein Knuckle, ein Blasenfeld, das das Sonar
dämpft, ein Falschecho gibt und einen kielwassersuchenden Torpedo ablenken kann.
Wracks und Felsen geben Echos, Wracks MAD-Anomalien. Stürme bringen Blitze in
den Optiken, Donner, stärkeren Regen und Sferics, die auf dem ESM knistern und
HF/DF-Peilungen streuen. Bei schwerer See startet und landet der Hubschrauber
nur in einer ruhigen Phase; eine Deckbewegungsanzeige zeigt sie, und weniger
Fahrt hilft. Spielstände haben jetzt das Format v41; ältere Spielstände laden
nicht.


## 1.3.116

Version 1.3.116 gibt derselben Funktion an jeder Station dieselbe Taste, auf
der Fregatte wie auf dem U-Boot. Strg+Enter ist die einzige Feuertaste (T und E
feuern nicht mehr), Q/E zoomen überall, auch den OPZ-Radarbereich, das Fernglas
und das Sehrohr, und Bild auf/ab blättern an jeder Station. Kurs, Fahrt und
Tiefe werden auf beiden Seiten mit C/V/D eingegeben, die Torpedo-Lauftiefe mit
T. Das U-Boot nutzt jetzt wie die Fregatte G für Gefechtsstationen, A für
Schleichfahrt, V für den Täuschkörper und W/M/U auf der Besatzungsseite; der
Seefernaufklärer hat die Tasten des Helikopters, beide Luftfahrzeug-Radare
liegen auf Strg+R, und Helikopter und ELOKA folgen dem Sonar (Shift+A Ping,
G Freigabe an die OPZ, J Ton). Ein Klick auf das Meldungsfenster der Crew
geht nicht mehr an eine Stationstaste darunter.

## 1.3.115

Version 1.3.115 setzt neue Spieler in einer sinnvollen Reihenfolge an die
Stationen. Ein Browser, der bei offener Mehrspieler-Lobby koppelt, bekommt jetzt
die erste freie Station der Einheit des uConsole, zuerst die Stationen, die
Urteil brauchen: auf der Fregatte Brücke, Sonar, Waffen, Hubschrauber, OPZ,
EloKa, Funk, Maschine und Schadensabwehr, auf dem U-Boot Führung, Sonar, Waffen,
Mast und ESM, Navigation, Maschine und Funkraum. Die Routinestationen hält die
KI-Crew gut. Jeder Spieler kann Einheit und Station weiter jederzeit wechseln.

## 1.3.114

Version 1.3.114 lässt den Befehl eines Spielers vor der KI-Crew gelten. Im
Mehrspieler mit Crew-Hilfe tauchte das KI-Kommando das U-Boot alle paar
Sekunden weg und holte so das Sehrohr ein, das ein Spieler am Mast oder im
Funkraum ausgefahren hatte; jetzt hält es das Boot auf Sehrohrtiefe, solange
ein Spieler den Mast oben hält. Eine Station, die die KI besetzt, übersteuert
nicht mehr, was ein Spieler an einer anderen Station befiehlt: Kurs, Tiefe und
Ausweichen bleiben bei einem Spieler an der Navigation, Fahrt und Schleichfahrt
bei einem im Maschinenraum, Trimm und Leckwehr bei einem am Kommando, und ein
ausgefahrener Mast bleibt bei Alarm oben, solange ein Spieler am Kommando oder
im Funkraum ihn hält. Auf der Fregatte steuert die KI-Brücke nicht mehr über
einen Spieler im Maschinenraum hinweg, KI-Waffen und Seefernaufklärer behalten
ein Ziel, das ein Spieler bestimmt hat, und ein am uConsole gewählter Kontakt
bleibt gewählt. Eine Lobby-Runde ohne Browser ist jetzt ein Solospiel mit
ausgeschalteter Crew-Hilfe.

## 1.3.113

Version 1.3.113 macht die uConsole komplett mit der Maus spielbar und die
Karten und den Schiffsverkehr leichter lesbar. Ein Klick auf eine Taste in der
Tastenleiste einer Station drückt sie (gehalten wie die Taste), nummerierte
Reiter in der Kopfzeile wechseln die Station, ein Klick auf die Kurs-, Fahrt-
oder Tiefenscheibe befiehlt diesen Wert, Zahleneingaben zeigen ein Tastenfeld,
Menü- und Dialogzeilen sind anklickbar, das Mausrad blättert durch Menüs und
ein Rechtsklick bricht ab. Jede Karte zeigt jetzt die eigene Kursspur, die
früheren Positionen jedes Kontakts und die früheren Peilungen des gewählten
Kontakts, und Kartenbeschriftungen weichen einander aus, statt sich zu
verdecken. Frachter, Tanker und Passagierschiffe laufen auf festen Kursen
zwischen Häfen und dem Rand des Seegebiets, weichen einander nach den
Kollisionsverhütungsregeln aus und laufen vor nahen Detonationen davon.

## 1.3.112

Version 1.3.112 macht den Mehrspieler für den Gastgeber einfacher. F9 ist
jetzt ein Schalter, Mehrspieler an oder aus: Er nimmt die erste lokale
Netzwerkadresse oder öffnet ohne Netz den eigenen Hotspot der uConsole;
Netzwerkmodus, Adresse und Port liegen unter den erweiterten Einstellungen.
Der Hotspot behält Name und Passwort, der uConsole-Installer richtet ihn ein,
und Lobby und F9 zeigen zwei Schritte: den WLAN-QR-Code, dann den QR-Code der
Crew-Seite. Ein Browser, der eine Station anfragt, die ein anderer Spieler
hält, fragt jetzt diesen Spieler, der sie im Browser übergeben kann; jede
Station hat immer alle ihre Rechte. Die Kommandozeile hat einen Schalter,
--multiplayer, der die Lobby öffnet, und das Windows-Programm startet ohne
Starter-Fenster direkt ins Spiel.

## 1.3.111

Version 1.3.111 bringt auf beiden Seiten eine Schusslage in die Feuerleitung.
Die Waffenstation der Fregatte und die Waffenseite des U-Boots zeigen jetzt,
genordet um das eigene Schiff, die Reichweite des Torpedos, die Peilung zum
Ziel und, sobald eine Entfernung vorliegt, die geschätzte Position, den
Treffpunkt aus TMA-Kurs und -Fahrt und die Torpedolaufbahn dorthin, allein
aus der Beobachtung des Kontakts. Führung und Navigation des U-Boots haben
beschriftete Rundinstrumente für Kurs, Tiefe (Test- und Zerstörungstiefe markiert) und
Fahrt wie die Brücke der Fregatte, und die Kästen im Funkraum des U-Boots
passen wieder zu ihrem Text, sodass der Befehl der Führung nicht mehr durch
den Rahmen läuft.

## 1.3.110

Version 1.3.110 installiert Updates nicht mehr von selbst. Gibt es ein neueres
Release, zeigen Startbildschirm und Hauptmenü dessen Version, den Eintrag aus
dem Änderungsprotokoll in der Spielsprache und eine Warnung, wenn Spielstände
dieser Version (auch die automatische Sicherung) damit nicht mehr laden, dazu
den Knopf **Jetzt updaten** (Taste U oder Klick). Erst dieser Knopf installiert
es: Auf der uConsole schließt das Spiel, aktualisiert sich auf das Release und
startet neu (der alte Hintergrund-Update-Timer schaltet sich selbst ab); das
Windows-Programm lädt die neue Datei im Hintergrund, prüft sie, tauscht sich
aus und startet neu. Ohne Netz erscheint kein Hinweis.

## 1.3.109

Version 1.3.109 lässt die KI jede freie Station besetzen. Die neue Crew-Hilfe
(Shift+F2, in einer Mission aus der Mehrspieler-Lobby immer an) bemannt jede
Station der Fregatte und eines bemannten U-Boots, die niemand hält, damit
jeder Spieler bei einer Station bleiben kann: Die Station auf dem Bildschirm
der uConsole und jede Station, die ein Browser hält, bleiben bei ihrem
Spieler, und eine im Browser freigegebene Station („An KI übergeben“) geht
sofort an die KI zurück. Auf dem U-Boot weicht die KI aus, patrouilliert oder
läuft eine bekannte Fregatte an, hält die Rohre geladen und schießt auf eine
nahe Ortung, schnorchelt zum Laden, hält den Trimm und schickt die Leckteams.
In der Lobby kann die uConsole auch nur Gastgeber sein (Station „keine, nur
Gastgeber“): Sie spielt keine Station, Browser und KI besetzen jede.
Spielstände sind jetzt v40.

## 1.3.108

Version 1.3.108 gibt dem KI-Aufklärungs-U-Boot eine echte Sehrohrsuche.
In der Aufklärungsmission von der Fregatte aus sichtet das KI-U-Boot auf
Sehrohrtiefe die Fregatte nicht mehr nur nach Entfernung und Sichtweite: Es
fährt alle 90 s für einen 24-s-Rundblick das Sehrohr aus, dreht vom Bug aus
herum und macht die Fregatte nur dort aus, wo das Kontrastmodell des Ausgucks
in 2,5 m Augenhöhe es erlaubt (Licht, Mond, Sichtweite, Seegang, Land
dazwischen). Solange das Sehrohr oben ist, zählt es als ausgefahrener Mast,
den das Oberflächenradar der Fregatte und der Seefernaufklärer erfassen
können. Nacht, Nebel und schwere See schützen jetzt die Fregatte, und jeder
Rundblick ist ein Risiko für das U-Boot.

## 1.3.107

Version 1.3.107 lässt die KI-Jäger und die KI-U-Boote das Funkspektrum
mehr wie echte Besatzungen nutzen (Spielstandsformat v39). Wenn niemand die
Fregatte fährt, trägt ihre EloKa eine ESM-Peilung auf das Mastradar eines
U-Boots als Linie vom eigenen Standort ein, eine je gelaufene Seemeile, und
kreuzt die neueste Linie mit einer früheren zu einem Positionsdatum für
Schiff, Hubschrauber und Seefernaufklärer (nicht für das ASROC eines
befreundeten Geleitschiffs). Ein KI-U-Boot auf Sehrohrtiefe, das die Fregatte
hält, meldet sie jetzt alle 30 Minuten mit einem 20-s-Kurzwellenruf an seine
Führung, den das HF/DF der Fregatte hört und peilen kann, gleich wer es
bedient. Die ESM-Linien werden gespeichert, ein geladenes Spiel setzt die
Jagd also unverändert fort.

## 1.3.106

Version 1.3.106 bringt eine Mehrspieler-Lobby. Der neue Hauptmenüpunkt
Mehrspieler startet Remote Crew im Crew-Modus und zeigt QR-Code und
Beitrittscode; die Browser koppeln, wählen Einheit und Stationen und drücken
Bereit, und alle sehen die Mission, Einheit und Station des uConsole und die
Stationen und Bereit-Häkchen jedes Crewmitglieds. Der Gastgeber wählt die
Mission, die Einheit des uConsole und seine eigene Station und startet dann
einen Countdown von fünf Sekunden, den jeder Browser sieht; die Mission
beginnt für alle gleichzeitig. Eine aus der Lobby gestartete Mission führt am
Ende alle zurück in die Lobby.

## 1.3.103

Version 1.3.103 macht die Karte Leckwehr des U-Boots im Browser zu einem
Leckwehr-Leitstand wie bei der Fregatte: eine Warn- und Meldetafel mit
Sammellampe (Strom, Wasser, Lecks, Brand, Gas, ausgefallene Abteilungen,
geschlossene Schotten, Trupps, Lenzpumpen, Verwundete, Trimm, Pressluft und
Übertiefe) über einer Seitenansicht des Druckkörpers mit vom Kiel steigendem
Wasser, Brandschein, Gasschleier, Lecks, geschlossenen Schotten, einer
Zustandslampe je Abteilung und den Trupp-Plaketten, dazu Rundinstrumente für
Trimm, Wassereinbruch und Pressluft; Tabelle und Trupp-Befehle bleiben
darunter.

## 1.3.102

Version 1.3.102 lässt den Brückenausguck nachts und bei schlechter Sicht
die Positionslichter melden, die er sieht, mit seiner Deutung: beide
Seitenlichter heißen, ein Fahrzeug hält auf das Schiff zu, und werden laut
gemeldet, Grün oder Rot allein zeigen seine Steuerbord- oder Backbordseite,
das Hecklicht allein, dass es abläuft, und Rundumlichter seine Arbeit
(Fischer, Lotse, manövrierbehindert, Minenräumer) oder, blitzend, ein
Luftfahrzeug. Die Lichter eines Kontakts meldet er erst wieder, wenn sich ihre
Aussage ändert, höchstens alle zwei Minuten, und die Remote-Crew-Brücke führt
die Meldungen mit den übrigen.

## 1.3.101

Version 1.3.101 bringt die Listen „Nicht modelliert“ im Handbuch auf den
Stand: Die OPZ fusioniert eindeutig passende Meldungen verschiedener Sensoren
selbst, und der Funkraum ruft das HQ mit Kontaktmeldungen und
Unterstützungsanforderungen; beide Listen nennen jetzt nur, was wirklich fehlt.

## 1.3.100

Version 1.3.100 bringt die Stationen Sonar, Elektronische Kampfführung, Funk
und Waffen in den Konsolenstil der Maschinen- und Schadensbildschirme. Das
Sonar von Fregatte und U-Boot bekommt dunklere Leuchtschirme, eine Horchkonsole
mit Lampen für Ping, Ton und Spitzenwert-Halten und eine nordorientierte
Peilrose mit Horchrichtung, toten Winkeln, eigenem Kurs und Kontaktpeilungen;
jede Kontaktzeile trägt eine Lampe und einen Balken für den Störabstand. Das
Tauchsonar des Hubschraubers zeigt Lampen für Dom, Ping und Wassereintritt,
eine Anzeige der Wassersäule und Peilkeile so breit wie ihr Fehler, und seine
Wasserfälle nutzen die Leuchtfarben des Schiffs. ESM und KW-Peilung bekommen
Peilrosen, die Waffenseiten Rohr- und Sperrlampen und Magazintanks. Im Browser
bekommen Sonar und Hubschrauber dieselbe Rose und Lampen, die Waffenkarte
Lampen und Rohrsäulen und das ESM-Sichtgerät eine Rose mit Skala.

## 1.3.99

Version 1.3.99 macht die Schadensbildschirme auf der uConsole und im Browser
zu Leckwehr-Leitständen. Im Schiffsplan der Fregatte auf der uConsole steigt
das Wasser in jeder Abteilung vom Kiel an, ein Brand glüht rot und eine
ausgefallene Abteilung ist schraffiert; jede Abteilungskarte trägt eine
Zustands-LED, Flutung und Brand mit LEDs und Balken sowie nummerierte
Trupp-Plaketten. Die Leckwehr-Seite des U-Boots ist eine Abteilungs-Mimik vom
Heck zum Bug mit Wasserstand, Brandschein, Gasschleier, LEDs für Leck, Brand,
Gas und Schotten, Trupp-Plaketten und Lampen für die gewählte Abteilung und
den Strom. Die Browser-Karte Schaden beginnt mit einer Warn- und Meldetafel
über einer Seitenansicht des Schiffs und Rundinstrumenten für Krängung, Trimm
und Gesamtschaden; ein Klick auf eine Abteilung schickt weiter den gewählten
Trupp.

## 1.3.98

Version 1.3.98 verwundet Menschen. Treffer, Feuer, Wassereinbruch und Gas
verletzen die Besatzung der Fregatte und jedes U-Boots an Sonar, Waffen und
Leckwehr; jeder leere Posten verlangsamt die Station (Erkennen, Nachladen und
Fluten der Rohre, Reparaturen), und jeder dritte Verwundete fällt für die
Mission aus. Der Leckwehroffizier schickt das Sanitätsteam (Fregatte
Schadenskontrolle Seite 3 `M`, U-Boot `Shift+M`, Browser-Knopf) und besetzt die
schlimmste Station mit bis zu zwei Mann der ruhenden Wachen nach (`U`, U-Boot
`Ctrl+M`), denen dann die Ruhe fehlt; KI-Schiffe besetzen selbst nach.
Spielstände sind jetzt v38. Damit sind neun Verbesserungen ab 1.3.90 fertig,
jede mit einem Gegenstück für die U-Boot-Seite.

## 1.3.97

Version 1.3.97 gibt der Fregatte einen U-Jagd-Raketenwerfer (Waffen `R`,
Browser-Knopf): Salven zu sechs Raketen 0,4 bis 3 sm auf eine frische
Entfernungspeilung, 36 Raketen, eine Minute Nachladen. `Shift+R` schießt eine
flache Abwehrlinie in der Peilung einer Torpedowarnung, die einen Torpedo
zerstört, neben dem sie detoniert. Die Einschläge warnen jedes U-Boot bis
3 sm: KI-Boote weichen aus, der Sonarraum des bemannten Boots meldet ihre
Peilung. Die KI-Fregatte nutzt beides. Spielstände sind jetzt v37.

## 1.3.96

Version 1.3.96 bringt eine Sonar-Klassenbibliothek: die DEMON-Seite zeigt
die drei Katalogklassen, die am besten zu den Wellen-, Blatt- und
LOFAR-Marken des Bedieners passen, mit Passung in Prozent, und der
F8-Analysator sortiert den ganzen Katalog nach Passung. Der Sonarraum des
U-Boots und die Web-Sonarstation haben dieselbe Bibliothek.

## 1.3.95

Version 1.3.95 lässt beide Seiten frei mit dem Hauptquartier funken: der
Funkraum sendet eine Kontaktmeldung mit der frischesten Peilung (`K`) oder
fordert Unterstützung an (`H`). Jeder Spruch ist 20 s auf Sendung und kann
von einem feindlichen U-Boot mit ausgefahrener Antenne gepeilt werden, so wird
Funk zum Sensor für beide Seiten; genaue Meldungen zählen am Missionsende.
Spielstände sind jetzt v36.

## 1.3.94

Version 1.3.94 bildet den toten Winkel achteraus nach: die Rumpfbasis der
Fregatte und das Rumpfsonar jedes U-Boots hören innerhalb von 30 Grad um das
eigene Heck nichts mehr, Schleppsonar und VDS schon. Brücke und bemanntes Boot
räumen den toten Winkel mit `Ctrl+B` (Browser-Knopf): 60 Grad nach Steuerbord
für zwei Minuten, dann zurück. Ein KI-U-Boot dicht im toten Winkel der
Fregatte folgt ihr nach einem Ping dort, statt zu fliehen. Spielstände sind
jetzt v35.

## 1.3.93

Version 1.3.93 bringt ein Logbuch im Hauptmenü: jede beendete Mission der
Seite, die die uConsole gespielt hat, steht in `~/.u-jagd/logbook.json`, mit
der Bestpunktzahl je Mission und fünf Auszeichnungen je Seite. Das U-Boot
bekommt jetzt Punkte aus seinem Ergebnis, sodass beide Seiten gleich viel
erreichen können.

## 1.3.92

Version 1.3.92 bringt die Realismusstufen Anfänger, Standard und
Realistisch (Optionen, je Mission gespeichert). Sie stimmen nur den
Computergegner ab (Angriffslust und Schusslösungsschwelle der KI-U-Boote,
Klassifizierung und Hubschrauberverzögerung der KI-Fregatte) und die
Bedienerhilfen; die Missionswertung wird mit 75, 100 oder 125 % gewichtet.

## 1.3.91

Version 1.3.91 bringt Ereignisse auf See. Ab 20 bis 40 Minuten einer
eingebauten Mission kommen bis zu vier über den Fernschreiber: ein Treibnetz
quer zum Kurs (Überfahren kostet Punkte und verfängt ein ausgebrachtes
Schleppsonar oder VDS, ein flach fahrendes U-Boot verfängt sich laut), eine
Wetterfront mit Warnung des Hauptquartiers, ein Frachter ohne AIS zum
Identifizieren und eine Walschule. Das Hauptquartier gibt Netz, Front und Wale
an das U-Boot weiter; die KI-Fregatte umfährt gemeldete Netze. Spielstände
sind jetzt v34.

## 1.3.90

Version 1.3.90 macht das Fluten der Torpedorohre hörbar. Ein U-Boot, das ein
Rohr flutet und die Mündungsklappe öffnet, erzeugt einen Transienten, den das
Sonar der Fregatte als Warnung mit gemessener Peilung meldet: lautes Fluten
bis 8 sm, langsames leises Fluten bis 1,5 sm. Das bemannte Boot kann leise
fluten (`Ctrl+M`, Browser-Knopf); KI-Boote fluten leise und früh auf eine
Peilung, laut kurz vor dem Schuss auf trockene Rohre. Spielstände sind jetzt
v33.

## 1.3.89

Version 1.3.89 macht die Maschinenräume der uConsole zu Maschinenleitständen
im Splash-Stil. Auf der Fregatte wird der Telegraf eine Säule leuchtender
Stufen neben einem großen Fahrtinstrument, Instrumenten für Drehzahl und
Eigenlärm und Anlagenlampen; die Seite Systeme hat eine Warn- und Meldetafel
mit Sammellampe, den Kraftstoffbunker als Tanksäule, Instrumente für Rollen,
Stampfen und Schlagseite und ein Bild der Schiffsabschnitte vom Bug zum Heck
mit Wasserstand, LEDs und nummerierten Reparaturtrupps. Auf dem U-Boot zeigt
die Seite Anlage Instrumente für Fahrt, Batterie (beim Atom-U-Boot die Tiefe)
und Eigenlärm mit Betriebsartenlampen, und Vorräte zeigt Tanksäulen für
Batterie, AIP, Diesel und Absorber und einen Balken je Telegrafenstufe.

## 1.3.88

Version 1.3.88 lässt die OPZ übereinanderliegende Meldungen von selbst
zusammenlegen: Ein Schiff, das Radar, Ausguck und AIS sehen, ist jetzt ein
Kontakt statt drei. Zusammengelegt wird nur bei eindeutiger Übereinstimmung
(mindestens eine Position, kein zweiter Kandidat derselben Sensorart); dicht
beieinander fahrende Schiffe bleiben getrennt und erscheinen als Vorschlag,
und `Shift+L` trennt eine Fusion weiterhin. Die zusammengelegten Meldungen
verschwinden aus Trackliste und Karte, jede Zeile endet mit Sensorkürzeln
(`R` Radar, `V` Ausguck, `A` AIS, `E` ESM, `S` Sonar ...), und die Zieldetails
und die Remote-Crew-OPZ nennen die Quellen einer Fusion mit Namen.
Spielstände bleiben v32.

## 1.3.87

Version 1.3.87 gibt dem Maschinenraum der Fregatte im Browser denselben
Maschinenleitstand wie dem U-Boot: eine Warn- und Meldetafel aus Statuslampen
für Wellen, Anlage, Kavitation, Kraftstoff, Fahrtbegrenzung, Maschinenschaden,
Brände und Wassereinbruch an Bord, runde Instrumente für Fahrt,
Wellendrehzahl, Eigenlärm, Kraftstoff, Rollen und Stampfen, den
Kraftstoffbunker mit Ausdauer und Reichweite und ein Bild der Schiffsabschnitte
vom Bug zum Heck mit Wasserstand, Brandlampen und Reparaturtrupps. Der
Leitstand zeigt nur an; die Befehle bleiben im Stationsbereich.

## 1.3.86

Version 1.3.86 macht die 3D-Modelle massiv. Bisher wurden ihre Flächen nach
ihrem Mittelpunkt sortiert gezeichnet, sodass aus vielen Winkeln eine ferne
Fläche über eine nahe gemalt wurde: Decks schienen durch Aufbauten, die ferne
Rumpfseite durch die nahe, und Schiffe wirkten hohl. Jedes Modell wird jetzt
einmal in eine binäre Raumteilung zerlegt, die von jeder Seite eine exakte
Reihenfolge von hinten nach vorn ergibt, auf der uConsole wie im Browser; die
Rumpfbeplankung ist geschlossen und zeigt nach außen, und Rümpfe, U-Boote und
Flugzeugrümpfe haben ein feineres Raster. Aufbauten sind keine Klötze mehr:
Sie steigen in Decksstufen an, bei Kriegsschiffen eingezogen und geneigt, bei
Passagierschiffen in Terrassen zurückgesetzt, bei Handelsschiffen mit kurzem
Steuerhaus und Brückennocken oben; U-Boot-Türme sind stromlinienförmig.
Spielstände bleiben v32.

## 1.3.85

Version 1.3.85 lässt den Helikopter sein Suchradar aus- und wieder
einschalten (`Shift+R`, Knopf im Browser): Ein strahlender Helikopter oder
Seefernaufklärer drückt ein KI-U-Boot mit ausgefahrenem Mast oder Schnorchel
jetzt für 15 Minuten auf Tiefe, ein stiller kann es an der Oberfläche
erwischen. Der Seefernaufklärer fliegt MAD-Anflüge über sein Suchgebiet (`V`
auf OPZ-Seite 3, Knopf im Browser) und meldet einen getauchten Rumpf, den er
überfliegt, als MAD-Ortung per Datenlink. In den Fregattenszenarien
torpediert ein KI-Patrouillen-U-Boot fern der Fregatte, das nicht gejagt
wird, ab und zu ein nahes Handelsschiff, und jedes verlorene Handelsschiff
kostet 300 Punkte. KI gegen KI gemessen blieben die Missionsausgänge in allen
30 Vorher-nachher-Paaren der Szenarien 1 bis 3 und 5 bis 7 gleich; die Doppeljagd verlor in
2 von 6 Läufen ein Handelsschiff. Spielstände sind jetzt v32; ältere werden
nicht geladen.

## 1.3.84

Version 1.3.84 lässt den Autopiloten der Brücke den Weg durch Fahrwasser, in
Buchten und um lange Küsten finden: Reicht ein Ausweichpunkt für eine Strecke
nicht, plant eine Wegsuche auf der Karte die Wendepunkte (die Planung ist
dabei schneller als bisher). GitHub prüft jetzt jede Änderung mit der ganzen
Testsuite samt Browser-Tests, den Prüfungen der erzeugten Dateien, der
Kalibrierung und dem Smoke-Test, und zwei wackelige Browser-Prüfungen sind
repariert: Der Handy-Ausguck fällt nicht mehr auf die Kopplungsseite zurück,
wenn der Host direkt nach dem Koppeln langsam antwortet, und die Statusleiste
wird mit den mitgelieferten Schriften vermessen. Das Handbuch behauptet nicht mehr, die
Fregatte habe kein ASROC, und `tools/hw_report.py` macht aus einem
Debug-Lauf auf der uConsole die Tabelle der Hardware-Checkliste. Spielstände bleiben v31.

## 1.3.83

Version 1.3.83 macht aus dem Maschinenraum des U-Boots im Remote-Crew-Browser
einen Maschinenleitstand. Die große, bisher leere Bildfläche zeigt eine Warn-
und Meldetafel aus Statuslampen (dunkel, wenn aus, türkis im Betrieb, gelb bei
einer Warnung, rot blinkend bei einem Alarm, jede mit ihrem Wert) für
E-Maschine, Schnorchel, Generator, Batterie, Laden, Kraftstoff, Luft,
Hauptzellen, Pressluft, Pumpen, Trimm, Strom, Wassereinbruch, Leck, Brand und
Gas, mit einer Sammellampe, die die Alarme zählt. Darunter stehen runde
Instrumente für Fahrt, Batterie, Energiebilanz, Tiefe, Pressluft und
Trimmwinkel, Tanksäulen für Vorräte und Zellen und ein Bild der sechs
Abteilungen vom Bug zum Heck mit Wasserstand, den Lampen jedes Raums, den
Schotten und den arbeitenden Trupps. Die Befehle bleiben im Stationsbereich.
Spielstände bleiben v31.

## 1.3.82

Version 1.3.82 lässt die Sprachmeldungen des Handy-Ausgucks sagen, woran sie
scheitern. Statt nur „Spracherkennung fehlgeschlagen“ nennt die Seite jetzt die
Ursache: Siri und Diktierfunktion am iPhone ausgeschaltet (mit dem Weg zum
Einschalten), Mikrofon nicht erlaubt, Mikrofon belegt, nichts gehört oder der
Sprachdienst des Handys nicht erreichbar; jeder andere Fehler zeigt seinen
Fehlercode. Chrome, Firefox und Edge auf dem iPhone nutzen Safaris Technik
ohne dessen Sprachdienst, deshalb rät die Seite dort für Sprachmeldungen zu
Safari; das Ziel antippen geht überall. Eine kurze Meldung, die Safari beendet,
ohne sie als fertig zu markieren, wird jetzt trotzdem gelesen. Spielstände
bleiben v31.

## 1.3.81

Version 1.3.81 zeigt die eigene Fahrt in den Bildern des Ausgucks. In Fahrt
strömen die Wellen voraus auf das Auge zu, achteraus von ihm fort und querab
vom Bug zum Heck, schneller mit mehr Fahrt und ohne Sprung, wenn sich Fahrt
oder Kurs ändern. Achteraus läuft das Kielwasser als Band aus glatterem,
hellerem Wasser mit Schaum zwischen den beiden Armen der Kelvin-Welle bis zum
Horizont, und voraus wirft die Bugwelle ihre Gischt in den unteren Bildrand.
Das gilt auf der uConsole und im Browser für das Brückenfernglas, den
Ausguckstreifen und den Handy-Ausguck; im Sehrohr des U-Boots strömt das
Wasser mit der eigenen Fahrt des U-Boots vorbei. Spielstände bleiben v31.

## 1.3.80

Version 1.3.80 gibt jedem Schiffs-, U-Boot- und Flugzeugtyp ein eigenes
3D-Modell. Jeder der 111 Katalogtypen ist aus den öffentlichen
Hauptabmessungen und der Anordnung der echten Klasse gebaut (Wikipedia;
allgemeine Typen wie ein VLCC oder ein Hafenschlepper mit typischen Werten):
Länge, Breite und Tiefgang, wo Brücke, Masten, Schornsteine, Geschütze,
Flugkörperzellen, Flugdeck, Kräne und Ladung stehen, beim U-Boot Turm,
Tiefenruder, Heckruder und Raketendeck, beim Flugzeug Flügel, Leitwerk und
Triebwerke. Derselbe Typ sieht immer gleich aus, eine Type 23 also nicht mehr
wie eine Arleigh Burke. Analysator, Einheiteneditor und die Okulare
(Fernglas, Sehrohr, Handy-Ausguck) zeigen den echten Typ, den das Auge sieht,
sodass er sich auf Sicht bestimmen lässt; die Meldung des Ausgucks nennt
weiter nur, was er ausgemacht hat, und nur sie geht an die OPZ. Spielstände
bleiben v31.

## 1.3.79

Version 1.3.79 repariert die Kopplung in Safari und Firefox und damit den
Handy-Ausguck auf dem iPhone. Die Seiten des Spiels verlangten vom Browser,
gar keinen Referrer zu senden; nach dem Webstandard kennzeichnen Safari und
Firefox dann die eigenen Anfragen der Seite als herkunftslos („Origin: null“),
und das Spiel wies sie als fremde Adresse ab, sodass die Kopplung mit „Das
Spiel hat diese Adresse abgelehnt“ scheiterte. Die Seiten behalten den
Referrer jetzt für das Spiel selbst und senden weiterhin keinen an andere
Seiten; Chrome war nie betroffen. Spielstände bleiben v28.

## 1.3.78

Version 1.3.78 zeigt die Einheiten als 3D-Modelle. Im Einheitenanalysator
(`F8`) ist die erste Seite jedes Katalogprofils jetzt ein langsam drehendes
3D-Modell seiner Klasse, vor den Klang- und Radarbildern; im
Remote-Crew-Browser lässt es sich zusätzlich durch Ziehen drehen. Der
Einheiteneditor zeigt dasselbe Modell unter dem gewählten Profil und neben den
Feldern eines geöffneten. Schiffe, U-Boote und Luftfahrzeuge sind die
Silhouetten des Ausgucks, räumlich ausgebaut, sodass eine Einheit im
Analysator so aussieht wie im Fernglas und im Sehrohr (Kriegsschiff,
Handelsschiff, Kleinfahrzeug, U-Boot, der Hubschrauber des Ausgucks für jedes
Luftfahrzeug); Torpedos, Täuschkörper und Tiere, die kein Ausguck sieht, haben
eigene Modelle. Dieselben Modelle stehen jetzt im Fernglas des Ausgucks und
im Sehrohr auf der uConsole, im Browser und am Handy, gedreht um den
Lagewinkel, den der Beobachter schätzt, sobald er die Klasse ausgemacht hat.
Spielstände bleiben v31.

## 1.3.75

Version 1.3.75 räumt auch die Git-Tags auf GitHub auf: Beim Veröffentlichen
einer neuen Version löscht der Windows-Build jetzt jeden älteren
`vX.Y.Z`-Tag zusammen mit seinem Release, sodass nur das neueste Release samt
Tag bleibt. Der uConsole-Updater braucht nur diesen neuesten Tag. Spielstände
bleiben v31.

## 1.3.74

Version 1.3.74 gibt dem U-Boot eine faire Chance gegen die vom Computer
geführte Fregatte. Wenn du das U-Boot spielst, braucht die Besatzung der
Fregatte jetzt etwa 3 Minuten, um ein U-Boot am Geräusch zu erkennen, und etwa
10 Minuten, um den Hubschrauber klarzumachen. Auf eine bloße Peilung horcht der
Hubschrauber mit dem Tauchsonar nur, der Seefernaufklärer kommt nur für eine
Position, und Flugzeuge greifen nur aus einem höchstens 2 Minuten alten Fix an.
Der Durchbruch dauert jetzt 5 statt 4 Stunden, die Aufklärung 2 statt 3.
Spielstände bleiben v31.

## 1.3.73

Version 1.3.73 repariert das Selbst-Update unter Windows: Nach **Update
installieren** ersetzt die neue U-Jagd-Windows.exe jetzt die laufende und
startet. Bisher blieb der Download als `U-Jagd-Windows.exe.new` daneben liegen
und die alte Version startete wieder. Der Starter löscht eine solche
liegengebliebene `.new`-Datei, und der Windows-Build prüft den Austausch bei
jeder Änderung. Spielstände bleiben v31.

## 1.3.72

Version 1.3.72 macht das computergesteuerte U-Boot in den Missionen
Durchbruch, Aufklärung und Geleitzug klüger und gibt der Fregatte mehr
Torpedos. Das U-Boot schleicht jetzt mit 3 kn, solange es Pings hört oder die
Fregatte in der Nähe weiß, umfährt eine geortete Fregatte weiträumig, lauert
dem Geleitzug 2 sm voraus auf, statt ihm nachzulaufen, weicht Pings leise mit
5 kn aus und schießt deutlich eher auf eine geortete Fregatte zurück. Die
Fregatte hat in der Doppeljagd 8 und im Abfang 6 Torpedos. Spielstände bleiben
v31.

## 1.3.71

Version 1.3.71 macht die Sprache des Remote-Crew-Servers zwischen Englisch und
Deutsch umschaltbar. Der Windows-Starter hat oben ein Feld Sprache: Die Wahl
gilt sofort für den Starter und wird in den Einstellungen gespeichert, sodass
auch das Spielfenster und jeder Besatzungs-Browser darin starten. Die
Browser-Seiten öffnen jetzt in der gespeicherten Sprache des Hosts statt in der
des Browsers, und die Besatzungsseite hat neben Ton einen sichtbaren Knopf
English/Deutsch, der nur diesen Browser umstellt; die Admin-Seite des Web-Hosts
wechselt mit der gespeicherten Serversprache auch ihre eigene Sprache.
Spielstände bleiben v31.

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
