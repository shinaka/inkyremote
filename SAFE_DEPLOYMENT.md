# Safe Deployment Guide 🛡️

This guide ensures you can safely deploy the WiFi/AP switching features without losing access to your headless Pi Zero W2.

## ⚠️ **BEFORE YOU START**

Your concern about getting locked out is valid! This guide provides **multiple safety layers** to prevent that.

## 🔒 **Safety Mechanisms Included**

1. **WiFi Backup Cron Job**: Runs every 5 minutes, automatically restores WiFi if connection is lost
2. **Network Watchdog Service**: Monitors network health and performs emergency recovery
3. **Configuration Backup**: Your current network settings are saved for rollback
4. **Staged Testing**: Test network switching before full deployment
5. **Emergency Recovery Commands**: Multiple ways to recover if things go wrong

## 📋 **Safe Deployment Steps**

### Step 1: Run the Safety Setup
```bash
# Make scripts executable
chmod +x network_safety.sh
chmod +x setup_network.sh

# Install safety mechanisms FIRST
sudo bash network_safety.sh safe-deploy
```

**What this does:**
- Backs up your current network configuration
- Installs a network watchdog service
- Tests WiFi/AP switching safely (30-second test)
- Only proceeds if tests pass

### Step 2: Check Safety Status
```bash
sudo bash network_safety.sh status
```

You should see:
- ✅ Network backup available
- ✅ Network watchdog service running  
- ✅ Internet connectivity: OK

### Step 3: Deploy with Enhanced Safety
```bash
# This now includes WiFi backup cron job
./deploy.sh

# Restart service with monitoring
sudo systemctl restart inkyremote

# Monitor for any issues
sudo journalctl -u inkyremote -f
```

## 🆘 **Recovery Options**

### If You Lose Network Access

**Option 1: Automatic Recovery**
- **Wait 5 minutes** - the WiFi backup cron job should restore connectivity
- **Wait 6 minutes** - the network watchdog should kick in

**Option 2: Manual Recovery via SSH** (if you can still connect)
```bash
# Emergency WiFi restoration
sudo bash network_safety.sh emergency-wifi

# Or full configuration restore
sudo bash network_safety.sh restore-config
```

**Option 3: Physical Access Recovery**
If you need to connect keyboard/monitor to the Pi:
```bash
# Kill all network management
sudo systemctl stop inkyremote
sudo systemctl stop hostapd  
sudo systemctl stop dnsmasq

# Restart basic networking
sudo systemctl restart dhcpcd
sudo systemctl restart wpa_supplicant

# Check status
iwconfig wlan0
ip addr show wlan0
```

## 🧪 **Testing Before Deployment**

### Test Network Switching Safely
```bash
# This tests AP mode for 30 seconds then restores WiFi
sudo bash network_safety.sh test-switching
```

### Test Individual Components
```bash
# Test button handler (safe - read-only)
python3 button_handler.py

# Test display manager (safe - just shows test message)
python3 display_manager.py

# Check network manager status (safe - read-only)
python3 -c "from network_manager import network_manager; print(network_manager.get_current_status())"
```

## 📊 **Monitoring Tools**

### Check Safety Status
```bash
sudo bash network_safety.sh status
```

### View Logs
```bash
# Main service logs
sudo journalctl -u inkyremote -f

# Network watchdog logs  
sudo journalctl -u network-recovery -f

# WiFi backup cron logs
sudo tail -f /var/log/wifi-backup.log

# System network logs
sudo journalctl -u dhcpcd -f
```

### Check What's Running
```bash
# Network services status
sudo systemctl status inkyremote
sudo systemctl status network-recovery
sudo systemctl status hostapd
sudo systemctl status dnsmasq

# Current network state
iwconfig wlan0
ip addr show wlan0
```

## 🎯 **Recommended Deployment Process**

1. **Start with safety setup**:
   ```bash
   sudo bash network_safety.sh safe-deploy
   ```

2. **If that succeeds**, deploy normally:
   ```bash
   ./deploy.sh
   sudo systemctl restart inkyremote
   ```

3. **Monitor for 5 minutes**:
   ```bash
   # Watch logs and test connectivity
   sudo journalctl -u inkyremote -f
   ```

4. **Test button functionality**:
   - Press Button B to show network status on display
   - This confirms the system is working

## 🔧 **Configuration Files Backed Up**

The safety script backs up:
- `/etc/dhcpcd.conf`
- `/etc/wpa_supplicant/wpa_supplicant.conf`
- Current WiFi connection details
- Network routes and interface configuration

## 📞 **Emergency Contacts** 

If you get completely locked out:

1. **Physical access**: Connect keyboard + monitor
2. **Recovery commands**: Use the commands in "Option 3" above
3. **Nuclear option**: Reflash SD card with backup image

## ✅ **Verification Steps**

After deployment, verify:

```bash
# 1. Service is running
sudo systemctl is-active inkyremote

# 2. Network connectivity maintained
ping -c 3 8.8.8.8

# 3. Safety mechanisms active
sudo systemctl is-active network-recovery
sudo crontab -l | grep wifi_backup

# 4. Button test (optional)
python3 button_handler.py  # Press buttons to test

# 5. Web interface accessible
curl -s http://$(hostname -I | awk '{print $1}'):5000 > /dev/null && echo "Web interface OK"
```

## 🎉 **You're Protected!**

With these safety mechanisms, you have **multiple layers of protection**:

- ⏰ **Every 5 minutes**: WiFi backup check
- ⏰ **Every 2 minutes**: Network watchdog check  
- 🔄 **Automatic recovery**: If network fails
- 💾 **Configuration backup**: For manual restore
- 🚨 **Emergency commands**: For manual intervention

**The chance of getting completely locked out is extremely low** with all these safety nets in place! 