
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
import multiprocessing as mp
from pathlib import Path
import queue
import traceback
import time 
from iseg_control import IsegMPOD, RampVerificationError, SNMPConfig
import matplotlib.dates as mdates
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
RAMP_SAMPLE_INTERVAL_S = 0.017
RAMP_COMPLETION_TOLERANCE_V = 1.0
STOP_MESSAGE = None

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

def close_device():
    global dev
    if dev is not None:
        gpib.close(dev)
        dev = None

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
    return 11+add + 100

def read_daq_voltages(channels, device=None):
    daq_device = dev if device is None else device
    daq_channels = [gpib_channel(ch) for ch in channels]
    channel_list = ",".join(str(ch) for ch in daq_channels)

    gpib.write(daq_device, f"MEAS:VOLT:DC? (@{channel_list})")
    result = gpib.read(daq_device, 4096).decode().strip()
    values = [float(value) for value in result.split(",")]

    if len(values) != len(channels):
        raise RuntimeError(
            f"DAQ returned {len(values)} readings for {len(channels)} channels: {result!r}"
        )

    return dict(zip(channels, values))

def ramp_acquisition_worker(
    data_queue,
    error_queue,
    ready_event,
    run_event,
    stop_event,
    channels,
    sample_interval_s,
):
    worker_dev = None
    try:
        worker_dev = gpib.dev(BOARD, ADDRESS)
        gpib.write(worker_dev, "*IDN?")
        identity = gpib.read(worker_dev, 256).decode().strip()
        print(f"[ramp acquisition] Instrument: {identity}", flush=True)

        ready_event.set()
        run_event.wait()

        start = time.time()
        next_sample_time = start
        while not stop_event.is_set():
            voltages = read_daq_voltages(channels, device=worker_dev)
            sample_time = datetime.now()
            elapsed_time = time.time() - start
            data_queue.put({
                "sample_timestamp": sample_time,
                "elapsed_time_s": elapsed_time,
                "voltages": voltages,
            })

            next_sample_time += sample_interval_s
            sleep_time = next_sample_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as exc:
        error_queue.put({
            "message": str(exc),
            "traceback": traceback.format_exc(),
        })
    finally:
        if worker_dev is not None:
            try:
                gpib.close(worker_dev)
            except Exception:
                pass
        data_queue.put(STOP_MESSAGE)

def _linear_ramp_fit(time_values, voltage_values):
    if len(time_values) < 2:
        return 0.0, float(voltage_values[0])
    slope, intercept = np.polyfit(time_values, voltage_values, 1)
    return float(slope), float(intercept)

def ramp_rate_setup(channel, ramp_rate, voltage):
    mpod.set_outputVoltage(channel,voltage)
    mpod.set_VoltageRiseRate(channel, ramp_rate)
    mpod.set_VoltageFallRate(channel, ramp_rate)

def wait_for_channels_near_voltage(channels, target_voltage=0.0, tolerance=5.0, timeout_s=180.0):
    start = time.time()
    remaining = set(channels)

    while remaining:
        high_channels = {}
        for ch in list(remaining):
            voltage = abs(mpod.read_outputVoltage(ch))
            if abs(voltage - target_voltage) <= tolerance:
                remaining.remove(ch)
            else:
                high_channels[ch] = voltage

        if not remaining:
            return

        elapsed = time.time() - start
        if elapsed >= timeout_s:
            for ch, voltage in sorted(high_channels.items()):
                print(f"Ch.{ch} still at {voltage:.2f} V after {elapsed:.1f} s")
            raise RuntimeError(
                f"Channels did not reach {target_voltage} V within {timeout_s:.0f} s: "
                f"{sorted(remaining)}"
            )

        print(
            f"Waiting for channels to reach {target_voltage:.1f} V "
            f"(+/- {tolerance:.1f} V): {sorted(remaining)}"
        )
        time.sleep(1)

def ramp_config(channels, ramp_rate, voltage):
    # ensure all channels off
    all_channels_off(channels)
    time.sleep(10) # ramp down time after all channels off
    wait_for_channels_near_voltage(channels)
    for ch in channels:
        ramp_rate_setup(ch,ramp_rate,voltage)

def _channels_reached_voltage(channels, target_voltage, tolerance=RAMP_COMPLETION_TOLERANCE_V):
    for ch in channels:
        voltage = abs(mpod.read_outputVoltage(ch))
        if abs(voltage - target_voltage) > tolerance:
            return False
    return True

def _drain_ramp_errors(error_queue):
    errors = []
    while True:
        try:
            errors.append(error_queue.get_nowait())
        except queue.Empty:
            return errors

def _plot_channel_ramp(mode, channel, ramp_rate, voltage, channel_samples):
    ch = gpib_channel(channel)
    if not channel_samples:
        print(f"Ch.{channel} Ramp Rate {ramp_rate} Test, {voltage} V : FAIL")
        return None, []

    timestamp_values = [point["sample_timestamp"] for point in channel_samples]
    time_values = np.array([point["elapsed_time_s"] for point in channel_samples], dtype=float)
    voltage_values = np.array([point["daq_voltage_V"] for point in channel_samples], dtype=float)

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
    for timestamp, time_point, voltage_point, fit_point in zip(
        timestamp_values,
        time_values,
        voltage_values,
        best_fit_voltage_values,
    ):
        ramp_rows.append({
            "test_type": "RampTest",
            "mode": mode,
            "iseg_channel": channel,
            "gpib_channel": ch,
            "set_ramp_rate_V_per_s": ramp_rate,
            "target_voltage_V": voltage,
            "sample_timestamp": timestamp.isoformat(timespec="milliseconds"),
            "elapsed_time_s": float(time_point),
            "daq_voltage_V": float(voltage_point),
            "best_fit_voltage_V": float(fit_point),
            "calculated_ramp_rate_V_per_s": daq_ramp_rate,
        })

    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    ax.plot(timestamp_values, voltage_values, "o", label="DAQ voltage")
    ax.plot(timestamp_values, best_fit_voltage_values, "-", label=f"Best fit: {daq_ramp_rate:.2f} V/s")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("voltage (Volts)")
    ax.set_title(f"CH {channel}/{ch} - {ramp_rate} V/s Ramp {mode} with {voltage} V")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S.%f"))
    fig.autofmt_xdate()
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

def run_ramp(mode,channels,ramp_rate,voltage):
    mode = mode.upper()
    if ramp_rate_results_directory is None:
        initialize_RR_folder(ramp_rate, voltage)

    for channel in channels:
        starting_voltage = abs(mpod.read_outputVoltage(channel))
        print(f"Ch.{channel} starting voltage before ramp {mode}: {starting_voltage:.2f} V")

    context = mp.get_context("spawn")
    data_queue = context.Queue()
    error_queue = context.Queue()
    ready_event = context.Event()
    run_event = context.Event()
    stop_event = context.Event()

    acquisition_process = context.Process(
        name="ramp-acquisition",
        target=ramp_acquisition_worker,
        args=(
            data_queue,
            error_queue,
            ready_event,
            run_event,
            stop_event,
            tuple(channels),
            RAMP_SAMPLE_INTERVAL_S,
        ),
    )

    ramp_rows = []
    samples_by_channel = {channel: [] for channel in channels}

    acquisition_process.start()
    try:
        if not ready_event.wait(timeout=30):
            raise RuntimeError("Ramp acquisition process did not become ready.")

        if mode == "UP":
            for channel in channels:
                mpod.channel_on(channel)
            end_voltage = voltage
        elif mode == "DOWN":
            for channel in channels:
                mpod.channel_off(channel)
            end_voltage = 0.0
        else:
            raise ValueError(f"Unsupported ramp mode: {mode}")

        time.sleep(0.5)
        run_event.set()

        while not _channels_reached_voltage(channels, end_voltage):
            for error in _drain_ramp_errors(error_queue):
                raise RuntimeError(
                    "Ramp acquisition process failed:\n"
                    f"{error['message']}\n{error['traceback']}"
                )
            time.sleep(0.1)

    finally:
        stop_event.set()
        run_event.set()

        acquisition_process.join(timeout=10)
        if acquisition_process.is_alive():
            acquisition_process.terminate()
            acquisition_process.join(timeout=5)

        while True:
            try:
                item = data_queue.get_nowait()
            except queue.Empty:
                break

            if item is STOP_MESSAGE:
                continue

            for channel in channels:
                samples_by_channel[channel].append({
                    "sample_timestamp": item["sample_timestamp"],
                    "elapsed_time_s": item["elapsed_time_s"],
                    "daq_voltage_V": item["voltages"][channel],
                })

    for error in _drain_ramp_errors(error_queue):
        raise RuntimeError(
            "Ramp acquisition process failed:\n"
            f"{error['message']}\n{error['traceback']}"
        )

    data_queue.close()
    error_queue.close()

    for channel in channels:
        plot_path, channel_rows = _plot_channel_ramp(
            mode,
            channel,
            ramp_rate,
            voltage,
            samples_by_channel[channel],
        )
        ramp_rows.extend(channel_rows)

    return ramp_rows


def RampTest(channels):
    ramp_rows = []
    print("____________________________________________________________________________")
    print("____________________________________________________________________________")
    print(" 2. Ramp Rate test")
    print("____________________________________________________________________________")
    print("----------------------------------------------------------------------------")
    # # set up gpib connection
    # setup_device()
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
                "sample_timestamp",
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
    daq_voltage = {}
    # set the default ramp up/down rate 

    for ch in channels:
        # set fall rate and rise rate
        mpod.set_VoltageFallRate(ch, ramp_rate) 
        mpod.set_VoltageRiseRate(ch, ramp_rate)

        # set outputvoltage
        mpod.set_outputVoltage(ch, voltage)

    for ch in channels:
        # turn channel on 
        mpod.channel_on(ch)

    # wait time
    time.sleep( (voltage // int(ramp_rate) ) + 5 ) # get measurement 5 seconds after target voltage is reached

    # get current and store it in a list
    for ch in channels:
        ch_current = mpod.read_outputCurrent(ch) * 1e6 # all current measurements in uA scale
        current_measurements[ch] = abs(ch_current)

    daq_voltage = read_daq_voltages(channels)

    return current_measurements, daq_voltage


def IVtest(voltage_values, channels):
    iv_rows = []
    initialize_RR_folder()
    print("____________________________________________________________________________")    
    print("____________________________________________________________________________")
    print(" 1. IV test")
    print("____________________________________________________________________________")
    print("----------------------------------------------------------------------------")

    for voltage in voltage_values:
        current_measurements, daq_voltage = set_ISEG_voltage(voltage, channels)
        print(f"Current Measurements at Voltage {voltage} for Channels : {channels}")
        for ch,curr in current_measurements.items():
            iv_rows.append({
                "test_type": "IVtest",
                "iseg_channel": ch,
                "set_voltage_V": voltage,
                "measured_current_uA": curr,
                "measured_DAQ_voltage": daq_voltage[ch]
            })
            print(f"Ch. {ch}: {curr} uA, DAQ voltage: {daq_voltage[ch]}")
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
                "measured_DAQ_voltage"
            ],
        )
        print(f"IV test data saved to: {csv_path}")

    print("____________________________________________________________________________")    
    print("____________________________________________________________________________")


# shut off channels off
def all_channels_off(channels):
    for ch in channels:
        mpod.channel_off(ch)
        time.sleep(10)

def shutdown():
    global dev

    if mpod is not None:
        try:
            mpod.turn_off_crate()
        except Exception as exc:
            print(f"Failed to turn off ISEG crate during shutdown: {exc}")

    if dev is not None:
        try:
            close_device()
            print("GPIB connection closed.")
        except Exception as exc:
            print(f"Failed to close GPIB connection during shutdown: {exc}")

if __name__ == "__main__":
    mp.freeze_support()
    channels = [200,201,202,203,204,205,206,207]
    voltages = [50.0, 100.0, 200.0, 500.0, 1000.0, 1500.0, 2000.0]
    try:
        setup_device() # gpib
        setup_ISEG()

        # 1. IVtest
        IVtest(voltages, channels=channels)
        all_channels_off(channels=channels)
        close_device()

        # 2. DAQ Ramp Rate Test
        RampTest(channels)

    except KeyboardInterrupt:
        print("\nKeyboard interrupt received; shutting down hardware connections.")
        raise SystemExit(130)
    finally:
        # turn everything off and release GPIB for future tests
        shutdown()
        




    
