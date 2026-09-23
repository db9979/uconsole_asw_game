# 8 Helikopterdeck {#station-helicopter}

## Zweck {#helicopter-purpose}

Der HSP-5 „Sea Lynx" verlängert den Arm der Fregatte: er fliegt mit 120 kn zu einem Datum, wirft Sonarbojen, taucht sein eigenes Sonar und greift mit Leichttorpedos an, während die Fregatte leise und außerhalb der Torpedoreichweite bleibt.

## Anzeigen und Instrumente {#helicopter-displays}

Die Station hat vier Seiten (nochmals `8` blättert); sie öffnet auf Seite 3.

| Seite | Inhalt |
|---|---|
| 1 Status | Kraftstoff, Zuladung, Wettergrenzen, Deckzustand |
| 2 Mission | Karte mit Wegpunkt, Bojen, Kontakten |
| 3 Sonar | Kontakte von Tauchsonar und Bojen, Tiefe, Quelle |
| 4 Akustik | Abhören: BROADBAND / LOFAR / DEMON des Tauchsonars oder einer passiven Boje |

```text
         Fregatte                           Wegpunkt (1-30 sm)
            *----------- 120 kn -------------->  H  Schweben + Tauchen
                                                 |
   Bojenlinie (B):  o ---- o ---- o              |  Kabel 15-300 m
   PASSIV: Peilungen;                            )))  Tauchsonar
   zwei Kreuzpeilungen (>= 10 Grad) = Fix           passiv 18 sm
   AKTIV: Entfernung + Peilung alle 30 s            aktiv  14 sm
```

- **Kraftstoff:** 2 Stunden. Der Helikopter kehrt automatisch zurück, wenn nur noch die 20-Minuten-Reserve bleibt. Leerfliegen vor der Landung kostet die Maschine.
- **Startgrenzen:** Wind bis 32 kn, Seitenwind bis 22 kn, Sicht mindestens 2 sm, Seegang höchstens 5, einsatzbereites Flugdeck.
- **Tauchsonar:** Tiefe 15-300 m (Standard 75 m, mindestens 10 m über Grund), passiv 18 sm mit +/-2 Grad, aktiver Ping 14 sm mit 30 s Abklingzeit. Tauchen braucht Wind bis 30 kn und 1 sm Sicht.
- **Sonarbojen:** 5 je Einsatz, 8 sm Reichweite, 60 min Batterie. PASSIV-Bojen liefern Peilungen (wie DIFAR); AKTIV-Bojen liefern Entfernung und Peilung alle 30 s (wie DICASS).
- **Leichttorpedo:** 2 je Einsatz, 55 kn, 12 sm, von der Helikopterposition Richtung Datum geworfen, ohne Draht. Das Ziel muss als U-Boot klassifiziert sein.

## Tasten {#helicopter-keys}

<!-- keys:helicopter -->

Mit „Akustik" markierte Tasten gelten nur auf der Akustikseite (Seite 4).

## Standardablauf {#helicopter-sop}

<!-- sop:helicopter -->

Angriffsablauf:

1. Mit zwei passiven Bojen oder einem Ping von Aktivboje/Tauchsonar orten, bis der Kontakt eine frische Position hat.
2. Als U-Boot klassifizieren (`C`) und als Ziel setzen (`M`).
3. Zum Datum fliegen; Torpedo werfen (`D` oder `Strg+Enter`). Kontakt halten für einen zweiten Wurf.

## Tipps für Profis {#helicopter-tips}

- Das Tauchsonar unter die Schicht legen (mit dem Bathythermographen im Sonar messen), um tiefe U-Boote zu hören.
- Bojen vor den geschätzten Zielkurs legen, nicht auf das letzte Datum.
- `F` bestätigt einen Helikopterkontakt; `Shift+G` gibt ihn wie einen Sonarkontakt an die OPZ frei.
- Auf der Akustikseite schaltet `T` die Horchquelle zwischen Tauchsonar und jeder passiven Boje.
- Den Helikopter rechtzeitig zurückrufen (`H`): die Landung braucht ein einsatzbereites Flugdeck, und die Zuladung wird zwischen Einsätzen nicht ergänzt.

## Nicht modelliert {#helicopter-limits}

- Keine Bojenmuster (Feld, Sperre) und keine Kanalverwaltung; Bojen werden einzeln geworfen.
- Kein MAD (Magnetanomaliedetektor) und kein Radar am Helikopter.
- Nur ein Helikopter.
