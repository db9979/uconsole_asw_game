# Entwicklungsplan 0.1.7

## Arbeitsstand

Diese Checkliste ist der persistente Wiederaufnahmepunkt. Ein Paket wird erst
abgehakt, wenn Implementierung, fokussierte Abnahme, Vollsuite und Handoff
abgeschlossen sind. Physische Abnahmen bleiben offen, bis sie tatsaechlich auf
der Zielhardware erfolgt sind.

- [x] R0-R8: Baseline, Commander, Katalogpilot, Sensorik, ELOKA, ASW und Save v10.
- [x] R9 Flugkoerperabwehr.
  - [x] Profilbasierter Runtime-/Save-/Testpatch erstellt.
  - [x] Unabhaengige Code- und Observation-Boundary-Pruefung.
  - [x] Fokussierte und vollstaendige Softwareabnahme.
  - [x] Handoff und Verifikationsledger aktualisiert.
- [x] R10 Gesamtkatalogmigration.
  - [x] U-Boote und generische Szenarioarchetypen.
  - [x] Kriegsschiffe und Hilfsschiffe.
  - [x] Zivile Schiffe.
  - [x] Flugzeuge.
  - [x] Tiere, Torpedos, Decoys und Akustikbibliothek.
  - [x] Gesamtprovenienz, Runtimeparitaet und Save-/Determinismusabnahme.
- [x] R11 Kontakt-DB und Tactical Unit Analyzer.
  - [x] Reine begrenzte Katalogprojektion fuer Spiel und Commander.
  - [x] Deterministische Bildgenerierung und Hashmanifest.
  - [x] Feste sichere Serverrouten und paketierte Ressourcen.
  - [x] EN/DE-, Browser-, Traversal- und Reproduzierbarkeitsabnahme.
- [x] R12 vollstaendige Commander-Webanleitung.
  - [x] Inhalte und EN/DE-Katalogparitaet.
  - [x] Sichere DOM-Einsetzung, Navigation und Layoutabnahme.
- [x] R13 Integrationscheckpoint.
  - [x] Vollsuite, Katalog-, Bild-, Smoke- und Buildpruefung.
  - [x] Isolierte Artefaktinstallation und Save-v10-Abnahme.
  - [x] Browser-/Loopbackmatrix und Quellen-/Lizenzscan.
  - [x] Physische uConsole-/Zwei-Geraete-Abnahme oder als offen dokumentiert.
- [x] R14 Sonarhoerbild und Fixpublikation.
  - [x] Audiozustand, A/B, Heterodyn und Filteruebergaenge.
  - [x] Ping-/TMA-/Sonobuoyfixe auf Bruecke und Commander.
  - [x] Softwareabnahme; physische Audioabnahme offen dokumentiert.
- [x] R15 Sonarlayout, Kontrast, Maus und Stationsabnahme.
  - [x] Sechs verdichtete Sonarseiten und gemeinsame Draw-/Hit-Geometrie.
  - [x] EN/DE-, Grossschrift-, Pseudolocale- und Letterboxmatrix.
  - [x] Physischer 1280x720-Kontrast-/Trackballtest offen dokumentiert.
- [x] R16 Batterie-/AIP-Endurance.
  - [x] Strikter fiktiver Katalog- und Runtimezustand.
  - [x] Energie-, Schnorchel-, Funk- und Save-Fortsetzungsabnahme.
- [x] R17 erweiterte synthetische Schallausbreitung.
  - [x] Begrenzte gemeinsame Propagations-/BT-API.
  - [x] Pfad-, Terrain- und Determinismusabnahme; physische Performance offen.
- [x] R18 Grundberuehrung und lokalisierte Schaeden.
  - [x] Swept-Kontakt, Aufprall-Latch, Bergung und Schadensverteilung.
  - [x] Save-, Substep- und Akustik-/Physiktrennungsabnahme.
- [x] R19 Gesamtabnahme und Pause.
  - [x] R13-Softwarematrix nach B-F wiederholt.
  - [x] Hardware-/Performancegrenzen abgenommen oder ehrlich dokumentiert.
  - [x] Finaler Handoff erstellt und verpflichtender Pausenpunkt erreicht.

## Ziel und Freigabe

0.1.7 erweitert den ausgelieferten Commander-Meilenstein um eine Crew-MessageBox
fuer die vorhandene lokale Vorschlagsannahme, eine tabbasierte Webkonsole, eine
neunte Eloka-Station und
einen neutralen, quellengestuetzten Plattformbaukasten bis zum ASW-Kern und zur
modellierten Flugkoerperabwehr.

Freigegeben sind die bisherigen Pakete G, I, J, K und L, die fuer die
gewuenschte Runtimewirkung notwendigen Plattform-, Sensor-, ASW- und
Luftabwehrgrundlagen sowie die Sonar-/Fidelity-Pakete B-F. Nach deren
Gesamtabnahme folgt ein verpflichtender dokumentierter Pausenpunkt.

## Festgelegte Produktentscheidungen

- 0.1.6 wird zuerst stabilisiert; diese Funktionen erscheinen als 0.1.7.
- Reale Klassennamen und unabhaengig belegte oeffentliche Referenzdaten sind
  erlaubt. Akustik, Radarleistung und andere nicht belastbare Werte sind klar
  gekennzeichnete synthetische Spielparameter.
- Die neun vorgegebenen Plattformen bilden einen Pilot, danach werden alle
  Profile familienweise migriert.
- Plattform und Szenarioseite sind getrennt. Mission/Doktrin bestimmen
  freundlich, neutral oder feindlich.
- 0.1.7 schreibt und laedt ausschliesslich Save v10. Andere Versionen und
  unvollstaendige Schemas werden ohne Migration abgelehnt.
- Einsatzmagazine sind dokumentierte fiktive ASW-Beladungen, keine Aussagen
  ueber aktuelle reale Bestaende.
- Eloka ist an OPZ-Schaden gekoppelt und erhaelt kein neues Schadensabteil.
- Nimitz und Type 901 erhalten Bewegung, Sensorik, Akustik und Selbstschutz.
  Vollstaendiger Traegerbetrieb und Nachversorgung folgen erst in Tier 4.
- Runtimeumfang ist Tier 1 bis 3: plattformspezifische Sensorik, ASW-Kern sowie
  ASM/SAM/VLS/CIWS und Softkill. LACM, allgemeiner Geschuetzkrieg,
  Traegerfluegel, Nachversorgung und Verbandsoperationen bleiben ausserhalb.

## Quellen- und Rechtegrenze

Private WaveOps-/MNW-Unterlagen sind keine Quelle fuer Repositorydaten oder
Assets. Sie werden nicht zitiert, transkribiert, imitiert oder fuer abgeleitete
Diagramme verwendet. Oeffentliche Erreichbarkeit ist keine Lizenz.

Jeder uebernommene oeffentliche Fakt benoetigt Quelle, Herausgeber, URL,
Bezugsstand und Abrufdatum. Werte werden als `published`, `derived`,
`game_assumption` oder `unknown` markiert. Moderne LOFAR-Linien, genaue
Wellen-/Propellerdaten, Kavitation, Radarleistung, PRF und Modulation gelten ohne
belastbare offene Quelle als synthetische Spielwerte.

Alle Bilder werden deterministisch aus eigenen Datenmodellen erzeugt. Keine
Fotos, Herstellerzeichnungen, Logos, Schiffsrisse oder nachgezeichneten
Drittgrafiken werden gebuendelt.

## Architekturvertraege

- `data/contacts/*.json` und neue normalisierte Katalogressourcen bleiben SSoT;
  Python dupliziert keine JSON-eigenen Werte.
- Plattformprofil, Seite, Doktrin, Sensor, Launcher, Magazin, Waffe und
  Gegenmassnahme sind getrennte typisierte Begriffe. Freitext wird nie geparst,
  um Runtimefaehigkeiten abzuleiten.
- Sensorproduktion und KI duerfen interne Entitaeten sehen. UI, Zielwahl,
  Waffenfreigabe und Vor-Endphasenguidance verwenden Beobachtungen oder
  ausdruecklich modellierten Datalink.
- Radar, ESM, AIS und Sonar sind getrennte Messungen. Ein Track kann mehrere
  Beobachtungen korrelieren, ohne Objektverweise oder versteckte Profil-IDs zu
  publizieren.
- Neue Zufallsprozesse verwenden dedizierte, gespeicherte RNG-Streams, stabile
  Sortierung und feste Updatephasen. Rendering, Browserpolling, Audio und Wall
  Clock beeinflussen die Simulation nicht.
- Alle Sammlungen fuer Tracks, Sensorereignisse, Projektile, Magazine,
  Luftfahrzeuge, Bilder und HTTP-Routen sind begrenzt.

## Pilotmanifest

Bestehende Keys bleiben stabil:

| Plattform | Stabiler Key | Behandlung |
|---|---|---|
| Arleigh Burke Flight IIA | `warship_01` | vorhandenes Profil praezisieren |
| Ticonderoga Baseline 2 | `warship_02` | vorhandenes Profil praezisieren |
| Type 055 | `warship_25` | vorhandenes Profil praezisieren |
| Virginia Block III | `sub_03` | vorhandenes Profil praezisieren |
| Yasen-M | `sub_14` | vorhandenes Profil praezisieren |
| Panamax Container Ship | `cargo_05` | vorhandenes Profil praezisieren |
| Type 052D | `warship_26` | am Ende anfuegen |
| Type 901 | `warship_27` | am Ende anfuegen |
| Nimitz | `warship_28` | am Ende anfuegen |

Der erwartete Katalog steigt damit von 112 auf 115 Runtimeprofile und, sofern
alle drei neuen Oberflaechenprofile einen Akustikblock besitzen, von 106 auf 109
Akustikprofile. Vor der ersten Datenmigration wird diese Liste als Testmanifest
fixiert. Neue Keys veraendern Legacy-Seedpools nicht; neue Szenarien muessen sie
explizit oder ueber einen versionierten erweiterten Pool anfordern.

## Datenmodell v2

### Referenzdaten

- Masse in SI-Einheiten mit klarer Basis, insbesondere
  `displacement_tonnes` plus `displacement_basis`.
- Laenge, Wasserlinienbreite, optionale Gesamt-/Flugdeckbreite und Tiefgang.
- Crew als Bereich; Schiffsbesatzung und Luftgruppe bleiben getrennt.
- Kontrollierte Rollen-/Rumpftyp-Codes werden in EN/DE lokalisiert.
- Varianten-/Refit-Bezugsjahr und neutrale Aliasnamen.

### Maschinen und Akustik

- Cruise-, Maximal- und gegebenenfalls Leisefahrt sind semantisch getrennt.
- Motor-RPM und Wellen-RPM werden nie gleichgesetzt.
- `propulsor_type` unterscheidet Schraube und Pumpjet; unbekannte Blattzahl ist
  `null`, nicht 0.
- LOFAR-Zustaende enthalten Frequenz, relativen Pegel und Linienbreite fuer
  Cruise und hohe Fahrt. Interpolation verwendet nur simulierte interne Fahrt
  bei Sensorproduktion beziehungsweise beobachtete frische Fahrt beim Ranking.
- Bestehende Fingerprint-Ziehungen bleiben als Praefix stabil. Erweiterungen
  folgen danach oder verwenden einen getrennten lokalen Seed.

### Sensor-, Launcher- und Waffenregister

- Sensoren referenzieren stabile Keys, Domain, Aktiv/Passiv-Modus, Emission,
  synthetische Reichweite/Empfindlichkeit, Kadenz und Unsicherheiten.
- Radar-Emitter besitzen typisierte Frequenz-/PRF-Baender und kontrollierte
  Modulationscodes. Plattformen referenzieren Emitterkeys.
- Launcher besitzen Anzahl, Bereitschaft, Nachladezeit, Winkel und kompatible
  Waffenkeys. VLS-Zellzahl und Einsatzmagazin sind getrennt.
- Magazine speichern Waffenkey und Missionsanzahl. Gegenmassnahmen besitzen
  Bestand, Bereitschaft und Wirkungstyp.
- Beschreibende Waffen-/Sensorprosa darf zusaetzlich angezeigt werden, hat aber
  keine implizite Runtimewirkung.

### Provenienz

`docs/platform-data-sources.md` fuehrt Quellen und Feldgruppen. Ein streng
validiertes Manifest verbindet Profil/Feldpfad mit Quellen-ID und Status, ohne
die eigentlichen Profilwerte zu duplizieren.

## Optimierte Umsetzungsreihenfolge

### R0 Baseline und Save-v10-Vertrag

Voraussetzung: 0.1.6 ist automatisiert gruen und seine offenen Hardwaretests sind
ehrlich dokumentiert.

- Version auf 0.1.7 erhoehen; ausschliesslich Save v10 schreiben und laden.
- V10-Schema fuer Komponenten, Magazine, Launcher, Sensorzustand, lokale Tracks,
  Countermeasures, Projektile und neue RNG-Streams definieren.
- V1-v9 sowie zukuenftige Versionen werden ohne Migration abgelehnt.
- V10 speichert ausreichend Profilrevision/-snapshot, damit spaetere
  Katalogaenderungen laufende Saves nicht unkontrolliert umdeuten.
- Kandidatenload bleibt atomar; Fehler veraendern weder Livewelt noch ID-Zaehler.

Abnahme: v1-v9-/malformed-/future rejection, v10 Roundtrip,
unterbrechungsfreie versus gespeicherte Fortsetzung und unveraenderte IDs/RNGs
nach fehlgeschlagenem Load.

### R1 Crew-MessageBox (G)

- Feste, nicht pausierende Box fuer Ziel- und Navigationsvorschlaege.
- Ziel steht in der Anzeige vor Navigation. `F8` wechselt bei zwei wartenden
  Vorschlaegen, `F6` nimmt an, `F7` lehnt ab.
- Esc blendet nur die aktuelle Proposal-Sequenz aus. Der Vorschlag bleibt in F9
  erreichbar und eine neue Sequenz oeffnet die Box erneut.
- Leaseverlust, Widerruf, Disconnect oder Weltwechsel schliesst/verwirft die Box.
- Key-Repeat, Alt+Enter, numerische Eingabe, Administration, gepinnter Tooltip,
  Letterbox und Select-then-confirm-Mausvertrag erhalten klare Praezedenz.
- Kein Proposal-/Boxzustand wird gespeichert.

Abnahme: Ziel/Navigation einzeln und gemeinsam, alle Statusuebergaenge,
Stations-Key-Leaks, laufende Simulation, EN/DE/Pseudolocale und beide Textgroessen.

### R2 Feste Webshell (K1)

- Tabs `Operations`, `Lookout`, `Guide`, `Contacts` mit ARIA-Tabvertrag.
- Das gekoppelte UI nutzt exakt den Viewport; nur Panelinhalte scrollen.
- Kein Clipping durch pauschales `body { overflow: hidden }`.
- Tabwechsel veraendert weder Browserauswahl noch Entwuerfe und sendet keinen
  Befehl.

Abnahme: `scrollHeight <= innerHeight + 1`, keine horizontale Ueberbreite oder
Ueberlagerung bei 390 bis 3840 CSS-Pixeln, EN/DE, 200 Prozent, 120 Kontakte,
neun Schaeden und 80 Ereignisse.

### R3 Katalog-v2-Grundlage und Provenienz (L0)

- Loader/Validator akzeptieren gemischte v1-/v2-Dokumente, behalten die
  Dokumentversion und rekonstruieren jedes Feld verlustfrei.
- Neue unveraenderliche Referenz-, Maschinen-, Sensor-, Emitter-, Launcher-,
  Magazin- und Countermeasure-Datentypen.
- Strikte Typen, endliche Grenzen, eindeutige Keys, begrenzte Arrays/Texte und
  vollstaendige Querverweise.
- Quellenmanifest und `docs/platform-data-sources.md` einfuehren.
- Noch keine breite Runtime- oder Datenumstellung.

Abnahme: v1 bitgleich geladen, v2 strikt, unbekannte Felder/Booleans/NaN
abgewiesen, Runtime-JSON-Paritaet, keine Dateipfade in logischen Profilfeldern.

### R4 Neun-Plattform-Pilot (L1)

- Sechs bestehende Profile migrieren, drei neue Keys anfuegen.
- Gepostete Werte nur als Intake verwenden; jeden oeffentlichen Fakt unabhaengig
  belegen, mehrdeutige Werte normalisieren und technische Detailwerte als
  synthetisch markieren.
- LOFAR-Frequenzlisten um modellierte Pegel/Breiten ergaenzen; keine Behauptung
  gemessener Spektren.
- Type 901 und Nimitz sind in diesem Paket Plattformen ohne Nachversorgungs- oder
  Traegerfluegel-Runtime.
- Fiktive Einsatzbeladungen getrennt von maximaler Zellen-/Launcherzahl.

Abnahme: Manifest und erwartete Counts, stabile Altkeys, keine Legacy-Poolaenderung,
Quellenabdeckung, Katalogcheck und expliziter Gameplaydiff.

### R5 Plattform- und Sensorgrundlage (Tier 1)

- Seite/Hostilitaet aus Profilen loesen und in Mission/Doktrin legen.
- Profilbezogene Bewegung, Manovriergrenzen, Akustik und grobe Komponenten.
- Eigene Radar-, ESM-, Sonar- und AIS-Controller mit begrenzten lokalen Bildern.
- Expliziter Friendly Datalink transportiert Beobachtungen, keine Entity-Truth.
- EMCON und bestehende Schadenszustaende beeinflussen Sensoren.
- KI-Ziel- und Waffenfreigabe verwendet eigene oder Datalink-Beobachtungen.

Abnahme: dieselbe Klasse auf verschiedenen Seiten, Sensoren unabhaengig,
beobachtungsbasierte KI, stabile Sensorphasen, begrenzte Bilder, v10-Fortsetzung.

### R6 Bridge Lookout (I)

- Eigene Topdown-Ansicht auf Basis des Commander-Snapshots.
- Eigenes Schiff, Kursvektor, Ringe, Seeklasse und Tag/Nacht.
- Positionierte Beobachtungen als Punkte, reine Peilungen als Randindikatoren.
- Eigener Browserzoom/-bereich; keine Sichtweiten- oder Identitaetsbehauptung.
- Redaktierte Phasen publizieren keine Umweltdaten.

Abnahme: nur Snapshotdaten, keine neue Mutation, korrektes Canvas-Resize und
Ein-Bildschirm-Vertrag in allen Browsermatrizen.

### R7 Eloka/ESM (J)

- Separate begrenzte `esm_picture` mit Peilung, Unsicherheit, beobachteter
  Frequenz/PRF/Modulation, Qualitaet und Alter.
- Kandidatenranking verwendet nur diese Messwerte und stabile Emitterkeys.
- Korrelation mit Radar/Sonar beruht auf Zeit-/Peil-/Positionskompatibilitaet,
  nie auf versteckter Entity-ID.
- `Station.ELOKA` wird am Enum-Ende angefuegt; Taste 9 und Tab-Zyklus umfassen
  neun Stationen.
- Manuelle Radartypzuordnung ist Operatorannotation. OPZ-Schaden deaktiviert
  Eloka; kein zehntes Abteil.
- Save v10 speichert Bild, Auswahl und Annotationen als Pflichtzustand.

Abnahme: Radar aus/ESM an, parallele Radar-/ESM-Evidenz, Hidden-ID-Negativtests,
EN/DE, Eingabeownership und Savewert `"ELOKA"` statt Stationsindex.

### R8 ASW-Kern (Tier 2)

- Torpedorohre, Bereitschaft, Nachladen und typisierte Magazine.
- Unterschiedliche Torpedoprofile mit beobachtungsbasiertem Datum und erst
  terminaler Wahrheitssuche.
- ASROC-Flug zum beobachteten Datum mit anschliessendem Wassereintritt.
- Begrenzte ASW-Luftfahrzeuge, Nutzlast, Treibstoff, Sonobuoys und Torpedos;
  Nimitz-Vollfluegel bleibt ausgenommen.
- Akustische Decoys und Nixie-artige Gegenmassnahmen als modellierte
  Sucherkandidaten.
- Beobachtungsbasierte ASW-KI und gespeicherte dedizierte RNG-Streams.

Abnahme: Inventar-/Reloadgrenzen, keine versteckte Vor-Endphasenguidance,
Gegenmassnahmen, deterministische Salven und v10-Roundtrip waehrend jeder Phase.

### R9 Flugkoerperabwehr (Tier 3)

- Profilbezogene ASM-, SAM-, VLS-, CIWS- und Softkill-Komponenten.
- VLS-Kapazitaet, Einsatzbeladung und Feuerkanaele sind getrennt.
- SAM/CIWS benoetigen frische lokale oder Datalink-Beobachtung.
- Chaff/Softkill besitzen endlichen Bestand und Bereitschaft.
- Bestehende ASM-Abstraktion wird auf profilbezogene Waffen und
  beobachtungsbasierte Freigabe migriert.
- Geschuetze/LACM, Landziele, Nachversorgung und allgemeine Verbandslogik sind
  ausdruecklich nicht Teil dieses Pakets.

Abnahme: Magazin-/Kanalgrenzen, Beobachtungsalter, Soft-/Hardkill-Reihenfolge,
kein Renderer-/Wall-Time-Einfluss, gespeicherte Flugkoerper und Fortsetzung.

### R10 Gesamtkatalogmigration (L2)

Nach stabilem Pilot und Runtimevertrag folgen getrennte Batches:

1. U-Boote und drei generische Szenarioarchetypen.
2. Kriegsschiffe/Hilfsschiffe.
3. Zivile Schiffe.
4. Flugzeuge.
5. Tiere, Torpedos, Decoy und Akustikbibliothek.

Jeder Batch behaelt vorhandene Keys/Reihenfolge, fuehrt Quellenstatus und
Gameplaydiff auf und durchlaeuft Katalog-, Fingerprint-, Save-, Determinismus-
und Beobachtungsgrenztests. Generische Archetypen bleiben als solche benannt;
reale Namen machen synthetische Leistungswerte nicht zu Fakten.

### R11 Kontakt-DB und generierte Bilder (K3)

- Reine, begrenzte Katalogprojektion in einem Game-/Pygame-freien Modul.
- Server erhaelt vorgebaute Bytes und feste allowlist-basierte JSON-/Bildrouten;
  keine Pfadinterpretation aus Requests oder Profilen.
- Superseded by the analyzer follow-up: the earlier R11 silhouette sentence is
  no longer active. No silhouette assets or routes exist. Acoustic profiles
  receive deterministic Cruise/High diagrams only; inapplicable data is not
  invented.
- Generator ist fontfrei/reproduzierbar, schreibt feste PNGs plus Hashmanifest
  und besitzt einen strikt lesenden `--check`-Modus.
- Wheel/sdist enthalten exakt Manifest und allowlistete Assets.

Abnahme: zwei bytegleiche Generatorlaeufe, Hash-/Routenparitaet,
Traversal-Negativtests, keine Liveentitaeten, keine Drittbilder, EN/DE und
interner Contacts-Panel-Scroll.

### R12 Vollstaendige Webanleitung (K2)

Die Anleitung kommt bewusst zuletzt und beschreibt ausschliesslich vorhandenes
Verhalten: Kopplung, Grant/Widerruf, Operations, Lookout, Beobachtungsalter,
Klassifizierung/Zugehoerigkeit, Ziel-/Navigation/MessageBox, Eloka, EMCON,
Contacts, Sicherheit, Reconnect und verbotene Fernaktionen.

Texte kommen aus den Root-EN/DE-Katalogen, werden mit `textContent` eingesetzt
und besitzen exakte Paritaet. Interne Navigation scrollt nur das Guide-Panel.

### R13 Integrationscheckpoint G-L und Tier 1-3

Erforderlich:

```sh
pytest
python tools/gen_contacts.py --check
python tools/gen_contact_analysis_images.py --check
python tools/smoke_full.py
python -m build
```

Zusaetzlich: isolierte Wheel-/sdist-Installation, Save-v10-Roundtrip und
Versionsablehnung, Browsermatrix,
echte Loopback- und Zwei-Geraete-Kopplung, 1280x720-uConsole, neun Stationen,
Audio-/Framezeit-/Thermallauf und Quellen-/Lizenzscan. Bekannte Fehler werden
vor B geschlossen; der Checkpoint ist kein Pausenpunkt.

### R14 Sonarhoerbild und Fixpublikation (B)

- Dauerstatus fuer Audioverfuegbarkeit, Breitband/gefiltert, Gain, Band, Notch,
  Lautstaerke und Stummschaltung oberhalb 1x.
- Direkter A/B-Vergleich und hoerbarer Traegerband-/Heterodynmodus fuer tiefe
  Frequenzen. Der gesamte Beam-Mix wird verarbeitet, nie eine versteckte
  Einzelentitaet solo wiedergegeben.
- Filterwechsel verwenden kurze blockkontinuierliche Uebergaenge; Analyse und
  Simulation bleiben unabhaengig von Audiohardware und Lautstaerke.
- Alle gueltigen Ping-, TMA- und Sonobuoyfixes erscheinen auf Bruecke und
  Commander mit Quelle, Messalter, Fixalter und Unsicherheit. Abgelaufene Fixe
  hinterlassen keine unsichtbaren klickbaren Marker.

Abnahme: synthetische Frequenzantwort, A/B-Grenzsprung, Gain in beiden Modi,
keine Audio-/RNG-Abhaengigkeit der Simulation, Fixalterung ohne Rendering sowie
physischer Kopfhoerer-/Lautsprechertest bei 1x.

### R15 Sonarlayout, Kontrast, Maus und Stationsabnahme (C)

- Strukturierte Command-Segmente: Tasten hellcyan, Beschreibung hellgrau,
  Labels gedaempft, Werte heller; Alarm-/NATO-Farben behalten ihre Semantik.
- Der virtuelle 1280x720-Canvas und Pygame bleiben verbindlich. Ein
  1280x800-Fenster zeigt ihn seitenrichtig mit Letterboxing und verwendet
  weiterhin dieselbe Hit-Test- und Stationsgeometrie.
- Die sechs Sonarseiten bleiben aufgabenspezifisch getrennt. Kopfzeile,
  Statusgruppen und Footer werden verdichtet, damit die Diagramme mehr nutzbare
  Hoehe erhalten; lange Erklaerungen wandern in begrenzte Tooltips, waehrend
  Messwerte, Quelle, Evidenzalter und Betriebszustand dauerhaft sichtbar bleiben.
- LOFAR ordnet ein kompaktes Live-Spektrum ueber einem moeglichst grossen
  Wasserfall an. Die Seitenleiste trennt Beam-/Filterstatus, gemessene Tonlinien
  und operatorgewaehlte Harmonik-Hilfen klar von der Kontaktliste. Grundfrequenz
  und f/2f/3f-Markierungen sind Hypothesen aus Receiverdaten, keine Identifikation.
- DEMON behaelt einen grossen Hauptplot und trennt Evidenz, Blade-Rate,
  RPM-Hypothesen fuer angenommene Blattzahlen und hoechstens drei
  Referenzkandidaten. Weder eine wahre Blattzahl noch eine Plattformidentitaet
  wird aus internem Entity- oder Fingerprintzustand angezeigt.
- Der zweizeilige Sonarfooter wird in klar getrennte, lokalisierte Segmente fuer
  Seite, Array, Gain, Band/Filter, Notch, Peak-Hold und Audiozustand gegliedert.
  Nur ausdruecklich ungefaehrliche Segmente werden klickbar; die Tastatur bleibt
  vollstaendig bedienbar.
- Gemeinsame Draw-/Hit-Geometrie fuer Kontakt-/Markerwahl, Sonartabs,
  ausdrueckliche ungefaehrliche Aktionen und Optionen. Mausbedienung funktioniert
  unabhaengig von Tooltips.
- Kein Waffenstart durch beilaufigen Einzelklick; sicherheitskritische Aktionen
  behalten explizite Bestaetigung.
- Visuelle Matrix: Bruecke, Waffen, Schaden, OPZ, Funk, Maschine, Helikopter,
  Eloka und sechs Sonarseiten, jeweils EN/DE, Normal/Gross und representative
  belegt/selektiert/veraltet/leer-Zustaende.

Abnahme: Tasten 1-9, 1280x720 sowie ein 1280x800-Letterbox-Fenster,
Letterbox-Ablehnung, kein Station-Key-Leak und Draw/Hit-Paritaet. Das
Sonarhauptpanel bleibt mindestens 850x380 Pixel gross und die Kontaktleiste zeigt
mindestens drei Eintraege; LOFAR und DEMON bleiben in EN/DE, Pseudolokalisierung
und beiden Textgroessen fuer leere, belegte, ausgewaehlte, veraltete und
evidenzarme Zustaende lesbar. Keine zusaetzliche FFT pro Renderframe, Render-I/O,
Simulationsmutation oder Truth-Reads; abschliessend physischer 1280x720-Kontrast-/
Trackballtest.

### R16 Batterie-/AIP-Endurance (D)

- Eigener streng validierter, ausdruecklich fiktiver Endurance-Block fuer
  relevante U-Bootprofile: kWh, Hotel-/Fahrtlast, Generatorleistung,
  AIP-Reaktanten, Reserve und Hysterese.
- Energiekomponente integriert Speicher und Uebergangsphasen deterministisch;
  keine negativen Vorraete und kein Zustandsflattern.
- Diesel laedt erst nach tatsaechlich erreichter Schnorcheltiefe. Funkbetrieb
  ist ein separater Zustand. Nuklearprofile erhalten keine erfundene
  Diesel-/AIP-Abhaengigkeit.
- Die bisherige zufaellige Schnorchellogik wird durch einen dedizierten,
  gespeicherten Modellzustand ersetzt, ohne bestehende gemeinsame RNG-Streams
  umzuschichten.

Abnahme: numerisch geschlossene Energiebilanz, Last-/Reservegrenzen,
Schnorchel-/Funktrennung, strikte Schemaablehnung und identische v10-Fortsetzung
mit/ohne Save.

Softwareabnahme abgeschlossen: alle 12 relevanten nichtnuklearen Profile besitzen
streng validierte `game_assumption`-Endurancewerte; Energiebilanz, exakte
Schwellenereignisse, Subsekundenpartitionierung, Schnorchel-/Funk-/Abtauchphasen,
1024er-Schrittgrenze, Legacy-RNG-Reihenfolge und die eng erkannte praezise
prae-R16-v10-Dateiform sind regressionsgeprueft. Physischer uConsole-Langlauf
bleibt bis R19 offen.

### R17 Erweiterte synthetische Schallausbreitung (E)

- Eine reine begrenzte `sonar/propagation.py`-API liefert ein gemeinsames
  synthetisches Schallgeschwindigkeitsprofil fuer Ausbreitung und BT-Messung.
- Zuerst direkter Pfad mit frequenzabhaengiger Daempfung, Laufzeit und
  Terrainfreiheit; danach begrenzte refraktierte, Oberflaechen- und Bodenpfade
  sowie Nachhall.
- Pfad-/Segmentzahl, Cache, Frequenzbaender und Updatekadenz sind hart begrenzt;
  Reihenfolge und Tie-Breaks sind stabil.
- Physische Terrainkollision verwendet nie die akustische Erreichbarkeits-API.
- Das bestehende eingefrorene Aktiv-Echo bleibt erhalten, bis ein getrennt
  getesteter Sende-/Auftreff-/Rueckkehrvertrag es ersetzt.

Abnahme: Profil-/BT-Konsistenz, monotone Frequenzdaempfung, Terrainfaelle,
deterministische Pfade, keine globale RNG-/Renderabhaengigkeit und gemessene
uConsole-Sensorkadenz. Mehrere aktive Echos brauchen einen ausdruecklichen
Zwischencheckpoint vor Semantikaenderung.

Softwareabnahme abgeschlossen: Die reine API ist auf vier stabile Pfade, drei
Segmente je Pfad, vier Frequenzbaender und 500 NM begrenzt. BT und passive
Sensoren teilen das synthetische Profil; Terrain, CZ-Fokussierung,
Frequenzdaempfung, Laufzeit und Nachhall sind deterministisch getestet. Aktive
Echo-Snapshots, physische Terrainkollision und Saveform bleiben unveraendert.
Die physische uConsole-Sensorkadenzmessung bleibt bis R19 offen.

### R18 Grundberuehrung und lokalisierte Schaeden (F)

- Neue Welten erhalten kontrollierte synthetische Flachwasserbereiche und
  weiterhin sichere Starts. Gespeicherte Bathymetriesnapshots alter Saves bleiben
  unveraendert.
- Separate physische Mindesttiefen-/First-Contact-Abfrage; keine Wiederverwendung
  der Sonar-Mehrwege-API.
- Fiktive Rumpfmasse, Abmessungen, Tiefgang und Kielreserve speisen gesweepten
  Kontakt, erste sichere Position, Streifen, Aufsetzen, Stranden und Bergung.
- Ein Kontaktuebergang erzeugt genau einen Aufprall. Stillstehender Kontakt
  verursacht nicht pro Frame erneut Schaden.
- Kontaktlage und dissipierte Energie verteilen Schaden auf bestehende Abteile;
  kein neues Schadensabteil. Hydraulische Rohr-/Pumpennetze bleiben ausserhalb.
- Grounding-Latch, letzte sichere Position und Kontaktzustand werden streng in
  Save v10 validiert und gespeichert.

Abnahme: Substep-invarianter Swept-Kontakt, stabile erste Kontaktposition,
einmaliger Aufprall, definierte Rueckwaertsbergung, unpassierbares Land,
getrennte Akustik-/Physiktests und identische Savefortsetzung im Grundzustand.

Softwareabnahme abgeschlossen: Neue Welten besitzen kontrollierte synthetische
Untiefen und hullsichere Starts; alte Bathymetriesnapshots bleiben abgeloest und
wertgleich. Der begrenzte physische Hull-Sweep behandelt Translation und Drehung,
Land, Weltrand und bilineare Mindesttiefe getrennt von Sonar. ASTERN-Bergung,
Einmal-Latch, lokalisierter Nicht-RNG-Schaden und strikter v10-Zustand sind
fortsetzungs- und partitionsgeprueft. Physische uConsole-Abnahme bleibt R19.

### R19 Gesamtabnahme und Pause

Alle Befehle aus R13 werden nach B-F erneut ausgefuehrt. Hinzu kommen die
Hardware-/Performance-Abnahmen fuer Sonarhoeren, neun Stationen,
Endurance-Langlauf, Ausbreitungskosten und Grundberuehrung. Danach wird
`docs/resume.md` mit Commit, Teststand, Hardwaregrenzen und naechstem kleinen
Schritt aktualisiert und die Arbeit verpflichtend gestoppt.

Softwareabnahme abgeschlossen: 2363 Tests, beide Generatorchecks, Smoke, Build,
isolierte Artefaktinstallationen, Save-v10-, Browser-, Loopback-, Stations-,
Layout-, Audio-/DSP-, Performance-, Quellen-, Lizenz- und Sicherheitstests sind
gruen. Der akzeptierte Kandidat wurde nach ausdruecklicher Freigabe vollstaendig
als `e42a678` committed; er wurde nicht gepusht. Physische
uConsole-, Zwei-Geraete-LAN-, Firewall-, Hoer-, Thermal-, Endurance- und
Groundingabnahmen bleiben offen, der Release daher auf HOLD. Pausenpunkt erreicht.

Nicht freigegeben bleibt Tier 4: Nimitz-Luftgruppe, Type-901-Nachversorgung,
LACM, allgemeiner Geschuetzkrieg und Verbandsoperationen.
