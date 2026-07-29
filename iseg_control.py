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

    # @staticmethod
    # def display_value(encoded_value: str) -> str:
    #     value = encoded_value.strip()

    #     float_match = re.search(
    #         r"(?:Opaque:\s*)?Float:\s*([-+]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?|nan))",
    #         value,
    #         re.IGNORECASE,
    #     )
    #     if float_match:
    #         return float_match.group(1)

    #     integer_match = re.search(r"INTEGER:\s*([^\s]+)", value, re.IGNORECASE)
    #     if integer_match:
    #         return integer_match.group(1)

    #     ip_match = re.search(r"IpAddress:\s*(\S+)", value, re.IGNORECASE)
    #     if ip_match:
    #         return ip_match.group(1)

    #     if value.upper().startswith("STRING:"):
    #         return value.split(":", 1)[1].strip().strip('"')

    #     if value.startswith('"') and value.endswith('"'):
    #         return value.strip('"')

    #     return value

    # helpers to run commands
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

    def turn_on_crate(self):
        return self.snmpset_int("sysMainSwitch.0", 1)

    def turn_off_crate(self):
        return self.snmpset_int("sysMainSwitch.0", 0)

    # RAMP RATE 
    # set ramp UP rate 
    def set_VoltageRiseRate(self, channel, voltageRR):
        return self.snmpset_float(f"outputVoltageRiseRate.u{channel}", voltageRR)
    
    # set ramp DOWN rate 
    def set_VoltageFallRate(self, channel, voltageRR):
        return self.snmpset_float(f"outputVoltageFallRate.u{channel}", voltageRR)
   

    # run and record the ramp to manually calculate the ramp rate, 

    # # manually check the ramp rate 
    # def monitor_channel_ramp(
    #     self,
    #     channel: str,
    #     target_voltage_v: float,
    #     commanded_ramp_rate_v_per_s: float,
    #     polarity: str = "",
    #     neglect_readback_polarity: bool = True,
    # ) -> Tuple[bool, List[str]]:
    #     warnings = []
    #     if commanded_ramp_rate_v_per_s <= 0:
    #         raise RuntimeError(
    #             f"{channel.upper()}: commanded ramp rate must be positive for ramp monitoring."
    #         )

    #     monitor_duration_s = (
    #         abs(target_voltage_v) / commanded_ramp_rate_v_per_s
    #         + RAMP_MONITOR_EXTRA_SECONDS
    #     )
    #     start_time = time.monotonic()
    #     first_time = start_time
    #     first_voltage = self.read_measured_voltage(
    #         channel,
    #         polarity=polarity,
    #         neglect_readback_polarity=neglect_readback_polarity,
    #     )
    #     last_time = first_time
    #     last_voltage = first_voltage

    #     print(
    #         f"Monitoring {channel.upper()} ramp for up to {monitor_duration_s:.1f} s "
    #         f"toward {target_voltage_v:g} V."
    #     )

    #     while True:
    #         status = self.snmpget_value(f"outputStatus.{channel}")
    #         measured_voltage = self.read_measured_voltage(
    #             channel,
    #             polarity=polarity,
    #             neglect_readback_polarity=neglect_readback_polarity,
    #         )
    #         last_time = time.monotonic()
    #         last_voltage = measured_voltage
    #         elapsed_s = last_time - start_time

    #         print(
    #             f"  {channel.upper()} t={elapsed_s:.1f} s "
    #             f"status={status} measured={measured_voltage:g} V"
    #         )

    #         if self._target_voltage_reached(measured_voltage, target_voltage_v):
    #             warnings.append(
    #                 f"{channel.upper()}: ramp-rate readback was unreliable, but target "
    #                 f"{target_voltage_v:g} V was reached in {elapsed_s:.1f} s "
    #                 f"within the expected {monitor_duration_s:.1f} s window."
    #             )
    #             return True, warnings

    #         if elapsed_s >= monitor_duration_s:
    #             break

    #         time.sleep(1.0)

    #     elapsed_measurement_s = max(last_time - first_time, 1e-9)
    #     empirical_ramp_rate = (
    #         abs(last_voltage - first_voltage) / elapsed_measurement_s
    #     )
    #     lower_bound = commanded_ramp_rate_v_per_s * (1.0 - RAMP_RATE_TOLERANCE_FRACTION)
    #     upper_bound = commanded_ramp_rate_v_per_s * (1.0 + RAMP_RATE_TOLERANCE_FRACTION)
    #     within_tolerance = lower_bound <= empirical_ramp_rate <= upper_bound

    #     warnings.append(
    #         f"{channel.upper()}: target {target_voltage_v:g} V was not reached within "
    #         f"{monitor_duration_s:.1f} s. Empirical ramp estimate: "
    #         f"{empirical_ramp_rate:.3g} V/s from {first_voltage:g} V to "
    #         f"{last_voltage:g} V over {elapsed_measurement_s:.1f} s. "
    #         f"Commanded ramp rate: {commanded_ramp_rate_v_per_s:g} V/s. "
    #         f"This is {'within' if within_tolerance else 'outside'} the "
    #         f"{RAMP_RATE_TOLERANCE_FRACTION:.0%} tolerance window."
    #     )

    #     return within_tolerance, warnings

    def channel_on(self, channel):
        self.snmpset_int(f"outputSwitch.u{channel}", 1)

    def channel_off(self, channel):
        self.snmpset_int(f"outputSwitch.u{channel}", 0)

    def read_outputCurrent(self, channel):
        response = self.snmpget_value(f"outputMeasurementCurrent.u{channel}")
        response_list = response.split()
        return float(response_list[-2]) 

    def set_outputVoltage(self, channel, voltage):
        return self.snmpset_float(f"outputVoltage.u{channel}", voltage)

    # def configure_and_turn_on(
    #     self,
    #     channels: List[str],
    #     voltage_setpoint_v: float = 50.0,
    #     current_limit_a: float = 0.001,
    #     ramp_rate_v_per_s: float = 100.0,
    #     polarity: str = "",
    #     neglect_readback_polarity: bool = False,
    # ) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    #     for ch in channels:
    #         self.snmpset_int(f"outputSwitch.{ch}", 10)
    #         self.snmpset_float(f"outputVoltage.{ch}", voltage_setpoint_v)
    #         self.snmpset_float(f"outputCurrent.{ch}", current_limit_a)
    #         self.snmpset_float(f"outputVoltageRiseRate.{ch}", ramp_rate_v_per_s)

    #     configured_data = self.read_channel_settings(
    #         channels,
    #         polarity=polarity,
    #         neglect_readback_polarity=neglect_readback_polarity,
    #     )
    #     expected_voltage_v = self._expected_voltage(
    #         voltage_setpoint_v,
    #         polarity,
    #         neglect_readback_polarity,
    #     )
    #     expected_ramp_rate_v_per_s = self._expected_ramp_rate(
    #         ramp_rate_v_per_s,
    #         polarity,
    #         neglect_readback_polarity,
    #     )

    #     verification_failures = []
    #     ramp_warning_channels = []
    #     warnings = []
    #     for ch in channels:
    #         set_v = float(configured_data[ch]["set_voltage_V"])
    #         set_i = float(configured_data[ch]["set_current_A"])
    #         ramp_up = float(configured_data[ch]["ramp_up_V_per_s"])

    #         if abs(set_v - expected_voltage_v) > 1.0:
    #             verification_failures.append(
    #                 f"{ch.upper()}: voltage readback mismatch "
    #                 f"(expected {expected_voltage_v:g} V, got {set_v:g} V)"
    #             )

    #         if abs(set_i - current_limit_a) > 0.0001:
    #             verification_failures.append(
    #                 f"{ch.upper()}: current limit readback mismatch "
    #                 f"(expected {current_limit_a:g} A, got {set_i:g} A)"
    #             )

    #         ramp_readback_tolerance = (
    #             abs(expected_ramp_rate_v_per_s) * RAMP_RATE_READBACK_TOLERANCE_FRACTION
    #         )
    #         if abs(ramp_up - expected_ramp_rate_v_per_s) > ramp_readback_tolerance:
    #             ramp_warning_channels.append(ch)
    #             warnings.append(
    #                 f"{ch.upper()}: ramp-rate readback mismatch "
    #                 f"(expected readback {expected_ramp_rate_v_per_s:g} V/s "
    #                 f"from commanded {ramp_rate_v_per_s:g} V/s, "
    #                 f"read back {ramp_up:g} V/s; tolerance "
    #                 f"+/-{ramp_readback_tolerance:g} V/s). "
    #                 "Proceeding with timed voltage/status monitoring instead of "
    #                 "trusting ramp-rate readback."
    #             )

    #     if verification_failures:
    #         detail = "\n  - ".join(verification_failures)
    #         raise RuntimeError(
    #             "Pre-ON setting verification failed. Refusing to turn ON.\n"
    #             f"  - {detail}"
    #         )

    #     ramp_failures = []
    #     ramp_warning_channel_set = set(ramp_warning_channels)
    #     for ch in channels:
    #         self.snmpset_int(f"outputSwitch.{ch}", 1)
    #         if ch in ramp_warning_channel_set:
    #             ramp_ok, ramp_warnings = self.monitor_channel_ramp(
    #                 ch,
    #                 expected_voltage_v,
    #                 ramp_rate_v_per_s,
    #                 polarity=polarity,
    #                 neglect_readback_polarity=neglect_readback_polarity,
    #             )
    #             warnings.extend(ramp_warnings)
    #             if not ramp_ok:
    #                 ramp_failures.append(
    #                     f"{ch.upper()}: empirical ramp rate was outside "
    #                     f"{RAMP_RATE_TOLERANCE_FRACTION:.0%} of commanded "
    #                     f"{ramp_rate_v_per_s:g} V/s."
    #                 )

    #     if ramp_failures:
    #         detail = "\n  - ".join(ramp_failures)
    #         raise RampVerificationError(
    #             "Empirical ramp-rate verification failed.\n"
    #             f"  - {detail}",
    #             warnings,
    #         )

    #     data = self.read_channel_settings(
    #         channels,
    #         polarity=polarity,
    #         neglect_readback_polarity=neglect_readback_polarity,
    #     )
    #     return data, warnings

    # def clear_events(self, channels: List[str]) -> None:
    #     for ch in channels:
    #         self.snmpset_int(f"outputSwitch.{ch}", 10)

    # def turn_off_all(self, channels: List[str], emergency: bool = False) -> None:
    #     value = 3 if emergency else 0
    #     for ch in channels:
    #         self.snmpset_int(f"outputSwitch.{ch}", value)
