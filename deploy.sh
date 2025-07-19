#!/bin/bash

# Enhanced InkyRemote Deploy Script with Safety Features
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

cd /home/jweinhart/inkyremote

log "Starting InkyRemote deployment..."

# Check network connectivity before deploying
if ! ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
    warning "No internet connectivity detected"
    warning "Skipping git pull to avoid potential issues"
else
    log "Pulling latest changes from git..."
    git pull
    success "Git pull completed"
fi

# Make safety script executable
if [ -f network_safety.sh ]; then
    chmod +x network_safety.sh
    log "Made network_safety.sh executable"
fi

# Copy and enable services
log "Updating systemd services..."
sudo cp inkyremote.service /etc/systemd/system/
sudo systemctl daemon-reload

# Install WiFi backup cron job for additional safety
if [ -f wifi_backup_cron.sh ]; then
    log "Installing WiFi backup cron job..."
    sudo cp wifi_backup_cron.sh /usr/local/bin/
    sudo chmod +x /usr/local/bin/wifi_backup_cron.sh
    
    # Add to crontab if not already present
    if ! sudo crontab -l 2>/dev/null | grep -q "wifi_backup_cron.sh"; then
        (sudo crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/wifi_backup_cron.sh") | sudo crontab -
        success "WiFi backup cron job installed"
    else
        log "WiFi backup cron job already installed"
    fi
fi

success "Deployment completed successfully"

echo ""
warning "IMPORTANT SAFETY INFORMATION:"
echo "1. A WiFi backup cron job has been installed that runs every 5 minutes"
echo "2. If network issues occur, run: sudo bash network_safety.sh emergency-wifi"
echo "3. For full recovery: sudo bash network_safety.sh restore-config"
echo "4. Service logs: sudo journalctl -u inkyremote -f"
echo "5. WiFi backup logs: sudo tail -f /var/log/wifi-backup.log"
echo ""

log "Ready to restart service. Your current network connection should remain stable."
log "The system has multiple fallback mechanisms to prevent network lockout."