# ZeroMOUSE for Home Assistant

*[Deutsche Version](README.de.md)*

An **unofficial** Home Assistant integration for [ZeroMOUSE](https://zeromouse.com), the
AI-based prey detection add-on for cat flaps. It brings your ZeroMOUSE devices, their
detection events, pictures, statistics and settings into Home Assistant, with realtime
updates and two dashboard cards that show events the way the ZeroMOUSE app does.

> [!IMPORTANT]
> This project is not affiliated with, endorsed by or supported by the manufacturer of
> ZeroMOUSE. ZeroMOUSE does not publish an API; the cloud interface used here was
> reconstructed from the official app for interoperability (see [API.md](API.md)). The
> manufacturer can change the backend at any time, which may break the integration
> without notice. Use at your own risk.

---

## Contents

- [Features](#features)
- [Supported devices](#supported-devices)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Events](#events)
- [Dashboard cards](#dashboard-cards)
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
- **Detection events** such as *prey detected*, *no prey*, *inconclusive* or *leaving*,
  as sensors, an event entity and a Home Assistant bus event.
- **Realtime**: new events arrive within seconds through the same push channel the app
  uses (AWS AppSync subscription). The integration also polls every 60 s.
- **Pictures**: the latest event picture as an image entity. The gallery card shows all
  pictures of an event as an animation.
- **Control**: entry mode, exit mode and its time window, handling of inconclusive
  events, prey block duration, prey blocking on/off, per-cat entry permission and
  blocking of unknown cats.
- **Statistics**: prey per month and in total.
- **Diagnostics**: firmware, AI and feedback scores, cloud connection.
- **Dashboard cards**: an event gallery and a timeline. Both can match events with the
  cat that passed according to a Sure Petcare (SureFlap) flap.
- German and English translations.

## Supported devices

| Device | Status |
|---|---|
| ZeroMOUSE (firmware 0.17.x, EU cloud) | Tested |
| Other ZeroMOUSE devices that use the ZeroMOUSE app | Expected to work, not tested |
| Devices without a ZeroMOUSE app account | Not supported |

Settings the device does not support (for example face detection on firmware that lacks
it) are still shown, because the cloud API does not report device capabilities.

## Requirements

- Home Assistant **2026.3** or newer (tested with 2026.9).
- A ZeroMOUSE account (email and password) with at least one device set up in the app.
  Accounts that require multi-factor authentication are not supported.
- Internet access from Home Assistant to the ZeroMOUSE cloud (AWS, region
  `eu-central-1`).
- Optional, for matching events to cats: a Sure Petcare integration that provides one
  presence `binary_sensor` per pet with the attributes `since` and `where` (for example
  the *sureha* custom integration).

## Installation

### HACS (recommended)

1. In HACS, open *Integrations* → ⋮ → *Custom repositories*.
2. Add `https://github.com/joergwall/zeromouse-homeassistant` with the category *Integration*.
3. Search for **ZeroMOUSE**, install it and restart Home Assistant.

### Manual

1. Download the repository.
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
   ZeroMOUSE. Each ZeroMOUSE account can be added once.

## Configuration

There are no options to configure. All device settings are exposed as entities (see
below) and take effect in the cloud immediately, just as in the app.

- **Reauthentication**: if the password changes, Home Assistant shows a notification
  under *Settings → Devices & services* that asks for the new password.
- **Reconfiguration**: *Settings → Devices & services → ZeroMOUSE → ⋮ → Reconfigure* lets
  you change email and password. The credentials must belong to the same account.

## Entities

Entity names below are the English defaults; `<device>` is the name you gave the
ZeroMOUSE in the app.

### Sensors

| Entity | Description | Notes |
|---|---|---|
| Last event | Classification of the newest event: `prey`, `clean`, `undecidable`, `out`, `hand`, `early`, `late`, `free`, `test`, `unknown` | Attributes: `event_id`, `cat`, `image_count`, `is_favorite` |
| Last event time | Time of the newest event | Timestamp |
| Last prey | Time of the newest event classified as prey | Timestamp |
| Last cat | Name of the cat recognised for the newest event (face detection) | Empty without cat profiles |
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

| Entity | Type | Values |
|---|---|---|
| Entry mode | select | Free entry, Block prey, Face detection, Locked |
| Exit mode | select | Open, Locked, Time based |
| Exit open from / Exit open until | time | Time window for the time based exit mode |
| Inconclusive event handling | select | Smart mode (block only if prey was seen recently), Always allow, Always block |
| Prey block duration | select | 10 s … 60 min minimum lock time after prey |
| Block prey | switch | Off = only record events, do not block |
| Block unknown cats | switch | In face detection mode, block cats that are not in your cat list |
| `<cat>` allow entry | switch | One per cat profile; applies in face detection mode. Cats added in the app appear automatically. |

### Other

| Entity | Description |
|---|---|
| Last event image | Preview picture of the newest event |
| Detection (event entity) | Fires once per new event with the classification as event type and the attributes `event_id`, `cat` and `time` |

## Events

Every new detection also fires the bus event `zeromouse_event`:

```yaml
event_type: zeromouse_event
data:
  device_id: "AbCdEf0123456789xyzABC"   # ZeroMOUSE device id
  device_name: "Cat flap"
  event_id: "6ab3be5c-…"
  classification: prey                 # see "Last event" for all values
  cat: null                            # cat name if recognised
  time: "2026-09-23T11:56:12+00:00"
```

The integration registers no service actions, triggers or conditions of its own. Use the
entities and the bus event in automations.

## Dashboard cards

The integration ships two Lovelace cards. They are loaded automatically; you do not need
to add a resource.

### Event gallery: `custom:zeromouse-events-card`

Shows the newest events like the app: the pictures of each event play as an animation,
below them the classification, the device and the time. Clicking a picture pauses it.

```yaml
type: custom:zeromouse-events-card
limit: 10            # number of events
fps: 2               # pictures per second
language: en         # de (default) or en
show_hidden: false   # also show events the app hides (leaving, too early/late, …)
correlate:           # optional: match events with Sure Petcare passages
  - entity: binary_sensor.tiger
    name: Tiger
    color: "#2a78d6"
  - entity: binary_sensor.luna
    name: Luna
    color: "#eb6834"
window_before: 60    # seconds a passage may lie before the event
window_after: 180    # … or after it
```

### Timeline: `custom:zeromouse-timeline-card`

One row per day and one round icon per event. The icon shows **who** (from Sure Petcare),
its background shows the **result**: green = no prey, red = prey, orange = inconclusive.
Events without a matching passage use `unknown_icon` with a coloured ring. The card
covers the events classified as prey, no prey and inconclusive.

```yaml
type: custom:zeromouse-timeline-card
days: 10
language: en
correlate:
  - entity: binary_sensor.tiger
    name: Tiger
    icon: /local/zeromouse/tiger-{class}.webp   # {class} = clean | prey | undecidable
  - entity: binary_sensor.luna
    name: Luna
    icon: /local/zeromouse/luna-{class}.webp
unknown_icon: /local/zeromouse/unknown.webp
note: ""   # optional: replace or hide the explanatory note
```

Put your own round icons (for example 96 × 96 px WebP or PNG) into `<config>/www/zeromouse/`.

**How matching works.** A Sure Petcare flap updates the `since` attribute of the pet's
sensor on every passage, and `where` tells the direction (1 = came in, 2 = went out). The
cards take all passages from the recorder history and pair each ZeroMOUSE event with the
closest passage in the right direction within the configured window, one to one. In
practice the Sure Petcare passage follows the ZeroMOUSE event by 9 to 16 seconds.

> [!NOTE]
> When ZeroMOUSE detects prey or an inconclusive event it blocks the flap, so the cat
> never passes and Sure Petcare records nothing. Such events therefore always appear as
> *unknown*. The timeline explains this in its legend.

## How data is updated

| What | How | When |
|---|---|---|
| Devices, cat profiles, scores | GraphQL (AWS AppSync) | every 60 s |
| Settings and connection state (device shadow) | REST | every 60 s |
| Newest 20 events | GraphQL | every 60 s, and right away on push |
| New events (push) | AppSync realtime subscription | within seconds |
| Statistics | REST | every 30 min |
| Pictures | S3, signed with temporary AWS credentials | on demand, cached in memory |

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
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'undecidable' }}"
```

More ideas:

- Count prey per month on a dashboard with the statistics sensors.
- Switch *Inconclusive event handling* to *Always block* while you are away.
- Correlate ZeroMOUSE with Sure Petcare to see which cat brings prey home.

## Known limitations

- **Unofficial API.** Reconstructed from app version 2025-08-31. Backend changes by the
  manufacturer can break the integration at any time.
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
  the older ones do not fire the event entity. They are still visible in the cards.
- **Timeline history** is limited by the retention of the recorder (Sure Petcare) and by
  the `days` option.
- **Sure Petcare matching** depends on how often the Sure Petcare integration polls. Two
  passages between two polls leave only the second one visible.

## Troubleshooting

| Problem | Solution |
|---|---|
| *Invalid email or password* during setup | Check that you can sign in to the ZeroMOUSE app with the same credentials. Accounts with MFA are not supported. |
| *Cannot reach the ZeroMOUSE cloud* | Check internet access from Home Assistant. The integration retries automatically. |
| Entities are unavailable | The cloud was not reachable. They recover with the next successful refresh. Check the log for details. |
| Home Assistant asks to reauthenticate | The password was changed or the session was revoked. Enter the current password. |
| *Custom element doesn't exist: zeromouse-…-card* | Reload the page. After an update the browser may still use a cached start page. |
| Events arrive only every minute | The realtime subscription could not connect. Polling still works; enable debug logging to see why. |
| Timeline shows many *unknown* events | See the note in [Dashboard cards](#dashboard-cards). Increase `window_after` only if your Sure Petcare integration polls slowly. |

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
  permissions of the signed-in user.

## Removal

1. Go to **Settings → Devices & services → ZeroMOUSE → ⋮ → Delete**. This removes the
   devices, entities and stored credentials.
2. Remove the ZeroMOUSE cards from your dashboards.
3. Uninstall the integration in HACS, or delete `<config>/custom_components/zeromouse`.
4. Delete `<config>/www/zeromouse/` if you created icons there.
5. Restart Home Assistant.

Your ZeroMOUSE account and device are not changed by removing the integration.

## Quality scale

Self-assessment against the
[Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Details per rule: [`quality_scale.yaml`](custom_components/zeromouse/quality_scale.yaml).

| Tier | Status |
|---|---|
| 🥉 Bronze | All rules met (actions, triggers and conditions exempt: none provided) |
| 🥈 Silver | All rules met. Test coverage 99 %. |
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
├── frontend.py          websocket command, image proxy, card registration
├── diagnostics.py
├── www/zeromouse-events-card.js   both dashboard cards
├── brand/               integration icon
└── quality_scale.yaml
tools/zeromouse_cli.py   command line client for the API
tests/                   pytest suite
API.md                   reverse-engineered API documentation
```

```bash
pip install pytest-homeassistant-custom-component pycognito mypy
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

The command line tool uses the same client without Home Assistant and is handy to
inspect the raw API:

```bash
ZEROMOUSE_EMAIL=you@example.com python tools/zeromouse_cli.py dump
```

Other commands: `devices`, `shadow`, `events`, `stats`, `user`, `image`, `watch`,
`set-entry <0-3>`, `set-undecidable <0-2>`. The password is asked interactively.

## License and trademarks

The code is released under the [MIT License](LICENSE).

ZeroMOUSE and the ZeroMOUSE logo are trademarks of their respective owner and are used
here only to identify the product this integration works with. Sure Petcare and SureFlap
are trademarks of their respective owner.

Maintainer: [@joergwall](https://github.com/joergwall). Please report bugs and ideas as
[issues](https://github.com/joergwall/zeromouse-homeassistant/issues).
