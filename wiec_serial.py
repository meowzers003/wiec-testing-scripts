#!/usr/bin/env python3

import os
import sys
import time
import subprocess


try:
    import serial
except ImportError:
    print("Missing pyserial. Install it with:")
    print("  pip install pyserial")
    sys.exit(1)


DEVICES = ["/dev/ttyUSB0","/dev/ttyUSB1"]
DEVICE = "/dev/ttyUSB0"
BAUDRATE = 115200
USERNAME = "root"
PASSWORD = "root"


def check_host_serial_device():
    """
    This checks the Ubuntu host computer, not the Zynq.
    Equivalent idea to running: ls /dev/tty*
    """
    global DEVICE
    result = subprocess.run(
        ["bash", "-lc", "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null"],
        capture_output=True,
        text=True
    )
    
    time.sleep(20)

    available_ports = result.stdout.strip().splitlines()
    none = False
    for dev in DEVICES:
        if dev not in available_ports:
            print("Zynq serial device was not found.")
            print("Detected serial-like ports:")
            if available_ports:
                for port in available_ports:
                    print(f"  {port}")
            else:
                print("  None")
        else:
            print(f"Found Zynq serial device: {dev}")
            DEVICE = dev
            return None

    print(f"\nExpected: {DEVICES}")
    print("Check that the Zynq board USB cable is connected.")
    sys.exit(1)

    #print(f"Found Zynq serial device: {DEVICE}")


def read_until_any(ser, keywords, timeout=40):
    """
    Reads serial output until one of the keywords appears.
    Garbage bytes are ignored safely.
    """
    # FIX: Removed ser.reset_input_buffer() from here to prevent erasing valid text.

    print("Waiting for PetaLinux login prompt...")

    start_time = time.time()
    buffer = ""
    next_wake = start_time + 5

    while time.time() - start_time < timeout:
        waiting = ser.in_waiting

        if waiting:
            raw = ser.read(waiting)
            text = raw.decode(errors="ignore")
            buffer += text

            lower_buffer = buffer.lower()
            for keyword in keywords:
                if keyword.lower() in lower_buffer:
                    return buffer, keyword

        if time.time() >= next_wake:
            # FIX: Send raw \r\n instead of relying on default print formatting
            ser.write(b"\r\n")
            ser.flush()
            next_wake += 5

        time.sleep(0.1)

    return buffer, None

def send_line(ser, line):
    # FIX: Force \r\n explicitly to break past stuck terminal states
    ser.write((line + "\r\n").encode())
    ser.flush()
    time.sleep(0.3)



def login_petalinux():
    print(f"Opening serial console: {DEVICE} @ {BAUDRATE}")

    try:
        ser = serial.Serial(
            DEVICE,
            BAUDRATE,
            timeout=1,
            write_timeout=1
        )
    except PermissionError:
        print(f"Permission denied opening {DEVICE}.")
        sys.exit(1)

    time.sleep(1)
    ser.reset_input_buffer()

    # FIX 1: Do NOT spam enter right away. Let's check where the board is first.
    print("Checking initial terminal state...")
    ser.write(b"\r\n")
    ser.flush()
    time.sleep(0.5)

    # FIX 2: Add "ZynqMP>" to your allowed initial keywords
    output, matched = read_until_any(
        ser,
        keywords=["login:", "password:", "#", "$", "ZynqMP>"],
        timeout=300
    )

    if matched is None:
        print("Did not see login prompt, shell prompt, or bootloader.")
        print("Last serial output was:")
        print(output)
        ser.close()
        sys.exit(1)

    # FIX 3: If stuck in U-Boot, force it to boot into PetaLinux
    if matched == "ZynqMP>":
        print("Detected U-Boot prompt. Forcing PetaLinux boot sequence...")
        send_line(ser, "boot")
        
        # Wait longer because booting Linux takes time
        print("Waiting for PetaLinux to finish booting...")
        output, matched = read_until_any(
            ser,
            keywords=["login:", "password:", "#", "$"],
            timeout=60  # Increased timeout for full kernel boot
        )
        
        if matched is None:
            print("PetaLinux failed to boot after forcing 'boot'.")
            print(output)
            ser.close()
            sys.exit(1)

    # Already logged in
    if matched in ["#", "$"]:
        print("Already at shell prompt.")
        return ser

    # Username prompt
    if matched.lower() == "login:":
        print("Sending username...")
        send_line(ser, USERNAME)
        #output, matched = read_until_any(ser, keywords=["password:", "#", "$"], timeout=10)

    # Password prompt
 #   if matched and matched.lower() == "password:":
  #      print("Sending password...")
   #     send_line(ser, PASSWORD)
   #     output, matched = read_until_any(ser, keywords=["#", "$", "login incorrect"], timeout=10)

    if matched is None or "login incorrect" in output.lower():
        print("Login failed.")
        ser.close()
        sys.exit(1)

    print("Logged into PetaLinux.")
    return ser


def run_petalinux_command(ser, command, timeout=10):
    """
    Sends a command to the PetaLinux shell and returns printed output.
    """
    # Consume any trailing leftover data safely instead of wiping the hardware buffer
    if ser.in_waiting:
        ser.read(ser.in_waiting)

    send_line(ser, command)

    output, matched = read_until_any(
        ser,
        keywords=["#", "$"],
        timeout=timeout
    )

    return output



# function to collect output resposnse 
def login(): # func to just login
    check_host_serial_device()
    ser = login_petalinux()
    set_date(ser)
    return ser

def set_timing(ser):
    """
    Sets the timing parameter on the PetaLinux shell.
    """
    output = run_petalinux_command(ser, "python3 setup_timing.py")
    print(output)



def power_wib(ser, wibs):
    """
    Powers on or off the specified WIB.
    """
    outputs = {}
    print(f"\nSetting power for WIBs as follows {wibs}...")
    for wib, power_state in wibs.items():
        command = f"python3 power_on_wib.py {wib} {power_state}"
        output = run_petalinux_command(ser, command)
        print(output)
        outputs[wib] = output
        
    # user prompted wait 
    userinput = "no"
    while userinput != "go":
        userinput = input("continue?")

    return outputs

def sensors_addr(ser, wibs):
    sensor_outputs = {}
    for wib, power_state in wibs.items():
        print(f"Getting sensor output for WIB {wib}...")
        switch_output = run_petalinux_command(ser, f"i2cset -y 2 0x7{wib} 0x0002")
        print(switch_output)
        # user prompted wait 
        userinput = "no"
        while userinput != "go":
            userinput = input("continue?") 
    	           
    	           
        detect_output = run_petalinux_command(ser, f"i2cdetect -y -r 2")       
        print(detect_output)
        userinput = "no"
        while userinput != "go":
            userinput = input("continue?") 
    	           
        sensor_outputs[wib] = {
            "i2cset": switch_output,
            "i2cdetect": detect_output,
        }
    # output = run_petalinux_command(ser, f"python3 ecat_test1b.py logfile_willupdatetorealdatelater.txt")
    # print(output)
    return sensor_outputs
    
def close_serial(ser):
    ser.close()
    print("\nSerial connection closed.")

#### just to get current time and date in ubuntu format --------------------
import time
def get_system_ubuntu_date():
    # Grab the current system time structure
    local_time = time.localtime() #
    
    # Format according to Ubuntu's default structure
    # Alternative format string fallback for Windows cross-compatibility (%d instead of %e)
    return time.strftime("%a %b %d %H:%M:%S %Z %Y", local_time)

def set_date(ser):
    """
    Sets the date on the PetaLinux shell.
    """
    set_timing(ser)
    date_str = get_system_ubuntu_date()
    print(f"Setting date to {date_str}...")
    output = run_petalinux_command(ser, f"sudo date -s '{date_str}'")
    output += run_petalinux_command(ser, "date")
    print(f"\n Set date output: {output}")

def main():
    check_host_serial_device()

    ser = login_petalinux()

    print("\nRunning test command on PetaLinux...")
    output = run_petalinux_command(ser, "uname -a")
    print(output)

    print("\nListing PetaLinux tty devices...")
    output = run_petalinux_command(ser, "ls /dev/tty*")
    print(output)

    close_serial(ser)


if __name__ == "__main__":
    main()
