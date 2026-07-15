import json
import traceback
import subprocess
import os
import sys
import importlib


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
    



def main():
    test_sequence = [
        #{
        #   "name": "dune_hv_crate_test.py",
        #   "key": "dune_hv_crate_test",
        #    "module": "wiec_crate_gui",
        #    "function": "main",
        #},
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

        # {
        #     "name": "continuity_tests.py",
        #     "key": "continuity_tests",
        #     "function": WIEC_CONTINUITY_TESTS.run_continuity_tests,
        # },
    ]

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


if __name__ == "__main__":
    main()
