#!/usr/bin/env python3

import subprocess
import shlex
import re
import sys
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


RESULTS_DIR = Path.cwd() / "iseg_qc_results"
RESULTS_CSV = RESULTS_DIR / "iseg_pmod_qc_results.csv"

CHANNEL_PARAMETERS = [
    ("set_voltage_V", "set voltage [V]"),
    ("measured_voltage_V", "measured voltage [V]"),
    ("set_current_A", "set current [A]"),
    ("measured_current_A", "measured current [A]"),
    ("ramp_up_V_per_s", "ramp up [V/s]"),
    ("ramp_down_V_per_s", "ramp down [V/s]"),
]


@dataclass
class SNMPConfig:
    ip: str
    mib_path: str = "/usr/share/snmp/mibs"
    mib_name: str = "+WIENER-CRATE-MIB"
    read_community: str = "public"
    write_community: str = "guru"
    version: str = "2c"
    timeout_s: int = 5


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

    def snmpget(self, oid: str, community: Optional[str] = None, quiet: bool = True) -> str:
        community = community or self.cfg.read_community
        args = [
            "snmpget",
            "-v", self.cfg.version,
            "-M", self.cfg.mib_path,
            "-m", self.cfg.mib_name,
            "-c", community,
        ]
        if quiet:
            args.append("-OqvU")
        args += [self.cfg.ip, oid]
        return self._run(args)

    def snmpwalk(self, oid: str, community: Optional[str] = None, quiet: bool = False) -> str:
        community = community or self.cfg.read_community
        args = [
            "snmpwalk",
            "-v", self.cfg.version,
            "-M", self.cfg.mib_path,
            "-m", self.cfg.mib_name,
            "-c", community,
        ]
        if quiet:
            args.append("-OqvU")
        args += [self.cfg.ip, oid]
        return self._run(args)

    def snmpset_float(self, oid: str, value: float) -> str:
        return self._run([
            "snmpset",
            "-OqvU",
            "-v", self.cfg.version,
            "-M", self.cfg.mib_path,
            "-m", self.cfg.mib_name,
            "-c", self.cfg.write_community,
            self.cfg.ip,
            oid,
            "F",
            str(value),
        ])

    def snmpset_int(self, oid: str, value: int) -> str:
        return self._run([
            "snmpset",
            "-OqvU",
            "-v", self.cfg.version,
            "-M", self.cfg.mib_path,
            "-m", self.cfg.mib_name,
            "-c", self.cfg.write_community,
            self.cfg.ip,
            oid,
            "i",
            str(value),
        ])

    # ------------------------------------------------------------
    # a. Confirm MPOD crate presence and firmware info
    # ------------------------------------------------------------

    def check_crate(self) -> Dict[str, str]:
        print("\n=== Checking MPOD crate ===")

        # Basic identity
        sys_descr = self.snmpget("sysDescr.0", quiet=False)

        # Full crate walk confirms SNMP presence
        crate_tree = self.snmpwalk("crate", quiet=False)

        print("sysDescr:")
        print(sys_descr)
        print("\nCrate SNMP tree successfully read.")

        return {
            "sysDescr": sys_descr,
            "crate_tree_present": "True" if crate_tree else "False",
        }

    # ------------------------------------------------------------
    # b. Confirm HV module presence: serial number, firmware number
    # ------------------------------------------------------------

    def discover_modules(self) -> Dict[str, str]:
        print("\n=== Discovering modules ===")

        raw = self.snmpwalk("moduleDescription", quiet=False)
        modules = {}

        for line in raw.splitlines():
            # Example form:
            # WIENER-CRATE-MIB::moduleDescription.ma2 = STRING: "iseg ..."
            if "moduleDescription" in line:
                left, _, right = line.partition("=")
                oid = left.strip().split("::")[-1].strip()
                desc = right.strip()
                modules[oid] = desc
                print(f"{oid}: {desc}")

        if not modules:
            raise RuntimeError("No moduleDescription entries found. HV module may not be detected.")

        return modules

    # ------------------------------------------------------------
    # Discover all HV channel indices
    # ------------------------------------------------------------

    def discover_channels(self) -> List[str]:
        print("\n=== Discovering output channels ===")

        raw = self.snmpwalk("outputName", quiet=False)
        channels = []

        for line in raw.splitlines():
            # Example:
            # WIENER-CRATE-MIB::outputName.u100 = STRING: U100
            match = re.search(r"outputName\.(u\d+)", line)
            if match:
                channels.append(match.group(1))

        if not channels:
            raise RuntimeError("No output channels found from outputName walk.")

        print(f"Found {len(channels)} output channels:")
        print(", ".join(channels))

        return channels

    # ------------------------------------------------------------
    # c. Confirm no communication errors or hardware alarms
    # ------------------------------------------------------------

    def check_module_health(self) -> bool:
        print("\n=== Checking module health ===")

        module_status_raw = self.snmpwalk("moduleStatus", quiet=False)
        module_event_raw = self.snmpwalk("moduleEventStatus", quiet=False)
        module_event_channel_raw = self.snmpwalk("moduleEventChannelStatus", quiet=False)

        print("\nmoduleStatus:")
        print(module_status_raw)

        print("\nmoduleEventStatus:")
        print(module_event_raw)

        print("\nmoduleEventChannelStatus:")
        print(module_event_channel_raw)

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

        combined = "\n".join([module_status_raw, module_event_raw, module_event_channel_raw])

        failed = [kw for kw in bad_keywords if kw in combined]

        if failed:
            print("\nFAIL: Detected possible module alarms/errors:")
            for kw in failed:
                print(f"  - {kw}")
            return False

        print("\nPASS: No obvious module communication errors or hardware alarms detected.")
        return True

    def check_channel_health(self, channels: List[str]) -> bool:
        print("\n=== Checking channel health ===")

        all_ok = True

        for ch in channels:
            status = self.snmpget(f"outputStatus.{ch}", quiet=False)
            print(f"{ch}: {status}")

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

    def read_channel_settings(self, channels: List[str]) -> Dict[str, Dict[str, str]]:
        print("\n=== Reading voltage/current settings and measurements ===")

        data = {}

        for ch in channels:
            set_v = self.snmpget(f"outputVoltage.{ch}")
            set_i = self.snmpget(f"outputCurrent.{ch}")
            meas_v = self.snmpget(f"outputMeasurementTerminalVoltage.{ch}")
            meas_i = self.snmpget(f"outputMeasurementCurrent.{ch}")
            ramp_up = self.snmpget(f"outputVoltageRiseRate.{ch}")
            ramp_down = self.snmpget(f"outputVoltageFallRate.{ch}")

            data[ch] = {
                "set_voltage_V": set_v,
                "set_current_A": set_i,
                "measured_voltage_V": meas_v,
                "measured_current_A": meas_i,
                "ramp_up_V_per_s": ramp_up,
                "ramp_down_V_per_s": ramp_down,
            }

            print(
                f"{ch}: "
                f"Vset={set_v} V, "
                f"Ilim={set_i} A, "
                f"Vmeas={meas_v} V, "
                f"Imeas={meas_i} A, "
                f"RampUp={ramp_up} V/s, "
                f"RampDown={ramp_down} V/s"
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
        also_set_fall_rate: bool = True,
    ) -> Dict[str, Dict[str, str]]:
        print("\n=== Configuring HV settings and turning channels ON ===")
        print(f"Target voltage setting: {voltage_setpoint_v} V")
        print(f"Target current limit:   {current_limit_a} A")
        print(f"Target ramp rate:       {ramp_rate_v_per_s} V/s")
        data = {}

        for ch in channels:
            print(f"\nConfiguring {ch}...")

            # Clear old latched events before attempting ON
            self.snmpset_int(f"outputSwitch.{ch}", 10)

            # Set safe initial HV parameters
            self.snmpset_float(f"outputVoltage.{ch}", voltage_setpoint_v)
            self.snmpset_float(f"outputCurrent.{ch}", current_limit_a)
            self.snmpset_float(f"outputVoltageRiseRate.{ch}", ramp_rate_v_per_s)

            if also_set_fall_rate:
                self.snmpset_float(f"outputVoltageFallRate.{ch}", ramp_rate_v_per_s)

            # Read back before enabling output
            set_v = float(self.snmpget(f"outputVoltage.{ch}"))
            set_i = float(self.snmpget(f"outputCurrent.{ch}"))
            ramp_up = float(self.snmpget(f"outputVoltageRiseRate.{ch}"))
            ramp_down = float(self.snmpget(f"outputVoltageFallRate.{ch}"))

            print(f"  Readback Vset:      {set_v} V")
            print(f"  Readback Ilimit:    {set_i} A")
            print(f"  Readback ramp up:   {ramp_up} V/s")
            print(f"  Readback ramp down: {ramp_down} V/s")

            # Basic sanity checks before HV ON
            if abs(set_v - voltage_setpoint_v) > 1.0:
                raise RuntimeError(f"{ch}: Voltage readback mismatch. Refusing to turn ON.")

            if abs(set_i - current_limit_a) > 0.0001:
                raise RuntimeError(f"{ch}: Current limit readback mismatch. Refusing to turn ON.")

            if abs(ramp_up - ramp_rate_v_per_s) > 5.0:
                raise RuntimeError(f"{ch}: Ramp-rate readback mismatch. Refusing to turn ON.")

            # Turn HV output ON
            print(f"  Turning {ch} ON...")
            self.snmpset_int(f"outputSwitch.{ch}", 1)

            # Verify ON / ramping / status
            status = self.snmpget(f"outputStatus.{ch}", quiet=False)
            meas_v = self.snmpget(f"outputMeasurementTerminalVoltage.{ch}")
            meas_i = self.snmpget(f"outputMeasurementCurrent.{ch}")

            data[ch] = {
                "set_voltage_V": set_v,
                "set_current_A": set_i,
                "measured_voltage_V": meas_v,
                "measured_current_A": meas_i,
                "ramp_up_V_per_s": ramp_up,
                "ramp_down_V_per_s": ramp_down,
            }

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
        mib_path="/usr/share/snmp/mibs",
        read_community="public",
        write_community="guru",
    )

    mpod = IsegMPOD(cfg)
    test_title = input("Enter test title for CSV logging: ").strip()
    if not test_title:
        test_title = "Untitled ISEG PMOD QC Test"

    try:
        # a. Crate presence and firmware
        crate_info = mpod.check_crate()

        # b. HV module presence, serial number, firmware
        modules = mpod.discover_modules()

        # Discover channels from actual crate
        channels = mpod.discover_channels()

        # c. Communication errors / alarms
        module_ok = mpod.check_module_health()
        channel_ok = mpod.check_channel_health(channels)

        if not module_ok or not channel_ok:
            print("\nAborting configuration because alarms/errors were detected.")
            print("Inspect moduleStatus, moduleEventStatus, and outputStatus before setting HV.")
            sys.exit(2)

        # d. Initial readback
        initial_data = mpod.read_channel_settings(channels)
        append_channel_data_to_csv(test_title, "Initial readback", channels, initial_data)

        # e. Set voltage/current/ramp limits
        configured_data = mpod.configure_and_turn_on(
            channels=channels,
            voltage_setpoint_v=50.0,
            current_limit_a=0.001,
            ramp_rate_v_per_s=100.0,
            also_set_fall_rate=True,
        )
        append_channel_data_to_csv(test_title, "Configured and turned on", channels, configured_data)

        # Final readback
        final_data = mpod.read_channel_settings(channels)
        append_channel_data_to_csv(test_title, "Final readback", channels, final_data)

        print("\nDONE: MPOD/iség HV module configuration completed successfully.")

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected. Turning off all discovered channels if possible.")
        try:
            channels = mpod.discover_channels()
            mpod.turn_off_all(channels, emergency=False)
        except Exception as e:
            print(f"Could not safely turn off channels after interrupt: {e}")
        sys.exit(130)

    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
