#!/bin/bash

# Disable All Network Monitoring for Button-Only Control
# This script stops and disables all automatic network switching

set -e

log() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

success() {
    echo -e "\033[0;32m[SUCCESS]\033[0m $1"
}

warning() {
    echo -e "\033[1;33m[WARNING]\033[0m $1"
}

log "=== Disabling All Network Monitoring ==="
log "Converting to pure button control mode"
log ""

# Stop and disable network recovery watchdog
if systemctl is-active --quiet network-recovery.service 2>/dev/null; then
    log "Stopping network-recovery.service..."
    sudo systemctl stop network-recovery.service
    success "network-recovery.service stopped"
else
    log "network-recovery.service not running"
fi

if systemctl is-enabled --quiet network-recovery.service 2>/dev/null; then
    log "Disabling network-recovery.service..."
    sudo systemctl disable network-recovery.service
    success "network-recovery.service disabled"
else
    log "network-recovery.service not enabled"
fi

# Stop and disable any WiFi backup cron
if crontab -l 2>/dev/null | grep -q wifi_backup_cron.sh; then
    log "Removing WiFi backup cron job..."
    crontab -l | grep -v wifi_backup_cron.sh | crontab -
    success "WiFi backup cron removed"
else
    log "No WiFi backup cron found"
fi

# Ensure old hostapd/dnsmasq services are disabled (if they exist)
for service in hostapd dnsmasq; do
    if systemctl list-unit-files | grep -q "^$service.service"; then
        if systemctl is-enabled --quiet $service.service 2>/dev/null; then
            log "Disabling $service.service..."
            sudo systemctl disable $service.service
            success "$service.service disabled"
        fi
        if systemctl is-active --quiet $service.service 2>/dev/null; then
            log "Stopping $service.service..."
            sudo systemctl stop $service.service
            success "$service.service stopped"
        fi
    fi
done

log ""
success "=== All Network Monitoring Disabled ==="
log ""
log "Your InkyRemote is now in pure button control mode:"
log "- Button A: Toggle between WiFi and AP modes"
log "- Button B: Show network status"
log "- Button C: Force WiFi mode"
log "- Button D: Force AP mode"
log ""
log "No automatic switching will occur!"
log "Restart InkyRemote to activate: sudo systemctl restart inkyremote.service" 