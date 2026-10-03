# 3 Waffenzentrale {#station-weapons}

## Zweck {#weapons-purpose}

Die Waffenzentrale macht aus einem Sonarkontakt eine Feuerlösung. Sie startet die drahtgelenkten Torpedos und das eigene ASROC der Fregatte, wirft Wasserbomben, verwaltet die Zuladung des Helikopters (Bojen, Leichttorpedos), bringt den geschleppten Täuschkörper Nixie aus und gibt das Flak-Geschütz frei.

## Anzeigen und Instrumente {#weapons-displays}

Seite 1 (Ziel) zeigt die Karte mit dem gewählten Kontakt, die Torpedotiefe und die Bereitschaftszeile der Feuerleitung. Seite 2 (Bestände) listet Rohre, Nachladezeiten, Torpedovorrat, Nixie-Zustand, Helikopter-Zuladung und die Torpedo-Einstellzeile: gewählter Typ mit Restvorrat, Suchmuster, Sucheraktivierungspunkt und Salvengröße.

![Waffen auf der uConsole](figure:station-weapons)

![Waffen im Remote-Crew-Browser](figure:web-weapons-desktop)

Die Bereitschaftszeile wird von oben nach unten geprüft; die erste fehlgeschlagene Prüfung wird angezeigt:

```text
 BLOCKIERT: KEIN ZIEL            Kontakt wählen oder übernehmen (M)
 BLOCKIERT: ZUGEHOERIGKEIT ...   als FREUND/NEUTRAL markiert
 BLOCKIERT: KEINE ENTFERNUNG     ROE STD braucht Ping/TMA/Boje
 BLOCKIERT: NICHT KLASSIFIZIERT  als U-Boot/Kampfschiff (Sonar C)
 BLOCKIERT: KEINE TORPEDOS / KEIN ROHR BEREIT / SALVENLIMIT
 BLOCKIERT: WAFFENZENTRALE GESTOERT
 FEUER FREI                      -> Strg+Enter
```

Torpedolauf von oben:

```text
 Fregatte ==Draht==> . . . . /\/\/\/\  ( Datum )
                   Marschlauf    Schlangen-    Sucher an
                   zum Datum     suche         innerhalb 1,2 sm
                   (Draht-Update +/-15 Grad    -> steuert nächsten
                    alle 0,5 s)                   Kandidaten an
```

- Zwei Torpedotypen teilen sich die zwei Rohre (60 s Nachladen). Mk1: 45 kn, 12 sm, drahtgelenkt. Mk2: 55 kn, aber nur 8 sm. Der Szenariovorrat (Standard 6) ist 2:1 auf Mk1 und Mk2 verteilt; `W` wählt den Typ, und hält kein Rohr ihn, entlädt ein Rohr und lädt ihn nach (60 s).
- Suchmuster (`X`): die Schlange (+/-15° um den Datumskurs, Standard), ein Kreis von 0,4 sm um den Aktivierungspunkt oder eine Helix, die sich von 0,15 sm um 0,15 sm je Umlauf bis 1 sm öffnet. Das Muster läuft erst, wenn der Sucher aktiv ist und noch nicht erfasst hat.
- Sucheraktivierungspunkt (`,` / `.`): 0,6 bis 3,0 sm vor dem Datum in Schritten von 0,2 sm (Standard 1,2 sm). Frühe Aktivierung findet ein Ziel, das sich vom Datum entfernt hat; späte Aktivierung hält die Waffe länger still.
- Salve (`Y`): ein Torpedo oder zwei im Fächer von +/-8° mit eigenen, um das Schiff gedrehten Datums; ein Fächer braucht zwei geladene Rohre des gewählten Typs und zählt gegen die Doktringrenze.
- Voreingestellte Tiefe 10-300 m (Standard 60 m): `↑`/`↓` halten oder nach `T` eintippen, wie auf dem U-Boot. Falsche Tiefe bedeutet Fehlschuss: Tiefe aus dem Ping nehmen, nicht aus der TMA.
- Der Draht aktualisiert das Datum aus der beobachteten Kontaktposition. Ohne Updates wird er nach 3 s STALE und nach 12 s BROKEN; der Torpedo läuft dann zum letzten Datum weiter.
- Der Sucher steuert den nächsten Kandidaten an: das kann ein Täuschkörper, ein Wal oder ein Handelsschiff sein. Ein ziviler Treffer beendet die Mission.
- Salvendoktrin SHOOT-LOOK-SHOOT: höchstens 2 eigene Torpedos gleichzeitig im Wasser.
- ASROC (`A`): 4 Schuss pro Mission. Die Rakete fliegt mit 500 kn zur beobachteten Position des Ziels (1 bis 10 sm, aktuelle Entfernung nötig) und setzt dort den Leichttorpedo des Helikopters auf der voreingestellten Tiefe ab. Es gelten dieselben Zielprüfungen wie beim Torpedo, und es zählt gegen die Doktringrenze.
- Wasserbomben (`Z`): 20 pro Mission, geworfen als Muster aus 5 (drei im Kielwasser 20, 80 und 140 m achteraus, zwei 70 m querab geworfen), danach 45 s Nachladen der Ablaufbahn. Das Schiff muss mindestens 10 kn laufen. Die Bomben sinken mit 3,5 m/s bis zur voreingestellten Tiefe (15-300 m) oder zum Grund; jede 90-kg-Ladung ist bis etwa 25 m tödlich und beschädigt noch bis etwa 100 m. U-Boote innerhalb von 5 sm hören die Detonation und weichen aus.
- U-Jagd-Raketenwerfer (`R`, Typ RBU/Bofors): 36 Raketen pro Mission, abgefeuert in Salven zu 6, danach 60 s Nachladen. Eine Angriffssalve geht auf die beobachtete Position des zugewiesenen Ziels in 0,4 bis 3 sm (aktuelle Entfernung nötig, dieselben Zielprüfungen wie beim Torpedo): ein Schuss auf den Zielpunkt, fünf auf einem Ring von 80 m darum. Die Raketen fliegen mit 400 kn (etwa 9 s je sm), jede Ladung sinkt mit 11 m/s bis zur voreingestellten Tiefe (10-300 m) oder zum Grund; die 23-kg-Ladungen sind nur bis etwa 14 m tödlich und schaden bis 60 m, eine grobe oder alte Ortung verschwendet die Salve. **Abwehrsalve** (`Umschalt+R`): sechs Schuss in einer Linie 0,3 bis 0,8 sm hinaus in Peilung einer höchstens 5 s alten Torpedowarnung, Tiefe 15 m; eine Ladung, die innerhalb von 35 m eines laufenden Torpedos detoniert, zerstört ihn, und das Protokoll meldet, dass das Torpedogeräusch endet. Jedes U-Boot innerhalb von 3 sm hört die Raketen ins Wasser schlagen: ein KI-Boot weicht sofort aus, der Sonarraum des bemannten U-Boots meldet die Einschläge mit ihrer Peilung.

Beide Seiten sind wie ein Feuerleitpult aufgebaut: Auf Seite 1 hat jedes Rohr eine Lampe (grün geladen, gelb im Nachladen, dunkel wenn leer), und die Sperrkette (Ziel, Fix, ROE, Waffe, Flak) ist eine Lampensäule, die Stufe für Stufe grün wird. Zwischen Lösung und Rohrlampen zeigt eine Schusslage, genordet um das eigene Schiff, die Reichweite des gewählten Torpedotyps als gestrichelten gelben Ring, die Peilung zum Ziel (gestrichelt, solange nur die Peilung bekannt ist) und, sobald eine Entfernung vorliegt, die geschätzte Zielposition, den Treffpunkt aus TMA-Kurs und -Fahrt und die Torpedolaufbahn dorthin (grün innerhalb der Reichweite, rot darüber hinaus); die Zahl links unten ist der Halbmesser der Skizze. Sie nutzt nur die Beobachtung des Kontakts, nie das U-Boot selbst; Seite 2 zeigt die restlichen Torpedos, Hubschraubertorpedos, Sonarbojen und RBU-Raketen als Tanksäulen. Der Remote-Crew-Browser zeigt Station, ROE und Sperre als Lampen und jedes Rohr als Säule.

## Tasten {#weapons-keys}

<!-- keys:weapons -->

## Standardablauf {#weapons-sop}

<!-- sop:weapons -->

Gefechtslage:

1. Feindtorpedo gemeldet: sofort Nixie ausbringen (`V`). Er hält 600 s an einem 0,2-sm-Kabel; einer bereit, ein zweiter nach 60 s. Bei 15 kn läuft er in 10 m Tiefe, bei langsamer Fahrt tiefer und näher achteraus, über 25 kn reißt das Kabel. In einer Wende läuft das Kabel hinterher.
2. Den Gegenangriff fortsetzen: ein frischer Kontakt hält das Draht-Datum auf dem U-Boot.
3. Ist der Helikopter in der Luft, erreicht ein Leichttorpedo (`D`) einen entfernten Kontakt schneller als der Schiffstorpedo.

## Einsatzregeln {#weapons-roe}

| ROE | Voraussetzung |
|---|---|
| STD (Start) | Aktuelle Entfernung (Ping, TMA oder Boje) und Klassifizierung U-Boot oder Kampfschiff |
| FREI | Nur Klassifizierung; ohne Entfernung zielt der Torpedo 10 sm in Peilrichtung |

Das Hauptquartier schaltet nach dem ersten versenkten feindlichen U-Boot per Funk auf FREI; der Spieler kann die ROE nicht ändern. Ein in der OPZ als FREUND oder NEUTRAL markierter Kontakt, direkt oder über eine Fusion, kann nie bekämpft werden.

## Tipps für Profis {#weapons-tips}

- Aus etwa 6-8 sm oder näher schießen: mit 45 kn braucht der Torpedo 8 Minuten für 6 sm, und das U-Boot hört den Abschuss bis 35 sm und weicht aus.
- Das Datum vor ein fahrendes Ziel legen, indem TMA weiterläuft; der Draht folgt der Beobachtung, nicht der Wahrheit.
- Während der Lenkung unter der Kavitationsgrenze bleiben; Kontaktverlust heißt Verlust des Draht-Datums.
- Der Draht ist ein echtes Kabel: er reißt, wenn das Schiff etwa 5 s lang schneller als 20 kn läuft oder schneller als 1,5 Grad/s dreht, wenn die schiffsseitige Spule (5 sm eigener Weg) abgelaufen ist oder wenn der Torpedo das 1,25-fache seiner Reichweite gelaufen ist.
- Die Torpedoreichweite kommt aus der Batterie: bei voller Fahrt läuft er die Katalogreichweite, harte Manöver drosseln ihn und sparen Energie; ist die Batterie leer, läuft er einige Sekunden aus und geht verloren. Direkt nach dem Ausstoß dreht er langsamer (fester Drehkreis), und Tiefenänderungen brauchen einen Moment.
- Der Gefechtskopf hat einen Annäherungszünder: er zündet bei der größten Annäherung innerhalb seines Radius, der Schaden fällt mit dem Abstand (Schockfaktor). Ein knapper Fehlschuss kann ein U-Boot beschädigt entkommen lassen.
- Ein laufender Torpedo wird vom Ziel über die Sonargleichung gehört: leise U-Boote hören ihn bei ruhiger See auf einige Meilen, Regen und eigene Fahrt überdecken ihn.
- Nur zwei Nixies je Mission: den ersten ausbringen, wenn ein Torpedo wahrscheinlich ist, den zweiten für den nächsten Angriff aufheben.
- Zielsuchköpfe halten den lautesten Kandidaten und wechseln nur, wenn ein anderer deutlich (6 dB) lauter ist. Echos ohne Doppler ignorieren sie, ein schwebendes Ziel ist daher schwer zu finden; ein Torpedo, der einen Täuschkörper ohne Rumpftreffer überläuft, merkt ihn sich und greift erneut an. Täuschkörper gegnerischer U-Boote werden mit leerer werdender Batterie leiser; gegnerische Kriegsschiffe bringen eigene Täuschkörper aus, wenn sie Ihren Torpedostart hören.

## Nicht modelliert {#weapons-limits}

- Wasserbomben nur aus Ablaufbahn und Werfern; der Raketenwerfer hat keinen Aufschlagzünder (jede Ladung geht in ihrer Tiefe hoch) und kein eigenes Torpedoabwehr-Geschoss.
- Ein Torpedotyp für den Helikopter; die Doktringrenze von zwei laufenden eigenen Torpedos ist fest.
- Kein Tiefenunterschied zwischen Mk1 und Mk2; beide laufen auf der eingestellten Tiefe.
