#!/usr/bin/env python3

import subprocess
import time
import threading
import logging
import os
import json
from typing import Dict, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkMode(Enum):
    WIFI = "wifi"
    AP = "access_point"
    TRANSITIONING = "transitioning"
    UNKNOWN = "unknown"

@dataclass
class NetworkStatus:
    mode: NetworkMode
    ssid: Optional[str] = None
    ip_address: Optional[str] = None
    connected_clients: int = 0
    signal_strength: Optional[int] = None
    is_internet_available: bool = False

class NetworkManager:
    """Manages WiFi and Access Point mode switching for Pi Zero W2."""
    
    def __init__(self, 
                 wifi_interface: str = "wlan0",
                 ap_ssid: str = "InkyRemote",
                 ap_password: str = "inkyremote123",
                 check_interval: int = 60,
                 connectivity_timeout: int = 5):
        
        self.wifi_interface = wifi_interface
        self.ap_ssid = ap_ssid
        self.ap_password = ap_password
        self.check_interval = check_interval
        self.connectivity_timeout = connectivity_timeout
        
        self._current_mode = NetworkMode.UNKNOWN
        self._status_callbacks = []
        self._monitoring_thread = None
        self._should_monitor = False
        self._manual_ap_mode = False  # Flag to track manual AP mode activation
        self._manual_control = False  # Flag to disable automatic monitoring completely
        
        # Configuration file paths
        self.hostapd_conf = "/etc/hostapd/hostapd.conf"
        self.dnsmasq_conf = "/etc/dnsmasq.conf"
        self.dhcpcd_conf = "/etc/dhcpcd.conf"
        
    def add_status_callback(self, callback: Callable[[NetworkStatus], None]):
        """Add a callback function to be called when network status changes."""
        self._status_callbacks.append(callback)
        
    def remove_status_callback(self, callback: Callable[[NetworkStatus], None]):
        """Remove a status callback function."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    def _notify_status_change(self, status: NetworkStatus):
        """Notify all registered callbacks of status change."""
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")
    
    def _run_command(self, command: str, timeout: int = 10, suppress_errors: bool = False) -> Tuple[bool, str]:
        """Execute a shell command and return (success, output)."""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            
            if not success and not suppress_errors:
                logger.warning(f"Command failed: {command}")
                logger.warning(f"Error: {output}")
                
            return success, output.strip()
            
        except subprocess.TimeoutExpired:
            if not suppress_errors:
                logger.error(f"Command timed out: {command}")
            return False, "Command timed out"
        except Exception as e:
            if not suppress_errors:
                logger.error(f"Error running command '{command}': {e}")
            return False, str(e)
    
    def check_wifi_connectivity(self) -> bool:
        """Check if WiFi is connected (lightweight check)."""
        # Quick check - if we have an IP address on wlan0, assume WiFi is working
        # This is much lighter than doing iwconfig + ping tests
        success, output = self._run_command(
            f"ip addr show {self.wifi_interface} | grep 'inet.*scope global'", 
            suppress_errors=True
        )
        
        if success and output:
            return True
            
        # Fallback - check iwconfig if IP check failed
        success, output = self._run_command(
            f"iwconfig {self.wifi_interface}", 
            suppress_errors=True
        )
        
        return success and "ESSID:off" not in output
    
    def _test_internet_connection(self) -> bool:
        """Test internet connectivity by pinging a reliable server."""
        success, _ = self._run_command(
            f"ping -c 1 -W {self.connectivity_timeout} 8.8.8.8", 
            timeout=self.connectivity_timeout + 5,
            suppress_errors=True
        )
        return success
    
    def get_wifi_info(self) -> Dict[str, Optional[str]]:
        """Get current WiFi connection information."""
        info = {
            'ssid': None,
            'ip_address': None,
            'signal_strength': None
        }
        
        # Get SSID
        success, output = self._run_command(
            f"iwconfig {self.wifi_interface} | grep ESSID", 
            suppress_errors=True
        )
        if success and 'ESSID:' in output:
            try:
                info['ssid'] = output.split('ESSID:')[1].strip().strip('"')
                if info['ssid'] == 'off/any':
                    info['ssid'] = None
            except IndexError:
                pass
        
        # Get IP address
        success, output = self._run_command(
            f"hostname -I", 
            suppress_errors=True
        )
        if success and output:
            info['ip_address'] = output.split()[0]
        
        # Get signal strength
        success, output = self._run_command(
            f"iwconfig {self.wifi_interface} | grep 'Signal level'", 
            suppress_errors=True
        )
        if success and 'Signal level=' in output:
            try:
                signal_part = output.split('Signal level=')[1].split()[0]
                info['signal_strength'] = int(signal_part.replace('dBm', ''))
            except (IndexError, ValueError):
                pass
        
        return info
    
    def get_ap_clients(self) -> int:
        """Get number of connected AP clients."""
        success, output = self._run_command(
            "iw dev wlan0 station dump | grep Station | wc -l", 
            suppress_errors=True
        )
        if success and output.isdigit():
            return int(output)
        return 0
    
    def start_access_point(self) -> bool:
        """Start Access Point mode using NetworkManager native hotspot."""
        logger.info("Starting NetworkManager hotspot...")
        self._current_mode = NetworkMode.TRANSITIONING
        
        try:
            # Remove any existing hotspot connections first
            logger.info("Cleaning up existing hotspot connections...")
            self._run_command("sudo nmcli connection delete Hotspot", suppress_errors=True)
            time.sleep(2)
            
            # Create NetworkManager native hotspot
            logger.info(f"Creating NetworkManager hotspot: {self.ap_ssid}")
            success, output = self._run_command(
                f"sudo nmcli device wifi hotspot ssid {self.ap_ssid} password {self.ap_password} ifname {self.wifi_interface} band bg"
            )
            
            if not success:
                logger.error(f"Failed to create NetworkManager hotspot: {output}")
                self._current_mode = NetworkMode.UNKNOWN
                return False
            
            # Wait for hotspot to initialize
            time.sleep(5)
            
            # Verify hotspot is active
            success, output = self._run_command("sudo nmcli connection show --active")
            if "Hotspot" not in output:
                logger.error("Hotspot connection not found in active connections")
                logger.warning(f"Active connections: {output}")
                self._current_mode = NetworkMode.UNKNOWN
                return False
            
            self._current_mode = NetworkMode.AP
            logger.info("NetworkManager hotspot started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error starting NetworkManager hotspot: {e}")
            self._current_mode = NetworkMode.UNKNOWN
            return False
    
    def stop_access_point(self) -> bool:
        """Stop NetworkManager hotspot."""
        logger.info("Stopping NetworkManager hotspot...")
        self._current_mode = NetworkMode.TRANSITIONING
        
        try:
            # Find and stop hotspot connection
            success, output = self._run_command("sudo nmcli connection show --active", suppress_errors=True)
            if "Hotspot" in output:
                logger.info("Stopping active hotspot connection...")
                success, output = self._run_command("sudo nmcli connection down Hotspot")
                if not success:
                    logger.warning(f"Failed to stop hotspot: {output}")
            else:
                logger.info("No active hotspot found")
            
            # Delete hotspot connection completely to clean up
            self._run_command("sudo nmcli connection delete Hotspot", suppress_errors=True)
            
            logger.info("NetworkManager hotspot stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping NetworkManager hotspot: {e}")
            return False
    
    def connect_to_wifi(self) -> bool:
        """Attempt to connect to WiFi."""
        logger.info("Attempting to connect to WiFi...")
        
        # Check if we need to stop AP mode BEFORE changing the mode
        was_ap_mode = (self._current_mode == NetworkMode.AP)
        self._current_mode = NetworkMode.TRANSITIONING
        
        try:
            # Stop AP mode if it was running
            if was_ap_mode:
                logger.info("Stopping hotspot before switching to WiFi...")
                self.stop_access_point()
            
            # NetworkManager will automatically handle WiFi reconnection
            logger.info("Waiting for NetworkManager to reconnect to WiFi...")
            
            # Restart networking services (adapt for dhclient system)
            success, _ = self._run_command("sudo systemctl restart networking")
            if not success:
                # Try dhclient directly if networking service fails
                self._run_command("sudo dhclient -r wlan0", suppress_errors=True)
                success, _ = self._run_command("sudo dhclient wlan0")
                if not success:
                    logger.warning("Failed to restart networking services")
            
            # Wait a moment for networking to initialize
            time.sleep(5)
            
            # Try to reconnect to WiFi
            success, _ = self._run_command("sudo wpa_cli -i wlan0 reconnect")
            if not success:
                logger.error("Failed to reconnect to WiFi")
                return False
            
            # Wait for connection
            for i in range(20):  # Wait up to 20 seconds
                if self.check_wifi_connectivity():
                    self._current_mode = NetworkMode.WIFI
                    logger.info("WiFi connection established")
                    return True
                time.sleep(1)
            
            logger.warning("WiFi connection timeout")
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to WiFi: {e}")
            return False
    
    def get_current_status(self) -> NetworkStatus:
        """Get current network status."""
        if self._current_mode == NetworkMode.WIFI:
            wifi_info = self.get_wifi_info()
            return NetworkStatus(
                mode=NetworkMode.WIFI,
                ssid=wifi_info['ssid'],
                ip_address=wifi_info['ip_address'],
                signal_strength=wifi_info['signal_strength'],
                is_internet_available=self._test_internet_connection()
            )
        elif self._current_mode == NetworkMode.AP:
            # Get NetworkManager hotspot IP address
            ap_ip = "10.42.0.1"  # Default NetworkManager hotspot IP
            
            # Try to get the actual IP from the interface
            success, output = self._run_command("ip addr show wlan0", suppress_errors=True)
            if success:
                import re
                # Look for NetworkManager hotspot IP ranges (10.42.0.x or similar)
                matches = re.findall(r'inet (\d+\.\d+\.\d+\.\d+)/\d+', output)
                for ip in matches:
                    # NetworkManager typically uses 10.42.0.x range for hotspots
                    if ip.startswith('10.42.') or ip.startswith('172.20.') or ip.startswith('192.168.4.'):
                        ap_ip = ip
                        break
            
            logger.info(f"AP mode IP: {ap_ip}")
            return NetworkStatus(
                mode=NetworkMode.AP,
                ssid=self.ap_ssid,
                ip_address=ap_ip,
                connected_clients=self.get_ap_clients(),
                is_internet_available=False
            )
        else:
            return NetworkStatus(mode=self._current_mode)
    
    def switch_to_ap_mode(self, manual: bool = False) -> bool:
        """Switch to Access Point mode - BUTTON CONTROL ONLY."""
        logger.info("Switching to AP mode...")
        
        if self._current_mode == NetworkMode.AP:
            logger.info("Already in AP mode")
            return True
            
        success = self.start_access_point()
        if success:
            status = self.get_current_status()
            self._notify_status_change(status)
        return success
    
    def switch_to_wifi_mode(self, manual: bool = False) -> bool:
        """Switch to WiFi mode - BUTTON CONTROL ONLY."""
        logger.info("Switching to WiFi mode...")
        
        if self._current_mode == NetworkMode.WIFI and self.check_wifi_connectivity():
            logger.info("Already connected to WiFi")
            return True
            
        success = self.connect_to_wifi()
        if success:
            status = self.get_current_status()
            self._notify_status_change(status)
        return success
    
    def toggle_mode(self) -> bool:
        """Toggle between WiFi and AP mode - BUTTON CONTROL ONLY."""
        logger.info(f"Toggling mode from {self._current_mode}")
        
        if self._current_mode == NetworkMode.WIFI:
            return self.switch_to_ap_mode(manual=True)
        else:
            return self.switch_to_wifi_mode(manual=True)
    
    def enable_automatic_mode(self) -> bool:
        """Enable automatic network mode switching."""
        logger.info("Enabling automatic network mode switching")
        self._manual_control = False
        self._manual_ap_mode = False
        return True
    
    def _monitoring_loop(self):
        """Background monitoring loop - DISABLED for button-only control."""
        logger.info("Network monitoring disabled - using button control only")
        
        # Just sleep and do nothing - monitoring is disabled
        while self._should_monitor:
            time.sleep(60)  # Long sleep since we're not doing anything
        
        logger.info("Network monitoring thread stopped")
    
    def start_monitoring(self):
        """Start background network monitoring."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Monitoring already started")
            return
        
        self._should_monitor = True
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        logger.info("Network monitoring thread started")
    
    def stop_monitoring(self):
        """Stop background network monitoring."""
        self._should_monitor = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("Network monitoring stopped")
    
    def initialize(self) -> bool:
        """Initialize network manager and determine current state - BUTTON CONTROL ONLY."""
        logger.info("Initializing NetworkManager in button-control mode...")
        
        # Just detect current state without auto-switching
        if self.check_wifi_connectivity():
            self._current_mode = NetworkMode.WIFI
            logger.info("Currently connected to WiFi - ready for button control")
        else:
            self._current_mode = NetworkMode.UNKNOWN
            logger.info("No WiFi connectivity detected - ready for button control")
            logger.info("Use buttons to switch to WiFi or AP mode")
        
        # Notify initial status
        status = self.get_current_status()
        self._notify_status_change(status)
        
        logger.info("Network manager ready - automatic switching DISABLED")
        return True

# Global network manager instance
network_manager = NetworkManager() 