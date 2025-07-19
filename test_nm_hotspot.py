#!/usr/bin/env python3
"""
Test NetworkManager Native Hotspot
This replaces hostapd with NetworkManager's built-in AP functionality
"""

import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_command(command, suppress_errors=False):
    """Run a command and return success/output."""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=10
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

def create_nm_hotspot():
    """Create NetworkManager native hotspot."""
    logger.info("Creating NetworkManager hotspot...")
    
    # Remove any existing hotspot connections
    success, output = run_command("sudo nmcli connection show --active", suppress_errors=True)
    if "Hotspot" in output:
        logger.info("Removing existing hotspot...")
        run_command("sudo nmcli connection delete Hotspot", suppress_errors=True)
    
    # Create new hotspot using NetworkManager
    success, output = run_command(
        "sudo nmcli device wifi hotspot ssid InkyRemote password inkyremote123 ifname wlan0 band bg"
    )
    
    if success:
        logger.info("NetworkManager hotspot created successfully!")
        
        # Show connection details
        success, output = run_command("sudo nmcli connection show")
        logger.info(f"Active connections:\n{output}")
        
        # Show IP info
        success, output = run_command("ip addr show wlan0")
        logger.info(f"Interface info:\n{output}")
        
        return True
    else:
        logger.error(f"Failed to create hotspot: {output}")
        return False

def stop_nm_hotspot():
    """Stop NetworkManager hotspot."""
    logger.info("Stopping NetworkManager hotspot...")
    
    # Find and stop hotspot connection
    success, output = run_command("sudo nmcli connection show", suppress_errors=True)
    if "Hotspot" in output:
        success, output = run_command("sudo nmcli connection down Hotspot")
        if success:
            logger.info("Hotspot stopped successfully")
            return True
        else:
            logger.error(f"Failed to stop hotspot: {output}")
            return False
    else:
        logger.info("No active hotspot found")
        return True

def connect_to_wifi():
    """Connect to regular WiFi."""
    logger.info("Connecting to WiFi...")
    
    # Stop any hotspot first
    stop_nm_hotspot()
    
    # Let NetworkManager handle WiFi reconnection automatically
    # It should reconnect to saved networks
    time.sleep(5)
    
    # Check connection
    success, output = run_command("nmcli device status")
    logger.info(f"Device status:\n{output}")
    
    return True

def main():
    """Test NetworkManager hotspot functionality."""
    print("=== NetworkManager Native Hotspot Test ===")
    print()
    
    while True:
        print("Options:")
        print("1. Create hotspot")  
        print("2. Stop hotspot")
        print("3. Connect to WiFi")
        print("4. Show status")
        print("5. Exit")
        
        choice = input("Enter choice (1-5): ").strip()
        
        if choice == "1":
            create_nm_hotspot()
        elif choice == "2":
            stop_nm_hotspot()
        elif choice == "3":
            connect_to_wifi()
        elif choice == "4":
            success, output = run_command("nmcli device status")
            print(f"Device status:\n{output}")
            success, output = run_command("nmcli connection show")
            print(f"Connections:\n{output}")
        elif choice == "5":
            break
        else:
            print("Invalid choice")
        
        print()

if __name__ == "__main__":
    main() 