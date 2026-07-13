import json
import traceback
import subprocess
import os
import sys
import re
import time 
#### ----------------------------------------------------------------------------
import wiec_serial as WIEC_SERIAL


VALID_POWER_STATES = {"on", "off"}
WIB_IP_PREFIX = "10.73.137"
WIB_IP_LAST_OCTET_BASE = 71


def normalize_wib_number(wib_number):
    wib_number = WIEC_SERIAL.sanitize_terminal_text(wib_number)
    wib_number = str(wib_number).strip()
    if not wib_number.isdigit():
        raise ValueError(f"WIB number must be an integer 0-5, got {wib_number!r}")

    wib_int = int(wib_number)
    if not 0 <= wib_int <= 5:
        raise ValueError(f"WIB number must be between 0 and 5, got {wib_int}")

    return str(wib_int)


def normalize_power_state(state):
    state = WIEC_SERIAL.sanitize_terminal_text(state)
    state = str(state).strip().lower()
    if state not in VALID_POWER_STATES:
        raise ValueError(f"Power state must be ON or OFF, got {state!r}")
    return state


def clean_input(prompt):
    return WIEC_SERIAL.sanitize_terminal_text(input(prompt)).strip()


def i2cdetect_addresses(output):
    """
    Extract hex I2C addresses from an i2cdetect table.
    """
    addresses = set()
    for line in output.splitlines():
        match = re.match(r"\s*([0-7][0-9a-fA-F]):\s*(.*)", line)
        if not match:
            continue

        row_prefix = match.group(1)[0]
        cells = match.group(2).split()
        for cell in cells:
            if re.fullmatch(r"[0-9a-fA-F]{2}", cell):
                addresses.add(cell.lower())
            elif re.fullmatch(r"[0-9a-fA-F]", cell):
                addresses.add(f"{row_prefix}{cell.lower()}")

    return addresses


def expected_wib_address(wib_number):
    return f"7{int(wib_number):x}"


def expected_wib_ip(wib_number):
    return f"{WIB_IP_PREFIX}.{WIB_IP_LAST_OCTET_BASE + int(wib_number)}"


def ip_addresses(output):
    return set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", output))


def validate_wib_i2c_outputs(wibs, sensor_outputs):
    all_passed = True

    for wib, state in wibs.items():
        if state != "on":
            print(f"WIB {wib} is {state}; skipping WIB address check.")
            continue

        expected_address = expected_wib_address(wib)
        outputs = sensor_outputs.get(wib, {})
        detect_output = outputs.get("i2cdetect", "")
        detected_addresses = i2cdetect_addresses(detect_output)

        if expected_address in detected_addresses:
            print(f"WIB {wib} address check passed: found 0x{expected_address}.")
        else:
            print(
                f"WIB {wib} address check failed: expected 0x{expected_address}, "
                f"detected {sorted(detected_addresses)}."
            )
            all_passed = False

    return all_passed


def validate_wib_ip_outputs(wibs, power_outputs, sensor_outputs):
    all_passed = True

    for wib, state in wibs.items():
        if state != "on":
            continue

        expected_ip = expected_wib_ip(wib)
        combined_output = power_outputs.get(wib, "")
        sensor_data = sensor_outputs.get(wib, {})
        combined_output += "\n" + sensor_data.get("i2cset", "")
        combined_output += "\n" + sensor_data.get("i2cdetect", "")

        detected_ips = ip_addresses(combined_output)
        if not detected_ips:
            print(f"WIB {wib} expected IP: {expected_ip}. No IP address was found in serial output.")
            continue

        if expected_ip in detected_ips:
            print(f"WIB {wib} IP check passed: found {expected_ip}.")
        else:
            print(
                f"WIB {wib} IP check failed: expected {expected_ip}, "
                f"detected {sorted(detected_ips)}."
            )
            all_passed = False

    return all_passed


def wib_power():
    # globals so they wont initialize upon import 
    global ser, wibs
    time.sleep(100)  # wait for the Zynq to boot up and be ready for commands
    ser = WIEC_SERIAL.login()
    # userinput = input("is serial out empty?:")
    # while userinput != "yes":
    #     ser = WIEC_SERIAL.login()
    #     userinput = input("is serial out empty?:")

    time.sleep(100)  # wait for the Zynq to boot up and be ready for commands
    
    wibs = {} # key is wib number, value is power state (ON/OFF)


    # asks user the wib # of interest to power on/off
    wib_number = normalize_wib_number(clean_input("Enter the WIB number you want to power on/off: "))
    wibs[wib_number] = "off"  # Initialize with None
    state = normalize_power_state(clean_input(f"Enter the power state (on/off) for WIB {wib_number}: "))
    wibs[wib_number] = state  # Store the state in uppercase

    more = clean_input("Do you want to power on/off more WIBs? (y/n): ")
    if more.lower() == 'y':
        while True:
            wib_number = normalize_wib_number(clean_input("Enter the WIB number you want to power on/off: "))
            wibs[wib_number] = "OFF"
            state = normalize_power_state(clean_input(f"Enter the power state (on/off) for WIB {wib_number}: "))
            wibs[wib_number] = state
            more = clean_input("Do you want to power on/off more WIBs? (y/n): ")
            if more.lower() != 'y':
                break
    
    power_outputs = WIEC_SERIAL.power_wib(ser, wibs)
    print("\nPower control raw outputs:")
    for wib, output in power_outputs.items():
        print(f"\n--- WIB {wib} ---")
        print(output)

    powered_on_wibs = {wib: state for wib, state in wibs.items() if state == "on"}
    if not powered_on_wibs:
        print("No WIBs requested ON; power command completed.")
        return True

    WIEC_SERIAL.run_ecat_soft_timeout_then_i2cdetect(ser)
    sensor_outputs = WIEC_SERIAL.sensors_addr(ser, powered_on_wibs)
    print(sensor_outputs)
    i2c_passed = validate_wib_i2c_outputs(powered_on_wibs, sensor_outputs)
    ip_passed = validate_wib_ip_outputs(powered_on_wibs, power_outputs, sensor_outputs)
    return i2c_passed and ip_passed
    #return True

    # power_outputs = WIEC_SERIAL.power_wib(ser, wibs)
    # print("\nPower control outputs:")
    # for output in power_outputs:
    #     print(output)
    
    #### check what potential error messages could be later and account to handle those 




def main():
    wib_power()

    











