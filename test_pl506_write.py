from pl506 import PL506

psu = PL506(ip="169.254.12.2")

channels = [0]
#1,2,3,4,5
print("Turning on and off all channels with 48.0 V and 8 A current limit...")

for channel in channels:
   rb = psu.safe_turn_on_channel(
      channel=channel,
      voltage_v=48.0,
      current_limit_a=8.0,
      max_voltage_v=50.0,
      max_current_a=8.0,
      settle_s=5.0,)
   print(rb)

   #input("Press Enter to turn channel off...")
   #psu.channel_off(channel)
   #print(f"Channel U{channel} off.")
