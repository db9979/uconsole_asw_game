# Wiederaufnahme: neue Anweisung G-L (2026-09-07)

Stand 2026-09-07: Commander-Meilenstein A0-A5 abgeschlossen, Version 0.1.6,
Save v8 (v1-v8 ladbar). Am selben Tag neue Anweisung: Pakete G-L
(Crew-MessageBox, uConsole-Audio-Defekt, Bridge Lookout, Eloka/ESM-Station,
Webkonsole: Ein-Bildschirm/Anleitung/Kontakt-DB, Kontakt-Profile Real-Basis
Schema v2). Details: docs/plan-0.1.6.md, Abschnitt "G-L Umsetzung".
Pakete B-F bleiben vertagt, starten nach G-L nur mit erneuter Anweisung.

## Arbeitsbaum / Git

- Branch main; letzter Commit 3bf30bf (Harden world seed selection).
- Die vorausgehende Reviewarbeit UND Commander-Aenderungen sind uncommittet.
  Keine vorhandenen Aenderungen verwerfen oder mit einem alten Stand ersetzen.
- Neue Kernbereiche: src/commander/, data/commander/, Commander-Tests,
  Paketressourcen, Game-Options-/F9-Integration, Versions-/Anleitungsupdates.
- Kein Commit/Push ausgefuehrt. git diff --check sauber, Projektdateien auf
  GitHub-Tokenmuster geprueft. Vor Push Dateiauswahl und Gesamtdiff pruefen;
  Geheimnisse ausschliesslich ueber sichere lokale Anmeldung verwenden.

## Abnahme

- `.venv/bin/python -m pytest -q -p no:cacheprovider`: 1648 passed in 278.28s.
- `tools/smoke_full.py`: SMOKE-OK mit SDL-Dummy-Treibern.
- `tools/gen_contacts.py --check`: 106 Akustikprofile gueltig.
- sdist und Wheel 0.1.6 gebaut. Installiertes Wheel unter
  /tmp/opencode/u-jagd-commander-016 separat mit echter Loopback-Kopplung und
  Beobachtungs-API geprueft. Temporaere Testlistener sind beendet.
- Chromium-Vertragstests bei 1920/2560/3840 sowie 390 CSS-Pixeln.
- Echte Browserbilder mit Game/Bridge/Server ueber Loopback aufgenommen,
  Kopplung anschliessend widerrufen. Keine Livecodes in den Bildern.
- Physische Zwei-PC-LAN-, Firewall-, Audio- und uConsole-Dauerpruefung offen.

## Start / Bedienung

1. Spiel mit der lokalen .venv starten.
2. F10 > Commander LAN oder F9. Dienst standardmaessig aus.
3. Fuer den zweiten PC ausdruecklich lokale private IPv4 waehlen; 127.0.0.1
   ist nur fuer denselben Rechner. Port standardmaessig 8765, aenderbar.
4. Dienst einschalten, angezeigte URL im Browser oeffnen, Code eingeben:
   drei Ziffern plus drei Grossbuchstaben; fuenf Minuten gueltig.
5. Nach Kopplung lokal Aenderungen freigeben, Overlay schliessen.
6. Commander waehlt/klassifiziert/markiert; Zielvorschlag in F9 bestaetigen.
   Kein Fernfeuern/Steuern. Browserton bewusst mit Schaltflaeche einschalten.

Nur vertrauenswuerdiges LAN: HTTP ist unverschluesselt. Fuenf Fehlversuche pro
rollender Minute sperren weitere Versuche voruebergehend. Eine neue Verbindung
erbt keine alte Freigabe. Laden/Reset widerruft Kopplung am naechsten Pump.

## Naechster kleinster Schritt

Bei Wiederaufnahme zuerst diesen Stand und docs/plan-0.1.6.md (Abschnitt
"G-L Umsetzung vom 2026-09-07") lesen; falls gewuenscht Commit/Push-Freigabe
erledigen und die reale Zwei-Geraete-Abnahme durchfuehren. Dann mit den neuen
Anweisungen G-L beginnen, Reihenfolge:

1. H: uConsole-Audio knackt - Root-Cause messen (Framedauer um den
   0.25-s-Tick, engine_dropped_blocks), danach Puffer/DSP-Massnahmen.
2. G: Crew-MessageBox (nicht blockierend) fuer Ziel-/Navigationsvorschlaege
   an der uConsole; F9-Overlay bleibt bestehen.
3. L: Kontakt-Profile auf Real-Basis (Schema v2, Keys stabil, v1+v2 valid);
   Datengrundlage fuer J und K3.
4. K1: Webkonsole-Ein-Bildschirm-Layout (Tabs), K2: Anleitung EN/DE.
5. I: Bridge Lookout (2D-Topdown) im Commander-Browser.
6. J: Eloka (ESM-Zentrale) als 9. Station, K_9.
7. K3: Kontakt-Datenbank mit Radar-/Sonar-Fingerprints und generierten
   Analyse-/Silhouetten-Bildern.

Pakete B-F (Sonarhoerbild, Tastenkontrast/Maus/Stationenbilder, Batterie/AIP,
erweiterte Akustik, Grundberuehrung) bleiben vertagt und starten nach G-L
wieder **nur mit erneuter Anweisung**. Paket C (Stationenabnahme) umfasst
nach J neun Stationen. Die vormals vorhandenen Reviewkorrekturen sind davon
getrennt zu betrachten.

Details: commander-coop.md, commander-protocol.md, plan-0.1.6.md und
screenshots/commander-captures.md. Tokens/Codes niemals hier eintragen.
