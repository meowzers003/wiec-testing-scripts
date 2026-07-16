#!/usr/bin/env python3

import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from iseg_pmod_wrapper import IsegMPOD, SNMPConfig

RESULTS_DIR = Path.cwd() / "iseg_qc_results"
RESULTS_CSV = RESULTS_DIR / "iseg_pmod_qc_results.csv"

CHANNEL_PARAMETERS = [
    ("set_voltage_V", "set voltage [V]"),
    ("measured_voltage_V", "measured voltage [V]"),
    ("set_current_A", "set current [A]"),
    ("measured_current_A", "measured current [A]"),
    ("ramp_up_V_per_s", "ramp up [V/s]"),
]

DEFAULT_VOLTAGE_V = 2000.0
DEFAULT_CURRENT_A = 0.001
DEFAULT_RAMP_V_PER_S = 100.0
DEFAULT_IP = "169.254.4.31"


def print_section(title: str) -> None:
    width = max(len(title) + 4, 56)
    border = "=" * width
    print(f"\n{border}")
    print(f"  {title}")
    print(f"{border}")


def print_module_header(module_id: str) -> None:
    title = f"HV module {module_id}"
    width = max(len(title) + 4, 50)
    border = "-" * width
    print(f"\n{border}")
    print(f"  {title}")
    print(f"{border}")


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

    write_header = not RESULTS_CSV.exists() or RESULTS_CSV.stat().st_size == 0
    with RESULTS_CSV.open("a", newline="") as csv_file:
        writer = csv.writer(csv_file)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)

    print(f"\nSaved {readback_label} data to {RESULTS_CSV}")


def display_crate_info(crate_info: Dict[str, str]) -> None:
    print_section("HV Crate found")
    print("id info:")
    for label, value in crate_info.items():
        if value:
            print(f"  {label}: {value}")


def display_module_info(module_id: str, module_info: Dict[str, str]) -> None:
    print_module_header(module_id)
    print("id info:")
    print(f"  description: {module_info.get('description', 'UNKNOWN')}")
    serial_number = module_info.get("serial_number") or "UNKNOWN"
    firmware_version = module_info.get("firmware_version") or "UNKNOWN"
    print(f"  serial number: {serial_number}")
    print(f"  firmware version: {firmware_version}")


def run_module_qc(
    mpod: IsegMPOD,
    module_id: str,
    module_info: Dict[str, str],
    module_channels: List[str],
    test_title: str,
) -> bool:
    display_module_info(module_id, module_info)

    if not module_channels:
        print(f"\nNo channels assigned to {module_id}. Skipping QC for this module.")
        return False

    module_snapshot = mpod.read_all()

    module_ok = mpod.check_module_health(module_snapshot, {module_id})
    channel_ok = mpod.check_channel_health(module_channels, module_snapshot)

    if not module_ok or not channel_ok:
        print("\nSkipping configuration because alarms/errors were detected.")
        return False

    initial_data = mpod.read_channel_settings(module_channels, module_snapshot)
    append_channel_data_to_csv(test_title, f"{module_id} initial readback", module_channels, initial_data)

    configured_data = mpod.configure_and_turn_on(
        channels=module_channels,
        voltage_setpoint_v=DEFAULT_VOLTAGE_V,
        current_limit_a=DEFAULT_CURRENT_A,
        ramp_rate_v_per_s=DEFAULT_RAMP_V_PER_S,
    )
    append_channel_data_to_csv(test_title, f"{module_id} configured and turned on", module_channels, configured_data)

    final_snapshot = mpod.read_all()
    final_data = mpod.read_channel_settings(module_channels, final_snapshot)
    append_channel_data_to_csv(test_title, f"{module_id} final readback", module_channels, final_data)

    return True

def main():
    ip = DEFAULT_IP
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
    module_qc_passed = 0

    try:
        initial_snapshot = mpod.read_all()
        crate_info = mpod.get_crate_info(initial_snapshot)
        display_crate_info(crate_info)

        modules = mpod.discover_iseg_modules(initial_snapshot)
        channels = mpod.discover_channels(initial_snapshot, modules)
        channel_assignments = mpod.channels_by_module(channels)

        if not modules:
            raise RuntimeError("No ISEG modules were discovered in the crate.")

        module_count = len(modules)
        print(f"\nDiscovered {module_count} ISEG module(s).")

        for module_id in sorted(modules, key=lambda item: int(item[2:])):
            module_channels = channel_assignments.get(module_id, [])
            try:
                if run_module_qc(mpod, module_id, modules[module_id], module_channels, test_title):
                    module_qc_passed += 1
            except Exception as e:
                print(f"\n{module_id}: unexpected error during QC: {e}")
                continue

        print(f"\nQC complete: {module_qc_passed}/{module_count} module(s) completed successfully.")

        if module_qc_passed == module_count:
            test_result = "PASS"
        elif module_qc_passed == 0:
            test_result = "FAIL (no modules completed QC successfully)"
        else:
            test_result = "FAIL (partial module QC completion)"

        print(f"\nTEST COMPLETE: {test_result}")
        return

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected. Turning off all discovered channels if possible.")
        try:
            if not channels:
                shutdown_snapshot = mpod.read_all()
                shutdown_modules = mpod.discover_iseg_modules(shutdown_snapshot)
                channels = mpod.discover_channels(shutdown_snapshot, shutdown_modules)
            mpod.turn_off_all(channels, emergency=False)
        except Exception as e:
            print(f"Could not safely turn off channels after interrupt: {e}")
        print("\nTEST COMPLETE: FAIL (interrupted)")
        sys.exit(130)

    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nTEST COMPLETE: FAIL (exception)")
        sys.exit(1)

if __name__ == "__main__":
    main()
