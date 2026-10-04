# U-Boot {#submarine}

## Überblick {#sub-overview}

Eine zweite Crew kann das U-Boot auf der uConsole oder im Browser spielen (Lobby, `F9` oder ein neues Spiel als U-Boot). Das U-Boot hat sieben Stationen; jeder Befehl wird nur von der Station angenommen, der er gehört, und eine KI besetzt jede freie Station, wenn die Crew-Hilfe an ist. Dieses Kapitel beschreibt jede Station, ihre Seiten und ihren Standardablauf; die Einsätze des U-Boots stehen im Kapitel Szenarien und Missionen.

Solange eine davon besetzt ist, folgt das lebende feindliche U-Boot mit der kleinsten Nummer nur den Befehlen dieser Crew; werden die Rollen abgegeben oder vom Host entzogen, übernimmt die KI das U-Boot wieder dort, wo es gerade ist. Ein Browser hält nur Rollen einer Seite (Fregatte oder U-Boot), nie beide; die Lobby fragt zuerst, welche Einheit er spielt.

![U-Boot-Stationen auf der uConsole im Überblick](figure:uboot-overview)

| Station | Seiten |
|---|---|
| 1 Führung | Navigation, Waffen & Kontakte, Sehrohr, Bedrohung |
| 2 Sonar | Breitband, LOFAR, DEMON, TMA, Umwelt, Aktiv (wie das Sonar der Fregatte) |
| 3 Waffen | Rohre und Feuerleitung |
| 4 Maschine | Anlage, Vorräte, Zellen, Leckwehr |
| 5 Mast & ESM | ESM, Sehrohr |
| 6 Navigation | Karte & Echolot, Navigation, Bedrohung |
| 7 Funk | Funk |

**Stationen:** Die *Führung* befiehlt Kurs, Fahrt und Tiefe, legt das U-Boot auf Grund, pingt (`Umschalt+A`), nimmt eine BT-Messung (die BT-Messung im Browser; auf der uConsole nimmt sie der Sonarraum) und sieht das ganze U-Boot. Die *Navigation* befiehlt Kurs und Tiefe, führt den Plot des U-Boots und überwacht Kiel und Hindernisse. Die *Maschine* bedient Telegraf, Schnorchel, Schleichfahrt, Trimm und Notanblasen und überwacht Batterie und Lärm. *Mast & ESM* fährt den Mast aus und überwacht ESM und Alarme; auch die Führung darf ihn ausfahren, um durchs Sehrohr zu sehen. Die *Waffen* schießen, lenken die Drähte und stoßen Täuschkörper aus. Das *Sonar* ist der Sonarraum des U-Boots. Der *Funkraum* nimmt den Rundspruch der Führung auf und sendet Lagemeldungen; er darf für seine Antenne den Mast ausfahren. Jeder Befehl wird nur von der Station angenommen, zu der er gehört.

**Was die U-Boot-Crew sieht:** das eigene U-Boot, die bekannte Seekarte, die eigenen Sonarmessungen und die eigenen Torpedos im Wasser. Position, Plot, Ereignisse und Missionsmeldungen der Fregatte sieht sie nie; die Fregatten-Crew kann ein besetztes U-Boot nicht von der KI unterscheiden.

Ein Spielstand bewahrt Befehle, Betriebsarten, Mast, Drähte, Plot, Alarmpeilungen, ESM-Bild und Funktagebuch der Crew; nach dem Laden fährt das U-Boot seine letzten Befehle weiter und wartet bis zu zehn Minuten darauf, dass seine Crew die Stationen erneut übernimmt (jede U-Boot-Station wird neu vergeben), bevor die KI es zurücknimmt.

### U-Boot am uConsole spielen {#ref-opfor-local}

Jedes neue Spiel fragt zuerst **Welche Einheit spielst du?**: *Fregatte F-217* oder *Feindliches U-Boot* (`Auf`/`Ab` oder `1`/`2`, `Enter`; die letzte Wahl ist vorausgewählt). Außerhalb einer Mission ändert auch Optionen (`F10`) Seite 2 **uConsole spielt** die Wahl, etwa vor dem Laden eines Spielstands. Mit dem U-Boot führt der uConsole das feindliche U-Boot statt der Fregatte. Die Fregatte wird dann über Remote Crew (`F9`) aus den Browsern besetzt; jede Fregattenstation, die kein Browser hält, besetzen die **KI-Jäger** (unten).

Der uConsole zeigt nur das Lagebild des U-Boots; Banner, Ereignislog, Soundeffekte, Plot und Tooltips der Fregatte erscheinen nie (die Lampenhinweise des U-Boots schon), und Trackball- und Telegraphenbedienung der Fregatte sind gesperrt. Die Seite lässt sich nur außerhalb einer Mission wechseln; die Wahl gilt nur für diesen Programmstart und wird nie gespeichert, jeder Start beginnt also mit der Fregatte.

Auf der uConsole wechseln `1` bis `7` die Stationen, dieselbe Zahl noch einmal (oder `Bild↑`/`Bild↓`) blättert die Seiten der Station. Jede Station hat unten eine Tastenleiste; ein Klick auf eine Taste dort, auf eine Lampe oder eine Skala wirkt wie die Taste. Die vollständige Tastentabelle steht am Ende dieses Kapitels; die Browser-Stationen haben dieselben Befehle als Schaltflächen.

Die obere Leiste zeigt die sieben Stationen des U-Boots als Reiter: `1` Führung, `2` Sonar, `3` Waffen, `4` Maschine, `5` Mast & ESM, `6` Navigation, `7` Funkraum (`Tab` oder ein Klick auf den Reiter wechselt), rechts Mission, Uhrzeit, Fahrt, Kurs und Tiefe. Jede Befehlstaste wirkt nur an der Station, zu der der Befehl gehört, wie im Browser; sonst nennt ein Banner die richtige Station. Browser können gleichzeitig die übrigen Stationen des U-Boots besetzen; eine Station, die ein Browser hält, ist in der oberen Leiste markiert und wird nicht vom uConsole bedient.

Jede Station außer dem Sonarraum ist aufgebaut wie die Brücke: links die Seekarte (bekannte Geografie, der eigene Plot des U-Boots, die ESM-Peillinien und Kreuzpeilungen, das eigene U-Boot mit Sollkurs und Fahrtvektor, die Peilstriche der eigenen Sonarkontakte bzw. ihr Symbol bei aktuellem Ping- oder TMA-Fix, die eigenen Torpedos `T1`…, ein begrenztes Schussfeld der Rohre), rechts die Station mit Bedrohungsleiste (Torpedoalarm und gehörtes Aktivsonar mit gemessener Peilung, Rumpfschaden, Kavitation, schwache Batterie, ESM-Radarerfassung) und die Seite der Station. Die Bedrohungsleiste erscheint nur, solange eine Bedrohung aktuell ist: ein gehörter Ping oder eine ESM-Erfassung füllt sie 30 s lang; danach steht in der oberen Leiste ein gelbes Dreieck mit der Zahl der anstehenden Warnungen, die Einzelheiten bleiben auf der Seite Bedrohung.

Unten stehen U-Boot-Log und Telemetrie des U-Boots, als Leiste oder Statuszeile wie in den Optionen eingestellt; Befehle, Schüsse und Täuschkörper werden dort protokolliert.

Tasten, die an jeder Station des U-Boots wirken (`F1` zeigt sie auf der uConsole zuerst):

<!-- keys:uboot_global -->

## Führung {#sub-command}

Die Führung sieht das ganze U-Boot: Karte, Navigation, Waffen und Kontakte, das Sehrohr und die Bedrohungsseite. Sie befiehlt Kurs, Fahrt und Tiefe, legt das U-Boot auf Grund, pingt, nimmt ein BT und weicht auf den frischesten Alarm aus.

- **Navigation (Seite 1):** die Karte mit den eigenen Kontakten und Peillinien, die Skalen für Kurs, Fahrt und Tiefe und der Tiefenbalken. `C`, `V` und `D` befehlen Kurs, Fahrt und Tiefe; `U`, `J` und `H` gehen auf Sehrohr-, Unter-Schicht- oder tiefe Tiefe (mit `Umschalt` Schnorchel- und Über-Schicht-Tiefe); ein Klick auf eine Skala befiehlt diesen Wert.
- **Waffen & Kontakte (Seite 2):** die Rohre und die Kontaktliste, wie die Waffenstation sie sieht, um den Angriff mitzuverfolgen.
- **Sehrohr (Seite 3):** der Blick durch den Kopf auf Sehrohrtiefe mit ausgefahrenem Mast. `←`/`→` schwenken, `↑`/`↓` neigen, `Q`/`E` schalten schwache und starke Vergrößerung, `Leertaste` den Stabilisator; `Enter` nimmt eine Stadimeter-Entfernung der Sichtung unter dem Fadenkreuz, `Strg+Enter` schießt auf die Lösung des Angriffsrechners.
- **Bedrohung (Seite 4):** die jüngsten Pings, Torpedogeräusche und Radarauffassungen mit ihren Peilungen. `I` weicht dem jüngsten Alarm aus, `Strg+B` klärt die Hecklücke, `G` ruft Gefechtsstationen.
- Die Führung pingt mit `Umschalt+A` auf der uConsole und im Browser. Das BT nimmt auf der uConsole der Sonarraum (`2`, `E`); im Browser kann es auch die Führung.

**Tiefenstufen und Anzeigen:** Führung und Navigation befehlen die Tiefe in einem Schritt: Sehrohrtiefe (15 m, der Mast bleibt nutzbar), Schnorcheltiefe (U-Boote mit Schnorchel), über oder unter der Schicht (15 m darüber / 30 m darunter; erst nach der eigenen BT-Messung, denn nur daraus kennt die Crew die Schicht) und tief (die sichere Tiefe über dem kartierten Grund). Auf der uConsole sind das `U`, `Umschalt+U`, `Umschalt+J`, `J` und `H`.

Der Browser zeigt die Wassersäule (Oberfläche, Sehrohrtiefe, gemessene Schicht, Soll-, sichere und Zerstörungstiefe, Grund, das U-Boot und seine Tauchrichtung), große Anzeigen für Kurs, Fahrt, Tiefe und Batterie mit farbigen Betriebs- und Alarmchips sowie eine ESM-Rose mit der Peilung jedes Emitters und den Peilungen von Ping- und Torpedoalarm; die Seite Mast & ESM am uConsole hat dieselbe Rose. Mast, Schnorchel, Schleichfahrt und Auf-Grund-Legen haben getrennte Knöpfe zum Ein- und Ausschalten.

**Navigation** (Führung Seite 1 und Navigation Seite 2) zeigt Kurs und Tiefe, das Wasser unter dem Kiel und ein kartiertes Hindernis voraus, Fahrt, Eigenlärm, Batterie und die aktiven Betriebsarten, darunter eine Reihe Rundinstrumente für Kurs (der befohlene Kurs als gelbe Marke), Tiefe (gelb jenseits der Testtiefe, rot jenseits der Zerstörungstiefe) und Fahrt wie auf der Brücke der Fregatte, sowie die Wassersäule unter dem U-Boot: U-Boot-Tiefe, befohlene Tiefe, sichere Tiefe und Grund; die Sprungschicht erscheint dort erst nach einer eigenen BT-Messung (`E` am U-Boot-Sonar).

![U-Boot-Führung auf der uConsole](figure:uboot-command)

![U-Boot-Führung im Remote-Crew-Browser](figure:web-uboot-desktop)

### Sehrohr, Stadimeter und Angriffsrechner {#sub-periscope}

Mit ausgefahrenem Mast zeigt die Seite **Sehrohr** (Führung Seite 3, Mast & ESM Seite 2; `P` fährt an beiden den Mast aus) das Okular im Stil des Startbilds: Himmel und See im Licht der Stunde (Tag, Dämmerung, Nacht mit Sternen und Mond), Wolken, Regen, Schnee und Nebel nach dem Wetter, den mit der See bewegten Horizont, eine Skala rechtweisender Peilungen und ein Fadenkreuz; das Rohr schwenkt in 2°-Schritten (`←`/`→`, `Umschalt`: 10°). Alles, was die Optik im Kontrastmodell des Fregattenausgucks bei 2,5 m Augenhöhe ausmacht (Tag/Nacht, Mond, Sicht, Seegang, Land im Weg), erscheint als Silhouette und als reine Peilungs-**Sichtung** mit grober Klasse (Kriegsschiff, Handelsschiff, Fahrzeug, Luftfahrzeug, Torpedolaufbahn) und scheinbarer Länge; das Log meldet jede neue Sichtung. Neutrale Schiffe zeigen hier ihre Positionslichter wie im Fernglas der Brücke. Ausgemachte Schiffe, U-Boote und Luftfahrzeuge erscheinen wie im Fernglas als gedrehte 3D-Modelle, in der vollen Länge, die sich aus scheinbarer Länge und geschätztem Lagewinkel ergibt, jeweils als Modell ihres echten Typs; die Sichtung der Besatzung nennt weiter nur die grobe Klasse.

`↑`/`↓` neigen den Kopf um 2° (`Umschalt`: 10°, von 10° nach unten bis 60° nach oben, für Flugzeuge), `Q`/`E` wechseln wie beim Fernglas der Fregatte zwischen kleiner (32° Feld) und großer Vergrößerung (8°), und die `Leertaste` schaltet die Stabilisierung; Neigung und Feld stehen in der Bildecke. Diese Einstellungen gehören zum Okular der uConsole oder jedes Browsers, ändern nur das Bild (nicht, was die Optik erkennt) und werden nicht gespeichert. Ein Hubschrauber in Sicht hängt in seinem wahren Höhenwinkel über der Kimm im ruhigen Himmel, hinter den Wolken. In Fahrt strömt das Wasser mit der eigenen Fahrt des U-Boots dicht unter dem Okular vorbei (voraus auf das Auge zu, querab vom Bug zum Heck). Ein Schiff mit Stadimeter-Entfernung steht so weit unter der Kimm, wie das niedrige Auge seine Wasserlinie sieht (auf 0,5 sm kaum ein Zehntel Grad), ein näheres Schiff vor einem ferneren.

`Enter` liest das **Stadimeter** an der Sichtung unter dem Fadenkreuz ab: die Entfernung folgt aus der scheinbaren Länge und der angenommenen Rumpflänge der Klasse (130 m für ein Kriegsschiff oder ein nicht erkanntes Fahrzeug, 150 m für ein Handelsschiff), ein nicht erkanntes oder bugwärts stehendes Ziel misst sich also zu weit; die Ablesung ist ±25 % und wird für 120 s zu einem VISUAL-Fix am Sonarkontakt des U-Boots auf dieses Ziel, für einen Schuss nutzbar wie ein Ping-Fix. Luftfahrzeuge und Laufbahnen lassen sich nicht messen.

Jede Ablesung ist zugleich eine **Marke** für den **Angriffsrechner**: aus zwei oder mehr Marken im Abstand von mindestens einer Minute (die letzten sechs innerhalb von 15 Minuten) legt er eine Gerade durch Kurs und Fahrt des Ziels und zeigt mit der Torpedogeschwindigkeit den Vorhaltewinkel (links oder rechts der Peilung) und die Laufzeit unter dem Sehrohr (Browser: Spalte Lösung); die Güte wächst mit der Zeit zwischen erster und letzter Marke (voll nach 5 Minuten) und mit der Zahl der Marken. `Strg+Enter` auf der Sehrohrseite (Browser: Schuss nach Lösung, nur die Führung) schießt nach der Lösung der Sichtung unter dem Fadenkreuz: der Torpedo läuft auf dem Abfangkurs zu dem Punkt, an dem Ziel und Torpedo zusammentreffen. Ein Schuss auf den Sonarkontakt eines markierten Ziels nutzt die Lösung ebenfalls. Ein Ziel, das nach der letzten Marke dreht, lässt die Lösung hinter sich; eine Anpassung schneller als 40 kn wird als schlechte Marke verworfen. Die Marken gehören zum Spielstand.

Die kartierte Küste steht auf dem Horizont des Sehrohrs, so weit seine niedrige Optik Land sieht (Hügel mit 25 bis 70 m angenommen). Die Führung kann auch ohne Sonarbediener pingen und eine BT-Messung nehmen. Die Karte zeigt das Schussfeld der Rohre, wo sie nicht rundum schießen, und das vom Sonar zugewiesene Ziel ist für den Schuss vorausgewählt.

![Sehrohr bei Tag](figure:uboot-periscope-day)

![Sehrohr bei Nacht](figure:uboot-periscope-night)

![Sehrohr im Remote-Crew-Browser](figure:web-periscope-day)

### Bedrohung und Ausweichen {#sub-threat}

**Lagebild:** ein gehörter Aktivping oder Torpedo wird mit der Peilung protokolliert, die das U-Boot selbst gemessen hat (einige Grad ungenau), und mit seinem Alter in den Alarmen angezeigt. Auf Sehrohrtiefe lässt sich der **Mast** ausfahren; sein ESM meldet dann die Radare, die das U-Boot überstreichen, mit Peilung (Log und ESM-Liste), und beim Tieferkommen fährt der Mast selbst ein.

Der Sonarraum des U-Boots unterscheidet einen aufgefangenen Aktivping an seiner Frequenz als Rumpfsonar der Fregatte, Tauchsonar eines Hubschraubers oder Sonoboje und protokolliert ihn mit gemessener Peilung und Empfangspegel (dB re 1 µPa, aus Quellpegel, Ausbreitung und Absorption); eine pingende Boje im Umkreis von 12 sm hört nur ein bemanntes U-Boot. Eine Boje, die im Umkreis von 4 sm ins Wasser fällt, wird mit grober Peilung (±6°) gehört; eine Salve des U-Jagd-Raketenwerfers der Fregatte, die im Umkreis von 3 sm einschlägt, wird mit ihrer Peilung gemeldet, während ihre Ladungen sinken (etwa 11 m/s): Zeit, die Tiefe zu wechseln oder darunter wegzulaufen; ein Torpedoalarm bleibt mit seiner Peilung stehen.

Die Seite **Bedrohung** (Führung Seite 4 und Navigation Seite 3; im Browser die Karte Bedrohung an Führung und Navigation) zählt die Pings der letzten 5 Minuten nach Quelle, nennt den lautesten Pegel mit Bewertung (ab 150 dB hat der Pinger wahrscheinlich ein Echo) und den Trend der letzten beiden Pings (steigend: er kommt näher), Splashes, Torpedoalarme und ESM-Emitter, die eigene Signatur (Tiefe gegen die gemessene Schicht, Eigenlärm: kavitierend, schnorchelnd, laut, mäßig oder leise, der Mast) und die Empfehlungen der Crew. Die Karte zeichnet jede Auffassung der letzten 2 Minuten als gestrichelten Peilstrahl.

**Ausweichen** (`I` an Führung oder Navigation, im Browser die Schaltfläche **Ausweichen**) gibt den Ausweichbefehl der Crew zum frischesten Alarm (unter 2 Minuten): gegen einen Torpedo die kleinere Wende, die ihn 150° achteraus legt, Höchstfahrt und ein Täuschkörper; gegen Aktivsonar das Heck zum Pinger, Schleichfahrt mit 3 kn. Beide wechseln durch die gemessene Schicht (nach unten, wenn das U-Boot darüber oder darin steht, nach oben, wenn es darunter steht), ohne BT gehen sie auf Tiefe; ein aufgesetztes U-Boot hebt zuerst ab. Der Befehl durchläuft dieselben Prüfungen wie die Einzeltasten, und die Seite zeigt ihn, bevor er gegeben wird. Das Bild ist nur Anzeige und wird nicht gespeichert.

<!-- sop:uboot_command -->

## Sonar {#sub-sonar}

Der Sonarraum des U-Boots arbeitet wie der der Fregatte, ohne Schleppsonar, OPZ-Freigabe, Plot und Telegraph. Achteraus ist das Rumpfsonar in der Hecklücke taub.

- Die sechs Seiten und ihre Tasten sind die des Fregattensonars (Kapitel 2 Sonar): Breitband-Wasserfall, LOFAR-Linien, DEMON-Wellendrehzahl, TMA, Umwelt mit BT, aktive Pings mit `Umschalt+A`.
- Das Rumpfsonar horcht in der eigenen Tiefe: über der Schicht hört es Überwasserschiffe gut, darunter ist es gegen sie abgeschirmt. Achteraus liegt die taube Hecklücke; deshalb ab und zu bei der Führung ein Klären der Hecklücke anfordern.

![U-Boot-Sonar](figure:uboot-sonar)

![U-Boot-Sonar im Remote-Crew-Browser](figure:web-uboot-sonar-desktop)

<!-- sop:uboot_sonar -->

## Waffen {#sub-weapons}

Die Waffenstation lädt und flutet die Rohre, stellt Lauftiefe und Fächer ein, schießt auf einen gewählten Kontakt oder eine eingegebene Peilung, lenkt die drahtgelenkten Torpedos und stößt Täuschkörper aus. Die Seite hat neben der Karte zwei Spalten: Kontaktkarten (ein Klick wählt einen Kontakt) über der Schusslage sowie die Feuerleitung über den Rohrlampen. Der Feuerleitkasten zeigt die Suchkopf-Einstellung der nächsten Schüsse; an der Waffenstation feuert ein Klick auf das rote Feuerfeld wie `Strg+Enter`. Unter den Voreinstellungen fluten Tastenchips das nächste trockene Rohr (`Shift+M`, leise `Strg+M`) und stoßen einen Täuschkörper aus (`V`), und ein Klick auf eine Rohrlampe lädt ein leeres Rohr (`M`) oder flutet ein trockenes (`Shift+M`).

- **Rohre:** jedes Rohr ist leer, geladen (trocken) oder geflutet; nur ein geflutetes Rohr feuert. `M` lädt das nächste leere Rohr, `Strg+M` flutet das nächste geladene langsam (60 s, kaum hörbar), `Umschalt+M` schnell (20 s, laut).
- **Feuerleitung:** `↑`/`↓` wählen einen Kontakt mit frischer Entfernung, `T` stellt die Lauftiefe, `Y` Einzelschuss oder Zweierfächer, `X` das Suchmuster und `,`/`.` den Scharfschaltpunkt; `Strg+Enter` schießt. `F` schießt ohne Kontakt: Peilung eingeben und `Enter`, dann die Entfernung zum Datum (leer: 10 sm in Schussrichtung) und `Enter`, und `Strg+Enter` schießt; `Enter` allein schießt nie.
- **Draht und Täuschkörper:** `W` lenkt den jüngsten drahtgelenkten Torpedo auf eine neue Peilung, `Umschalt+W` kappt den Draht; `V` stößt einen Täuschkörper aus.

**Waffen** (Seite und Station Waffen) zeigt Feuerbereitschaft, Torpedos, klare (geflutete) Rohre, Nachladen, Täuschkörper, Notanblasen, eine Zeile mit den Rohren, die nicht klar sind (`M` lädt das nächste leere Rohr, `Shift+M` flutet das nächste trockene, `Strg+M` flutet es langsam und leise) und die eigenen Sonarkontakte (Peilung, Entfernung falls bekannt, und Güte in Prozent: der bessere Wert aus Signalgüte und Spurvertrauen, 100 % ist ein sicherer Kontakt), darunter die Schusslage des gewählten Kontakts wie bei der Fregatte (Torpedoreichweite, Peilung, geschätzte Position, Treffpunkt und Torpedolaufbahn, nur aus der eigenen Beobachtung des U-Boots).

**Befehle und Waffen:** das U-Boot folgt Kurs-, Fahrt- und Tiefenbefehlen im Rahmen seiner Wende-, Tiefen- und Beschleunigungsgrenzen; Fahrtstufen (Stopp, 3, 6, 10, 15 kn, Maximum) setzen die Fahrt schnell. Schießt einen Torpedo auf die gemessene Peilung eines Sonarkontakts, mit Ping-Fix oder TMA-Lösung, solange aktuell, oder auf eine freie Peilung mit optionaler Entfernung; der Schuss braucht ein geflutetes, geladenes Rohr und das Ziel im Schussfeld der Rohre.

**Rohre:** Die Crew übernimmt die geladenen Rohre geflutet. Ein leergeschossenes Rohr bleibt leer, bis die Torpedogasten es aus den Reserven laden, sofern dort noch ein Torpedo liegt (`M` an der Station Waffen, Browser: Laden; jedes U-Boot führt mindestens noch einmal so viele Reservetorpedos wie Rohre, und das Laden dauert 2 min auf einem Atom-U-Boot, 3 min auf einem konventionellen und 4 min auf den älteren Dieselklassen, langsamer bei verbrauchter Luft); ein geladenes Rohr ist trocken und muss vor dem Schuss geflutet werden, was die Mündungsklappe öffnet, 20 s dauert und 4 s lang wie ein kurzer Transient hörbar ist, den das Sonar der Fregatte bis 8 sm hört (`Shift+M`, Browser: Fluten); langsames Fluten dauert 60 s und ist nur bis 1,5 sm zu hören (`Strg+M`, Browser: Leise fluten). Die Station Waffen und der Browser zeigen jedes Rohr als leer, lädt, trocken, flutet oder klar, und das Log meldet jedes geladene und geflutete Rohr. Die U-Boote der KI laden und fluten selbst: leise und früh, sobald sie die Fregatte innerhalb von 15 sm geortet haben, laut und kurz vor dem Schuss, wenn sie mit trockenen Rohren schießen müssen.

Die Crew stellt die Lauftiefe ein (5-300 m, sonst eine flache Voreinstellung) und schießt einen Torpedo oder zwei im Fächer von ±4°, jeder mit eigenem Datum. Jeder Crew-Torpedo läuft am Draht: die Crew kann sein Datum versetzen (Peilung und Entfernung vom U-Boot), und der Draht dreht ihn darauf ein, bis sein Suchkopf erfasst; schneller als 10 kn oder stärker als 1,5°/s drehen für 5 s lässt den Draht reißen, ebenso eine abgelaufene Spule, und die Crew kann ihn kappen. Stößt einen Täuschkörper aus und bläst im Notfall die Hauptzellen an (mit voller Pressluft dreimal).

![U-Boot-Waffen](figure:uboot-weapons)

![U-Boot-Waffen im Remote-Crew-Browser](figure:web-uboot-weapons-desktop)

### Torpedo-Suchkopf {#sub-seeker}

- `X` schaltet das Suchmuster der nächsten Schüsse weiter: gerade (wie bisher), Schlange, Kreis oder Helix. Der Torpedo läuft gerade zum Datum; ist sein Suchkopf an und hat nichts gefunden, sucht er in diesem Muster.
- `,` und `.` verschieben den Einschaltpunkt zwischen 0,6 und 3,0 sm vor dem Datum in Schritten von 0,2 sm (Vorgabe 3,0 sm). Ein später Einschaltpunkt hält den Suchkopf länger blind, so dass er Täuschkörper und andere Schiffe auf dem Weg nicht nimmt.
- Ein Torpedo im Wasser behält die Einstellung, mit der er geschossen wurde; die Waffen-Karte im Browser stellt beides mit **Anwenden** ein.

<!-- sop:uboot_weapons -->

## Maschinenraum {#sub-engine}

Der Maschinenraum fährt Telegraph, Schnorchel und Laderate, Schleichfahrt, die Trimmzellen und das Notanblasen, hält die Luft atembar und führt die Leckwehrtrupps.

- **Anlage (Seite 1):** Telegraph (`+`/`-`), Schleichfahrt (`A`, höchstens 5 kn), Schnorchel (`N`) und die Werte von Batterie, Diesel und E-Maschine.
- **Vorräte (Seite 2):** Batterie, Kraftstoff, Kohlendioxid und Sauerstoff. `R` schaltet die Laderate beim Schnorcheln (voll, halb, nur Luft), `Umschalt+O` setzt einen frischen Absorbersatz ein, `O` zündet eine Sauerstoffkerze.
- **Zellen (Seite 3):** Regel- und Trimmzellen. `↑`/`↓` lenzen oder fluten die Regelzelle, `←`/`→` verschieben Trimmwasser, `Z` schaltet die Trimmautomatik; `Umschalt+B` ist das einmalige Notanblasen.
- **Leckwehr (Seite 4):** die Abteilungen mit Wasser, Lecks, Feuer und Gas. `↑`/`↓` wählen eine Abteilung, `←`/`→` eine Aufgabe, `Enter` schickt Trupp 1 (`Umschalt+Enter` Trupp 2), `I` schließt oder öffnet ihre Schotten; `W`, `M` und `U` lösen die Wache ab, schicken den Sanitätstrupp und besetzen die am schwersten getroffene Station neu.

Die **Maschine** ist ein Leitstand: Rundinstrumente für Fahrt (die befohlene Fahrt als gelbe Marke), Batterie (beim Atom-U-Boot die Tiefe) und Eigenlärm, Lampen für Schleichfahrt, Schnorchel, Auf Grund, Kavitation, Notanblasen und den Anlagenzustand sowie die Telegrafenstufen.

![U-Boot-Maschine](figure:uboot-engine)

![U-Boot-Leckwehr (Maschine, Seite 4)](figure:uboot-damage-control)

![U-Boot-Maschine im Remote-Crew-Browser](figure:web-uboot-engine-desktop)

### Anlage und Vorräte {#sub-plant}

**Anlage und U-Boot-Betrieb:** ein besetztes U-Boot taucht nie von selbst auf, schnorchelt nicht und funkt nicht von selbst. Die Batterie entlädt sich mit Fahrt und Bordnetz; unter 20 % warnt das U-Boot-Log, eine leere Batterie begrenzt die Fahrt auf das, was die Anlage noch liefert (eine AIP-Anlage übernimmt die Last weiterhin selbst).

**Schnorcheln** betreibt die Diesel auf Schnorcheltiefe und lädt die Batterie, höchstens 6 kn; tieferes Tauchen schließt das Kopfventil. Die laufenden Diesel sind laut: +12 dB abgestrahlter Pegel, ein niedrigerer Stillefaktor und zwei Zündlinien bei 50 und 100 Hz in der LOFAR-Signatur des U-Boots (auch bei KI-U-Booten). **Schleichfahrt** begrenzt das U-Boot auf 5 kn und macht es so leise wie ein lauerndes KI-U-Boot. **Auf Grund legen** stoppt das U-Boot 3 m über dem Grund, wo das Wasser nicht tiefer als die Tauchtiefe ist: leise und ohne Drift; jeder Fahrt- oder Tiefenbefehl hebt ab. Vor Land oder einer Untiefe stoppt das U-Boot, statt auszuweichen, und das Log warnt bei wenig Wasser unter dem Kiel.

**Energie und Vorräte:** die Maschine zeigt unter **Energie & Vorräte** (Karte im Browser, auf der uConsole Maschine Seite 2 **Vorräte**) die Energiebilanz bei der aktuellen Fahrt (Verbrauch, Erzeugung und Bilanz in kW, die Zeit bis die Batterie leer oder voll ist), Batterie und AIP-Sauerstoff, die Dieselbunker und eine Tabelle, wie lange die Batterie getaucht bei jeder Telegrafenstufe reicht und wie weit das U-Boot damit kommt (auf der uConsole Tanksäulen für Batterie, AIP-Sauerstoff, Diesel und Absorber und ein Balken je Telegrafenstufe).

**Diesel:** die Bunker fassen 300 Stunden volle Generatorleistung, eine Fahrt beginnt mit 65 %; nur laufende Diesel verbrauchen (0,27 l je kWh), das Log warnt bei 10 %, und mit leeren Bunkern lädt Schnorcheln nicht mehr. Die **Laderate** bestimmt, was Schnorcheln tut: *voll* (die ganze Generatorleistung, +12 dB und beide Diesellinien), *halb* (die halbe Leistung, +9 dB, schwächere Linien) oder *nur lüften* (die Lüfter ohne Diesel, +4 dB, keine Linien).

**Luft:** getaucht verbraucht die Crew Sauerstoff und atmet Kohlendioxid aus (je etwa 0,45 % pro Stunde); ein CO2-Absorbersatz nimmt CO2 auf, bis er verbraucht ist (8 Ersatzsätze), eine O2-Kerze setzt in 15 Minuten 1 % O2 zu (12 an Bord, eine zur Zeit), und Schnorcheln lüftet das U-Boot in wenigen Minuten Richtung Frischluft. Ab 3 % CO2 oder unter 18 % O2 ist die Luft verbraucht, ab 5 % CO2 oder unter 16 % O2 gefährlich; das Log warnt bei jeder Stufe. Schlechte Luft macht die Crew langsamer (bis 30 % Leistung), und die Torpedomannschaft lädt entsprechend langsamer nach. KI-U-Boote versorgen ihre Luft selbst und tauchen zum Lüften auf, wenn sie gefährlich wird. Ein Atom-U-Boot hat keine dieser Vorräte.

Die zweite Seite der Maschine, **Vorräte**, zeigt Energie, Ausdauer und Luft; `R` wechselt die Laderate, `Shift+O` setzt einen Absorbersatz ein und `O` zündet eine O2-Kerze.

### Zellen, Trimm und Luft {#sub-tanks}

Die Maschine zeigt unter **Tauchzellen & Trimm** (Karte im Browser mit Schnittbild des U-Boots, auf der uConsole Maschine Seite 3 **Zellen**) die Hauptzellen, die Regelzelle, die Trimmzellen, die Pressluft und den Trimmzustand des U-Boots.

Jede Gewichtsänderung bringt das U-Boot aus dem Gleichgewicht: ein Torpedo aus einem Bugrohr macht es 1,5 t leichter und achterlastig, Wasser in vollgelaufenen Abteilungen (siehe Leckwehr) macht es schwerer und trimmt es zum gefluteten Ende; die Trimmautomatik gleicht davon aus, was ihre Zellen fassen. Mit der **Trimmautomatik** pumpt der LI die Regelzelle (±8 t, 25 kg/s) und die Trimmzellen (±3 t vorn und achtern, 15 kg/s) zurück ins Gleichgewicht; von Hand verschiebt jeder Befehl die Regelzelle um 0,5 t oder das Trimmwasser um 0,25 t (und schaltet die Automatik aus). Laufende Trimmpumpen sind hörbar (+3 dB und eine Linie bei 120 Hz). Was die Zellen nicht aufnehmen, lässt das U-Boot mit 0,03 m/s je Tonne sinken oder steigen, und ein Trimmwinkel (1° je Tonne Moment, + vorlastig) drückt es mit Fahrt nach unten oder oben; die Tiefenruder halten das nur mit Fahrt, ein schweres U-Boot sinkt bei wenig Fahrt unter seine befohlene Tiefe; das Log warnt ab 2 t und ab 3°.

Die **Pressluft** (200 bar) reicht für drei Notanblasungen zu je 60 bar; Anblasen leert die Hauptzellen in 20 s, das U-Boot steigt auf 10 m und bleibt dort, die befohlene Tiefe steht dann auf 10 m. Der nächste Befehl unter 12 m öffnet die Entlüftung: die Hauptzellen fluten in 40 s, erst dann kann das U-Boot tauchen. Schnorcheln auf Diesel betreibt den Kompressor (0,05 bar/s); mit nur lüften läuft er nicht. Ohne Strom laufen weder Trimmpumpen noch Kompressor. Die KI-U-Boote halten sich selbst im Trimm und behalten ihr eines Notanblasen.

Ihre dritte Seite **Zellen** zeigt das Schnittbild, Hauptzellen und Pressluft, die Zellen mit ihren Sollwerten, Gewicht, Trimmwinkel, Drift ohne Tiefenruder, Wassereinbruch und Pumpen; `↑`/`↓` lenzen oder fluten die Regelzelle, `←`/`→` pumpen Trimmwasser nach achtern oder vorn und `Z` schaltet die Trimmautomatik.

### Leckwehr {#sub-damage}

Ihre vierte Seite **Leckwehr** ist ein Schnittbild des U-Boots vom Heck zum Bug (Turm, Außenhülle und der Druckkörper mit seinen Einbauten; Wasser, das sich mit dem Trimm neigt, Brand und Rauch, Chlorgasschleier, ein Leck mit einströmendem Wasser, runde Schotttüren mit einem Kreuz, wenn geschlossen, Trupp-Plaketten; darunter Name und Wasser in Tonnen jeder Abteilung), Lampen mit Wasser, Leck, Brand, Gas, Schotten der gewählten Abteilung und dem Strom sowie beide Trupps; `↑`/`↓` wählen eine Abteilung, `←`/`→` eine Aufgabe, `Enter` schickt Trupp 1 und `Umschalt+Enter` Trupp 2 mit dieser Aufgabe dorthin, und `I` schließt oder öffnet die Schotten der Abteilung.

Die Maschine zeigt unter **Leckwehr** (Karte im Browser mit einer Leckwehr-Tafel, einer Seitenansicht des Druckkörpers mit Wasser, Brandschein, Gasschleier, Lecks, geschlossenen Schotten, einer Zustandslampe je Abteilung und den Trupp-Plaketten, Rundinstrumenten für Trimm, Wassereinbruch und Pressluft und darunter der Tabelle; auf der uConsole Maschine Seite 4 **Leckwehr**) den Druckkörper in sechs Abteilungen: Bugraum, Zentrale, Wohnraum, Batterieraum, Maschinenraum und Heckraum.

Ein Treffer auf das besetzte U-Boot schlägt ein Leck in die getroffene Abteilung (1,5 % Leck je % Trefferschaden, höchstens ein volles Leck; ab 50 % Schaden auch in die Nachbarabteilung mit halbem Leck) und kann dort einen Brand auslösen (Wahrscheinlichkeit = Schaden / 150); ein Versagen des Druckkörpers unter der Testtiefe schlägt ebenfalls ein Leck (siehe Unter der Testtiefe). Durch ein volles Leck dringen in 100 m Tiefe 40 kg/s ein, mit der Wurzel der Tiefe mehr; über halbvoll läuft das Wasser in offene Nachbarabteilungen über (20 kg/s) und erstickt einen Brand. Ein Brand wächst in 2 min zum Vollbrand und greift dann durch offene Schotten über; Seewasser im Batterieraum (ab 2 t) setzt Chlorgas frei, das durch offene Schotten zieht und erst langsam abzieht, wenn die Batterie trocken ist. Wasser im Batterieraum (ab 5 t) oder ein Brand dort legen den **Strom** lahm: der Motor steht (keine Fahrt, also halten die Tiefenruder ein schweres U-Boot nicht), Trimmpumpen, Kompressor und elektrische Lenzpumpen stehen still.

**Schotten schließen** hält Wasser, Brand und Gas in der Abteilung und erstickt einen Brand dort in 3 min. Zwei **Leckwehrtrupps** gehen durchs U-Boot (8 s je Abteilung) und **dichten ein Leck ab** (ein volles in 60 s), **lenzen** (30 kg/s, ohne Strom ein Viertel von Hand) oder **löschen einen Brand** (einen Vollbrand in 60 s); im Gas arbeiten sie halb so schnell, und in einer zu 90 % vollen Abteilung können sie nur lenzen. Eine Abteilung, die zur Hälfte voll Wasser ist, halb brennt oder halb vergast ist, legt ihre Station lahm: der Bugraum die Torpedorohre, die Zentrale Mast und Sehrohr, der Maschinenraum die Diesel, der Heckraum die halbe Höchstfahrt. Das Wasser ist Gewicht und Moment für den Trimm (siehe oben); ein U-Boot, das unter die 1,5-fache Testtiefe sinkt, wird zerdrückt. Das Log meldet Lecks, Brände, abgedichtete Lecks, gelöschte Brände, vollgelaufene Abteilungen, Chlorgas und den Strom.

### Unter der Testtiefe {#sub-depth}

Die Crew darf das besetzte U-Boot unter seine Testtiefe befehlen, bis zur Zerstörungstiefe (1,5-fache Testtiefe); die Stufe "tief" und das Auf-Grund-Legen bleiben bei der sicheren Tiefe. Die Tiefenleiter am uConsole und im Browser markieren die Zerstörungstiefe, und solange das U-Boot unter der Testtiefe ist, zeigen die Führung am uConsole den roten Alarm **UNTER TESTTIEFE** und der Browser einen roten Alarmchip, beide mit Test- und Zerstörungstiefe. Ab 90 % der Testtiefe ermüdet der Druckkörper wie bisher (ein Versagen in etwa 30 min bei Testtiefe); unter der Testtiefe versagt er viel schneller, mit dem Quadrat der Überschreitung: etwa alle 6 min bei 110 %, jede Minute bei 125 % und alle 20 s bei 140 %.

Jedes Versagen ist eines von dreien: **gebrochene Bolzen** einer Armatur (ein Viertelleck in einer zufälligen Abteilung, 6 % Schaden), eine **versagende Dichtung** an Welle oder Ventil (ein halbes Leck im Maschinen- oder Heckraum, 12 % Schaden) oder ein **Riss im Druckkörper** (ein volles Leck und ein 60-%-Leck in der Nachbarabteilung, 30 % Schaden). Knapp unter der Testtiefe reißt der Druckkörper nicht; die Wahrscheinlichkeit steigt um 15 % je 10 % Überschreitung, bis 60 %, und vom Rest versagt in 30 % eine Dichtung. Das Log meldet jedes Versagen mit der Abteilung, und in Zerstörungstiefe bricht der Druckkörper zusammen und das U-Boot ist verloren. Die U-Boote der KI halten ihre Testtiefe.

### Maschinenleitstand im Browser {#sub-console}

Im Browser ist die Bildfläche des Maschinenraums statt einer Karte ein Maschinenleitstand. Eine **Warn- und Meldetafel** aus Statuslampen zeigt jeden Anlagenzustand auf einen Blick: dunkel, wenn aus, türkis im Betrieb, gelb bei einer Warnung und rot blinkend bei einem Alarm, jede mit ihrem Wert (E-Maschine, Schleichfahrt, Kavitation, Schnorchel, Generator, Batterie, Laden, Kraftstoff, Sauerstoff, Kohlendioxid, CO2-Absorber, O2-Kerze, Hauptzellen, Anblasen, Entlüftung, Pressluft, Kompressor, Trimmpumpen, Trimmautomatik, Trimmwinkel, Strom, Wassereinbruch, Leck, Brand, Gas, Übertiefe, Notauftauchen, Auf Grund); die Sammellampe im Schild zählt Alarme und Warnungen.

Darunter stehen runde **Instrumente** für Fahrt, Batterie, Energiebilanz, Tiefe (Test- bis Zerstörungstiefe gelb), Pressluft und Trimmwinkel mit dem Sollwert als gelber Marke, **Tanksäulen** für Batterie, Kraftstoff, AIP-Sauerstoff, Absorber, Pressluft, Hauptzellen sowie Regel- und Trimmzellen (diese von der Mitte aus: nach oben schwer, nach unten leicht) und das **Schnittbild der Abteilungen**: das U-Boot im Schnitt vom Heck zum Bug (Außenhülle, Turm mit Masten, der Druckkörper mit seinen Einbauten) mit dem Wasser jeder Abteilung, das sich mit dem Trimm neigt, Brand und Rauch, Chlorgasschleier, einem Leck mit einströmendem Wasser, den runden Schotttüren (ein Kreuz, wenn geschlossen) und den arbeitenden Trupps, darunter Name, Wasser und Trupps jeder Abteilung. Ein Atom-U-Boot zeigt keine Batterie, keinen Diesel und keine Luftvorräte. Der Leitstand zeigt nur an; die Befehle bleiben im Stationsbereich rechts.

<!-- sop:uboot_engine -->

## Mast & ESM {#sub-esm}

Mast & ESM fährt den Mast an Sehrohrtiefe aus, hört auf der ESM-Rose nach Radaren, klassifiziert die Sender, plottet Kreuzpeilungen und schaut durchs Sehrohr. Ein Klick auf eine Zeile der Senderliste wählt diesen Sender, wie ↑/↓.

- **ESM (Seite 1):** mit ausgefahrenem Mast (`P`, nur auf Sehrohrtiefe) zeigt die Rose jedes gehörte Radar mit Peilung und Pegel. `↑`/`↓` wählen einen Sender, `C` (oder `→`; `Umschalt+C` oder `←` zurück) klassifiziert ihn aus der Bibliothek (eine Anmerkung, nie die Wahrheit), `Enter` gibt seine Kreuzpeilung oder Peillinie in den Plot des U-Boots. Ein Hauptkeulentreffer heißt, dass das Radar den Mast womöglich schon sieht.
- **Sehrohr (Seite 2):** dasselbe Sehrohr wie Seite 3 der Führung, ohne Schuss.

**Mast & ESM** zeigt die Mastzeit, die Rose, die Emitterliste und den gewählten Emitter (Signal, Pegel und Trend, Kreuzpeilung, Einstufung); ihre zweite Seite und die dritte der Führung ist das **Sehrohr** (Okular, Sichtlinie, Licht und die Sichtungsliste; `←`/`→` schwenken, `Enter` Stadimeter).

Mit ausgefahrenem Mast auf Sehrohrtiefe hört die ESM-Antenne des U-Boots (3 m über Wasser) einmal pro Sekunde die Radare ringsum: das der Fregatte, anderer Schiffe und von Flugzeugen innerhalb des Radarhorizonts, über Land nur, wo die Küste die Linie nicht verdeckt. Der Hubschrauber der Fregatte strahlt sein X-Band-Suchradar, solange er fliegt und nicht taucht (Antenne in 150 m), der Seefernaufklärer sein frequenzagiles Suchradar, solange die OPZ es eingeschaltet hat. Jede Erfassung trägt die gemessene Peilung (±4°), Band, Trägerfrequenz, PRF, Modulation und Empfangspegel, nie die Identität oder Position des Senders.

Die Crew führt eine **Emitterliste** (`E1`, `E2` …) über mehrere Mastperioden: eine Erfassung gehört zu einem Emitter, wenn Peilung, Band und Signalform passen (ein frequenzagiles Radar nur nach Peilung und Band), und die Liste vergisst einen Emitter 30 Minuten nach seiner letzten Erfassung. Die **Einstufung** ist die Annotation der Crew aus der Bibliothek: die Emitter, deren veröffentlichte Frequenz- und PRF-Bereiche die Messung enthalten, bis zu 16, die bestpassenden zuerst: jeder Eintrag zeigt seine Passung (**passt gut**, **mittel** oder **schwach**: Frequenz und PRF nahe der Mitte der Bereiche und dieselbe Modulation passen am besten), Einträge gleicher Stufe stehen nach Katalogschlüssel, und die Liste ordnet sich nur um, wenn sich eine Stufe ändert; die Wahl legt die Leistungsklasse für die **Entfernungsschätzung** aus dem Pegel fest (ohne Einstufung die kürzeste Entfernung, die die Bibliothek zulässt). Alle 30 s behält jeder Emitter eine **Peilung** von der eigenen Position des U-Boots (20 Minuten); die Karte zeigt die letzten Peillinien, und sobald die eigene Fahrt die Peilung um mindestens 8° gedreht hat, ist die **Kreuzpeilung** ihr bester Schnittpunkt mit einer 95-%-Fehlerellipse, die einen seit jeder Linie bis zu 8 kn versetzten Sender einrechnet (eine schnelle Fregatte ergibt meist keine; eine Kreuzpeilung, deren Linien nicht zusammenpassen, wird markiert). Der **Stärketrend** zeigt steigend, gleichbleibend oder fallend über fünf Minuten.

Die **Umlaufzeit** ist die Zeit zwischen den Treffern der Hauptkeule eines Emitters (den Pegelspitzen; nah dran sind dazwischen die schwächeren Nebenkeulen zu hören und zählen nicht), gemessen nur an der eigenen Signalform des Emitters, über Lücken bis 12 s ohne überspülten Durchlauf dazwischen, und angezeigt nach 8 s: **dreht** mit ihrer Dauer (etwa 2,5 s für ein Navigations- oder Seeraumradar, 5 s für ein Luftraumradar, 2 s für ein Mehrzweckradar) ist ein Suchradar, das vorbeistreicht; **dauernd** (die Keule bei jedem Durchlauf auf dem Mast) ist ein Verfolgungs- oder Feuerleitradar. Ein dauernd beleuchtender, erfasster Emitter ist immer eine Mastwarnung, und das Log meldet einmal, wenn ein Emitter auf Dauerbeleuchtung wechselt.

Die **Mastwarnung** („Radar kann Mast sehen“) kommt, wenn die geschätzte Entfernung eines erfassten Suchradars innerhalb der Entfernung liegt, auf der ein Seeraumradar bei diesem Seegang und Regen einen ausgefahrenen Mast sieht (der Wert der Wetterseite); die **empfohlene Mastzeit** ist 60 s bei ruhiger See, bis zu 300 s, wenn die Seegangsechos den Mast verbergen, und 20 s unter dieser Warnung, und das Log meldet, wenn sie überschritten ist. Ab Seegang 3 überspülen Wellen die Antenne, und manche Durchläufe hören nichts.

Die Karte Mast & ESM im Browser hat die Rose, die Emittertabelle und die Auswertung des gewählten Emitters; **In den Plot übernehmen** trägt die Kreuzpeilung (Markierung und Fehlerkreis) oder sonst die letzte Peillinie in den Plot des U-Boots ein. Auf der Seite Mast & ESM der uConsole wählen `↑`/`↓` einen Emitter, `C` oder `←`/`→` (`Umschalt+C` zurück) schalten seine Einstufung aus der Bibliothek weiter und `Enter` übernimmt ihn in den Plot. Ein ausgefahrener Mast zieht eine Schaumfahne, die Ausguck, Helikopter und Seefernaufklärer mit dem Auge sehen (siehe Kapitel Brücke): langsam fahren hält sie klein, und läuft das U-Boot mit oben stehendem Mast schneller als 5 kn, warnt die Crew „Schaumfahne sichtbar, Fahrt verringern“.

![Mast/ESM](figure:uboot-mast-esm)

![Mast/ESM im Remote-Crew-Browser](figure:web-uboot-esm-desktop)

<!-- sop:uboot_esm -->

## Navigation {#sub-nav}

Die Navigation befiehlt Kurs und Tiefe, achtet auf Kiel und Untiefen auf Lotsenkarte und Echolot, führt die Koppelnavigation und steuert die Route.

- **Karte & Echolot (Seite 1):** die Lotsenkarte um das U-Boot mit Tiefen, Untiefen und Land, das Echolot mit dem Wasser unter dem Kiel und die Lampe für den Koppelort. Ein Linksklick befiehlt den Kurs zu diesem Punkt.
- **Navigation (Seite 2):** die Lagekarte wie Seite 1 der Führung; ein Rechtsklick setzt einen Wegpunkt, `W` legt eine Zickzack- oder Quadratsuche, `Rück` löscht die Route.
- **Bedrohung (Seite 3):** wie die Bedrohungsseite der Führung; `I` weicht aus, `Umschalt+G` legt das U-Boot in flachem Wasser auf Grund.

Die Station Navigation öffnet auf ihrer eigenen Seite **Karte & Echolot**: vier Anzeigen (Tiefe, Lotung unter dem Kiel, Wasser unter dem Kiel, die Kartenprüfung voraus), eine Lotsenkarte von ±6 sm mit dem U-Boot in der Mitte, Norden oben (die Kartentiefe in Abstufungen mit Tiefenlinien bei 20, 50, 100, 200, 500, 1000 und 2000 m, Wasser flacher als die Kielgrenze rot und bis 30 m darunter gelb, Land, kartierte Hindernisse, Entfernungsringe alle 2 sm, das Kielwasser der letzten 10 Minuten, der befohlene Kurs bis zur 5-sm-Prüfung mit einem Strich alle 5 Minuten bei der jetzigen Fahrt und ein rotes Kreuz auf einem Hindernis voraus; ein Klick in die Karte befiehlt den Kurs zu diesem Punkt, wie mit `C` eingegeben) und einen **Echolot**-Streifen: Grund und eigene Tiefe der letzten 10 Minuten (eine Lotung alle 5 s), das Wasser unter dem Kiel gelb unter 30 m und rot unter 15 m, rechts das Kartenprofil entlang des befohlenen Kurses bis 5 sm mit der befohlenen Tiefe; die Kopfzeile nennt das geringste Wasser unter dem Kiel der 10 Minuten.

Die Aufzeichnung dient nur der Anzeige, wird nicht gespeichert und beginnt nach dem Laden leer.

**Plot:** Im Browser führen Führung und Navigation den eigenen Fettstift-Plot des U-Boots (Markierungen, Lineale, Peillinien, Kreise, Koppellinien). Auf der uConsole hat die U-Boot-Seite keine Zeichenwerkzeuge (`P` bedient dort den Mast), aber `Enter` auf der Seite Mast & ESM überträgt eine Kreuzpeilung oder Peillinie in den Plot, und die Karte jeder Station zeigt den Plot. Die Fregatte sieht ihn nie; der Plot wird mit dem Spiel gespeichert.

Die Navigation zeigt das Wasser unter dem Kiel und prüft die Seekarte entlang des Sollkurses bis 5 sm: Land oder ein Grund flacher als das U-Boot wird als Hindernis voraus gemeldet, im Log und als Warnung. Es zählt nur die kartierte Geografie; andere Fahrzeuge sind nicht Teil der Prüfung.

![U-Boot-Navigation](figure:uboot-navigation)

![U-Boot-Navigation im Remote-Crew-Browser](figure:web-uboot-nav-desktop)

### Koppelnavigation und Route {#sub-dead-reckoning}

- Getaucht kennt das U-Boot seinen Ort nur durch Koppeln. Der gekoppelte Ort wandert vom wahren Ort weg: durch eine gleichmäßige Versetzung bis 0,4 kn, die Log und Kreisel nicht sehen (die Trägheitsnavigation eines Atomboots wandert nur 0,3-mal so viel), dazu einmal pro Minute ein kleiner Zufallsschritt; der Fehler bleibt unter 8 sm.
- Die Karte der Crew (Küste, Tiefen, Hindernisse, Einsatzziel, HQ-Meldungen und Route) liegt dort, wo der Navigator sie gegenüber dem U-Boot vermutet. Das U-Boot selbst, seine eigenen Sonarkontakte und eigenen Torpedos bleiben dort, wo das U-Boot sie misst.
- Ein GPS-Fix: 20 s Mast oben an Sehrohrtiefe setzen den gekoppelten Ort wieder auf den wahren. Die Lampe **Koppelort** auf der Seite Karte & Echolot zeigt die eigene Fehlerschätzung des Navigators und die Minuten seit dem Fix oder den laufenden Fix.
- Kartencheck voraus und Route rechnen vom gekoppelten Ort; ein alter Fix kann das U-Boot so in Wasser führen, das die Karte für frei hält.
- Die Route: ein Rechtsklick auf die Karte setzt einen Wegpunkt (höchstens 8), `W` legt eine Zickzack- oder Quadratsuche ab dem U-Boot und schaltet weiter bis aus, `Rücktaste` löscht sie. Jeder Kursbefehl vom Ruder und jedes Ausweichen beendet die Route; das Klären der Hecklücke hat das Ruder, solange es läuft. Im Browser macht **Wegpunkte auf der Karte setzen** Klicks auf die Karte zu Wegpunkten.

<!-- sop:uboot_nav -->

## Funkraum {#sub-radio}

Der Funkraum schreibt die Sendungen des HQ mit, liest Befehle und Kontaktmeldungen des HQ und sendet Lagemeldungen.

- Die Seite zeigt, wann die nächste Sendung des HQ kommt, ob eine Antenne oben ist (Mast `P` auf Sehrohrtiefe oder die Schleppbojenantenne `B` bis 60 m bei höchstens 6 kn), die Befehle und Kontaktmeldungen des HQ und das Protokoll.
- `Enter` sendet eine Lagemeldung; dazu muss der Mast oben sein, und die Fregatte kann sie mit KW-Peilung orten.

Der **Funkraum** hat eine Seite: Antenne, Rundspruchplan, Fortschritt von Aufnahme und Sendung, die letzte Feindlage der Führung und das Funktagebuch; `Enter` sendet eine Lagemeldung und `P` fährt den Mast aus oder ein.

Die Flottenführung sendet alle 10 Minuten einen U-Boot-Rundspruch (Rundspruch 0 bei Missionsbeginn, dann 1, 2 …) und wiederholt ihn bis zum nächsten. Das U-Boot nimmt ihn nur mit klarer Antenne auf, das heißt mit ausgefahrenem Mast auf Sehrohrtiefe, und erst nach 20 s ununterbrochenem Empfang innerhalb der Sendezeit dieses Rundspruchs; ein U-Boot, das tief bleibt, verpasst Rundsprüche und bekommt nur den jeweils neuesten. In 60 % der Fälle enthält ein Rundspruch die **Feindlagemeldung** der Führung zur Fregatte: einen 5 bis 15 Minuten alten Standort mit 4 sm Fehlerkreis und gerundetem Kurs und Fahrt. Die Karte zeigt ihn als gelben Kreis mit seinem Alter, und die Funkseite nennt Peilung und Entfernung vom U-Boot.

Eine **Lagemeldung** (`Enter` im Funkraum oder der Knopf im Browser) sind 20 s Kurzwellensendung mit klarer Antenne. Währenddessen kann der KW-Peiler der Fregatte das U-Boot peilen (Funkraum HF/DF), und Mast einfahren bricht sie ab. Die Führung bestätigt eine Meldung im nächsten Rundspruch und fügt dann immer eine schärfere Feindlagemeldung (2 sm) bei. Die Funkseite und die Karte Funkraum im Browser zeigen Antenne, Rundspruchnummer und Zeit bis zum nächsten, Fortschritt von Aufnahme und Sendung, gesendete Meldungen, die letzte Feindlage und das Funktagebuch (12 Einträge, wird gespeichert).

Unter dem Mast nimmt die **VLF-Rahmenantenne** den Rundspruch noch bis 25 m Tiefe auf, das langsame VLF-Signal braucht aber 60 s ununterbrochenen Empfang statt 20 s; sie empfängt nur, eine Lagemeldung braucht weiter den Mast. Noch tiefer bringt die **Bojenantenne** (`B` auf der Funkseite oder die Schaltflächen der Funkraum-Karte im Browser) in 60 s etwa 280 m achteraus aus und nimmt den Rundspruch bis 60 m Tiefe in 30 s auf, aber nur bei höchstens 6 kn (schneller wird sie unter Wasser gezogen); auch sie empfängt nur. Über 10 kn reißt das Kabel, und die Boje ist für die Mission verloren. Die kleine Boje auf dem Wasser kann der Ausguck der Fregatte aus der Nähe sehen (ein unbekanntes kleines Objekt, nie als U-Boot erkannt) und ihr Überwasserradar auf kurze Entfernung orten; Flugzeugbesatzungen achten nicht auf sie. Einholen dauert wieder 60 s.

Ab Rundspruch 2 kann ein Rundspruch einen **Befehl der Führung** enthalten (die Hälfte, solange kein Befehl offen ist, höchstens 4 je Mission; ein verpasster Rundspruch ist ein verpasster Befehl): ein Seegebiet 8 bis 15 sm entfernt in tiefem Wasser anlaufen und binnen 40 Minuten auf 3 sm erreichen (grüner Kreis auf der Karte), binnen 30 Minuten eine Lagemeldung absetzen oder 20 Minuten Funkstille halten (nicht senden). Die Funkseite und die Karte Funkraum im Browser zeigen den offenen Befehl mit Peilung, Entfernung und Restzeit sowie die Zahl der ausgeführten; das Funktagebuch vermerkt, welcher Rundspruch einen Befehl brachte. Befehle entscheiden die Mission nicht.

Ein Rundspruch gibt auch die Ereignisse auf See weiter, die HQ kennt (Treibnetz, Wetterfront, Wale; siehe Kapitel Funk); die Crew trägt ein Netz in die Karte des U-Boots ein. Mit ausgefahrener Antenne hört der Funkraum auch die Fregatte, wenn sie HQ ruft (Kontaktmeldung oder Unterstützungsanforderung, je 20 s): Er meldet die KW-Peilung (+/-8 Grad Bodenwelle, +/-16 Grad Raumwelle) und zeichnet einen 30 sm langen Peilstrahl mit der Beschriftung HF auf die Karte.

![U-Boot-Funkraum](figure:uboot-radio)

![U-Boot-Funkraum im Remote-Crew-Browser](figure:web-uboot-radio-desktop)

<!-- sop:uboot_radio -->

## Auftauchen und Alarmtauchen {#sub-surface}

- `Shift+H` (Browser: **Auftauchen**, Kommando oder Navigation) lässt das U-Boot an die Oberfläche gehen. Bei 2 m oder weniger ist es aufgetaucht: Das Niederdruckgebläse bläst die Hauptzellen in 2 Minuten aus (ohne Pressluft aus den Flaschen), das Luk ist offen und das U-Boot lüftet sich.
- Aufgetaucht laufen die Diesel (`N`) an der freien Luft: bis 12 kn (oder die Höchstfahrt des U-Boots) statt 6 kn am Schnorchel, und der Generator gibt das 1,3-fache seiner Schnorchelleistung, die Batterie lädt also schneller.
- Die Brückenwache sieht aus 6 m statt aus den 2,5 m des Sehrohrs und damit weiter; ihre Meldungen beginnen mit **Brücke:**, ein Flugzeug meldet sie als Alarm. Die Sehrohrseite zeigt den Blick der Brückenwache.
- Auch der Gegner sieht ein aufgetauchtes U-Boot: Das Überwasserradar der Fregatte und die Radare von Hubschrauber und Seefernaufklärer sehen Rumpf und Turm (das Zehnfache des Echos eines Masts), Ausgucks sehen es mit dem Auge.
- `H` von der Oberfläche oder mit ausgeblasenen Zellen (Browser: **Alarmtauchen**) ist das Alarmtauchen: Alarm, Masten und Schnorchel ein, Flutventile auf, äußerste Kraft, befohlene Tiefe 40 m. Ausgeblasene Zellen halten das U-Boot über 10 m, bis die Flutventile sie geflutet haben (bis 40 s), und das Fluten ist ein Geräusch, das der Gegner hören kann. Aus mehr als 12 m Tiefe wird Alarmtauchen abgelehnt.

## Besatzung, Geräusche und Rotlicht {#sub-crew}

**Besatzung:** das U-Boot hat einen eigenen Wachplan mit den Regeln der Fregatte (siehe Schadensabwehr, Besatzung und Wachen): drei Wachen, Ermüdung, Gefechtsstationen und Moral. Maschine und Führung befehlen Gefechtsstationen (`G` auf der uConsole wie auf der Fregatte, eine Taste in der Leckwehr-Karte im Browser) und lösen die Wache ab (`W` auf der Seite Leckwehr oder die Taste). Die Moral steigt, wenn ein Schiff sinkt, und sinkt mit je 10 % Rumpfschaden. Eine müde Besatzung hört am Sonar später, sichtet durch das Sehrohr später und ihre Leckwehrtrupps dichten und löschen langsamer (die Pumpen sind Maschinen und behalten ihre Leistung).

**Verwundete** folgen ebenfalls den Regeln der Fregatte: Rumpfschaden (ein Verwundeter je 15 % in einem Treffer) und eine Minute in einer vollgelaufenen, brennenden oder vergasten Abteilung verwunden Leute in der Zentrale (Sonar, 4 Posten), im Bugraum (Torpedomannschaft, 4 Posten) oder im übrigen U-Boot (Leckwehr, 8 Posten); leere Posten verlangsamen die Sonarerkennung, das Laden und Fluten der Rohre und die Leckwehrtrupps. Das Protokoll meldet die Verwundeten; die Seite Leckwehr zeigt sie mit den leeren Posten und der Reserve. `M` schickt den Sanitätstrupp zur nächsten Station, `U` besetzt die am schwersten getroffene Station aus den Freiwachen um (die Leckwehr-Karte im Browser hat beide Tasten).

**Atmosphäre:** das U-Boot hat eigene Geräusche, am uConsole, wenn er das U-Boot spielt, und in den Browsern des U-Boots bei eingeschaltetem Ton (nie auf der Fregatte). Ab 60 % der Testtiefe knarzt der Rumpf, erst ab und zu, ab der Testtiefe alle 12 bis 28 s; ein Versagen des Druckkörpers kracht. Jede Detonation im Wasser im Umkreis von 30 sm (ein Torpedo- oder Flugkörpertreffer, ein torpediertes Handelsschiff) ist zu hören: innerhalb von 2 sm als schwerer Schlag dicht beim U-Boot, weiter weg als dumpfes, fernes Grollen, und das Log meldet sie mit der Peilung, die die Ohren der Crew liefern (einige Grad daneben). Das Ping eines Jägers (Rumpfsonar, Tauchsonar oder aktive Boje) klingt am Rumpf an. Mit Stereoton kommen beide aus dieser Peilung, links für Backbord und rechts für Steuerbord vom Bug des U-Boots aus.

Bei **Schleichfahrt** schaltet das U-Boot auf Rotlicht: die U-Boot-Bildschirme am uConsole und die Führungsstationen des U-Boots im Browser werden gedimmt rot, bis die Schleichfahrt endet. Das Gefechtsstationen-Signal des U-Boots ist nur eine leise Alarmklingel, und beim Einschalten der Schleichfahrt laufen die Lüfter hörbar aus, beim Aufheben wieder an.

## Missionsende, Nachbesprechung und Sprachmeldungen {#sub-mission}

**Mission:** Aus Sicht des U-Boots ist eine Mission gewonnen, wenn die Fregatte sinkt, wenn das U-Boot entkommt (150 sm von seinem Start) oder wenn es in einer Jagd bis zum Zeitlimit durchhält; sinkt das U-Boot, sieht seine Crew „U-Boot verloren“.

`D` im Endfenster des U-Boots öffnet dessen eigene **Nachbesprechung**: seinen Weg, was sein Sonar von der Fregatte hielt, die wahren Positionen von Fregatte, Hubschrauber, Seefernaufklärer und Bojen, Torpedos in beide Richtungen, die Pings, die es abbekam, und die Zeitspannen (mindestens 1 min), in denen das Sonar der Fregatte es wirklich hielt, markiert unter oder über der Schicht.

Gesprochene Crew-Meldungen (Optionen Seite 2) sprechen das Log des U-Boots, wenn die uConsole das U-Boot spielt: Torpedo und Pings gehört, Bojen-Splash, neuer Kontakt, Ausweichen, Mastwarnung, Leck, Brand, Gefechtsstationen, jeder eigene Torpedo los (das Log nennt das Rohr), Detonationen nah oder entfernt und Sinkgeräusche mit ihrer gemessenen Peilung, ein aufgenommener Rundspruch der Führung (mit oder ohne Feindlagemeldung zur Fregatte), eine neue Sehrohrsichtung mit Art und Peilung, das Passieren von 90 % der Testtiefe und das Unterschreiten der Testtiefe beim Tiefergehen, ein Treffer, jedes Versagen des Druckkörpers sowie der gewonnene oder verlorene Auftrag; Browser an U-Boot-Stationen bekommen dieselben Meldungen.

## KI-Jäger {#ref-opfor-hunters}

Wenn niemand die Fregatte fährt (die uConsole spielt das U-Boot oder ein Solo-Browser das U-Boot), besetzen KI-Jäger jede Fregattenstation, die kein Browser hält; eine Station, die ein Browser übernimmt, überlassen sie ihm sofort. Sie lesen nur, was die Sensoren der Fregatte melden, nie Position oder Identität des U-Boots:

- **Klassifizierung:** Ein Kontakt, dessen gehörte Signatur die Bibliothek nur von U-Booten kennt, wird als U-Boot klassifiziert, wie ein Bediener es nach dem Vergleich mit der Bibliothek täte; das Erkennen dauert im Mittel 3 Minuten. Andere Kontakte bleiben unklassifiziert.
- **Datum:** der frischeste geortete U-Boot-Kontakt (Ping, TMA oder Bojenfix); sonst das jüngste aus einer Radar-Mastspur bis 10 Minuten alt, einer HF/DF- oder ESM-Kreuzpeilung bis 15 Minuten alt und einer U-Boot-Datummeldung der Führung bis 30 Minuten alt; sonst die Peilung eines U-Boot-Kontakts; sonst die frischere aus einer HF/DF-Peilung und einer ESM-Peilung auf ein Mastradar bis 5 Minuten alt (ein Intercept, dem die Bibliothek unter ihren drei besten Treffern ein U-Boot-Radar zuordnet, auf dessen Peilung innerhalb 10° kein Radar- oder AIS-Schiff steht und das höchstens 10 Minuten zu hören ist: ein Radar, das länger strahlt, ist ein Schiff); sonst eine Spur. Eine verlorene U-Boot-Peilung bleibt 20 Minuten eine Spur: Die Fregatte läuft die Linie vom Ort, an dem sie gehört wurde, ab, 8 sm vor ihrer eigenen Position darauf, höchstens 60 sm hinaus. In den Fregatten-Szenarien ist die Startmeldung der Führung über die Bedrohung (Peilung und Entfernung vom Schiff) eine Stunde lang eine Spur, bis das Schiff innerhalb 3 sm der gemeldeten Position ist. In den U-Boot-Szenarien 4 und 5 meldet die Führung zum Start keine Bedrohungsposition und gibt kein U-Boot-Datum: Die Fregatte kennt nur, was sie bewacht. Die Spuren werden gespeichert (Spielstand v43). Die OPZ markiert jeden bloßen Radarpunkt eines ausgefahrenen Masts oder Schnorchels wie ein Bediener als Spur, und eine Mastspur innerhalb 10° der Peilung eines U-Boot-Kontakts gilt als dieser Kontakt. Der Funkraum nimmt HF/DF-Peilungen und Kreuzpeilungen wie die Autocrew. Die EloKa trägt eine höchstens 30 s alte ESM-Peilung auf ein Mastradar als Linie vom eigenen Standort ein, eine neue Linie erst, nachdem das Schiff 1 sm von der letzten gelaufen ist (höchstens 8, je 15 Minuten), und kreuzt die neueste Linie mit der jüngsten früheren, die sie unter mindestens 15° schneidet, höchstens 60 sm entfernt: diese ESM-Kreuzpeilung ist ein Positionsdatum wie ein HF/DF-Fix.
- **Brücke:** Im Geleitzugangriff hält die Fregatte ihre Position 3 sm vor dem Geleitzug und pendelt alle 5 Minuten 45° zu beiden Seiten (mehr als 2,5 sm abseits schließt sie mit 18 kn auf); ein Datum bearbeitet sie nur innerhalb 8 sm vom Geleitzug; beim Versorgerschutz ist der Versorger ihr Geleitzug. Ohne Datum fährt sie bei der Meerengen-Sperre mit 10 kn quer durch die Sperre und wendet 1,5 sm vor jedem Ufer, bei den Kampfschwimmern entlang des Küstenabschnitts (70 % seines Radius zu beiden Seiten der Mitte) und schließt mit 18 kn auf, wenn sie außerhalb ist. Sonst sucht die Fregatte ohne Datum mit 10 kn im Zickzack (Schläge von 10 Minuten), dessen Grundkurs sich alle 30 Minuten um 90° dreht. Zu einem Positionsdatum weiter als 6 sm läuft sie mit 18 kn, ein näheres bearbeitet sie mit 8 kn auf einem Querkurs (60° versetzt, alle 5 Minuten die Seite wechselnd), damit Schleppantenne und TMA Peilungsänderung bekommen; auf eine bloße Peilung steuert sie 30° daneben mit 14 kn, und eine Spur läuft sie mit 14 kn ab. Gegen einen Durchbruch (5) bewacht sie ihre Patrouillenposition: Ein Datum bearbeitet sie nur innerhalb 6 sm davon, und ohne Datum kehrt sie zurück, sobald sie mehr als 3 sm abseits ist. Bei der Meerengen-Sperre bearbeitet sie ein Datum nur bis 6 sm über die Enden der Sperre hinaus, bei den Kampfschwimmern nur innerhalb des Küstenabschnitts. Vor Torpedos und Flugkörpern dreht sie wie die Autocrew ab und steuert nie in flaches Wasser.
- **Sonar und Waffen:** Das Schiff pingt alle 10 Minuten auf einen U-Boot-Kontakt ohne frische Entfernung (ein Ping, der nichts findet, scheucht das U-Boot nur davon) und schießt einen Torpedo (oder die eingestellte Salve) auf ein geortetes U-Boot innerhalb 6 sm (in den U-Boot-Szenarien 1, 2, 4 und 5, in denen sie ihren Posten bewacht, innerhalb 3 sm), erneut erst, wenn er nicht mehr läuft. Gegen einen gehörten Torpedo gehen Nixies aus.
- **Hubschrauber:** Er startet für ein Datum innerhalb 30 sm (in den U-Boot-Szenarien 1, 2, 4 und 5 innerhalb 8 sm; wenn Wetter und Deck es erlauben), sobald das Deck ihn klargemacht hat (im Mittel 10 Minuten), fliegt zum Datum oder 8 sm die Peilung hinab und taucht das Sonar. Auf eine Position pingt er alle 30 s, auf eine bloße Peilung horcht er nur. Auf ein geortetes U-Boot innerhalb 1,5 sm wirft er aus einem höchstens 2 Minuten alten Fix einen Torpedo, einen nach dem anderen. Ohne Datum kehrt er zurück.
- **Seefernaufklärer:** Er wird angefordert, sobald ein Positionsdatum besteht (nie für eine bloße Peilung und nie in U-Boot-Szenario 1, in dem die Fregatte die Durchfahrt allein bewacht), fliegt mit eingeschaltetem Radar zum Datum, legt einen Bojenkreis, wo im Umkreis von 4 sm keine Boje horcht, und greift ein geortetes U-Boot in seiner Abwurfweite aus einem höchstens 2 Minuten alten Fix über den Datenlink an.
- **ASROC:** Ein Positionsdatum der eigenen Sensoren (keine Meldung der Führung und keine ESM-Kreuzpeilung), höchstens 2 Minuten alt, geht per Datenlink an das nächste befreundete KI-Kriegsschiff mit ASROC in Reichweite, höchstens alle 2 Minuten und nie, solange ein ASROC fliegt oder sein Torpedo läuft. Die KI-Jäger feuern weder das eigene ASROC der Fregatte noch ihre Wasserbomben (beides bleibt einem Spieler an der Waffenstation vorbehalten), und die U-Boot-Szenarien stellen dafür keinen Geleitschutz.
- Die übrigen Stationen (Schadensbekämpfung, Maschinenraum, OPZ-Luftverteidigung, EloKa) laufen mit den Regeln der Autocrew. Die Jagd hat keinen eigenen Zustand; die Radarpunkte und Markierungen der OPZ, nach denen sie handelt (Spielstand v25), die ESM-Linien der EloKa (Spielstand v39) und ihre Spuren (Spielstand v43) werden gespeichert, ein geladenes Spiel setzt sie also unverändert fort.

## Tasten {#sub-keys}

Alle Tasten des U-Boots auf der uConsole (`F1` an einer U-Boot-Station zeigt dieselbe Tabelle):

<!-- keys:uboot -->

## Maus {#sub-mouse}

- Jede Taste in der Tastenleiste einer Station lässt sich anklicken; Lampen, Seitenreiter und Tastenhinweise im Text drücken ihre Tasten, und die Stationsreiter in der Kopfzeile wechseln die Station.
- Ein Klick auf die Kurs-, Fahrt- oder Tiefenscheibe befiehlt diesen Wert.
- In der Feuerleitung flutet die Lampe eines trockenen Rohrs dieses, die eines leeren lädt es; der Täuschkörper hat einen Tastenchip. Die Feuertaste `Strg+Enter` lässt sich nur an der Station Waffen anklicken.
- Navigation, Karte & Echolot: Ein Linksklick auf die Lotsenkarte befiehlt den Kurs zu diesem Punkt; auf der Seite Navigation setzt ein Rechtsklick einen Wegpunkt der Route.
- Ein Klick auf eine Zeile der Emitterliste wählt diesen Emitter. Auf der Karte zoomt das Mausrad, Ziehen verschiebt.

## Nicht modelliert {#sub-limits}

- Keine Ortsbestimmung über Landmarken, Lotungen oder Sterne; nur GPS löscht den Koppelfehler.
- Der Plot behält seine Marken dort, wo sie gegenüber dem U-Boot gezeichnet wurden; er wandert mit einem Fix nicht mit.
- Keine eigene Zentrale und kein LI-Platz; Trimm und Ballast bleiben beim Maschinenraum.
- Der Funkraum kennt den Rundspruchplan der Führung, drei Befehlsarten (sieben auf freier Fahrt) und Lagemeldungen: keine freien Nachrichten der Führung, kein Empfang unter 25 m ohne Bojenantenne und keiner unter 60 m (kein ELF, keine Schleppdrahtantenne), keine Kurzsignale und keine anderen Einheiten im Netz; die Feindlage der Führung ist modellierte Aufklärung, kein eigener Sensor.
- Die Leckwehr kennt sechs Abteilungen und zwei Trupps: keine getrennten Schäden an Druck- und Außenhülle, keine Ausbreitung von Rauch oder Hitze, kein Brand in den Luftvorräten und kein Sauerstoffverbrauch durch Feuer; der Gesamtschaden des U-Boots (Lärm, Höchstfahrt, Untergang bei 100 %) summiert sich weiter aus Treffern, und die KI-U-Boote haben nur diesen Wert.
- Unter der Testtiefe kennt der Druckkörper keine einzelnen Armaturen, kein allmähliches Zusammendrücken und keine verstärkten Nähte aus einer Werftzeit; ein Versagen wählt Art und Abteilung zufällig, und ein zerdrücktes U-Boot ist sofort verloren.
- Die Geräusche des U-Boots sind einfache Signale: Stereo unterscheidet nur Backbord von Steuerbord (voraus und achteraus klingen gleich), eine Detonation liefert keine Entfernungsschätzung und kein Knarzen kommt aus einer bestimmten Abteilung; der Sonarraum des U-Boots hat kein Rotlicht.
- Das Trimmmodell kennt ein Gewicht und ein Moment: keinen Effekt freier Oberflächen, keine Kompressibilität des Druckkörpers mit der Tiefe und keine eigene Schnelltauchzelle; das U-Boot taucht nicht ganz auf. Proviant und Frischwasser gehen nicht aus.
- Ein ausgefahrener Mast oder Schnorchelkopf erscheint auf dem Fregattenradar nur als bloßer Punkt (siehe Kapitel OPZ). Die Schaumfahne eines ausgefahrenen Masts hängt nur von der Fahrt ab (nicht von der Mastlänge über Wasser oder dem Kurs zur See), und die Crew warnt nur einmal, sobald das U-Boot mit oben stehendem Mast schneller als 5 kn läuft.
- Das ESM des U-Boots hört keine Radare anderer U-Boote und keine Flugkörpersucher; es hat keine gewichtete Wahrscheinlichkeitsanalyse und keine Bewegungsanalyse eines Senders (die Kreuzpeilung nimmt einen langsamen Sender an).
- Die Passung ist die Lesart der Crew aus den veröffentlichten Bereichen, keine Wahrscheinlichkeit: ein Breitbandradar, nahe der Mitte seines Bereichs gemessen, kann besser passen als der wahre Sender nahe dem Rand, und der Browser zeigt die ersten 8 Einträge.
- Das ASROC der KI-Jäger kommt nur von befreundeten Kriegsschiffen, die ohnehin im Szenario sind, nie vom eigenen Starter der Fregatte.
- Das Sehrohr hat keine Kamera; Sichtungen tragen keine Identifikation über die grobe Klasse hinaus, und das Stadimeter nimmt eine Klassenlänge statt einer Masthöhe an.
