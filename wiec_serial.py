#!/usr/bin/env python3

import sys
import time
import glob
import re


try:
    import serial
except ImportError:
    print("Missing pyserial. Install it with:")
    print("  pip install pyserial")
    sys.exit(1)


DEVICES = ["/dev/ttyUSB0","/dev/ttyUSB1"]
DEVICE = "/dev/ttyUSB0"
KNOWN_USB_PORTS = set()
USB_PORT_SCAN_STORED = False
BAUDRATE = 115200
USERNAME = "root"
PASSWORD = "root"

ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)


def sanitize_terminal_text(text):
    """
    Remove ANSI terminal control sequences from text read over serial or stdin.
    """
    return ANSI_ESCAPE_RE.sub("", str(text))


def scan_host_usb_serial_ports():
    """
    Return currently available USB/ACM serial ports on the host computer.
    """
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    return sorted(set(ports))


def store_current_usb_ports(available_ports=None):
    """
    Store the USB/ACM serial ports present before the Zynq is powered on.
    """
    global KNOWN_USB_PORTS, USB_PORT_SCAN_STORED
    if available_ports is None:
        available_ports = scan_host_usb_serial_ports()

    KNOWN_USB_PORTS = set(available_ports)
    USB_PORT_SCAN_STORED = True
    print("Stored current USB serial ports:")
    if KNOWN_USB_PORTS:
        for port in sorted(KNOWN_USB_PORTS):
            print(f"  {port}")
    else:
        print("  None")

    return KNOWN_USB_PORTS.copy()


def check_host_serial_device(timeout=100, poll_interval=1):
    """
    This checks the Ubuntu host computer, not the Zynq.
    If store_current_usb_ports() was called before power-up, the first new
    USB/ACM serial port is treated as the Zynq device port.
    """
    global DEVICE

    start_time = time.time()
    available_ports = []
    new_ports = []

    if USB_PORT_SCAN_STORED:
        while time.time() - start_time <= timeout:
            available_ports = scan_host_usb_serial_ports()
            new_ports = sorted(set(available_ports) - KNOWN_USB_PORTS)

            if new_ports:
                DEVICE = new_ports[0]
                if len(new_ports) > 1:
                    print("Multiple new USB serial ports were found:")
                    for port in new_ports:
                        print(f"  {port}")
                    print(f"Using first new port as Zynq serial device: {DEVICE}")
                else:
                    print(f"Found new Zynq serial device: {DEVICE}")
                return None

            time.sleep(poll_interval)

        print("Zynq serial device was not found as a new USB port.")
        print("Previously known USB serial ports:")
        if KNOWN_USB_PORTS:
            for port in sorted(KNOWN_USB_PORTS):
                print(f"  {port}")
        else:
            print("  None")

        print("Detected serial-like ports:")
        if available_ports:
            for port in available_ports:
                print(f"  {port}")
        else:
            print("  None")

        print("\nCheck that the Zynq board USB cable is connected and that PTC power is on.")
        sys.exit(1)

    available_ports = scan_host_usb_serial_ports()
    print("No stored pre-power USB scan was found. Falling back to legacy device names.")
    print("Detected serial-like ports:")
    if available_ports:
        for port in available_ports:
            print(f"  {port}")
    else:
        print("  None")

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
            text = sanitize_terminal_text(text)
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


def run_ecat_soft_timeout_then_i2cdetect(
    ser,
    command="python3 ecat_test1b.py logfile.txt",
    soft_timeout=65,
    settle_time=45,
):
    """
    Run the ecat command briefly, stop it with Ctrl-Z, then scan I2C bus 2.
    The Ctrl-Z stop is intentionally treated as normal flow for QC.
    """
    if ser.in_waiting:
        ser.read(ser.in_waiting)

    print(f"Running {command} for {soft_timeout} seconds...")
    send_line(ser, command)

    start_time = time.time()
    while time.time() - start_time < soft_timeout:
        if ser.in_waiting:
            raw = ser.read(ser.in_waiting)
            _ = sanitize_terminal_text(raw.decode(errors="ignore"))
        time.sleep(0.1)

    ser.write(b"\x1a")
    ser.flush()
    time.sleep(1)

    if ser.in_waiting:
        raw = ser.read(ser.in_waiting)
        stopped_output = sanitize_terminal_text(raw.decode(errors="ignore"))
        if stopped_output.strip():
            print(stopped_output)

    print(f"Waiting {settle_time} seconds before I2C scan...")
    time.sleep(settle_time)

    detect_output = run_petalinux_command(ser, "i2cdetect -y -r 2", timeout=15)
    print(detect_output)
    return detect_output



# function to collect output resposnse 
def login(): # func to just login
    check_host_serial_device()
    time.sleep(100)  # wait for the Zynq to boot up and be ready for commands
    ser = login_petalinux()
    set_date(ser)
    return ser

def set_timing(ser):
    """
    Sets the timing parameter on the PetaLinux shell.
    """
    output = run_petalinux_command(ser, "python setup_timing.py")
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
    print(output)
    # user prompted wait 
    userinput = "no"
    while userinput != "go":
        print(output)
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
