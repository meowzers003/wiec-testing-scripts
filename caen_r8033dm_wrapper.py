
from caen_r8033dm import CAENR8033DM
import sys
import time

class CAENR8033DM_WRAPPER:
    def __init__(self, json_data):
        self.prefix = "CAEN R8033DM Wrapper"            #Prefix for log messages
        self.json_data = json_data
        self.caen = CAENR8033DM(json_data)      #Creates instance of lower level which holds the connection
        self.rounding_factor = 2                #When comparing floats, we need to round
        self.ramp_wait = 1                      #Time between checks when ramping up or down
        if (self.caen.caen.value == -1):
            sys.exit(f"{self.prefix} --> Device could not be intialized, returned {self.caen.caen.value}")

        #Doesn't seem to work
        # if (self.get_board_control() == self.caen.board_params['BdCtr']['Onstate']):
        #     sys.exit(f"{self.prefix} --> Board control is in Local mode, not Remote!")

        if (self.get_board_interlock() == self.caen.board_params['BdIlk']['Onstate']):
            sys.exit(f"{self.prefix} --> Board interlock has tripped!")

        if (self.get_board_status() != 0):
            sys.exit(f"{self.prefix} --> Board failed with error {hex(self.get_board_status())}")

        channels = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15]
        self.set_current_range(channels, self.json_data['caenR8033DM_current_range'])
        self.set_overcurrent(channels, self.json_data['caenR8033DM_overcurrent'])
        self.set_powerdown(channels, self.json_data['caenR8033DM_power_down_mode'])
        self.set_rampdown(channels, self.json_data['caenR8033DM_ramp_down'])
        self.set_rampup(channels, self.json_data['caenR8033DM_ramp_up'])
        self.set_trip_time(channels, self.json_data['caenR8033DM_trip_time'])
        self.set_HV_value(channels, self.json_data['caenR8033DM_term_voltage'])

        # print(self.get_channel_status(3))
        # print(self.get_channel_status([3,4,5,6, 7]))

        # self.set_powerdown([4, 5], 1)
        # self.set_HV_value([4, 5, 7], 690.42)
        # self.set_overcurrent(5, 34.35)
        # self.set_current_range(1, 0)
        # self.set_current_range(1, 1)
        # self.set_trip_time([4,5,6], [7.7,8.8,9])
        # self.set_rampdown([2,7], 50)
        # self.set_rampup([3,4,5], 45)
        # self.set_powerdown([3,4], [0,1])
        #
        # self.set_HV_value(2, 500)
        # self.set_rampup(2, 50)
        # self.set_rampdown(2, 50)
        # self.turn_on([2,7])
        # self.turn_off([2,7])
        # self.turn_on([2,7])
        # self.turn_off([2,7])


    def turn_on(self, ch):
        self.power_cycle(ch, True)

    def turn_off(self, ch, emergency=False):
        try:
            self.power_cycle(ch, False)
        except:
            if emergency: #turn off anyways
                 self.caen.set_ch_parameter(ch, "Pw", False)   
            raise                             

    def power_cycle(self, ch, up):
        if (up):
            value = 1
        else:
            value = 0
        status = self.get_channel_status(ch)
        #Make it work for both single channels and lists
        if (not isinstance(ch, list)):
            ch = [ch]
        if (not isinstance(status, list)):
            status = [status]
        #Check if there's any error in the channels before the power is touched
        for num,i in enumerate(ch):
            if (status[num] > 0x7):
                self.channel_error(i, status[num])
        #Set all the channels to turn on or off
        self.caen.set_ch_parameter(ch, "Pw", value)
        #Need the device status to update, sometimes it says it's completed before it starts
        print(f"Channel(s) starting at {self.get_voltage(ch)} V, {self.get_current(ch)} uA")        
        time.sleep(self.ramp_wait)
        print(f"Channel(s) at {self.get_voltage(ch)} V, {self.get_current(ch)} uA")
        #If any channels are ramping, wait for ramping to finish
        for num,i in enumerate(ch):
            self.get_power_status(ch[num])
            if (self.get_channel_status(ch[num]) != value):
                self.wait_for_ramp(ch[num], up)

    #Monitor the ramping of the power, while checking to see if channel status throws and error
    def wait_for_ramp(self, ch, going_up):
        secs_passed = 0
        while(True):
            #print(self.get_channel_status(ch))
            #print(self.caen.get_channel_parameter_value(ch, "Pw"))
            if (going_up):
                #if (self.get_channel_status(ch) == 1 and (self.get_HV_value(ch) - self.get_voltage(ch)) < 100 ):
                if self.get_channel_status(ch) == 1:
                    break
                print(f"{self.prefix} --> Channel {ch} is ramping up to {self.get_HV_value(ch)} V, currently at {self.get_voltage(ch)} V and {self.get_current(ch)} uA ({secs_passed} seconds passed)")
            else:
                #if (self.get_channel_status(ch) == 0 and self.get_voltage(ch) < 20) :
                if self.get_channel_status(ch) == 0:
                    break
                print(f"{self.prefix} --> Channel {ch} is ramping down to turn off, currently at {self.get_voltage(ch)} V and {self.get_current(ch)} uA ({secs_passed} seconds passed) ")
            time.sleep(self.ramp_wait)
            secs_passed = secs_passed + self.ramp_wait
            if (self.get_channel_status(ch) > 0x7):
                self.channel_error(ch, self.get_channel_status(ch))

    #These functions basically get and set different parameters of each channel, with a variable amount of channels as the input
    def get_voltage(self, ch, num_avgs=5, print_meas=False):
        return self.caen.get_channel_parameter_value(ch, "VMon", print_meas)
        
    def set_HV_value(self, ch, voltage):
        self.caen.set_ch_parameter(ch, "VSet", voltage)
        return self.get_check_channel_parameter(ch, "VSet", voltage)

    def get_HV_value(self, ch):
        return self.caen.get_channel_parameter_value(ch, "VSet")

    def set_overcurrent(self, ch, current):
        self.caen.set_ch_parameter(ch, "ISet", current)
        return self.get_check_channel_parameter(ch, "ISet", current)

    def get_overcurrent(self, ch, current):
        return self.caen.get_channel_parameter_value(ch, "ISet")

    def get_current(self, ch, num_avgs=5, print_meas=False):
        return self.caen.get_channel_parameter_value(ch, "IMon", print_meas)

    def set_current_range(self, ch, value):
        self.caen.set_ch_parameter(ch, "IMRange", value)
        return self.get_check_channel_parameter(ch, "IMRange", value)

    def get_current_range(self, ch):
        return self.caen.get_channel_parameter_value(ch, "IMRange")

    def set_trip_time(self, ch, value):
        self.caen.set_ch_parameter(ch, "Trip", value)
        return self.get_check_channel_parameter(ch, "Trip", value)

    def get_trip_time(self, ch):
        return self.caen.get_channel_parameter_value(ch, "Trip")

    def set_rampdown(self, ch, value):
        self.caen.set_ch_parameter(ch, "RDwn", value)
        return self.get_check_channel_parameter(ch, "RDwn", value)

    def get_rampdown(self, ch):
        return self.caen.get_channel_parameter_value(ch, "RDwn")

    def set_rampup(self, ch, value):
        self.caen.set_ch_parameter(ch, "RUp", value)
        return self.get_check_channel_parameter(ch, "RUp", value)

    def get_rampup(self, ch):
        return self.caen.get_channel_parameter_value(ch, "RUp")

    def set_powerdown(self, ch, value):
        self.caen.set_ch_parameter(ch, "PDwn", value)
        return self.get_check_channel_parameter(ch, "PDwn", value)

    def get_powerdown(self, ch):
        return self.caen.get_channel_parameter_value(ch, "PDwn")

    def get_channel_status(self, ch):
        return self.caen.get_channel_parameter_value(ch, "Status")

    def get_power_status(self, ch):
        return self.caen.get_channel_parameter_value(ch, "Pw")

    #After setting a parameter, this function is called to get the reading of that parameter
    #It should agree, if it doesn't, it throws an error
    #Much of the loops is just dealing with that you can send a single channel and value
    #Or multiple channels and 1 value, or multiple channels and values
    def get_check_channel_parameter(self, ch, param, value):
        resp = self.caen.get_channel_parameter_value(ch, param)
        if (isinstance(ch, list) and not isinstance(value, list)):
            for num in range(len(ch)):
                if (round(resp[num],self.rounding_factor) != value):
                    print(f"{self.prefix} --> {self.get_channel_status(ch[num])}")
                    sys.exit(f"{self.prefix} --> Wrote {value} to {param}, read back {resp} list")
        elif (isinstance(ch, list) and isinstance(value, list)):
            for num,i in enumerate(value):
                if (round(resp[num],self.rounding_factor) != i):
                    print(f"{self.prefix} --> {self.get_channel_status(ch[num])}")
                    sys.exit(f"{self.prefix} --> Wrote {value} to {param}, read back {resp} list")
        elif (round(resp,self.rounding_factor) != value):
            print(f"{self.prefix} --> {self.get_channel_status(ch)}")
            sys.exit(f"{self.prefix} --> Wrote {value} to {param}, read back {resp}")
        return resp

    #Getting board level parameters doesn't require a channel
    def get_board_status(self):
        return self.caen.get_board_parameter_value("BdStatus")

    def get_board_interlock(self):
        if (self.caen.get_board_parameter_value("BdIlk")):
            return self.caen.board_params['BdIlk']['Onstate']
        else:
            return self.caen.board_params['BdIlk']['Offstate']

    #Always seems to return Local, even when it's Remote
    def get_board_control(self):
        ret = self.caen.get_board_parameter_value("BdCtr")
        #print(ret)
        if (ret):
            return self.caen.board_params['BdCtr']['Onstate']
        else:
            return self.caen.board_params['BdCtr']['Offstate']

    #Channel status is passed here, if it's not settled or ramping up/down, I assume there's an error and throw it
    def channel_error(self, ch, val):
        if (val > 0x7):
            print(f"{self.prefix} --> Error code {hex(val)}")
            print(f"Channel {ch}: {self.get_voltage(ch)} V, {self.get_current(ch)} uA")
            if (val & 0x8):
                sys.exit(f"{self.prefix} --> Channel {ch} is overcurrent")
            if (val & 0x10):
                sys.exit(f"{self.prefix} --> Channel {ch} is overvoltage")
            if (val & 0x20):
                sys.exit(f"{self.prefix} --> Channel {ch} is undervoltage")
            if (val & 0x40):
                sys.exit(f"{self.prefix} --> Channel {ch} has tripped due to overcurrent")
            if (val & 0x80):
                sys.exit(f"{self.prefix} --> Channel {ch} is overpowered")
            if (val & 0x100):
                sys.exit(f"{self.prefix} --> Channel {ch} has a temperature warning")
            if (val & 0x200):
                sys.exit(f"{self.prefix} --> Channel {ch} is over temperature")
            if (val & 0x400):
                sys.exit(f"{self.prefix} --> Channel {ch}'s switch is in the kill state")
            if (val & 0x800):
                sys.exit(f"{self.prefix} --> Channel {ch}'s interlock is tripped")
            if (val & 0x1000):
                sys.exit(f"{self.prefix} --> Channel {ch}'s switch is in the off state")
            if (val & 0x2000):
                sys.exit(f"{self.prefix} --> Channel {ch} has a general failure")
            if (val & 0x4000):
                sys.exit(f"{self.prefix} --> Channel {ch}'s switch is on but in local mode")
            elif (val & 0x20):
                sys.exit(f"{self.prefix} --> Channel {ch}'s voltage exceeds the hardware max")
