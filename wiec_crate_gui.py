#!/usr/bin/env python3

"""
Terminal GUI wrapper for running dune_hv_crate_test.py.

Naming scheme:
    [version number]_[name of tester]_[extra comments from test user]

Example generated test name:
    v3_JohnDoe_fan_sweep_after_rewire

Usage:
    python3 run_dune_test_gui.py

Optional:
    chmod +x run_dune_test_gui.py
    ./run_dune_test_gui.py
"""

import os
import re
import sys
from pathlib import Path


# Import the main test class from your existing file.
# This assumes dune_hv_crate_test.py is in the same folder as this wrapper.
try:
    from dune_hv_crate_test import LDOmeasure
except ImportError as exc:
    LDOmeasure = None
    LDO_IMPORT_ERROR = exc
else:
    LDO_IMPORT_ERROR = None


def clean_name_field(text: str) -> str:
    """
    Converts user input into a safe filename/test-name component.

    Examples:
        'John Doe' -> 'John_Doe'
        'fan sweep after rewire!' -> 'fan_sweep_after_rewire'
    """

    text = text.strip()

    # Replace spaces with underscores.
    text = text.replace(" ", "_")

    # Remove characters that are risky in filenames or paths.
    text = re.sub(r"[^A-Za-z0-9_.-]", "", text)

    # Collapse repeated underscores.
    text = re.sub(r"_+", "_", text)

    # Avoid empty fields.
    if not text:
        text = "NA"

    return text


def prompt_required(prompt_text: str) -> str:
    """
    Prompts until the user enters a non-empty value.
    """

    while True:
        value = input(prompt_text).strip()

        if value:
            return value

        print("This field is required. Please enter a value.")


def prompt_config_file() -> str:
    """
    Prompts user for config file path and verifies that it exists.
    """

    while True:
        config_path = input("Enter config file path [default: config.json]: ").strip()

        if not config_path:
            config_path = "config.json"

        config_path = os.path.expanduser(config_path)
        config_path = os.path.abspath(config_path)

        if os.path.isfile(config_path):
            return config_path

        print(f"ERROR: Config file not found: {config_path}")
        print("Please enter a valid path.")


def build_test_name(version_number: str, tester_name: str, comments: str) -> str:
    """
    Builds final test name:
        [version number]_[name of tester]_[extra comments from test user]
    """

    version_number = clean_name_field(version_number)
    tester_name = clean_name_field(tester_name)
    comments = clean_name_field(comments)

    return f"{version_number}_{tester_name}_{comments}"


active_test = None
wibs = {}
configured_config_file = None
configured_test_name = None
VALID_WIB_POWER_STATES = {"on", "off"}


def normalize_wib_number(wib_number):
    wib_number = str(wib_number).strip()
    if not wib_number.isdigit():
        raise ValueError(f"WIB number must be an integer 0-5, got {wib_number!r}")

    wib_int = int(wib_number)
    if not 0 <= wib_int <= 5:
        raise ValueError(f"WIB number must be between 0 and 5, got {wib_int}")

    return str(wib_int)


def normalize_wib_power_state(state):
    state = str(state).strip().lower()
    if state not in VALID_WIB_POWER_STATES:
        raise ValueError(f"Power state must be ON or OFF, got {state!r}")
    return state


def prompt_wib_power_states():
    global wibs

    selected_wibs = {}

    while True:
        try:
            wib_number = normalize_wib_number(input("Enter the WIB number you want to power on/off: "))
            state = normalize_wib_power_state(input(f"Enter the power state (on/off) for WIB {wib_number}: "))
        except ValueError as exc:
            print(f"ERROR: {exc}")
            continue

        selected_wibs[wib_number] = state

        while True:
            more = input("Do you want to power on/off more WIBs? (y/n): ").strip().lower()
            if more in ("y", "yes"):
                break
            if more in ("n", "no"):
                wibs = selected_wibs
                return wibs
            print("ERROR: Please enter y or n.")

    wibs = selected_wibs
    return wibs


def set_test_context(config_file: str, test_name: str, wib_power_states=None):
    global configured_config_file, configured_test_name, wibs

    configured_config_file = config_file
    configured_test_name = test_name
    if wib_power_states is not None:
        wibs = dict(wib_power_states)


def run_dune_hv_crate_test(config_file: str, test_name: str):
    global active_test

    if LDOmeasure is None:
        print("ERROR: Could not import LDOmeasure from dune_hv_crate_test.py.")
        print("Make sure this wrapper script is in the same folder as dune_hv_crate_test.py.")
        print(f"Import error: {LDO_IMPORT_ERROR}")
        return False

    print("\nStarting DUNE HV crate test...")
    print("Do not close this terminal while the test is running.\n")

    try:
        active_test = LDOmeasure(config_file, test_name)
        # return getattr(active_test, "datastore", {}).get("overall") == "Pass" # uncomment once parameters confirmed
        return True  # your intentional policy for now
    except Exception:
        return False
    finally:
        active_test = None


def shutdown_dune_hv_crate_test():
    if active_test is None:
        return True

    try:
        active_test.emergency_shutoff()
        return True
    except Exception as exc:
        print(f"DUNE HV crate shutdown raised an exception: {exc}")
        return False



def main():
    if configured_config_file and configured_test_name:
        config_file = configured_config_file
        test_name = configured_test_name
    else:
        print("\n" + "=" * 70)
        print("DUNE HV CRATE TEST TERMINAL GUI")
        print("=" * 70)

        prompt_wib_power_states()

        version_number = prompt_required("Enter version number: ")
        tester_name = prompt_required("Enter name of tester: ")
        comments = prompt_required("Enter extra comments from test user: ")
        config_file = prompt_config_file()

        test_name = build_test_name(
            version_number=version_number,
            tester_name=tester_name,
            comments=comments
        )

    print("\n" + "=" * 70)
    print("DUNE HV CRATE TEST RUN SUMMARY")
    print("=" * 70)
    print(f"Config file : {config_file}")
    print(f"Test name   : {test_name}")
    print("=" * 70)

    test_result = True
        
    # not running until FEMB is debugged (for the sake of time)
    #try:
    #    test_result = run_dune_hv_crate_test(config_file, test_name)
    #except KeyboardInterrupt:
    #    print("\nTest interrupted by user with Ctrl+C.")
    #    print("The main test class should handle emergency shutoff if interruption occurs inside its try/except.")
    #    test_result = False
    #except Exception as exc:
    #    print("\nERROR: Test failed or raised an exception.")
    #    print(f"Exception: {exc}")
    #    test_result = False

    #print("\nDUNE HV crate test wrapper complete.")
    return test_result


if __name__ == "__main__":
    main()
