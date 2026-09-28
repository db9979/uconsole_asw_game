# Änderungsprotokoll

[English changelog](CHANGELOG.md)

Alle Versionen von U-Jagd, die neueste zuerst. Die [README](README.de.md) zeigt nur die neueste.

## 1.3.15

Version 1.3.15 behebt das Selbst-Update des Windows-Programms: Nach dem
Austausch startete die neue `U-Jagd-Windows.exe` nicht ("Failed to load
Python DLL"), weil sie das bereits gelöschte Entpackverzeichnis des alten
Prozesses erbte. Der Neustart entpackt jetzt frisch. Das Starterfenster zeigt
außerdem den Link "Spendier mir einen Kaffee". Spielstände bleiben v23.

## 1.3.14

Version 1.3.14 bringt **Bootsmissionen**: Szenario 5 *Durchbruch* (das U-Boot
muss ein Zielgebiet hinter der Patrouillenposition der Fregatte erreichen)
und Szenario 6 *Aufklärung* (es muss die Fregatte durch das Sehrohr sichten
und eine Lagemeldung funken, während sie in Sicht ist). Die Fregatte muss das
verhindern. Der Auftrag des Boots steht über seiner Karte und in den
Bootsstationen im Browser; das Ziel ist auf der Bootskarte markiert.
Spielstände bleiben v23.

## 1.3.13

Version 1.3.13 rendert die uConsole-Screenshots nach drei simulierten
Minuten statt nach sechs Sekunden, damit Wasserfälle, Plots und Kontaktlisten
gefüllt sind, und zeigt den Missionseditor mit der mitgelieferten
Beispielmission (Bibliothek und Seed-Vorschau des Sektors) statt einer leeren
Bibliothek. Die README verlinkt jetzt auch Menü- und Editoransichten.
Spielstände bleiben v23.

## 1.3.12

Version 1.3.12 erneuert die Screenshots in der README aus dem aktuellen
Spiel (uConsole mit 1280 x 720, einschließlich der Stationen des besetzten
U-Boots, und der Remote-Crew-Browser in Chromium) und verschiebt die
Versionsgeschichte nach [CHANGELOG.de.md](CHANGELOG.de.md), damit die README nur noch
die neueste Version steht. `tools/capture_screenshots.py` und
`tools/capture_commander.py` erzeugen alle Bilder neu. Spielstände bleiben v23.

## 1.3.11

Version 1.3.11 bringt ein **Windows-Programm**: `U-Jagd-Windows.exe` startet
das Spiel als Remote-Crew-Server (Besatzungs- oder Solomodus, wahlweise als
U-Boot), zeigt Browser-Adresse, Beitrittscode und QR-Code und bietet jede
neuere Version selbst zum Update an. GitHub Actions baut es bei jedem Push auf
`main` und veröffentlicht es als Release `v<Version>`. Das Spiel kennt dazu
`--remote-crew` (Remote Crew im Besatzungsmodus auf der ersten privaten
LAN-Adresse beim Start) und `--status-file`. Siehe
[Windows-Programm](README.de.md#windows-programm). Spielstände bleiben v23.

## 1.3.10

Version 1.3.10 behebt den uConsole-Installer bei einem Checkout, der älter als
der Installer ist: Er zieht diesen Checkout jetzt zuerst per Fast-Forward auf
`main`, statt mit fehlender `u_jagd_updater.py` abzubrechen.

## 1.3.9

Version 1.3.9 bringt einen Ein-Befehl-Installer für die uConsole mit
automatischem Update: Jeder Start holt das neueste GitHub-Release (ein
Hintergrund-Timer prüft zusätzlich alle sechs Stunden), ohne Netz startet die
installierte Version, und eine Version, die nicht startet, wird zurückgerollt.
Er legt Menüeintrag, Desktop-Verknüpfung und den Befehl `u-jagd` an.
Spielstände bleiben v23.

## 1.3.8

Version 1.3.8 bringt einen Unterstützungslink: einen QR-Code im Hauptmenü des
uConsole und einen kleinen Link auf den Remote-Crew-Seiten Kopplung, Lobby und
Einstellungen sowie auf der Admin-Seite des Webspiels, nie über einer
laufenden Station. Außerdem sind die Anleitungen aktualisiert: Referenz und
README nennen das VDS und 31 kn, die Grenzen des Missionseditors in der README
entsprechen der Laufzeit, und die Koop- und Protokollanleitungen beschreiben
Seitenwahl im Solo-Modus, U-Boot-Rollen und das Beenden über die Admin-Seite.
Spielstände bleiben v23.

## 1.3.7

Version 1.3.7 gibt der Fregatte F-217 ihre echte Höchstfahrt von 31 kn
(AK). Die Antriebsleistung ist so skaliert, dass Widerstand, Beschleunigung
und Drehverhalten bis 25 kn unverändert bleiben; der Eigenlärm steigt jetzt
bis 31 kn, und das Kabel der Nixie reißt weiterhin über 25 kn. Die
Admin-Seite des Webspiels bekommt **Spiel jetzt beenden**, das den
Serverprozess nach Rückfrage stoppt, damit er nicht im Hintergrund
weiterläuft. Spielstände bleiben v23.

## 1.3.6

Version 1.3.6 zeichnet den Startbildschirm als animierte Nachtjagd: die
Fregatte F-217 mit drehendem Radar, Schornsteinrauch, Bugwelle und
Schleppantenne, der Hubschrauber mit Tauchsonar und ein U-Boot unter der
Sprungschicht, das aufleuchtet, wenn der Puls des Rumpfsonars es trifft; im
Titel stehen Autor und Version. Dieselbe Szene liegt abgedunkelt hinter dem
Hauptmenü. Die Silhouetten in Sehrohr und Brückenfernglas zeigen jetzt
detaillierte Klassenprofile (Fregatte, Containerschiff, Kleinfahrzeug,
Hubschrauber), die mit der See stampfen, Radar und Rotoren drehen und Bugwelle
und Kielwasser ziehen. Im Remote-Crew-Solomodus wählt der Dialog „Neues
Spiel“ die Seite: Fregatte oder U-Boot, das dann die KI-Jäger jagen.
Spielstände bleiben v23.

## 1.3.5

Version 1.3.5 bringt KI-Jäger: Wenn niemand die Fregatte fährt (die uConsole
spielt das Boot oder ein Solo-Browser das U-Boot), jagen Fregatte,
Hubschrauber und Seefernaufklärer das Boot mit den eigenen Sensoren der
Fregatte, auf jeder Fregattenstation, die kein Browser hält. Spielstände
bleiben v23.

## 1.3.4

Version 1.3.4 gibt der Fregatte ein Tiefensonar mit variabler Tiefe (VDS)
als dritte Anlage neben Rumpfsonar und Schleppantenne: `Shift+Y` fiert den
Schleppkörper aus oder holt ihn ein (3-15 kn, Seegang bis 5, Verlust über
24 kn), `U`/`V` stellen seine Tiefe (20-300 m), solange er die gewählte
Anlage ist, und er horcht und pingt aus seiner eigenen Tiefe, also unter der
Sprungschicht, wenn er dort hängt. Er löst die Links/Rechts-Mehrdeutigkeit
der Schleppantenne wie das Rumpfsonar auf. Das Remote-Crew-Sonar bekommt
dieselben Bedienelemente. Spielstände wechseln auf Format v23 (VDS-Zustand).

## 1.3.3

Version 1.3.3 zeichnet die Wasserfälle (LOFAR, DEMON, Breitband) im
Remote-Crew-Browser über `OffscreenCanvas` in einem Hintergrund-Worker, wo der
Browser das anbietet; der Hauptthread der Seite und das Live-Sonaraudio darauf
laufen die Rasterschleife nicht mehr. Andere Browser behalten den bisherigen
Weg. Spielstände bleiben v22.

## 1.3.2

Version 1.3.2 lässt im Missionseditor die Referenzwelt einer Mission aus einer
Liste der 128 mitgelieferten Sektoren (mit ihren Ländern) wählen, statt
`sector:<n>` einzutippen; die Vorschau zeichnet die Küste des gewählten
Sektors. Spielstände bleiben v22.

## 1.3.1

Version 1.3.1 gibt dem besetzten U-Boot einen Funkraum (eine siebte
Bootsstation: der Rundspruch des Hauptquartiers mit einer Kontaktmeldung zur
Fregatte und Lagemeldungen, die der KW-Peiler der Fregatte peilen kann) und
lässt die ESM des Boots den Hubschrauber der Fregatte und den
Seefernaufklärer an ihren eigenen katalogisierten Suchradaren hören.
Spielstände wechseln auf Format v22 (Zustand des Funkraums).

## 1.3.0

Version 1.3.0 erweitert Simulation und Werkzeuge der Besatzung, ohne die
Balance von 1.0.0 zu verschieben (77 Kalibrierungsmetriken unverändert): ein
zweiter Leichtgewichtstorpedo mit Suchmustern, Einschaltpunkt und
Salvenstreuung; feindliche U-Boote, die erst nach konvergierter eigener
Zielanalyse schießen; Gegenfluten, Längstrimm und Anlagenwahl an Bord;
Sonobojen-Muster und MAD-Lauf des Hubschraubers; Konvergenzzonen aus dem
gemessenen Schallprofil mit Ekelund- und Punktstapel-TMA; ein Sehrohr mit
Sichtungen, Stadimeter und Dieselgeräusch beim Schnorcheln für das besetzte
U-Boot; geglättete Kartenlinien, das Licht der Stunde auf der Karte, ein
Wetterband und ein gemeinsamer Horizont-Renderer; ein WebSocket-Zustandspush
für die Remote Crew mit generierter Schema-Allowlist; eine reine
Beobachterrolle, ein Zeitstrahl zur Nachbesprechung mit JSON-Export und
Sprachfunk ab Start; und eine Missionslaufzeit im Umfang des Editors
(Referenzsektoren, Schützen- und Erreichen-Ziele, Zufallsgruppen,
zeitgesteuerte Ereignisse, eingestelltes Wetter, platzierte Luftfahrzeuge,
Tiere und Täuschkörper). Der Kern ist in Mixins zerlegt, die Testsuite läuft
parallel. **Spielstände haben das Format v23 (Tiefensonar der Fregatte, Funkraum des besetzten Boots, Funkaufträge der Führung, Wachplan, Ermüdung und Moral der Crew, der Seefernaufklärer auf Abruf, Abteilungen und Leckabwehr, Tauchzellen, Trimm und Pressluft sowie ESM-Bild des besetzten Boots,
Diesel, Laderate und Luftvorräte der U-Boote, Crew-Zustand des Bootes,
Sehrohr-Sichtungen, Waffeneinstellungen, Missionsereignisse, fremde Pings auf
dem Weg zur Fregatte); ältere Stände werden abgewiesen.**

## 1.2.0

Version 1.2.0 verbessert den Spielfluss und die Übergabe zwischen den
Stationen: Der `Esc`-Dialog und das Missionsende führen zurück ins Hauptmenü
(`M`), `R` startet eine Editor-Mission als sie selbst neu, Konvoimissionen
melden die Restzeit als Fortschritt, und eine OPZ-Fusion aus einem
Sonarkontakt lässt sich der Waffenzentrale zuweisen; ihre Klassifizierung und
Zugehörigkeit gelten für die Feuerleitung (FREUND/NEUTRAL auf einer Fusion
sperrt jeden Torpedoschuss). Spielstände bleiben v14.

## 1.1.0

Version 1.1.0 ersetzt die verbliebenen kinematischen Vereinfachungen durch
physikalische Modelle und hält dabei die Spielbalance von 1.0.0 (geprüft durch
einen Kalibrierungs-Harness): kraftbasierte Schiffshydrodynamik und
Seegangsbewegungen; ein zeitlich veränderlicher Ozean mit Gezeiten,
Deckschicht, Sedimenten und Wracks; passive/aktive Sonargleichungen mit
Strahlverfolgung; Seiten-Mehrdeutigkeit der Schleppantenne, Doppler und TMA mit
Kovarianz; U-Boot- und Torpedophysik (Energie, Flossen, Draht,
Annäherungszünder); Täuschkörper-Diskriminierung; Abteilungsflutung,
Stabilität, Brand und Reparaturlogistik; die Radargleichung mit drehender
Antenne, ESM-Pegel, KW-Ausbreitung und ein Ausguck mit Mondlicht; sowie
Flugkörper-Flugphysik mit Düppelwolken, CIWS-Ballistik, Pop-up-Angriffen,
Helikopter-Schwebeflug/Decklimits und treibenden Bojen. Feindliche U-Boote
brauchen jetzt eine eigene TMA, bevor sie Ihre Entfernung kennen.
**Spielstände haben jetzt das Format v14 (Katalogzuordnung, gemeinsamer Kartenplot);
ältere Spielstände werden abgelehnt.** Das Remote-Crew-v2-Protokoll bleibt bis auf neue ELOKA-Felder
unverändert. Die vollständige Übersicht steht in
[docs/simulation-gaps.md](docs/simulation-gaps.md).

## 1.0.0

Version 1.0.0 teilt jede Arbeitsstation in zwei per Tab wählbare Unterseiten,
ergänzt manuelle Freigabeschalter für CIWS und FLAK neben den bestehenden
automatischen Feuerfreigaben und gibt der Autocrew-Brücke ein Ausweich- und
Grundberührungs-Vermeidungsverhalten gegen ASM-/Torpedo-Bedrohungen. TMA-
Neulösungen nutzen jetzt eine Hysterese gegen fast gleichwertige
Peilungslösungen, und feindliche Seezielflugkörper tragen einen aktiven
Radar-Suchkopf in der Terminalphase, der eine ESM/RWR-Warnung liefert, bevor
das Suchradar sie erfasst. Ein konsolidiertes Theme-System ergänzt eine
optionale High-Contrast-Palette für Farbfehlsichtigkeit. Speicherformat v11
und das Remote-Crew-v2-Protokoll bleiben unverändert.
