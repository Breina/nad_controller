import socket
from enum import Enum

DEFAULT_TCP_PORT = 52000
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

    def __init__(self, ip: str, port=DEFAULT_TCP_PORT):
        self._ip = ip
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((ip, port))

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