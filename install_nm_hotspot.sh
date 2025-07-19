#!/bin/bash

# NetworkManager Native Hotspot Setup for InkyRemote
# Simple installation without hostapd/dnsmasq complexity

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "Please run as root (use sudo)"
        exit 1
    fi
}

install_network_manager() {
    log "Installing NetworkManager..."
    
    # Update package list
    apt update
    
    # Install NetworkManager if not present
    if ! dpkg -l | grep -q network-manager; then
        log "Installing network-manager..."
        apt install -y network-manager
    else
        log "NetworkManager already installed"
    fi
    
    # Ensure NetworkManager is enabled and started
    systemctl enable NetworkManager
    systemctl start NetworkManager
    
    success "NetworkManager installed and running"
}

configure_sudo_permissions() {
    log "Configuring sudo permissions for NetworkManager..."
    
    # Get the actual username (not root, even when run with sudo)
    if [ -n "$SUDO_USER" ]; then
        USERNAME="$SUDO_USER"
    else
        USERNAME=$(logname 2>/dev/null || echo "pi")
    fi
    
    log "Setting up permissions for user: $USERNAME"
    
    # Create sudoers file for NetworkManager hotspot commands
    cat > /etc/sudoers.d/inkyremote-network << EOF
# Allow inkyremote user to manage NetworkManager without password
$USERNAME ALL=(root) NOPASSWD: /usr/bin/nmcli device wifi hotspot *
$USERNAME ALL=(root) NOPASSWD: /usr/bin/nmcli connection down *
$USERNAME ALL=(root) NOPASSWD: /usr/bin/nmcli connection delete *
$USERNAME ALL=(root) NOPASSWD: /usr/bin/nmcli connection show *
$USERNAME ALL=(root) NOPASSWD: /usr/bin/nmcli device disconnect *
$USERNAME ALL=(root) NOPASSWD: /usr/bin/nmcli device set *
$USERNAME ALL=(root) NOPASSWD: /sbin/dhclient *
$USERNAME ALL=(root) NOPASSWD: /sbin/ip *
$USERNAME ALL=(root) NOPASSWD: /usr/sbin/wpa_cli *
$USERNAME ALL=(root) NOPASSWD: /bin/systemctl start wpa_supplicant
$USERNAME ALL=(root) NOPASSWD: /bin/systemctl stop wpa_supplicant
$USERNAME ALL=(root) NOPASSWD: /bin/systemctl restart wpa_supplicant
$USERNAME ALL=(root) NOPASSWD: /bin/systemctl start networking
$USERNAME ALL=(root) NOPASSWD: /bin/systemctl stop networking
$USERNAME ALL=(root) NOPASSWD: /bin/systemctl restart networking
EOF

    success "Sudo permissions configured for $USERNAME"
}

install_python_deps() {
    log "Installing Python dependencies..."
    
    # Install Python packages
    apt install -y python3 python3-pip python3-venv
    
    # Install system packages for GPIO
    apt install -y python3-gpiod python3-pil python3-flask python3-requests
    
    success "Python dependencies installed"
}

test_networkmanager_hotspot() {
    log "Testing NetworkManager hotspot functionality..."
    
    # Test if we can create a hotspot
    if nmcli device wifi hotspot --help >/dev/null 2>&1; then
        success "NetworkManager hotspot support confirmed"
    else
        warning "NetworkManager hotspot command not available"
        return 1
    fi
    
    # Check if device supports AP mode
    if iw list 2>/dev/null | grep -q "AP"; then
        success "WiFi device supports AP mode"
    else
        warning "WiFi device AP mode support unclear"
    fi
}

main() {
    log "=== NetworkManager Native Hotspot Setup ==="
    log "This script sets up NetworkManager native hotspot for InkyRemote"
    log ""
    
    check_root
    install_network_manager
    configure_sudo_permissions
    install_python_deps
    test_networkmanager_hotspot
    
    log ""
    success "=== Installation Complete ==="
    log ""
    log "Next steps:"
    log "1. Test the hotspot: sudo python3 test_nm_hotspot.py"
    log "2. If that works, restart InkyRemote service: sudo systemctl restart inkyremote.service"
    log "3. Use Button A to toggle between WiFi and Hotspot modes"
    log ""
    log "The hotspot will use:"
    log "- SSID: InkyRemote"  
    log "- Password: inkyremote123"
    log "- Connect via phone/laptop to access http://[hotspot-ip]:5000"
}

# Handle different command line arguments
case "${1:-install}" in
    "install")
        main
        ;;
    "test")
        test_networkmanager_hotspot
        ;;
    "permissions")
        check_root
        configure_sudo_permissions
        ;;
    *)
        echo "Usage: $0 [install|test|permissions]"
        echo "  install     - Full installation (default)"
        echo "  test        - Test NetworkManager hotspot support"
        echo "  permissions - Configure sudo permissions only"
        exit 1
        ;;
esac 