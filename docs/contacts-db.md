# Kontakt-DB: `data/contacts/*.json`

Die Kontakt-Datenbank ist die einzige Quelle (SSoT) für alle Plattformprofile
des Spiels. Sie liegt als JSON im Repository und wird zur Laufzeit von
`src.data.catalog` geladen; `tools/gen_contacts.py` erzeugt sie aus dem
eingebauten Default-Katalog und prüft Abweichungen mit `--check`.

```sh
python tools/gen_contacts.py            # JSON neu erzeugen
python tools/gen_contacts.py --check    # Abweichungen melden (0 = identisch)
```

`src/audio/database.py` ist nur noch ein Kompatibilitäts-Shim
(`TARGET_DATABASE`, `SIGNATURES_BY_KEY`, `CIVILIAN_SIGNATURES`,
`signature_for_key`, `rank_signatures`); der Inhalt kommt aus dem Katalog.

Bei Lese-/Validierungsfehlern fällt der Katalog auf den eingebauten
Default zurück (die alten 3 U-Boot-Archetypen + Zivilfamilien); `db_source`
zeigt dann `"eingebauter Default"` statt `"data/contacts"`.

## Struktur

Jede Datei: `{"version": 1, "entries": [...]}` (Version für spätere
Migrationen). `load_catalog` validiert alle Einträge (`_validate`):
- keine Duplikate von `key`
- rpm/tonal-Bänder nicht invertiert (falls positiv)
- Kavitation/Breitband-Level im Bereich 0..1
- Breitband: `0 < low_hz < high_hz`
- Sub-Profile: `torpedoes >= 0`
- mindestens 100 Akustik-Profile außerhalb `BIOLOGISCH`

## Akustik-Block (alle Plattformen)

| Feld | Typ | Bedeutung |
|---|---|---|
| `label` | str | Anzeigename |
| `propulsion` | str | Antriebstyp (Text) |
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
`hit_dist_nm`, `acoustic` (nur `enemy_torp`, sonst `null`).
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
