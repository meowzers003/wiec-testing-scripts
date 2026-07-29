
"""
For electrical test for each channel, please develop script to perform:

 

IV test, set voltage to 50V, 100V, 200V, 500V, 1000V, 1500V, 2000V, measure currents.
Ramp rate test (up/down):
(a) ramp rate set to 10V/s, ramp up to 1000V and then down, make plots to get the ramp rate

(b) ramp rate set to 100V, ramp up to 1000V and then down, make plots to get the ramp rate



Refer to screenshots in recent draft and photos to know the testing scheme 

"""

#!/usr/bin/env python3

import time 
from iseg_control import IsegMPOD, RampVerificationError, SNMPConfig
# import matplotlib
# import numpy as np
import gpib

# # GPIB board number and instrument address
# BOARD = 0
# ADDRESS = 9
# # Open the instrument
# dev = gpib.dev(BOARD, ADDRESS)

# # Identify the instrument
# gpib.write(dev, "*IDN?")
# print("Instrument:", gpib.read(dev, 256).decode().strip())

#  demo code 
#  while True:
# 	ch = int(input ("chn = (11-20) : ")) + 100
# 	# Measure DC voltage on channel 101
# 	gpib.write(dev, "MEAS:VOLT:DC? (@%3d)"%ch)

# 	result = gpib.read(dev, 256).decode().strip()

# 	print("Channel %3d ="%ch, result, "V")
# 	time.sleep(1)

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
    print("____________________________________________________________________________")    
    print("____________________________________________________________________________")
    print(" 1. IV test")
    print("____________________________________________________________________________")

    for voltage in voltage_values:
        current_measurements = set_ISEG_voltage(voltage, channels)

        print("-------------------------------------------------------------------------")
        print(f"Current Measurements at Voltage {voltage} for Channels : {channels}")
        print(current_measurements)
        print("-------------------------------------------------------------------------")

    print("____________________________________________________________________________")    
    print("____________________________________________________________________________")




if __name__ == "__main__":
    channels = [200,201,202,203,204,205,206,207]
    voltages = [50.0, 100.0, 200.0, 500.0, 1000.0, 1500.0, 2000.0]
    setup_ISEG()

    IVtest(voltages, channels=channels)
    for ch in channels:
        mpod.turn_off_crate()







        



    

    



        




    
