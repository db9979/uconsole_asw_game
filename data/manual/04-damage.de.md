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

- **FLUTEND:** durch ein Leck unter der Wasserlinie dringt Wasser ein. Der Zufluss folgt dem Wasserdruck: anfangs schnell, dann langsamer, je näher der Wasserstand innen der Wasserlinie außen kommt. Hoch liegende Räume (Brücke) fluten durch ein Leck nicht. Bei 70 % ist die Abteilung ZERSTÖRT.
- **BESCHÄDIGT:** das Leck ist abgedichtet; eine kleine Restleckage bleibt, bis ein Trupp den Raum lenzt.
- **Leckabdichtsätze:** jedes Abdichten verbraucht einen von 8 Sätzen. Ohne Sätze kann ein Trupp nur gegen das offene Leck lenzen.
- **Trefferort:** der Einschlagpunkt des Torpedos bestimmt die Abteilung; eine nahe Detonation reißt ein größeres Leck als eine entfernte. Flugkörper treffen über der Wasserlinie und verursachen vor allem Brände.
- **Brand:** wächst mit der Brandlast des Raums (Maschine, Flugdeck und Magazin brennen am stärksten) und wird von steigendem Wasser erstickt. Ein Raum, der etwa 30 s heiß bleibt, entzündet seine Nachbarn. Eine geflutete Schalttafel (Sonar, OPZ, Funk, Maschine) schließt kurz und löst einen Elektrobrand aus. Ein Brand über 90 % in der Waffenzentrale bringt das Magazin zur Explosion: der Raum ist zerstört, die Nachbarräume sind leckgeschlagen.
- **Stabilität:** Flutwasser macht das Schiff schwerer, und freie Wasseroberflächen verringern die metazentrische Höhe (GM). Das Schiff sinkt, wenn das Flutwasser die Reserveverdrängung übersteigt, und kentert, wenn GM verloren geht oder die Krängung 35 Grad überschreitet.
- **Krängung:** außermittiges Flutwasser lässt das Schiff zu dieser Seite krängen und zieht es vom Kurs.
- **Gegenfluten:** mit `C` und ab 5° Krängung öffnet die Leckwehr das Flutventil der hohen Rumpfseite; Wasser strömt mit 0,5 % des Raums je Sekunde ein, bis die Krängung ausgeglichen ist, nie über 60 % dieser Seite, und das Ventil schließt unter 1° von selbst (oder mit `C` erneut). Das Wasser ist echtes Flutwasser: es bringt Gewicht und Tiefgang, und ein Trupp muss es später lenzen.
- **Trimm:** Flutwasser vorn oder achtern trimmt das Schiff (Bug unten zählt positiv). Jedes Grad kostet 0,5 kn Höchstfahrt und erhöht bei Bug unten das Eigengeräusch am Bugsonar. Die Stabilitätszeile auf Seite 2 zeigt Krängung, Trimm und das offene Ventil.
- **Rudermaschine und Stabilisatoren:** die Rudermaschine liegt achtern unter dem Flugdeck. Ist dieser Raum zerstört, klemmt das Ruder in der letzten Lage, bis der Raum repariert ist. Ein zerstörter Rumpfraum auf einer Seite legt die Flossenstabilisatoren lahm, das Schiff rollt dann im Seegang stärker. Flutwasser macht das Schiff schwerer: es liegt tiefer und beschleunigt langsamer.

Auswirkungen auf Stationen: eine Station verliert mit Flutung und Brand in ihrem Raum stufenlos an Leistung (Sonar- und Radarreichweite sinken allmählich); ein zerstörter Raum legt sie lahm. Eine beschädigte Maschine begrenzt die Fahrt auf 15 kn, eine zerstörte auf 8 kn; eine beschädigte oder zerstörte Waffenzentrale sperrt Torpedostarts; ein zerstörtes Flugdeck verhindert Start und Landung des Helikopters; eine zerstörte OPZ legt auch ESM lahm.

## Tasten {#damage-keys}

<!-- keys:damage -->

Auf der uConsole weisen die Joystick-Tasten 1-3 Trupp 1-3 direkt der gewählten Abteilung zu.

## Standardablauf {#damage-sop}

<!-- sop:damage -->

## Tipps für Profis {#damage-tips}

- Trupps starten in der OPZ und brauchen je Abteilung etwa 20 s Weg; wirksam sind sie erst nach der Ankunft. Einen Trupp nahe Maschine und Waffenzentrale halten.
- Ein Trupp dichtet zuerst das Leck ab, dann lenzt er. Leckabdichtsätze sind begrenzt: für Räume unter der Wasserlinie verwenden, nicht für Räume, die schon nicht mehr fluten.
- Zwei Trupps in einem Raum halbieren die Zeit. Trupps können keiner zerstörten Abteilung zugewiesen werden.
- Brand neben Maschine oder Waffenzentrale ist am gefährlichsten: er greift auf einsatzkritische Räume über.

## Nicht modelliert {#damage-limits}

- Keine einzelnen Besatzungsmitglieder oder Verwundeten.
- Gegenfluten nur zwischen den beiden Rumpfseiten; kein gezieltes Fluten anderer Räume.
