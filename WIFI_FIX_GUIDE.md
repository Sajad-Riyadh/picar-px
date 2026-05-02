# WiFi Client Discovery Fix - Deployment Guide

## Problem Summary

Passive WiFi client discovery was working when running the application manually but failing when running via systemd service. The issue was caused by missing Linux capabilities in the systemd service configuration.

## Root Cause Analysis

### Manual Execution (Working)
When running manually with `python -m picarx_unified`, the process inherits the full capabilities of the user shell, including:
- `CAP_NET_RAW`: Required for raw socket access and packet capture
- `CAP_NET_ADMIN`: Required for network interface configuration (monitor mode)
- Ability to run `sudo` commands for network operations

### Systemd Service (Broken - Before Fix)
The systemd service was running as root but missing critical capabilities:
- No `CAP_NET_RAW` → Cannot create raw sockets for packet capture
- No `CAP_NET_ADMIN` → Cannot configure network interfaces (monitor mode)
- `sudo` commands don't work the same way in systemd services
- Restricted capability bounding set by default

## Changes Made

### 1. Systemd Service File (`/etc/systemd/system/picarx-unified.service`)

**Added Capabilities:**
```ini
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
```

**Added Device Access:**
```ini
DeviceAllow=network rw
```

**Removed Restrictions:**
```ini
NoNewPrivileges=false
```

**Updated Paths:**
```ini
WorkingDirectory=/root/picar-px
EnvironmentFile=-/root/picar-px/.env
Environment=PATH=/root/picar-px/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/root/picar-px/.venv/bin/python -m picarx_unified
```

### 2. Python Code (`src/picarx_unified/attacks/wifi_jammer.py`)

**Removed `sudo` commands** since the service now runs with proper capabilities:

**Before:**
```python
subprocess.run(["sudo", "airodump-ng", ...])
subprocess.run(["sudo", "ip", "link", "set", ...])
subprocess.run(["sudo", "iw", "dev", ...])
```

**After:**
```python
subprocess.run(["airodump-ng", ...])
subprocess.run(["ip", "link", "set", ...])
subprocess.run(["iw", "dev", ...])
```

## Deployment Instructions

### Option 1: Automated Deployment (Recommended)

```bash
# Copy files to your PiCar-X
scp -r Picar-px root@<pi-ip>:/root/

# SSH into the PiCar-X
ssh root@<pi-ip>

# Navigate to project directory
cd /root/picar-px

# Run deployment script
chmod +x scripts/deploy_wifi_fix.sh
sudo bash scripts/deploy_wifi_fix.sh
```

### Option 2: Manual Deployment

```bash
# SSH into your PiCar-X
ssh root@<pi-ip>

# Navigate to project directory
cd /root/picar-px

# Backup existing service file
sudo cp /etc/systemd/system/picarx-unified.service /root/picar-px/backups/picarx-unified.service.bak

# Copy updated service file
sudo cp deploy/picarx-unified.service /etc/systemd/system/picarx-unified.service

# Reload systemd
sudo systemctl daemon-reload

# Restart service
sudo systemctl restart picarx-unified.service

# Check status
sudo systemctl status picarx-unified.service
```

## Verification Steps

### 1. Check Service Status

```bash
sudo systemctl status picarx-unified.service
```

**Expected output:** Service should be `active (running)` without errors.

### 2. Verify Capabilities

```bash
sudo systemctl show picarx-unified.service | grep -E "(CapabilityBoundingSet|AmbientCapabilities)"
```

**Expected output:**
```
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
```

### 3. Test Health Endpoint

```bash
curl http://127.0.0.1:8080/api/health
```

**Expected output:** JSON response with `ok: true`

### 4. Test WiFi Client Discovery

```bash
curl -X POST http://127.0.0.1:8080/api/jammer/discover_clients \
  -H "Content-Type: application/json" \
  -d '{"bssid": "04:95:E6:19:DE:B1", "channel": 1, "duration": 25}'
```

**Expected output:** JSON response with discovered clients, e.g.:
```json
{
  "clients": [
    {
      "mac": "7E:14:F4:E1:E8:28",
      "bssid": "04:95:E6:19:DE:B1",
      "signal_strength": -45,
      "is_robot_device": false
    },
    {
      "mac": "0E:17:D9:91:43:EC",
      "bssid": "04:95:E6:19:DE:B1",
      "signal_strength": -52,
      "is_robot_device": false
    }
  ],
  "count": 2
}
```

### 5. Check Service Logs

```bash
sudo journalctl -u picarx-unified.service -f
```

**Look for:**
- `Successfully set wlan1 to monitor mode`
- `Discovered X clients for AP 04:95:E6:19:DE:B1`
- No permission denied errors

### 6. Manual Verification (Compare with Manual Execution)

```bash
# Stop the service
sudo systemctl stop picarx-unified.service

# Run manually
cd /root/picar-px
source .venv/bin/activate
python -m picarx_unified

# Test client discovery via browser or curl
# Should work the same as systemd service

# Stop manual execution and restart service
sudo systemctl start picarx-unified.service
```

## Troubleshooting

### Issue: Service fails to start

**Check logs:**
```bash
sudo journalctl -u picarx-unified.service -n 50
```

**Common causes:**
- Wrong working directory in service file
- Python executable path incorrect
- Missing dependencies

### Issue: Client discovery still returns empty

**Check network interface:**
```bash
ip link show wlan1
iw dev wlan1 info
```

**Test monitor mode manually:**
```bash
sudo ip link set wlan1 down
sudo iw dev wlan1 set type monitor
sudo ip link set wlan1 up
sudo timeout 10 airodump-ng --bssid 04:95:E6:19:DE:B1 -c 1 wlan1
```

**Check airodump-ng installation:**
```bash
which airodump-ng
airodump-ng --help
```

### Issue: Permission denied errors

**Verify capabilities:**
```bash
sudo systemctl show picarx-unified.service | grep Capability
```

**Check if running as root:**
```bash
ps aux | grep picarx_unified
```

### Issue: Interface stuck in monitor mode

**Reset interface:**
```bash
sudo ip link set wlan1 down
sudo iw dev wlan1 set type managed
sudo ip link set wlan1 up
```

## Technical Details

### Linux Capabilities Explained

**CAP_NET_RAW:**
- Allows creation of raw sockets
- Required for packet capture and injection
- Essential for airodump-ng and Scapy operations

**CAP_NET_ADMIN:**
- Allows network interface configuration
- Required for monitor mode switching
- Needed for channel changes and interface management

**CAP_NET_BIND_SERVICE:**
- Allows binding to privileged ports (< 1024)
- Useful for network services

### Why Manual Execution Worked

When you run `python -m picarx_unified` manually:
1. The process inherits capabilities from your shell
2. If you're root or in sudoers, `sudo` commands work
3. No capability restrictions apply by default

### Why Systemd Failed

Systemd services by default:
1. Run with minimal capability set
2. Don't inherit full root capabilities
3. Have restricted device access
4. `sudo` doesn't work the same way

### The Fix

By adding explicit capabilities to the systemd service:
1. Service can perform network operations without sudo
2. Raw socket access is available for packet capture
3. Interface configuration works for monitor mode
4. Device access is granted for network hardware

## Testing Checklist

- [ ] Service starts successfully
- [ ] Service status shows `active (running)`
- [ ] Health endpoint responds correctly
- [ ] WiFi scan returns networks
- [ ] Client discovery returns clients
- [ ] No permission errors in logs
- [ ] Monitor mode can be set/reset
- [ ] Results match manual execution
- [ ] Service restarts correctly after crash
- [ ] Capabilities are properly configured

## Rollback Instructions

If you need to rollback the changes:

```bash
# Stop service
sudo systemctl stop picarx-unified.service

# Restore backup service file
sudo cp /root/picar-px/backups/picarx-unified.service.bak /etc/systemd/system/picarx-unified.service

# Reload systemd
sudo systemctl daemon-reload

# Restart service
sudo systemctl start picarx-unified.service

# Check status
sudo systemctl status picarx-unified.service
```

## Additional Resources

- **Systemd Capabilities:** https://www.freedesktop.org/software/systemd/man/systemd.exec.html
- **Linux Capabilities:** http://man7.org/linux/man-pages/man7/capabilities.7.html
- **Aircrack-ng Documentation:** https://www.aircrack-ng.org/doku.php
- **WiFi Monitor Mode:** https://wiki.wireshark.org/CaptureSetup/WLAN

## Support

If issues persist after applying this fix:

1. Check service logs: `sudo journalctl -u picarx-unified.service -n 100`
2. Verify network hardware: `ip link show`, `iw dev`
3. Test airodump-ng manually: `sudo airodump-ng wlan1`
4. Check Python environment: `source .venv/bin/activate && python -c "import scapy; print('Scapy OK')"`
5. Review this guide and troubleshooting section

## Summary

This fix resolves the WiFi client discovery issue by:

1. ✅ Adding necessary Linux capabilities to systemd service
2. ✅ Removing dependency on `sudo` commands in Python code
3. ✅ Updating paths to match actual installation location
4. ✅ Adding device access permissions for network hardware
5. ✅ Removing capability restrictions that prevented network operations

The service now has the same network capabilities as manual execution, ensuring consistent behavior across both run modes.