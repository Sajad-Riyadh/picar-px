# WiFi Client Discovery Fix - Quick Reference

## 🚀 Quick Deployment

```bash
# Copy files to PiCar-X
scp -r Picar-px root@<pi-ip>:/root/

# SSH and deploy
ssh root@<pi-ip>
cd /root/picar-px
chmod +x scripts/deploy_wifi_fix.sh
sudo bash scripts/deploy_wifi_fix.sh
```

## ✅ Verification Commands

```bash
# Check service status
sudo systemctl status picarx-unified.service

# Verify capabilities
sudo systemctl show picarx-unified.service | grep -E "(CapabilityBoundingSet|AmbientCapabilities)"

# Test health endpoint
curl http://127.0.0.1:8080/api/health

# Test client discovery
curl -X POST http://127.0.0.1:8080/api/jammer/discover_clients \
  -H "Content-Type: application/json" \
  -d '{"bssid": "04:95:E6:19:DE:B1", "channel": 1, "duration": 25}'

# View logs
sudo journalctl -u picarx-unified.service -f
```

## 🔧 Key Changes

### Systemd Service
- Added `CAP_NET_RAW`, `CAP_NET_ADMIN`, `CAP_NET_BIND_SERVICE`
- Added `DeviceAllow=network rw`
- Removed `NoNewPrivileges` restriction
- Updated paths to `/root/picar-px`

### Python Code
- Removed all `sudo` commands from subprocess calls
- Service now runs with proper capabilities

## 🐛 Troubleshooting

```bash
# Check service logs
sudo journalctl -u picarx-unified.service -n 50

# Verify network interface
ip link show wlan1
iw dev wlan1 info

# Test monitor mode manually
sudo ip link set wlan1 down
sudo iw dev wlan1 set type monitor
sudo ip link set wlan1 up
sudo timeout 10 airodump-ng --bssid 04:95:E6:19:DE:B1 -c 1 wlan1

# Reset interface
sudo ip link set wlan1 down
sudo iw dev wlan1 set type managed
sudo ip link set wlan1 up
```

## 🔄 Service Management

```bash
# Restart service
sudo systemctl restart picarx-unified.service

# Stop service
sudo systemctl stop picarx-unified.service

# Start service
sudo systemctl start picarx-unified.service

# Enable on boot
sudo systemctl enable picarx-unified.service

# Disable on boot
sudo systemctl disable picarx-unified.service
```

## 📋 Expected Results

### Service Status
```
● picarx-unified.service - PiCar-X Unified Control Stack
   Loaded: loaded (/etc/systemd/system/picarx-unified.service; enabled)
   Active: active (running) since ...
```

### Capabilities
```
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
```

### Client Discovery Response
```json
{
  "clients": [
    {
      "mac": "7E:14:F4:E1:E8:28",
      "bssid": "04:95:E6:19:DE:B1",
      "signal_strength": -45,
      "is_robot_device": false
    }
  ],
  "count": 1
}
```

## 📁 Files Modified

1. `/etc/systemd/system/picarx-unified.service` - Systemd service configuration
2. `src/picarx_unified/attacks/wifi_jammer.py` - Removed sudo commands
3. `scripts/deploy_wifi_fix.sh` - Deployment script
4. `WIFI_FIX_GUIDE.md` - Comprehensive guide

## ⚠️ Important Notes

- Service must run as root for network capabilities
- Monitor mode requires `CAP_NET_ADMIN` capability
- Packet capture requires `CAP_NET_RAW` capability
- Manual execution and systemd service should now behave identically
- Backup created automatically during deployment

## 🆘 Still Having Issues?

1. Check full deployment guide: `WIFI_FIX_GUIDE.md`
2. Review service logs: `sudo journalctl -u picarx-unified.service -n 100`
3. Test airodump-ng manually: `sudo airodump-ng wlan1`
4. Verify Python environment: `source .venv/bin/activate && python -c "import scapy"`
5. Check network hardware: `ip link show`, `iw dev`

## 🎯 Success Indicators

✅ Service starts without errors
✅ Health endpoint responds
✅ WiFi scan returns networks
✅ Client discovery returns clients
✅ No permission denied errors
✅ Monitor mode works correctly
✅ Results match manual execution