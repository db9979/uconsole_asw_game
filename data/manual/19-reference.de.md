# Referenzdaten {#reference}

Alle Werte sind die Standardwerte der aktuellen Spielversion. Eigene Schwierigkeit und Missionen können Bestände und Zeitlimits ändern.

## Einheiten {#ref-units}

| Größe | Einheit |
|---|---|
| Distanz, Entfernung | Seemeilen (sm) |
| Fahrt | Knoten (kn) |
| Tiefe | Meter (m) |
| Frequenz | Hertz (Hz) |
| Kurs, Peilung | rechtweisende Grad, 000 = Nord, im Uhrzeigersinn |
| Zeit | Simulationssekunden; nur 1x |

## Sensoren {#ref-sensors}

| Sensor | Reichweite | Genauigkeit / Hinweis |
|---|---|---|
| Passivsonar (Basis) | 20 sm | nur Peilung; HMS +/-6 Grad, TAS +/-2 Grad, VDS +/-4 Grad |
| Aktiver Ping | 18 sm (Referenzziel, schräger Aspekt) | CW oder LFM (`W`); Entfernungsgenauigkeit aus Puls und SNR, Tiefe +/-12 m; 30 s Abklingzeit; hörbar bis 60 sm |
| Tauchsonar | 18 sm passiv / 14 sm aktiv | +/-2 Grad |
| Sonarboje | 8 sm | 60 min Batterie |
| Überwasserradar | 30 sm (50 % je Umlauf) | 4 s Antennenumlauf; Radarhorizont; keine getauchten Kontakte |
| Luftradar | 100 sm (50 % je Umlauf) | Flugzeuge und Flugkörper; Störer werden aus der Nähe durchbrannt |
| ESM | 150 sm (Hauptkeule) | +/-3 Grad Peilung; Pegel und Entfernungsschätzung |
| HFDF | 120 sm Bodenwelle bei 15 MHz (je nach Frequenz etwa 95-150 sm) | +/-8 Grad Peilung (Raumwelle +/-16) |
| Ausguck | 12 sm Überwasser, 5 sm aufgetauchtes U-Boot, 20 sm Luft, 20 sm Land | x0,25 (Neumond) bis x0,45 (Vollmond) bei Nacht; Nebel und Seegang verkürzen; Klasse ab 2, Typ ab 3,2 aufgelösten Zyklen je relativer Größe (Tanker etwa 7/5 sm, Fregatte 5/4 sm, Speedboot 3/2 sm an einem klaren Tag) |

## Waffen und Gegenmaßnahmen {#ref-weapons}

| System | Daten |
|---|---|
| Fregattentorpedo | 45 kn, 12 sm (Batterie), drahtgelenkt (Schiff <= 20 kn, <= 1,5 Grad/s, 5 sm Spule), 2 Rohre, 60 s Nachladen, Tiefe 10-300 m, Annäherungszünder |
| Helikoptertorpedo | 45 kn, 6 sm, 2 je Einsatz, ohne Draht |
| Feindtorpedo | 40 kn, 20 sm, zielsuchend ab 3 sm, detoniert innerhalb etwa 90 m (unter einem Schiff auf Kieltiefe), Schaden sinkt mit dem Abstand; schneller als die Fregatte, bloßes Ablaufen hilft selten; ein KI-U-Boot greift eine geortete Fregatte innerhalb 10 sm auch bei leiser Fahrt an |
| Nixie-Schlepptäuschkörper | 2 je Mission, 600 s, 0,2-sm-Kabel (10 m bei 15 kn, langsamer tiefer, reißt über 25 kn), 60 s Nachladen |
| ESSM | 6 Flugkörper, 30 sm, 2 Feuerkanäle |
| CIWS | 1,5 sm, 180 Schuss, braucht Freigabe; 115 Grad/s Schwenken, eigenes Folgeradar innerhalb 3 sm |
| Flak-Geschütz | 240 Schuss, braucht Freigabe |
| Düppel | 6 Ladungen, 8 sm, 40 % Zielverlust nach dem Aufblühen; Wolke treibt 90 s mit dem Wind |

## Eigenes Schiff {#ref-ship}

| Merkmal | Wert |
|---|---|
| Fahrt | 4-31 kn; Telegraph STOP 0, SLOW 6, HALF 10, FULL 16, FLANK 31 kn |
| Drehrate | etwa 0,075 Grad/s je Knoten (1,2 Grad/s bei 16 kn); Drehkreis etwa 0,4 NM |
| Kavitation | ab 15 kn bei ruhiger See, bei schwerer See früher; Passivreichweite x0,35 |
| Modus LEISE | Lärm x0,65, max. 12 kn |
| TAS-Handhabung | 3-12 kn, ausbringen 360 s, einholen 480 s, Defekt über 20 kn |
| TAS-Tiefe | 20-260 m, minus 4 m je Knoten |
| Schaden | 9 Abteilungen, 3 Trupps (etwa 20 s Weg je Abteilung), 8 Leckabdichtsätze; sinkt jenseits der Reserveverdrängung, kentert bei 35 Grad Krängung oder verlorenem GM |

## Umwelt {#ref-environment}

| Vorgang | Modell |
|---|---|
| Gezeit | M2 (12,42 h) + S2 (12 h), 0,4-1,4 m Amplitude, im Flachwasser größer |
| Deckschicht | jahreszeitliche Grundtiefe; nachmittags etwa 8 m flacher; vertieft sich bei Wind über 12 kn; interne Wellen +/-6 m |
| Schallgeschwindigkeit | Mackenzie-Gleichung aus dem Temperaturprofil (Oberfläche 8-18 Grad C je nach Jahreszeit) |
| Strömung | festes Feld bis 1 kn plus 3 % des Windes, 20 Grad rechts der Windrichtung |
| Meeresboden | Fels, Kies, Sand, Schluff oder Schlick; beeinflusst die Bodenreflexion |
| Hindernisse | bis zu 64 kartierte Wracks und Unterwasserfelsen (Spitzen mindestens 15 m tief), auf jeder Karte eingetragen (Wrack: Rumpfstrich mit Masten, Fels: Sternchen; Tiefe der Oberkante beim Heranzoomen, Details im Tooltip); beide heben in ihrer Grundfläche den Meeresboden an und sind Hindernisse für Schiff, U-Boote und Waffen |
| Schiffsverkehr | Frachter, Tanker und Passagierschiffe laufen auf festen Kursen von Ziel zu Ziel (die eingezeichneten Häfen und Ausgänge am Rand des Seegebiets); sie weichen nach den Kollisionsverhütungsregeln aus (entgegenkommend, von Steuerbord kreuzend oder beim Überholen: 35 Grad nach Steuerbord, wenn der Passierabstand unter 0,5 NM läge; jedes Schiff weicht unter 0,25 NM aus) und laufen vor einer Detonation innerhalb von 8 NM 10 min mit voller Fahrt davon; Arbeits- und Fischereifahrzeuge ziehen weiter frei umher, Geleitzüge und Schiffe von HQ-Aufträgen halten ihren Kurs |
| Atmosphäre | Barometer 975-1025 hPa, das vor steigendem Seegang fällt; Lufttemperatur aus Wasser, Jahreszeit, Tageszeit und kaltem Nordwind (in Winterstürmen unter 0 Grad C: Schnee, Vereisung); Böen; Wolkenuntergrenze; Sonnenstand mit bürgerlicher/nautischer Dämmerung; Mondphase |
| Regenlinse | Regen süßt die obersten Meter aus (bis -1 PSU, vom Wind eingemischt) und senkt die Schallgeschwindigkeit an der Oberfläche |
| SOFAR-Kanal | ein inneres Schallgeschwindigkeitsminimum (etwa 400-500 m unter der Deckschicht) gibt es nur in ausreichend tiefem Wasser |

## See, Wetter und Effekte {#ref-sea-effects}

Was See und Wetter bewirken und was die Bildschirme davon zeigen:

- **Optiken:** Brückenglas, Sehrohr und Handy-Ausguck zeigen, was auf See geschieht: Wassersäulen von Torpedo- und Wasserbombentreffern, Feuer und Rauch eines brennenden Schiffs und ein sinkendes Schiff. Beim Ausfahren kommt das Sehrohr aus dem Wasser, das Wasser läuft vom Glas ab; ab Seegang 3,5 spülen Wellen ab und zu über den Kopf und lassen Tropfen zurück.
- **Karten:** Marken gleiten zwischen den Sensormeldungen weich weiter, ein neuer Ping oder eine Detonation breitet sich als Ring vom Ort des Geschehens aus.
- **Instrumente:** Zeiger und Telegrafenhebel bewegen sich mit Masse und schwingen ein; ein neuer Maschinenbefehl läutet die Telegrafenglocke.
- **Meeresleuchten:** nachts in warmem Wasser (ab 11 °C Oberflächentemperatur, voll ab 16 °C) leuchtet Plankton, wo das Wasser aufgewühlt wird. Kielwasser, die Schaumfahne eines Sehrohrs und Torpedobahnen leuchten blaugrün und sind weiter zu sehen: ein voll leuchtendes Kielwasser nimmt 40 % des nächtlichen Nachteils für Ausgucke beider Seiten zurück. Wie stark ein Seegebiet leuchtet, legt sein Seed fest.
- **Knuckles:** eine harte Drehung (ab 0,9 Grad/s) mit Fahrt (ab 12 kn) hinterlässt dort, wo das Heck herumschwang, ein Blasenfeld von etwa 150 m, höchstens eines alle 15 s je Plattform, das über etwa 100 s abklingt und nach 5 min vergangen ist. Schall hindurch verliert bis zu 12 dB (passiv und aktiv, bei mehreren höchstens 20 dB), ein aktiver Ping bekommt daraus ein Falschecho ohne Doppler, und ein kielwassersuchender Torpedo nahe einem starken Feld kann hineingezogen werden und dort kreisen. Fregatte und U-Boote erzeugen und erleiden sie gleich; das Brückenlog meldet das erste Knuckle einer Drehung.
- **Wracks und Felsen:** kartierte Wracks und Felsen geben aktive Echos wie ein stehendes Ziel. Ein Hubschrauber oder Seefernaufklärer, der mit MAD über ein Wrack fliegt, bekommt eine Anomalie ohne Kontakt (Log: „Wrack oder U-Boot?“).
- **Gewitter:** unter einem Sturm (Regen ab 55 %) schlagen zufällig Blitze rund um das Schiff ein, im stärksten Regen etwa einer alle 12 s. Ein Blitz erhellt die Optiken und zuckt in seiner Peilung herab, der Regen prasselt stärker, und einem Einschlag innerhalb von 10 sm folgt nach der Laufzeit des Schalls (3 s je km) Donner. Die Sferics der Entladungen knistern auf den ESM-Rosen (ELOKA und ESM des U-Boots), auf der HF/DF-Rose und im Browser (Hinweis **Sferics**) und streuen jede HF/DF-Peilung, die der Fregatte auf den Funkspruch eines U-Boots wie die eines U-Boots auf den der Fregatte, um bis zu 75 %. Die Blitze folgen Seed und Simulationszeit und brauchen daher keinen Spielstand.
- **Deckbewegung:** siehe Hubschrauberdeck, Startgrenzen: Start und Landung brauchen eine ruhige Phase von mindestens 6 s innerhalb der Roll- und Stampfgrenzen.

## Gegnerische U-Boote {#ref-subs}

| Klasse | Leisheit | Max. Tiefe | Torpedos |
|---|---|---|---|
| Diesel (älter) | 0,75 | 200 m | 4 |
| AIP (modern) | 0,85 | 250 m | 5 |
| Nuklear-Jagd-U-Boot | 0,92 | 400 m | 8 |

U-Boote weichen nach einem gehörten Ping oder Torpedo 240 s aus, können einen Täuschkörper ausstoßen, lauern, schnorcheln (durch HFDF und ESM erfassbar) und pingen gelegentlich aus 15 sm oder weniger. In der Nähe der Fregatte kann ein U-Boot stattdessen zu einem kartierten Wrack innerhalb von 8 sm schleichen und sich 15-30 Minuten still daneben auf Grund legen.

Ein U-Boot mit ausgefahrenem Mast oder Schnorchel, das ein Flugzeugradar (Helikopter oder Seefernaufklärer) hört, geht auf Tiefe und schiebt das Schnorcheln 15 Minuten auf. In den Fregattenszenarien (1 bis 4) torpediert ein Patrouillen-U-Boot, das 10 Minuten keinen Ping und keinen Torpedo gehört hat, mehr als 2 Torpedos behält und mehr als 10 sm von der Fregatte entfernt ist, ein Handelsschiff innerhalb von 4 sm bei etwa einem von sieben seiner minütlichen Schussfenster; jedes verlorene Handelsschiff kostet 300 Punkte.

U-Boot-Physik: der Rumpf beschleunigt auf die befohlene Fahrt (kein Sofortsprint); Tiefenruder brauchen Fahrt (unter etwa 4 kn ändert sich die Tiefe nur langsam); das abgestrahlte Geräusch steigt je Verdopplung der Fahrt um etwa 12 dB und springt, wenn die Schraube kavitiert, wobei die Kavitationsfahrt mit der Tiefe steigt; ein Torpedoausstoß erzeugt 8 s lang ein Transientengeräusch; ein stark geflutetes U-Boot bläst einmal an und steigt schnell und laut auf; unter der Testtiefe ermüdet der Druckkörper, bei 1,5-facher Testtiefe wird er zerdrückt; ein lauerndes U-Boot hält seine Position gegen die Strömung.

U-Boote orten wie Sie: passive Peilungen aus dem eigenen Sonar, eine Entfernung erst nach eigenen TMA-Schlägen (einige Minuten), und ein Schuss auf diese TMA erst, wenn ihr Entfernungsfehler konvergiert ist (Schwierigkeitsfeld "Gegnerische Feuerleitkonvergenz": Sigma zu Entfernung höchstens 0,25 in den Patrouillenszenarien, 0,15 beim SSN; eine Lösung, die älter als 90 s ist oder durch Ihre Kursänderung wieder aufgeht, wird nicht beschossen), ESM nur mit ausgefahrenem Mast, den Datalink nur auf Masttiefe oder beim Schnorcheln, und ein Torpedoalarm braucht einige Sekunden Reaktionszeit der Besatzung (2-15 s), bevor das U-Boot ausweicht.

Überwasserschiffe verlieren bei schwerer See Höchstfahrt (kleine Schiffe mehr).

## Gegnerische Kommandanten {#ref-commanders}

- Jeder Computer-U-Boot-Kommandant und der Kapitän der KI-Jagdfregatte hat einen von vier Charakteren, durch den Seed festgelegt: **Draufgänger** (greift früh an, weicht kurz aus, lauert selten), **Fuchs** (lauert lange und weit, pingt wenig), **Vorsichtiger** (weicht lange aus, hält das Feuer zurück, hält Abstand) und **Jäger** (hartnäckig, läuft eine verlorene Peilung lange ab).
- Jeder Charakter ändert die vorhandene Taktik nur über Faktoren (Angriffsrate, Ausweichzeit, Lauerabstand; bei der Jagdfregatte Annäherungsfahrt, Pingabstand, Schussweite und Vorhaltezeit); über die vier gleichen sie sich aus.
- In etwa sechs von zehn Einsätzen deutet die Führung den Charakter nach 90 s an (*Der Nachrichtendienst hält den gegnerischen Kommandanten für ...*); die Nachbesprechung nennt ihn.
- **Eigene Pläne:** Jedes freie KI-U-Boot und die KI-Jagdfregatte wählen selbst einen Plan, ganz ohne Sprachmodell. Ein U-Boot, das die Fregatte hört, schließt heran (Draufgänger, Jäger), lauert unter der Sprungschicht (Fuchs) oder bleibt bei seiner Streife (Vorsichtiger); nach einem Ping geht es tief und schleicht oder schwebt lauschend unter der Schicht; beschädigt oder ohne Torpedos setzt es sich ab. Die Jagdfregatte sucht ohne Datum schnell, leise, in Sprints mit Lauschpausen oder normal, je nach Kapitän. Ausweichen, Lauern und Angriffe behalten Vorrang.

## Erschütterung, Trefferbild und Suchköpfe {#ref-shock}

- Eine Detonation innerhalb 0,6 sm vom eigenen Schiff lässt das Bild wackeln und das Licht flackern; innerhalb 0,15 sm springt kurz das Instrumentenglas. Beides ist nur Anzeige.
- Sieht die eigene Seite einen Treffer (Feuerball, Wassersäule eines Torpedos, ein sinkendes Schiff), öffnet sich an jeder Station für 8 s ein kleines Fenster in seine Peilung; ein nur gehörter Treffer öffnet es mit Peilung und Geräusch.
- Im Fernglas und im Sehrohr zeigt ein erkanntes Schiff Bugwelle und Kielwasser: hoch und weiß bei schneller Fahrt, kaum etwas bei langsamer.
- Der Suchkopf eines zielsuchenden Torpedos pingt langsam, solange er sucht, und schnell, sobald er aufgeschaltet hat. Fregatte und U-Boot hören das: *Torpedo hat aufgeschaltet*, *Peilung steht* (Kollisionskurs) und auf der Bedrohungsseite des U-Boots eine grobe Torpedouhr, die nach Gehör geschätzte Zeit bis zum Einschlag.

## Wertung {#ref-scoring}

| Posten | Punkte |
|---|---|
| Fregatte: U-Boot versenkt | je 1000 |
| Fregatte: nicht verschossener Torpedo | je 200 |
| Fregatte: keine zivilen Verluste | 500 |
| Fregatte: Zeitbonus | bis 500 |
| U-Boot: Fregatte versenkt | 1500 |
| U-Boot: Geleitzug versenkt | 1200 |
| U-Boot: Durchbruch oder Meldung | 1000 |
| U-Boot: Entkommen | 800 |
| U-Boot: Überlebt | 600 |
| U-Boot: unbeschädigt | bis 500 |
| U-Boot: verbliebener Torpedo | je 100 |
| Realismusfaktor | Einsteiger 75 %, Standard 100 %, Realistisch 125 % |
