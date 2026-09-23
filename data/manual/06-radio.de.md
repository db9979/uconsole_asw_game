# 6 Funk {#station-radio}

## Zweck {#radio-purpose}

Der Funkraum wickelt die Verbindung zum Hauptquartier und die Kurzwellenpeilung (HFDF) ab. Das Hauptquartier sendet Befehle, Wetterberichte und ROE-Änderungen per Fernschreiber. HFDF peilt U-Boote, die auf Kurzwelle senden oder schnorcheln, bis 120 sm, weit jenseits der Sonarreichweite.

## Anzeigen und Instrumente {#radio-displays}

Seite 1 listet aktuelle HFDF-Signale und das Peilprotokoll; Seite 2 ist der Fernschreiber mit dem HQ-Verkehr.

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
- Jedes Signal zeigt Frequenz und Ausbreitung. Ein U-Boot, das eine ferne Landstation ruft, wählt tagsüber eine hohe Frequenz (Bodenwelle bis etwa 95 sm hörbar) und nachts eine niedrigere (etwa 150 sm). Jenseits der Sprungdistanz, einige hundert sm entfernt, kommt stattdessen die Raumwelle an.
- Protokollierte Linien und Kreuzpeilungen erscheinen auf den Karten von Brücke, Waffenzentrale und Helikopter.
- Eine zweite Peilung desselben Signals ergibt eine Kreuzpeilung, wenn sie mindestens 1 sm entfernt von der ersten und innerhalb von 300 s genommen wird.
- Der Fernschreiber bringt außerdem alle 30 Minuten den Wetterbericht und HQ-Meldungen (Bedrohungswarnungen, ROE FREI).

## Tasten {#radio-keys}

<!-- keys:radio -->

## Standardablauf {#radio-sop}

<!-- sop:radio -->

## Tipps für Profis {#radio-tips}

- Die beiden Peilungen von Positionen quer zur erwarteten Peillinie nehmen: je rechtwinkliger sie sich schneiden, desto kleiner die Fehlerellipse.
- Ein sendendes oder schnorchelndes U-Boot ist meist flach und langsam: ein guter Moment, mit dem Helikopter heranzugehen.
- HFDF-Peilung mit einer Sonarpeilung kombinieren ergibt schnell eine Positionsschätzung.

## Nicht modelliert {#radio-limits}

- Keine eigenen Funksprüche oder Meldungen an das HQ; kein Fernmeldeplan und keine Kryptierung.
- Keine Frequenzabstimmung: HFDF überwacht das ganze KW-Band und listet die erfassten Signale mit ihrer Frequenz.
