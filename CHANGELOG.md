# Changelog

All notable changes to this project. The version matches `version` in
`custom_components/zeromouse/manifest.json` and the Git tag (`vX.Y.Z`).

## 0.4.0 – unreleased

### Added
- Gallery card: filters like in the app (no prey, prey, inconclusive, hand, leaving,
  favourites only, reset) with the app's defaults, *Wrong / Right / Delete* buttons
  (tapping an active rating again removes it), unlimited "load more", pictures load
  only for events on screen.
- Actions `zeromouse.rate_event` (`correct`, `incorrect`, `none`) and
  `zeromouse.delete_event`.
- Matching events with any cat flap integration or sensor (presets for Sure Petcare,
  surepcha, PetSafe SmartDoor, OnlyCat, state changes and event entities) and with
  ZeroMOUSE's own face detection. Matching now runs in the backend.
- Timeline card works without cat flap and without own icons.
- Cards follow the Home Assistant language.
- GitHub Actions: HACS validation, hassfest, tests, mypy, ruff.

### Changed
- Requires Home Assistant 2026.8 or newer.
- `zeromouse_event`: `device_id` is now the Home Assistant device id;
  the cloud id moved to `zeromouse_device_id`.
- The card's cache version is derived from its content.
- Events are grouped like in app 1.14.19: `early` counts as *no prey detected*, `late`
  and `unknown` as *inconclusive*, `test` is *hand detected*. Titles, colours, filters,
  the timeline and the cat flap matching use these groups; the websocket API returns
  each event's `group`.
- Translations of `early`, `late` and `test` follow the app.
- The integration icon is now an own, neutral design instead of the ZeroMOUSE logo.

## 0.3.0 – 2026-09-24
- Login fully asynchronous, quality scale up to Platinum, reconfiguration, dynamic and
  stale devices, translated errors, icon translations, brand icon.
- Timeline card.

## 0.2.0 – 2026-09-23
- Event gallery card, diagnostics, connectivity sensor.

## 0.1.0 – 2026-09-23
- First version.
