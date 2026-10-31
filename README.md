# HomeBus Control

**A phone-first, self-hosted control app for BTicino/Legrand MyHOME lights and shades.**

The original Grasshopper home-control app ran on a Raspberry Pi. HomeBus Control is a clean new implementation of that use case, focused on Docker Compose deployment on an Unraid NAS. It talks to a MyHOME F455 gateway using OpenWebNet, monitors bus feedback, and serves a responsive web interface on a private network. It carries forward the home's control needs, not the old application's code.

**Origin:** Original Grasshopper project: [https://github.com/bozzy-gh/grasshopper](https://github.com/bozzy-gh/grasshopper)

> Personal project in active development. The current Unraid deployment is operating against a real F455 installation. Light and shade controls, physical-switch state updates, and whole-home All OFF/All ON have been tested on that installation. Hardware, wiring, device setup, and gateway firmware vary; do not assume compatibility without commissioning against your own system.

## Why this project

The original interface could lose track of device state and was difficult to use from a phone. This rewrite makes reported bus state authoritative, shows unknown or stale state honestly, and keeps the user interface focused on everyday controls. The project is also a hands-on example of product management combined with AI-assisted software development.

HomeBus Control is intentionally a small, standalone application rather than a Home Assistant add-on or integration. Home Assistant is a much broader home-automation platform and already has community MyHOME integrations; this project explores a focused interface and deployment for one MyHOME installation.

## Current features

- Responsive, phone-first light and shade controls grouped by room.
- Live F455 connection status and bus event diagnostics.
- State updates from physical wall-switch events as well as browser commands.
- Whole-home **All OFF** using the gateway's group command.
- Whole-home **All ON** with shuffled, staggered individual commands; dimmers use a 50% default.
- Password-protected device setup and configuration diagnostics.
- Reconnect and status reconciliation after gateway or network interruptions.
- Docker Compose deployment with persistent local SQLite state.

See [ROADMAP.md](ROADMAP.md) for planned work, including room-level bulk actions, timed shade positions, event-log improvements, and scheduling.

## Hardware and software

| Area | Current implementation |
| --- | --- |
| Home automation | BTicino/Legrand MyHOME SCS signal bus |
| Gateway | MyHOME Gateway F455, connected over the local network |
| Protocol | OpenWebNet |
| Host | Unraid NAS (tested on Unraid 7.2.9); originally a Raspberry Pi |
| Packaging | Docker Compose; Compose Manager Plus on the tested Unraid host |
| Backend | Python 3.12, FastAPI, Uvicorn |
| Gateway client | OWNd Python package, pinned in `requirements.txt` |
| Front end | HTML, CSS, and vanilla JavaScript |
| State storage | SQLite database in a persistent Docker volume |
| Time zone | Configurable; current installation uses `Europe/Vienna` |

PostgreSQL is not required. SQLite keeps this single-home installation simple and stores its data on the persistent appdata volume. A future multi-user or multi-installation deployment can revisit the database choice.

## How it is structured

```text
Phone / desktop browser
          │ HTTP on the private LAN
          ▼
FastAPI web app ─────── SQLite (persistent state and event data)
          │
          │ OpenWebNet event monitoring, commands, and queries
          ▼
MyHOME F455 gateway ─── BTicino/Legrand SCS bus ─── lights and shades
```

The monitor consumes gateway reports independently of browser requests. Browser actions request a command; the interface waits for bus feedback before presenting the resulting state as confirmed. Gateway credentials are read from environment variables and are not stored in the device map.

## Run with Docker Compose

### 1. Prepare private configuration

Copy `.env.example` to `.env` and set values for your own network. Copy `config/devices.example.json` to `config/devices.json`, then replace the sample rooms and addresses with your own setup. Both files are intentionally ignored by Git, except the example files.

| Variable | Purpose |
| --- | --- |
| `LAN_BIND_IP` | Host LAN address to bind the web port to. Use `127.0.0.1` for local-only access during development. |
| `GATEWAY_HOST` | Local network address of the F455 gateway. |
| `GATEWAY_PORT` | OpenWebNet gateway port; commonly `20000`. |
| `GATEWAY_PASSWORD` | Gateway password configured on the F455. |
| `ADMIN_PASSWORD` | Password protecting setup and administrative endpoints. |
| `GATEWAY_COMMAND_KEEPALIVE_SECONDS` | Interval for the gateway command-channel keepalive; tune for the installation. |
| `TZ` | Container time zone. |

Never commit `.env`, real device configuration, raw home-specific bus traces, or database backups.

### 2. Start the app

From this directory, build and start the Compose service:

```sh
docker compose up -d --build
docker compose logs -f grasshopper
```

Open `http://<your-host-LAN-IP>:9999` from a device on the trusted local network. On Unraid, the Compose Manager Plus stack can manage startup and rebuilds. Set its source to the folder containing `compose.yaml`, and enable autostart after confirming the stack works.

### 3. Persistent data and backups

- `./data` is mounted at `/data` and contains the SQLite database.
- `./config` is mounted read-only at `/config`; it contains the private `devices.json`.
- Back up both folders before upgrades or moving the app to another host.
- Keep `.env` separately in a secure backup; it contains credentials.
- To update, back up the folders, copy the new application files, rebuild the image, then check container health and gateway status.

The host bind address is a convenience, not an authentication boundary. The control page is intended for a trusted private LAN and does not currently require a user login. Do not expose port 9999 to the internet or add a router port-forward. Remote access via Tailscale is a future item and needs an access-control review before enabling it.

## Configuration format

`config/devices.example.json` shows the expected structure. Each device has an OpenWebNet `who` value, a `where` address, a display name, and a kind (`light`, `dimmer`, or `shade`). Keep the real file local: names and addresses identify the layout of a private home.

## Product and delivery approach

This is being developed as a product, not just as a code sample:

- Roadmap stories describe a user problem and observable acceptance criteria.
- Product decisions and scope are documented in `PRODUCT.md`, `ROADMAP.md`, and `docs/decisions/`.
- Work is validated against a live home installation, with the user confirming behavior before stories are closed.
- AI assists with implementation and review; product priorities, acceptance decisions, and real-device validation remain human-led.

## Relationship to the original Grasshopper

HomeBus Control takes inspiration from the behavior and use case of [Grasshopper by bozzy-gh](https://github.com/bozzy-gh/grasshopper). The original project ran on a Raspberry Pi; this rewrite is designed for Docker Compose on Unraid. It does not include the legacy application's PHP/Python implementation. The original repository is GPL-3.0 licensed; this rewrite is separately licensed under GPL-3.0-only. Third-party dependencies keep their own licenses.

Home Assistant users may also want to explore the community [OpenWebNet-HA MyHOME integration](https://github.com/OpenWebNet-HA/MyHOME). HomeBus Control is an independent, standalone project and is not affiliated with Home Assistant, OpenWebNet-HA, BTicino, or Legrand.

## Security and privacy

- Bind the service to a trusted network interface and restrict access at the network level.
- Use a unique gateway password and a strong setup/admin password.
- Do not publish `.env`, `config/devices.json`, `/data`, raw event logs, or backup dumps.
- Avoid publishing unredacted screenshots or traces that reveal device names, addresses, or household routines.
- The real F455 IP, gateway password, NAS IP, device map, and shade calibration data are installation-specific and are not part of this repository.

## License

This project is licensed under **GNU General Public License v3.0 only (GPL-3.0-only)**. See [LICENSE](LICENSE) for the complete terms. Recipients may use, modify, and redistribute the project under those terms; if they distribute a modified version, the GPL requires preserving the recipients' corresponding freedoms. GPL permits charging for distribution. Third-party dependencies retain their own licenses; see their package metadata and notices.



