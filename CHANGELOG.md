# Changelog

All notable changes to this project. The version matches `version` in
`custom_components/zeromouse/manifest.json` and the tag of the GitHub release
(`vX.Y.Z`). 0.4.0 is the first public release; 0.1.0 to 0.3.0 were private test
versions without releases.

## 0.4.0 – 2026-10-26

First public release.

### Added
- Gallery card like the app: filters (no prey, prey, inconclusive, hand, leaving,
  favourites only, reset) with the app's defaults, *Wrong / Right / Delete* buttons
  (tapping an active rating again removes it), unlimited "load older", pictures load
  only for events on screen. After a longer pause (e.g. a sleeping tablet) the list
  reloads instead of skipping events.
- Actions `zeromouse.rate_event` (`correct`, `incorrect`, `none`) and
  `zeromouse.delete_event`; they need the permission to control ZeroMOUSE entities.
- Matching events with a cat flap integration or sensor and with ZeroMOUSE's own face
  detection, in the backend. Presets for Sure Petcare (only the core integration was
  tested), surepcha, PetSafe SmartDoor, OnlyCat, state changes and event entities; all
  presets except the tested one are untested.
- Timeline card works without cat flap and without own icons.
- Cards follow the Home Assistant language (or `language: de|en`).
- Websocket command `zeromouse/events`: paging with `cursor`, `has_more`, `release`,
  filters, matching; each event carries its app `group` (null for values the app lists
  in no filter, e.g. `free`).
- GitHub Actions: HACS validation, hassfest, tests, mypy, ruff.

### Changed
- Requires Home Assistant 2026.8 or newer.
- `zeromouse_event`: `device_id` is now the Home Assistant device id;
  the cloud id moved to `zeromouse_device_id`.
- Events are grouped like in app 1.14.19: `early` counts as *no prey detected*, `late`
  and `unknown` as *inconclusive*, `test` is *hand detected*. Titles, colours, filters,
  the timeline and the matching use these groups. The timeline now also shows `early`
  (as *no prey*), `late` and `unknown` events (as *inconclusive*); `free` events stay
  out.
- Gallery `show_hidden` only pre-checks *Leaving detected*: like in the app the check
  boxes decide what is shown, hidden or not.
- Translations of `early`, `late` and `test` follow the app.
- The integration icon is an own, neutral design instead of the ZeroMOUSE logo.
- The card's cache version is derived from its content.

### Security and privacy
- Diagnostics leave out device IDs, device and cat names and all shadow values the
  integration does not use.
- The integration's logs and error messages leave out access tokens, the S3 key and
  AWS messages that contain the identity ID.
- The image endpoint rejects malformed event IDs.
- Command line tool: no full owner ID, no token-bearing library debug output.

## 0.3.0 – 2026-09-24 (not published)
- Login fully asynchronous, quality scale up to Platinum, reconfiguration, dynamic and
  stale devices, translated errors, icon translations, brand icon.
- Timeline card.

## 0.2.0 – 2026-09-23 (not published)
- Event gallery card, diagnostics, connectivity sensor.

## 0.1.0 – 2026-09-23 (not published)
- First version.
