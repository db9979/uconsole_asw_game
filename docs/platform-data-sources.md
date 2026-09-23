# Plattformdaten: Quellen und Modellannahmen

## Geltungsbereich

`data/contacts/*.json` bleibt die einzige Quelle fuer Profilwerte. Das streng
validierte `data/contacts/sources.json` verknuepft ein v2-Profil und einen
logischen Feldpfad mit Quellen-IDs und einem Status, dupliziert aber keinen Wert.
Der historische R3-Baseline-Stand migrierte noch kein Profil. Der R4-Pilot stellte
`subs.json`, `warships.json` und `civilians.json` auf Version 2 um. R10 Batch 5
deckt nun alle 23 U-Boot-, alle 28 Kriegsschiff-, alle 55 Zivil-, beide
Flugzeug-, alle drei Tier-, alle drei Torpedo- und das Dekoyprofil feldgenau ab.
`acoustics.json` ist ebenfalls Version 2, besitzt als reine Bibliothek aber keine
Plattformkomponenten und daher keine Komponentenclaims.

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

## Fiktive Rumpfannahme fuer Grundberuehrung

Das physische Grundberuehrungsmodell verwendet eine unveraenderliche fiktive
U-Jagd-Spielannahme von 3.600 t Masse, 118 m Laenge, 14 m Breite, 7,5 m Tiefgang
und 1,5 m Kielreserve. Diese Werte sind `game_assumption`, gehoeren zu keiner
realen Plattform und duerfen nicht als reale Abmessungen oder Seebodenaussage
interpretiert werden. Neu erzeugte Flachstellen sind ebenfalls kontrollierte,
synthetische Spielgeometrie; gespeicherte Kuesten-/Bathymetriesnapshots werden
beim Laden nicht daraus neu erzeugt.

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

## R16: Fiktive U-Boot-Endurance

`subs.json` besitzt fuer jedes nichtnukleare v2-Profil genau eine
`endurances`-Komponente. Batterieenergie, Hotel- und Fahrtlastkurve,
Generatorleistung, optionale AIP-Leistung und -Energie, Reservehysterese,
Schnorcheltiefe und Funkdauer sind vollstaendig synthetische
`game_assumption`-Werte aus `u-jagd.game-model`. Sie sind keine publizierten oder
abgeleiteten Angaben zu den benannten Klassen. `null` bei den beiden AIP-Feldern
kennzeichnet nur die Nichtanwendbarkeit fuer die fiktiven Dieselprofile.

Nuklearprofile besitzen bewusst keine Endurance-Komponente und damit keine
erfundene Batterie-, Diesel-, Schnorchel- oder AIP-Abhaengigkeit. Die Runtime
verwendet die Komponente nur fuer eingebaute U-Bootprofile; sie erweitert weder
das Unit-Editor-Schema noch dessen Runtimewirkung.

## R10 Batch 1: U-Boote

Die drei generischen Szenarioarchetypen bleiben unter ihren bestehenden Keys
`diesel_alt`, `aip_modern` und `ssn` als synthetische Archetypen erkennbar. Fuer
die 18 neu migrierten benannten Klassen und diese drei Archetypen wurden keine
neuen oeffentlichen Quellen aufgenommen. Variantenbezeichnung, Rollen,
Antriebscodes, Maschinenlinien, Sensor-, Waffen-, Launcher-, Magazin- und
Gegenmassnahmenwerte sind deshalb ausschliesslich `game_assumption`. Nicht
belegte Jahre, Abmessungen, Verdraengung, Crew, Blattzahl und nullable
Systemdetails bleiben `null` mit Status `unknown`.

Die bestehenden oeffentlichen Claims fuer Virginia Block III (`sub_03`) und
Yasen-M (`sub_14`) bleiben unveraendert. Ebenso bleiben alle Legacy-Entry-Werte,
Keys, Reihenfolge und Spawngewichte unveraendert. Maschinen-Maximalfahrt und
Missionsmunition der neu migrierten Profile spiegeln nur diese vorhandenen
Spielwerte; sie sind keine publizierten Leistungs- oder Ausruestungsangaben.
Die endliche akustische Decoy-Ausstattung wird mit R10 bewusst auf diese Familie
ausgerollt. Anzahl, Bereitschaft, Cooldown und Wirksamkeit sind rein synthetische
`game_assumption`-Werte und keine Aussage ueber reale Plattformen.

## R10 Batch 2: Kriegsschiffe und Hilfsschiffe

Die 22 zuvor nicht migrierten Profile `warship_03` bis `warship_24` verwenden
keine neuen oeffentlichen Quellen. Variantenbezeichnung und Rollen sowie alle
Maschinen-, Sensor-, Emitter-, ASM-, Launcher-, Magazin- und
Gegenmassnahmenwerte sind `game_assumption`; nicht belegte Jahre, Abmessungen,
Verdraengung, Crew, Wellen-/Propulsordetails und nullable Systemverweise bleiben
`null` mit Status `unknown`. Insbesondere wird aus dem Anzeigenamen kein
Rumpftyp oder technisches Einzeldatum abgeleitet.

Maschinen-Maximalfahrt, ASM-Reichweite, Nachladezeit und Missionsbeladung
spiegeln ausschliesslich die bestehenden Spielgrenzen von 28 kn, 35 NM,
900 Sekunden und maximal vier Flugkoerpern je Salve. Der unbekannte Propulsor
erhaelt die bisherige fingerprintbasierte Akustik. Die normalisierten ASM- statt
ASROC-Komponenten fuegen den neu migrierten Profilen keine neue ASW-Faehigkeit
hinzu. Reihenfolge, Spawnpool und Gewichte bleiben unveraendert.

Die bereits in R8/R9 profilierten Komponenten von `warship_01`, `warship_02`
und `warship_25` bis `warship_28` bleiben unveraendert. Type 901 besitzt
weiterhin keine Nachversorgungslogik; Nimitz besitzt weiterhin keine Luftgruppe.

## R10 Batch 3: Zivile Schiffe

Die 54 zuvor nicht migrierten Zivilprofile verwenden keine neuen oeffentlichen
Quellen. Variantenbezeichnung, grobe Rolle, Maschinenlinien sowie generische
Radar-, AIS- und Emitterwerte sind deshalb `game_assumption`. Nicht belegte
Jahre, Abmessungen, Verdraengung, Crew, Wellen-/Motor-RPM, Blattzahl und nullable
Sensordetails bleiben `null` mit Status `unknown`. Anzeigenamen werden nicht als
Quelle fuer technische Einzeldaten behandelt.

Maschinen-Cruise- und Maximalfahrt entsprechen der bisherigen oberen
Profilfahrt. Der unbekannte Propulsor behaelt die fingerprintbasierte
Legacy-Akustik und veraendert keine Bewegungsgrenze oder RNG-Zugfolge. Die
Radar-/AIS-Komponenten verwenden das bestehende synthetische zivile Pilotmodell;
sie behaupten keine reale Systemleistung und nutzen nur lokale stabile
Sensorzufallswerte. Kein Zivilprofil erhaelt Waffen, Launcher, Magazine,
Gegenmassnahmen oder eine Kampfdoktrin. Eintragsreihenfolge, Kategorien,
Rufzeichen, Spawngewichte und der zivile Spawnpool bleiben unveraendert.

Der bestehende `cargo_05`-Datensatz bleibt mit der Variante `Generic Panamax
container-ship archetype` und seinem bisherigen R4-Komponentensatz explizit
generisch; er wird nicht nachtraeglich als reale Einzelplattform ausgegeben.

## R10 Batch 4: Flugzeuge

Die beiden bestehenden Archetypen `mil_patrol` und `civil_transit` bleiben unter
ihren bisherigen Keys, in derselben Reihenfolge und mit unveraenderten
Entry-Werten. Es werden keine realen Einzelmuster behauptet und keine neuen
oeffentlichen Quellen aufgenommen. Varianten, Rollen, Maschinenlinien sowie die
groben Radar-, ESM-/AIS- und Emitterwerte sind deshalb `game_assumption`.
Nicht belegte Jahre, Abmessungen, Verdraengung, Crew, RPM, Blattzahl und nullable
Systemdetails bleiben `null` mit Status `unknown`.

Die Maschinenfahrt entspricht jeweils exakt der bisherigen einzelnen
Profilgeschwindigkeit. Die militaerische Patrouille erhaelt Radar und passives
ESM mit der bestehenden ESM-Reichweite von 60 NM; der zivile Transit erhaelt
Radar und AIS. Eigene Radar-Emission und AIS-Uebertragung bleiben durch die
bisherige Flugdoktrin bestimmt. Komponentenmessungen verwenden nur stabile,
lokale Sensorhashes, waehrend die bestehende abgeloeste ESM-Beobachtung weiterhin
die Patrouillensteuerung speist. Dadurch bleiben Spawnpool, Loiterziehung,
Haupt-RNG-Zugfolge und Bewegungsdoktrin unveraendert.

Keines der beiden Profile besitzt Waffen, Launcher, Magazine oder
Gegenmassnahmen. Insbesondere wird weder eine Nimitz-Luftgruppe noch eine neue
Start-, Lande-, Traeger- oder sonstige Flugzeugoperation modelliert.

## R10 Batch 5: Tiere, Torpedos, Dekoy und Akustikbibliothek

Die sieben bestehenden Tier-, Torpedo- und Dekoyprofile bleiben synthetische
Spielarchetypen unter unveraenderten Keys und in unveraenderter Reihenfolge. Es
werden keine realen Arten, Torpedomuster oder Gegenmassnahmensysteme behauptet
und keine oeffentlichen Quellen aufgenommen. Variantenbezeichnung sowie alle
nicht-null Referenz- und Maschinenfelder sind `game_assumption`; Jahre,
Abmessungen, Verdraengung, Crew, RPM und Blattzahl bleiben `null` mit Status
`unknown`.

Maschinenfahrt, Tonallinien und Breitbandwerte spiegeln ausschliesslich die
vorhandenen Entry- und Bibliothekswerte. Der unbekannte Propulsor ist ein
verhaltensneutraler Adapter: Bewegung, Torpedoreichweite und Trefferhuelle,
Dekoy-Lebensdauer/Cooldown/Chance sowie Fingerprint- und Klassifikationswerte
bleiben aus den bisherigen Runtimeprofilen gespeist. Tiere und Dekoys erhalten
keine Sensor-, Emitter-, Waffen-, Launcher-, Magazin- oder
Gegenmassnahmenkomponenten. Die Torpedoprofile fuegen ebenfalls keine neuen
Sucher oder Waffen hinzu; bestehende Plattformkomponenten behalten ihre
`runtime_profile_key`-Verweise.

Die Akustikbibliothek behaelt exakt `animal` und `decoy`. Diese Keys sind ein
Klassifikations-Fangnetz beziehungsweise der beabsichtigte Alias des
Dekoyprofils, keine zusaetzlichen Plattformen. Deshalb sind ihre v2-Register
leer; insbesondere wird fuer den biologischen Bibliothekseintrag kein Sensor
und fuer den Dekoy keine Waffe erfunden.

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
privaten Quelldateien oder nachgezeichneten Drittgrafiken gebuendelt. Die
Analyzerdiagramme entstehen deterministisch aus normalisierten Akustikfeldern;
sie enthalten keine fremden Grafiken, Schriften oder Aufnahmen.

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
