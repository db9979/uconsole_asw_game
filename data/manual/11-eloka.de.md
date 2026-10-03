# 9 EloKa {#station-eloka}

## Zweck {#eloka-purpose}

Die Elektronische Kampfführung (EloKa) horcht passiv auf Radarsender (ESM) und stört sie auf Befehl (ECM). ESM erfasst Radare bis etwa 150 sm, weit jenseits des eigenen Radars, ohne selbst zu senden. Sie liefert Peilungen und Senderparameter, die auf einen Plattformtyp hinweisen, und warnt, wenn ein Flugkörpersucher aufschaltet.

## Seiten {#eloka-pages}

| Seite | Zeigt |
|---|---|
| 1 Auffassungen | Auffassungskarten, Bedrohungsrose mit Filterzeile, die gewählte Auffassung, Lampen für ESM, Störsender, automatisches ECM und Ton |
| 2 Evidenz | Volle Evidenz der gewählten Auffassung: Frequenz, PRF, Modulation, Kandidaten, Korrelation |

## Anzeigen und Instrumente {#eloka-displays}

Beide Seiten zeigen die Erfassungen links als Karten (Kennung, Peilung, Frequenz und Band, Güte und Alter; der Streifen trägt die Bedrohungsfarbe; ein Klick wählt eine wie `↑`/`↓`). Seite 1 hat in der Mitte die Bedrohungsrose mit der Filterzeile und rechts die gewählte Erfassung (Signal-Fingerabdruck, Peilung, Radarart, Bedrohung, ECM, Zuordnung, beste Bibliothekskandidaten) über den Lampen für ESM, Störer, ECM-Automatik und Ton; Seite 2 zeigt alle Belege für die gewählte Erfassung (Frequenz, PRF, Modulation, Kandidaten, Korrelation).

![ELOKA auf der uConsole](figure:station-eloka)

![ELOKA im Remote-Crew-Browser](figure:web-eloka-desktop)

```text
 ERFASSUNGEN                      Status  Bedroh. Band
 > E-07  Pg 312  9,3 GHz  PRF 2,4k  NEU     HOCH    X
   E-04  Pg 045  3,0 GHz  PRF 1,0k  TRACK   NIEDRIG S

 BELEGE E-07
   Frequenz 9,3 GHz   PRF 2400 Hz   Modulation Puls-Doppler
   Kandidaten (gerankt, nicht identifiziert):
     1. Flugkörpersucher     2. Feuerleitradar
   Korrelation: vereinbar mit OPZ-Track T-12 (Zeit/Peilung)
```

- Die Peilgenauigkeit beträgt etwa +/-3 Grad. Erfassungen sind Peilungen, keine Positionen.
- Ein drehendes Suchradar trifft die ESM-Antenne einmal je Umlauf mit der Hauptkeule; seine Nebenkeulen sind nur aus der Nähe hörbar. Die Belegseite zeigt den Spitzenpegel, eine Entfernungsschätzung unter Annahme der Leistungsklasse des besten Kandidaten (ein falscher Kandidat ergibt eine falsche Entfernung) und die gemessene Antennenumlaufzeit.
- Standardmäßig (Realismusstufe Standard oder Realistisch, `F10`) zeigt die Belegseite nur die gemessenen Parameter und eine Bibliotheksabfrage: jeder Sender, dessen veröffentlichter Frequenz- (und PRF-)Bereich die Messung enthält, nach Namen sortiert, ohne Bewertung. Radartyp, Bedrohung und Entfernungsschätzung beurteilen Sie dann selbst; `C` schaltet die Bibliothek in Namensreihenfolge durch. Auf der Stufe Einsteiger werden Kandidaten nach Frequenz, PRF und Modulation mit Bewertung gerankt und Radartyp, Bedrohung und Entfernungsschätzung ausgefüllt. Ein Gleichstand ist keine Identifizierung.
- Die Korrelation mit Radar- oder Sonartracks nutzt vereinbare Zeit, Peilung und beobachtete Position, nie verborgene Identität.
- Die Senderbibliothek enthält den Suchkopf des Seezielflugkörpers (9,0-9,5 GHz, PRF 1,8-3,2 kHz, Puls-Doppler). Er sendet nur auf den letzten 18 sm und erst, wenn der Tiefflieger über dem Radarhorizont ist, und er passt ebenso gut zum Feuerleitradar eines Angriffsflugzeugs: Peilungsverlauf und Luftlage entscheiden.
- ESM läuft aus der OPZ-Abteilung: eine zerstörte OPZ legt es lahm.

Neben der Liste der Auffassungen zeigt eine Peilrose jede Auffassung als Strahl in ihrer Bedrohungsfarbe, und Lampen zeigen ESM, Störer, ECM-Automatik und Ton.

## ECM-Techniken {#eloka-ecm}

| Technik | Wirkung |
|---|---|
| Rauschen | Überdeckt das Opferradar mit Breitbandrauschen |
| RGPO | Range Gate Pull-Off: zieht das Entfernungstor des Suchers weg |
| VGPO | Velocity Gate Pull-Off: zieht das Dopplertor weg |
| Falschziele | Speist falsche Echos ein |

Der Automatikmodus (`A`) wählt Ziele und Techniken und koppelt das Stören während eines Flugkörperangriffs mit Soft-Kill (Düppel).

## Tasten {#eloka-keys}

<!-- keys:eloka -->

## Maus {#eloka-mouse}

Jede Taste in der Tastenleiste am Fuß der Station lässt sich anklicken; gedrückt halten hält die Taste. Lampen, Seitenreiter und Tastenhinweise im Text sind ebenfalls anklickbar (Kapitel Werkzeuge, Maus). Außerdem:

- Ein Klick auf eine Auffassungskarte wählt sie wie `↑`/`↓`.

## Standardablauf {#eloka-sop}

<!-- sop:eloka -->

## Tipps für Profis {#eloka-tips}

- ESM auch unter EMCON laufen lassen: es ist vollständig passiv.
- Wechselt eine Erfassung bei stehender Peilung von Suche auf einen Puls-Doppler-Sucher mit hoher PRF, steht ein Flugkörperangriff bevor: sofort die OPZ warnen.
- Das Zuordnen eines Radartyps (`C`) gibt die Peilung an die OPZ frei; das Löschen der Zuordnung zieht sie zurück.
- Stören ist eine Aussendung. Gezielt einsetzen, nicht dauerhaft.
- Das eigene Radar wird ebenfalls gehört: ein U-Boot auf Sehrohrtiefe (Mast oben, etwa 18 m) fängt es mit seinem ESM auf und kann die Peilung über seinen Datalink an andere Gegner weitergeben. Tief getauchte U-Boote hören weder Radar noch empfangen sie den Datalink.

## Nicht modelliert {#eloka-limits}

- Keine Fernmeldeaufklärung (COMINT); KW-Signale bearbeitet der Funkraum (HFDF).
- Keine Täuschkörperwerfer außer Düppel und keine geschleppten Radartäuschkörper.
