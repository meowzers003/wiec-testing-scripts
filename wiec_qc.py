import re
import subprocess
import time
import sys
import pl506 
import traceback

##### runs multiple scripts in order based on output result 

# first run dune_hv_crate_test.py, 
#       if it passes, run ptc_power.py,
#               if it passes, run wib_serial.py, 
#                      if it passes, run wib_setup.py, 
#                           if it passes, run continuity_tests.py
# at the end, shut everything off 