import pyvisa
import sys
import json
import csv
import os
import time
from datetime import datetime
import openpyxl
from datetime import datetime
from rigol_dp832a import RigolDP832A
from caen_r8033dm_wrapper import CAENR8033DM_WRAPPER

class LDOmeasure:
    def __init__(self, config_file, name = None):
        self.prefix = "DUNE HV Crate Tester"
        print(f"{self.prefix} --> Welcome to the DUNE HV crate production testing script")
        with open(config_file, "r") as jsonfile:
            self.json_data = json.load(jsonfile)
        self.rm = pyvisa.ResourceManager('@py')

        #Initialize all instruments first so that you don't waste time with input if something is not connected
        self.c = CAENR8033DM_WRAPPER(self.json_data)
        self.r1 = RigolDP832A(self.rm, self.json_data, 1)
        self.r1.setup_hvpullup()
        self.r1.setup_hvpullup2()

        #Now we can get the input for the name of the test
        if (name):
            self.test_name = name
        else:
            self.test_name = input("Input the test name:\n")

        self.rounding_factor = self.json_data["rounding_factor"]
        #The datastore is the eventual output JSON file that will be written after the test
        #Want to also include what the inputs for this particular test was
        self.seconds_interval = 1
        self.minutes_duration = 5
        self.datastore = {}
        self.datastore['input_params'] = self.json_data
        self.datastore['test_name'] = self.test_name
        self.datastore['seconds_interval'] = self.seconds_interval
        self.datastore['minutes_duration'] = self.minutes_duration
        self.start_time = datetime.now()
        self.datastore['start_time'] = self.start_time
        self.sequence()

    def sequence(self):
        data = []
        self.r1.power("ON", "hvpullup")
        self.r1.power("ON", "hvpullup2")
        self.c.turn_off(0)
        self.c.set_HV_value(0, 1)
        self.c.turn_on(0)
        for i in range(120):
            print(f"{i}V")
            self.c.set_HV_value(0, i)
            time.sleep(60)
            datum = [i]
            datum.append(self.c.get_voltage(0))
            datum.append(self.c.get_current(0))
            data.append(datum)
        with open(f"{self.test_name}_scan_voltage.csv", 'w') as fp:
            csv_writer = csv.writer(fp, delimiter=',')
            csv_writer.writerows(data)

        self.c.turn_off(0)
        self.r1.power("OFF", "hvpullup")
        self.r1.power("OFF", "hvpullup2")
        input("Ready for all channel connected and positive test?")
        self.c.turn_on([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
        data = []
        cycle_start_time = time.time()
        prev_measurement = cycle_start_time - 1
        while (time.time() - cycle_start_time < (self.minutes_duration * 60)):
            if (time.time() > prev_measurement + self.seconds_interval):
                print(f"measure at {time.time()}")
                prev_measurement = prev_measurement + self.seconds_interval
                datum = [datetime.now()]
                for i in range(16):
                    datum.append(self.c.get_voltage(i))
                    datum.append(self.c.get_current(i))
                data.append(datum)
        with open(f"{self.test_name}_multiple_plugged_positive.csv", 'w') as fp:
            csv_writer = csv.writer(fp, delimiter=',')
            csv_writer.writerows(data)

        self.c.turn_off([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])

        # input("Ready for single channel test?")
        # self.c.turn_on(0)
        # data = []
        # cycle_start_time = time.time()
        # prev_measurement = cycle_start_time - 1
        # while (time.time() - cycle_start_time < (self.minutes_duration * 60)):
        #     if (time.time() > prev_measurement + self.seconds_interval):
        #         print(f"measure at {time.time()}")
        #         prev_measurement = prev_measurement + self.seconds_interval
        #         datum = [datetime.now()]
        #         datum.append(self.c.get_voltage(0))
        #         datum.append(self.c.get_current(0))
        #         data.append(datum)
        # with open(f"{self.test_name}_single.csv", 'w') as fp:
        #     csv_writer = csv.writer(fp, delimiter=',')
        #     csv_writer.writerows(data)
        #
        # self.c.turn_off(0)

        input("Ready for all channel connected test?")
        self.c.turn_on(0)
        data = []
        cycle_start_time = time.time()
        prev_measurement = cycle_start_time - 1
        while (time.time() - cycle_start_time < (self.minutes_duration * 60)):
            if (time.time() > prev_measurement + self.seconds_interval):
                print(f"measure at {time.time()}")
                prev_measurement = prev_measurement + self.seconds_interval
                datum = [datetime.now()]
                for i in range(8):
                    datum.append(self.c.get_voltage(i))
                    datum.append(self.c.get_current(i))
                data.append(datum)
        with open(f"{self.test_name}unplugged_all.csv", 'w') as fp:
            csv_writer = csv.writer(fp, delimiter=',')
            csv_writer.writerows(data)

        self.c.turn_off(0)

        input("Ready for all channel connected and positive test?")
        self.c.turn_on([0, 1, 2, 3, 4, 5, 6, 7])
        data = []
        cycle_start_time = time.time()
        prev_measurement = cycle_start_time - 1
        while (time.time() - cycle_start_time < (self.minutes_duration * 60)):
            if (time.time() > prev_measurement + self.seconds_interval):
                print(f"measure at {time.time()}")
                prev_measurement = prev_measurement + self.seconds_interval
                datum = [datetime.now()]
                for i in range(16):
                    datum.append(self.c.get_voltage(i))
                    datum.append(self.c.get_current(i))
                data.append(datum)
        with open(f"{self.test_name}_multiple_plugged_positive.csv", 'w') as fp:
            csv_writer = csv.writer(fp, delimiter=',')
            csv_writer.writerows(data)

        self.c.turn_off([0, 1, 2, 3, 4, 5, 6, 7])

        input("Ready for all channel connected and negative test?")
        self.c.turn_on([0, 8,9,10,11,12,13,14,15])
        data = []
        cycle_start_time = time.time()
        prev_measurement = cycle_start_time - 1
        while (time.time() - cycle_start_time < (self.minutes_duration * 60)):
            if (time.time() > prev_measurement + self.seconds_interval):
                print(f"measure at {time.time()}")
                prev_measurement = prev_measurement + self.seconds_interval
                datum = [datetime.now()]
                for i in range(16):
                    datum.append(self.c.get_voltage(i))
                    datum.append(self.c.get_current(i))
                data.append(datum)
        with open(f"{self.test_name}_multiple_plugged_negative.csv", 'w') as fp:
            csv_writer = csv.writer(fp, delimiter=',')
            csv_writer.writerows(data)

        self.c.turn_off([0, 8,9,10,11,12,13,14,15])

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(f"Error: You need to supply a config file for this test as the argument! You had {len(sys.argv)-1} arguments!")
    if (len(sys.argv) == 2):
        LDOmeasure(sys.argv[1])
    elif (len(sys.argv) == 3):
        LDOmeasure(sys.argv[1], sys.argv[2])
    else:
        sys.exit(f"Error: You need to supply a config file and optional test name for this program, 2 arguments max. You supplied {sys.argv}, which is {len(sys.argv)-1} arguments")
