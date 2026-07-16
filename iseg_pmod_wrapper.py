#!/usr/bin/env python3

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class SNMPConfig:
    ip: str
    mib_name: str = "+WIENER-CRATE-MIB"
    read_community: str = "public"
    write_community: str = "guru"
    version: str = "2c"
    timeout_s: int = 30
    log_commands: bool = False


class IsegMPOD:
    def __init__(self, cfg: SNMPConfig):
        self.cfg = cfg

    def _run(self, args: List[str]) -> str:
        if self.cfg.log_commands:
            command = " ".join(shlex.quote(arg) for arg in args)
            print(f"SNMP command: {command}")

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
            raise RuntimeError(f"SNMP command timed out: {' '.join(shlex.quote(a) for a in args)}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                "SNMP command failed:\n"
                f"Command: {' '.join(shlex.quote(a) for a in args)}\n"
                f"STDOUT: {e.stdout}\n"
                f"STDERR: {e.stderr}"
            )

    def _command_args(self, command: str, community: str) -> List[str]:
        args = [
            command,
            "-v", self.cfg.version,
            "-m", self.cfg.mib_name,
            "-c", community,
            self.cfg.ip,
        ]
        if command == "snmpwalk":
            args.append("crate")
        return args

    @staticmethod
    def parse_walk_output(raw: str) -> Dict[str, str]:
        entries: Dict[str, str] = {}
        for line in raw.splitlines():
            if "No more variables left in this MIB View" in line:
                continue
            match = re.match(r"^\S+::([^\s=]+)\s*=\s*(.+)$", line.strip())
            if match:
                entries[match.group(1)] = match.group(2).strip()
        return entries

    @staticmethod
    def parse_response_value(raw: str) -> str:
        for line in raw.splitlines():
            match = re.match(r"^\S+::[^\s=]+\s*=\s*(.+)$", line.strip())
            if match:
                return match.group(1).strip()
        return raw.strip()

    @staticmethod
    def display_value(encoded_value: str) -> str:
        value = encoded_value.strip()

        float_match = re.search(
            r"(?:Opaque:\s*)?Float:\s*([-+]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?|nan))",
            value,
            re.IGNORECASE,
        )
        if float_match:
            return float_match.group(1)

        integer_match = re.search(r"INTEGER:\s*([^\s]+)", value, re.IGNORECASE)
        if integer_match:
            return integer_match.group(1)

        ip_match = re.search(r"IpAddress:\s*(\S+)", value, re.IGNORECASE)
        if ip_match:
            return ip_match.group(1)

        if value.upper().startswith("STRING:"):
            return value.split(":", 1)[1].strip().strip('"')

        if value.startswith('"') and value.endswith('"'):
            return value.strip('"')

        return value

    @staticmethod
    def _find_snapshot_value(snapshot: Dict[str, str], candidates: List[str]) -> str:
        for key in candidates:
            if key in snapshot:
                return IsegMPOD.display_value(snapshot[key])

        for key, value in snapshot.items():
            for candidate in candidates:
                if key.startswith(candidate):
                    return IsegMPOD.display_value(value)

        return ""

    @staticmethod
    def parse_module_description(description: str) -> Dict[str, str]:
        parts = [part.strip() for part in description.split(",")]
        fields = {
            "module_name": parts[0] if len(parts) > 0 else "UNKNOWN",
            "firmware_name": parts[1] if len(parts) > 1 else "UNKNOWN",
            "channel_count": parts[2] if len(parts) > 2 else "UNKNOWN",
            "serial_number": parts[3] if len(parts) > 3 else "UNKNOWN",
            "firmware_number": parts[4] if len(parts) > 4 else "UNKNOWN",
        }
        return fields

    @staticmethod
    def _channel_count(module_info: Dict[str, str]) -> int:
        try:
            return int(module_info.get("channel_count", "0"))
        except ValueError:
            return 0

    @staticmethod
    def _module_number(module_id: str) -> int:
        match = re.fullmatch(r"ma(\d+)", module_id)
        if not match:
            raise ValueError(f"Unexpected module id format: {module_id}")
        return int(match.group(1))

    @staticmethod
    def _apply_readback_polarity(
        value: str,
        polarity: str,
        neglect_readback_polarity: bool,
    ) -> str:
        if not neglect_readback_polarity:
            return value

        polarity = polarity.lower()
        if polarity not in {"positive", "negative"}:
            return value

        try:
            numeric_value = float(value)
        except ValueError:
            return value

        magnitude = abs(numeric_value)
        signed_value = magnitude if polarity == "positive" else -magnitude
        return f"{signed_value:g}"

    def read_all(self) -> Dict[str, str]:
        raw = self._run(self._command_args("snmpwalk", self.cfg.read_community))
        entries = self.parse_walk_output(raw)
        if not entries:
            raise RuntimeError(
                "The full snmpwalk returned no parseable 'OID = TYPE: value' records."
            )
        return entries

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

    def get_crate_info(self, snapshot: Dict[str, str]) -> Dict[str, str]:
        required_oids = ["sysMainSwitch.0", "sysStatus.0", "outputNumber.0"]
        missing = [oid for oid in required_oids if oid not in snapshot]
        if missing:
            raise RuntimeError(
                "The crate snmpwalk did not include required crate records: "
                + ", ".join(missing)
            )

        crate_info = {
            "sysMainSwitch": self.display_value(snapshot["sysMainSwitch.0"]),
            "sysStatus": self.display_value(snapshot["sysStatus.0"]),
            "outputNumber": self.display_value(snapshot["outputNumber.0"]),
            "moduleNumber": self.display_value(snapshot.get("moduleNumber.0", "")),
            "psSerialNumber": self.display_value(snapshot.get("psSerialNumber.0", "")),
            "ipDynamicAddress": self.display_value(snapshot.get("ipDynamicAddress.0", "")),
            "ipStaticAddress": self.display_value(snapshot.get("ipStaticAddress.0", "")),
            "macAddress": self.display_value(snapshot.get("macAddress.0", "")),
            "firmwareVersion": self._find_snapshot_value(snapshot, [
                "crateFirmwareVersion.0",
                "crateFirmwareVersion.",
                "systemFirmwareVersion.0",
                "sysFirmwareVersion.0",
                "psFirmwareVersion.0",
            ]),
        }

        return crate_info

    def discover_iseg_modules(self, snapshot: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        modules: Dict[str, Dict[str, str]] = {}

        for oid, encoded_value in snapshot.items():
            match = re.fullmatch(r"moduleDescription\.(ma\d+)", oid)
            if not match:
                continue

            module_id = match.group(1)
            description = self.display_value(encoded_value)
            if "iseg" not in description.lower():
                continue

            description_info = self.parse_module_description(description)
            serial_number = self._find_snapshot_value(snapshot, [
                f"moduleSerialNumber.{module_id}",
            ]) or description_info["serial_number"]
            firmware_number = self._find_snapshot_value(snapshot, [
                f"moduleFirmwareVersion.{module_id}",
            ]) or description_info["firmware_number"]

            modules[module_id] = {
                "description": description,
                "module_name": description_info["module_name"],
                "firmware_name": description_info["firmware_name"],
                "channel_count": description_info["channel_count"],
                "serial_number": serial_number,
                "firmware_number": firmware_number,
            }

        if not modules:
            raise RuntimeError("No iseg moduleDescription entries found in this crate walk.")

        return modules

    @staticmethod
    def channel_module_id(channel: str) -> str:
        channel_number = int(channel[1:])
        module_number = channel_number // 100
        return f"ma{module_number}"

    def discover_channels(
        self,
        snapshot: Dict[str, str],
        iseg_modules: Dict[str, Dict[str, str]],
    ) -> List[str]:
        channels = []

        for oid in snapshot:
            match = re.fullmatch(r"outputIndex\.(u\d+)", oid)
            if match:
                channels.append(match.group(1))

        if not channels:
            for oid in snapshot:
                match = re.fullmatch(r"outputName\.(u\d+)", oid)
                if match:
                    channels.append(match.group(1))

        if not channels:
            raise RuntimeError("No output channels found from outputIndex/outputName records.")

        channels = [
            channel for channel in channels
            if not 700 <= int(channel[1:]) <= 707
        ]
        channels = [
            channel for channel in channels
            if self.channel_module_id(channel) in iseg_modules
        ]

        if not channels:
            raise RuntimeError("No output channels found for discovered iseg modules.")

        channels.sort(key=lambda channel: int(channel[1:]))
        return channels

    def expected_channels_for_module(
        self,
        module_id: str,
        module_info: Dict[str, str],
    ) -> List[str]:
        module_number = self._module_number(module_id)
        channel_count = self._channel_count(module_info)
        start_index = module_number * 100
        return [
            f"u{channel_index}"
            for channel_index in range(start_index, start_index + channel_count)
        ]

    def channels_by_module(self, channels: List[str]) -> Dict[str, List[str]]:
        assignments: Dict[str, List[str]] = {}
        for channel in channels:
            assignments.setdefault(self.channel_module_id(channel), []).append(channel)
        for module_id in assignments:
            assignments[module_id].sort(key=lambda channel: int(channel[1:]))
        return assignments

    def channel_health_failures(
        self,
        channels: List[str],
        snapshot: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        failures = []
        bad_keywords = [
            "outputFailure",
            "outputEmergencyOff",
            "outputInhibit",
            "outputCurrentBoundsExceeded",
            "outputVoltageBoundsExceeded",
        ]

        for ch in channels:
            oid = f"outputStatus.{ch}"
            try:
                if snapshot is not None:
                    status = snapshot.get(oid, "MISSING")
                else:
                    status = self.snmpget_value(oid)
            except Exception as e:
                failures.append(f"{ch.upper()}: could not read {oid}: {e}")
                continue

            if status == "MISSING":
                failures.append(f"{ch.upper()}: {oid} record is missing")
                continue

            detected_conditions = [
                keyword for keyword in bad_keywords
                if keyword in status
            ]
            for condition in detected_conditions:
                failures.append(f"{ch.upper()}: {condition} detected in {status}")

        return failures

    def check_channel_health(
        self,
        channels: List[str],
        snapshot: Optional[Dict[str, str]] = None,
    ) -> bool:
        return not self.channel_health_failures(channels, snapshot)

    def read_channel_settings(
        self,
        channels: List[str],
        snapshot: Optional[Dict[str, str]] = None,
        polarity: str = "",
        neglect_readback_polarity: bool = False,
    ) -> Dict[str, Dict[str, str]]:
        data = {}

        for ch in channels:
            required_oids = {
                "set_voltage_V": f"outputVoltage.{ch}",
                "set_current_A": f"outputCurrent.{ch}",
                "measured_voltage_V": f"outputMeasurementSenseVoltage.{ch}",
                "measured_current_A": f"outputMeasurementCurrent.{ch}",
                "ramp_up_V_per_s": f"outputVoltageRiseRate.{ch}",
            }

            values = {}
            for key, oid in required_oids.items():
                if snapshot is not None:
                    if oid not in snapshot:
                        raise RuntimeError(
                            f"{ch}: missing required record from snmpwalk: {oid}"
                        )
                    encoded_value = snapshot[oid]
                else:
                    encoded_value = self.snmpget_value(oid)

                values[key] = self.display_value(encoded_value)

            for voltage_key in ("set_voltage_V", "measured_voltage_V"):
                values[voltage_key] = self._apply_readback_polarity(
                    values[voltage_key],
                    polarity,
                    neglect_readback_polarity,
                )

            data[ch] = values

        return data

    def configure_and_turn_on(
        self,
        channels: List[str],
        voltage_setpoint_v: float = 50.0,
        current_limit_a: float = 0.001,
        ramp_rate_v_per_s: float = 100.0,
        polarity: str = "",
        neglect_readback_polarity: bool = False,
    ) -> Dict[str, Dict[str, str]]:
        for ch in channels:
            self.snmpset_int(f"outputSwitch.{ch}", 10)
            self.snmpset_float(f"outputVoltage.{ch}", voltage_setpoint_v)
            self.snmpset_float(f"outputCurrent.{ch}", current_limit_a)
            self.snmpset_float(f"outputVoltageRiseRate.{ch}", ramp_rate_v_per_s)

        configured_data = self.read_channel_settings(
            channels,
            polarity=polarity,
            neglect_readback_polarity=neglect_readback_polarity,
        )
        expected_voltage_v = voltage_setpoint_v
        if neglect_readback_polarity:
            if polarity.lower() == "negative":
                expected_voltage_v = -abs(voltage_setpoint_v)
            elif polarity.lower() == "positive":
                expected_voltage_v = abs(voltage_setpoint_v)

        verification_failures = []
        for ch in channels:
            set_v = float(configured_data[ch]["set_voltage_V"])
            set_i = float(configured_data[ch]["set_current_A"])
            ramp_up = float(configured_data[ch]["ramp_up_V_per_s"])

            if abs(set_v - expected_voltage_v) > 1.0:
                verification_failures.append(
                    f"{ch.upper()}: voltage readback mismatch "
                    f"(expected {expected_voltage_v:g} V, got {set_v:g} V)"
                )

            if abs(set_i - current_limit_a) > 0.0001:
                verification_failures.append(
                    f"{ch.upper()}: current limit readback mismatch "
                    f"(expected {current_limit_a:g} A, got {set_i:g} A)"
                )

            if abs(ramp_up - ramp_rate_v_per_s) > 5.0:
                verification_failures.append(
                    f"{ch.upper()}: ramp-rate readback mismatch "
                    f"(expected {ramp_rate_v_per_s:g} V/s, got {ramp_up:g} V/s)"
                )

        if verification_failures:
            detail = "\n  - ".join(verification_failures)
            raise RuntimeError(
                "Pre-ON setting verification failed. Refusing to turn ON.\n"
                f"  - {detail}"
            )

        for ch in channels:
            self.snmpset_int(f"outputSwitch.{ch}", 1)

        data = self.read_channel_settings(
            channels,
            polarity=polarity,
            neglect_readback_polarity=neglect_readback_polarity,
        )
        return data

    def clear_events(self, channels: List[str]) -> None:
        for ch in channels:
            self.snmpset_int(f"outputSwitch.{ch}", 10)

    def turn_off_all(self, channels: List[str], emergency: bool = False) -> None:
        value = 3 if emergency else 0
        for ch in channels:
            self.snmpset_int(f"outputSwitch.{ch}", value)
