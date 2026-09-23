# 1 Brücke {#station-bridge}

## Zweck {#bridge-purpose}

Die Brücke führt die Fregatte: Kurs, Fahrt und Position zu Küste, Kontakten und Bedrohungen. Jeder Sensor hängt davon ab, wie das Schiff gefahren wird. Schnell und geradeaus ist laut und blind; langsame, ruhige Schläge mit bewussten Wenden lassen Sonar und TMA arbeiten.

## Anzeigen und Instrumente {#bridge-displays}

Seite 1 (Navigation) zeigt Karte und vier Felder; Seite 2 (nochmals `1`) zeigt das Missionsbriefing.

```text
+---------------------------+----------------------+
|                           | KURS / RUDER         |
|   KARTE (genordet)        |  Kurs 045 > 080      |
|   eigenes Schiff + Kielw. |  Ruder 15 stb        |
|   veröffentlichte Tracks  +----------------------+
|   Peillinien / Fixe       | FAHRT / AKUSTIK      |
|   Helikopter, Bojen       |  HALF 10,0 kn        |
|                           |  38% Eigenlärm       |
|                           +----------------------+
|                           | TAKTISCHE LAGE       |
|                           |  Bedrohungen, Senso- |
|                           |  ren, Mittel, Wetter |
+---------------------------+----------------------+
 Fußzeile: <- -> Kurs | Auf/Ab Telegraph | U/V direkt
```

- **Kurs / Ruder:** aktueller Kurs, befohlener Kurs, Ruderlage und Drehkreis.
- **Fahrt / Akustik:** Telegraphenstufe, Fahrt, Eigenlärm in Prozent und Warnung KAVITATION über 15 kn.
- **Taktische Lage:** beobachtete Bedrohungen (z. B. Torpedopeilung oder Flugkörperbedrohung), Sensorzustand (Radar, TAS), Mittel (Helikopter, Bojen) und Wetter/Tag-Nacht.
- **Karte:** synthetische Kartentiefe und Küste, eigenes Schiff, von anderen Stationen veröffentlichte Tracks. Mausrad oder `Q`/`E` zoomen, Ziehen verschiebt, `K` folgt dem eigenen Schiff.

## Tasten {#bridge-keys}

<!-- keys:bridge -->

Auf der Brücke steuert der Trackball das Ruder. `U` und `V` öffnen die direkte Zahleneingabe; die Simulation läuft währenddessen weiter. `Enter` bestätigt, `Esc` bricht ab.

## Standardablauf {#bridge-sop}

<!-- sop:bridge -->

Gefechtslage:

1. Torpedo gemeldet: sofort FLANK, so drehen, dass die Torpedopeilung achteraus oder querab liegt.
2. Nixie in der Waffenzentrale befehlen (`V`); weiter drehen, damit der Torpedo zuerst den Täuschkörper sieht.
3. Nach der Abwehr unter 15 kn gehen, damit das Sonar wieder erfasst; mit ausgebrachtem Schleppsonar nie über 20 kn.

## Tipps für Profis {#bridge-tips}

- TMA braucht eine echte Änderung der eigenen Geschwindigkeit. Eine Wende um 30-60 Grad mit anschließend mehreren Minuten ruhigem Schlag liefert die beste Entfernungsschätzung. Drehen auf der Stelle hilft nicht.
- Das Schiff dreht höchstens 0,8 Grad pro Sekunde und braucht Minuten für Fahrtänderungen. Ausweichmanöver früh beginnen.
- Sprint und Drift: mit FULL an eine neue Position, dann auf 4-6 kn gehen und horchen.
- Starke einseitige Flutung bewirkt Krängung und einen stetigen Drehzug; mit Ruder ausgleichen.
- Das Schiff kann nicht auf Land fahren (es wird zurückgeschoben), aber Flachwasser begrenzt die Tauchtiefe des Helikoptersonars (10 m Bodenabstand).
- Die Wassertiefe folgt der Gezeit (halbtägig, etwa 12,4 h, im Flachwasser bis zu einigen Metern). Eine Passage, die bei Hochwasser sicher ist, kann bei Niedrigwasser zur Grundberührung führen; das HQ-Wetterbulletin meldet die aktuelle Gezeit am Schiff.
- Wind treibt das Oberflächenwasser: etwa 3 % der Windgeschwindigkeit, 20 Grad rechts von der Windrichtung, zusätzlich zur ständigen Meeresströmung.

## Nicht modelliert {#bridge-limits}

- Keine Zeitraffung und keine Autopilot-Wegpunkte für die Fregatte.
- Kein eigener Torpedoalarm-Ablauf: anlaufende Torpedos erscheinen nur als Sonarkontakt und in der taktischen Lage, wenn sie beobachtet werden.
