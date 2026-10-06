# Schnellstart {#quickstart}

U-Jagd ist eine Echtzeitsimulation der U-Boot-Abwehr. Sie spielen eine von zwei Seiten: die U-Jagd-Fregatte F-217 mit neun Stationen, deren Auftrag es ist, feindliche U-Boote zu orten, zu verfolgen, zu klassifizieren und zu versenken, ohne das eigene Schiff zu verlieren oder neutrale Schifffahrt zu gefährden, oder das feindliche U-Boot mit sieben Stationen, das durchbricht, angreift oder die Jagd übersteht.

Das Spiel läuft immer in Echtzeit: Eine echte Sekunde ist eine simulierte Sekunde. Es gibt keinen Zeitraffer und keine Pause; Menüs, Hilfe und Optionen öffnen sich über der laufenden Mission.

> Dieses Handbuch beschreibt nur, was die Simulation tatsächlich abbildet. Nicht modellierte Funktionen stehen am Ende jedes Stationskapitels.

## Auftrag und Siegbedingungen {#qs-goal}

- **Sieg:** alle zugewiesenen Ziel-U-Boote versenken oder bis zum Zeitlimit überleben (je nach Mission).
- **Niederlage:** eigenes Schiff sinkt, ein ziviles Schiff wird getroffen, das Ziel entkommt mehr als 150 sm von seinem Startpunkt, oder die Zeit läuft bei einem Versenkungsauftrag ab.
- Zeitwarnungen kommen bei 5, 2 und 1 Minute Restzeit: bei einem Versenkungsauftrag als Frist, bei einem Überlebensauftrag (Konvoi) als Zeit, bis der Konvoi in Sicherheit ist.
- Am Missionsende startet `R` die Mission mit gleichem Seed neu (eine Editor-Mission startet sich selbst neu), `M` führt ins Hauptmenü. Während der Mission bietet `Esc` neben Speichern und Beenden auch "Zum Hauptmenü (ohne Speichern)".
- Punkte: 1000 je versenktem U-Boot, 200 je unverbrauchtem Torpedo, 500 ohne zivile Verluste, bis zu 500 Zeitbonus.

## Stationen {#qs-stations}

Das Schiff ist in neun Stationen gegliedert. Die Tasten `1`-`9` wählen eine Station; erneutes Drücken der Nummer der aktiven Station blättert ihre Seiten.

![Fregatten-Stationen auf der uConsole: Brücke, Sonar, Waffen und Schadensabwehr](figure:stations-overview-1)

![Fregatten-Stationen auf der uConsole: OPZ, Funk, Antrieb und Heli](figure:stations-overview-2)

![Fregatten-Station ELOKA auf der uConsole](figure:stations-overview-3)

```text
 1 Brücke      2 Sonar       3 Waffen
 4 Schaden     5 OPZ         6 Funk
 7 Maschine    8 Helikopter  9 EloKa
```

Jede Station zeigt nur, was ihre Sensoren und Bediener wissen. Sonarkontakte sind verrauschte Peilungen, bis Ping, TMA, Boje oder Kreuzpeilung eine Entfernung liefern. Keine Station zeigt „die Wahrheit".

Das U-Boot hat sieben Stationen auf den Tasten `1`-`7` (siehe Kapitel U-Boot). `F2` übergibt die aktuelle Station an die Autocrew, `F3` zeigt, welche Stationen automatisch laufen (siehe Kapitel Werkzeuge).

## Bedienung in 60 Sekunden {#qs-controls}

- **Stationen:** `1`-`9` (U-Boot `1`-`7`), `Tab`/`Umschalt+Tab` oder ein Klick auf einen Reiter in der Kopfzeile.
- **Seiten:** die Nummer der Station nochmals drücken, `Bild Auf`/`Bild Ab` oder einen Seitenreiter anklicken.
- **Feuern:** `Strg+Eingabe` feuert Torpedos und Flugkörper. `Eingabe` allein feuert nie.
- **Hilfe:** `F1` (oder `?`) listet alle Tasten der aktuellen Station, ihren Standardablauf und dieses Handbuch; im Handbuch blättern die Schaltflächen **[ Kapitel zurück** und **] Kapitel vor** die Kapitel, und jede Taste in der Hinweiszeile ist ein klickbarer Chip. `Esc` bricht eine Eingabe ab oder öffnet den Beenden-Dialog.
- **Trackball:** horizontal steuert er auf der Brücke, vertikal schaltet er sonst die Hauptauswahl der Station.
- **Maus:** Ein Klick auf eine Taste in der Tastenleiste der Station, eine Lampe, einen Hinweis, einen Reiter, eine Scheibe oder eine Listenzeile tut genau das, was seine Taste tut, mit denselben Prüfungen. Das Menü-Symbol in der Kopfzeile öffnet das Spielmenü (Hilfe, Optionen, Speichern, Laden, Beenden). Auf Karten zoomt das Mausrad, Ziehen verschiebt (Einzelheiten im Kapitel Werkzeuge).

Globale Tasten (alle Stationen):

<!-- keys:global -->

## Die erste Patrouille (Fregatte) {#qs-first-patrol}

![Szenarioauswahl, nach Seite sortiert](figure:mission-scenario-selection)

1. Hauptmenü: **Neuer Einsatz** mit den Pfeiltasten und `Eingabe` wählen, die Fregatte mit `1` und `Eingabe`, dann Szenario 1 (Patrouille) mit `1` und `Eingabe`; die Einweisung zeigt Wetter und Tageszeit, `Eingabe` startet.
2. Brücke (`1`): nochmals `1` für die Missionsseite, Auftrag und Zeitlimit lesen.
3. Maschine (`7`): SLOW oder 6-8 kn wählen. Sonar (`2`): Schleppsonar mit `Y` ausbringen.
4. Sonar-Seite BROADBAND: nach einer hellen senkrechten Spur suchen; mit den Pfeiltasten wählen und mit `Eingabe` verfolgen.
5. Mit `C` klassifizieren, mit `T` TMA einschalten, dann auf der Brücke 30-60 Grad drehen und den neuen Schlag einige Minuten halten.
6. Sobald TMA oder Ping eine Entfernung liefern: Kontakt an die OPZ freigeben (`G`) und als Ziel setzen (`M`).
7. Waffen (`3`): Torpedotiefe auf die gepingte Zieltiefe stellen, mit `Strg+Eingabe` feuern.
8. Sonar auf anlaufende Torpedos beobachten; kommt einer, mit 24 kn laufen (nicht FLANK: das Schleppkabel des Nixie reißt über 25 kn), abdrehen und Nixie ausbringen (`V` in der Waffenzentrale).

## Die erste Tauchfahrt (U-Boot) {#qs-first-dive}

Am schnellsten kommen Sie mit Lektion 8 der Ausbildung ins U-Boot: Hauptmenü **Ausbildung**, Lektion 8 (Horchen und unter die Schicht) mit `8` oder den Pfeiltasten, `Eingabe`. Die uConsole spielt für diese Lektion das U-Boot, und ein Hinweisbanner wartet auf jeden Schritt:

1. Sonarraum (`2`): warten, bis die Fregatte in der Kontaktliste erscheint.
2. Den Kontakt mit `Auf`/`Ab` wählen und `C` drücken, bis er Kampfschiff heißt.
3. Die Schicht mit dem Bathythermografen messen (`E`).
4. Führung (`1`), dann `J`: Das U-Boot taucht unter die gemessene Schicht, wo das Bugsonar der Fregatte es schlecht hört.

Lektion 9 übt das Ausweichen vor einer pingenden Fregatte (`I` auf der Seite Bedrohung). Danach starten Sie **Neuer Einsatz**, das U-Boot mit `2` und `Eingabe`, dann Szenario 1 (Durchbruch) mit `1` und `Eingabe`: Erreichen Sie das auf der Karte mit ZIEL markierte Zielgebiet. Fahren Sie langsam (`-` am Telegrafen oder `A` für Schleichfahrt), bleiben Sie unter der Schicht, halten Sie den Mast nahe der Fregatte unten und weichen Sie mit `I` aus, wenn ein Ping- oder Torpedoalarm kommt.

## Unterwasserakustik in fünf Minuten {#qs-acoustics}

- **Passives Sonar liefert nur Peilung.** Jeder Kontakt beginnt als Peillinie. Entfernung liefern aktiver Ping, TMA, Sonarbojen oder Kreuzpeilung.
- **Ortung heißt Signal gegen Rauschen.** Es entscheidet die passive Sonargleichung SE = SL - TL - NL + DI - DT: Quellpegel des Ziels (lauter = weiter), Übertragungsverlust (Ausbreitung, Absorption, Schicht- und Pfadverluste), Rauschen (eigenes Rauschen plus Wind, Regen und Schiffsverkehr in der Nähe) und Gewinn der Antenne. Ab SE >= 0 dB gilt ein Kontakt als geortet. Wind und Regen wirken am stärksten, wenn Sie langsam und leise fahren; bei hoher Eigenfahrt dominiert das eigene Rauschen.
- **Eigene Fahrt ist eigener Lärm.** Der Eigenlärm steigt von 4 kn bis 31 kn, der Höchstfahrt der Fregatte. Ab 15 kn kavitieren die Schrauben, die Passivreichweite fällt auf etwa ein Drittel.
- **Die Sprungschicht (Thermokline) beugt den Schall.** Die passive Ausbreitung wird als Strahlverfolgung durch das echte Schallgeschwindigkeitsprofil gerechnet: über der Schicht trägt ein Oberflächenkanal den Schall weit, darunter liegt eine einige Meilen breite Schattenzone. In tiefem Wasser ist der Schatten stark; in einigen hundert Metern Wassertiefe füllen Bodenreflexionen und Mehrwege ihn ab etwa 10 sm auf, das Verstecken unter der Schicht wirkt dort vor allem auf kurze Distanz. Ein Ping in die Schattenzone erreicht nur 35 % seiner Reichweite.
- **Meeresboden und Oberfläche zählen.** Fels und Kies reflektieren gut, Schluff und Schlick schlucken; rauer Seegang streut hohe Frequenzen. **Konvergenzzonen** entstehen nur dort, wo das Wasser tief genug ist, damit die Strahlen wieder nach oben umkehren.
- **Baffles:** Eigenlärm ist eine weiche 70-Grad-Keule achteraus der Bugsonaranlage (beim Schleppsonar entlang des Kabels). Sie überdeckt, sie blendet nicht vollständig aus.

```text
            Oberfläche
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Fregatte HMS )))            direkter Pfad
  ---------- Sprungschicht ----------------  -6,5 dB quer
       TAS unter Schicht )))   U-Boot
                                (Schattenzone für flachen Sensor)
  ________________________________________ Meeresboden
```

## Navigationskonventionen {#qs-navigation}

- Entfernungen in Seemeilen (sm), Fahrt in Knoten (kn), Tiefe in Metern, Frequenz in Hz.
- Kurse und Peilungen sind rechtweisende Grad: 000 Nord, im Uhrzeigersinn. Karten sind genordet.
- Das Schiff dreht umso schneller, je schneller es fährt (etwa 0,75 Grad pro Sekunde bei 10 kn, 1,2 bei 16 kn), und gestoppt dreht es nicht; Fahrtänderungen dauern Minuten. Manöver früh planen.
