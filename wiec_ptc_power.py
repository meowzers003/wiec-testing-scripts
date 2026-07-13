import re
import subprocess
import time
import sys
import traceback
import json
import pyvisa


# device classes
from keysight_daq970a import Keysight970A
from rigol_dp832a import RigolDP832A
from pl506 import PL506
import wiec_serial

# fans_on = True # unnecessary since there's blocking logic

ptc_initialized = False  # global variable to track if PTC hardware has been initialized



def turn_on_pl506():
    readback = pl506.safe_turn_on_channel(channel=json_data["PL506_channel"],
                                                max_voltage_v=json_data["PL506_voltage_max"],
                                                voltage_v=json_data["PL506_sense_voltage"],
                                                max_current_a=json_data["PL506_current_max"],
                                                current_limit_a=json_data["PL506_current_limit"],
                                                settle_s=json_data["PL506_settle_seconds"])
    return readback


def initialize_wiec():
    # initialization little guys 
    # set up configurations
    global json_data, rm, r0, r1, k, pl506, ptc_initialized # doesnt initialize upon import
    wiec_serial.store_current_usb_ports() # do a usb port scan before turning on ptc zynq s
    json_data = None
    with open('config.json') as jsonfile:
        json_data = json.load(jsonfile)
    rm = pyvisa.ResourceManager('@py')
    r0 = RigolDP832A(rm, json_data, 0)
    r1 = RigolDP832A(rm, json_data, 1)
    k = Keysight970A(rm, json_data)
    pl506 = PL506(ip=json_data["PL506_IP_ADDR"])

    ptc_initialized = True

    # turn on all fans 
    json_data['rigol832a_fan_voltage'] = json_data['WIEC_fan_voltage'] 
    json_data['rigol832a_fan_current'] = json_data['WIEC_fan_current']
    r0.setup_fan() # apply new settings to fan
    r0.power("ON", "fan") # turn on fan power supply
    r1.setup_fanread()
    r1.power("ON", "fanread")
    k.initialize_fan()

    # check if every fan is on and oscillating at the correct frequency
    fan_voltage = r0.get_voltage("fan")
    fan_current = r0.get_current("fan")
    fanread_voltage = r1.get_voltage("fanread")
    fanread_current = r1.get_current("fanread")
    fan_read_signal = k.measure_fan()

    num_fans = int(json_data['keysight970a_fan_num'] )
    for fan in range(1, num_fans + 1):
        if (fan_read_signal[fan] < json_data["fan_osc_freq"]):
            print(f" --> CONFIG ERROR! Fan #{fan} is not oscillating at the correct frequency: {fan_read_signal[fan]} Hz")			
            print(f" --> Please check fan connections and restart test")	
            return False # end func execution early upon error

    # turn on PL506 channel for PTC power supply since fan is confirmed to be working
    readback = turn_on_pl506()
    print(readback)
    
    if readback.get("measured_current_a",0.0) == 0.0 or readback.get("terminal_voltage_v",0.0) == 0.0 :
        print("error. PTC power is not on. will try again 3x times")
        # error turning on power supply, redo it x3
        i=0
        while i != 3:
            print(f"Retry Attempt # {i+1}")
            readback = turn_on_pl506()
            if readback.get("measured_current_a",0.0) != 0.0 and readback.get("terminal_voltage_v",0.0) != 0.0 :
                print(f" --> PL506 channel {json_data['PL506_channel']} turned on with readback information:")
                print(readback)
                return True
            else:
                i+=1            
                                                    
    print(f" --> PL506 channel {json_data['PL506_channel']} turned on with readback information:")
    print(readback)
    return True

        
def shutdown_wiec():
    if not ptc_initialized:
        print("PTC shutdown skipped: PTC hardware was not initialized.")
        return True
    
    # turn off PL506 channel for PTC power supply
    pl506.channel_off(channel=json_data["PL506_channel"])
    pl506.main_off()
    print(f" --> PL506 channel {json_data['PL506_channel']} turned off")
    # turn off all fans 
    r0.power("OFF", "fan") # turn off fan power supply 
    r1.power("OFF", "fanread")
    return True
    



