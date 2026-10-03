# 2 Sonar {#station-sonar}

## Zweck {#sonar-purpose}

Die Sonarzentrale ist der Hauptsensor der U-Jagd. Sie horcht passiv mit Bugsonar (HMS), Schleppsonar (TAS) und tiefenveränderlichem Sonar (VDS), analysiert Signaturen in LOFAR und DEMON, schätzt die Zielbewegung per TMA, misst das Schallprofil und sendet auf Befehl einen aktiven Ping. Sie klassifiziert Kontakte und gibt sie an OPZ und Waffenzentrale frei.

## Anzeigen und Instrumente {#sonar-displays}

Die Station hat sechs Seiten. `Bild Auf`/`Bild Ab` (oder nochmals `2`) blättert sie. Der Hörposten rechts zeigt Quelle und Alter der Evidenz, das Array, die Hörpeilung und die Ping-Bereitschaft; ein Schlepp- oder Tiefensonar, das gerade aus- oder einfährt oder noch nicht bereit ist, erscheint auf jeder Seite gelb mit Kabellänge, Stabilität und PAUSE, wenn die Handhabung außerhalb der Grenzen liegt. Die eine Tastenzeile unten zeigt die vier Haupttasten der Seite mit ihren Werten; alle übrigen Tasten stehen in der F1-Hilfe. Auf BREITBAND ist die gelbe Linie die Hörpeilung und die grauen Linien die Grenzen des Hörstrahls; dunkel heißt leise, türkis laut.

| Seite | Zeigt | Wofür |
|---|---|---|
| BROADBAND | Peilung-Zeit-Wasserfall | Kontakte entdecken und ihrer Peilung folgen |
| LOFAR | Frequenz-Zeit-Wasserfall, 0-300 Hz | Tonale Linien: Maschinen, Welle, Schraubensignaturen |
| DEMON | Modulationsspektrum des Horchstrahls | Hypothesen zu Blatt- und Wellenfrequenz |
| TMA | Lösung für den fokussierten Kontakt | Schätzung von Entfernung, Kurs und Fahrt |
| UMWELT / FUSION | Schallprofil, Schicht, CZ, Array-Vergleich | TAS-Tiefe wählen, Geisterkontakte erkennen |
| ACTIVE | Gespeicherte Echos mit Alter und Fehler | Entfernung und Tiefe aus Pings |

Die Station hat drei Spalten: links Kontaktkarten, in der Mitte die Anzeige der Seite, rechts die Detailzeilen und die Horchkonsole. Die Horchkonsole unter den Detailzeilen ist wie ein Leitstand aufgebaut: Lampen zeigen Ping bereit (gelb, solange ein Ping läuft), Ton und Spitzenwert-Halten, und eine nordorientierte Peilrose zeigt die Horchrichtung (gelb), die toten Winkel achtern (roter Sektor), den eigenen Kurs und jede veröffentlichte Kontaktpeilung. Jede Kontaktkarte zeigt eine Lampe, die Peilung, die Klassifizierung und einen Balken für den Störabstand; ein Klick wählt den Kontakt. Der Remote-Crew-Browser zeigt dieselbe Rose neben seinen Wasserfällen.

### BROADBAND-Wasserfall {#sonar-broadband}

```text
 Peilung  000      090      180      270      359
 jetzt  |   .   #     .        :          .    |
        |   .   #    .         :         .     |
        |   .    #   .          :        .     |
 älter  |   .    #  .           :       .      |
        +--------------------------------------+
            ^    ^              ^
            |    wandernder     Eigenlärm (weiche Keule achteraus)
            |    Kontakt
            stehender schwacher Kontakt
```

Neueste Daten stehen oben. Eine gerade senkrechte Spur ist ein Kontakt mit stehender Peilung; eine schräge Spur zeigt Peilungswanderung. Die Historie umfasst 20 s Feindaten plus 4 Minuten Langzeithistorie (`Shift+H` wählt 25/50/100 %). Helligkeit ist relativer Empfangspegel, keine Entfernung.

### LOFAR {#sonar-lofar}

Die x-Achse ist die Frequenz (0-300 Hz), die Zeit läuft nach unten. Die Klassen sind 1 Hz breit unter 40 Hz, 2 Hz bis 100 Hz und 5 Hz darüber. Alle 0,25 s kommt eine Zeile hinzu; 80 Zeilen bleiben stehen.

- Stehende senkrechte Linien sind **Töne** (Schmalband): Generatoren, Pumpen, Wellenlinien. Mehrere Linien bei ganzzahligen Vielfachen einer Frequenz bilden eine Harmonischenfamilie: den weißen Cursor mit `Z`/`X` auf eine Linie setzen (`Umschalt`: 10-Hz-Schritte) und mit `K` als Grundton markieren; bernsteinfarbene Hilfslinien zeigen dann 2f, 3f usw. `K` auf derselben Frequenz löscht ihn.
- Das eigene Schiff erzeugt eine Wellenlinie bei etwa 10 + 1,9 x eigene Fahrt Hz. `N` blendet sie per Notch aus.
- `Leertaste` hält Spitzen, damit schwache Töne hervortreten.
- Der Spektrumstreifen über dem Wasserfall schreibt die Frequenz über jede deutliche Linie (zwischen den Klassen interpoliert; mit `Leertaste` die gehaltene Hüllkurve). Wo sich Werte überdecken würden, behält die stärkere Linie ihre Beschriftung. Der Remote-Crew-Browser beschriftet seine Spektren genauso.
- `F` wählt das Analyseband: FULL 0-300, LOW 4-80, SHAFT 8-55, MID 20-120 Hz. `Strg+Z` / `Strg+X` setzen die untere / obere Bandkante auf den Cursor für jeden Band-, Tief- oder Hochpass; `Umschalt+N` legt einen zusätzlichen Notch auf die Cursorfrequenz.
- `Q` wählt die Integrationszeit: 2 s (die FFT des Empfängers), 8, 16 oder 64 s. Längere Integration mittelt aufeinanderfolgende Spektren, sodass ein schwacher stehender Ton aus dem Rauschen tritt; eine wandernde Linie verschmiert dabei. `Umschalt+Q` öffnet den Nonius: 20 Hz um den Cursor in der nativen 0,5-Hz-Auflösung.
- Die Detailspalte liest den Pegel am Cursor. Automatisch beschriftet der Streifen Linien nur auf der Realismusstufe Einsteiger (`F10`).

### DEMON {#sonar-demon}

DEMON demoduliert die Hüllkurve des Breitbandrauschens im Horchstrahl. Schraubenkavitation ist mit der **Blattfrequenz** moduliert = Wellenfrequenz x Blattzahl.

```text
 Pegel
   |      |              Blattfrequenz 12,5 Hz
   |  |   |              -> 5 Blätter => Welle 2,5 Hz = 150 U/min
   |  |   |   |
   +--+---+---+------ Hz
     2,5 12,5 25
    Welle Blatt 2. Harmonische
```

Die Anzeige zeigt gemessene Modulation, keine Identität. Nach einer Peilungsänderung einige Sekunden horchen, bevor Sie urteilen. Blätter selbst zählen: den Cursor (`Z`/`X`, 0,5 Hz) auf die Wellenlinie setzen und `K` drücken, dann auf die Blattlinie und erneut `K`; die Spalte zeigt Blätter = Blattfrequenz / Wellenfrequenz (mit der Abweichung von einer ganzen Zahl) und die Wellendrehzahl. Ein drittes `K` löscht beide Marken. Die **Klassenbibliothek** unter den Marken nennt die drei Katalogklassen, die am besten zu Ihren Marken passen: Wellendrehzahl gegen den Drehzahlbereich der Klasse, Blattzahl gegen ihre Blattzahlen und Ihre LOFAR-Grundlinie (`K` auf der LOFAR-Seite) gegen ihr Tonalband und ihre Maschinenlinien, jeweils am besten in der Mitte des Bereichs. Mit weniger als zwei Marken ist sie nur ein Hinweis. Der Kontaktanalysator (`F8`) listet dann den ganzen Katalog nach Passung mit der Passung in Prozent. Die Bibliothek bewertet Ihre Marken, nie den Kontakt selbst, und die Klassifizierung bleibt Ihre Entscheidung; der Sonarraum des U-Boots hat dieselbe Bibliothek. Auf der Realismusstufe Einsteiger (`F10`) beschriftet das Sonar zusätzlich Modulationslinien, schlägt Drehzahlen für 3-7 Blätter vor und rankt Katalogkandidaten.

### TMA, Umwelt und Aktiv {#sonar-tma-env}

- **TMA** machen Sie selbst. Die Seite zeichnet die Peilungen des gewählten Kontakts über der Zeit. Stellen Sie eine Hypothese auf: `Z`/`X` Kurs (`Umschalt`: 1 Grad), `Strg+Z`/`Strg+X` Fahrt, `Q`/`Umschalt+Q` Entfernung auf der neuesten Peilung (`Strg`: 0,2 sm). Die bernsteinfarbene Kurve zeigt die Peilungen, die diese Hypothese vorhersagt, die Punkte am Fuß die Residuen (gemessen minus vorhergesagt). Gute Hypothesen lassen die Residuen um null streuen; ein falscher Kurs, eine falsche Fahrt oder Entfernung hinterlässt einen Trend. Die Spalte zeigt RMS der Residuen, den systematischen Trend nach Mittelung, die Passung und die Beobachtbarkeit. Die Entfernung ist erst nach einer eigenen Kursänderung beobachtbar (mindestens 6 Grad, besser 30-60); ohne sie verweigert `K`. `K` übernimmt die Hypothese als TMA-Fix des Kontakts; er wird auf Kurs und Fahrt mitgekoppelt und veraltet nach 120 s, also verfeinern und erneut übernehmen, wenn Peilungen hinzukommen. Verrauschte Peilungen ergeben auch bei guter Passung eine große Entfernungsunsicherheit. Tiefe schätzt TMA nicht. Auf der Realismusstufe Einsteiger (`F10`) wird ein automatischer Solver-Vorschlag (er braucht mindestens 4 Peilungen über 180 s) als dünne Linie gezeichnet, und `Umschalt+K` kopiert ihn in die Hypothese. Sonobojen-Peilungen gehen mit der Boje als Beobachter in den Track ein. `Umschalt+T` wechselt die TMA-Methode: HYPOTHESE (oben), EKELUND (die Entfernung aus den Peilraten zweier eigener Schläge um eine Kursänderung von mindestens 30°, je 90 s; `Umschalt+K` übernimmt sie in die Hypothese, `K` nimmt dann wie üblich an) oder DOT-STACK (Residuenzeilen bei 0,6-, 1,0- und 1,6-facher Hypothesenentfernung: die flache Zeile ist die Entfernung, die die Peilungen stützen).
- **UMWELT / FUSION** zeigt den Bathythermographen (`E`, 60 s Abklingzeit): gemessene Schichttiefe, Schallgeschwindigkeitsprofil und Konvergenzzonen, dazu den Vergleich HMS/TAS. Peilungen innerhalb 5 Grad bestätigen sich; ab 9 Grad Abweichung wird ein möglicher Geisterkontakt markiert. Die Schicht ist nicht fest: Nachmittagssonne macht sie flacher (etwa 8 m), starker Wind mischt sie über Stunden tiefer, und interne Wellen verschieben sie um einige Meter. Den BT nach einigen Stunden oder einem Wetterwechsel wiederholen. Das gemessene Profil ist die echte temperaturabhängige Schallgeschwindigkeit (Mackenzie-Gleichung) und fällt deshalb unterhalb der Schicht ab. Mit der Maus über dem Profil lesen Sie die genaue Tiefe, die dortige Schallgeschwindigkeit und ob die Tiefe über oder unter der Schicht liegt (uConsole und Web). Im Web-Client beschriftet die Grafik zusätzlich Schicht, Meeresgrund und das Schallgeschwindigkeitsminimum. Die Konvergenzzonen darin stammen aus dem gemessenen Profil selbst: aus der Strahlverfolgung dieses Profils über dem kartierten Bodentyp in der Tiefe des Arrays, sie ändern sich also mit Schicht, Tiefe und Boden (keine im Flachwasser).
- **ACTIVE** listet die Echos der letzten 120 s: Peilung, Entfernung und Tiefe (+/-12 m). Ein Ping-Fix veraltet nach 120 s. `W` wählt den Puls: **CW** (1-s-Ton) misst die Entfernung grob (etwa 0,1-0,3 sm), trennt aber über den Doppler ein bewegtes Ziel vom Nachhall des Meeresbodens; **LFM** (100-Hz-Sweep) misst die Entfernung auf wenige Meter und gewinnt 20 dB gegen Rauschen, ein langsames oder stehendes Ziel bleibt aber im Nachhall. Die Echostärke hängt vom Aspekt (breitseits etwa 15 dB stärker als von vorn) und der Größe des Ziels ab. Felsgrund hallt viel stärker nach als Schlick; kartierte Wracks liefern echte Echos ohne zugehörigen Kontakt ("nicht zugeordnetes Echo").
- **Das Echo hören:** Jede Rückkehr ist hörbar, sobald sie eintrifft, nach ihrer echten Laufzeit hin und zurück (etwa 2,5 s je Seemeile Entfernung), für das Schiffssonar ebenso wie für das Tauchsonar des Helikopters. Ein CW-Echo ist ein weicher Ton auf der Trägerfrequenz, ein LFM-Echo ein kurzer Sweep; maßgeblich ist der Puls, mit dem gepingt wurde. Ein starkes Echo hebt sich deutlich ab, ein schwaches steigt kaum aus dem Nachhallrauschen. Im Remote-Crew-Browser klingt das Echo über den allgemeinen Ton (laut oder leise). Das aktive Ping eines U-Boots kommt umgekehrt nach seiner einfachen Laufzeit an (etwa 1,2 s je Seemeile): Erst dann gibt die Fregatte ihren tiefen Warnton, spielt das Ping selbst und meldet es im Log mit der nach Gehör gemessenen Peilung (ganze Grad, etwa ±2° ungenau); eine Entfernung liefert ein fremdes Ping nie. **Richtungshören:** Mit Stereoton (Kopfhörer) kommen Echos, Detonationen und das Ping eines U-Boots aus der Peilung, aus der sie gehört wurden: links für Backbord, rechts für Steuerbord vom Bug des Schiffs aus, mittig recht voraus und achteraus (voraus und achteraus klingen gleich). Das eigene Ping, Starts und Geschützfeuer bleiben mittig. Der uConsole und der Remote-Crew-Browser setzen sie gleich.

## Bugsonar, Schleppsonar und VDS {#sonar-arrays}

| | HMS (Bug) | TAS (Schlepp) | VDS (tiefenveränderlich) |
|---|---|---|---|
| Passivreichweite | 1,0 x Basis | 1,4 x Basis, minus 3 % je Knoten | 1,15 x Basis |
| Strahlbreite | 12 Grad | 6 Grad | 8 Grad |
| Peilfehler | +/-6 Grad | +/-2 Grad, links/rechts mehrdeutig | +/-4 Grad, eindeutig |
| Eigenlärm | voll | 35 % des Bugsonars | 60 % des Bugsonars |
| Pingreichweite | 1,0 x | 0,8 x | 1,1 x, aus der Tiefe des Körpers |
| Handhabung | immer bereit | ausbringen 360 s, einholen 480 s, nur bei 3-12 kn, 30 s Beruhigung | fieren 120 s, hieven 120 s, nur bei 3-15 kn und Seegang bis 5, 20 s Beruhigung |

- TAS-Tiefe 20-260 m (`U`/`V` in 10-m-Schritten), begrenzt auf 260 m minus 4 m je Knoten eigener Fahrt. Ab 30 m Tiefe und in derselben Schicht wie das Ziel gewinnt es weitere 25 %.
- Über 20 kn mit ausgebrachtem Kabel erleidet das Array einen dauerhaften FAULT.
- Das Array folgt einer Kursänderung mit etwa 45 s Verzögerung; während es nachschwenkt, sind seine Peilungen weniger verlässlich.
- **Toter Winkel (Baffles):** Das Bugsonar (HMS) ist 30° beiderseits des eigenen Hecks taub; ein Boot genau achteraus hört nur das Schleppsonar oder das VDS. Der BREITBAND-Wasserfall markiert die Grenzen des toten Winkels gepunktet. Klären Sie ihn von der Brücke mit `Strg+B` (zwei Minuten 60° nach Steuerbord, dann zurück) oder mit einer eigenen Kursänderung. Für den Gegner gilt dasselbe: Auch das Rumpfsonar eines U-Boots ist achtern taub, und ein KI-Boot, das sich nach einem Ping dicht im toten Winkel der Fregatte findet, folgt ihr dort, statt zu fliehen.
- VDS (`Umschalt+Y` fiert oder hievt ihn, `Umschalt+B` wählt ihn): ein Körper an kurzem Kabel, 20-300 m tief, begrenzt auf 300 m minus 8 m je Knoten. `U`/`V` verstellen die Tiefe des jeweils gewählten Arrays. Ab 30 m Tiefe in der Schicht des Ziels gewinnt er dieselben 25 % wie das TAS. Er peilt eindeutig, eine VDS-Peilung löst die TAS-Seite also wie das Bugsonar auf. Ein Ping auf dem VDS sendet aus dem Körper: unter der Sprungschicht trifft der Schattenzonenverlust flache statt tiefe Ziele. Fieren und Hieven pausieren außerhalb 3-15 kn oder über Seegang 5; über 24 kn mit ausgebrachtem Körper geht er verloren (FAULT).

```text
          HMS                          TAS
     Lärmkeule achteraus        Lärmkeule entlang Kabel
            ^                           ^
      \ Schiff /                   Schiff ===== Kabel === Array
       \  ||  /                             (Keule zeigt zum Schiff)
      ~~~~||~~~~  weiche 70-Grad-Keule
```

## Tasten {#sonar-keys}

<!-- keys:sonar -->

## Standardablauf {#sonar-sop}

<!-- sop:sonar -->

Gefechtslage:

1. Ein Transient beim Rohrfluten warnt, dass ein Schuss folgen kann: Bugsonar und Schleppsonar auf die Peilung richten und Gegenmaßnahmen bereithalten. Ein Starttransient, hochfrequente Ortungsimpulse oder ein neuer lauter Breitbandkontakt ohne Tonale mit schnell wandernder Peilung kann ein Torpedo sein. Als Torpedo klassifizieren (`C`) und die Peilung sofort an die Brücke melden.
2. Fokus auf dem feindlichen U-Boot halten, damit das Draht-Datum des Torpedos frisch bleibt.
3. Nur pingen, wenn die Tiefe für den Schuss fehlt oder der Kontakt verloren geht: das U-Boot hört einen Ping bis 60 sm und weicht aus.

## Tipps für Profis {#sonar-tips}

- Verstärkung (`I`/`O`) ändert nur Anzeige und Audio, nicht die Ortung. Schwarzwert (`Ctrl+I`/`Ctrl+O`) und Kontrast (`Shift+I`/`Shift+O`) heben schwache Spuren hervor; `Shift+C` wechselt die Phosphorfarbe.
- `D` oder `A`/`B`/`H` wählen Breitband-, gefiltertes oder Überlagerungs-Abhören. Überlagerung verschiebt das tiefe Band auf etwa 700 Hz, damit tiefe Töne hörbar werden.
- Das Abhör-Audio läuft etwa anderthalb Sekunden hinter der Anzeige (Remote-Crew-Browser etwa zwei Sekunden), damit es auch unter Last nicht aussetzt. Nach dem Schwenken der Abhörpeilung geht der alte Strahl nach dieser Verzögerung in den neuen über; der Ton bricht nicht ab.
- TAS unter die gemessene Schicht legen, um tiefe Ziele zu hören; das HMS für flache Ziele nutzen. Beide Arrays arbeiten parallel.
- Die TMA-Seite zeigt die aus der übernommenen Lösung abgeleitete Annäherungsrate: positiv heißt, das Ziel kommt näher.
- Weichen TAS und HMS um 9 Grad oder mehr ab, den Kontakt als möglichen Geist behandeln (die Anzeige markiert ihn) und durch eine Wende klären.
- Die Schleppantenne ist eine Linie: sie kann eine Peilung nicht von ihrem Spiegelbild zum Kabel unterscheiden. Ein nur auf der TAS gehörter Kontakt wird als "TAS links/rechts mehrdeutig" mit Spiegelpeilung markiert und speist keine TMA; die Anzeige zeigt die von Ihnen gewählte Seite (Standard Steuerbord). 20 Grad drehen und beide Spuren beobachten: die echte bleibt stetig, die Geisterspur springt (der Status lautet dann "Wende gefahren - Spuren vergleichen"). Auf der Breitband- oder Fusionsseite zeigt `X` die andere Seite, `Umschalt+X` bestätigt die angezeigte; nichts wird für Sie entschieden. Eine falsch bestätigte Seite bleibt gespiegelt (die TMA-Residuen zeigen es; `X` öffnet die Wahl wieder). Eine Peilung des Rumpfsonars löst die Seite durch Messung auf. Peilungen zu den Kabelenden (Endfire) sind zudem ungenauer als querab.
- `Umschalt+F` wählt das DEMON-Trägerband (200-800, 400-1400 oder 1000-2000 Hz): das Band suchen, in dem das Kavitationsrauschen am stärksten ist. `Strg+F` stellt den Überlagerungsversatz (400/700/1000/1200 Hz) zum Abhören tiefer Töne ein.
- Im Kontaktanalysator (`F8`) ordnet `Enter` bei gewähltem Kontakt das angezeigte Katalogprofil diesem Kontakt zu, `Umschalt+Enter` löscht die Zuordnung. Die Zuordnung ist Ihr Vermerk: sie erscheint in der Kontaktliste, wird gespeichert und ändert nie die Klassifizierung oder die Waffensperren des Kontakts.
- Ein Kontakt geht 120 s nach der letzten Ortung verloren. Schwache Kontakte weiter verfolgen oder per Ping wieder erfassen.
- Wracks liefern echte Echos ohne Doppler. Ein U-Boot, das still neben einem kartierten Wrack auf Grund liegt, versteckt sich vor einem CW-Ping in dessen Echo (750 m Entfernungszelle); ein LFM-Ping löst etwa 8 m auf und kann U-Boot und Wrack trennen. Jedes Wrack, das der Gegner erreichen konnte, ist verdächtig.
- Der Bathythermograph (`E`) misst bis zum Grund, höchstens 1500 m. Erst nach einer Messung zeigt die Wetter- & Sonar-Analyse (`0`) die Schicht, die Schattenzone darunter und einen SOFAR-Kanal.
- Das Sonar benennt nie einen Torpedo oder ein U-Boot. Es meldet, was es hört: einen mechanischen Starttransient (hörbar bis 35 NM), hochfrequente Ortungsimpulse (etwa 6 NM) oder den kurzen Transienten eines U-Boots, das ein Torpedorohr flutet und die Mündungsklappe öffnet (eine Warnung, dass ein Schuss folgen kann: bis 8 NM, langsames, leises Fluten nur bis 1,5 NM; beides schrumpft mit Eigenlärm, Seegang und Sonarschaden) als Peilung, die der Brückenalarm 60 s hält, und Sinkgeräusche, wenn ein Rumpf sinkt. Das OPZ-Symbol eines Sonarkontakts folgt allein Ihrer Klassifizierung; ein unklassifizierter Kontakt bleibt unbekannt.

## Nicht modelliert {#sonar-limits}

- `T` schaltet den Löser hinter der Trainingshilfe um; der automatische Löser schreibt nie selbst einen Fix.
- Keine wählbare Split-Window-Normalisierung (TPSW); stattdessen Verstärkung, Schwarzwert und Kontrast nutzen.
- Der tote Winkel blendet nur das passive Horchen; ein aktiver Ping des Bugsonars erfasst weiter den ganzen Kreis.
