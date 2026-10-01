# 5 OPZ / CIC {#station-opz}

## Zweck {#opz-purpose}

Die Operationszentrale (OPZ / CIC) bildet das Lagebild über Wasser: Überwasser- und Luftradar, AIS, freigegebene Sonar- und ESM-Peilungen, manuelle Fusion von Meldungen, NATO-Zugehörigkeit und Luftverteidigung. Sie übergibt bezeichnete Tracks an Sonar und Waffenzentrale.

## Anzeigen und Instrumente {#opz-displays}

Seite 1 ist eine freie Karte über die volle Höhe mit allen veröffentlichten Tracks; Seite 2 ist die Zielseite für den gewählten Track; Seite 3 führt den Seefernaufklärer; Seite 4 führt den Begleitzerstörer einer Gruppenjagd. Das schiffszentrierte Radarbild hat eine eigene Bereichsskala (10/20/40/80/120 sm, `Q`/`E` wie der Zoom an anderen Stationen; `Bild Auf`/`Bild Ab` blättern), unabhängig vom Kartenzoom (Mausrad bis 0,25 sm Radius; Ziehen verschiebt; `K` folgt). Eigene Einheiten stammen aus dem Datenlink, nicht aus Sensoren: das Schiff, der fliegende Helikopter ("HSP-5 DL") und jede laufende eigene Waffe, also Torpedos von Schiff, Helikopter oder ASROC (`T<n>`), ASROC im Flug und ESSM, jeweils mit Freund-Symbol und Kursstrich.

```text
 NATO-Rahmenfarben (Bedienervermerk, keine Wahrheit)
   gelb = UNBEKANNT  blau = FREUND  grün = NEUTRAL  rot = FEIND

 Meldungsquellen: Radar  AIS  Sonar(freigegeben)  ESM  HFDF  Ausguck
 Trackliste:  ID  Quelle  Peilung  Entfernung  Kurs/Fahrt  Alter  Klasse
```

- **Überwasserradar:** 30 sm, begrenzt durch Radarhorizont (20-m-Mast) und Zielhöhe; getauchte U-Boote sind unsichtbar.
- **Mast- und Schnorchelechos:** ein U-Boot auf Sehrohrtiefe mit ausgefahrenem Mast oder Schnorchelkopf (Mast einer Crew, ein schnorchelndes U-Boot, eines auf Funktiefe oder das Sehrohr eines KI-Aufklärungs-U-Boots während seines Rundblicks) gibt ein winziges Echo: bei ruhiger See findet es etwa jeder zweite Umlauf auf 7 sm, bei Seegang 3 auf etwa 2,5 sm, bei Seegang 5 unter 1 sm. Es erscheint nur als bloßer Punkt, der etwa 6 s nachleuchtet, ohne Symbol, Beschriftung und Track. Den Punkt im PPI anklicken oder `B` drücken (neuester Punkt) markiert ihn: aus dieser Messung beginnt ein Radartrack `R-…`, und weitere Echos desselben Masts führen ihn fort; ohne neue Echos verblasst er nach 30 s. Echos und Markierung werden nicht gespeichert.
- **Luftradar:** 100 sm für Flugzeuge und Seezielflugkörper (ASM).
- Die Antenne dreht sich alle 4 s einmal: ein Kontakt wird nur aktualisiert, wenn der Strahl über ihn streicht, und jeder Umlauf erfasst ihn mit einer Wahrscheinlichkeit, die mit der Entfernung sinkt (50 % bei Nennreichweite für ein Schiff in Breitseite; Ziele mit spitzem Aspekt werden später gesehen, schwankende Echos können einen Umlauf verfehlen). Seegangsclutter wächst mit dem Seegang (etwa -5 % bei Seegang 4, -25 % bei 6), Regen dämpft das Echo (-10 % Überwasser, -20 % Luft); ab Seegang 5 nehmen Messfehler zu. Innerhalb 3 sm hält das Such-/Folgeradar des CIWS einen anfliegenden Flugkörper ununterbrochen, solange das CIWS freigegeben ist.
- **AIS:** zivile Schiffe senden Kurs und Fahrt alle 2-10 s (vor Anker alle 3 min) und ihren Namen etwa alle 6 min. Der UKW-Empfänger hört sie nur in Sichtlinie (etwa 20 NM). Ein Radartrack eines Zivilschiffs zeigt Name und Kurs erst, wenn die passende AIS-Meldung empfangen wurde; Radar allein liefert nur die Position. Optionaler Live-AIS/ADS-B-Verkehr ist von simuliertem Verkehr nicht unterscheidbar.
- **Fusion:** 2-8 Rohmeldungen markieren (`Leertaste`) und zu einem Bedienertrack fusionieren (`L`); `Shift+L` löst ihn auf. Eine Fusion, deren Meldungen von genau einem Sonarkontakt stammen, lässt sich der Waffenzentrale zuweisen; ihre Klassifizierung zählt für die Feuerleitung, solange das Sonar den Kontakt nicht selbst klassifiziert hat, und ihre Zugehörigkeit gilt für diesen Kontakt. Eine Fusion besteht nur, solange alle ihre Meldungen aktuell sind.
- **Automatische Fusion:** einmal pro Sekunde fusioniert die OPZ Meldungen verschiedener Sensoren, die übereinanderliegen, von selbst, sodass ein Schiff, das Radar, Ausguck und AIS sehen, ein Kontakt ist. Sie nutzt dieselben Grenzen wie die Zuordnungsvorschläge unten, aber nur bei eindeutiger Übereinstimmung: die Bewertung muss deutlich innerhalb der Grenzen liegen, mindestens eine der beiden Meldungen braucht eine Position (zwei reine Peilungen, etwa Sonar und ESM, werden nie automatisch fusioniert), und keine darf einen zweiten Kandidaten derselben Sensorart haben (zwei dicht beieinander fahrende Schiffe bleiben getrennt und erscheinen als Vorschlag). Eine weitere Meldung tritt auf dieselbe Weise einer bestehenden automatischen Fusion bei, bis zu 8 Meldungen. Eine automatische Fusion behält ihre Kennung, solange mindestens zwei ihrer Meldungen aktuell sind, und lässt eine erloschene Meldung fallen; mit weniger als zwei endet sie. Ihren Namen übernimmt sie von einer AIS-Meldung, wenn sie eine hat. `Shift+L` trennt sie, und diese Meldungen werden erst wieder automatisch fusioniert, wenn eine davon neu ist. Bei ausgefallener OPZ wird nichts fusioniert.
- **Quellen:** Meldungen in einer Fusion werden nicht mehr einzeln gelistet oder gezeichnet; die Fusion steht für sie (`H` zeigt sie mit den unterdrückten Meldungen). Jede Zeile der Trackliste auf Seite 1 endet mit Sensorkürzeln: `R` Radar, `V` Ausguck, `A` AIS, `E` ESM, `S` Sonar, `H` Hubschrauber, `B` Boje, `M` Seefernaufklärer, `F` Funkpeiler, `J` Störerpeilung, `D` Datenlink. Seite 2 zeigt für eine Fusion die vollen Namen unter *Quellen* (zum Beispiel `Radar · Ausguck · AIS`). Die Remote-Crew-OPZ-Station listet die Quellen jeder Fusion und blendet ihre Meldungen aus, solange *Unterdrückte Meldungen verwalten* nicht an ist.
- **Zuordnungsvorschläge:** die OPZ vergleicht ihre aktuellen Meldungen (höchstens 30 s alt) verschiedener Sensoren: Sonar (nur eigene Peilungen und Ortungen des Schiffs, keine Bojen und kein Tauchsonar), Radar, ESM, Ausguck und AIS. Empfangene AIS-Meldungen sind eigene OPZ-Meldungen: die gemeldete Position des Schiffs, mit seinem gemeldeten Kurs und seiner Fahrt auf jetzt gekoppelt, und sein Name, sobald die statische Meldung da ist; sie zählen, solange ihre Daten frisch sind (vor Anker bis 10 min). Zwei Meldungen, deren Peilungen vom Schiff innerhalb 1,5° plus der Peilungsunsicherheiten beider Meldungen (zusammen höchstens 8°) übereinstimmen und die, wenn beide eine Position haben, höchstens 1,5 sm plus ein Zehntel ihrer Entfernung auseinanderliegen, werden als Paar vorgeschlagen, wenn auch Bewegung und Klasse passen: geben beide einen Kurs und fährt eine mit 3 kn oder mehr, müssen die Kurse innerhalb 35° übereinstimmen; geben beide eine Fahrt, innerhalb 4 kn plus einem Viertel der schnelleren; zwei Klassifizierungen des Bedieners müssen gleich sein, und eine AIS-Meldung wird nie mit einer als U-Boot, biologisch oder Flugzeug klassifizierten Meldung gepaart. Gleiche Klassen setzen ein Paar weiter nach oben. Sonar und AIS werden nie mit einem Luftziel gepaart. Die Seitenleiste von Seite 1 zeigt die zwei besten (zum Beispiel `> K03 + R-2  Rtg 087°`); `U` fusioniert den obersten genau so, als hätten Sie beide markiert und `L` gedrückt, `Shift+U` verwirft ihn. Die Remote-Crew-OPZ-Station listet alle, mit Kurs- und Fahrtunterschied und ob die Klassen übereinstimmen, und den Schaltflächen *Vorschlag fusionieren* und *Verwerfen*. Es gibt höchstens 4 Vorschläge zugleich, jede Meldung nur in einem; bereits fusionierte Meldungen bleiben außen vor. Vorschläge sind Hinweise, keine Identifizierung, und werden wie Fusionen und Verwerfungen nicht gespeichert.
- **Unterdrückung:** `Entf` blendet eine Meldung lokal aus; `H` zeigt unterdrückte Meldungen wieder.

## Seefernaufklärer {#opz-mpa}

Seite 3 führt einen Seefernaufklärer (MPA) auf Abruf vom nächsten eigenen Flugplatz (ohne Flugplatz kommt er vom nächsten Kartenrand). Er fliegt im Transit 300 kn und kreist mit 200 kn auf einem 3-sm-Kreis um sein Suchgebiet. Ein Einsatz dauert bis zu 5 h einschließlich 15 min Reserve; am Mindestkraftstoff fliegt er selbst zurück. Nach der Landung braucht er 30 min am Boden und fliegt dann noch einmal: 2 Einsätze je Mission mit je 16 Sonarbojen und 2 leichten Torpedos.

- Das Flugzeug hat die Tasten des Helikopters. `H` fordert das Flugzeug an (es fliegt zuerst zur Schiffsposition) oder schickt es heim.
- `W` legt das Suchgebiet auf die geplottete Position des gewählten Tracks (ohne Auswahl auf das Schiff); ein Klick in die Karte legt es auf diesen Punkt. Ein reiner Peilungstrack hat keine Position zum Anfliegen.
- `X` plant ein Bojenmuster (Feld, Sperre, Kreis) um das Suchgebiet; das Flugzeug fliegt die Punkte ab und wirft an jedem eine Boje. `Shift+X` bricht das Muster ab. `B` wirft eine Boje dort, wo das Flugzeug ist, `Shift+B` schaltet seine Bojen zwischen PASSIV und AKTIV.
- `Strg+R` schaltet das Seeraumradar des Flugzeugs (wie beim Helikopter). Aus 300 m sieht es Schiffe und aufgetauchte oder mit Mast fahrende U-Boote bis 60 sm (begrenzt durch den Radarhorizont); seine Kontakte erscheinen als `RADAR-MPA`-Tracks mit dem Flugzeug als Beobachter. KI-U-Boote mit ausgefahrenem Mast hören es und tauchen weg (siehe Kapitel Helikopter).
- Die Besatzung des Flugzeugs sieht wie die des Helikopters die Schaumfahne eines ausgefahrenen Masts (siehe Kapitel Helikopter); solange der Datenlink steht, erscheinen diese Sichtungen als `MPA-EYE`-Tracks.
- `Shift+M` beginnt oder beendet **MAD-Überflüge** (Browser: *MAD-Anflüge beginnen*/*beenden*), solange das Flugzeug unterwegs oder auf Station ist: dort geht es auf 60 m und fliegt mit 180 kn gerade Bahnen durch das Suchgebiet und kehrt 2 sm dahinter um (ein Kleeblatt). Ein getauchter Rumpf innerhalb von etwa 400 m Schrägentfernung wird mit einem zustandslosen Zug je Sekunde erfasst (sicher unter 250 m) und erreicht das Schiff per Datenlink als MAD-Ortung ohne Tiefe und Kurs auf dem Sonarkontakt dieses U-Boots. Ein Bojenmuster wird zuerst abgeflogen; `H` (heim) beendet die Überflüge.
- `D` wirft einen Torpedo auf den zugewiesenen Sonarkontakt. Es gelten dieselben Prüfungen wie beim Helikopter (aktueller, als U-Boot klassifizierter Kontakt, Einsatzregeln, unter Standard-ROE eine frische Ortung), und das Flugzeug muss höchstens 2 sm vom Datum entfernt sein.

Alles, was das Flugzeug erfährt, erreicht das Schiff nur per Datenlink bis 250 sm. Seine Bojen melden nur, solange das Flugzeug höchstens 50 sm von ihnen entfernt ist; fliegt es weg oder landet es, verstummen sie für das Schiff. Die Seitenleiste zeigt Zustand, Peilung und Entfernung, Restzeit auf Station, Vorräte, verbleibende Einsätze und wie viele seiner Bojen übertragen werden.

## Begleitzerstörer {#opz-consort}

Seite 4 (Verband) führt das Begleitschiff einer Gruppenjagd: den Zerstörer LUETJENS (Rumpfsonar, 8 ASROC), der in Fregatten-Szenario 11 (Suchgruppe) und U-Boot-Szenario 11 (Jagdgruppe) mit der Fregatte fährt. Andere Missionen haben kein Begleitschiff, und die Seite sagt das. Der Zerstörer ist eine eigene Einheit im Datenlink (bis 100 sm): Position, Kurs, Fahrt, Befehle und Vorräte werden als Wahrheit gezeigt und auf der OPZ-Karte als eigenes Symbol mit Rufzeichen und `DL` gezeichnet; was sein Sonar hört, erreicht die Fregatte nur als Messungen.

- **Befehle:** `Y` selbständig, `F` Formation (jeder Druck schickt ihn auf den nächsten Platz 5 sm von der Fregatte: querab Steuerbord, voraus, querab Backbord, achteraus), `H` halten (4 kn auf seinem Kurs), `X` einen Punkt absuchen (er läuft mit 18 kn heran und kreist mit 10 kn in 4 sm Abstand um den Punkt, damit sein Sonar hört), `W` die geplottete Position des gewählten Tracks verfolgen (26 kn, dann ein 2-sm-Kreis mit Aktivsonar). Ein Klick in die Karte setzt den Punkt und macht aus Formation, Halten oder Selbständig ein Absuchen.
- **Selbständig:** Er hält Formation, bis das eigene Lagebild der Fregatte einen Kontakt hat, den du als U-Boot klassifiziert oder zugewiesen hast und der einen Standort unter 10 Minuten hat; dann verfolgt er den frischesten mit Aktivsonar.
- **Sonar:** Alle 10 s erscheinen seine Passivpeilungen auf Seite 4 als Linien vom Zerstörer aus. Schneidet eine davon die eigene Passivpeilung der Fregatte auf denselben Kontakt mit 15° oder mehr und innerhalb 30 sm, erhält der Kontakt einen `CONSORT`-Standort (Unsicherheit aus beiden Peilfehlern und dem Schnittwinkel). `Shift+A` schaltet sein Aktivsonar: Alle 20 s ortet ein Ping jeden getauchten Kontakt innerhalb 7 sm mit Position und Tiefe (je näher, desto sicherer) als `CONSORT`-Standort; jedes U-Boot innerhalb 25 sm hört den Ping.
- **Waffen:** `Shift+F` schaltet Waffen frei oder gesperrt (zu Beginn gesperrt). Frei schießt er höchstens alle 3 Minuten ein ASROC auf den Standort des selbständig verfolgten Kontakts, wenn dieser jünger als 2 Minuten ist und 1 bis 12 sm vom Zerstörer liegt. `Strg+Enter` befiehlt ein ASROC auf den Standort des gewählten Tracks (jünger als 2 Minuten); ohne Auswahl auf den selbständig verfolgten Kontakt. Es ist immer nur eines seiner ASROC in der Luft.

Wird der Zerstörer versenkt, melden das die Seite und das Ereignisprotokoll; die Mission geht weiter. Die OPZ im Browser hat dieselben Befehle in der Karte *Begleitzerstörer*, und ihre Karte zeigt den Zerstörer, seinen Punkt und seine Peillinien.

## Tasten {#opz-keys}

<!-- keys:opz -->

## Standardablauf {#opz-sop}

<!-- sop:opz -->

Ablauf Luftverteidigung (Flugkörper im Anflug):

```text
  40 sm  ASM erfasst (Luftradar / ESM-Sucherpeilung)
  30 sm  ESSM-Bereich           -> Strg+Enter (2 Feuerkanäle)
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
- Der Seefernaufklärer hat kein Tauchsonar und kein eigenes ESM; er kann nicht abgeschossen werden. MAD-Überflüge gehen nur über das Suchgebiet, nicht entlang eines Tracks.
- Automatische Fusion nur bei eindeutiger Übereinstimmung von Meldungen verschiedener Sensoren mit mindestens einer Position; reine Peilungspaare und mehrdeutige Fälle warten auf den Bediener. Signaturen werden nur als Klassifizierungen des Bedieners verglichen (kein Abgleich akustischer oder Emitter-Fingerabdrücke), und AIS meldet keinen Schiffstyp.
- Keine Link-gestützte Luftraumführung befreundeter Flugzeuge.
- Der Begleitzerstörer lässt sich nicht von einer eigenen Station aus besetzen: Er hat keinen Helikopter, kein Schleppsonar und keine Torpedos, nimmt Befehle nur von der OPZ der Fregatte an, und seine Peilungen gehen nicht an Helikopter oder Seefernaufklärer. Eigene Torpedos suchen ihn nie auf (seine Datenlink-Position bleibt aus jeder Suche heraus), die Torpedos der U-Boote können ihn versenken.
