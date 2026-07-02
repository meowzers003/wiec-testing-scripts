import json
import traceback
import subprocess
import os
import sys

import dune_hv_crate_test as DUNE_HV_CRATE_TEST
import wiec_ptc_power as WIEC_PTC_POWER
import wiec_serial as WIEC_SERIAL
import wiec_wib_setup as WIEC_SETUP
import wiec_continuity as WIEC_CONTINUITY_TESTS
import wiec_crate_gui as WIEC_CRATE_GUI
import wiec_femb_checkout as WIEC_FEMB_CHECKOUT

RESULTS_FILE = "results.json"


def load_results():
    try:
        with open(RESULTS_FILE, "r") as jsonfile:
            return json.load(jsonfile)
    except FileNotFoundError:
        return {}


def save_results(results):
    with open(RESULTS_FILE, "w") as jsonfile:
        json.dump(results, jsonfile, indent=4)


def mark_result(test_key, passed):
    results = load_results()
    results[test_key] = "True" if passed else "False"
    save_results(results)


def test_passed(test_key):
    results = load_results()
    return str(results.get(test_key)) == "True"


def run_required_step(test_name, test_key, test_function):
    # print clean header for current test
    print("\n" + "=" * 70)
    print(f"Running {test_name}...")
    print("=" * 70)

    try:
        test_function()
    except Exception:
        print(f"{test_name} raised an exception.")
        print(traceback.format_exc())
        mark_result(test_key, False)
        return False

    if test_passed(test_key):
        print(f"{test_name} passed.")
        return True

    print(f"{test_name} failed.")
    return False


def shutdown_all():
    print("\nRunning final shutdown logic...")
    WIEC_PTC_POWER.shutdown_wiec()
    



def main():
    test_sequence = [
        {
            "name": "dune_hv_crate_test.py",
            "key": "dune_hv_crate_test",
            "function": WIEC_CRATE_GUI.main,
        },
        {
            "name": "ptc_power.py",
            "key": "ptc_power",
            "function": WIEC_PTC_POWER.initialize_wiec,
        },
        ### wib_serial is just helper function for wiec ptc-wib setup. wib setup calls upon it already
        ### to login and whatnot 
        # { 
        #     "name": "wib_serial.py",
        #     "key": "wib_serial",
        #     "function": WIEC_SERIAL.main,
        # },
        {
            "name": "wib_setup.py",
            "key": "wib_setup",
            "function": WIEC_SETUP.power_wib,
        },
        # {
        #     "name": "femb_checkout.py",
        #     "key": "femb_checkout",
        #     "function": WIEC_FEMB_CHECKOUT.main,
        # },

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
                test_function=step["function"],
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