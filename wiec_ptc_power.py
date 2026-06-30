import re
import subprocess
import time
import sys
import traceback
import json
import pyvisa

# device classes
import rigol_dp832a as RigolDP832A
import pl506 as PL506
import keysight_daq970a as KEYSIGHT

import dune_hv_crate_test as DUNE_HV_CRATE_TEST

# set up configurations
json_data = None
with open('config.json') as jsonfile:
    config_file = json.load(jsonfile)

results_data = None
with open('results.json') as jsonfile:
    results_data = json.load(jsonfile)

rm = pyvisa.ResourceManager('@py')

fans_on = True

r0 = RigolDP832A(rm, json_data, 0)
r1 = RigolDP832A(rm, json_data, 1)
k = KEYSIGHT(rm, json_data)

def initialize_wiec(self):
    # turn on all fans 
    json_data['rigol832a_fan_voltage'] = json_data['WIEC_fan_voltage'] 
    json_data['rigol832a_fan_current'] = json_data['WIEC_fan_current']
    r0.setup_fan() # apply new settings to fan
    r0.power("ON", "fan") # turn on fan power supply
    r1.setup_fanread()
    r1.power("ON", "fanread")

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
            results_data["errors"].append(f"CONFIG ERROR! Fan #{fan} is not oscillating at the correct frequency: {fan_read_signal[fan]} Hz")
            results_data["ptc_setup"] = "False"
            
            with open('results.json', 'w') as jsonfile:
                json.dump(results_data, jsonfile, indent=4) 

            return None # end func execution early upon error

    # turn on PL506 channel for PTC power supply since fan is confirmed to be working
    readback = PL506.safe_turn_on_channel(channel=json_data["PL506_channel"],
                                                max_voltage_v=json_data["PL506_voltage_max"],
                                                voltage_v=json_data["PL506_sense_voltage"],
                                                max_current_a=json_data["PL506_current_max"],
                                                current_limit_a=json_data["PL506_current_limit"],
                                                settle_s=json_data["PL506_settle_seconds"])
        
    print(" --> PL506 channel {json_data['PL506_channel']} turned on with readback information:")
    print(readback)

        
def shutdown_wiec(self):
    # turn off PL506 channel for PTC power supply
    pl506 = PL506(ip=json_data["PL506_IP_ADDR"])
    pl506.channel_off(channel=json_data["PL506_channel"])
    PL506.main_off()
    print(" --> PL506 channel {json_data['PL506_channel']} turned off")
    # turn off all fans 
    r0.power("OFF", "fan") # turn off fan power supply 





