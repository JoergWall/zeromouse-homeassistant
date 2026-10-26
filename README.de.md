# ZeroMOUSE für Home Assistant

*[English version](README.md)*

Eine **inoffizielle** Home-Assistant-Integration für [ZeroMOUSE](https://zeromouse.com),
den KI-basierten Beute-Erkenner für Mikrochip-Katzenklappen. Sie bringt deine
ZeroMOUSE-Geräte, ihre Erkennungen, Bilder, Statistiken und Einstellungen nach Home
Assistant, mit Echtzeit-Aktualisierung und zwei Dashboard-Karten, die Ereignisse wie die
ZeroMOUSE-App darstellen. Auf Wunsch zeigt sie, **welche Katze** es war, indem sie
Ereignisse mit den Durchgängen abgleicht, die deine Katzenklappe an Home Assistant meldet.

> [!IMPORTANT]
> Dieses Projekt steht in keiner Verbindung zum Hersteller von ZeroMOUSE und wird von ihm
> weder unterstützt noch empfohlen. ZeroMOUSE veröffentlicht keine API; die hier genutzte
> Cloud-Schnittstelle wurde zur Herstellung der Interoperabilität aus der offiziellen App
> rekonstruiert (siehe [API.md](API.md)). Der Hersteller kann das Backend jederzeit ändern,
> wodurch die Integration ohne Vorwarnung ausfallen kann. Nutzung auf eigenes Risiko.

---

## Inhalt

- [Funktionen](#funktionen)
- [Unterstützte Geräte und Katzenklappen](#unterstützte-geräte-und-katzenklappen)
- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Entitäten](#entitäten)
- [Aktionen](#aktionen)
- [Ereignisse](#ereignisse)
- [Dashboard-Karten](#dashboard-karten)
- [Ereignisse mit der Katzenklappe verknüpfen](#ereignisse-mit-der-katzenklappe-verknüpfen)
- [Wie Daten aktualisiert werden](#wie-daten-aktualisiert-werden)
- [Beispiele und Anwendungsfälle](#beispiele-und-anwendungsfälle)
- [Bekannte Einschränkungen](#bekannte-einschränkungen)
- [Fehlerbehebung](#fehlerbehebung)
- [Datenschutz und Sicherheit](#datenschutz-und-sicherheit)
- [Entfernen](#entfernen)
- [Qualitätsskala](#qualitätsskala)
- [Entwicklung](#entwicklung)
- [Lizenz und Marken](#lizenz-und-marken)

## Funktionen

- Einrichtung über die Oberfläche mit dem Konto der ZeroMOUSE-App; erneute Anmeldung und
  Neukonfiguration werden unterstützt.
- **Erkennungen** wie *Beute erkannt*, *Keine Beute*, *Nicht entscheidbar*, *Hand* oder
  *Rausgehen* als Sensoren, als Ereignis-Entität und als Home-Assistant-Ereignis.
- **Echtzeit**: Neue Ereignisse kommen innerhalb weniger Sekunden über denselben
  Push-Kanal wie in der App (AWS-AppSync-Subscription). Zusätzlich fragt die Integration
  alle 60 s ab.
- **Bilder**: das Bild des letzten Ereignisses als Bild-Entität. Die Galerie-Karte spielt
  die Bilder jedes Ereignisses als Animation ab.
- **Rückmeldung wie in der App**: Ereignisse als *Richtig* oder *Falsch* bewerten (das
  trainiert die KI) und löschen, im Dashboard oder per Aktion in Automationen.
- **Steuerung**: Eingangsmodus, Ausgangsmodus mit Zeitfenster, Verhalten bei „Nicht
  entscheidbar“, Blockierdauer bei Beute, Beute blockieren an/aus, Eintritt pro Katze und
  Blockieren unbekannter Katzen.
- **Statistik**: Beute pro Monat und gesamt.
- **Welche Katze war es?** Ereignisse lassen sich mit den Durchgängen jeder Katzenklappe
  verknüpfen, die an Home Assistant meldet (getestet mit Sure Petcare), mit einfachen
  Tür- oder Vibrationssensoren an Klappen ohne Netzanbindung oder mit der
  Gesichtserkennung von ZeroMOUSE selbst.
- **Dashboard-Karten**: eine Ereignis-Galerie mit den Filtern der App und unbegrenztem
  Nachladen sowie eine Zeitleiste der letzten Tage.
- Diagnose, deutsche und englische Übersetzung.

## Unterstützte Geräte und Katzenklappen

### ZeroMOUSE

| Gerät | Status |
|---|---|
| ZeroMOUSE 2.0 (Firmware 0.17.x, EU-Cloud, App 1.14.x) | Getestet |
| Andere ZeroMOUSE-Geräte, die die ZeroMOUSE-App nutzen | Sollte funktionieren, nicht getestet |
| ZeroMOUSE Cat Flap (die eigene Klappe des Herstellers) | Unbekannt, nicht getestet |

Einstellungen, die das Gerät nicht beherrscht, werden trotzdem angezeigt, weil die
Cloud-API die Fähigkeiten eines Geräts nicht meldet.

### Katzenklappen

ZeroMOUSE sitzt vor einer vorhandenen **Mikrochip**-Katzenklappe. Erkennt es Beute, sendet
es dem RFID-Leser der Klappe ein „Fremdchip“-Signal, sodass die Klappe mit ihrer eigenen
Logik verriegelt bleibt. Die Integration spricht nicht mit der Klappe. Die Klappe spielt nur
eine Rolle, wenn du wissen willst, welche Katze es war (siehe
[Ereignisse mit der Katzenklappe verknüpfen](#ereignisse-mit-der-katzenklappe-verknüpfen)).

| Katzenklappe | Mit ZeroMOUSE kompatibel ¹ | Durchgänge in Home Assistant | Verknüpfung |
|---|---|---|---|
| Sure Petcare: SureFlap DualScan, Microchip Pet Door / Cat Flap Connect | Ja | Ja, mit Hub (Core *surepetcare*, *sureha*, *surepcha*) | **Getestet** |
| Sure Petcare: SureFlap Microchip Cat Flap (ohne Hub) | Ja (Händlerangabe) | Nein | ZeroMOUSE-Gesichtserkennung oder Eigenbau-Sensor |
| PetSafe Microchip Cat Flap (nicht PetPorte; braucht Adapter) | Ja | Nein (keine Netzanbindung) | ZeroMOUSE-Gesichtserkennung oder Eigenbau-Sensor |
| PetSafe SmartDoor Connected | Nicht gelistet | Ja (*petsafe_extended*) | Vorlage `petsafe`, ungetestet ² |
| Cat Mate Elite, Cat Mate 360 | Ja (ab App 1.14.14) | Nein (keine Netzanbindung) | ZeroMOUSE-Gesichtserkennung oder Eigenbau-Sensor |
| Ferplast Mikrochip-Klappen | Keine Angabe | Nein (keine Netzanbindung) | ZeroMOUSE-Gesichtserkennung oder Eigenbau-Sensor |
| OnlyCat | Keine Angabe (hat eigene Beuteerkennung) | Ja (OnlyCat-Integration) | Vorlage `onlycat`, ungetestet ² |

¹ Laut FAQ und Produktseiten des Herstellers, Stand Oktober 2026; vor dem Kauf bitte die
aktuelle Liste auf zeromouse.com prüfen. Die Klappe braucht einen flachen Tunnel.
² Dem Entwickler stand nur eine Sure-Petcare-Klappe zur Verfügung. Die Vorlagen für
andere Klappen folgen dem Quellcode ihrer Home-Assistant-Integrationen und wurden nie mit
echten Ereignissen getestet. Rückmeldungen sind willkommen.

## Voraussetzungen

- Home Assistant **2026.8** oder neuer (getestet mit 2026.9 und 2026.10).
- Ein ZeroMOUSE-Konto (E-Mail und Passwort) mit mindestens einem in der App
  eingerichteten Gerät. Konten mit Zwei-Faktor-Anmeldung werden nicht unterstützt.
- Internetzugang von Home Assistant zur ZeroMOUSE-Cloud (AWS, Region `eu-central-1`).
- Optional, um Ereignisse Katzen zuzuordnen: der Recorder (standardmäßig aktiv) und eine
  Katzenklappen-Integration oder ein Sensor, siehe
  [unten](#ereignisse-mit-der-katzenklappe-verknüpfen).

## Installation

### HACS / Home Assistant Marketplace

1. Bis Home Assistant 2026.10: in HACS ⋮ → *Benutzerdefinierte Repositories* öffnen.
   Ab Home Assistant 2026.11: *Einstellungen → Marketplace*, ⋮ → *Benutzerdefinierte Repositories*.
2. `https://github.com/JoergWall/zeromouse-homeassistant` mit der Kategorie *Integration* hinzufügen.
3. Nach **ZeroMOUSE** suchen, installieren und Home Assistant neu starten.

HACS und der Marketplace können nur öffentliche Repositories installieren.

### Manuell

1. Das neueste Release (oder das Repository) herunterladen.
2. `custom_components/zeromouse` nach `<config>/custom_components/zeromouse` kopieren,
   sodass `<config>/custom_components/zeromouse/manifest.json` existiert.
3. Home Assistant neu starten.

### Integration einrichten

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen und nach
   **ZeroMOUSE** suchen.
2. Die Zugangsdaten der ZeroMOUSE-App eingeben:

   | Feld | Beschreibung |
   |---|---|
   | E-Mail | Die E-Mail-Adresse, mit der du dich in der ZeroMOUSE-App anmeldest. |
   | Passwort | Das Passwort dieses Kontos. |

3. Die Integration meldet sich an, liest deine Geräte und legt für jede ZeroMOUSE ein
   Gerät in Home Assistant an. Jedes ZeroMOUSE-Konto kann einmal hinzugefügt werden.
   Später im Konto hinzugefügte Geräte erscheinen automatisch, entfernte verschwinden aus
   Home Assistant.

## Konfiguration

Es gibt keine Optionen. Alle Geräteeinstellungen stehen als Entitäten bereit (siehe unten)
und wirken sofort in der Cloud, genau wie in der App.

- **Erneute Anmeldung**: Ändert sich das Passwort, zeigt Home Assistant unter
  *Einstellungen → Geräte & Dienste* eine Aufforderung, das neue Passwort einzugeben.
- **Neukonfiguration**: Über *Einstellungen → Geräte & Dienste → ZeroMOUSE → ⋮ → Neu
  konfigurieren* lassen sich E-Mail und Passwort ändern. Es muss dasselbe Konto bleiben.

## Entitäten

Die Namen unten sind die deutschen Standardnamen.

### Sensoren

| Entität | Beschreibung | Hinweise |
|---|---|---|
| Letztes Ereignis | Klassifikation des neuesten Ereignisses: `prey`, `clean`, `undecidable`, `out`, `hand`, `early`, `late`, `free`, `test`, `unknown` | Attribute: `event_id`, `cat`, `image_count`, `is_favorite` |
| Zeit des letzten Ereignisses | Zeitpunkt des neuesten Ereignisses | Zeitstempel |
| Letzte Beute | Zeitpunkt des neuesten Ereignisses mit Beute | Zeitstempel |
| Letzte Katze | Name der Katze, die ZeroMOUSE beim neuesten Ereignis erkannt hat (Gesichtserkennung) | Leer ohne Katzenprofile |
| Beute diesen Monat | Im laufenden Monat erkannte Beute | Aus der Statistik-API |
| Beute gesamt | Summe aller Monate, die die Statistik-API liefert | Attribut `monthly` listet jeden Monat |
| Anzahl Ereignisse | Vom Gerät aufgezeichnete Ereignisse | Diagnose |
| KI-Personalisierungsstatus | Wie gut die KI an deine Umgebung angepasst ist, in % | Diagnose |
| Feedback Score | Deine Feedback-Aktivität, in % | Diagnose |
| WLAN-Signal | WLAN-RSSI in dBm | Diagnose, standardmäßig deaktiviert (siehe [Einschränkungen](#bekannte-einschränkungen)) |
| Anzahl Neustarts | Neustarts des Geräts | Diagnose, standardmäßig deaktiviert |

### Binärsensoren

| Entität | Beschreibung |
|---|---|
| Beutesperre aktiv | An, solange das letzte Beute-Ereignis jünger ist als die eingestellte Blockierdauer. Das berechnet die Integration; die Cloud meldet nicht, ob die Klappe tatsächlich gesperrt ist. |
| Konnektivität | Ob das Gerät mit der Cloud verbunden ist. Diagnose. |

### Steuerung

| Entität | Typ | Werte | Optionswerte für Automationen |
|---|---|---|---|
| Eingangsmodus | Auswahl | Freier Eintritt, Beute blockieren, Gesichtserkennung, Gesperrt | `free_entry`, `blocking_prey`, `face_detection`, `locked` |
| Ausgangsmodus | Auswahl | Offen, Gesperrt, Zeitbasiert | `open`, `locked`, `time_based` |
| Ausgang offen ab / Ausgang offen bis | Uhrzeit | Zeitfenster für den zeitbasierten Ausgangsmodus | `"07:30:00"` |
| Verhalten bei „Nicht entscheidbar“ | Auswahl | Smarter Modus (blockiert nur, wenn kürzlich Beute erkannt wurde), Immer öffnen, Immer blockieren | `smart`, `always_allow`, `always_block` |
| Blockierdauer bei Beute | Auswahl | 10 s … 60 min Mindestsperrzeit nach Beute | Sekunden als Text: `"10"`, `"15"`, `"30"`, `"60"`, `"120"`, `"300"`, `"600"`, `"900"`, `"1800"`, `"3600"` |
| Beute blockieren | Schalter | Aus = Ereignisse nur aufzeichnen, nicht blockieren | |
| Unbekannte Katzen blockieren | Schalter | Blockiert bei Gesichtserkennung Katzen, die nicht in deiner Katzenliste stehen | |
| `<Katze>` Eintritt erlauben | Schalter | Einer pro Katzenprofil; gilt bei Gesichtserkennung. In der App neu angelegte Katzen erscheinen automatisch. | |

### Sonstiges

| Entität | Beschreibung |
|---|---|
| Letztes Ereignisbild | Vorschaubild des neuesten Ereignisses |
| Erkennung (Ereignis-Entität) | Löst pro neuem Ereignis einmal aus, mit der Klassifikation als Ereignistyp und den Attributen `event_id`, `cat` und `time` |

### Klassifikationen

Sensoren, Ereignis-Entität und `zeromouse_event` liefern den Rohwert. Die App (und die
Karten dieser Integration) zeigen ihn in fünf Gruppen:

| Wert | Anzeige | Bemerkung |
|---|---|---|
| `clean`, `early` | Keine Beute erkannt | `early` markiert das Gerät als versteckt |
| `prey` | Beute erkannt | |
| `undecidable`, `late`, `unknown` | Nicht entscheidbar | `undecidable` und `late` sind als versteckt markiert, werden aber angezeigt |
| `test` (`hand`) | Hand erkannt | |
| `out` | Rausgehen erkannt | als versteckt markiert |
| `free`, andere Werte | Nicht entscheidbar | ohne Filter nicht in der Liste |

## Aktionen

| Aktion | Felder | Beschreibung |
|---|---|---|
| `zeromouse.rate_event` | `device_id`, `event_id`, `rating` (`correct` / `incorrect` / `none`) | Gibt dieselbe Rückmeldung wie *Richtig* / *Falsch* in der App. ZeroMOUSE trainiert damit die KI nach. `none` entfernt die Bewertung, wie erneutes Tippen auf den aktiven Knopf in der App. |
| `zeromouse.delete_event` | `device_id`, `event_id` | Löscht ein Ereignis wie *Löschen* in der App. |

`device_id` ist das Home-Assistant-Gerät der ZeroMOUSE (Geräteauswahl in der Oberfläche),
`event_id` stammt aus dem Ereignis `zeromouse_event`, der Ereignis-Entität oder dem Sensor
*Letztes Ereignis*. Falsche Eingaben führen zu einem Validierungsfehler, Cloud-Fehler zu
einer übersetzten Fehlermeldung.

```yaml
action: zeromouse.rate_event
data:
  device_id: "{{ trigger.event.data.device_id }}"
  event_id: "{{ trigger.event.data.event_id }}"
  rating: correct
```

## Ereignisse

Jede neue Erkennung löst außerdem das Home-Assistant-Ereignis `zeromouse_event` aus:

```yaml
event_type: zeromouse_event
data:
  device_id: "8f1c…"                       # Home-Assistant-Geräte-ID (für die Aktionen)
  zeromouse_device_id: "AbCdEf0123456789xyzABC"
  device_name: "Katzenklappe"
  event_id: "6ab3be5c-…"
  classification: prey                    # alle Werte siehe „Letztes Ereignis“
  cat: null                               # Name der Katze, falls ZeroMOUSE sie erkannt hat
  time: "2026-09-23T11:56:12+00:00"
```

Die Integration bringt keine eigenen Auslöser oder Bedingungen mit. Nutze in Automationen
die Entitäten und das Ereignis.

## Dashboard-Karten

Die Integration bringt zwei Lovelace-Karten mit. Sie werden automatisch geladen; eine
Ressource musst du nicht anlegen. Beide funktionieren auch ohne Katzenklappe.

### Ereignis-Galerie: `custom:zeromouse-events-card`

Zeigt Ereignisse wie die App: Die Bilder jedes Ereignisses laufen als Animation (Klick
pausiert), darunter stehen Klassifikation, Gerät, Uhrzeit und, falls eingerichtet, die
Katze.

- **Filter**-Knopf mit den Filtern der App: *Keine Beute erkannt*, *Beute erkannt*,
  *Nicht entscheidbar*, *Hand erkannt*, *Rausgehen erkannt*, *Nur Favoriten anzeigen* und
  *Zurücksetzen*. Wie in der App sind anfangs alle Kästchen außer *Rausgehen erkannt*
  angehakt, jedes Kästchen umfasst die unter [Klassifikationen](#klassifikationen)
  genannten Werte, und *Nur Favoriten anzeigen* zeigt alle Favoriten unabhängig von den
  anderen Kästchen. Die Auswahl merkt sich die Karte pro Browser.
- Knöpfe **Falsch / Richtig / Löschen** unter jedem Ereignis, mit Rückfrage bei *Falsch*
  und *Löschen*. Erneutes Tippen auf das aktive *Falsch* oder *Richtig* entfernt die
  Bewertung.
- Eine **+**-Kachel am Ende lädt ältere Ereignisse nach, so viele du willst. Bilder werden
  nur für Ereignisse geladen, die gerade sichtbar sind.

```yaml
type: custom:zeromouse-events-card
title: Katzenklappe  # optionale Überschrift
limit: 10            # Ereignisse pro Seite
fps: 2               # Bilder pro Sekunde
language: de         # de oder en; Standard: Sprache von Home Assistant
show_filter: true    # Filter-Knopf
show_actions: true   # Knöpfe Falsch / Richtig / Löschen
confirm: true        # vor „Falsch“ und „Löschen“ nachfragen
show_hidden: false   # „Rausgehen erkannt“ anfangs ebenfalls anhaken
filter:              # anfangs angehakt: clean, prey, undecidable, hand, out
  classifications: [prey]  # Standard: alle außer out (mit show_hidden auch out)
  favorites_only: false
remember_filter: true  # Filter des Nutzers pro Karte und Browser merken
storage_key: kueche    # optional, eigener Schlüssel für den gemerkten Filter
flap_name: SureFlap  # Bezeichnung der Durchgänge, Standard „Klappe“
correlate:           # optional, siehe „Ereignisse mit der Katzenklappe verknüpfen“
  - entity: binary_sensor.tiger
    name: Tiger
    color: "#2a78d6"
window_before: 60    # optionales Zeitfenster der Zuordnung in Sekunden (0–3600)
window_after: 180
```

Der gemerkte Filter liegt pro Karte (Titel, eingestellter Filter und Dashboard) im
Browser. Wünscht das System reduzierte Bewegung, starten die Animationen angehalten; Bilder
lassen sich per Klick oder mit Enter/Leertaste anhalten.

### Zeitleiste: `custom:zeromouse-timeline-card`

Eine Zeile pro Tag und ein runder Marker für jedes Ereignis mit dem Ergebnis *Keine Beute*,
*Beute* oder *Nicht entscheidbar*, gruppiert wie in der App (siehe
[Klassifikationen](#klassifikationen); Hand- und Rausgehen-Ereignisse fehlen). Der Hintergrund zeigt das **Ergebnis** (grün = keine Beute, rot =
Beute, orange = nicht entscheidbar); mit Katzen-Zuordnung zeigt er außerdem, **wer** es
war, in einer Spur pro Katze.

```yaml
type: custom:zeromouse-timeline-card
title: Wer kam wann   # optional, Standard je nach Sprache
days: 10
language: de          # de oder en; Standard: Sprache von Home Assistant
correlate:            # optional
  - entity: binary_sensor.tiger
    name: Tiger
    icon: /local/zeromouse/tiger-{class}.webp   # optional; {class} = clean | prey | undecidable
  - entity: binary_sensor.luna
    name: Luna
unknown_icon: /local/zeromouse/unbekannt.webp   # optional, {class} geht auch hier
unknown_name: Unbekannt # Bezeichnung von Ereignissen ohne Katze
flap_name: SureFlap   # Bezeichnung der Durchgänge in den Tooltips
night_start: 22       # schattierte Nachtstunden
night_end: 6
note: ""              # optional: Hinweistext ersetzen oder ausblenden
window_before: 60     # optionales Zeitfenster der Zuordnung in Sekunden (0–3600)
window_after: 180
```

Ohne `icon` erscheint eine Katze als farbiger Kreis mit ihrem Anfangsbuchstaben. Eigene
runde Bilder (etwa 96 × 96 px, WebP oder PNG) gehören nach `<config>/www/zeromouse/`.

## Ereignisse mit der Katzenklappe verknüpfen

ZeroMOUSE sieht, *dass* eine Katze an der Klappe ist, ohne Gesichtserkennung aber nicht,
*welche*. Mikrochip-Klappen, die an Home Assistant melden, kennen die Katze. Beides passiert
fast gleichzeitig, deshalb kann die Integration es über die Zeit zusammenführen.

### So funktioniert es

1. Jede Katze bekommt eine **Durchgangsquelle**: eine Home-Assistant-Entität, deren
   Verlauf die Durchgänge dieser Katze zeigt.
2. Die Integration liest den Verlauf dieser Entitäten aus dem Recorder und macht daraus
   Durchgänge (Zeit, Richtung rein/raus, Katze).
3. Jedes ZeroMOUSE-Ereignis wird mit dem zeitlich nächsten Durchgang innerhalb eines
   Zeitfensters verknüpft (Standard 60 s vor bis 180 s nach dem Ereignis), jeweils eins zu
   eins. Ereignisse *Keine Beute*, *Beute*, *Nicht entscheidbar* und *Hand* brauchen einen
   Durchgang *rein*, *Rausgehen* einen Durchgang *raus*; ein Durchgang ohne bekannte
   Richtung passt zu beidem.
4. Passt kein Durchgang, hat ZeroMOUSE die Katze aber selbst erkannt (Gesichtserkennung),
   wird diese Katze verwendet.

Die Zuordnung läuft auf dem Home-Assistant-Server, sobald eine Karte Ereignisse abruft. Sie
funktioniert deshalb auch für vergangene Ereignisse, so weit der Recorder den Verlauf
aufbewahrt.

> [!NOTE]
> Bei *Beute erkannt* und *Nicht entscheidbar* sperrt ZeroMOUSE die Klappe. Die Katze geht
> nicht durch, und die Klappe meldet nichts. Diese Ereignisse bleiben deshalb *unbekannt*,
> außer ZeroMOUSE erkennt die Katze selbst. Viele Klappen erfassen außerdem keine
> hinausgehenden Katzen; *Rausgehen*-Ereignisse finden daher selten einen Durchgang.

### Konfiguration

Die Liste `correlate` ist in beiden Karten gleich:

| Schlüssel | Bedeutung |
|---|---|
| `entity` | Die Entität mit den Durchgängen der Katze (weglassen für eine Katze, die nur ZeroMOUSE erkennt) |
| `name` | Name der Katze |
| `preset` | Wie Durchgänge gelesen werden: `auto` (Standard), `sureflap`, `sureflap_state`, `petsafe`, `onlycat`, `state`, `event`, `attribute` |
| `source` | Für Fortgeschrittene: `attribute`, `state` oder `event`, überschreibt die Leseweise der Vorlage |
| `time_attribute` | Attribut mit der Durchgangszeit. Standard: Quelle `state` → Zeitpunkt der Zustandsänderung, Quelle `event` → der Zustand (Zeit des Ereignisses), Quelle `attribute` → `since` |
| `direction_attribute` | Attribut mit der Richtung. Standard: Quelle `state` → der Zustand, Quelle `event` → `event_type`, Quelle `attribute` → keine Richtung |
| `in` / `out` | Werte, die „kam herein“ / „ging hinaus“ bedeuten (Groß-/Kleinschreibung egal) |
| `filter` | Nur Verlaufszeilen verwenden, deren Attribute diese Werte haben, z. B. eine Katze an einer Entität für die ganze Klappe |
| `color`, `icon` | Anzeigeoptionen der Karten |

`window_before` und `window_after` (Sekunden, 0–3600, in der Karte gesetzt) legen das
Zeitfenster für alle Quellen fest.

| Vorlage | Liest | Typische Entität |
|---|---|---|
| `sureflap` | jedes neue `since`, Richtung aus `where` (1 = rein, 2 = raus) | Tier-`binary_sensor` von Sure Petcare (Core-Integration, *sureha*) |
| `sureflap_state` | jedes neue `since`, Richtung aus dem Zustand (an = drinnen) | Präsenzsensor von *surepcha* |
| `petsafe` | Ereignis-Entität, Zeit aus `occurred_at`, `pet_entered` / `pet_exited` | Ereignis-Entität „‹Tier› Activity“ von *petsafe_extended* |
| `onlycat` | `timestamp`, Richtung `INWARD` / `OUTWARD`; pro Katze einen `filter` auf `rfidCode` | `binary_sensor` „Flap event“ von OnlyCat |
| `state` | jede Zustandsänderung; an/home = rein, aus/not_home = raus | Präsenzsensoren, Tür-/Kontaktsensoren |
| `event` | jedes Ereignis einer Ereignis-Entität, Richtung aus `event_type` | Ereignis-Entitäten von ESPHome oder Zigbee |
| `attribute` | eigenes `time_attribute` / `direction_attribute` | alles andere |

Mit `auto` wird die Vorlage aus der Entität gewählt: `event.*` ergibt `event` (oder
`petsafe` mit Attribut `occurred_at`), eine Entität mit `since` und `where` ergibt
`sureflap`, nur `since` ergibt `sureflap_state`, die Attribute von OnlyCat ergeben
`onlycat`, alles andere `state`.

### Beispiel: Sure Petcare (getestet)

Die Core-Integration *surepetcare* und *sureha* legen pro Tier einen Präsenz-`binary_sensor`
an. Sein Attribut `since` ändert sich bei jedem Durchgang, `where` nennt die Richtung. Weil
die Integrationen die Cloud nur alle 2,5–3 Minuten abfragen, ändert sich der *Zustand* nur,
wenn der Aufenthaltsort wechselt; `since` enthält aber die genaue Serverzeit des letzten
Durchgangs.

```yaml
correlate:
  - entity: binary_sensor.tiger       # Core-Integration; sureha: binary_sensor.pet_tiger
    name: Tiger
  - entity: binary_sensor.luna
    name: Luna
```

In der Umgebung des Autors folgte der Sure-Petcare-Durchgang dem ZeroMOUSE-Ereignis nach
**9 bis 16 Sekunden**. In zehn Tagen wurden 58 von 67 Sure-Petcare-Durchgängen innerhalb
einer Minute zugeordnet. Geht dieselbe Katze zwischen zwei Abfragen zweimal durch, ist nur
der zweite Durchgang sichtbar.

### Beispiel: PetSafe SmartDoor Connected (ungetestet)

```yaml
correlate:
  - entity: event.tiger_activity      # Ereignis-Entität „Tiger Activity“ von petsafe_extended
    name: Tiger
    preset: petsafe
```

### Beispiel: OnlyCat (ungetestet)

Die OnlyCat-Integration hat pro Klappe einen Sensor „Flap event“, dessen Attribute die
Chipnummer der Katze, die Richtung und die Aktion enthalten. Pro Katze filtern:

```yaml
correlate:
  - entity: binary_sensor.oc_00000000001_event
    name: Tiger
    preset: onlycat
    filter:
      rfidCode: "900123456789012"
      action: [TRANSIT, BREACH]
```

### Klappen ohne Netzanbindung (Cat Mate, Ferplast, PetSafe Microchip, SureFlap ohne Hub)

Diese Klappen melden nichts. Zwei Möglichkeiten:

- **Gesichtserkennung von ZeroMOUSE**: In der ZeroMOUSE-App Katzenprofile anlegen. Erkannte
  Katzen erscheinen ohne Konfiguration in der Galerie-Karte und im Feld `cat` der
  Ereignisse. Für eine eigene Spur (und ein Icon) in der Zeitleiste die Katze mit ihrem
  ZeroMOUSE-Namen ohne Entität eintragen: `- name: Tiger`.
- **Ein Sensor an der Klappe**: ein Tür-/Kontaktsensor, ein Vibrationssensor oder ein
  ESPHome-Eigenbau mit zwei Reedkontakten oder Lichtschranken. Solche Sensoren zeigen,
  *dass* sich die Klappe bewegt hat (eventuell mit Richtung), nicht *welche* Katze. Eine
  Quelle mit allgemeinem Namen bestätigt, dass die Katze wirklich hereingekommen ist:

  ```yaml
  correlate:
    - entity: binary_sensor.katzenklappe_kontakt   # oder event.katzenklappe_opening (ESPHome)
      name: Klappe
      in: ["on", "inside"]
      out: ["outside"]
  ```

## Wie Daten aktualisiert werden

| Was | Wie | Wann |
|---|---|---|
| Geräte, Katzenprofile, Scores | GraphQL (AWS AppSync) | alle 60 s |
| Einstellungen und Verbindungsstatus (Device Shadow) | REST | alle 60 s |
| Neueste 20 Ereignisse | GraphQL | alle 60 s und sofort bei Push |
| Neue Ereignisse (Push) | AppSync-Echtzeit-Subscription | innerhalb von Sekunden |
| Statistik | REST | alle 30 min |
| Ereignislisten der Karten | GraphQL, Seiten zu 100 | beim Laden, Filtern oder Nachladen einer Karte |
| Bilder | S3, signiert mit temporären AWS-Zugangsdaten | bei Bedarf, im Speicher zwischengespeichert |
| Katzen-Zuordnung | Recorder von Home Assistant | mit jeder Ereignisliste |

Die Sitzung wird automatisch mit Cognito-Refresh-Tokens erneuert. Ist das Refresh-Token
nicht mehr gültig, meldet sich die Integration mit den gespeicherten Zugangsdaten neu an.
Scheitert auch das, fordert Home Assistant zur erneuten Anmeldung auf. Ist die Cloud nicht
erreichbar, werden die Entitäten unverfügbar und erholen sich automatisch.

## Beispiele und Anwendungsfälle

### Benachrichtigung bei Beute, mit Bild

```yaml
automation:
  - alias: ZeroMOUSE Beute-Alarm
    triggers:
      - trigger: event
        event_type: zeromouse_event
        event_data:
          classification: prey
    actions:
      - action: notify.mobile_app_handy
        data:
          title: "Beute an der Katzenklappe"
          message: >
            {{ trigger.event.data.cat or 'Eine Katze' }} wollte um
            {{ as_timestamp(trigger.event.data.time) | timestamp_custom('%H:%M') }}
            Beute mitbringen.
          data:
            image: "{{ state_attr('image.katzenklappe_letztes_ereignisbild', 'entity_picture') }}"
```

### „early“-Ereignisse automatisch löschen

Die App zeigt sie als *Keine Beute erkannt*, obwohl das Gerät sie als versteckt markiert.

```yaml
automation:
  - alias: ZeroMOUSE aufräumen
    triggers:
      - trigger: event
        event_type: zeromouse_event
        event_data:
          classification: early
    actions:
      - action: zeromouse.delete_event
        data:
          device_id: "{{ trigger.event.data.device_id }}"
          event_id: "{{ trigger.event.data.event_id }}"
```

### Nachts den Ausgang sperren

```yaml
automation:
  - alias: Katzen bleiben nachts drin
    triggers:
      - trigger: sun
        event: sunset
    actions:
      - action: select.select_option
        target:
          entity_id: select.katzenklappe_ausgangsmodus
        data:
          option: locked
  - alias: Katzen dürfen morgens raus
    triggers:
      - trigger: time
        at: "07:00:00"
    actions:
      - action: select.select_option
        target:
          entity_id: select.katzenklappe_ausgangsmodus
        data:
          option: open
```

### Auf jede Erkennung mit der Ereignis-Entität reagieren

```yaml
triggers:
  - trigger: state
    entity_id: event.katzenklappe_erkennung
    not_from: [unavailable, unknown]   # nach einem Ausfall nicht erneut auslösen
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'undecidable' }}"
```

Weitere Ideen:

- Beute pro Monat mit den Statistik-Sensoren im Dashboard zählen.
- Während der Abwesenheit *Verhalten bei „Nicht entscheidbar“* auf *Immer blockieren*
  stellen.
- In der Zeitleiste sehen, welche Katze wann Beute mitbringt.

Die Entitäts-IDs in den Beispielen hängen von der Sprache und dem Gerätenamen ab; prüfe sie
unter *Einstellungen → Geräte & Dienste → Entitäten*.

## Bekannte Einschränkungen

- **Inoffizielle API.** Rekonstruiert aus den App-Versionen 1.13 und 1.14 (2025–2026).
  Änderungen am Backend können die Integration jederzeit unbrauchbar machen.
- **Nur Cloud.** Eine lokale Schnittstelle gibt es nicht; ohne Internet wird nichts
  aktualisiert.
- **Zugangsdaten werden gespeichert** (im Config-Entry von Home Assistant), weil Cognito
  keine langlebigen Tokens kennt und nach Ablauf des Refresh-Tokens eine vollständige
  Anmeldung nötig ist.
- **Keine Zwei-Faktor-Anmeldung.** Konten, die sie verlangen, können sich nicht anmelden.
- **WLAN-Signal**: Firmware 0.17 meldet 0 dBm und aktualisiert den Wert nie. Der Sensor
  zeigt deshalb *unbekannt* und ist standardmäßig deaktiviert.
- **Beutesperre aktiv** wird aus dem letzten Beute-Ereignis und der Blockierdauer
  berechnet, nicht vom Gerät gemeldet.
- **Fähigkeiten werden nicht gemeldet.** Eingangsmodi wie Gesichtserkennung erscheinen
  auch, wenn Gerät oder Firmware sie nicht unterstützen.
- **Bis zu 20 Ereignisse pro Abfrage.** Passieren zwischen zwei Abfragen mehr als 20
  Ereignisse, lösen die älteren weder die Ereignis-Entität noch `zeromouse_event` aus. In
  den Karten sind sie trotzdem sichtbar.
- **Ereignisse während eines Neustarts** von Home Assistant (oder während es nicht läuft)
  lösen weder die Ereignis-Entität noch `zeromouse_event` aus; in den Karten erscheinen sie.
- **Beutesperre aktiv** geht mit der nächsten Abfrage nach Ablauf der Blockierdauer aus,
  bis zu 60 s verspätet.
- **Katzen-Zuordnung** reicht nur so weit zurück, wie der Recorder den Verlauf aufbewahrt,
  hängt davon ab, wie oft die Klappen-Integration abfragt, und wurde nur mit Sure Petcare
  getestet.
- **Seltene Filter** (z. B. *Hand*) brauchen eventuell mehrere Klicks auf „+“, weil die
  Cloud nur seitenweise lesbar ist, 100 Ereignisse auf einmal.

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| *E-Mail oder Passwort ungültig* bei der Einrichtung | Prüfe, ob die Anmeldung in der ZeroMOUSE-App mit denselben Daten klappt. Konten mit Zwei-Faktor-Anmeldung werden nicht unterstützt. |
| *Keine Verbindung zur ZeroMOUSE-Cloud* | Internetzugang von Home Assistant prüfen. Die Integration versucht es automatisch erneut. |
| Entitäten sind unverfügbar | Die Cloud war nicht erreichbar. Sie erholen sich mit der nächsten erfolgreichen Abfrage. Details stehen im Log. |
| Home Assistant fordert zur erneuten Anmeldung auf | Das Passwort wurde geändert oder die Sitzung widerrufen. Aktuelles Passwort eingeben. |
| *Custom element doesn't exist: zeromouse-…-card* | Seite neu laden. Nach einem Update nutzt der Browser eventuell noch eine zwischengespeicherte Startseite. |
| Ereignisse kommen nur minütlich | Die Echtzeit-Verbindung kam nicht zustande. Die Abfrage funktioniert trotzdem; mit Debug-Logging siehst du den Grund. |
| Keine Katze in den Karten | Die Entität unter *Entwicklerwerkzeuge → Zustände* prüfen: Ändert sich ihr Verlauf bei jedem Durchgang? Eine ausdrückliche `preset` versuchen. Der Recorder muss aktiv sein und darf die Entität nicht ausschließen. |
| Viele *unbekannte* Ereignisse | Siehe Hinweis unter [Verknüpfen](#ereignisse-mit-der-katzenklappe-verknüpfen). Vergrößere `window_after` nur, wenn deine Klappen-Integration selten abfragt. |
| Nach **+** beginnt die Liste wieder von vorn | Home Assistant wurde zwischendurch neu gestartet und hat vergessen, wo die Liste stand; die Karte lädt sie neu. |

**Debug-Logging**

```yaml
logger:
  logs:
    custom_components.zeromouse: debug
```

**Diagnose**: *Einstellungen → Geräte & Dienste → ZeroMOUSE → ⋮ → Diagnose herunterladen*
liefert die Rohdaten aller Geräte. E-Mail, Passwort, Owner- und Identity-IDs sowie
WLAN-Namen werden entfernt. Bitte hänge die Datei an Fehlerberichte an.

## Datenschutz und Sicherheit

- Home Assistant spricht nur mit der ZeroMOUSE-Cloud bei AWS (Cognito, AppSync, API
  Gateway und S3 in `eu-central-1`), genau wie die App. Andere Dienste werden nicht
  kontaktiert.
- Bilder werden bei Bedarf geladen und nur im Arbeitsspeicher gehalten. Der Bild-Endpunkt
  `/api/zeromouse/image/…` verlangt einen angemeldeten Home-Assistant-Benutzer.
- Die Dashboard-Karten lesen Daten über die WebSocket-API von Home Assistant mit den
  Rechten des angemeldeten Benutzers. Die Katzen-Zuordnung liest nur Entitäten, die der
  Benutzer lesen darf.
- *Löschen* entfernt das Ereignis in der ZeroMOUSE-Cloud, wie in der App.

## Entfernen

1. **Einstellungen → Geräte & Dienste → ZeroMOUSE → ⋮ → Löschen**. Das entfernt Geräte,
   Entitäten und gespeicherte Zugangsdaten.
2. Die ZeroMOUSE-Karten aus den Dashboards entfernen.
3. Die Integration in HACS bzw. im Marketplace deinstallieren oder
   `<config>/custom_components/zeromouse` löschen.
4. `<config>/www/zeromouse/` löschen, falls du dort Icons angelegt hast.
5. Home Assistant neu starten.

Dein ZeroMOUSE-Konto und das Gerät bleiben davon unberührt.

## Qualitätsskala

Selbsteinschätzung nach der
[Integration Quality Scale von Home Assistant](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Details pro Regel: [`quality_scale.yaml`](custom_components/zeromouse/quality_scale.yaml).

| Stufe | Status |
|---|---|
| 🥉 Bronze | Alle Regeln erfüllt (Auslöser und Bedingungen ausgenommen: keine vorhanden) |
| 🥈 Silber | Alle Regeln erfüllt. Testabdeckung über 95 %. |
| 🥇 Gold | Alle Regeln erfüllt (Discovery bei einem Cloud-Konto ausgenommen, Repair-Issues ausgenommen) |
| 🏆 Platin | Alle Regeln erfüllt: eigener asyncio-Client auf aiohttp, übergebene Web-Session, `mypy --strict` fehlerfrei |

Custom-Integrationen werden vom Home-Assistant-Projekt nicht geprüft; die Tabelle gibt die
Einschätzung des Autors wieder. Für eine Aufnahme in Home Assistant Core müsste der
API-Client als eigene Bibliothek auf PyPI veröffentlicht werden.

## Entwicklung

Aufbau, Tests und das Kommandozeilen-Werkzeug sind im Abschnitt
[Development](README.md#development) der englischen README beschrieben.

## Lizenz und Marken

Der Code steht unter der [MIT-Lizenz](LICENSE).

ZeroMOUSE und das ZeroMOUSE-Logo sind Marken ihres jeweiligen Inhabers und werden hier nur
verwendet, um das Produkt zu benennen, mit dem diese Integration zusammenarbeitet. Sure
Petcare, SureFlap, PetSafe, Cat Mate, Ferplast und OnlyCat sind Marken ihrer jeweiligen
Inhaber.

Maintainer: [@JoergWall](https://github.com/JoergWall). Fehler und Ideen bitte als
[Issue](https://github.com/JoergWall/zeromouse-homeassistant/issues) melden.
