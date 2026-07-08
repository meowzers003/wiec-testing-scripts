import json
import traceback
import subprocess
import os
import sys

#### ----------------------------------------------------------------------------
import wiec_serial as WIEC_SERIAL


ser = WIEC_SERIAL.login()

wibs = {} # key is wib number, value is power state (ON/OFF)

def wib_power():
    # asks user the wib # of interest to power on/off

    wib_number = input("Enter the WIB number you want to power on/off: ")
    wibs[wib_number] = "OFF"  # Initialize with None
    state = input(f"Enter the power state (ON/OFF) for WIB {wib_number}: ")
    wibs[wib_number] = state.upper()  # Store the state in uppercase

    more = input("Do you want to power on/off more WIBs? (y/n): ")
    if more.lower() == 'y':
        while True:
            wib_number = input("Enter the WIB number you want to power on/off: ")
            wibs[wib_number] = "OFF"
            state = input(f"Enter the power state (ON/OFF) for WIB {wib_number}: ")
            wibs[wib_number] = state.upper()
            more = input("Do you want to power on/off more WIBs? (y/n): ")
            if more.lower() != 'y':
                break
    
    power_outputs = WIEC_SERIAL.power_wib(ser, wibs)

    print("\nPower control outputs:")
    for output in power_outputs:
        print(output)
    
    #### check what potential error messages could be later and account to handle those 




def main():
    wib_power()

    

















