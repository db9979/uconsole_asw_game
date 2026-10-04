# Nach dem Einsatz {#after-mission}

## Endtafel {#after-end}

Endet eine Mission, nennt die Endtafel das Ergebnis, die Punkte mit dem Faktor der Realismusstufe, einen neuen Bestwert und neue Auszeichnungen. `R` startet die Mission mit demselben Seed neu, `M` führt ins Hauptmenü und `D` öffnet die Nachbesprechung. Eine Mission aus der Mehrspieler-Lobby führt alle zurück in die Lobby.

## Nachbesprechung {#after-debrief}

Nachbesprechung: Nach Missionsende öffnet `D` im Endfenster die Nachbesprechung. Sie spielt die Mission ab und zeigt die Wahrheit neben dem, was die Crew wusste: die echten Kurse von Schiff und feindlichen U-Booten, die Kontakte der Crew dort, wo sie sie verortet hatte (reine Peilungen als Peilstrahlen), Waffen, Bojen und Luftfahrzeuge.

Daneben stehen die Zeit des ersten Kontakts, der ersten Ortung und der Klassifizierung, abgefeuerte Waffen und versenkte U-Boote, der mittlere Fehler der Ortungen und alle Ereignisse; eine "verpasste Chance" ist ein feindliches U-Boot, das mindestens 5 min lang höchstens 4 sm entfernt war, ohne dass es einen Kontakt gab, mit dem Hinweis über oder unter der Sprungschicht.

`Links`/`Rechts` blättern (Shift: 1 min), `Auf`/`Ab` oder `Bild auf`/`Bild ab` springen zwischen Ereignissen, ein Klick in die Zeitleiste springt dorthin, `Leertaste` spielt sie ab (`Tab`: 10× oder 60×), `D` oder `Esc` kehrt zurück. Aufgezeichnet wird alle 10 s (bei langen Missionen gröber); die Nachbesprechung ist während der Mission nie sichtbar und wird nicht gespeichert: nach dem Laden deckt sie die Mission ab dem Laden ab.

- **Nachbesprechung als Zeitraffer:** nach der Mission spielt `Leertaste` die Nachbesprechung ab, `Tab` wechselt zwischen 10× und 60×; die Wege wachsen, Schüsse, Pings, Treffer und Untergänge blitzen dort auf, wo sie geschahen. Im Browser zeigt die Schaltfläche **Nachbesprechung abspielen** (neben dem Missionsstand, erst nach dem Ende) dieselbe Wiedergabe für die eigene Seite.

## Einsatzbuch und Auszeichnungen {#after-logbook}

**Einsatzbuch** (Hauptmenü): jede beendete Mission (nie eine Lektion) der Seite, die die uConsole gespielt hat, mit Datum, Mission, Realismusstufe, Ergebnis, Punkten und Minuten; der Bestwert je Mission und fünf Auszeichnungen je Seite: erster Sieg, ein Schuss ein Treffer (der Gegner mit einer einzigen Waffe versenkt), ohne Kratzer (kein Schaden), nie beschossen und Realist (ein Sieg auf der Stufe Realistisch).

Die Fregatte trägt ihre Missionspunkte ein; das U-Boot zählt sein Ergebnis (Fregatte versenkt 1500, Geleitzug versenkt 1200, Durchbruch oder Meldung 1000, Entkommen 800, Überleben 600) plus bis zu 500 für ein unbeschädigtes U-Boot und 100 je übrigem Torpedo, mal dem Faktor der Stufe.

`Links`/`Rechts` oder `Tab` wechseln Fregatte und U-Boot, `A` die Auswertung des Sprachmodells, `B` den neuesten Bericht, `L` das Lernen des Gegners, `Enter` oder `Esc` zurück; die Fußzeile nennt diese Tasten, ein Klick darauf drückt sie. Das Endpanel nennt die Punkte, einen neuen Bestwert und neue Auszeichnungen. Das Einsatzbuch ist `~/.u-jagd/logbook.json` (die neuesten 200 Missionen), nie Teil eines Spielstands.

## Der Gegner lernt mit {#ref-habits}

- Nach jedem Einsatz ab 5 min notiert das Dienstbuch grobe Gewohnheiten der gespielten Seite. Fregatte: **frühes Pingen** (erster Ping vor oder bis 2 min nach dem ersten Kontakt), **schnelle Suche** (im Mittel ab 18 kn ohne Standort), **weite Schüsse** (Torpedos im Mittel ab 5 sm). U-Boot: **Sehrohrtiefe** (ein Viertel der Zeit), **über der Schicht** (die Hälfte der Zeit), **hohe Fahrt** (im Mittel ab 10 kn).
- Zeigten mehr als die Hälfte der letzten fünf Einsätze einer Seite (mindestens drei) eine Gewohnheit, kennt der Gegner sie im nächsten Einsatz und stellt sich leicht darauf ein: Gegen frühes Pingen gehen die U-Boote unter die Sprungschicht, sobald sie die Fregatte hören, und nach einem Ping alle tief; gegen schnelle Suche lauern sie, statt heranzuschließen; gegen weite Schüsse schleichen sie tief, statt heranzuschließen. Gegen ein U-Boot oft auf Sehrohrtiefe sucht die Jagdfregatte in Sprints, ebenso gegen eines über der Schicht, gegen hohe Fahrt sucht sie leise.
- Was der Gegner kennt, wird zu Beginn des Einsatzes festgelegt und gespeichert. Die Nachbesprechung nennt es, die Logbuchseite zeigt es je Seite. `L` auf der Logbuchseite schaltet das Mitlernen ab und wieder an. Im Tageseinsatz, in Lektionen und im Spiel mit zwei Crews lernt der Gegner nie mit.
