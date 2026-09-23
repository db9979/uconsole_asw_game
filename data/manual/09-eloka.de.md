# 9 EloKa {#station-eloka}

## Zweck {#eloka-purpose}

Die Elektronische Kampfführung (EloKa) horcht passiv auf Radarsender (ESM) und stört sie auf Befehl (ECM). ESM erfasst Radare bis etwa 150 sm, weit jenseits des eigenen Radars, ohne selbst zu senden. Sie liefert Peilungen und Senderparameter, die auf einen Plattformtyp hinweisen, und warnt, wenn ein Flugkörpersucher aufschaltet.

## Anzeigen und Instrumente {#eloka-displays}

Seite 1 listet die Erfassungen; Seite 2 zeigt die Belege für die gewählte Erfassung (Frequenz, PRF, Modulation, Kandidaten, Korrelation).

```text
 ERFASSUNGEN                      Status  Bedroh. Band
 > E-07  Pg 312  9,3 GHz  PRF 2,4k  NEU     HOCH    X
   E-04  Pg 045  3,0 GHz  PRF 1,0k  TRACK   NIEDRIG S

 BELEGE E-07
   Frequenz 9,3 GHz   PRF 2400 Hz   Modulation Puls-Doppler
   Kandidaten (gerankt, nicht identifiziert):
     1. Flugkörpersucher     2. Feuerleitradar
   Korrelation: vereinbar mit OPZ-Track T-12 (Zeit/Peilung)
```

- Die Peilgenauigkeit beträgt etwa +/-3 Grad. Erfassungen sind Peilungen, keine Positionen.
- Kandidaten werden nur aus beobachteter Frequenz, PRF und Modulation gerankt. Ein Gleichstand ist keine Identifizierung.
- Die Korrelation mit Radar- oder Sonartracks nutzt vereinbare Zeit, Peilung und beobachtete Position, nie verborgene Identität.
- ESM läuft aus der OPZ-Abteilung: eine zerstörte OPZ legt es lahm.

## Tasten {#eloka-keys}

<!-- keys:eloka -->

## Standardablauf {#eloka-sop}

<!-- sop:eloka -->

## ECM-Techniken {#eloka-ecm}

| Technik | Wirkung |
|---|---|
| Rauschen | Überdeckt das Opferradar mit Breitbandrauschen |
| RGPO | Range Gate Pull-Off: zieht das Entfernungstor des Suchers weg |
| VGPO | Velocity Gate Pull-Off: zieht das Dopplertor weg |
| Falschziele | Speist falsche Echos ein |

Der Automatikmodus (`A`) wählt Ziele und Techniken und koppelt das Stören während eines Flugkörperangriffs mit Soft-Kill (Düppel).

## Tipps für Profis {#eloka-tips}

- ESM auch unter EMCON laufen lassen: es ist vollständig passiv.
- Wechselt eine Erfassung bei stehender Peilung von Suche auf einen Puls-Doppler-Sucher mit hoher PRF, steht ein Flugkörperangriff bevor: sofort die OPZ warnen.
- Das Zuordnen eines Radartyps (`C`) gibt die Peilung an die OPZ frei; das Löschen der Zuordnung zieht sie zurück.
- Stören ist eine Aussendung. Gezielt einsetzen, nicht dauerhaft.
- Das eigene Radar wird ebenfalls gehört: ein U-Boot auf Sehrohrtiefe (Mast oben, etwa 18 m) fängt es mit seinem ESM auf und kann die Peilung über seinen Datalink an andere Gegner weitergeben. Tief getauchte Boote hören weder Radar noch empfangen sie den Datalink.

## Nicht modelliert {#eloka-limits}

- Keine Fernmeldeaufklärung (COMINT); KW-Signale bearbeitet der Funkraum (HFDF).
- Keine Täuschkörperwerfer außer Düppel und keine geschleppten Radartäuschkörper.
