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


DEVICE = "/dev/ttyUSB0"
BAUDRATE = 115200
USERNAME = "root"
PASSWORD = "root"


def check_host_serial_device():
    """
    This checks the Ubuntu host computer, not the Zynq.
    Equivalent idea to running: ls /dev/tty*
    """
    result = subprocess.run(
        ["bash", "-lc", "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null"],
        capture_output=True,
        text=True
    )

    available_ports = result.stdout.strip().splitlines()

    if DEVICE not in available_ports:
        print("Zynq serial device was not found.")
        print("Detected serial-like ports:")
        if available_ports:
            for port in available_ports:
                print(f"  {port}")
        else:
            print("  None")

        print(f"\nExpected: {DEVICE}")
        print("Check that the Zynq board USB cable is connected.")
        sys.exit(1)

    print(f"Found Zynq serial device: {DEVICE}")


def read_until_any(ser, keywords, timeout=20):
    """
    Reads serial output until one of the keywords appears.
    Garbage bytes are ignored safely.
    """
    start_time = time.time()
    buffer = ""

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

        time.sleep(0.1)

    return buffer, None


def send_line(ser, line):
    ser.write((line + "\n").encode())
    ser.flush()
    time.sleep(0.3)


def login_petalinux():
    print(f"Opening serial console: {DEVICE} @ {BAUDRATE}")

    try:
        ser = serial.Serial(
            DEVICE,
            BAUDRATE,
            timeout=0.2,
            write_timeout=1
        )
    except PermissionError:
        print(f"Permission denied opening {DEVICE}.")
        print("You may need to add your user to the dialout group:")
        print("  sudo usermod -a -G dialout $USER")
        print("Then log out and log back in.")
        sys.exit(1)

    # Let the serial line settle.
    time.sleep(1)

    # Clear garbage/startup bytes.
    ser.reset_input_buffer()

    # Press Enter a few times to trigger a login prompt or shell prompt.
    for _ in range(3):
        send_line(ser, "")

    print("Waiting for PetaLinux login prompt...")

    output, matched = read_until_any(
        ser,
        keywords=["login:", "password:", "#", "$"],
        timeout=20
    )

    if matched is None:
        print("Did not see login prompt or shell prompt.")
        print("Last serial output was:")
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

        output, matched = read_until_any(
            ser,
            keywords=["password:", "#", "$"],
            timeout=10
        )

    # Password prompt
    if matched and matched.lower() == "password:":
        print("Sending password...")
        send_line(ser, PASSWORD)

        output, matched = read_until_any(
            ser,
            keywords=["#", "$", "login incorrect"],
            timeout=10
        )

    if matched is None or "login incorrect" in output.lower():
        print("Login failed.")
        print("Last serial output was:")
        print(output)
        ser.close()
        sys.exit(1)

    print("Logged into PetaLinux.")
    return ser


def run_petalinux_command(ser, command, timeout=10):
    """
    Sends a command to the PetaLinux shell and returns printed output.
    """
    ser.reset_input_buffer()

    send_line(ser, command)

    output, matched = read_until_any(
        ser,
        keywords=["#", "$"],
        timeout=timeout
    )

    return output


# function to collect output response 



def main():
    check_host_serial_device()

    ser = login_petalinux()

    print("\nRunning test command on PetaLinux...")
    output = run_petalinux_command(ser, "uname -a")
    print(output)

    print("\nListing PetaLinux tty devices...")
    output = run_petalinux_command(ser, "ls /dev/tty*")
    print(output)

    ser.close()
    print("\nDone.")


if __name__ == "__main__":
    main()