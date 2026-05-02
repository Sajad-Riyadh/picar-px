#!/bin/bash
# Deployment script for WiFi client discovery fix
# This script updates the systemd service and Python code for proper network capabilities

set -e

echo "🔧 Deploying WiFi client discovery fix..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (sudo $0)"
    exit 1
fi

# Define paths
PROJECT_DIR="/root/picar-px"
SERVICE_FILE="/etc/systemd/system/picarx-unified.service"
BACKUP_DIR="/root/picar-px/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup existing service file
if [ -f "$SERVICE_FILE" ]; then
    echo "📦 Backing up existing service file..."
    cp "$SERVICE_FILE" "$BACKUP_DIR/picarx-unified.service.$TIMESTAMP.bak"
fi

# Copy updated service file
echo "📄 Installing updated systemd service file..."
cp "$PROJECT_DIR/deploy/picarx-unified.service" "$SERVICE_FILE"

# Verify the service file was updated
if [ -f "$SERVICE_FILE" ]; then
    echo "✅ Service file installed successfully"
else
    echo "❌ Failed to install service file"
    exit 1
fi

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

# Check if the service exists and is enabled
if systemctl is-enabled --quiet picarx-unified.service; then
    echo "🔄 Restarting picarx-unified service..."
    systemctl restart picarx-unified.service

    # Wait for service to start
    echo "⏳ Waiting for service to start..."
    sleep 5

    # Check service status
    echo "📊 Service status:"
    systemctl status picarx-unified.service --no-pager

    # Check if service is running
    if systemctl is-active --quiet picarx-unified.service; then
        echo "✅ Service is running successfully"
    else
        echo "❌ Service failed to start"
        echo "📋 Recent logs:"
        journalctl -u picarx-unified.service -n 20 --no-pager
        exit 1
    fi
else
    echo "⚠️  Service is not enabled. Enabling..."
    systemctl enable picarx-unified.service
    systemctl start picarx-unified.service

    # Wait for service to start
    echo "⏳ Waiting for service to start..."
    sleep 5

    # Check service status
    echo "📊 Service status:"
    systemctl status picarx-unified.service --no-pager
fi

# Test the health endpoint
echo "🧪 Testing health endpoint..."
if curl -s http://127.0.0.1:8080/api/health > /dev/null; then
    echo "✅ Health endpoint responding"
else
    echo "❌ Health endpoint not responding"
    echo "📋 Recent logs:"
    journalctl -u picarx-unified.service -n 20 --no-pager
    exit 1
fi

# Display service capabilities
echo "🔐 Service capabilities:"
systemctl show picarx-unified.service | grep -E "(CapabilityBoundingSet|AmbientCapabilities|DeviceAllow)"

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📝 Summary of changes:"
echo "  • Added CAP_NET_RAW capability for raw socket access"
echo "  • Added CAP_NET_ADMIN capability for network interface configuration"
echo "  • Added CAP_NET_BIND_SERVICE capability for network binding"
echo "  • Added DeviceAllow for network device access"
echo "  • Removed NoNewPrivileges restriction"
echo "  • Updated working directory to /root/picar-px"
echo "  • Removed sudo commands from Python code (now runs with proper capabilities)"
echo "  • Fixed API endpoint to accept POST requests with JSON body"
echo "  • Added comprehensive error handling and logging"
echo ""
echo "🧪 To test WiFi client discovery:"
echo "  curl -X POST http://127.0.0.1:8080/api/jammer/discover_clients \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"bssid\": \"04:95:E6:19:DE:B1\", \"channel\": 1, \"duration\": 10}'"
echo ""
echo "🔍 To run diagnostics:"
echo "  bash /root/picar-px/scripts/diagnose_wifi.sh"
echo ""
echo "📋 To view logs:"
echo "  journalctl -u picarx-unified.service -f"
echo ""
echo "🔄 To restart service:"
echo "  systemctl restart picarx-unified.service"
echo ""
echo "⚠️  If issues persist, check:"
echo "  • Service logs: journalctl -u picarx-unified.service -n 50"
echo "  • Network interface: ip link show wlan1"
echo "  • Monitor mode: iw dev wlan1 info | grep type"
echo "  • Run diagnostics: bash /root/picar-px/scripts/diagnose_wifi.sh"