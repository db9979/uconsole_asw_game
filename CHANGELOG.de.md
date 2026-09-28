# Änderungsprotokoll

[English changelog](CHANGELOG.md)

Alle Versionen von U-Jagd, die neueste zuerst. Die [README](README.de.md) zeigt nur die neueste.

## 1.3.35

Version 1.3.35 behebt Sonar-Ton auf der uConsole, der verstummen konnte, bis
man den Ton in den Optionen aus- und wieder einschaltete. Ein seltenes
Wettrennen im pygame-Mixer konnte den Sonarkanal still stehen lassen, während
sein nächster Block für immer in der Warteschlange hing, und die
Sonar-Wiedergabe wartete dauerhaft auf diesen Platz. Die Wiedergabe spielt
einen solchen hängenden Block jetzt selbst ab und macht weiter, und ein
beendeter Sonar-Audio-Thread startet mit dem nächsten Block neu.
`audio_debug.log` zählt beides (`queue_stranded`, `worker_restarts`).
Spielstände bleiben v27.

## 1.3.34

Version 1.3.34 schreibt ein Absturzprotokoll: Jeder Spielstart hängt an
`~/.u-jagd/crash.log` eine Start- und eine Endzeile an, und endet das Spiel
durch einen Fehler, steht dort der Traceback, nach einem harten Absturz
(Speicherzugriffsfehler in SDL oder Audio, `SIGTERM`) die Stapel aller Threads.
Eine Startzeile ohne Endzeile heißt, das Spiel wurde von außen beendet, meist
vom Kernel bei Speichermangel. Die Datei bleibt unter 256 KiB. Spielstände
bleiben v26.

## 1.3.33

Version 1.3.33 lässt das ESM des besetzten U-Boots die Umlaufzeit jedes Radars
messen, die Zeit zwischen den Treffern seiner Hauptkeule: ein Suchradar zeigt
„dreht“ mit seiner Umlaufzeit (etwa 2,5 s für Navigations- und Seeraumradar, 5
s für Luftraumradar), ein Verfolgungs- oder Feuerleitradar „dauernd“. Eine
Dauerbeleuchtung des Mastes ist immer eine Mastwarnung und steht im Log; die
Seite Mast & ESM am uConsole und der Browser zeigen die Messung. Spielstände
sind jetzt v27.

## 1.3.32

Version 1.3.32 bringt Richtungshören: Mit Stereoton kommen Detonationen,
zurückkehrende Echos und das aktive Ping einer anderen Plattform aus der
Peilung, aus der sie gehört wurden, links für Backbord und rechts für
Steuerbord vom Bug der Fregatte oder des besetzten U-Boots aus, am uConsole
und im Remote-Crew-Browser. Die Fregatte spielt jetzt auch das Ping eines
U-Boots selbst, und das besetzte U-Boot hört das Ping eines Jägers am Rumpf.

## 1.3.31

Version 1.3.31 gibt dem besetzten U-Boot echte Torpedorohre: Die Torpedogasten
laden jedes leere Rohr aus den Reserven (`M` an der Station Waffen oder Laden
im Browser), und ein geladenes Rohr muss vor dem Schuss geflutet werden, was
20 s dauert und hörbar ist (`Shift+M` oder Fluten). Jedes U-Boot führt jetzt
noch einmal so viele Reservetorpedos wie Rohre, nachgeladen in 2 bis 4
Minuten; die U-Boote der KI laden und fluten weiter selbst. Spielstände sind
jetzt v26.

## 1.3.30

Version 1.3.30 lässt die **Fregatte die U-Boot-Missionen gegen die KI
spielen**: Ein unbesetztes Missions-U-Boot verfolgt jetzt seinen Auftrag,
statt zu patrouillieren. Es läuft unter der Sprungschicht zum
Durchbruchsziel, folgt den Feindmeldungen der Führung und geht zum Sichten
und Melden der Fregatte auf Sehrohrtiefe, und beim Geleitzugangriff läuft es
dem Geleitzug voraus und torpediert seine Handelsschiffe einzeln.
Spielstände bleiben v25.

## 1.3.29

Version 1.3.29 benennt das U-Boot einheitlich: Alle Anzeigen, die
Web-Clients, Hilfe und Handbuch sagen jetzt **U-Boot** (englisch
**submarine**), wo bisher nur „Boot“ stand, etwa **U-Boot-Kampagne** und
U-Boot-Missionen. Spielstände bleiben v25.

## 1.3.28

Version 1.3.28 macht die **KI-Jäger klüger**: Die OPZ markiert den bloßen
Radarpunkt eines ausgefahrenen Masts oder Schnorchels, und eine Mastspur,
eine HF/DF-Kreuzpeilung oder eine U-Boot-Datummeldung der Führung wird jetzt
zum Datum der Jagd. Ein frischer Fix der eigenen Sensoren geht per Datenlink
an ein befreundetes KI-Kriegsschiff mit ASROC in Reichweite. Spielstände sind
jetzt v25 (Radarpunkte und Markierungen).

## 1.3.27

Version 1.3.27 sortiert die **ESM-Bibliothek des Boots nach Passung**: die
Emitter, deren veröffentlichte Bereiche eine Messung enthalten, stehen mit der
besten Passung zuerst (Frequenz und PRF nahe der Bereichsmitte, dieselbe
Modulation), jeder mit der Stufe gut, mittel oder schwach am uConsole und im
Browser, sodass ein gut passendes Radar wie das des Hubschraubers nicht mehr
aus der Liste fällt. Spielstände bleiben v24.

## 1.3.26

Version 1.3.26 überspringt auf der uConsole die Update-Suche, wenn kein
Internet da ist: Ein Verbindungstest zu GitHub entscheidet in höchstens 2,5
Sekunden, danach startet das Spiel sofort, statt auf Zeitüberschreitungen zu
warten. Hängende Git-Abrufe brechen nach spätestens 60 Sekunden ab. Spielstände
bleiben v23.

## 1.3.25

Version 1.3.25 räumt die Dokumentation auf. Das Spiel bleibt unverändert, Spielstände
bleiben v24.

## 1.3.24

Version 1.3.24 bringt **Atmosphäre ins besetzte Boot**: der Druckkörper knarzt in
der Tiefe und kracht, wenn er versagt, Detonationen im Wasser sind dicht beim
Boot oder in der Ferne zu hören und stehen mit Peilung im Log, und bei
**Schleichfahrt** schalten die Boot-Bildschirme am uConsole und im Browser auf
gedimmtes Rotlicht. Die Browser des Boots spielen jetzt dessen eigene Töne, und
der Alarmton einer Rettungsaufgabe stört den Browser nicht mehr. Spielstände
bleiben v24.

## 1.3.23

Version 1.3.23 gibt allen Menüs und Dialogen das Aussehen des Startbildschirms:
Hilfe, Optionen, Speichern/Laden, Beenden, Nationen, Remote-Crew-Verwaltung
(`F9`) und das Missionsende zeigen jetzt die nächtliche Jagd hinter einem
durchscheinenden Konsolen-Panel mit Phosphor-Eckwinkeln und leuchtendem Titel;
die Mission läuft dahinter weiter. Bei hohem Kontrast bleiben die Panels
deckend. Die Browser-Dialoge nutzen denselben Nachthimmel und Winkelrahmen.
Spielstände bleiben v24.

## 1.3.22

Version 1.3.22 macht die Remote-Crew-Datenströme stabiler. Ein Browser, der
seinen Sonar-Audio- oder Sonar-Anzeigestrom neu verbindet, übernimmt jetzt
sofort seinen eigenen bisherigen Strom, statt abgewiesen zu werden, solange der
Host die alte Verbindung noch nicht als beendet erkannt hat. Der Web-Client
fragt bei eingeschaltetem Push nicht mehr zu jedem gepushten Zustand
zusätzlich den Zustand ab. Die Browsertests für Live-Audio und den
Zustands-Push laufen jetzt in Echtzeit neben dem Host. Spielstände bleiben
v23.

## 1.3.21

Version 1.3.21 lässt das besetzte Boot **unter seine Testtiefe** tauchen, bis zur
Zerstörungstiefe (1,5-fache Testtiefe), mit wachsendem Risiko: gebrochene
Bolzen, versagende Wellen- oder Ventildichtungen und, tiefer, ein Riss im
Druckkörper fluten Abteilungen und erhöhen den Schaden, je tiefer, desto
häufiger; in Zerstörungstiefe bricht der Druckkörper zusammen. Die
Tiefenleitern markieren die Zerstörungstiefe, und ein roter Alarm zeigt die
Fahrt unter der Testtiefe. Spielstände bleiben v24.

## 1.3.20

Version 1.3.20 bringt den **Angriffsrechner am Sehrohr** des Boots: Jede
Stadimeter-Messung ist eine Marke, und zwei oder mehr Marken im Abstand von
einer Minute ergeben Kurs und Fahrt des Ziels, den Vorhaltewinkel und die
Laufzeit des Torpedos unter dem Sehrohr (Browser: Spalte Lösung).
`Strg+Enter` auf der Sehrohrseite (Browser: Schuss nach Lösung) schießt auf
den Abfangkurs; ein Schuss auf einen markierten Sonarkontakt nutzt die Lösung
ebenfalls. Spielstände wechseln auf **v24** (die Marken werden gespeichert);
v23-Spielstände werden nicht mehr geladen.

## 1.3.19

Version 1.3.19 macht den Start auf der uConsole sofort sichtbar: Ein kleines
Startfenster zeigt, ob der Starter nach einem Update sucht, es lädt oder
installiert, und schließt sich, sobald das Spiel erscheint. Ein zweiter Start,
während U-Jagd startet oder läuft, öffnet das Spiel nicht mehr doppelt, sondern
meldet „U-Jagd läuft bereits.“. Spielstände bleiben v23.

## 1.3.18

Version 1.3.18 bringt ein **A4-Werbeplakat** auf Deutsch und Englisch (PNG mit
300 dpi und PDF) in `docs/poster/`: die Szene des Startbildschirms, eine kurze
Beschreibung der uConsole- und Windows-Version, vier Screenshots und QR-Codes
zum Download und zur Unterstützerseite. `tools/build_poster.py` rendert es aus
der aktuellen Szene und den Screenshots neu. Das Spiel selbst ist unverändert;
Spielstände bleiben v23.

## 1.3.17

Version 1.3.17 behebt das Selbst-Update des Windows-Programms: Nach dem
Austausch startete die neue `U-Jagd-Windows.exe` nicht ("Failed to load
Python DLL"), weil sie das bereits gelöschte Entpackverzeichnis des alten
Prozesses erbte. Der Neustart entpackt jetzt frisch. Das Starterfenster zeigt
außerdem den Link "Spendier mir einen Kaffee". Spielstände bleiben v23.

## 1.3.16

Version 1.3.16 bringt die **Bootskampagne**: fünf verkettete Bootsmissionen in
einem Seegebiet (Aufklärung, Durchbruch, Geleitzugangriff, Durchbruch,
Geleitzugangriff), gewählt mit `Tab` im Kampagnenbildschirm. Das Boot nimmt
Torpedos, Rumpfschaden und Ansehen bei der U-Boot-Führung von Mission zu
Mission mit; im Stützpunkt gibt es volle Überholung oder schnelles Auslaufen.
Gespeichert in `~/.u-jagd/boat_campaign.json`; Spielstände bleiben v23.

## 1.3.15

Version 1.3.15 bringt Bootsmission 7, **Geleitzugangriff**: Die Fregatte
geleitet vier Handelsschiffe, und das U-Boot muss zwei davon versenken. Nur
die Torpedos des besetzten Boots treffen ein Handelsschiff; die KI-Fregatte
hält ihre Position vor dem Geleitzug und verfolgt Kontakte nur in seiner Nähe.
Der Auftrag des Boots zählt die versenkten Handelsschiffe. Spielstände bleiben v23.

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
