# Commander-LAN-Koop (0.2.2)

[English](commander-coop.md)

Remote Crew belässt die Autorität beim uConsole-Prozess, während authentifizierte
Besatzungsmitglieder exklusive Stationsrollen über Browser bedienen. Ein Client
kann mehrere Leases behalten, zeigt aber immer nur eine aktive Station an. Der
optionale Dienst hat keine zusätzliche Laufzeitabhängigkeit und ist ausschließlich
für ein vertrauenswürdiges lokales IPv4-Netzwerk vorgesehen. HTTP schützt den
Datenverkehr nicht vor Personen, die das LAN beobachten können.

## Einrichtung

1. Starte das Spiel. Die Netzwerkfunktion ist unabhängig von Einstellungen oder
   Spielstand ausgeschaltet.
2. Öffne mit F10 die Optionen und wähle Commander LAN oder drücke direkt F9.
3. Waehle **vorhandenes LAN** oder **temporaerer U-Jagd-Hotspot**. Im LAN-Modus
   wird danach die lokale private IPv4-Adresse gewaehlt. Loopback 127.0.0.1 ist
   nur fuer Tests auf demselben Rechner bestimmt.
4. Der Hotspot-Modus benoetigt den einmalig installierten System-Helper aus der
   uConsole-Installationsanleitung. Beim Aktivieren trennt er voruebergehend das
   aktuelle WLAN und zeigt eine zufaellige SSID sowie ein neues WLAN-Passwort an.
   Beides wird weder gespeichert noch an Browser uebertragen.
5. Wähle einen Port, falls der Standardport 8765 belegt ist. Aktiviere den Dienst
   mit Enter. Erst nachdem der Hotspot eine private IPv4-Adresse erhalten hat,
   startet der Commander-Listener auf genau dieser Adresse.
6. Öffne in jedem Browser der Besatzung die tatsächlich angezeigte URL. Erlaube
   eingehende Verbindungen in der Host-Firewall bei Bedarf ausschließlich aus dem
   vertrauenswürdigen LAN.
7. Gib den lokalen Kopplungscode ein: drei Ziffern gefolgt von drei
   Großbuchstaben. Kleinbuchstaben aus dem Browser werden normalisiert. Der
   angezeigte Code bleibt für weitere Besatzungsmitglieder gültig. Fünf falsche
   Versuche innerhalb eines gleitenden Zeitfensters von einer Minute sperren
   weitere Versuche vorübergehend und erneuern den Code. Ein ausdrücklicher
   lokaler Widerruf erzeugt ebenfalls einen neuen Code und hebt die Sperre auf.
8. Fordere nach der Kopplung im Browser eine Station an. Der Host genehmigt oder
   verwirft genau diese Anfrage. Die Genehmigung aktiviert die normale
   Stationsbedienung; Sonar-Audio und Direktfeuer bleiben separate Freigaben. Wenn
   eine Besatzungsstation aktiv ist, läuft die Simulation hinter F9 weiter und F9
   kann für die Besatzungsverwaltung geöffnet bleiben.

Die geheime Sitzungszugangskennung wird in einem auf die v2-API beschränkten
HttpOnly-SameSite-Cookie gehalten. JavaScript, URLs, DOM, Einstellungen,
Spielstände und Protokolle erhalten sie niemals. Nach dem Neuladen kann dieselbe
Sitzung wiederhergestellt werden, die Stationsberechtigung läuft jedoch schnell
ab, wenn die Anwesenheitsabfrage aussetzt. Veröffentliche niemals echte
Kopplungscodes, Cookies oder CSRF-Token in Bildschirmfotos, Protokollen oder
Fehlerberichten.

## Rollensteuerung

- Der Host vergibt pro Station genau einen exklusiven Besitzer. Ein Client kann
  mehrere Stations-Leases behalten und zwischen ihnen wechseln, ohne die
  inaktiven Leases freizugeben. Verwende Station hinzufügen für eine weitere
  Anfrage; eine genehmigte Station wird automatisch geöffnet. Danach kann jede
  behaltene Lease über die stabile Stationsauswahl geöffnet werden.
- Eine Station mit aktiver Lease ist auf der uConsole schreibgeschützt, bis der
  Host ihre Lease widerruft. F9-Verwaltung, Pause und das Umschalten der lokalen
  Anzeige auf eine andere Station bleiben verfügbar; behaltene inaktive
  Browser-Leases bleiben exklusiv.
- Kontaktauswahl, Kartenverschiebung/-zoom/-verfolgung, Arbeitsplatzseiten,
  Entwürfe und Analyseauswahl bleiben lokal im jeweiligen Browser.
- Beim Überfahren eines deaktivierten Bedienelements wird der aktuelle lokalisierte
  Grund angezeigt. Die Gründe stammen ausschließlich aus veröffentlichtem Zustand
  und umfassen Freigaben, Phase, Schaden, Abklingzeit, Bestand, Auswahl und
  Handhabungsgrenzen. Beim TAS meldet der Browser, ob die Eigenschifffahrt unter
  3 kn oder über 12 kn liegt.
- Jede Station stellt nur ihre freigegebene, beobachtungsbasierte Projektion und
  ihre freigegebenen Bedienelemente bereit. Klassifizierung und Zuordnung bleiben
  Beurteilungen des Bedieners.
- Sichtbare Bezeichnungen entsprechen der jeweiligen uConsole-Station:
  Sonar/OPZ verwenden K-Bezeichnungen, HFDF verwendet öffentliche
  H-Bezeichnungen und ELOKA verwendet seinen öffentlichen Track-Schlüssel.
  Transportreferenzen bleiben undurchsichtig und werden nicht angezeigt. Nur
  modellierte AIS-Meldungen behalten Namen bei.
- Die Zuweisung aktiviert sofort die normale Bedienung dieser Station. Waffen
  benötigen zusätzlich die Direktfeuer-Freigabe des Hosts. Jede Aktion wird
  unmittelbar vor der Anwendung erneut anhand von Lease-Generation, Weltkontext,
  Aktualität, Bereitschaft, Schäden, Bestand, ROE und Einsatzbereich geprüft.
- Sonarkontakte werden ausdrücklich an OPZ freigegeben; die Klassifizierung allein
  veröffentlicht sie nicht. Sonar-Audio benötigt eine eigene Host-Freigabe und
  bleibt bei 1x ausschließlich live verfügbar. Seine Modi Broadband, Filtered und
  Heterodyne nutzen gemeinsam mit dem Sonar-Arbeitsplatz die maßgeblichen
  Einstellungen für Band, Notch und Gain.
- Die Sonarbesatzung kann Zielvorschläge und die Brückenbesatzung Kurs- und/oder
  Fahrtvorschläge bereitstellen. Vorschläge sind an die ursprüngliche v2-Sitzung,
  aktive Rolle, Stationsgeneration, den Weltkontext und die Beobachtungsreferenz
  gebunden. Ziel oder Navigationssollwerte ändern sich erst nach lokaler Annahme
  durch den Host.
- Das lokale Bedienfeld unterstützt unabhängige Entscheidungen über Anfragen je
  Station, zusätzliche Freigaben, Widerruf, Übernahme und Host-Steuerung. Ein Klick
  umgeht niemals die Bereitschaftsprüfung.
- Die Sprachkoordination erfolgt über eine vorhandene externe Sprachverbindung
  oder im direkten Gespräch. Es gibt weder integrierten Chat noch Mikrofonaufnahme
  oder allgemeine Befehlsausführung.
- Manuelle Pause, Fokusverlust, Speichern/Laden, Beenden, Nationen, echte Editoren,
  Menüs und der Splash-Sperrbildschirm sperren Remote-Änderungen. Bei einer aktiven
  Besatzungsstation lassen F1-Hilfe, der spielinterne F8-Analyzer, die
  F9-Besatzungsverwaltung und die F10-Optionen Simulation und Remote-Stationen
  weiterlaufen; ohne aktive Besatzung behalten sie ihr normales Pausenverhalten.
  Unbekannte oder veraltete Beobachtungen liefern nicht allein deshalb zusätzliche
  Informationen, weil Commander sie auswählt. Menü-, Editor- und Splash-Seiten
  geben keine vorgenerierte taktische Welt preis.

## Anzeige und Alarme

Nach der Kopplung wird die Oberfläche zu einem rollenspezifischen Arbeitsplatz.
Brücke, Sonar, Waffen, Schadensabwehr, OPZ, Funk, Maschine, Hubschrauber und ELOKA
verfügen jeweils über ein eigenes Instrument und begrenzte Bedienelemente. OPZ
blendet Radarreichweite und Radarumlauf über bekannter Kartengeografie ein;
Meldungen mit reiner Peilung bleiben Strahlen, anstatt erfundene Positionen zu
erhalten. Beim Wechsel auf eine behaltene Station wird unsicherer rollenlokaler
Zustand gelöscht, während die andere Lease bestehen bleibt. Anleitung und
Kontaktreferenzbibliothek bleiben verfügbar, ohne das taktische Bild einer anderen
Station offenzulegen.

Die Karte passt sich an Browsergröße und Gerätepixelverhältnis an und behält
gleiche Kartenmaßstäbe bei. Kontaktdetails zeigen das Alter von Beobachtung/Fix
sowie optional Reichweite/Tiefe/Bewegung. Beobachtungen mit reiner Peilung werden
als Strahlen dargestellt, nicht als erfundene Entfernungsfixes. Lokale Auswahl,
Commander-Vorschlag und Besatzungsziel haben unterschiedliche Umrandungen.
Die Hubschrauberkarte folgt dem fliegenden Hubschrauber statt dem Schiff und
bezeichnet ihre projizierten Sonarbojen kurz als `SB01`, `SB02` und so weiter.

Das Wetterinstrument der Brücke zeigt den maßgeblichen Tag-/Nachtzustand,
effektiven Seegang, Wetterart, Wind, Regen und Sicht. Seine zurückhaltende Wellen-
und Regenanimation folgt der projizierten Simulationszeit und friert bei Pause
ein. Die Helikopterbereitschaft zeigt Wetterfreigaben für Start und Tauchsonar
sowie Querwind getrennt an. Der Autocrew-Status ist in jeder Browserrolle nur
lesbar; gesteuert wird Autocrew lokal durch den Host.

Bei Sonar legt ein Klick oder Tippen in den Broadband-Wasserfall die manuelle
Hörpeilung fest und hebt die Kontaktverfolgung auf. Die gelbe Linie kennzeichnet
diese Peilung. LOFAR und die anderen Analysedarstellungen steuern den Hörstrahl
nicht.

Schadensstatus und Teamstärke, verfügbare eigene Waffen sowie die Position des
fliegenden Hubschraubers werden angezeigt. Ein im Hangar befindlicher oder
verlorener Hubschrauber wird nicht als aktuelles Luftfahrzeug eingezeichnet.
Missions-, Bedrohungs- und Schadensalarme basieren auf Beobachtungen. Wähle die
Sound-Schaltfläche, um Browser-Töne und das synthetisierte
Eigenschiff-Kavitationsgeräusch der Brücke zu aktivieren; Lautstärke und
Stummschaltung sind vom uConsole-Audio unabhängig. Das Kavitationsgeräusch verwendet
nur die Brückenprojektion und endet bei ruhiger Fahrt, veralteter Verbindung,
Rollenwechsel, Pause, versteckter Seite oder Stummschaltung. Autoplay kann vom
Browser bis zu dieser Geste gesperrt werden. Visuelle Alarme bleiben immer
verfügbar. Eine neue Verbindung setzt eine neue Ton-Ausgangsbasis, statt Alarme
erneut abzuspielen.

Ereignisse sind rollenbegrenzt: Schadensmeldungen erreichen Brücke und
Schadensabwehr, Bedrohungen Brücke, OPZ und Waffen und Missionsereignisse alle
Rollen. Der Lebenszyklus eines Vorschlags ist nur für Ursprungssitzung und
-rolle sichtbar. Mit lokaler SimLog-Freigabe erhält ein Browser höchstens 64
frühere Rollenprojektionen, niemals das vollständige Host-SimLog oder verborgene
Entity-IDs.

Eine Antwort über die Einreihung in die Warteschlange ist keine angenommene
Aktion. Bei unsicherer Zustellung hält der Browser die Aktion ausstehend. Seine
ausdrückliche Abgleichsteuerung wiederholt dieselbe Anfrage-ID/denselben Umschlag
mit einer Abklingzeit von fünf Sekunden; sie sendet niemals stillschweigend eine
neue Aktion und erfindet keinen Erfolg. Veralteter Kontext oder
Revisionskonflikte erfordern eine Prüfung des aktuellen Lagebilds. Der Server
meldet abgelaufene Aktionen in der Warteschlange als Ablehnungen.

## Lebenszyklus und Grenzen

Lokales Deaktivieren oder das Beenden des Prozesses stoppt zuerst den Listener und
widerruft Zugangsdaten. Ein vom Spiel gestarteter Hotspot wird danach entfernt und
die vorherige WLAN-Verbindung wieder aktiviert. Auch ein normaler Programmabbruch
schliesst den Steuerkanal des Helpers und loest diese Bereinigung aus.
Erfolgreiches Laden/Zurücksetzen ersetzt die
Netzwerksitzung beim nächsten Pump des Hauptthreads; Kopplung und Freigaben müssen
erneut erfolgen. Eine fehlgeschlagene Wiederherstellung eines Kandidaten lässt die
aktive Netzwerksitzung unverändert. Eine neue Verbindung übernimmt niemals die
Freigabe der vorherigen Verbindung.

Clients, Worker, Historien, Projektionen und Befehlswarteschlangen sind strikt
begrenzt. Snapshots werden normalerweise zweimal pro Echtzeitsekunde
veröffentlicht, wichtige Übergänge unmittelbar. Dies ist weder ein für das
Internet bestimmter Dienst noch ein VPN-Produkt oder Remote Desktop. Die exakte
Abgrenzung beschreibt [commander-protocol.de.md](commander-protocol.de.md).

## Abnahme / Pause

Die automatisierte Abdeckung verwendet echtes Loopback-HTTP und Headless-Chromium-
Verträge mit Desktop- und schmalen Viewport-Größen. Dies gilt nicht als Abnahme
für ein Netzwerk mit zwei physischen Geräten, Firewall, Kopfhörer,
uConsole-Thermik oder Lesbarkeit. Der aktuelle wiederaufnehmbare Arbeitsstand ist
in `docs/plan-0.1.8.md` und `docs/resume.md` festgehalten.
