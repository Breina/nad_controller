"""Async client for NAD CI multi-channel amplifiers.

State is read from the web UI's JSON API (Web/Handler.php), which returns the whole amplifier in a few requests.
Commands go over the documented IP control protocol (TCP port 52000), which NAD keeps stable for its integrator
drivers. Firmware V2.2x numbers channels from 1 in both TCP commands and queries.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_TCP_PORT = 52000
CHANNEL_COUNT = 16
GLOBAL_COUNT = 2
MIN_GAIN = -6.0
MAX_GAIN = 6.0
GAIN_STEP = 0.5

TCP_TIMEOUT = 3
TCP_ATTEMPTS = 3
TCP_RETRY_DELAY = 2
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)
BUFFER_SIZE = 1024
ERROR_RESPONSE = "Error Command"


class NadError(Exception):
    """Base error for the NAD client."""


class NadConnectionError(NadError):
    """The amplifier could not be reached."""


class NadCommandError(NadError):
    """The amplifier rejected a command."""


class StereoMono(Enum):
    STEREO = "00"
    MONO = "01"


class PowerMethod(Enum):
    POWER_BUTTON = "0"
    ALWAYS_ON = "1"
    V12_TRIGGER = "2"
    SIGNAL_SENSE = "3"


STANDBY_TIMES = ["OFF", "5Min", "10Min", "15Min", "20Min", "30Min", "60Min"]
FAN_SPEED_METHODS = ["Auto", "High", "Medium", "Low"]


@dataclass
class Zone:
    index: int
    name: str
    channels: list[int]
    """1-based output channels that belong to this zone."""


@dataclass
class Temperature:
    value: float
    unit: str
    """Either "C" or "F", as configured in the web UI."""


@dataclass
class NadState:
    """Snapshot of everything the integration knows about the amplifier."""

    power: bool
    input_names: list[str]
    output_names: list[str]
    output_gains: list[float]
    output_mutes: list[bool]
    sources: list[int]
    """0-based input index per output channel."""
    presets: list[int]
    """Preset value per output channel, 0 being 'None'."""
    preset_names: dict[int, str]
    input_gains: list[float] = field(default_factory=list)
    signals: list[bool] = field(default_factory=list)
    protection: list[str] = field(default_factory=list)
    stereo_mono: list[str] = field(default_factory=list)
    """'stereo' or 'mono' per input pair."""
    bridge_modes: list[str] = field(default_factory=list)
    global_enabled: list[bool] = field(default_factory=list)
    global_gains: list[float] = field(default_factory=list)
    global_names: list[str] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    amp_status: str | None = None
    temperatures: list[Temperature] = field(default_factory=list)
    inner_temperature: Temperature | None = None
    fan_speeds: list[str] = field(default_factory=list)
    power_on_method: str | None = None
    standby_time: str | None = None
    power_on_delay: int | None = None
    fan_speed_method: str | None = None
    green_mode: bool | None = None
    password_protection: bool = False
    firmware_version: str | None = None
    from_http: bool = True
    """False when this snapshot was patched together from TCP queries because the web API was unreachable."""


@dataclass
class NadIdentity:
    name: str | None
    model: str | None
    serial_number: str | None
    firmware_version: str | None


def _named(items: list[dict[str, Any]]) -> list[str]:
    """Names from the web API's lists; V2.05 used name/value keys, V2.2x uses N/V."""
    return [item.get("N", item.get("name", "")) for item in items]


def _named_values(items: list[dict[str, Any]]) -> dict[int, str]:
    return {int(item.get("V", item.get("value"))): item.get("N", item.get("name", "")) for item in items}


def _on(value: Any) -> bool:
    return str(value).lower() == "on"


def _temperature(value: str | None) -> Temperature | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*([CF])\s*", value)
    return Temperature(float(match.group(1)), match.group(2)) if match else None


def _zone_channels(zone_index: int, channel_masks: list[dict[str, Any]]) -> list[int]:
    """Channels whose membership bitmask includes the zone; a channel can belong to several zones."""
    return [
        int(item.get("I", position)) + 1
        for position, item in enumerate(channel_masks)
        if int(item.get("V", 0)) & (1 << zone_index)
    ]


class NadClient:

    def __init__(self, host: str, session: aiohttp.ClientSession, port: int = DEFAULT_TCP_PORT):
        self._host = host
        self._port = port
        self._session = session
        self._tcp_lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    @staticmethod
    def channel_to_hex(channel: int) -> str:
        if not 1 <= channel <= CHANNEL_COUNT:
            raise ValueError(f"Channel should be between 1 and {CHANNEL_COUNT} (inclusive)")
        return f"{channel:02X}"

    @staticmethod
    def gain_to_hex(gain: float) -> str:
        if not MIN_GAIN <= gain <= MAX_GAIN:
            raise ValueError(f"Gain should be between {MIN_GAIN} and {MAX_GAIN} (inclusive)")
        return f"{round((gain - MIN_GAIN) / GAIN_STEP):02X}"

    # TCP

    async def send(self, hex_string: str) -> str:
        """Send one command and return the reply text.

        The amplifier stops answering for a few seconds around power changes, so a failed connection is retried.
        That is safe because every command sets an absolute value.
        """
        for attempt in range(TCP_ATTEMPTS):
            try:
                return await self._send_once(hex_string)
            except NadConnectionError:
                if attempt == TCP_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(TCP_RETRY_DELAY)
        raise AssertionError("unreachable")

    async def _send_once(self, hex_string: str) -> str:
        # The protocol has no framing, so commands are serialised and each gets its own short-lived connection;
        # a dropped connection then never leaves the client in a bad state.
        async with self._tcp_lock:
            writer = None
            try:
                async with asyncio.timeout(TCP_TIMEOUT):
                    reader, writer = await asyncio.open_connection(self._host, self._port)
                    writer.write(bytes.fromhex(hex_string))
                    await writer.drain()
                    response = await reader.read(BUFFER_SIZE)
            except (OSError, TimeoutError) as ex:
                raise NadConnectionError(f"Could not reach NAD amplifier at {self._host}: {ex!r}") from ex
            finally:
                if writer is not None:
                    writer.close()

        text = response.decode(errors="replace").split("\x00")[0].strip().strip('"')
        _LOGGER.debug("TCP %s -> %r", hex_string, text)
        if text == ERROR_RESPONSE:
            raise NadCommandError(f"Amplifier rejected command {hex_string}")
        return text

    async def _query_value(self, hex_string: str) -> str:
        return (await self.send(hex_string)).split(":", 1)[1].strip()

    async def get_device_name(self) -> str:
        return await self.send("FF5501E0")

    async def get_device_model(self) -> str:
        return await self.send("FF5501E1")

    async def get_firmware_version(self) -> str:
        return await self.send("FF5501E5")

    async def get_serial_number(self) -> str:
        return await self.send("FF5501E6")

    async def get_identity(self) -> NadIdentity:
        return NadIdentity(
            name=await self.get_device_name(),
            model=await self.get_device_model(),
            serial_number=await self.get_serial_number(),
            firmware_version=await self.get_firmware_version(),
        )

    async def led_flash(self, on: bool) -> None:
        await self.send("FF5502EB" + ("01" if on else "00"))

    async def power_on(self) -> None:
        await self.send("FF550101")

    async def power_off(self) -> None:
        await self.send("FF550102")

    async def get_power(self) -> bool:
        # Power status:On
        return (await self._query_value("FF550170")).lower() == "on"

    async def set_global_enabled(self, global_index: int, on: bool) -> None:
        # Set Global A ON; global_index is 0 for A and 1 for B
        if not 0 <= global_index < GLOBAL_COUNT:
            raise ValueError("Global index should be 0 (A) or 1 (B)")
        await self.send(f"FF5503F0{global_index:02X}" + ("01" if on else "00"))

    async def set_input_gain(self, input_channel: int, gain: float) -> None:
        await self.send("FF5503F1" + self.channel_to_hex(input_channel) + self.gain_to_hex(gain))

    async def set_output_gain(self, output_channel: int, gain: float) -> None:
        # Cmd:ChannelOutputGain ,Channel 1
        await self.send("FF5503F2" + self.channel_to_hex(output_channel) + self.gain_to_hex(gain))

    async def get_output_gain(self, output_channel: int) -> float:
        # Channel[1] Output Gain:-1.5
        return float(await self._query_value("FF550210" + self.channel_to_hex(output_channel)))

    async def set_output_preset(self, output_channel: int, preset: int) -> None:
        # Cmd:ChannelOutputPreset ,Channel 1; preset 0 is 'None'
        if not 0 <= preset <= 9:
            raise ValueError("Preset should be between 0 and 9 (inclusive)")
        await self.send("FF5503F3" + self.channel_to_hex(output_channel) + f"{preset:02X}")

    async def set_output_source(self, output_channel: int, input_index: int) -> None:
        # Cmd:ChannelOutputSource ,Channel 1; input_index is 0-based like the web API
        await self.send("FF5503F4" + self.channel_to_hex(output_channel) + self.channel_to_hex(input_index + 1))

    async def set_output_mute(self, output_channel: int, muted: bool) -> None:
        # Cmd:ChannelMute ,Channel 1; the amplifier mutes the whole stereo pair
        await self.send("FF5503F7" + self.channel_to_hex(output_channel) + ("00" if muted else "01"))

    async def get_output_mute(self, output_channel: int) -> bool:
        # Channel[1] MuteStatus:0, where 0 is muted
        return await self._query_value("FF550212" + self.channel_to_hex(output_channel)) == "0"

    async def set_power_method(self, power_method: PowerMethod) -> None:
        await self.send("FF5502F8" + f"{int(power_method.value):02X}")

    async def set_green_mode(self, green: bool) -> None:
        await self.send("FF5502F9" + ("01" if green else "00"))

    # HTTP

    async def _handler(self, **params: str) -> dict[str, Any]:
        url = f"http://{self._host}/Web/Handler.php"
        try:
            async with self._session.get(url, params=params, timeout=HTTP_TIMEOUT) as response:
                response.raise_for_status()
                # The amplifier serves JSON as text/html
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as ex:
            raise NadConnectionError(f"Web API of {self._host} failed for {params}: {ex!r}") from ex

    async def _write(self, page: str, name: str, value: Any, index: int | None = None) -> None:
        params = {"page": page, "action": "write", "name": name, "value": str(value)}
        if index is not None:
            params["index"] = str(index)
        await self._handler(**params)

    async def set_global_gain(self, global_index: int, gain: float) -> None:
        if not MIN_GAIN <= gain <= MAX_GAIN:
            raise ValueError(f"Gain should be between {MIN_GAIN} and {MAX_GAIN} (inclusive)")
        await self._write("in-out", f"global-{'ab'[global_index]}-gain", f"{gain:g}")

    async def set_stereo_mono(self, input_pair: int, mono: bool) -> None:
        """Sum an input pair (1-based) to mono, or keep it stereo."""
        await self._write("in-out", "stereo-or-mono", "mono" if mono else "stereo", index=input_pair)

    async def set_standby_time(self, standby_time: str) -> None:
        if standby_time not in STANDBY_TIMES:
            raise ValueError(f"Standby time should be one of {STANDBY_TIMES}")
        await self._write("settings", "standby-time", standby_time)

    async def set_fan_speed_method(self, method: str) -> None:
        if method not in FAN_SPEED_METHODS:
            raise ValueError(f"Fan speed method should be one of {FAN_SPEED_METHODS}")
        await self._write("settings", "fan-speed-method", method)

    async def set_power_on_delay(self, seconds: int) -> None:
        # AutoOnDelayTime:2, in steps of 2 seconds; the web API's own write for this hangs on V2.27
        if not 0 <= seconds <= 20:
            raise ValueError("Delay should be between 0 and 20 seconds (inclusive)")
        await self.send(f"FF5502FA{int(seconds) // 2:02X}")

    async def reboot(self) -> None:
        await self._write("identification", "reboot", "reboot")

    async def read_state(self) -> NadState:
        in_out = await self._handler(page="in-out", action="read")
        identification = await self._handler(page="identification", action="read")
        settings = await self._handler(page="settings", action="read")

        zone_channels = identification.get("zone-channel", [])
        zones = [
            Zone(int(zone.get("I", i)), zone.get("N", ""), _zone_channels(int(zone.get("I", i)), zone_channels))
            for i, zone in enumerate(identification.get("zone-info", []))
        ]

        return NadState(
            power=_on(identification.get("power-status", settings.get("power-status"))),
            input_names=_named(in_out["input-names"]),
            output_names=_named(in_out["output-names"]),
            output_gains=[float(gain) for gain in in_out["output-gain"]],
            output_mutes=[_on(mute) for mute in identification.get("channel-mute", ["off"] * CHANNEL_COUNT)],
            sources=[int(source) for source in in_out["sources"]],
            presets=[int(preset) for preset in in_out["dsp-presets"]],
            preset_names=_named_values(in_out.get("dsp-preset-items", [])),
            input_gains=[float(gain) for gain in in_out.get("input-gain", [])],
            signals=[bool(int(signal)) for signal in identification.get("channel-signal", [])],
            protection=list(identification.get("channel-protection", [])),
            stereo_mono=list(in_out.get("stereo-or-mono", [])),
            bridge_modes=list(in_out.get("bridge-modes", [])),
            global_enabled=[_on(in_out.get(f"global-{g}-enable")) for g in "ab"],
            global_gains=[float(in_out.get(f"global-{g}-gain", 0)) for g in "ab"],
            global_names=[in_out.get(f"global-{g}-name") or f"Global {g.upper()}" for g in "ab"],
            zones=[zone for zone in zones if zone.channels],
            amp_status=identification.get("amp-status"),
            temperatures=[t for t in map(_temperature, identification.get("temperature", [])) if t],
            inner_temperature=_temperature(identification.get("inner-temperature")),
            fan_speeds=list(identification.get("fan-speed", [])),
            power_on_method=settings.get("power-on-method"),
            standby_time=settings.get("standby-time"),
            power_on_delay=int(settings["power-on-delay"]) if settings.get("power-on-delay") else None,
            fan_speed_method=settings.get("fan-speed-method"),
            green_mode=_on(settings.get("green-mode")),
            password_protection=_on(settings.get("password-protection")),
            firmware_version=settings.get("firmware-version"),
        )

    async def read_state_over_tcp(self, previous: NadState) -> NadState:
        """Refresh what the IP protocol can report, keeping the rest of a previous snapshot."""
        power = await self.get_power()
        gains = [await self.get_output_gain(channel) for channel in range(1, CHANNEL_COUNT + 1)]
        mutes = [await self.get_output_mute(channel) for channel in range(1, CHANNEL_COUNT + 1)]
        return NadState(
            **{
                **previous.__dict__,
                "power": power,
                "output_gains": gains,
                "output_mutes": mutes,
                "from_http": False,
            }
        )
