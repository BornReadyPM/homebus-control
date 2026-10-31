# Roadmap

## At-a-glance overview

### Change requests and control-page improvements

- **Complete P1 UX-01 — Mobile control page:** Simplify phone controls, show device state through icon colors, improve device names and room summaries, and remove introductory copy.
- **P1 LOG-01 — Readable bus event log:** Show named devices and plain-language states, suppress keepalive and duplicate echo events, and retain raw diagnostics separately.
- **P2 SHADE-01/02 — Timed shade positions:** Estimate physical position from measured travel times and add individual 50% and 80% target controls.
- **P4 SETUP-01 — Setup and ordering:** Derive device protocol type from Light/Dimmer/Shade and add manual room and device ordering.
- **Low priority DIMMER-01 — Verify dimmer controls:** The icon appearance is accepted. Verify ON/OFF and brightness behavior later with a compatible dimmable load connected; the current result is inconclusive because no device is connected.

### New features

- **P3 BULK-01 — Whole-home and room light controls (in progress):** Whole-home All OFF and All ON are deployed and confirmed; room-level actions remain.
- **P3 BULK-02 — Whole-home shade controls:** Open, close, or move all shades to 50% or 80% with staggered starts and per-shade progress.
- **Future — Scheduler:** Schedule light and shade actions using the Europe/Vienna timezone.
- **Future — Installable web app:** Evaluate a PWA-style install experience for phone access.
- **Future — Native mobile app:** Revisit after the responsive web page has been used in daily life.
- **Future — Home Assistant integration:** Consider an optional integration while keeping Grasshopper standalone.
- **Low priority FAVICON-01 — Add a favicon:** Add a browser-tab icon that matches the final product identity.

### Platform and operations

- **Complete P0 OPS-01 — Compose Manager Plus and NAS autostart:** Existing stack adopted; autostart enabled and confirmed after an Unraid restart.
- **Remaining — Operations readiness:** Confirm the imported setup and device types; capture remaining protocol traces; document repeatable backup and upgrade steps.

## Prioritized user stories

Stories are ordered by implementation priority. Acceptance criteria (ACs) describe the behavior that must be observable before a story is considered done. OPS-01 and UX-01 are complete; remaining stories have not started.

### P0 — [x] OPS-01: Adopt the existing Compose stack and enable NAS autostart

Register the running `/mnt/cache/appdata/grasshopper-next` project with Compose Manager Plus on Unraid 7.2.9 (plugin 2026.10.27). Keep and adopt the existing stack rather than creating a duplicate.

**ACs**

- The stack is manageable in Compose Manager Plus and its existing container remains visible on the Docker page.
- There is exactly one Grasshopper Next container and it continues using the existing `.env`, database, and device configuration.
- Compose Manager Plus autostart and the container restart policy are configured so the service returns after an Unraid restart.
- After a NAS restart, the site is reachable at the current LAN address and the gateway reconnects without manual intervention.

**Validation:** Registered the existing stack in Compose Manager Plus, confirmed 1/1 container running and healthy, enabled stack autostart, then confirmed Grasshopper came up after an Unraid restart.

### P1 — [x] UX-01: Refresh the mobile control page

**ACs**

- Remove “Good to see you” and the explanatory “tap a control…” copy.
- Replace the separate light On/Off buttons with a compact, stateful toggle. Keep dimmer brightness controls.
- Keep state available to the user, but communicate it through the device icon color instead of a separate state label. Unknown and stale states have distinct neutral styling and are not shown as Off.
- Make device names larger and remove the light/dimmer/shade type subtitle.
- Room headers show the number of on lights/dimmers and total device count when the room contains at least one light or dimmer; shade-only rooms show only their device count.
- Controls remain usable on a phone and show pending/failure feedback while bus reports remain the source of truth.

**Validation:** User reviewed the live desktop and phone pages and confirmed the refreshed layout and controls look good. Dimmer ON/OFF and brightness behavior still needs a physical-load check and is tracked separately in DIMMER-01.

### P1 — LOG-01: Make recent bus reports readable

**ACs**

- The main event list uses the active device setup to show `timestamp | device name | state`.
- Lights show `ON` or `OFF`; shades show `UP`, `DOWN`, or `STOP`.
- WHO 13 command-channel keepalive replies are omitted from the main event list.
- A possible command echo followed by its matching confirmed state produces one readable entry, not two.
- Unrecognized and diagnostic frames (including WHO 1001) remain available in a separate raw/technical view, with timestamp and frame, so they can still be investigated.
- Device names are looked up from the current setup; events for unknown addresses remain identifiable in the technical view.

### P2 — SHADE-01: Track estimated shade position from motion timings

Implement position estimation from the user's measured, direction-specific calibration data. The actual timings and device addresses are private installation configuration and are intentionally kept out of the public roadmap.

Calibration must support separate travel curves for door and window shades, each direction, and the configured target positions. Store per-home calibration values in local configuration rather than source-controlled product documentation.

**ACs**

- Use the installation's measured values as direction-specific calibration points; do not assume the same travel time in both directions or infer a single linear full-travel rate.
- Movement-start, stop, and physical-switch events update the estimated position using elapsed movement time.
- Estimated position and its confidence/reference state persist across application/container restarts.
- If position is unknown, percentage targets stay unavailable until a user-issued full Open or Close establishes an endpoint reference; do not automatically move shades on startup.
- Full-travel overrun is acceptable to the user because the shade’s physical limit stops it. The app still stops timed partial moves at their estimated target.
- If a new move, manual action, stop, or connection loss makes the estimate unreliable, show it as unknown rather than inventing a position.

### P2 — SHADE-02: Add individual 50% and 80% shade targets

**ACs**

- Each shade has 50% and 80% target controls alongside the existing Open, Stop, and Close controls.
- From a known estimated position, the app selects direction and duration from that shade group’s calibration data, then sends Stop at the estimated target.
- The page labels the result as estimated; it does not imply the F455 reports an absolute position.
- Partial targets are unavailable while that shade’s position is unknown.
- Manual wall-switch movement updates the estimate and remains reflected on the page.

### P3 — BULK-01: Add whole-home light controls

Add controls at the top of the phone page. Bulk Off includes every light and dimmer. Bulk On turns on regular lights and sets dimmers to a defined medium default level.

**Status:** In progress — Whole-home All OFF and All ON are deployed and user-tested. Room-level controls remain to be implemented.

**ACs**

- [x] All OFF sends the group-off command observed from the physical all-off control (`*1*0*0##`), includes all WHO 1 lights and dimmers, and refreshes each configured point from subsequent bus feedback.
- [x] The top-of-page All OFF control asks for confirmation, shows pending feedback, and does not optimistically mark devices off.
- [x] A gateway rejection is shown to the user; previously confirmed states are preserved if the command is not acknowledged.
- [x] All ON sends individual commands in a shuffled order, with commands scheduled across approximately four seconds; dimmers are set to the product-defined medium default brightness. User tested and confirmed working.
- [ ] Per-room On/Off controls appear in each room header only when that room contains at least one light or dimmer. Each action applies to all lights and dimmers in that room.
- [ ] Room and whole-home bulk controls report per-device confirmation from bus feedback; they do not optimistically mark devices on or off.
- [ ] A user can tell which lights or dimmers did not confirm a group action.

### Unprioritized backlog — FAVICON-01: Add a favicon

**Status:** Low priority; align the icon with the final product identity when the name and visual mark are selected.

- [ ] The browser tab shows the product favicon on the home and setup pages.
- [ ] The favicon is included in the Docker image and served locally by the app.

### P3 — BULK-02: Add whole-home shade controls

Add Open All, Close All, 50%, and 80% actions at the top of the phone page.

**ACs**

- Starts for all shades are staggered in a shuffled order across no more than ten seconds.
- Full Open and Close use the existing controls and endpoint timings; 50% and 80% use the estimate and calibration behavior in SHADE-01/02.
- The page reports per-shade progress and estimated result; a failed or unknown shade does not make the whole group appear complete.
- Manual movement or Stop cancels that shade’s pending timed target without cancelling other shades.

### P4 — SETUP-01: Simplify device type and add manual ordering

**ACs**

- Setup asks for Light, Dimmer, or Shade and derives WHO 1/2 automatically.
- Existing device configuration is migrated/preserved; invalid type/address combinations are reported clearly.
- Rooms can be manually reordered, and devices can be manually reordered within a room using phone-friendly drag-and-drop controls.
- Saved ordering remains after reload and does not change device addresses or state history.

### Unprioritized backlog — DIMMER-01: Verify dimmer controls

**Status:** Low priority; pending a compatible dimmable load being connected.

- The dimmer icon appearance is accepted.
- With a compatible dimmable load connected, verify that the toggle switches the light on/off and the brightness slider changes its level.
- Confirm the displayed state follows bus feedback after those commands.

### Agreed product decisions

- Bulk light Off includes lights and dimmers. Bulk light On includes dimmers, set to a medium default brightness of 50%.
- Room-level light On/Off controls include lights and dimmers, and appear only in rooms that contain at least one of them.
- Shade estimates are local, time-based estimates; the gateway does not provide absolute percentages.
- Do not automatically home shades on startup. Unknown position must be established through a user action.
- Preserve raw diagnostic events separately from the simplified state-change list.
- Unraid target is version 7.2.9 with Compose Manager Plus 2026.10.27.
- Manual touch-friendly ordering is preferred for rooms and devices.
- Keepalive interval is currently 25 seconds in the NAS `.env`; the interval can be tuned after confirming the behavior remains reliable.

### Shade target position definition

- The 50% and 80% labels refer to the physical position of the shade, regardless of approach direction. Use direction-specific installation calibration points to calculate travel from a known estimated position.
- The user confirms the supplied measurements are correct and that passing the nominal endpoint is safe because the shade physically stops. Timed partial moves should still stop at the estimated target.

## 0. Foundation and protocol proof

- [x] Define a standalone product and a phone-first control experience.
- [x] Import the existing room/device map as private local configuration.
- [x] Add LAN-only Docker deployment scaffolding for Unraid.
- [x] Add typed status, reconnect/resync, and bus diagnostics foundations.
- [x] Verify F455 authentication and event-session behavior on the actual gateway.
- [ ] Capture representative light, dimmer, and shade traces; refine any nonstandard parsing.
- [x] Confirm command echoes are not mistaken for actuator confirmation.

## 1. Reliable daily control

- [x] Validate initial status sweep and after-command state reconciliation.
- [x] Validate physical switch changes update the phone page promptly.
- [ ] Review the imported setup and confirm every address/device type.
- [ ] Add a clear whole-home all-lights-off action with confirmation.
- [x] Register the existing Compose stack in Compose Manager Plus and enable autostart; verified Grasshopper starts after an Unraid restart.
- [ ] Prepare repeatable Unraid backup and upgrade instructions.

## 2. Convenience

- [ ] Add scheduled light and shade actions with Europe/Vienna timezone handling.
- [ ] Add an installable web app experience if it improves phone use.
- [ ] Evaluate a native mobile app only after real-world use of the responsive page.
- [ ] Consider an optional Home Assistant integration without making it a dependency.

## Product validation notes

Keep an issue for each behavior change with the user problem, acceptance criteria, and a short validation note. Use sanitized traces and screenshots; never publish the real device map, gateway credentials, home IPs, or identifying bus traces.

