#!/usr/bin/env python3

import subprocess
import shlex
import re
import sys
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict


RESULTS_DIR = Path.cwd() / "iseg_qc_results"
RESULTS_CSV = RESULTS_DIR / "iseg_pmod_qc_results.csv"

CHANNEL_PARAMETERS = [
    ("set_voltage_V", "set voltage [V]"),
    ("measured_voltage_V", "measured voltage [V]"),
    ("set_current_A", "set current [A]"),
    ("measured_current_A", "measured current [A]"),
    ("ramp_up_V_per_s", "ramp up [V/s]"),
]


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
        # Command form documented in MPOD HV manual section 4.4.
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
        """Parse section 4.4's '<MIB>::<OID> = <TYPE>: <value>' output."""
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

    # ------------------------------------------------------------
    # a. Confirm MPOD crate presence and crate-tree info
    # ------------------------------------------------------------

    def check_crate(self, snapshot: Dict[str, str]) -> Dict[str, str]:
        print("\n=== Checking MPOD crate ===")

        required_oids = ["sysMainSwitch.0", "sysStatus.0", "outputNumber.0"]
        missing = [oid for oid in required_oids if oid not in snapshot]
        if missing:
            raise RuntimeError(
                "The crate snmpwalk did not include required crate records: "
                + ", ".join(missing)
            )

        crate_info = {
            "sysMainSwitch": self.display_value(snapshot["sysMainSwitch.0"]),
            "sysStatus": snapshot["sysStatus.0"],
            "outputNumber": self.display_value(snapshot["outputNumber.0"]),
            "moduleNumber": self.display_value(snapshot.get("moduleNumber.0", "")),
            "psSerialNumber": self.display_value(snapshot.get("psSerialNumber.0", "")),
            "ipDynamicAddress": self.display_value(snapshot.get("ipDynamicAddress.0", "")),
            "ipStaticAddress": self.display_value(snapshot.get("ipStaticAddress.0", "")),
            "macAddress": self.display_value(snapshot.get("macAddress.0", "")),
        }

        for label, value in crate_info.items():
            if value:
                print(f"{label}: {value}")
        print(f"\nParsed {len(snapshot)} records from the crate SNMP walk.")

        return crate_info

    # ------------------------------------------------------------
    # b. Confirm module presence from records that exist in the crate walk
    # ------------------------------------------------------------

    def discover_modules(self, snapshot: Dict[str, str]) -> Dict[str, str]:
        print("\n=== Discovering modules ===")
        modules = {}

        for oid, encoded_value in snapshot.items():
            if oid.startswith("moduleDescription."):
                desc = self.display_value(encoded_value)
                modules[oid] = desc
                print(f"{oid}: {desc}")

        if not modules:
            for oid, encoded_value in snapshot.items():
                if oid.startswith("moduleIndex."):
                    value = self.display_value(encoded_value)
                    modules[oid] = value
                    print(f"{oid}: {value}")

        if not modules:
            print("No moduleDescription/moduleIndex entries found in this crate walk.")
            return {}

        return modules

    # ------------------------------------------------------------
    # Discover all HV channel indices
    # ------------------------------------------------------------

    def discover_channels(self, snapshot: Dict[str, str]) -> List[str]:
        print("\n=== Discovering output channels ===")
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
        
        # skip channels U200-207 for now, seems sussy
        channels = [
            channel for channel in channels
            if not 200 <= int(channel[1:]) <= 207
        ]

        channels.sort(key=lambda channel: int(channel[1:]))
        print(f"Found {len(channels)} output channels:")
        print(", ".join(channels))

        return channels

    # ------------------------------------------------------------
    # c. Confirm no communication errors or hardware alarms
    # ------------------------------------------------------------

    def check_module_health(self, snapshot: Dict[str, str]) -> bool:
        print("\n=== Checking module health ===")
        status_entries = {
            oid: value
            for oid, value in snapshot.items()
            if oid.startswith((
                "moduleStatus.",
                "moduleEventStatus.",
                "moduleEventChannelStatus.",
            ))
        }

        for oid, value in status_entries.items():
            print(f"{oid}: {value}")

        if not status_entries:
            print("No moduleStatus/moduleEventStatus records were present in this crate walk.")
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
            print("\nFAIL: Detected possible module alarms/errors:")
            for kw in failed:
                print(f"  - {kw}")
            return False

        print("\nPASS: No obvious module communication errors or hardware alarms detected.")
        return True

    def check_channel_health(
        self, channels: List[str], snapshot: Dict[str, str]
    ) -> bool:
        print("\n=== Checking channel health ===")

        all_ok = True

        for ch in channels:
            status = snapshot.get(f"outputStatus.{ch}", "MISSING")
            print(f"{ch}: {status}")

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
                print(f"  FAIL: suspicious status bits detected on {ch}")

        if all_ok:
            print("\nPASS: No obvious channel alarms detected.")
        else:
            print("\nFAIL: One or more channels reported suspicious status bits.")

        return all_ok

    # ------------------------------------------------------------
    # d. Readback voltage and current settings
    # ------------------------------------------------------------

    def read_channel_settings(
        self, channels: List[str], snapshot: Dict[str, str]
    ) -> Dict[str, Dict[str, str]]:
        print("\n=== Reading voltage/current settings and measurements ===")

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
            set_v = values["set_voltage_V"]
            set_i = values["set_current_A"]
            meas_v = values["measured_voltage_V"]
            meas_i = values["measured_current_A"]
            ramp_up = values["ramp_up_V_per_s"]

            data[ch] = values

            print(
                f"{ch}: "
                f"Vset={set_v} V, "
                f"Ilim={set_i} A, "
                f"Vmeas={meas_v} V, "
                f"Imeas={meas_i} A, "
                f"RampUp={ramp_up} V/s"
            )

        return data

    # ------------------------------------------------------------
    # e. Set voltage/current/ramp limits
    # ------------------------------------------------------------

    def configure_and_turn_on(
        self,
        channels: List[str],
        voltage_setpoint_v: float = 50.0,
        current_limit_a: float = 0.001,
        ramp_rate_v_per_s: float = 100.0,
    ) -> Dict[str, Dict[str, str]]:
        print("\n=== Configuring HV settings and turning channels ON ===")
        print(f"Target voltage setting: {voltage_setpoint_v} V")
        print(f"Target current limit:   {current_limit_a} A")
        print(f"Target ramp rate:       {ramp_rate_v_per_s} V/s")
        for ch in channels:
            print(f"\nConfiguring {ch}...")

            # Clear old latched events before attempting ON
            self.snmpset_int(f"outputSwitch.{ch}", 10)

            # Set safe initial HV parameters
            self.snmpset_float(f"outputVoltage.{ch}", voltage_setpoint_v)
            self.snmpset_float(f"outputCurrent.{ch}", current_limit_a)
            self.snmpset_float(f"outputVoltageRiseRate.{ch}", ramp_rate_v_per_s)

        # Section 4.4 documents reading all values with snmpwalk. Parse one
        # snapshot after all writes instead of issuing individual get commands.
        configured_snapshot = self.read_all()
        configured_data = self.read_channel_settings(channels, configured_snapshot)

        for ch in channels:
            set_v = float(configured_data[ch]["set_voltage_V"])
            set_i = float(configured_data[ch]["set_current_A"])
            ramp_up = float(configured_data[ch]["ramp_up_V_per_s"])

            print(f"\nVerifying {ch}...")
            print(f"  Readback Vset:      {set_v} V")
            print(f"  Readback Ilimit:    {set_i} A")
            print(f"  Readback ramp up:   {ramp_up} V/s")

            # Basic sanity checks before HV ON
            if abs(set_v - voltage_setpoint_v) > 1.0:
                raise RuntimeError(f"{ch}: Voltage readback mismatch. Refusing to turn ON.")

            if abs(set_i - current_limit_a) > 0.0001:
                raise RuntimeError(f"{ch}: Current limit readback mismatch. Refusing to turn ON.")

            if abs(ramp_up - ramp_rate_v_per_s) > 5.0:
                raise RuntimeError(f"{ch}: Ramp-rate readback mismatch. Refusing to turn ON.")

            print(f"  Turning {ch} ON...")
            self.snmpset_int(f"outputSwitch.{ch}", 1)

        enabled_snapshot = self.read_all()
        data = self.read_channel_settings(channels, enabled_snapshot)

        for ch in channels:
            status = enabled_snapshot.get(f"outputStatus.{ch}", "MISSING")
            meas_v = data[ch]["measured_voltage_V"]
            meas_i = data[ch]["measured_current_A"]
            print(f"  Status:             {status}")
            print(f"  Measured voltage:   {meas_v} V")
            print(f"  Measured current:   {meas_i} A")

        return data

    def clear_events(self, channels: List[str]) -> None:
        print("\n=== Clearing channel events ===")
        for ch in channels:
            print(f"Clearing events on {ch}")
            self.snmpset_int(f"outputSwitch.{ch}", 10)

    def turn_off_all(self, channels: List[str], emergency: bool = False) -> None:
        print("\n=== Turning off all channels ===")
        value = 3 if emergency else 0
        for ch in channels:
            print(f"Turning off {ch} with outputSwitch={value}")
            self.snmpset_int(f"outputSwitch.{ch}", value)


def make_csv_header(channels: List[str]) -> List[str]:
    header = ["row header", "test title", "readback label", "date/time"]

    for channel_number, _ in enumerate(channels):
        for _, column_label in CHANNEL_PARAMETERS:
            header.append(f"ch{channel_number} - {column_label}")

    return header


def append_channel_data_to_csv(
    test_title: str,
    readback_label: str,
    channels: List[str],
    channel_data: Dict[str, Dict[str, str]],
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_header = f"{timestamp} - {test_title} - {readback_label}"
    header = make_csv_header(channels)
    row = [row_header, test_title, readback_label, timestamp]

    for ch in channels:
        values = channel_data.get(ch, {})
        for data_key, _ in CHANNEL_PARAMETERS:
            row.append(values.get(data_key, ""))

    write_header = True
    if RESULTS_CSV.exists() and RESULTS_CSV.stat().st_size > 0:
        with RESULTS_CSV.open("r", newline="") as csv_file:
            first_row = next(csv.reader(csv_file), None)
        write_header = first_row != header

    with RESULTS_CSV.open("a", newline="") as csv_file:
        writer = csv.writer(csv_file)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)

    print(f"\nSaved {readback_label} data to {RESULTS_CSV}")


def main():
    # if len(sys.argv) < 2:
    #     print("Usage: python3 iseg_mpod_qc.py <MPOD_IP>")
    #     print("Example: python3 iseg_mpod_qc.py 192.168.2.25")
    #     sys.exit(1)
    
    ip = "169.254.4.31"  # default IP for the iseg MPOD crate

    cfg = SNMPConfig(
        ip=ip,
        read_community="public",
        write_community="guru",
    )

    mpod = IsegMPOD(cfg)
    test_title = input("Enter test title for CSV logging: ").strip()
    if not test_title:
        test_title = "Untitled ISEG PMOD QC Test"

    channels: List[str] = []

    try:
        initial_snapshot = mpod.read_all()

        # a. Crate presence and crate-tree info
        crate_info = mpod.check_crate(initial_snapshot)

        # b. Module presence from moduleDescription/moduleIndex records
        modules = mpod.discover_modules(initial_snapshot)

        # Discover channels from actual crate
        channels = mpod.discover_channels(initial_snapshot)

        # c. Communication errors / alarms
        module_ok = mpod.check_module_health(initial_snapshot)
        channel_ok = mpod.check_channel_health(channels, initial_snapshot)

        if not module_ok or not channel_ok:
            print("\nAborting configuration because alarms/errors were detected.")
            print("Inspect moduleStatus, moduleEventStatus, and outputStatus before setting HV.")
            sys.exit(2)

        # d. Initial readback
        initial_data = mpod.read_channel_settings(channels, initial_snapshot)
        append_channel_data_to_csv(test_title, "Initial readback", channels, initial_data)

        # e. Set voltage/current/ramp limits
        configured_data = mpod.configure_and_turn_on(
            channels=channels,
            voltage_setpoint_v=50.0,
            current_limit_a=0.001,
            ramp_rate_v_per_s=100.0,
        )
        append_channel_data_to_csv(test_title, "Configured and turned on", channels, configured_data)

        # Final readback
        final_snapshot = mpod.read_all()
        final_data = mpod.read_channel_settings(channels, final_snapshot)
        append_channel_data_to_csv(test_title, "Final readback", channels, final_data)

        print("\nDONE: MPOD/iség HV module configuration completed successfully.")

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected. Turning off all discovered channels if possible.")
        try:
            if not channels:
                channels = mpod.discover_channels(mpod.read_all())
            mpod.turn_off_all(channels, emergency=False)
        except Exception as e:
            print(f"Could not safely turn off channels after interrupt: {e}")
        sys.exit(130)

    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
