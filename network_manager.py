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
        """Start Access Point mode."""
        logger.info("Starting Access Point mode...")
        self._current_mode = NetworkMode.TRANSITIONING
        
        try:
            # Stop any existing WiFi connections
            self._run_command("sudo wpa_cli -i wlan0 disconnect", suppress_errors=True)
            time.sleep(2)
            
            # Configure static IP for AP mode
            success, _ = self._run_command(
                f"sudo ip addr flush dev {self.wifi_interface}"
            )
            if not success:
                logger.error("Failed to flush interface")
                return False
                
            success, _ = self._run_command(
                f"sudo ip addr add 192.168.4.1/24 dev {self.wifi_interface}"
            )
            if not success:
                logger.error("Failed to set static IP")
                return False
            
            # Start hostapd
            success, _ = self._run_command("sudo systemctl start hostapd")
            if not success:
                logger.error("Failed to start hostapd")
                return False
            
            # Start dnsmasq
            success, _ = self._run_command("sudo systemctl start dnsmasq")
            if not success:
                logger.error("Failed to start dnsmasq")
                # Stop hostapd if dnsmasq failed
                self._run_command("sudo systemctl stop hostapd", suppress_errors=True)
                return False
            
            # Enable IP forwarding
            self._run_command("sudo sysctl net.ipv4.ip_forward=1", suppress_errors=True)
            
            self._current_mode = NetworkMode.AP
            logger.info("Access Point mode started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error starting Access Point: {e}")
            self._current_mode = NetworkMode.UNKNOWN
            return False
    
    def stop_access_point(self) -> bool:
        """Stop Access Point mode."""
        logger.info("Stopping Access Point mode...")
        self._current_mode = NetworkMode.TRANSITIONING
        
        try:
            # Stop services
            self._run_command("sudo systemctl stop hostapd", suppress_errors=True)
            self._run_command("sudo systemctl stop dnsmasq", suppress_errors=True)
            
            # Flush IP configuration
            self._run_command(f"sudo ip addr flush dev {self.wifi_interface}", suppress_errors=True)
            
            logger.info("Access Point mode stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping Access Point: {e}")
            return False
    
    def connect_to_wifi(self) -> bool:
        """Attempt to connect to WiFi."""
        logger.info("Attempting to connect to WiFi...")
        self._current_mode = NetworkMode.TRANSITIONING
        
        try:
            # Stop AP mode if running
            if self._current_mode == NetworkMode.AP:
                self.stop_access_point()
            
            # Restart networking services (adapt for dhclient system)
            success, _ = self._run_command("sudo systemctl restart networking")
            if not success:
                # Try dhclient directly if networking service fails
                self._run_command("sudo dhclient -r wlan0", suppress_errors=True)
                success, _ = self._run_command("sudo dhclient wlan0")
                if not success:
                    logger.warning("Failed to restart networking services")
            
            # Wait a moment for networking to initialize
            time.sleep(3)
            
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
            return NetworkStatus(
                mode=NetworkMode.AP,
                ssid=self.ap_ssid,
                ip_address="192.168.4.1",
                connected_clients=self.get_ap_clients(),
                is_internet_available=False
            )
        else:
            return NetworkStatus(mode=self._current_mode)
    
    def switch_to_ap_mode(self, manual: bool = False) -> bool:
        """Switch to Access Point mode."""
        if manual:
            self._manual_ap_mode = True
        
        if self._current_mode == NetworkMode.AP:
            logger.info("Already in AP mode")
            return True
            
        success = self.start_access_point()
        if success:
            status = self.get_current_status()
            self._notify_status_change(status)
        return success
    
    def switch_to_wifi_mode(self) -> bool:
        """Switch to WiFi mode."""
        self._manual_ap_mode = False
        
        if self._current_mode == NetworkMode.WIFI and self.check_wifi_connectivity():
            logger.info("Already connected to WiFi")
            return True
            
        success = self.connect_to_wifi()
        if success:
            status = self.get_current_status()
            self._notify_status_change(status)
        return success
    
    def toggle_mode(self) -> bool:
        """Toggle between WiFi and AP mode."""
        if self._current_mode == NetworkMode.WIFI:
            return self.switch_to_ap_mode(manual=True)
        else:
            return self.switch_to_wifi_mode()
    
    def _monitoring_loop(self):
        """Background monitoring loop."""
        logger.info("Network monitoring started")
        
        while self._should_monitor:
            try:
                # Skip monitoring if in manual AP mode
                if self._manual_ap_mode:
                    time.sleep(self.check_interval)
                    continue
                
                # Check current connectivity
                wifi_connected = self.check_wifi_connectivity()
                
                if wifi_connected and self._current_mode != NetworkMode.WIFI:
                    # WiFi is available but we're not using it
                    logger.info("WiFi connectivity detected, switching from AP mode")
                    if self.connect_to_wifi():
                        status = self.get_current_status()
                        self._notify_status_change(status)
                
                elif not wifi_connected and self._current_mode == NetworkMode.WIFI:
                    # WiFi lost, switch to AP mode
                    logger.info("WiFi connectivity lost, switching to AP mode")
                    if self.start_access_point():
                        status = self.get_current_status()
                        self._notify_status_change(status)
                
                elif self._current_mode == NetworkMode.UNKNOWN:
                    # Try to determine current state
                    if wifi_connected:
                        self._current_mode = NetworkMode.WIFI
                    else:
                        # Try to start AP mode
                        self.start_access_point()
                    
                    status = self.get_current_status()
                    self._notify_status_change(status)
                
                # Periodic status update
                status = self.get_current_status()
                self._notify_status_change(status)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            time.sleep(self.check_interval)
        
        logger.info("Network monitoring stopped")
    
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
        """Initialize network manager and determine current state."""
        logger.info("Initializing NetworkManager...")
        
        # Check current state
        if self.check_wifi_connectivity():
            self._current_mode = NetworkMode.WIFI
            logger.info("Currently connected to WiFi")
        else:
            logger.info("No WiFi connectivity, starting AP mode")
            if self.start_access_point():
                self._current_mode = NetworkMode.AP
            else:
                logger.error("Failed to initialize any network mode")
                return False
        
        # Notify initial status
        status = self.get_current_status()
        self._notify_status_change(status)
        
        return True

# Global network manager instance
network_manager = NetworkManager() 