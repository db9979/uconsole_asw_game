# 7 Maschinenraum {#station-engine}

## Zweck {#engine-purpose}

Der Maschinenraum stellt die Fahrstufe ein und verwaltet die akustische Signatur des Schiffes. Fahrt ist der wichtigste Zielkonflikt der U-Jagd: schnell, um ein Datum zu erreichen, langsam und leise, um überhaupt etwas zu hören.

## Seiten {#engine-pages}

| Seite | Zeigt |
|---|---|
| 1 Telegraph & Fahrt | Telegrafenstufen, Fahrtanzeige, Wellendrehzahl und Eigengeräusch, Zustandslampen |
| 2 Systeme | Meldetafel, Brennstoffbunker, Anzeigen für Rollen, Stampfen und Krängung, Schema der Schiffsabschnitte |

## Anzeigen und Instrumente {#engine-displays}

Der Maschinenraum ist ein Maschinenleitstand. Seite 1 zeigt den Maschinentelegraphen als Säule leuchtender Stufen, ein großes Fahrtinstrument (die befohlene Fahrt als gelbe Marke, die Schadensbegrenzung rot), Instrumente für Wellendrehzahl und Eigenlärm (Kavitationsbereich rot) und Lampen für Welle, Anlage, Kurs, Akustikmodus, Kavitation und Fahrtgrenze. Seite 2 **Systeme** hat eine Warn- und Meldetafel aus Statuslampen (dunkel, wenn aus, grün im Betrieb, gelb bei einer Warnung, rot bei einem Alarm) mit einer Sammellampe, die Alarme und Warnungen zählt, den Kraftstoffbunker als Tanksäule mit Vorrat, Verbrauch, Ausdauer und Reichweite, Instrumente für Rollen, Stampfen und Schlagseite und ein Bild der Schiffsabschnitte vom Bug zum Heck zwischen Steuerbord- und Backbordrumpf, jeder mit Wasserstand, Zustand, Wassereinbruch- und Brand-LEDs und den nummerierten Reparaturtrupps.

![Antrieb auf der uConsole](figure:station-engineering)

![Antrieb, Systemseite](figure:engineering-systems)

![Antrieb im Remote-Crew-Browser](figure:web-engine-desktop)

```text
 TELEGRAPH      kn     Eigenlärm
   FLANK        31     |##########|  kavitiert
   FULL         16     |#######   |  kavitiert über 15 kn
 > HALF         10     |####      |
   SLOW          6     |##        |
   STOP          0     |          |
   (ASTERN       3 kn, eigener Zustand)

 Lärm   ^                    ____ Kavitation (>= 0,85)
        |                ___/
        |           ____/
        |      ____/
        |_____/
        +----+------------+--------+---> kn
             4           15        31
```

- Der Eigenlärm steigt linear von 4 kn bis 31 kn. Die Schrauben kavitieren, wenn die Flügelspitzengeschwindigkeit für den Wasserdruck an den Schrauben zu hoch ist: bei ruhiger See ab 15 kn, bei schwerer See früher, wenn das Stampfen das Heck anhebt. Kavitation hebt den Lärm auf mindestens 0,85 und senkt die passive Sonarreichweite auf 35 %.
- Die Lampe der befohlenen Stufe leuchtet (ZURÜCK gelb). Liegt eine Direktfahrt (`V` auf der Brücke) zwischen zwei Stufen, nennt eine Warnzeile die befohlene Fahrt, damit HALF 10 kn bei befohlenen 12 kn nicht mit HALF verwechselt wird.
- Modus LEISE senkt den Eigenlärm auf 65 % und begrenzt die Fahrt auf 12 kn.
- Anlagenwahl (`G`): AUTO fährt die Anlage wie bisher. DIESEL ist die leise Anlage (Eigenlärm etwa -4 dB, Brennstoff -10 %), begrenzt aber auf 18 kn; TURBINE gibt volle Fahrt bei etwa +3 dB und +25 % Brennstoff. Die Wahl steht auf Seite 2 und im Maschinenraum des Browsers.
- Die Wellendrehzahl folgt dem Festpropeller: bei konstanter Fahrt etwa 5,8 U/min je Knoten (146 U/min bei 25 kn, 181 U/min bei 31 kn Höchstfahrt). Beim Beschleunigen hält das Fahrprogramm die Welle höchstens etwa 11 U/min vor der aktuellen Fahrt; beim Abbremsen wird die Steigung umgesteuert und die Welle läuft mit 20 U/min im Leerlauf. Die eigene Wellenlinie im LOFAR wandert mit der Fahrt.
- Maschinenschaden begrenzt die Fahrt auf 15 kn (beschädigt) oder 8 kn (zerstört).
- Der Kraftstoffverbrauch folgt der abgegebenen Propellerleistung: bei konstanter Fahrt wächst er mit der dritten Potenz der Fahrt, Beschleunigen und Bremsen kosten zusätzlich. Ein leichteres Schiff (verbrauchter Kraftstoff) beschleunigt etwas schneller; Flutwasser macht es langsamer und tiefer. Schwere See erhöht den Widerstand und kostet bei FULL bis etwa 1 kn. Mit leeren Tanks steht die Welle, und kein Maschinenbefehl wird angenommen.
- **Maschinenleitstand (Browser):** im Browser ist die Bildfläche des Maschinenraums ein Maschinenleitstand. Eine **Warn- und Meldetafel** aus Statuslampen (dunkel, wenn aus, türkis im Betrieb, gelb bei einer Warnung, rot blinkend bei einem Alarm, jede mit ihrem Wert) zeigt Wellen, Anlage Auto, Diesel, Gasturbine, Schleichfahrt, Kavitation, Kraftstoff, Fahrtbegrenzung, Zustand der Maschinenanlage, Wassereinbruch und Brand im Maschinenraum, Reparaturtrupps, Brände und geflutete Abschnitte an Bord, Grundberührung, Schleppsonar, Seegang und Rollwinkel; die Sammellampe im Schild zählt Alarme und Warnungen. Darunter stehen runde **Instrumente** für Fahrt (die befohlene Fahrt als gelbe Marke, die Schadensbegrenzung rot), Wellendrehzahl, Eigenlärm (Kavitationsbereich rot), Kraftstoff, Rollen und Stampfen, der **Kraftstoffbunker** mit Vorrat, Fassungsvermögen, Verbrauch, Ausdauer und Reichweite und die **Schiffsabschnitte** vom Bug zum Heck zwischen den Rumpfstreifen Steuerbord und Backbord, jeder mit Wasserstand, Zustand, Wassereinbruch- und Brandlampe und den arbeitenden Trupps. Der Leitstand zeigt nur an; die Befehle bleiben im Stationsbereich rechts.

## Tasten {#engine-keys}

<!-- keys:engine -->

## Maus {#engine-mouse}

Jede Taste in der Tastenleiste am Fuß der Station lässt sich anklicken; gedrückt halten hält die Taste. Lampen, Seitenreiter und Tastenhinweise im Text sind ebenfalls anklickbar (Kapitel Werkzeuge, Maus). Außerdem:

- `+` oder `-` in der Tastenleiste gedrückt halten schaltet den Telegrafen; die Lampen drücken ihre Tasten.

## Standardablauf {#engine-sop}

<!-- sop:engine -->

## Tipps für Profis {#engine-tips}

- Fahrtänderungen dauern Minuten; vor einem Horchschlag früh verlangsamen.
- Das Schleppsonar lässt sich nur zwischen 3 und 12 kn ausbringen oder einholen; über 20 kn mit Kabel draußen geht es verloren.
- Ein feindliches U-Boot hört Sie besser als Sie es, wenn Sie kavitieren. Nur sprinten, wenn der erwartete Kontakt weit entfernt ist.

## Nicht modelliert {#engine-limits}

- Keine Einzelwellensteuerung; die Anlagenwahl gilt für beide Wellen.
