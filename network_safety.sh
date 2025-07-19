#!/bin/bash

# InkyRemote Network Safety & Recovery Script
# This script provides safety mechanisms to prevent network lockout

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')] $1${NC}"; }
error() { echo -e "${RED}[ERROR] $1${NC}"; }
warning() { echo -e "${YELLOW}[WARNING] $1${NC}"; }
success() { echo -e "${GREEN}[SUCCESS] $1${NC}"; }

# Configuration
BACKUP_DIR="/home/jweinhart/network_backup"
SAFETY_SERVICE="network-recovery.service"

show_help() {
    echo "InkyRemote Network Safety Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  backup-config    - Backup current network configuration"
    echo "  restore-config   - Restore network configuration from backup"
    echo "  install-watchdog - Install network watchdog service"
    echo "  test-switching   - Safely test network switching (non-disruptive)"
    echo "  test-full        - Full network switching test (disconnects SSH!)"
    echo "  emergency-wifi   - Force WiFi reconnection"
    echo "  safe-deploy      - Deploy with safety checks"
    echo "  status          - Show network safety status"
    echo ""
}

backup_network_config() {
    log "Backing up network configuration..."
    
    mkdir -p "$BACKUP_DIR"
    
    # Backup key network files
    if [ -f /etc/dhcpcd.conf ]; then
        cp /etc/dhcpcd.conf "$BACKUP_DIR/dhcpcd.conf.backup"
    fi
    
    if [ -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
        cp /etc/wpa_supplicant/wpa_supplicant.conf "$BACKUP_DIR/wpa_supplicant.conf.backup"
    fi
    
    # Save current WiFi connection details
    iwconfig wlan0 > "$BACKUP_DIR/wifi_status.txt" 2>/dev/null || true
    ip route > "$BACKUP_DIR/routes.txt"
    ip addr show wlan0 > "$BACKUP_DIR/interface.txt"
    
    success "Network configuration backed up to $BACKUP_DIR"
}

restore_network_config() {
    log "Restoring network configuration from backup..."
    
    if [ ! -d "$BACKUP_DIR" ]; then
        error "No backup found in $BACKUP_DIR"
        exit 1
    fi
    
    # Stop network management services
    systemctl stop inkyremote || true
    systemctl stop hostapd || true
    systemctl stop dnsmasq || true
    
    # Restore configuration files
    if [ -f "$BACKUP_DIR/dhcpcd.conf.backup" ]; then
        cp "$BACKUP_DIR/dhcpcd.conf.backup" /etc/dhcpcd.conf
        log "Restored dhcpcd.conf"
    fi
    
    if [ -f "$BACKUP_DIR/wpa_supplicant.conf.backup" ]; then
        cp "$BACKUP_DIR/wpa_supplicant.conf.backup" /etc/wpa_supplicant/wpa_supplicant.conf
        log "Restored wpa_supplicant.conf"
    fi
    
    # Restart networking
    systemctl restart networking
    systemctl restart wpa_supplicant
    
    # Try dhclient directly as backup
    dhclient -r wlan0 2>/dev/null || true
    dhclient wlan0 2>/dev/null || true
    
    success "Network configuration restored. Rebooting in 5 seconds..."
    sleep 5
    reboot
}

install_watchdog() {
    log "Installing network watchdog service..."
    
    # Create watchdog script
    cat > /usr/local/bin/network-watchdog.sh << 'EOF'
#!/bin/bash

# Network Recovery Watchdog
# Ensures WiFi connectivity is restored if network management fails

LOGFILE="/var/log/network-watchdog.log"
MAX_FAILURES=3
FAILURE_COUNT=0

log_msg() {
    echo "$(date): $1" >> "$LOGFILE"
}

check_connectivity() {
    # Check if we can reach the internet
    if ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1; then
        return 0
    fi
    
    # Check if we have a local IP
    if ip addr show wlan0 | grep -q "inet.*scope global"; then
        return 0
    fi
    
    return 1
}

emergency_wifi_restore() {
    log_msg "EMERGENCY: Attempting WiFi restore"
    
    # Stop potentially problematic services
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    
    # Reset interface completely
    ip link set wlan0 down 2>/dev/null || true
    ip addr flush dev wlan0 2>/dev/null || true
    ip link set wlan0 up 2>/dev/null || true
    
    # Re-enable WiFi in NetworkManager and restart services
    nmcli device set wlan0 managed yes 2>/dev/null || true
    nmcli radio wifi on 2>/dev/null || true
    systemctl restart networking
    systemctl restart wpa_supplicant
    
    # Wait for connection
    sleep 10
    
    if check_connectivity; then
        log_msg "EMERGENCY: WiFi restored successfully"
        return 0
    else
        log_msg "EMERGENCY: WiFi restore failed"
        return 1
    fi
}

# Main watchdog loop
while true; do
    if ! check_connectivity; then
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        log_msg "Connectivity check failed ($FAILURE_COUNT/$MAX_FAILURES)"
        
        if [ $FAILURE_COUNT -ge $MAX_FAILURES ]; then
            log_msg "Maximum failures reached, attempting emergency restore"
            
            if emergency_wifi_restore; then
                FAILURE_COUNT=0
            else
                log_msg "Emergency restore failed, will retry in next cycle"
            fi
        fi
    else
        if [ $FAILURE_COUNT -gt 0 ]; then
            log_msg "Connectivity restored, resetting failure count"
            FAILURE_COUNT=0
        fi
    fi
    
    # Check every 2 minutes
    sleep 120
done
EOF

    chmod +x /usr/local/bin/network-watchdog.sh
    
    # Create systemd service
    cat > /etc/systemd/system/network-recovery.service << 'EOF'
[Unit]
Description=Network Recovery Watchdog
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/network-watchdog.sh
Restart=always
RestartSec=30
User=root

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=network-watchdog

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable network-recovery.service
    systemctl start network-recovery.service
    
    success "Network watchdog installed and started"
}

test_network_switching() {
    log "Starting safe network switching test..."
    
    # Check current connectivity
    if ! ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1; then
        error "No internet connectivity - cannot safely test network switching"
        exit 1
    fi
    
    success "Current WiFi connection is working"
    
    # Non-disruptive test - just check if services can start
    log "Testing AP services (non-disruptive)..."
    
    # Test if hostapd config is valid
    if hostapd -t /etc/hostapd/hostapd.conf >/dev/null 2>&1; then
        success "hostapd configuration is valid"
    else
        error "hostapd configuration is invalid"
        return 1
    fi
    
    # Test if dnsmasq config is valid  
    if dnsmasq --test >/dev/null 2>&1; then
        success "dnsmasq configuration is valid"
    else
        error "dnsmasq configuration is invalid"
        return 1
    fi
    
    # Test if services can start (without disrupting network)
    log "Testing if services can start..."
    
    # Quick start/stop test
    if systemctl start hostapd && sleep 2 && systemctl is-active --quiet hostapd; then
        success "hostapd can start successfully"
        systemctl stop hostapd
    else
        error "hostapd cannot start"
        return 1
    fi
    
    if systemctl start dnsmasq && sleep 2 && systemctl is-active --quiet dnsmasq; then
        success "dnsmasq can start successfully" 
        systemctl stop dnsmasq
    else
        error "dnsmasq cannot start"
        return 1
    fi
    
    success "All AP services tested successfully (non-disruptive)"
    log "Note: Full network switching will work, but would disconnect your SSH session"
    return 0
}

test_network_switching_full() {
    log "Starting FULL network switching test (will disconnect SSH!)..."
    
    # Check current connectivity
    if ! ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1; then
        error "No internet connectivity - cannot safely test network switching"
        exit 1
    fi
    
    success "Current WiFi connection is working"
    
    # Test AP mode temporarily - THIS WILL DISCONNECT SSH
    log "Testing AP mode for 30 seconds (you will be disconnected)..."
    
    # Start AP mode services
    systemctl start hostapd
    systemctl start dnsmasq
    
    # Set static IP
    ip addr add 192.168.4.1/24 dev wlan0 2>/dev/null || true
    
    sleep 5
    
    # Check if AP is running and log to file for later review
    if systemctl is-active --quiet hostapd; then
        echo "$(date): AP mode activated successfully" >> /var/log/network-test.log
        
        # Show AP status
        iw dev wlan0 info >> /var/log/network-test.log 2>&1 || true
        
        # Wait
        echo "$(date): AP mode running for 30 seconds..." >> /var/log/network-test.log
        sleep 30
        
        # Restore WiFi
        echo "$(date): Restoring WiFi mode..." >> /var/log/network-test.log
        systemctl stop hostapd
        systemctl stop dnsmasq
        
        # Reset interface completely
        ip link set wlan0 down
        ip addr flush dev wlan0
        ip link set wlan0 up
        
        # Re-enable WiFi in NetworkManager and restart services
        nmcli device set wlan0 managed yes 2>/dev/null || true
        nmcli radio wifi on 2>/dev/null || true
        systemctl restart networking  
        systemctl restart wpa_supplicant
        
        # Try dhclient directly as backup
        dhclient -r wlan0 2>/dev/null || true
        dhclient wlan0 2>/dev/null || true
        
        # Wait for WiFi restoration
        echo "$(date): Waiting for WiFi restoration..." >> /var/log/network-test.log
        for i in {1..20}; do
            if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
                echo "$(date): WiFi restored successfully after $i attempts" >> /var/log/network-test.log
                return 0
            fi
            sleep 3
        done
        
        echo "$(date): Failed to restore WiFi - manual intervention required" >> /var/log/network-test.log
        return 1
    else
        echo "$(date): Failed to start AP mode" >> /var/log/network-test.log
        return 1
    fi
}

emergency_wifi_fix() {
    log "Performing emergency WiFi restoration..."
    
    # Stop all network management
    systemctl stop inkyremote 2>/dev/null || true
    systemctl stop hostapd 2>/dev/null || true  
    systemctl stop dnsmasq 2>/dev/null || true
    
    # Kill any Python network processes
    pkill -f "network_manager.py" 2>/dev/null || true
    pkill -f "button_handler.py" 2>/dev/null || true
    
    # Completely reset network interface
    ip link set wlan0 down 2>/dev/null || true
    ip addr flush dev wlan0 2>/dev/null || true
    ip route flush dev wlan0 2>/dev/null || true
    ip link set wlan0 up 2>/dev/null || true
    
    # Re-enable WiFi in NetworkManager and restart services
    nmcli device set wlan0 managed yes 2>/dev/null || true
    nmcli radio wifi on 2>/dev/null || true
    systemctl restart networking
    systemctl restart wpa_supplicant
    
    # Try dhclient directly
    dhclient -r wlan0 2>/dev/null || true
    dhclient wlan0 2>/dev/null || true
    
    # Wait for connection
    log "Waiting for WiFi connection..."
    for i in {1..30}; do
        if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
            success "Emergency WiFi restoration successful after $i attempts"
            ip addr show wlan0
            return 0
        fi
        sleep 2
    done
    
    error "Emergency WiFi restoration failed"
    log "Manual recovery steps:"
    echo "1. Connect keyboard/monitor to Pi"
    echo "2. Check 'sudo iwconfig wlan0'"  
    echo "3. Restart networking: 'sudo systemctl restart dhcpcd'"
    echo "4. Check WiFi config: 'sudo nano /etc/wpa_supplicant/wpa_supplicant.conf'"
    return 1
}

safe_deploy() {
    log "Starting safe deployment process..."
    
    # Step 1: Backup
    backup_network_config
    
    # Step 2: Install watchdog
    install_watchdog
    
    # Step 3: Test network switching
    if test_network_switching; then
        success "Network switching test passed"
    else
        error "Network switching test failed - aborting deployment"
        exit 1
    fi
    
    # Step 4: Deploy with staged restart
    log "Deploying InkyRemote service..."
    
    # Update service file
    cp inkyremote.service /etc/systemd/system/
    systemctl daemon-reload
    
    # Restart service with monitoring
    log "Restarting InkyRemote service (monitoring for 60 seconds)..."
    systemctl restart inkyremote
    
    # Monitor for issues
    for i in {1..12}; do
        if systemctl is-active --quiet inkyremote; then
            if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
                success "Service running and network connectivity maintained"
                break
            else
                warning "Service running but network connectivity lost - continuing monitoring..."
            fi
        else
            error "Service failed to start"
            emergency_wifi_fix
            exit 1
        fi
        
        sleep 5
    done
    
    success "Safe deployment completed successfully"
    log "Network watchdog is running as backup protection"
}

show_status() {
    log "Network Safety Status"
    echo ""
    
    # Check if backup exists
    if [ -d "$BACKUP_DIR" ]; then
        success "Network backup available in $BACKUP_DIR"
    else
        warning "No network backup found"
    fi
    
    # Check watchdog service
    if systemctl is-active --quiet network-recovery; then
        success "Network watchdog service is running"
    else
        warning "Network watchdog service not running"
    fi
    
    # Check current connectivity
    if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
        success "Internet connectivity: OK"
    else
        error "Internet connectivity: FAILED"
    fi
    
    # Show WiFi status
    echo ""
    log "Current WiFi status:"
    iwconfig wlan0 2>/dev/null || echo "WiFi interface not available"
    
    echo ""
    log "Current IP address:"
    ip addr show wlan0 | grep "inet " || echo "No IP address assigned"
}

# Main command handler
case "${1:-}" in
    "backup-config")
        backup_network_config
        ;;
    "restore-config")
        restore_network_config
        ;;
    "install-watchdog")
        install_watchdog
        ;;
    "test-switching")
        test_network_switching
        ;;
    "test-full")
        test_network_switching_full
        ;;
    "emergency-wifi")
        emergency_wifi_fix
        ;;
    "safe-deploy")
        safe_deploy
        ;;
    "status")
        show_status
        ;;
    "help"|"--help"|"-h"|"")
        show_help
        ;;
    *)
        error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac 