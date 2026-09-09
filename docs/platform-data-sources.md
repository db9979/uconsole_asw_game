# Plattformdaten: Quellen und Modellannahmen

## Geltungsbereich

`data/contacts/*.json` bleibt die einzige Quelle fuer Profilwerte. Das streng
validierte `data/contacts/sources.json` verknuepft ein v2-Profil und einen
logischen Feldpfad mit Quellen-IDs und einem Status, dupliziert aber keinen Wert.
Der historische R3-Baseline-Stand migrierte noch kein Profil. Der R4-Pilot stellt
`subs.json`, `warships.json` und `civilians.json` auf Version 2 um und deckt neun
Profile feldgenau ab. Die fuenf uebrigen Profildokumente bleiben Version 1.

## Quellenarten

| Art | Bedeutung |
|---|---|
| `public_source` | Oeffentlich zugaengliche Behoerden-, Museums-, Fach- oder vergleichbare Referenz. |
| `manufacturer` | Oeffentliches Herstellermaterial. Eine Herstellerangabe ist keine unabhaengige Bestaetigung. |
| `game_assumption` | Eigenstaendig erstellter synthetischer Spielwert; keine verschleierte Ableitung aus privaten Unterlagen. |

Oeffentliche Erreichbarkeit ist keine Lizenz zur Uebernahme von Texten,
Tabellen, Zeichnungen, Bildern oder Datensaetzen. `license: null` behauptet keine
Weitergabelizenz; es dokumentiert nur, dass eine Quelle fuer einzelne oeffentliche
Fakten zitiert wird. Erforderliche Attributionen muessen zusaetzlich in
`THIRD_PARTY_NOTICES.md` stehen.

## Claimstatus

| Status | Vertrag |
|---|---|
| `published` | Der Feldwert wird direkt von mindestens einer oeffentlichen oder Herstellerquelle berichtet. |
| `derived` | Der Wert wird nachvollziehbar aus genannten oeffentlichen Quellen normalisiert oder berechnet. |
| `game_assumption` | Der Wert stammt aus dem dokumentierten U-Jagd-Spielmodell und referenziert exakt eine Quelle dieser Art. |
| `unknown` | Es wird kein Faktenwert behauptet; das referenzierte v2-Feld ist `null` und besitzt keine Quelle. |

Ein Claim besitzt eine eindeutige Kombination aus Ressource, Profilkey und
Feldpfad. Mehrere bestaetigende Quellen stehen gemeinsam in `source_ids`.
Feldpfade sind kontrollierte logische Bezeichner wie `/reference/length_m` oder
`/sensors/sensor.example.radar/synthetic_range_nm`, niemals Dateipfade.

## R4-Pilotquellen

| Profile | Oeffentliche Referenzen im Manifest |
|---|---|
| Arleigh Burke Flight IIA (`warship_01`) | `usn.ddg51.2026`, `fas.aegis.1998` |
| Ticonderoga Baseline 2 (`warship_02`) | `fas.aegis.1998`, `usn.ticonderoga` |
| Type 055 (`warship_25`) | `navalnews.type055-type052d.2020`, `navalnews.type055-roles.2023` |
| Type 052D (`warship_26`) | `navalnews.type052d.2022` |
| Type 901 (`warship_27`) | `navaltechnology.type901.2022` |
| Nimitz (`warship_28`) | `usn.cvn.2025`, `usn.nimitz.about`, `usn.nimitz.history` |
| Virginia Block III (`sub_03`) | `usn.attack-subs` |
| Yasen-M (`sub_14`) | `navalnews.yasenm-launch.2020`, `navalnews.yasenm-commission.2021`, `navalnews.yasenm-analysis.2021` |
| Panamax-Archetyp (`cargo_05`) | Keine reale Einzelplattform behauptet; `u-jagd.game-model` |

Das Manifest enthaelt 14 oeffentliche Referenzen und eine lokale
Spielannahmenquelle. Direkte Fakten, metrische/rollenbezogene Normalisierungen,
synthetische Werte und unbekannte Felder bleiben getrennte Claims. Type 052D
verwendet 17,2 m Breite und 6,2 m Tiefgang. Mehrdeutige oder nicht hinreichend
belegte Werte, darunter mehrere Nimitz-Abmessungen und Crewangaben, bleiben
`null` statt aus dem Intake uebernommen zu werden.

Die groben Sensor-, Emitter-, Waffen-, Launcher-, Magazin- und
Gegenmassnahmenkomponenten sind vollstaendig `game_assumption` bzw. bei
absichtlich leeren Feldern `unknown`. Ihre technischen Zahlen behaupten keine
Leistung realer Systeme. Type 901 besitzt keine Nachversorgungslogik und Nimitz
keine Luftgruppe. VLS-Zellzahlen beschreiben separat die Modellkapazitaet;
`mission_count` ist eine kleinere fiktive Einsatzbeladung.

## Synthetische und unbekannte Werte

Moderne LOFAR-Linien und -Pegel, genaue Wellen-/Propellerdaten, Kavitation,
Radarleistung, PRF, Modulation, fiktive Einsatzmagazine und taktische
Effektivitaet gelten ohne belastbare offene Quelle als `game_assumption`.
Unbekannte Blattzahlen werden als `null`, nicht als 0 modelliert. Motor-RPM und
Wellen-RPM werden nie ohne Beleg gleichgesetzt. Widerspruechliche oeffentliche
Angaben werden nicht gemittelt: Variante, Bezugsjahr und Normalisierung werden
explizit festgelegt oder der Wert bleibt unbekannt.

Die R4-LOFAR-Pegel sind innerhalb jedes Betriebszustands relativ zum staerksten
Eintrag normiert:

```text
relative_level = 10 ** ((level_db - maximum_level_db) / 20)
```

Sie sind keine empfangenen Pegel und keine Messspektren. Absoluter Empfangspegel
und SNR bleiben Aufgabe der Sensorpipeline; `Target Strength` gehoert zum aktiven
Sonarmodell und wird nicht in diese relative Linienliste eingerechnet.

## Rechte- und Quellenausschluss

Es werden keine Fotos, Logos, Herstellerzeichnungen, Schiffsrisse, Tabellen,
privaten Quelldateien oder nachgezeichneten Drittgrafiken gebuendelt. Bilder und
Silhouetten entstehen spaeter deterministisch aus eigenen normalisierten
Geometriedaten.

Private WaveOps-/MNW-PDFs sind keine Quelle fuer Daten, Text, Bilder, Layouts
oder abgeleitete Diagramme. Sie erhalten weder eine Quellen-ID noch eine
`game_assumption`-Zuordnung. Hersteller-Claims duerfen nur wirklich oeffentliches
Herstellermaterial referenzieren, keine privat bereitgestellten Broschueren.

## Pflegeverfahren

1. Oeffentlichen Fakt unabhaengig pruefen und Variante/Bezugsstand festlegen.
2. Rechte und erlaubte Zitier-/Weitergabebedingungen pruefen.
3. Stabile Quellen-ID und Feldclaims in `sources.json` eintragen.
4. Normalisierung oder Herleitung in dieser Datei dokumentieren.
5. Erforderliche Attribution in `THIRD_PARTY_NOTICES.md` spiegeln.
6. `python tools/gen_contacts.py --check`, fokussierte Katalogtests,
   Paketressourcentests und den privaten-Asset-Scan ausfuehren.

Automatische Tests koennen Schema, Referenzen und Paketinhalt pruefen, aber
nicht die sachliche Richtigkeit, oeffentliche Erreichbarkeit oder Rechtefreiheit
einer Quelle beweisen. Diese Punkte bleiben manuelle Releasepruefungen.
Quellen-URLs werden vom Spiel und Validator nie abgerufen. Falls ein spaeteres
Werkzeug dies tun soll, muss es DNS-Ergebnisse und jeden Redirect erneut gegen
lokale, private und reservierte Ziele pruefen; die heutige Syntaxpruefung ist
keine Netzfreigabe.
