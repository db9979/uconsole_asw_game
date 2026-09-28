# 5 OPZ / CIC {#station-opz}

## Zweck {#opz-purpose}

Die Operationszentrale (OPZ / CIC) bildet das Lagebild über Wasser: Überwasser- und Luftradar, AIS, freigegebene Sonar- und ESM-Peilungen, manuelle Fusion von Meldungen, NATO-Zugehörigkeit und Luftverteidigung. Sie übergibt bezeichnete Tracks an Sonar und Waffenzentrale.

## Anzeigen und Instrumente {#opz-displays}

Seite 1 ist eine freie Karte über die volle Höhe mit allen veröffentlichten Tracks; Seite 2 ist die Zielseite für den gewählten Track; Seite 3 führt den Seefernaufklärer. Das schiffszentrierte Radarbild hat eine eigene Bereichsskala (10/20/40/80/120 sm, `Bild Auf`/`Bild Ab`), unabhängig vom Kartenzoom (Mausrad bis 5 sm Radius; Ziehen verschiebt; `K` folgt). Eigene Einheiten stammen aus dem Datenlink, nicht aus Sensoren: das Schiff, der fliegende Helikopter ("HSP-5 DL") und jede laufende eigene Waffe, also Torpedos von Schiff, Helikopter oder ASROC (`T<n>`), ASROC im Flug und ESSM, jeweils mit Freund-Symbol und Kursstrich.

```text
 NATO-Rahmenfarben (Bedienervermerk, keine Wahrheit)
   gelb = UNBEKANNT  blau = FREUND  grün = NEUTRAL  rot = FEIND

 Meldungsquellen: Radar  AIS  Sonar(freigegeben)  ESM  HFDF  Ausguck
 Trackliste:  ID  Quelle  Peilung  Entfernung  Kurs/Fahrt  Alter  Klasse
```

- **Überwasserradar:** 30 sm, begrenzt durch Radarhorizont (20-m-Mast) und Zielhöhe; getauchte U-Boote sind unsichtbar.
- **Mast- und Schnorchelechos:** ein U-Boot auf Sehrohrtiefe mit ausgefahrenem Mast oder Schnorchelkopf (Mast einer Crew, ein schnorchelndes U-Boot oder eines auf Funktiefe) gibt ein winziges Echo: bei ruhiger See findet es etwa jeder zweite Umlauf auf 7 sm, bei Seegang 3 auf etwa 2,5 sm, bei Seegang 5 unter 1 sm. Es erscheint nur als bloßer Punkt, der etwa 6 s nachleuchtet, ohne Symbol, Beschriftung und Track. Den Punkt im PPI anklicken oder `B` drücken (neuester Punkt) markiert ihn: aus dieser Messung beginnt ein Radartrack `R-…`, und weitere Echos desselben Masts führen ihn fort; ohne neue Echos verblasst er nach 30 s. Echos und Markierung werden nicht gespeichert.
- **Luftradar:** 100 sm für Flugzeuge und Seezielflugkörper (ASM).
- Die Antenne dreht sich alle 4 s einmal: ein Kontakt wird nur aktualisiert, wenn der Strahl über ihn streicht, und jeder Umlauf erfasst ihn mit einer Wahrscheinlichkeit, die mit der Entfernung sinkt (50 % bei Nennreichweite für ein Schiff in Breitseite; Ziele mit spitzem Aspekt werden später gesehen, schwankende Echos können einen Umlauf verfehlen). Seegangsclutter wächst mit dem Seegang (etwa -5 % bei Seegang 4, -25 % bei 6), Regen dämpft das Echo (-10 % Überwasser, -20 % Luft); ab Seegang 5 nehmen Messfehler zu. Innerhalb 3 sm hält das Such-/Folgeradar des CIWS einen anfliegenden Flugkörper ununterbrochen, solange das CIWS freigegeben ist.
- **AIS:** zivile Schiffe senden Kurs und Fahrt alle 2-10 s (vor Anker alle 3 min) und ihren Namen etwa alle 6 min. Der UKW-Empfänger hört sie nur in Sichtlinie (etwa 20 NM). Ein Radartrack eines Zivilschiffs zeigt Name und Kurs erst, wenn die passende AIS-Meldung empfangen wurde; Radar allein liefert nur die Position. Optionaler Live-AIS/ADS-B-Verkehr ist von simuliertem Verkehr nicht unterscheidbar.
- **Fusion:** 2-8 Rohmeldungen markieren (`Leertaste`) und zu einem Bedienertrack fusionieren (`L`); `Shift+L` löst ihn auf. Eine Fusion, deren Meldungen von genau einem Sonarkontakt stammen, lässt sich der Waffenzentrale zuweisen; ihre Klassifizierung zählt für die Feuerleitung, solange das Sonar den Kontakt nicht selbst klassifiziert hat, und ihre Zugehörigkeit gilt für diesen Kontakt. Eine Fusion besteht nur, solange alle ihre Meldungen aktuell sind.
- **Unterdrückung:** `Entf` blendet eine Meldung lokal aus; `H` zeigt unterdrückte Meldungen wieder.

## Seefernaufklärer {#opz-mpa}

Seite 3 führt einen Seefernaufklärer (MPA) auf Abruf vom nächsten eigenen Flugplatz (ohne Flugplatz kommt er vom nächsten Kartenrand). Er fliegt im Transit 300 kn und kreist mit 200 kn auf einem 3-sm-Kreis um sein Suchgebiet. Ein Einsatz dauert bis zu 5 h einschließlich 15 min Reserve; am Mindestkraftstoff fliegt er selbst zurück. Nach der Landung braucht er 30 min am Boden und fliegt dann noch einmal: 2 Einsätze je Mission mit je 16 Sonarbojen und 2 leichten Torpedos.

- `A` fordert das Flugzeug an (es fliegt zuerst zur Schiffsposition) oder schickt es heim.
- `W` legt das Suchgebiet auf die geplottete Position des gewählten Tracks (ohne Auswahl auf das Schiff); ein Klick in die Karte legt es auf diesen Punkt. Ein reiner Peilungstrack hat keine Position zum Anfliegen.
- `Z` plant ein Bojenmuster (Feld, Sperre, Kreis) um das Suchgebiet; das Flugzeug fliegt die Punkte ab und wirft an jedem eine Boje. `Shift+Z` bricht das Muster ab. `X` wirft eine Boje dort, wo das Flugzeug ist, `Y` schaltet seine Bojen zwischen PASSIV und AKTIV.
- `T` schaltet das Seeraumradar des Flugzeugs. Aus 300 m sieht es Schiffe und aufgetauchte oder mit Mast fahrende U-Boote bis 60 sm (begrenzt durch den Radarhorizont); seine Kontakte erscheinen als `RADAR-MPA`-Tracks mit dem Flugzeug als Beobachter.
- `D` wirft einen Torpedo auf den zugewiesenen Sonarkontakt. Es gelten dieselben Prüfungen wie beim Helikopter (aktueller, als U-Boot klassifizierter Kontakt, Einsatzregeln, unter Standard-ROE eine frische Ortung), und das Flugzeug muss höchstens 2 sm vom Datum entfernt sein.

Alles, was das Flugzeug erfährt, erreicht das Schiff nur per Datenlink bis 250 sm. Seine Bojen melden nur, solange das Flugzeug höchstens 50 sm von ihnen entfernt ist; fliegt es weg oder landet es, verstummen sie für das Schiff. Die Seitenleiste zeigt Zustand, Peilung und Entfernung, Restzeit auf Station, Vorräte, verbleibende Einsätze und wie viele seiner Bojen übertragen werden.

## Tasten {#opz-keys}

<!-- keys:opz -->

## Standardablauf {#opz-sop}

<!-- sop:opz -->

Ablauf Luftverteidigung (Flugkörper im Anflug):

```text
  40 sm  ASM erfasst (Luftradar / ESM-Sucherpeilung)
  30 sm  ESSM-Bereich           -> E / Strg+Enter (2 Feuerkanäle)
   8 sm  Düppelkegel            -> G (40 % Zielverlust, kurz blind)
 1,5 sm  CIWS                   -> muss mit I freigegeben sein
```

1. Luftradar ein (`Shift+R`), ASM-Track wählen (`Links`/`Rechts`).
2. Erst Düppel und Manöver, dann ESSM. Nur 6 ESSM sind geladen.
3. CIWS freigegeben lassen, solange Flugkörper anfliegen; zurückgehaltenes CIWS feuert nie.

## Tipps für Profis {#opz-tips}

- Radar ist eine Aussendung, die feindliches ESM auffassen kann. Radare abschalten (EMCON), wenn Tarnung wichtiger ist als das Luftlagebild.
- Das Radar weiß nicht, was ein Luftkontakt ist. Die Bedrohungsbewertung markiert einen Luftkontakt nur aus seinen eigenen Messungen als möglichen Flugkörper (ASM): schneller als 300 kn in höchstens 150 m Höhe oder ein Störstrobe; ein tief und schnell anfliegendes Angriffsflugzeug kann dieselbe Markierung auslösen. Die Markierung braucht etwa eine Sekunde Plots, CIWS und ESSM bekämpfen nur markierte Tracks, und HFDF-Fixe sowie unklassifizierte Sonarkontakte tragen keine Domäne, bis Sie sie klassifizieren.
- Seezielflugkörper fliegen in etwa 20 m Höhe (auf den letzten 5 sm in 5 m): das Radar sieht sie erst innerhalb etwa 20 sm, und ein störender Flugkörper liefert bis zum Durchbrennen nur eine Home-on-Jam-Peilung (HOJ). Flugkörper fliegen trägheitsgelenkt zu ihrem Startdatum; dann muss der Suchkopf das Schiff 1,5 s in seinem Kegel haben, bevor er ansteuert. Angriffsflugzeuge steigen vor jeder Salve für einige Sekunden auf etwa 300 m, um ihr Feuerleitradar aufzuschalten (eine ESM-Warnung und ein früher Radarkontakt).
- Düppel legt neben dem Schiff eine Wolke, die in etwa 3 s aufblüht und mit dem Wind treibt; früh genug werfen, damit die Wolke aufblühen kann. Das CIWS muss erst auf den Flugkörper schwenken und trifft meist auf den letzten paar hundert Metern.
- Zugehörigkeit ist Ihr Vermerk. Ein als FREUND oder NEUTRAL markierter Kontakt, oder eine Fusion, die ihn enthält, sperrt jeden Torpedoschuss darauf.
- Kartensymbole folgen dem NATO-Stil auf der uConsole und auf jeder Remote-Crew-Karte: der Rahmen zeigt Ihre Zugehörigkeit (Feind Raute, Neutral Quadrat, Freund breites Rechteck, Unbekannt ohne Rahmen), das innere Zeichen die beobachtete Domäne.
- `J` vergibt eine gemeinsame Track-ID, die die ganze Crew (und Remote-Crew-Browser) sieht.
- `Enter` bestätigt einen Angriff auf einen Live-Kontakt (echter Verkehr), nachdem Sie ihn als feindlich klassifiziert haben; auf unklassifizierte Kontakte wird nie automatisch gefeuert.

## Nicht modelliert {#opz-limits}

- Die Bojen des Helikopters gehören zur Helikopterstation; die OPZ führt nur die Bojen des Seefernaufklärers.
- Der Seefernaufklärer hat kein Tauchsonar, kein MAD und kein eigenes ESM; er kann nicht abgeschossen werden.
- Keine automatische sensorübergreifende Korrelation; Fusion ist manuell.
- Keine Link-gestützte Luftraumführung befreundeter Flugzeuge.
