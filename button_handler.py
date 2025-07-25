#!/usr/bin/env python3

import gpiod
import gpiodevice
from gpiod.line import Bias, Direction, Edge
import threading
import time
import logging
from typing import Callable, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ButtonAction(Enum):
    NETWORK_TOGGLE = "network_toggle"
    STATUS_DISPLAY = "status_display"
    WIFI_MODE = "wifi_mode"
    AP_MODE = "ap_mode"

@dataclass
class ButtonConfig:
    gpio_pin: int
    label: str
    action: ButtonAction
    hold_time: float = 0.0  # Minimum hold time in seconds (0 = single press)

class ButtonHandler:
    """Handles GPIO button presses for the Spectra6 E-Ink display."""
    
    def __init__(self):
        # GPIO pins for each button (these may need to be adjusted for your specific display)
        # These correspond to buttons A, B, C and D respectively
        self.SW_A = 5
        self.SW_B = 6
        self.SW_C = 16  # Use 25 if you have a 13.3" display or different revision
        self.SW_D = 24
        
        # Button configurations (simplified - all immediate press actions)
        self.button_configs = {
            self.SW_A: ButtonConfig(
                gpio_pin=self.SW_A,
                label="A",
                action=ButtonAction.NETWORK_TOGGLE,
                hold_time=0.0
            ),
            self.SW_B: ButtonConfig(
                gpio_pin=self.SW_B,
                label="B", 
                action=ButtonAction.STATUS_DISPLAY,
                hold_time=0.0
            ),
            self.SW_C: ButtonConfig(
                gpio_pin=self.SW_C,
                label="C",
                action=ButtonAction.WIFI_MODE,
                hold_time=0.0  # Simplified to immediate press
            ),
            self.SW_D: ButtonConfig(
                gpio_pin=self.SW_D,
                label="D",
                action=ButtonAction.AP_MODE,
                hold_time=0.0  # Simplified to immediate press
            )
        }
        
        self.buttons = [self.SW_A, self.SW_B, self.SW_C, self.SW_D]
        self.labels = ["A", "B", "C", "D"]
        
        # GPIO setup
        self.chip = None
        self.request = None
        self.offsets = None
        
        # Threading
        self._monitoring_thread = None
        self._should_monitor = False
        
        # Callbacks
        self._button_callbacks = {}
        
        # Rate limiting
        self._last_press_times = {}
        self._debounce_time = 0.2  # 200ms debounce
        
    def add_button_callback(self, action: ButtonAction, callback: Callable[[str], None]):
        """Add a callback for a specific button action."""
        self._button_callbacks[action] = callback
        
    def remove_button_callback(self, action: ButtonAction):
        """Remove a callback for a specific button action."""
        if action in self._button_callbacks:
            del self._button_callbacks[action]
    
    def _execute_callback(self, action: ButtonAction, button_label: str):
        """Execute the callback for a button action."""
        if action in self._button_callbacks:
            try:
                self._button_callbacks[action](button_label)
            except Exception as e:
                logger.error(f"Error in button callback for {action}: {e}")
    
    def _is_debounced(self, gpio_pin: int) -> bool:
        """Check if button press is within debounce period."""
        current_time = time.time()
        last_press = self._last_press_times.get(gpio_pin, 0)
        
        if current_time - last_press < self._debounce_time:
            return False
            
        self._last_press_times[gpio_pin] = current_time
        return True
    
    def _handle_button_press(self, event):
        """Handle button press events (simplified approach like Pimoroni example)."""
        try:
            # Get button info
            gpio_number = self.buttons[self.offsets.index(event.line_offset)]
            config = self.button_configs[gpio_number]
            
            # Debounce check
            if not self._is_debounced(gpio_number):
                return
            
            logger.info(f"Button {config.label} pressed (GPIO {gpio_number})")
            
            # For simplicity, treat all buttons as immediate press (no hold detection for now)
            # This matches the working Pimoroni example behavior
            self._execute_callback(config.action, config.label)
                
        except Exception as e:
            logger.error(f"Error handling button press: {e}")
    
    def _monitoring_loop(self):
        """Main button monitoring loop."""
        logger.info("Button monitoring started")
        
        try:
            while self._should_monitor:
                # Simple event reading (matches working Pimoroni example)
                for event in self.request.read_edge_events():
                    # Only handle falling edge (button press) since we configured FALLING only
                    self._handle_button_press(event)
                        
        except Exception as e:
            logger.error(f"Error in button monitoring loop: {e}")
            logger.error("Button monitoring thread crashed - this explains why buttons don't work")
        finally:
            logger.info("Button monitoring stopped")
    
    def initialize(self) -> bool:
        """Initialize GPIO for button monitoring."""
        try:
            logger.info("Initializing button handler...")
            
            # Find the GPIO chip
            self.chip = gpiodevice.find_chip_by_platform()
            logger.info(f"Using GPIO chip: {self.chip}")
            
            # Create settings for input pins with pull-up and edge detection
            # Use FALLING edge only (matches working Pimoroni example)
            input_settings = gpiod.LineSettings(
                direction=Direction.INPUT, 
                bias=Bias.PULL_UP, 
                edge_detection=Edge.FALLING  # Only detect button press (falling edge)
            )
            
            # Build configuration for each button
            self.offsets = [self.chip.line_offset_from_id(id) for id in self.buttons]
            line_config = dict.fromkeys(self.offsets, input_settings)
            
            # Request the GPIO lines
            self.request = self.chip.request_lines(
                consumer="inkyremote-buttons", 
                config=line_config
            )
            
            logger.info("Button GPIO initialized successfully")
            logger.info("Button mappings:")
            for button, config in self.button_configs.items():
                logger.info(f"  Button {config.label} (GPIO {button}): {config.action.value} (press)")
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize button handler: {e}")
            return False
    
    def start_monitoring(self):
        """Start button monitoring in background thread."""
        if not self.request:
            logger.error("Button handler not initialized")
            return False
            
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Button monitoring already started")
            return True
        
        self._should_monitor = True
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        
        logger.info("Button monitoring thread started")
        return True
    
    def is_monitoring(self):
        """Check if button monitoring is currently active."""
        return (self._monitoring_thread and 
                self._monitoring_thread.is_alive() and 
                self._should_monitor)
    
    def stop_monitoring(self):
        """Stop button monitoring."""
        self._should_monitor = False
        
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
            
        logger.info("Button monitoring stopped")
    
    def cleanup(self):
        """Clean up GPIO resources."""
        try:
            self.stop_monitoring()
            
            if self.request:
                self.request.release()
                self.request = None
                
            self.chip = None
            logger.info("Button handler cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during button handler cleanup: {e}")
    
    def test_buttons(self, duration: int = 10):
        """Test button functionality by monitoring for a specified duration."""
        print(f"\n=== Button Test Mode ===")
        print(f"Testing buttons for {duration} seconds...")
        print(f"Button mappings:")
        for config in self.button_configs.values():
            print(f"  Button {config.label}: {config.action.value} (single press)")
        print(f"Press Ctrl+C to exit early\n")
        
        def test_callback(action_name: str, button_label: str):
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] Button {button_label} triggered action: {action_name}")
        
        # Add test callbacks
        for action in ButtonAction:
            self.add_button_callback(action, lambda label, a=action.value: test_callback(a, label))
        
        try:
            start_time = time.time()
            while time.time() - start_time < duration:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nTest interrupted by user")
            
        finally:
            # Clean up test callbacks
            for action in ButtonAction:
                self.remove_button_callback(action)
            
            print("Button test completed")

# Global button handler instance
button_handler = ButtonHandler()

# Test mode when run directly
if __name__ == "__main__":
    import sys
    
    try:
        if not button_handler.initialize():
            print("Failed to initialize button handler")
            sys.exit(1)
            
        if not button_handler.start_monitoring():
            print("Failed to start button monitoring")
            sys.exit(1)
        
        # Run test mode
        button_handler.test_buttons(30)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        button_handler.cleanup() 