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
| Überwasserradar | 30 sm | Radarhorizont; keine getauchten Kontakte |
| Luftradar | 100 sm | Flugzeuge und Flugkörper |
| ESM | 150 sm | +/-3 Grad Peilung |
| HFDF | 120 sm | +/-8 Grad Peilung |
| Ausguck | 12 sm Überwasser, 5 sm aufgetauchtes U-Boot, 20 sm Luft | x0,35 bei Nacht |

## Waffen und Gegenmaßnahmen {#ref-weapons}

| System | Daten |
|---|---|
| Fregattentorpedo | 45 kn, 12 sm (Batterie), drahtgelenkt (Schiff <= 20 kn, <= 1,5 Grad/s, 5 sm Spule), 2 Rohre, 60 s Nachladen, Tiefe 10-300 m, Annäherungszünder |
| Helikoptertorpedo | 55 kn, 12 sm, 2 je Einsatz, ohne Draht |
| Feindtorpedo | 28 kn, 30 sm, zielsuchend ab 3 sm |
| Nixie-Schlepptäuschkörper | 2 je Mission, 600 s, 0,2 sm achteraus, 60 s Nachladen |
| ESSM | 6 Flugkörper, 30 sm, 2 Feuerkanäle |
| CIWS | 1,5 sm, 180 Schuss, braucht Freigabe |
| Flak-Geschütz | 240 Schuss, braucht Freigabe |
| Düppel | 6 Ladungen, 8 sm, 40 % Zielverlust |

## Eigenes Schiff {#ref-ship}

| Merkmal | Wert |
|---|---|
| Fahrt | 4-25 kn; Telegraph STOP 0, SLOW 6, HALF 10, FULL 16, FLANK 25 kn |
| Drehrate | etwa 0,075 Grad/s je Knoten (1,2 Grad/s bei 16 kn); Drehkreis etwa 0,4 NM |
| Kavitation | ab 15 kn bei ruhiger See, bei schwerer See früher; Passivreichweite x0,35 |
| Modus LEISE | Lärm x0,65, max. 12 kn |
| TAS-Handhabung | 3-12 kn, ausbringen 360 s, einholen 480 s, Defekt über 20 kn |
| TAS-Tiefe | 20-260 m, minus 4 m je Knoten |
| Schaden | 9 Abteilungen, 3 Trupps; sinkt bei 60 % mittlerer Flutung |

## Umwelt {#ref-environment}

| Vorgang | Modell |
|---|---|
| Gezeit | M2 (12,42 h) + S2 (12 h), 0,4-1,4 m Amplitude, im Flachwasser größer |
| Deckschicht | jahreszeitliche Grundtiefe; nachmittags etwa 8 m flacher; vertieft sich bei Wind über 12 kn; interne Wellen +/-6 m |
| Schallgeschwindigkeit | Mackenzie-Gleichung aus dem Temperaturprofil (Oberfläche 8-18 Grad C je nach Jahreszeit) |
| Strömung | festes Feld bis 1 kn plus 3 % des Windes, 20 Grad rechts der Windrichtung |
| Meeresboden | Fels, Kies, Sand, Schluff oder Schlick; beeinflusst die Bodenreflexion |
| Hindernisse | bis zu 64 kartierte Wracks und Unterwasserfelsen (Spitzen mindestens 15 m tief) |

## Gegnerische U-Boote {#ref-subs}

| Klasse | Leisheit | Max. Tiefe | Torpedos |
|---|---|---|---|
| Diesel (älter) | 0,75 | 200 m | 4 |
| AIP (modern) | 0,85 | 250 m | 5 |
| Nuklear-Jagd-U-Boot | 0,92 | 400 m | 8 |

U-Boote weichen nach einem gehörten Ping oder Torpedo 240 s aus, können einen Täuschkörper ausstoßen, lauern, schnorcheln (durch HFDF und ESM erfassbar) und pingen gelegentlich aus 15 sm oder weniger.

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
