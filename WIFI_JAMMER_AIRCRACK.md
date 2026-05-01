# WiFi Jammer - Aircrack-ng Integration

## Overview
The WiFi Jammer has been enhanced to use the **Aircrack-ng suite** for reliable network scanning and client discovery. This is the industry-standard tool for wireless network security testing.

## What's New

### 1. **Aircrack-ng Integration**
- **Network Scanning**: Uses `airodump-ng` for comprehensive WiFi network discovery
- **Client Discovery**: Uses `airodump-ng` to detect connected devices on target networks
- **Better Results**: More accurate network and client information compared to basic tools

### 2. **Improved Network Scanning**
```python
# Old method: Basic iw scan
# New method: Comprehensive airodump-ng scan
```
- Captures more network details (encryption, signal strength, channel)
- Better detection of hidden networks
- More reliable signal strength measurements

### 3. **Enhanced Client Discovery**
```python
# Old method: Limited iw station dump
# New method: Full airodump-ng client capture
```
- Discovers all clients connected to a target network
- Captures signal strength for each client
- Identifies and protects robot's own device
- Proper MAC address validation

### 4. **Automatic Installation**
The installation script now automatically installs Aircrack-ng:
```bash
bash scripts/install_pi.sh
```

## Manual Installation

If you need to install Aircrack-ng manually:

```bash
sudo apt update
sudo apt install aircrack-ng
```

## Usage

### Scan for Networks
1. Go to the WiFi Jammer panel
2. Click "Scan for Networks"
3. Wait for the scan to complete (default 10 seconds)
4. View discovered networks with signal strength and encryption

### Discover Clients on a Network
1. Select "Client Deauth (Specific Devices)" mode
2. Choose a network from the dropdown
3. Click "Discover Clients"
4. Wait for client discovery (10 seconds)
5. Select specific clients to target
6. Robot's device is automatically protected

### Attack Modes
- **Mass Deauth**: Attack multiple selected networks
- **Targeted Deauth**: Attack a specific network by BSSID
- **Client Deauth**: Attack specific devices on a network

## Technical Details

### Aircrack-ng Tools Used
- **airodump-ng**: Network scanning and client discovery
- **Monitor Mode**: Required for wireless packet capture
- **CSV Output**: Structured data parsing for network/client information

### File Structure
```
src/picarx_unified/attacks/wifi_jammer.py  # Main implementation
scripts/install_pi.sh                       # Auto-installs aircrack-ng
```

### Key Functions
- `_check_aircrack_ng()`: Verifies Aircrack-ng installation
- `scan_networks()`: Uses airodump-ng for network discovery
- `_discover_clients()`: Uses airodump-ng for client discovery
- `_set_monitor_mode()`: Enables monitor mode for packet capture

## Safety Features

1. **Robot Protection**: Automatically detects and protects robot's network and device
2. **MAC Validation**: Proper MAC address format validation
3. **Error Handling**: Graceful fallback if Aircrack-ng is not available
4. **Legal Warnings**: Clear warnings about authorized use only

## Troubleshooting

### "No clients found on this network"
- Ensure you're in monitor mode
- Check that aircrack-ng is installed: `which airodump-ng`
- Try increasing scan duration
- Verify the target network has active clients

### "airodump-ng not found"
```bash
sudo apt install aircrack-ng
```

### Permission Issues
```bash
# Add user to netdev group for wireless operations
sudo usermod -a -G netdev $USER
```

## Legal Disclaimer

⚠️ **IMPORTANT**: This tool is for educational and authorized security testing purposes only.

- Only use on networks you own or have explicit written permission to test
- Unauthorized use is illegal and unethical
- Users are solely responsible for their actions
- Always comply with local laws and regulations

## References

- [Aircrack-ng Official Documentation](https://www.aircrack-ng.org/doku.php)
- [WiFi Security Testing Best Practices](https://www.aircrack-ng.org/doku.php?id=tutorials)
- [IEEE 802.11 Standards](https://standards.ieee.org/)