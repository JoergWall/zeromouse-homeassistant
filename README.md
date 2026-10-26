# ZeroMOUSE for Home Assistant

*[Deutsche Version](README.de.md)*

An **unofficial** Home Assistant integration for [ZeroMOUSE](https://zeromouse.com), the
AI-based prey detection add-on for microchip cat flaps. It brings your ZeroMOUSE devices,
their detection events, pictures, statistics and settings into Home Assistant, with
realtime updates and two dashboard cards that show events the way the ZeroMOUSE app does.
Optionally it tells you **which cat** it was, by matching events with the passages your
cat flap reports to Home Assistant.

> [!IMPORTANT]
> This project is not affiliated with, endorsed by or supported by the manufacturer of
> ZeroMOUSE. ZeroMOUSE does not publish an API; the cloud interface used here was
> reconstructed from the official app for interoperability (see [API.md](API.md)). The
> manufacturer can change the backend at any time, which may break the integration
> without notice. Use at your own risk.

---

## Contents

- [Features](#features)
- [Supported devices and cat flaps](#supported-devices-and-cat-flaps)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Actions](#actions)
- [Events](#events)
- [Dashboard cards](#dashboard-cards)
- [Matching events with your cat flap](#matching-events-with-your-cat-flap)
- [How data is updated](#how-data-is-updated)
- [Examples and use cases](#examples-and-use-cases)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Privacy and security](#privacy-and-security)
- [Removal](#removal)
- [Quality scale](#quality-scale)
- [Development](#development)
- [License and trademarks](#license-and-trademarks)

## Features

- Set up from the UI with your ZeroMOUSE app account; reauthentication and
  reconfiguration are supported.
- **Detection events** such as *prey detected*, *no prey*, *inconclusive*, *hand* or
  *leaving*, as sensors, an event entity and a Home Assistant bus event.
- **Realtime**: new events arrive within seconds through the same push channel the app
  uses (AWS AppSync subscription). The integration also polls every 60 s.
- **Pictures**: the latest event picture as an image entity. The gallery card shows all
  pictures of every event as an animation.
- **Feedback like in the app**: mark events as *right* or *wrong* (this trains the AI)
  and delete events, from the dashboard or with actions in automations.
- **Control**: entry mode, exit mode and its time window, handling of inconclusive
  events, prey block duration, prey blocking on/off, per-cat entry permission and
  blocking of unknown cats.
- **Statistics**: prey per month and in total.
- **Which cat was it?** Events can be matched with the passages of any cat flap that
  reports to Home Assistant (tested with Sure Petcare), with plain door or vibration
  sensors on flaps without connectivity, or with ZeroMOUSE's own face detection.
- **Dashboard cards**: an event gallery with the app's filters and unlimited
  "load more", and a timeline of the last days.
- Diagnostics, German and English translations.

## Supported devices and cat flaps

### ZeroMOUSE

| Device | Status |
|---|---|
| ZeroMOUSE 2.0 (firmware 0.17.x, EU cloud, app 1.14.x) | Tested |
| Other ZeroMOUSE devices that use the ZeroMOUSE app | Expected to work, not tested |
| ZeroMOUSE Cat Flap (the manufacturer's own flap) | Unknown, not tested |

Settings the device does not support are still shown, because the cloud API does not
report device capabilities.

### Cat flaps

ZeroMOUSE sits in front of an existing **microchip** cat flap. When it sees prey it sends
a "foreign chip" signal to the flap's RFID reader, so the flap stays locked with its own
logic. The integration does not talk to the flap. The flap only matters if you want to
know which cat it was (see [Matching events with your cat flap](#matching-events-with-your-cat-flap)).

| Cat flap | Compatible with ZeroMOUSE ¹ | Passages in Home Assistant | Matching |
|---|---|---|---|
| Sure Petcare: SureFlap DualScan, Microchip Pet Door / Cat Flap Connect | Yes | Yes, with a hub (core *surepetcare*, *sureha*, *surepcha*) | **Tested** |
| Sure Petcare: SureFlap Microchip Cat Flap (without hub) | Yes (dealer statement) | No | ZeroMOUSE face detection or DIY sensor |
| PetSafe Microchip Cat Flap (not PetPorte; needs an adapter) | Yes | No (no connectivity) | ZeroMOUSE face detection or DIY sensor |
| PetSafe SmartDoor Connected | Not listed | Yes (*petsafe_extended*) | Preset `petsafe`, untested ² |
| Cat Mate Elite, Cat Mate 360 | Yes (app 1.14.14 or newer) | No (no connectivity) | ZeroMOUSE face detection or DIY sensor |
| Ferplast microchip flaps | No statement | No (no connectivity) | ZeroMOUSE face detection or DIY sensor |
| OnlyCat | No statement (has its own prey detection) | Yes (OnlyCat integration) | Preset `onlycat`, untested ² |

¹ According to the manufacturer's FAQ and product pages as of October 2026; please check
the current list on zeromouse.com before buying. A flap needs a flat tunnel.
² The developer only had a Sure Petcare flap. The presets for other flaps follow the
source code of their Home Assistant integrations and were never tested with real
events. Feedback is welcome.

## Requirements

- Home Assistant **2026.8** or newer (tested with 2026.9 and 2026.10).
- A ZeroMOUSE account (email and password) with at least one device set up in the app.
  Accounts that require multi-factor authentication are not supported.
- Internet access from Home Assistant to the ZeroMOUSE cloud (AWS, region
  `eu-central-1`).
- Optional, for matching events with cats: the recorder (enabled by default) and a cat
  flap integration or sensor, see [below](#matching-events-with-your-cat-flap).

## Installation

### HACS / Home Assistant Marketplace

1. Home Assistant 2026.10 and older: in HACS open ⋮ → *Custom repositories*.
   Home Assistant 2026.11 and newer: open *Settings → Marketplace*, ⋮ → *Custom repositories*.
2. Add `https://github.com/JoergWall/zeromouse-homeassistant` with the category *Integration*.
3. Search for **ZeroMOUSE**, install it and restart Home Assistant.

HACS and the Marketplace can only install public repositories.

### Manual

1. Download the latest release (or the repository).
2. Copy `custom_components/zeromouse` to `<config>/custom_components/zeromouse` so that
   `<config>/custom_components/zeromouse/manifest.json` exists.
3. Restart Home Assistant.

### Set up the integration

1. Go to **Settings → Devices & services → Add integration** and search for
   **ZeroMOUSE**.
2. Enter the credentials of your ZeroMOUSE app:

   | Field | Description |
   |---|---|
   | Email | The email address you use to sign in to the ZeroMOUSE app. |
   | Password | The password of that account. |

3. The integration signs in, reads your devices and creates one Home Assistant device per
   ZeroMOUSE. Each ZeroMOUSE account can be added once. Devices you add to the account
   later appear automatically; devices removed from the account are removed from Home
   Assistant.

## Configuration

There are no options to configure. All device settings are exposed as entities (see
below) and take effect in the cloud immediately, just as in the app.

- **Reauthentication**: if the password changes, Home Assistant shows a notification
  under *Settings → Devices & services* that asks for the new password.
- **Reconfiguration**: *Settings → Devices & services → ZeroMOUSE → ⋮ → Reconfigure* lets
  you change email and password. The credentials must belong to the same account.

## Entities

Entity names below are the English defaults.

### Sensors

| Entity | Description | Notes |
|---|---|---|
| Last event | Classification of the newest event: `prey`, `clean`, `undecidable`, `out`, `hand`, `early`, `late`, `free`, `test`, `unknown` | Attributes: `event_id`, `cat`, `image_count`, `is_favorite` |
| Last event time | Time of the newest event | Timestamp |
| Last prey | Time of the newest event classified as prey | Timestamp |
| Last cat | Name of the cat ZeroMOUSE recognised for the newest event (face detection) | Empty without cat profiles |
| Prey this month | Prey detected in the current month | From the statistics API |
| Prey total | Sum of all months the statistics API returns | Attribute `monthly` lists every month |
| Event count | Number of events recorded by the device | Diagnostic |
| AI personalization status | How well the AI is adapted to your setup, in % | Diagnostic |
| Feedback score | Your feedback activity, in % | Diagnostic |
| Wi-Fi signal | Wi-Fi RSSI in dBm | Diagnostic, disabled by default (see [limitations](#known-limitations)) |
| Boot count | Number of device restarts | Diagnostic, disabled by default |

### Binary sensors

| Entity | Description |
|---|---|
| Prey block active | On while the last prey event is younger than the configured prey block duration. This is derived by the integration; the cloud does not report whether the flap is actually locked. |
| Connectivity | Whether the device is connected to the cloud. Diagnostic. |

### Controls

| Entity | Type | Values | Option values for automations |
|---|---|---|---|
| Entry mode | select | Free entry, Block prey, Face detection, Locked | `free_entry`, `blocking_prey`, `face_detection`, `locked` |
| Exit mode | select | Open, Locked, Time based | `open`, `locked`, `time_based` |
| Exit open from / Exit open until | time | Time window for the time based exit mode | `"07:30:00"` |
| Inconclusive event handling | select | Smart mode (block only if prey was seen recently), Always allow, Always block | `smart`, `always_allow`, `always_block` |
| Prey block duration | select | 10 s … 60 min minimum lock time after prey | seconds as text: `"10"`, `"15"`, `"30"`, `"60"`, `"120"`, `"300"`, `"600"`, `"900"`, `"1800"`, `"3600"` |
| Block prey | switch | Off = only record events, do not block | |
| Block unknown cats | switch | In face detection mode, block cats that are not in your cat list | |
| `<cat>` allow entry | switch | One per cat profile; applies in face detection mode. Cats added in the app appear automatically. | |

### Other

| Entity | Description |
|---|---|
| Last event image | Preview picture of the newest event |
| Detection (event entity) | Fires once per new event with the classification as event type and the attributes `event_id`, `cat` and `time` |

### Classifications

Sensors, the event entity and `zeromouse_event` report the raw value. The app (and the
cards of this integration) show it in five groups:

| Value | Shown as | Notes |
|---|---|---|
| `clean`, `early` | No prey detected | the device marks `early` as hidden |
| `prey` | Prey detected | |
| `undecidable`, `late`, `unknown` | Inconclusive | `undecidable` and `late` are marked hidden but still listed |
| `test` (`hand`) | Hand detected | |
| `out` | Leaving detected | marked hidden |
| `free`, other values | Inconclusive | not listed without a filter |

## Actions

| Action | Fields | Description |
|---|---|---|
| `zeromouse.rate_event` | `device_id`, `event_id`, `rating` (`correct` / `incorrect` / `none`) | Gives the same feedback as *Right* / *Wrong* in the app. ZeroMOUSE uses it to retrain the AI. `none` removes the rating, like tapping the active button again in the app. |
| `zeromouse.delete_event` | `device_id`, `event_id` | Deletes an event like *Delete* in the app. |

`device_id` is the Home Assistant device of the ZeroMOUSE (device selector in the UI),
`event_id` comes from the `zeromouse_event` bus event, the event entity or the *Last
event* sensor. Wrong input raises a validation error, cloud errors a translated error
message.

```yaml
action: zeromouse.rate_event
data:
  device_id: "{{ trigger.event.data.device_id }}"
  event_id: "{{ trigger.event.data.event_id }}"
  rating: correct
```

## Events

Every new detection also fires the bus event `zeromouse_event`:

```yaml
event_type: zeromouse_event
data:
  device_id: "8f1c…"                       # Home Assistant device id (for the actions)
  zeromouse_device_id: "AbCdEf0123456789xyzABC"
  device_name: "Cat flap"
  event_id: "6ab3be5c-…"
  classification: prey                    # see "Last event" for all values
  cat: null                               # cat name if ZeroMOUSE recognised it
  time: "2026-09-23T11:56:12+00:00"
```

The integration provides no triggers or conditions of its own. Use the entities and the
bus event in automations.

## Dashboard cards

The integration ships two Lovelace cards. They are loaded automatically; you do not need
to add a resource. Both work without any cat flap configuration.

### Event gallery: `custom:zeromouse-events-card`

Shows events like the app: the pictures of each event play as an animation (click to
pause), below them the classification, the device, the time and, if configured, the cat.

- **Filter** button with the app's filters: *No prey detected*, *Prey detected*,
  *Inconclusive*, *Hand detected*, *Leaving detected*, *Show favorites only* and *Reset*.
  Like in the app, all boxes except *Leaving detected* are checked at first, each box
  covers the values listed under [Classifications](#classifications), and *Show favorites
  only* shows all favourites regardless of the other boxes. The selection is remembered
  per browser.
- **Wrong / Right / Delete** buttons under each event, with a confirmation for *Wrong*
  and *Delete*. Tapping the active *Wrong* or *Right* again removes the rating.
- A **+** tile at the end loads older events, as many as you like. Pictures load only for
  events on screen.

```yaml
type: custom:zeromouse-events-card
title: Cat flap      # optional heading
limit: 10            # events per page
fps: 2               # pictures per second
language: en         # de or en; default: the Home Assistant language
show_filter: true    # filter button
show_actions: true   # wrong / right / delete buttons
confirm: true        # ask before "wrong" and "delete"
show_hidden: false   # also check "Leaving detected" at first
filter:              # boxes checked at first: clean, prey, undecidable, hand, out
  classifications: [prey]  # default: all but out (out too with show_hidden)
  favorites_only: false
remember_filter: true  # remember the user's filter per card and browser
storage_key: kitchen   # optional, own key for the remembered filter
flap_name: SureFlap  # how passages are labelled, default "Flap"
correlate:           # optional, see "Matching events with your cat flap"
  - entity: binary_sensor.tiger
    name: Tiger
    color: "#2a78d6"
window_before: 60    # optional matching window in seconds (0–3600)
window_after: 180
```

The remembered filter is stored in the browser per card (title, configured filter and
dashboard). Animations start paused when the system asks for reduced motion; pictures
can be paused with a click or with Enter/Space.

### Timeline: `custom:zeromouse-timeline-card`

One row per day and one round marker for every event with the result *no prey*,
*prey* or *inconclusive*, grouped like the app (see [Classifications](#classifications);
hand and leaving events are left out). The
marker's background shows the **result** (green = no prey, red = prey, orange =
inconclusive); with cat matching it also shows **who** it was, in one lane per cat.

```yaml
type: custom:zeromouse-timeline-card
title: Who came when  # optional, default depends on the language
days: 10
language: en          # de or en; default: the Home Assistant language
correlate:            # optional
  - entity: binary_sensor.tiger
    name: Tiger
    icon: /local/zeromouse/tiger-{class}.webp   # optional; {class} = clean | prey | undecidable
  - entity: binary_sensor.luna
    name: Luna
unknown_icon: /local/zeromouse/unknown.webp     # optional, {class} works here too
unknown_name: Unknown # label of events without a cat
flap_name: SureFlap   # label of passages in the tooltips
night_start: 22       # shaded night hours
night_end: 6
note: ""              # optional: replace or hide the explanatory note
window_before: 60     # optional matching window in seconds (0–3600)
window_after: 180
```

Without `icon` a cat is shown as a coloured circle with its initial. Own round pictures
(for example 96 × 96 px WebP or PNG) go into `<config>/www/zeromouse/`.

## Matching events with your cat flap

ZeroMOUSE sees *that* a cat is at the flap, but without face detection not *which* cat.
Microchip flaps that report to Home Assistant know the cat. Both happen at nearly the
same moment, so the integration can pair them by time.

### How it works

1. Each cat gets a **passage source**: one Home Assistant entity whose history shows the
   cat's passages through the flap.
2. The integration reads the history of these entities from the recorder and turns it
   into passages (time, direction in/out, cat).
3. Each ZeroMOUSE event is paired with the closest passage within a time window
   (default 60 s before to 180 s after the event), one to one. Events of the
   classifications *no prey*, *prey*, *inconclusive* and *hand* need a passage *in*,
   *leaving* needs a passage *out*; a passage without known direction fits both.
4. If no passage fits but ZeroMOUSE recognised the cat itself (face detection), that cat
   is used.

The pairing runs on the Home Assistant server whenever a card asks for events, so it
also works for events of the past, as far back as the recorder keeps history.

> [!NOTE]
> On *prey detected* and *inconclusive* ZeroMOUSE blocks the flap, so the cat does not
> pass and the flap reports nothing. These events stay *unknown* unless ZeroMOUSE
> recognises the cat itself. Many flaps also do not register cats going out, so
> *leaving* events rarely find a passage.

### Configuration

The `correlate` list is the same in both cards:

| Key | Meaning |
|---|---|
| `entity` | The entity that shows the cat's passages (omit it for a cat that only ZeroMOUSE recognises) |
| `name` | Name of the cat |
| `preset` | How passages are read: `auto` (default), `sureflap`, `sureflap_state`, `petsafe`, `onlycat`, `state`, `event`, `attribute` |
| `source` | Advanced: `attribute`, `state` or `event`, overrides the preset's way of reading |
| `time_attribute` | Attribute holding the passage time. Defaults: `state` source → time of the state change, `event` source → the state (time of the event), `attribute` source → `since` |
| `direction_attribute` | Attribute holding the direction. Defaults: `state` source → the state, `event` source → `event_type`, `attribute` source → no direction |
| `in` / `out` | Values that mean "came in" / "went out" (case-insensitive) |
| `filter` | Only use history rows whose attributes have these values, e.g. one cat on a flap-wide entity |
| `color`, `icon` | Display options of the cards |

`window_before` and `window_after` (seconds, 0–3600, set on the card) define the time
window for all sources.

| Preset | Reads | Typical entity |
|---|---|---|
| `sureflap` | every new `since`, direction from `where` (1 = in, 2 = out) | Sure Petcare pet `binary_sensor` (core integration, *sureha*) |
| `sureflap_state` | every new `since`, direction from the state (on = inside) | *surepcha* presence sensor |
| `petsafe` | event entity, time from `occurred_at`, `pet_entered` / `pet_exited` | *petsafe_extended* "‹pet› Activity" event entity |
| `onlycat` | `timestamp`, direction `INWARD` / `OUTWARD`; add a `filter` on `rfidCode` per cat | OnlyCat "Flap event" `binary_sensor` |
| `state` | every state change; on/home = in, off/not_home = out | presence sensors, door/contact sensors |
| `event` | every event of an event entity, direction from `event_type` | ESPHome or Zigbee event entities |
| `attribute` | your own `time_attribute` / `direction_attribute` | anything else |

With `auto` the preset is chosen from the entity: `event.*` gives `event` (or `petsafe`
with an `occurred_at` attribute), an entity with `since` and `where` gives `sureflap`,
`since` alone gives `sureflap_state`, OnlyCat's attributes give `onlycat`, everything
else `state`.

### Example: Sure Petcare (tested)

The core *surepetcare* integration and *sureha* create one presence `binary_sensor` per
pet. Its attribute `since` changes on every passage, `where` tells the direction. Because
the integrations poll the cloud every 2.5–3 minutes, the *state* only changes when the
location changes, but `since` carries the exact server time of the last passage.

```yaml
correlate:
  - entity: binary_sensor.tiger       # core integration; sureha: binary_sensor.pet_tiger
    name: Tiger
  - entity: binary_sensor.luna
    name: Luna
```

In the author's setup the Sure Petcare passage followed the ZeroMOUSE event by
**9 to 16 seconds**. Over ten days 58 of 67 Sure Petcare passages were matched within a
minute. If two passages of the same cat happen between two polls, only the second one
is visible.

### Example: PetSafe SmartDoor Connected (untested)

```yaml
correlate:
  - entity: event.tiger_activity      # "Tiger Activity" event entity of petsafe_extended
    name: Tiger
    preset: petsafe
```

### Example: OnlyCat (untested)

The OnlyCat integration has one "Flap event" sensor per flap whose attributes contain the
cat's RFID, the direction and the action. Filter it per cat:

```yaml
correlate:
  - entity: binary_sensor.oc_00000000001_event
    name: Tiger
    preset: onlycat
    filter:
      rfidCode: "900123456789012"
      action: [TRANSIT, BREACH]
```

### Flaps without connectivity (Cat Mate, Ferplast, PetSafe Microchip, SureFlap without hub)

These flaps report nothing. Two options:

- **ZeroMOUSE face detection**: create cat profiles in the ZeroMOUSE app. Recognised
  cats appear in the gallery card and in the `cat` field of events without any
  configuration. For an own lane (and icon) in the timeline, list the cat by its
  ZeroMOUSE name without an entity: `- name: Tiger`.
- **A sensor on the flap**: a door/contact sensor, a vibration sensor or an ESPHome
  build with two reed contacts or light barriers. Such sensors show *that* the flap
  moved (and maybe the direction), not *which* cat. One source with a generic name
  confirms that the cat really came in:

  ```yaml
  correlate:
    - entity: binary_sensor.cat_flap_contact   # or event.cat_flap_opening (ESPHome)
      name: Flap
      in: ["on", "inside"]
      out: ["outside"]
  ```

## How data is updated

| What | How | When |
|---|---|---|
| Devices, cat profiles, scores | GraphQL (AWS AppSync) | every 60 s |
| Settings and connection state (device shadow) | REST | every 60 s |
| Newest 20 events | GraphQL | every 60 s, and right away on push |
| New events (push) | AppSync realtime subscription | within seconds |
| Statistics | REST | every 30 min |
| Event lists of the cards | GraphQL, pages of 100 | when a card loads, filters or loads more |
| Pictures | S3, signed with temporary AWS credentials | on demand, cached in memory |
| Cat matching | Home Assistant recorder | with each event list |

The session is refreshed automatically with Cognito refresh tokens. If the refresh token
is no longer valid, the integration signs in again with the stored credentials. If that
fails, Home Assistant asks you to reauthenticate. When the cloud cannot be reached, the
entities become unavailable and recover automatically.

## Examples and use cases

### Notify when prey is detected, with picture

```yaml
automation:
  - alias: ZeroMOUSE prey alert
    triggers:
      - trigger: event
        event_type: zeromouse_event
        event_data:
          classification: prey
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Prey at the cat flap"
          message: >
            {{ trigger.event.data.cat or 'A cat' }} tried to bring prey home
            at {{ as_timestamp(trigger.event.data.time) | timestamp_custom('%H:%M') }}.
          data:
            image: "{{ state_attr('image.cat_flap_last_event_image', 'entity_picture') }}"
```

### Delete "early" events automatically

The app lists them as *No prey detected* although the device marks them hidden.

```yaml
automation:
  - alias: ZeroMOUSE clean up
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

### Lock the exit at night

```yaml
automation:
  - alias: Cats stay in at night
    triggers:
      - trigger: sun
        event: sunset
    actions:
      - action: select.select_option
        target:
          entity_id: select.cat_flap_exit_mode
        data:
          option: locked
  - alias: Cats may go out in the morning
    triggers:
      - trigger: time
        at: "07:00:00"
    actions:
      - action: select.select_option
        target:
          entity_id: select.cat_flap_exit_mode
        data:
          option: open
```

### React to every detection with the event entity

```yaml
triggers:
  - trigger: state
    entity_id: event.cat_flap_detection
    not_from: [unavailable, unknown]   # do not fire again after an outage
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'undecidable' }}"
```

More ideas:

- Count prey per month on a dashboard with the statistics sensors.
- Switch *Inconclusive event handling* to *Always block* while you are away.
- Use the timeline to see which cat brings prey home and when.

Entity IDs in the examples depend on your language and device name; check them under
*Settings → Devices & services → Entities*.

## Known limitations

- **Unofficial API.** Reconstructed from app versions 1.13 and 1.14 (2025–2026). Backend
  changes by the manufacturer can break the integration at any time.
- **Cloud only.** There is no local API; without internet nothing updates.
- **Credentials are stored** in the Home Assistant config entry, because Cognito has no
  long-lived tokens and a full sign-in is needed when the refresh token expires.
- **No multi-factor authentication.** Accounts that require it cannot sign in.
- **Wi-Fi signal** is reported as 0 dBm by firmware 0.17 and never updated. The sensor
  therefore shows *unknown* and is disabled by default.
- **Prey block active** is calculated from the last prey event and the block duration,
  not reported by the device.
- **Capabilities are not reported.** Entry modes such as face detection appear even if
  the device or firmware does not support them.
- **Up to 20 events per poll.** Should more than 20 events happen between two refreshes,
  the older ones fire neither the event entity nor `zeromouse_event`. They are still
  visible in the cards.
- **Events during a restart** of Home Assistant (or while it is offline) fire neither the
  event entity nor `zeromouse_event`; they appear in the cards.
- **Prey block active** turns off with the next refresh after the block duration, up to
  60 s late.
- **Cat matching** only reaches back as far as the recorder keeps history, depends on
  how often the flap integration polls, and was only tested with Sure Petcare.
- **Rare filters** (for example *Hand*) may need several "load more" clicks, because the
  cloud can only be read page by page, 100 events at a time.

## Troubleshooting

| Problem | Solution |
|---|---|
| *Invalid email or password* during setup | Check that you can sign in to the ZeroMOUSE app with the same credentials. Accounts with MFA are not supported. |
| *Cannot reach the ZeroMOUSE cloud* | Check internet access from Home Assistant. The integration retries automatically. |
| Entities are unavailable | The cloud was not reachable. They recover with the next successful refresh. Check the log for details. |
| Home Assistant asks to reauthenticate | The password was changed or the session was revoked. Enter the current password. |
| *Custom element doesn't exist: zeromouse-…-card* | Reload the page. After an update the browser may still use a cached start page. |
| Events arrive only every minute | The realtime subscription could not connect. Polling still works; enable debug logging to see why. |
| No cat is shown in the cards | Check the entity in *Developer tools → States*: does its history change on every passage? Try an explicit `preset`. The recorder must be enabled and must not exclude the entity. |
| Many *unknown* events | See the note in [Matching events](#matching-events-with-your-cat-flap). Increase `window_after` only if your flap integration polls slowly. |
| The list starts again from the top after **+** | Home Assistant was restarted meanwhile and forgot where the list was; the card reloads it. |

**Debug logging**

```yaml
logger:
  logs:
    custom_components.zeromouse: debug
```

**Diagnostics**: *Settings → Devices & services → ZeroMOUSE → ⋮ → Download diagnostics*
returns the raw data of all devices. Email, password, owner and identity IDs and Wi-Fi
network names are removed. Please attach it to bug reports.

## Privacy and security

- Home Assistant talks only to the ZeroMOUSE cloud on AWS (Cognito, AppSync, API Gateway
  and S3 in `eu-central-1`), exactly like the app. No other service is contacted.
- Pictures are fetched on demand and kept only in memory. The image endpoint
  `/api/zeromouse/image/…` requires a signed-in Home Assistant user.
- The dashboard cards read data through the Home Assistant websocket API with the
  permissions of the signed-in user. Cat matching reads only entities the user is
  allowed to read.
- *Delete* removes the event in the ZeroMOUSE cloud, like in the app.

## Removal

1. Go to **Settings → Devices & services → ZeroMOUSE → ⋮ → Delete**. This removes the
   devices, entities and stored credentials.
2. Remove the ZeroMOUSE cards from your dashboards.
3. Uninstall the integration in HACS / the Marketplace, or delete
   `<config>/custom_components/zeromouse`.
4. Delete `<config>/www/zeromouse/` if you created icons there.
5. Restart Home Assistant.

Your ZeroMOUSE account and device are not changed by removing the integration.

## Quality scale

Self-assessment against the
[Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Details per rule: [`quality_scale.yaml`](custom_components/zeromouse/quality_scale.yaml).

| Tier | Status |
|---|---|
| 🥉 Bronze | All rules met (triggers and conditions exempt: none provided) |
| 🥈 Silver | All rules met. Test coverage above 95 %. |
| 🥇 Gold | All rules met (discovery exempt for a cloud account, repair issues exempt) |
| 🏆 Platinum | All rules met: own asyncio client on aiohttp, injected web session, `mypy --strict` clean |

Custom integrations are not reviewed by the Home Assistant project; this table reflects
the author's assessment. For inclusion in Home Assistant core, the API client would have
to be published as a separate library on PyPI.

## Development

```text
custom_components/zeromouse/
├── __init__.py          setup, unload, device removal
├── api.py               async cloud client (Cognito SRP, AppSync, REST, S3)
├── realtime.py          AppSync websocket subscription
├── coordinator.py       polling, event detection, stale devices
├── config_flow.py       setup, reauthentication, reconfiguration
├── entity.py            base entity, dynamic devices
├── binary_sensor.py … time.py   platforms
├── services.py          rate_event, delete_event
├── frontend.py          websocket command, image proxy, card registration
├── pager.py             filtered, unlimited paging of events
├── correlation.py       matching events with cat flap passages
├── diagnostics.py
├── www/zeromouse-events-card.js   both dashboard cards
├── brand/               integration icon
└── quality_scale.yaml
tools/zeromouse_cli.py   command line client for the API
tests/                   pytest suite
API.md                   reverse-engineered API documentation
```

```bash
pip install -r requirements_test.txt
```

```bash
pytest --cov=custom_components.zeromouse --cov-report=term-missing
```

```bash
mypy --strict --ignore-missing-imports --follow-imports=silent custom_components/zeromouse
```

```bash
ruff check custom_components/zeromouse
```

GitHub Actions run the HACS validation, hassfest, the tests, mypy and ruff on every push.

The command line tool uses the same client without Home Assistant and is handy to
inspect the raw API:

```bash
ZEROMOUSE_EMAIL=you@example.com python tools/zeromouse_cli.py dump
```

Other commands: `devices`, `shadow`, `events`, `raw-events`, `schema`, `stats`, `user`,
`image`, `watch`, `set-entry <0-3>`, `set-undecidable <0-2>`. The password is asked
interactively; output files are listed in `.gitignore` because they contain account
data.

## License and trademarks

The code is released under the [MIT License](LICENSE).

ZeroMOUSE and the ZeroMOUSE logo are trademarks of their respective owner and are used
here only to identify the product this integration works with. Sure Petcare, SureFlap,
PetSafe, Cat Mate, Ferplast and OnlyCat are trademarks of their respective owners.

Maintainer: [@JoergWall](https://github.com/JoergWall). Please report bugs and ideas as
[issues](https://github.com/JoergWall/zeromouse-homeassistant/issues).
