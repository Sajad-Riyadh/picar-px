# Quick Fix Deployment Guide

## 🚀 Issue: "Empty reply from server" when calling client discovery endpoint

This error occurs because the API endpoint was defined as GET but you're calling it as POST. I've fixed this issue along with adding better error handling.

## 📋 Files Changed

1. **`src/picarx_unified/app.py`**
   - Changed endpoint from GET to POST
   - Added proper JSON body parsing
   - Added comprehensive error handling

2. **`src/picarx_unified/attacks/wifi_jammer.py`**
   - Enhanced error handling and logging
   - Better subprocess management
   - Improved monitor mode/channel setting with verification

3. **`deploy/picarx-unified.service`**
   - Added network capabilities (from previous fix)

## 🔧 Deployment Steps

### Option 1: Copy Files Manually (Quick)

```bash
# On your PiCar-X, copy these files from your development machine:

# 1. Copy updated Python files
scp src/picarx_unified/app.py root@<pi-ip>:/root/picar-px/src/picarx_unified/
scp src/picarx_unified/attacks/wifi_jammer.py root@<pi-ip>:/root/picarx_unified/attacks/

# 2. SSH into PiCar-X
ssh root@<pi-ip>

# 3. Restart service
cd /root/picar-px
systemctl restart picarx-unified.service

# 4. Wait 5 seconds for service to start
sleep 5

# 5. Test the endpoint
curl -X POST http://127.0.0.1:8080/api/jammer/discover_clients \
  -H "Content-Type: application/json" \
  -d '{"bssid": "04:95:E6:19:DE:B1", "channel": 1, "duration": 10}'
```

### Option 2: Full Deployment (Recommended)

```bash
# Copy entire project to PiCar-X
scp -r Picar-px root@<pi-ip>:/root/

# SSH into PiCar-X
ssh root@<pi-ip>

# Run deployment script
cd /root/picar-px
chmod +x scripts/deploy_wifi_fix.sh
bash scripts/deploy_wifi_fix.sh
```

## ✅ Verification

### 1. Check Service Status
```bash
systemctl status picarx-unified.service
```
Should show: `active (running)`

### 2. Test Health Endpoint
```bash
curl http://127.0.0.1:8080/api/health
```
Should return JSON with `"ok": true`

### 3. Test Client Discovery (Fixed Endpoint)
```bash
curl -X POST http://127.0.0.1:8080/api/jammer/discover_clients \
  -H "Content-Type: application/json" \
  -d '{"bssid": "04:95:E6:19:DE:B1", "channel": 1, "duration": 10}'
```

Should return JSON like:
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
  "count": 1,
  "bssid": "04:95:E6:19:DE:B1"
}
```

## 🔍 Diagnostics

If issues persist, run the diagnostic script:

```bash
bash /root/picar-px/scripts/diagnose_wifi.sh
```

This will check:
- Service status and capabilities
- Network interfaces
- airodump-ng installation
- Monitor mode functionality
- Service logs

## 📋 Viewing Logs

```bash
# Follow logs in real-time
journalctl -u picarx-unified.service -f

# View last 50 lines
journalctl -u picarx-unified.service -n 50

# View logs since service start
journalctl -u picarx-unified.service -b
```

## 🐛 Common Issues

### Issue: Service fails to start
```bash
# Check logs
journalctl -u picarx-unified.service -n 50

# Restart service
systemctl restart picarx-unified.service
```

### Issue: "Empty reply from server" persists
```bash
# 1. Verify service is running
systemctl status picarx-unified.service

# 2. Check health endpoint
curl http://127.0.0.1:8080/api/health

# 3. Check for Python errors in logs
journalctl -u picarx-unified.service -n 100 | grep -i error
```

### Issue: No clients discovered
```bash
# 1. Run diagnostics
bash /root/picar-px/scripts/diagnose_wifi.sh

# 2. Test airodump-ng manually
sudo ip link set wlan1 down
sudo iw dev wlan1 set type monitor
sudo ip link set wlan1 up
sudo timeout 10 airodump-ng --bssid 04:95:E6:19:DE:B1 -c 1 wlan1

# 3. Reset interface
sudo ip link set wlan1 down
sudo iw dev wlan1 set type managed
sudo ip link set wlan1 up
```

### Issue: Permission denied errors
```bash
# Check service capabilities
systemctl show picarx-unified.service | grep Capability

# Should show:
# CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
# AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE
```

## 🎯 Key Changes Explained

### 1. API Endpoint Fix
**Before:**
```python
@app.get("/api/jammer/discover_clients")
async def jammer_discover_clients(request: Request, bssid: str, channel: int, duration: int = 25):
```

**After:**
```python
@app.post("/api/jammer/discover_clients")
async def jammer_discover_clients(request: Request, body: dict):
    bssid = body.get("bssid")
    channel = body.get("channel")
    duration = body.get("duration", 25)
```

### 2. Enhanced Error Handling
- Added comprehensive logging at each step
- Better subprocess timeout handling
- Verification of monitor mode and channel setting
- Proper cleanup in finally blocks

### 3. Improved Process Management
- Better handling of airodump-ng termination
- Multiple fallback attempts for process cleanup
- Proper error messages for debugging

## 📞 Support

If you still have issues after applying these fixes:

1. Run diagnostics: `bash /root/picar-px/scripts/diagnose_wifi.sh`
2. Check logs: `journalctl -u picarx-unified.service -n 100`
3. Verify all files are copied correctly
4. Ensure service has proper capabilities

## 🔄 Testing Checklist

- [ ] Service starts without errors
- [ ] Health endpoint responds
- [ ] Client discovery endpoint responds (not empty)
- [ ] No "Empty reply from server" errors
- [ ] Logs show successful monitor mode setting
- [ ] Logs show airodump-ng execution
- [ ] Clients are discovered (if any are present)

## 📝 Summary

The main issue was that the API endpoint was defined as GET with query parameters, but you were calling it as POST with a JSON body. This has been fixed, and I've also added comprehensive error handling and logging to help diagnose any remaining issues.

After deploying these changes, the client discovery endpoint should work correctly and return proper JSON responses instead of "Empty reply from server".