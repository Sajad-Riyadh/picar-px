#!/bin/bash
# Diagnostic script for WiFi client discovery issues

set -e

echo "🔍 WiFi Client Discovery Diagnostics"
echo "===================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (sudo $0)"
    exit 1
fi

# Check service status
echo "📊 Service Status:"
systemctl status picarx-unified.service --no-pager || echo "Service not running"
echo ""

# Check service capabilities
echo "🔐 Service Capabilities:"
systemctl show picarx-unified.service | grep -E "(CapabilityBoundingSet|AmbientCapabilities|DeviceAllow|User)" || echo "Could not retrieve capabilities"
echo ""

# Check network interfaces
echo "🌐 Network Interfaces:"
ip link show | grep -E "^[0-9]+: (wlan|eth)" || echo "No network interfaces found"
echo ""

# Check wlan1 specifically
echo "📡 wlan1 Status:"
if ip link show wlan1 &>/dev/null; then
    ip link show wlan1
    echo ""
    echo "📡 wlan1 Details:"
    iw dev wlan1 info 2>/dev/null || echo "Could not get wlan1 details"
else
    echo "❌ wlan1 interface not found"
fi
echo ""

# Check airodump-ng installation
echo "🔧 Aircrack-ng Installation:"
if which airodump-ng &>/dev/null; then
    echo "✅ airodump-ng found: $(which airodump-ng)"
    airodump-ng --help | head -5
else
    echo "❌ airodump-ng not found"
    echo "Install with: sudo apt-get install aircrack-ng"
fi
echo ""

# Check Python environment
echo "🐍 Python Environment:"
if [ -f "/root/picar-px/.venv/bin/python" ]; then
    echo "✅ Virtual environment found: /root/picar-px/.venv/bin/python"
    /root/picar-px/.venv/bin/python --version
    echo ""
    echo "📦 Python Packages:"
    /root/picar-px/.venv/bin/pip list | grep -E "(scapy|fastapi|uvicorn)" || echo "Could not list packages"
else
    echo "❌ Virtual environment not found"
fi
echo ""

# Test health endpoint
echo "🧪 Health Endpoint Test:"
if curl -s http://127.0.0.1:8080/api/health > /dev/null 2>&1; then
    echo "✅ Health endpoint responding"
    curl -s http://127.0.0.1:8080/api/health | head -10
else
    echo "❌ Health endpoint not responding"
fi
echo ""

# Test monitor mode manually
echo "🔬 Monitor Mode Test:"
echo "Attempting to set wlan1 to monitor mode..."
if ip link set wlan1 down 2>/dev/null && iw dev wlan1 set type monitor 2>/dev/null && ip link set wlan1 up 2>/dev/null; then
    echo "✅ Successfully set monitor mode"
    iw dev wlan1 info | grep -E "(type|channel)" || echo "Could not verify monitor mode"

    # Reset to managed mode
    echo "Resetting to managed mode..."
    ip link set wlan1 down 2>/dev/null && iw dev wlan1 set type managed 2>/dev/null && ip link set wlan1 up 2>/dev/null
    echo "✅ Reset to managed mode"
else
    echo "❌ Failed to set monitor mode"
    echo "This might indicate missing capabilities or permissions"
fi
echo ""

# Check service logs
echo "📋 Recent Service Logs:"
journalctl -u picarx-unified.service -n 20 --no-pager || echo "Could not retrieve logs"
echo ""

# Test airodump-ng manually
echo "🧪 Manual Airodump-ng Test:"
echo "Running airodump-ng for 5 seconds..."
timeout 5 airodump-ng --bssid 04:95:E6:19:DE:B1 -c 1 wlan1 2>&1 | head -10 || echo "airodump-ng test failed"
echo ""

# Summary
echo "📝 Summary:"
echo "=========="
echo "If you see issues above, here are common fixes:"
echo ""
echo "1. Service not running:"
echo "   sudo systemctl start picarx-unified.service"
echo ""
echo "2. Missing capabilities:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl restart picarx-unified.service"
echo ""
echo "3. airodump-ng not found:"
echo "   sudo apt-get install aircrack-ng"
echo ""
echo "4. Monitor mode fails:"
echo "   Check service capabilities in systemd service file"
echo "   Ensure CAP_NET_ADMIN and CAP_NET_RAW are set"
echo ""
echo "5. Health endpoint not responding:"
echo "   Check service logs: journalctl -u picarx-unified.service -f"
echo "   Restart service: sudo systemctl restart picarx-unified.service"
echo ""
echo "🔍 For detailed logs:"
echo "   journalctl -u picarx-unified.service -f"
echo ""
echo "🧪 To test client discovery:"
echo "   curl -X POST http://127.0.0.1:8080/api/jammer/discover_clients \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"bssid\": \"04:95:E6:19:DE:B1\", \"channel\": 1, \"duration\": 10}'"