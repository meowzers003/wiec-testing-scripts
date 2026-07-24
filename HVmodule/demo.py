#!/usr/bin/env python3

import gpib
import time

# GPIB board number and instrument address
BOARD = 0
ADDRESS = 9

# Open the instrument
dev = gpib.dev(BOARD, ADDRESS)

# Identify the instrument
gpib.write(dev, "*IDN?")
print("Instrument:", gpib.read(dev, 256).decode().strip())

while True:
	ch = int(input ("chn = (11-20) : ")) + 100
	# Measure DC voltage on channel 101
	gpib.write(dev, "MEAS:VOLT:DC? (@%3d)"%ch)

	result = gpib.read(dev, 256).decode().strip()

	print("Channel %3d ="%ch, result, "V")
	time.sleep(1)
