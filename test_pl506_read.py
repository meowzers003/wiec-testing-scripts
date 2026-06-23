from pl506 import PL506

psu = PL506(ip="192.168.91.80")

print("Channel names:")
print(psu.list_channels())

print("\nMain switch:")
print(psu.get_raw("sysMainSwitch.0"))

print("\nChannel 0:")
print(psu.read_channel(0))