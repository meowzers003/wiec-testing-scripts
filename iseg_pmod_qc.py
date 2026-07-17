#!/usr/bin/env python3

import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Tuple

from iseg_pmod_wrapper import IsegMPOD, RampVerificationError, SNMPConfig

SPREADSHEET_RESULTS_DIR = Path.cwd() / "HV Modules Test Results"
TEXT_OUTPUT_ROOT = Path.cwd() / "HV PMOD QC Output Text Files"
RAMP_WARNING_DIR = Path.cwd() / "HV PMOD QC Ramp Warnings"

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


class Tee:
    def __init__(self, *streams: TextIO):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


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


def setup_terminal_log(test_title: str = "pending_test_title") -> Tuple[TextIO, Path]:
    now = datetime.now()
    date_label = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")
    log_dir = TEXT_OUTPUT_ROOT / date_label
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{safe_filename_part(test_title)}_{timestamp}.txt"
    log_file = log_path.open("w")
    sys.stdout = Tee(sys.__stdout__, log_file)
    sys.stderr = Tee(sys.__stderr__, log_file)
    return log_file, log_path


def rename_terminal_log(log_path: Path, test_title: str) -> Path:
    timestamp = log_path.stem.rsplit("_", 1)[-1]
    final_path = log_path.with_name(f"{safe_filename_part(test_title)}_{timestamp}.txt")
    if final_path != log_path:
        log_path.rename(final_path)
    print(f"Terminal output log: {final_path}")
    return final_path


def module_csv_path(module_info: Dict[str, str]) -> Path:
    module_name = safe_filename_part(module_info.get("module_name", "iseg").lower())
    serial_number = safe_filename_part(module_info.get("serial_number", "UNKNOWN"))
    firmware_name = safe_filename_part(module_info.get("firmware_name", "UNKNOWN"))
    firmware_number = safe_filename_part(module_info.get("firmware_number", "UNKNOWN"))
    filename = f"{module_name}_{serial_number}_{firmware_name}_{firmware_number}.csv"
    return SPREADSHEET_RESULTS_DIR / filename


def module_warning_path(module_info: Dict[str, str], module_channels: List[str]) -> Path:
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    module_name = safe_filename_part(module_info.get("module_name", "iseg").lower())
    serial_number = safe_filename_part(module_info.get("serial_number", "UNKNOWN"))
    firmware_name = safe_filename_part(module_info.get("firmware_name", "UNKNOWN"))
    firmware_number = safe_filename_part(module_info.get("firmware_number", "UNKNOWN"))
    polarity = safe_filename_part(module_info.get("polarity", "UNKNOWN"))
    channel_range = safe_filename_part(format_channel_range(module_channels))
    filename = (
        f"{module_name}_{serial_number}_{firmware_name}_{firmware_number}_"
        f"{polarity}_{channel_range}_{timestamp}_warnings.txt"
    )
    return RAMP_WARNING_DIR / filename


def write_module_warnings(
    module_info: Dict[str, str],
    module_channels: List[str],
    warnings: List[str],
) -> Optional[Path]:
    if not warnings:
        return None

    RAMP_WARNING_DIR.mkdir(parents=True, exist_ok=True)
    warning_path = module_warning_path(module_info, module_channels)
    with warning_path.open("w") as warning_file:
        warning_file.write("HV module ramp warning report\n")
        warning_file.write(f"date/time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        warning_file.write(f"module name: {module_info.get('module_name', 'UNKNOWN')}\n")
        warning_file.write(f"firmware name: {module_info.get('firmware_name', 'UNKNOWN')}\n")
        warning_file.write(f"firmware number: {module_info.get('firmware_number', 'UNKNOWN')}\n")
        warning_file.write(f"serial number: {module_info.get('serial_number', 'UNKNOWN')}\n")
        warning_file.write(f"polarity: {module_info.get('polarity', 'UNKNOWN')}\n")
        warning_file.write(f"channel indices: {format_channel_list(module_channels)}\n\n")
        for index, warning in enumerate(warnings, start=1):
            warning_file.write(f"{index}. {warning}\n")

    print(f"\nSaved ramp warning report to {warning_path}")
    return warning_path


def make_readback_columns(channels: List[str]) -> List[str]:
    columns = []
    for channel_number, _ in enumerate(channels):
        for _, column_label in CHANNEL_PARAMETERS:
            columns.append(f"ch{channel_number} - {column_label}")
    return columns


def make_csv_headers(channels: List[str]) -> List[List[str]]:
    readback_columns = make_readback_columns(channels)
    leading_columns = ["test title", "date/time"]
    group_header = (
        leading_columns
        + ["initial readback"] * len(readback_columns)
        + ["final readback"] * len(readback_columns)
    )
    measurement_header = leading_columns + readback_columns + readback_columns
    return [group_header, measurement_header]


def append_readback_values(
    row: List[str],
    channels: List[str],
    channel_data: Dict[str, Dict[str, str]],
) -> None:
    for ch in channels:
        values = channel_data.get(ch, {})
        for data_key, _ in CHANNEL_PARAMETERS:
            row.append(values.get(data_key, ""))


def append_module_test_result_to_csv(
    test_title: str,
    module_info: Dict[str, str],
    channels: List[str],
    initial_data: Dict[str, Dict[str, str]],
    final_data: Dict[str, Dict[str, str]],
) -> None:
    SPREADSHEET_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [test_title, timestamp]
    append_readback_values(row, channels, initial_data)
    append_readback_values(row, channels, final_data)

    csv_path = module_csv_path(module_info)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="") as csv_file:
        writer = csv.writer(csv_file)
        if write_header:
            for header in make_csv_headers(channels):
                writer.writerow(header)
        writer.writerow(row)

    print(f"\nSaved module test result data to {csv_path}")


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


def prompt_module_readback_polarity_handling(
    module_info: Dict[str, str],
    module_channels: List[str],
) -> bool:
    serial_number = module_info.get("serial_number", "UNKNOWN")
    channel_range = format_channel_range(module_channels)
    return prompt_yes_no(
        "Neglect readback polarity and treat voltage readback magnitudes as "
        f"the user-defined polarity for ISEG SN {serial_number} ({channel_range})?",
        default=False,
    )


def prompt_module_qc_selection(
    module_info: Dict[str, str],
    module_channels: List[str],
) -> bool:
    serial_number = module_info.get("serial_number", "UNKNOWN")
    channel_range = format_channel_range(module_channels)
    return prompt_yes_no(
        f"Perform QC functionality tests on ISEG SN {serial_number} ({channel_range})?",
        default=True,
    )


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
    readback_mode = (
        "manual readback polarity"
        if module_info.get("neglect_readback_polarity", False)
        else "direct readback polarity"
    )
    title = (
        f"ISEG SN {serial_number} {polarity} "
        f"{format_channel_range(module_channels)} ({readback_mode})"
    )
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
) -> Dict[str, Any]:
    neglect_readback_polarity = module_info.get("neglect_readback_polarity", False)
    result: Dict[str, Any] = {
        "module_id": module_id,
        "serial_number": module_info.get("serial_number", "UNKNOWN"),
        "polarity": module_info.get("polarity", "UNKNOWN"),
        "neglect_readback_polarity": neglect_readback_polarity,
        "channel_range": format_channel_range(module_channels),
        "failures": [],
        "warnings": [],
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

    initial_data: Dict[str, Dict[str, str]] = {}
    final_data: Dict[str, Dict[str, str]] = {}

    print("\nInitial readback check:")
    initial_readback_ok = False
    try:
        initial_data = mpod.read_channel_settings(
            module_channels,
            polarity=module_info.get("polarity", ""),
            neglect_readback_polarity=neglect_readback_polarity,
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
            _, ramp_warnings = mpod.configure_and_turn_on(
                channels=module_channels,
                voltage_setpoint_v=DEFAULT_VOLTAGE_V,
                current_limit_a=DEFAULT_CURRENT_A,
                ramp_rate_v_per_s=DEFAULT_RAMP_V_PER_S,
                polarity=module_info.get("polarity", ""),
                neglect_readback_polarity=neglect_readback_polarity,
            )
            result["warnings"].extend(ramp_warnings)
            if ramp_warnings:
                print("  PASS with ramp warning(s):")
                print_failure_lines(ramp_warnings)
            print("  PASS: settings verified and channels turned ON.")
        except RampVerificationError as e:
            result["warnings"].extend(e.warnings)
            message = f"Voltage/current/ramp setting check failed: {e}"
            print("  FAIL:")
            print_failure_lines([message])
            record_failure(result, message)
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
        print("  PASS: final readback captured.")
    except Exception as e:
        message = f"Final readback failed: {e}"
        print(f"  FAIL: {message}")
        record_failure(result, message)

    append_module_test_result_to_csv(
        test_title,
        module_info,
        module_channels,
        initial_data,
        final_data,
    )
    write_module_warnings(module_info, module_channels, result["warnings"])

    return result


def print_final_summary(module_results: List[Dict[str, Any]]) -> None:
    print_section("Final Summary Report")
    passed = 0

    for result in module_results:
        failures = result["failures"]
        warnings = result.get("warnings", [])
        status = "PASS" if not failures else "FAIL"
        if status == "PASS":
            passed += 1

        label = (
            f"ISEG SN {result['serial_number']} "
            f"{result['polarity']} {result['channel_range']}"
        )
        readback_mode = (
            "manual readback polarity"
            if result.get("neglect_readback_polarity", False)
            else "direct readback polarity"
        )
        label = f"{label} ({readback_mode})"
        print(f"{status}: {label}")
        if failures:
            print_failure_lines(failures)
        if warnings:
            print("  WARNINGS:")
            print_failure_lines(warnings)

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
    log_file: Optional[TextIO] = None
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
        log_file, log_path = setup_terminal_log()
        test_title = input("Enter test title for CSV logging: ").strip()
        if not test_title:
            test_title = "Untitled ISEG PMOD QC Test"
        rename_terminal_log(log_path, test_title)
        print(f"Test title: {test_title}")

        initial_snapshot = mpod.read_all()
        crate_info = mpod.get_crate_info(initial_snapshot)
        display_crate_info(crate_info)

        modules = mpod.discover_iseg_modules(initial_snapshot)
        channels = mpod.discover_channels(initial_snapshot, modules)
        channel_assignments = mpod.channels_by_module(channels)

        module_count = len(modules)
        print(f"\nDiscovered {module_count} ISEG module(s).")

        module_channels_by_id: Dict[str, List[str]] = {}
        selected_module_ids: List[str] = []
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
            module_info["perform_qc"] = prompt_module_qc_selection(module_info, module_channels)
            if not module_info["perform_qc"]:
                print("Skipping QC functionality tests for this module.")
                continue

            selected_module_ids.append(module_id)
            module_info["polarity"] = prompt_module_polarity(module_info, module_channels)
            module_info["neglect_readback_polarity"] = (
                prompt_module_readback_polarity_handling(module_info, module_channels)
            )
            readback_mode = (
                "manual/user-defined polarity"
                if module_info["neglect_readback_polarity"]
                else "direct readback polarity"
            )
            print(f"Readback polarity handling for this module: {readback_mode}.")

        module_results = []
        for module_id in selected_module_ids:
            module_results.append(
                run_module_qc(
                    mpod,
                    module_id,
                    modules[module_id],
                    module_channels_by_id[module_id],
                    test_title,
                )
            )

        skipped_count = module_count - len(selected_module_ids)
        if skipped_count:
            print(f"\nSkipped QC functionality tests for {skipped_count} module(s).")

        if module_results:
            print_final_summary(module_results)
        else:
            print("\nNo modules were selected for QC functionality tests.")
            print("\nTEST COMPLETE: NO MODULES TESTED")

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

    finally:
        if log_file is not None:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            log_file.close()


if __name__ == "__main__":
    main()
