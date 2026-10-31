# Product brief

## Problem

The existing Grasshopper page is difficult to trust because it can show stale light state and has no reliable recovery when its long-lived bus monitor disconnects. The replacement should keep the quick, direct controls while making reported state and connection health clear.

## First release

- Responsive light and shade controls grouped by room.
- Bus-reported state, with unknown/unavailable states represented explicitly.
- F455 connection indicator, recent event diagnostics, and automatic reconnect/resync.
- A password-protected setup page for rooms and devices, plus gateway connection diagnostics. Gateway credentials stay in Unraid's container settings.
- LAN deployment on Unraid at port `9999`.

## Later ideas

- Date/time scheduler using the `Europe/Vienna` timezone.
- Tailscale access from a phone.
- Optional installable/PWA experience; decide on a native app only after the mobile web version has been used.
- Possible Home Assistant integration, while keeping this app usable on its own.
- Whole-home All OFF and staggered All ON actions, including dimmers at the agreed medium level.

## Acceptance criteria for state accuracy

- A physical wall-switch action updates the page from the actuator's resulting status event.
- A browser command does not optimistically change the displayed status.
- Initial and reconnect status checks refresh known device states without deleting configuration or prior audit data.
- Missing, unknown, unsupported, and stale states do not silently become OFF.
- Each event can be traced to a raw OpenWebNet frame and timestamp without logging gateway credentials.

## Current field status

The app is deployed on an Unraid NAS and connected to a MyHOME F455 gateway. The user has tested lights, shades, physical-switch feedback, whole-home All OFF, and whole-home All ON. Dimmer behavior with a compatible connected load, room-level bulk controls, shade percentage positioning, and the scheduler remain future validation or implementation items.

