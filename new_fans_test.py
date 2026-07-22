import pyvisa
import sys
import json
import os
import time
import openpyxl
from datetime import datetime
from keysight_daq970a import Keysight970A
from rigol_dp832a import RigolDP832A
from caen_r8033dm_wrapper import CAENR8033DM_WRAPPER

class fantest:
    def __init__(self, config_file = 'config.json', name = None):
        with open(config_file, "r") as jsonfile:
            self.json_data = json.load(jsonfile)	
	
        self.rm = pyvisa.ResourceManager('@py')      
        self.prefix = "fantest"

	#Initialize all instruments first so that you don't waste time with input if something is not connected
        #self.c = CAENR8033DM_WRAPPER(self.json_data)
        self.k = Keysight970A(self.rm, self.json_data)
        #print(self.k.keysight.query("SYST:ERR?", delay = self.json_data['keysight970a_fan_delay']))

	#Since there are 2 Rigols, set them up here so they know what channels they have
	#And if the test sequence calls the wrong one, it'll throw an error
        self.r0 = RigolDP832A(self.rm, self.json_data, 0)
        self.r0.setup_fan()
        self.r0.setup_heater_supply()
        self.r0.setup_heater_switch()

        self.r1 = RigolDP832A(self.rm, self.json_data, 1)
        self.r1.setup_hvpullup()
        self.r1.setup_hvpullup2()
        self.r1.setup_fanread() #for new fans Vpullup_max=15V, this is set at 5V, should be fine
	#Now we can get the input

	#Fan test
        self.k.initialize_fan_new()
        self.r0.power("ON", "fan")
        self.r1.power("ON", "fanread") 
        print(f"{self.prefix} --> Fans turned on, waiting {self.json_data['fan_wait']} seconds for the fans to reach steady state...")

        fan_voltage = self.r0.get_voltage("fan")
        fan_current = self.r0.get_current("fan")
        fanread_voltage = self.r1.get_voltage("fanread")
        fanread_current = self.r1.get_current("fanread")
        fan_read_signal = self.k.measure_fan_new() #replace this with PWM read
        print(fan_read_signal)
		
        self.r0.power("OFF", "fan")
        self.r1.power("OFF", "fanread")
        
        
        #Heater test
        #First measure resistance of heating element with no power connected
        self.k.initialize_resistance()
        heater_resistance = self.k.measure_resistance()
        
        self.k.initialize_rtd()
        temp1 = self.k.measure_rtd()
        #temp1 = self.k.measure_rtd() #measure again for good measure
        self.r0.power("ON", "heat_supply")
        self.r0.power("ON", "heat_switch")
        print(f"{self.prefix} --> Heat turned on, waiting {self.json_data['heat_wait']} seconds for the sensors to heat up...")
        time.sleep(self.json_data['heat_wait'])
        supply_voltage = self.r0.get_voltage("heat_supply")
        supply_current = self.r0.get_current("heat_supply")
        switch_voltage = self.r0.get_voltage("heat_switch")
        switch_current = self.r0.get_current("heat_switch")
        temp2 = self.k.measure_rtd()
        #temp2 = self.k.measure_rtd() #measure again for good measure
        temp_rise = []
        temp_rise.append(temp2[1] - temp1[1])
        temp_rise.append(temp2[2] - temp1[2])
        temp_rise.append(temp2[3] - temp1[3])
        temp_rise.append(temp2[4] - temp1[4])

        self.r0.power("OFF", "heat_supply")
        self.r0.power("OFF", "heat_switch")                
	
fantest()
