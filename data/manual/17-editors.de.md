# Missions- und Einheiteneditor {#editors}

Missionseditor und Einheiteneditor (beide im Hauptmenü) bauen eigene Missionen und Einheitenprofile. Sie laufen außerhalb einer Mission; während Sie bearbeiten, läuft keine Simulation.

## Missionseditor {#ed-mission}

![Missionseditor](figure:mission-editor)

![Missionseditor, Einheitendetails](figure:mission-editor-detail)

Eigene Missionen starten aus dem Missionseditor (`F5` in dessen Browser). Die Laufzeit übernimmt den Umfang des Editors: eine 500-sm-Welt fest oder als paketierter Referenzsektor (`sector:0` bis `sector:127`), das eingestellte Wetter, platzierte U-Boote, Überwasserschiffe, Luftfahrzeuge (Patrouille in einem 10-sm-Kasten mit Profilgeschwindigkeit), Tiere, ruhende Täuschkörper und feindliche Torpedos, die schon auf ihrem Kurs laufen, gesäte Zufallsgruppen, zeitgesteuerte Ereignisse (Meldung, Erscheinen, Wetter, Ziel) und die Ziele Versenken, Überstehen, Schützen (die benannten Einheiten bis zum Zeitlimit erhalten) und Erreichen (den Radius des Zielpunkts betreten).

Im Einheiteneditor gespeicherte Profile lassen sich wie eingebaute platzieren und wirken in dieser Mission (Fahrtbereich, Tiefe, Torpedozahl, Verhalten, Akustik); ein eigenes U-Boot übernimmt Sensoren, Rohre, Täuschkörper und seine Batterie-, Diesel- oder AIP-Anlage vom eingebauten U-Boot seines Antriebs. Torpedos der Fregatte und des Helikopters, fehlende Benutzerprofile und andere Weltgrößen werden beim Start abgewiesen.

Ein Feld öffnet sich mit `Eingabe` oder einem zweiten Klick auf seine Zeile (der erste Klick wählt sie). Im Editor-Reiter Welt öffnet `Eingabe` auf Art oder Referenz eine Auswahlliste (`Hoch`/`Runter`, `Bild auf`/`Bild ab`, `Eingabe` übernimmt, `Esc` bricht ab); Referenz listet die 128 Sektoren mit ihren Ländern, und die Wahl eines Sektors macht die Welt zu einer 500-sm-Referenzwelt. Der Reiter Vorschau zeichnet dann die Küste dieses Sektors.

## Eigene Missionen und Weitergabe {#ed-share}

Eigene Missionen und Teilen: In der Übersicht des Missionseditors ist die Spielerseite Fregatte oder U-Boot. Für das U-Boot nennt „Eigenes U-Boot“ ein platziertes feindliches U-Boot, das der Spieler führt, während die KI die Fregatte besetzt; seine Ziele sind Versenken (Ziele können nur Handelsschiffe sein, weil die Torpedos des U-Boots die zivile Schifffahrt treffen), Überstehen (bis zum Zeitlimit aushalten) oder Erreichen, nie Schützen. Das U-Boot gewinnt, wenn es alle Ziele versenkt, den Punkt erreicht oder aushält, und verliert, wenn es versenkt wird oder bei Versenken und Erreichen die Zeit abläuft. Die Liste des Editors markiert U-Boot-Missionen mit `[U]`, und Kurzbeschreibung und Vorschau geben Fairness-Hinweise: ein U-Boot, das näher als 3 sm an der Fregatte startet, gar keine feindliche Einheit, oder ein Zielpunkt bzw. nächstes Ziel, das die Seite im Zeitlimit kaum erreicht (Fregatte 20 kn, U-Boot 8 kn).

`Strg+E` teilt die gewählte Mission als Datei in den Austauschordner `~/.u-jagd/share` (Windows: `%USERPROFILE%\.u-jagd\share`), mit jeder eigenen Einheit, auf die sie verweist; `Strg+Umschalt+E` exportiert weiter auf einen eingetippten Pfad. `Strg+I` listet die Dateien in diesem Ordner mit ihren Missionen (`Hoch`/`Runter`, `Eingabe` importiert, ein zweites `Eingabe` überschreibt vorhandene Einträge, `Tab` tippt stattdessen einen Pfad, `O` öffnet den Ordner, `Esc` schließt); schon gleiche Einträge werden übersprungen. `O` in der Liste des Editors öffnet den Ordner im Dateimanager (unter Windows im Explorer). Eine Datei in den Ordner eines Freundes kopieren, und er importiert sie mit `Strg+I`.

Im Solo-Modus von Remote Crew listet „Eigene Missionen“ in der Gastgeberleiste des Browsers dieselben Missionen mit Seite, Ziel, Hinweisen oder Fehlern: Starten (wechselt vorher auf die Seite der Mission), Bearbeiten, Herunterladen (dieselbe Teilen-Datei) und Löschen; „Datei hochladen“ nimmt eine Teilen-Datei oder eine einzelne Mission (höchstens 1 MB). „Neue Mission“ oder Bearbeiten öffnet den Missionsplaner: Reiter Übersicht, Welt, Einheiten, Ziel und Ereignisse und eine Karte der Welt oder des Referenzsektors, auf der ein Klick die Fregatte, die gewählte Einheit oder den Zielpunkt setzt. Speichern legt die Mission nach derselben Prüfung wie im Editor auf der uConsole ab (Fehler werden aufgelistet, ein vorhandener Schlüssel fragt vor dem Überschreiben), Speichern und starten startet sie sofort. Crew-Sitzungen haben keinen Zugriff auf die Bibliothek.

## Einheitenanalysator und Einheiteneditor {#ed-unit}

![Einheiteneditor](figure:unit-editor)

![Kontaktanalyse (F8)](figure:contact-analyzer)

Einheitenanalysator (`F8`, Hauptmenü) und Einheiteneditor: Die erste Seite jedes Katalogprofils im Analysator ist ein schematisches 3D-Modell seines Typs (Reiter `3D`, danach mit `Links`/`Rechts` die Klang- und Radarbilder); es dreht sich langsam und lässt sich im Remote-Crew-Browser zusätzlich durch Ziehen drehen. Der Einheiteneditor zeigt dasselbe Modell unter dem gewählten Profil und neben den Feldern eines geöffneten.

Jeder Schiffs-, U-Boot- und Flugzeugtyp des Katalogs hat ein eigenes Modell, gebaut aus den öffentlichen Hauptabmessungen und der Anordnung der echten Klasse (Wikipedia; allgemeine Typen wie ein VLCC oder ein Hafenschlepper mit typischen Werten): Länge, Breite und Tiefgang, wo Brücke, Masten, Schornsteine, Geschütze, Flugkörperzellen, Flugdeck, Kräne und Ladung stehen, beim U-Boot Turm, Tiefenruder, Heckruder und Raketendeck, beim Flugzeug Flügel, Leitwerk und Triebwerke. Derselbe Typ sieht immer gleich aus; Profile aus dem Einheiteneditor und alles ohne eigenen Typ behalten das Modell ihrer Klasse (Kriegsschiff, Handelsschiff, Kleinfahrzeug, U-Boot, der Hubschrauber des Ausgucks). Torpedos, Täuschkörper, Wale, Fischschwärme und Quallen haben eigene Modelle.

Die Modelle sind schematisch und werden alle gleich lang gezeichnet, sind also untereinander nicht maßstäblich. Dieselben Modelle stehen, um den geschätzten Lagewinkel gedreht, in den Okularen (Ausguck, Fernglas, Sehrohr); der Browser lädt sie beim ersten Gebrauch in drei Gruppen nach.
