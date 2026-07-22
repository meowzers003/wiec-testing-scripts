import os, sys
import csv
import json
import matplotlib
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import numpy as np
from scipy.optimize import curve_fit
from dune_hv_crate_test import LDOmeasure

class JustPlot:
    def __init__(self, path):
        self.orig = LDOmeasure()
        self.orig.results_path = path
        self.test_name = self.get_test_name()

    def get_test_name(self):
        for f in os.listdir(self.orig.results_path):
            if f.endswith(".json"):
                json_file = os.path.join(self.orig.results_path, f)
                with open(json_file, "r") as jsonfile:
                    self.json_data = json.load(jsonfile)
                    return (self.json_data["test_name"])

    def plot_multiple(self, base, timestamps):
        self.multiplot(base, timestamps, "_ch0_pos_open_on", 0, "c", "Open termination, charging current, 0V to 2000V", 'upper right')
        self.multiplot(base, timestamps, "_ch0_neg_open_on", 8, "c", "Open termination, charging current, 0V to -2000V", 'upper right')
        self.multiplot(base, timestamps, "_ch0_pos_open_off", 0, "v", "Open termination, relaxing voltage, 2000V to 0V", 'upper right')
        self.multiplot(base, timestamps, "_ch0_neg_open_off", 8, "v", "Open termination, relaxing voltage, -2000V to 0V", 'upper right')

        self.multiplot(base, timestamps, "_ch0_pos_term_on", 0, "c", "10k Termination, charging current, 0V to 20V", 'lower right')
        self.multiplot(base, timestamps, "_ch0_neg_term_on", 8, "c", "10k Termination, charging current, 0V to -20V", 'lower right')
        self.multiplot(base, timestamps, "_ch0_pos_term_off", 0, "v", "10k Termination, relaxing voltage, 20V to 0V", 'upper right')
        self.multiplot(base, timestamps, "_ch0_neg_term_off", 8, "v", "10k Termination, relaxing voltage, -20V to 0V", 'upper right')

    def multiplot(self, base, timestamps, test, ch_num, vc, title, loc):
        num = len(timestamps)
        arr = [i+1 for i in range(num)]
        times = []
        volts = []
        currs = []
        for ts, ch in zip(timestamps, arr):
            filename = os.path.join(base, ts, f"channel{ch}{test}.csv")
            print(filename)
            time, volt, curr = self.get_ch_data(filename, ch_num)
            times.append(time)
            volts.append(volt)
            currs.append(curr)

        fig = plt.figure(figsize=(16, 12), dpi=80)
        ax = fig.add_subplot(1,1,1)
        #print(currs)
        if (vc == "c"):
            for num,(t,c) in enumerate(zip(times,currs)):
                ax.plot(t, c, label=f"Ch{num} Current")
            ax.set_ylabel("Current (uA)", fontsize=24)
        elif (vc == "v"):
            for num,(t,v) in enumerate(zip(times,volts)):
                ax.plot(t, v, label=f"Ch{num} Voltage")
            ax.set_ylabel("Voltage (V)", fontsize=24)
        self.format_plot(ax)

        fig.suptitle((title), fontsize=36)
        ax.set_xlabel("Time (Minutes:Seconds)", fontsize=24)


        # ax.set_xlim([0,150])

        ax.legend(loc=loc, prop={'size': 20}, ncol=2)
        ax.yaxis.set_major_formatter('{x:9<5.3f}')
        fig.savefig(os.path.join(base, f"multiple{test}.png"))
        plt.close(fig)

    def format_plot(self, ax):
        tick_size = 18
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%M:%S'))
        ax.tick_params(axis='x', labelsize=tick_size, colors='black')  # Set tick size and color here
        ax.tick_params(axis='y', labelsize=tick_size, colors='black')  # Set tick size and color here
        ax.get_yaxis().set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, p: format(int(x), ',')))

if __name__ == "__main__":
    jp = JustPlot("/home/dune-daq/DUNE-HV-Crate-Testing/results/20240708162535")

    jp.orig.make_plot(f"{jp.test_name}_ch0_pos_open_on.csv", "0 to 2000V, open termination redid", 0, fit = None, axes = [1990, 2030])

    #results_path = "/home/dune-daq/DUNE-HV-Crate-Testing/results"
    #jp.plot_multiple(results_path, ["20240318142641", "20240318151109", "20240318155445", "20240318163921", "20240318172152", "20240318180505", "20240319102102", "20240319110328"])
    #sys.exit("Done with multiple plotting")
