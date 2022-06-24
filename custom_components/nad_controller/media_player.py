"""Support for interfacing with NAD Cl 16-60 home audio controller."""
import logging
from enum import Enum

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature, MediaPlayerDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from const import DOMAIN
import socket
from enum import Enum

_LOGGER = logging.getLogger(__name__)

TCP_PORT = 52000
BUFFER_SIZE = 1024


class StereoMono(Enum):
    STEREO = "00"
    MONO = "01"


class Bridge(Enum):
    STAND = "00"
    BRIDGE = "01"


class PowerMethod(Enum):
    POWER_BUTTON = "00"
    ALWAYS_ON = "01"
    V12_TRIGGER = "02"
    SIGNAL_SENSE = "03"


class NadClient:

    def __init__(self, ip):
        self._ip = ip
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((ip, TCP_PORT))

    def send(self, hex_string):
        self._socket.send(bytearray.fromhex(hex_string))
        return self._socket.recv(BUFFER_SIZE)

    @staticmethod
    def to_string(byte_text: bytes):
        return byte_text.decode().split("\x00")[0]

    @staticmethod
    def ip_to_hex(ip: str):
        return '{:02X}{:02X}{:02X}{:02X}'.format(*map(int, ip.split('.')))

    @staticmethod
    def int_to_hex(i: int):
        return '{:02X}'.format(i)

    def global_input_to_hex(self, global_input: int):
        if not 1 <= global_input <= 2:
            raise ValueError("Channel should be either 1 or 2")
        return self.int_to_hex(global_input - 1)

    def channel_to_hex(self, channel: int):
        if not 1 <= channel <= 16:
            raise ValueError("Channel should be between 1 and 16 (inclusive)")
        return self.int_to_hex(channel - 1)

    def gain_to_hex(self, gain: float):
        if not -6 <= gain <= 6:
            raise ValueError("Gain should be between -6 and 6 (inclusive)")
        return self.int_to_hex(int((gain + 6) * 2))

    def preset_to_hex(self, preset_index: int):
        if not 0 <= preset_index <= 9:
            raise ValueError("Preset index should be between 0 and 9 (inclusive)")
        return self.int_to_hex(preset_index)

    def delay_time_to_hex(self, delay_time: int):
        if not 0 <= delay_time <= 20:
            raise ValueError("Delay time should be between 0 and 20 (inclusive)")
        return self.int_to_hex(int(delay_time / 2))

    # Identification
    def get_device_name(self):
        return self.to_string(self.send("FF5501E0"))

    def get_device_model(self):
        return self.to_string(self.send("FF5501E1"))

    def get_project_name(self):
        return self.to_string(self.send("FF5501E2"))

    def get_installation_date(self):
        return self.to_string(self.send("FF5501E4"))

    def get_firmware_version(self):
        return self.to_string(self.send("FF5501E5"))

    def get_serial_number(self):
        return self.to_string(self.send("FF5501E6"))

    def led_flash_on(self):
        # Flash LED:ON
        return self.to_string(self.send("FF5502EB01"))

    def led_flash_off(self):
        # Flash LED:OFF
        return self.to_string(self.send("FF5502EB00"))

    def dhcp_on(self):
        # IP Method:DHCP
        return self.to_string(self.send("FF5502EC01"))

    def dhcp_off(self):
        # IP Method:STATIC
        return self.to_string(self.send("FF5502EC00"))

    def set_ip_address(self, ip: str):
        # Broken?
        return self.to_string(self.send("FF5501ED" + self.ip_to_hex(ip)))

    def set_subnet_mask(self, subnet_mask: str):
        # Broken?
        return self.to_string(self.send("FF5501EE" + self.ip_to_hex(subnet_mask)))

    # Control
    def set_global_control(self, global_input: int, on: bool):
        # Set Global 1 ON
        # Set Global 1 OFF
        global_input_hex = self.global_input_to_hex(global_input)
        code = {True: "01", False: "00"}[on]
        return self.to_string(self.send("FF5503F0" + global_input_hex + code))

    def set_input_gain(self, input_channel: int, gain: float):
        # Cmd:ChannelInputGain ,Channel Input 1
        channel_hex = self.channel_to_hex(input_channel)
        gain_hex = self.gain_to_hex(gain)
        return self.to_string(self.send("FF5503F1" + channel_hex + gain_hex))

    def set_output_gain(self, output_channel: int, gain: float):
        # Cmd:ChannelOutputGain ,Channel Output 1
        channel_hex = self.channel_to_hex(output_channel)
        gain_hex = self.gain_to_hex(gain)
        return self.to_string(self.send("FF5503F2" + channel_hex + gain_hex))

    def get_output_gain(self, output_channel: int):
        # Channel[0] Output Gain:0
        channel_hex = self.channel_to_hex(output_channel)
        result = self.to_string(self.send("FF550210" + channel_hex))
        return float(result.split(':')[1])

    def set_output_source(self, output_channel: int, input_channel: int):
        # Cmd:ChannelOutputSource ,Channel Output 1
        output_hex = self.channel_to_hex(output_channel)
        input_hex = self.channel_to_hex(input_channel)
        return self.to_string(self.send("FF5503F4" + output_hex + input_hex))

    def set_stereo_mono(self, input_channel: int, stereo: StereoMono):
        # Cmd:ChannelStereoMono ,Channel Input 1
        channel_hex = self.channel_to_hex(input_channel)
        return self.to_string(self.send("FF5503F5" + channel_hex + stereo.value))

    def set_bridge(self, output_channel: int, bridged: Bridge):
        # Cmd:ChannelBridge ,Channel Output 1
        channel_hex = self.channel_to_hex(output_channel)
        return self.to_string(self.send("FF5503F6" + channel_hex + bridged.value))

    def set_output_mute(self, output_channel: int, muted: bool):
        # Cmd:ChannelMute ,Channel Output 1
        channel_hex = self.channel_to_hex(output_channel)
        code = {True: "00", False: "01"}[muted]
        return self.to_string(self.send("FF5503F7" + channel_hex + code))

    def get_output_mute(self, output_channel: int):
        # Channel[0] Mute Status:Unmute
        channel_hex = self.channel_to_hex(output_channel)
        mute_string = self.to_string(self.send("FF550212" + channel_hex)).split(':')[1]
        return mute_string == "Mute"

    # DSP
    def set_output_preset(self, output_channel: int, preset_index=0):
        # Cmd:ChannelOutputPreset ,Channel Output 1
        channel_hex = self.channel_to_hex(output_channel)
        preset_hex = self.preset_to_hex(preset_index)
        return self.to_string(self.send("FF5503F3" + channel_hex + preset_hex))

    # Settings
    def set_power_method(self, power_method: PowerMethod):
        # Power mode:Power Button
        return self.to_string(self.send("FF5502F8" + power_method.value))

    def set_green_mode(self, green: bool):
        # Green mode:off
        code = {True: "01", False: "00"}[green]
        return self.to_string(self.send("FF5502F9" + code))

    def set_delay_time(self, delay: int):
        # AutoOnDelayTime:0
        delay_hex = self.delay_time_to_hex(delay)
        return self.to_string(self.send("FF5502FA" + delay_hex))

    def reset(self):
        # Wait system reset all
        return self.to_string(self.send("FF5501FB"))

    def power_on(self):
        # Cmd:PowerOn
        return self.to_string(self.send("FF550101"))

    def power_off(self):
        # Cmd:PowerOff
        return self.to_string(self.send("FF550102"))

    def power_toggle(self):
        # Cmd:PowerToggle
        return self.to_string(self.send("FF550103"))

    def get_power_status(self):
        # Power status:On
        return self.to_string(self.send("FF550170"))

    def test_command(self, command: str):
        return self.to_string(self.send(command))


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the NAD Cl 16-60 home audio controller platform."""
    ip = config_entry.data[CONF_HOST]

    client = NadClient(ip)

    amp = NadAmp(client)

    entities = [amp]
    for output_channel_index in range(1, 16):
        _LOGGER.info("Adding channel %d", output_channel_index)
        entities.append(
            NadChannel(client, amp, output_channel_index)
        )

    async_add_entities(entities)


class SoundMode(Enum):
    PresetNone: 0
    Preset1: 1
    Preset2: 2
    Preset3: 3
    Preset4: 4
    Preset5: 5
    Preset6: 6
    Preset7: 7
    Preset8: 8
    Preset9: 9


class InputSource(Enum):
    Global1: (True, 1)
    Global2: (True, 2)
    Source1: (False, 1)
    Source2: (False, 2)
    Source3: (False, 3)
    Source4: (False, 4)
    Source5: (False, 5)
    Source6: (False, 6)
    Source7: (False, 7)
    Source8: (False, 8)
    Source9: (False, 9)
    Source10: (False, 10)
    Source11: (False, 11)
    Source12: (False, 12)
    Source13: (False, 13)
    Source14: (False, 14)
    Source15: (False, 15)
    Source16: (False, 16)


class NadAmp(MediaPlayerEntity):
    _attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, client: NadClient):
        self._client = client

        self._attr_device_class = MediaPlayerDeviceClass.RECEIVER
        self._attr_sound_mode_list = [sm.key for sm in SoundMode]

        device_name = client.get_device_name()
        serial_number = client.get_serial_number()
        model = client.get_device_model()
        sw_version = client.get_firmware_version()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            manufacturer="NAD",
            model=model,
            name=device_name,
            sw_version=sw_version,
        )

        self._attr_unique_id = serial_number
        self._attr_name = device_name

        self._state = None
        self._update_success = True

    def update(self):
        """Retrieve latest state."""
        try:
            self._state = self._client.get_power_status()
            self._update_success = True
        except Exception:
            self._update_success = False
            _LOGGER.warning("Could not update")
            return

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._update_success

    def turn_on(self):
        self._client.power_on()

    def turn_off(self):
        self._client.power_off()

    async def async_toggle(self):
        await self._client.power_toggle()


class NadChannel(MediaPlayerEntity):
    _attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
    )

    def __init__(self, client: NadClient, amp: NadAmp, output_index: int):
        self._client = client
        self._output_channel = output_index

        self._attr_source_list = [source.key for source in InputSource]
        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER

        self._attr_unique_id = f"{amp.unique_id}_{self._output_channel}"
        self._attr_name = f"{amp.name} channel {self._output_channel}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._attr_name,
            manufacturer="NAD",
            via_device=amp.device_info.get('identifiers')[0]
        )

        self._source_index = None
        self._is_global = False
        self._snapshot = None
        self._volume = None
        self._update_success = True

    def update(self):
        """Retrieve latest state."""
        try:
            self._volume = self._client.get_output_gain(self._output_channel)
            self._attr_is_volume_muted = self._client.get_output_mute(self._output_channel)
            self._update_success = True
        except Exception:
            self._update_success = False
            _LOGGER.warning("Could not update output index %d", self._output_channel)
            return

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._update_success

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        if self._volume is None:
            return None
        return (self._volume + 6) / 12

    def set_volume_level(self, volume):
        self._volume = volume * 12 - 6
        self._client.set_output_gain(self._output_channel, self._volume)

    async def async_volume_up(self):
        await self._client.set_output_gain(self._output_channel, self._volume + 0.5)
        self._volume += 0.5

    async def async_volume_down(self):
        await self._client.set_output_gain(self._output_channel, self._volume - 0.5)
        self._volume -= 0.5

    def mute_volume(self, mute):
        self._client.set_output_mute(self._output_channel, mute)

    @property
    def source(self) -> str | None:
        if self._source_index is None:
            return None
        return f"{'Global' if self._is_global else 'Input'}{self._source_index}"

    def select_source(self, source):
        if source not in InputSource:
            return

        (is_global, index) = InputSource[source].value

        if ((not is_global) and self._is_global) or (is_global and (index != self._source_index)):
            self._client.set_global_control(self._source_index, False)

        if is_global:
            self._client.set_global_control(index, True)
        else:
            self._client.set_output_source(self._output_channel, index)

        self._source_index = index
        self._is_global = is_global

    def select_sound_mode(self, sound_mode):
        self._client.set_output_preset(self._output_channel, SoundMode[sound_mode].value)
