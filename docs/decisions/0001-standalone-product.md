# Decision 0001: Build a standalone replacement

**Status:** Accepted

## Context

The existing Grasshopper installation is an old PHP/Python app with unreliable state reporting. The user wants a simple phone-accessible control page on Unraid and would like to keep the product independent of Home Assistant.

## Decision

Build a new standalone web app and monitor. Use the old code and backup files only to understand the installation and import its room/device map. Use OWNd as the OpenWebNet protocol client rather than reimplementing gateway authentication and socket handling. Keep a clean app API so a mobile client or Home Assistant integration can be considered later.

## Consequences

- The new app can use a current Python runtime and a small mobile-first UI.
- The status model can treat gateway reports as authoritative and represent unknown/stale states explicitly.
- The old app's GPL-3.0 implementation is not copied into the new codebase; OWNd is a separate Apache-2.0 dependency.
- F455 behavior must be commissioned against real sanitized traces before the new UI is trusted for daily control.

