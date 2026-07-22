# -*- coding: utf-8 -*-
"""
Created on Wed Sept 25 10:51:58 2023

@author: Eraguzin
"""
import sys, time

class Keysight970A:
    def __init__(self, rm, json_data):
        self.prefix = "Keysight DAQ 970A"
        self.json_data = json_data
        self.keysight = rm.open_resource(self.json_data['keysight970a'])
        print(f"{self.prefix} --> Connected to {self.keysight.query('*IDN?')}")
        self.keysight.write("*RST")

        #Common commands
        self.keysight.write("SYSTem:BEEPer:STATe ON")
        #self.keysight.write("SYSTem:BEEPer:IMMediate")
        self.keysight.write("FORMat:READing:CHANnel ON")

        #Keeps track of state to make sure commands don't collide
        self.state = None
        self.relay_hv_state = None
        self.relay_term_state = None

        #Build the string of the list of RTD channels
        self.rtd_ch_list = ""
        self.rtd_convert = {}
        rtd_slot = self.json_data['keysight970a_901A_slot']
        self.num_rtds = self.json_data['keysight970a_rtd_num']
        for i in range(1,self.num_rtds+1,1):
            ch_num = self.json_data[f'keysight970a_rtd_ch{i}']
            ch_string = f"{rtd_slot}{ch_num:02d}"
            self.rtd_convert[f"{ch_string}"] = i
            if (i == 1):
                self.rtd_ch_list += (f"@{ch_string}")
            else:
                self.rtd_ch_list += (f",{ch_string}")

        #Build the string of the list of heater channels
        self.heater_ch_list = ""
        self.heater_convert = {}
        heater_slot = self.json_data['keysight970a_901A_slot']
        self.num_heaters = self.json_data['keysight970a_heater_num']
        for i in range(1,self.num_heaters+1,1):
            ch_num = self.json_data[f'keysight970a_heater_ch{i}']
            ch_string = f"{heater_slot}{ch_num:02d}"
            self.heater_convert[f"{ch_string}"] = i
            if (i == 1):
                self.heater_ch_list += (f"@{ch_string}")
            else:
                self.heater_ch_list += (f",{ch_string}")

        #Build the string of the list of fan channels
        self.fan_ch_list = ""
        self.fan_convert = {}
        fan_slot = self.json_data['keysight970a_901A_slot']
        self.num_fans = self.json_data['keysight970a_fan_num']
        for i in range(1,self.num_fans+1,1):
            ch_num = self.json_data[f'keysight970a_fan_ch{i}']
            ch_string = f"{fan_slot}{ch_num:02d}"
            self.fan_convert[f"{ch_string}"] = i
            if (i == 1):
                self.fan_ch_list += (f"@{ch_string}")
            else:
                self.fan_ch_list += (f",{ch_string}")

    def clear_scan_list(self):
        self.keysight.write("ROUTe:SCAN (@)")

    def initialize_rtd(self):
        #Keysight DAQ970A requires you to do a Configure first and then change the parameters with Sense
        #Configure sets the resistance of the RTD, and default resolution
        #It also updates the scan list so only the channels in this Configure command are scanned
        self.keysight.write(f"CONFigure:TEMPerature:RTD {self.json_data['keysight970a_rtd_RES']},DEF,({self.rtd_ch_list})")

        #Sets the sample rate a little slower for accuracy, whether in low power mode or not, and units to use
        self.keysight.write(f"SENSe:TEMPerature:NPLCycles {self.json_data['keysight970a_rtd_NPLcycles']},({self.rtd_ch_list})")
        self.keysight.write(f"SENSe:TEMPerature:TRANsducer:RTD:POWer:LIMit:STATe {self.json_data['keysight970a_rtd_LowPower']},({self.rtd_ch_list})")
        self.keysight.write(f"UNIT:TEMPerature {self.json_data['keysight970a_rtd_units']},({self.rtd_ch_list})")
        self.keysight.write("FORMat:READing:CHANnel ON")

        self.state = "rtd"

    def initialize_resistance(self):
        self.keysight.write(f"CONFigure:RESistance AUTO,DEF,({self.heater_ch_list})")
        self.keysight.write(f"SENSe:RESistance:NPLCycles {self.json_data['keysight970a_heater_NPLcycles']},({self.heater_ch_list})")
        self.keysight.write(f"SENSe:RESistance:POWer:LIMit:STATe {self.json_data['keysight970a_heater_LowPower']},({self.heater_ch_list})")
        self.keysight.write(f"SENSe:RESistance:OCOMpensated {self.json_data['keysight970a_heater_ocomp']},({self.heater_ch_list})")
        self.keysight.write("FORMat:READing:CHANnel ON")

        self.state = "resistance"

    def initialize_fan(self): #for new fans with PWM readback
        self.keysight.write(f"CONFigure:FREQuency AUTO,DEF,({self.fan_ch_list})")
        self.keysight.write(f"SENSe:FREQuency:RANGe:LOWer {self.json_data['keysight970a_fan_freqrange_lower']},({self.fan_ch_list})")
        self.keysight.write(f"SENSe:FREQuency:APERture DEF,({self.fan_ch_list})")
        self.keysight.write("FORMat:READing:CHANnel ON")
        
        self.state = "fan"

    #Sets the output channels for the HV relay control. Easier to split it into 2 blocks with separate functions
    def set_relay(self, hv, term):
        if (type(hv) != int or type(term) != int):
            print(f"{self.prefix} --> Type for hv value is {type(hv)} and type for termination value is {type(term)}")
            return 0
        if (hv < 0 or hv > 255):
            print(f"{self.prefix} --> HV value is {hv}, it needs to be between 0 and 255")
            return 0
        if (term < 0 or term > 255):
            print(f"{self.prefix} --> HV value is {term}, it needs to be between 0 and 255")
            return 0

        self.keysight.write(f"SOURce:DIGital:DATA:BYTE {hv},(@{self.json_data['keysight970a_907A_slot']}01)")
        self.keysight.write(f"SOURce:DIGital:DATA:BYTE {term},(@{self.json_data['keysight970a_907A_slot']}02)")


    def measure_rtd(self):
        if (self.state != "rtd"):
            print(f"{self.prefix} --> Tried to measure temperature without being in the temperature state! State is {self.state}!")
            return None
        #Response is something like
        #['+9.90000000E+2', '101', '+9.90000000E+2', '102', '+9.90000000E+1', '103', '+9.90000000E+0', '104\n']
        #Get rid of /n at the end of the string
        resp = self.keysight.query("READ?", delay = self.json_data['keysight970a_rtd_delay']).strip()
        #Split commas into lists
        sep = resp.split(",")
        #Make a dictionary with the channel as the key and the float reading as value
        results = {}
        for i in range(0,(self.num_rtds * 2)-1,2):
            results[self.rtd_convert[f"{sep[i+1]}"]] = float(sep[i])

        return results

    def measure_resistance(self):
        if (self.state != "resistance"):
            print(f"{self.prefix} --> Tried to measure resistance without being in the resistance state! State is {self.state}!")
            return None
        resp = self.keysight.query("READ?", delay = self.json_data['keysight970a_heater_delay']).strip()
        sep = resp.split(",")
        results = {}
        for i in range(0,(self.num_rtds * 2)-1,2):
            results[self.heater_convert[f"{sep[i+1]}"]] = float(sep[i])

        return results

    def measure_fan(self):
        if (self.state != "fan"):
            print(f"{self.prefix} --> Tried to measure fan without being in the fan state! State is {self.state}!")
            return None
        resp = self.keysight.query("READ?", delay = self.json_data['keysight970a_fan_delay']).strip()
        #Split commas into lists
        sep = resp.split(",")
        results = {}
        for i in range(0,(self.num_fans * 2)-1,2):
            results[self.fan_convert[f"{sep[i+1]}"]] = float(sep[i])

        return results     

    def beep(self):
        self.keysight.write("SYSTem:BEEPer:IMMediate")
