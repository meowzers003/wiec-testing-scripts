from pl506 import PL506

psu = PL506(ip="169.254.12.2")

channel = 0
#1,2,3,4,5


psu.channel_off(channel)
print(f"Channel U{channel} off.")
