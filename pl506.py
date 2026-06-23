import re
import subprocess
import time
from dataclasses import dataclass


@dataclass
class PL506ChannelReadback:
    channel: int
    voltage_setpoint_v: float
    current_limit_a: float
    terminal_voltage_v: float
    sense_voltage_v: float
    measured_current_a: float
    switch_state: str
    status: str


class PL506:
    def __init__(
        self,
        ip="192.168.91.80",
        read_community="public",
        write_community="guru",
        mib_dir="/usr/share/snmp/mibs",
        timeout_s=5,
    ):
        self.ip = ip
        self.read_community = read_community
        self.write_community = write_community
        self.timeout_s = timeout_s

        self.mib_args = [
            "-v", "2c",
            "-M", f"+{mib_dir}",
            "-m", "+WIENER-CRATE-MIB",
        ]

    def _run(self, cmd):
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=self.timeout_s,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "SNMP command failed\n"
                f"Command: {' '.join(cmd)}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

        return result.stdout.strip()

    def get_raw(self, oid, community=None):
        community = community or self.read_community
        return self._run([
            "snmpget",
            *self.mib_args,
            "-Oqv",
            "-c", community,
            self.ip,
            oid,
        ])

    def walk_raw(self, oid, community=None):
        community = community or self.read_community
        return self._run([
            "snmpwalk",
            *self.mib_args,
            "-Oqv",
            "-c", community,
            self.ip,
            oid,
        ])

    def set_float(self, oid, value, community=None):
        community = community or self.write_community
        return self._run([
            "snmpset",
            *self.mib_args,
            "-Oqv",
            "-c", community,
            self.ip,
            oid,
            "F",
            str(float(value)),
        ])

    def set_int(self, oid, value, community=None):
        community = community or self.write_community
        return self._run([
            "snmpset",
            *self.mib_args,
            "-Oqv",
            "-c", community,
            self.ip,
            oid,
            "i",
            str(int(value)),
        ])

    @staticmethod
    def parse_float(text):
        match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
        if not match:
            raise ValueError(f"Could not parse float from: {text}")
        return float(match.group(0))

    def get_float(self, oid):
        return self.parse_float(self.get_raw(oid))

    def list_channels(self):
        return self.walk_raw("outputName")

    def main_on(self):
        return self.set_int("sysMainSwitch.0", 1)

    def main_off(self):
        return self.set_int("sysMainSwitch.0", 0)

    def channel_on(self, channel):
        return self.set_int(f"outputSwitch.u{channel}", 1)

    def channel_off(self, channel):
        return self.set_int(f"outputSwitch.u{channel}", 0)

    def set_voltage(self, channel, voltage_v):
        return self.set_float(f"outputVoltage.u{channel}", voltage_v)

    def set_current_limit(self, channel, current_a):
        return self.set_float(f"outputCurrent.u{channel}", current_a)

    def read_channel(self, channel):
        return PL506ChannelReadback(
            channel=channel,
            voltage_setpoint_v=self.get_float(f"outputVoltage.u{channel}"),
            current_limit_a=self.get_float(f"outputCurrent.u{channel}"),
            terminal_voltage_v=self.get_float(f"outputMeasurementTerminalVoltage.u{channel}"),
            sense_voltage_v=self.get_float(f"outputMeasurementSenseVoltage.u{channel}"),
            measured_current_a=self.get_float(f"outputMeasurementCurrent.u{channel}"),
            switch_state=self.get_raw(f"outputSwitch.u{channel}"),
            status=self.get_raw(f"outputStatus.u{channel}"),
        )

    def safe_turn_on_channel(
        self,
        channel,
        voltage_v,
        current_limit_a,
        max_voltage_v=30.0,
        max_current_a=5.0,
        settle_s=1.0,
    ):
        if not (0.0 <= voltage_v <= max_voltage_v):
            raise ValueError(f"Refusing voltage {voltage_v} V")

        if not (0.0 <= current_limit_a <= max_current_a):
            raise ValueError(f"Refusing current limit {current_limit_a} A")

        self.channel_off(channel)
        self.set_current_limit(channel, current_limit_a)
        self.set_voltage(channel, voltage_v)

        self.main_on()
        self.channel_on(channel)

        time.sleep(settle_s)
        return self.read_channel(channel)