#!/bin/bash

# WiFi Backup Recovery Cron Job
# This runs every 5 minutes to ensure WiFi connectivity
# Simple fallback mechanism if main network management fails

LOGFILE="/var/log/wifi-backup.log"
LOCKFILE="/tmp/wifi-backup.lock"

# Exit if already running
if [ -f "$LOCKFILE" ]; then
    exit 0
fi

# Create lock file
echo $$ > "$LOCKFILE"

# Cleanup on exit
cleanup() {
    rm -f "$LOCKFILE"
}
trap cleanup EXIT

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOGFILE"
}

# Check if WiFi is connected
check_wifi() {
    # Check for IP address on wlan0
    if ip addr show wlan0 | grep -q "inet.*scope global"; then
        # Check internet connectivity
        if ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1; then
            return 0  # WiFi is working
        fi
    fi
    return 1  # WiFi is not working
}

# Simple WiFi recovery
recover_wifi() {
    log_msg "BACKUP RECOVERY: Attempting WiFi restore"
    
    # Stop potentially conflicting services
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    
    # Flush interface to clean state
    ip addr flush dev wlan0 2>/dev/null || true
    
    # Restart networking services
    systemctl restart wpa_supplicant
    systemctl restart networking
    
    # Also try dhclient directly
    dhclient -r wlan0 2>/dev/null || true
    dhclient wlan0 2>/dev/null || true
    
    # Wait and check
    sleep 15
    
    if check_wifi; then
        log_msg "BACKUP RECOVERY: WiFi restored successfully"
        return 0
    else
        log_msg "BACKUP RECOVERY: WiFi restore failed"
        return 1
    fi
}

# Main logic
if ! check_wifi; then
    log_msg "WiFi connectivity lost - attempting backup recovery"
    recover_wifi
else
    # Log successful check (once per hour to avoid spam)
    MINUTE=$(date +%M)
    if [ "$MINUTE" = "00" ]; then
        log_msg "WiFi connectivity check: OK"
    fi
fi

# Keep log file reasonable size (last 100 lines)
if [ -f "$LOGFILE" ] && [ $(wc -l < "$LOGFILE") -gt 100 ]; then
    tail -n 50 "$LOGFILE" > "${LOGFILE}.tmp"
    mv "${LOGFILE}.tmp" "$LOGFILE"
fi 