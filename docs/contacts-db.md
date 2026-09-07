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

Jede Datei: `{"version": 1, "entries": [...]}` (Version für spätere
Migrationen). Nur die Integer-Version 1 wird akzeptiert, nicht `true`, `1.0`
oder `"1"`. Runtime-Loader und CLI teilen `validate_contact_entry()` und die
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

Defensive Obergrenzen (z.B. 2000 m Tiefe, 100000 Hz Frequenz, 256 Tonallinien,
500 Zeichen Text) begrenzen die akzeptierten Daten; sie sind keine Aussagen ueber
reale Plattformleistung. Oberflaechen-Hostilitaet und Akustik-Kategorie muessen zur
Datei bzw. Plattform passen. Der CLI-Validator prueft zusaetzlich jedes geladene
Feld gegen das JSON. Korrektes Laden allein beweist noch keine Simulationswirkung.

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

## `warships.json` (25 Profile) / `civilians.json` (55 Profile)

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

## `animals.json` (3 Profile)

`key`, `name`, `depth_min`, `depth_max`, `speed_kn`, `quiet`, `size_nm`,
`spawn_weight`, `lines` ([[hz,amp,width],…]), `signature_text`.

## `torpedoes.json` (3 Profile)

`key`, `name`, `used_by` (`frigate`/`helo`/`enemy`), `speed_kn`, `range_nm`,
`hit_dist_nm`, optional `acoustic` (paketiert nur bei `enemy_torp`, bei den anderen
Profilen weggelassen; im Kontakt-JSON ist explizites `null` nicht gueltig).
`enemy_torp` hat `blades: []` (keine DEMON-RPM-Ableitung) und ein Tonalfenster
90–150 Hz (Kreischen); die Subharmonische 45–75 Hz erzeugt die DEMON-
Blattfrequenz.

## `decoys.json` (1 Profil)

`key`, `name`, `life_s`, `speed_kn`, `cooldown_s`, `chance`, `lines`,
`signature_text`.

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
ist ein Fangnetz-Profil (kein Spawn, nur Kandidaten-Liste). Die 100
Kernplattformen (20 U-Boote + 25 Kriegsschiffe + 55 Zivile) plus 3
Legacy-Archetypen bilden den Spawn-Pool; Tiere und Dekoys zählen nicht dazu.

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
| `AircraftProfile.nation` | Katalog-/Editor-Metadatum. `Flight.nation` kommt von der Startbasis, nicht aus diesem Feld. |
| `AnimalProfile.size_nm` | Wird in `AnimalType` uebernommen, derzeit aber nicht als Sonar-Ausdehnung oder Trefferhuelle ausgewertet. |
| `TorpedoProfile.used_by` | Validiertes Zuordnungsmetadatum; Waffen werden ueber explizite Profil-IDs ausgewaehlt, nicht automatisch anhand dieses Feldes. |
| `acoustics.json` | Zusaetzliche Bibliothekssignaturen: `animal` ist ein Klassifikations-Fangnetz, kein Tier-Spawnprofil. `decoy` liefert auch Breitbanddaten fuer die Dekoy-Runtime; die Dekoy-Tonallinien kommen aus `decoys.json`. |

`SubProfile.is_nuclear` und `SubProfile.requires_air` sind abgeleitete, nicht
serialisierte Properties. Sie verwenden den vorhandenen JSON-Wert
`acoustic.propulsion`, nicht den Legacy-Schluessel `ssn`: Kernantrieb ergibt
`True`/`False`, Diesel und AIP `False`/`True`. Das API erlaubt der Einheiten-Runtime,
Luftbedarf konsistent fuer benannte Profile zu behandeln. Es definiert weder
Batterie-/AIP-Ausdauer noch Schnorchelintervalle; solche Regeln bleiben Aufgabe
der Runtime und ihrer Determinismus-/Save-Tests. Die Properties werden nicht als
neue JSON-Felder akzeptiert.

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
