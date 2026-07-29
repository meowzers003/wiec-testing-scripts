#!/usr/bin/env python3

import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


MAX_SNMP_RETRIES = 3
RAMP_MONITOR_EXTRA_SECONDS = 2.0
RAMP_RATE_TOLERANCE_FRACTION = 0.10
RAMP_RATE_READBACK_TOLERANCE_FRACTION = 0.05


class RampVerificationError(RuntimeError):
    def __init__(self, message: str, warnings: List[str]):
        super().__init__(message)
        self.warnings = warnings


@dataclass
class SNMPConfig:
    ip: str
    mib_name: str = "+WIENER-CRATE-MIB"
    read_community: str = "public"
    write_community: str = "guru"
    precision: str = ".9"
    version: str = "2c"
    timeout_s: int = 30
    log_commands: bool = False
    max_retries: int = MAX_SNMP_RETRIES


class IsegMPOD:
    def __init__(self, cfg: SNMPConfig):
        self.cfg = cfg

    def _run(self, args: List[str]) -> str:
        command = " ".join(shlex.quote(arg) for arg in args)
        # if self.cfg.log_commands:
        #     print(f"SNMP command: {command}")

        max_retries = max(0, self.cfg.max_retries)
        max_attempts = max_retries + 1
        last_error: Optional[RuntimeError] = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = subprocess.run(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=self.cfg.timeout_s,
                    check=True,
                )
                return result.stdout.strip()
            except subprocess.TimeoutExpired:
                last_error = RuntimeError(
                    "SNMP command timed out:\n"
                    f"Command: {command}"
                )
            except subprocess.CalledProcessError as e:
                last_error = RuntimeError(
                    "SNMP command failed:\n"
                    f"Command: {command}\n"
                    f"STDOUT: {e.stdout}\n"
                    f"STDERR: {e.stderr}"
                )

            if attempt < max_attempts:
                print(
                    f"SNMP command attempt {attempt}/{max_attempts} failed; "
                    f"retrying {command}"
                )

        raise RuntimeError(
            f"SNMP command failed after {max_attempts} attempt(s).\n"
            f"{last_error}"
        )

    def _command_args(self, command: str, community: str) -> List[str]:
        args = [
            command,
            "-Op", self.cfg.precision,
            "-v", self.cfg.version,
            "-m", self.cfg.mib_name,
            "-c", community,
            self.cfg.ip,
        ]
        if command == "snmpwalk":
            args.append("crate")
        return args

    @staticmethod
    def parse_response_value(raw: str) -> str:
        for line in raw.splitlines():
            match = re.match(r"^\S+::[^\s=]+\s*=\s*(.+)$", line.strip())
            if match:
                return match.group(1).strip()
        return raw.strip()

    # snmp helpers to run commands
    def snmpset_float(self, oid: str, value: float) -> str:
        return self._run(
            self._command_args("snmpset", self.cfg.write_community)
            + [oid, "F", str(value)]
        )

    def snmpset_int(self, oid: str, value: int) -> str:
        return self._run(
            self._command_args("snmpset", self.cfg.write_community)
            + [oid, "i", str(value)]
        )

    def snmpget_value(self, oid: str) -> str:
        raw = self._run(self._command_args("snmpget", self.cfg.read_community) + [oid])
        return self.parse_response_value(raw)

    # on and off controls
    def turn_on_crate(self):
        return self.snmpset_int("sysMainSwitch.0", 1)

    def turn_off_crate(self):
        return self.snmpset_int("sysMainSwitch.0", 0)

    def channel_on(self, channel):
        self.snmpset_int(f"outputSwitch.u{channel}", 1)

    def channel_off(self, channel):
        self.snmpset_int(f"outputSwitch.u{channel}", 0)


    # RAMP RATE
    # set ramp UP rate
    def set_VoltageRiseRate(self, channel, voltageRR):
        return self.snmpset_float(f"outputVoltageRiseRate.u{channel}", voltageRR)
    
    # set ramp DOWN rate
    def set_VoltageFallRate(self, channel, voltageRR):
        return self.snmpset_float(f"outputVoltageFallRate.u{channel}", voltageRR)

    def set_outputVoltage(self, channel, voltage):
        return self.snmpset_float(f"outputVoltage.u{channel}", voltage)

    def set_outputCurrent(self, channel, current):
        return self.snmpset_float(f"outputCurrent.u{channel}", current)


    # run and record the ramp to manually calculate the ramp rate,
    def read_outputCurrent(self, channel):
        response = self.snmpget_value(f"outputMeasurementCurrent.u{channel}")
        response_list = response.split()
        return float(response_list[-2])

    def read_outputVoltage(self,channel):
        response = self.snmpget_value(f"outputMeasurementSenseVoltage.u{channel}")
        response_list = response.split()
        return float(response_list[-2])
