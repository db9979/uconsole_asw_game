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
| Passivsonar (Basis) | 20 sm | nur Peilung; HMS +/-6 Grad, TAS +/-2 Grad |
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
| Helikoptertorpedo | 55 kn, 12 sm, 2 je Einsatz, ohne Draht |
| Feindtorpedo | 28 kn, 30 sm, zielsuchend ab 3 sm |
| Nixie-Schlepptäuschkörper | 2 je Mission, 600 s, 0,2-sm-Kabel (10 m bei 15 kn, langsamer tiefer, reißt über 25 kn), 60 s Nachladen |
| ESSM | 6 Flugkörper, 30 sm, 2 Feuerkanäle |
| CIWS | 1,5 sm, 180 Schuss, braucht Freigabe; 115 Grad/s Schwenken, eigenes Folgeradar innerhalb 3 sm |
| Flak-Geschütz | 240 Schuss, braucht Freigabe |
| Düppel | 6 Ladungen, 8 sm, 40 % Zielverlust nach dem Aufblühen; Wolke treibt 90 s mit dem Wind |

## Eigenes Schiff {#ref-ship}

| Merkmal | Wert |
|---|---|
| Fahrt | 4-25 kn; Telegraph STOP 0, SLOW 6, HALF 10, FULL 16, FLANK 25 kn |
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
| Atmosphäre | Barometer 975-1025 hPa, das vor steigendem Seegang fällt; Lufttemperatur aus Wasser, Jahreszeit, Tageszeit und kaltem Nordwind (in Winterstürmen unter 0 Grad C: Schnee, Vereisung); Böen; Wolkenuntergrenze; Sonnenstand mit bürgerlicher/nautischer Dämmerung; Mondphase |
| Regenlinse | Regen süßt die obersten Meter aus (bis -1 PSU, vom Wind eingemischt) und senkt die Schallgeschwindigkeit an der Oberfläche |
| SOFAR-Kanal | ein inneres Schallgeschwindigkeitsminimum (etwa 400-500 m unter der Deckschicht) gibt es nur in ausreichend tiefem Wasser |

## Wetter- & Sonar-Analyse (Taste 0) {#ref-weather-station}

Taste `0` öffnet über jeder Station ein Analysepanel über den ganzen Bildschirm (`0` oder `Esc` schließt es; die Simulation läuft weiter). Im Web-Client öffnet jede Station es mit `0` oder über das Arbeitsplatz-Menü.

- **Umwelt:** Uhrzeit, Tageslicht (Tag, bürgerliche oder nautische Dämmerung, Nacht), Mondphase, Wetter und Niederschlag, Sicht, Wind mit Böen und Beaufort, Seegang, Barometer mit 3-Stunden-Tendenz (steigend, stabil, fallend, rasch fallend), Luft- und Wassertemperatur, Wolkenuntergrenze und Vereisung. Rasch fallender Luftdruck unter etwa 1004 hPa löst eine Sturmwarnung aus. Das Wetter ändert sich höchstens um eine Seegangsstufe pro Stunde, deshalb bewegt sich das Barometer schneller als ein echtes.
- **Wettereinflüsse:** Sonne (starke Sprungschicht), Wind (tiefere Deckschicht) und Regen oder Schnee (süßeres Oberflächenwasser, Regenrauschen) leuchten, solange sie wirken.
- **Helikopter-Flugwetter:** CLEAR, LIMITED (innerhalb von 80 % eines Grenzwerts oder leichte Vereisung) oder NO-GO, mit Wind, Böen, Seitenwind, Sicht, Wolkenuntergrenze, Seegang, Rollen und Stampfen des Decks, Vereisung und ob Tauchsonar möglich ist.
- **Meeresprofil:** erscheint erst, wenn das Sonar einen Bathythermographen genommen hat (Sonar `E`): gemessene Schallgeschwindigkeit über der Tiefe, die Schicht, eine SOFAR-Achse falls vorhanden, neun Schallstrahlen vom Bugsonar bis 20 sm und die Schattenzone unter der Schicht (rot), in der das Bugsonar wenig hört. Nach 30 min oder 10 sm gilt die Messung als veraltet.

## Karten-Plotwerkzeuge (Taste P) {#ref-plot}

Die Besatzung führt einen gemeinsamen Fettstift-Plot. Alle Stationen und alle Remote-Crew-Browser sehen dieselbe Zeichnung, und sie wird mit dem Spiel gespeichert. Es ist die eigene Zeichnung der Besatzung: nichts darin stammt von einem Sensor, und sie verändert die Simulation nie.

- **Öffnen:** `P` auf der Brücken-, Waffen- oder Helikopterkarte oder auf der OPZ-Karte drücken. Ein Cursor erscheint am Eigenschiff. Die Pfeiltasten bewegen ihn (Shift: schneller), oder auf die Karte klicken. `Enter` setzt einen Punkt, `Esc` bricht ein begonnenes Objekt ab und beendet danach den Plotmodus, `P` beendet ihn ebenfalls. Eine Hinweisleiste oben auf der Karte zeigt links das aktive Werkzeug und die Tasten, rechts Peilung und Abstand des Cursors vom Eigenschiff.
- **Werkzeuge:** `M` Marke (ein Punkt); `R` Lineal (zwei Punkte, zeigt Peilung und Entfernung); `B` Peillinie vom Eigenschiff durch den Cursor (eigene Position und Zeit werden gespeichert, die Linie bleibt also dort, wo sie gelegt wurde); `C` Kreis (Mitte, dann ein Punkt auf dem Radius, höchstens 200 sm); `D` Koppellinie (Startpunkt, dann ein Punkt in Fahrtrichtung, dann die Fahrt 0-60 kn eingeben). Die Koppellinie wandert mit der Zeit weiter und zeigt ihren CPA zu Kurs und Fahrt des Eigenschiffs.
- **Löschen:** `Rücktaste` löscht das Objekt, das dem Cursor am nächsten liegt. `Shift+Rücktaste` löscht den ganzen Plot.
- **Bezeichnungen:** Objekte werden als M1, R2, B3 usw. nummeriert. Im Web-Client kann vor dem Zeichnen eine Bezeichnung eingegeben oder ein Objekt in der Liste unter der Karte umbenannt werden.
- **Web-Client:** über der Karte ein Werkzeug wählen, dann einmal (Marke, Peillinie) oder zweimal (Lineal, Kreis, Koppellinie) klicken. „Trackpeilung plotten“ legt die gemessene Peilung des gewählten Tracks von dessen Beobachterposition an.
- **Grenzen:** höchstens 64 Objekte und 24 Zeichen je Bezeichnung.

## Gegnerische U-Boote {#ref-subs}

| Klasse | Leisheit | Max. Tiefe | Torpedos |
|---|---|---|---|
| Diesel (älter) | 0,75 | 200 m | 4 |
| AIP (modern) | 0,85 | 250 m | 5 |
| Nuklear-Jagd-U-Boot | 0,92 | 400 m | 8 |

U-Boote weichen nach einem gehörten Ping oder Torpedo 240 s aus, können einen Täuschkörper ausstoßen, lauern, schnorcheln (durch HFDF und ESM erfassbar) und pingen gelegentlich aus 15 sm oder weniger. In der Nähe der Fregatte kann ein Boot stattdessen zu einem kartierten Wrack innerhalb von 8 sm schleichen und sich 15-30 Minuten still daneben auf Grund legen.

U-Boot-Physik: der Rumpf beschleunigt auf die befohlene Fahrt (kein Sofortsprint); Tiefenruder brauchen Fahrt (unter etwa 4 kn ändert sich die Tiefe nur langsam); das abgestrahlte Geräusch steigt je Verdopplung der Fahrt um etwa 12 dB und springt, wenn die Schraube kavitiert, wobei die Kavitationsfahrt mit der Tiefe steigt; ein Torpedoausstoß erzeugt 8 s lang ein Transientengeräusch; ein stark geflutetes Boot bläst einmal an und steigt schnell und laut auf; unter der Testtiefe ermüdet der Druckkörper, bei 1,5-facher Testtiefe wird er zerdrückt; ein lauerndes Boot hält seine Position gegen die Strömung. U-Boote orten wie Sie: passive Peilungen aus dem eigenen Sonar, eine Entfernung erst nach eigenen TMA-Schlägen (einige Minuten), ESM nur mit ausgefahrenem Mast, den Datalink nur auf Masttiefe oder beim Schnorcheln, und ein Torpedoalarm braucht einige Sekunden Reaktionszeit der Besatzung (2-15 s), bevor das Boot ausweicht. Überwasserschiffe verlieren bei schwerer See Höchstfahrt (kleine Schiffe mehr).

## Mission und Wertung {#ref-mission}

- Szenarien: 1 Patrouille, 2 Doppeljagd, 3 Nuklear-Abfang, 4 Zufall (eigene Schwierigkeit). Eigene Missionen starten aus dem Missionseditor (`F5` in dessen Browser).
- Sieg: alle Ziele versenkt oder Zeitlimit überlebt. Niederlage: eigenes Schiff versenkt, ziviler Treffer, Ziel 150 sm vom Start entfernt oder Zeit abgelaufen.
- Punkte: 1000 je versenktem U-Boot, 200 je unverbrauchtem Torpedo, 500 ohne zivile Verluste, bis zu 500 Zeitbonus.

## Glossar {#ref-glossary}

| Begriff | Bedeutung |
|---|---|
| U-Jagd (ASW) | Anti-Submarine Warfare, Bekämpfung von U-Booten |
| HMS / TAS | Bugsonar / Schleppsonar (Towed Array) |
| LOFAR | Low Frequency Analysis and Recording: Frequenz-Zeit-Wasserfall |
| DEMON | Demodulated Noise: zeigt Blatt- und Wellenfrequenz |
| TMA | Target Motion Analysis, Zielbewegungsanalyse aus Peilungen |
| BT | Bathythermograph: misst Schallprofil und Sprungschicht |
| CZ | Konvergenzzone |
| Datum | Letzte geschätzte Zielposition für Waffen und Suche |
| OPZ / CIC | Operationszentrale / Combat Information Centre |
| ESM / ECM | Elektronische Unterstützung (passiv) / Gegenmaßnahmen (Stören) |
| HFDF | Kurzwellenpeilung (High Frequency Direction Finding) |
| EMCON | Emissionskontrolle: Radare aus |
| ROE | Einsatzregeln (Rules of Engagement) |

## Bildschirm-Abkürzungen {#ref-abbreviations}

Passt eine volle Beschriftung nicht auf den 1280x720-Bildschirm, zeigt die Station die Katalog-Abkürzung, statt den Text abzuschneiden. Das F11-Log und die Tooltips zeigen immer den vollen Wortlaut.

| Kurz | Bedeutung |
|---|---|
| KRS/FRT | Kurs / Fahrt |
| EGG, KAV | Eigengeräusch in %, Kavitation |
| SG/SCHICHT | Seegang / gemessene Schichttiefe (BT) |
| FLUT | Mittlere Flutung |
| TORP, VLS/DÜPP | Verbleibende Torpedos, VLS-Zellen / Düppel-Nachladen |
| HELO/ROE, HGR | Helikopterzustand / Einsatzregeln, Hangar |
| PLG, G, N | Peilung, Verstärkung, Notch |
| BB, FILT, HET | Breitband-, gefiltertes, Überlagerungs-Abhören |
| VERST, AUSBR, EINH, AUSGEBR, STAB | Schleppsonar verstaut, ausbringen, einholen, ausgebracht, Stabilität |
| BER, N/BER | Bereit, nicht bereit |
| UNB, FRD, NEU, FEI | Zugehörigkeit: unbekannt, Freund, neutral, Feind |
| SEE, UBT, LFT, FKR, TOR | Domäne: See, Unterwasser, Luft, Flugkörper, Torpedo |
| RDR S/L | Radar See / Luft |
| T, W, KZ | Tauchsonartiefe, Wassertiefe, Ping-Kühlzeit |
| P-Rate, Soll | Peilrate, Sollwert |
