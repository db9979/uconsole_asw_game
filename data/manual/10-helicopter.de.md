# 8 Helikopterdeck {#station-helicopter}

## Zweck {#helicopter-purpose}

Der HSP-5 „Sea Lynx" verlängert den Arm der Fregatte: er fliegt mit 120 kn zu einem Datum, wirft Sonarbojen, taucht sein eigenes Sonar und greift mit Leichttorpedos an, während die Fregatte leise und außerhalb der Torpedoreichweite bleibt.

## Seiten {#helicopter-pages}

Die Station hat vier Seiten (nochmals `8` blättert); sie öffnet auf Seite 3.

| Seite | Inhalt |
|---|---|
| 1 Status | Statuskonsole: Zustandslampen, Kraftstoff, Peilung zum Schiff, Zuladung, Flugwetter, Deckbewegung |
| 2 Einsatzregeln | Peilung und Abstand zum Wegpunkt, Treibstoffreserve für den Rückflug, Tasten für Start, Tauchen und Waffen, Bojenmuster, MAD, Radar, ROE |
| 3 Sonar | Kontakte von Tauchsonar und Bojen, Tiefe, Quelle |
| 4 Akustik | Abhören: BROADBAND / LOFAR / DEMON des Tauchsonars oder einer passiven Boje |

## Anzeigen und Instrumente {#helicopter-displays}

![Heli-Deck auf der uConsole](figure:station-helicopter)

![Heli-Deck im Remote-Crew-Browser](figure:web-helicopter-desktop)

Im Browser hat der Helikopter auf der Bühne drei Seiten: *Akustikanalyse* (BREITBAND, LOFAR und DEMON der Bojen und des Tauchsonars), *Tauchsonar* (das genordete Bild des Tauchsonars über die ganze Bühne, Ringe bei 5, 10, 15 und 20 sm, daneben Wassertiefe, Sprungschicht und die Werte jedes Kontakts) und *Taktische Karte* (die Karte über die ganze Bühne). `Bild auf`/`Bild ab`, nochmals die Stationsnummer `8` oder der Tastenchip neben den Reitern blättern zwischen ihnen.

```text
         Fregatte                           Wegpunkt (1-30 sm)
            *----------- 120 kn -------------->  H  Schweben + Tauchen
                                                 |
   Bojenlinie (B):  o ---- o ---- o              |  Kabel 15-300 m
   PASSIV: Peilungen;                            )))  Tauchsonar
   zwei Kreuzpeilungen (>= 10 Grad) = Fix           passiv 18 sm
   AKTIV: Entfernung + Peilung alle 30 s            aktiv  14 sm
```

- **Kraftstoff:** 2 Stunden im Vorwärtsflug; im Schwebeflug (Tauchsonar) verbraucht er 1,3-mal so schnell. Der Helikopter kehrt automatisch zurück, wenn nur noch die 20-Minuten-Reserve bleibt. Leerfliegen vor der Landung kostet die Maschine. Im Schwebeflug drückt ihn der Wind etwas von seinem Schwebepunkt nach Lee.
- **Startvorbereitung:** Der Hubschrauber steht nie sofort bereit. `H` (Browser: *Helikopter starten*) beginnt 5 Minuten Startvorbereitung im Hangar (Checks, Treibstoff, Waffen, Besatzungseinweisung); der Zustand zeigt STARTVORBEREITUNG mit der Restzeit, die HANGAR-Lampe leuchtet gelb. Danach hebt er im nächsten Startfenster ab; bis dahin zeigt der Zustand STARTBEREIT, WARTET. Ein zweites `H` (Browser: *Startvorbereitung abbrechen*) bricht die Vorbereitung ab. Nach jeder Landung braucht der nächste Start wieder die volle Vorbereitung, also früh befehlen. Auch die KI-Fregatte wartet sie ab.
- **Tanken:** Zu Missionsbeginn ist der Tank voll. Nach einer Landung behält der Hubschrauber den Kraftstoff, mit dem er zurückkam, und wird an Deck betankt: 15 Minuten von leer bis voll (8 Minuten Flugzeit je Minute an Deck). Der Zustand zeigt TANKEN mit der Zeit bis zum vollen Tank, die HANGAR-Lampe leuchtet gelb. Ein Startbefehl wartet nicht auf den vollen Tank: Der Hubschrauber hebt nach der Vorbereitung mit dem bis dahin getankten Kraftstoff ab, aber nie mit weniger als 30 Minuten (Reserve plus 10 Minuten); fehlt so viel, zeigt er TANKEN mit der Zeit bis zu diesem Minimum. Torpedos und Bojen werden nicht nachgeladen: Was an Bord ist, ist die Ladung der ganzen Mission. Die KI-Fregatte tankt genauso.
- **Startgrenzen:** Wind bis 32 kn, Seitenwind bis 22 kn, Sicht mindestens 2 sm, Seegang höchstens 5, einsatzbereites Flugdeck, Böen bis 40 kn, Wolkenuntergrenze mindestens 300 ft, keine starke Vereisung und ein ruhiges Deckfenster: Rollen höchstens 8 Grad und Stampfen höchstens 3,5 Grad für eine ruhige Phase von mindestens 6 s. Leichte Vereisung kostet 20 % mehr Treibstoff; die Wetter- & Sonar-Analyse (`0`) zeigt CLEAR, LIMITED oder NO-GO. Auch die Landung wartet auf ein solches Fenster. Seite 1 zeigt neben den Einsatzmitteln die **Deckbewegung**: das Heck von achtern gesehen, wie es gegen den Horizont rollt, einen Stampfbalken mit seinen Grenzen und einen Balken, der sich während der ruhigen Phase füllt (grün: Fenster offen, gelb: innerhalb der Grenzen, aber noch nicht lange genug ruhig, rot: außerhalb). Mit Fahrt gegen die See stampft das Schiff stärker (es trifft die Wellen schneller), mit der See von querab rollt es; weniger Fahrt und die See etwas seitlich vom Bug geben die meisten Fenster, das kostet aber Zeit bei der Jagd.
- **Tauchsonar:** Tiefe 15-300 m (Standard 75 m, mindestens 10 m über Grund), passiv 18 sm mit +/-2 Grad, aktiver Ping 14 sm mit 30 s Abklingzeit. Tauchen braucht Wind bis 30 kn, 1 sm Sicht und keine Vereisung.
- **Sonarbojen:** 5 je Einsatz, 8 sm Reichweite, 60 min Batterie; sie treiben mit der Strömung und etwas mit dem Wind. PASSIV-Bojen liefern Peilungen (wie DIFAR); AKTIV-Bojen liefern Entfernung und Peilung alle 30 s (wie DICASS).
- **Bojenmuster:** mit `X` wird ein Muster geplant: eine Folge von Abwurfpunkten um den Wegpunkt: ein 2x2-Feld (Abstand 1,5 sm), eine Sperre quer zur Peilung vom Schiff zum Wegpunkt (Abstand 3 sm) oder ein Kreis von 1,5 sm Radius, jeweils mit bis zu 4 Bojen des Restvorrats. Der Helikopter fliegt die Punkte nacheinander an und wirft an jedem die gewöhnliche Einzelboje (in der gewählten Betriebsart); EINZELN löscht die Folge, der Rückflug verwirft sie.
- **MAD-Anflug:** mit `Umschalt+M` und eingeholtem Tauchsonar geht der Helikopter auf 30 m und 90 kn. Ein getauchter Rumpf innerhalb von etwa 400 m Schrägdistanz wird je Sensortakt mit einem zustandslosen Zufallszug erfasst (sicher innerhalb 250 m) und als MAD-Positionsfix ohne Tiefe oder Kurs gemeldet; er zählt für die Entfernungsprüfung der Waffen und, sobald der Helikopter seinen Kontakt freigibt, für die OPZ.
- **Seeraumradar:** sucht, solange der Helikopter fliegt und das Tauchsonar eingeholt ist (Statuszeile auf Seite 2). Aus 150 m sieht es Schiffe bis 40 sm, aufgetauchte U-Boote sowie ausgefahrene Schnorchel oder Sehrohre innerhalb seines Radarhorizonts (etwa 30 sm). Ein Mast ist klein: bei ruhiger See zeigt er sich auf etwa 10 sm, bei Seegang 3 auf 3-5 sm, bei Seegang 5 verschwindet er im Seegangsecho. Jeder Kontakt geht als `RADAR-HELO`-Track mit dem Helikopter als Beobachter an die OPZ, ein Blick alle 2 s. Das ESM eines besetzten U-Boots hört das Radar und kann seine Besatzung warnen. `Strg+R` (wie beim Seefernaufklärer; Browser: *Radar ausschalten*/*einschalten*) schaltet das Radar aus und wieder ein; ausgeschaltet sieht es nichts und strahlt nicht, und es bleibt aus (gespeichert), bis es wieder eingeschaltet wird. Ein KI-U-Boot mit ausgefahrenem Mast oder Schnorchel hört ein Flugzeugradar innerhalb von 40 sm (im Radarhorizont seines Masts) bei vier von fünf Blicken im 5-s-Takt, geht 40 m unter Schnorcheltiefe und schiebt das Schnorcheln 15 Minuten auf, solange seine Batterie mehr als 5 % hält; ein strahlender Helikopter drückt Schnorchler also weg, ein stiller kann sie an der Oberfläche erwischen.
- **Augen der Besatzung:** Solange der Helikopter fliegt, hält auch seine Besatzung Ausguck, mit dem Kontrastmodell des Brückenausgucks aus der Flughöhe (150 m, beim Tauchen 20 m): die Schaumfahne eines ausgefahrenen Sehrohrs oder Schnorchels sieht sie auf dieselbe Entfernung wie der Ausguck, unabhängig vom Radar und ohne zu strahlen. Die Sichtung geht alle 2 s als `HELO-EYE`-Track an die OPZ, auf die halbe Entfernung als U-Boot.
- **Leichttorpedo:** 2 je Einsatz, 45 kn, 6 sm, von der Helikopterposition Richtung Datum geworfen, ohne Draht. Das Ziel muss als U-Boot klassifiziert sein.
- **Rettungswinde:** Überlebende einer Rettungsinsel kommen nur auf Befehl hoch. Zur Insel fliegen (ein Klick auf ihren SAR-Kreis setzt den Wegpunkt dorthin); innerhalb 0,1 sm startet `Z` (Browser: *Winde starten*) die Winde. Der Windenführer lotst dann den Piloten über die treibende Insel, und sobald der Hubschrauber über ihr steht (auf etwa 40 m), winscht die Winde einen Überlebenden pro Minute auf. Die Kabine fasst 6; die Winde stoppt, wenn die Insel leer oder die Kabine voll ist. Die Winde braucht Tauchwetter (Wind bis 30 kn, Sicht 1 sm, keine Vereisung) und eingeholtes Tauchsonar, und der Schwebeflug verbraucht 1,3-mal so viel Kraftstoff. Als gerettet zählen die Überlebenden erst, wenn der Hubschrauber wieder an Deck ist (`H`): bis dahin sitzen sie in der Kabine und gehen mit dem Hubschrauber verloren. `Z` noch einmal stoppt die Winde.
- **Rettungsinseln im Radar:** Eine Insel mit Radarreflektor ist ein kleines Ziel (ein halbes Prozent des Echos eines Schiffes, etwa 1 m hoch). Das Radar des Hubschraubers sieht sie bei ruhiger See auf etwa 6 sm, bei Seegang 3 auf 1,5 bis 2 sm und bei Seegang 5 nur noch auf wenige Kabellängen; das Überwasserradar des Schiffes etwas weniger. Das erste Echo setzt den SAR-Kreis des Funkers (0,3 sm) darauf und wird im Protokoll gemeldet (`Radar: kleines Echo bei SAR 1`); weitere Echos halten ihn dort, bis der Ausguck die Insel in Sicht hat.

Seite 1 ist die Statuskonsole des Hubschraubers. Eine Leiste Zustandslampen zeigt, wo er ist: HANGAR (gelb während der Startvorbereitung und beim Tanken), DECK (grün, wenn er jetzt starten darf, gelb, solange Wetter oder Deckbewegung ihn halten, rot bei ausgefallenem Flugdeck), FLUG (rot, wenn er verloren ist), SONAR (Tauchsonar im Wasser, gelb beim Fieren und Hieven) und RÜCKFLUG.

Darunter ein Tank mit der 20-Minuten-Reserve als gelbe Marke (im Hangar füllt er sich beim Tanken; der Tooltip über dem Status nennt, worauf der Hubschrauber wartet), eine Rose mit der Peilung zurück zum Schiff und der Kursnadel des Hubschraubers sowie Anzeigen: Zustand, Flugzeit (und im Schwebeflug, der 1,3-mal so viel verbraucht), Bingo (Kraftstoff nach Heimflug und Reserve), Peilung, Entfernung und Flugzeit zurück zum Schiff, Flugkurs sowie Zustand und Tiefe des Tauchsonars. Die Einsatzmittel zeigen Torpedos und Bojen an Bord als Punkte, die Bojen im Wasser und den Datenlink, dann Lampen für das Flugwetter (CLEAR, LIMITED oder NO-GO), das Deckfenster, das Tauchwetter, Dom, Ping, Wassereintritt und Radar. Die Deckbewegungsanzeige steht ganz unten; in einem kleinen Fenster oder bei großer Schrift weichen erst die untere Lampenreihe und dann diese Anzeige. Solange der Hubschrauber fliegt und eine Rettungsinsel wartet oder Überlebende in der Kabine sind, nimmt das Feld **Rettungswinde** den Platz dieser Anzeige ein (bei großer Schrift den der Einsatzmittel): die Windenlampe `Z` mit ihrem Zustand (keine Insel, bereit, geht drüber, winscht, Wetter, zum Schiff), die Kabine (zum Beispiel 5/6 an Bord), ein Balken für den Überlebenden, der gerade hochkommt, und eine Zeile mit dem nächsten Schritt. Der Browser zeigt dasselbe als Karte *Rettungswinde*.

Seite 3 zeigt das Tauchsonar wie eine Konsole: Lampen für Dom (grün im Wasser, gelb beim Fieren oder Hieven), Ping bereit und Wassereintritt frei, eine Seitenansicht des Tauchens (graue Luft mit dem Hubschrauber oben, eine kräftige blaue Wasserlinie, darunter das mit der Tiefe dunklere Wasser, die Sprungschicht als gelbe Linie und der Dom an seinem Kabel; der Browser zeichnet sie neben dem Tauchsonar-Sichtgerät) und ein Sichtgerät mit den Peilungen von Tauchsonar und Bojen als Keile so breit wie ihr Fehler. Seite 4 zeichnet ihre Wasserfälle in denselben Leuchtfarben wie das Sonar des Schiffs.

## Tasten {#helicopter-keys}

<!-- keys:helicopter -->

Mit „Akustik" markierte Tasten gelten nur auf der Akustikseite (Seite 4).

## Maus {#helicopter-mouse}

Jede Taste in der Tastenleiste am Fuß der Station lässt sich anklicken; gedrückt halten hält die Taste. Lampen, Seitenreiter und Tastenhinweise im Text sind ebenfalls anklickbar (Kapitel Werkzeuge, Maus). Außerdem:

- Auf Seite 2 sind die in den Regeln genannten Tasten (`H`, `Y`, `U`/`V`, `Umschalt+A`, `B`, `D`, `Umschalt+B`, `Umschalt+M`, `Strg+R`) Schalter: Ein Klick drückt sie.
- Auf Seite 1 ist die Windenlampe im Feld Rettungswinde ein Schalter für `Z`.
- Auf der Akustikseite schaltet ein Klick auf die Quellenangabe die Hörquelle um.
- Auf der Karte zoomt das Mausrad, Ziehen verschiebt (und beendet das Folgen mit `K`) und ein Klick heftet eine Kurzinfo an.

## Standardablauf {#helicopter-sop}

<!-- sop:helicopter -->

Angriffsablauf:

1. Mit zwei passiven Bojen oder einem Ping von Aktivboje/Tauchsonar orten, bis der Kontakt eine frische Position hat.
2. Als U-Boot klassifizieren (`C`) und als Ziel setzen (`M`).
3. Zum Datum fliegen; Torpedo werfen (`Strg+Eingabe`; `D` an der Waffenstation wählt dafür den Lufttorpedo). Kontakt halten für einen zweiten Wurf.

## Tipps für Profis {#helicopter-tips}

- Das Tauchsonar unter die Schicht legen, um tiefe U-Boote zu hören. Die Tauchanzeige zeigt die Schicht am Helikopter erst, wenn der abgesenkte Dom sie durchfahren hat; vorher nur die Kartentiefe.
- Bojen vor den geschätzten Zielkurs legen, nicht auf das letzte Datum.
- `F` bestätigt einen Helikopterkontakt; `G` gibt ihn wie am Sonar an die OPZ frei; `Umschalt+↑`/`Umschalt+↓` wählen den nächsten Tauchsonarkontakt; `W` legt den Wegpunkt auf die Position des gewählten Kontakts (wie `W` beim Seefernaufklärer; ein reiner Peilkontakt hat keine). Ein Klick in die Karte (uConsole und Browser, auch auf ein Symbol oder eine Beschriftung, nur ein Sonarkontakt wählt diesen Kontakt) legt den Wegpunkt genau auf diesen Punkt; die Karte zeigt ihn als HSP-5 WP mit einer gestrichelten Linie vom Hubschrauber. Der Hubschrauber wird im Anflug langsamer und bleibt auf dem Punkt stehen (auf etwa 20 m); die Pfeiltasten verschieben den Wegpunkt weiter in Schritten von 15 Grad und 1 sm vom Schiff aus.
- Auf der Akustikseite schaltet `T` die Horchquelle zwischen Tauchsonar und jeder passiven Boje.
- Den Helikopter rechtzeitig zurückrufen (`H`): die Landung braucht ein einsatzbereites Flugdeck, und die Zuladung wird zwischen Einsätzen nicht ergänzt.

## Nicht modelliert {#helicopter-limits}

- Keine Kanalverwaltung für Bojen.
- Das Helikopterradar kennt keine Leistungs- oder Sektoreinstellung, nur ein und aus; ein KI-U-Boot hört es nur mit ausgefahrenem Mast oder Schnorchel.
- Nur ein Helikopter.
