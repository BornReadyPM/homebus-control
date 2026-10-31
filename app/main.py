Warning: truncated output (original token count: 8210)
Total output lines: 730

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import random
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("grasshopper")

DB_PATH = Path(os.getenv("DATABASE_PATH", "/data/grasshopper.sqlite3"))
DEVICE_CONFIG = Path(os.getenv("DEVICE_CONFIG", "/config/devices.json"))
GATEWAY_HOST = os.getenv("GATEWAY_HOST", "")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "20000"))
GATEWAY_PASSWORD = os.getenv("GATEWAY_PASSWORD", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
STATIC_DIR = Path(__file__).resolve().parent.parent / "web"
GATEWAY_COMMAND_KEEPALIVE_SECONDS = max(5, min(300, int(os.getenv("GATEWAY_COMMAND_KEEPALIVE_SECONDS", "20"))))
GATEWAY_RESYNC_SECONDS = 900
DEFAULT_DIMMER_LEVEL = 50
ALL_LIGHTS_ON_DISPATCH_SECONDS = 4.0
basic = HTTPBasic(auto_error=False)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dimmer_what(level: int) -> int:
    if level <= 0:
        return 0
    return max(2, min(10, round(1 + level * 9 / 100)))


@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with db() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT NOT NULL,
                who INTEGER NOT NULL CHECK (who IN (1, 2)),
                address TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('light', 'dimmer', 'shade')),
                sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS devices_room_order ON devices(room, sort_order, id);
            CREATE TABLE IF NOT EXISTS device_state (
                who INTEGER NOT NULL,
                address TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'unknown',
                brightness INTEGER,
                raw_frame TEXT,
                updated_at TEXT,
                PRIMARY KEY (who, address)
            );
            CREATE TABLE IF NOT EXISTS bus_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                raw_frame TEXT NOT NULL,
                interpreted_as TEXT NOT NULL
            );
            """
        )
        count = connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        if count == 0 and DEVICE_CONFIG.is_file():
            config = json.loads(DEVICE_CONFIG.read_text(encoding="utf-8"))
            for room in config.get("rooms", []):
                for order, device in enumerate(room.get("devices", [])):
                    who = int(device["who"])
                    address = str(device["where"])
                    name = str(device["name"])
                    kind = str(device["kind"])
                    validate_device(who, address, name, kind)
                    connection.execute(
                        "INSERT INTO devices(room, who, address, name, kind, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                        (str(room["name"]), who, address, name, kind, order),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO device_state(who, address) VALUES (?, ?)",
                        (who, address),
                    )
        connection.commit()


def validate_device(who: int, address: str, name: str, kind: str) -> None:
    if who not in (1, 2):
        raise ValueError("Only WHO 1 lights and WHO 2 shades are supported.")
    if not re.fullmatch(r"[0-9#]+", address) or len(address) > 24:
        raise ValueError(f"Invalid OpenWebNet address: {address}")
    if not name.strip() or len(name) > 80:
        raise ValueError("Device names must contain 1 to 80 characters.")
    if kind not in {"light", "dimmer", "shade"}:
        raise ValueError(f"Unsupported device type: {kind}")
    if (who == 2) != (kind == "shade"):
        raise ValueError("Shades use WHO 2; lights and dimmers use WHO 1.")


class DeviceInput(BaseModel):
    room: str = Field(min_length=1, max_length=80)
    who: int
    where: str = Field(min_length=1, max_length=24)
    name: str = Field(min_length=1, max_length=80)
    kind: str


class DeviceListInput(BaseModel):
    devices: list[DeviceInput]


class Monitor:
    def __init__(self) -> None:
        self.connected = False
        self.last_event_at: str | None = None
        self.last_error: str | None = None
        self._transport: Any = None
        self._send_lock = asyncio.Lock()
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._pending: dict[tuple[int, str], tuple[str, int | None, float]] = {}
        self.bulk_lights_on: dict[str, Any] | None = None

    def add_frame(self, raw: str) -> None:
        try:
            self._queue.put_nowait(raw)
        except asyncio.QueueFull:
            log.warning("Dropping bus frame because the event queue is full")

    @property
    def is_connected(self) -> bool:
        transport = self._transport
        return bool(self.connected and transport is not None and transport.is_connected)

    async def send(self, frame: str) -> Any:
        transport = self._transport
        if not self.is_connected or transport is None:
            raise HTTPException(status_code=503, detail="Gateway monitor is not connected")
        async with self._send_lock:
            return await transport.send(frame)

    async def run(self) -> None:
        if not GATEWAY_HOST or not GATEWAY_PASSWORD:
            self.last_error = "Gateway settings are incomplete"
            log.warning("Gateway worker not started; set GATEWAY_HOST and GATEWAY_PASSWORD")
            return
        delay = 2
        while True:
            transport = None
            try:
                from OWNd.connection import OWNGateway
                from OWNd.transport.tcp import AsyncTcpTransport

                gateway = OWNGateway({"address": GATEWAY_HOST, "port": GATEWAY_PORT, "password": GATEWAY_PASSWORD})
                transport = AsyncTcpTransport(gateway)
                transport.register_listener(lambda message: self.add_frame(str(message)))
                self._transport = transport
                connected = await transport.connect()
                if not connected:
                    raise ConnectionError("OpenWebNet connection was not established")
                self.connected = True
                self.last_error = None
                delay = 2
                log.info("Connected to the configured OpenWebNet gateway")
                log.info("Gateway command keepalive interval: %s seconds", GATEWAY_COMMAND_KEEPALIVE_SECONDS)
                await self.resynchronize(reset_state=True)
                loop = asyncio.get_running_loop()
                last_bus_activity = loop.time()
                last_resync = last_bus_activity
                last_keepalive = last_bus_activity
                while True:
                    now = loop.time()
                    if now - last_keepalive >= GATEWAY_COMMAND_KEEPALIVE_SECONDS:
                        response = await transport.send("*#13**0##", is_status_request=True)
                        if response is None or response is False:
                            if not transport.is_connected:
                                raise ConnectionError("Gateway command session was lost")
                            log.debug("Gateway did not acknowledge the command-channel keepalive")
                        last_keepalive = loop.time()
                    now = loop.time()
                    if now - last_bus_activity >= GATEWAY_RESYNC_SECONDS and now - last_resync >= GATEWAY_RESYNC_SECONDS:
                        await self.resynchronize()
                        last_resync = loop.time()
                    remaining = min(
                        GATEWAY_COMMAND_KEEPALIVE_SECONDS - (loop.time() - last_keepalive),
                        GATEWAY_RESYNC_SECONDS - (loop.time() - last_bus_activity),
                    )
                    try:
                        raw = await asyncio.wait_for(self._queue.get(), timeout=max(remaining, 0.1))
                        await self.process_frame(raw)
                        last_bus_activity = loop.time()
                    except asyncio.TimeoutError:
                        continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = type(exc).__name__
                log.warning("Gateway session ended (%s); retrying in %s seconds", type(exc).__name__, delay)
            finally:
                self.connected = False
                self._transport = None
                if transport is not None:
                    try:
                        await transport.disconnect()
                    except Exception:
                        pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def resynchronize(self, reset_state: bool = False) -> None:
        # The F455 replies to these snapshots on the event session; they do not
        # erase stored configuration or states. Reports arrive as normal events.
        if reset_state:
            self._pending.clear()
            with db() as connection:
                connection.execute("UPDATE device_state SET state='unknown', brightness=NULL, raw_frame=NULL, updated_at=NULL")
                connection.commit()
        await self.send("*#1*0##")
        await asyncio.sleep(0.35)
        with db() as connection:
            dimmers = connection.execute("SELECT DISTINCT address FROM devices WHERE who=1 AND kind='dimmer'").fetchall()
        for row in dimmers:
            await self.send(f"*#1*{row['address']}*1##")
            await asyncio.sleep(0.1)
        await self.send("*#2*0##")

    async def refresh_all_lights(self) -> None:
        with db() as connection:
            addresses = connection.execute("SELECT DISTINCT address FROM devices WHERE who=1 ORDER BY address").fetchall()
        for row in addresses:
            await self.send(f"*#1*{row['address']}##")
            await asyncio.sleep(0.1)

    def mark_pending(self, who: int, address: str, expected_state: str, brightness: int | None = None) -> float:
        deadline = asyncio.get_running_loop().time() + 1.5
        self._pending[(who, address)] = (expected_state, brightness, deadline)
        return deadline

    def cancel_pending(self, who: int, address: str, deadline: float) -> None:
        pending = self._pending.get((who, address))
        if pending is not None and pending[2] == deadline:
            self._pending.pop((who, address), None)

    def mark_lights_pending(self) -> float:
        until = asyncio.get_running_loop().time() + 1.5
        with db() as connection:
            addresses = connection.execute("SELECT DISTINCT address FROM devices WHERE who=1").fetchall()
            for row in addresses:
                self._pending[(1, row["address"])] = ("off", 0, until)
        return until

    def cancel_lights_pending(self, deadline: float) -> None:
        for key, value in list(self._pending.items()):
            if key[0] == 1 and value[2] == deadline:
                self._pending.pop(key, None)

    def light_commands_pending(self) -> bool:
        now = asyncio.get_running_loop().time()
        return any(who == 1 and value[2] > now for (who, _), value in self._pending.items())

    def active_bulk_lights_on(self) -> bool:
        return bool(self.bulk_lights_on and self.bulk_lights_on.get("status") in {"dispatching", "confirming"})

    def public_bulk_lights_on(self) -> dict[str, Any] | None:
        if self.bulk_lights_on is None:
            return None
        return {key: value for key, value in self.bulk_lights_on.items() if not key.startswith("_")}

    async def run_all_lights_on(self, operation_id: str, devices: list[dict[str, Any]]) -> None:
        operation = self.bulk_lights_on
        if operation is None or operation["id"] != operation_id:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(30.0, len(devices) * 3.0 + 10.0)
        before: dict[str, str | None] = {}
        with db() as connection:
            for device in devices:
                row = connection.execute(
                    "SELECT updated_at FROM device_state WHERE who=1 AND address=?",
                    (device["address"],),
                ).fetchone()
                before[device["address"]] = row["updated_at"] if row else None
                expected_brightness = dimmer_what(DEFAULT_DIMMER_LEVEL) if device["kind"] == "dimmer" else None
                self._pending[(1, device["address"])] = ("on", expected_brightness, deadline)

        order = list(devices)
        random.shuffle(order)
        dispatch_started = loop.time()
        operation["status"] = "dispatching"
        operation["sent"] = 0
        operation["attempted"] = 0
        operation["failed"] = []
        operation["confirmed"] …1210 tokens truncated…process_frame(self, raw: str) -> None:
        raw = raw.strip()
        if not raw.startswith("*") or not raw.endswith("##"):
            return
        interpretation = "observed"
        who: int | None = None
        address: str | None = None
        state: str | None = None
        brightness: int | None = None

        # WHO 1 status event: *1*WHAT*WHERE##. WHAT=1000 is a physical
        # button request, not the actuator's resulting state; wait for feedback.
        light = re.fullmatch(r"\*1\*(\d+)(?:#[^*]*)?\*([^*#]+)(?:#[^*]*)?##", raw)
        if light:
            what = int(light.group(1))
            who, address = 1, light.group(2)
            if what == 1000 or what in (30, 31):
                interpretation = "lighting command/no direct state"
                if what == 1000 and address == "0":
                    deadline = self.mark_lights_pending()
                    asyncio.create_task(self.resolve_all_lights(deadline))
            elif address == "0":
                interpretation = "general lighting report; no per-device state inferred"
            elif what == 19:
                state, interpretation = "unknown", "lighting anomaly"
            elif what == 0:
                state, brightness, interpretation = "off", 0, "light off report"
            elif 1 <= what <= 10 or 11 <= what <= 18 or 20 <= what <= 29:
                state = "on"
                if 2 <= what <= 10:
                    brightness = round((what - 1) * 100 / 9)
                interpretation = "light on report"

        # WHO 1 dimension 1 reply: *#1*WHERE*1*LEVEL100*SPEED##.
        dimmer = re.fullmatch(r"\*#1\*([^*#]+)\*([14])\*([0-9]+)(?:\*([0-9]+))?##", raw)
        if dimmer:
            who, address = 1, dimmer.group(1)
            brightness = max(0, min(100, int(dimmer.group(3)) - 100))
            state = "off" if brightness == 0 else "on"
            interpretation = "light brightness report"

        # WHO 2 state events report movement/stop; F455 does not necessarily
        # report an absolute shade position, so do not infer one here.
        shade = re.fullmatch(r"\*2\*(\d+)\*([^*#]+)##", raw)
        if shade:
            what = int(shade.group(1))
            who, address = 2, shade.group(2)
            if what == 0:
                state, interpretation = "stopped", "shade stop report"
            elif what == 1:
                state, interpretation = "moving_open", "shade opening report"
            elif what == 2:
                state, interpretation = "moving_closed", "shade closing report"

        if who is not None and address is not None and state is not None:
            pending = self._pending.get((who, address))
            if pending and asyncio.get_running_loop().time() < pending[2] and state == pending[0]:
                interpretation = "possible command echo suppressed while awaiting queried status"
                state = None

        with db() as connection:
            event_cursor = connection.execute(
                "INSERT INTO bus_events(received_at, raw_frame, interpreted_as) VALUES (?, ?, ?)",
                (now_iso(), raw, interpretation),
            )
            connection.execute("DELETE FROM bus_events WHERE id NOT IN (SELECT id FROM bus_events ORDER BY id DESC LIMIT 300)")
            if who is not None and address not in (None, "0") and state is not None:
                connection.execute(
                    "INSERT INTO device_state(who, address, state, brightness, raw_frame, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(who, address) DO UPDATE SET state=excluded.state, "
                    "brightness=COALESCE(excluded.brightness, device_state.brightness), "
                    "raw_frame=excluded.raw_frame, updated_at=excluded.updated_at",
                    (who, address, state, brightness, raw, now_iso()),
                )
                interpretation += " → state updated"
                connection.execute("UPDATE bus_events SET interpreted_as=? WHERE id=?", (interpretation, event_cursor.lastrowid))
            connection.commit()
        self.last_event_at = now_iso()


monitor = Monitor()


def admin_auth(credentials: HTTPBasicCredentials | None = Depends(basic)) -> str:
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin password is not configured")
    if credentials is None or credentials.username != "admin" or not hmac.compare_digest(
        credentials.password.encode(), ADMIN_PASSWORD.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to manage setup",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    task = asyncio.create_task(monitor.run())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Grasshopper Next", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/setup")
async def setup_page(_: str = Depends(admin_auth)) -> FileResponse:
    return FileResponse(STATIC_DIR / "setup.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    with db() as connection:
        devices = connection.execute(
            'SELECT d.id, d.room, d.who, d.address AS "where", d.name, d.kind, '
            "COALESCE(s.state, 'unknown') AS state, s.brightness, s.updated_at "
            "FROM devices d LEFT JOIN device_state s ON s.who=d.who AND s.address=d.address "
            "ORDER BY d.room, d.sort_order, d.id"
        ).fetchall()
        events = connection.execute(
            "SELECT received_at, raw_frame, interpreted_as FROM bus_events ORDER BY id DESC LIMIT 20"
        ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in devices:
        item = dict(row)
        if item["updated_at"]:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(item["updated_at"])).total_seconds()
            item["stale"] = age > 1800
        else:
            item["stale"] = True
        pending = monitor._pending.get((item["who"], item["where"]))
        item["pending"] = bool(pending and asyncio.get_running_loop().time() < pending[2])
        grouped.setdefault(item.pop("room"), []).append(item)
    return {
        "connected": monitor.is_connected,
        "last_event_at": monitor.last_event_at,
        "gateway_error": monitor.last_error,
        "rooms": [{"name": room, "devices": items} for room, items in grouped.items()],
        "events": [dict(event) for event in events],
        "bulk_lights_on": monitor.public_bulk_lights_on(),
    }


@app.post("/api/devices/{device_id}/command")
async def device_command(device_id: int, body: dict[str, str]) -> JSONResponse:
    action = body.get("action", "")
    with db() as connection:
        device = connection.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    who, address, kind = device["who"], device["address"], device["kind"]
    if who == 1 and monitor.active_bulk_lights_on():
        raise HTTPException(status_code=409, detail="A whole-home lights-on action is in progress")
    if kind == "shade":
        frames = {"open": f"*2*1*{address}##", "stop": f"*2*0*{address}##", "close": f"*2*2*{address}##"}
    else:
        frames = {"on": f"*1*1*{address}##", "off": f"*1*0*{address}##"}
        if action.startswith("brightness:") and kind == "dimmer":
            try:
                level = max(0, min(100, int(action.split(":", 1)[1])))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid dimmer level") from exc
            what = 0 if level == 0 else max(2, min(10, round(1 + level * 9 / 100)))
            frames[action] = f"*1*{what}*{address}##"
    frame = frames.get(action)
    if frame is None:
        raise HTTPException(status_code=422, detail="Action does not match this device")
    if kind == "shade":
        expected_state = {"open": "moving_open", "close": "moving_closed", "stop": "stopped"}[action]
    elif action == "off" or action == "brightness:0":
        expected_state = "off"
    else:
        expected_state = "on"
    deadline = monitor.mark_pending(who, address, expected_state)
    try:
        acknowledgement = await monitor.send(frame)
    except Exception:
        monitor.cancel_pending(who, address, deadline)
        raise
    if acknowledgement is None or acknowledgement is False:
        monitor.cancel_pending(who, address, deadline)
        log.warning("Gateway did not acknowledge command frame %s", frame)
        raise HTTPException(status_code=502, detail="The gateway did not acknowledge the command. Please try again.")
    log.info("Gateway acknowledged command frame %s", frame)
    # Re-query the addressed point so the UI is reconciled to actuator feedback,
    # rather than treating the sent command as confirmation.
    asyncio.create_task(monitor.resolve_command(who, address, kind, deadline))
    return JSONResponse({"accepted": True, "state": "pending_feedback"}, status_code=202)


@app.post("/api/lights/off")
async def all_lights_off() -> JSONResponse:
    if monitor.active_bulk_lights_on():
        raise HTTPException(status_code=409, detail="A whole-home lights-on action is in progress")
    if monitor.light_commands_pending():
        raise HTTPException(status_code=409, detail="A light command is already in progress")
    deadline = monitor.mark_lights_pending()
    try:
        acknowledgement = await monitor.send("*1*0*0##")
    except Exception:
        monitor.cancel_lights_pending(deadline)
        raise
    if acknowledgement is None or acknowledgement is False:
        monitor.cancel_lights_pending(deadline)
        log.warning("Gateway did not acknowledge all-lights-off command")
        raise HTTPException(status_code=502, detail="The gateway did not acknowledge the all-lights-off command. Please try again.")
    log.info("Gateway acknowledged all-lights-off command")
    asyncio.create_task(monitor.resolve_all_lights(deadline))
    return JSONResponse({"accepted": True, "state": "pending_feedback"}, status_code=202)


@app.post("/api/lights/on")
async def all_lights_on() -> JSONResponse:
    if not monitor.is_connected:
        raise HTTPException(status_code=503, detail="Gateway monitor is not connected")
    if monitor.active_bulk_lights_on() or monitor.light_commands_pending():
        raise HTTPException(status_code=409, detail="A light command is already in progress")
    with db() as connection:
        rows = connection.execute(
            "SELECT address, MIN(kind) AS kind, MIN(name) AS name FROM devices "
            "WHERE who=1 GROUP BY address ORDER BY address"
        ).fetchall()
    devices = [dict(row) for row in rows]
    if not devices:
        raise HTTPException(status_code=409, detail="No lights or dimmers are configured")

    operation_id = uuid.uuid4().hex
    monitor.bulk_lights_on = {
        "id": operation_id,
        "status": "dispatching",
        "total": len(devices),
        "sent": 0,
        "attempted": 0,
        "confirmed": [],
        "failed": [],
        "unconfirmed": [],
        "started_at": now_iso(),
    }
    asyncio.create_task(monitor.run_all_lights_on(operation_id, devices))
    return JSONResponse({"accepted": True, "state": "pending_feedback", "operation_id": operation_id}, status_code=202)


@app.get("/api/admin/devices")
async def admin_get_devices(_: str = Depends(admin_auth)) -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            'SELECT id, room, who, address AS "where", name, kind FROM devices ORDER BY room, sort_order, id'
        ).fetchall()
    return {"devices": [dict(row) for row in rows]}


@app.put("/api/admin/devices")
async def admin_save_devices(body: DeviceListInput, _: str = Depends(admin_auth)) -> dict[str, bool]:
    if len(body.devices) > 250:
        raise HTTPException(status_code=422, detail="The setup can contain at most 250 entries")
    try:
        for device in body.devices:
            if not device.room.strip():
                raise ValueError("Room names must contain at least one non-space character.")
            validate_device(device.who, device.where, device.name, device.kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with db() as connection:
        connection.execute("DELETE FROM devices")
        for order, device in enumerate(body.devices):
            connection.execute(
                "INSERT INTO devices(room, who, address, name, kind, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (device.room.strip(), device.who, device.where, device.name.strip(), device.kind, order),
            )
            connection.execute(
                "INSERT OR IGNORE INTO device_state(who, address) VALUES (?, ?)",
                (device.who, device.where),
            )
        connection.commit()
    return {"saved": True}


@app.post("/api/admin/resynchronize")
async def admin_resynchronize(_: str = Depends(admin_auth)) -> dict[str, bool]:
    await monitor.resynchronize()
    return {"requested": True}


@app.get("/api/admin/events")
async def admin_events(_: str = Depends(admin_auth)) -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            "SELECT received_at, raw_frame, interpreted_as FROM bus_events ORDER BY id DESC LIMIT 300"
        ).fetchall()
    return {"connected": monitor.is_connected, "events": [dict(row) for row in rows]}

