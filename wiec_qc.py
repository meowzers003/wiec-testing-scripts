import json
import traceback
import subprocess
import os
import sys
import importlib

import wiec_crate_gui
import wiec_output_log


RESULTS_FILE = "results.json"


def load_results():
    try:
        with open(RESULTS_FILE, "r") as jsonfile:
            return json.load(jsonfile)
    except FileNotFoundError:
        return {}


def save_results(results): # updates with edits 
    with open(RESULTS_FILE, "w") as jsonfile:
        json.dump(results, jsonfile, indent=4)


def mark_result(test_key, passed): # edits results.json
    results = load_results()
    results[test_key] = "True" if passed else "False"
    save_results(results)


def test_passed(test_key):
    results = load_results()
    return str(results.get(test_key)) == "True"



def load_function(module_name, function_name):
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def run_required_step(test_name, test_key, module_name, function_name):
    print("\n" + "=" * 70)
    print(f"Running {test_name}...")
    print("=" * 70)

    try:
        test_function = load_function(module_name, function_name)
        test_result = bool(test_function())
    except AttributeError:
        print(f"Function {function_name} not found in module {module_name}.")
        mark_result(test_key, False)
        return False
    except BaseException as exc:
        print(f"{test_name} raised an exception.")
        print(traceback.format_exc())
        mark_result(test_key, False)
        return False

    mark_result(test_key, test_result)

    if test_result:
        print(f"{test_name} passed.")
        return True

    print(f"{test_name} failed.")
    return False

def shutdown_all():
    print("\nRunning final shutdown logic...")

    try:
        ptc_power = importlib.import_module("wiec_ptc_power")
        ptc_power.shutdown_wiec()
    except BaseException:
        print("PTC shutdown raised an exception.")
        print(traceback.format_exc())

    try:
        crate_gui = importlib.import_module("wiec_crate_gui")
        crate_gui.shutdown_dune_hv_crate_test()
    except BaseException:
        print("DUNE HV crate shutdown raised an exception.")
        print(traceback.format_exc())
    

def print_prompt_section(title):
    print("\n" + "-" * 15 + f" {title} " + "-" * 15)


def prompt_run_mode():
    valid_modes = {"c": "crate", "w": "wib_femb", "b": "both"}
    while True:
        response = input(
            "Are you testing HV crate only [C], WIB-FEMB only [W], or Both [B]: "
        ).strip().lower()
        if response in valid_modes:
            return valid_modes[response]
        print("ERROR: Please enter C, W, or B.")


def prompt_wib_power_states():
    selected_wibs = {}

    while True:
        while True:
            try:
                wib_number = wiec_crate_gui.normalize_wib_number(
                    input("Enter the WIB number you want to power on/off: ")
                )
                break
            except ValueError as exc:
                print(f"ERROR: {exc}")

        while True:
            try:
                state = wiec_crate_gui.normalize_wib_power_state(
                    input(f"Enter the power state (on/off) for WIB {wib_number}: ")
                )
                break
            except ValueError as exc:
                print(f"ERROR: {exc}")

        selected_wibs[wib_number] = state

        while True:
            more = input("Do you want to power on/off more WIBs? (y/n): ").strip().lower()
            if more in ("y", "yes"):
                break
            if more in ("n", "no"):
                return selected_wibs
            print("ERROR: Please enter y or n.")


def prompt_wiec_test_info():
    print_prompt_section("WIEC QC : Test Info")
    version_number = wiec_crate_gui.prompt_required("Enter version number: ")
    tester_name = wiec_crate_gui.prompt_required("Enter name of tester: ")
    comments = wiec_crate_gui.prompt_required("Enter extra comments from test user: ")
    config_file = wiec_crate_gui.prompt_config_file()
    run_mode = prompt_run_mode()
    test_name = wiec_crate_gui.build_test_name(
        version_number=version_number,
        tester_name=tester_name,
        comments=comments,
    )

    wibs = {}
    if run_mode in ("wib_femb", "both"):
        print_prompt_section("WIB Under Test")
        wibs = prompt_wib_power_states()

    return {
        "config_file": config_file,
        "run_mode": run_mode,
        "test_name": test_name,
        "wibs": wibs,
    }


def steps_for_mode(run_mode):
    hv_crate_step = {
        "name": "dune_hv_crate_test.py",
        "key": "dune_hv_crate_test",
        "module": "wiec_crate_gui",
        "function": "main",
    }
    wib_femb_steps = [
        {
            "name": "wiec_ptc_power.py",
            "key": "ptc_setup",
            "module": "wiec_ptc_power",
            "function": "initialize_wiec",
        },
        {
            "name": "wiec_wib_setup.py",
            "key": "wib_setup",
            "module": "wiec_wib_setup",
            "function": "wib_power",
        },
        {
           "name": "femb_checkout.py",
           "key": "femb_checkout",
           "module": "wiec_femb_checkout",
           "function": "main",
        },
    ]

    if run_mode == "crate":
        return [hv_crate_step]
    if run_mode == "wib_femb":
        return wib_femb_steps
    return [hv_crate_step] + wib_femb_steps



def main():
    test_info = prompt_wiec_test_info()
    wiec_crate_gui.set_test_context(
        config_file=test_info["config_file"],
        test_name=test_info["test_name"],
        wib_power_states=test_info["wibs"],
    )
    wiec_output_log.start_output_log(test_info["test_name"])
    print(f"Selected test mode: {test_info['run_mode']}")
    print(f"Selected config file: {test_info['config_file']}")
    if test_info["wibs"]:
        print(f"Selected WIB power states: {test_info['wibs']}")
    test_sequence = steps_for_mode(test_info["run_mode"])

    try:
        for step in test_sequence:
            passed = run_required_step(
                test_name=step["name"],
                test_key=step["key"],
                module_name=step["module"],
                function_name=step["function"],
            )

            if not passed:
                print(f"\nStopping sequence because {step['name']} did not pass.")
                mark_result("full_wiec_test_sequence", False)
                return

        print("\nAll tests passed successfully!")
        mark_result("full_wiec_test_sequence", True)

    except KeyboardInterrupt:
        print("\nTest sequence interrupted by user.")
        mark_result("full_wiec_test_sequence", False)

    finally:
        shutdown_all()
        wiec_output_log.stop_output_log()


if __name__ == "__main__":
    main()
