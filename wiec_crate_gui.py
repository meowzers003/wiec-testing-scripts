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
    print("ERROR: Could not import LDOmeasure from dune_hv_crate_test.py.")
    print("Make sure this wrapper script is in the same folder as dune_hv_crate_test.py.")
    print(f"Import error: {exc}")
    sys.exit(1)


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


def confirm_before_run(config_file: str, test_name: str) -> bool:
    """
    Shows summary and asks user to confirm before starting hardware test.
    """

    print("\n" + "=" * 70)
    print("DUNE HV CRATE TEST RUN SUMMARY")
    print("=" * 70)
    print(f"Config file : {config_file}")
    print(f"Test name   : {test_name}")
    print("=" * 70)

    while True:
        answer = input("Start test now? [y/n]: ").strip().lower()

        if answer in ("y", "yes"):
            return True

        if answer in ("n", "no"):
            return False

        print("Please enter y or n.")


def run_dune_hv_crate_test(config_file: str, test_name: str):
    """
    Calls the existing DUNE HV crate test class.
    Creating LDOmeasure starts the test sequence.
    """

    print("\nStarting DUNE HV crate test...")
    print("Do not close this terminal while the test is running.\n")

    try:
        test = LDOmeasure(config_file, test_name)
    except Exception:
        return False
    
    return getattr(test, "datastore", {}).get("overall") == "Pass"

def shutdown_dune_hv_crate_test():
    LDOmeasure("None", "None", True)


def main():
    print("\n" + "=" * 70)
    print("DUNE HV CRATE TEST TERMINAL GUI")
    print("=" * 70)

    version_number = prompt_required("Enter version number: ")
    tester_name = prompt_required("Enter name of tester: ")
    comments = prompt_required("Enter extra comments from test user: ")
    config_file = prompt_config_file()

    test_name = build_test_name(
        version_number=version_number,
        tester_name=tester_name,
        comments=comments
    )

    should_run = confirm_before_run(
        config_file=config_file,
        test_name=test_name
    )

    if not should_run:
        print("Test cancelled by user.")
        sys.exit(0)

    try:
        run_dune_hv_crate_test(config_file, test_name)
    except KeyboardInterrupt:
        print("\nTest interrupted by user with Ctrl+C.")
        print("The main test class should handle emergency shutoff if interruption occurs inside its try/except.")
        sys.exit(130)
    except Exception as exc:
        print("\nERROR: Test failed or raised an exception.")
        print(f"Exception: {exc}")
        raise

    print("\nDUNE HV crate test wrapper complete.")
    return True


if __name__ == "__main__":
    main()