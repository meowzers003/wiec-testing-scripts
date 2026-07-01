import json
import traceback
import subprocess
import os
import sys

#### just to get current time and date in ubuntu format --------------------
import time

def get_system_ubuntu_date():
    # Grab the current system time structure
    local_time = time.localtime() #
    
    # Format according to Ubuntu's default structure
    # Alternative format string fallback for Windows cross-compatibility (%d instead of %e)
    return time.strftime("%a %b %d %H:%M:%S %Z %Y", local_time)

#### ----------------------------------------------------------------------------
import wiec_serial as WIEC_SERIAL

# log into Petalinux 
ser = WIEC_SERIAL.login()
print(f"\n Login in to PetaLinux output: {ser}") # may not be printable 


# set timing and date first 
date_output = WIEC_SERIAL.set_date(ser, get_system_ubuntu_date())
print(f"\n Set date output: {date_output}")

def wib_power():
    # asks user the wib # of interest to power on/off
    wibs = []
    wib_states = []
    wib_number = input("Enter the WIB number you want to power on/off: ")
    wibs.append(wib_number)
    state = input("Enter the power state (ON/OFF) for WIB {}: ".format(wib_number))
    wib_states.append(state)

    more = input("Do you want to power on/off more WIBs? (y/n): ")
    if more.lower() == 'y':
        while True:
            wib_number = input("Enter the WIB number you want to power on/off: ")
            wibs.append(wib_number)
            more = input("Do you want to power on/off more WIBs? (y/n): ")
            if more.lower() != 'y':
                break
    
    power_outputs = WIEC_SERIAL.power_wib(ser, wibs, wib_states)

    print("\nPower control outputs:")
    for output in power_outputs:
        print(output)
    
    #### check what potential error messages could be later and account to handle those 

    
















