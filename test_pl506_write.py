from pl506 import PL506

psu = PL506(ip="192.168.91.80")

channel = 0

print("Turning on channel with 1.0 V and 0.1 A current limit...")
rb = psu.safe_turn_on_channel(
    channel=channel,
    voltage_v=1.0,
    current_limit_a=0.1,
    max_voltage_v=50.0,
    max_current_a=12.5,
    settle_s=1.0,
)

print(rb)

input("Press Enter to turn channel off...")

psu.channel_off(channel)
print("Channel off.")