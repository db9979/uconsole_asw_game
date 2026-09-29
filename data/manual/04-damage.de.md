# 4 Schadensabwehr {#station-damage}

## Zweck {#damage-purpose}

Die Schadensabwehr hält das Schiff nach einem Treffer schwimmfähig und die Stationen einsatzbereit. Drei Reparaturtrupps bekämpfen Wassereinbruch und Brand in neun Abteilungen. Jede Abteilung beherbergt eine Station; eine beschädigte Abteilung schwächt sie, eine zerstörte fällt für den Rest der Mission aus.

## Anzeigen und Instrumente {#damage-displays}

Seite 1 ist der Schiffsplan als Leckwehr-Leitstand: in jeder Abteilung steigt das Wasser vom Kiel an, ein Brand glüht rot und eine zerstörte Abteilung ist schraffiert. Die Karte jeder Abteilung trägt eine Zustands-LED, Flutung und Brand mit ihren LEDs und Balken sowie nummerierte Plaketten für die Trupps vor Ort; eine Legende unter dem Plan erklärt die LEDs. Seite 2 zeigt Details je Abteilung (Flutung, Brand, Tendenz, Trupps vor Ort, Krängung); Seite 3 ist der Wachplan der Besatzung. Im Browser beginnt die Karte Schaden mit einer Warn- und Meldetafel (Brände, Wassereinbruch, ausgefallen, verschlechtert, Gesamtschaden, Krängung, Trimm, Gegenfluten, Trupps aktiv, Schiff gesunken) über einer Seitenansicht des Schiffs, Bug links, und Rundinstrumenten für Krängung, Trimm und Gesamtschaden; ein Klick auf eine Abteilung schickt den gewählten Trupp dorthin.

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

## Besatzung und Wachen {#damage-crew}

Seite 3 (Besatzung) zeigt den Wachplan. Die Besatzung geht in drei Wachen: eine ist im Dienst und ermüdet, die beiden anderen ruhen und erholen sich. Die Wache im Dienst wird jede Spielstunde automatisch abgelöst (eine echte Wache dauert vier Stunden; das Spiel verkürzt sie, damit eine Partie den Wechsel erlebt) oder früher mit `W` auf dieser Seite. In der ersten Minute nach der Ablösung arbeitet sich die neue Wache ein und bringt 85 %.

- **Ermüdung** (0 bis 100 % je Wache) steigt in einer normalen Stunde im Dienst um etwa 25 % und sinkt in der Ruhe wieder. Bis 25 % kostet sie nichts, normaler Wachwechsel hält die Besatzung also bei voller Leistung. Darüber kosten je 10 % Ermüdung 6 % Leistung.
- **Gefechtsstationen** (`G` hier oder auf der Brücke) holen alle Wachen in den Dienst: die Besatzung ist 10 % aufmerksamer, aber niemand ruht, und alle sind in 90 Minuten von frisch bis erschöpft, schneller bei Brand- oder Leckbekämpfung. Auf Gefechtsstationen gibt es keine Ablösung; beim Aufheben übernimmt die frischeste Wache. Für einen Angriff auf Station gehen und danach aufheben: nach etwa einer halben Stunde auf Gefechtsstationen ist der Vorteil aufgebraucht.
- **Moral** beginnt bei 70 %. Ein versenktes U-Boot (+15), eine Rettung (+12) oder ein anderer erfüllter Auftrag (+6) heben sie; eine beschädigte Abteilung (-6), ein gescheiterter (-8) oder abgelehnter Auftrag (-2) senken sie; eine reparierte Abteilung bringt +2. Niedrige Moral ermüdet schneller; je 10 % Moral ändern die Leistung um 2 %.
- **Leistung** ist, was die Besatzung bringt: der Sonarbediener braucht ein stärkeres Signal (je 10 % Verlust hebt die Erkennungsschwelle um 1 dB, die Passivreichweiten sinken), der Ausguck braucht mehr Kontrast zum Sichten, Erkennen und Identifizieren, und die Reparaturtrupps dichten, lenzen und löschen in diesem Tempo. Seite 3 zeigt die aktuellen Werte; der Statusticker zeigt `BES` mit der Leistung oder `GEF` auf Gefechtsstationen.
- Das besetzte Gegner-U-Boot hat einen eigenen Wachplan mit denselben Regeln (siehe Kapitel Referenz).

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

- Keine einzelnen Besatzungsmitglieder, Verwundeten oder Schlaf nach der Uhr; Wachen werden jede Spielstunde abgelöst.
- Gegenfluten nur zwischen den beiden Rumpfseiten; kein gezieltes Fluten anderer Räume.
