from caen_r8033dm_wrapper import CAENR8033DM_WRAPPER
import sys
import json

class HVTest():
    def __init__(self, config_file):
        with open(config_file, "r") as jsonfile:
            self.json_data = json.load(jsonfile)

        #Initialize all instruments first so that you don't waste time with input if something is not connected
        self.c = CAENR8033DM_WRAPPER(self.json_data)

        v = 2000
        for i in range(1,16):
            self.c.set_HV_value(i, v)
            print(f"HV Test --> Turning Channel {i} HV from 0 to {v}V with open termination")

if __name__ == "__main__":
    HVTest(sys.argv[1])
