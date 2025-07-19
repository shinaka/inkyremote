#!/usr/bin/env python3

import os
import time
import logging
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple, Dict, Any
import textwrap
from datetime import datetime
import threading

# Import the Inky library
try:
    from inky.auto import auto
    INKY_AVAILABLE = True
except ImportError:
    INKY_AVAILABLE = False

from network_manager import NetworkStatus, NetworkMode

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DisplayManager:
    """Manages E-Ink display output for network status and messages."""
    
    def __init__(self, 
                 display_width: int = 800,
                 display_height: int = 480,
                 rotation: int = 0):
        
        self.display_width = display_width
        self.display_height = display_height
        self.rotation = rotation
        
        # Display state
        self._display = None
        self._display_lock = threading.Lock()
        self._last_status_display = None
        
        # Colors (for E-Ink displays)
        self.colors = {
            'white': (255, 255, 255),
            'black': (0, 0, 0),
            'red': (255, 0, 0),
            'yellow': (255, 255, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'orange': (255, 165, 0),
        }
        
        # Layout constants
        self.margin = 20
        self.line_height = 25
        self.title_font_size = 24
        self.header_font_size = 18
        self.body_font_size = 14
        self.small_font_size = 12
        
        # Font setup
        self._fonts = {}
        self._setup_fonts()
        
    def _setup_fonts(self):
        """Set up fonts for different text sizes."""
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        ]
        
        # Find available fonts
        available_font = None
        for font_path in font_paths:
            if os.path.exists(font_path):
                available_font = font_path
                break
        
        try:
            if available_font:
                self._fonts = {
                    'title': ImageFont.truetype(available_font, self.title_font_size),
                    'header': ImageFont.truetype(available_font, self.header_font_size),
                    'body': ImageFont.truetype(available_font, self.body_font_size),
                    'small': ImageFont.truetype(available_font, self.small_font_size),
                }
                logger.info(f"Using font: {available_font}")
            else:
                # Fall back to default font
                self._fonts = {
                    'title': ImageFont.load_default(),
                    'header': ImageFont.load_default(),
                    'body': ImageFont.load_default(),
                    'small': ImageFont.load_default(),
                }
                logger.warning("Using default fonts - text may not look optimal")
                
        except Exception as e:
            logger.error(f"Error loading fonts: {e}")
            # Use default fonts as fallback
            default_font = ImageFont.load_default()
            self._fonts = {
                'title': default_font,
                'header': default_font,
                'body': default_font,
                'small': default_font,
            }
    
    def initialize_display(self) -> bool:
        """Initialize the E-Ink display."""
        if not INKY_AVAILABLE:
            logger.error("Inky library not available - display functionality disabled")
            return False
            
        try:
            with self._display_lock:
                self._display = auto(ask_user=False, verbose=True)
                logger.info(f"Initialized display: {self._display.width}x{self._display.height}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")
            return False
    
    def _create_status_image(self, status: NetworkStatus) -> Image.Image:
        """Create an image showing the current network status."""
        # Create image
        img = Image.new('RGB', (self.display_width, self.display_height), self.colors['white'])
        draw = ImageDraw.Draw(img)
        
        y = self.margin
        
        # Title
        title = "InkyRemote Network Status"
        draw.text((self.margin, y), title, font=self._fonts['title'], fill=self.colors['black'])
        y += self.title_font_size + 15
        
        # Current time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((self.margin, y), f"Last updated: {current_time}", 
                 font=self._fonts['small'], fill=self.colors['black'])
        y += self.small_font_size + 20
        
        # Network mode section
        mode_text = self._get_mode_display_text(status.mode)
        mode_color = self._get_mode_color(status.mode)
        
        draw.text((self.margin, y), "Network Mode:", font=self._fonts['header'], fill=self.colors['black'])
        y += self.header_font_size + 5
        
        draw.text((self.margin + 20, y), mode_text, font=self._fonts['body'], fill=mode_color)
        y += self.body_font_size + 15
        
        # Connection details
        if status.mode == NetworkMode.WIFI and status.ssid:
            # WiFi details
            draw.text((self.margin, y), "WiFi Connection:", font=self._fonts['header'], fill=self.colors['black'])
            y += self.header_font_size + 5
            
            details = [
                f"Network: {status.ssid}",
                f"IP Address: {status.ip_address or 'Not available'}",
            ]
            
            if status.signal_strength is not None:
                signal_quality = self._get_signal_quality(status.signal_strength)
                details.append(f"Signal: {status.signal_strength} dBm ({signal_quality})")
            
            details.append(f"Internet: {'Available' if status.is_internet_available else 'Not available'}")
            
            for detail in details:
                draw.text((self.margin + 20, y), detail, font=self._fonts['body'], fill=self.colors['black'])
                y += self.body_font_size + 3
                
        elif status.mode == NetworkMode.AP:
            # Access Point details
            draw.text((self.margin, y), "Access Point:", font=self._fonts['header'], fill=self.colors['black'])
            y += self.header_font_size + 5
            
            details = [
                f"Network Name: {status.ssid}",
                f"IP Address: {status.ip_address}",
                f"Connected Devices: {status.connected_clients}",
                "Password: inkyremote123",
            ]
            
            for detail in details:
                draw.text((self.margin + 20, y), detail, font=self._fonts['body'], fill=self.colors['black'])
                y += self.body_font_size + 3
                
        y += 20
        
        # Instructions
        draw.text((self.margin, y), "Button Controls:", font=self._fonts['header'], fill=self.colors['black'])
        y += self.header_font_size + 5
        
        instructions = [
            "Button A: Toggle WiFi/AP mode",
            "Button B: Show this status",
            "Hold Button C: Force WiFi mode",
            "Hold Button D: Force AP mode",
        ]
        
        for instruction in instructions:
            draw.text((self.margin + 20, y), instruction, font=self._fonts['body'], fill=self.colors['black'])
            y += self.body_font_size + 3
        
        return img
    
    def _create_message_image(self, title: str, message: str, message_type: str = "info") -> Image.Image:
        """Create an image displaying a message."""
        img = Image.new('RGB', (self.display_width, self.display_height), self.colors['white'])
        draw = ImageDraw.Draw(img)
        
        y = self.margin
        
        # Title bar with colored background
        title_color = self._get_message_color(message_type)
        title_bg_height = self.title_font_size + 20
        
        # Draw colored background for title
        draw.rectangle([0, y - 10, self.display_width, y + title_bg_height], fill=title_color)
        
        # Title text
        draw.text((self.margin, y), title, font=self._fonts['title'], fill=self.colors['white'])
        y += title_bg_height + 20
        
        # Message content
        # Wrap text to fit display width
        max_chars_per_line = (self.display_width - 2 * self.margin) // 8  # Rough estimate
        wrapped_lines = textwrap.wrap(message, width=max_chars_per_line)
        
        for line in wrapped_lines:
            draw.text((self.margin, y), line, font=self._fonts['body'], fill=self.colors['black'])
            y += self.body_font_size + 3
            
            # Don't overflow the display
            if y > self.display_height - self.margin - self.body_font_size:
                break
        
        # Timestamp
        y = self.display_height - self.margin - self.small_font_size
        timestamp = datetime.now().strftime("%H:%M:%S")
        draw.text((self.margin, y), timestamp, font=self._fonts['small'], fill=self.colors['black'])
        
        return img
    
    def _get_mode_display_text(self, mode: NetworkMode) -> str:
        """Get human-readable text for network mode."""
        mode_texts = {
            NetworkMode.WIFI: "Connected to WiFi",
            NetworkMode.AP: "Access Point Mode",
            NetworkMode.TRANSITIONING: "Switching modes...",
            NetworkMode.UNKNOWN: "Unknown / Initializing",
        }
        return mode_texts.get(mode, "Unknown")
    
    def _get_mode_color(self, mode: NetworkMode) -> Tuple[int, int, int]:
        """Get color for network mode display."""
        mode_colors = {
            NetworkMode.WIFI: self.colors['green'],
            NetworkMode.AP: self.colors['blue'],
            NetworkMode.TRANSITIONING: self.colors['orange'],
            NetworkMode.UNKNOWN: self.colors['red'],
        }
        return mode_colors.get(mode, self.colors['black'])
    
    def _get_message_color(self, message_type: str) -> Tuple[int, int, int]:
        """Get color for message type."""
        type_colors = {
            'info': self.colors['blue'],
            'success': self.colors['green'],
            'warning': self.colors['orange'],
            'error': self.colors['red'],
        }
        return type_colors.get(message_type, self.colors['blue'])
    
    def _get_signal_quality(self, signal_strength: int) -> str:
        """Convert signal strength to quality description."""
        if signal_strength >= -50:
            return "Excellent"
        elif signal_strength >= -60:
            return "Good"
        elif signal_strength >= -70:
            return "Fair"
        else:
            return "Poor"
    
    def _update_display(self, image: Image.Image, saturation: float = 0.5) -> bool:
        """Update the physical E-Ink display with an image."""
        if not self._display:
            logger.error("Display not initialized")
            return False
        
        try:
            with self._display_lock:
                # Resize image to display resolution
                resized_image = image.resize(self._display.resolution)
                
                # Set the image on the display
                try:
                    self._display.set_image(resized_image, saturation=saturation)
                except TypeError:
                    # Fallback for displays that don't support saturation
                    self._display.set_image(resized_image)
                
                # Update the display
                self._display.show()
                
                logger.info("Display updated successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update display: {e}")
            return False
    
    def show_network_status(self, status: NetworkStatus, saturation: float = 0.5) -> bool:
        """Display network status on the E-Ink screen."""
        logger.info(f"Displaying network status: {status.mode.value}")
        
        try:
            # Create status image
            status_image = self._create_status_image(status)
            
            # Update display
            success = self._update_display(status_image, saturation)
            
            if success:
                self._last_status_display = time.time()
            
            return success
            
        except Exception as e:
            logger.error(f"Error displaying network status: {e}")
            return False
    
    def show_message(self, 
                     title: str, 
                     message: str, 
                     message_type: str = "info",
                     duration: Optional[float] = None,
                     saturation: float = 0.5) -> bool:
        """Display a message on the E-Ink screen."""
        logger.info(f"Displaying message: {title}")
        
        try:
            # Create message image
            message_image = self._create_message_image(title, message, message_type)
            
            # Update display
            success = self._update_display(message_image, saturation)
            
            # Auto-restore previous display after duration
            if success and duration and self._last_status_display:
                def restore_status():
                    time.sleep(duration)
                    # Could implement status restoration here if needed
                    logger.info("Message display duration expired")
                
                threading.Thread(target=restore_status, daemon=True).start()
            
            return success
            
        except Exception as e:
            logger.error(f"Error displaying message: {e}")
            return False
    
    def show_connection_change(self, old_mode: NetworkMode, new_mode: NetworkMode) -> bool:
        """Show a quick message about network mode change."""
        messages = {
            (NetworkMode.WIFI, NetworkMode.AP): ("Switched to Access Point", "WiFi connection lost. Now in AP mode."),
            (NetworkMode.AP, NetworkMode.WIFI): ("Connected to WiFi", "Successfully connected to your WiFi network."),
            (NetworkMode.UNKNOWN, NetworkMode.WIFI): ("WiFi Connected", "Successfully connected to WiFi."),
            (NetworkMode.UNKNOWN, NetworkMode.AP): ("Access Point Started", "InkyRemote AP is now available."),
        }
        
        title, message = messages.get((old_mode, new_mode), ("Network Mode Changed", f"Switched from {old_mode.value} to {new_mode.value}"))
        message_type = "success" if new_mode in [NetworkMode.WIFI, NetworkMode.AP] else "info"
        
        return self.show_message(title, message, message_type, duration=5.0)
    
    def test_display(self) -> bool:
        """Test the display with a simple message."""
        return self.show_message(
            "Display Test",
            "InkyRemote display is working! This is a test message to verify the E-Ink display functionality.",
            "info"
        )

# Global display manager instance
display_manager = DisplayManager()

# Test mode when run directly
if __name__ == "__main__":
    import sys
    from network_manager import NetworkStatus, NetworkMode
    
    try:
        if not display_manager.initialize_display():
            print("Failed to initialize display")
            sys.exit(1)
        
        print("Testing display...")
        
        # Test message display
        display_manager.show_message(
            "InkyRemote Test", 
            "Testing the display manager functionality. This message should appear on your E-Ink display.",
            "info"
        )
        
        time.sleep(3)
        
        # Test status display
        test_status = NetworkStatus(
            mode=NetworkMode.AP,
            ssid="InkyRemote",
            ip_address="192.168.4.1",
            connected_clients=1,
            is_internet_available=False
        )
        
        display_manager.show_network_status(test_status)
        
        print("Display test completed")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1) 