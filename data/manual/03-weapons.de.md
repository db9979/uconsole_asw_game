# 3 Waffenzentrale {#station-weapons}

## Zweck {#weapons-purpose}

Die Waffenzentrale macht aus einem Sonarkontakt eine Feuerlösung. Sie startet die drahtgelenkten Torpedos der Fregatte, verwaltet die Zuladung des Helikopters (Bojen, Leichttorpedos), bringt den geschleppten Täuschkörper Nixie aus und gibt das Flak-Geschütz frei.

## Anzeigen und Instrumente {#weapons-displays}

Seite 1 (Ziel) zeigt die Karte mit dem gewählten Kontakt, die Torpedotiefe und die Bereitschaftszeile der Feuerleitung. Seite 2 (Bestände) listet Rohre, Nachladezeiten, Torpedovorrat, Nixie-Zustand, Helikopter-Zuladung und die Torpedo-Einstellzeile: gewählter Typ mit Restvorrat, Suchmuster, Sucheraktivierungspunkt und Salvengröße.

Die Bereitschaftszeile wird von oben nach unten geprüft; die erste fehlgeschlagene Prüfung wird angezeigt:

```text
 BLOCKIERT: KEIN ZIEL            Kontakt wählen oder übernehmen (M)
 BLOCKIERT: ZUGEHOERIGKEIT ...   als FREUND/NEUTRAL markiert
 BLOCKIERT: KEINE ENTFERNUNG     ROE STD braucht Ping/TMA/Boje
 BLOCKIERT: NICHT KLASSIFIZIERT  als U-Boot/Kampfschiff (Sonar C)
 BLOCKIERT: KEINE TORPEDOS / KEIN ROHR BEREIT / SALVENLIMIT
 BLOCKIERT: WAFFENZENTRALE GESTOERT
 FEUER FREI                      -> T oder Strg+Enter
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
- Voreingestellte Tiefe 10-300 m (Standard 60 m). Falsche Tiefe bedeutet Fehlschuss: Tiefe aus dem Ping nehmen, nicht aus der TMA.
- Der Draht aktualisiert das Datum aus der beobachteten Kontaktposition. Ohne Updates wird er nach 3 s STALE und nach 12 s BROKEN; der Torpedo läuft dann zum letzten Datum weiter.
- Der Sucher steuert den nächsten Kandidaten an: das kann ein Täuschkörper, ein Wal oder ein Handelsschiff sein. Ein ziviler Treffer beendet die Mission.
- Salvendoktrin SHOOT-LOOK-SHOOT: höchstens 2 eigene Torpedos gleichzeitig im Wasser.

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
- Ein laufender Torpedo wird vom Ziel über die Sonargleichung gehört: leise Boote hören ihn bei ruhiger See auf einige Meilen, Regen und eigene Fahrt überdecken ihn.
- Nur zwei Nixies je Mission: den ersten ausbringen, wenn ein Torpedo wahrscheinlich ist, den zweiten für den nächsten Angriff aufheben.
- Zielsuchköpfe halten den lautesten Kandidaten und wechseln nur, wenn ein anderer deutlich (6 dB) lauter ist. Echos ohne Doppler ignorieren sie, ein schwebendes Ziel ist daher schwer zu finden; ein Torpedo, der einen Täuschkörper ohne Rumpftreffer überläuft, merkt ihn sich und greift erneut an. Täuschkörper gegnerischer U-Boote werden mit leerer werdender Batterie leiser; gegnerische Kriegsschiffe bringen eigene Täuschkörper aus, wenn sie Ihren Torpedostart hören.

## Nicht modelliert {#weapons-limits}

- Keine Wasserbomben, U-Jagd-Raketen oder vom Schiff gestartetes ASROC (ASROC nutzen nur befreundete KI-Kriegsschiffe).
- Ein Torpedotyp für den Helikopter; die Doktringrenze von zwei laufenden eigenen Torpedos ist fest.
- Kein Tiefenunterschied zwischen Mk1 und Mk2; beide laufen auf der eingestellten Tiefe.
