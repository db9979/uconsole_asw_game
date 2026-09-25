# Schnellstart {#quickstart}

Sie führen die U-Jagd-Fregatte F-217 und besetzen neun Stationen. Auftrag: feindliche U-Boote orten, verfolgen, klassifizieren und versenken, ohne das eigene Schiff zu verlieren oder neutrale Schifffahrt zu gefährden.

> Dieses Handbuch beschreibt nur, was die Simulation tatsächlich abbildet. Nicht modellierte Funktionen stehen am Ende jedes Stationskapitels.

## Auftrag und Siegbedingungen {#qs-goal}

- **Sieg:** alle zugewiesenen Ziel-U-Boote versenken oder bis zum Zeitlimit überleben (je nach Mission).
- **Niederlage:** eigenes Schiff sinkt, ein ziviles Schiff wird getroffen, das Ziel entkommt mehr als 150 sm von seinem Startpunkt, oder die Zeit läuft bei einem Versenkungsauftrag ab.
- Fristwarnungen kommen bei 5, 2 und 1 Minute Restzeit.
- Punkte: 1000 je versenktem U-Boot, 200 je unverbrauchtem Torpedo, 500 ohne zivile Verluste, bis zu 500 Zeitbonus.

## Stationen {#qs-stations}

Das Schiff ist in neun Stationen gegliedert. Die Tasten `1`-`9` wählen eine Station; erneutes Drücken der Nummer der aktiven Station blättert ihre Seiten.

```text
 1 Brücke      2 Sonar       3 Waffen
 4 Schaden     5 OPZ         6 Funk
 7 Maschine    8 Helikopter  9 EloKa
```

Jede Station zeigt nur, was ihre Sensoren und Bediener wissen. Sonarkontakte sind verrauschte Peilungen, bis Ping, TMA, Boje oder Kreuzpeilung eine Entfernung liefern. Keine Station zeigt „die Wahrheit".

`F2` übergibt die aktuelle Station an die Autocrew; `F3` zeigt, welche Stationen automatisch laufen. Nutzen Sie das, um sich auf ein oder zwei Stationen zu konzentrieren.

## Bedienung {#qs-controls}

Das Spiel läuft mit 1280x720 und ist für Tastatur und Trackball der uConsole ausgelegt. Der Trackball wirkt als Joystick: horizontal steuert er auf der Brücke, vertikal schaltet er sonst die Hauptauswahl der Station. Eine Maus funktioniert ebenfalls: Rad zoomt Karten, Ziehen verschiebt, Klick heftet einen Tooltip an.

Globale Tasten (alle Stationen):

<!-- keys:global -->

Im Remote-Crew-Browser (Commander, `F9`) werden Stationen mit Schaltflächen bedient; die Tastatur hilft bei der Navigation:

<!-- keys:web -->

Die Statuszeile unten zeigt das neueste Ereignis und die wichtigste Telemetrie; `F11` blendet das volle Ereignislog und die Telemetrie über der Station ein, ohne sie anzuhalten oder ihr die Tasten zu nehmen. `F1` (oder `?`) öffnet jederzeit die Hilfe. Sie hat vier Kategorien: globale Tasten, aktuelle Station (Tasten und Standardablauf), Sensoren und Taktik sowie dieses Handbuch.

## Unterwasserakustik in fünf Minuten {#qs-acoustics}

- **Passives Sonar liefert nur Peilung.** Jeder Kontakt beginnt als Peillinie. Entfernung liefern aktiver Ping, TMA, Sonarbojen oder Kreuzpeilung.
- **Ortung heißt Signal gegen Rauschen.** Es entscheidet die passive Sonargleichung SE = SL - TL - NL + DI - DT: Quellpegel des Ziels (lauter = weiter), Übertragungsverlust (Ausbreitung, Absorption, Schicht- und Pfadverluste), Rauschen (eigenes Rauschen plus Wind, Regen und Schiffsverkehr in der Nähe) und Gewinn der Antenne. Ab SE >= 0 dB gilt ein Kontakt als geortet. Wind und Regen wirken am stärksten, wenn Sie langsam und leise fahren; bei hoher Eigenfahrt dominiert das eigene Rauschen.
- **Eigene Fahrt ist eigener Lärm.** Der Eigenlärm steigt von 4 kn bis 25 kn. Ab 15 kn kavitieren die Schrauben, die Passivreichweite fällt auf etwa ein Drittel.
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
- Das Spiel läuft immer in Echtzeit: eine echte Sekunde ist eine Simulationssekunde. Es gibt weder Zeitraffer noch Pause; auch Menüs, Hilfe, Optionen, Speichern/Laden und ein Fokuswechsel halten die Simulation nicht an.
- Das Schiff dreht höchstens 0,8 Grad pro Sekunde; Fahrtänderungen dauern Minuten. Manöver früh planen.

## Die erste Patrouille {#qs-first-patrol}

1. Hauptmenü: Szenario 1 (Patrouille) mit `1` wählen und mit `Enter` starten.
2. Brücke (`1`): nochmals `1` für die Missionsseite, Auftrag und Zeitlimit lesen.
3. Maschine (`7`): SLOW oder 6-8 kn wählen. Sonar (`2`): Schleppsonar mit `Y` ausbringen.
4. Sonar-Seite BROADBAND: nach einer hellen senkrechten Spur suchen; mit den Pfeiltasten wählen und mit `Enter` verfolgen.
5. Mit `C` klassifizieren, mit `T` TMA einschalten, dann auf der Brücke 30-60 Grad drehen und den neuen Schlag einige Minuten halten.
6. Sobald TMA oder Ping eine Entfernung liefern: Kontakt an die OPZ freigeben (`G`) und als Ziel setzen (`M`).
7. Waffen (`3`): Torpedotiefe auf die gepingte Zieltiefe stellen, mit `T` feuern.
8. Sonar auf anlaufende Torpedos beobachten; kommt einer, FLANK, abdrehen und Nixie ausbringen (`V` in der Waffenzentrale).

## Hauptmenü, Speichern und Optionen {#qs-menu}

- Menü: `1`-`4` Szenario (4 = Zufall mit eigener Schwierigkeit), `W` Weltmodus, `R` neuer Seed, `F` Vollbild, `Enter` Start.
- `S` / `L`: Speichern / Laden (Plätze 1-5). Spielstände sind exakt und deterministisch: ein geladenes Spiel läuft identisch weiter.
- `F10`: Optionen - Sprache, Vollbild, Audio, große Schrift, Tooltips, Bildrate (30 oder 60 FPS; 30 spart Rechenleistung auf der uConsole und ist voreingestellt), Ereignislog/Telemetrie als Statuszeile (Standard, mehr Platz für die Station) oder feste Leiste.
- `F9`: Commander / Remote Crew - Browser im LAN können Stationen übernehmen.
