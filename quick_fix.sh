#!/bin/bash

# Quick fix for NetworkManager hotspot setup
# Skips problematic packages and focuses on core functionality

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

log "=== Quick NetworkManager Hotspot Fix ==="

# The GPIO library issue doesn't affect NetworkManager hotspot functionality
warning "Skipping python3-gpiod installation (not critical for hotspot)"

# Test NetworkManager hotspot functionality
log "Testing NetworkManager hotspot support..."

if command -v nmcli >/dev/null && nmcli device wifi hotspot --help >/dev/null 2>&1; then
    success "NetworkManager hotspot support confirmed"
else
    echo "ERROR: NetworkManager hotspot command not available"
    exit 1
fi

# Check if wlan0 device exists
if nmcli device status | grep -q wlan0; then
    success "wlan0 device found"
else
    warning "wlan0 device not found - but continuing anyway"
fi

# Test basic hotspot creation (will clean up immediately)
log "Testing hotspot creation..."
if sudo nmcli device wifi hotspot ssid TestHotspot password testpass123 ifname wlan0 band bg; then
    success "Hotspot creation test successful!"
    
    # Clean up test hotspot immediately
    log "Cleaning up test hotspot..."
    sudo nmcli connection down Hotspot 2>/dev/null || true
    sudo nmcli connection delete Hotspot 2>/dev/null || true
    success "Test cleanup complete"
else
    echo "ERROR: Hotspot creation failed"
    exit 1
fi

log ""
success "=== NetworkManager Hotspot Setup Complete ==="
log ""
log "Next steps:"
log "1. Test the hotspot: sudo python3 test_nm_hotspot.py"
log "2. Restart InkyRemote: sudo systemctl restart inkyremote.service"
log "3. Press Button A to test hotspot mode"
log ""
log "Your hotspot will be:"
log "- SSID: InkyRemote"
log "- Password: inkyremote123" 