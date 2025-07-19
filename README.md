# InkyRemote - WiFi & Access Point Management

InkyRemote is a Flask-based web interface for managing images on a Spectra6 E-Ink display with Pi Zero W2. This enhanced version includes automatic WiFi/Access Point switching functionality.

## Features

### Core Features
- **Image Upload & Management**: Upload, crop, and display images on E-Ink display
- **Web Interface**: Modern, responsive web UI for remote management
- **Image Processing**: Automatic cropping, resizing, and optimization for E-Ink displays

### Network Management Features ✨ **NEW**
- **Automatic WiFi Fallback**: Automatically switches to AP mode when home WiFi is unavailable
- **Manual Mode Switching**: Use physical buttons or web interface to change network modes
- **Visual Feedback**: Network status displayed on E-Ink screen with real-time updates
- **Dual Network Modes**:
  - **WiFi Mode**: Connects to your existing WiFi network
  - **AP Mode**: Creates "InkyRemote" access point for direct connection

## Hardware Requirements

- Raspberry Pi Zero W2
- Pimoroni Spectra6 E-Ink Display (800x480)
- MicroSD card (16GB+ recommended)
- Power supply (5V 2.5A recommended)

## Network Modes

### WiFi Mode
- Connects to your existing WiFi network
- Full internet access available
- Access via your home network IP address

### Access Point Mode  
- Creates "InkyRemote" WiFi network
- **SSID**: `InkyRemote`
- **Password**: `inkyremote123`
- **IP Address**: `192.168.4.1`
- **Access URL**: `http://192.168.4.1:5000`

## Installation

### 1. Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd inkyremote

# Run the network setup script
sudo bash setup_network.sh
```

### 2. Deploy the Service

```bash
# Update deployment script to include new files
./deploy.sh

# Enable and start the service
sudo systemctl enable inkyremote.service
sudo systemctl start inkyremote.service
```

### 3. Reboot

```bash
sudo reboot
```

## Usage

### Physical Button Controls

The E-Ink display has 4 buttons with the following functions:

| Button | Action | Function |
|--------|--------|----------|
| **A** | Single Press | Toggle between WiFi and AP mode |
| **B** | Single Press | Show network status on display |
| **C** | Hold 1 second | Force WiFi mode |
| **D** | Hold 1 second | Force Access Point mode |

### Web Interface Controls

Access the web interface at:
- **WiFi Mode**: `http://<pi-ip-address>:5000`
- **AP Mode**: `http://192.168.4.1:5000`

The web interface includes:
- Network status display in header
- Network control buttons
- Original image management features

### API Endpoints

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/api/network/status` | GET | Get current network status |
| `/api/network/toggle` | POST | Toggle network mode |
| `/api/network/wifi` | POST | Switch to WiFi mode |
| `/api/network/ap` | POST | Switch to AP mode |
| `/network/status` | GET | Display network status on E-Ink |

## Network Behavior

### Automatic Fallback
- System starts in WiFi mode by default
- If WiFi connection fails, automatically switches to AP mode
- Periodically retries WiFi connection when in AP mode
- Manual AP mode prevents automatic switching back to WiFi

### Manual Control
- Button A: Quick toggle between modes
- Hold Button C/D: Force specific mode
- Web interface: Control via buttons or API calls

## Troubleshooting

### Network Issues

**WiFi not connecting:**
```bash
# Check WiFi status
iwconfig wlan0

# Check network manager logs
sudo journalctl -u inkyremote -f

# Restart network services
sudo systemctl restart dhcpcd
```

**AP mode not working:**
```bash
# Check hostapd status
sudo systemctl status hostapd

# Check dnsmasq status  
sudo systemctl status dnsmasq

# View hostapd logs
sudo journalctl -u hostapd -f
```

**Button not responding:**
```bash
# Test button functionality
cd /home/jweinhart/inkyremote
python3 button_handler.py

# Check GPIO permissions
groups $USER  # Should include 'gpio'
```

### Service Issues

**Service not starting:**
```bash
# Check service status
sudo systemctl status inkyremote

# View service logs
sudo journalctl -u inkyremote -f

# Restart service
sudo systemctl restart inkyremote
```

**Permission errors:**
```bash
# Check sudoers configuration
sudo visudo -f /etc/sudoers.d/inkyremote-network

# Verify file permissions
ls -la /home/jweinhart/inkyremote/
```

## File Structure

```
inkyremote/
├── inkyremote.py           # Main Flask application
├── network_manager.py      # WiFi/AP switching logic
├── button_handler.py       # Physical button management
├── display_manager.py      # E-Ink display control
├── setup_network.sh        # Network setup script
├── inkyremote.service      # Systemd service file
├── deploy.sh              # Deployment script
├── static/
│   ├── uploads/           # Uploaded images
│   └── thumbnails/        # Image thumbnails
└── templates/
    └── index.html         # Web interface template
```

## Configuration Files

| File | Purpose |
|------|---------|
| `/etc/hostapd/hostapd.conf` | Access Point configuration |
| `/etc/dnsmasq.conf` | DHCP server configuration |
| `/etc/sudoers.d/inkyremote-network` | Network management permissions |
| `/etc/iptables/rules.v4` | Firewall rules |

## Development

### Testing Components

**Test button handler:**
```bash
cd /home/jweinhart/inkyremote
python3 button_handler.py
```

**Test display manager:**
```bash
python3 display_manager.py
```

**Test network manager:**
```bash
python3 -c "from network_manager import network_manager; print(network_manager.get_current_status())"
```

### Adding New Features

1. Network callbacks: Register with `network_manager.add_status_callback()`
2. Button actions: Add new `ButtonAction` enum values
3. Display screens: Create new display functions in `display_manager.py`

## Security Notes

- Change default AP password in `/etc/hostapd/hostapd.conf`
- Consider enabling SSH key authentication
- Review iptables rules for your security requirements
- The service runs with limited privileges for security

## License

This project is open source. Please check the license file for details.

## Contributing

Contributions are welcome! Please submit pull requests with:
- Clear description of changes
- Testing on actual hardware
- Documentation updates

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review service logs: `sudo journalctl -u inkyremote -f`
3. Test components individually
4. Submit issues with full error logs 