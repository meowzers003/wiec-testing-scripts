
"""
For electrical test for each channel, please develop script to perform:

 

IV test, set voltage to 50V, 100V, 200V, 500V, 1000V, 1500V, 2000V, measure currents.
Ramp rate test (up/down):
(a) ramp rate set to 10V/s, ramp up to 1000V and then down, make plots to get the ramp rate

(b) ramp rate set to 100V, ramp up to 1000V and then down, make plots to get the ramp rate



Refer to screenshots in recent draft and photos to know the testing scheme 

"""

#!/usr/bin/env python3

import csv
from datetime import datetime
from pathlib import Path
import time 
from iseg_control import IsegMPOD, RampVerificationError, SNMPConfig
import matplotlib.pyplot as plt
import numpy as np
import gpib

# GPIB board number and instrument address
BOARD = 0
ADDRESS = 9
dev = None

#  demo code 
#  while True:
# 	ch = int(input ("chn = (11-20) : ")) + 100
# 	# Measure DC voltage on channel 101
# 	gpib.write(dev, "MEAS:VOLT:DC? (@%3d)"%ch)

# 	result = gpib.read(dev, 256).decode().strip()

# 	print("Channel %3d ="%ch, result, "V")
# 	time.sleep(1)
# --------------------- Ramp Rate Test ----------------------------------------------
ramp_rate_results_directory = None
RAMP_RATE_RESULTS_ROOT = Path.cwd() / "ISEG_E-Tests_RampRate"

def _timestamp():
    return datetime.now().strftime("%d-%m-%y_%H-%M-%S")

def _csv_path(test_type):
    if ramp_rate_results_directory is None:
        initialize_RR_folder()
    return Path(ramp_rate_results_directory) / f"{test_type}_{_timestamp()}.csv"

def _write_csv(csv_path, rows, fieldnames):
    with open(csv_path, "w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def setup_device():
    # Open the instrument
    global dev
    dev = gpib.dev(BOARD, ADDRESS)
    # Identify the instrument
    gpib.write(dev, "*IDN?")
    print("Instrument:", gpib.read(dev, 256).decode().strip())


def ramp_rate_setup(channel, ramp_rate, voltage):
    mpod.set_outputVoltage(channel,voltage)
    mpod.set_VoltageRiseRate(channel, ramp_rate)
    mpod.set_VoltageFallRate(channel, ramp_rate)

def initialize_RR_folder(ramp_rate=None,voltage=None):
    global ramp_rate_results_directory
    if ramp_rate_results_directory is not None:
        return ramp_rate_results_directory

    # make a folder called "ISEG_E-Tests_RampRate" if it doesnt already exist in current directory
    RAMP_RATE_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    # make a folder for the test result files/plots - title it as using DD/MM/YR_time format
    timestamp = _timestamp()
    if ramp_rate is None or voltage is None:
        test_folder = RAMP_RATE_RESULTS_ROOT / f"{timestamp}_ElectricalTests"
    else:
        test_folder = RAMP_RATE_RESULTS_ROOT / f"{timestamp}_{ramp_rate}Vps_{voltage}V"
    test_folder.mkdir(parents=True, exist_ok=True)

    #  set the global ramp rate results directory path to point to the one just created
    ramp_rate_results_directory = test_folder

    return ramp_rate_results_directory

def gpib_channel(iseg_ch):
    add = iseg_ch % 100
    return 11+add

def ramp_test(mode,channel,ramp_rate,voltage):
    plot_data = {}
    mode = mode.upper()
    ch = gpib_channel(channel) + 100

    end_voltage = voltage
    if mode == "UP":
        mpod.channel_on(channel)
    elif mode == "DOWN":
        end_voltage = 0
        mpod.channel_off(channel)
    else:
        raise ValueError(f"Unsupported ramp mode: {mode}")

    start = time.time()

    voltage_read = abs(mpod.read_outputVoltage(channel))
    while round(voltage_read) != end_voltage: # did not reach the end of ramping
        time.sleep(0.5)

        # get DAQ measurement
        gpib.write(dev, "MEAS:VOLT:DC? (@%3d)"%ch)
        result = gpib.read(dev, 256).decode().strip()
        voltage_point = float(result)
        time_point = time.time() - start

        # store data
        plot_data[time_point] = voltage_point

        voltage_read = abs(mpod.read_outputVoltage(channel))

    # make the plot and store it in ramp_rate_results_directory
    # x-axis "time (seconds)", y-axis "voltage (Volts)"
    # title each plot "CH {channel}/{ch} - {ramp_rate} V/s Ramp {mode} with {voltage} V"
    # each plot will also have a linear line of best fit in order to find the ramp rate
    # calculated DAQ ramp rate will be displayed on the plot image
    if ramp_rate_results_directory is None:
        initialize_RR_folder(ramp_rate, voltage)

    if not plot_data:
        print(f"Ch.{channel} Ramp Rate {ramp_rate} Test, {voltage} V : FAIL")
        return None, []

    time_values = np.array(list(plot_data.keys()), dtype=float)
    voltage_values = np.array(list(plot_data.values()), dtype=float)

    if mode == "DOWN":
        fit_values = voltage - voltage_values
        slope, intercept = _linear_ramp_fit(time_values, fit_values)
        best_fit_voltage_values = voltage - (slope * time_values + intercept)
    else:
        fit_values = voltage_values
        slope, intercept = _linear_ramp_fit(time_values, fit_values)
        best_fit_voltage_values = slope * time_values + intercept

    daq_ramp_rate = abs(slope)
    ramp_rows = []
    for time_point, voltage_point, fit_point in zip(time_values, voltage_values, best_fit_voltage_values):
        ramp_rows.append({
            "test_type": "RampTest",
            "mode": mode,
            "iseg_channel": channel,
            "gpib_channel": ch,
            "set_ramp_rate_V_per_s": ramp_rate,
            "target_voltage_V": voltage,
            "elapsed_time_s": float(time_point),
            "daq_voltage_V": float(voltage_point),
            "best_fit_voltage_V": float(fit_point),
            "calculated_ramp_rate_V_per_s": daq_ramp_rate,
        })

    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    ax.plot(time_values, voltage_values, "o", label="DAQ voltage")
    ax.plot(time_values, best_fit_voltage_values, "-", label=f"Best fit: {daq_ramp_rate:.2f} V/s")
    ax.set_xlabel("time (seconds)")
    ax.set_ylabel("voltage (Volts)")
    ax.set_title(f"CH {channel}/{ch} - {ramp_rate} V/s Ramp {mode} with {voltage} V")
    ax.grid(True)
    ax.legend()
    ax.text(
        0.02,
        0.95,
        f"Calculated DAQ ramp rate: {daq_ramp_rate:.2f} V/s",
        transform=ax.transAxes,
        va="top",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )

    # save plot image into the ramp_rate_results_directory
    safe_ramp_rate = str(ramp_rate).replace(".", "p")
    safe_voltage = str(voltage).replace(".", "p")
    plot_path = (
        Path(ramp_rate_results_directory)
        / f"CH_{channel}_{ch}_{safe_ramp_rate}Vps_ramp_{mode}_{safe_voltage}V.png"
    )
    fig.savefig(plot_path, bbox_inches="tight")
    plt.close(fig)

    print(f"Ch.{channel} Ramp Rate {ramp_rate} Test, {voltage} V : COMPLETE")
    return plot_path, ramp_rows


def _linear_ramp_fit(time_values, voltage_values):
    if len(time_values) < 2:
        return 0.0, float(voltage_values[0])
    slope, intercept = np.polyfit(time_values, voltage_values, 1)
    return float(slope), float(intercept)

def ramp_config(channels, ramp_rate, voltage):
    # ensure all channels off
    all_channels_off(channels)
    time.sleep(10) # ramp down time after all channels off
    for ch in channels:
        ramp_rate_setup(ch,ramp_rate,voltage)

def run_ramp(mode,channels,ramp_rate,voltage):
    ramp_rows = []
    for channel in channels:
        plot_path, channel_rows = ramp_test(mode,channel,ramp_rate,voltage)
        ramp_rows.extend(channel_rows)
    return ramp_rows


def RampTest(channels):
    ramp_rows = []
    print("____________________________________________________________________________")
    print("____________________________________________________________________________")
    print(" 2. Ramp Rate test")
    print("____________________________________________________________________________")
    print("----------------------------------------------------------------------------")
    # set up gpib connection
    setup_device()
    print("----------------------------------------------------------------------------")

    # (a) ramp UP, 10 V/s, 1000 V
    initialize_RR_folder(10.0, 1000.0)
    ramp_config(channels, 10.0, 1000.0)
    print("----------------------------------------------------------------------------")

    print("Test : ramp UP, 10 V/s, 1000 V => in progress")
    ramp_rows.extend(run_ramp("UP",channels,10.0,1000.0))
    print("Test : ramp UP, 10 V/s, 1000 V => DONE")

    print("----------------------------------------------------------------------------")

    print("Test : ramp DOWN, 10 V/s, 1000 V => in progress")
    # (b) ramp DOWN, 10 V/s, 1000 V
    ramp_rows.extend(run_ramp("DOWN",channels,10.0,1000.0))
    print("Test : ramp DOWN, 10 V/s, 1000 V => DONE")

    print("----------------------------------------------------------------------------")

    print("Test : ramp UP, 100 V/s, 1000 V => in progress")
    # (c) ramp UP, 100 V/s, 1000 V
    initialize_RR_folder(100.0, 1000.0)
    ramp_config(channels, 100.0, 1000.0)
    ramp_rows.extend(run_ramp("UP",channels,100.0,1000.0))
    print("Test : ramp UP, 100 V/s, 1000 V => DONE")

    print("----------------------------------------------------------------------------")

    print("Test : ramp DOWN, 100 V/s, 1000 V => in progress")
    # (d) ramp DOWN, 100 V/s, 1000 V
    ramp_rows.extend(run_ramp("DOWN",channels,100.0,1000.0))
    print("Test : ramp DOWN, 100 V/s, 1000 V => DONE")

    if ramp_rows:
        csv_path = _csv_path("RampTests")
        _write_csv(
            csv_path,
            ramp_rows,
            [
                "test_type",
                "mode",
                "iseg_channel",
                "gpib_channel",
                "set_ramp_rate_V_per_s",
                "target_voltage_V",
                "elapsed_time_s",
                "daq_voltage_V",
                "best_fit_voltage_V",
                "calculated_ramp_rate_V_per_s",
            ],
        )
        print(f"Ramp test data saved to: {csv_path}")

    print("----------------------------------------------------------------------------")
    print("----------------------------------------------------------------------------")





#----------------------- IVtest -----------------------------------------------------
mpod = None
ip = None
cfg = None 
ISEG_IP = "169.254.4.31"

# set up the ISEG mod 
def setup_ISEG():
    # configure and turn it on 
    global ip, cfg, mpod 
    ip = ISEG_IP
    cfg = SNMPConfig(
        ip=ip,
        read_community="public",
        write_community="guru",
        log_commands=True,
    )

    mpod = IsegMPOD(cfg)

    # send command to turn it on
    response = mpod.turn_on_crate()
    time.sleep(20) # add small delay
    # print(mpod.turn_on_crate())
    for i in range(3):
        if "on(1)" not in response:
            response = mpod.turn_on_crate()

    if "on(1)" not in response:
        print("did not turn on, exact response after 3 attempts:")
        print(response)
        return False 
    
    return True 

# sets voltage for the specified iseg channel 
def set_ISEG_voltage(voltage, channels, ramp_rate=100.0):
    current_measurements ={}
    # set the default ramp up/down rate 
    for ch in channels:
        # set fall rate and rise rate
        mpod.set_VoltageFallRate(ch, ramp_rate) 
        mpod.set_VoltageRiseRate(ch, ramp_rate)

        # set outputvoltage
        mpod.set_outputVoltage(ch, voltage)

        # turn channel on 
        mpod.channel_on(ch)
        # wait time 
        time.sleep( (voltage // int(ramp_rate) ) + 5 ) # get measurement 5 seconds after target voltage is reached   

        # get current and store it in a list 
        ch_current = mpod.read_outputCurrent(ch) * 1e6 # all current measurements in uA scale
        current_measurements[ch] = abs(ch_current)

    return current_measurements


def IVtest(voltage_values, channels):
    iv_rows = []
    initialize_RR_folder()
    print("____________________________________________________________________________")    
    print("____________________________________________________________________________")
    print(" 1. IV test")
    print("____________________________________________________________________________")
    print("----------------------------------------------------------------------------")

    for voltage in voltage_values:
        current_measurements = set_ISEG_voltage(voltage, channels)
        print(f"Current Measurements at Voltage {voltage} for Channels : {channels}")
        for ch,curr in current_measurements.items():
            iv_rows.append({
                "test_type": "IVtest",
                "iseg_channel": ch,
                "set_voltage_V": voltage,
                "measured_current_uA": curr,
            })
            print(f"Ch. {ch}: {curr} uA")
        print("----------------------------------------------------------------------------")

    if iv_rows:
        csv_path = _csv_path("IVtest")
        _write_csv(
            csv_path,
            iv_rows,
            [
                "test_type",
                "iseg_channel",
                "set_voltage_V",
                "measured_current_uA",
            ],
        )
        print(f"IV test data saved to: {csv_path}")

    print("____________________________________________________________________________")    
    print("____________________________________________________________________________")


# shut off channels off
def all_channels_off(channels):
    for ch in channels:
        mpod.channel_off(ch)

def shutdown():
    global dev

    if mpod is not None:
        try:
            mpod.turn_off_crate()
        except Exception as exc:
            print(f"Failed to turn off ISEG crate during shutdown: {exc}")

    if dev is not None:
        try:
            gpib.close(dev)
            print("GPIB connection closed.")
        except Exception as exc:
            print(f"Failed to close GPIB connection during shutdown: {exc}")
        finally:
            dev = None

if __name__ == "__main__":
    channels = [200,201,202,203,204,205,206,207]
    voltages = [50.0, 100.0, 200.0, 500.0, 1000.0, 1500.0, 2000.0]
    try:
        setup_ISEG()

        # 1. IVtest
        IVtest(voltages, channels=channels)
        all_channels_off(channels=channels)

        # 2. DAQ Ramp Rate Test
        RampTest(channels)
        
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received; shutting down hardware connections.")
        raise SystemExit(130)
    finally:
        # turn everything off and release GPIB for future tests
        shutdown()
        




    
