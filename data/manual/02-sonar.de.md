# 2 Sonar {#station-sonar}

## Zweck {#sonar-purpose}

Die Sonarzentrale ist der Hauptsensor der U-Jagd. Sie horcht passiv mit Bugsonar (HMS) und Schleppsonar (TAS), analysiert Signaturen in LOFAR und DEMON, schätzt die Zielbewegung per TMA, misst das Schallprofil und sendet auf Befehl einen aktiven Ping. Sie klassifiziert Kontakte und gibt sie an OPZ und Waffenzentrale frei.

## Anzeigen und Instrumente {#sonar-displays}

Die Station hat sechs Seiten. `Bild Auf`/`Bild Ab` (oder nochmals `2`) blättert sie.

| Seite | Zeigt | Wofür |
|---|---|---|
| BROADBAND | Peilung-Zeit-Wasserfall | Kontakte entdecken und ihrer Peilung folgen |
| LOFAR | Frequenz-Zeit-Wasserfall, 0-300 Hz | Tonale Linien: Maschinen, Welle, Schraubensignaturen |
| DEMON | Modulationsspektrum des Horchstrahls | Hypothesen zu Blatt- und Wellenfrequenz |
| TMA | Lösung für den fokussierten Kontakt | Schätzung von Entfernung, Kurs und Fahrt |
| UMWELT / FUSION | Schallprofil, Schicht, CZ, Array-Vergleich | TAS-Tiefe wählen, Geisterkontakte erkennen |
| ACTIVE | Gespeicherte Echos mit Alter und Fehler | Entfernung und Tiefe aus Pings |

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

- Stehende senkrechte Linien sind **Töne** (Schmalband): Generatoren, Pumpen, Wellenlinien. Mehrere Linien bei ganzzahligen Vielfachen einer Frequenz bilden eine Harmonischenfamilie; `K` schaltet die erkannte Harmonischen-Hypothese.
- Das eigene Schiff erzeugt eine Wellenlinie bei etwa 10 + 1,9 x eigene Fahrt Hz. `N` blendet sie per Notch aus.
- `Leertaste` hält Spitzen, damit schwache Töne hervortreten.
- Der Spektrumstreifen über dem Wasserfall schreibt die Frequenz über jede deutliche Linie (zwischen den Klassen interpoliert; mit `Leertaste` die gehaltene Hüllkurve). Wo sich Werte überdecken würden, behält die stärkere Linie ihre Beschriftung. Der Remote-Crew-Browser beschriftet seine Spektren genauso.
- `F` wählt das Analyseband: FULL 0-300, LOW 4-80, SHAFT 8-55, MID 20-120 Hz.

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

Die Anzeige zeigt gemessene Modulation, keine sichere Identität. Die Analysefenster sind bis zu 2 s lang: nach einer Peilungsänderung mindestens eine Sekunde horchen, bevor Sie urteilen. Gerankte Kandidaten aus dem Akustikkatalog erscheinen als Hinweis; die Klassifizierung bleibt Ihre Entscheidung. Der Spektrumstreifen beschriftet jede deutliche Modulationslinie mit ihrer Frequenz; die stärkste ist bernsteinfarben markiert.

### TMA, Umwelt und Aktiv {#sonar-tma-env}

- **TMA** löst Entfernung, Kurs und Fahrt aus einer Peilungsreihe des fokussierten Kontakts. Nötig sind mindestens 4 Peilungen über 180 s und eine eigene Kursänderung von mindestens 6 Grad; die Entfernung gilt ab Qualität 0,35. Tiefe schätzt TMA nicht. Eine Gittersuche findet den Bereich, eine Levenberg-Marquardt-Anpassung verfeinert ihn; die Detailzeile zeigt die 1-Sigma-Unsicherheitsellipse. Das stärkste Tonal wird mit seiner Dopplerverschiebung gemessen ("Tonal (Doppler)"): ein nah vorbeiziehendes Ziel verschiebt seine Frequenz, das legt die Entfernung auch ohne eigene Wende fest. Sonobojen-Peilungen gehen mit der Boje als Beobachter in dieselbe Schätzung ein, ein Bojenfeld liefert deshalb schnell Entfernung.
- **UMWELT / FUSION** zeigt den Bathythermographen (`E`, 60 s Abklingzeit): gemessene Schichttiefe, Schallgeschwindigkeitsprofil und Konvergenzzonen, dazu den Vergleich HMS/TAS. Peilungen innerhalb 5 Grad bestätigen sich; ab 9 Grad Abweichung wird ein möglicher Geisterkontakt markiert. Die Schicht ist nicht fest: Nachmittagssonne macht sie flacher (etwa 8 m), starker Wind mischt sie über Stunden tiefer, und interne Wellen verschieben sie um einige Meter. Den BT nach einigen Stunden oder einem Wetterwechsel wiederholen. Das gemessene Profil ist die echte temperaturabhängige Schallgeschwindigkeit (Mackenzie-Gleichung) und fällt deshalb unterhalb der Schicht ab.
- **ACTIVE** listet die Echos der letzten 120 s: Peilung, Entfernung und Tiefe (+/-12 m). Ein Ping-Fix veraltet nach 120 s. `W` wählt den Puls: **CW** (1-s-Ton) misst die Entfernung grob (etwa 0,1-0,3 sm), trennt aber über den Doppler ein bewegtes Ziel vom Nachhall des Meeresbodens; **LFM** (100-Hz-Sweep) misst die Entfernung auf wenige Meter und gewinnt 20 dB gegen Rauschen, ein langsames oder stehendes Ziel bleibt aber im Nachhall. Die Echostärke hängt vom Aspekt (breitseits etwa 15 dB stärker als von vorn) und der Größe des Ziels ab. Felsgrund hallt viel stärker nach als Schlick; kartierte Wracks liefern echte Echos ohne zugehörigen Kontakt ("nicht zugeordnetes Echo").

## Bugsonar und Schleppsonar {#sonar-arrays}

| | HMS (Bug) | TAS (Schlepp) |
|---|---|---|
| Passivreichweite | 1,0 x Basis | 1,4 x Basis, minus 3 % je Knoten |
| Strahlbreite | 12 Grad | 6 Grad |
| Peilfehler | +/-6 Grad | +/-2 Grad |
| Eigenlärm | voll | 35 % des Bugsonars |
| Pingreichweite | 1,0 x | 0,8 x |
| Handhabung | immer bereit | ausbringen 360 s, einholen 480 s, nur bei 3-12 kn, 30 s Beruhigung |

- TAS-Tiefe 20-260 m (`U`/`V` in 10-m-Schritten), begrenzt auf 260 m minus 4 m je Knoten eigener Fahrt. Ab 30 m Tiefe und in derselben Schicht wie das Ziel gewinnt es weitere 25 %.
- Über 20 kn mit ausgebrachtem Kabel erleidet das Array einen dauerhaften FAULT.
- Das Array folgt einer Kursänderung mit etwa 45 s Verzögerung; während es nachschwenkt, sind seine Peilungen weniger verlässlich.

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

1. Ein Starttransient, hochfrequente Ortungsimpulse oder ein neuer lauter Breitbandkontakt ohne Tonale mit schnell wandernder Peilung kann ein Torpedo sein. Als Torpedo klassifizieren (`C`) und die Peilung sofort an die Brücke melden.
2. Fokus auf dem feindlichen U-Boot halten, damit das Draht-Datum des Torpedos frisch bleibt.
3. Nur pingen, wenn die Tiefe für den Schuss fehlt oder der Kontakt verloren geht: das U-Boot hört einen Ping bis 60 sm und weicht aus.

## Tipps für Profis {#sonar-tips}

- Verstärkung (`I`/`O`) ändert nur Anzeige und Audio, nicht die Ortung. Schwarzwert (`Ctrl+I`/`Ctrl+O`) und Kontrast (`Shift+I`/`Shift+O`) heben schwache Spuren hervor; `Shift+C` wechselt die Phosphorfarbe.
- `D` oder `A`/`B`/`H` wählen Breitband-, gefiltertes oder Überlagerungs-Abhören. Überlagerung verschiebt das tiefe Band auf etwa 700 Hz, damit tiefe Töne hörbar werden.
- Das Abhör-Audio läuft etwa eine Sekunde hinter der Anzeige, damit es auch unter Last nicht aussetzt. Nach dem Schwenken der Abhörpeilung geht der alte Strahl nach etwa einer Sekunde in den neuen über; der Ton bricht nicht ab.
- TAS unter die gemessene Schicht legen, um tiefe Ziele zu hören; das HMS für flache Ziele nutzen. Beide Arrays arbeiten parallel.
- Die TMA-Seite zeigt die aus der Lösung abgeleitete Annäherungsrate: positiv heißt, das Ziel kommt näher.
- Weichen TAS und HMS um 9 Grad oder mehr ab, den Kontakt als möglichen Geist behandeln (die Anzeige markiert ihn) und durch eine Wende klären.
- Die Schleppantenne ist eine Linie: sie kann eine Peilung nicht von ihrem Spiegelbild zum Kabel unterscheiden. Ein nur auf der TAS gehörter Kontakt wird als "TAS links/rechts mehrdeutig" mit Spiegelpeilung markiert und speist keine TMA; die angezeigte Seite stimmt nur in der Hälfte der Fälle. 20 Grad drehen (oder den Kontakt auf die HMS bekommen), dann fällt die falsche Seite weg. Peilungen zu den Kabelenden (Endfire) sind zudem ungenauer als querab.
- Ein Kontakt geht 120 s nach der letzten Ortung verloren. Schwache Kontakte weiter verfolgen oder per Ping wieder erfassen.
- Wracks liefern echte Echos ohne Doppler. Ein U-Boot, das still neben einem kartierten Wrack auf Grund liegt, versteckt sich vor einem CW-Ping in dessen Echo (750 m Entfernungszelle); ein LFM-Ping löst etwa 8 m auf und kann Boot und Wrack trennen. Jedes Wrack, das der Gegner erreichen konnte, ist verdächtig.
- Der Bathythermograph (`E`) misst bis zum Grund, höchstens 1500 m. Erst nach einer Messung zeigt die Wetter- & Sonar-Analyse (`0`) die Schicht, die Schattenzone darunter und einen SOFAR-Kanal.
- Das Sonar benennt nie einen Torpedo oder ein U-Boot. Es meldet, was es hört: einen mechanischen Starttransient (hörbar bis 35 NM) oder hochfrequente Ortungsimpulse (etwa 6 NM) als Peilung, die der Brückenalarm 60 s hält, und Sinkgeräusche, wenn ein Rumpf sinkt. Das OPZ-Symbol eines Sonarkontakts folgt allein Ihrer Klassifizierung; ein unklassifizierter Kontakt bleibt unbekannt.

## Nicht modelliert {#sonar-limits}

- Keine manuelle TMA (Punktstapel, manuelle Lösungseingabe); nur der automatische Löser, geschaltet mit `T`.
- Keine wählbare Split-Window-Normalisierung (TPSW); stattdessen Verstärkung, Schwarzwert und Kontrast nutzen.
- Kein harter blinder Baffle-Sektor; Eigenlärm ist eine weiche Keule.
- Kein vom TAS getrenntes Tiefensonar (VDS).
