# 7 Maschinenraum {#station-engine}

## Zweck {#engine-purpose}

Der Maschinenraum stellt die Fahrstufe ein und verwaltet die akustische Signatur des Schiffes. Fahrt ist der wichtigste Zielkonflikt der U-Jagd: schnell, um ein Datum zu erreichen, langsam und leise, um überhaupt etwas zu hören.

## Anzeigen und Instrumente {#engine-displays}

Seite 1 ist der Maschinentelegraph mit Stufe, Fahrt, Wellendrehzahl und Eigenlärm; Seite 2 zeigt Maschinenanlagen, Kraftstoff und Schadenszustand.

```text
 TELEGRAPH      kn     Eigenlärm
   FLANK        25     |##########|  kavitiert
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
             4           15        25
```

- Der Eigenlärm steigt linear von 4 kn bis 25 kn. Ab 15 kn kavitieren die Schrauben: der Lärm liegt bei mindestens 0,85, die passive Sonarreichweite fällt auf 35 %.
- Modus LEISE senkt den Eigenlärm auf 65 % und begrenzt die Fahrt auf 12 kn.
- Die Wellendrehzahl beträgt etwa 20 + 2,4 x Fahrt. Die eigene Wellenlinie im LOFAR wandert mit der Fahrt.
- Maschinenschaden begrenzt die Fahrt auf 15 kn (beschädigt) oder 8 kn (zerstört).
- Der Kraftstoffverbrauch steigt mit der Fahrt. Mit leeren Tanks steht die Welle, und kein Maschinenbefehl wird angenommen.

## Tasten {#engine-keys}

<!-- keys:engine -->

## Standardablauf {#engine-sop}

<!-- sop:engine -->

## Tipps für Profis {#engine-tips}

- Fahrtänderungen dauern Minuten; vor einem Horchschlag früh verlangsamen.
- Das Schleppsonar lässt sich nur zwischen 3 und 12 kn ausbringen oder einholen; über 20 kn mit Kabel draußen geht es verloren.
- Ein feindliches U-Boot hört Sie besser als Sie es, wenn Sie kavitieren. Nur sprinten, wenn der erwartete Kontakt weit entfernt ist.

## Nicht modelliert {#engine-limits}

- Keine Auswahl zwischen Gasturbine und Diesel und keine Einzelwellensteuerung.
- Keine Versorgung auf See.
