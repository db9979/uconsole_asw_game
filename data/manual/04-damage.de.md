# 4 Schadensabwehr {#station-damage}

## Zweck {#damage-purpose}

Die Schadensabwehr hält das Schiff nach einem Treffer schwimmfähig und die Stationen einsatzbereit. Drei Reparaturtrupps bekämpfen Wassereinbruch und Brand in neun Abteilungen. Jede Abteilung beherbergt eine Station; eine beschädigte Abteilung schwächt sie, eine zerstörte fällt für den Rest der Mission aus.

## Anzeigen und Instrumente {#damage-displays}

Seite 1 ist der Schiffsplan; Seite 2 zeigt Details je Abteilung (Flutung, Brand, Tendenz, Trupps vor Ort, Krängung).

```text
  Bug                                                    Heck
 +--------+--------+---------+-----+-------+--------+-----------+
 | BRÜCKE | SONAR  | WAFFEN  | OPZ | FUNK  | MASCH. | FLUGDECK  |
 +--------+--------+---------+-----+-------+--------+-----------+
 |          RUMPF BACKBORD       |        RUMPF STEUERBORD       |
 +-------------------------------+-------------------------------+
  Zustand: OK -> BESCHÄDIGT / FLUTEND -> ZERSTÖRT     Trupps: 1 2 3
```

- **FLUTEND:** das Wasser steigt (0,10 % je Sekunde), bis ein Trupp lenzt. Bei 70 % ist die Abteilung ZERSTÖRT.
- **BESCHÄDIGT:** stabilisierte Restleckage (0,025 % je Sekunde); braucht weiterhin einen Trupp bis OK.
- **Brand:** ein Treffer entfacht mit 35 % Wahrscheinlichkeit ein Feuer. Es wächst von selbst und kann auf Nachbarräume übergreifen; bei 100 % ist die Abteilung zerstört.
- **Gesamtflutung:** das Schiff sinkt bei 540 Punkten, also 60 % mittlerer Flutung über alle neun Abteilungen.
- **Krängung:** ungleiche Flutung zwischen Backbord- und Steuerbordrumpf lässt das Schiff krängen (bis 15 Grad) und zieht es zu einer Seite.
- **Rudermaschine und Stabilisatoren:** die Rudermaschine liegt achtern unter dem Flugdeck. Ist dieser Raum zerstört, klemmt das Ruder in der letzten Lage, bis der Raum repariert ist. Ein zerstörter Rumpfraum auf einer Seite legt die Flossenstabilisatoren lahm, das Schiff rollt dann im Seegang stärker. Flutwasser macht das Schiff schwerer: es liegt tiefer und beschleunigt langsamer.

Auswirkungen auf Stationen: eine beschädigte Sonarzentrale halbiert die Sonarreichweite; eine beschädigte Maschine begrenzt die Fahrt auf 15 kn, eine zerstörte auf 8 kn; eine beschädigte oder zerstörte Waffenzentrale sperrt Torpedostarts; ein zerstörtes Flugdeck verhindert Start und Landung des Helikopters; eine zerstörte OPZ legt auch ESM lahm.

## Tasten {#damage-keys}

<!-- keys:damage -->

Auf der uConsole weisen die Joystick-Tasten 1-3 Trupp 1-3 direkt der gewählten Abteilung zu.

## Standardablauf {#damage-sop}

<!-- sop:damage -->

## Tipps für Profis {#damage-tips}

- Ein Trupp lenzt 0,12 % je Sekunde, mehr als eine flutende Abteilung zunimmt. Zwei Trupps in einem Raum halbieren die Zeit.
- Unter 35 % Flutung wechselt ein Raum von FLUTEND auf BESCHÄDIGT; das ist der Moment, einen Trupp zum nächsten Notfall zu schicken.
- Trupps können keiner zerstörten Abteilung zugewiesen werden. Nicht dort verschwenden.
- Brand neben Maschine oder Waffenzentrale ist am gefährlichsten: er greift auf einsatzkritische Räume über.

## Nicht modelliert {#damage-limits}

- Keine einzelnen Besatzungsmitglieder, Verwundeten oder Munitionsexplosionen.
- Kein Gegenfluten; Krängung mit Reparatur und Ruder ausgleichen.
