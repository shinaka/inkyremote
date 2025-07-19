#!/usr/bin/env python3

import gpiod
import gpiodevice
from gpiod.line import Bias, Direction
import time

print("""
GPIO Button Pin Scanner
=======================

This script will help you find the correct GPIO pins for your Spectra6 buttons.

Instructions:
1. For each GPIO pin tested, you'll have 3 seconds
2. Press and hold a button when prompted
3. Look for pins that show "BUTTON DETECTED!" 
4. Note the GPIO numbers that respond to button presses

Press Ctrl+C to exit early.
""")

# Common GPIO pins used for buttons on Pi displays
test_pins = [2, 3, 4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27]

try:
    # Find GPIO chip
    chip = gpiodevice.find_chip_by_platform()
    print(f"Using GPIO chip: {chip}")
    print()

    for pin in test_pins:
        try:
            print(f"Testing GPIO {pin}... Press and HOLD any button NOW!", end="", flush=True)
            
            # Request the pin as input with pull-up
            offset = chip.line_offset_from_id(pin)
            line_config = {offset: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)}
            
            with chip.request_lines(consumer="button-scanner", config=line_config) as request:
                # Read initial value
                initial_value = request.get_value(offset)
                
                # Monitor for 3 seconds
                button_detected = False
                for i in range(30):  # 30 x 0.1s = 3 seconds
                    current_value = request.get_value(offset)
                    
                    # Button press detected if value changes from 1 to 0 (pull-up inverted)
                    if initial_value == 1 and current_value == 0:
                        print(f" -> BUTTON DETECTED! GPIO {pin} changed from {initial_value} to {current_value}")
                        button_detected = True
                        time.sleep(1)  # Give time to see the message
                        break
                    
                    time.sleep(0.1)
                
                if not button_detected:
                    print(" (no button detected)")
                    
        except Exception as e:
            print(f" (error: {e})")
        
        print()

    print("\nScan complete!")
    print("\nSummary:")
    print("- Note any GPIO pins that showed 'BUTTON DETECTED!'")
    print("- Try pressing different buttons to find all 4 pins")
    print("- Common button order: A, B, C, D (top to bottom)")

except KeyboardInterrupt:
    print("\n\nScan interrupted by user")
except Exception as e:
    print(f"\nError: {e}")

print("\nTip: Run this script multiple times and press different buttons each time")
print("to identify which GPIO corresponds to which physical button.") 