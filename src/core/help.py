"""W0: Kontextbezogenes Hilfe-System (F1) – pro Station.

STATION_HELP[Station]: (Einleitung, [(Taste, Aktion), ...],
                        [Parameter/Erklärung], [Taktik-Hinweise])
"""

from src.core.station import Station

GLOBAL_HELP = (
    "Steuerung (alle Stationen):",
    [
        ("Tab / Shift+Tab", "Naechste / vorherige Station"),
        ("1 / 2 / 3 / 4", "Bruecke / Sonar / Waffen / Schaden"),
        ("5 / 6 / 7 / 8", "OPZ / Funk / Maschine / Helikopter"),
        ("P", "Pause / Weiter (nur P)"),
        ("Z / X oder [ / ]", "Zeitraffer langsamer / schneller (auch im Sonar)"),
        ("Auf / Ab", "Stationsbezogene Auswahl; Ruder nur auf der Bruecke"),
        ("U / V", "Bruecke: Zielkurs / Zielgeschwindigkeit"),
        ("+ / -", "Telegraph (auch im Sonar)"),
        ("F1", "Hilfe (diese Anzeige)"),
        ("N", "Nationen & Einheiten; im Sonar: Notchfilter"),
        ("S / L", "Speichern / Laden (Slots 1-5)"),
        ("Alt+Enter", "Vollbild (alle Stationen)"),
        ("Q / E oder Mausrad", "Karte: heraus-/hineinzoomen"),
        ("Drag", "Karte verschieben (Führungsstationen)"),
        ("K", "Karte: Kamera-Follow an/aus (Drag schaltet Follow aus)"),
    ],
)

STATION_HELP = {
    Station.BRIDGE: (
        "Brücke / Nautik – Navigation, Kurs & Fahrt, Missionsüberblick.",
        [
            ("Auf / Ab", "Ruder: Zielkurs ändern"),
            ("U", "Direkten Zielkurs eingeben (000-359)"),
            ("V", "Direkte Zielgeschwindigkeit eingeben (0-25 kn)"),
            ("+ / -", "Telegraph: Motorenbefehl (STOP-SLOW-HALF-FULL-FLANK)"),
            ("Karte", "Mausrad: Zoom, Maus-Drag: Pan"),
            ("Q / E", "Karte heraus-/hineinzoomen"),
        ],
        [
            "Fahrt = Lärm: Hohe Fahrt verschlechtert das passive Sonar und "
            "verratet die Fregatte. Kavitation ab 15 kn.",
            "Küsten: Fregatte kann nicht in Land fahren (Rückstoß).",
        ],
        ["Stillstand/4 kn = bestes Lauschen. Schnell anrennen, dann leise "
         "werfen – taktisch nutzen."],
    ),
    Station.SONAR: (
        "Sonarzentrale – LOFAR-Wasserfall, Kontakte, Peilungen, Ping, TMA.",
        [
            ("A", "Aktiv-Ping abfeuern (Kühlzeit, verrät Position!)"),
            ("B / Y", "B: Array wechseln Bug/Towed; Y: Towed waehlen"),
            ("Bild auf/ab", "Broadband / LOFAR / DEMON / TMA / Umwelt-Fusion"),
            ("E", "Bathythermograph: lokales Schallprofil messen"),
            ("U / V", "TAS/VDS-Solltiefe um 10 m heben / senken"),
            ("R", "Hoerpeilung direkt: 000 bis 359.9 Grad rechtweisend"),
            ("<- / ->", "Peilung +/-0.5 Grad; Shift: 5, Ctrl: 0.1"),
            ("Auf / Ab", "Kontakt fuer TMA und Klassifikation waehlen"),
            ("Enter", "Gemessener Kontaktpeilung folgen / manuell halten"),
            ("J | , / .", "Empfangston an/aus | Lautstaerke senken/erhoehen"),
            ("D", "Abhoeren: Breitband oder gefiltertes LOFAR-Band"),
            ("I / O", "Gain senken / erhoehen (3 dB)"),
            ("F", "Frequenzband wählen: breit / tief / mittel"),
            ("N", "Notchfilter gegen Eigenantrieb"),
            ("SPACE", "LOFAR Peak-Hold ein/aus"),
            ("T", "TMA für ausgewählten Kontakt ein/aus"),
            ("C", "Kontakt klassifizieren (U-Boot / Biologisch / Fahrzeug)"),
            ("M", "Ausgewählten Kontakt als Ziel setzen"),
        ],
        [
            "Passiv: nur Peilung (± Peilfehler je Array & Eigenfahrt).",
            "TMA: durch Manövrieren + Peilungsreihe wird Position + "
            "Geschwindigkeit des Ziels geschätzt (Konfidenz steigt), keine Tiefe.",
            "Wasserfall: neu oben, alt unten. Broadband: X = Peilung; "
            "LOFAR: X = Frequenz. Helligkeit = relativer Empfangspegel.",
            "Ton und Spektren stammen aus demselben synthetischen Hoerstrahl. "
            "Mehrere Quellen und Eigenrauschen koennen sich ueberlagern.",
            "DEMON: gemessene Modulation, keine sichere Blattfrequenz oder Identitaet. "
            "FFT-Fenster bis 2 s; nach Umpeilen mindestens 1 s neu auswerten.",
            "Gain wirkt auf Anzeige und Ton, nicht auf Detektion. D aktiviert "
            "Band/Notch im Ton; DEMON analysiert den ungefilterten Hoerstrahl.",
            "SNR: Signal/Rauschen aus Entfernung, Thermokline, Seegang, "
            "Eigenrauschen & Schleppsonar-Tiefe.",
            "Thermokline: Ziel darunter = Schattenzone (schlechter SNR).",
            "HMS und TAS laufen parallel; gleiche Peilungen bestätigen Tracks.",
            "Starke Arrayabweichung markiert einen möglichen Geisterkontakt.",
            "TAS unter die gemessene Sprungschicht fahren, um tiefe Ziele zu hören.",
        ],
        ["Erst passiv lauschen (langsam fahren), dann gezielt pingen. "
         "Ping = Waffe + Warnung an den U-Boot-Fahrer."],
    ),
    Station.WEAPONS: (
        "Waffenzentrale – Ziel, Torpedotiefe, Start, HSP-5.",
        [
            ("M", "Ziel setzen (aus Sonarkontakten)"),
            ("Auf / Ab", "Torpedotiefe (10-300 m)"),
            ("T", "Torpedo abfeuren (ROE-Prüfung)"),
            ("H", "HSP-5 starten / zurückrufen"),
            ("B", "Sonarbojen aussetzen (HSP-5 in Luft)"),
            ("D", "Leichttorpedo vom HSP-5"),
        ],
        [
            "ROE STD: Ziel muss geortet (Ping/TMA) + als U-Boot "
            "klassifiziert sein. ROE FREE: nur Klassifikation.",
            "Zieltiefe: aus aktivem Ping, nicht aus TMA; falsche Tiefe = Fehlschuss.",
            "Salven-Doktrin: max. 2 Drahttorpedos gleichzeitig in der Luft.",
        ],
        ["Tiefe erst aus Ping, dann Schuss. Dekoys: Signatur-Nachbau – "
         "Kontakt verliert dann Eigenfrequenzen."],
    ),
    Station.DAMAGE: (
        "Schadensbekämpfung – Kompartimente, Flutung, Brand, Reparaturteams.",
        [
            ("<- / ->", "Kompartiment wählen"),
            ("Auf / Ab", "Team 1-3 auswaehlen (ohne Zuweisung)"),
            ("Enter", "Gewaehltes Team dem gewaehlten Kompartiment zuweisen"),
            ("Backspace", "Gewaehltes Team zurueckziehen"),
            ("1-8", "Immer Station wechseln, keine Teamzuweisung"),
        ],
        [
            "ZUSTÄNDE: OK -> BESCHAEDIGT/FLUTEND -> ZERSTOERT.",
            "ZERSTOERT = Station unwiederbringlich verloren.",
            "Ab 60 % mittlerer Flutung über alle Räume sinkt die Fregatte.",
            "Feuer: breitet sich aus; Löschteams reduzieren es.",
            "Zuweisung nur zu reparierbaren Schaeden; belegte Kompartimente "
            "verdrängen kein anderes Team.",
        ],
        ["Priorität: Maschinerie & Sonarzentrale, dann Rumpf. "
         "Feuer sofort besetzen."],
    ),
    Station.OPZ: (
        "OPZ / CIC – Radar, AIS, ESM, Lagebild und ASM-Abwehr.",
        [
            ("Auf / Ab", "CIC-Track waehlen"),
            ("C", "NATO-Zugehoerigkeit setzen"),
            ("M", "CIC-Track an Sonar/Waffen uebergeben"),
            ("Bild Auf / Ab", "Radarbereich 5/10/20/40 NM"),
            ("<- / ->", "ASM-Track wählen"),
            ("E", "ESSM abfeuern (VLS-Cell)"),
            ("G", "Chaff abwerfen (8 NM-Kegel, Kühlzeit)"),
            ("R", "Seeraumradar an/aus (EMCON)"),
            ("Shift+R", "Luftraumradar an/aus (EMCON)"),
        ],
        [
            "Radar sieht Oberflaeche und ASMs; getauchte U-Boote bleiben unsichtbar.",
            "AIS liefert zivile Tracks; ESM liefert Bearing-only.",
            "NATO-Rahmen: Freund blau, Neutral gruen, Feind rot, Unbekannt gelb.",
            "CIWS: automatisch abfangend < 1.5 NM (begrenzt).",
            "JAMMER-ASMs: jenseits 20 NM nur HOJ-Peilung (Bearing-only).",
            "Radarclutter und Messstoerung beginnen erst bei Seegang 5.",
            "Chaff: Rakete bricht ab (40 %) oder wird kurz blind.",
        ],
        ["Erst Chaff + Manöver, dann ESSM gezielt. VLS-Zellen sind knapp."],
    ),
    Station.RADIO: (
        "Funkraum – HFDF-Peilungen, Teletype (HQ), Funkverkehr.",
        [
            ("Auf / Ab", "HFDF-Signal auswählen"),
            ("Enter", "Peilung mit eigener Position protokollieren"),
        ],
        [
            "HFDF: Peilung (±8°) sendender U-Boote (Schnorchel, HF).",
            "Teletype: HQ-Bulletins, Wetter, ROE-Änderungen.",
            "Protokollierte Peilstriche und Kreuzpeilungen erscheinen auf der Karte.",
        ],
        ["HFDF-Peilung + Sonar-Peilung -> Kreuzpeilung zur "
         "Positionsschätzung."],
    ),
    Station.ENGINE: (
        "Maschinenraum – Telegraph, RPM, Lärm, Maschinerie-Status.",
        [
            ("+ / -", "Motorenbefehl (Telegraph)"),
            ("Auf / Ab", "Telegraph runter / hoch"),
            ("A", "Akustikmodus LEISE/NORMAL"),
        ],
        [
            "Kavitation ab 15 kn: Lärm stark erhöht, passives Sonar bricht.",
            "Maschinerie gestört: Fahrt-Cap 15 kn; zerstört: 8 kn.",
            "Lärm % = eigene Detektions-/Verraten-Weite.",
            "LEISE reduziert Eigenlärm, begrenzt die Fahrt aber auf 12 kn.",
        ],
        ["Schnell anrennen (FULL/FLANK), dann SLOW zum Lauschen."],
    ),
    Station.HELICOPTER: (
        "Helikopter-Deck – HSP-5, Sonarbojen und Lufttorpedos.",
        [
            ("H", "HSP-5 starten / zurueckrufen"),
            ("Pfeile", "Wegpunktpeilung und -entfernung einstellen"),
            ("B", "Eine Sonarboje an aktueller Position aussetzen"),
            ("D", "Leichttorpedo abwerfen"),
        ],
        [
            "Der HSP-5 hat endliche Bojen- und Torpedovorraete; Starts laden nicht nach.",
            "Treibstoffende vor der Landung bedeutet Verlust des HSP-5.",
            "Bojen liefern passive Daten und bleiben bis zum Batterieverlust aktiv.",
            "Das Ziel muss vor dem Lufttorpedo-Einsatz als U-Boot klassifiziert sein.",
            "H/B/D sind auch in der Waffenstation verfuegbar. "
            "Dipping-Sonar ist nicht implementiert.",
        ],
        ["Bojenfeld vor der vermuteten Zielposition auslegen; danach HSP-5 "
         "rechtzeitig zurueckrufen."],
    ),
}


def get_help(station: Station) -> tuple:
    return STATION_HELP.get(
        station, ("Unbekannte Station.", [], [], []))
