# ZeroMOUSE für Home Assistant

*[English version](README.md)*

Eine **inoffizielle** Home-Assistant-Integration für [ZeroMOUSE](https://zeromouse.com),
den KI-basierten Beute-Erkenner für Katzenklappen. Sie bringt deine ZeroMOUSE-Geräte, ihre
Erkennungen, Bilder, Statistiken und Einstellungen nach Home Assistant, mit
Echtzeit-Aktualisierung und zwei Dashboard-Karten, die Ereignisse wie die ZeroMOUSE-App
darstellen.

> [!IMPORTANT]
> Dieses Projekt steht in keiner Verbindung zum Hersteller von ZeroMOUSE und wird von ihm
> weder unterstützt noch empfohlen. ZeroMOUSE veröffentlicht keine API; die hier genutzte
> Cloud-Schnittstelle wurde zur Herstellung der Interoperabilität aus der offiziellen App
> rekonstruiert (siehe [API.md](API.md)). Der Hersteller kann das Backend jederzeit ändern,
> wodurch die Integration ohne Vorwarnung ausfallen kann. Nutzung auf eigenes Risiko.

---

## Inhalt

- [Funktionen](#funktionen)
- [Unterstützte Geräte](#unterstützte-geräte)
- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Entitäten](#entitäten)
- [Ereignisse](#ereignisse)
- [Dashboard-Karten](#dashboard-karten)
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
- **Erkennungen** wie *Beute erkannt*, *Keine Beute*, *Nicht entscheidbar* oder
  *Rausgehen* als Sensoren, als Ereignis-Entität und als Home-Assistant-Ereignis.
- **Echtzeit**: Neue Ereignisse kommen innerhalb weniger Sekunden über denselben
  Push-Kanal wie in der App (AWS-AppSync-Subscription). Zusätzlich fragt die Integration
  alle 60 s ab.
- **Bilder**: das Bild des letzten Ereignisses als Bild-Entität. Die Galerie-Karte
  spielt alle Bilder eines Ereignisses als Animation ab.
- **Steuerung**: Eingangsmodus, Ausgangsmodus mit Zeitfenster, Verhalten bei „Nicht
  entscheidbar“, Blockierdauer bei Beute, Beute blockieren an/aus, Eintritt pro Katze und
  Blockieren unbekannter Katzen.
- **Statistik**: Beute pro Monat und gesamt.
- **Diagnose**: Firmware, KI- und Feedback-Score, Cloud-Verbindung.
- **Dashboard-Karten**: eine Ereignis-Galerie und eine Zeitleiste. Beide können jedem
  Ereignis die Katze zuordnen, die laut einer Sure-Petcare-Klappe (SureFlap)
  durchgegangen ist.
- Deutsche und englische Übersetzung.

## Unterstützte Geräte

| Gerät | Status |
|---|---|
| ZeroMOUSE (Firmware 0.17.x, EU-Cloud) | Getestet |
| Andere ZeroMOUSE-Geräte, die die ZeroMOUSE-App nutzen | Sollte funktionieren, nicht getestet |
| Geräte ohne Konto in der ZeroMOUSE-App | Nicht unterstützt |

Einstellungen, die das Gerät nicht beherrscht (etwa Gesichtserkennung bei einer Firmware
ohne diese Funktion), werden trotzdem angezeigt, weil die Cloud-API die Fähigkeiten eines
Geräts nicht meldet.

## Voraussetzungen

- Home Assistant **2026.3** oder neuer (getestet mit 2026.9).
- Ein ZeroMOUSE-Konto (E-Mail und Passwort) mit mindestens einem in der App
  eingerichteten Gerät. Konten mit Zwei-Faktor-Anmeldung werden nicht unterstützt.
- Internetzugang von Home Assistant zur ZeroMOUSE-Cloud (AWS, Region `eu-central-1`).
- Optional, um Ereignisse Katzen zuzuordnen: eine Sure-Petcare-Integration, die pro Tier
  einen Präsenz-`binary_sensor` mit den Attributen `since` und `where` bereitstellt (etwa
  die Custom-Integration *sureha*).

## Installation

### HACS (empfohlen)

1. In HACS *Integrationen* → ⋮ → *Benutzerdefinierte Repositories* öffnen.
2. `https://github.com/joergwall/zeromouse-homeassistant` mit der Kategorie *Integration* hinzufügen.
3. Nach **ZeroMOUSE** suchen, installieren und Home Assistant neu starten.

### Manuell

1. Das Repository herunterladen.
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
| Letzte Katze | Name der beim neuesten Ereignis erkannten Katze (Gesichtserkennung) | Leer ohne Katzenprofile |
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

| Entität | Typ | Werte |
|---|---|---|
| Eingangsmodus | Auswahl | Freier Eintritt, Beute blockieren, Gesichtserkennung, Gesperrt |
| Ausgangsmodus | Auswahl | Offen, Gesperrt, Zeitbasiert |
| Ausgang offen ab / Ausgang offen bis | Uhrzeit | Zeitfenster für den zeitbasierten Ausgangsmodus |
| Verhalten bei „Nicht entscheidbar“ | Auswahl | Smarter Modus (blockiert nur, wenn kürzlich Beute erkannt wurde), Immer öffnen, Immer blockieren |
| Blockierdauer bei Beute | Auswahl | 10 s … 60 min Mindestsperrzeit nach Beute |
| Beute blockieren | Schalter | Aus = Ereignisse nur aufzeichnen, nicht blockieren |
| Unbekannte Katzen blockieren | Schalter | Blockiert bei Gesichtserkennung Katzen, die nicht in deiner Katzenliste stehen |
| `<Katze>` Eintritt erlauben | Schalter | Einer pro Katzenprofil; gilt bei Gesichtserkennung. In der App neu angelegte Katzen erscheinen automatisch. |

### Sonstiges

| Entität | Beschreibung |
|---|---|
| Letztes Ereignisbild | Vorschaubild des neuesten Ereignisses |
| Erkennung (Ereignis-Entität) | Löst pro neuem Ereignis einmal aus, mit der Klassifikation als Ereignistyp und den Attributen `event_id`, `cat` und `time` |

## Ereignisse

Jede neue Erkennung löst außerdem das Home-Assistant-Ereignis `zeromouse_event` aus:

```yaml
event_type: zeromouse_event
data:
  device_id: "AbCdEf0123456789xyzABC"   # ZeroMOUSE-Geräte-ID
  device_name: "Katzenklappe"
  event_id: "6ab3be5c-…"
  classification: prey                 # alle Werte siehe „Letztes Ereignis“
  cat: null                            # Name der Katze, falls erkannt
  time: "2026-09-23T11:56:12+00:00"
```

Die Integration registriert keine eigenen Aktionen, Auslöser oder Bedingungen. Nutze in
Automationen die Entitäten und das Ereignis.

## Dashboard-Karten

Die Integration bringt zwei Lovelace-Karten mit. Sie werden automatisch geladen; eine
Ressource musst du nicht anlegen.

### Ereignis-Galerie: `custom:zeromouse-events-card`

Zeigt die neuesten Ereignisse wie die App: Die Bilder jedes Ereignisses laufen als
Animation, darunter stehen Klassifikation, Gerät und Uhrzeit. Ein Klick aufs Bild
pausiert die Animation.

```yaml
type: custom:zeromouse-events-card
limit: 10            # Anzahl Ereignisse
fps: 2               # Bilder pro Sekunde
language: de         # de (Standard) oder en
show_hidden: false   # auch Ereignisse zeigen, die die App ausblendet (Rausgehen, zu früh/spät, …)
correlate:           # optional: Ereignisse Sure-Petcare-Durchgängen zuordnen
  - entity: binary_sensor.tiger
    name: Tiger
    color: "#2a78d6"
  - entity: binary_sensor.luna
    name: Luna
    color: "#eb6834"
window_before: 60    # Sekunden, die ein Durchgang vor dem Ereignis liegen darf
window_after: 180    # … bzw. danach
```

### Zeitleiste: `custom:zeromouse-timeline-card`

Eine Zeile pro Tag und ein rundes Icon pro Ereignis. Das Icon zeigt, **wer** es war (aus
Sure Petcare), der Hintergrund das **Ergebnis**: grün = keine Beute, rot = Beute, orange =
nicht entscheidbar. Ereignisse ohne passenden Durchgang zeigen `unknown_icon` mit farbigem
Ring. Die Karte berücksichtigt Ereignisse mit Beute, ohne Beute und „nicht entscheidbar“.

```yaml
type: custom:zeromouse-timeline-card
days: 10
language: de
correlate:
  - entity: binary_sensor.tiger
    name: Tiger
    icon: /local/zeromouse/tiger-{class}.webp   # {class} = clean | prey | undecidable
  - entity: binary_sensor.luna
    name: Luna
    icon: /local/zeromouse/luna-{class}.webp
unknown_icon: /local/zeromouse/unbekannt.webp
note: ""   # optional: Hinweistext ersetzen oder ausblenden
```

Lege eigene runde Icons (etwa 96 × 96 px, WebP oder PNG) in `<config>/www/zeromouse/` ab.

**So funktioniert die Zuordnung.** Eine Sure-Petcare-Klappe aktualisiert bei jedem
Durchgang das Attribut `since` des Tier-Sensors, `where` gibt die Richtung an (1 = kam
herein, 2 = ging hinaus). Die Karten lesen alle Durchgänge aus der Recorder-Historie und
ordnen jedem ZeroMOUSE-Ereignis den nächstgelegenen Durchgang in passender Richtung
innerhalb des Zeitfensters zu, jeweils eins zu eins. In der Praxis folgt der
Sure-Petcare-Durchgang dem ZeroMOUSE-Ereignis nach 9 bis 16 Sekunden.

> [!NOTE]
> Erkennt ZeroMOUSE Beute oder ein nicht entscheidbares Ereignis, sperrt es die Klappe.
> Die Katze geht dann nicht durch, und Sure Petcare registriert nichts. Solche Ereignisse
> erscheinen deshalb immer als *Unbekannt*. Die Zeitleiste erklärt das in ihrer Legende.

## Wie Daten aktualisiert werden

| Was | Wie | Wann |
|---|---|---|
| Geräte, Katzenprofile, Scores | GraphQL (AWS AppSync) | alle 60 s |
| Einstellungen und Verbindungsstatus (Device Shadow) | REST | alle 60 s |
| Neueste 20 Ereignisse | GraphQL | alle 60 s und sofort bei Push |
| Neue Ereignisse (Push) | AppSync-Echtzeit-Subscription | innerhalb von Sekunden |
| Statistik | REST | alle 30 min |
| Bilder | S3, signiert mit temporären AWS-Zugangsdaten | bei Bedarf, im Speicher zwischengespeichert |

Die Sitzung wird automatisch mit Cognito-Refresh-Tokens erneuert. Ist das Refresh-Token
nicht mehr gültig, meldet sich die Integration mit den gespeicherten Zugangsdaten neu an.
Scheitert auch das, fordert Home Assistant zur erneuten Anmeldung auf. Ist die Cloud
nicht erreichbar, werden die Entitäten unverfügbar und erholen sich automatisch.

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
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'undecidable' }}"
```

Weitere Ideen:

- Beute pro Monat mit den Statistik-Sensoren im Dashboard zählen.
- Während der Abwesenheit *Verhalten bei „Nicht entscheidbar“* auf *Immer blockieren*
  stellen.
- ZeroMOUSE mit Sure Petcare verknüpfen, um zu sehen, welche Katze Beute mitbringt.

Die Entitäts-IDs in den Beispielen hängen von der Sprache und dem Gerätenamen ab; prüfe
sie unter *Einstellungen → Geräte & Dienste → Entitäten*.

## Bekannte Einschränkungen

- **Inoffizielle API.** Rekonstruiert aus der App-Version vom 31.08.2025. Änderungen am
  Backend können die Integration jederzeit unbrauchbar machen.
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
  Ereignisse, lösen die älteren die Ereignis-Entität nicht aus. In den Karten sind sie
  trotzdem sichtbar.
- **Historie der Zeitleiste** ist durch die Aufbewahrungsdauer des Recorders (Sure
  Petcare) und die Option `days` begrenzt.
- **Zuordnung zu Sure Petcare** hängt davon ab, wie oft die Sure-Petcare-Integration
  abfragt. Bei zwei Durchgängen zwischen zwei Abfragen ist nur der zweite sichtbar.

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| *E-Mail oder Passwort ungültig* bei der Einrichtung | Prüfe, ob die Anmeldung in der ZeroMOUSE-App mit denselben Daten klappt. Konten mit Zwei-Faktor-Anmeldung werden nicht unterstützt. |
| *Keine Verbindung zur ZeroMOUSE-Cloud* | Internetzugang von Home Assistant prüfen. Die Integration versucht es automatisch erneut. |
| Entitäten sind unverfügbar | Die Cloud war nicht erreichbar. Sie erholen sich mit der nächsten erfolgreichen Abfrage. Details stehen im Log. |
| Home Assistant fordert zur erneuten Anmeldung auf | Das Passwort wurde geändert oder die Sitzung widerrufen. Aktuelles Passwort eingeben. |
| *Custom element doesn't exist: zeromouse-…-card* | Seite neu laden. Nach einem Update nutzt der Browser eventuell noch eine zwischengespeicherte Startseite. |
| Ereignisse kommen nur minütlich | Die Echtzeit-Verbindung kam nicht zustande. Die Abfrage funktioniert trotzdem; mit Debug-Logging siehst du den Grund. |
| Zeitleiste zeigt viele *Unbekannt* | Siehe Hinweis unter [Dashboard-Karten](#dashboard-karten). Vergrößere `window_after` nur, wenn deine Sure-Petcare-Integration selten abfragt. |

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
  Rechten des angemeldeten Benutzers.

## Entfernen

1. **Einstellungen → Geräte & Dienste → ZeroMOUSE → ⋮ → Löschen**. Das entfernt Geräte,
   Entitäten und gespeicherte Zugangsdaten.
2. Die ZeroMOUSE-Karten aus den Dashboards entfernen.
3. Die Integration in HACS deinstallieren oder `<config>/custom_components/zeromouse`
   löschen.
4. `<config>/www/zeromouse/` löschen, falls du dort Icons angelegt hast.
5. Home Assistant neu starten.

Dein ZeroMOUSE-Konto und das Gerät bleiben davon unberührt.

## Qualitätsskala

Selbsteinschätzung nach der
[Integration Quality Scale von Home Assistant](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Details pro Regel: [`quality_scale.yaml`](custom_components/zeromouse/quality_scale.yaml).

| Stufe | Status |
|---|---|
| 🥉 Bronze | Alle Regeln erfüllt (Aktionen, Auslöser und Bedingungen ausgenommen: keine vorhanden) |
| 🥈 Silber | Alle Regeln erfüllt. Testabdeckung 99 %. |
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
Petcare und SureFlap sind Marken ihres jeweiligen Inhabers.

Maintainer: [@joergwall](https://github.com/joergwall). Fehler und Ideen bitte als
[Issue](https://github.com/joergwall/zeromouse-homeassistant/issues) melden.
