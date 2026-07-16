#!/usr/bin/env python3

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class SNMPConfig:
    ip: str
    mib_name: str = "+WIENER-CRATE-MIB"
    read_community: str = "public"
    write_community: str = "guru"
    version: str = "2c"
    timeout_s: int = 30


class IsegMPOD:
    def __init__(self, cfg: SNMPConfig):
        self.cfg = cfg

    def _run(self, args: List[str]) -> str:
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

            modules[module_id] = {
                "description": description,
                "serial_number": self._find_snapshot_value(snapshot, [
                    f"moduleSerialNumber.{module_id}",
                ]),
                "firmware_version": self._find_snapshot_value(snapshot, [
                    f"moduleFirmwareVersion.{module_id}",
                ]),
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

    def channels_by_module(self, channels: List[str]) -> Dict[str, List[str]]:
        assignments: Dict[str, List[str]] = {}
        for channel in channels:
            assignments.setdefault(self.channel_module_id(channel), []).append(channel)
        for module_id in assignments:
            assignments[module_id].sort(key=lambda channel: int(channel[1:]))
        return assignments

    def check_module_health(
        self,
        snapshot: Dict[str, str],
        allowed_module_ids: Set[str],
    ) -> bool:
        status_entries = {
            oid: value
            for oid, value in snapshot.items()
            if oid.startswith((
                "moduleStatus.",
                "moduleEventStatus.",
                "moduleEventChannelStatus.",
            ))
            and oid.rsplit(".", 1)[-1] in allowed_module_ids
        }

        if not status_entries:
            return True

        bad_keywords = [
            "moduleNeedService",
            "moduleIsInputError",
            "moduleIsEventActive",
            "moduleEventPowerFail",
            "moduleEventService",
            "moduleHardwareLimitVoltageNotGood",
            "moduleEventInputError",
            "moduleEventSafetyLoopNotGood",
            "moduleEventSupplyNotGood",
            "moduleEventTemperatureNotGood",
        ]

        combined = "\n".join(status_entries.values())
        failed = [kw for kw in bad_keywords if kw in combined]

        if failed:
            return False
        return True

    def check_channel_health(
        self, channels: List[str], snapshot: Dict[str, str]
    ) -> bool:
        all_ok = True

        for ch in channels:
            status = snapshot.get(f"outputStatus.{ch}", "MISSING")
            if status == "MISSING":
                all_ok = False
                continue

            bad_keywords = [
                "outputFailure",
                "outputEmergencyOff",
                "outputInhibit",
                "outputCurrentBoundsExceeded",
                "outputVoltageBoundsExceeded",
            ]

            if any(keyword in status for keyword in bad_keywords):
                all_ok = False

        return all_ok

    def read_channel_settings(
        self, channels: List[str], snapshot: Dict[str, str]
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
            missing = [oid for oid in required_oids.values() if oid not in snapshot]
            if missing:
                raise RuntimeError(
                    f"{ch}: missing required records from snmpwalk: {', '.join(missing)}"
                )

            values = {
                key: self.display_value(snapshot[oid])
                for key, oid in required_oids.items()
            }

            data[ch] = values

        return data

    def configure_and_turn_on(
        self,
        channels: List[str],
        voltage_setpoint_v: float = 50.0,
        current_limit_a: float = 0.001,
        ramp_rate_v_per_s: float = 100.0,
    ) -> Dict[str, Dict[str, str]]:
        for ch in channels:
            self.snmpset_int(f"outputSwitch.{ch}", 10)
            self.snmpset_float(f"outputVoltage.{ch}", voltage_setpoint_v)
            self.snmpset_float(f"outputCurrent.{ch}", current_limit_a)
            self.snmpset_float(f"outputVoltageRiseRate.{ch}", ramp_rate_v_per_s)

        configured_snapshot = self.read_all()
        configured_data = self.read_channel_settings(channels, configured_snapshot)

        for ch in channels:
            set_v = float(configured_data[ch]["set_voltage_V"])
            set_i = float(configured_data[ch]["set_current_A"])
            ramp_up = float(configured_data[ch]["ramp_up_V_per_s"])

            if abs(set_v - voltage_setpoint_v) > 1.0:
                raise RuntimeError(f"{ch}: Voltage readback mismatch. Refusing to turn ON.")

            if abs(set_i - current_limit_a) > 0.0001:
                raise RuntimeError(f"{ch}: Current limit readback mismatch. Refusing to turn ON.")

            if abs(ramp_up - ramp_rate_v_per_s) > 5.0:
                raise RuntimeError(f"{ch}: Ramp-rate readback mismatch. Refusing to turn ON.")

            self.snmpset_int(f"outputSwitch.{ch}", 1)

        enabled_snapshot = self.read_all()
        data = self.read_channel_settings(channels, enabled_snapshot)
        return data

    def clear_events(self, channels: List[str]) -> None:
        for ch in channels:
            self.snmpset_int(f"outputSwitch.{ch}", 10)

    def turn_off_all(self, channels: List[str], emergency: bool = False) -> None:
        value = 3 if emergency else 0
        for ch in channels:
            self.snmpset_int(f"outputSwitch.{ch}", value)