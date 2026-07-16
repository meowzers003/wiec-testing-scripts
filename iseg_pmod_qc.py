#!/usr/bin/env python3

import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from iseg_pmod_wrapper import IsegMPOD, SNMPConfig

RESULTS_DIR = Path.cwd() / "iseg_qc_results"

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
NEGLECT_READBACK_POLARITY = False


def print_section(title: str, border_char: str = "=") -> None:
    width = max(len(title) + 4, 56)
    border = border_char * width
    print(f"\n{border}")
    print(f"  {title}")
    print(f"{border}")


def sorted_module_ids(modules: Dict[str, Dict[str, str]]) -> List[str]:
    return sorted(modules, key=lambda item: int(item[2:]))


def display_channel(channel: str) -> str:
    return channel.upper()


def format_channel_list(channels: List[str]) -> str:
    return ", ".join(display_channel(channel) for channel in channels)


def format_channel_range(channels: List[str]) -> str:
    if not channels:
        return "no channels"

    channel_numbers = sorted(int(channel[1:]) for channel in channels)
    first_channel = channel_numbers[0]
    last_channel = channel_numbers[-1]
    if first_channel == last_channel:
        return f"U{first_channel}"
    return f"U{first_channel}-{last_channel}"


def safe_filename_part(value: str) -> str:
    value = value.strip() or "UNKNOWN"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value)


def module_csv_path(module_info: Dict[str, str]) -> Path:
    module_name = safe_filename_part(module_info.get("module_name", "iseg").lower())
    serial_number = safe_filename_part(module_info.get("serial_number", "UNKNOWN"))
    firmware_name = safe_filename_part(module_info.get("firmware_name", "UNKNOWN"))
    firmware_number = safe_filename_part(module_info.get("firmware_number", "UNKNOWN"))
    filename = f"{module_name}_{serial_number}_{firmware_name}_{firmware_number}.csv"
    return RESULTS_DIR / filename


def make_csv_header(channels: List[str]) -> List[str]:
    header = ["test title", "readback label", "date/time"]
    for channel_number, _ in enumerate(channels):
        for _, column_label in CHANNEL_PARAMETERS:
            header.append(f"ch{channel_number} - {column_label}")
    return header


def append_channel_data_to_csv(
    test_title: str,
    readback_label: str,
    module_info: Dict[str, str],
    channels: List[str],
    channel_data: Dict[str, Dict[str, str]],
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = make_csv_header(channels)
    row = [test_title, readback_label, timestamp]

    for ch in channels:
        values = channel_data.get(ch, {})
        for data_key, _ in CHANNEL_PARAMETERS:
            row.append(values.get(data_key, ""))

    csv_path = module_csv_path(module_info)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="") as csv_file:
        writer = csv.writer(csv_file)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)

    print(f"\nSaved {readback_label} data to {csv_path}")


def display_crate_info(crate_info: Dict[str, str]) -> None:
    print_section("HV Crate found")
    print("id info:")
    for label, value in crate_info.items():
        if value:
            print(f"  {label}: {value}")


def display_module_discovery_info(
    module_info: Dict[str, str],
    module_channels: List[str],
) -> None:
    title = f"ISEG module discovery: {format_channel_range(module_channels)}"
    print_section(title, border_char="-")
    print("id info:")
    print(f"  module name: {module_info.get('module_name', 'UNKNOWN')}")
    print(f"  firmware name: {module_info.get('firmware_name', 'UNKNOWN')}")
    print(f"  number of channels: {module_info.get('channel_count', 'UNKNOWN')}")
    print(f"  serial number: {module_info.get('serial_number', 'UNKNOWN')}")
    print(f"  firmware number: {module_info.get('firmware_number', 'UNKNOWN')}")
    print(f"  channel indices: {format_channel_list(module_channels)}")


def prompt_module_polarity(
    module_info: Dict[str, str],
    module_channels: List[str],
) -> str:
    serial_number = module_info.get("serial_number", "UNKNOWN")
    channel_range = format_channel_range(module_channels)

    while True:
        answer = input(
            f"Is ISEG SN {serial_number} ({channel_range}) a positive or negative power supply? "
            "[positive/negative]: "
        ).strip().lower()
        if answer in {"positive", "pos", "p", "+"}:
            return "positive"
        if answer in {"negative", "neg", "n", "-"}:
            return "negative"
        print("Please enter positive or negative.")


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    default_label = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} [{default_label}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter yes or no.")


def print_functionality_header(
    module_info: Dict[str, str],
    module_channels: List[str],
) -> None:
    serial_number = module_info.get("serial_number", "UNKNOWN")
    polarity = module_info.get("polarity", "UNKNOWN")
    title = f"ISEG SN {serial_number} {polarity} {format_channel_range(module_channels)}"
    print_section(title, border_char="-")


def print_failure_lines(failures: List[str]) -> None:
    for failure in failures:
        for line in failure.splitlines():
            print(f"  - {line}")


def record_failure(result: Dict[str, Any], message: str) -> None:
    result["failures"].append(message)


def read_module_channels(
    mpod: IsegMPOD,
    module_id: str,
    module_info: Dict[str, str],
    channel_assignments: Dict[str, List[str]],
) -> List[str]:
    expected_channels = mpod.expected_channels_for_module(module_id, module_info)
    if expected_channels:
        return expected_channels

    discovered_channels = channel_assignments.get(module_id, [])
    if discovered_channels:
        return discovered_channels
    return []


def run_module_qc(
    mpod: IsegMPOD,
    module_id: str,
    module_info: Dict[str, str],
    module_channels: List[str],
    test_title: str,
    neglect_readback_polarity: bool,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "module_id": module_id,
        "serial_number": module_info.get("serial_number", "UNKNOWN"),
        "polarity": module_info.get("polarity", "UNKNOWN"),
        "channel_range": format_channel_range(module_channels),
        "failures": [],
    }

    print_functionality_header(module_info, module_channels)

    if not module_channels:
        message = "No channel indices were assigned to this module."
        print(f"\nFAIL: {message}")
        record_failure(result, message)
        return result

    print("\nCommunication and channel hardware alarm check:")
    health_failures = mpod.channel_health_failures(module_channels)
    health_ok = not health_failures

    if health_ok:
        print("  PASS: no channel alarm conditions detected.")
    else:
        print("  FAIL: alarm/error conditions detected:")
        print_failure_lines(health_failures)
        record_failure(result, "Communication/channel hardware alarm check failed.")

    print("\nInitial readback check:")
    initial_readback_ok = False
    try:
        initial_data = mpod.read_channel_settings(
            module_channels,
            polarity=module_info.get("polarity", ""),
            neglect_readback_polarity=neglect_readback_polarity,
        )
        append_channel_data_to_csv(
            test_title,
            "initial readback",
            module_info,
            module_channels,
            initial_data,
        )
        print("  PASS: initial readback captured.")
        initial_readback_ok = True
    except Exception as e:
        message = f"Initial readback failed: {e}"
        print(f"  FAIL: {message}")
        record_failure(result, message)

    if health_ok and initial_readback_ok:
        print("\nVoltage/current/ramp setting check:")
        try:
            configured_data = mpod.configure_and_turn_on(
                channels=module_channels,
                voltage_setpoint_v=DEFAULT_VOLTAGE_V,
                current_limit_a=DEFAULT_CURRENT_A,
                ramp_rate_v_per_s=DEFAULT_RAMP_V_PER_S,
                polarity=module_info.get("polarity", ""),
                neglect_readback_polarity=neglect_readback_polarity,
            )
            append_channel_data_to_csv(
                test_title,
                "configured and turned on",
                module_info,
                module_channels,
                configured_data,
            )
            print("  PASS: settings verified and channels turned ON.")
        except Exception as e:
            message = f"Voltage/current/ramp setting check failed: {e}"
            print("  FAIL:")
            print_failure_lines([message])
            record_failure(result, message)
    else:
        print("\nVoltage/current/ramp setting check:")
        print("  SKIP: unsafe or incomplete prerequisites for HV configuration.")

    print("\nFinal readback check:")
    try:
        final_data = mpod.read_channel_settings(
            module_channels,
            polarity=module_info.get("polarity", ""),
            neglect_readback_polarity=neglect_readback_polarity,
        )
        append_channel_data_to_csv(
            test_title,
            "final readback",
            module_info,
            module_channels,
            final_data,
        )
        print("  PASS: final readback captured.")
    except Exception as e:
        message = f"Final readback failed: {e}"
        print(f"  FAIL: {message}")
        record_failure(result, message)

    return result


def print_final_summary(module_results: List[Dict[str, Any]]) -> None:
    print_section("Final Summary Report")
    passed = 0

    for result in module_results:
        failures = result["failures"]
        status = "PASS" if not failures else "FAIL"
        if status == "PASS":
            passed += 1

        label = (
            f"ISEG SN {result['serial_number']} "
            f"{result['polarity']} {result['channel_range']}"
        )
        print(f"{status}: {label}")
        if failures:
            print_failure_lines(failures)

    total = len(module_results)
    print(f"\nQC complete: {passed}/{total} module(s) passed.")

    if passed == total:
        test_result = "PASS"
    elif passed == 0:
        test_result = "FAIL (no modules completed QC successfully)"
    else:
        test_result = "FAIL (partial module QC completion)"

    print(f"\nTEST COMPLETE: {test_result}")


def main() -> None:
    global NEGLECT_READBACK_POLARITY

    ip = DEFAULT_IP
    cfg = SNMPConfig(
        ip=ip,
        read_community="public",
        write_community="guru",
        log_commands=True,
    )

    mpod = IsegMPOD(cfg)
    channels: List[str] = []

    try:
        test_title = input("Enter test title for CSV logging: ").strip()
        if not test_title:
            test_title = "Untitled ISEG PMOD QC Test"

        initial_snapshot = mpod.read_all()
        crate_info = mpod.get_crate_info(initial_snapshot)
        display_crate_info(crate_info)

        modules = mpod.discover_iseg_modules(initial_snapshot)
        channels = mpod.discover_channels(initial_snapshot, modules)
        channel_assignments = mpod.channels_by_module(channels)

        module_count = len(modules)
        print(f"\nDiscovered {module_count} ISEG module(s).")

        module_channels_by_id: Dict[str, List[str]] = {}
        for module_id in sorted_module_ids(modules):
            module_info = modules[module_id]
            module_channels = read_module_channels(
                mpod,
                module_id,
                module_info,
                channel_assignments,
            )
            module_channels_by_id[module_id] = module_channels
            display_module_discovery_info(module_info, module_channels)
            module_info["polarity"] = prompt_module_polarity(module_info, module_channels)

        NEGLECT_READBACK_POLARITY = prompt_yes_no(
            "Neglect readback polarity and treat voltage readback magnitudes as the user-defined polarity?",
            default=False,
        )
        print(
            "\nReadback polarity handling: "
            f"{'neglecting readback sign' if NEGLECT_READBACK_POLARITY else 'using readback sign directly'}."
        )

        module_results = []
        for module_id in sorted_module_ids(modules):
            module_results.append(
                run_module_qc(
                    mpod,
                    module_id,
                    modules[module_id],
                    module_channels_by_id[module_id],
                    test_title,
                    NEGLECT_READBACK_POLARITY,
                )
            )

        print_final_summary(module_results)

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
