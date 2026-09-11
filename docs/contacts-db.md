# Kontakt-DB: `data/contacts/*.json`

Die Kontakt-Datenbank ist die einzige Quelle (SSoT) für alle Plattformprofile
des Spiels. Sie liegt als JSON im Repository und wird zur Laufzeit von
`src.data.catalog` geladen. `tools/gen_contacts.py` ist trotz seines historischen
Namens ein strikt lesender Validator; es erzeugt oder veraendert keine Dateien.

```sh
python tools/gen_contacts.py            # Schema und Runtime-Ladeparitaet pruefen
python tools/gen_contacts.py --check    # identisches Verhalten (0 = gueltig)
python tools/gen_contacts.py --check DIRECTORY  # externen Gesamtkatalog pruefen
```

`src/audio/database.py` ist nur noch ein Kompatibilitäts-Shim
(`TARGET_DATABASE`, `SIGNATURES_BY_KEY`, `CIVILIAN_SIGNATURES`,
`signature_for_key`, `rank_signatures`); der Inhalt kommt aus dem Katalog.

`load_catalog(external_directory)` faellt bei Lese-/Validierungsfehlern auf den
vollstaendigen paketierten JSON-Katalog zurueck, nicht auf Python-Defaultwerte
oder einen reduzierten Legacy-Katalog. `quiet=True` unterdrueckt die Warnung.
Der paketierte Katalog hat `db_source == "contacts"`; externe Quellen verwenden
den Verzeichnisnamen. Fehler der Paketressourcen selbst werden nicht verdeckt.
Der CLI-Validator meldet externe Fehler mit Exitcode 1, ohne Fallback.

## Struktur

Jede Profildatei verwendet Version 1 oder 2. Version 1 besteht aus
`{"version": 1, "entries": [...]}`. Version 2 behaelt dieselben streng
validierten Runtime-Eintraege und ergaenzt normalisierte Register sowie
`profiles`-Verknuepfungen. Dadurch koennen einzelne Profile migriert werden,
ohne die bestehenden Runtime-Dataclasses oder v1-Eintraege umzudeuten. Nur
echte Integer-Versionen werden akzeptiert, nicht `true`, `1.0` oder `"1"`.
Runtime-Loader und CLI teilen `validate_contact_entry()` und die
Dokumentpruefung in `src/data/catalog.py`:
- exakte Objektfelder, erforderliche Werte und Typen; keine String-/Bool-Zahlkonvertierung
- keine doppelten JSON-Objektfelder, auch nicht in verschachtelten Akustik-Bloecken
- keine doppelten Profil-IDs innerhalb oder zwischen Dateien
- Library-Eintraege muessen `animal` und jedes Dekoy-Profil abdecken; die Dekoy-Aliase
  sind beabsichtigt, duerfen aber keine anderen Plattformen ueberschreiben
- alle Zahlen endlich, mit nichtnegativen bzw. positiven fachlichen Grenzen
- RPM-/Tonal-Baender strikt aufsteigend; `[0,0]` bedeutet explizit kein Band
- Kavitation/Breitband-Level im Bereich 0..1
- Breitband: `0 < low_hz < high_hz`
- Blattzahlen eindeutige Integer von 1 bis 20 (leere Liste erlaubt)
- Sub-Profile: `torpedoes` Integer von 0 bis 100
- mindestens 100 Akustik-Profile außerhalb `BIOLOGISCH`

Der R10-Batch-5-Paketstand verwendet Version 2 fuer alle acht Profildateien.
Alle 23
U-Boot-Eintraege, einschliesslich der drei generischen Szenarioarchetypen
`diesel_alt`, `aip_modern` und `ssn`, sowie alle 28 Kriegsschiffe besitzen
vollstaendige v2-Verknuepfungen. Das gilt nun auch fuer alle 55 zivilen Profile;
der bestehende `cargo_05`-Panamax-Datensatz bleibt ausdruecklich ein generischer
Archetyp.
Gemischte
externe v1/v2-Gesamtkataloge sind zulaessig. Sobald mindestens eine
Profildatei Version 2 verwendet, ist `sources.json` erforderlich. Der Loader
behaelt jede Dokumentversion und kann alle akzeptierten Felder einschliesslich
JSON-Zahltypen als abgetrennte Dokumentkopie rekonstruieren. Die unveraenderlichen
v2-Datentypen und schreibgeschuetzten Register umfassen:

- Referenzdaten mit Variante, Jahren, Rollen, Rumpftyp, Abmessungen,
  Verdraengungsbasis sowie getrennten Schiffs-/Luftgruppen-Crewbereichen,
- Maschinen mit Cruise-/Maximal-/Leisefahrt, getrennten Motor-/Wellen-RPM,
  Propulsortyp und Cruise-/Hochfahrt-Akustikzustaenden,
- Sensoren und Radar-Emitter mit kontrollierten Domains, Modi, Baendern,
  Kadenz und synthetischen Unsicherheiten,
- Waffen mit Ziel-Domains, optionaler Legacy-Runtimebruecke, Fahrleistung,
  Einsatzbereich, Sucher, Guidance und Payloadtyp,
- Waffen, Launcher, VLS-Zellzahl, Missionsmagazine und Gegenmassnahmen als
  getrennte Register mit vollstaendig validierten Querverweisen. Das optionale
  `runtime_profile_key` einer v2-Torpedowaffe darf nur auf ein vorhandenes
  Legacy-Torpedoprofil zeigen; andere Waffentypen besitzen keine solche Bruecke.

R5 aktiviert fuer die neun Pilotprofile Maschinenfahrt-/Akustikwerte,
Manovriergrenzen und die getrennten Radar-, ESM-, Sonar- und AIS-Controller. R8
aktiviert die ausdruecklich getesteten ASW-Waffen, Launcher, Magazine und
Gegenmassnahmen der Pilotprofile; R9 aktiviert die Flugkoerperabwehr. R10 Batch 1
ergaenzt alle uebrigen U-Boote. Ihre Maschinen-Maximalfahrt,
Torpedomunition und Spawnwerte entsprechen den unveraenderten Legacy-Eintraegen;
unbekannte Propulsoren behalten die etablierte fingerprintbasierte Akustik und
den abgeloesten Legacy-Beobachtungsgate. Die R8-Decoy-Komponente wird in R10 auf
die restliche Familie ausgerollt: Jedes migrierte Boot besitzt nun einen
endlichen, synthetischen Decoy-Bestand statt keiner kataloggebundenen
Gegenmassnahme. Dieser beabsichtigte Gameplayunterschied nutzt den gespeicherten
`rng_asw` und ist deterministisch getestet. R10 Batch 2 ergaenzt entsprechend die
22 noch nicht migrierten Kriegsschiffe. Ihre unbekannten Propulsoren behalten
ebenfalls Legacy-Akustik und -Beobachtung; die ASM-Komponenten spiegeln nur die
vorhandene Modellbewaffnung und aktivieren keine neue ASW-Faehigkeit. Die neuen
Sensorcontroller und Komponenten werden dennoch streng validiert und im
Save-v10-Snapshot gespeichert. R10 Batch 3 ergaenzt Radar, AIS und
Maschinenmetadaten fuer die 54 zuvor nicht migrierten zivilen Profile. Sie
besitzen keine Waffen-, Launcher-, Magazin- oder Gegenmassnahmenkomponenten.
Unbekannte Propulsoren und Abmessungen erhalten keine erfundenen Werte; dadurch
bleiben Legacy-Akustik, Bewegungsgrenzen, Spawnreihenfolge und RNG-Zugfolge
unveraendert. Radar/AIS erzeugen nur komponentenlokalen, stabil gehashten
Sensorzustand und aendern die zivile Transitdoktrin nicht.
R10 Batch 4 ergaenzt beide Flugzeugprofile mit Referenz-/Maschinenmetadaten und
getrennten Sensorcontrollern: die militaerische Patrouille besitzt Radar und ESM,
der zivile Transit Radar und AIS. Beide Radarprofile besitzen Emitter. Die
Komponenten verwenden nur stabile lokale Sensorhashes; die bestehende abgeloeste
ESM-Entscheidungsbruecke bleibt fuer die Patrouillensteuerung massgeblich. Beide
Profile bleiben unbewaffnet, und es entstehen weder eine Nimitz-Luftgruppe noch
neue Flugzeugoperationen.
R10 Batch 5 ergaenzt Referenz- und Maschinenkomponenten fuer Tiere, Torpedos und
Dekoys. Diese Komponenten spiegeln ausschliesslich bestehende Geschwindigkeiten,
Tonallinien und Breitbandwerte; `propulsor_type: "unknown"` haelt den bisherigen
Entry-/Bibliotheks-Akustikpfad ausdruecklich massgeblich. Tiere und Dekoys erhalten
keine Sensoren oder Waffen. Auch die Torpedoprofile erhalten keine zusaetzlichen
Sucher-, Waffen- oder Launcherfunktionen; vorhandene Plattformwaffen verweisen
weiterhin ueber `runtime_profile_key` auf die unveraenderten Torpedo-Entries.
`acoustics.json` ist ein v2-Bibliotheksdokument mit leeren Plattformregistern,
weil `animal` ein Klassifikations-Fangnetz und `decoy` ein beabsichtigter Alias
des Dekoyprofils ist, keine zwei weiteren Spawnprofile.

V2-Komponentenschluessel sind logische Kleinbuchstaben-IDs; Pfadtrenner und
Dateipfade sind ungueltig. Referenz-, Maschinen-, Sensor-, Emitter-, Waffen-,
Launcher-, Magazin- und Gegenmassnahmenschluessel verwenden jeweils ihren
kontrollierten Namespace. Der Loader begrenzt Dokumentgroesse, Eintragszahl und
JSON-Verschachtelung, oeffnet ausschliesslich die fest benannten Katalogdateien
und ruft keine Quellen-URLs ab. Nicht referenzierte Komponenten, falsche
Namespaces, unaufgeloeste Referenzen und inkompatible Launcher-/Waffentypen
werden abgewiesen.

## Quellenmanifest

`sources.json` enthaelt nur Quellenmetadaten und Zuordnungen von
Profil/Feldpfad zu `published`, `derived`, `game_assumption` oder `unknown`.
Profilwerte werden dort nicht dupliziert. R4 deckt alle Referenz-, Maschinen- und
groben Komponentenfelder seiner neun Pilotprofile ab. Der genaue
Rechte-, Status- und Pflegevertrag steht in
[`platform-data-sources.md`](platform-data-sources.md).

Defensive Obergrenzen (z.B. 2000 m Tiefe, 100000 Hz Frequenz, 256 Tonallinien,
500 Zeichen Text) begrenzen die akzeptierten Daten; sie sind keine Aussagen ueber
reale Plattformleistung. Das historische JSON-Feld `hostile` muss weiterhin zur
Ressourcendatei passen, waehlt aber nur den stabilen Legacy-Spawnpool. Die
Runtime-Seite kommt aus Mission und Doktrin; ein Plattformprofil ist neutral.
Der CLI-Validator prueft zusaetzlich jedes geladene Feld gegen das JSON. Korrektes
Laden allein beweist noch keine Simulationswirkung.

## Akustik-Block (U-Boote, Schiffe, optional Torpedos)

| Feld | Typ | Bedeutung |
|---|---|---|
| `label` | str | Anzeigename |
| `propulsion` | str | Antriebstyp; Sub-Katalog: `Diesel-elektrisch`, `elektrisch/AIP`, `elektrisch/Kernantrieb` |
| `blades` | [int] | mögliche Schrauben-Blätterzahlen (leer = keine DEMON-RPM-Ableitung, z.B. Torpedo) |
| `rpm_range` | [min,max] | Wellendrehzahl 1/min (Klassifikation; (0,0) = keine Angabe) |
| `tonal_band_hz` | [min,max] | Haupttonal-Band über die ganze Spannbreite (Hz) |
| `cavitation_tendency` | 0..1 | typische Kavitation (Ranking-Merkmal) |
| `category` | str | `U_BOOT`, `KAMPFSCHIFF`, `TANKER`, `PASSAGIER`, `FRACHT`, `SONSTIGES`, `FAHRZEUG`, `BIOLOGISCH` |
| `secondary_tonals` | [[hz,amp,width],…] | Getriebe-/Pumpen-Tonals (LOFAR, feste Frequenz) |
| `broadband` | [level,low_hz,high_hz] | Bandrauschen (level 0..1, Band in Hz); `null` = kein Breitenband-Beitrag |
| `signature_text` | str | Kurze Hörbeschreibung |

## `subs.json` (23 Profile)

| Feld | Typ |
|---|---|
| `key` | str (z.B. `ssn`, `sub_01`) |
| `name` | str |
| `speed_kn` | [min,max] |
| `max_depth_m` | float |
| `torpedoes` | int (Munitionsstand) |
| `quiet` | 0..1 (Leise; 0 = laut) |
| `aggression` | 0..1 |
| `spawn_weight` | float |
| `acoustic` | Akustik-Block |

## `warships.json` (28 Profile) / `civilians.json` (55 Profile)

| Feld | Typ |
|---|---|
| `key` | str |
| `name` | str |
| `category` | `KAMPFSCHIFF` / `TANKER` / `PASSAGIER` / `FRACHT` / `SONSTIGES` |
| `hostile` | bool |
| `speed_kn` | [min,max] |
| `callsigns` | [str] (AIS-Rufzeichen-Pool; feindlich: Name) |
| `esm_prob` | 0..1 (Wahrscheinlichkeit eines ESM-Emitters) |
| `asm_salvo` | [min,max] (Salvengröße; [0,0] = feuert nie, zivil) |
| `asm_cooldown_s` | float |
| `loiter_nm` | float (Loiter-Radius um Ankerpunkt; zivil 0.0) |
| `spawn_weight` | float |
| `acoustic` | Akustik-Block |

## `aircraft.json` (2 Profile)

`key`, `name`, `nation`, `kind` (`mil_patrol`/`civil_transit`-Typ:
`"military"`/`"civil"`), `speed_kn`, `esm` (bool), `esm_range_nm`,
`loiter_nm` [min,max], `spawn_weight`, `signature_text`.

Beide Eintraege besitzen vollstaendige v2-Verknuepfungen. Ihre synthetischen
Referenz-, Maschinen-, Radar-, ESM-/AIS- und Emitterwerte sind
`game_assumption`; nicht belegte Jahre, Abmessungen, Crew-, RPM- und nullable
Sensordetails sind `unknown`. Waffen-, Launcher-, Magazin- und
Gegenmassnahmenregister sind leer.

## `animals.json` (3 Profile)

`key`, `name`, `depth_min`, `depth_max`, `speed_kn`, `quiet`, `size_nm`,
`spawn_weight`, `lines` ([[hz,amp,width],…]), `signature_text`.

Alle drei Eintraege besitzen Referenz- und Maschinenverknuepfungen. Sensor-,
Emitter-, Waffen-, Launcher-, Magazin- und Gegenmassnahmenregister sind leer.

## `torpedoes.json` (3 Profile)

`key`, `name`, `used_by` (`frigate`/`helo`/`enemy`), `speed_kn`, `range_nm`,
`hit_dist_nm`, optional `acoustic` (paketiert nur bei `enemy_torp`, bei den anderen
Profilen weggelassen; im Kontakt-JSON ist explizites `null` nicht gueltig).
`enemy_torp` hat `blades: []` (keine DEMON-RPM-Ableitung) und ein Tonalfenster
90–150 Hz (Kreischen); die Subharmonische 45–75 Hz erzeugt die DEMON-
Blattfrequenz.

Alle drei Eintraege besitzen Referenz- und Maschinenverknuepfungen. Ihre
Runtimewerte und Auswahl ueber die festen Bindungen bleiben aus den Legacy-
Entries gespeist; das v2-Dokument fuegt keine neuen Sucher oder Launcher hinzu.

## `decoys.json` (1 Profil)

`key`, `name`, `life_s`, `speed_kn`, `cooldown_s`, `chance`, `lines`,
`signature_text`.

Das Profil besitzt Referenz- und Maschinenverknuepfungen, aber weder Sensoren
noch Waffen. Lebensdauer, Geschwindigkeit, Cooldown, Ablenkwahrscheinlichkeit,
Tonallinien und Bibliotheks-Breitband bleiben unveraendert runtimewirksam.

## Save-v10-Runtime-Snapshot

V10-Saves tragen zwingend eine streng validierte `catalog_snapshot`-Version 2. Sie
enthaelt die vollstaendigen runtimewirksamen `entries`, die validierten
v2-Komponentendokumente der acht Profilressourcen und feste Bindungen fuer
Fregatten-, Hubschrauber- und Feindtorpedo, U-Boot-Dekoy sowie
zivile/militaerische Standardfluege und deren v2-Komponenten. Quellen- und
Provenienzmetadaten werden nicht in den Save kopiert.

Beim Laden wird ein instanzlokaler Katalog aufgebaut. Wiederhergestellte und
spaeter in derselben Mission erzeugte U-Boote, Oberflaechenschiffe, Tiere,
Fluege, Torpedos und Dekoys verwenden diesen Snapshot; Sonarklassifikation nutzt
dieselbe gespeicherte Akustikbibliothek. Geaenderte Paketdefaults koennen eine
laufende Mission dadurch nicht umdeuten. Snapshotlose Saves, Snapshot v1 und
andere aeussere Saveversionen werden abgelehnt; es gibt keinen stillen Rueckfall
auf Paketwerte und keine Saveformatmigration.

R5 speichert zusaetzlich je U-Boot, Oberflaechenschiff und Flug die explizite
Seite/Doktrin, aktivierte Sensorcontroller, naechste Scanphase, Scanindex sowie
auf jeweils 64 Beobachtungen begrenzte lokale und Datalink-Bilder. Diese Bilder
enthalten weder Entity-IDs noch Profilkeys oder Objektverweise. Peilungen tragen
ihren Messursprung; der Friendly Datalink uebertraegt nur abgeloeste
Beobachtungen. Noch nicht migrierte Profilfamilien sowie R10-U-Boote und
-Kriegsschiffe mit nur synthetischen, unbekannten Propulsordetails und
R10-Flugzeuge mit bewusst beibehaltener Legacy-Doktrin verwenden einen
expliziten Adapter, dessen KI ebenfalls nur eine abgeloeste Beobachtung erhaelt.

## Modellannahmen

Alle akustischen Zahlen (RPM-Bänder, Tonal-Bänder, Kavitation, Breitband-
Bänder) sind **Spiel-Modellannahmen**, keine verifizierten Messdaten. Sie sind
so abgestimmt, dass:
- Diesel-/AIP-/Nuklear-Untertöne überblattzahlen-RPM-Kandidaten sinnvoll
  trennbar sind,
- Kampfschiffe (Gasturbinen, hohe Wellendrehzahl) nicht mit Diesel-Booten
  verwechselt werden (RPM-Untergrenze 200),
- Feindtorpedos über Subharmonische + Tonalfenster erkennbar sind.

Pro-Instanz-Variation (Blattzahl-Faktor, Tacho ±15 %, Ton-Offsets ±0.5 Hz,
Kavitations-/Breitband-Skalierung) kommt aus dem Fingerprint
(`src/data/fingerprint.py`, deterministisch aus `sensor_seed`) – die DB liefert
nur die Klassen-Referenzwerte.

## Kategorien (Klassifikation)

`CIVIL_CATEGORIES = ("TANKER", "PASSAGIER", "FRACHT", "SONSTIGES")` – diese
Profile zählen zu den zivilen Signaturen (`CIVILIAN_SIGNATURES`). `BIOLOGISCH`
ist ein Fangnetz-Profil (kein Spawn, nur Kandidaten-Liste). Der Katalog enthaelt
20 benannte U-Boote, 28 Kriegsschiffe und 55 zivile Schiffe plus 3
Legacy-U-Boot-Archetypen. Die neuen `warship_26` bis `warship_28` besitzen
`spawn_weight: 0`; die feindliche Legacy-Zufallsauswahl bleibt explizit auf
`warship_01` bis `warship_25` begrenzt. Tiere und Dekoys zählen nicht dazu.

## Runtime-Grenzen und Metadaten

Die Zahlen sind illustrative Spielprofile, keine verifizierten technischen Daten
der benannten Klassen. Akzeptanz, Bibliothekswirkung und Simulationswirkung sind
unterschiedliche Vertraege:

| Felder / Bereich | Nachgewiesene Verwendung und Grenzen |
|---|---|
| Sub-/Schiffs-Bewegung, Tiefe, Waffen, Verhalten | Die Runtime liest Profilwerte, kombiniert sie aber mit KI-, Szenario- und Schwierigkeitsregeln. `speed_kn` ist kein vollstaendiges reales Fahrleistungsmodell. |
| `spawn_weight` | Wird von den gewichteten `ContactCatalog.pick_*`-Hilfen verwendet. Explizite Profilwahl und Szenario-Pools muessen diese Hilfen nicht verwenden. Insbesondere waehlt `Flight` normalerweise feste Standard-IDs; die gewichtete Flugzeugwahl ist ein Fallback. |
| `rpm_range` | Klassifikationsreferenz in `rank_signatures()`, keine Vorgabe der simulierten Wellendrehzahl. |
| `blades`, `cavitation_tendency`, `broadband` | Eingang fuer deterministische Instanz-Fingerprints; Kavitation und Blattzahlen auch Klassifikationsmerkmale. Die Hoer-/Sensorwirkung haengt vom jeweiligen Runtime-Verbraucher ab. |
| `tonal_band_hz`, `secondary_tonals` | Klassifikation bzw. plattformspezifische LOFAR-Synthese. Nicht jeder Signaturtyp verarbeitet jedes Feld gleich. |
| `label`, `signature_text` | Beschreibende Bibliotheks-/Diagnosetexte, keine physikalischen Parameter. `AircraftProfile.signature_text` hat derzeit keinen Simulationsverbraucher. |
| `propulsion` | Ausserhalb der Sub-Capability-Metadaten beschreibender Text, kein allgemeines Antriebsmodell. |
| `endurances` | Nur in `subs.json`: streng typisierte fiktive Batterie-/AIP-Komponenten. Der Schluessel ist exakt `endurance.<profile_key>`; jedes nichtnukleare v2-U-Boot braucht genau eine, nukleare Profile duerfen keine besitzen. |
| `AircraftProfile.nation` | Katalog-/Editor-Metadatum. `Flight.nation` kommt von der Startbasis, nicht aus diesem Feld. |
| `AnimalProfile.size_nm` | Wird in `AnimalType` uebernommen, derzeit aber nicht als Sonar-Ausdehnung oder Trefferhuelle ausgewertet. |
| `TorpedoProfile.used_by` | Validiertes Zuordnungsmetadatum; Waffen werden ueber explizite Profil-IDs ausgewaehlt, nicht automatisch anhand dieses Feldes. |
| `acoustics.json` | Zusaetzliche Bibliothekssignaturen: `animal` ist ein Klassifikations-Fangnetz, kein Tier-Spawnprofil. `decoy` liefert auch Breitbanddaten fuer die Dekoy-Runtime; die Dekoy-Tonallinien kommen aus `decoys.json`. Als v2-Bibliotheksdokument besitzt die Datei bewusst keine Plattformkomponenten. |

`SubProfile.is_nuclear` und `SubProfile.requires_air` sind abgeleitete, nicht
serialisierte Properties. Sie verwenden den vorhandenen JSON-Wert
`acoustic.propulsion`, nicht den Legacy-Schluessel `ssn`: Kernantrieb ergibt
`True`/`False`, Diesel und AIP `False`/`True`. Das API erlaubt der Einheiten-Runtime,
Luftbedarf konsistent fuer benannte Profile zu behandeln. Die zugeordnete
`EnduranceProfile`-Komponente definiert `battery_capacity_kwh`, `hotel_load_kw`,
`propulsion_max_kw` mit `propulsion_exponent`, `generator_power_kw`, die gemeinsam
optionalen `aip_power_kw`/`aip_energy_kwh`, geordnete
`reserve_start_fraction`/`reserve_stop_fraction`, `snorkel_depth_m` und
`radio_duration_s`. Alle Zahlen sind endlich, positiv und defensiv begrenzt;
Startreserve muss echt unter Stopreserve liegen, AIP-Felder sind gemeinsam Zahl
oder `null`, und Generatorleistung muss die Hotellast uebersteigen. Diese Werte
sind ausschliesslich fiktive Spielannahmen. Die Properties selbst werden nicht
als neue JSON-Felder akzeptiert.

## Unit Editor

User-Profile in `~/.u-jagd/units/` sind ausschliesslich Editor-Daten. Erfolgreiche
Validierung, Klonen, Speichern und Bundle-Import aktivieren sie nicht in der
Simulation. `unit_field_metadata(kind)` markiert weiterhin alle Felder als
`supported=True`, `effective=False`; die Mission-Runtime lehnt User-Profile ab.

Die Editor-Version 1 verwendet eigene Identitaetsfelder (`version`, `key`,
`profile_kind`) und bei Flugzeugen `aircraft_kind` statt `kind`. Unbekannte
Top-Level- und Akustik-Felder werden abgelehnt, nicht stillschweigend gespeichert.
Der optionale verschachtelte `acoustic.key` bleibt fuer bereits ausgelieferte
Built-in-Klone erlaubt und erhalten; er ist beschreibende Quellidentitaet und
keine Runtime-Verknuepfung. Leere Beschreibungstexte, optionale Beschreibungen,
stationaere Bereiche und `acoustic: null` bei Editor-Torpedos bleiben erlaubt.
Der Editor ist deshalb nicht einfach der paketierte Kontakt-JSON-Vertrag.
